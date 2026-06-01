"""Gemini-research layer (L0b): turn grounded research into country x domain cells.

For now Gemini is driven *interactively* via the MCP this session: we build a
prompt + JSON schema per domain, paste Gemini's structured JSON into
data/research/<domain>.json, and ingest it here. When a Gemini API key is added
later, the same prompt/schema can be called in batch with no other changes.
"""
from __future__ import annotations

import json
from pathlib import Path

import taxonomy
from store import DATA_DIR, Store

RESEARCH_DIR = DATA_DIR / "research"

# Curated set of deep-tech-relevant economies for the first global pass.
# (ISO-2 -> name). Extend freely; the matrix simply grows.
TARGET_COUNTRIES: dict[str, str] = {
    "US": "United States", "CN": "China", "JP": "Japan", "KR": "South Korea",
    "TW": "Taiwan", "DE": "Germany", "NL": "Netherlands", "GB": "United Kingdom",
    "FR": "France", "IL": "Israel", "IN": "India", "SG": "Singapore",
    "CH": "Switzerland", "SE": "Sweden", "FI": "Finland", "CA": "Canada",
    "AU": "Australia", "IE": "Ireland", "BE": "Belgium", "AT": "Austria",
    "IT": "Italy", "ES": "Spain", "MY": "Malaysia", "VN": "Vietnam",
    "TH": "Thailand", "ID": "Indonesia", "AE": "United Arab Emirates",
    "SA": "Saudi Arabia", "BR": "Brazil", "PL": "Poland",
}

# JSON schema (string) for gemini-structured: one domain -> list of country cells.
DOMAIN_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "cells": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "country_iso": {"type": "string", "description": "ISO-3166 alpha-2"},
                    "country_name": {"type": "string"},
                    "volume_band": {
                        "type": "string",
                        "enum": [b["key"] for b in taxonomy.VOLUME_BANDS.values()],
                        "description": "relative hiring volume for this domain",
                    },
                    "skill_level": {
                        "type": "integer",
                        "description": "typical complexity tier 1-5 (1 entry .. 5 frontier)",
                    },
                    "frontier": {
                        "type": "number",
                        "description": "0-1: presence of genuine frontier/tier-5 R&D",
                    },
                    "rationale": {"type": "string", "description": "<=25 words"},
                    "evidence": {
                        "type": "array", "items": {"type": "string"},
                        "description": "short source/anchor descriptors (orgs, programmes, reports)",
                    },
                    "confidence": {"type": "string", "enum": taxonomy.CONFIDENCE_LEVELS},
                },
                "required": ["country_iso", "country_name", "volume_band",
                             "skill_level", "frontier", "confidence"],
            },
        },
    },
    "required": ["domain", "cells"],
})


def build_prompt(domain_key: str) -> str:
    d = taxonomy.DOMAINS[domain_key]
    countries = ", ".join(f"{iso} ({name})" for iso, name in TARGET_COUNTRIES.items())
    tiers = "; ".join(f"{k}={v}" for k, v in taxonomy.COMPLEXITY_TIERS.items())
    bands = "; ".join(f"{b['key']}={b['label']} ({b['hint']}/mo)"
                      for b in taxonomy.VOLUME_BANDS.values())
    return f"""You are a labour-market + technology-capability analyst. Use grounded
search. Assess the **{d['label']}** domain (cues: {', '.join(d['anchors'][:10])}).

For EACH of these countries, estimate the current advanced-{d['label']} job
market and report one cell:
{countries}

Definitions:
- volume_band (relative advanced-role hiring volume): {bands}
- skill_level (typical complexity tier): {tiers}
- frontier (0-1): how much genuine tier-5 frontier R&D exists (labs, world-first work)
- evidence: name the concrete anchors you reasoned from (major firms, fabs/labs,
  national programmes, industry reports) — be specific, these are auditable.
- confidence: your confidence in the estimate.

Be realistic and differentiate countries. Return JSON matching the schema.
These are honest ESTIMATES, not exact counts."""


def ingest_payload(payload: dict, as_of: str, source: str = "gemini_research") -> int:
    """Validate a single-domain Gemini payload and write its cells to the store."""
    domain = payload.get("domain")
    if domain not in taxonomy.ALL_DOMAINS:
        # tolerate label instead of key
        rev = {v.lower(): k for k, v in taxonomy.DOMAIN_LABELS.items()}
        domain = rev.get(str(domain).lower(), domain)
    if domain not in taxonomy.ALL_DOMAINS:
        raise ValueError(f"Unknown domain in payload: {payload.get('domain')!r}")

    store = Store()
    cells = []
    for c in payload.get("cells", []):
        band = c.get("volume_band")
        if band not in taxonomy.VOLUME_KEY_TO_ORD:
            continue
        try:
            skill = max(1, min(5, int(c.get("skill_level", 2))))
        except (TypeError, ValueError):
            skill = 2
        cells.append({
            "country_iso": str(c["country_iso"]).upper()[:2],
            "country_name": c.get("country_name", ""),
            "domain": domain,
            "volume_band": band,
            "volume_ord": taxonomy.VOLUME_KEY_TO_ORD[band],
            "volume_estimate": c.get("volume_estimate"),
            "skill_level": skill,
            "frontier": float(c.get("frontier", 0.0) or 0.0),
            "rationale": c.get("rationale", ""),
            "evidence": c.get("evidence", []),
            "confidence": c.get("confidence", "low"),
            "precision": "band",
            "source": source,
            "as_of": as_of,
        })
    n = store.upsert_many(cells)
    store.close()
    return n


def ingest_file(path: str | Path, as_of: str) -> int:
    payload = json.loads(Path(path).read_text())
    return ingest_payload(payload, as_of=as_of)


def ingest_all(as_of: str) -> int:
    """Ingest every data/research/<domain>.json present."""
    total = 0
    for key in taxonomy.ALL_DOMAINS:
        p = RESEARCH_DIR / f"{key}.json"
        if p.exists():
            total += ingest_file(p, as_of=as_of)
            print(f"[ingest] {key}: ok")
        else:
            print(f"[ingest] {key}: (no file yet)")
    return total
