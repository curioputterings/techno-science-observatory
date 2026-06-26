"""Cross-border MNC footprint — the division-of-labour map.

For each live ATS employer, classify every open posting by (country, function,
domain) and aggregate into employer × country × function counts. This reveals how
a multinational orchestrates its value chain across borders: research in one
country, engineering in another, manufacturing/test in a third.

Reuses ats/scrape.fetch_board + ats/classify. Stdlib only.

    python3 ats/footprint.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ats import scrape  # noqa: E402  (fetch_board + pacing)
from ats.classify import classify_posting  # noqa: E402
from store import Store  # noqa: E402

REGISTRY = ROOT / "data" / "ats_registry.json"
LOG = ROOT / "data" / "research" / "footprint_run.log"


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run() -> dict:
    if not REGISTRY.exists():
        raise SystemExit("No registry. Run `python3 ats/probe.py` first.")
    boards = json.loads(REGISTRY.read_text())
    as_of = dt.date.today().isoformat()
    log(f"=== footprint {as_of}: {len(boards)} employers ===")

    # (employer, country, function) -> {n, domains:Counter}
    agg: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "domains": Counter()})
    employer_sector = {}

    n_ok = n_err = 0
    for b in boards:
        employer_sector[b["name"]] = b.get("sector", "")
        try:
            posts = scrape.fetch_board(b)
        except Exception as e:  # noqa: BLE001
            log(f"[err] {b['name']}: {e!r}")
            n_err += 1
            continue
        n_ok += 1
        for p in posts:
            c = classify_posting(p["title"], p["text"], p["location"], b.get("sector"))
            country = c["country"]
            if not country:
                continue  # honest: skip roles we can't geolocate
            key = (b["name"], country, c["function"])
            agg[key]["n"] += 1
            if c["domain"]:
                agg[key]["domains"][c["domain"]] += 1
        log(f"[ok] {b['name']:22} processed")
        time.sleep(scrape.POLITE_DELAY_S)

    rows = []
    for (emp, country, fn), v in agg.items():
        top_domain = v["domains"].most_common(1)[0][0] if v["domains"] else None
        rows.append({
            "employer": emp,
            "sector": employer_sector.get(emp, ""),
            "country_iso": country,
            "function": fn,
            "domain": top_domain,
            "n_roles": v["n"],
            "as_of": as_of,
        })

    # Safety guard: never let a transient outage wipe the table. If every board
    # errored (e.g. a DNS blackout — exactly what happened 2026-06-26), `rows` is
    # empty not because the world has no footprint but because we couldn't reach
    # it. Refuse the destructive replace and keep the prior snapshot instead.
    if boards and n_ok == 0:
        store = Store()
        total = store.count_footprint()
        store.close()
        log(f"=== ABORTED: all {n_err} boards failed (no network?) — kept existing "
            f"{total} rows, refused to overwrite with 0 ===")
        return {"rows": 0, "multi_country": 0, "aborted": True, "kept": total}

    store = Store()
    n = store.replace_footprint(rows)
    total = store.count_footprint()
    store.close()

    # quick summary: how many genuinely multi-country employers?
    by_emp = defaultdict(set)
    for r in rows:
        by_emp[r["employer"]].add(r["country_iso"])
    multi = {e: len(cs) for e, cs in by_emp.items() if len(cs) >= 2}
    log(f"=== done. {n} footprint rows | {total} in db | "
        f"{len(multi)} multi-country employers ===")
    log(f"    multi-country: {dict(sorted(multi.items(), key=lambda x: -x[1]))}")
    return {"rows": n, "multi_country": len(multi)}


if __name__ == "__main__":
    run()
