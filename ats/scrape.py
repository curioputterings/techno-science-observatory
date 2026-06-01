"""Scrape live ATS boards -> classify -> aggregate -> store counted cells.

Phase 3 (L0a). Reads the verified registry (data/ats_registry.json from probe.py),
pulls every open posting from each live board, classifies each by domain +
complexity tier + country, then aggregates into (country, domain) cells written
with source='ats' and an honest precision:
  - counted        >= MIN_COUNTED postings observed in that cell
  - partial_count  fewer than that (real, but thin)

These cells coexist with the gemini_research cells (separate source) so the
dashboard can show verified counts alongside the global estimates.

Stdlib only. Run:  python3 ats/scrape.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import taxonomy  # noqa: E402
from ats.classify import classify_posting  # noqa: E402
from store import Store  # noqa: E402

REGISTRY = ROOT / "data" / "ats_registry.json"
RAW_DIR = ROOT / "data" / "ats_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
LOG = ROOT / "data" / "research" / "ats_run.log"

UA = "technoscience-foresight-research/0.2 (research; contact: research@example.org)"
MIN_COUNTED = 3          # >= this many postings -> precision 'counted'
POLITE_DELAY_S = 1.0

# Map an absolute posting count in a cell to the shared 0..5 volume band.
# ATS boards are per-company, so even modest counts are meaningful signal.
def count_to_volume_ord(n: int) -> int:
    if n <= 0:
        return 0
    if n <= 2:
        return 1
    if n <= 5:
        return 2
    if n <= 15:
        return 3
    if n <= 40:
        return 4
    return 5


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buf = []

    def handle_data(self, d):
        self.buf.append(d)

    def text(self):
        return " ".join(self.buf)


def strip_html(html: str) -> str:
    p = _Text()
    try:
        p.feed(html or "")
    except Exception:  # noqa: BLE001
        return html or ""
    return p.text()


def _get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_board(board: dict) -> list[dict]:
    """Return normalized postings: {title, text, location} for one board."""
    kind, ref = board["kind"], board["ref"]
    out = []
    if kind == "greenhouse":
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{ref}/jobs?content=true")
        for j in data.get("jobs", []):
            out.append({
                "title": j.get("title", ""),
                "text": strip_html(j.get("content", "")),
                "location": (j.get("location") or {}).get("name", ""),
            })
    elif kind == "lever":
        data = _get(f"https://api.lever.co/v0/postings/{ref}?mode=json")
        for j in data:
            out.append({
                "title": j.get("text", ""),
                "text": j.get("descriptionPlain", ""),
                "location": (j.get("categories") or {}).get("location", ""),
            })
    elif kind == "ashby":
        data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{ref}?includeCompensation=true")
        for j in data.get("jobs", []):
            out.append({
                "title": j.get("title", ""),
                "text": j.get("descriptionPlain", "") or "",
                "location": j.get("location", "") or "",
            })
    return out


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
    log(f"=== ATS scrape {as_of}: {len(boards)} boards ===")

    # aggregate: (country, domain) -> {n, tier_sum, employers:set}
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"n": 0, "tier_sum": 0, "employers": set()})
    classified = unclassified = no_country = 0
    snapshot_rows = []

    for b in boards:
        try:
            postings = fetch_board(b)
        except Exception as e:  # noqa: BLE001
            log(f"[err] {b['name']}: {e!r}")
            continue
        for p in postings:
            c = classify_posting(p["title"], p["text"], p["location"], b.get("sector"))
            dom, tier, country = c["domain"], c["tier"], c["country"]
            if not dom:
                unclassified += 1
                continue
            # ATS postings with no parseable country: attribute to US only if the
            # board is a US company default? No — be honest, skip country-less.
            if not country:
                no_country += 1
                continue
            classified += 1
            cell = agg[(country, dom)]
            cell["n"] += 1
            cell["tier_sum"] += tier
            cell["employers"].add(b["name"])
        snapshot_rows.append({"board": b["name"], "kind": b["kind"],
                              "open_jobs": len(postings)})
        log(f"[ok] {b['name']:22} {len(postings)} postings")
        time.sleep(POLITE_DELAY_S)

    (RAW_DIR / f"scrape_{as_of}.json").write_text(json.dumps(snapshot_rows, indent=2))

    # build + write cells (upsert_many commits internally)
    cells = []
    for (country, dom), v in agg.items():
        n = v["n"]
        avg_tier = round(v["tier_sum"] / n) if n else 2
        cells.append({
            "country_iso": country,
            "country_name": "",  # filled from gemini cells in the dashboard join
            "domain": dom,
            "volume_band": list(taxonomy.VOLUME_BANDS.values())[count_to_volume_ord(n)]["key"],
            "volume_ord": count_to_volume_ord(n),
            "volume_estimate": f"{n} open ATS postings",
            "skill_level": max(1, min(5, avg_tier)),
            "frontier": 0.0,
            "rationale": f"{n} live postings from {len(v['employers'])} ATS board(s): "
                         + ", ".join(sorted(v["employers"])[:4]),
            "evidence": sorted(v["employers"]),
            "confidence": "high",
            "precision": "counted" if n >= MIN_COUNTED else "partial_count",
            "source": "ats",
            "as_of": as_of,
        })
    store = Store()
    written = store.upsert_many(cells)
    total_ats = store.conn.execute(
        "SELECT COUNT(*) FROM cells WHERE source='ats'").fetchone()[0]
    store.close()

    log(f"=== done. classified={classified} unclassified={unclassified} "
        f"no_country={no_country} | cells written={written} | ats cells total={total_ats} ===")
    return {"classified": classified, "cells": written, "ats_total": total_ats}


if __name__ == "__main__":
    run()
