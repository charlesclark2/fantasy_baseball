"""
features_pa_outcome.py — E13.2 Phase 1 point-in-time feature builder.

Builds LEAK-SAFE batter / pitcher prior-outcome-rate profiles for the PA-outcome
model from the substrate itself (`mart_pa_outcome_substrate`), so no Snowflake
dependency is introduced (cost posture: lakehouse-native).

Leakage contract (the substrate's own caveat — every joined feature must be as-of
`< game_date`): for every plate appearance, a batter's / pitcher's prior-rate
profile is computed from PAs strictly BEFORE that PA's game_date. We implement
this with a cumulative-minus-current-date trick (no row-order shift to misalign):

    counts_strictly_before(date) = cumsum_through(date) - counts_on(date)

so all PAs sharing a game_date see the SAME profile, reflecting only earlier dates.
This excludes same-day games too (conservative — a doubleheader's game 1 does not
leak into game 2's features).

Empirical-Bayes shrinkage toward the league marginal handles thin batter×pitcher
cells: rate_eb_c = (n_c + KAPPA * league_c) / (n_total + KAPPA). The shrinkage
target is STATIC_LEAGUE_PRIOR — the documented 2015-2025 marginal. This is a fixed
GLOBAL CONSTANT (domain knowledge: "MLB HR rate ≈ 3%"), not per-row future data, so
it carries no temporal leakage — it is the standard EB prior. (An as-of expanding
league rate was considered but rejected: on the earliest dates it is degenerate
— e.g. one prior HR ⇒ league HR-rate 100% — which poisons cold-start games for no
real leak-safety gain over the constant.) The leak-critical quantities are the
batter/pitcher COUNTS, which are computed strictly as-of `< game_date` below.

The returned feature columns carry no rolling-window suffix (e.g. `_30d`) because
they are EXPANDING career-to-date rates; the purged-CV splitter's feature-aware
purge band therefore uses its default lookback, which is correct — there is no
fixed look-back window to purge beyond the season boundary the splitter already
enforces.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Canonical class order — matches mart_pa_outcome_substrate.pa_outcome_label.
CLASSES: list[str] = ["1B", "2B", "3B", "HR", "BB", "IBB", "HBP", "K", "out", "other"]

# Static cold-start league prior (2015-2025 R-season marginal, from the Phase-0
# class-balance query). Used ONLY when there is no as-of league history yet (the
# earliest dates). A fixed constant → no leakage. Order matches CLASSES.
STATIC_LEAGUE_PRIOR: dict[str, float] = {
    "1B": 0.14318, "2B": 0.04407, "3B": 0.00408, "HR": 0.03117, "BB": 0.08028,
    "IBB": 0.00109, "HBP": 0.01054, "K": 0.22218, "out": 0.46150, "other": 0.00191,
}

# Shrinkage strength (pseudo-PAs of league prior). ~100 PAs ≈ a few weeks for a
# regular; strong enough to tame rookies/relievers, weak enough to let regulars
# express their true rate.
DEFAULT_KAPPA: float = 100.0

_DATE = "game_date"
_OH = [f"_oh_{c}" for c in CLASSES]
_ONE = "_one"


def _counts_strictly_before(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per (`*keys`, game_date), the count of each class among that group's PAs
    strictly BEFORE that game_date, plus the prior PA total. Leak-safe by
    construction (cumulative-through-date minus the current date's own counts).

    `keys` is a list so the same mechanism serves overall rates (keys=["batter_id"])
    and matched SPLIT rates (keys=["batter_id","pitcher_hand"] etc.). Returns a frame
    indexed [*keys, game_date] with columns _oh_<c> + _one.
    """
    grp_cols = keys + [_DATE]
    daily = (
        df.groupby(grp_cols, sort=True)[_OH + [_ONE]]
        .sum()
        .reset_index()
        .sort_values(grp_cols)
    )
    grp = daily.groupby(keys, sort=False)
    cum_through = grp[_OH + [_ONE]].cumsum()          # includes current date
    strictly_before = cum_through - daily[_OH + [_ONE]].values  # subtract current date
    out = daily[keys + [_DATE]].copy()
    out[_OH + [_ONE]] = strictly_before.to_numpy()
    return out


def _eb_rates(counts: pd.DataFrame, kappa: float, prefix: str, keys: list[str]) -> pd.DataFrame:
    """Empirical-Bayes shrink `counts` (per *keys,date — strictly-before-date prior
    counts) toward STATIC_LEAGUE_PRIOR, returning EB rate columns
    `<prefix>_eb_<class>` + a prior-N column `<prefix>_prior_n`, indexed [*keys, date].
    """
    n_total = counts[_ONE].to_numpy(dtype=float)
    res = counts[keys + [_DATE]].copy()
    for c, oh in zip(CLASSES, _OH):
        n_c = counts[oh].to_numpy(dtype=float)
        res[f"{prefix}_eb_{c}"] = (n_c + kappa * STATIC_LEAGUE_PRIOR[c]) / (n_total + kappa)
    res[f"{prefix}_prior_n"] = n_total
    return res


# Heavier shrinkage for SPLIT rates — conditioned samples (vs-hand, at-TTO) are far
# thinner than overall rates, so shrink hard toward the player's OWN overall rate
# (hierarchical: thin split → player overall → league). κ≈200 pseudo-PAs.
DEFAULT_KAPPA_SPLIT: float = 200.0


def _split_eb_matched(
    df: pd.DataFrame, keys: list[str], target_prefix: str, out_prefix: str,
    kappa_split: float,
) -> pd.DataFrame:
    """Matched conditional EB rates, hierarchically shrunk toward the per-row
    player-overall rate `<target_prefix>_eb_<class>` (already on `df`).

    `keys` = [player_id, split_col] where split_col is a column on `df` whose value
    on each PA IS the context to match (e.g. pitcher_hand → batter's rate vs THIS
    pitcher's hand). Strictly-before-date counts are merged back on [*keys, date],
    so each PA sees only that player's earlier PAs in the matching context.
    Returns df with `<out_prefix>_eb_<class>` columns added.
    """
    counts = _counts_strictly_before(df, keys)
    counts = counts.rename(columns={**{oh: f"_sc_{c}" for c, oh in zip(CLASSES, _OH)},
                                    _ONE: "_sc_total"})
    df = df.merge(counts, on=keys + [_DATE], how="left")
    sc_total = df["_sc_total"].fillna(0.0).to_numpy(dtype=float)
    for c in CLASSES:
        sc_c = df[f"_sc_{c}"].fillna(0.0).to_numpy(dtype=float)
        target = df[f"{target_prefix}_eb_{c}"].to_numpy(dtype=float)  # player overall (as-of)
        df[f"{out_prefix}_eb_{c}"] = (sc_c + kappa_split * target) / (sc_total + kappa_split)
    df = df.drop(columns=[f"_sc_{c}" for c in CLASSES] + ["_sc_total"])
    return df


def build_pit_features(
    substrate: pd.DataFrame,
    kappa: float = DEFAULT_KAPPA,
    include_splits: bool = True,
    kappa_split: float = DEFAULT_KAPPA_SPLIT,
) -> tuple[pd.DataFrame, list[str]]:
    """Attach leak-safe point-in-time batter & pitcher prior-rate features.

    Parameters
    ----------
    substrate : DataFrame with at least game_pk, at_bat_number, game_date,
        batter_id, pitcher_id, batter_hand, pitcher_hand,
        pitcher_times_thru_order_at_entry, pa_outcome_label.
    kappa : EB shrinkage strength for OVERALL rates (toward the league marginal).
    include_splits : also build v2 MATCHED split rates (platoon + times-thru-order),
        hierarchically shrunk toward each player's overall rate.
    kappa_split : shrinkage strength for the split rates (heavier — thin samples).

    Returns
    -------
    (df, pit_feature_cols) : input with feature columns appended, and the list of
    appended PIT feature names. v1 = 20 overall EB rates + 2 prior-N (22). v2 adds
    30 matched-split EB rates (batter-platoon, pitcher-platoon, pitcher-TTO).
    """
    df = substrate.copy()
    df[_DATE] = pd.to_datetime(df[_DATE])

    # One-hot the label once.
    lab = df["pa_outcome_label"].astype(str)
    for c, oh in zip(CLASSES, _OH):
        df[oh] = (lab == c).astype("int64")
    df[_ONE] = 1

    # Overall batter & pitcher prior counts (strictly before date), EB → league.
    bat_eb = _eb_rates(_counts_strictly_before(df, ["batter_id"]), kappa, "bat", ["batter_id"])
    pit_eb = _eb_rates(_counts_strictly_before(df, ["pitcher_id"]), kappa, "pit", ["pitcher_id"])
    df = df.merge(bat_eb, on=["batter_id", _DATE], how="left")
    df = df.merge(pit_eb, on=["pitcher_id", _DATE], how="left")

    pit_cols = (
        [f"bat_eb_{c}" for c in CLASSES]
        + [f"pit_eb_{c}" for c in CLASSES]
        + ["bat_prior_n", "pit_prior_n"]
    )

    # Players with zero prior PAs get NaN: fill EB rates with the static marginal,
    # prior_n with 0. (Done before splits so splits can shrink toward a valid target.)
    for c in CLASSES:
        df[f"bat_eb_{c}"] = df[f"bat_eb_{c}"].fillna(STATIC_LEAGUE_PRIOR[c])
        df[f"pit_eb_{c}"] = df[f"pit_eb_{c}"].fillna(STATIC_LEAGUE_PRIOR[c])
    df["bat_prior_n"] = df["bat_prior_n"].fillna(0.0)
    df["pit_prior_n"] = df["pit_prior_n"].fillna(0.0)

    if include_splits:
        # Times-through-order bucket {1,2,3} (3 = 3rd+ time), the matched TTO context.
        df["_tto_bucket"] = (
            df["pitcher_times_thru_order_at_entry"].fillna(1).clip(lower=1, upper=3).astype("int64")
        )
        # Batter platoon: batter's rate vs THIS pitcher's hand → shrink to batter overall.
        df = _split_eb_matched(df, ["batter_id", "pitcher_hand"], "bat", "bat_plat", kappa_split)
        # Pitcher platoon: pitcher's rate vs THIS batter's hand → shrink to pitcher overall.
        df = _split_eb_matched(df, ["pitcher_id", "batter_hand"], "pit", "pit_plat", kappa_split)
        # Pitcher TTO: pitcher's rate at THIS times-thru-order bucket → shrink to pitcher overall.
        df = _split_eb_matched(df, ["pitcher_id", "_tto_bucket"], "pit", "pit_tto", kappa_split)
        pit_cols += (
            [f"bat_plat_eb_{c}" for c in CLASSES]
            + [f"pit_plat_eb_{c}" for c in CLASSES]
            + [f"pit_tto_eb_{c}" for c in CLASSES]
        )
        df = df.drop(columns="_tto_bucket")

    df = df.drop(columns=_OH + [_ONE])
    return df, pit_cols
