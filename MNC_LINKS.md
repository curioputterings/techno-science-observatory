# Cross-border MNCs — validated career links

The multinationals in the **MNC footprint** layer (operating in ≥2 countries), from the live ATS boards. Every link below was HTTP-checked and returned 200.

_Links validated 2026-06-02; role/country counts from the latest `footprint` scrape. Career pages are the public human-facing boards; the pipeline reads the corresponding ATS JSON API._

| # | Company | Domain | Countries | Open roles | ATS | Career page |
|---|---------|--------|----------:|-----------:|-----|-------------|
| 1 | Mistral AI | AI | 14 | 160 | lever | <https://jobs.lever.co/mistral> |
| 2 | OpenAI | AI | 12 | 717 | ashby | <https://jobs.ashbyhq.com/openai> |
| 3 | Anthropic | AI | 11 | 366 | greenhouse | <https://job-boards.greenhouse.io/anthropic> |
| 4 | IonQ | Quantum | 10 | 115 | greenhouse | <https://job-boards.greenhouse.io/ionq> |
| 5 | Tenstorrent | Semiconductors | 7 | 111 | greenhouse | <https://job-boards.greenhouse.io/tenstorrent> |
| 6 | Scale AI | AI | 6 | 150 | greenhouse | <https://job-boards.greenhouse.io/scaleai> |
| 7 | Ramp | Digital | 3 | 115 | ashby | <https://jobs.ashbyhq.com/ramp> |
| 8 | PsiQuantum | Quantum | 3 | 78 | greenhouse | <https://job-boards.greenhouse.io/psiquantum> |
| 9 | Recursion | Pharmaceuticals | 3 | 28 | greenhouse | <https://job-boards.greenhouse.io/recursionpharmaceuticals> |
| 10 | Modal | Digital | 2 | 29 | ashby | <https://jobs.ashbyhq.com/modal> |
| 11 | Etched | Semiconductors | 2 | 19 | ashby | <https://jobs.ashbyhq.com/etched> |

## Notes & honest caveats

- **Coverage is curated, not a census.** These are the multi-country subset of 14 probed ATS boards — skewed to AI-native US/EU firms that use Greenhouse/Lever/Ashby. Large hardware MNCs (Intel, TSMC, Samsung) use Workday and are **not** included (no Workday adapter built).
- **"Countries" = distinct role locations** parsed from postings — i.e. where each firm hires, the division-of-labour signal (e.g. OpenAI: R&D+eng in US, commercial-only outposts in SG/JP/KR).
- Refresh links + counts any time with `python3 ats/probe.py` then `python3 ats/footprint.py`.
