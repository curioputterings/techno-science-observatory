"""Fill gaps left by a network-interrupted refresh.

Designed for a laptop that moves between networks: run `refresh.py` whenever, and
if a wifi/VPN handoff made some Gemini domains time out (they keep their prior
values — never zeroed), run this from a stable connection to top up ONLY the
domains that are still stale for today. Idempotent: re-run as many times as you
like; each run re-pulls just what's missing and re-snapshots today.

    python3 refresh_gaps.py            # detect + fill capability and ambition gaps
    python3 refresh_gaps.py --dry-run  # just report which domains are stale

Resilience lives in gemini_client.structured (long backoff on connectivity errors);
this script adds an outer per-domain retry so one stubborn domain can't stall the run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time

import ambition
import gemini_client
import research
import taxonomy
from store import Store


def _fresh_domains(as_of: str) -> tuple[set, set]:
    """Domains already refreshed today, for (capability, ambition)."""
    import sqlite3
    from store import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cap = {r[0] for r in conn.execute(
        "SELECT DISTINCT domain FROM cells WHERE source='gemini_research' AND as_of=?",
        (as_of,))}
    amb = {r[0] for r in conn.execute(
        "SELECT DISTINCT domain FROM ambition WHERE as_of=?", (as_of,))}
    conn.close()
    return cap, amb


def _with_retry(fn, label, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            wait = 15 * (i + 1)
            print(f"  [retry {i + 1}/{tries}] {label}: {e} -> sleep {wait}s", flush=True)
            time.sleep(wait)
    print(f"  [GIVEUP] {label} — still stale, run again later", flush=True)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Re-pull only the domains a flaky refresh missed")
    ap.add_argument("--dry-run", action="store_true", help="report stale domains, pull nothing")
    args = ap.parse_args(argv)

    as_of = dt.date.today().isoformat()
    store = Store()
    cap_fresh, amb_fresh = _fresh_domains(as_of)
    all_domains = set(taxonomy.ALL_DOMAINS)
    cap_gaps = sorted(all_domains - cap_fresh)
    amb_gaps = sorted(all_domains - amb_fresh)

    print(f"=== gaps for {as_of}: capability {len(cap_gaps)}/{len(all_domains)} stale, "
          f"ambition {len(amb_gaps)}/{len(all_domains)} stale ===", flush=True)
    if cap_gaps:
        print(f"  capability stale: {cap_gaps}", flush=True)
    if amb_gaps:
        print(f"  ambition stale:   {amb_gaps}", flush=True)

    if args.dry_run:
        store.close()
        return
    if not cap_gaps and not amb_gaps:
        print("nothing to do — panel is fully fresh for today.", flush=True)
        store.close()
        return
    if not gemini_client.ready():
        print("ERROR: GEMINI_API_KEY missing.", flush=True)
        sys.exit(1)

    schema = gemini_client.domain_schema()
    for key in cap_gaps:
        def _do(key=key):
            payload = gemini_client.structured(research.build_prompt(key), schema)
            payload["domain"] = key
            (research.RESEARCH_DIR / f"{key}.json").write_text(json.dumps(payload, indent=2))
            return research.ingest_payload(payload, as_of=as_of)
        n = _with_retry(_do, f"capability {key}")
        print(f"  capability {key}: {n} cells", flush=True)

    for key in amb_gaps:
        n = _with_retry(lambda key=key: ambition.run([key], as_of).get(key, 0), f"ambition {key}")
        print(f"  ambition {key}: {n} cells", flush=True)

    n = store.snapshot(as_of)
    store.close()
    print(f"=== re-snapshot {as_of}: {n} cells | done ===", flush=True)


if __name__ == "__main__":
    main()
