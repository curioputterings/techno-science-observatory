"""Economic-complexity metrics (Hidalgo-Hausmann / OEC) over the job panel.

We treat the (country x technology-domain) capability panel the way the OEC
treats (country x product) trade:

    intensity_cd  ~  export value of product d by country c

From that intensity matrix we derive the standard toolkit:

  RCA      Revealed Comparative Advantage  -> is a country specialised in a domain?
  M        binary specialisation matrix (RCA >= 1)
  diversity / ubiquity  (row / column sums of M)
  ECI      Economic/Technology Complexity Index per country
  PCI      Product/Technology Complexity Index per domain
  proximity   how related two domains are (min conditional co-specialisation)
  density     for each (country, domain) NOT yet specialised, how close it is
              -> the "adjacent possible": what a country could realistically build next

Reads data/jobs.db (cells table). Pure numpy/pandas — run under the project venv.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import taxonomy  # noqa: E402
from store import DB_PATH  # noqa: E402

# Intensity = volume(quantity) x skill-tier weight. Frontier roles dominate; this
# is what makes the complexity math reward *depth*, not just headcount.
TIER_WEIGHT = {1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0, 5: 8.0}


def load_panel(db_path=None, source: str = "gemini_research") -> pd.DataFrame:
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT country_iso, country_name, domain, volume_ord, skill_level, "
            "frontier FROM cells WHERE source = ?",
            conn, params=(source,),
        )
    finally:
        conn.close()
    return df


def intensity_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Country x domain matrix of capability intensity (the OEC 'value' matrix)."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["w"] = d["skill_level"].map(TIER_WEIGHT).fillna(1.0)
    # quantity (volume_ord 0..5) scaled by skill weight, with a frontier bonus
    d["intensity"] = d["volume_ord"] * d["w"] * (1.0 + d["frontier"].fillna(0.0))
    mat = d.pivot_table(index="country_iso", columns="domain",
                        values="intensity", aggfunc="sum", fill_value=0.0)
    cols = [c for c in taxonomy.ALL_DOMAINS if c in mat.columns]
    return mat[cols]


def rca(mat: pd.DataFrame) -> pd.DataFrame:
    """Revealed Comparative Advantage. RCA_cd = (X_cd/X_c) / (X_d/X)."""
    total = mat.values.sum()
    if total == 0:
        return mat * 0.0
    row = mat.sum(axis=1).replace(0, np.nan)
    col = mat.sum(axis=0) / total
    out = mat.div(row, axis=0).div(col.replace(0, np.nan), axis=1)
    return out.fillna(0.0)


def volume_ord_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Country x domain matrix of raw volume_ord (0..5), for absolute floors."""
    if df.empty:
        return pd.DataFrame()
    mat = df.pivot_table(index="country_iso", columns="domain",
                         values="volume_ord", aggfunc="max", fill_value=0)
    cols = [c for c in taxonomy.ALL_DOMAINS if c in mat.columns]
    return mat[cols]


def specialisation(mat: pd.DataFrame, threshold: float = 1.0,
                   vol: pd.DataFrame | None = None, min_vol_ord: int = 2) -> pd.DataFrame:
    """Binary specialisation M.

    A cell counts as specialised iff RCA >= threshold AND (when `vol` is given)
    the country has at least `min_vol_ord` real volume in that domain. The volume
    floor removes the RCA pathology where a near-empty country's noise reads as
    'specialisation' — which otherwise inflates ubiquity and corrupts ECI/PCI.
    """
    M = (rca(mat) >= threshold).astype(float)
    if vol is not None and not vol.empty:
        vol_al = vol.reindex(index=M.index, columns=M.columns).fillna(0)
        M = M * (vol_al >= min_vol_ord).astype(float)
    return M


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return s * 0.0
    return (s - s.mean()) / sd


def _second_eigvec(square: np.ndarray, index) -> pd.Series:
    vals, vecs = np.linalg.eig(square)
    order = np.argsort(vals.real)[::-1]
    idx = order[1] if len(order) > 1 else order[0]  # 2nd eigenvector carries signal
    return pd.Series(vecs[:, idx].real, index=index)


def complexity_indices(M: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """ECI (countries) and PCI (domains) via the method of reflections."""
    if M.empty or M.values.sum() == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    kc = M.sum(axis=1)   # diversity
    kp = M.sum(axis=0)   # ubiquity
    Mn = M.div(kc.replace(0, np.nan), axis=0).fillna(0.0)
    Mp = M.div(kp.replace(0, np.nan), axis=1).fillna(0.0)

    eci = _second_eigvec(Mn.values @ Mp.values.T, M.index)
    if eci.corr(kc) < 0:               # orient: more diverse -> higher ECI
        eci = -eci
    eci = _zscore(eci)

    pci = _second_eigvec(Mp.values.T @ Mn.values, M.columns)
    if pci.corr(kp) > 0:               # orient: less ubiquitous -> higher PCI
        pci = -pci
    pci = _zscore(pci)
    return eci, pci


def fitness_complexity(M: pd.DataFrame, iterations: int = 1000
                       ) -> tuple[pd.Series, pd.Series]:
    """Tacchella et al. non-linear Fitness-Complexity — a robust alternative to the
    eigenvector ECI/PCI, which degenerates on small/dense panels (here corr(ECI,
    diversity) was ~0.22 and the ranks inverted).

    Iterate to convergence, renormalising to mean 1 each step:
        F_c <- sum_d M[c,d] * Q_d                     (country fitness)
        Q_d <- 1 / sum_c ( M[c,d] / F_c )             (domain complexity)

    The 1/F_c term is the point: a domain is complex only if even *low-fitness*
    countries can't do it, so ubiquity is penalised non-linearly and diversified
    countries rise — exactly the failure modes of the linear method. Returns
    (fitness per country, complexity per domain), both mean-normalised (≈1 = avg).
    """
    if M.empty or M.values.sum() == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    Mv = M.values.astype(float)
    F = np.ones(Mv.shape[0])
    Q = np.ones(Mv.shape[1])
    for _ in range(iterations):
        F = Mv @ Q
        F = F / (F.mean() or 1.0)
        denom = Mv.T @ (1.0 / np.maximum(F, 1e-12))   # sum_c M[c,d]/F_c
        Q = 1.0 / np.maximum(denom, 1e-12)
        Q = Q / (Q.mean() or 1.0)
    return (pd.Series(F, index=M.index).sort_values(ascending=False),
            pd.Series(Q, index=M.columns).sort_values(ascending=False))


def proximity(M: pd.DataFrame) -> pd.DataFrame:
    """Domain-domain proximity: min(P(i|j), P(j|i)) over co-specialisation."""
    if M.empty:
        return pd.DataFrame()
    co = M.T.values @ M.values
    kp = M.sum(axis=0).values
    with np.errstate(divide="ignore", invalid="ignore"):
        cond = co / kp[None, :]
    cond = np.nan_to_num(cond)
    prox = np.minimum(cond, cond.T)
    np.fill_diagonal(prox, 0.0)
    return pd.DataFrame(prox, index=M.columns, columns=M.columns)


def density(M: pd.DataFrame) -> pd.DataFrame:
    """(country, domain) density: weighted share of related domains already held."""
    prox = proximity(M)
    if prox.empty:
        return pd.DataFrame()
    denom = prox.sum(axis=0).replace(0, np.nan)
    dens = (M.values @ prox.values) / denom.values[None, :]
    return pd.DataFrame(np.nan_to_num(dens), index=M.index, columns=M.columns)


def complexity_weighted_capability(mat: pd.DataFrame, pci: pd.Series) -> pd.Series:
    """Basket complexity: how complex is the *mix* of what a country does?

    Each country's intensity is turned into a within-country share across domains,
    then dotted with domain complexity (PCI). High = concentrated in rare/complex
    domains (e.g. semiconductors), regardless of absolute size. This is the
    interpretable complement to the noisy small-N eigenvector ECI.
    """
    if mat.empty or pci.empty:
        return pd.Series(dtype=float)
    shares = mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return shares.mul(pci.reindex(shares.columns).fillna(0.0), axis=1).sum(axis=1)


def full_report(db_path=None, source: str = "gemini_research",
                min_vol_ord: int = 2) -> dict:
    df = load_panel(db_path, source)
    mat = intensity_matrix(df)
    vol = volume_ord_matrix(df)
    M = specialisation(mat, vol=vol, min_vol_ord=min_vol_ord)
    eci, pci = complexity_indices(M)
    fitness, dom_fitness = fitness_complexity(M)
    cwc = complexity_weighted_capability(mat, pci)
    names = (df.drop_duplicates("country_iso")
             .set_index("country_iso")["country_name"].to_dict())
    return {
        "panel": df,
        "names": names,
        "intensity": mat,
        "rca": rca(mat),
        "M": M,
        "diversity": M.sum(axis=1),
        "ubiquity": M.sum(axis=0),
        "eci": eci.sort_values(ascending=False) if not eci.empty else eci,
        "fitness": fitness,            # non-linear country complexity (robust ECI)
        "domain_fitness": dom_fitness,
        "pci": pci.sort_values(ascending=False) if not pci.empty else pci,
        "basket_complexity": (cwc.sort_values(ascending=False)
                              if not cwc.empty else cwc),
        "proximity": proximity(M),
        "density": density(M),
    }
