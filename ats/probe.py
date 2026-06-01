"""Probe candidate ATS boards to find which are LIVE (Phase 3 discovery).

Rather than ship a registry of guessed tokens, we test each candidate against the
real public JSON endpoint and keep only those that respond with jobs. Output is a
verified registry (data/ats_registry.json) the scraper then uses.

Stdlib only (urllib). Run:  python3 ats/probe.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ats_registry.json"

UA = "technoscience-foresight-research/0.2 (research; contact: research@example.org)"

# Candidate deep-tech employers. (name, ats_type, token, sector). Tokens are best
# guesses from known board URLs; the probe confirms which are real. Spanning
# semiconductors, quantum, AI, space/fusion, bio — the frontier domains.
CANDIDATES = [
    # --- Greenhouse (token = board name in boards.greenhouse.io/<token>) ---
    ("Nvidia", "greenhouse", "nvidia", "semiconductors"),
    ("AMD", "greenhouse", "amd", "semiconductors"),
    ("Cerebras", "greenhouse", "cerebras", "semiconductors"),
    ("SambaNova", "greenhouse", "sambanovasystems", "semiconductors"),
    ("Groq", "greenhouse", "groq", "semiconductors"),
    ("Tenstorrent", "greenhouse", "tenstorrent", "semiconductors"),
    ("Applied Materials", "greenhouse", "appliedmaterials", "semiconductors"),
    ("PsiQuantum", "greenhouse", "psiquantum", "quantum"),
    ("Rigetti", "greenhouse", "rigetticomputing", "quantum"),
    ("IonQ", "greenhouse", "ionq", "quantum"),
    ("Quantinuum", "greenhouse", "quantinuum", "quantum"),
    ("Anthropic", "greenhouse", "anthropic", "artificial_intelligence"),
    ("Scale AI", "greenhouse", "scaleai", "artificial_intelligence"),
    ("Cohere", "greenhouse", "cohere", "artificial_intelligence"),
    ("Hugging Face", "greenhouse", "huggingface", "artificial_intelligence"),
    ("SpaceX", "greenhouse", "spacex", "other_frontier"),
    ("Relativity Space", "greenhouse", "relativityspace", "other_frontier"),
    ("Commonwealth Fusion", "greenhouse", "commonwealthfusionsystems", "other_frontier"),
    ("Ginkgo Bioworks", "greenhouse", "ginkgobioworks", "biomedical"),
    ("Benchling", "greenhouse", "benchling", "biomedical"),
    ("Recursion", "greenhouse", "recursionpharmaceuticals", "pharmaceuticals"),
    # --- Lever (token = company handle in jobs.lever.co/<token>) ---
    ("Mistral AI", "lever", "mistral", "artificial_intelligence"),
    ("Together AI", "lever", "together", "artificial_intelligence"),
    ("SandboxAQ", "lever", "sandboxaq", "quantum"),
    ("Astranis", "lever", "astranis", "other_frontier"),
    ("Zipline", "lever", "zipline", "other_frontier"),
    # --- Ashby (token = org slug in jobs.ashbyhq.com/<token>) ---
    ("OpenAI", "ashby", "openai", "artificial_intelligence"),
    ("Ramp", "ashby", "ramp", "digital"),
    ("Modal", "ashby", "modal", "digital"),
    ("Atomic Semi", "ashby", "atomic-semi", "semiconductors"),
    ("Etched", "ashby", "etched", "semiconductors"),
]

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
}


def _get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def count_jobs(ats: str, data) -> int:
    if ats == "greenhouse":
        return len(data.get("jobs", [])) if isinstance(data, dict) else 0
    if ats == "lever":
        return len(data) if isinstance(data, list) else 0
    if ats == "ashby":
        return len(data.get("jobs", [])) if isinstance(data, dict) else 0
    return 0


def probe():
    live, dead = [], []
    for name, ats, token, sector in CANDIDATES:
        url = ENDPOINTS[ats].format(t=token)
        try:
            data = _get(url)
            n = count_jobs(ats, data)
            if n > 0:
                live.append({"name": name, "kind": ats, "ref": token,
                             "sector": sector, "open_jobs": n})
                print(f"[LIVE] {name:24} {ats:11} {token:28} {n} jobs")
            else:
                dead.append((name, ats, token, "0 jobs"))
                print(f"[----] {name:24} {ats:11} {token:28} 0 jobs")
        except urllib.error.HTTPError as e:
            dead.append((name, ats, token, f"HTTP {e.code}"))
            print(f"[{e.code:>4}] {name:24} {ats:11} {token:28}")
        except Exception as e:  # noqa: BLE001
            dead.append((name, ats, token, repr(e)[:40]))
            print(f"[ERR ] {name:24} {ats:11} {token:28} {e!r}"[:90])
        time.sleep(0.5)

    OUT.write_text(json.dumps(live, indent=2))
    print(f"\n{len(live)} live / {len(CANDIDATES)} probed  ->  {OUT}")
    print(f"total open jobs across live boards: {sum(b['open_jobs'] for b in live)}")
    return live


if __name__ == "__main__":
    probe()
