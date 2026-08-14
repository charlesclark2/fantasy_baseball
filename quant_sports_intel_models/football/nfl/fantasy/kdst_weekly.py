"""kdst_weekly.py — NF-W7: weekly KICKER + TEAM-DEFENSE (DST) distributional projections (pure).

THE STORY IN ONE PARAGRAPH. The NF-W1 champion is skill-positions only (QB/RB/WR/TE), so a
fantasy team's K and DST slots are UNPROJECTED today — this is the first new-target weekly story,
not a re-model of a covered one. The thesis (tested, not assumed): weekly K/DST value is largely
OPPORTUNITY — teams that score or stall in the red zone / inside the 30 generate FG attempts; DST
output tracks opponent quality, script and pace. That is a real reason a component decomposition
(§4A: drives → FG opportunities → distance band → make probability → XP → league scoring; DST
counting components + EXACT TIER SCORING as expected-bucket probabilities) could beat a direct
points model here, unlike the skill positions where NF-W3/W4/W5 measured the opportunity channels
inert. It must EARN that against an honest K+DST climatology null AND a direct-learned points
foil, OOS — a null is a legitimate published outcome, with the null model standing.

⭐ THE CORE DISCIPLINE — EXACT TIER SCORING. Points-allowed and yards-allowed scoring are STEP
functions. ⛔ Never project a point estimate and pass it through a tier table: the bucket
probabilities P(B_PA = b | X) and P(B_YA = b | X) are modeled directly (ordered logit /
multinomial / a full count distribution integrated over the bucket boundaries) and the exact
league table is applied per bucket. The bucket edges are NF1.6's nine-bucket common refinements
(`kdst_projection.PA_BUCKET_EDGES` / `YA_BUCKET_EDGES`), so ESPN and Yahoo schemes are exact
unions and any league rescoring stays linear in the emitted probabilities.

Everything decidable in advance is a CONSTANT here; the runner READS it (NF-D16). The narrative
pre-registration is committed at `ablation_results/nf_w7_preregistration.md` BEFORE the full run.

NF-W0 CONSTRAINTS, honored mechanically:
  (1) certified families only — game_context / team_environment / opponent_matchup /
      prior_week_box; unknown provenance REJECTS the build (`assert_feature_provenance_w7`).
      ⚠️ CONTRACT FINDING (recorded, not silently absorbed): the `prior_week_box` spec prose
      enumerates offensive-skill columns; the KICKING block lives in the SAME certified source
      (`stats_player_week`, lagged, postgame, retrospective) with identical PIT semantics. Read
      as covered; flagged as a contract-doc wording gap in the report.
  (2) ⛔ NO pbp_participation legs at all — the NF-W0c 2023 era boundary honored by EXCLUSION
      (`ERA_FORBIDDEN_TOKENS` verbatim); the capture-era (2025) fold read is REPORT-ONLY (W2d).
  (3) `assert_point_in_time` INVOKED per (season, week) on every frame, fail-closed.
  (4) ⛔ no `fillna(0)` — a missing lagged window is NaN; learners that cannot pass NaN use
      TRAIN-fitted MEDIAN imputation as a device inside the arm.
  (5) ⛔ no markets / WEATHER / depth-chart rank / game-day inactive status. ⚠️ Weather is
      genuinely predictive for KICKING and is exactly what the opportunity thesis tempts toward —
      it is BANNED as a historical feature (it enters only via the NF-W0a forward capture once it
      accrues). `game_context__roofed_stadium` is the STRUCTURAL stadium attribute
      (roof ∈ {dome, closed, open} — "the stadium has a roof"), never the realized game-day
      open/closed state. Enforced by the banned-source token scan on every aggregation SQL
      (comments stripped — INC-38) and on every feature name.

⭐ TAIL DISCIPLINE (NF-MARGIN1, inherited from day one): everything is scored on the DENSE
199-level grid (`crps_q199`); parametric count arms emit exact integer-support banks (real tails
by construction); 9-knot quantile learners are extended with the exponential mean-excess tail
model, ⛔ never flat-extended; assembly banks come from S=4000 MC draws.

⚖️ EDGE-INDEPENDENT (best_alpha N/A) · DEPLOY-HELD: this module promotes nothing, publishes
nothing, retrains nothing; serving is the weekly path / NF-C6, an operator decision.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import kdst_projection as KP
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W7"
SELECTION_METRIC = "crps_q199"                  # NF-MARGIN1: the dense grid, never the 39-level
EVAL_LEVELS = MC.EVAL_LEVELS                    # 199 levels
FIT_LEVELS = WP.FIT_LEVELS                      # the 9 knot levels quantile learners fit
TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
SEASONS: tuple[int, int] = (2016, 2025)
_SEED = 20260813

#: Monte-Carlo draws per row for the assembled fantasy-point banks.
ASSEMBLY_DRAWS = 4000
#: Integer support ceiling for count predictives (weekly K/DST counts never approach this).
COUNT_SUPPORT = 30
#: EB shrinkage, in entity-GAMES, for the entity-EB count foils / rare-leg EB arms.
EB_KAPPA_GAMES = 8.0
#: EB shrinkage, in ATTEMPTS, for kicker make-rate / band-mix priors.
EB_KAPPA_ATT = 50.0
EB_KAPPA_BAND = 12.0
#: The 2025 folds — the capture-era read is REPORT-ONLY (NF-W2d).
CAPTURE_ERA_SEASON = 2025

#: The three league scoring bands (exact kick distance is retained upstream; these are applied at
#: scoring time only). Representative per-band distances for assembly are fit IN-FOLD from train.
BANDS: tuple[str, ...] = ("b0_39", "b40_49", "b50p")
BAND_EDGES = (0.0, 40.0, 50.0)                  # inclusive lower bounds
BAND_POINTS = (3.0, 4.0, 5.0)                   # the modal default (NF1.6 K_CONVENIENCE_SCORING)

#: Exact-tier tables — NF1.6's nine-bucket refinements, reused verbatim.
PA_EDGES, PA_LABELS = KP.PA_BUCKET_EDGES, KP.PA_BUCKET_LABELS
YA_EDGES, YA_LABELS = KP.YA_BUCKET_EDGES, KP.YA_BUCKET_LABELS
PA_TIER_POINTS = tuple(KP.DST_PA_TIER_POINTS[b] for b in PA_LABELS)
#: The modal-default DST linear terms (ESPN default; NF1.6 DST_CONVENIENCE_SCORING).
DST_LINEAR_POINTS = {"def_sacks": 1.0, "def_int": 2.0, "def_fumble_rec": 2.0,
                     "dst_td": 6.0, "def_safety": 2.0, "def_blocked_kick": 2.0}

# ── The declared Layer-A field ──────────────────────────────────────────────────────────────────
COUNT_LEGS: tuple[str, ...] = ("fg_att", "xp_att", "def_sacks", "def_int", "def_fumble_rec")
RARE_LEGS: tuple[str, ...] = ("dst_td", "def_safety", "def_blocked_kick")
BUCKET_LEGS: tuple[str, ...] = ("pa_bucket", "ya_bucket")
ATTEMPT_LEGS: tuple[str, ...] = ("fg_make", "fg_band")
ALL_LEGS: tuple[str, ...] = (*COUNT_LEGS, *ATTEMPT_LEGS, *RARE_LEGS, *BUCKET_LEGS)

REAL_ARMS: dict[str, tuple[str, ...]] = {
    **{t: ("pois_glm", "negbin_glm", "lgbm_quantile") for t in COUNT_LEGS},
    **{t: ("eb_pois", "hurdle_pois") for t in RARE_LEGS},
    "fg_make": ("eb_kicker_curve", "logit_distance_glm", "lgbm_classifier"),
    "fg_band": ("mnlogit", "eb_dirichlet_kicker", "lgbm_multiclass"),
    "pa_bucket": ("ordered_logit", "mnlogit", "negbin_integrated"),
    "ya_bucket": ("ordered_logit", "mnlogit", "gauss_integrated"),
}
FOILS: dict[str, tuple[str, ...]] = {
    **{t: ("foil_climatology", "foil_entity_eb") for t in COUNT_LEGS},
    **{t: ("foil_climatology", "foil_league_rate") for t in RARE_LEGS},
    "fg_make": ("foil_league_curve", "foil_constant_rate"),
    "fg_band": ("foil_league_mix",),
    "pa_bucket": ("foil_climatology", "foil_entity_eb"),
    "ya_bucket": ("foil_climatology", "foil_entity_eb"),
}
#: The proper score per leg — CRPS for real-valued banks, log-loss / RPS for categorical legs.
LEG_METRIC: dict[str, str] = {
    **{t: "crps_q199" for t in (*COUNT_LEGS, *RARE_LEGS)},
    "fg_make": "log_loss", "fg_band": "log_loss_multiclass",
    "pa_bucket": "rps", "ya_bucket": "rps",
}
#: The permuted control's estimator family per leg — fixed BEFORE any score is seen.
PERMUTED_FAMILY: dict[str, str] = {
    **{t: "lgbm_quantile" for t in COUNT_LEGS},
    **{t: "eb_pois" for t in RARE_LEGS},
    "fg_make": "logit_distance_glm", "fg_band": "mnlogit",
    "pa_bucket": "mnlogit", "ya_bucket": "mnlogit",
}

# ── Layer B ─────────────────────────────────────────────────────────────────────────────────────
LAYER_B_TARGETS: tuple[str, ...] = ("k_points", "dst_points")
LAYER_B_REAL_ARMS: tuple[str, ...] = ("assembled",)
LAYER_B_FOILS: tuple[str, ...] = ("foil_climatology", "foil_board_eb", "foil_direct")
LAYER_B_ANCHORS: tuple[str, ...] = (
    "nihilist_zero", "zero_width", "max_width", "permuted_direct",
    "oracle__assembled", "matched_n__assembled",
    "oracle__foil_climatology", "oracle__foil_board_eb", "oracle__foil_direct",
)
#: The eligible field — declared here, never trimmed or grown after a score (MH2 (a)).
LAYER_B_ELIGIBLE: tuple[str, ...] = (*LAYER_B_REAL_ARMS, *LAYER_B_FOILS)

#: ⭐ TWO pre-registered multiplicity families; the STRICTER binds (MH2 (a)).
FDR_FAMILIES: dict[str, tuple[str, ...]] = {
    "component": ALL_LEGS,
    "downstream": LAYER_B_TARGETS,
}

ERA_FORBIDDEN_TOKENS = WP.ERA_FORBIDDEN_TOKENS
BANNED_SOURCE_TOKENS = GE.BANNED_SOURCE_TOKENS  # temp/wind/markets/depth-chart — reused verbatim
USED_FAMILIES: tuple[str, ...] = (
    "game_context", "team_environment", "opponent_matchup", "prior_week_box",
)

# ── Features (all lagged / strictly prior; ⛔ no fillna(0)) ─────────────────────────────────────
FEATURES_K: tuple[str, ...] = (
    "game_context__is_home", "game_context__div_game", "game_context__week_index",
    "game_context__days_since_last_game", "game_context__roofed_stadium",
    # the kicker's own lagged kicking line (the prior_week_box family — see the contract finding)
    "prior_week_box__fg_att_l4", "prior_week_box__fg_att_l8", "prior_week_box__fg_att_ewm",
    "prior_week_box__fg_att_s2d", "prior_week_box__fg_att_prior_season",
    "prior_week_box__pat_att_l4", "prior_week_box__pat_att_l8",
    "prior_week_box__fg_makerate_prior", "prior_week_box__share50_prior",
    "prior_week_box__kicker_games_prior_season",
    # his offense's scoring environment (lagged pbp)
    "team_environment__points_l4", "team_environment__points_l8",
    "team_environment__points_prior_season", "team_environment__drives_l4",
    "team_environment__rz_trips_l4", "team_environment__rz_tdrate_l4",
    "team_environment__fgrange_trips_l4", "team_environment__team_fg_att_l4",
    "team_environment__epa_per_play_l4", "team_environment__games_prior_season",
    # the defense he kicks against (lagged)
    "opponent_matchup__def_points_allowed_l4", "opponent_matchup__def_rz_tdrate_allowed_l4",
    "opponent_matchup__def_fgatt_faced_l4", "opponent_matchup__def_epa_allowed_l4",
    "opponent_matchup__def_drives_faced_l4",
)
FEATURES_D: tuple[str, ...] = (
    "game_context__is_home", "game_context__div_game", "game_context__week_index",
    "game_context__days_since_last_game",
    # own defense, lagged
    "team_environment__sacks_l4", "team_environment__sacks_l8", "team_environment__sacks_ewm",
    "team_environment__qb_hits_l4", "team_environment__tfl_l4",
    "team_environment__int_l4", "team_environment__int_l8", "team_environment__fr_l4",
    "team_environment__takeaways_l8", "team_environment__dsttd_l16",
    "team_environment__safety_l16", "team_environment__block_l16",
    "team_environment__pa_l4", "team_environment__pa_l8", "team_environment__pa_s2d",
    "team_environment__pa_prior_season", "team_environment__ya_l4", "team_environment__ya_l8",
    "team_environment__games_prior_season",
    # the offense faced, lagged
    "opponent_matchup__opp_points_l4", "opponent_matchup__opp_points_l8",
    "opponent_matchup__opp_points_prior_season", "opponent_matchup__opp_sacks_taken_l4",
    "opponent_matchup__opp_sacks_taken_l8", "opponent_matchup__opp_giveaways_l4",
    "opponent_matchup__opp_giveaways_l8", "opponent_matchup__opp_off_yards_l4",
    "opponent_matchup__opp_pass_yards_l4",
)
#: Attempt-grain features. `kick_distance` is the CONDITIONING variable of the make component
#: (P(make | attempt at distance d)) — part of the chain's definition, drawn from the band model
#: at assembly time, never a pregame forecast feature.
FEATURES_MAKE: tuple[str, ...] = (
    "game_context__kick_distance", "game_context__roofed_stadium",
    "prior_week_box__kicker_prior_makerate_eb", "prior_week_box__kicker_prior_att",
)
FEATURES_BAND: tuple[str, ...] = (
    "game_context__roofed_stadium",
    "prior_week_box__kicker_prior_share50_eb", "prior_week_box__kicker_prior_share40_eb",
    "prior_week_box__kicker_prior_att",
)
LEG_FEATURES: dict[str, tuple[str, ...]] = {
    "fg_att": FEATURES_K, "xp_att": FEATURES_K,
    "fg_make": FEATURES_MAKE, "fg_band": FEATURES_BAND,
    **{t: FEATURES_D for t in (*("def_sacks", "def_int", "def_fumble_rec"), *RARE_LEGS,
                               "pa_bucket", "ya_bucket")},
}


def oracle_of(arm: str) -> str:
    return f"oracle__{arm}"


def matched_n_of(arm: str) -> str:
    return f"matched_n__{arm}"


def eligible_labels(leg: str) -> list[str]:
    """The set the selection searched — real arms + foils; anchors NEVER (MH2.1 (a))."""
    return [*REAL_ARMS[leg], *FOILS[leg]]


# ── Provenance + source hygiene ─────────────────────────────────────────────────────────────────
def assert_feature_provenance_w7(feature_columns) -> None:
    """Reject any feature whose provenance is not checkable against the NF-W0 contract.
    Mirrors `GE.assert_feature_provenance_w3` clause-for-clause with this story's family set."""
    cols = list(feature_columns)
    bad = [c for c in cols if "__" not in c or c.split("__", 1)[0] not in USED_FAMILIES]
    if bad:
        raise WF.LeakageError(
            f"features with unknown provenance reject the build: {sorted(bad)} — every NF-W7 "
            f"feature must be named '<family>__<detail>' with family in {USED_FAMILIES}"
        )
    leaky = [c for c in cols
             if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_")
                    for tok in WF.LEAKY_COLUMNS)]
    if leaky:
        raise WF.LeakageError(f"leaky feature columns reject the build: {sorted(leaky)}")
    era = [c for c in cols if any(tok in c for tok in ERA_FORBIDDEN_TOKENS)]
    if era:
        raise WF.LeakageError(
            f"participation-era features reject this build: {sorted(era)} — NF-W0c forbids "
            f"pooling pressure/coverage/route legs across the 2023 provider switch"
        )
    banned = [c for c in cols if any(tok in c for tok in BANNED_SOURCE_TOKENS)]
    if banned:
        raise WF.LeakageError(
            f"deferred-contract features reject this build: {sorted(banned)} — markets, weather, "
            f"depth-chart rank and game-day inactive status are NF-W0 DEFERRED, not allowed"
        )
    WF.assert_no_leakage(pd.DataFrame(),
                         feature_columns=sorted({c.split("__", 1)[0] for c in cols}),
                         projection_week=0)


def assert_source_query_is_clean(sql: str) -> None:
    """The aggregation SQL may not READ a deferred-contract column (markets / realized weather).
    Comment lines are stripped first so prose can neither satisfy nor trip it (INC-38).

    ⚠️ WHY THIS IS NOT `GE.assert_source_query_is_clean` VERBATIM: GE's scan is a raw SUBSTRING
    match, and `'temp' in 'field_goal_attempt'` is TRUE — a kicker story cannot say "attempt"
    without tripping it (measured: the first smoke run died on exactly this). The ban here is
    matched at IDENTIFIER boundaries instead, which still catches `temp`, `wind`,
    `spread_line`, `vegas_wp` … as column reads while not misfiring on legitimate kicking
    columns. The token LIST is GE's, unchanged."""
    import re
    body = "\n".join(ln.split("--", 1)[0] for ln in sql.splitlines()).lower()
    hits = sorted({tok for tok in BANNED_SOURCE_TOKENS
                   if re.search(rf"(?<![a-z0-9_]){re.escape(tok)}(?![a-z0-9_])", body)})
    if hits:
        raise WF.LeakageError(
            f"the NF-W7 aggregation reads deferred-contract columns {hits} — markets and "
            f"realized weather are banned at the SOURCE, not merely as named features"
        )


# ── Team-code hygiene (the measured NF-W3 defect) ───────────────────────────────────────────────
canonicalize_team_codes = GE.canonicalize_team_codes


def assert_no_nan_join_keys(df: pd.DataFrame, columns, context: str) -> None:
    """pandas matches NaN against NaN, so a NaN join key CROSS-JOINS and silently duplicates
    (the NF-W3 measured defect). Refuse before any merge."""
    for c in columns:
        n = int(df[c].isna().sum())
        if n:
            raise WF.LeakageError(
                f"{context}: {n} NaN values in join key `{c}` — a NaN key cross-joins on merge")


# ── Lag helpers (shift(1) BEFORE any window — a window never contains its own target row) ───────
def lagged_mean(df: pd.DataFrame, key: str, col: str, window: int, minp: int = 1) -> pd.Series:
    return (df.groupby(key, sort=False)[col].shift(1)
            .groupby(df[key], sort=False).rolling(window, min_periods=minp).mean()
            .reset_index(level=0, drop=True))


def lagged_ewm(df: pd.DataFrame, key: str, col: str, halflife: float = 3.0) -> pd.Series:
    return (df.groupby(key, sort=False)[col].shift(1)
            .groupby(df[key], sort=False)
            .transform(lambda s: s.ewm(halflife=halflife, min_periods=1).mean()))


def s2d_mean(df: pd.DataFrame, keys: list[str], col: str) -> pd.Series:
    """Season-to-date mean of strictly PRIOR weeks of the same season."""
    g = df.groupby(keys, sort=False)
    csum = g[col].cumsum() - df[col]
    cnt = g[col].cumcount()
    return csum / cnt.replace(0, np.nan)


def prior_cum(df: pd.DataFrame, key: str, col: str) -> pd.Series:
    """Career-to-date SUM of strictly prior rows (per entity)."""
    return df.groupby(key, sort=False)[col].cumsum() - df[col]


# ── PIT gate (NF-W0a — invoked per week, fail-closed; the GE pattern, subject-generic) ──────────
def pit_guard_records(rows: pd.DataFrame, subject_col: str, source: str) -> list[dict]:
    window_end_s = ((pd.to_datetime(rows["_window_end_day"]) + timedelta(days=1))
                    .dt.strftime("%Y-%m-%dT00:00:00+00:00").to_numpy())
    target_s = (pd.to_datetime(rows["_target_gameday"])
                .dt.strftime("%Y-%m-%dT00:00:00+00:00").to_numpy())
    out: list[dict] = []
    for season, week, subj, window_end, target in zip(
        rows["season"].to_numpy(), rows["week"].to_numpy(), rows[subject_col].to_numpy(),
        window_end_s, target_s,
    ):
        payload = f"{season}|{week}|{subj}"
        out.append({
            "capture_source": source,
            "capture_id": payload,
            "subject_key": payload,
            "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "record_tier": "lake_feature",
            "feature_timestamp": window_end,
            "source_timestamp": None,
            "source_timestamp_absent_reason": (
                "nflverse releases carry no per-row as-of stamp; stamps are the window-end as-of "
                "instant (the day after the last strictly-prior game)"),
            "capture_timestamp": window_end,
            "vendor_release_timestamp": window_end,
            "ingestion_timestamp": window_end,
            "is_rolling_window": True,
            "window_end_timestamp": window_end,
            "target_game_timestamp": target,
        })
    return out


def run_pit_gate(df: pd.DataFrame, subject_col: str, source: str, *,
                 guard=LG.assert_point_in_time) -> dict:
    """FAIL-CLOSED per-week PIT gate. A rejected week is DROPPED and counted; a week the guard
    checked ZERO records for is a rejection, never a pass (NF1.7 (a))."""
    dropped: list[dict] = []
    kept: list[np.ndarray] = []
    weeks = records = 0
    for (season, week), rows in df.groupby(["season", "week"], sort=True):
        proj = rows["_projection_day"].iloc[0].strftime("%Y-%m-%dT00:00:00+00:00")
        recs = pit_guard_records(rows, subject_col, source)
        weeks += 1
        records += len(recs)
        try:
            report = guard(recs, proj, store_index={})
            if getattr(report, "checked", len(recs)) == 0:
                raise LG.LeakageRejection([LG.LeakageFinding(
                    LG.Rejection.UNEVALUABLE, "guard checked zero records", None)])
            kept.append(rows.index.to_numpy())
        except LG.LeakageRejection as exc:
            dropped.append({"season": int(season), "week": int(week), "n_rows": int(len(rows)),
                            "reasons": sorted({f.reason.name for f in exc.findings})})
    return {
        "weeks_checked": weeks, "records_checked": records, "weeks_dropped": dropped,
        "rows_dropped": int(sum(d["n_rows"] for d in dropped)),
        "kept_index": np.concatenate(kept) if kept else np.array([], dtype=int),
    }


def attach_week_meta(df: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """gw + the PIT day columns (_window_end_day / _projection_day / _target_gameday)."""
    gw = WP._global_week_index(schedule)
    sched = schedule.copy()
    sched["gameday"] = pd.to_datetime(sched["gameday"])
    sched = sched.merge(gw, on=["season", "week"], how="left").sort_values("gw")
    week_max = sched.groupby("gw")["gameday"].max().sort_index()
    week_min = sched.groupby("gw")["gameday"].min().sort_index()
    meta = pd.DataFrame({"gw": week_max.index,
                         "_window_end_day": week_max.cummax().shift(1).values,
                         "_projection_day": week_min.values})
    out = df.merge(gw, on=["season", "week"], how="left")
    out = out.merge(meta, on="gw", how="left")
    out["_window_end_day"] = out["_window_end_day"].fillna(
        out["_projection_day"] - pd.Timedelta(days=7))
    return out


def matrix_key(name: str, seasons: tuple[int, int], features: tuple[str, ...]) -> str:
    """Cache key over everything that changes the matrix CONTENT (NF-C0e)."""
    return hashlib.sha256(json.dumps({
        "story": STORY, "frame": name, "seasons": seasons, "features": list(features),
        # schema 2: sides canonicalized to CURRENT franchise codes (the era-code join defect)
        "schema": 2,
    }, sort_keys=True).encode()).hexdigest()[:16]


# ── Dense-grid predictive banks ─────────────────────────────────────────────────────────────────
def bank_from_count_cdf(cdf: np.ndarray) -> np.ndarray:
    """(n, S+1) count CDF over support 0..S → the (n, 199) quantile bank. Exact tails by
    construction — the inverse CDF is evaluated at every dense level."""
    cdf = np.asarray(cdf, dtype=float)
    return (cdf[:, :, None] < EVAL_LEVELS[None, None, :]).sum(axis=1).astype(float)


def poisson_bank(mu: np.ndarray, support: int = COUNT_SUPPORT) -> np.ndarray:
    from scipy.stats import poisson
    k = np.arange(support + 1)
    return bank_from_count_cdf(poisson.cdf(k[None, :], np.clip(mu, 1e-9, None)[:, None]))


def nbinom_bank(mu: np.ndarray, alpha: float, support: int = COUNT_SUPPORT) -> np.ndarray:
    from scipy.stats import nbinom
    r = 1.0 / max(alpha, 1e-9)
    mu = np.clip(mu, 1e-9, None)
    p = r / (r + mu)
    k = np.arange(support + 1)
    return bank_from_count_cdf(nbinom.cdf(k[None, :], r, p[:, None]))


def marginal_bank(train_y: np.ndarray, n_rows: int) -> np.ndarray:
    """Climatology: the train marginal at every dense level — the honest null. Empirical at 199
    levels over thousands of rows, so its tails are REAL, not modeled."""
    y = np.asarray(train_y, float)
    y = y[np.isfinite(y)]
    return np.tile(np.quantile(y, EVAL_LEVELS), (n_rows, 1))


def point_plus_residual_bank(point: np.ndarray, train_y: np.ndarray,
                             train_point: np.ndarray, clip_lo: float | None = None) -> np.ndarray:
    """EB point + empirical train residual quantiles at 199 levels (dense-native tails)."""
    r = np.asarray(train_y, float) - np.asarray(train_point, float)
    r = r[np.isfinite(r)]
    bank = np.asarray(point, float)[:, None] + np.quantile(r, EVAL_LEVELS)[None, :]
    return np.clip(bank, clip_lo, None) if clip_lo is not None else bank


def dense_bank_from_knots(knots: np.ndarray, tail: dict, clip_lo: float | None = 0.0) -> np.ndarray:
    """9-knot quantile function → dense 199-level bank with EXPONENTIAL mean-excess tails beyond
    the end knots (⛔ never flat-extended — the NF-MARGIN1 flat-tail defect)."""
    kv = np.sort(np.asarray(knots, dtype=float), axis=1)
    lv = np.asarray(FIT_LEVELS, dtype=float)
    out = np.empty((kv.shape[0], len(EVAL_LEVELS)))
    inner = np.clip(EVAL_LEVELS, lv[0], lv[-1])
    for i in range(kv.shape[0]):
        out[i] = np.interp(inner, lv, kv[i])
    above = EVAL_LEVELS > lv[-1]
    below = EVAL_LEVELS < lv[0]
    if above.any() and tail.get("beta_hi", 0.0) > 0:
        ext = tail["beta_hi"] * np.log((1 - lv[-1]) / (1.0 - EVAL_LEVELS[above]))
        out[:, above] = kv[:, -1][:, None] + ext[None, :]
    if below.any() and tail.get("beta_lo", 0.0) > 0:
        ext = tail["beta_lo"] * np.log(lv[0] / EVAL_LEVELS[below])
        out[:, below] = kv[:, 0][:, None] - ext[None, :]
    return np.clip(out, clip_lo, None) if clip_lo is not None else out


def fit_knot_tail_betas(train_knots: np.ndarray, train_y: np.ndarray) -> dict:
    """Exponential exceedance scales beyond the END KNOTS, fit by mean excess on TRAIN (in-fold,
    causal). A side with < MC.MIN_TAIL_N exceedances gets beta 0 and is COUNTED (the MARGIN1
    convention — degrade to the flat end, loudly countable, never silently)."""
    kv = np.sort(np.asarray(train_knots, dtype=float), axis=1)
    yv = np.asarray(train_y, dtype=float)
    ok = np.isfinite(yv)
    kv, yv = kv[ok], yv[ok]
    q_lo, q_hi = kv[:, 0], kv[:, -1]
    hi_exc = yv[yv > q_hi] - q_hi[yv > q_hi]
    lo_exc = q_lo[yv < q_lo] - yv[yv < q_lo]
    return {"beta_hi": float(np.mean(hi_exc)) if len(hi_exc) >= MC.MIN_TAIL_N else 0.0,
            "beta_lo": float(np.mean(lo_exc)) if len(lo_exc) >= MC.MIN_TAIL_N else 0.0,
            "n_hi": int(len(hi_exc)), "n_lo": int(len(lo_exc)),
            "thin_hi": bool(len(hi_exc) < MC.MIN_TAIL_N),
            "thin_lo": bool(len(lo_exc) < MC.MIN_TAIL_N)}


def crps_dense(bank: np.ndarray, y: np.ndarray) -> np.ndarray:
    return WP.crps_from_quantiles(bank, y, EVAL_LEVELS)


def assert_finite_predictive(mat: np.ndarray, label: str) -> None:
    """A predictive with non-finite cells is scored on a silently different population by any
    nan-aware mean — REFUSED (the NF-W3 measured defect, NF1.7 (a))."""
    bad = int((~np.isfinite(np.asarray(mat, dtype=float))).sum())
    if bad:
        raise ValueError(
            f"arm `{label}` emitted {bad} non-finite cells of {np.size(mat)} — a non-finite "
            f"predictive is a silent partial failure, never a scoreable arm")


def coverage80_dense(bank: np.ndarray, y: np.ndarray) -> dict:
    q = np.sort(np.asarray(bank, float), axis=1)
    li = int(np.argmin(np.abs(EVAL_LEVELS - 0.10)))
    hi = int(np.argmin(np.abs(EVAL_LEVELS - 0.90)))
    yv = np.asarray(y, float)
    inside = (yv >= q[:, li]) & (yv <= q[:, hi])
    n = len(yv)
    cov = float(inside.mean()) if n else float("nan")
    se = float(np.sqrt(0.8 * 0.2 / n)) if n else float("nan")
    return {"coverage": cov, "n": n, "binomial_se": se,
            "blocking_shortfall": bool(n and (COVERAGE_FLOOR - cov) > COVERAGE_BLOCK_SE * se)}


def randomized_pit_from_bank(bank: np.ndarray, y: np.ndarray, seed: int = _SEED) -> np.ndarray:
    """Randomized PIT from a dense quantile bank: u ~ U(F(y−), F(y)) where F is read off the bank
    (ties randomized). Reported as max-decile deviation from flat (E2.1-r) — report-only."""
    rng = np.random.default_rng(seed)
    q = np.sort(np.asarray(bank, float), axis=1)
    yv = np.asarray(y, float)[:, None]
    lo = (q < yv).mean(axis=1)
    hi = (q <= yv).mean(axis=1)
    return lo + rng.uniform(size=len(yv)) * np.maximum(hi - lo, 0.0)


def pit_flatness(u: np.ndarray) -> dict:
    u = np.asarray(u, float)
    u = u[np.isfinite(u)]
    if not len(u):
        return {"max_decile_dev": None, "n": 0}
    hist, _ = np.histogram(u, bins=10, range=(0, 1))
    freq = hist / len(u)
    return {"max_decile_dev": float(np.max(np.abs(freq - 0.1))), "n": int(len(u))}


# ── Feature-matrix devices (median imputation inside the arm — never a data edit) ───────────────
_X = GE._X
train_medians = GE.train_medians


def entity_eb_rate(df: pd.DataFrame, prior_season_col: str, prior_games_col: str,
                   s2d_col: str, week_index_col: str, league_rate: float,
                   kappa: float = EB_KAPPA_GAMES) -> np.ndarray:
    """EB per-game rate: prior-season + season-to-date shrunk to the league rate by κ games."""
    prior = pd.to_numeric(df[prior_season_col], errors="coerce")
    prior_g = pd.to_numeric(df[prior_games_col], errors="coerce").fillna(0.0)
    s2d = pd.to_numeric(df[s2d_col], errors="coerce")
    s2d_g = pd.to_numeric(df[week_index_col], errors="coerce").sub(1).clip(lower=0.0)
    s2d_g = s2d_g.where(s2d.notna(), 0.0)
    num = prior.fillna(0.0) * prior_g + s2d.fillna(0.0) * s2d_g + kappa * league_rate
    return (num / (prior_g + s2d_g + kappa)).to_numpy(dtype=float)


#: (target → the frame columns its EB rate reads). Every count/rare leg's entity foil goes
#: through ONE formula so a new leg cannot re-implement it wrong.
EB_COLS: dict[str, tuple[str, str, str]] = {
    "fg_att": ("prior_week_box__fg_att_prior_season", "prior_week_box__kicker_games_prior_season",
               "prior_week_box__fg_att_s2d"),
    "xp_att": ("prior_week_box__pat_att_prior_season", "prior_week_box__kicker_games_prior_season",
               "prior_week_box__pat_att_s2d"),
    "def_sacks": ("team_environment__sacks_prior_season", "team_environment__games_prior_season",
                  "team_environment__sacks_s2d"),
    "def_int": ("team_environment__int_prior_season", "team_environment__games_prior_season",
                "team_environment__int_s2d"),
    "def_fumble_rec": ("team_environment__fr_prior_season", "team_environment__games_prior_season",
                       "team_environment__fr_s2d"),
    "dst_td": ("team_environment__dsttd_prior_season", "team_environment__games_prior_season",
               "team_environment__dsttd_s2d"),
    "def_safety": ("team_environment__safety_prior_season", "team_environment__games_prior_season",
                   "team_environment__safety_s2d"),
    "def_blocked_kick": ("team_environment__block_prior_season",
                         "team_environment__games_prior_season", "team_environment__block_s2d"),
    "pa_bucket": ("team_environment__pa_prior_season", "team_environment__games_prior_season",
                  "team_environment__pa_s2d"),
}


def eb_rate_for(leg: str, df: pd.DataFrame, league_rate: float,
                kappa: float = EB_KAPPA_GAMES) -> np.ndarray:
    ps, pg, s2d = EB_COLS[leg]
    return entity_eb_rate(df, ps, pg, s2d, "game_context__week_index", league_rate, kappa)


# ── Count arms ──────────────────────────────────────────────────────────────────────────────────
def fit_count_pois_glm(train, test, features, target, *, y_train=None) -> np.ndarray:
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    ok = np.isfinite(y)
    m = PoissonRegressor(alpha=1e-3, max_iter=2000).fit(
        sc.transform(_X(train, features, med))[ok], y[ok])
    mu = np.clip(m.predict(sc.transform(_X(test, features, med))), 1e-6, None)
    return poisson_bank(mu)


def fit_count_negbin_glm(train, test, features, target, *, y_train=None) -> np.ndarray:
    import statsmodels.api as sm
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    ok = np.isfinite(y)
    Xtr = sm.add_constant(sc.transform(_X(train, features, med))[ok], has_constant="add")
    Xte = sm.add_constant(sc.transform(_X(test, features, med)), has_constant="add")
    warm = PoissonRegressor(alpha=1e-3, max_iter=2000).fit(
        sc.transform(_X(train, features, med))[ok], y[ok])
    mu_tr = np.clip(warm.predict(sc.transform(_X(train, features, med))[ok]), 1e-6, None)
    alpha = GE._mom_dispersion(y[ok], mu_tr)
    res = sm.GLM(y[ok], Xtr, family=sm.families.NegativeBinomial(alpha=alpha)).fit(maxiter=200)
    mu = np.clip(res.predict(Xte), 1e-6, None)
    return nbinom_bank(mu, alpha)


def fit_count_lgbm(train, test, features, target, *, y_train=None) -> np.ndarray:
    """Distributional boosting: 9-knot bank → dense grid + exponential mean-excess tails fit on
    TRAIN exceedances (in-fold). ⛔ never flat-extended (NF-MARGIN1)."""
    Xtr, Xte = _X(train, features), _X(test, features)
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    ok = np.isfinite(y)
    knots_te = np.empty((len(test), len(FIT_LEVELS)))
    knots_tr = np.empty((int(ok.sum()), len(FIT_LEVELS)))
    for j, a in enumerate(FIT_LEVELS):
        m = WP._lgbm({"objective": "quantile", "alpha": a, "n_estimators": 200,
                      "num_leaves": 31, "min_child_samples": 30})
        m.fit(Xtr[ok], y[ok])
        knots_te[:, j] = m.predict(Xte)
        knots_tr[:, j] = m.predict(Xtr[ok])
    tail = fit_knot_tail_betas(knots_tr, y[ok])
    return dense_bank_from_knots(knots_te, tail, clip_lo=0.0)


def fit_rare_eb_pois(train, test, features, target, *, y_train=None) -> np.ndarray:
    """Entity-EB rate → exact Poisson predictive (the thin rare-leg family's EB arm)."""
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    league = float(np.nanmean(y))
    return poisson_bank(eb_rate_for(target, test, league))


def fit_rare_hurdle(train, test, features, target, *, y_train=None) -> np.ndarray:
    """ZIP-style hurdle: P(y>0 | X) logistic × positive-Poisson body (league positive mean)."""
    from scipy.stats import poisson
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    ok = np.isfinite(y)
    any_pos = (y[ok] > 0).astype(int)
    if any_pos.sum() in (0, len(any_pos)):
        pi = np.full(len(test), float(any_pos.mean()))
    else:
        m = LogisticRegression(max_iter=1000).fit(sc.transform(_X(train, features, med))[ok],
                                                  any_pos)
        pi = m.predict_proba(sc.transform(_X(test, features, med)))[:, 1]
    mu_pos = float(np.mean(y[ok][y[ok] > 0])) if (y[ok] > 0).any() else 1.0
    k = np.arange(COUNT_SUPPORT + 1)
    body = poisson.cdf(k, mu_pos)
    p0 = poisson.pmf(0, mu_pos)
    pos_cdf = np.clip((body - p0) / max(1 - p0, 1e-9), 0.0, 1.0)
    cdf = (1 - pi)[:, None] + pi[:, None] * pos_cdf[None, :]
    cdf[:, -1] = 1.0
    return bank_from_count_cdf(cdf)


def foil_climatology_bank(train, test, target, *, y_train=None) -> np.ndarray:
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    return marginal_bank(y[np.isfinite(y)], len(test))


def foil_entity_eb_bank(train, test, target, *, y_train=None) -> np.ndarray:
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    league = float(np.nanmean(y))
    return poisson_bank(eb_rate_for(target, test, league))


def foil_league_rate_bank(train, test, target, *, y_train=None) -> np.ndarray:
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    return poisson_bank(np.full(len(test), float(np.nanmean(y))))


COUNT_FITTERS = {
    "pois_glm": fit_count_pois_glm, "negbin_glm": fit_count_negbin_glm,
    "lgbm_quantile": fit_count_lgbm, "eb_pois": fit_rare_eb_pois, "hurdle_pois": fit_rare_hurdle,
    "foil_climatology": lambda tr, te, f, t, *, y_train=None: foil_climatology_bank(
        tr, te, t, y_train=y_train),
    "foil_entity_eb": lambda tr, te, f, t, *, y_train=None: foil_entity_eb_bank(
        tr, te, t, y_train=y_train),
    "foil_league_rate": lambda tr, te, f, t, *, y_train=None: foil_league_rate_bank(
        tr, te, t, y_train=y_train),
}


# ── Attempt-grain arms: make probability ────────────────────────────────────────────────────────
_MAKE_BINS = (0.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 100.0)


def _league_curve(train, target="made"):
    """Empirical make rate by distance bin (train), clipped — the design's league-curve foil."""
    d = pd.to_numeric(train["game_context__kick_distance"], errors="coerce")
    y = pd.to_numeric(train[target], errors="coerce")
    idx = np.clip(np.digitize(d, _MAKE_BINS) - 1, 0, len(_MAKE_BINS) - 2)
    rates = np.full(len(_MAKE_BINS) - 1, float(np.nanmean(y)))
    for b in range(len(_MAKE_BINS) - 1):
        sel = idx == b
        if sel.sum() >= 20:
            rates[b] = float(np.nanmean(y[sel]))
    return np.clip(rates, 0.01, 0.99), idx


def fit_make_league_curve(train, test, features, target="made", *, y_train=None) -> np.ndarray:
    tr = train.copy()
    if y_train is not None:
        tr = tr.assign(made=np.asarray(y_train, float))
    rates, _ = _league_curve(tr)
    d = pd.to_numeric(test["game_context__kick_distance"], errors="coerce")
    idx = np.clip(np.digitize(d, _MAKE_BINS) - 1, 0, len(_MAKE_BINS) - 2)
    return rates[idx]


def fit_make_constant(train, test, features, target="made", *, y_train=None) -> np.ndarray:
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    return np.full(len(test), float(np.clip(np.nanmean(y), 0.01, 0.99)))


def _distance_logit(train, y):
    from sklearn.linear_model import LogisticRegression
    d = pd.to_numeric(train["game_context__kick_distance"], errors="coerce").to_numpy(float)
    X = np.column_stack([d, d ** 2])
    return LogisticRegression(max_iter=1000).fit(X, y.astype(int))


def fit_make_eb_kicker_curve(train, test, features, target="made", *, y_train=None) -> np.ndarray:
    """League logistic distance curve + a kicker EB intercept offset (shrunk by attempts)."""
    from scipy.special import expit, logit
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    base = _distance_logit(train, y)
    d_te = pd.to_numeric(test["game_context__kick_distance"], errors="coerce").to_numpy(float)
    p0 = np.clip(base.predict_proba(np.column_stack([d_te, d_te ** 2]))[:, 1], 1e-3, 1 - 1e-3)
    eb = pd.to_numeric(test["prior_week_box__kicker_prior_makerate_eb"], errors="coerce")
    league = float(np.clip(np.nanmean(y), 1e-3, 1 - 1e-3))
    off = logit(np.clip(eb.fillna(league).to_numpy(float), 1e-3, 1 - 1e-3)) - logit(league)
    return np.clip(expit(logit(p0) + off), 1e-4, 1 - 1e-4)


def fit_make_logit_glm(train, test, features, target="made", *, y_train=None) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    aug = list(features) + ["_dist_sq"]
    tr, te = train.copy(), test.copy()
    for f in (tr, te):
        f["_dist_sq"] = pd.to_numeric(f["game_context__kick_distance"], errors="coerce") ** 2
    med["_dist_sq"] = float(pd.to_numeric(tr["_dist_sq"], errors="coerce").median())
    sc = StandardScaler().fit(_X(tr, aug, med))
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    m = LogisticRegression(max_iter=1000).fit(sc.transform(_X(tr, aug, med)), y.astype(int))
    return np.clip(m.predict_proba(sc.transform(_X(te, aug, med)))[:, 1], 1e-4, 1 - 1e-4)


def fit_make_lgbm(train, test, features, target="made", *, y_train=None) -> np.ndarray:
    from lightgbm import LGBMClassifier
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    m = LGBMClassifier(n_estimators=200, num_leaves=15, min_child_samples=30,
                       learning_rate=0.05, verbose=-1, random_state=_SEED)
    m.fit(_X(train, features), y.astype(int))
    return np.clip(m.predict_proba(_X(test, features))[:, 1], 1e-4, 1 - 1e-4)


MAKE_FITTERS = {
    "eb_kicker_curve": fit_make_eb_kicker_curve, "logit_distance_glm": fit_make_logit_glm,
    "lgbm_classifier": fit_make_lgbm, "foil_league_curve": fit_make_league_curve,
    "foil_constant_rate": fit_make_constant,
}


def log_loss_binary(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    yv = np.asarray(y, float)
    return -(yv * np.log(p) + (1 - yv) * np.log(1 - p))


# ── Attempt-grain arms: band allocation ─────────────────────────────────────────────────────────
def band_index(distance: np.ndarray) -> np.ndarray:
    d = np.asarray(distance, float)
    return np.clip(np.digitize(d, BAND_EDGES) - 1, 0, len(BANDS) - 1)


def fit_band_league_mix(train, test, features, target="band", *, y_train=None) -> np.ndarray:
    y = train[target].to_numpy() if y_train is None else np.asarray(y_train)
    mix = np.array([(y == b).mean() for b in range(len(BANDS))], dtype=float)
    mix = np.clip(mix, 1e-4, None)
    mix = mix / mix.sum()
    return np.tile(mix, (len(test), 1))


def fit_band_mnlogit(train, test, features, target="band", *, y_train=None) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = (train[target].to_numpy() if y_train is None else np.asarray(y_train)).astype(int)
    m = LogisticRegression(max_iter=1000).fit(sc.transform(_X(train, features, med)), y)
    return _expand_proba(m.predict_proba(sc.transform(_X(test, features, med))), m.classes_,
                         len(BANDS))


def fit_band_eb_dirichlet(train, test, features, target="band", *, y_train=None) -> np.ndarray:
    """Kicker band-mix EB: strictly-prior per-kicker band counts + α·league mix (the leg-strength
    signal — 50+ share persists at ρ≈0.43, NF1.6 finding ③)."""
    y = train[target].to_numpy() if y_train is None else np.asarray(y_train)
    league = np.array([(y == b).mean() for b in range(len(BANDS))], dtype=float)
    league = np.clip(league, 1e-4, None)
    league = league / league.sum()
    att = pd.to_numeric(test["prior_week_box__kicker_prior_att"], errors="coerce").fillna(0.0)
    s50 = pd.to_numeric(test["prior_week_box__kicker_prior_share50_eb"], errors="coerce")
    s40 = pd.to_numeric(test["prior_week_box__kicker_prior_share40_eb"], errors="coerce")
    s50 = s50.fillna(league[2]).to_numpy(float)
    s40 = s40.fillna(league[1]).to_numpy(float)
    n = att.to_numpy(float)
    w = n / (n + EB_KAPPA_BAND)
    p50 = w * s50 + (1 - w) * league[2]
    p40 = w * s40 + (1 - w) * league[1]
    p0 = np.clip(1.0 - p50 - p40, 1e-4, None)
    out = np.column_stack([p0, np.clip(p40, 1e-4, None), np.clip(p50, 1e-4, None)])
    return out / out.sum(axis=1, keepdims=True)


def fit_band_lgbm(train, test, features, target="band", *, y_train=None) -> np.ndarray:
    from lightgbm import LGBMClassifier
    y = (train[target].to_numpy() if y_train is None else np.asarray(y_train)).astype(int)
    m = LGBMClassifier(n_estimators=200, num_leaves=15, min_child_samples=30,
                       learning_rate=0.05, verbose=-1, random_state=_SEED)
    m.fit(_X(train, features), y)
    return _expand_proba(m.predict_proba(_X(test, features)), m.classes_, len(BANDS))


def _expand_proba(proba: np.ndarray, classes: np.ndarray, n_classes: int) -> np.ndarray:
    """A classifier fit on a train block missing a class emits a narrower proba matrix — expand
    to the declared class space (absent classes get 0 + renormalized epsilon floor)."""
    out = np.full((proba.shape[0], n_classes), 1e-6)
    for j, c in enumerate(np.asarray(classes, dtype=int)):
        out[:, c] = proba[:, j]
    return out / out.sum(axis=1, keepdims=True)


BAND_FITTERS = {
    "mnlogit": fit_band_mnlogit, "eb_dirichlet_kicker": fit_band_eb_dirichlet,
    "lgbm_multiclass": fit_band_lgbm, "foil_league_mix": fit_band_league_mix,
}


def log_loss_multiclass(proba: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(proba, float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    return -np.log(p[np.arange(len(y)), np.asarray(y, dtype=int)])


# ── Bucket legs (the exact-tier discipline) ─────────────────────────────────────────────────────
def bucket_index(values: np.ndarray, edges: tuple) -> np.ndarray:
    v = np.asarray(values, float)
    return np.clip(np.digitize(v, np.asarray(edges, float)) - 1, 0, len(edges) - 1)


def fit_bucket_climatology(train, test, features, target, *, y_train=None, n_buckets=9) -> np.ndarray:
    y = (train[target].to_numpy() if y_train is None else np.asarray(y_train)).astype(int)
    mix = np.array([(y == b).mean() for b in range(n_buckets)], dtype=float)
    mix = np.clip(mix, 1e-5, None)
    mix = mix / mix.sum()
    return np.tile(mix, (len(test), 1))


def fit_bucket_entity_eb(train, test, features, target, *, y_train=None, n_buckets=9) -> np.ndarray:
    """The empirical CONDITIONAL bucket mix given the team's EB points/yards-allowed rate — the
    NF1.6 quantile-bin mechanism at weekly grain (an entity-conditioned climatology)."""
    rate_leg = "pa_bucket"
    y_tr = (train[target].to_numpy() if y_train is None else np.asarray(y_train)).astype(int)
    league = float(np.nanmean(pd.to_numeric(train["pa" if target == "pa_bucket" else "ya"],
                                            errors="coerce")))
    r_tr = eb_rate_for(rate_leg, train, league) if target == "pa_bucket" else \
        pd.to_numeric(train["team_environment__ya_l8"], errors="coerce").fillna(league).to_numpy()
    r_te = eb_rate_for(rate_leg, test, league) if target == "pa_bucket" else \
        pd.to_numeric(test["team_environment__ya_l8"], errors="coerce").fillna(league).to_numpy()
    qs = np.nanquantile(r_tr, [0.2, 0.4, 0.6, 0.8])
    bin_tr = np.digitize(r_tr, qs)
    bin_te = np.digitize(r_te, qs)
    out = np.empty((len(test), n_buckets))
    marg = fit_bucket_climatology(train, test.iloc[:1], features, target, y_train=y_train,
                                  n_buckets=n_buckets)[0]
    for b in range(5):
        sel = bin_tr == b
        if sel.sum() >= 50:
            mix = np.array([(y_tr[sel] == k).mean() for k in range(n_buckets)])
            mix = np.clip(mix, 1e-5, None)
            mix = mix / mix.sum()
        else:
            mix = marg
        out[bin_te == b] = mix
    return out


def fit_bucket_ordered_logit(train, test, features, target, *, y_train=None, n_buckets=9) -> np.ndarray:
    from statsmodels.miscmodels.ordinal_model import OrderedModel
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = (train[target].to_numpy() if y_train is None else np.asarray(y_train)).astype(int)
    res = OrderedModel(y, sc.transform(_X(train, features, med)), distr="logit").fit(
        method="lbfgs", maxiter=400, disp=False)
    proba = np.asarray(res.predict(sc.transform(_X(test, features, med))))
    present = np.sort(np.unique(y))
    return _expand_proba(proba, present, n_buckets)


def fit_bucket_mnlogit(train, test, features, target, *, y_train=None, n_buckets=9) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = (train[target].to_numpy() if y_train is None else np.asarray(y_train)).astype(int)
    m = LogisticRegression(max_iter=2000).fit(sc.transform(_X(train, features, med)), y)
    return _expand_proba(m.predict_proba(sc.transform(_X(test, features, med))), m.classes_,
                         n_buckets)


def fit_bucket_negbin_integrated(train, test, features, target="pa_bucket", *,
                                 y_train=None, n_buckets=9) -> np.ndarray:
    """The full points-allowed COUNT distribution integrated over the bucket boundaries — the
    §4A.3 candidate #3. ⚠️ Fit on the underlying `pa` count, never on the bucket index; when the
    control permutes the BUCKET label, the underlying count is permuted identically (y_train
    carries pa)."""
    from scipy.stats import nbinom
    import statsmodels.api as sm
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = (pd.to_numeric(train["pa"], errors="coerce").to_numpy(float)
         if y_train is None else np.asarray(y_train, float))
    ok = np.isfinite(y)
    warm = PoissonRegressor(alpha=1e-3, max_iter=2000).fit(
        sc.transform(_X(train, features, med))[ok], y[ok])
    mu_tr = np.clip(warm.predict(sc.transform(_X(train, features, med))[ok]), 1e-6, None)
    alpha = GE._mom_dispersion(y[ok], mu_tr)
    Xtr = sm.add_constant(sc.transform(_X(train, features, med))[ok], has_constant="add")
    Xte = sm.add_constant(sc.transform(_X(test, features, med)), has_constant="add")
    res = sm.GLM(y[ok], Xtr, family=sm.families.NegativeBinomial(alpha=alpha)).fit(maxiter=200)
    mu = np.clip(res.predict(Xte), 1e-6, None)
    r = 1.0 / max(alpha, 1e-9)
    p = r / (r + mu)
    edges = np.asarray(PA_EDGES, float)
    cdf_hi = np.empty((len(test), n_buckets))
    for b in range(n_buckets):
        hi = edges[b + 1] - 1 if b + 1 < n_buckets else np.inf
        cdf_hi[:, b] = nbinom.cdf(hi, r, p) if np.isfinite(hi) else 1.0
    cdf_lo = np.column_stack([np.zeros(len(test)), cdf_hi[:, :-1]])
    out = np.clip(cdf_hi - cdf_lo, 1e-9, None)
    return out / out.sum(axis=1, keepdims=True)


def fit_bucket_gauss_integrated(train, test, features, target="ya_bucket", *,
                                y_train=None, n_buckets=9) -> np.ndarray:
    """The yards-allowed distribution integrated over the YA edges: linear mean + train residual
    normal spread (§4A.3 candidate #3, the continuous twin)."""
    from scipy.stats import norm
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = (pd.to_numeric(train["ya"], errors="coerce").to_numpy(float)
         if y_train is None else np.asarray(y_train, float))
    ok = np.isfinite(y)
    m = Ridge(alpha=1.0).fit(sc.transform(_X(train, features, med))[ok], y[ok])
    resid = y[ok] - m.predict(sc.transform(_X(train, features, med))[ok])
    sd = float(np.std(resid, ddof=1))
    mu = m.predict(sc.transform(_X(test, features, med)))
    edges = np.asarray(YA_EDGES, float)
    cdf_hi = np.empty((len(test), n_buckets))
    for b in range(n_buckets):
        hi = edges[b + 1] if b + 1 < n_buckets else np.inf
        cdf_hi[:, b] = norm.cdf(hi, mu, sd) if np.isfinite(hi) else 1.0
    cdf_lo = np.column_stack([np.zeros(len(test)), cdf_hi[:, :-1]])
    out = np.clip(cdf_hi - cdf_lo, 1e-9, None)
    return out / out.sum(axis=1, keepdims=True)


BUCKET_FITTERS = {
    "ordered_logit": fit_bucket_ordered_logit, "mnlogit": fit_bucket_mnlogit,
    "negbin_integrated": fit_bucket_negbin_integrated,
    "gauss_integrated": fit_bucket_gauss_integrated,
    "foil_climatology": fit_bucket_climatology, "foil_entity_eb": fit_bucket_entity_eb,
}


def rps(proba: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ranked probability score over ordered categories, normalized by K−1 — proper for the
    exact-tier bucket legs (⛔ never MAE on a tier index)."""
    p = np.clip(np.asarray(proba, float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    K = p.shape[1]
    cum_p = np.cumsum(p, axis=1)
    cum_y = (np.arange(K)[None, :] >= np.asarray(y, dtype=int)[:, None]).astype(float)
    return ((cum_p - cum_y) ** 2).sum(axis=1) / (K - 1)


# ── Categorical anchors ─────────────────────────────────────────────────────────────────────────
def anchor_point_mass(proba_shape: tuple[int, int], modal: int) -> np.ndarray:
    out = np.full(proba_shape, 1e-6)
    out[:, modal] = 1.0
    return out / out.sum(axis=1, keepdims=True)


def anchor_uniform(proba_shape: tuple[int, int]) -> np.ndarray:
    return np.full(proba_shape, 1.0 / proba_shape[1])


def permute_within_group(y: np.ndarray, groups: np.ndarray, seed: int = _SEED) -> np.ndarray:
    """Labels shuffled WITHIN group (week / distance bin) — destroys entity identity while
    preserving every group-level marginal. The permuted arm must LOSE."""
    rng = np.random.default_rng(seed)
    out = np.asarray(y).copy()
    for g in pd.unique(groups):
        pos = np.flatnonzero(groups == g)
        if len(pos) > 1:
            out[pos] = rng.permutation(out[pos])
    return out


def matched_n_train(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """The most recent train slice about the test block's size — the NF1.9 (f) capacity control."""
    n = max(len(test), 50)
    return train.sort_values("gw").tail(n)


# ── Assembly: components → exact scoring → the fantasy-point bank ───────────────────────────────
def sample_from_bank(bank: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Inverse-CDF draws from a dense quantile bank: u (n, S) → values (n, S)."""
    q = np.sort(np.asarray(bank, float), axis=1)
    out = np.empty_like(u)
    for i in range(q.shape[0]):
        out[i] = np.interp(u[i], EVAL_LEVELS, q[i])
    return out


def _split_bands(att: np.ndarray, p_band: np.ndarray, rng) -> tuple[np.ndarray, ...]:
    """Multinomial split of integer attempt draws (n, S) into the 3 bands via chained binomials."""
    p = np.clip(np.asarray(p_band, float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    n0 = rng.binomial(att.astype(int), p[:, [0]] * np.ones_like(att))
    rest = att.astype(int) - n0
    p1c = np.clip(p[:, [1]] / np.clip(1 - p[:, [0]], 1e-9, None), 0.0, 1.0)
    n1 = rng.binomial(rest, p1c * np.ones_like(att))
    n2 = rest - n1
    return n0, n1, n2


def assemble_k_bank(att_bank: np.ndarray, xp_bank: np.ndarray, p_band: np.ndarray,
                    p_make: np.ndarray, xp_rate: float, *, draws: int = ASSEMBLY_DRAWS,
                    seed: int = _SEED) -> np.ndarray:
    """The kicker chain: FG attempts → band split → distance-conditional makes → XP → the
    modal-default scoring → the (n, 199) fantasy-point bank. Component draws independent
    (declared V1 simplification; the coverage floor is the check that would expose it)."""
    rng = np.random.default_rng(seed)
    n = att_bank.shape[0]
    att = np.rint(np.clip(sample_from_bank(att_bank, rng.uniform(size=(n, draws))), 0, None))
    xp = np.rint(np.clip(sample_from_bank(xp_bank, rng.uniform(size=(n, draws))), 0, None))
    n0, n1, n2 = _split_bands(att, p_band, rng)
    made0 = rng.binomial(n0, np.clip(p_make[:, [0]], 0, 1) * np.ones_like(n0, dtype=float))
    made1 = rng.binomial(n1, np.clip(p_make[:, [1]], 0, 1) * np.ones_like(n1, dtype=float))
    made2 = rng.binomial(n2, np.clip(p_make[:, [2]], 0, 1) * np.ones_like(n2, dtype=float))
    xp_made = rng.binomial(xp.astype(int), float(np.clip(xp_rate, 0, 1)))
    pts = (BAND_POINTS[0] * made0 + BAND_POINTS[1] * made1 + BAND_POINTS[2] * made2
           + 1.0 * xp_made)
    return np.quantile(pts, EVAL_LEVELS, axis=1).T


def assemble_dst_bank(count_banks: dict[str, np.ndarray], pa_proba: np.ndarray, *,
                      draws: int = ASSEMBLY_DRAWS, seed: int = _SEED) -> np.ndarray:
    """The DST chain: counting components + the EXACT tier draw from the PA bucket
    probabilities → the (n, 199) fantasy-point bank. ⛔ no point estimate ever crosses the tier
    table — the bucket is DRAWN from its modeled probabilities and scored exactly."""
    rng = np.random.default_rng(seed)
    n = next(iter(count_banks.values())).shape[0]
    pts = np.zeros((n, draws))
    for leg, w in DST_LINEAR_POINTS.items():
        c = np.rint(np.clip(sample_from_bank(count_banks[leg], rng.uniform(size=(n, draws))),
                            0, None))
        pts += w * c
    p = np.clip(np.asarray(pa_proba, float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    cum = np.cumsum(p, axis=1)
    u = rng.uniform(size=(n, draws))
    bucket = (u[:, :, None] > cum[:, None, :]).sum(axis=2)
    pts += np.asarray(PA_TIER_POINTS, float)[bucket]
    return np.quantile(pts, EVAL_LEVELS, axis=1).T


def expected_tier_points(pa_proba: np.ndarray) -> np.ndarray:
    """E[tier points] = Σ_b s_b · P(B=b) — the linear-in-probabilities identity (§4A.3)."""
    p = np.clip(np.asarray(pa_proba, float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    return p @ np.asarray(PA_TIER_POINTS, float)


# ── Layer-B foils on the points targets ─────────────────────────────────────────────────────────
def foil_board_eb_points(train, test, target: str, entity_col: str, *,
                         y_train=None) -> np.ndarray:
    """The NF1/MVP-1-board-equivalent weekly read: entity-EB points rate (prior-season +
    season-to-date shrunk to league) + the train residual bank at 199 levels. ⚠️ The shipped
    board is SEASON-grain and consumes week-1 Vegas implied points (deferred here); this in-fold
    weekly reconstruction without markets is the comparable form — recorded as such."""
    y_tr = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    league = float(np.nanmean(y_tr))
    # ⚠️ expanding means REQUIRE gw order within entity — computed on one gw-sorted history and
    # mapped back by index, so a merge-scrambled frame order cannot corrupt the running level.
    # A TEST row's history may include earlier TEST rows of the same block: for a foil that is
    # the entity's honest running level, that is the same information a served season÷games
    # board accrues week over week.
    # the own-form ORACLE calls this with train IS test — append only the test rows not already
    # present, or the concat duplicates every index and the reindex below refuses
    te_extra = test.loc[~test.index.isin(train.index)]
    hist = pd.concat([train[[entity_col, "gw", target]], te_extra[[entity_col, "gw", target]]])
    hist = hist.sort_values("gw", kind="stable")
    exp_mean = hist.groupby(entity_col, sort=False)[target].transform(
        lambda s: s.shift(1).expanding().mean())
    exp_cnt = hist.groupby(entity_col, sort=False).cumcount().astype(float)
    pt = np.where(np.isfinite(exp_mean.to_numpy(float)), exp_mean.to_numpy(float), league)
    w = exp_cnt.to_numpy() / (exp_cnt.to_numpy() + EB_KAPPA_GAMES)
    point = pd.Series(w * pt + (1 - w) * league, index=hist.index)
    point_tr = point.reindex(train.index).to_numpy(float)
    point_te = point.reindex(test.index).to_numpy(float)
    return point_plus_residual_bank(point_te, y_tr, point_tr,
                                    clip_lo=0.0 if target == "k_points" else None)


def fit_direct_points(train, test, features, target, *, y_train=None) -> np.ndarray:
    """The direct-learned points foil: 9-knot LGBM quantile on weekly fantasy points → dense grid
    + exponential tails (never flat)."""
    return fit_count_lgbm(train, test, features, target, y_train=y_train)


# ── Verdicts / gates / classification — shared with the sibling stories ─────────────────────────
paired_ci95 = GE.paired_ci95
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
classify_layer_b = GE.classify_layer_b
hand_classify_refusal = GE.hand_classify_refusal
flag_unsafe_field_shrink = GE.flag_unsafe_field_shrink
gate_sensitivity = GE.gate_sensitivity


def compose_gate(sel: dict, fdr_pass: bool, *, coverage: bool = False) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["degenerates_lose"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
    }
    if coverage:
        checks["coverage_floor_ok"] = not sel["coverage"]["blocking_shortfall"]
    return {"checks": checks, "ship": all(checks.values())}


def coverage_constraint_refusal(sel: dict, checks: dict, base: dict, *,
                                mechanism: str | None = None,
                                remedy: str | None = None) -> dict:
    """NF-D18: a Layer-B null whose ONLY refusing clause is the pre-registered coverage(80)
    FLOOR is a **CONSTRAINT_REFUSED**, not POWER_LIMITED — more folds shrink the binomial SE and
    make the refusal MORE certain, so no fold count and no field size changes the verdict.
    `GE.classify_layer_b`'s POWER_LIMITED branch was written for the NF-W3 shape (arm wins but the
    CI spans zero) and, applied here, publishes both a self-contradicting reason ("spans zero"
    about an interval that excludes zero) and a fold-count trigger for a shortfall data cannot
    move — the exact misleading-trigger direction NF-D18/MH2 (g″) forbid.

    Applies ONLY when every other gate clause is green AND the floor's shortfall is blocking
    (measured, not thin-sample): otherwise the base classification stands untouched.

    `mechanism`/`remedy` let a SUCCESSOR story (NF-W7b) state ITS mechanism — the defaults are
    NF-W7's independence-simplification prose, which would be FALSE of a joint-draw arm.
    """
    cov = sel.get("coverage") or {}
    others_green = all(v for k, v in checks.items() if k != "coverage_floor_ok")
    if not (sel.get("beats_foil") and others_green
            and checks.get("coverage_floor_ok") is False and cov.get("blocking_shortfall")):
        return base
    se = cov.get("binomial_se")
    shortfall_se = ((COVERAGE_FLOOR - cov["winner_coverage_80"]) / se) if se else None
    out = dict(base)
    out.update({
        "state": "CONSTRAINT_REFUSED",
        "hand_corrected": True,
        "reason": (
            f"every statistical gate is GREEN — the assembled arm beats the best foil by "
            f"{sel['mean_delta']:+.4f} CRPS (CI95 {sel['ci95']} excludes zero), fold wins "
            f"{sel['fold_wins']} against a required {sel['fold_clause']['required']}, "
            f"p={sel['p_one_sided']}, PBO/DSR/FDR all pass — and the ship is refused by the "
            f"pre-registered coverage(80) FLOOR alone: {cov['winner_coverage_80']:.4f} against "
            f"0.80 at n={cov.get('n_rows')}"
            + (f" (≈{shortfall_se:.1f} binomial SE below nominal — decisive under-coverage, not "
               f"sampling noise)" if shortfall_se is not None else "")
            + (mechanism if mechanism is not None else
               ". The mechanism is the DECLARED independence-simplification check firing: "
               "component banks drawn independently under-disperse the assembled sum wherever "
               "the components co-move.")),
        "retest_trigger": (remedy if remedy is not None else (
            "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds make the "
            "refusal MORE certain. The remedy is a DIFFERENT MECHANISM (a successor modeling "
            "cross-component dependence — e.g. a joint/copula draw over the component legs) or a "
            "PM decision; ⛔ never a post-hoc floor change (a floor re-set after seeing the result "
            "is the E2.1-r inversion — NF1.8).")),
    })
    return out
