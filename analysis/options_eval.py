"""Ad-hoc evaluation: a country wanting BOTH job growth and rising sophistication
— what are its options? Reads the live panel via analysis.complexity.

Two axes the panel already measures:
  job-growth feasibility  -> density  (adjacency: can employment realistically grow here?)
  sophistication payoff   -> PCI      (domain complexity: does it raise the basket?)
                             + current volume_ord (the existing job base)

A "win-win" move = an UNBUILT domain (not yet specialised) that is both high-density
(feasible) and high-PCI (sophisticated). We rank those per country.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import taxonomy  # noqa: E402
from analysis import complexity as cx  # noqa: E402

LBL = taxonomy.DOMAIN_LABELS


def main() -> None:
    r = cx.full_report()
    names, M, dens, pci = r["names"], r["M"], r["density"], r["pci"]
    vol = cx.volume_ord_matrix(r["panel"])
    intensity = r["intensity"]

    # --- 1. the sophistication ladder: PCI per domain (which domains are the prizes) ---
    print("=" * 70)
    print("SOPHISTICATION LADDER — domain complexity (PCI, z-scored)")
    print("=" * 70)
    for dom, v in pci.sort_values(ascending=False).items():
        ub = int(M[dom].sum())
        print(f"  {v:+5.2f}   {LBL[dom]:24}  (held by {ub}/{len(M)} countries)")

    # normalise PCI to 0..1 for combining with density
    p = pci.reindex(M.columns)
    p01 = (p - p.min()) / (p.max() - p.min())

    # --- 2. per-country win-win options: unbuilt domains, ranked by density x PCI ---
    # win-win score = geometric mean of feasibility(density) and payoff(pci01)
    print("\n" + "=" * 70)
    print("WIN-WIN FRONTIER — best unbuilt moves per country")
    print("(feas = density 0..1 | soph = PCI 0..1 | score = geomean)")
    print("=" * 70)

    rows = []
    for iso in M.index:
        for dom in M.columns:
            if M.loc[iso, dom] == 1:
                continue  # already specialised — this is a 'deepen', not a new move
            feas = float(dens.loc[iso, dom])
            soph = float(p01[dom])
            score = float(np.sqrt(max(feas, 0) * max(soph, 0)))
            rows.append((iso, names.get(iso, iso), dom, feas, soph, score,
                         int(vol.loc[iso, dom]) if dom in vol.columns else 0))
    opt = pd.DataFrame(rows, columns=["iso", "country", "domain", "feas",
                                      "soph", "score", "cur_vol"])

    # diversity (how many domains a country already holds) to classify its situation
    diversity = M.sum(axis=1)

    # representative set: 2 leaders, 2 fast-followers, 2 aspirants by diversity
    div_sorted = diversity.sort_values(ascending=False)
    reps = list(div_sorted.index[:2]) + \
        list(div_sorted.index[len(div_sorted) // 2 - 1: len(div_sorted) // 2 + 1]) + \
        list(div_sorted.index[-2:])
    for iso in reps:
        sub = opt[opt.iso == iso].sort_values("score", ascending=False).head(3)
        held = [LBL[d] for d in M.columns if M.loc[iso, d] == 1]
        print(f"\n{names.get(iso, iso)}  — already specialised in "
              f"{len(held)}: {', '.join(held) or '(none)'}")
        for _, x in sub.iterrows():
            print(f"    -> {LBL[x.domain]:24} feas {x.feas:.2f}  soph {x.soph:.2f}"
                  f"  score {x.score:.2f}")

    # --- 3. who has GOOD options vs who must LEAP ---
    # best available win-win score per country = quality of its easiest sophistication move
    best = opt.sort_values("score", ascending=False).groupby("iso").first()
    best = best.join(diversity.rename("diversity"))
    best["country"] = [names.get(i, i) for i in best.index]
    print("\n" + "=" * 70)
    print("OPTION QUALITY — best win-win move available to each country")
    print("(high score = has an adjacent sophisticated move; low = must leap far)")
    print("=" * 70)
    bs = best.sort_values("score", ascending=False)
    for iso, x in bs.iterrows():
        print(f"  {x.score:.2f}  {x.country:18} next: {LBL[x.domain]:22}"
              f" (holds {int(x.diversity)} domains)")


if __name__ == "__main__":
    main()
