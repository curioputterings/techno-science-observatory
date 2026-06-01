"""Patents layer — invention output by country × domain, from PatentsView.

A FOURTH independent signal. Publications reveal research; patents reveal applied
/ commercial invention. The gap between them is itself informative (a country can
publish heavily but patent little = research without commercialisation, or
vice-versa). Triangulates against gemini_research, ats, and publications.

Source: PatentsView Search API (USPTO grants). Free, but needs an API key:
    request one at  https://patentsview.org/  (or https://search.patentsview.org/)
    then put it in .env:   PATENTSVIEW_API_KEY=...
The key is read the same way as the Gemini key — never hardcoded, .env gitignored.

Coverage note: PatentsView is USPTO data, so it captures patents *filed in the US*
by inventors worldwide (via inventor country). That over-weights economies that
patent into the US market — an honest, documented bias, surfaced in the dashboard.

    python3 research_sources/patents.py --year 2023
    python3 research_sources/patents.py --check        # validate key + endpoint only
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
from gemini_client import load_env  # noqa: E402  (reuse the .env reader)
from research import TARGET_COUNTRIES  # noqa: E402
from store import Store  # noqa: E402

# PatentsView Search API (new). Endpoint + auth header per their docs.
BASE = "https://search.patentsview.org/api/v1/patent/"
API_KEY = load_env().get("PATENTSVIEW_API_KEY", "")
LOG = ROOT / "data" / "research" / "patents_run.log"

# Patent-flavoured search terms per domain (CPC-ish phrasing; patents use
# product/process language). OR-joined via _text_any on the title+abstract.
DOMAIN_TERMS: dict[str, str] = {
    "semiconductors": "semiconductor lithography transistor integrated circuit wafer",
    "quantum": "quantum computing qubit quantum cryptography",
    "precision_engineering": "photonics actuator metrology mems optical sensor",
    "advanced_materials": "nanomaterial composite graphene alloy thin film",
    "biomedical": "gene editing crispr biosensor tissue engineering genomic",
    "pharmaceuticals": "pharmaceutical compound drug formulation vaccine antibody",
    "digital": "wireless network cybersecurity edge computing data center",
    "artificial_intelligence": "machine learning neural network artificial intelligence",
    "other_frontier": "rocket propulsion fusion reactor hydrogen fuel cell satellite",
}


def ready() -> bool:
    return bool(API_KEY)


def count_to_volume_ord(n: int) -> int:
    if n <= 0:
        return 0
    if n < 25:
        return 1
    if n < 100:
        return 2
    if n < 500:
        return 3
    if n < 2500:
        return 4
    return 5


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def _post(query: dict, fields: list[str], opts: dict, retries: int = 3) -> dict:
    """PatentsView accepts GET with url-encoded q/f/o, or POST JSON. Use POST."""
    body = json.dumps({"q": query, "f": fields, "o": opts}).encode()
    req = urllib.request.Request(
        BASE, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "X-Api-Key": API_KEY,
                 "User-Agent": "techsci-research/0.1"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:160]!r}"
            time.sleep((6 if e.code == 429 else 2) * (i + 1))
        except urllib.error.URLError as e:
            last = repr(e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"PatentsView failed: {last}")


def count_one(terms: str, iso: str, year: int) -> int:
    """Patent grants in a domain with >=1 inventor from `iso` in `year`."""
    query = {"_and": [
        {"_text_any": {"patent_title": terms}},
        {"inventors.inventor_country": iso},
        {"_gte": {"patent_date": f"{year}-01-01"}},
        {"_lte": {"patent_date": f"{year}-12-31"}},
    ]}
    # size=1, we only want total_hits from the response metadata
    data = _post(query, ["patent_id"], {"size": 1})
    # new API returns {"error":..., "count":.., "total_hits":..} — total_hits is the count
    return int(data.get("total_hits") or data.get("count") or 0)


def check() -> bool:
    """Validate the key + endpoint with one tiny query. Self-diagnoses setup."""
    if not ready():
        print("PATENTSVIEW_API_KEY missing in .env — request a free key at "
              "https://patentsview.org/ and add it.")
        return False
    try:
        n = count_one("semiconductor", "JP", 2022)
        print(f"OK: PatentsView reachable, key valid. (JP semiconductor 2022 = {n})")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e}")
        print("If this is a DNS error, your network may block search.patentsview.org; "
              "try from an unrestricted connection.")
        return False


def run(year: int, domains: list[str] | None = None) -> dict:
    if not ready():
        raise SystemExit("PATENTSVIEW_API_KEY missing in .env. See module docstring.")
    domains = domains or taxonomy.ALL_DOMAINS
    as_of = dt.date.today().isoformat()
    log(f"=== patents {as_of}: year={year}, domains={domains} ===")
    store = Store()
    written = 0
    for dom in domains:
        terms = DOMAIN_TERMS[dom]
        counts = {}
        for iso in TARGET_COUNTRIES:
            counts[iso] = count_one(terms, iso, year)  # let failures raise
            time.sleep(0.4)
        cells = []
        for iso, name in TARGET_COUNTRIES.items():
            n = counts[iso]
            cells.append({
                "country_iso": iso, "country_name": name, "domain": dom,
                "volume_band": list(taxonomy.VOLUME_BANDS.values())[count_to_volume_ord(n)]["key"],
                "volume_ord": count_to_volume_ord(n),
                "volume_estimate": f"{n} US patents ({year})",
                "skill_level": None, "frontier": None,
                "rationale": f"{n} USPTO grants in {dom} with a {name} inventor, {year}",
                "evidence": ["PatentsView", "USPTO", str(year)],
                "confidence": "high", "precision": "counted",
                "source": "patents", "as_of": as_of,
            })
        written += store.upsert_many(cells)
        top = sorted(((counts[i], i) for i in TARGET_COUNTRIES), reverse=True)[:4]
        log(f"[ok] {dom:22} top: {', '.join(f'{i}:{n}' for n,i in top)}")
    total = store.conn.execute(
        "SELECT COUNT(*) FROM cells WHERE source='patents'").fetchone()[0]
    store.close()
    log(f"=== done. wrote {written} | patents cells in db: {total} ===")
    return {"written": written, "total": total}


def main(argv=None):
    ap = argparse.ArgumentParser(description="PatentsView USPTO patents by country×domain")
    ap.add_argument("--year", type=int, default=dt.date.today().year - 2,
                    help="grant year (default: 2 years back; recent years lag)")
    ap.add_argument("--domains", nargs="*", default=None)
    ap.add_argument("--check", action="store_true", help="validate key+endpoint only")
    args = ap.parse_args(argv)
    if args.check:
        sys.exit(0 if check() else 1)
    run(args.year, domains=args.domains)


if __name__ == "__main__":
    main()
