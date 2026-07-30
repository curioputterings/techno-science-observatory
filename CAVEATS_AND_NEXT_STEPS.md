# Caveats & Next Steps

> Known limitations of the 30-domain observatory and what to do about them.
> Written 2026-06-19 as the starting backlog for the next session. Ordered by how
> much each should affect confidence in the results. See `REPORT.md` for the
> findings and `SESSION_2026-06-19.md` for how the current state was built.

## Tier 1 — affects the core of every finding

### 1. The primary signal is an LLM estimate, not a measurement
`gemini_research` capability + ambition (1,800 cells) are Gemini judgments at
band precision — model bias, cutoff staleness, real run-to-run variance (all 30
countries "moved" between two snapshots from re-estimation alone). Capability,
Fitness, basket complexity, and the win-win analysis all rest on this.
- [ ] **Finish the precision ratchet** (half-done Phase-0 goal): where a counted
      signal covers a cell, prefer it over the estimate on the main tabs.
- [ ] **Estimate-vs-counts divergence report**: flag/down-weight cells where the
      Gemini estimate disagrees with patents/publications/ATS.
- [ ] **Average 2–3 Gemini pulls** per cell to cut variance (or pin low temp).

### 2. Fitness rests on hand-tuned knobs over that estimate
Fitness (corr 0.86) is computed from a binarized RCA matrix whose volume floor
(`min_vol_ord=2`), RCA threshold, and tier weights (`TIER_WEIGHT`) are all
hand-chosen. Different knobs → different ranks.
- [ ] **Sensitivity sweep**: vary floor/threshold/weights, report rank stability
      (bootstrap). The "does the ranking survive perturbation" test.
- [ ] **Build the RCA matrix from the counted signals** (patents/publications)
      so Fitness rests on hard data, then publish it with a confidence band.

## Tier 2 — the counted signals have their own biases

### 3. Each counted signal measures something narrower than "capability"
- **Patents** — CPC maps hand-assigned; sibling sub-domains share CPC space and
  can double-count; counts track inventor location (favours large/old-IP
  economies); 2023 still lags indexing.
- **Publications** — search-string matching has false +/−; counts volume not
  quality/impact; English-biased.
- **ATS** — 14 boards, US-heavy, 124 cells; not globally representative.
- [ ] Patents: audit CPC overlaps, use **fractional counting** for multi-class
      patents; keep "latest" cells to ≤2-year-lag years.
- [ ] Publications: switch to **citation- or field-normalised** counts.
- [ ] ATS: **broaden the registry** (non-US employers) + add the **Workday adapter**.

### 4. Taxonomy/classification quality = the curated anchors
Anchors, CPC codes, and OpenAlex queries are hand-built; **sibling domains share
vocabulary** (ML vs computer-vision, 5G vs embedded), so misclassification leaks
across all four signals. Low PCI for AI/genomics is partly a **self-report
artifact** (many countries claim AI → reads "not rare"), understating difficulty.
- [ ] **Classification audit**: spot-check labelled samples per signal, tighten
      discriminating terms (free; no LLM needed).
- [ ] UI annotation: **PCI = rarity, not difficulty**.
- [ ] **Inter-signal consistency check**: flag domains ranking very differently
      across signals (a classification-problem smell test).

## Tier 3 — narrower / operational

### 5. Trends are shallow and noisy
Only 5 snapshots; single-week "movers" are mostly estimate noise; real 9→30 step.
- [ ] Accumulate more snapshots (time); show movers only **above a noise
      threshold**; anchor trend views to the stabler counted `*_trend` series.

### 6. The ambition gap is structurally one-sided
Negative gaps for leaders are an artifact (ambition 0–5 scaled to 100 can't
exceed 100 capability); only the **positive build-out side** is meaningful.
- [ ] Surface only positive gaps; keep ambition tied to cited policy sources.

### 7. Degenerate eigenvector ECI still in the codebase
Retained "for reference" but misleading; someone could resurface it.
- [ ] **Retire or quarantine** `complexity_indices` now that Fitness is trusted.

### 8. Reproducibility
Gemini outputs aren't reproducible run-to-run; keys/mailto are machine-local; the
BigQuery service account lives outside the repo.
- [ ] Record **model + prompt version** per cell (alongside the existing `as_of`);
      document env setup in the README.

## Also-known (already mitigated, watch for regressions)
- OpenAlex throttling / VPN-DNS fragility — mitigated via `OPENALEX_MAILTO` +
  `OPENALEX_PACING=3.0` + `OPENALEX_JITTER=1.5` + fail-fast on `URLError` +
  `--skip-existing` retry loops. Keep these if revisiting publications.
- macOS cron fires only while the Mac is awake.
- Weekly patent scan is guarded by skip-existing (≈0 GB unless a new year ticks
  over); don't remove that guard.

## If you only do three things next session
1. **Precision ratchet + divergence report** (caveat 1) — moves headline numbers
   from "LLM thinks" toward "measured, cross-checked."
2. **Fitness sensitivity sweep** (caveat 2) — is the country ranking robust or an
   artifact of three constants?
3. **Classification audit of CPC/anchors/queries** (caveat 4) — cheap foundational
   fix that improves all four signals at once.

All buildable in the current codebase; none need new paid APIs.
