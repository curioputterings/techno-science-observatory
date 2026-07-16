"""Publications layer — research output by country × domain, from OpenAlex.

An INDEPENDENT third signal to triangulate the Gemini estimates and ATS counts.
Jobs reveal current hiring; publications reveal accumulated research capacity.
Where they agree, confidence is high; where they diverge, something interesting.

OpenAlex is free (polite pool via mailto), METERED since 2026-07: free daily budget
is $0.10/day with no key or $1/day (~10,000 requests) with a free API key, resets
midnight UTC, enforced via 429s carrying a long Retry-After. Set OPENALEX_API_KEY
in .env (see below).

We fetch all country counts for a domain-year in ONE group_by call (~30 calls/run):
    works?filter=default.search:<q>,<dates>&group_by=authorships.countries
Counts verified 2026-07-16 identical to the old per-country sweep (per-page=1,
meta.count), which stays as the fallback. NB: group_by must NOT be sent with
per-page — per-page caps its output to N groups (per-page=1 -> one group), which was
the long-misdiagnosed "group_by collapses" bug (it was never the query). A
budget-exhaustion 429 raises BudgetExhausted and aborts the whole run; resume later
with --skip-existing.

Counts are written as cells with source='publications', precision='counted'
(they are real counts), mapped to the shared 0..5 volume band so they sit
alongside the other layers in the same country×domain panel.

    python3 research_sources/publications.py            # last full year, 9 domains
    python3 research_sources/publications.py --year 2024
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import socket
socket.setdefaulttimeout(35)  # hard backstop: no urlopen can hang past this

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import taxonomy  # noqa: E402
from gemini_client import load_env  # noqa: E402
from research import TARGET_COUNTRIES  # noqa: E402  (reuse the country set)
from store import Store  # noqa: E402

API = "https://api.openalex.org/works"
# Polite pool needs a REAL, reachable mailto or OpenAlex throttles you into the
# common pool (sustained 429s on a long run). Read it from .env (gitignored) so
# the address stays out of the public repo; placeholder is a last resort.
MAILTO = load_env().get("OPENALEX_MAILTO", "research@example.org")
# A FREE registered API key raises the metered daily budget 10x: $0.10/day (no key,
# polite pool only) -> $1/day (~10,000 requests) — enough for a full multi-year
# rebuild in one day. Get one at openalex.org/settings/api and put it in .env as
# OPENALEX_API_KEY. Sent as &api_key= in _get(); absent = graceful no-op ($0.10/day).
API_KEY = load_env().get("OPENALEX_API_KEY", "").strip()
# Seconds between calls = PACING + random jitter in [0, JITTER]. The jitter breaks
# the rhythmic call pattern that rate-limiters fingerprint; raise via env for a very
# slow, throttle-safe run (a 30x30x5 burst at 0.4s once earned a sustained 429).
PACING = float(load_env().get("OPENALEX_PACING", "1.0"))
JITTER = float(load_env().get("OPENALEX_JITTER", "0.5"))
LOG = ROOT / "data" / "research" / "publications_run.log"

# Academic search phrasing per domain (publications use different language than
# job ads). Kept tight to avoid false positives; OR-joined via the | operator.
DOMAIN_QUERIES: dict[str, str] = {
    # --- Semiconductors ---
    "chip_design": "\"integrated circuit design\" OR \"VLSI\" OR \"RTL\" OR \"chip design\" OR \"ASIC\"",
    "memory_devices": "\"DRAM\" OR \"NAND flash\" OR \"non-volatile memory\" OR \"memory device\" OR \"SRAM\"",
    "advanced_packaging": "\"advanced packaging\" OR \"chiplet\" OR \"heterogeneous integration\" OR \"through-silicon via\" OR \"2.5D integration\"",
    "semi_equipment": "\"photolithography\" OR \"EUV lithography\" OR \"plasma etching\" OR \"thin film deposition\" OR \"semiconductor fabrication\"",
    # --- Quantum ---
    "quantum_computing": "\"quantum computing\" OR qubit OR \"quantum error correction\" OR \"superconducting qubit\"",
    "quantum_comms_sensing": "\"quantum communication\" OR \"quantum key distribution\" OR \"quantum sensing\" OR \"quantum metrology\"",
    # --- Precision Engineering ---
    "robotics_motion": "robotics OR mechatronics OR \"motion control\" OR \"robot manipulator\" OR \"servo control\"",
    "photonics_optics": "photonics OR \"optical engineering\" OR \"silicon photonics\" OR \"laser\" OR optoelectronics",
    "mems_metrology": "MEMS OR \"microelectromechanical\" OR metrology OR \"precision measurement\" OR \"inertial sensor\"",
    "additive_mfg": "\"additive manufacturing\" OR \"3D printing\" OR \"selective laser melting\" OR \"powder bed fusion\"",
    # --- Advanced Materials ---
    "nanomaterials": "nanomaterial OR graphene OR \"carbon nanotube\" OR \"two-dimensional material\" OR \"quantum dot\"",
    "energy_storage": "\"lithium-ion battery\" OR \"solid-state battery\" OR \"energy storage\" OR supercapacitor OR \"battery electrode\"",
    "composites_polymers": "\"composite material\" OR polymer OR ceramic OR \"superconductor\" OR perovskite",
    # --- Biomedical ---
    "genomics": "genomics OR CRISPR OR \"gene editing\" OR \"DNA sequencing\" OR bioinformatics",
    "cell_gene_therapy": "\"cell therapy\" OR \"gene therapy\" OR \"CAR-T\" OR \"stem cell\" OR \"regenerative medicine\"",
    "synbio_bioprocess": "\"synthetic biology\" OR \"metabolic engineering\" OR fermentation OR \"protein engineering\" OR biomanufacturing",
    # --- Pharmaceuticals ---
    "drug_discovery": "\"drug discovery\" OR \"medicinal chemistry\" OR pharmacology OR \"lead optimization\" OR preclinical",
    "biologics_vaccines": "biologics OR mRNA OR vaccine OR \"monoclonal antibody\" OR immunotherapy",
    "pharma_mfg": "\"pharmaceutical manufacturing\" OR \"drug formulation\" OR \"clinical trial\" OR \"GMP\" OR \"drug delivery\"",
    # --- Digital ---
    "cloud_distributed": "\"distributed systems\" OR \"cloud computing\" OR kubernetes OR \"edge computing\" OR microservices",
    "cybersecurity": "cybersecurity OR cryptography OR \"intrusion detection\" OR \"network security\" OR \"malware\"",
    "networks_5g": "\"5G\" OR \"6G\" OR \"wireless network\" OR \"software defined networking\" OR \"radio access network\"",
    "embedded_iot": "\"embedded systems\" OR \"Internet of Things\" OR firmware OR \"real-time operating system\" OR microcontroller",
    # --- Artificial Intelligence ---
    "machine_learning": "\"machine learning\" OR \"deep learning\" OR \"neural network\" OR \"reinforcement learning\"",
    "generative_nlp": "\"natural language processing\" OR \"large language model\" OR \"generative AI\" OR transformer OR \"speech recognition\"",
    "computer_vision": "\"computer vision\" OR \"object detection\" OR \"image recognition\" OR \"image segmentation\"",
    # --- Other Frontier ---
    "space_aerospace": "aerospace OR satellite OR \"space propulsion\" OR spacecraft OR \"launch vehicle\"",
    "fusion_nuclear": "\"nuclear fusion\" OR plasma OR tokamak OR \"nuclear reactor\" OR \"magnetic confinement\"",
    "hydrogen_fuelcells": "\"hydrogen energy\" OR \"fuel cell\" OR electrolyzer OR \"green hydrogen\" OR electrolysis",
    "carbon_capture": "\"carbon capture\" OR \"direct air capture\" OR \"carbon sequestration\" OR \"CO2 utilization\"",
}

# HYBRID MATCHING (2026-07-16). Where OpenAlex's curated topic taxonomy cleanly
# bounds a domain, we filter by primary_topic.id (precise: strips the noise that
# fuzzy default.search OR-queries pull in). The other ~11 domains have no clean
# topic set — ML is a method fragmented across hundreds of application topics;
# drug_discovery/biologics/carbon_capture etc. map to only 1-2 on-target topics
# and would UNDER-count — so those keep default.search (see DOMAIN_QUERIES).
# Topic sets curated from the full 4,516-topic catalog and verified 2026-07-16
# (country rankings validated against known reality). A domain NOT in this dict
# uses its keyword query. Counts are lower than keyword (strict primary_topic) but
# cleaner — read shares/rankings, not absolute volume, per the panel's own rule.
DOMAIN_TOPICS: dict[str, list[str]] = {
    "chip_design": ["T11522", "T10187", "T10363", "T14117"],
    "memory_devices": ["T10502", "T11181", "T11315"],
    "advanced_packaging": ["T11527", "T11661"],
    "photonics_optics": ["T10299", "T10846", "T10988", "T11050"],
    "mems_metrology": ["T10369", "T11583", "T11325"],
    "additive_mfg": ["T10783", "T10705"],
    "nanomaterials": ["T10083", "T11341", "T11523"],
    "energy_storage": ["T10018", "T10663", "T10179"],
    "genomics": ["T10015", "T10878", "T13937"],
    "cell_gene_therapy": ["T12264", "T10613", "T10505"],
    "pharma_mfg": ["T10704", "T10920", "T11649"],
    "cloud_distributed": ["T10101", "T10715"],
    "cybersecurity": ["T10400", "T10237", "T13983", "T11504"],
    "networks_5g": ["T11458", "T10936", "T10148", "T10125"],
    "embedded_iot": ["T12941", "T13420", "T10273"],
    "generative_nlp": ["T10181", "T10201", "T10028"],
    "computer_vision": ["T10036", "T11448", "T10812", "T12549", "T11605"],
    "space_aerospace": ["T12449", "T11082", "T13200", "T12513"],
    "fusion_nuclear": ["T10346", "T10597", "T13769"],
}


def domain_filter(domain: str) -> str:
    """OpenAlex filter fragment selecting a domain's works: topic-based
    (primary_topic.id:T1|T2|...) for domains in DOMAIN_TOPICS, else the domain's
    keyword default.search. This is the single place the hybrid method is decided."""
    tids = DOMAIN_TOPICS.get(domain)
    if tids:
        return "primary_topic.id:" + "|".join(tids)
    return "default.search:" + DOMAIN_QUERIES[domain]


def domain_method(domain: str) -> str:
    """Provenance label for the matcher used, recorded in each cell's evidence."""
    return "primary_topic" if domain in DOMAIN_TOPICS else "default.search"


# Publication counts are large; bands tuned to research volume (works/year/domain).
def count_to_volume_ord(n: int) -> int:
    if n <= 0:
        return 0
    if n < 50:
        return 1
    if n < 250:
        return 2
    if n < 1000:
        return 3
    if n < 5000:
        return 4
    return 5


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


class BudgetExhausted(RuntimeError):
    """OpenAlex daily free budget spent — a 429 carrying a long Retry-After (hours,
    to the midnight-UTC reset). Distinct from a transient per-second throttle:
    retrying before the reset can't succeed, so this unwinds the ENTIRE run rather
    than being retried per-call or swallowed per-domain."""


def _get(url: str, retries: int = 6):
    if API_KEY and "api_key=" not in url:
        url = f"{url}&api_key={API_KEY}"  # 10x the daily budget; no-op if unset
    req = urllib.request.Request(url, headers={
        "User-Agent": f"techsci-research/0.1 (mailto:{MAILTO})"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                # Two very different 429s share this code:
                #  - budget exhausted: Retry-After is hours (to midnight-UTC reset).
                #    Nothing recovers by retrying now, and every later call in the
                #    run will 429 too — so abort the whole run immediately.
                #  - transient burst throttle: short/absent Retry-After — back off.
                try:
                    ra = int(e.headers.get("Retry-After") or 0)
                except (ValueError, TypeError):
                    ra = 0
                if ra > 300:  # > 5 min ⇒ metered-budget 429, not a burst
                    raise BudgetExhausted(
                        f"OpenAlex daily budget exhausted; resets in ~{ra}s "
                        f"(~{ra // 3600}h, midnight UTC)") from e
                time.sleep(15 * (i + 1))  # transient: back off harder than usual
            else:
                time.sleep(3 * (i + 1))
        except urllib.error.URLError as e:
            # DNS / connection failure — usually a VPN switch dropping the network.
            # No point burning the full retry/backoff: it won't recover in seconds.
            # Fail fast (2 quick tries) so the pass skips on; --skip-existing retries
            # this (year, domain) on a later pass once connectivity is back.
            last = e
            if i >= 1:
                break
            time.sleep(2)
        except Exception as e:  # noqa: BLE001 — e.g. socket timeout, malformed JSON
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"OpenAlex failed after {min(i + 1, retries)} tries: {last}")


def _count_one(domain: str, iso: str, year: int) -> int:
    flt = (f"{domain_filter(domain)},"
           f"authorships.countries:{iso},"
           f"from_publication_date:{year}-01-01,"
           f"to_publication_date:{year}-12-31")
    url = (f"{API}?per-page=1"
           f"&filter={urllib.parse.quote(flt, safe=':,|')}&mailto={MAILTO}")
    return _get(url)["meta"]["count"]


def _group_country_counts(domain: str, year: int) -> dict[str, int]:
    """All country counts for one domain-year in a SINGLE group_by call ->
    {ISO2: works_count}, using the domain's hybrid filter (topic or keyword).
    group_by counts verified 2026-07-16 identical to the per-country method.

    CRITICAL: do NOT send per-page here. `per-page=N` caps group_by output to N
    groups (per-page=1 -> one collapsed group) — THIS was the long-misdiagnosed
    "group_by collapses on complex OR queries" bug; it was never the query.
    group_by returns up to 200 groups by default; our 30 target countries are all
    major research nations and always rank well within that.
    """
    flt = (f"{domain_filter(domain)},"
           f"from_publication_date:{year}-01-01,"
           f"to_publication_date:{year}-12-31")
    url = (f"{API}?filter={urllib.parse.quote(flt, safe=':,|')}"
           f"&group_by=authorships.countries&mailto={MAILTO}")
    out = {}
    for g in _get(url).get("group_by", []):
        key = g.get("key")
        if key:
            out[key.rsplit("/", 1)[-1].upper()] = g.get("count", 0)
    return out


def country_counts(domain: str, year: int) -> dict[str, int]:
    """{ISO2: works_count} over TARGET_COUNTRIES via ONE group_by call — ~30x fewer
    requests than the old per-country sweep, counts verified identical. group_by
    omits zero-count countries, so any target country absent from the result is 0.
    The matcher (topic vs keyword) is chosen per domain by domain_filter().

    Safety net: every one of these broad tech domains spans dozens of publishing
    countries, so a healthy result has many groups; if group_by errors or returns
    implausibly few (<3), we fall back to the reliable one-call-per-country form
    rather than trust a bogus result (silent zeros corrupt the panel).
    BudgetExhausted propagates (the per-country path would 429 too).
    """
    try:
        grouped = _group_country_counts(domain, year)
        time.sleep(PACING + random.uniform(0, JITTER))  # jittered polite pacing
    except BudgetExhausted:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"    [warn] group_by failed ({e}); per-country fallback")
        grouped = None

    if grouped is not None and len(grouped) >= 3:
        return {iso: grouped.get(iso, 0) for iso in TARGET_COUNTRIES}

    if grouped is not None:
        log(f"    [warn] group_by returned only {len(grouped)} group(s) — "
            f"suspect; per-country fallback")
    out = {}
    for iso in TARGET_COUNTRIES:
        out[iso] = _count_one(domain, iso, year)  # let failures propagate
        time.sleep(PACING + random.uniform(0, JITTER))  # jittered polite pacing
    return out


# Impact-weighting needs citations to accrue; a year younger than this has no
# stable FWCI, so run_impact() skips it.
IMPACT_MIN_LAG = 3  # only weight years <= current_year - IMPACT_MIN_LAG


def impact_counts(domain: str, year: int) -> dict[str, int]:
    """{ISO2: count of works with FWCI>1} for a domain-year in ONE group_by call —
    the above-world-average slice of country_counts(). FWCI (field-weighted
    citation impact) normalises across fields and years, so it's comparable domain
    to domain. Only meaningful once citations have accrued (see IMPACT_MIN_LAG)."""
    flt = (f"{domain_filter(domain)},fwci:>1,"
           f"from_publication_date:{year}-01-01,"
           f"to_publication_date:{year}-12-31")
    url = (f"{API}?filter={urllib.parse.quote(flt, safe=':,|<>')}"
           f"&group_by=authorships.countries&mailto={MAILTO}")
    out = {}
    for g in _get(url).get("group_by", []):
        key = g.get("key")
        if key:
            out[key.rsplit("/", 1)[-1].upper()] = g.get("count", 0)
    return out


def run_impact(years: list[int], domains: list[str] | None = None,
               skip_existing: bool = False) -> dict:
    """Populate publication_impact_trend (FWCI>1 counts) for citation-mature years.
    Parallels run() but writes the impact slice; divide by publication_trend.n_pubs
    downstream for the impact-share quality signal. Years younger than
    IMPACT_MIN_LAG are skipped (FWCI not yet stable). All 30 domains (impact is
    orthogonal to the topic/keyword split). Resumable via skip_existing."""
    as_of = dt.date.today().isoformat()
    domains = domains or taxonomy.ALL_DOMAINS
    cutoff = dt.date.today().year - IMPACT_MIN_LAG
    log(f"=== publication impact {as_of}: years={years}, mature cutoff<={cutoff} ===")
    store = Store()
    done = set()
    if skip_existing:
        for (y, d) in store.conn.execute(
                "SELECT year, domain FROM publication_impact_trend "
                "GROUP BY year, domain HAVING COUNT(*)>=30"):
            done.add((y, d))
    for year in years:
        if year > cutoff:
            log(f"[skip-impact] {year}: too recent for stable FWCI (need <= {cutoff})")
            continue
        for dom in domains:
            if (year, dom) in done:
                log(f"[skip] impact {dom:22} {year} already complete")
                continue
            try:
                counts = impact_counts(dom, year)
                time.sleep(PACING + random.uniform(0, JITTER))
            except BudgetExhausted as e:
                log(f"[abort] impact {dom} {year}: {e}. Resume with --skip-existing.")
                store.close()
                return {"aborted": True}
            except Exception as e:  # noqa: BLE001
                log(f"[err] impact {dom} {year}: {e}")
                continue
            store.upsert_publication_impact(
                [{"country_iso": iso, "country_name": name, "domain": dom,
                  "year": year, "n_impact": int(counts.get(iso, 0))}
                 for iso, name in TARGET_COUNTRIES.items()])
            top = sorted(((counts.get(i, 0), i) for i in TARGET_COUNTRIES), reverse=True)[:4]
            log(f"[ok] impact {dom:22} {year} top: {', '.join(f'{i}:{n}' for n,i in top)}")
    yrs = store.publication_impact_years()
    store.close()
    log(f"=== impact done. impact years now: {yrs} ===")
    return {"impact_years": yrs}


INSTITUTION_TOP_N = 20


def institution_leaders(domain: str, year: int, top_n: int = INSTITUTION_TOP_N) -> list[dict]:
    """Top research institutions for a domain-year by publication volume, with
    country. Two calls: one group_by=authorships.institutions.id for the ranking,
    one batched /institutions lookup to resolve the top-N institutions' countries
    (group_by returns names but not country_code)."""
    flt = (f"{domain_filter(domain)},"
           f"from_publication_date:{year}-01-01,to_publication_date:{year}-12-31")
    url = (f"{API}?filter={urllib.parse.quote(flt, safe=':,|')}"
           f"&group_by=authorships.institutions.id&mailto={MAILTO}")
    groups = _get(url).get("group_by", [])[:top_n]
    if not groups:
        return []
    ids = [g["key"].rsplit("/", 1)[-1] for g in groups]
    iflt = "ids.openalex:" + "|".join(ids)
    iurl = (f"https://api.openalex.org/institutions?per-page={len(ids)}"
            f"&filter={urllib.parse.quote(iflt, safe=':,|')}"
            f"&select=id,display_name,country_code&mailto={MAILTO}")
    ctry = {}
    for inst in _get(iurl).get("results", []):
        ctry[inst["id"].rsplit("/", 1)[-1]] = inst.get("country_code")
    out = []
    for rank, g in enumerate(groups, 1):
        iid = g["key"].rsplit("/", 1)[-1]
        out.append({
            "domain": domain, "year": year, "rank": rank,
            "institution_id": iid,
            "institution_name": g.get("key_display_name"),
            "country_iso": (ctry.get(iid) or "").upper() or None,
            "n_works": g["count"],
        })
    return out


def run_institutions(year: int, domains: list[str] | None = None,
                     top_n: int = INSTITUTION_TOP_N) -> dict:
    """Populate institution_leaders (top-N institutions per domain) for a year."""
    domains = domains or taxonomy.ALL_DOMAINS
    log(f"=== institution leaders {dt.date.today().isoformat()}: year={year}, top {top_n} ===")
    store = Store()
    total = 0
    for dom in domains:
        try:
            rows = institution_leaders(dom, year, top_n)
            time.sleep(PACING + random.uniform(0, JITTER))
        except BudgetExhausted as e:
            log(f"[abort] institutions {dom}: {e}")
            store.close()
            return {"aborted": True, "rows": total}
        except Exception as e:  # noqa: BLE001
            log(f"[err] institutions {dom} {year}: {e}")
            continue
        if rows:
            store.upsert_institution_leaders(rows)
            total += len(rows)
            lead = rows[0]
            log(f"[ok] institutions {dom:22} {year}: "
                f"{lead['institution_name']} ({lead['country_iso']}) leads")
    store.close()
    log(f"=== institutions done: {total} rows for {year} ===")
    return {"rows": total}


def intl_counts(domain: str, year: int) -> dict[str, int]:
    """{ISO2: count of internationally co-authored works} for a domain-year in ONE
    group_by call (countries_distinct_count>1 = authors from >1 country). Divide by
    country_counts() for the international-collaboration rate."""
    flt = (f"{domain_filter(domain)},countries_distinct_count:>1,"
           f"from_publication_date:{year}-01-01,to_publication_date:{year}-12-31")
    url = (f"{API}?filter={urllib.parse.quote(flt, safe=':,|<>')}"
           f"&group_by=authorships.countries&mailto={MAILTO}")
    out = {}
    for g in _get(url).get("group_by", []):
        key = g.get("key")
        if key:
            out[key.rsplit("/", 1)[-1].upper()] = g.get("count", 0)
    return out


def run_collaboration(years: list[int], domains: list[str] | None = None,
                      skip_existing: bool = False) -> dict:
    """Populate collaboration_trend (internationally co-authored counts) per
    country×domain×year. Meaningful for all years. Resumable via skip_existing."""
    domains = domains or taxonomy.ALL_DOMAINS
    log(f"=== collaboration {dt.date.today().isoformat()}: years={years} ===")
    store = Store()
    done = set()
    if skip_existing:
        for (y, d) in store.conn.execute(
                "SELECT year, domain FROM collaboration_trend "
                "GROUP BY year, domain HAVING COUNT(*)>=30"):
            done.add((y, d))
    for year in years:
        for dom in domains:
            if (year, dom) in done:
                log(f"[skip] collab {dom:22} {year} already complete")
                continue
            try:
                counts = intl_counts(dom, year)
                time.sleep(PACING + random.uniform(0, JITTER))
            except BudgetExhausted as e:
                log(f"[abort] collab {dom} {year}: {e}. Resume with --skip-existing.")
                store.close()
                return {"aborted": True}
            except Exception as e:  # noqa: BLE001
                log(f"[err] collab {dom} {year}: {e}")
                continue
            store.upsert_collaboration_year(
                [{"country_iso": iso, "country_name": name, "domain": dom,
                  "year": year, "n_intl": int(counts.get(iso, 0))}
                 for iso, name in TARGET_COUNTRIES.items()])
        log(f"[ok] collab year {year} done")
    store.close()
    log("=== collaboration done ===")
    return {"years": years}


# Strategic country pairs for bilateral co-authorship (the geopolitical
# coupling/decoupling signal). US-CN is the headline; extend the list as needed.
STRATEGIC_PAIRS = [("US", "CN")]


def bilateral_count(a: str, b: str, domain: str, year: int) -> int:
    """Works in a domain-year co-authored by BOTH country a and country b."""
    flt = (f"{domain_filter(domain)},"
           f"authorships.countries:{a},authorships.countries:{b},"
           f"from_publication_date:{year}-01-01,to_publication_date:{year}-12-31")
    url = f"{API}?per-page=1&filter={urllib.parse.quote(flt, safe=':,|')}&mailto={MAILTO}"
    return _get(url)["meta"]["count"]


def run_bilateral(years: list[int], pairs=None, domains: list[str] | None = None,
                  skip_existing: bool = False) -> dict:
    """Populate bilateral_collab for the given country pairs. One call per
    (pair, year, domain). Resumable via skip_existing."""
    pairs = pairs or STRATEGIC_PAIRS
    domains = domains or taxonomy.ALL_DOMAINS
    log(f"=== bilateral {dt.date.today().isoformat()}: pairs={pairs}, years={years} ===")
    store = Store()
    done = set()
    if skip_existing:
        for row in store.conn.execute(
                "SELECT country_a, country_b, year, domain FROM bilateral_collab"):
            done.add(tuple(row))
    total = 0
    for a, b in pairs:
        for year in years:
            for dom in domains:
                if (a, b, year, dom) in done:
                    continue
                try:
                    n = bilateral_count(a, b, dom, year)
                    time.sleep(PACING + random.uniform(0, JITTER))
                except BudgetExhausted as e:
                    log(f"[abort] bilateral {a}-{b} {dom} {year}: {e}")
                    store.close()
                    return {"aborted": True, "rows": total}
                except Exception as e:  # noqa: BLE001
                    log(f"[err] bilateral {a}-{b} {dom} {year}: {e}")
                    continue
                store.upsert_bilateral([{"country_a": a, "country_b": b,
                    "domain": dom, "year": year, "n_works": n}])
                total += 1
        log(f"[ok] bilateral {a}-{b} done")
    store.close()
    log(f"=== bilateral done: {total} rows ===")
    return {"rows": total}


def run(year: int, domains: list[str] | None = None,
        latest_year: int | None = None, skip_existing: bool = False) -> dict:
    as_of = dt.date.today().isoformat()
    domains = domains or taxonomy.ALL_DOMAINS
    is_latest = year >= (latest_year if latest_year is not None else year)
    log(f"=== publications {as_of}: year={year}, latest={is_latest}, domains={domains} ===")
    store = Store()
    # resume support: which (year,domain) are already complete (30 countries)?
    done = set()
    if skip_existing:
        for (d,) in store.conn.execute(
                "SELECT domain FROM publication_trend WHERE year=? "
                "GROUP BY domain HAVING COUNT(*)>=30", (year,)):
            done.add(d)
    written = 0
    summary = {}
    for dom in domains:
        if dom in done:
            log(f"[skip] {dom:22} already complete for {year}")
            continue
        try:
            counts = country_counts(dom, year)
        except BudgetExhausted as e:
            # Whole-run stop: every remaining domain would 429 too. --skip-existing
            # on a later run (after the midnight-UTC reset) resumes where we left off.
            log(f"[abort] {dom}: {e}. Stopping run; retry after reset with "
                f"--skip-existing to resume.")
            summary[dom] = 0
            break
        except Exception as e:  # noqa: BLE001
            log(f"[err] {dom}: {e}")
            summary[dom] = 0
            continue
        # always record the year in the trend table
        store.upsert_publication_year(
            [{"country_iso": iso, "country_name": name, "domain": dom,
              "year": year, "n_pubs": int(counts.get(iso, 0))}
             for iso, name in TARGET_COUNTRIES.items()])
        # update the 'latest' cells snapshot only for the newest year pulled
        if is_latest:
            cells = []
            for iso, name in TARGET_COUNTRIES.items():
                n = counts.get(iso, 0)
                cells.append({
                    "country_iso": iso, "country_name": name, "domain": dom,
                    "volume_band": list(taxonomy.VOLUME_BANDS.values())[count_to_volume_ord(n)]["key"],
                    "volume_ord": count_to_volume_ord(n),
                    "volume_estimate": f"{n} publications ({year})",
                    "skill_level": None, "frontier": None,
                    "rationale": f"{n} OpenAlex works in {dom} with an author in {name}, {year}",
                    "evidence": ["OpenAlex", f"{domain_method(dom)}:{dom}", str(year)],
                    "confidence": "high", "precision": "counted",
                    "source": "publications", "as_of": as_of,
                })
            written += store.upsert_many(cells)
        summary[dom] = sum(1 for v in counts.values() if v > 0)
        top = sorted(((counts.get(i, 0), i) for i in TARGET_COUNTRIES), reverse=True)[:4]
        log(f"[ok] {dom:22} top: {', '.join(f'{i}:{n}' for n,i in top)}")
    yrs = store.publication_years()
    store.close()
    log(f"=== done. year {year} | cells updated={is_latest} | trend years now: {yrs} ===")
    return {"year": year, "trend_years": yrs}


def main(argv=None):
    ap = argparse.ArgumentParser(description="OpenAlex publications by country×domain")
    ap.add_argument("--year", type=int, default=dt.date.today().year - 1,
                    help="single publication year (default: last full year)")
    ap.add_argument("--years", nargs="*", type=int, default=None,
                    help="multiple years for a trend, e.g. --years 2016 2018 2020 2022")
    ap.add_argument("--domains", nargs="*", default=None,
                    help="subset of domains to (re)run; default all 9")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip (year,domain) already complete — resume an interrupted run")
    ap.add_argument("--impact", action="store_true",
                    help="populate the FWCI>1 impact series for --years (citation-mature "
                         "years only) instead of the volume pull")
    ap.add_argument("--institutions", action="store_true",
                    help="populate top-N institution leaders per domain for --year")
    ap.add_argument("--collaboration", action="store_true",
                    help="populate international-collaboration counts for --years")
    ap.add_argument("--bilateral", action="store_true",
                    help="populate US-CN bilateral co-authorship for --years")
    args = ap.parse_args(argv)
    years = args.years or [args.year]
    if args.impact:
        run_impact(years, domains=args.domains, skip_existing=args.skip_existing)
        return
    if args.institutions:
        run_institutions(args.year, domains=args.domains)
        return
    if args.collaboration:
        run_collaboration(years, domains=args.domains, skip_existing=args.skip_existing)
        return
    if args.bilateral:
        run_bilateral(years, domains=args.domains, skip_existing=args.skip_existing)
        return
    latest = max(years)
    for y in sorted(years):
        run(y, domains=args.domains, latest_year=latest, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
