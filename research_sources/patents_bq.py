"""Patents layer (BigQuery) — invention output by country × domain.

Alternative to the EPO OPS connector: Google's `patents-public-data` dataset on
BigQuery. Global coverage, no citizenship gate, and one SQL query per domain
returns counts for ALL countries at once (GROUP BY inventor country) — far more
efficient than per-country API calls.

Cost: BigQuery's free tier is 1 TB of query scanning per month. Each domain query
here scans a few GB (filtered + COUNT), so a full 9-domain run is well under the
free quota. Use --dry-run first to see the bytes each query will scan.

Auth: a Google Cloud **service-account JSON key** (no gcloud CLI / browser flow).
    1. create a GCP project (billing enabled — free tier won't charge)
    2. enable the BigQuery API
    3. create a service account + JSON key, download it
    4. in .env:
         GOOGLE_APPLICATION_CREDENTIALS=/abs/path/to/key.json
         BQ_PROJECT=your-gcp-project-id
The key path + project are read from .env; the key file itself stays off git.

    python3 research_sources/patents_bq.py --check          # auth + tiny query
    python3 research_sources/patents_bq.py --dry-run --year 2020   # cost only
    python3 research_sources/patents_bq.py --year 2020
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import taxonomy  # noqa: E402
from gemini_client import load_env  # noqa: E402
from research import TARGET_COUNTRIES  # noqa: E402
from store import Store  # noqa: E402

_ENV = load_env()
CREDS = _ENV.get("GOOGLE_APPLICATION_CREDENTIALS", "")
BQ_PROJECT = _ENV.get("BQ_PROJECT", "")
LOG = ROOT / "data" / "research" / "patents_run.log"

# CPC classification-code prefixes per domain. Using the patent office's own
# expert classification (the `cpc` field) is both far cheaper to query (~18 GB vs
# ~228 GB for full-text LIKE) AND more reliable than keyword-matching titles.
# Validated against patents-public-data 2020 — counts are face-valid (e.g.
# semiconductors top = US/JP/KR/TW/CN). Prefixes are matched with LIKE 'CODE%'.
DOMAIN_CPC: dict[str, list[str]] = {
    # --- Semiconductors ---
    "chip_design": ["H01L27", "H03K", "G06F30"],   # IC layout, logic, EDA
    "memory_devices": ["G11C", "H10B"],            # memory circuits / devices
    "advanced_packaging": ["H01L23", "H01L24", "H01L25"],  # packaging / interconnect
    "semi_equipment": ["G03F", "H01J37", "H01L21/67"],     # litho, e-beam, fab handling
    # --- Quantum ---
    "quantum_computing": ["G06N10"],
    "quantum_comms_sensing": ["H04L9/08", "H04B10/70", "G01R33"],  # QKD, photonic, sensing
    # --- Precision Engineering ---
    "robotics_motion": ["B25J", "G05B19"],         # manipulators, programmable control
    "photonics_optics": ["G02B", "H01S", "G02F"],  # optics, lasers, optical modulation
    "mems_metrology": ["B81B", "B81C", "G01B"],    # MEMS, microfab, length metrology
    "additive_mfg": ["B33Y", "B29C64"],            # additive manufacturing
    # --- Advanced Materials ---
    "nanomaterials": ["B82Y", "C01B32"],           # nanotech, carbon nanostructures
    "energy_storage": ["H01M10", "H01M4"],         # secondary cells, electrodes
    "composites_polymers": ["C08", "C04B", "C22C"],  # polymers, ceramics, alloys
    # --- Biomedical ---
    "genomics": ["C12N15", "G16B"],                # genetic engineering, bioinformatics
    "cell_gene_therapy": ["A61K35", "A61K48", "C12N5"],  # cell/gene therapy
    "synbio_bioprocess": ["C12N1", "C12P", "C12M"],      # microorganisms, fermentation, apparatus
    # --- Pharmaceuticals ---
    "drug_discovery": ["A61K31", "C07D"],          # organic active ingredients, heterocycles
    "biologics_vaccines": ["A61K39", "C07K16"],    # vaccines/antigens, antibodies
    "pharma_mfg": ["A61K9", "A61J"],               # formulation, containers/delivery
    # --- Digital ---
    "cloud_distributed": ["G06F9", "G06F15"],      # program execution, distributed compute
    "cybersecurity": ["H04L9", "G06F21"],          # cryptography, security
    "networks_5g": ["H04W", "H04B7"],              # wireless networks, radio transmission
    "embedded_iot": ["G06F1", "H04Q9"],            # device architecture, selecting/IoT
    # --- Artificial Intelligence ---
    "machine_learning": ["G06N3", "G06N20"],       # neural nets, machine learning
    "generative_nlp": ["G06F40", "G10L"],          # NLP, speech
    "computer_vision": ["G06V", "G06T"],           # image/vision, image data processing
    # --- Other Frontier ---
    "space_aerospace": ["B64G", "B64D"],           # cosmonautics, aircraft equipment
    "fusion_nuclear": ["G21B", "G21C", "G21D"],    # fusion, fission reactors
    "hydrogen_fuelcells": ["H01M8", "C25B"],       # fuel cells, electrolysis
    "carbon_capture": ["B01D53", "Y02C"],          # gas separation, CO2 capture/storage
}


def ready() -> bool:
    return bool(CREDS and BQ_PROJECT and Path(CREDS).exists())


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


def _client():
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(CREDS, project=BQ_PROJECT)


def _query_sql(cpc_prefixes: list[str], year: int) -> str:
    """Count patent publications per inventor-country for one domain+year.

    - publication_date is an INT64 like 20200115; filter by the year range.
    - cpc is a repeated record -> UNNEST and prefix-match the classification code
      (the patent office's own subject classification — robust + cheap to scan).
    - country comes from inventor_harmonized[].country_code (UNNEST), so a patent
      co-invented across 2 countries counts once per country.
    """
    cond = " OR ".join(f"c.code LIKE '{p}%'" for p in cpc_prefixes)
    iso_list = ",".join(f"'{c}'" for c in TARGET_COUNTRIES)
    return f"""
    SELECT inv.country_code AS iso, COUNT(DISTINCT p.publication_number) AS n
    FROM `patents-public-data.patents.publications` AS p,
         UNNEST(p.cpc) AS c,
         UNNEST(p.inventor_harmonized) AS inv
    WHERE p.publication_date BETWEEN {year}0101 AND {year}1231
      AND inv.country_code IN ({iso_list})
      AND ({cond})
    GROUP BY iso
    """


def _run_query(sql: str, dry_run: bool):
    from google.cloud import bigquery
    client = _client()
    job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=dry_run,
                                                               use_query_cache=False))
    if dry_run:
        return job.total_bytes_processed  # bytes, no rows
    return list(job.result())


def check() -> bool:
    if not ready():
        print("Not configured. Need in .env:\n"
              "  GOOGLE_APPLICATION_CREDENTIALS=/abs/path/to/service-account.json\n"
              "  BQ_PROJECT=your-gcp-project-id\n"
              "and the BigQuery API enabled on that project.")
        return False
    try:
        gb = _run_query(_query_sql(["H01L"], 2020), dry_run=True) / 1e9
        print(f"OK: auth works. One domain-year query scans ~{gb:.1f} GB "
              f"(free tier = 1000 GB/month).")
        rows = _run_query(_query_sql(["G06N10"], 2020), dry_run=False)
        top = sorted(((r["n"], r["iso"]) for r in rows), reverse=True)[:5]
        print("Live test (qubit patents 2020):",
              ", ".join(f"{i}:{n}" for n, i in top) or "(no rows)")
        return bool(rows)
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e}")
        return False


def run(year: int, domains: list[str] | None = None, dry_run: bool = False,
        latest_year: int | None = None) -> dict:
    if not ready():
        raise SystemExit("BigQuery not configured — see module docstring / --check.")
    domains = domains or taxonomy.ALL_DOMAINS
    global _latest_year
    _latest_year = latest_year if latest_year is not None else year
    as_of = dt.date.today().isoformat()
    log(f"=== patents (BigQuery) {as_of}: year={year}, dry_run={dry_run}, domains={domains} ===")

    if dry_run:
        total_gb = 0.0
        for dom in domains:
            gb = _run_query(_query_sql(DOMAIN_CPC[dom], year), dry_run=True) / 1e9
            total_gb += gb
            log(f"[dry] {dom:22} ~{gb:.2f} GB")
        log(f"=== dry-run total ~{total_gb:.1f} GB (free tier 1000 GB/mo) ===")
        return {"dry_run_gb": round(total_gb, 1)}

    store = Store()
    written = 0
    is_latest = year >= max(_latest_year, year)  # only update cells if this is newest
    for dom in domains:
        rows = _run_query(_query_sql(DOMAIN_CPC[dom], year), dry_run=False)
        counts = {r["iso"]: r["n"] for r in rows}
        # always record the year in the trend table
        trend = [{"country_iso": iso, "country_name": name, "domain": dom,
                  "year": year, "n_patents": int(counts.get(iso, 0))}
                 for iso, name in TARGET_COUNTRIES.items()]
        store.upsert_patent_year(trend)
        # update the 'latest' cells snapshot only for the newest year pulled
        if is_latest:
            cells = []
            for iso, name in TARGET_COUNTRIES.items():
                n = int(counts.get(iso, 0))
                cells.append({
                    "country_iso": iso, "country_name": name, "domain": dom,
                    "volume_band": list(taxonomy.VOLUME_BANDS.values())[count_to_volume_ord(n)]["key"],
                    "volume_ord": count_to_volume_ord(n),
                    "volume_estimate": f"{n} patents ({year})",
                    "skill_level": None, "frontier": None,
                    "rationale": f"{n} patent publications in {dom} with a {name} inventor, {year}",
                    "evidence": ["BigQuery", "patents-public-data", str(year)],
                    "confidence": "high", "precision": "counted",
                    "source": "patents", "as_of": as_of,
                })
            written += store.upsert_many(cells)
        top = sorted(((counts.get(i, 0), i) for i in TARGET_COUNTRIES), reverse=True)[:4]
        log(f"[ok] {dom:22} top: {', '.join(f'{i}:{n}' for n,i in top)}")
        time.sleep(0.3)
    yrs = store.patent_years()
    store.close()
    log(f"=== done. year {year} | cells updated={is_latest} | trend years now: {yrs} ===")
    return {"year": year, "trend_years": yrs}


def main(argv=None):
    ap = argparse.ArgumentParser(description="BigQuery patents-public-data by country×domain")
    ap.add_argument("--year", type=int, default=dt.date.today().year - 3,
                    help="single publication year (default: 3y back; patents lag)")
    ap.add_argument("--years", nargs="*", type=int, default=None,
                    help="multiple years for a trend, e.g. --years 2016 2018 2020 2022")
    ap.add_argument("--domains", nargs="*", default=None)
    ap.add_argument("--check", action="store_true", help="validate auth + tiny query")
    ap.add_argument("--dry-run", action="store_true", help="estimate GB scanned, no data")
    args = ap.parse_args(argv)
    if args.check:
        sys.exit(0 if check() else 1)
    years = args.years or [args.year]
    latest = max(years)
    for y in sorted(years):  # oldest first; newest updates the 'latest' cells
        run(y, domains=args.domains, dry_run=args.dry_run, latest_year=latest)


if __name__ == "__main__":
    main()
