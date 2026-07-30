"""Classify a single ATS posting -> (domain, complexity tier, country, function).

Reuses the shared taxonomy so ATS output is directly comparable to the Gemini
research cells. Regex/keyword rules are the fast first pass (free, always
runs); a local LLM (via LM Studio, free) fills in only the fields the rules
couldn't confidently resolve -- a zero/tied domain-anchor match, a tier that
never matched a cue (silently defaulted to 2), or a function that never
matched a cue (silently defaulted to "engineering"). Those silent defaults
were previously indistinguishable from a real, confident classification; this
makes the gap visible and fills it instead of guessing.

A registry board can carry thousands of open postings with roughly half
needing escalation (measured: SpaceX 1829 postings/33%, Anthropic 395/83%,
OpenAI 713/61% -- this is NOT a small-volume feature). Two guards keep that
tractable:
  - a persistent cache (data/classify_cache.db) keyed on posting content, so a
    still-open posting is only ever escalated ONCE across the pipeline's
    lifetime, not re-classified from scratch on every weekly run;
  - a per-process cap (llm_local.ESCALATION_CAP_PER_RUN) on *new* escalations,
    so a run with a large uncached backlog finishes in bounded time instead of
    taking all day -- postings skipped this run for the cap keep their existing
    regex-only default (same as before this feature existed, nothing forced)
    and are picked up on a later run once cache misses come back under budget.

A small residual sample of postings (LLM-escalated or not) also gets an
independent Gemini classification purely for drift auditing -- printed as a
disagreement, never used to override the returned value. There's no
pre-existing "ground truth" classifier here to preserve (unlike ai_work_recomp's
Haiku, which predates its own local tier), so nothing needs to "win": the audit
is diagnostic, for noticing if the taxonomy or prompt needs work.

Pure stdlib + regex + (optional) local/cloud LLM calls.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gemini_client  # noqa: E402
import llm_local  # noqa: E402
import taxonomy  # noqa: E402

# ~1 in N postings (LLM-escalated or not) gets an independent Gemini
# classification for drift-auditing. Diagnostic only -- never overrides.
AUDIT_SAMPLE_RATE = 25

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


# Anchors that are complete acronyms/words, not deliberate stems, but that
# happen to also be a genuine PREFIX of an unrelated common English word
# ("dram" -> "drama"/"dramatic"). A leading \b alone can't catch this (a
# prefix match looks identical to intentional stemming, e.g. "quantum
# comput" -> computing/computer), so these additionally get a trailing \b.
# NOTE: "fab" has the same shape (-> "fabulous"/"fabric") but is deliberately
# left prefix-only, since it also needs to catch "fabrication"/"fabless" --
# a real semiconductor term, so trail-bounding it would cost more than it
# fixes. Known residual risk, not blindly extended to every short anchor.
_FULL_WORD_ANCHORS = {"dram"}


def _leading_boundary(kw: str) -> re.Pattern:
    """Match `kw` only where it starts at a word boundary -- not embedded
    mid-word (the bug: bare anchor "ran" matched inside "brand"/"warranty"/
    "guarantee"/"franchise"). No TRAILING boundary requirement by default,
    since several anchors are deliberate stems meant to catch multiple forms
    of a word ("quantum comput" -> computing/computer/computation) -- see
    _FULL_WORD_ANCHORS for the (small) set that also need a trailing bound."""
    suffix = r"\b" if kw in _FULL_WORD_ANCHORS else ""
    return re.compile(r"\b" + re.escape(kw) + suffix)


def _hit_count(patterns: list[re.Pattern], text: str) -> int:
    return sum(1 for p in patterns if p.search(text))

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


_DOMAIN_ANCHOR_PATTERNS: dict[str, list[re.Pattern]] = {
    domain: [_leading_boundary(kw) for kw in meta["anchors"]]
    for domain, meta in taxonomy.DOMAINS.items()
}


def classify_domain(text: str, fallback_sector: str | None = None) -> tuple[str | None, bool]:
    """Returns (domain_key_or_None, confident).

    confident=False when the anchor match was weak (no hits at all, or the top
    hit count is tied across multiple domains) or came only from the sector
    fallback rather than the posting's own text -- these are exactly the cases
    worth an LLM second look rather than a silent guess."""
    t = (text or "").lower()
    hits_by_domain = {
        domain: hits
        for domain, patterns in _DOMAIN_ANCHOR_PATTERNS.items()
        if (hits := _hit_count(patterns, t))
    }
    if not hits_by_domain:
        if fallback_sector:
            return taxonomy.resolve_domain(fallback_sector), False
        return None, False
    best_hits = max(hits_by_domain.values())
    tied = sum(1 for h in hits_by_domain.values() if h == best_hits) > 1
    best = next(d for d, h in hits_by_domain.items() if h == best_hits)
    return best, not tied


_TIER_CUE_PATTERNS: dict[int, list[re.Pattern]] = {
    tier: [_leading_boundary(cue) for cue in cues] for tier, cues in _TIER_CUES.items()
}


def complexity_tier(title: str, text: str) -> tuple[int, bool]:
    blob = f" {title} {text} ".lower()
    for tier in (5, 4, 1, 3):  # extremes before the generic 'senior' bucket
        if _hit_count(_TIER_CUE_PATTERNS[tier], blob):
            return tier, True
    return 2, False  # default applied professional -- no cue matched, unconfident


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


_FUNCTION_TITLE_PATTERNS: dict[str, list[re.Pattern]] = {
    fn: [_leading_boundary(kw) for kw in meta["title"]] for fn, meta in FUNCTIONS.items()
}
_FUNCTION_TEXT_PATTERNS: dict[str, list[re.Pattern]] = {
    fn: [_leading_boundary(kw) for kw in meta["text"]] for fn, meta in FUNCTIONS.items()
}


def classify_function(title: str, text: str) -> tuple[str, bool]:
    t = (title or "").lower()
    tx = (text or "").lower()[:600]
    scores = {}
    for fn in _FUNC_ORDER:
        s = 3 * _hit_count(_FUNCTION_TITLE_PATTERNS[fn], t)
        s += _hit_count(_FUNCTION_TEXT_PATTERNS[fn], tx)
        if s:
            scores[fn] = s
    if not scores:
        return "engineering", False  # default: most ATS deep-tech roles are build roles
    # tie-break by _FUNC_ORDER priority
    best = max(scores.values())
    for fn in _FUNC_ORDER:
        if scores.get(fn) == best:
            return fn, True
    return "engineering", False


# ---------------------------------------------------------------------------
# LLM escalation -- local-first, fills only the fields regex wasn't confident
# about. Gemini is reserved for a residual audit sample (diagnostic only).
#
# A registry board can carry thousands of postings with ~50% needing
# escalation, so two guards keep any single run bounded: a persistent cache
# (classify once per posting, reused across runs) and a per-run cap on *new*
# escalations (llm_local.ESCALATION_CAP_PER_RUN).
# ---------------------------------------------------------------------------

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "classify_cache.db"

_cache_conn: sqlite3.Connection | None = None
_new_escalations_this_run = 0
_cache_hits_this_run = 0
_capped_this_run = 0


def _cache() -> sqlite3.Connection:
    global _cache_conn
    if _cache_conn is None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _cache_conn = sqlite3.connect(CACHE_PATH)
        _cache_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_classifications (
                key           TEXT PRIMARY KEY,
                domain        TEXT,
                tier          INTEGER,
                function      TEXT,
                classified_at TEXT NOT NULL
            )
            """
        )
        _cache_conn.commit()
    return _cache_conn


def _cache_key(title: str, text: str, location: str, sector: str | None) -> str:
    # Bounded by the same [:2000] window the LLM prompt itself uses, so the key
    # is insensitive to content past what the model ever saw.
    raw = f"{title}|{(text or '')[:2000]}|{location}|{sector or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> dict | None:
    row = _cache().execute(
        "SELECT domain, tier, function FROM llm_classifications WHERE key=?", (key,)
    ).fetchone()
    if row is None:
        return None
    return {"domain": row[0], "tier": row[1], "function": row[2]}


def _cache_put(key: str, result: dict) -> None:
    conn = _cache()
    conn.execute(
        "INSERT OR REPLACE INTO llm_classifications "
        "(key, domain, tier, function, classified_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (key, result.get("domain"), result.get("tier"), result.get("function")),
    )
    conn.commit()


def cache_stats() -> dict:
    """Run-level counters for the caller's end-of-run summary log."""
    return {
        "cache_hits": _cache_hits_this_run,
        "new_escalations": _new_escalations_this_run,
        "capped": _capped_this_run,
        "cache_size": _cache().execute("SELECT COUNT(*) FROM llm_classifications").fetchone()[0],
    }


_DOMAIN_CATALOG = "\n".join(f"{k}: {v['label']}" for k, v in taxonomy.DOMAINS.items())
_FUNCTION_CATALOG = ", ".join(f"{k} ({v['label']})" for k, v in FUNCTIONS.items())

_LLM_SYSTEM = (
    "You classify a job posting for a techno-science capability observatory.\n\n"
    f"TECH DOMAINS (choose exactly one key, or \"none\" if this role isn't in "
    f"any of these leading-edge domains):\n{_DOMAIN_CATALOG}\n\n"
    "COMPLEXITY TIER (integer 1-5): 1=intern/junior/entry-level, "
    "2=applied professional (no strong signal either way), "
    "3=senior/specialist/expert, 4=principal/staff/PhD research scientist/"
    "architect, 5=world-class/distinguished fellow/chief scientist/"
    "breakthrough-level.\n\n"
    f"BUSINESS FUNCTION (choose exactly one key): {_FUNCTION_CATALOG}\n\n"
    "Respond with STRICT JSON only, no prose, no markdown fences: "
    '{"domain": "<key or none>", "tier": <1-5 integer>, "function": "<key>"}.'
)

_GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "enum": list(taxonomy.DOMAINS.keys()) + ["none"]},
        "tier": {"type": "integer"},
        "function": {"type": "string", "enum": ALL_FUNCTIONS},
    },
    "required": ["domain", "tier", "function"],
}


def _llm_prompt(title: str, text: str) -> str:
    return f"Job title: {title!r}\nJob description: {(text or '')[:2000]!r}"


def _in_audit_sample(key: str) -> bool:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % AUDIT_SAMPLE_RATE == 0


def _classify_with_llm(title: str, text: str) -> dict | None:
    try:
        data = llm_local.structured(_llm_prompt(title, text), system=_LLM_SYSTEM)
    except llm_local.LocalLLMUnavailable as exc:
        print(f"[classify] local LLM unavailable: {exc}")
        return None
    except (ValueError, KeyError) as exc:
        print(f"[classify] local LLM parse failed: {exc!r} title={title!r}")
        return None
    dom = data.get("domain")
    dom = dom if dom in taxonomy.DOMAINS else None
    tier = data.get("tier")
    tier = tier if isinstance(tier, int) and 1 <= tier <= 5 else None
    fn = data.get("function")
    fn = fn if fn in FUNCTIONS else None
    return {"domain": dom, "tier": tier, "function": fn}


def _audit_with_gemini(title: str, text: str, final: dict) -> None:
    """Independent Gemini classification for a residual sample, purely to spot
    taxonomy/prompt drift. Never changes the returned classification."""
    if not gemini_client.ready():
        return
    try:
        data = gemini_client.structured(_llm_prompt(title, text), schema=_GEMINI_SCHEMA)
    except Exception as exc:  # noqa: BLE001 -- diagnostic only, never fail the run
        print(f"[classify] gemini audit failed: {exc!r} title={title!r}")
        return
    if (data.get("domain"), data.get("tier"), data.get("function")) != (
        final["domain"], final["tier"], final["function"]
    ):
        print(
            f"[classify] audit disagreement title={title!r} "
            f"final={final} gemini={data}"
        )


def classify_posting(title: str, text: str, location: str,
                     sector: str | None = None) -> dict:
    dom, dom_confident = classify_domain(f"{title} {text}", fallback_sector=sector)
    tier, tier_confident = complexity_tier(title, text)
    fn, fn_confident = classify_function(title, text)
    result = {
        "domain": dom,
        "tier": tier,
        "country": infer_country(location),
        "function": fn,
    }

    needs_llm = not (dom_confident and tier_confident and fn_confident)
    sample_key = f"{title}|{(text or '')[:200]}"
    audited = _in_audit_sample(sample_key)

    if needs_llm:
        global _new_escalations_this_run, _cache_hits_this_run, _capped_this_run
        key = _cache_key(title, text, location, sector)
        llm_result = _cache_get(key)
        if llm_result is not None:
            _cache_hits_this_run += 1
        elif _new_escalations_this_run < llm_local.ESCALATION_CAP_PER_RUN:
            llm_result = _classify_with_llm(title, text)
            _new_escalations_this_run += 1
            if llm_result:
                _cache_put(key, llm_result)
        else:
            # Cap hit this run: stays on the regex-only default below, same as
            # before this feature existed. A cache miss, so it's retried (and
            # likely resolved) on a future run once the cap resets.
            _capped_this_run += 1
            llm_result = None

        if llm_result:
            if not dom_confident and llm_result["domain"] is not None:
                result["domain"] = llm_result["domain"]
            if not tier_confident and llm_result["tier"] is not None:
                result["tier"] = llm_result["tier"]
            if not fn_confident and llm_result["function"] is not None:
                result["function"] = llm_result["function"]

    if audited:
        _audit_with_gemini(title, text, result)

    return result
