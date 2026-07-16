"""Funding layer — which national funders back which frontier fields, from
Crossref funder-acknowledgement metadata. A "revealed ambition" signal to
triangulate against the stated-ambition (national-plans) layer: where funded
research and stated intent diverge is itself a finding.

WHY CROSSREF (not OpenAlex): OpenAlex removed grant/funder querying in 2026
(grants.funder filter, group_by, has_grants all HTTP 400). Crossref is where
funding-acknowledgement metadata originates (OpenAlex derived its grants from it).
Free, no key (polite pool via mailto).

We count works per (funder, domain, year) by filtering on the funder's Registry
DOI and a topic query. Two honest caveats, both make this DIRECTIONAL not exact:
  - Acknowledgement-based: a work counts only if its publisher recorded the funder
    in the metadata, so coverage is incomplete and skews by publisher / discipline
    / country. Read shares and rankings, never absolute totals.
  - Crossref has no topic taxonomy, so domain matching is a free-text query
    (keyword-fuzzy, like the keyword publication domains — not topic-precise).

    python3 research_sources/funding.py --years 2016 2018 2020 2022
    python3 research_sources/funding.py --years 2022 --skip-existing
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
socket.setdefaulttimeout(35)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import taxonomy  # noqa: E402
from gemini_client import load_env  # noqa: E402
from store import Store  # noqa: E402

CROSSREF = "https://api.crossref.org/works"
MAILTO = load_env().get("OPENALEX_MAILTO", "research@example.org")
# Crossref polite pool is generous; gentle pacing keeps us well-behaved on a long run.
PACING = float(load_env().get("CROSSREF_PACING", "0.5"))
JITTER = float(load_env().get("CROSSREF_JITTER", "0.5"))
LOG = ROOT / "data" / "research" / "funding_run.log"

# Major national science funders: (slug, display name, country ISO2, Registry DOI).
# All DOIs verified against Crossref 2026-07-17. "EU" for supranational bodies.
FUNDERS: list[tuple[str, str, str, str]] = [
    ("nsfc",   "National Natural Science Foundation of China", "CN", "10.13039/501100001809"),
    ("nsf",    "National Science Foundation (US)",             "US", "10.13039/100000001"),
    ("nih",    "National Institutes of Health (US)",           "US", "10.13039/100000002"),
    ("erc",    "European Research Council",                    "EU", "10.13039/501100000781"),
    ("ec",     "European Commission",                          "EU", "10.13039/501100000780"),
    ("dfg",    "Deutsche Forschungsgemeinschaft",              "DE", "10.13039/501100001659"),
    ("jsps",   "Japan Society for the Promotion of Science",   "JP", "10.13039/501100001691"),
    ("mext",   "MEXT (Japan)",                                 "JP", "10.13039/501100001700"),
    ("nrf_kr", "National Research Foundation of Korea",        "KR", "10.13039/501100003725"),
    ("ukri",   "UK Research and Innovation",                   "GB", "10.13039/100014013"),
    ("anr",    "Agence Nationale de la Recherche",             "FR", "10.13039/501100001665"),
    ("nserc",  "NSERC (Canada)",                               "CA", "10.13039/501100000038"),
    ("arc",    "Australian Research Council",                  "AU", "10.13039/501100000923"),
]

# One representative Crossref query phrase per domain (free-text; no topic taxonomy).
DOMAIN_TERMS: dict[str, str] = {
    "chip_design": "integrated circuit design",
    "memory_devices": "semiconductor memory device",
    "advanced_packaging": "heterogeneous integration chip packaging",
    "semi_equipment": "semiconductor fabrication lithography",
    "quantum_computing": "quantum computing",
    "quantum_comms_sensing": "quantum communication sensing",
    "robotics_motion": "robotics motion control",
    "photonics_optics": "photonics optics",
    "mems_metrology": "microelectromechanical systems metrology",
    "additive_mfg": "additive manufacturing",
    "nanomaterials": "nanomaterials",
    "energy_storage": "battery energy storage",
    "composites_polymers": "composite materials polymers",
    "genomics": "genomics sequencing",
    "cell_gene_therapy": "gene therapy cell therapy",
    "synbio_bioprocess": "synthetic biology bioprocess",
    "drug_discovery": "drug discovery",
    "biologics_vaccines": "vaccine monoclonal antibody",
    "pharma_mfg": "pharmaceutical formulation drug delivery",
    "cloud_distributed": "cloud distributed computing",
    "cybersecurity": "cybersecurity cryptography",
    "networks_5g": "wireless networks 5G",
    "embedded_iot": "internet of things embedded systems",
    "machine_learning": "machine learning deep learning",
    "generative_nlp": "natural language processing large language model",
    "computer_vision": "computer vision image recognition",
    "space_aerospace": "aerospace spacecraft",
    "fusion_nuclear": "nuclear fusion",
    "hydrogen_fuelcells": "hydrogen fuel cell",
    "carbon_capture": "carbon capture",
}


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def _get(url: str, retries: int = 5):
    req = urllib.request.Request(
        url, headers={"User-Agent": f"techsci-research/0.1 (mailto:{MAILTO})"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            # Crossref throttles with 429/503; back off. Others: brief retry.
            time.sleep((5 if e.code in (429, 503) else 2) * (i + 1))
        except urllib.error.URLError as e:
            # network drop (VPN switch etc.) — fail fast so the pass skips on;
            # --skip-existing resumes this (funder,year,domain) later.
            last = e
            if i >= 1:
                break
            time.sleep(2)
        except Exception as e:  # noqa: BLE001 — socket timeout, malformed JSON
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Crossref failed after {min(i + 1, retries)} tries: {last}")


def funder_domain_count(funder_doi: str, query: str, year: int) -> int:
    """Works acknowledging a funder in a field-year — one Crossref count call."""
    flt = (f"funder:{funder_doi},"
           f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31")
    url = (f"{CROSSREF}?filter={urllib.parse.quote(flt, safe=':,./')}"
           f"&query={urllib.parse.quote(query)}&rows=0&mailto={MAILTO}")
    return int(_get(url)["message"]["total-results"])


def run_funding(years: list[int], funders=None, domains: list[str] | None = None,
                skip_existing: bool = False) -> dict:
    """Populate funder_trend for the given funders × domains × years. One Crossref
    call per (funder, domain, year). Resumable via skip_existing."""
    funders = funders or FUNDERS
    domains = domains or list(DOMAIN_TERMS)
    log(f"=== funding {dt.date.today().isoformat()}: {len(funders)} funders, "
        f"{len(domains)} domains, years={years} ===")
    store = Store()
    done = set()
    if skip_existing:
        for row in store.conn.execute(
                "SELECT funder_id, year, domain FROM funder_trend"):
            done.add(tuple(row))
    total = 0
    for year in years:
        for fid, name, ctry, doi in funders:
            for dom in domains:
                if (fid, year, dom) in done:
                    continue
                try:
                    n = funder_domain_count(doi, DOMAIN_TERMS[dom], year)
                    time.sleep(PACING + random.uniform(0, JITTER))
                except Exception as e:  # noqa: BLE001
                    log(f"[err] funding {fid} {dom} {year}: {e}")
                    continue
                store.upsert_funder_trend([{
                    "funder_id": fid, "funder_name": name, "funder_country": ctry,
                    "domain": dom, "year": year, "n_works": n}])
                total += 1
            log(f"[ok] funding {fid:8} {year} done")
    store.close()
    log(f"=== funding done: {total} rows ===")
    return {"rows": total}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Crossref funder × domain × year counts")
    ap.add_argument("--years", nargs="*", type=int,
                    default=[dt.date.today().year - 2],
                    help="publication years (default: 2 years back)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip (funder,year,domain) already recorded — resume a run")
    args = ap.parse_args(argv)
    run_funding(args.years, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
