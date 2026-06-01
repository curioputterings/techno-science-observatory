"""Shared spine: the 9 leading-tech domains, 5 complexity tiers, volume bands.

This is the single source of truth used by every layer (Gemini research ingest,
the ATS enrichment classifier, the store, and the dashboard) so all outputs are
directly comparable. Phase 1 deliverable.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 9 domains. `anchors` are lowercase keyword cues used by the rules/ATS path and
# injected into Gemini prompts so both classifiers share one vocabulary.
# ---------------------------------------------------------------------------
DOMAINS: dict[str, dict] = {
    "semiconductors": {
        "label": "Semiconductors",
        "anchors": ["semiconductor", "chip design", "asic", "fpga", "lithography",
                    "euv", "wafer", "fab", "rtl", "vlsi", "cmos", "verilog",
                    "advanced packaging", "chiplet", "ic design", "tape-out"],
    },
    "quantum": {
        "label": "Quantum",
        "anchors": ["quantum comput", "qubit", "quantum sensing",
                    "quantum communication", "quantum cryptograph", "ion trap",
                    "superconducting qubit", "quantum error correction", "cryogenic"],
    },
    "precision_engineering": {
        "label": "Precision Engineering",
        "anchors": ["precision engineer", "robotics", "mechatronic", "photonic",
                    "mems", "metrology", "optomechanic", "motion control",
                    "actuator", "optical engineer", "laser engineer"],
    },
    "advanced_materials": {
        "label": "Advanced Materials",
        "anchors": ["nanomaterial", "composite", "superconductor", "graphene",
                    "metallurg", "thin film", "crystal growth", "materials scien",
                    "ceramic", "perovskite", "battery material"],
    },
    "biomedical": {
        "label": "Biomedical / Bio",
        "anchors": ["synthetic biology", "bioengineer", "genomic", "crispr",
                    "bioinformatic", "cell therapy", "gene therapy",
                    "tissue engineer", "protein engineer", "biosensor",
                    "bioprocess", "fermentation", "biochemical"],
    },
    "pharmaceuticals": {
        "label": "Pharmaceuticals",
        "anchors": ["drug discovery", "medicinal chemist", "clinical development",
                    "biologics", "pharmacolog", "preclinical", "gmp manufactur",
                    "formulation scien", "mrna", "vaccine", "clinical trial"],
    },
    "digital": {
        "label": "Digital",
        "anchors": ["cloud architect", "edge computing", "cybersecurity",
                    "kubernetes", "distributed systems", "devops",
                    "site reliability", "platform engineer", "data engineer",
                    "5g", "embedded systems", "firmware"],
    },
    "artificial_intelligence": {
        "label": "Artificial Intelligence",
        "anchors": ["machine learning", "deep learning", "ml engineer",
                    "ai research", "computer vision", "nlp", "llm",
                    "neural network", "reinforcement learning", "mlops",
                    "generative ai", "foundation model"],
    },
    "other_frontier": {
        "label": "Other Frontier",
        "anchors": ["space", "satellite", "aerospace", "propulsion", "fusion",
                    "plasma", "nuclear", "hydrogen", "additive manufactur",
                    "3d printing", "carbon capture", "rocket"],
    },
}

ALL_DOMAINS: list[str] = list(DOMAINS.keys())
DOMAIN_LABELS: dict[str, str] = {k: v["label"] for k, v in DOMAINS.items()}

# Map the existing scraper's SKILL_PATTERNS keys onto the 9 domains so the ATS
# layer's skill_flags fold in without loss (CLAUDE.md continuity).
SKILL_TO_DOMAIN: dict[str, str] = {
    "ai_ml": "artificial_intelligence",
    "rtl_design": "semiconductors",
    "advanced_pkg": "semiconductors",
    "photonics": "precision_engineering",
    "synbio": "biomedical",
    "quantum": "quantum",
    "nuclear": "other_frontier",
    # "cleared_dual_use" is a cross-cutting flag, not a domain -> left unmapped
}

# ---------------------------------------------------------------------------
# Complexity tiers 1..5 (the skill-level axis).
# ---------------------------------------------------------------------------
COMPLEXITY_TIERS: dict[int, str] = {
    1: "entry",        # technician / support / junior / internship
    2: "applied",      # standard professional engineering / lab work
    3: "specialist",   # domain-deep senior individual contributor
    4: "expert",       # principal / staff / PhD-level R&D
    5: "frontier",     # cutting-edge research, world-first, lead scientist
}

# ---------------------------------------------------------------------------
# Volume bands (the quantity axis) — ordinal so they chart and compare cleanly,
# while honestly signalling these start as estimates, not exact counts.
# ordinal -> (key, human label, rough monthly-postings hint)
# ---------------------------------------------------------------------------
VOLUME_BANDS: dict[int, dict] = {
    0: {"key": "none", "label": "None / negligible", "hint": "~0"},
    1: {"key": "very_low", "label": "Very low", "hint": "1-50"},
    2: {"key": "low", "label": "Low", "hint": "50-250"},
    3: {"key": "medium", "label": "Medium", "hint": "250-1k"},
    4: {"key": "high", "label": "High", "hint": "1k-5k"},
    5: {"key": "very_high", "label": "Very high", "hint": "5k+"},
}
VOLUME_KEY_TO_ORD: dict[str, int] = {v["key"]: k for k, v in VOLUME_BANDS.items()}

# precision ratchet: how trustworthy a cell's volume is (bands -> absolute)
PRECISION_LEVELS = ["band", "partial_count", "counted"]

CONFIDENCE_LEVELS = ["low", "medium", "high"]
