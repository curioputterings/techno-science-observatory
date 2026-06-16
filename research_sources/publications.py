"""Publications layer — research output by country × domain, from OpenAlex.

An INDEPENDENT third signal to triangulate the Gemini estimates and ATS counts.
Jobs reveal current hiring; publications reveal accumulated research capacity.
Where they agree, confidence is high; where they diverge, something interesting.

OpenAlex is free, no key (polite pool via mailto). We query one count per
(country, domain) — the `group_by` endpoint proved flaky with complex OR queries
(intermittently collapses to a single group), so we use the reliable count-only
form (per-page=1, read meta.count) filtered by authorships.countries:
    works?per-page=1&filter=default.search:<q>,authorships.countries:<ISO>,<dates>

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


def _get(url: str, retries: int = 6):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"techsci-research/0.1 (mailto:{MAILTO})"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            # 429s need a long cooldown; back off harder and longer than transient errors
            time.sleep((15 if e.code == 429 else 3) * (i + 1))
        except Exception as e:  # noqa: BLE001 — incl. ConnectionResetError, socket timeout
            # any transport-level failure (reset, timeout, DNS blip): back off + retry
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"OpenAlex failed after {retries} tries: {last}")


def _count_one(query: str, iso: str, year: int) -> int:
    flt = (f"default.search:{query},"
           f"authorships.countries:{iso},"
           f"from_publication_date:{year}-01-01,"
           f"to_publication_date:{year}-12-31")
    url = (f"{API}?per-page=1"
           f"&filter={urllib.parse.quote(flt, safe=':,')}&mailto={MAILTO}")
    return _get(url)["meta"]["count"]


def country_counts(query: str, year: int) -> dict[str, int]:
    """One reliable count call per target country -> {ISO2: works_count}.

    Raises if a country fails all retries — the caller should NOT persist a
    partial/zeroed domain (silent zeros corrupt the panel). Pacing is gentle to
    stay under OpenAlex rate limits across a 270-call run.
    """
    out = {}
    for iso in TARGET_COUNTRIES:
        out[iso] = _count_one(query, iso, year)  # let failures propagate
        time.sleep(1.0)  # polite pacing — slower to avoid 429 over a long multi-year run
    return out


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
            counts = country_counts(DOMAIN_QUERIES[dom], year)
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
                    "evidence": ["OpenAlex", f"default.search:{dom}", str(year)],
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
    args = ap.parse_args(argv)
    years = args.years or [args.year]
    latest = max(years)
    for y in sorted(years):
        run(y, domains=args.domains, latest_year=latest, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
