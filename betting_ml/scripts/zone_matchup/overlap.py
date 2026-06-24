"""E13.10 zone-overlap scalar + per-game aggregation — PURE pandas (unit-tested).

The matchup feature (TRACK B) is the E5.6 game-theory-corrected overlap:

    overlap(b, p) = Σ_{cell, group}  batter_value(b, vs p.hand, cell, group)
                                     · pitcher_freq(p, vs b.hand, cell, group)

`pitcher_freq` sums to 1 over (cell, group) within a (pitcher, faced-batter-hand), so the overlap
is the batter's per-cell run value AVERAGED BY WHERE/WHAT THE PITCHER ACTUALLY THROWS — i.e. a
hitter's hot zones only count to the extent the pitcher lives there (the §"game-theory correction"
that distinguishes this from a naive max-hot-cell read). Units: expected batter run value per
pitch (>0 ⇒ batter advantaged vs this pitcher's tendencies).

Per game/side: aggregate overlap over the side's first-time-through lineup vs the opposing
starter → `home_zone_overlap` / `away_zone_overlap`, the columns the E13.4 harness ingests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Profile-frame column contracts (post-shrinkage).
BATTER_VALUE_COLS = ["batter_id", "vs_p_hand", "pgroup", "ix", "iz", "value"]
PITCHER_FREQ_COLS = ["pitcher_id", "vs_b_hand", "pgroup", "ix", "iz", "freq"]


def compute_overlap(batter_val: pd.DataFrame, pitcher_freq: pd.DataFrame,
                    pairs: pd.DataFrame) -> pd.DataFrame:
    """Overlap scalar for each (batter_id, b_hand, pitcher_id, p_hand) row in `pairs`.

    batter_val: [batter_id, vs_p_hand, pgroup, ix, iz, value]  (EB-shrunk run value)
    pitcher_freq: [pitcher_id, vs_b_hand, pgroup, ix, iz, freq] (normalized, Σ=1 per pitcher×hand)
    pairs: [batter_id, b_hand, pitcher_id, p_hand]
    Returns pairs + ["overlap", "overlap_cells"] (overlap_cells = #joined cells, a coverage tell).
    """
    pairs = pairs.copy()
    pairs["__pair__"] = np.arange(len(pairs))

    # Batter side: keep only rows matching each pair's faced pitcher hand.
    bj = pairs.merge(
        batter_val.rename(columns={"value": "b_value"}),
        left_on=["batter_id", "p_hand"], right_on=["batter_id", "vs_p_hand"], how="left",
    )[["__pair__", "pgroup", "ix", "iz", "b_value"]]

    # Pitcher side: rows matching each pair's batter hand.
    pj = pairs.merge(
        pitcher_freq.rename(columns={"freq": "p_freq"}),
        left_on=["pitcher_id", "b_hand"], right_on=["pitcher_id", "vs_b_hand"], how="left",
    )[["__pair__", "pgroup", "ix", "iz", "p_freq"]]

    cells = bj.merge(pj, on=["__pair__", "pgroup", "ix", "iz"], how="inner")
    cells = cells[cells["b_value"].notna() & cells["p_freq"].notna()]
    cells["contrib"] = cells["b_value"] * cells["p_freq"]

    agg = (cells.groupby("__pair__")
           .agg(overlap=("contrib", "sum"), overlap_cells=("contrib", "size"))
           .reset_index())
    out = pairs.merge(agg, on="__pair__", how="left").drop(columns="__pair__")
    out["overlap_cells"] = out["overlap_cells"].fillna(0).astype(int)
    return out


def game_side_overlap(lineups: pd.DataFrame, starters: pd.DataFrame,
                      batter_val: pd.DataFrame, pitcher_freq: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-batter overlap to a per-(game_pk, side) team feature.

    lineups:  [game_pk, side, batter_id, b_hand]   (the side's hitters; side ∈ {home, away})
    starters: [game_pk, side, pitcher_id, p_hand]   (each side's starting pitcher)
    A side's offense faces the OPPOSING side's starter. Returns
    [game_pk, home_zone_overlap, away_zone_overlap, home_zone_overlap_n, away_zone_overlap_n],
    where _n is the number of lineup hitters that resolved (a coverage / shrink-trust tell).
    """
    opp = {"home": "away", "away": "home"}
    st = starters.rename(columns={"side": "opp_side", "pitcher_id": "pitcher_id",
                                  "p_hand": "p_hand"})
    lu = lineups.copy()
    lu["opp_side"] = lu["side"].map(opp)
    pairs = lu.merge(st, on=["game_pk", "opp_side"], how="inner")
    pairs = pairs[["game_pk", "side", "batter_id", "b_hand", "pitcher_id", "p_hand"]]
    if pairs.empty:
        return pd.DataFrame(columns=["game_pk", "home_zone_overlap", "away_zone_overlap",
                                     "home_zone_overlap_n", "away_zone_overlap_n"])

    ov = compute_overlap(batter_val, pitcher_freq, pairs)
    ov = ov[ov["overlap"].notna()]
    side_ag = (ov.groupby(["game_pk", "side"])
               .agg(zone_overlap=("overlap", "mean"), n=("overlap", "size"))
               .reset_index())
    wide = side_ag.pivot(index="game_pk", columns="side", values=["zone_overlap", "n"])
    wide.columns = [f"{side}_zone_overlap" if metric == "zone_overlap"
                    else f"{side}_zone_overlap_n" for metric, side in wide.columns]
    wide = wide.reset_index()
    for c in ["home_zone_overlap", "away_zone_overlap",
              "home_zone_overlap_n", "away_zone_overlap_n"]:
        if c not in wide.columns:
            wide[c] = np.nan
    return wide[["game_pk", "home_zone_overlap", "away_zone_overlap",
                 "home_zone_overlap_n", "away_zone_overlap_n"]]
