"""Classify a single ATS posting -> (domain, complexity tier, country).

Reuses the shared taxonomy so ATS output is directly comparable to the Gemini
research cells. Pure stdlib + regex.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import taxonomy  # noqa: E402

# Complexity-tier cues (1 entry .. 5 frontier), highest-priority first.
_TIER_CUES = {
    5: ["principal investigator", "chief scientist", "research lead", "world-first",
        "breakthrough", "fellow", "distinguished"],
    4: ["principal", "staff ", "phd", "ph.d", "research scientist", "lead scientist",
        "senior staff", "architect"],
    3: ["senior", "specialist", "expert", " lead", " iii", "iv ", "5+ years",
        "advanced"],
    1: ["intern", "internship", "junior", "graduate", "apprentice", "trainee",
        "entry-level", "entry level", "technician", " i ", " ii "],
}

# Lightweight country inference from a location string -> ISO-2.
_COUNTRY_PATTERNS = [
    ("US", r"\b(usa|united states|u\.s\.|, ca\b|, tx\b|, ny\b|, wa\b|, ma\b|"
           r"california|texas|new york|washington|seattle|austin|boston|"
           r"san francisco|sunnyvale|santa clara|mountain view|palo alto|"
           r"redmond|hawthorne|remote - us|remote, us)\b"),
    ("GB", r"\b(uk|united kingdom|england|london|cambridge|oxford|manchester|"
           r"bristol|scotland)\b"),
    ("DE", r"\b(germany|deutschland|berlin|munich|münchen|hamburg|frankfurt)\b"),
    ("FR", r"\b(france|paris|grenoble|toulouse|lyon)\b"),
    ("CA", r"\b(canada|toronto|vancouver|montreal|ottawa|waterloo)\b"),
    ("NL", r"\b(netherlands|amsterdam|eindhoven|delft)\b"),
    ("CH", r"\b(switzerland|zurich|zürich|geneva|lausanne)\b"),
    ("IL", r"\b(israel|tel aviv|haifa|jerusalem)\b"),
    ("IN", r"\b(india|bangalore|bengaluru|hyderabad|pune|mumbai|delhi|chennai)\b"),
    ("SG", r"\b(singapore)\b"),
    ("JP", r"\b(japan|tokyo|osaka)\b"),
    ("KR", r"\b(korea|seoul)\b"),
    ("TW", r"\b(taiwan|taipei|hsinchu)\b"),
    ("AU", r"\b(australia|sydney|melbourne|canberra)\b"),
    ("IE", r"\b(ireland|dublin)\b"),
    ("SE", r"\b(sweden|stockholm)\b"),
    ("ES", r"\b(spain|madrid|barcelona)\b"),
    ("IT", r"\b(italy|rome|milan|turin)\b"),
    ("PL", r"\b(poland|warsaw|krakow|kraków|wroclaw)\b"),
    ("AE", r"\b(uae|united arab emirates|dubai|abu dhabi)\b"),
    ("SA", r"\b(saudi|riyadh|neom|jeddah)\b"),
    ("BR", r"\b(brazil|brasil|são paulo|sao paulo)\b"),
]


def infer_country(location: str) -> str | None:
    loc = (location or "").lower()
    for iso, pat in _COUNTRY_PATTERNS:
        if re.search(pat, loc):
            return iso
    return None


def classify_domain(text: str, fallback_sector: str | None = None) -> str | None:
    t = (text or "").lower()
    best, best_hits = None, 0
    for domain, meta in taxonomy.DOMAINS.items():
        hits = sum(1 for kw in meta["anchors"] if kw in t)
        if hits > best_hits:
            best, best_hits = domain, hits
    if best:
        return best
    # fall back to the employer's sector tag if text was uninformative.
    # Accepts a domain key or a parent group key (resolved to its default child).
    if fallback_sector:
        return taxonomy.resolve_domain(fallback_sector)
    return None


def complexity_tier(title: str, text: str) -> int:
    blob = f" {title} {text} ".lower()
    for tier in (5, 4, 1, 3):  # extremes before the generic 'senior' bucket
        for cue in _TIER_CUES[tier]:
            if cue in blob:
                return tier
    return 2  # default applied professional


# ---------------------------------------------------------------------------
# Business function — WHERE in the value chain a role sits. This is what reveals
# cross-border division of labour: the same MNC doing R&D in one country,
# manufacturing/test in another, commercial ops in a third.
# Title cues are weighted heaviest; checked most-specific first.
# ---------------------------------------------------------------------------
FUNCTIONS: dict[str, dict] = {
    "research": {
        "label": "Research / R&D",
        "title": ["research scientist", "research engineer", "researcher",
                  "research lead", "principal investigator", "member of technical staff",
                  "research fellow", "scientist", "postdoc"],
        "text": ["publish", "novel", "state-of-the-art research", "research agenda",
                 "phd in", "first-principles"],
    },
    "engineering": {
        "label": "Engineering / Design",
        "title": ["software engineer", "design engineer", "hardware engineer",
                  "ml engineer", "developer", "architect", "rtl", "asic",
                  "firmware", "systems engineer", "platform engineer", "verification"],
        "text": ["design and build", "develop", "implement", "codebase", "ci/cd"],
    },
    "manufacturing_test": {
        "label": "Manufacturing / Test",
        "title": ["manufacturing", "process engineer", "production", "test engineer",
                  "assembly", "fabrication", "fab ", "yield", "equipment", "technician",
                  "quality engineer", "supply chain", "operations technician"],
        "text": ["production line", "cleanroom", "shop floor", "throughput", "yield",
                 "wafer", "assembly line"],
    },
    "field_deployment": {
        "label": "Field / Deployment",
        "title": ["field engineer", "solutions engineer", "deployment", "site engineer",
                  "installation", "field service", "launch", "integration engineer",
                  "forward deployed"],
        "text": ["on-site", "customer site", "deploy to", "installation"],
    },
    "commercial": {
        "label": "Commercial / GTM",
        "title": ["sales", "account executive", "marketing", "business development",
                  "partnerships", "customer success", "go-to-market", "revenue",
                  "growth", "account manager"],
        "text": ["pipeline", "quota", "close deals", "revenue target"],
    },
    "operations": {
        "label": "Corporate / Ops",
        "title": ["recruiter", "people ops", "human resources", "finance", "legal",
                  "counsel", "accountant", "office manager", "executive assistant",
                  "talent", "payroll", "facilities", "it support"],
        "text": ["headcount", "compliance", "bookkeeping"],
    },
}

FUNCTION_LABELS = {k: v["label"] for k, v in FUNCTIONS.items()}
ALL_FUNCTIONS = list(FUNCTIONS.keys())
# order of resolution: specific value-chain functions before generic corp/ops
_FUNC_ORDER = ["research", "manufacturing_test", "field_deployment",
               "engineering", "commercial", "operations"]


def classify_function(title: str, text: str) -> str:
    t = (title or "").lower()
    tx = (text or "").lower()[:600]
    scores = {}
    for fn in _FUNC_ORDER:
        meta = FUNCTIONS[fn]
        s = 3 * sum(1 for kw in meta["title"] if kw in t)
        s += sum(1 for kw in meta["text"] if kw in tx)
        if s:
            scores[fn] = s
    if not scores:
        return "engineering"  # default: most ATS deep-tech roles are build roles
    # tie-break by _FUNC_ORDER priority
    best = max(scores.values())
    for fn in _FUNC_ORDER:
        if scores.get(fn) == best:
            return fn
    return "engineering"


def classify_posting(title: str, text: str, location: str,
                     sector: str | None = None) -> dict:
    return {
        "domain": classify_domain(f"{title} {text}", fallback_sector=sector),
        "tier": complexity_tier(title, text),
        "country": infer_country(location),
        "function": classify_function(title, text),
    }
