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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import taxonomy  # noqa: E402
from research import TARGET_COUNTRIES  # noqa: E402  (reuse the country set)
from store import Store  # noqa: E402

API = "https://api.openalex.org/works"
MAILTO = "research@example.org"  # polite pool — faster, kinder rate limits
LOG = ROOT / "data" / "research" / "publications_run.log"

# Academic search phrasing per domain (publications use different language than
# job ads). Kept tight to avoid false positives; OR-joined via the | operator.
DOMAIN_QUERIES: dict[str, str] = {
    "semiconductors": "semiconductor OR lithography OR \"integrated circuit\" OR CMOS OR \"chip design\"",
    "quantum": "\"quantum computing\" OR qubit OR \"quantum information\" OR \"quantum sensing\"",
    "precision_engineering": "photonics OR mechatronics OR metrology OR MEMS OR \"precision engineering\"",
    "advanced_materials": "\"advanced materials\" OR nanomaterial OR graphene OR superconductor OR perovskite",
    "biomedical": "\"synthetic biology\" OR CRISPR OR genomics OR bioengineering OR \"gene therapy\"",
    "pharmaceuticals": "\"drug discovery\" OR pharmacology OR \"clinical trial\" OR mRNA OR biologics",
    "digital": "\"distributed systems\" OR cybersecurity OR \"edge computing\" OR \"5G\" OR \"cloud computing\"",
    "artificial_intelligence": "\"machine learning\" OR \"deep learning\" OR \"neural network\" OR \"large language model\"",
    "other_frontier": "\"nuclear fusion\" OR aerospace OR \"space propulsion\" OR \"hydrogen energy\" OR \"carbon capture\"",
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


def _get(url: str, retries: int = 3):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"techsci-research/0.1 (mailto:{MAILTO})"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            # 429 = rate limited: back off hard and longer each retry
            time.sleep((6 if e.code == 429 else 2) * (i + 1))
        except urllib.error.URLError as e:  # noqa: PERF203
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"OpenAlex failed: {last}")


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
        time.sleep(0.4)  # polite pacing — slower to avoid 429 over many calls
    return out


def run(year: int, domains: list[str] | None = None) -> dict:
    as_of = dt.date.today().isoformat()
    domains = domains or taxonomy.ALL_DOMAINS
    log(f"=== publications {as_of}: year={year}, domains={domains} ===")
    store = Store()
    written = 0
    summary = {}
    for dom in domains:
        try:
            counts = country_counts(DOMAIN_QUERIES[dom], year)
        except Exception as e:  # noqa: BLE001
            log(f"[err] {dom}: {e}")
            summary[dom] = 0
            continue
        cells = []
        for iso, name in TARGET_COUNTRIES.items():
            n = counts.get(iso, 0)
            cells.append({
                "country_iso": iso,
                "country_name": name,
                "domain": dom,
                "volume_band": list(taxonomy.VOLUME_BANDS.values())[count_to_volume_ord(n)]["key"],
                "volume_ord": count_to_volume_ord(n),
                "volume_estimate": f"{n} publications ({year})",
                "skill_level": None,        # publications don't carry a skill tier
                "frontier": None,
                "rationale": f"{n} OpenAlex works in {dom} with an author in {name}, {year}",
                "evidence": ["OpenAlex", f"default.search:{dom}", str(year)],
                "confidence": "high",
                "precision": "counted",
                "source": "publications",
                "as_of": as_of,
            })
        written += store.upsert_many(cells)
        summary[dom] = len([c for c in cells if c["volume_ord"] > 0])
        top = sorted(((counts.get(i, 0), i) for i in TARGET_COUNTRIES), reverse=True)[:4]
        log(f"[ok] {dom:22} top: {', '.join(f'{i}:{n}' for n,i in top)}")
    total = store.conn.execute(
        "SELECT COUNT(*) FROM cells WHERE source='publications'").fetchone()[0]
    store.close()
    log(f"=== done. wrote {written} cells | publications cells in db: {total} ===")
    return {"written": written, "total": total}


def main(argv=None):
    ap = argparse.ArgumentParser(description="OpenAlex publications by country×domain")
    ap.add_argument("--year", type=int, default=dt.date.today().year - 1,
                    help="publication year (default: last full year)")
    ap.add_argument("--domains", nargs="*", default=None,
                    help="subset of domains to (re)run; default all 9")
    args = ap.parse_args(argv)
    run(args.year, domains=args.domains)


if __name__ == "__main__":
    main()
