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


# ──────────────────────────────────────────────────────────────────────────────
# E13.2b — the RICHER profile decomposition the single overlap scalar collapsed.
#
# The E13.10 scalar `overlap` = Σ batter_value·pitcher_freq summed across BOTH pitch groups AND
# the value channel only. That collapse threw away three axes the profiles actually carry:
#   1. pitch-group STRUCTURE — a hitter exploited only on breaking balls vs only on fastballs reads
#      identically once summed; `ov_fb/ov_br/ov_os` keep the per-group freq-weighted value.
#   2. the WHIFF + xwOBA-on-contact channels — the scalar used `value` (Δrun_exp) alone; the
#      profile also carries `whiff_rate` (K-exposure → run suppression) and `xwoba_con`
#      (damage-on-contact) per cell. `ov_whiff`/`ov_xwoba` are those same freq-weighted reads.
#   3. PEAKINESS — the mean smooths over whether a batter has one concentrated exploitable cell the
#      pitcher lives in (`ov_peak` = the single largest cell contribution).
# Platoon structure is NOT a separate channel here: compute_*overlap already joins on each pair's
# actual b_hand/p_hand, so every feature below is already platoon-conditioned.
# These are the in-model test of the BUILT machinery (E13.2b) — emitted as home_/away_ game-grain
# columns the E13.4 harness ingests via --feature-parquet, exactly like the scalar.

PROFILE_VALUE_COLS = ["batter_id", "vs_p_hand", "pgroup", "ix", "iz",
                      "value", "whiff_rate", "xwoba_con"]

# The per-(game_pk, side) channels emitted, in the home_/away_ wide form.
PROFILE_CHANNELS = ["zone_value", "zone_fb", "zone_br", "zone_os",
                    "zone_whiff", "zone_xwoba", "zone_peak"]


def compute_profile_overlap(batter_val: pd.DataFrame, pitcher_freq: pd.DataFrame,
                            pairs: pd.DataFrame) -> pd.DataFrame:
    """Per-pair DECOMPOSED profile-overlap features (the richer form of compute_overlap).

    batter_val must carry [batter_id, vs_p_hand, pgroup, ix, iz, value, whiff_rate, xwoba_con];
    pitcher_freq [pitcher_id, vs_b_hand, pgroup, ix, iz, freq]; pairs [batter_id, b_hand,
    pitcher_id, p_hand]. Returns pairs + the per-pair channels:
      value  = Σ value·freq            (= compute_overlap's `overlap`; freq-weighted run value)
      fb/br/os = Σ_{group g} value·freq (the same, restricted to one pitch group)
      whiff  = Σ whiff_rate·freq        (freq-weighted K-exposure)
      xwoba  = Σ xwoba_con·freq         (freq-weighted damage-on-contact)
      peak   = max_cell (value·freq)    (largest single-cell contribution = exploitable-zone peak)
      cells  = #joined cells (coverage tell).
    freq sums to 1 over (cell, group) within a (pitcher, faced-hand) so value/whiff/xwoba are true
    usage-weighted averages; fb/br/os are the partial sums (NOT renormalised — they carry the
    pitcher's group MIX, which is the structural signal the total collapses)."""
    pairs = pairs.copy()
    pairs["__pair__"] = np.arange(len(pairs))

    bj = pairs.merge(
        batter_val.rename(columns={"value": "b_value", "whiff_rate": "b_whiff",
                                   "xwoba_con": "b_xwoba"}),
        left_on=["batter_id", "p_hand"], right_on=["batter_id", "vs_p_hand"], how="left",
    )[["__pair__", "pgroup", "ix", "iz", "b_value", "b_whiff", "b_xwoba"]]

    pj = pairs.merge(
        pitcher_freq.rename(columns={"freq": "p_freq"}),
        left_on=["pitcher_id", "b_hand"], right_on=["pitcher_id", "vs_b_hand"], how="left",
    )[["__pair__", "pgroup", "ix", "iz", "p_freq"]]

    cells = bj.merge(pj, on=["__pair__", "pgroup", "ix", "iz"], how="inner")
    cells = cells[cells["b_value"].notna() & cells["p_freq"].notna()]
    cells["c_value"] = cells["b_value"] * cells["p_freq"]
    cells["c_whiff"] = cells["b_whiff"] * cells["p_freq"]
    cells["c_xwoba"] = cells["b_xwoba"] * cells["p_freq"]
    for g in ("FB", "BR", "OS"):
        cells[f"c_{g.lower()}"] = np.where(cells["pgroup"] == g, cells["c_value"], 0.0)

    agg = (cells.groupby("__pair__")
           .agg(value=("c_value", "sum"), fb=("c_fb", "sum"), br=("c_br", "sum"),
                os=("c_os", "sum"), whiff=("c_whiff", "sum"), xwoba=("c_xwoba", "sum"),
                peak=("c_value", "max"), cells=("c_value", "size"))
           .reset_index())
    out = pairs.merge(agg, on="__pair__", how="left").drop(columns="__pair__")
    out["cells"] = out["cells"].fillna(0).astype(int)
    return out


def game_side_profile_features(lineups: pd.DataFrame, starters: pd.DataFrame,
                               batter_val: pd.DataFrame,
                               pitcher_freq: pd.DataFrame) -> pd.DataFrame:
    """Per-(game_pk, side) DECOMPOSED zone-profile features → home_/away_ wide form.

    Same lineup↔opposing-starter pairing as game_side_overlap, but emits the full PROFILE_CHANNELS
    (each averaged over the side's resolved hitters) instead of the lone overlap mean. Returns
    game_pk + home_/away_<channel> for each channel in PROFILE_CHANNELS + home_/away_zone_prof_n
    (resolved-hitter count). These are the columns the E13.4 harness ingests via --feature-parquet
    (home_win: pass home_/away_<channel>; perside: off_/opp_<channel>)."""
    opp = {"home": "away", "away": "home"}
    lu = lineups.copy()
    lu["opp_side"] = lu["side"].map(opp)
    pairs = lu.merge(starters.rename(columns={"side": "opp_side"}),
                     on=["game_pk", "opp_side"], how="inner")
    pairs = pairs[["game_pk", "side", "batter_id", "b_hand", "pitcher_id", "p_hand"]]
    out_cols = ["game_pk"] + [f"{s}_{c}" for c in PROFILE_CHANNELS for s in ("home", "away")] \
        + ["home_zone_prof_n", "away_zone_prof_n"]
    if pairs.empty:
        return pd.DataFrame(columns=out_cols)

    ov = compute_profile_overlap(batter_val, pitcher_freq, pairs)
    ov = ov[ov["value"].notna()]
    chan_src = {"zone_value": "value", "zone_fb": "fb", "zone_br": "br", "zone_os": "os",
                "zone_whiff": "whiff", "zone_xwoba": "xwoba", "zone_peak": "peak"}
    side_ag = (ov.groupby(["game_pk", "side"])
               .agg(**{c: (src, "mean") for c, src in chan_src.items()},
                    zone_prof_n=("value", "size"))
               .reset_index())
    metrics = list(chan_src) + ["zone_prof_n"]
    wide = side_ag.pivot(index="game_pk", columns="side", values=metrics)
    wide.columns = [f"{side}_{metric}" for metric, side in wide.columns]
    wide = wide.reset_index()
    for c in out_cols:
        if c not in wide.columns:
            wide[c] = np.nan
    return wide[out_cols]
