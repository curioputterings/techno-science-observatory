# ROADMAP — Techno-Science Capability Observatory

> Sequenced plan. Each phase is independently shippable and leaves a working
> artifact. No code is written until you approve a phase.

## Phase 0 — Decisions (all confirmed ✅)
1. **Scope** — global, country-by-country comparison, **all 9 domains**.
2. **Gemini** — interactive (MCP) now, API key later.
3. **Data sources** — free / no-key only.
4. **Global data strategy** — **hybrid**: Gemini research (breadth) + ATS (depth),
   labelled estimated vs scraped.
5. **Storage** — SQLite (CSV export retained).
6. **Precision** — bands first, **ratchet to absolute numbers** per cell as
   sources improve. Absolute counts are the eventual target.

Phase 0 is complete — ready to start Phase 1 on your go.

## Phase 1 — Shared taxonomy + schema spine
The single source of truth both classifiers share.
- Define the **9 domains** with keyword anchors, and the **5 complexity tiers**
  with explicit definitions/examples.
- Map the existing `SKILL_PATTERNS` (ai_ml, rtl_design, photonics, advanced_pkg,
  synbio, quantum, nuclear, …) onto the 9 domains so nothing is lost.
- Add `country` (ISO-2) + `country_inferred` and `parent` (canonical employer)
  to the `Posting` schema, per CLAUDE.md.
- Define the country × domain **cell** schema: `volume`, `precision`
  (band/partial_count/counted), `skill_level`, `source`, `confidence`,
  `as_of` — the unit both L0a and L0b write into and the dashboard reads.

*Deliverable: `taxonomy` + cell schema modules. No network needed.*

## Phase 2 — Enrichment layer (Gemini + regex fallback)
- Classifier interface that returns `{primary_domain, domains[],
  complexity_tier, classifier}` for a posting.
- Regex implementation first (deterministic, free, the fallback).
- Gemini implementation second: batched, structured-JSON schema, same output
  shape; auto-falls back to regex on no-key/error.
- Spot-audit: sample N postings, compare regex vs Gemini, eyeball disagreements.

*Deliverable: enrichment module; a small labelled sample to validate quality.*

## Phase 3 — Panel store + collection hardening
- SQLite store with idempotent upsert; CSV export retained.
- Fold in the empty-run fix; add the **Workday adapter**; grow `EMPLOYERS` for
  the chosen scope (seed by eye from EDB/MIDA/BOI/MPI/BKPM/PEZA rosters).
- First real multi-employer snapshot collected and enriched end-to-end.

*Deliverable: populated `jobs.db` from a real run; one weekly snapshot on disk.*

## Phase 4 — Complexity engine (OEC)
- Build country×domain tier-weighted matrix → RCA → ECI/PCI → proximity →
  density.
- Validate the math on the real panel; sanity-check rankings against intuition
  (e.g. does semiconductors score as high-complexity, low-ubiquity?).
- Emit a small confidence/N report alongside indices.

*Deliverable: analysis module producing all metrics from `jobs.db`.*

## Phase 5 — Dashboards (revealed capability)
- Streamlit app: capability heatmap, complexity ranking, adjacent-possible,
  convergence & cross-border footprint over time.
- Methodological caveats shown in-UI (sampling bias, small-N).

*Deliverable: `streamlit run` dashboard over real data.*

## Phase 6 — Ambition layer + gap analysis
- Gemini grounded-research pulls each country's stated target complexity per
  domain from strategy/policy/FDI sources, with citations, into a separate table.
- Dashboard view: **stated ambition vs revealed capability** gap per
  country×domain — the headline foresight signal.

*Deliverable: ambition table + gap dashboard; sources cited and auditable.*

## Phase 7 — Automation & longitudinal depth
- Weekly scheduled run (cron/`/schedule`) → new snapshot → re-enrich → refresh
  metrics → dashboard auto-updates.
- Trend views: capability momentum, convergence acceleration, footprint shifts.

*Deliverable: hands-off weekly panel growth; trend charts that need ≥4 snapshots
to become meaningful.*

## Suggested first build after approval
Given the **global comparison** goal, the fastest path to something real and
worldwide is **Phase 1 (taxonomy) + a Phase-2 Gemini-research pass (L0b)** that
produces a cited country × domain table of job-volume bands + skill level, then a
Phase-5 comparison dashboard over it. The ATS depth layer (L0a) and the OEC
engine follow once the global table exists and can be calibrated. (If you prefer
verifiable-first, we instead start with L0a on a handful of high-coverage
countries — deeper but not yet global.)

---
### Status
- [x] Phase 0 — all decisions confirmed.
- [x] Phase 1 — taxonomy + cell schema + SQLite store (`taxonomy.py`, `store.py`).
- [x] Phase 2 — Gemini enrichment via REST API (`gemini_client.py`, `research.py`,
      `run_research.py`). **Verified: 270 cells (9×30) in `data/jobs.db`, 0 dups.**
- [x] Phase 4 — OEC complexity engine (`analysis/complexity.py`): RCA (with a
      volume floor to kill the empty-country pathology), PCI, basket complexity,
      proximity, density/adjacent-possible. `verify_complexity.py` prints it.
      Note: classic eigenvector ECI is unreliable at 9 domains (small-N + washes
      out all-round leaders) — we surface **basket complexity** + **PCI** instead.
- [x] Phase 5 — dashboard (`dashboard/app.py`), now 8 tabs; boots clean (HTTP 200).
- [x] Phase 6 — ambition layer + gap analysis. `ambition.py` (Gemini policy
      research → `ambition` table, 270 cells), `analysis/gap.py` (ambition −
      revealed), dashboard tab 7 (gap heatmap / biggest build-outs / country
      detail). Boots clean. Build-out signal is face-valid (SA/AE/IN/VN/PL
      building semis/quantum/AI). Note: negative gaps for leaders (US/TW) are
      partly structural — the *positive* build-out side is the meaningful signal.
- [x] Phase 7 — longitudinal snapshots + weekly cron. `cell_history` table +
      `store.snapshot()` (idempotent per date, delete-then-insert), `refresh.py`
      (research + ambition + snapshot; `--snapshot-only`, `--trends`),
      `weekly_refresh.sh`, **crontab installed (Mondays 09:00)**, dashboard tab 8
      "Trends" (per-country lines + biggest movers). First snapshot seeded
      (1 date; trends need ≥2 weeks).
- [x] Phase 3 — ATS depth layer (L0a). `ats/probe.py` (verifies which candidate
      boards are live → `data/ats_registry.json`), `ats/classify.py` (posting →
      domain + complexity tier + country), `ats/scrape.py` (fetch → classify →
      aggregate → store cells, source='ats', precision=counted/partial_count).
      Verified live: 14 boards, 3,722 real postings, 2,602 classified → **42
      verified cells, 16 countries, all 9 domains**. Kept SEPARATE from
      gemini_research (dashboard tab 9 "Verified (ATS)"; `load()` filters to
      gemini so estimates and counts never blend). US-heavy by design (depth, not
      breadth). Cost: ~$0 (free public ATS JSON, no key). Workday adapter not
      added (no live tenant in the curated set) — optional follow-up.

**✅ ALL 7 PLANNED PHASES COMPLETE.** Optional follow-ups: Workday adapter,
broaden the ATS registry, fold ATS counts into the precision ratchet on the main
estimate tabs.
