# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

A longitudinal scraper for **advanced-technoscience job postings across Southeast
Asia** — semiconductors & ATE, IC design, assembly/test (ATM), photonics,
advanced packaging, HDD/storage, EV-battery & critical-minerals materials,
biotech, quantum, aerospace (thin nuclear tails). It is a **foresight /
computational-sociology instrument**, not a job-search tool: the point is to
track *hiring flow* over time as a leading indicator of capability formation, and
to do so **comparably across countries**.

The regional scope *is* the analytical payoff. Two signals matter most:

1. **Convergence** — AI/ML skill tags bleeding into firms that were previously
   pure-hardware: a datable measure of the frontier industrialising.
2. **Cross-border functional division of labour** — the same multinational
   hiring *design* in one country, *assembly/test* in another, *R&D* in a third.
   Tracking that footprint maps where each economy sits in the regional value
   chain, and how that position is shifting. This is the comparison the single-
   country version could not see.

Optimise for clean, country-comparable longitudinal panels, not one-off pulls.

## Hard rules (do not violate, even if asked)

These are the project's reason-for-being. Treat them as inviolable.

1. **Scrape only open sources.** Two tiers, both public-by-design:
   - ATS JSON APIs — Greenhouse, Lever, Ashby (GET); Workday (POST to `cxs`).
   - Server-rendered custom career pages with no auth/bot-defense.
2. **Never scrape defended aggregators.** Regional: JobStreet/SEEK, LinkedIn,
   Indeed, Glassdoor, Glints. Country-level: VietnamWorks / ITviec / TopCV (VN),
   JobsDB (TH), Kalibrr (PH/ID), and the JobStreet/Jobsdb country sites. All are
   ToS-encumbered and bot-defended — use them **by eye only** to populate the
   registry. Do **not** add an adapter, write a circumvention, rotate proxies, or
   solve CAPTCHAs. If a task seems to require any of that, stop and flag it.
3. **Postings only — never applicant data.** Job descriptions are not personal
   data and are fine to collect. Candidate-side data is personal under every
   jurisdiction here (SG PDPA, MY PDPA, TH PDPA, VN PDPD, PH Data Privacy Act,
   ID PDP Law) — never touch application forms, resumes, or submitted data.
4. **Be a polite client.** Respect `robots.txt`, keep the `User-Agent` honest,
   keep `POLITE_DELAY_S >= 2`, don't parallel-hammer a host, cache where possible.

If a request conflicts with these, surface the conflict; don't quietly comply.

## Layout

```
scraper.py            # adapters, schema, registry, runner (start here)
locales/              # per-country city/region vocab for custom-page parsing
data/                 # weekly CSV/parquet snapshots, partitioned by country (gitignored)
CLAUDE.md             # this file
```

## Setup & commands

Python env via **uv**:

```bash
uv venv
uv pip install requests beautifulsoup4
uv run python scraper.py            # writes a dated snapshot under data/
```

No test suite yet. When adding parsers, add a fixture test against saved HTML
rather than hitting the network in CI.

## Architecture

- **Adapters are keyed by source type, never by country.** One function per
  source type, registered in `ADAPTERS` (`fetch_greenhouse`/`_lever`/`_ashby`/
  `_workday` + custom page parsers). Country is data, not code.
- **Common schema.** Everything normalises to the `Posting` dataclass, which
  **must** carry `country` (ISO-3166 alpha-2) and a `country_inferred` flag, plus
  `parent` (canonical employer name) so cross-border footprints aggregate.
- **Prefer ATS structured location over text parsing.** It is locale-proof and
  scales across the region; fall back to `locales/` vocab only for custom pages.
- **Employer registry.** `EMPLOYERS` is the hand-curated universe, grouped by
  country. Each entry: `country`, `name`, `parent`, `sector`, `kind` (adapter),
  `ref` (ATS token/handle or career URL). This list is the manual heart.
- **Skill tagging.** `SKILL_PATTERNS` drives convergence detection and must
  tolerate non-English text (see gotchas). Extend the taxonomy, don't inline
  matches in adapters.
- **Longitudinal panel.** Each row carries a UTC `snapshot_date`. Derive flow by
  diffing `(country, employer, job_id)` across snapshots → openings/closings,
  tenure on board, skill-flag drift, and cross-border footprint shifts.

## Country nodes & seed sources

Populate the registry by eye from each country's investment agency and recruitment
events. Employer names below are **examples to confirm**, not a maintained roster.

| ISO | Seed sources | Frontier shape (examples) |
|----|---|---|
| SG | EDB, A*STAR | Regional R&D/HQ hub; fabs (GlobalFoundries, Micron, UMC), deep-tech startups on global ATS, quantum/biomed |
| MY | MIDA, InvestPenang | Penang/Kulim ATE & design houses (ViTrox, Greatech, Pentamaster), MNC fabs |
| TH | BOI | HDD/storage (WD, Seagate), automotive/EV electronics, some semi |
| VN | MPI | Rising ATM (Intel, Amkor, Hana, Samsung) + emerging IC design |
| ID | BKPM | EV-battery & nickel/critical-minerals processing, digital/platform |
| PH | BOI / PEZA | Large semiconductor ATM, electronics |

## Adding an employer (the common task)

1. Confirm **country** and **surface** by eye: ATS (look for `greenhouse.io`,
   `lever.co`, `ashbyhq.com`, `myworkdayjobs.com`) or custom page?
2. ATS → add a registry row with country, token/handle, parent; existing adapter
   handles it.
3. Custom page → write an adapter following the existing pattern: stable id,
   title, structured location if present, then `tag_skills(full_text)`. Put any
   city vocab in `locales/<iso>.py`, not inline.
4. Set `parent` to the canonical multinational name so footprint rolls up.

## Domain context / gotchas

- **Multilingual postings** (Bahasa Malaysia/Indonesia, Thai, Vietnamese, Tagalog).
  An English-only regex under-counts — but most *technical* terms stay English
  even inside local-language posts ("RTL", "CRISPR", "machine learning" rarely
  translate), so English anchors still work; add per-language synonym sets where
  needed and a `langdetect` pass to tag `lang`.
- **Workday is the regional MNC-fab backbone**, not an optional tier. Its `cxs`
  endpoint needs a POST with a JSON facet body (`appliedFacets`, `limit`,
  `offset`); paginate on `offset`. Build/maintain the WorkdayAdapter accordingly.
- **Same parent, many tenants.** A multinational may post under different ATS
  tenants per country. The `parent` field is what makes cross-border aggregation
  correct — keep it canonical and consistent.
- **Locale, not just language.** Don't hardcode per-country city regex; lean on
  ATS structured location and `locales/` lookups.
- **Time & money.** Stamp `snapshot_date` in UTC for clean cross-country diffs.
  If salary is captured, store amount + ISO currency; never normalise silently.
- Listings often include regional/remote roles outside the posting country — keep
  them but set `country_inferred` so analyses can filter to in-country hiring.

## Style

Plain stdlib + `requests`/`bs4`; no heavy frameworks. Dataclasses over dicts.
Adapters small and pure (`fetch -> list[Posting]`); side effects (I/O, sleeping,
partitioning) live in the runner.
