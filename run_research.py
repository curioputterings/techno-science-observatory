"""Generate the global country x domain capability table with Gemini, then ingest.

    python run_research.py            # all 9 domains
    python run_research.py quantum    # one domain

Writes data/research/<domain>.json (the cited raw output) and loads cells into
data/jobs.db. Logs progress to data/research/run.log too (sandbox-friendly).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import gemini_client
import research
import taxonomy
from store import Store

LOG = research.RESEARCH_DIR / "run.log"


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run(domains: list[str], as_of: str) -> dict:
    schema = gemini_client.domain_schema()
    summary = {}
    for key in domains:
        try:
            payload = gemini_client.structured(research.build_prompt(key), schema)
            payload["domain"] = key  # enforce our key regardless of model echo
            out = research.RESEARCH_DIR / f"{key}.json"
            out.write_text(json.dumps(payload, indent=2))
            n = research.ingest_payload(payload, as_of=as_of)
            log(f"[ok] {key}: {n} cells -> {out.name}")
            summary[key] = n
        except Exception as e:  # noqa: BLE001
            log(f"[err] {key}: {e}")
            summary[key] = 0
    return summary


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not gemini_client.ready():
        log("ERROR: GEMINI_API_KEY missing in .env")
        sys.exit(1)
    domains = argv or taxonomy.ALL_DOMAINS
    bad = [d for d in domains if d not in taxonomy.ALL_DOMAINS]
    if bad:
        log(f"ERROR: unknown domains {bad}. Valid: {taxonomy.ALL_DOMAINS}")
        sys.exit(1)
    as_of = dt.date.today().isoformat()
    log(f"=== run model={gemini_client.MODEL} domains={domains} as_of={as_of} ===")
    summary = run(domains, as_of)
    store = Store()
    total = store.count()
    store.close()
    log(f"=== done. per-domain={summary} | db total cells={total} ===")


if __name__ == "__main__":
    main()
