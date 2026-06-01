"""Weekly refresh (Phase 7): regenerate the panel and record a dated snapshot.

Run by the weekly cron (weekly_refresh.sh). Order:
  1. run_research.py   -> refresh revealed-capability cells (9 Gemini calls)
  2. ambition.py       -> refresh stated-ambition cells   (9 Gemini calls)
  3. store.snapshot()  -> copy current cells into cell_history under today's date

Idempotent per day: re-running the same day overwrites that day's snapshot, so
the cron yields one clean point per week. Stdlib-only (Gemini via urllib), so it
runs under the system python with no venv.

    python3 refresh.py            # full weekly refresh + snapshot
    python3 refresh.py --snapshot-only   # just snapshot current cells (no API)
    python3 refresh.py --trends   # print capability trend across snapshots
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import ambition
import gemini_client
import research
import taxonomy
from store import Store

RESEARCH_DIR = research.RESEARCH_DIR
LOG = RESEARCH_DIR / "refresh.log"


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def do_refresh(as_of: str, skip_api: bool = False) -> None:
    if not skip_api:
        if not gemini_client.ready():
            log("ERROR: GEMINI_API_KEY missing; cannot refresh. Run --snapshot-only "
                "to snapshot existing cells.")
            sys.exit(1)
        log("--- refreshing revealed capability (run_research) ---")
        rsum = research_run(as_of)
        log(f"    capability per-domain: {rsum}")
        log("--- refreshing stated ambition (ambition) ---")
        asum = ambition.run(taxonomy.ALL_DOMAINS, as_of)
        log(f"    ambition per-domain: {asum}")
    else:
        log("--- snapshot-only: skipping Gemini refresh ---")

    store = Store()
    n = store.snapshot(as_of)
    dates = store.snapshot_dates()
    store.close()
    log(f"--- snapshot {as_of}: {n} cells recorded | history dates: {dates} ---")


def research_run(as_of: str) -> dict:
    """Mirror run_research.run without re-importing its __main__ guard."""
    schema = gemini_client.domain_schema()
    summary = {}
    for key in taxonomy.ALL_DOMAINS:
        try:
            payload = gemini_client.structured(research.build_prompt(key), schema)
            payload["domain"] = key
            (RESEARCH_DIR / f"{key}.json").write_text(__import__("json").dumps(payload, indent=2))
            summary[key] = research.ingest_payload(payload, as_of=as_of)
        except Exception as e:  # noqa: BLE001
            log(f"    [err] capability {key}: {e}")
            summary[key] = 0
    return summary


def print_trends() -> None:
    import sqlite3
    from store import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT snapshot_date, country_name, AVG(capability) "
        "FROM cell_history WHERE source='gemini_research' "
        "GROUP BY snapshot_date, country_iso ORDER BY snapshot_date"
    ).fetchall()
    conn.close()
    dates = sorted({r[0] for r in rows})
    if not dates:
        print("No snapshots yet. Run `python3 refresh.py` or `--snapshot-only`.")
        return
    print(f"Snapshots: {dates}")
    if len(dates) < 2:
        print("(Need >=2 snapshots before trends become meaningful.)")
    # latest snapshot ranking
    latest = dates[-1]
    rank = sorted(((c, v) for d, c, v in rows if d == latest),
                  key=lambda x: x[1], reverse=True)
    print(f"\nLatest snapshot ({latest}) mean capability, top 10:")
    for c, v in rank[:10]:
        print(f"  {v:5.1f}  {c}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weekly panel refresh + snapshot")
    ap.add_argument("--snapshot-only", action="store_true",
                    help="snapshot current cells without calling Gemini")
    ap.add_argument("--trends", action="store_true",
                    help="print capability trends across snapshots and exit")
    args = ap.parse_args(argv)

    if args.trends:
        print_trends()
        return

    as_of = dt.date.today().isoformat()
    log(f"=== refresh start {as_of} (snapshot_only={args.snapshot_only}) ===")
    do_refresh(as_of, skip_api=args.snapshot_only)
    log("=== refresh done ===")


if __name__ == "__main__":
    main()
