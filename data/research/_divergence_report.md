# Estimate-vs-counts divergence report
_generated 2026-07-03 · read-only over `data/jobs.db`_

Compares the Gemini revealed-capability **estimate** against the **counted** signals (publications, patents, ATS) on the one dimension they share — the 0-5 `volume_ord` activity band. `measured band` = mean of the publications & patents bands; `measured div` = measured − estimate (**+** = counts run hotter than the model said → likely **over-cautious** estimate; **−** = counts run colder → likely **over-rated** estimate).

## Coverage & vintages
| source | cells vs estimate | as_of |
| --- | --- | --- |
| gemini_research (estimate) | 900 | 2026-07-01 |
| publications | 900 | 2026-06-17 |
| patents | 900 | 2026-06-16 |
| ats | 131 | 2026-06-18, 2026-07-01 |

**96** cells are flagged: the estimate exceeds *every* counted signal (`over_gap`≥2) — 8 cells with any positive over_gap — or *both* dense counts exceed it (`under_gap`≥2) — 462 with any positive under_gap.

## Most over-rated cells (estimate exceeds *every* count)
_`over_gap` = estimate band − max(publications, patents). The model claims activity no counted signal supports — the least-trustworthy high scores. (Semiconductor cells are correctly absent: patents back them even when publications don't.)_

| Country | Domain | est | pub | pat | over_gap |
| --- | --- | --- | --- | --- | --- |
| South Korea | Memory & Storage Devices | 5 | 3 | 4 | **+1** |
| Singapore | Memory & Storage Devices | 3 | 2 | 2 | **+1** |
| Thailand | Memory & Storage Devices | 2 | 1 | 1 | **+1** |
| Taiwan | Advanced Packaging | 5 | 2 | 4 | **+1** |
| Malaysia | Advanced Packaging | 3 | 1 | 2 | **+1** |
| Taiwan | Fab Equipment & Lithography | 5 | 2 | 4 | **+1** |
| Singapore | Fab Equipment & Lithography | 3 | 2 | 2 | **+1** |
| Ireland | Fab Equipment & Lithography | 2 | 1 | 1 | **+1** |

## Most under-rated cells (both counts exceed the estimate)
_`under_gap` = min(publications, patents) − estimate band. Both measured channels outrun the model's band — candidates the estimate is sleeping on._

| Country | Domain | est | pub | pat | under_gap |
| --- | --- | --- | --- | --- | --- |
| Switzerland | Composites & Polymers | 1 | 4 | 4 | **+3** |
| Finland | Composites & Polymers | 1 | 4 | 4 | **+3** |
| Belgium | Composites & Polymers | 1 | 4 | 4 | **+3** |
| Austria | Composites & Polymers | 1 | 4 | 4 | **+3** |
| Israel | Small-Molecule Drug Discovery | 1 | 4 | 4 | **+3** |
| Sweden | Small-Molecule Drug Discovery | 1 | 4 | 4 | **+3** |
| Australia | Small-Molecule Drug Discovery | 1 | 5 | 4 | **+3** |
| Ireland | Small-Molecule Drug Discovery | 0 | 4 | 3 | **+3** |
| Belgium | Small-Molecule Drug Discovery | 1 | 4 | 4 | **+3** |
| Spain | Small-Molecule Drug Discovery | 1 | 5 | 4 | **+3** |
| Netherlands | Computer Vision | 1 | 4 | 4 | **+3** |
| Switzerland | Computer Vision | 1 | 4 | 4 | **+3** |

## Systematic bias by country
_Mean signed (measured − estimate) across domains. Negative = the model is systematically more generous than the counts for that country._

| Country | mean div | n domains |
| --- | --- | --- |
| China | +0.1 | 30 |
| United States | +0.1 | 30 |
| Germany | +0.6 | 30 |
| South Korea | +0.7 | 30 |
| United Kingdom | +0.8 | 30 |
| Japan | +0.8 | 30 |
| Taiwan | +0.9 | 30 |
| Netherlands | +1.0 | 30 |
| Singapore | +1.0 | 30 |
| France | +1.0 | 30 |
| … | | |
| Malaysia | +1.5 | 30 |
| Italy | +1.5 | 30 |
| Vietnam | +1.5 | 30 |
| Brazil | +1.5 | 30 |
| Finland | +1.6 | 30 |
| Austria | +1.7 | 30 |
| Australia | +1.7 | 30 |
| Spain | +1.8 | 30 |
| Saudi Arabia | +1.8 | 30 |
| Indonesia | +2.0 | 30 |

## Systematic bias by domain
| Domain | mean div | n countries |
| --- | --- | --- |
| Advanced Packaging | +0.2 | 30 |
| Cloud & Distributed Systems | +0.6 | 30 |
| Networks & 5G/6G | +0.6 | 30 |
| Memory & Storage Devices | +0.7 | 30 |
| Fab Equipment & Lithography | +0.7 | 30 |
| Space & Aerospace | +0.7 | 30 |
| Chip & IC Design | +0.8 | 30 |
| Quantum Comms & Sensing | +1.0 | 30 |
| … | | |
| Cell & Gene Therapy | +1.5 | 30 |
| Biologics & Vaccines | +1.6 | 30 |
| Computer Vision | +1.7 | 30 |
| Genomics & Genetic Engineering | +1.7 | 30 |
| Machine & Deep Learning | +1.8 | 30 |
| Photonics & Optics | +1.9 | 30 |
| Composites & Polymers | +2.1 | 30 |
| Small-Molecule Drug Discovery | +2.5 | 30 |

## The gap is the finding — research vs commercialisation
_publications band minus patents band, per cell. **Research-leaning** = strong publication output relative to patents (knowledge, not yet captured); **patent-leaning** = the reverse._

**Research-leaning (publications ≫ patents):**

| Country | Domain | pub | pat | Δ |
| --- | --- | --- | --- | --- |
| Indonesia | Biologics & Vaccines | 5 | 0 | +5 |
| Indonesia | Space & Aerospace | 5 | 0 | +5 |
| Indonesia | Fusion & Advanced Nuclear | 5 | 0 | +5 |
| Indonesia | Robotics & Motion Control | 5 | 1 | +4 |
| Indonesia | Additive Manufacturing | 4 | 0 | +4 |
| Indonesia | Composites & Polymers | 5 | 1 | +4 |
| United Arab Emirates | Genomics & Genetic Engineering | 4 | 0 | +4 |
| Poland | Genomics & Genetic Engineering | 5 | 1 | +4 |
| Indonesia | Small-Molecule Drug Discovery | 5 | 1 | +4 |
| Malaysia | Biologics & Vaccines | 5 | 1 | +4 |

**Patent-leaning (patents ≫ publications):**

| Country | Domain | pub | pat | Δ |
| --- | --- | --- | --- | --- |
| Taiwan | Chip & IC Design | 2 | 5 | -3 |
| South Korea | Chip & IC Design | 3 | 5 | -2 |
| Japan | Advanced Packaging | 2 | 4 | -2 |
| South Korea | Advanced Packaging | 2 | 4 | -2 |
| Taiwan | Advanced Packaging | 2 | 4 | -2 |
| Japan | Fab Equipment & Lithography | 3 | 5 | -2 |
| Taiwan | Fab Equipment & Lithography | 2 | 4 | -2 |
| Netherlands | Fab Equipment & Lithography | 2 | 4 | -2 |
| Israel | Cloud & Distributed Systems | 2 | 4 | -2 |
| Israel | Embedded & IoT | 2 | 4 | -2 |

---
_Method note: this compares activity **bands**, the only signal common to all sources. It measures where the estimate and the counts disagree — not which is 'right'. A cell can diverge because the estimate is stale/biased, because publication/patent counts lag or are language-biased, or because the domains genuinely differ in how capability shows up. Treat large divergences as **cells to review**, per CAVEATS Tier-1 #1._
