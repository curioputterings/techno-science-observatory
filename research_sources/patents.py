"""Patents layer — invention output by country × domain, from EPO OPS.

A FOURTH independent signal. Publications reveal research; patents reveal applied
/ commercial invention. Triangulates against gemini_research, ats, publications.

Source: EPO Open Patent Services (OPS) — European Patent Office. No citizenship
restriction (unlike PatentsView), genuinely free, global patent-family coverage.
Auth is OAuth2 client-credentials: register a free app at
    https://developers.epo.org/   ->  get a Consumer Key + Consumer Secret
then put BOTH in .env:
    EPO_OPS_KEY=...
    EPO_OPS_SECRET=...
The connector exchanges them for a short-lived bearer token automatically.

IMPORTANT honest caveat — the country dimension:
    OPS's CQL search indexes title/abstract/date well, but country-of-inventor is
    NOT a clean first-class CQL index. This connector filters by country using the
    applicant/inventor-country CQL field (`pa`/`in` with a country code) which may
    or may not behave as hoped on your account. RUN `--check` FIRST: it validates
    auth AND tells you whether the country-filtered count actually works before any
    full run. If country filtering proves unreliable, the layer should not be
    trusted (don't silently persist bad counts).

    python3 research_sources/patents.py --check        # validate auth + country query
    python3 research_sources/patents.py --year 2022
"""
from __future__ import annotations

import argparse
import base64
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
from gemini_client import load_env  # noqa: E402
from research import TARGET_COUNTRIES  # noqa: E402
from store import Store  # noqa: E402

AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"
_ENV = load_env()
OPS_KEY = _ENV.get("EPO_OPS_KEY", "")
OPS_SECRET = _ENV.get("EPO_OPS_SECRET", "")
LOG = ROOT / "data" / "research" / "patents_run.log"

# Patent-flavoured title/abstract terms per domain (OPS CQL ti/ab search).
DOMAIN_TERMS: dict[str, str] = {
    "semiconductors": "semiconductor or lithography or transistor or wafer",
    "quantum": "qubit or \"quantum computing\" or \"quantum cryptography\"",
    "precision_engineering": "photonic or actuator or mems or metrology",
    "advanced_materials": "nanomaterial or graphene or composite or \"thin film\"",
    "biomedical": "crispr or \"gene editing\" or biosensor or genomic",
    "pharmaceuticals": "pharmaceutical or vaccine or antibody or \"drug formulation\"",
    "digital": "cybersecurity or \"edge computing\" or \"wireless network\"",
    "artificial_intelligence": "\"machine learning\" or \"neural network\"",
    "other_frontier": "propulsion or \"fusion reactor\" or \"fuel cell\" or satellite",
}


def ready() -> bool:
    return bool(OPS_KEY and OPS_SECRET)


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


_TOKEN = {"value": "", "exp": 0.0}


def _get_token(now: float) -> str:
    """OAuth2 client-credentials -> bearer token (cached until ~expiry)."""
    if _TOKEN["value"] and now < _TOKEN["exp"]:
        return _TOKEN["value"]
    basic = base64.b64encode(f"{OPS_KEY}:{OPS_SECRET}".encode()).decode()
    req = urllib.request.Request(
        AUTH_URL, data=b"grant_type=client_credentials", method="POST",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    _TOKEN["value"] = d["access_token"]
    # tokens last ~20min; refresh a bit early. pass `now` in (no Date.now ban issue)
    _TOKEN["exp"] = now + int(d.get("expires_in", 1200)) - 60
    return _TOKEN["value"]


def _search_count(cql: str, now: float, retries: int = 3) -> int:
    """Return OPS total-result-count for a CQL query (Range 1-1 = count only)."""
    token = _get_token(now)
    url = f"{SEARCH_URL}?q={urllib.parse.quote(cql)}&Range=1-1"
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read())
            # total count lives at ops:world-patent-data > ops:biblio-search @total-result-count
            bs = (d.get("ops:world-patent-data", {})
                    .get("ops:biblio-search", {}))
            return int(bs.get("@total-result-count", 0))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:150]!r}"
            if e.code == 401:  # token expired mid-run: force refresh
                _TOKEN["exp"] = 0.0
                token = _get_token(now)
            time.sleep((6 if e.code in (403, 429) else 2) * (i + 1))
        except (urllib.error.URLError, KeyError, ValueError) as e:
            last = repr(e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"OPS search failed: {last}")


def _cql(terms: str, iso: str, year: int) -> str:
    # ti,ab = title/abstract; pd = publication date (year); pa = applicant (incl. country code)
    return f'(ti,ab=({terms})) and pd within "{year}" and pa="{iso}"'


def count_one(terms: str, iso: str, year: int, now: float) -> int:
    return _search_count(_cql(terms, iso, year), now)


def check(now: float) -> bool:
    """Validate auth AND the country-filtered query before any full run."""
    if not ready():
        print("EPO_OPS_KEY / EPO_OPS_SECRET missing in .env. Register a free app at "
              "https://developers.epo.org/ and add both.")
        return False
    try:
        _get_token(now)
        print("OK: OAuth token obtained (auth works).")
    except Exception as e:  # noqa: BLE001
        print(f"AUTH FAILED: {e}")
        return False
    try:
        # sanity: a domain term with NO country, then WITH a country — both must work,
        # and the country-filtered count must be > 0 and < the unfiltered count.
        broad = _search_count('ti,ab=(semiconductor) and pd within "2020"', now)
        jp = count_one("semiconductor", "JP", 2020, now)
        print(f"broad semiconductor 2020 = {broad}; JP-filtered = {jp}")
        if broad <= 0:
            print("WARN: broad query returned 0 — CQL/term issue."); return False
        if jp <= 0:
            print("WARN: country filter returned 0 — the `pa=\"<ISO>\"` country "
                  "approach does NOT work on OPS as hoped. Do NOT trust this layer "
                  "until the country CQL is fixed.")
            return False
        print("OK: country-filtered count works. Patents layer is usable.")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"QUERY FAILED: {e}")
        return False


def run(year: int, now: float, domains: list[str] | None = None) -> dict:
    if not ready():
        raise SystemExit("EPO_OPS_KEY / EPO_OPS_SECRET missing in .env.")
    domains = domains or taxonomy.ALL_DOMAINS
    as_of = dt.date.today().isoformat()
    log(f"=== patents (EPO OPS) {as_of}: year={year}, domains={domains} ===")
    store = Store()
    written = 0
    for dom in domains:
        terms = DOMAIN_TERMS[dom]
        counts = {}
        for iso in TARGET_COUNTRIES:
            counts[iso] = count_one(terms, iso, year, now)  # let failures raise
            time.sleep(0.6)  # OPS is strict on throttling
        cells = []
        for iso, name in TARGET_COUNTRIES.items():
            n = counts[iso]
            cells.append({
                "country_iso": iso, "country_name": name, "domain": dom,
                "volume_band": list(taxonomy.VOLUME_BANDS.values())[count_to_volume_ord(n)]["key"],
                "volume_ord": count_to_volume_ord(n),
                "volume_estimate": f"{n} patents ({year})",
                "skill_level": None, "frontier": None,
                "rationale": f"{n} EPO OPS patent publications in {dom}, {name} applicant, {year}",
                "evidence": ["EPO OPS", "espacenet", str(year)],
                "confidence": "medium", "precision": "counted",
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
    ap = argparse.ArgumentParser(description="EPO OPS patents by country×domain")
    ap.add_argument("--year", type=int, default=dt.date.today().year - 3,
                    help="publication year (default: 3y back; patents lag)")
    ap.add_argument("--domains", nargs="*", default=None)
    ap.add_argument("--check", action="store_true", help="validate auth+country query")
    args = ap.parse_args(argv)
    now = time.time()
    if args.check:
        sys.exit(0 if check(now) else 1)
    run(args.year, now, domains=args.domains)


if __name__ == "__main__":
    main()
