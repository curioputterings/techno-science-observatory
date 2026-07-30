# Techno-Science Capability Observatory — Results Report

*Generated 2026-06-19. Panel: 30 domains × 30 countries, four independent signals.*

## What this measures

A global `country × domain` view of frontier technology capability across **30
leading-edge domains** (expanded from the original 9), fusing four independent
signals so that where they agree, confidence is high — and where they diverge,
the gap is itself the finding.

| Signal | Source | Precision | Cells |
|---|---|---|---|
| Capability (volume × skill × frontier) | Gemini grounded research | estimate (band) | 900 |
| National ambition | Gemini policy research | estimate | 900 |
| Patents | BigQuery `patents-public-data` (CPC codes) | counted | 900 |
| Publications | OpenAlex (authorship country) | counted | 900 |
| Verified hiring | Live ATS boards (regex classifier) | counted | 124 |

Trend series: patents `[2016, 2018, 2020, 2022, 2023]`, publications
`[2016, 2018, 2020, 2022, 2025]`. Longitudinal snapshots: 5 dates
(`2026-06-01 … 2026-06-18`).

---

## 1. Overall capability ranking

Mean capability across the 30 domains (Gemini estimate, 0–100):

| # | Country | Capability |
|---|---|---|
| 1 | United States | 96.8 |
| 2 | China | 83.1 |
| 3 | Germany | 73.5 |
| 4 | Japan | 69.6 |
| 5 | South Korea | 68.8 |
| 6 | United Kingdom | 68.0 |
| 7 | France | 61.5 |
| 8 | Netherlands | 55.5 |
| 9 | Switzerland | 55.3 |
| 10 | Canada | 54.1 |

Raw capability is dominated by the US and China. The structural measures below
tell a more textured story.

---

## 2. Country complexity — Fitness (the headline structural index)

We rank countries by the **Tacchella non-linear Fitness–Complexity** index, not
the classic eigenvector ECI (which is degenerate on this panel — see Methodology).
Fitness rewards *diversified depth*: doing many hard things that few others can.
(`≈1.0 = average`.)

| # | Country | Fitness |
|---|---|---|
| 1 | United States | 2.96 |
| 2 | Japan | 2.67 |
| 3 | South Korea | 2.20 |
| 4 | China | 2.10 |
| 5 | Germany | 2.09 |
| 6 | Italy | 1.88 |
| 7 | Netherlands | 1.85 |
| 8 | Switzerland | 1.53 |
| 9 | Canada | 1.38 |
| 10 | Israel | 1.31 |
| 11 | France | 1.16 |
| 12 | United Kingdom | 1.11 |

**Validity:** `corr(Fitness, diversity) = 0.86` (the broken eigenvector ECI was
0.22). The ranking is face-valid — diversified advanced economies on top.

---

## 3. Domain complexity — PCI (the sophistication ladder)

How rare and hard each domain is (PCI, z-scored). The 30-domain split resolved
the old single "Semiconductors" bucket into a genuine ladder:

**Hardest / rarest (top):**

| PCI | Domain |
|---|---|
| +2.82 | Advanced Packaging |
| +2.20 | Memory & Storage Devices |
| +1.58 | Nanomaterials |
| +1.38 | Fab Equipment & Lithography |
| +1.22 | Chip & IC Design |
| +0.69 | Embedded & IoT |
| +0.65 | Robotics & Motion Control |

**Most ubiquitous / widely attempted (bottom):**

| PCI | Domain |
|---|---|
| −0.95 | Machine & Deep Learning |
| −0.99 | Carbon Capture & Climate Tech |
| −1.00 | Cloud & Distributed Systems |
| −1.03 | Hydrogen & Fuel Cells |
| −1.19 | Genomics & Genetic Engineering |

> **Read with care:** low PCI ≠ "easy." AI/ML and genomics score low here because
> *many countries claim them* (high ubiquity), not because they are simple. PCI
> measures rarity of capability, not intrinsic difficulty.

---

## 4. Basket complexity — concentration (a complementary lens)

While Fitness rewards breadth, **basket complexity** rewards *concentration* in
the rarest domains. The two are nearly orthogonal (`corr = 0.07`), so they answer
different questions.

| Basket | Country | Story |
|---|---|---|
| +1.09 | Taiwan | concentrated in semiconductor packaging/fab |
| +1.06 | Malaysia | semiconductor back-end specialisation |
| +0.49 | South Korea | memory + semis |
| +0.48 | Vietnam | narrow electronics/assembly base |
| +0.38 | Belgium | — |

The US sits near zero on basket complexity (−0.06) precisely *because* it is
diversified — its capability is spread across many domains rather than
concentrated in the rarest few. **Fitness and basket complexity together** are
the richer picture: who is broad-and-deep (US, Japan, Germany) vs who is
narrow-but-specialised in hard things (Taiwan, Malaysia).

---

## 5. Diversity (breadth of specialisation)

Number of domains a country is revealed-specialised in (RCA ≥ 1, volume floor
applied):

| Domains | Country |
|---|---|
| 18 | United States |
| 14 | India |
| 13 | Japan, Canada |
| 12 | Italy, South Korea, UK, Germany, China, Singapore |

---

## 6. Triangulation — research vs invention divergence

The headline foresight signal: where independent signals *disagree*. Comparing
**publications** (research output, 2022) against **patents** (invention, 2023):

| Domain | Publications leader | Patents leader |
|---|---|---|
| Machine & Deep Learning | 🇨🇳 China | 🇺🇸 US |
| Generative AI & NLP | 🇨🇳 China | 🇺🇸 US |
| Computer Vision | 🇨🇳 China | 🇺🇸 US |
| Advanced Packaging | 🇨🇳 China | 🇹🇼 Taiwan |
| Chip & IC Design | 🇺🇸 US | 🇺🇸 US |
| Quantum Computing | 🇺🇸 US | 🇺🇸 US |
| Genomics | 🇺🇸 US | 🇺🇸 US |
| Space & Aerospace | 🇨🇳 China | 🇺🇸 US |

**Finding:** across AI (ML, NLP, vision) China leads *research output* while the
US leads *patented invention* — a persistent research-to-invention gap. In
semiconductors the split is three-way: China publishes most on advanced
packaging, but Taiwan patents it and the US leads chip design end-to-end.

---

## 7. The adjacent possible — feasible high-value moves

For each country, the unbuilt domains *closest* to its existing capabilities
(density = feasibility of growing employment there):

| Density | Country | Could build next |
|---|---|---|
| 0.75 | United States | Nanomaterials |
| 0.67 | United States | Space & Aerospace |
| 0.65 | United States | Fab Equipment & Lithography |
| 0.65 | Canada | Cloud & Distributed Systems |
| 0.63 | United States | Chip & IC Design |
| 0.62 | United Kingdom | Pharma Manufacturing & Formulation |
| 0.60 | Japan | Additive Manufacturing |

### Job growth *and* sophistication — the strategy framing

A country wanting **both** employment growth and rising sophistication faces a
menu sorted by where it starts:

1. **Deepen** existing strengths (climb the skill tier) — lowest risk.
2. **Diversify into the adjacent possible** — the win-win: domains both *feasible*
   (high density) and *more complex* (higher PCI) than the current mix. For
   capability-rich economies this often converges on semiconductors.
3. **The orchestrated leap** — for sparse economies, the high-PCI prizes are far;
   they must ladder through adjacent stepping-stones or import capability via
   anchored FDI. Highest risk, longest horizon.

The **anti-pattern** is chasing job growth in low-PCI, high-ubiquity domains —
headcount grows while the basket gets *less* sophisticated (the middle-income
trap). Option quality is stratified by existing diversity ("those who have,
gain"): capability-rich countries can get both at once; sparse aspirants cannot
and must sequence.

---

## Methodology & honest caveats

- **Estimates vs counts stay separate.** `gemini_research` is an LLM estimate
  (band precision); patents/publications/ATS are real counts. They are never
  silently blended.
- **Fitness, not eigenvector ECI.** The classic method-of-reflections ECI is
  degenerate on this 30×30 panel (`corr` with diversity 0.22, inverted ranks).
  We swapped to the non-linear Fitness–Complexity algorithm (`corr 0.86`).
  Eigenvector ECI is retained for reference only.
- **Recent years lag.** Patent/publication indexing lags ~2–3 years; read the
  slope of trend lines, not the final point.
- **ATS is US-heavy by design** (depth, not breadth) — 124 verified cells over
  23/30 domains from 14 public boards; the uncovered domains are simply where
  those employers don't hire.
- **Longitudinal trends roll up to the 9 parent groups** so snapshots before and
  after the 30-domain expansion stay comparable; a marked step at the expansion
  boundary reflects genuine finer-grain re-estimation, not an artifact.
