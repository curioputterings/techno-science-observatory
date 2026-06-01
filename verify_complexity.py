"""Print the OEC complexity report (run under the venv)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taxonomy
from analysis import complexity

rep = complexity.full_report()
names = rep["names"]
L = taxonomy.DOMAIN_LABELS
out = []

out.append(f"panel rows: {len(rep['panel'])} | intensity matrix: {rep['intensity'].shape}")

out.append("\n=== Technology Complexity Index (ECI, top 12) ===")
for iso, v in rep["eci"].head(12).items():
    out.append(f"{v:+5.2f}  {iso}  {names.get(iso, '')}")

out.append("\n=== Domain Complexity (PCI) — high = complex & rare ===")
for dom, v in rep["pci"].items():
    out.append(f"{v:+5.2f}  {L.get(dom, dom)}")

out.append("\n=== Diversity (domains a country is specialised in, top 10) ===")
div = rep["diversity"].sort_values(ascending=False)
for iso, v in div.head(10).items():
    out.append(f"{int(v):2d}  {iso}  {names.get(iso, '')}")

out.append("\n=== Domain proximity — closest pairs ===")
prox = rep["proximity"]
seen = set()
pairs = []
for i in prox.index:
    for j in prox.columns:
        if i < j:
            pairs.append((prox.loc[i, j], i, j))
for v, i, j in sorted(pairs, reverse=True)[:8]:
    out.append(f"{v:.2f}  {L.get(i,i)}  <->  {L.get(j,j)}")

out.append("\n=== Adjacent possible (highest-density UNbuilt domains) ===")
dens, M = rep["density"], rep["M"]
recs = []
for iso in dens.index:
    for dom in dens.columns:
        if M.loc[iso, dom] < 1:  # not yet specialised
            recs.append((dens.loc[iso, dom], iso, dom))
for v, iso, dom in sorted(recs, reverse=True)[:12]:
    out.append(f"{v:.2f}  {iso} {names.get(iso,''):14} -> could build: {L.get(dom,dom)}")

text = "\n".join(out)
print(text)
Path("data/research/_complexity_report.txt").write_text(text + "\n")
