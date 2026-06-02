# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **techno-science capability observatory**: a global, country-by-country view of
nine leading-edge industries (semiconductors, quantum, precision engineering,
advanced materials, biomedical, pharmaceuticals, digital, artificial intelligence,
other frontier). It fuses **multiple independent signals** into one
`country × domain` panel, then layers economic-complexity analysis, an
ambition-vs-reality gap, cross-border MNC orchestration, and multi-year momentum.

The point is *triangulation*: where independent signals agree, confidence is high;
where they diverge, that gap is itself the finding (e.g. China out-publishes the US
in AI research but the US still out-patents it). See `ARCHITECTURE.md` for the
layered design and `ROADMAP.md` for build history (all 7 phases complete +
adjacencies: MNC footprint, publications, patents).

## The central data model

Everything writes into **one SQLite DB** (`data/jobs.db`, gitignored) via
`store.py`. The key idea: the **`cells` table holds the latest `country × domain`
value per *source***, with PK `(country_iso, domain, source)`. Sources are kept
strictly separate and never silently blended:

- `gemini_research` — capability estimates (volume band + skill tier + frontier), `precision='band'`
- `ats` — verified counts from real job postings, `precision='counted'`
- `publications` — OpenAlex research-output counts, `precision='counted'`
- `patents` — BigQuery patent counts, `precision='counted'`

Separate tables: `ambition` (stated national intent), `footprint` (employer ×
country × function), `cell_history` (weekly snapshots), `patent_trend` /
`publication_trend` (country × domain × year time-series). When adding a new signal,
follow this convention: new `source` value in `cells` for a latest-snapshot, or a
dedicated table for anything multi-dimensional (per-year, per-employer).

`taxonomy.py` is the shared spine — the 9 domains (with keyword anchors), 5
complexity tiers, and 0–5 volume bands. **Every layer imports from it** so outputs
stay comparable. `research.TARGET_COUNTRIES` is the shared 30-country set.

## Architecture: data flows one direction

```
collectors ──▶ store.py (jobs.db) ──▶ analysis/ ──▶ dashboard/app.py (live)
                                                └──▶ export_site.py ──▶ docs/ (static, Pages)
```

- **Collectors** (each free/no-cost or key-gated, each idempotent):
  `run_research.py` + `ambition.py` (Gemini), `ats/` (probe→scrape→footprint),
  `research_sources/publications.py` (OpenAlex), `research_sources/patents_bq.py`
  (BigQuery).
- **`analysis/`** is pure computation over the DB: `complexity.py` (OEC — RCA, PCI,
  basket complexity, proximity, adjacent-possible) and `gap.py` (ambition − revealed).
- **`dashboard/app.py`** is an 11-tab Streamlit reader; **`export_site.py`** renders
  the same data to a static `docs/index.html` for GitHub Pages.
- **`refresh.py`** orchestrates the weekly cron: re-run research + ambition + ATS +
  publications (+ patents if configured) → snapshot into `cell_history`.

## Commands

Run collectors/analysis with **system `python3`** (stdlib-only; works anywhere).
Run the dashboard/analysis-with-pandas from the **`.venv`** (has streamlit, plotly,
pandas, numpy, google-cloud-bigquery):

```bash
# data collection (idempotent — safe to re-run)
python3 run_research.py                 # Gemini capability, 9 domains (needs GEMINI_API_KEY)
python3 run_research.py quantum         # single domain
python3 ambition.py                     # Gemini national-ambition layer
python3 ats/probe.py                    # find live ATS boards -> data/ats_registry.json
python3 ats/scrape.py                   # ATS verified counts
python3 ats/footprint.py                # cross-border MNC division-of-labour
python3 research_sources/publications.py --years 2016 2018 2020 2022 --skip-existing
python3 research_sources/patents_bq.py --check                    # validate BigQuery auth
python3 research_sources/patents_bq.py --dry-run --year 2020      # GB it will scan (free=1TB/mo)
python3 research_sources/patents_bq.py --years 2016 2018 2020 2022

# text verification (no UI) — these are the "tests": run after data changes
python3 verify_panel.py                 # capability ranking + domain leaders (stdlib)
.venv/bin/python verify_complexity.py   # OEC metrics report (needs numpy/pandas)

# dashboard + static site
.venv/bin/streamlit run dashboard/app.py     # http://localhost:8501
.venv/bin/python export_site.py              # regenerate docs/index.html for Pages

# weekly refresh (what the cron runs)
python3 refresh.py --snapshot-only      # snapshot current cells, no API cost
python3 refresh.py --trends             # text trend summary
./weekly_refresh.sh                      # exactly what cron runs
```

There is **no formal test suite**. `verify_panel.py` and `verify_complexity.py` are
the verification harness — run them after touching collectors or analysis. The
standard dashboard smoke-test is: boot headless on a spare port and curl
`/_stcore/health` for HTTP 200.

## Hard rules (inherited from the original scraper — still inviolable)

The `ats/` layer collects only **open, public-by-design** sources: ATS JSON APIs
(Greenhouse, Lever, Ashby; Workday via `cxs` POST) and undefended career pages.
**Never** add an adapter for defended/ToS-encumbered aggregators (LinkedIn, Indeed,
JobStreet/SEEK, Glassdoor, Glints), never rotate proxies or solve CAPTCHAs, and
collect **postings only — never applicant data**. If a task seems to need any of
that, stop and flag it. `my_technoscience_scraper.py` is the original SEA-focused
scraper, kept as reference.

## Conventions that matter

- **Secrets live in `.env`** (gitignored), read via `gemini_client.load_env()`.
  Keys present: `GEMINI_API_KEY`, BigQuery `GOOGLE_APPLICATION_CREDENTIALS` +
  `BQ_PROJECT`, and (unused) EPO OPS creds. The BigQuery service-account JSON lives
  **outside the repo**. Before any commit, scan staged files for `.env`, `*.json`
  keys, `.venv/`, and `jobs.db` — none should ever stage.
- **Collectors must not silently zero on failure.** A network/API error should
  raise or be retried, not persist a 0 (which corrupts the panel). Long multi-year
  pulls support `--skip-existing` to resume; OpenAlex needs backoff + a socket
  timeout backstop (a `Connection reset` once hung a run for 16 min).
- **BigQuery cost discipline:** always `--dry-run` first. Queries use **CPC
  classification codes** (`DOMAIN_CPC`), not full-text LIKE — ~18 GB/domain vs
  ~228 GB, and more accurate. Each year ≈ 162 GB; budget the 1 TB/month free tier.
- **Estimates vs counts stay visually distinct** in the dashboard — `gemini_research`
  is labelled estimated; ATS/publications/patents are counted. Don't merge them.
- **Patent/publication recent years lag** (~2y to fully index) — pull ≤ 2 years back
  for complete data; the UI says "read the slope, not the final dot".

## Environment notes

System Python is 3.14 with PEP-668 (externally-managed) — use the **`.venv`** for
anything needing third-party packages; never `pip install` globally. The Gemini
**MCP server is unusable** (pinned to a retired model) — `gemini_client.py` calls
the REST API directly with `gemini-2.5-flash`. The weekly cron is macOS `crontab`
(Mondays 09:00) and only fires while the Mac is awake.
