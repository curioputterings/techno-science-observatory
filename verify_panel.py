"""Stdlib-only verification of the capability panel (no pandas needed)."""
import sqlite3
from collections import Counter, defaultdict

import taxonomy
from store import DB_PATH

c = sqlite3.connect(DB_PATH)
c.row_factory = sqlite3.Row
# capability formula only applies to the Gemini estimate layer; counted sources
# (ats/patents/publications) carry NULL band fields, so filter to gemini_research.
rows = [dict(r) for r in c.execute("SELECT * FROM cells WHERE source='gemini_research'")]
c.close()

out = []
out.append(f"TOTAL cells: {len(rows)} | domains: {len(set(r['domain'] for r in rows))} "
           f"| countries: {len(set(r['country_iso'] for r in rows))}")
seen = Counter((r["domain"], r["country_iso"]) for r in rows)
out.append(f"duplicate (domain,country) groups: {sum(1 for v in seen.values() if v > 1)}")
out.append(f"per-domain: {dict(Counter(r['domain'] for r in rows))}")
out.append(f"confidence: {dict(Counter(r['confidence'] for r in rows))}")


def cap(r):
    return (0.4 * (r["volume_ord"] / 5)
            + 0.4 * (max(0, r["skill_level"] - 1) / 4)
            + 0.2 * min(1, max(0, r["frontier"] or 0))) * 100


byc = defaultdict(list)
for r in rows:
    byc[r["country_name"]].append(cap(r))
out.append("\n=== Overall capability (mean across 9 domains) ===")
for sc, n in sorted(((sum(v) / len(v), k) for k, v in byc.items()), reverse=True):
    out.append(f"{sc:5.1f}  {n}")

out.append("\n=== Domain leaders (top 5 by capability) ===")
for d in taxonomy.ALL_DOMAINS:
    s = sorted((r for r in rows if r["domain"] == d), key=cap, reverse=True)
    leaders = "  ".join(f"{r['country_iso']}({cap(r):.0f})" for r in s[:5])
    out.append(f"{taxonomy.DOMAIN_LABELS[d]:24} {leaders}")

text = "\n".join(out)
print(text)
open("data/research/_panel_report.txt", "w").write(text + "\n")
