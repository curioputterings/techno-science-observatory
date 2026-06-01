"""Ambition layer (Phase 6): each country's STATED strategic intent per domain.

Jobs reveal a country's *current* trajectory; they cannot show *intent*. This
layer asks Gemini grounded research what each country has publicly committed to —
national strategies, dedicated programmes, R&D budgets, headline FDI / fab / lab
announcements — and scores, per (country, domain):

    ambition      0..5  strength of national strategic intent / prioritisation
    target_level  1..5  the skill/complexity tier the country is aiming to reach
    horizon       short | medium | long

This is kept in a SEPARATE table from the revealed-capability `cells`, and is
clearly labelled as *stated intent*, never blended silently with revealed data.
The payoff is the GAP: ambition minus revealed capability (see analysis/gap.py).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini_client
import research  # reuse TARGET_COUNTRIES + RESEARCH_DIR
import taxonomy
from store import Store

AMB_DIR = research.RESEARCH_DIR / "ambition"
AMB_DIR.mkdir(parents=True, exist_ok=True)
LOG = research.RESEARCH_DIR / "ambition_run.log"


def schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "cells": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "country_iso": {"type": "string"},
                        "country_name": {"type": "string"},
                        "ambition": {"type": "integer",
                                     "description": "0-5 strength of stated national intent"},
                        "target_level": {"type": "integer",
                                         "description": "1-5 complexity tier targeted"},
                        "horizon": {"type": "string",
                                    "enum": ["short", "medium", "long"]},
                        "rationale": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "string"},
                                     "description": "named strategies/programmes/budgets/announcements"},
                        "confidence": {"type": "string",
                                       "enum": taxonomy.CONFIDENCE_LEVELS},
                    },
                    "required": ["country_iso", "country_name", "ambition",
                                 "target_level", "horizon", "confidence"],
                },
            },
        },
        "required": ["domain", "cells"],
    }


def build_prompt(domain_key: str) -> str:
    d = taxonomy.DOMAINS[domain_key]
    countries = ", ".join(f"{iso} ({name})"
                          for iso, name in research.TARGET_COUNTRIES.items())
    tiers = "; ".join(f"{k}={v}" for k, v in taxonomy.COMPLEXITY_TIERS.items())
    return f"""You are a science & technology POLICY analyst. Use grounded search.
Assess each country's STATED NATIONAL AMBITION in the **{d['label']}** domain
(cues: {', '.join(d['anchors'][:8])}) — NOT what they currently do, but what they
have publicly committed to building.

Base this on concrete, auditable signals: national strategies & roadmaps,
dedicated government programmes/agencies, earmarked R&D budgets & subsidies,
headline FDI / fab / lab / institute announcements, and explicit targets.

For EACH country report one cell:
{countries}

Scoring:
- ambition (0-5): strength of stated strategic intent / prioritisation
  (0 = none/not a stated priority, 5 = flagship national priority with funded plan)
- target_level (1-5): the complexity tier the country is aiming to REACH ({tiers})
- horizon: short (<3y) | medium (3-7y) | long (>7y) for the headline goal
- evidence: NAME the specific strategies/programmes/budgets/announcements
- confidence: your confidence

Differentiate honestly: many countries have NO real ambition in a given domain
(ambition 0-1). A few have flagship funded programmes (ambition 4-5). Return JSON."""


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ingest_payload(payload: dict, as_of: str) -> int:
    domain = payload.get("domain")
    if domain not in taxonomy.ALL_DOMAINS:
        rev = {v.lower(): k for k, v in taxonomy.DOMAIN_LABELS.items()}
        domain = rev.get(str(domain).lower(), domain)
    if domain not in taxonomy.ALL_DOMAINS:
        raise ValueError(f"unknown domain {payload.get('domain')!r}")
    store = Store()
    items = []
    for c in payload.get("cells", []):
        def clamp(v, lo, hi, dflt):
            try:
                return max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                return dflt
        items.append({
            "country_iso": str(c["country_iso"]).upper()[:2],
            "country_name": c.get("country_name", ""),
            "domain": domain,
            "ambition": clamp(c.get("ambition"), 0, 5, 0),
            "target_level": clamp(c.get("target_level"), 1, 5, 2),
            "horizon": c.get("horizon", "medium"),
            "rationale": c.get("rationale", ""),
            "evidence": c.get("evidence", []),
            "confidence": c.get("confidence", "low"),
            "as_of": as_of,
        })
    n = store.upsert_ambitions(items)
    store.close()
    return n


def run(domains: list[str], as_of: str) -> dict:
    sch = schema()
    summary = {}
    for key in domains:
        try:
            payload = gemini_client.structured(build_prompt(key), sch)
            payload["domain"] = key
            (AMB_DIR / f"{key}.json").write_text(json.dumps(payload, indent=2))
            n = ingest_payload(payload, as_of=as_of)
            log(f"[ok] {key}: {n} ambition cells")
            summary[key] = n
        except Exception as e:  # noqa: BLE001
            log(f"[err] {key}: {e}")
            summary[key] = 0
    return summary


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not gemini_client.ready():
        log("ERROR: GEMINI_API_KEY missing")
        sys.exit(1)
    domains = argv or taxonomy.ALL_DOMAINS
    bad = [d for d in domains if d not in taxonomy.ALL_DOMAINS]
    if bad:
        log(f"ERROR unknown domains {bad}")
        sys.exit(1)
    as_of = dt.date.today().isoformat()
    log(f"=== ambition run model={gemini_client.MODEL} domains={domains} as_of={as_of} ===")
    summary = run(domains, as_of)
    store = Store()
    total = store.count_ambition()
    store.close()
    log(f"=== done. per-domain={summary} | ambition cells={total} ===")


if __name__ == "__main__":
    main()
