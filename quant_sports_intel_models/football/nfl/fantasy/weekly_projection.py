"""weekly_projection.py — NF-W1: the lean weekly per-game distributional fantasy projection (pure).

THE STORY IN ONE PARAGRAPH. Everything in-season (next-N-games, weekly ROS, drop/add, start/sit)
needs a PER-GAME projection that does not exist: the whole NF1 stack is one row per player-SEASON.
NF-W0 certified the weekly point-in-time labeled frame this model may fit on (89,954 player-weeks
2016–2025 REG, 46.1% retained zeros, label `v1.nflverse.stats_player_week`); NF-W0a shipped the
PIT leakage guard this module must INVOKE at its assembly boundary; NF-W0b made snap features
NULL-bearing. NF-W1 fits INSIDE those constraints: a §0.5 bake-off of ≥3 learner classes against
the honest degenerate weekly baseline — "season ÷ games, spread by a matchup adjustment" — on
purged/embargoed held-out WEEKS, selected on CRPS, per position. A weekly model that does not beat
that foil is a recorded NULL, not served.

🚨 THE MOTIVATION IS NOT THE RESULT. The existing `run_nf1.py --mode weekly-bakeoff` null (matchup/
env/home tilts all lost to flat season÷games on within-position ρ, 2026-07-27) is cited here once as
prior context and never again: it was scored on ρ only — no CRPS, no deflation, no anchors — which
is exactly the opening this story tests cleanly.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS PRE-REGISTERED, AND WHERE IT IS WRITTEN DOWN
────────────────────────────────────────────────────────────────────────────────────────────────
Everything that could otherwise be chosen after seeing a result lives as a CONSTANT in THIS module
and the runner READS it (the NF-D16 discipline). The narrative copy is committed before the full
run in `ablation_results/nf_w1_preregistration.md`.

  · SELECTION_METRIC = "crps_q39" — CRPS via the 2×mean-pinball identity over Q_LEVELS (39 levels).
    ⛔ MAE is INVERTED at QB/TE on this frame (conditional median exactly 0.0 — NF-W0 §2.3, the
    NF-D11/NF-D14 class): MAE/RMSE are REPORTED, never select and never gate.
  · The scoring population: positions QB/RB/WR/TE, label ≠ 'bye'. A bye is a DETERMINISTIC zero
    knowable at schedule release — serving emits it as the identity 0, and scoring every arm on
    identical free zeros discriminates nothing. Inactive + dressed-no-stat zeros are RETAINED
    (game-day status is a banned feature, so availability risk is exactly what the model must
    price). The with-bye sensitivity is REPORTED for the winner/foil/nihilist.
  · Folds: 8 expanding-window HALF-SEASON test blocks over weeks (TEST_BLOCKS, 2022H1..2025H2),
    train = all rows ≥ PURGE_WEEKS global weeks before the block start. 2016–2021 is burn-in
    history only. Purged/embargoed over WEEKS, never a random shuffle.
  · The field: REAL_ARMS (4 learner classes) + FOILS (the story foil family). Anchors are
    DIAGNOSTIC, never trials (MH2.1 (a)): excluded from the PBO matrix and the DSR trial field.
  · Gates per position: beats the BEST foil on mean fold CRPS ∧ calibrated fold-consistency
    (cv_power.fold_consistency_clause(8)) ∧ PBO < 0.20 over the eligible field ∧ DSR ≥ 0.95 over
    the declared 4-arm real family ∧ BH-FDR(q=0.10) across the four position tests. Fail ⇒
    cv_power.classify_null, recorded, nothing served.
  · Anchors, two-sided (NF1.7 (d)): `nihilist_zero` + `pos_marginal` degenerates MUST lose;
    `permuted_within` (same estimator, labels shuffled within position×week) MUST lose;
    `oracle_marginal` (peeking per-position marginal on the test block) is a REPORTED ceiling a
    conditional arm may legitimately beat (capacity — NF1.9 (f)); `zero_width` + `max_width`
    sharpness degenerates MUST both lose (a coverage floor a degenerate satisfies is fine; a
    criterion one wins is fatal — NF1.8).
  · COVERAGE_FLOOR = 0.80 on the central 80% interval is a FLOOR, never a target: reported with
    binomial SE; blocks only when the shortfall exceeds 3 SE (NF1.8 rows-not-decimals rule).
  · Feature families: the six USED_FAMILIES below, all lagged, named `<family>__<detail>` so
    provenance is checkable by prefix against NF-W0's ALLOWED_FEATURE_CONTRACT. The
    pbp_participation-derived pressure/coverage/route legs are NOT USED AT ALL in this slice, so
    the NF-W0c 2023 era boundary cannot be pooled across (constraint honored by exclusion,
    guard-tested via ERA_FORBIDDEN_TOKENS).
  · Snap features are NULL-bearing (NF-W0b): a NULL means "unmeasured", never "zero snaps".
    ⛔ No fillna(0) on any snap_share__ column; the observed-share flag carries presence.
    Model-internal median imputation (fit on TRAIN only, presence flags retained) is declared for
    the learners that cannot pass NaN through — that is a device inside the arm, not a data edit.

⚖️ EDGE-INDEPENDENT (best_alpha = 0): a fantasy projection product. No betting/edge/CLV claim.

────────────────────────────────────────────────────────────────────────────────────────────────
THE PIT BOUNDARY (NF-W0a — the guard is a library; THIS module is its first caller)
────────────────────────────────────────────────────────────────────────────────────────────────
`assemble_matrix` — the ONLY sanctioned way to get a feature matrix out of this module — calls
`pit.leakage_guard.assert_point_in_time` once per target (season, week) over that week's assembled
rows. For lake-derived historical features the stamps are the WINDOW-END AS-OF INSTANT (the day
after the last source game's gameday): "when could this fact have been known" for a reproducible
vendor record of a played game is when the game was played, and the guard then enforces the two
invariants a backtest can violate — every stamp ≤ the projection instant, and every rolling window
strictly before the target kickoff (clause 9). `source_timestamp` is declared absent (the nflverse
weekly release carries no per-row as-of stamp — the injuries.date_modified class). A week whose
window cannot be proven clean (the 2020 rescheduling shape: a prior-week game PLAYED after this
week's first kickoff) is DROPPED fail-closed and counted, never silently retained.

The store_index is `{}` — honest, because this slice consumes ZERO rows from the PIT capture
store (weather/market/injury features are deferred by NF-W0 constraint (5)). The moment a PIT
source joins, `PIT_STORE_SOURCES_CONSUMED` must name it and `run_pit_gate` REFUSES to run with an
empty index (a loud NotImplementedError, so the future misuse cannot be quiet).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
LABEL_VERSION = "v1.nflverse.stats_player_week"
SCORING_SYSTEM_ID = "ppr"
POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

SELECTION_METRIC = "crps_q39"
#: CRPS evaluation levels — the common predictive representation every arm must emit.
Q_LEVELS: np.ndarray = np.round(np.arange(0.025, 0.9751, 0.025), 4)  # 39 levels
#: The 9 knot levels the quantile LEARNERS fit; predictions are interpolated onto Q_LEVELS.
FIT_LEVELS: tuple[float, ...] = (0.05, 0.10, 0.25, 0.40, 0.50, 0.60, 0.75, 0.90, 0.95)

#: Expanding-window folds over WEEKS: (test_season, half). H1 = weeks 1–9, H2 = weeks 10+.
TEST_BLOCKS: tuple[tuple[int, int], ...] = (
    (2022, 1), (2022, 2), (2023, 1), (2023, 2),
    (2024, 1), (2024, 2), (2025, 1), (2025, 2),
)
H1_WEEKS = tuple(range(1, 10))
PURGE_WEEKS = 2

PBO_MAX = 0.20
DSR_MIN = 0.95
FDR_Q = 0.10
COVERAGE_FLOOR = 0.80          # a FLOOR, never a target (NF1.8); blocking only beyond 3 binomial SE
COVERAGE_BLOCK_SE = 3.0
INTERVAL_LO, INTERVAL_HI = 0.10, 0.90

REAL_ARMS: tuple[str, ...] = ("lgbm_quantile", "lgbm_hurdle", "enet_residual", "knn_quantile")
FOILS: tuple[str, ...] = ("foil_flat", "foil_matchup")
ANCHORS: tuple[str, ...] = (
    "nihilist_zero", "pos_marginal", "oracle_marginal", "permuted_within", "zero_width", "max_width",
)
#: Foil wins and anchor wins are recorded nulls, never ships.
NON_SHIPPABLE: tuple[str, ...] = FOILS + ANCHORS

#: Foil form: EB-shrunk unconditional PPG × a clipped DVP multiplier (the story's
#: "season ÷ games, spread by a matchup adjustment"). Denominators are ROSTERED TEAM GAMES ex-bye
#: (unconditional — availability risk embedded), matching the served NF1 weekly leg's semantics.
EB_KAPPA = 4.0
DVP_CLIP = (0.75, 1.25)

#: NF-W0c constraint (7) honored by EXCLUSION in this slice: no participation-era legs at all.
ERA_FORBIDDEN_TOKENS: tuple[str, ...] = ("pressure", "coverage", "route", "ngs_air_yards")

#: NF-W0 contract families this slice consumes (prefix == family name; `assert_feature_provenance`
#: maps `<family>__<detail>` columns onto the certified contract and rejects everything else).
USED_FAMILIES: tuple[str, ...] = (
    "game_context", "prior_week_box", "snap_share",
    "team_environment", "opponent_matchup", "prior_season_priors",
)
#: Allowed-but-deliberately-unused in slice 1 (recorded, not silent): participation_proxies,
#: pfr_advanced, ngs_qualifying (sparse-overlay discipline deferred with it), injury_report
#: (prospective_shadow fidelity + the 46% semantic-null report_status trap).
UNUSED_ALLOWED_FAMILIES: tuple[str, ...] = (
    "participation_proxies", "pfr_advanced", "ngs_qualifying", "injury_report",
)

#: PIT capture-store sources this build consumes. EMPTY in slice 1 — see the module docstring.
PIT_STORE_SOURCES_CONSUMED: tuple[str, ...] = ()

FEATURES: tuple[str, ...] = (
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "prior_week_box__ppr_l1",
    "prior_week_box__ppr_l4_mean",
    "prior_week_box__ppr_ewm",
    "prior_week_box__ppr_s2d_mean",
    "prior_week_box__targets_l4",
    "prior_week_box__carries_l4",
    "prior_week_box__attempts_l4",
    "prior_week_box__receptions_l4",
    "prior_week_box__rec_yards_l4",
    "prior_week_box__rush_yards_l4",
    "prior_week_box__pass_yards_l4",
    "prior_week_box__played_share_l4",
    "prior_week_box__games_s2d",
    "prior_week_box__ppr_sum_s2d",
    "snap_share__l1",
    "snap_share__l4_mean",
    "snap_share__observed_l4",
    "team_environment__pass_att_l4",
    "team_environment__rush_att_l4",
    "team_environment__ppr_l4",
    "opponent_matchup__dvp_ppr_index_l8",
    "opponent_matchup__def_ppr_allowed_l8",
    "prior_season_priors__ppg_prior",
    "prior_season_priors__games_prior",
    "prior_season_priors__rookie_flag",
)

#: Raw components the winner's component head emits (MVP-1 raw-line philosophy: any league's
#: scoring can re-score them; points are a convenience, never the product contract).
COMPONENTS: tuple[str, ...] = (
    "attempts", "passing_yards", "passing_tds", "passing_interceptions",
    "carries", "rushing_yards", "rushing_tds",
    "targets", "receptions", "receiving_yards", "receiving_tds",
)

_SEED = 20260806


# ── Provenance (fail-closed, delegates to the NF-W0 certified guard) ────────────────────────────
def assert_feature_provenance(feature_columns: list[str] | tuple[str, ...]) -> None:
    """Reject any feature whose provenance is not checkable against the NF-W0 contract.

    Three clauses, each independently RED-provable:
      1. every column is `<family>__<detail>` with family ∈ USED_FAMILIES — unknown provenance is a
         REJECTION, not a warning;
      2. no column name carries a LEAKY token (WF.LEAKY_COLUMNS, token-boundary rule) — run on the
         FULL engineered names, not just the family names;
      3. no column carries a participation-era token (ERA_FORBIDDEN_TOKENS) — the 2023 provider
         switch means those legs may not exist here without an era split this slice does not build.
    Then the certified NF-W0 clause runs on the family names themselves.
    """
    bad_prefix = [c for c in feature_columns
                  if "__" not in c or c.split("__", 1)[0] not in USED_FAMILIES]
    if bad_prefix:
        raise WF.LeakageError(
            f"features with unknown provenance reject the build: {sorted(bad_prefix)} — every "
            f"NF-W1 feature must be named '<family>__<detail>' with family in {USED_FAMILIES}"
        )
    leaky = [c for c in feature_columns
             if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_")
                    for tok in WF.LEAKY_COLUMNS)]
    if leaky:
        raise WF.LeakageError(f"leaky feature columns reject the build: {sorted(leaky)}")
    era = [c for c in feature_columns if any(tok in c for tok in ERA_FORBIDDEN_TOKENS)]
    if era:
        raise WF.LeakageError(
            f"participation-era features reject this slice: {sorted(era)} — the 2023 provider "
            f"switch (NF-W0c) forbids pooling pressure/coverage/route legs without an era split"
        )
    families = sorted({c.split("__", 1)[0] for c in feature_columns})
    WF.assert_no_leakage(pd.DataFrame(), feature_columns=families, projection_week=0)


# ── Feature engineering (all lagged; NULL-preserving snaps) ─────────────────────────────────────
def _team_week_table(schedule: pd.DataFrame) -> pd.DataFrame:
    """One row per (season, week, team) with opponent / is_home / gameday / div_game."""
    home = schedule.rename(columns={"home_team": "team", "away_team": "opponent"}).assign(is_home=1)
    away = schedule.rename(columns={"away_team": "team", "home_team": "opponent"}).assign(is_home=0)
    cols = ["season", "week", "team", "opponent", "is_home", "gameday", "div_game"]
    tw = pd.concat([home[cols], away[cols]], ignore_index=True)
    tw["season"] = tw["season"].astype("int64")
    tw["week"] = tw["week"].astype("int64")
    tw["gameday"] = pd.to_datetime(tw["gameday"])
    return tw


def _global_week_index(schedule: pd.DataFrame) -> pd.DataFrame:
    """A dense global ordering of (season, week) across the whole span — the purge/fold axis."""
    sw = schedule[["season", "week"]].drop_duplicates().astype("int64")
    sw = sw.sort_values(["season", "week"]).reset_index(drop=True)
    sw["gw"] = np.arange(len(sw))
    return sw


def engineer_features(
    frame: pd.DataFrame,
    stats: pd.DataFrame,
    snaps: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the pre-registered lagged feature block to the certified frame.

    Every feature is computed from rows STRICTLY BEFORE the target week (shift(1) before any
    rolling), which `run_pit_gate` then independently enforces per week. Snap columns are
    NULL-preserving end to end (NF-W0b constraint (9)).
    """
    tw = _team_week_table(schedule)
    gw_map = _global_week_index(schedule)

    f = frame[frame["position"].isin(POSITIONS)].copy()
    f = f.merge(gw_map, on=["season", "week"], how="left")
    f = f.merge(tw, on=["season", "week", "team"], how="left")  # byes: opponent/gameday NaN

    # per-team rest days (from schedule alone — knowable at schedule release)
    tw_sorted = tw.sort_values(["team", "gameday"]).copy()
    tw_sorted["days_since_last_game"] = (
        tw_sorted.groupby("team")["gameday"].diff().dt.days
    )
    f = f.merge(
        tw_sorted[["season", "week", "team", "days_since_last_game"]],
        on=["season", "week", "team"], how="left",
    )

    # ── stat components on the frame rows (real zeros for rostered-no-stat weeks) ──
    comp_cols = ["passing_yards", "rushing_yards", "receiving_yards"]
    s = stats.rename(columns={"player_id": "gsis_id"})[
        ["season", "week", "gsis_id", *comp_cols]
    ].copy()
    for c in ("season", "week"):
        s[c] = s[c].astype("int64")
    f = f.merge(s, on=["season", "week", "gsis_id"], how="left")
    # These are LABEL-side realized values on the row itself; they are used ONLY through shift(1)
    # windows below and are dropped from the emitted matrix.
    for c in comp_cols + ["carries", "targets", "attempts", "receptions"]:
        f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0.0)

    f = f.sort_values(["gsis_id", "gw"]).reset_index(drop=True)
    g = f.groupby("gsis_id", sort=False)

    def lag_roll(col: str, window: int, minp: int = 1):
        return (
            g[col].shift(1).groupby(f["gsis_id"], sort=False)
            .rolling(window, min_periods=minp).mean().reset_index(level=0, drop=True)
        )

    f["prior_week_box__ppr_l1"] = g["fantasy_points"].shift(1)
    f["prior_week_box__ppr_l4_mean"] = lag_roll("fantasy_points", 4)
    f["prior_week_box__ppr_ewm"] = (
        g["fantasy_points"].shift(1).groupby(f["gsis_id"], sort=False)
        .transform(lambda x: x.ewm(halflife=2, min_periods=1).mean())
    )
    for src, name in [
        ("targets", "targets_l4"), ("carries", "carries_l4"), ("attempts", "attempts_l4"),
        ("receptions", "receptions_l4"), ("receiving_yards", "rec_yards_l4"),
        ("rushing_yards", "rush_yards_l4"), ("passing_yards", "pass_yards_l4"),
    ]:
        f[f"prior_week_box__{name}"] = lag_roll(src, 4)
    f["_played"] = (f["label"] == WF.LABEL_PLAYED).astype(float)
    f["prior_week_box__played_share_l4"] = lag_roll("_played", 4)

    # season-to-date (within season, strictly prior weeks; ex-bye games count toward the denominator)
    f["_is_game_row"] = (f["label"] != WF.LABEL_BYE).astype(float)
    gs = f.groupby(["gsis_id", "season"], sort=False)
    f["prior_week_box__ppr_sum_s2d"] = gs["fantasy_points"].cumsum() - f["fantasy_points"]
    f["prior_week_box__games_s2d"] = gs["_is_game_row"].cumsum() - f["_is_game_row"]
    f["prior_week_box__ppr_s2d_mean"] = (
        f["prior_week_box__ppr_sum_s2d"] / f["prior_week_box__games_s2d"].replace(0, np.nan)
    )

    # ── snaps: NULL-preserving (⛔ no fillna(0) — NF-W0b constraint (9)) ──
    sn = snaps.loc[snaps["gsis_id"].notna(),
                   ["season", "week", "gsis_id", "offense_pct"]].copy()
    for c in ("season", "week"):
        sn[c] = sn[c].astype("int64")
    sn["offense_pct"] = pd.to_numeric(sn["offense_pct"], errors="coerce")
    sn = sn.groupby(["season", "week", "gsis_id"], as_index=False)["offense_pct"].mean()
    f = f.merge(sn, on=["season", "week", "gsis_id"], how="left")
    f["snap_share__l1"] = g_shift = f.groupby("gsis_id", sort=False)["offense_pct"].shift(1)
    grp = g_shift.groupby(f["gsis_id"], sort=False)
    f["snap_share__l4_mean"] = grp.rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    # share of the player's PRIOR weeks (up to 4) with a MEASURED snap row — the presence flag the
    # NULL-bearing contract requires. The flag is per source week, lagged like every other feature.
    obs_flag = f["offense_pct"].notna().astype(float)
    f["snap_share__observed_l4"] = (
        obs_flag.groupby(f["gsis_id"], sort=False).shift(1)
        .groupby(f["gsis_id"], sort=False).rolling(4, min_periods=1).mean()
        .reset_index(level=0, drop=True)
    )

    # ── team environment (lagged team aggregates of the same audited stats feed) ──
    team_agg = (
        f.groupby(["season", "week", "team"], as_index=False)
        .agg(_t_pass=("attempts", "sum"), _t_rush=("carries", "sum"),
             _t_ppr=("fantasy_points", "sum"), _t_gw=("gw", "first"))
        .sort_values(["team", "_t_gw"])
    )
    tg = team_agg.groupby("team", sort=False)
    for src, name in [("_t_pass", "pass_att_l4"), ("_t_rush", "rush_att_l4"), ("_t_ppr", "ppr_l4")]:
        team_agg[f"team_environment__{name}"] = (
            tg[src].shift(1).groupby(team_agg["team"], sort=False)
            .rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
        )
    f = f.merge(
        team_agg[["season", "week", "team"] + [c for c in team_agg.columns if c.startswith("team_environment__")]],
        on=["season", "week", "team"], how="left",
    )

    # ── opponent matchup: PPR allowed BY the opponent's defense TO the position, lagged L8 ──
    st = stats.rename(columns={"player_id": "gsis_id"})[
        ["season", "week", "position", "opponent_team", "fantasy_points_ppr"]
    ].copy()
    st = st[st["position"].isin(POSITIONS)]
    for c in ("season", "week"):
        st[c] = st[c].astype("int64")
    dvp = (
        st.groupby(["season", "week", "opponent_team", "position"], as_index=False)
        ["fantasy_points_ppr"].sum()
        .rename(columns={"opponent_team": "def_team", "fantasy_points_ppr": "_allowed"})
    )
    dvp = dvp.merge(gw_map, on=["season", "week"], how="left").sort_values(["def_team", "position", "gw"])
    dg = dvp.groupby(["def_team", "position"], sort=False)
    dvp["_allowed_l8"] = (
        dg["_allowed"].shift(1).groupby([dvp["def_team"], dvp["position"]], sort=False)
        .rolling(8, min_periods=4).mean().reset_index(level=[0, 1], drop=True)
    )
    league = (
        dvp.groupby(["gw", "position"], as_index=False)["_allowed_l8"].mean()
        .rename(columns={"_allowed_l8": "_league_l8"})
    )
    dvp = dvp.merge(league, on=["gw", "position"], how="left")
    dvp["opponent_matchup__dvp_ppr_index_l8"] = dvp["_allowed_l8"] / dvp["_league_l8"]
    dall = (
        dvp.groupby(["def_team", "gw"], as_index=False)["_allowed_l8"].sum()
        .rename(columns={"_allowed_l8": "opponent_matchup__def_ppr_allowed_l8"})
    )
    f = f.merge(
        dvp[["season", "week", "def_team", "position", "opponent_matchup__dvp_ppr_index_l8"]]
        .rename(columns={"def_team": "opponent"}),
        on=["season", "week", "opponent", "position"], how="left",
    )
    f = f.merge(
        dall.rename(columns={"def_team": "opponent"}).merge(gw_map, on="gw")[
            ["season", "week", "opponent", "opponent_matchup__def_ppr_allowed_l8"]
        ],
        on=["season", "week", "opponent"], how="left",
    )

    # ── prior-season priors (unconditional PPG over rostered team games ex-bye) ──
    season_tot = (
        f.groupby(["gsis_id", "season"], as_index=False)
        .agg(_yr_pts=("fantasy_points", "sum"), _yr_games=("_is_game_row", "sum"))
    )
    season_tot["_prior_season"] = season_tot["season"] + 1
    prior = (
        season_tot.drop(columns="season")
        .rename(columns={"_prior_season": "season"})[["gsis_id", "season", "_yr_pts", "_yr_games"]]
    )
    f = f.merge(prior, on=["gsis_id", "season"], how="left")
    f["prior_season_priors__games_prior"] = f["_yr_games"]
    f["prior_season_priors__ppg_prior"] = f["_yr_pts"] / f["_yr_games"].replace(0, np.nan)
    f["prior_season_priors__rookie_flag"] = f["_yr_games"].isna().astype(float)

    # ── game context ──
    f["game_context__is_home"] = pd.to_numeric(f["is_home"], errors="coerce")
    f["game_context__div_game"] = pd.to_numeric(f["div_game"], errors="coerce")
    f["game_context__week_index"] = f["week"].astype(float)
    f["game_context__days_since_last_game"] = pd.to_numeric(
        f["days_since_last_game"], errors="coerce"
    )

    # ── per-week PIT metadata: the as-of window end + the target kickoff day ──
    sched = schedule.copy()
    sched["gameday"] = pd.to_datetime(sched["gameday"])
    sched = sched.merge(gw_map, on=["season", "week"], how="left").sort_values("gw")
    week_max = sched.groupby("gw")["gameday"].max().sort_index()
    prior_max = week_max.cummax().shift(1)  # max gameday over ALL strictly-prior global weeks
    week_min = sched.groupby("gw")["gameday"].min().sort_index()
    meta = pd.DataFrame({
        "gw": week_max.index,
        "_window_end_day": prior_max.values,
        "_projection_day": week_min.values,
    })
    f = f.merge(meta, on="gw", how="left")
    f["_window_end_day"] = f["_window_end_day"].fillna(f["_projection_day"] - pd.Timedelta(days=7))
    f["_target_gameday"] = f["gameday"]

    return f.reset_index(drop=True)


# ── The PIT gate (NF-W0a leakage guard — invoked, not just imported) ────────────────────────────
def pit_guard_records(week_rows: pd.DataFrame) -> list[dict]:
    """One §13 guard record per assembled player-week row.

    Stamps are the window-end as-of instant: the day AFTER the last strictly-prior game's gameday
    (a played game's facts exist once the game is over; +1 day bounds a Monday-night finish).
    `source_timestamp` is declared absent — the nflverse weekly release files carry no per-row
    as-of stamp (the injuries.date_modified class, NF-W0 finding #2).
    """
    window_end_s = (
        (pd.to_datetime(week_rows["_window_end_day"]) + timedelta(days=1))
        .dt.strftime("%Y-%m-%dT00:00:00+00:00").to_numpy()
    )
    target_s = (
        pd.to_datetime(week_rows["_target_gameday"])
        .dt.strftime("%Y-%m-%dT00:00:00+00:00").to_numpy()
    )
    records: list[dict] = []
    for season, week, gsis, pos, window_end, target in zip(
        week_rows["season"].to_numpy(), week_rows["week"].to_numpy(),
        week_rows["gsis_id"].to_numpy(), week_rows["position"].to_numpy(),
        window_end_s, target_s,
    ):
        payload = f"{season}|{week}|{gsis}|{pos}"
        records.append({
            "capture_source": "nflverse_lake_weekly",
            "capture_id": payload,
            "subject_key": payload,
            "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "record_tier": "lake_feature",
            "feature_timestamp": window_end,
            "source_timestamp": None,
            "source_timestamp_absent_reason": (
                "nflverse weekly release carries no per-row as-of stamp "
                "(date_modified deleted upstream 2025); stamps are the window-end as-of instant"
            ),
            "capture_timestamp": window_end,
            "vendor_release_timestamp": window_end,
            "ingestion_timestamp": window_end,
            "is_rolling_window": True,
            "window_end_timestamp": window_end,
            "target_game_timestamp": target,
        })
    return records


def run_pit_gate(feat: pd.DataFrame, *, guard=LG.assert_point_in_time) -> dict:
    """FAIL-CLOSED per-week PIT gate over the modeled rows. Returns the audit dict.

    A (season, week) whose records the guard REJECTS is DROPPED from the modeled population and
    counted — the 2020 rescheduling shape (a prior-week game played after this week's first
    kickoff) is genuinely un-knowable and fail-closed means refusing those rows, not warning.
    Every retained week has passed `assert_point_in_time` (checked > 0 — never vacuous).
    """
    if PIT_STORE_SOURCES_CONSUMED:
        raise NotImplementedError(
            "PIT_STORE_SOURCES_CONSUMED is non-empty — build a real store_index via "
            "pit.store.build_store_index per source before running this gate; an empty index "
            "would launder revised captures as originals (NF1.7 (a))."
        )
    modeled = feat[feat["label"] != WF.LABEL_BYE]
    dropped: list[dict] = []
    kept_idx: list[np.ndarray] = []
    weeks_checked = records_checked = 0
    for (season, week), rows in modeled.groupby(["season", "week"], sort=True):
        projection_ts = rows["_projection_day"].iloc[0].strftime("%Y-%m-%dT00:00:00+00:00")
        records = pit_guard_records(rows)
        weeks_checked += 1
        records_checked += len(records)
        try:
            report = guard(records, projection_ts, store_index={})
            if getattr(report, "checked", len(records)) == 0:
                raise LG.LeakageRejection([LG.LeakageFinding(
                    LG.Rejection.UNEVALUABLE, "guard checked zero records", None)])
            kept_idx.append(rows.index.to_numpy())
        except LG.LeakageRejection as exc:
            dropped.append({
                "season": int(season), "week": int(week), "n_rows": int(len(rows)),
                "reasons": sorted({fnd.reason.name for fnd in exc.findings}),
            })
    kept = np.concatenate(kept_idx) if kept_idx else np.array([], dtype=int)
    return {
        "weeks_checked": weeks_checked,
        "records_checked": records_checked,
        "weeks_dropped": dropped,
        "rows_dropped": int(sum(d["n_rows"] for d in dropped)),
        "kept_index": kept,
    }


def assemble_matrix(
    frame: pd.DataFrame,
    stats: pd.DataFrame,
    snaps: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    guard=LG.assert_point_in_time,
) -> tuple[pd.DataFrame, dict]:
    """THE feature-assembly boundary: engineer → provenance check → PIT gate. Returns
    (modeled matrix ex-bye, pit_audit). This is the only sanctioned path to a fit/score matrix."""
    feat = engineer_features(frame, stats, snaps, schedule)
    assert_feature_provenance(FEATURES)
    audit = run_pit_gate(feat, guard=guard)
    modeled = feat.loc[audit["kept_index"]].reset_index(drop=True)
    audit = {k: v for k, v in audit.items() if k != "kept_index"}
    return modeled, audit


# ── Folds (purged expanding-window over weeks) ──────────────────────────────────────────────────
@dataclass(frozen=True)
class Fold:
    label: str
    train_idx: np.ndarray
    test_idx: np.ndarray
    test_season: int
    test_half: int


def build_folds(feat: pd.DataFrame) -> list[Fold]:
    """Expanding-window folds: test = a half-season block of weeks; train = every modeled row at
    least PURGE_WEEKS global weeks before the block's first week. Train is strictly earlier — no
    future rows ever, the purge is belt-and-braces against week-adjacent autocorrelation."""
    folds: list[Fold] = []
    for season, half in TEST_BLOCKS:
        in_half = (feat["season"] == season) & (
            feat["week"].isin(H1_WEEKS) if half == 1 else ~feat["week"].isin(H1_WEEKS)
        )
        test_idx = feat.index[in_half].to_numpy()
        if not len(test_idx):
            continue
        start_gw = int(feat.loc[test_idx, "gw"].min())
        train_idx = feat.index[feat["gw"] <= start_gw - 1 - PURGE_WEEKS].to_numpy()
        folds.append(Fold(f"{season}H{half}", train_idx, test_idx, season, half))
    return folds


# ── CRPS + predictive-representation helpers ────────────────────────────────────────────────────
def crps_from_quantiles(qmat: np.ndarray, y: np.ndarray, levels: np.ndarray = Q_LEVELS) -> np.ndarray:
    """CRPS via the 2×mean-pinball identity over a fixed quantile grid — one metric, every arm.

    Exact for the grid-quantized predictive; identical treatment across arms is what makes the
    comparison fair. Handles the zero atom naturally (many grid quantiles equal 0)."""
    q = np.sort(np.asarray(qmat, dtype=float), axis=1)  # monotone rearrangement, uniformly applied
    yv = np.asarray(y, dtype=float)[:, None]
    lv = np.asarray(levels, dtype=float)[None, :]
    diff = yv - q
    pinball = np.maximum(lv * diff, (lv - 1.0) * diff)
    return 2.0 * pinball.mean(axis=1)


def interp_to_levels(knot_levels: np.ndarray, knot_values: np.ndarray,
                     levels: np.ndarray = Q_LEVELS) -> np.ndarray:
    """Interpolate a 9-knot quantile function onto the 39 evaluation levels (linear in level space,
    end knots extended flat — a conservative tail)."""
    kl = np.asarray(knot_levels, dtype=float)
    kv = np.sort(np.asarray(knot_values, dtype=float), axis=1)
    out = np.empty((kv.shape[0], len(levels)))
    for i in range(kv.shape[0]):
        out[i] = np.interp(levels, kl, kv[i])
    return out


def residual_bank(train_y: np.ndarray, train_point: np.ndarray, train_pos: np.ndarray,
                  levels: np.ndarray = Q_LEVELS) -> dict[str, np.ndarray]:
    """Per-position empirical residual quantiles — the additive distributional wrapper for any
    point-only arm (foils, enet). Fit on TRAIN only."""
    res = np.asarray(train_y, float) - np.asarray(train_point, float)
    bank: dict[str, np.ndarray] = {}
    for p in POSITIONS:
        sel = np.asarray(train_pos) == p
        r = res[sel]
        r = r[np.isfinite(r)]
        bank[p] = (np.quantile(r, levels) if len(r) >= 50
                   else np.quantile(res[np.isfinite(res)], levels))
    return bank


def apply_bank(point: np.ndarray, pos: np.ndarray, bank: dict[str, np.ndarray]) -> np.ndarray:
    out = np.empty((len(point), len(Q_LEVELS)))
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        if sel.any():
            out[sel] = np.asarray(point, float)[sel][:, None] + bank[p][None, :]
    return out


# ── Foil (the honest weekly null: season ÷ games + matchup) ─────────────────────────────────────
def foil_point(df: pd.DataFrame, pos_mean_ppg: dict[str, float], *, matchup: bool) -> np.ndarray:
    """EB-shrunk unconditional PPG, optionally spread by the clipped DVP multiplier."""
    prior_pts = pd.to_numeric(df["prior_season_priors__ppg_prior"], errors="coerce") * pd.to_numeric(
        df["prior_season_priors__games_prior"], errors="coerce"
    )
    prior_g = pd.to_numeric(df["prior_season_priors__games_prior"], errors="coerce").fillna(0.0)
    s2d_pts = pd.to_numeric(df["prior_week_box__ppr_sum_s2d"], errors="coerce").fillna(0.0)
    s2d_g = pd.to_numeric(df["prior_week_box__games_s2d"], errors="coerce").fillna(0.0)
    pos_mean = df["position"].map(pos_mean_ppg).astype(float)
    point = (prior_pts.fillna(0.0) + s2d_pts + EB_KAPPA * pos_mean) / (
        prior_g + s2d_g + EB_KAPPA
    )
    if matchup:
        mult = pd.to_numeric(df["opponent_matchup__dvp_ppr_index_l8"], errors="coerce").fillna(1.0)
        point = point * mult.clip(*DVP_CLIP)
    return point.to_numpy(dtype=float)


def train_pos_mean_ppg(train: pd.DataFrame) -> dict[str, float]:
    out = {}
    for p in POSITIONS:
        sel = train["position"] == p
        out[p] = float(train.loc[sel, "fantasy_points"].mean()) if sel.any() else 0.0
    return out


# ── Model-internal imputation (a device inside an arm, never a data edit) ───────────────────────
class _Imputer:
    """Median imputation fit on TRAIN only, with the presence pattern already carried by the
    engineered observed-flags. ⛔ Deliberately NOT zero-fill: 0 is a legal value of most features."""

    def __init__(self, features: list[str]):
        self.features = features
        self.medians: dict[str, float] = {}

    def fit(self, df: pd.DataFrame) -> "_Imputer":
        for c in self.features:
            med = pd.to_numeric(df[c], errors="coerce").median()
            self.medians[c] = float(med) if np.isfinite(med) else 0.0
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        X = np.column_stack([
            pd.to_numeric(df[c], errors="coerce").fillna(self.medians[c]).to_numpy(dtype=float)
            for c in self.features
        ])
        return X


def _pos_codes(df: pd.DataFrame) -> np.ndarray:
    return df["position"].map({p: i for i, p in enumerate(POSITIONS)}).to_numpy(dtype=float)


# ── Arms (each returns an [n_test, 39] quantile matrix) ─────────────────────────────────────────
def _lgbm(params: dict | None = None, **kw):
    import lightgbm as lgb
    base = dict(
        n_estimators=250, learning_rate=0.06, num_leaves=63, min_child_samples=40,
        subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
        random_state=_SEED, verbose=-1, n_jobs=-1,
    )
    base.update(params or {})
    base.update(kw)
    return lgb.LGBMRegressor(**base)


def fit_lgbm_quantile(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                      *, y_train: np.ndarray | None = None) -> np.ndarray:
    """Pooled GBM quantile bank (position is a feature), 9 knots → 39 levels."""
    Xtr = train[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    Xte = test[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    Xtr = np.column_stack([Xtr, _pos_codes(train)])
    Xte = np.column_stack([Xte, _pos_codes(test)])
    y = train["fantasy_points"].to_numpy(dtype=float) if y_train is None else y_train
    knots = np.empty((len(test), len(FIT_LEVELS)))
    for j, alpha in enumerate(FIT_LEVELS):
        m = _lgbm({"objective": "quantile", "alpha": alpha})
        m.fit(Xtr, y)
        knots[:, j] = m.predict(Xte)
    return interp_to_levels(np.array(FIT_LEVELS), knots)


def fit_lgbm_hurdle(train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Two-part mixture: P(zero) classifier × conditional-on-nonzero quantile bank, numerically
    inverted so the zero atom sits at its fitted mass."""
    import lightgbm as lgb
    Xtr = train[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    Xte = test[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    Xtr = np.column_stack([Xtr, _pos_codes(train)])
    Xte = np.column_stack([Xte, _pos_codes(test)])
    y = train["fantasy_points"].to_numpy(dtype=float)
    is_zero = (y == 0.0).astype(int)
    clf = lgb.LGBMClassifier(
        n_estimators=250, learning_rate=0.06, num_leaves=63, min_child_samples=40,
        subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
        random_state=_SEED, verbose=-1, n_jobs=-1,
    )
    clf.fit(Xtr, is_zero)
    p0 = clf.predict_proba(Xte)[:, 1]

    nz = y != 0.0
    knots = np.empty((len(test), len(FIT_LEVELS)))
    for j, alpha in enumerate(FIT_LEVELS):
        m = _lgbm({"objective": "quantile", "alpha": alpha})
        m.fit(Xtr[nz], y[nz])
        knots[:, j] = m.predict(Xte)
    cond = interp_to_levels(np.array(FIT_LEVELS), knots)

    out = np.empty((len(test), len(Q_LEVELS)))
    for i in range(len(test)):
        out[i] = _mixture_quantiles(p0[i], np.sort(cond[i]))
    return out


def _mixture_quantiles(p0: float, cond_q: np.ndarray, levels: np.ndarray = Q_LEVELS) -> np.ndarray:
    """Quantile function of `p0·δ0 + (1−p0)·F_cond`, where F_cond is the 39-level conditional
    quantile vector (which may include negative values — PPR can go negative)."""
    neg_mass = (1.0 - p0) * float((cond_q < 0.0).mean())  # F(0⁻) of the mixture
    out = np.empty(len(levels))
    for k, q in enumerate(levels):
        if q <= neg_mass:
            # inside the conditional's negative tail
            out[k] = np.interp(q / max(1.0 - p0, 1e-9), Q_LEVELS, cond_q)
        elif q <= neg_mass + p0:
            out[k] = 0.0
        else:
            out[k] = np.interp((q - p0) / max(1.0 - p0, 1e-9), Q_LEVELS, cond_q)
    return np.maximum.accumulate(out)


def fit_enet_residual(train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Linear class: ElasticNet mean (standardized, median-imputed) + per-position empirical
    residual quantiles. Distribution comes from the residual bank, not a Normal assumption."""
    from sklearn.linear_model import ElasticNet
    from sklearn.preprocessing import StandardScaler
    imp = _Imputer(list(features)).fit(train)
    Xtr, Xte = imp.transform(train), imp.transform(test)
    sc = StandardScaler().fit(Xtr)
    m = ElasticNet(alpha=0.03, l1_ratio=0.3, random_state=_SEED, max_iter=5000)
    m.fit(sc.transform(Xtr), train["fantasy_points"].to_numpy(dtype=float))
    point_tr = m.predict(sc.transform(Xtr))
    point_te = m.predict(sc.transform(Xte))
    bank = residual_bank(train["fantasy_points"].to_numpy(float), point_tr,
                         train["position"].to_numpy())
    return apply_bank(point_te, test["position"].to_numpy(), bank)


def fit_knn_quantile(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                     *, k: int = 300) -> np.ndarray:
    """Neighborhood class (the NF1.9 veteran-band winner's shape): per-position standardized kNN,
    empirical quantiles of the neighbors' realized points."""
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    out = np.empty((len(test), len(Q_LEVELS)))
    imp = _Imputer(list(features)).fit(train)
    for p in POSITIONS:
        tr_sel = (train["position"] == p).to_numpy()
        te_sel = (test["position"] == p).to_numpy()
        if not te_sel.any():
            continue
        Xtr = imp.transform(train.loc[tr_sel])
        Xte = imp.transform(test.loc[te_sel])
        sc = StandardScaler().fit(Xtr)
        kk = min(k, max(2, tr_sel.sum() - 1))
        nn = NearestNeighbors(n_neighbors=kk).fit(sc.transform(Xtr))
        _, idx = nn.kneighbors(sc.transform(Xte))
        ytr = train.loc[tr_sel, "fantasy_points"].to_numpy(dtype=float)
        out[te_sel] = np.quantile(ytr[idx], Q_LEVELS, axis=1).T
    return out


# ── Anchors (diagnostic — never trials) ─────────────────────────────────────────────────────────
def anchor_nihilist(test: pd.DataFrame) -> np.ndarray:
    """The degenerate all-zero ceiling — MEASURED every run, never reasoned about (NF-D14)."""
    return np.zeros((len(test), len(Q_LEVELS)))


def anchor_pos_marginal(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Train climatology per position — the 'all_mean' analog; conditioning must beat it."""
    out = np.empty((len(test), len(Q_LEVELS)))
    for p in POSITIONS:
        tr, te = (train["position"] == p).to_numpy(), (test["position"] == p).to_numpy()
        if te.any():
            src = train.loc[tr, "fantasy_points"] if tr.any() else train["fantasy_points"]
            out[te] = np.quantile(src.to_numpy(dtype=float), Q_LEVELS)[None, :]
    return out


def anchor_oracle_marginal(test: pd.DataFrame) -> np.ndarray:
    """PEEKING per-position marginal fit ON the test block — the ceiling of marginal information.
    A conditional arm may legitimately beat it (capacity, NF1.9 (f)); reported, never a veto."""
    out = np.empty((len(test), len(Q_LEVELS)))
    for p in POSITIONS:
        te = (test["position"] == p).to_numpy()
        if te.any():
            out[te] = np.quantile(test.loc[te, "fantasy_points"].to_numpy(dtype=float),
                                  Q_LEVELS)[None, :]
    return out


def permute_within_pos_week(train: pd.DataFrame, seed: int = _SEED) -> np.ndarray:
    """Labels shuffled WITHIN (position, global-week) — destroys player identity/usage signal while
    preserving every marginal a week×position slice has. The permuted arm must LOSE."""
    rng = np.random.default_rng(seed)
    y = train["fantasy_points"].to_numpy(dtype=float).copy()
    keys = train["position"].astype(str) + "|" + train["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(train)), index=keys).groupby(level=0):
        pos = idx.to_numpy()
        if len(pos) > 1:
            y[pos] = rng.permutation(y[pos])
    return y


def anchor_zero_width(point: np.ndarray) -> np.ndarray:
    """Maximally sharp: a point mass at the foil's point (CRPS degenerates to MAE)."""
    return np.repeat(np.asarray(point, float)[:, None], len(Q_LEVELS), axis=1)


def anchor_max_width(point: np.ndarray, pos: np.ndarray, bank: dict[str, np.ndarray],
                     scale: float = 3.0) -> np.ndarray:
    """Maximally wide: the foil's residual bank inflated ×3 — satisfies every coverage floor and
    must still LOSE CRPS (the NF1.8 proof that the floor is a constraint, not a criterion)."""
    wide = {p: v * scale for p, v in bank.items()}
    return apply_bank(point, pos, wide)


# ── Interval / coverage reporting (floor discipline) ────────────────────────────────────────────
def interval_coverage(qmat: np.ndarray, y: np.ndarray,
                      lo: float = INTERVAL_LO, hi: float = INTERVAL_HI) -> dict:
    q = np.sort(np.asarray(qmat, float), axis=1)
    li = int(np.argmin(np.abs(Q_LEVELS - lo)))
    hi_i = int(np.argmin(np.abs(Q_LEVELS - hi)))
    yv = np.asarray(y, float)
    inside = (yv >= q[:, li]) & (yv <= q[:, hi_i])
    n = len(yv)
    cov = float(inside.mean()) if n else float("nan")
    nominal = hi - lo
    se = float(np.sqrt(nominal * (1 - nominal) / n)) if n else float("nan")
    return {"coverage": cov, "n": n, "nominal": nominal, "binomial_se": se,
            "blocking_shortfall": bool(n and (nominal - cov) > COVERAGE_BLOCK_SE * se)}


# ── ROS aggregation (Σ remaining weekly projections) ────────────────────────────────────────────
def ros_projection(weekly: pd.DataFrame) -> pd.DataFrame:
    """Rest-of-season = Σ remaining weekly projections per player.

    `weekly` carries one row per (gsis_id, position, week) with `mean` and `q16`/`q84` (or any
    symmetric-ish central band) from the weekly predictive. Point = Σ means (a bye week simply
    contributes its identity 0 row or is absent). Interval = Normal approximation with
    σ_ros = sqrt(Σ σ_w²), σ_w = (q84 − q16)/2 — a DECLARED independence approximation, honest for
    ranking-scale use; week-to-week dependence (injury persistence) makes true tails wider."""
    need = {"gsis_id", "position", "week", "mean", "q16", "q84"}
    if missing := need - set(weekly.columns):
        raise ValueError(f"weekly projection frame missing {sorted(missing)}")
    w = weekly.copy()
    w["_sigma"] = (pd.to_numeric(w["q84"], errors="coerce")
                   - pd.to_numeric(w["q16"], errors="coerce")).clip(lower=0.0) / 2.0
    g = w.groupby(["gsis_id", "position"], as_index=False)
    out = g.agg(ros_mean=("mean", "sum"), _var=("_sigma", lambda s: float((s ** 2).sum())),
                n_weeks=("week", "nunique"))
    z90 = 1.2815515655446004
    sig = np.sqrt(out["_var"].to_numpy(dtype=float))
    out["ros_q10"] = out["ros_mean"] - z90 * sig
    out["ros_q90"] = out["ros_mean"] + z90 * sig
    return out.drop(columns="_var")


# ── Component head (raw lines — any league's scoring can re-score them) ─────────────────────────
def fit_component_head(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                       components: tuple[str, ...] = COMPONENTS) -> pd.DataFrame:
    """Per-component pooled LGBM means over the SAME feature set — advisory raw lines beside the
    gated points distribution (never themselves gated in this slice)."""
    Xtr = train[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    Xte = test[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    Xtr = np.column_stack([Xtr, _pos_codes(train)])
    Xte = np.column_stack([Xte, _pos_codes(test)])
    out = pd.DataFrame({
        "gsis_id": test["gsis_id"].to_numpy(),
        "season": test["season"].to_numpy(),
        "week": test["week"].to_numpy(),
        "position": test["position"].to_numpy(),
    })
    for comp in components:
        if comp not in train.columns:
            continue
        y = pd.to_numeric(train[comp], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        m = _lgbm({"objective": "regression", "n_estimators": 200})
        m.fit(Xtr, y)
        out[f"proj_{comp}"] = np.clip(m.predict(Xte), 0.0, None)
    return out


# ── Gate plumbing shared with the runner ────────────────────────────────────────────────────────
def matrix_key(seasons: tuple[int, int], feature_names: tuple[str, ...] = FEATURES) -> str:
    """Cache key for the assembled matrix — a SHA over the things that change its CONTENT
    (NF-C0e: a cache keyed on params but not the query serves a stale column set)."""
    payload = json.dumps({
        "seasons": seasons, "features": list(feature_names), "label_version": LABEL_VERSION,
        "scoring": SCORING_SYSTEM_ID, "positions": list(POSITIONS), "schema": 1,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
