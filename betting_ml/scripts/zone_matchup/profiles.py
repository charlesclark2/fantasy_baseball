"""E13.10 profile assembly — raw lakehouse frames → EB-shrunk, cold-start-flagged profiles.

PURE pandas (the duckdb reads happen in lakehouse.py; this module is unit-testable on small
frames). Two outputs, built ONCE and serving both the viz (Track A) and the overlap feature
(Track B):

  * batter value profile — per (batter, vs_pitcher_hand, group, cell): EB-shrunk run value +
    whiff-rate + xwOBA-on-contact, each shrunk toward a tiered league prior (cell → group →
    global). is_cold_start when the batter's total window pitches < a floor (rookie/call-up).
  * pitcher usage profile — per (pitcher, vs_batter_hand, group, cell): the normalized pitch
    FREQUENCY (Σ=1). Cold-start pitchers fall back to the league usage distribution for their
    handedness; is_cold_start flagged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .grid import GridSpec, PITCH_GROUPS
from .shrink import K_RATE, K_VALUE, K_XWOBA, eb_mean, eb_rate

MIN_BATTER_PITCHES = 200    # below this in the window → batter cold-start (rookie/call-up)
MIN_PITCHER_PITCHES = 200   # below this → pitcher cold-start → league usage fallback


def _full_grid(keys: pd.DataFrame, grid: GridSpec) -> pd.DataFrame:
    """Cross `keys` (the distinct entity×hand rows) with every (pgroup, ix, iz) cell so the
    profile spans the FULL grid — unobserved cells then resolve to the EB prior (n=0) rather than
    being silently dropped (which would bias the freq-weighted overlap toward observed cells)."""
    cells = pd.DataFrame(
        [(pg, ix, iz) for pg in PITCH_GROUPS for ix in range(grid.nx) for iz in range(grid.nz)],
        columns=["pgroup", "ix", "iz"])
    return keys.assign(_k=1).merge(cells.assign(_k=1), on="_k").drop(columns="_k")


def _league_priors(league_raw: pd.DataFrame) -> dict:
    """Tiered league priors (cell → group → global) for run value, whiff-rate, xwOBA-on-contact.
    Keyed by (p_hand, b_hand, pgroup, ix, iz). league_raw columns per lakehouse.league_raw."""
    lr = league_raw.copy()
    for c in ("lg_rv", "lg_rv_swing", "lg_xwoba_con", "n_pitches", "n_swings", "n_whiffs"):
        lr[c] = pd.to_numeric(lr[c], errors="coerce")
    lr["whiff_rate"] = lr["n_whiffs"] / lr["n_swings"].replace(0, np.nan)

    def _wmean(g, val, w):
        gg = g[g[val].notna()]
        ww = gg[w].to_numpy(float)
        return float(np.sum(ww * gg[val]) / np.sum(ww)) if ww.sum() > 0 else np.nan

    cell = lr.set_index(["p_hand", "b_hand", "pgroup", "ix", "iz"])
    grp = lr.groupby(["p_hand", "b_hand", "pgroup"])
    return {
        "cell_rv": cell["lg_rv"].to_dict(),
        "cell_rv_swing": cell["lg_rv_swing"].to_dict(),
        "cell_whiff": cell["whiff_rate"].to_dict(),
        "cell_xwoba": cell["lg_xwoba_con"].to_dict(),
        "grp_rv": {k: _wmean(g, "lg_rv", "n_pitches") for k, g in grp},
        "grp_rv_swing": {k: _wmean(g, "lg_rv_swing", "n_swings") for k, g in grp},
        "grp_whiff": {k: _wmean(g, "whiff_rate", "n_swings") for k, g in grp},
        "grp_xwoba": {k: _wmean(g, "lg_xwoba_con", "n_pitches") for k, g in grp},
        "glob_rv": _wmean(lr, "lg_rv", "n_pitches"),
        "glob_rv_swing": _wmean(lr, "lg_rv_swing", "n_swings"),
        "glob_whiff": _wmean(lr, "whiff_rate", "n_swings"),
        "glob_xwoba": _wmean(lr, "lg_xwoba_con", "n_pitches"),
    }


def _resolve(priors: dict, kind: str, p_hand, b_hand, pgroup, ix, iz) -> float:
    """Cell → group → global fallback for a prior of `kind` ∈ {rv, whiff, xwoba}."""
    v = priors[f"cell_{kind}"].get((p_hand, b_hand, pgroup, ix, iz))
    if v is not None and not (isinstance(v, float) and np.isnan(v)):
        return v
    v = priors[f"grp_{kind}"].get((p_hand, b_hand, pgroup))
    if v is not None and not (isinstance(v, float) and np.isnan(v)):
        return v
    return priors[f"glob_{kind}"]


def build_batter_value(batter_raw: pd.DataFrame, league_raw: pd.DataFrame, *,
                       grid: GridSpec | None = None,
                       k_value: float = K_VALUE, k_rate: float = K_RATE,
                       k_xwoba: float = K_XWOBA,
                       min_pitches: int = MIN_BATTER_PITCHES) -> pd.DataFrame:
    """[batter_id, b_hand, vs_p_hand, pgroup, ix, iz, value, whiff_rate, xwoba_con, n_pitches,
    is_cold_start]. `value` (EB-shrunk run value, batter POV) is the overlap input. The profile
    spans the FULL grid per (batter, b_hand, vs_p_hand): cells the batter rarely sees resolve to
    the EB prior so the overlap is a true freq-weighted average."""
    out_cols = ["batter_id", "b_hand", "vs_p_hand", "pgroup", "ix", "iz", "value",
                "swing_value", "whiff_rate", "xwoba_con", "n_pitches", "is_cold_start"]
    if batter_raw.empty:
        return pd.DataFrame(columns=out_cols)
    grid = grid or GridSpec()
    priors = _league_priors(league_raw)
    raw = batter_raw.copy()
    for c in ("n_pitches", "raw_rv", "raw_rv_swing", "n_swings", "n_whiffs", "n_bip", "raw_xwoba_con"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")

    # Track total observed pitches per batter BEFORE the full-grid expansion (cold-start = thin).
    obs_tot = raw.groupby("batter_id")["n_pitches"].sum()

    keys = raw[["batter_id", "b_hand", "vs_p_hand"]].drop_duplicates()
    br = _full_grid(keys, grid).merge(
        raw, on=["batter_id", "b_hand", "vs_p_hand", "pgroup", "ix", "iz"], how="left")
    for c in ("n_pitches", "n_swings", "n_whiffs", "n_bip"):
        br[c] = br[c].fillna(0.0)

    # vs_p_hand on the batter frame is the pitcher hand; b_hand is the batter stance → both index
    # the league prior (p_hand=vs_p_hand, b_hand=b_hand).
    pr_rv = np.array([_resolve(priors, "rv", r.vs_p_hand, r.b_hand, r.pgroup, r.ix, r.iz)
                      for r in br.itertuples()])
    pr_rv_swing = np.array([_resolve(priors, "rv_swing", r.vs_p_hand, r.b_hand, r.pgroup, r.ix, r.iz)
                            for r in br.itertuples()])
    pr_wh = np.array([_resolve(priors, "whiff", r.vs_p_hand, r.b_hand, r.pgroup, r.ix, r.iz)
                      for r in br.itertuples()])
    pr_xw = np.array([_resolve(priors, "xwoba", r.vs_p_hand, r.b_hand, r.pgroup, r.ix, r.iz)
                      for r in br.itertuples()])

    br["value"] = eb_mean(br["raw_rv"].to_numpy(), br["n_pitches"].to_numpy(), pr_rv, k_value)
    # swing_value: EB-shrunk delta_run_exp conditioned on swings only (n_swings as effective N).
    # Shadow/ball zones with few swings collapse to the league swing-RV prior (near-zero or negative),
    # so the display correctly shows neutral-to-cold rather than misleadingly red from called balls.
    br["swing_value"] = eb_mean(br["raw_rv_swing"].to_numpy(), br["n_swings"].to_numpy(), pr_rv_swing, k_value)
    br["whiff_rate"] = eb_rate(br["n_whiffs"].to_numpy(), br["n_swings"].to_numpy(), pr_wh, k_rate)
    br["xwoba_con"] = eb_mean(br["raw_xwoba_con"].to_numpy(), br["n_bip"].to_numpy(), pr_xw, k_xwoba)

    br["is_cold_start"] = br["batter_id"].map(obs_tot).fillna(0.0) < min_pitches
    return br[out_cols]


def build_pitcher_freq(pitcher_raw: pd.DataFrame, league_raw: pd.DataFrame, *,
                       min_pitches: int = MIN_PITCHER_PITCHES) -> pd.DataFrame:
    """[pitcher_id, p_hand, vs_b_hand, pgroup, ix, iz, freq, n_pitches, is_cold_start].
    freq sums to 1 within each (pitcher, vs_b_hand). Cold-start pitchers use the league usage
    distribution for (p_hand, vs_b_hand)."""
    pr = pitcher_raw.copy()
    cols = ["pitcher_id", "p_hand", "vs_b_hand", "pgroup", "ix", "iz", "freq", "n_pitches",
            "loc_x", "loc_znorm", "is_cold_start"]
    if pr.empty:
        return pd.DataFrame(columns=cols)
    pr["n_pitches"] = pd.to_numeric(pr["n_pitches"], errors="coerce").fillna(0.0)
    for lc in ("loc_x", "loc_znorm"):   # mean cell location (bubble position); NaN ⇒ cell center
        if lc not in pr.columns:
            pr[lc] = np.nan

    # League usage distribution per (p_hand, vs_b_hand): lg_freq over (pgroup, ix, iz).
    lr = league_raw.copy()
    lr["n_pitches"] = pd.to_numeric(lr["n_pitches"], errors="coerce").fillna(0.0)
    lg = (lr.groupby(["p_hand", "b_hand", "pgroup", "ix", "iz"])["n_pitches"].sum()
          .reset_index().rename(columns={"b_hand": "vs_b_hand"}))
    lg_tot = lg.groupby(["p_hand", "vs_b_hand"])["n_pitches"].transform("sum")
    lg["lg_freq"] = lg["n_pitches"] / lg_tot.replace(0, np.nan)
    lg_map = lg.rename(columns={"n_pitches": "lg_n"})

    # Per-pitcher totals + cold-start flag.
    tot = pr.groupby(["pitcher_id", "vs_b_hand"])["n_pitches"].sum().rename("tot").reset_index()
    pr = pr.merge(tot, on=["pitcher_id", "vs_b_hand"], how="left")
    pr_tot_all = pr.groupby("pitcher_id")["n_pitches"].transform("sum")
    pr["is_cold_start"] = (pr_tot_all < min_pitches)

    # Non-cold: own normalized usage. Cold: replace with league usage (built below).
    pr["freq"] = pr["n_pitches"] / pr["tot"].replace(0, np.nan)
    warm = pr[~pr["is_cold_start"]].copy()

    cold_ids = pr.loc[pr["is_cold_start"], ["pitcher_id", "p_hand", "vs_b_hand"]].drop_duplicates()
    if not cold_ids.empty:
        cold = cold_ids.merge(lg_map, on=["p_hand", "vs_b_hand"], how="left")
        cold = cold[cold["lg_freq"].notna()]
        cold["freq"] = cold["lg_freq"]
        cold["n_pitches"] = 0.0
        cold["loc_x"] = np.nan        # league fallback ⇒ no measured location; viz uses cell center
        cold["loc_znorm"] = np.nan
        cold["is_cold_start"] = True
        cold = cold[cols]
    else:
        cold = pd.DataFrame(columns=cols)

    frames = [f[cols] for f in (warm, cold) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
