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
        # snapshot-only is truly offline: no Gemini, no ATS/OpenAlex, no BigQuery.
        # It just copies the cells already in the DB into cell_history.
        log("--- snapshot-only: skipping all collectors (Gemini/ATS/OpenAlex/BigQuery) ---")

    if not skip_api:
        # cross-border footprint always refreshes (free ATS, no key needed)
        try:
            from ats import footprint
            fsum = footprint.run()
            log(f"    footprint: {fsum}")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] footprint refresh failed: {e!r}")

        # publications triangulation layer (OpenAlex). skip_existing=True: the
        # target year is `today-1`, and a full-year publication count is stable
        # once indexed — re-pulling it weekly would spend ~900 calls (30 countries
        # × 30 domains) of OpenAlex's now-metered ~1000/day budget on byte-identical
        # data. So we pull a year only until it's complete (all 30 domains × 30
        # countries), i.e. once when `year-1` ticks over to a new value (~January);
        # every other week skips with 0 calls. A run interrupted by BudgetExhausted
        # resumes next week (incomplete domains aren't marked done). Force a manual
        # re-pull with `publications.py` (no --skip-existing) if a year needs it.
        try:
            from research_sources import publications
            psum = publications.run(year=dt.date.today().year - 1, skip_existing=True)
            log(f"    publications: {psum}")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] publications refresh failed: {e!r}")

        # trend years drive the impact + collaboration maintenance below.
        store = Store()
        trend_years = store.publication_years()
        store.close()

        # impact-weighting layer: FWCI>1 counts for the citation-mature trend years.
        # skip_existing => ~0 calls once populated; fills a trend year only when it
        # crosses the maturity lag. Orthogonal to the volume pull above.
        try:
            isum = publications.run_impact(trend_years, skip_existing=True)
            log(f"    publication impact: {isum}")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] impact refresh failed: {e!r}")

        # institution leaders: top-N research institutions per domain for the latest
        # full year. Re-pulled weekly (idempotent by rank) — unlike stable-once-done
        # volume, current-year leadership shifts as new work is indexed. ~60 calls.
        try:
            lsum = publications.run_institutions(dt.date.today().year - 1)
            log(f"    institution leaders: {lsum}")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] institution leaders refresh failed: {e!r}")

        # international collaboration + US-CN bilateral (skip_existing => ~0 calls
        # once a year is complete; fills a new trend year when it appears).
        try:
            csum = publications.run_collaboration(trend_years, skip_existing=True)
            bsum = publications.run_bilateral(trend_years, skip_existing=True)
            log(f"    collaboration: {csum} | bilateral: {bsum}")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] collaboration refresh failed: {e!r}")

        # funder analysis (Crossref, NOT OpenAlex) — which national agencies back
        # which fields = revealed ambition. Mature years only (funder metadata
        # lags for recent years); skip_existing => ~0 calls once populated.
        try:
            from research_sources import funding
            fund_years = [y for y in trend_years if y <= dt.date.today().year - 2]
            fsum = funding.run_funding(fund_years, skip_existing=True)
            log(f"    funding: {fsum}")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] funding refresh failed: {e!r}")

        # patents layer — prefer BigQuery if configured, else EPO OPS, else skip.
        # Skip-existing: the target year is `today-3` and patents lag ~3y, so once a
        # year is pulled its counts are final and never change. Re-scanning it every
        # week would burn ~162 GB of the 1 TB/mo free tier for byte-identical data,
        # so we only scan a year that isn't already in patent_trend — i.e. exactly
        # once, when `year-3` ticks over to a new value. (Manual pulls via
        # patents_bq.py --year are unaffected and always run.)
        pat_year = dt.date.today().year - 3  # patents lag a few years
        try:
            have = set(Store().patent_years())  # cheap local read
            if pat_year in have:
                log(f"    patents: year {pat_year} already in DB — skipping scan (no cost)")
            else:
                from research_sources import patents_bq
                if patents_bq.ready():
                    log(f"    patents (BigQuery): {patents_bq.run(year=pat_year)}")
                else:
                    import time as _time
                    from research_sources import patents
                    if patents.ready():
                        log(f"    patents (EPO OPS): {patents.run(year=pat_year, now=_time.time())}")
                    else:
                        log("    patents: skipped (no BigQuery or EPO OPS creds in .env)")
        except Exception as e:  # noqa: BLE001
            log(f"    [warn] patents refresh failed: {e!r}")

    store = Store()
    n = store.snapshot(as_of)
    dates = store.snapshot_dates()
    store.close()
    log(f"--- snapshot {as_of}: {n} cells recorded | history dates: {dates} ---")


def research_run(as_of: str, domains: list[str] | None = None) -> dict:
    """Mirror run_research.run without re-importing its __main__ guard.

    `domains` restricts the pass to a subset — used by --domains to repair the
    handful of domains a transient outage stranded, without re-billing the ones
    that already landed.
    """
    schema = gemini_client.domain_schema()
    summary = {}
    for key in (domains or taxonomy.ALL_DOMAINS):
        try:
            payload = gemini_client.structured(research.build_prompt(key), schema)
            payload["domain"] = key
            (RESEARCH_DIR / f"{key}.json").write_text(__import__("json").dumps(payload, indent=2))
            summary[key] = research.ingest_payload(payload, as_of=as_of)
        except Exception as e:  # noqa: BLE001
            log(f"    [err] capability {key}: {e}")
            summary[key] = 0
    return summary


def do_repair(as_of: str, domains: list[str]) -> int:
    """Refresh only `domains`, then re-record today's snapshot.

    WHY THIS EXISTS: a network outage during the weekly run strands whichever
    domains it happened to cover (2026-08-31: the first 8 of 30, 4 min of dead
    Gemini retries each). The snapshot is still written, so the stranded domains
    silently carry the previous week's values forward — a flat week in
    cell_history rather than a visible hole. Re-running the whole refresh would
    repair them at the cost of re-billing the 22 that were already fine, so the
    catch-up guard calls this instead with just the stale set.

    Snapshot is idempotent per day: it overwrites today's rows, so the repaired
    values replace the carried-forward ones in place.
    """
    if not gemini_client.ready():
        log("ERROR: GEMINI_API_KEY missing; cannot repair.")
        return 1
    unknown = [d for d in domains if d not in taxonomy.ALL_DOMAINS]
    if unknown:
        log(f"ERROR: unknown domain(s): {unknown}")
        return 1

    log(f"--- repair: {len(domains)} stale domain(s): {domains} ---")
    rsum = research_run(as_of, domains)
    log(f"    repair capability per-domain: {rsum}")
    asum = ambition.run(domains, as_of)
    log(f"    repair ambition per-domain: {asum}")

    store = Store()
    n = store.snapshot(as_of)
    store.close()
    log(f"--- repair snapshot {as_of}: {n} cells recorded ---")

    # Report yield, not just completion: a repair that returned zero cells for
    # some domain is exactly the failure this whole path exists to catch, and it
    # must not read as success.
    empty = sorted([d for d in domains if not rsum.get(d)])
    if empty:
        log(f"--- repair INCOMPLETE: still no capability data for {empty} ---")
        return 2
    log(f"--- repair done: {len(domains)}/{len(domains)} domains refreshed ---")
    return 0


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
    ap.add_argument("--domains", metavar="A,B,C",
                    help="repair only these comma-separated domain keys "
                         "(capability + ambition), then re-snapshot")
    args = ap.parse_args(argv)

    if args.trends:
        print_trends()
        return

    if args.domains:
        as_of = dt.date.today().isoformat()
        keys = [d.strip() for d in args.domains.split(",") if d.strip()]
        log(f"=== repair start {as_of} ({len(keys)} domain(s)) ===")
        rc = do_repair(as_of, keys)
        log(f"=== repair done (rc={rc}) ===")
        sys.exit(rc)

    as_of = dt.date.today().isoformat()
    log(f"=== refresh start {as_of} (snapshot_only={args.snapshot_only}) ===")
    do_refresh(as_of, skip_api=args.snapshot_only)
    log("=== refresh done ===")


if __name__ == "__main__":
    main()
