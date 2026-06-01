# ARCHITECTURE — Techno-Science Capability Observatory

> Plan document. No new runtime code yet (see ROADMAP for sequencing).
> Builds **on** the existing `my_technoscience_scraper.py`, it does not replace it.

## 1. What we are building and why

**Goal (confirmed):** a **global, country-by-country** view of leading-edge
industries showing, per country and per domain, **(a) the quantity of jobs** and
**(b) the skill/complexity level** — so countries can be **compared** directly.
On top of that comparison we layer the OEC complexity math and a stated-ambition
view.

The existing scraper answers *"who is hiring for frontier skills, where"* with
verifiable depth. The new layers turn hiring signal into a **capability
instrument** that reads, per country and per domain,

- **revealed capability** — quantity × skill-level of roles being staffed now, and
- **stated ambition** — what a country *says* it wants to build (national
  strategies, investment-agency targets), via Gemini grounded research,

…and surfaces the **gap between the two** as the foresight signal. OEC
(Observatory of Economic Complexity) methodology ranks countries and domains by
complexity and computes each country's *adjacent possible* — what it is
positioned to build next.

The nine leading-technology domains we track:
**semiconductors · quantum · precision engineering · advanced materials ·
biomedical/biological/biochemical · pharmaceuticals · digital · artificial
intelligence · other frontier (space, fusion, nuclear, energy, advanced mfg).**

## 2. Layered design

```
                         ┌──────────────────────────────────────────┐
  L0  COLLECTION         │ existing ATS scraper (free, no-key):       │
  (already exists)       │ Greenhouse · Lever · Ashby · custom pages  │
                         │ → Posting rows, weekly snapshots (CSV)     │
                         └───────────────────┬──────────────────────┘
                                             ▼
  L1  ENRICHMENT         ┌──────────────────────────────────────────┐
  (Gemini + rules)       │ map each Posting → (domain, complexity     │
                         │ tier 1–5, sub-skills). Regex first;        │
                         │ Gemini for the ambiguous + structured pull │
                         └───────────────────┬──────────────────────┘
                                             ▼
  L2  PANEL STORE        ┌──────────────────────────────────────────┐
                         │ append-only snapshots → SQLite/parquet.    │
                         │ diff on (country,parent,job_id) over time  │
                         │ → flow: openings/closings, skill drift     │
                         └───────────────────┬──────────────────────┘
                                             ▼
  L3  COMPLEXITY ENGINE  ┌──────────────────────────────────────────┐
  (OEC methodology)      │ country×domain matrix → RCA → ECI/PCI →     │
                         │ proximity → density (adjacent possible)     │
                         └───────────────────┬──────────────────────┘
                                             ▼
  L4  AMBITION LAYER     ┌──────────────────────────────────────────┐
  (Gemini research)      │ per country: national strategy targets,    │
                         │ R&D budgets, FDI announcements → stated     │
                         │ target complexity per domain                │
                         └───────────────────┬──────────────────────┘
                                             ▼
  L5  DASHBOARDS         ┌──────────────────────────────────────────┐
                         │ capability heatmap · complexity ranking ·  │
                         │ adjacent-possible · ambition-vs-revealed   │
                         │ gap · convergence & footprint over time    │
                         └──────────────────────────────────────────┘
```

Each layer reads the layer below through a stable contract, so any one can be
rebuilt without touching the others.

## 3. Layer detail

### L0 — Collection (two complementary global sources)

Global country-by-country comparison from free sources needs **two** sources,
because no single free source is both global and unbiased:

**L0a — ATS scraper (verifiable depth, biased coverage).** The existing
open-source-only path: Greenhouse / Lever / Ashby + undefended career pages
(+ a Workday adapter to add). Gives *ground-truth* postings with full skill
text — but coverage is skewed to the US/EU/Indian tech sector and is sparse
elsewhere, so it is **not** a fair basis for cross-country *quantity*
comparison on its own. Role: deep, auditable signal for covered countries; used
to **calibrate/spot-check** L0b.

**L0b — Gemini grounded research (global breadth, estimates).** Gemini
grounded-search / deep-research compiles a **country × domain** table of
*estimated job volume bands* and *typical skill level*, each with **cited**
sources (national labour stats, industry reports, FDI/fab/lab announcements).
This is what makes a genuinely global comparison possible now, with no keys and
no defended scraping. Role: the breadth layer; clearly labelled as estimated.

Both feed the same schema; every row records its **source + confidence** so the
dashboard never blends "scraped" and "estimated" silently.

**Precision ratchet (bands → absolute numbers).** Each country × domain cell
carries a `volume` *and* a `precision` level:
`band` (e.g. 100–500, Gemini estimate) → `partial_count` (real but
under-covered, e.g. ATS-only) → `counted` (verified/official). We start mostly
in `band`, and **upgrade cells over time** as sources are added (more ATS
employers, national labour-stat APIs, official releases). The dashboard always
shows the current precision per cell, so "absolute numbers eventually" is a
visible, monotonic trajectory rather than a one-time promise. Trend/diff logic
must respect precision changes (don't read a band→count upgrade as real growth).

- Country is a first-class field (ISO-2) on every row; `parent` (canonical
  employer) retained for footprint roll-up where L0a applies.
- **Known fix to fold in (L0a):** `write_csv(run())` does `asdict(rows[0])` and
  will `IndexError` on an empty run — guard for zero rows.

> Coverage decision is open (see §4): L0b-led, L0a-led, or hybrid.

### L1 — Enrichment (the "work with Gemini" core)
The existing `SKILL_PATTERNS` regex is fast and free but flat — it flags skills,
it does not place a posting in a domain or judge its depth. We add two outputs
per posting:

1. **primary_domain** (one of the 9) + any secondary domains.
2. **complexity_tier 1–5**: 1 technician/entry · 2 applied professional ·
   3 specialist senior IC · 4 expert (principal/staff, PhD R&D) · 5 frontier
   (world-first research, lead scientist). This tier is what makes the OEC
   weighting meaningful — ten technician reqs ≠ one frontier-research req.

**How Gemini is used (two modes, same prompt + JSON schema):**
- *Interactive / dev:* via the Gemini MCP in this session — good for designing
  and spot-checking the taxonomy and prompt.
- *Batch / automated:* `google-generativeai` with a Gemini key, classifying
  postings in batches with a structured-JSON response schema.
- *Always:* the regex classifier is the **fallback** — if Gemini is unavailable
  the panel still populates (degraded but never blocked). This honours the
  "AI-augmented, not AI-dependent" principle.

The domain taxonomy + tier definitions live in **one shared module** so the
regex path and the Gemini path emit the *same* schema and stay comparable.

### L2 — Panel store
- Promote from flat CSV to **SQLite** (one row per posting-snapshot), keeping CSV
  export. Idempotent upsert on a stable posting id.
- The longitudinal value is the **diff**: openings/closings, role tenure,
  skill-flag drift, and cross-border footprint shift over snapshots — exactly the
  flow signal the CLAUDE.md calls the point of the project.

### L3 — Complexity engine (OEC, adapted)
We treat (country × technology-domain) hiring like the OEC treats
(country × product) trade:
- **RCA** — is a country specialised in a domain relative to the whole panel?
- **M** — binary specialisation matrix (RCA ≥ 1).
- **ECI / PCI** — country and domain complexity via the Hidalgo–Hausmann method
  of reflections (eigenvector form) → a **Technology Complexity Index**.
- **proximity** — how often two domains are co-developed by the same countries
  (the deep-tech "product space").
- **density** — for domains a country has *not* yet specialised in, how close its
  current capabilities are → the **adjacent possible**, i.e. the natural next
  capability to build.

Hiring counts are **complexity-tier-weighted** (frontier roles count far more
than entry roles) before the matrix is built.

### L4 — Ambition layer (Gemini grounded research)
Jobs reveal *current* trajectory; they cannot show *intent*. The user's question
— "the complexity each country *wants* to achieve" — needs policy signal:
national semiconductor/quantum/AI strategies, R&D-spend targets, headline FDI and
fab/lab announcements. Gemini deep-research/grounded-search compiles a structured,
**cited** "stated target complexity per domain" per country. This is a separate,
clearly-labelled data source — never silently merged with the jobs panel.

### L5 — Dashboards
Streamlit + Plotly (lightweight, local). Core views:
1. **Capability heatmap** — country × domain, tier-weighted intensity.
2. **Technology Complexity Index** — country ranking + domain (PCI) ranking.
3. **Adjacent possible** — per country, nearest unbuilt domains.
4. **Ambition vs revealed** — stated target minus current capability = the gap.
5. **Convergence & footprint over time** — AI bleeding into hardware firms;
   same parent hiring design/test/R&D across different countries.

## 4. Cross-cutting decisions — all confirmed
- **Scope:** ✅ global, country-by-country comparison, all 9 domains.
- **Gemini access:** ✅ interactive (MCP) now, API key later.
- **Data sources:** ✅ free / no-key only.
- **Global data strategy:** ✅ **hybrid** — Gemini research for breadth + ATS for
  verifiable depth, labelled estimated vs scraped.
- **Storage:** ✅ SQLite (CSV export retained).
- **Precision goal:** ✅ absolute numbers are the target; start with bands and
  ratchet up per cell as sources improve (see L0 precision ratchet).

## 5. Honest methodological caveats (must stay visible in the UI)
- **Global coverage bias (the big one).** ATS adoption (Greenhouse/Lever/Ashby/
  Workday) is heavily US/EU/India-skewed and sparse in China, Japan, Korea, most
  of SEA, MENA, LatAm, Africa. Pure-ATS *quantity* comparisons across countries
  are apples-to-oranges. This is why L0b (Gemini research) carries the global
  comparison and L0a (ATS) provides depth/calibration — and why scraped vs
  estimated rows must stay visibly distinct.
- **Sampling bias.** Even within covered countries the ATS registry is *not* a
  representative census — it skews to MNCs and startups. Results are a
  **capability signal**, not an official statistic. Treat absolute ECI
  cautiously; trust *change over time* and *proximity/adjacent-possible* more.
- **Small-N instability.** ECI/PCI need a reasonably sized country×domain matrix;
  with few countries the eigenvector indices are noisy. Report confidence/N.
- **Gemini is a classifier, not an oracle.** Keep the regex fallback, log which
  classifier labelled each row, and spot-audit Gemini labels.
- **Ambition ≠ capability.** L4 is stated intent from documents; keep it visibly
  separate from L0–L3 revealed data.
