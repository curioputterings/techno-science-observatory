"""Shared spine: the 30 leading-tech domains, 5 complexity tiers, volume bands.

This is the single source of truth used by every layer (Gemini research ingest,
the ATS enrichment classifier, the store, and the dashboard) so all outputs are
directly comparable. Phase 1 deliverable.

v2 (30 domains): each domain rolls up to one of the original 9 PARENTS via
`parent`, so historical 9-domain snapshots in cell_history stay comparable
through `rollup_to_parent`. The finer grain gives the complexity engine a
non-degenerate country×domain matrix (ECI/PCI were unreliable at 9).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# The 9 PARENT groups (the original v1 domains) — kept as rollup buckets so
# pre-expansion snapshots and trends remain directly comparable.
# ---------------------------------------------------------------------------
PARENT_LABELS: dict[str, str] = {
    "semiconductors": "Semiconductors",
    "quantum": "Quantum",
    "precision_engineering": "Precision Engineering",
    "advanced_materials": "Advanced Materials",
    "biomedical": "Biomedical / Bio",
    "pharmaceuticals": "Pharmaceuticals",
    "digital": "Digital",
    "artificial_intelligence": "Artificial Intelligence",
    "other_frontier": "Other Frontier",
}

# ---------------------------------------------------------------------------
# 30 domains. `anchors` are lowercase keyword cues used by the rules/ATS path and
# injected into Gemini prompts so both classifiers share one vocabulary. `parent`
# is the v1 group this domain rolls up to.
# ---------------------------------------------------------------------------
DOMAINS: dict[str, dict] = {
    # --- Semiconductors (4) ---
    "chip_design": {
        "label": "Chip & IC Design", "parent": "semiconductors",
        "anchors": ["chip design", "asic", "fpga", "rtl", "vlsi", "verilog",
                    "soc design", "ic design", "tape-out", "eda", "physical design",
                    "logic design", "place and route", "cmos design"],
    },
    "memory_devices": {
        "label": "Memory & Storage Devices", "parent": "semiconductors",
        "anchors": ["dram", "nand", "flash memory", "sram", "memory design",
                    "storage device", "mram", "3d nand", "memory controller", "hbm"],
    },
    "advanced_packaging": {
        "label": "Advanced Packaging", "parent": "semiconductors",
        "anchors": ["advanced packaging", "chiplet", "2.5d", "3d ic",
                    "heterogeneous integration", "wafer bonding", "interposer",
                    "fan-out", "hybrid bonding", "tsv"],
    },
    "semi_equipment": {
        "label": "Fab Equipment & Lithography", "parent": "semiconductors",
        "anchors": ["lithography", "euv", "wafer", "fab", "cleanroom",
                    "deposition", "etch", "cmp", "process engineer",
                    "semiconductor equipment", "ion implantation", "metrology tool"],
    },
    # --- Quantum (2) ---
    "quantum_computing": {
        "label": "Quantum Computing", "parent": "quantum",
        "anchors": ["quantum comput", "qubit", "superconducting qubit", "ion trap",
                    "quantum error correction", "quantum algorithm", "cryogenic",
                    "quantum processor", "transmon"],
    },
    "quantum_comms_sensing": {
        "label": "Quantum Comms & Sensing", "parent": "quantum",
        "anchors": ["quantum communication", "quantum cryptograph",
                    "quantum key distribution", "qkd", "quantum sensing",
                    "quantum metrology", "quantum network", "single photon"],
    },
    # --- Precision Engineering (4) ---
    "robotics_motion": {
        "label": "Robotics & Motion Control", "parent": "precision_engineering",
        "anchors": ["robotics", "mechatronic", "motion control", "actuator",
                    "servo", "industrial robot", "manipulator", "kinematics",
                    "control systems"],
    },
    "photonics_optics": {
        "label": "Photonics & Optics", "parent": "precision_engineering",
        "anchors": ["photonic", "optical engineer", "laser engineer", "optics",
                    "fiber optic", "optoelectronic", "lidar", "optical design",
                    "silicon photonics"],
    },
    "mems_metrology": {
        "label": "MEMS & Metrology", "parent": "precision_engineering",
        "anchors": ["mems", "metrology", "optomechanic", "microfabrication",
                    "sensor design", "inertial sensor", "precision measurement",
                    "nanopositioning"],
    },
    "additive_mfg": {
        "label": "Additive Manufacturing", "parent": "precision_engineering",
        "anchors": ["additive manufactur", "3d printing", "directed energy deposition",
                    "selective laser melting", "powder bed fusion", "binder jetting",
                    "metal printing"],
    },
    # --- Advanced Materials (3) ---
    "nanomaterials": {
        "label": "Nanomaterials", "parent": "advanced_materials",
        "anchors": ["nanomaterial", "graphene", "carbon nanotube", "nanostructure",
                    "thin film", "nanotech", "2d material", "quantum dot"],
    },
    "energy_storage": {
        "label": "Energy Storage & Batteries", "parent": "advanced_materials",
        "anchors": ["battery material", "lithium-ion", "solid-state battery",
                    "electrolyte", "cathode", "anode", "energy storage",
                    "supercapacitor", "battery cell"],
    },
    "composites_polymers": {
        "label": "Composites & Polymers", "parent": "advanced_materials",
        "anchors": ["composite", "polymer", "ceramic", "metallurg", "alloy",
                    "crystal growth", "superconductor", "perovskite", "coating"],
    },
    # --- Biomedical (3) ---
    "genomics": {
        "label": "Genomics & Genetic Engineering", "parent": "biomedical",
        "anchors": ["genomic", "crispr", "gene editing", "dna sequencing",
                    "genetic engineer", "bioinformatic", "computational biology",
                    "genome"],
    },
    "cell_gene_therapy": {
        "label": "Cell & Gene Therapy", "parent": "biomedical",
        "anchors": ["cell therapy", "gene therapy", "car-t", "stem cell",
                    "tissue engineer", "regenerative medicine", "immunotherapy",
                    "viral vector"],
    },
    "synbio_bioprocess": {
        "label": "Synthetic Biology & Bioprocess", "parent": "biomedical",
        "anchors": ["synthetic biology", "bioprocess", "fermentation",
                    "protein engineer", "biosensor", "biochemical",
                    "metabolic engineering", "biomanufacturing"],
    },
    # --- Pharmaceuticals (3) ---
    "drug_discovery": {
        "label": "Small-Molecule Drug Discovery", "parent": "pharmaceuticals",
        "anchors": ["drug discovery", "medicinal chemist", "preclinical",
                    "small molecule", "lead optimization", "pharmacolog",
                    "assay development", "hit-to-lead"],
    },
    "biologics_vaccines": {
        "label": "Biologics & Vaccines", "parent": "pharmaceuticals",
        "anchors": ["biologics", "mrna", "vaccine", "antibody", "monoclonal",
                    "immunogen", "antigen", "protein therapeutic"],
    },
    "pharma_mfg": {
        "label": "Pharma Manufacturing & Formulation", "parent": "pharmaceuticals",
        "anchors": ["gmp manufactur", "formulation scien", "fill-finish",
                    "drug product", "clinical development", "clinical trial",
                    "process development", "bioreactor"],
    },
    # --- Digital (4) ---
    "cloud_distributed": {
        "label": "Cloud & Distributed Systems", "parent": "digital",
        "anchors": ["cloud architect", "distributed systems", "kubernetes",
                    "devops", "site reliability", "platform engineer",
                    "microservices", "serverless", "data engineer"],
    },
    "cybersecurity": {
        "label": "Cybersecurity", "parent": "digital",
        "anchors": ["cybersecurity", "security engineer", "penetration test",
                    "cryptograph", "zero trust", "threat detection",
                    "application security", "soc analyst"],
    },
    "networks_5g": {
        "label": "Networks & 5G/6G", "parent": "digital",
        "anchors": ["5g", "6g", "telecom", "ran", "wireless", "network engineer",
                    "baseband", "sdn", "optical network"],
    },
    "embedded_iot": {
        "label": "Embedded & IoT", "parent": "digital",
        "anchors": ["embedded systems", "firmware", "iot", "rtos", "edge computing",
                    "microcontroller", "device driver", "embedded software"],
    },
    # --- Artificial Intelligence (3) ---
    "machine_learning": {
        "label": "Machine & Deep Learning", "parent": "artificial_intelligence",
        "anchors": ["machine learning", "deep learning", "ml engineer",
                    "neural network", "reinforcement learning", "mlops",
                    "model training", "ml research"],
    },
    "generative_nlp": {
        "label": "Generative AI & NLP", "parent": "artificial_intelligence",
        "anchors": ["nlp", "llm", "generative ai", "foundation model",
                    "large language model", "transformer", "prompt engineering",
                    "speech recognition"],
    },
    "computer_vision": {
        "label": "Computer Vision", "parent": "artificial_intelligence",
        "anchors": ["computer vision", "image recognition", "object detection",
                    "image processing", "visual perception", "scene understanding",
                    "video analytics"],
    },
    # --- Other Frontier (4) ---
    "space_aerospace": {
        "label": "Space & Aerospace", "parent": "other_frontier",
        "anchors": ["space", "satellite", "aerospace", "propulsion", "rocket",
                    "launch vehicle", "spacecraft", "avionics", "orbital"],
    },
    "fusion_nuclear": {
        "label": "Fusion & Advanced Nuclear", "parent": "other_frontier",
        "anchors": ["fusion", "plasma", "nuclear", "tokamak", "reactor",
                    "small modular reactor", "magnetic confinement", "fission"],
    },
    "hydrogen_fuelcells": {
        "label": "Hydrogen & Fuel Cells", "parent": "other_frontier",
        "anchors": ["hydrogen", "fuel cell", "electrolyzer", "green hydrogen",
                    "electrolysis", "hydrogen storage", "pem"],
    },
    "carbon_capture": {
        "label": "Carbon Capture & Climate Tech", "parent": "other_frontier",
        "anchors": ["carbon capture", "direct air capture", "ccs",
                    "co2 utilization", "climate tech", "carbon sequestration", "dac"],
    },
}

ALL_DOMAINS: list[str] = list(DOMAINS.keys())
DOMAIN_LABELS: dict[str, str] = {k: v["label"] for k, v in DOMAINS.items()}
DOMAIN_PARENT: dict[str, str] = {k: v["parent"] for k, v in DOMAINS.items()}

# children grouped under each parent (preserves display order)
PARENT_CHILDREN: dict[str, list[str]] = {
    p: [k for k, v in DOMAINS.items() if v["parent"] == p] for p in PARENT_LABELS
}
# a representative child per parent — used to resolve a parent-level hint
# (e.g. an ATS employer tagged 'artificial_intelligence') to a concrete domain.
PARENT_DEFAULT_CHILD: dict[str, str] = {p: kids[0] for p, kids in PARENT_CHILDREN.items()}


def rollup_to_parent(domain: str) -> str:
    """Map a domain (or an already-parent key) to its v1 parent group key."""
    if domain in DOMAIN_PARENT:
        return DOMAIN_PARENT[domain]
    return domain  # already a parent (e.g. historical 9-domain rows)


def resolve_domain(key: str) -> str | None:
    """Normalise a domain hint to a concrete domain key.

    Accepts a child key (returned as-is) or a parent key (mapped to its default
    child). Returns None if unknown — callers treat that as 'no hint'.
    """
    if key in DOMAINS:
        return key
    if key in PARENT_DEFAULT_CHILD:
        return PARENT_DEFAULT_CHILD[key]
    return None


# Map the existing scraper's SKILL_PATTERNS keys onto domains so the ATS layer's
# skill_flags fold in without loss (CLAUDE.md continuity).
SKILL_TO_DOMAIN: dict[str, str] = {
    "ai_ml": "machine_learning",
    "rtl_design": "chip_design",
    "advanced_pkg": "advanced_packaging",
    "photonics": "photonics_optics",
    "synbio": "synbio_bioprocess",
    "quantum": "quantum_computing",
    "nuclear": "fusion_nuclear",
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
