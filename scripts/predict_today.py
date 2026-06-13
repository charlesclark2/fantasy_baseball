"""Daily scoring entry point (scripts/ entry point for scripts-level tooling).

Given a date (default today), score all confirmed regular-season games, print
a picks table to stdout, and write predictions to Snowflake.

Run from project root:
    uv run python scripts/predict_today.py
    uv run python scripts/predict_today.py --date 2026-05-01

RANGE / BACKFILL mode (Story 30.7) — score every completed-game date in a window in ONE
process (models, historical features, and the imputation pipeline are built once and reused
per date, not reloaded per date), writing is_backfill=TRUE rows. Set TARGET_ENV=prod to write
the prod schema:
    TARGET_ENV=prod uv run python scripts/predict_today.py --start 2024-01-01 --is-backfill --no-log-snowflake
    TARGET_ENV=prod uv run python scripts/predict_today.py --start 2026-03-01 --end 2026-06-12 --is-backfill --no-log-snowflake
"""

from __future__ import annotations

import argparse
import functools as _functools
import json
import math
import os
import re
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, load_todays_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import load_model
from betting_ml.utils.probability_layer import (
    compute_posterior,
    compute_edge,
    compute_actionable_edge,
    compute_kelly,
    compute_bet_permission,
)
from betting_ml.models.total_runs_trainer import p_over_line
from betting_ml.scripts.evaluation.bayesian_model_eval import (
    compute_bet_decision,
    DEFAULT_TOTALS_MU_THRESHOLD,
    DEFAULT_H2H_MAGNITUDE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_VERSION = "v0"

# A1.12 — write target resolved by the shared resolver so this scorer, the
# betting_ml/ scorer, and the app all agree on dev vs prod (TARGET_ENV=prod →
# betting_ml; else betting_ml_dev). See betting_ml/utils/ml_env.py.
from betting_ml.utils.ml_env import ml_schema  # noqa: E402

_ML_SCHEMA = ml_schema()

_CALIBRATOR_PATH = PROJECT_ROOT / 'betting_ml/models/home_win/calibrator.joblib'


def _load_calibrator():
    if _CALIBRATOR_PATH.exists():
        return joblib.load(_CALIBRATOR_PATH)
    print('[WARN] calibrator.joblib not found — using consensus_win_prob uncalibrated')
    return None


_calibrator = _load_calibrator()


def _apply_calibrator(consensus_win_prob: float) -> float:
    """Return calibrated win probability; falls back to consensus if no calibrator."""
    if _calibrator is not None:
        raw = np.array([consensus_win_prob])
        try:
            calibrated_win_prob = float(_calibrator.predict_proba(raw.reshape(-1, 1))[0, 1])
        except AttributeError:
            calibrated_win_prob = float(_calibrator.predict(raw)[0])
        return calibrated_win_prob
    return consensus_win_prob


_CREATE_PREDICTIONS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_ML_SCHEMA}.daily_model_predictions (
    -- Run metadata
    model_version           VARCHAR(20)    NOT NULL,
    inserted_at             TIMESTAMP_NTZ  NOT NULL,
    score_date              DATE           NOT NULL,
    prediction_type         VARCHAR(20),
    lineup_confirmed        BOOLEAN,

    -- Game identifiers
    game_pk                 INTEGER,
    game_date               DATE,
    game_datetime           TIMESTAMP_NTZ,

    -- Matchup
    home_team               VARCHAR(100),
    away_team               VARCHAR(100),
    home_team_abbrev        VARCHAR(10),
    away_team_abbrev        VARCHAR(10),

    -- Whether bookmaker odds were available for this game
    has_odds                BOOLEAN,

    -- Core model outputs (populated for every game)
    p_home_win_ngboost      FLOAT,   -- NGBoost run-diff: P(home run diff > 0)
    p_home_win_classifier   FLOAT,   -- XGBoost + Platt calibration: P(home wins)
    consensus_win_prob      FLOAT,   -- 0.5 * ngboost + 0.5 * classifier (audit column)
    calibrated_win_prob     FLOAT,   -- consensus_win_prob after in-season Platt recalibration
    pick                    VARCHAR(60),
    pred_total_runs         FLOAT,   -- NGBoost total-runs point estimate (loc)
    pred_total_runs_scale   FLOAT,   -- NGBoost total-runs uncertainty (scale / std dev)
    pred_run_diff_loc       FLOAT,   -- NGBoost run-diff point estimate (loc)
    pred_run_diff_scale     FLOAT,   -- NGBoost run-diff uncertainty (scale / std dev)
    p_over_ngboost          FLOAT,   -- NGBoost P(total runs > total_line_consensus)

    -- Probability layer (alpha tuned on historical data)
    alpha                   FLOAT,

    -- H2H (moneyline) market — NULL when has_odds = FALSE
    h2h_market_implied_prob FLOAT,   -- consensus vig-adjusted P(home wins)
    h2h_posterior_prob      FLOAT,   -- Bayesian blend of model and market
    h2h_edge                FLOAT,   -- A2.5: actionable edge = h2h_posterior_prob - h2h_market_implied_prob (alpha-aware; ~0 when best_alpha=0). Raw cal-vs-market gap lives in layer4_h2h_edge.
    h2h_kelly_fraction      FLOAT,   -- full Kelly fraction sized off h2h_edge (positive = bet home; ~0 when best_alpha=0)

    -- Totals market — NULL when has_odds = FALSE
    total_line_consensus    FLOAT,   -- consensus over/under line
    over_prob_consensus     FLOAT,   -- consensus vig-adjusted P(over)
    totals_model_prob       FLOAT,   -- NGBoost P(total > total_line_consensus)
    totals_posterior_prob   FLOAT,
    totals_edge             FLOAT,   -- A2.5: actionable edge = totals_posterior_prob - over_prob_consensus (alpha-aware; ~0 when best_alpha=0)
    totals_kelly_fraction   FLOAT,   -- full Kelly fraction sized off totals_edge (~0 when best_alpha=0)

    -- Epic 16.2 — game-level sequential-posterior provenance
    posterior_source        VARCHAR(20),  -- least-informed source across the game's players
    prior_age_days          INTEGER,      -- max stale-belief age (>7 flags game_uncertainty_score)

    -- Layer 4 — live selective-strategy bet attribution. Records what the Layer 4
    -- rule would recommend for each live game; as CLV labels accumulate this is the
    -- honest real-world OOS surface for evaluate_selective_strategy().
    layer4_totals_decision    VARCHAR(10),  -- over / under / abstain (1.0-run threshold vs model mu)
    layer4_totals_over_signal FLOAT,        -- pred_total_runs - total_line_consensus
    layer4_h2h_decision       VARCHAR(10),  -- home / away / abstain
    layer4_h2h_rule           VARCHAR(20),  -- direction_flip / magnitude / abstain
    layer4_h2h_edge           FLOAT,        -- calibrated_win_prob - h2h_market_implied_prob

    -- Epic 19 / Story 17.1b — bullpen OOD gate
    bullpen_z_score_home      FLOAT,        -- (bullpen_mu_home - training_mean) / training_std
    bullpen_z_score_away      FLOAT,        -- (bullpen_mu_away - training_mean) / training_std
    bullpen_signal_ood        BOOLEAN,      -- TRUE when |z_home|>1.5 or |z_away|>1.5; blocks totals bets

    -- Story 28.3 — actual Bovada American moneyline odds at scoring time (not de-vigged).
    -- Populated for every game with Bovada h2h odds; used by the magnitude kill-criterion
    -- monitor to compute real-book ROI (decimal = 1 + 100/|odds| if negative, or odds/100+1 if positive).
    layer4_h2h_bovada_ml_home INTEGER,      -- e.g. -158 (home favored) or +132 (home dog)
    layer4_h2h_bovada_ml_away INTEGER,      -- mirroring away-side American odds

    -- Story 28.6b — conviction-gate overlay (the 28.2 selective filter). Flags games
    -- where the two INDEPENDENT H2H estimators agree within 0.02:
    --   |calibrated_win_prob − P_run_diff(home)|, where P_run_diff(home) = Φ(μ/σ).
    -- Consumed SHADOW/manual by monitor_conviction_h2h.py against the 28.6b kill
    -- criterion; NO automated bets until live CONFIRM. Independent of odds (a game can
    -- be flagged yet abstain when there's no priced market).
    layer4_h2h_conviction_flag     BOOLEAN,  -- TRUE when |cal_win − p_run_diff| <= 0.02
    layer4_h2h_conviction_disagree FLOAT,    -- |cal_win − p_run_diff| (kept for threshold tuning)

    -- A2.5 — per-game imputation transparency. From the PRE-imputation matrix:
    -- which model features were NULL and got median/constant-imputed. The
    -- discriminative_* columns track only the UNCONDITIONAL-CORE discriminative set
    -- (ELO, bullpen-EB, team-sequential, RISP/runners-on, park) — the serving-health
    -- signal that catches the 2026-06 incident WITHOUT re-flagging the expected
    -- pre-lineup absence of lineup-/pitcher-gated features (those are shown via the
    -- Lineups column + the per-driver 'imputed' marking in Game Insights instead).
    imputed_feature_count        INTEGER,      -- ALL model features imputed for this game (broad; includes lineup-gated)
    imputed_discriminative_count INTEGER,      -- of the ~27 unconditional-core discriminative features, how many imputed
    discriminative_coverage      FLOAT,        -- 1 - imputed_core / total_core (1.0 = every core signal served)
    is_degraded                  BOOLEAN,      -- discriminative_coverage < 0.85 → serving-degraded pick (NOT just pre-lineup)
    imputed_features             VARCHAR(4000), -- comma-joined imputed CORE discriminative feature names (truncated)

    -- A1 — row-level qualification flag. TRUE when either market has an actionable
    -- (non-abstain) layer4 decision. Used by /picks/history to filter to real signals.
    qualified_bet                BOOLEAN,
    -- Story 30.7 — explicit provenance flag. TRUE only for rows backfilled after a
    -- promotion; live (real-time, pre-game) rows are FALSE. Replaces the overloaded
    -- use of prediction_type='backfill'; prediction_type now means live-timing only.
    is_backfill                  BOOLEAN  DEFAULT FALSE
)
"""

_INSERT_PREDICTION = f"""
INSERT INTO {_ML_SCHEMA}.daily_model_predictions (
    model_version, inserted_at, score_date, prediction_type, lineup_confirmed,
    game_pk, game_date, game_datetime,
    home_team, away_team, home_team_abbrev, away_team_abbrev,
    has_odds,
    p_home_win_ngboost, p_home_win_classifier, consensus_win_prob, calibrated_win_prob, pick,
    pred_total_runs, pred_total_runs_scale,
    pred_run_diff_loc, pred_run_diff_scale,
    p_over_ngboost,
    alpha,
    h2h_market_implied_prob, h2h_posterior_prob, h2h_edge, h2h_kelly_fraction,
    total_line_consensus, over_prob_consensus,
    totals_model_prob, totals_posterior_prob, totals_edge, totals_kelly_fraction,
    posterior_source, prior_age_days,
    layer4_totals_decision, layer4_totals_over_signal,
    layer4_h2h_decision, layer4_h2h_rule, layer4_h2h_edge,
    layer4_h2h_conviction_flag, layer4_h2h_conviction_disagree,
    bullpen_z_score_home, bullpen_z_score_away, bullpen_signal_ood,
    data_source, feature_coverage_score,
    layer4_h2h_bovada_ml_home, layer4_h2h_bovada_ml_away,
    imputed_feature_count, imputed_discriminative_count,
    discriminative_coverage, is_degraded, imputed_features,
    qualified_bet,
    is_backfill
) VALUES (
    %(model_version)s, %(inserted_at)s, %(score_date)s, %(prediction_type)s, %(lineup_confirmed)s,
    %(game_pk)s, %(game_date)s, %(game_datetime)s,
    %(home_team)s, %(away_team)s, %(home_team_abbrev)s, %(away_team_abbrev)s,
    %(has_odds)s,
    %(p_home_win_ngboost)s, %(p_home_win_classifier)s, %(consensus_win_prob)s, %(calibrated_win_prob)s, %(pick)s,
    %(pred_total_runs)s, %(pred_total_runs_scale)s,
    %(pred_run_diff_loc)s, %(pred_run_diff_scale)s,
    %(p_over_ngboost)s,
    %(alpha)s,
    %(h2h_market_implied_prob)s, %(h2h_posterior_prob)s, %(h2h_edge)s, %(h2h_kelly_fraction)s,
    %(total_line_consensus)s, %(over_prob_consensus)s,
    %(totals_model_prob)s, %(totals_posterior_prob)s, %(totals_edge)s, %(totals_kelly_fraction)s,
    %(posterior_source)s, %(prior_age_days)s,
    %(layer4_totals_decision)s, %(layer4_totals_over_signal)s,
    %(layer4_h2h_decision)s, %(layer4_h2h_rule)s, %(layer4_h2h_edge)s,
    %(layer4_h2h_conviction_flag)s, %(layer4_h2h_conviction_disagree)s,
    %(bullpen_z_score_home)s, %(bullpen_z_score_away)s, %(bullpen_signal_ood)s,
    %(data_source)s, %(feature_coverage_score)s,
    %(layer4_h2h_bovada_ml_home)s, %(layer4_h2h_bovada_ml_away)s,
    %(imputed_feature_count)s, %(imputed_discriminative_count)s,
    %(discriminative_coverage)s, %(is_degraded)s, %(imputed_features)s,
    %(qualified_bet)s,
    %(is_backfill)s
)
"""


# Epic 16.2 — game-level posterior provenance for the scoring date. Aggregates the
# per-player posterior_source / prior_age_days (eb_batter_posteriors_raw + the starter
# table, written by the as-of injection in compute_*_posteriors) up to game grain:
#   prior_age_days   = MAX over the game's batters+starters (the stalest belief; the
#                      >7 flag raises game_uncertainty_score in the Epic 19 gate).
#   posterior_source = least-informed source present (prior_only > season_eb >
#                      sequential) — flags games carrying a debut/cold-start player.
_POSTERIOR_PROVENANCE_QUERY = """
with prov as (
    select game_pk, posterior_source, prior_age_days
    from baseball_data.betting.eb_batter_posteriors_raw where game_date = %(d)s
    union all
    select game_pk, posterior_source, prior_age_days
    from baseball_data.betting.eb_starter_posteriors where game_date = %(d)s
)
select game_pk,
    max(prior_age_days) as max_prior_age_days,
    case when count_if(posterior_source = 'prior_only') > 0 then 'prior_only'
         when count_if(posterior_source = 'season_eb')  > 0 then 'season_eb'
         when count_if(posterior_source = 'sequential') > 0 then 'sequential'
         else null end as posterior_source
from prov
where game_pk is not null
group by game_pk
"""


# Epic 19 / Story 17.1b — bullpen OOD gate. Loads bullpen_mu_v2 for each (game_pk, side)
# from feature_pregame_sub_model_signals, pivots to game grain (home + away), returns
# {game_pk: {"bullpen_mu_home": float, "bullpen_mu_away": float}}.
# Graceful: returns empty dict when table is unpopulated for the target date.
_BULLPEN_OOD_QUERY = """
select s.game_pk,
    max(case when s.side = 'home' then s.bullpen_mu_v2 end) as bullpen_mu_home,
    max(case when s.side = 'away' then s.bullpen_mu_v2 end) as bullpen_mu_away
from baseball_data.betting_features.feature_pregame_sub_model_signals s
where s.game_pk in (
    select game_pk
    from baseball_data.betting_features.feature_pregame_game_features
    where game_date = %(d)s
)
group by s.game_pk
"""


def _load_bullpen_ood_signals(target_date: str) -> dict[int, dict]:
    """{game_pk: {"bullpen_mu_home": float, "bullpen_mu_away": float}} for today.

    Used by the Epic 19 bullpen OOD gate in compute_bet_permission(). Returns
    empty dict on any failure — OOD gate then produces None z-scores (no block)."""
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_BULLPEN_OOD_QUERY, {"d": target_date})
            out: dict[int, dict] = {}
            for gpk, mu_home, mu_away in cur.fetchall():
                out[int(gpk)] = {
                    "bullpen_mu_home": float(mu_home) if mu_home is not None else None,
                    "bullpen_mu_away": float(mu_away) if mu_away is not None else None,
                }
            print(f"  [Epic 19] Loaded bullpen OOD signals for {len(out)} game(s).")
            return out
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [Epic 19] bullpen OOD signals unavailable ({exc}); OOD gate will not fire.")
        return {}


# Story 28.3 — latest Bovada American moneyline odds (not de-vigged) per game_pk.
# Used as the "real-book price taken" column for the magnitude kill-criterion monitor.
# Joins through mart_game_odds_bridge because mart_odds_outcomes is keyed by event_id.
_BOVADA_ML_QUERY = """
WITH bridge AS (
    SELECT game_pk, event_id
    FROM baseball_data.betting.mart_game_odds_bridge
    WHERE game_date = %(d)s
),
latest_bovada AS (
    SELECT
        o.event_id,
        MAX(CASE WHEN o.is_home_outcome THEN o.outcome_price_american END) AS bovada_ml_home,
        MAX(CASE WHEN NOT o.is_home_outcome THEN o.outcome_price_american END) AS bovada_ml_away
    FROM baseball_data.betting.mart_odds_outcomes o
    INNER JOIN bridge b ON b.event_id = o.event_id
    WHERE o.bookmaker_key = 'bovada'
      AND o.market_key = 'h2h'
    GROUP BY o.event_id
    QUALIFY ROW_NUMBER() OVER (PARTITION BY o.event_id ORDER BY MAX(o.ingestion_ts) DESC) = 1
)
SELECT b.game_pk,
       lb.bovada_ml_home,
       lb.bovada_ml_away
FROM bridge b
JOIN latest_bovada lb ON lb.event_id = b.event_id
"""


def _load_bovada_ml_odds(target_date: str) -> dict[int, dict]:
    """{game_pk: {"bovada_ml_home": int, "bovada_ml_away": int}} for scoring date.

    Story 28.3: captures the actual Bovada American moneyline at scoring time so the
    magnitude kill-criterion monitor can compute real-book ROI, not vig-free estimates.
    Graceful — returns empty dict on any failure so scoring is never blocked."""
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_BOVADA_ML_QUERY, {"d": target_date})
            out: dict[int, dict] = {}
            for gpk, ml_home, ml_away in cur.fetchall():
                out[int(gpk)] = {
                    "bovada_ml_home": int(ml_home) if ml_home is not None else None,
                    "bovada_ml_away": int(ml_away) if ml_away is not None else None,
                }
            print(f"  [28.3] Loaded Bovada ML odds for {len(out)} game(s).")
            return out
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [28.3] Bovada ML odds unavailable ({exc}); columns will be NULL.")
        return {}


def _load_posterior_provenance(target_date: str) -> dict[int, dict]:
    """{game_pk: {prior_age_days, posterior_source}} for the scoring date (Epic 16.2).

    Empty dict if the EB tables aren't yet populated for the date (graceful — the
    columns then write NULL). Read-only; never blocks scoring."""
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_POSTERIOR_PROVENANCE_QUERY, {"d": target_date})
            out: dict[int, dict] = {}
            for gpk, max_age, src in cur.fetchall():
                out[int(gpk)] = {
                    "prior_age_days": int(max_age) if max_age is not None else None,
                    "posterior_source": src,
                }
            return out
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [16.2] posterior provenance unavailable ({exc}); columns will be NULL.")
        return {}


# A1.10 — feature-source coverage. Representative column(s) per feature block; a
# block is "covered" for a game when all its columns are non-null. The score is
# the fraction of blocks covered (0.0–1.0), written per-row to
# daily_model_predictions so any degradation (e.g. an intraday_fallback day or a
# regressed re-spine in A1.11) is observable rather than silent.
_FEATURE_COVERAGE_BLOCKS = {
    "lineup":       ["home_avg_eb_woba", "away_avg_eb_woba"],
    "starter":      ["home_starter_eb_xwoba_against", "away_starter_eb_xwoba_against"],
    "team_rolling": ["home_off_woba_30d", "away_off_woba_30d"],
    "bullpen_eb":   ["home_bp_eb_xwoba", "away_bp_eb_xwoba"],
    "sequential":   ["home_team_sequential_woba", "away_team_sequential_woba"],
    "odds":         ["over_prob_consensus"],
}


def _feature_coverage_score(df: pd.DataFrame, i: int) -> float:
    """Fraction of feature blocks populated for game-row i (A1.10)."""
    covered = 0
    for cols in _FEATURE_COVERAGE_BLOCKS.values():
        if all(c in df.columns and pd.notna(df.iloc[i][c]) for c in cols):
            covered += 1
    return round(covered / len(_FEATURE_COVERAGE_BLOCKS), 3)


# A2.5 — discriminative coverage is the SERVING-HEALTH signal. It must catch the
# 2026-06 incident (features that should be carried forward for every scheduled game
# went NULL across the slate → constant-imputed → home_win corr collapsed to ~0)
# WITHOUT crying wolf on features that are *legitimately* absent until a lineup or
# probable pitcher is announced. So the floor is computed over the UNCONDITIONAL-CORE
# discriminative families only — ones with no valid reason to be null for any
# scheduled MLB game: ELO ratings, bullpen empirical-Bayes quality, team sequential
# posteriors, team RISP / runners-on splits, and the park run environment.
#
# DELIBERATELY EXCLUDED here: the lineup-gated families (lineup archetype / cluster /
# vs-starter / h2h, and the lineup-EB aggregates like `*_avg_eb_woba`) and the
# pitcher-gated starter-EB. Their absence pre-lineup is EXPECTED, not a serving
# failure, and is already surfaced by the Lineups column and the per-driver 'imputed'
# marking in Game Insights — folding them in here would just re-flag every pre-lineup
# pick as "degraded" (observed 2026-06-10: 5/15 morning games, all lineup-gated).
# Token-boundary on `elo` so it does NOT match `..._velo`.
_DISCRIMINATIVE_RE = re.compile(
    r"(?:^|_)elo(?:_|$)"           # ELO ratings + diff
    r"|bp_eb"                      # bullpen empirical-Bayes quality
    r"|team_sequential"            # team-level sequential posteriors
    r"|with_risp|with_runners_on"  # team RISP / runners-on splits
    r"|park_run_factor|runs_per_game_at_park",  # park run environment
    re.I,
)

# Below this fraction of unconditional-core discriminative features served
# (non-imputed) for a game, the pick is flagged `is_degraded`. The healthy steady
# state imputes 0 of ~27 core features (coverage = 1.0); the incident imputed ~all of
# them (coverage ≈ 0). 0.85 flags genuine collapse (≥4 core features missing) without
# nagging on a routine single-feature gap, which is still surfaced via the count.
_DISC_COVERAGE_FLOOR = 0.85


def _discriminative_cols(cols: list[str]) -> list[str]:
    """Subset of `cols` in the unconditional-core discriminative set (A2.5).

    Used as the coverage-floor / degraded-flag basis — the serving-health signal.
    NOT the same as "every matchup feature": lineup-/pitcher-gated families are
    excluded by design (see the regex comment) so the flag isolates genuine serving
    failure from the expected pre-lineup absence the Lineups column already shows.
    """
    return [c for c in cols if _DISCRIMINATIVE_RE.search(c)]


def _build_imputation_summary(
    X_raw: pd.DataFrame, model_cols: list[str], disc_cols: list[str]
) -> list[dict]:
    """Per-game imputation transparency from the PRE-imputation matrix (A2.5).

    `X_raw` carries real NaN for any feature that wasn't served (it is imputed to a
    median/constant downstream). For each row we record how many model features and
    how many *discriminative* features were null, the discriminative coverage, the
    degraded flag, and the (truncated) list of imputed discriminative feature names.
    Row order matches `X_raw` / `df_today`, so the writer indexes it by position.
    """
    model_cols = [c for c in model_cols if c in X_raw.columns]
    disc_cols = [c for c in disc_cols if c in X_raw.columns]
    n_disc = len(disc_cols)
    out: list[dict] = []
    for i in range(len(X_raw)):
        row = X_raw.iloc[i]
        imputed_all = [c for c in model_cols if pd.isna(row[c])]
        imputed_disc = [c for c in disc_cols if pd.isna(row[c])]
        cov = round(1.0 - len(imputed_disc) / n_disc, 3) if n_disc else 1.0
        names = ",".join(sorted(imputed_disc))
        if len(names) > 3900:  # keep within VARCHAR(4000)
            names = names[:3900] + ",…"
        out.append({
            "imputed_feature_count":        len(imputed_all),
            "imputed_discriminative_count": len(imputed_disc),
            "discriminative_coverage":      cov,
            "is_degraded":                  bool(n_disc and cov < _DISC_COVERAGE_FLOOR),
            "imputed_features":             names or None,
        })
    return out


def _post_lineup_delete_sql(schema: str, scoped_game_pks: list[int] | None) -> str:
    """Build the overwrite DELETE for a post_lineup re-score.

    A1.12 — when a ``--game-pks`` subset was scored, scope the DELETE to those
    game_pks so a partial re-score (e.g. the lineup sensor firing for one
    newly-confirmed game) doesn't wipe every OTHER game's post_lineup row for the
    date. A full-slate run (``scoped_game_pks`` falsy) keeps the date-wide
    overwrite so dropped/postponed games are cleaned up. game_pks are ints (cast
    at parse time), so inlining them is injection-safe.
    """
    base = (
        f"DELETE FROM {schema}.daily_model_predictions "
        f"WHERE score_date = %(d)s AND prediction_type = %(pt)s"
    )
    if scoped_game_pks:
        pk_list = ", ".join(str(int(pk)) for pk in scoped_game_pks)
        return f"{base} AND game_pk IN ({pk_list})"
    return base


def _serving_degraded(imp_summ: dict | None, has_full_data_val) -> tuple[bool, str]:
    """Story 30.3 — per-game SERVING-HEALTH gate for the ACTIONABLE edge path.

    Returns (degraded, reason). A degraded matrix means the model scored a
    VALUE-degraded row, so its posterior is untrustworthy and NO actionable
    edge/Kelly should be surfaced — the same stance the global ``best_alpha==0``
    EDGE-GUARD takes, applied per game (and mirroring the no-odds abstain).

    Two genuine-degradation conditions (NOT ordinary pre-lineup absence):
      1. ``is_degraded`` — the unconditional-CORE discriminative families
         (ELO / bullpen-EB / team-sequential / RISP / park) collapsed below the
         coverage floor. These have no valid reason to be null for any scheduled
         game, so their absence is a serving failure (the 2026-05-29 / 06-10
         carry-forward incidents), not the expected pre-lineup sparseness.
      2. ``has_full_data is False`` — the game is OUTSIDE the training admission
         criteria (`_QUERY` requires has_full_data=TRUE). The serve query
         `_TODAY_QUERY` applies no such filter, so it scores ~8% of games the
         model never saw the distribution of; their strong-tier null rate is
         2–4× higher (Story 30.3 parity report §4). Abstain rather than bet a
         posterior from an out-of-distribution matrix.

    Deliberately does NOT fire on a normal morning pre-lineup pick: the
    lineup-/pitcher-gated families excluded from `is_degraded` are EXPECTED to be
    null before lineups post (that is a TIMING question owned by the Epic A1 SLA,
    not a serving defect). Pure (no I/O) so it is unit-testable.
    """
    reasons: list[str] = []
    if imp_summ and imp_summ.get("is_degraded"):
        reasons.append(f"core-collapse (disc_cov={imp_summ.get('discriminative_coverage')})")
    if has_full_data_val is False:
        reasons.append("has_full_data=FALSE (out-of-training-distribution)")
    return (bool(reasons), "; ".join(reasons))


def _lineups_confirmed(df: pd.DataFrame, i: int) -> bool | None:
    """Story 30.3 — are BOTH lineups confirmed for game-row i?

    Returns True/False, or None when the flags aren't served (→ caller does not
    gate on lineup state). This is the "is this the DENSE serve" signal: the
    morning matrix is ~30% imputed because the lineup-/pitcher-gated families
    aren't known pre-lineup; once both lineups post, the post_lineup re-score
    serves them. The actionable bet should ride the dense post_lineup pass, so a
    pre-lineup (unconfirmed) game defers its edge to that re-score rather than
    surfacing one off the sparse morning matrix (Story 30.3: live skill ≈ 0 there).
    NaN/None flags count as NOT confirmed.
    """
    cols = ("home_has_full_lineup", "away_has_full_lineup")
    if not all(c in df.columns for c in cols):
        return None
    return all((lambda v: pd.notna(v) and bool(v))(df.iloc[i][c]) for c in cols)


def _write_predictions_to_snowflake(
    df_today: pd.DataFrame,
    target_date: str,
    inserted_at: datetime,
    prediction_type: str,
    lineup_confirmed: bool,
    scoped_game_pks: list[int] | None,
    is_backfill: bool,
    p_home_win_ngb: np.ndarray,
    p_home_win_clf: np.ndarray,
    loc_tot: np.ndarray,
    scale_tot: np.ndarray,
    loc_diff: np.ndarray,
    scale_diff: np.ndarray,
    p_over_total: np.ndarray,
    h2h_mkt: np.ndarray,
    over_mkt: np.ndarray,
    total_line_vals: np.ndarray,
    has_odds_col: pd.Series,
    best_alpha: float,
    picks: list[str],
    imputation_summary: list[dict] | None = None,
) -> None:
    def _f(arr, i) -> float | None:
        v = arr[i]
        return None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)

    def _s(df, col, i):
        if col not in df.columns:
            return None
        v = df.iloc[i][col]
        if pd.isna(v):
            return None
        return v.item() if hasattr(v, "item") else v

    def _sanitize(row: dict) -> dict:
        return {
            k: (None if isinstance(v, float) and v != v else v)
            for k, v in row.items()
        }

    rows: list[dict] = []
    score_date = date.fromisoformat(target_date)
    prov = _load_posterior_provenance(target_date)  # Epic 16.2 — game-level posterior provenance
    bullpen_ood_signals = _load_bullpen_ood_signals(target_date)  # Epic 19 — bullpen OOD gate
    bovada_ml = _load_bovada_ml_odds(target_date)  # Story 28.3 — actual Bovada ML for kill-criterion monitor
    _n_serving_guard = 0    # Story 30.3 — games abstained for value-degraded serving
    _n_lineup_deferred = 0  # Story 30.3 — pre-lineup games whose edge defers to the post_lineup re-score

    for i in range(len(df_today)):
        has_odds = bool(has_odds_col.iloc[i])
        ngb_win  = float(p_home_win_ngb[i])
        clf_win  = float(p_home_win_clf[i])
        cons_win = ngb_win * 0.5 + clf_win * 0.5
        cal_win  = _apply_calibrator(cons_win)

        # Story 30.3 — SERVING-HEALTH gate. Compute BEFORE the edge math so a
        # value-degraded matrix (core-feature collapse or an out-of-training game)
        # abstains the actionable edge/Kelly instead of surfacing a phantom bet
        # from an untrustworthy posterior. Raw diagnostic edges + model probs are
        # preserved (CLV / Layer-4 monitoring is unaffected).
        _imp_i = imputation_summary[i] if (imputation_summary and i < len(imputation_summary)) else None
        _hfd_i = _s(df_today, "has_full_data", i)
        game_degraded, _degraded_reason = _serving_degraded(_imp_i, _hfd_i)
        # Bind the actionable bet to the DENSE post_lineup serve: a pre-lineup
        # (unconfirmed) game defers its edge to the post_lineup re-score rather than
        # surfacing one off the ~30%-imputed morning matrix. None = flags unserved
        # → don't gate on lineup state (fail-open to prior behavior).
        _lineups_ok = _lineups_confirmed(df_today, i)
        lineup_deferred = (_lineups_ok is False) and not game_degraded
        game_actionable = (not game_degraded) and (_lineups_ok is not False)
        if game_degraded:
            _n_serving_guard += 1
        if lineup_deferred:
            _n_lineup_deferred += 1

        # H2H market values — use calibrated_win_prob as the live edge input.
        # A2.5 edge-artifact guard: the STORED/actionable edge is alpha-aware
        # (posterior − market), so when best_alpha=0 the model adds no skill and the
        # edge/Kelly collapse to ~0 — no phantom "bet every home underdog" picks. The
        # raw model-vs-market gap is preserved separately for Layer 4 / CLV diagnostics.
        h2h_mkt_v  = _f(h2h_mkt, i)
        if has_odds and h2h_mkt_v is not None:
            h2h_raw_edge = compute_edge(cal_win, h2h_mkt_v)        # diagnostic only (preserved when not actionable)
            if not game_actionable:
                # Abstain: degraded matrix (untrustworthy posterior) OR pre-lineup
                # (defer to the dense post_lineup re-score) → no actionable bet.
                h2h_post = h2h_edge = h2h_kelly = None
            else:
                h2h_post  = compute_posterior(cal_win, h2h_mkt_v, best_alpha)
                h2h_edge  = compute_actionable_edge(cal_win, h2h_mkt_v, best_alpha)
                h2h_kelly = compute_kelly(h2h_edge, h2h_mkt_v)
        else:
            h2h_raw_edge = h2h_edge = h2h_post = h2h_kelly = None

        # Totals market values
        over_mkt_v    = _f(over_mkt, i)
        total_line_v  = _f(total_line_vals, i)
        p_over_v      = float(p_over_total[i])
        if has_odds and over_mkt_v is not None and game_actionable:
            tot_post  = compute_posterior(p_over_v, over_mkt_v, best_alpha)
            tot_edge  = compute_actionable_edge(p_over_v, over_mkt_v, best_alpha)
            tot_kelly = compute_kelly(tot_edge, over_mkt_v)
        else:
            tot_edge = tot_post = tot_kelly = None

        # Layer 4 — live selective-strategy attribution (what the rule recommends).
        # Pure logging: any failure here must NEVER abort the core prediction write,
        # so it's fully guarded and falls back to NULL on error.
        l4_tot_decision = l4_tot_signal = l4_h2h_decision = l4_h2h_rule = l4_h2h_edge = None
        l4_h2h_conviction_flag = l4_h2h_conviction_disagree = None
        try:
            # Totals: model mu vs the book line at the 1.0-run threshold; abstain w/o a line.
            l4_line = total_line_v if has_odds else None
            l4_tot_signal = (float(loc_tot[i]) - l4_line) if l4_line is not None else None
            l4_tot_decision, _ = compute_bet_decision(
                "totals", model_mu=float(loc_tot[i]), total_line=l4_line,
                totals_mu_threshold=DEFAULT_TOTALS_MU_THRESHOLD)
            # H2H: deployed model P(home) = calibrated_win_prob vs de-vigged market home prob.
            l4_h2h_decision, l4_h2h_rule = compute_bet_decision(
                "h2h", model_p_home=cal_win,
                market_p_home=(h2h_mkt_v if has_odds else None),
                h2h_magnitude_threshold=DEFAULT_H2H_MAGNITUDE_THRESHOLD)
            l4_h2h_edge = h2h_raw_edge  # raw cal_win - h2h_mkt_v (Layer-4 magnitude; None when no odds)
            # Story 28.6b — conviction gate: agreement of the two INDEPENDENT estimators.
            # P_run_diff(home) = Φ(μ/σ) = P(run_diff > 0); Φ(x) = 0.5·erfc(−x/√2).
            _sd = float(scale_diff[i])
            _z = (float(loc_diff[i]) / _sd) if _sd else 0.0
            _p_run_diff = 0.5 * math.erfc(-_z / math.sqrt(2.0))
            l4_h2h_conviction_disagree = abs(float(cal_win) - _p_run_diff)
            l4_h2h_conviction_flag = bool(l4_h2h_conviction_disagree <= 0.02)
        except Exception as _l4_exc:
            print(f"  Warning: Layer 4 attribution failed for game index {i} "
                  f"({_l4_exc}); logging NULLs.")

        raw_dt = _s(df_today, "game_datetime", i)
        game_dt: datetime | None = None
        if raw_dt is not None:
            try:
                game_dt = pd.Timestamp(raw_dt).to_pydatetime().replace(tzinfo=None)
            except Exception:
                pass

        gpk_val = _s(df_today, "game_pk", i)
        game_prov = prov.get(int(gpk_val)) if gpk_val is not None else None
        game_bullpen = bullpen_ood_signals.get(int(gpk_val)) if gpk_val is not None else None
        game_bovada = bovada_ml.get(int(gpk_val)) if gpk_val is not None else None
        imp_summ = _imp_i  # Story 30.3 — computed above for the serving-health gate

        # Epic 19 bullpen OOD gate — compute permission and extract OOD fields
        ood_row = {
            "bullpen_mu_home": (game_bullpen or {}).get("bullpen_mu_home"),
            "bullpen_mu_away": (game_bullpen or {}).get("bullpen_mu_away"),
            "pred_total_runs": float(loc_tot[i]),
            "total_line_consensus": total_line_vals[i] if has_odds else None,
        }
        gate_result = compute_bet_permission(str(gpk_val), ood_row)

        rows.append(_sanitize({
            "model_version":          MODEL_VERSION,
            "inserted_at":            inserted_at,
            "score_date":             score_date,
            "prediction_type":        prediction_type,
            "lineup_confirmed":       lineup_confirmed,
            "game_pk":                gpk_val,
            "game_date":              score_date,
            "game_datetime":          game_dt,
            "home_team":              _s(df_today, "home_name", i) or _s(df_today, "home_team", i),
            "away_team":              _s(df_today, "away_name", i) or _s(df_today, "away_team", i),
            "home_team_abbrev":       _s(df_today, "home_team_abbrev", i) or _s(df_today, "home_abbr", i),
            "away_team_abbrev":       _s(df_today, "away_team_abbrev", i) or _s(df_today, "away_abbr", i),
            "has_odds":               has_odds,
            "p_home_win_ngboost":     ngb_win,
            "p_home_win_classifier":  clf_win,
            "consensus_win_prob":     cons_win,
            "calibrated_win_prob":    cal_win,
            "pick":                   picks[i],
            "pred_total_runs":        float(loc_tot[i]),
            "pred_total_runs_scale":  float(scale_tot[i]),
            "pred_run_diff_loc":      float(loc_diff[i]),
            "pred_run_diff_scale":    float(scale_diff[i]),
            "p_over_ngboost":         p_over_v,
            "alpha":                  best_alpha,
            "h2h_market_implied_prob": h2h_mkt_v if has_odds else None,
            "h2h_posterior_prob":     h2h_post,
            "h2h_edge":               h2h_edge,
            "h2h_kelly_fraction":     h2h_kelly,
            "total_line_consensus":   total_line_v if has_odds else None,
            "over_prob_consensus":    over_mkt_v if has_odds else None,
            "totals_model_prob":      p_over_v if has_odds else None,
            "totals_posterior_prob":  tot_post,
            "totals_edge":            tot_edge,
            "totals_kelly_fraction":  tot_kelly,
            "posterior_source":       (game_prov or {}).get("posterior_source"),
            "prior_age_days":         (game_prov or {}).get("prior_age_days"),
            "layer4_totals_decision":    l4_tot_decision,
            "layer4_totals_over_signal": l4_tot_signal,
            "layer4_h2h_decision":       l4_h2h_decision,
            "layer4_h2h_rule":           l4_h2h_rule,
            "layer4_h2h_edge":           l4_h2h_edge,
            "layer4_h2h_conviction_flag":     l4_h2h_conviction_flag,
            "layer4_h2h_conviction_disagree": l4_h2h_conviction_disagree,
            "bullpen_z_score_home":      gate_result.get("bullpen_z_score_home"),
            "bullpen_z_score_away":      gate_result.get("bullpen_z_score_away"),
            "bullpen_signal_ood":        gate_result.get("bullpen_signal_ood", False),
            # A1.10 — feature-source observability
            "data_source":               _s(df_today, "data_source", i),
            "feature_coverage_score":    _feature_coverage_score(df_today, i),
            # Story 28.3 — actual Bovada American moneyline (not de-vig) for kill-criterion monitor
            "layer4_h2h_bovada_ml_home": (game_bovada or {}).get("bovada_ml_home"),
            "layer4_h2h_bovada_ml_away": (game_bovada or {}).get("bovada_ml_away"),
            # A2.5 — per-game imputation transparency (None-safe when summary absent)
            "imputed_feature_count":        (imp_summ or {}).get("imputed_feature_count"),
            "imputed_discriminative_count": (imp_summ or {}).get("imputed_discriminative_count"),
            "discriminative_coverage":      (imp_summ or {}).get("discriminative_coverage"),
            "is_degraded":                  (imp_summ or {}).get("is_degraded"),
            "imputed_features":             (imp_summ or {}).get("imputed_features"),
            "qualified_bet": (
                (l4_h2h_decision is not None and l4_h2h_decision != "abstain")
                or (l4_tot_decision is not None and l4_tot_decision != "abstain")
            ),
            "is_backfill": is_backfill,
        }))

    if _n_serving_guard:
        warnings.warn(
            f"[SERVING-GUARD] {_n_serving_guard}/{len(df_today)} game(s) had their actionable "
            f"h2h/totals edge + Kelly ABSTAINED (set NULL) because the served matrix was "
            f"value-degraded (unconditional-core collapse and/or has_full_data=FALSE). The model "
            f"probabilities and raw diagnostic edges are still written for monitoring; only the "
            f"actionable bet is suppressed (Story 30.3 — same stance as the best_alpha=0 guard, "
            f"applied per game).",
            stacklevel=2,
        )
    if _n_lineup_deferred:
        print(
            f"[SERVING-GUARD] {_n_lineup_deferred}/{len(df_today)} game(s) are PRE-LINEUP "
            f"(lineups not both confirmed) — actionable edge/Kelly deferred to the dense "
            f"post_lineup re-score (Story 30.3: the morning matrix is ~30% imputed; the live "
            f"bet rides the post_lineup pass). Model probabilities + raw diagnostic edges still "
            f"written. This is expected on the morning run and clears as lineups post."
        )

    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_CREATE_PREDICTIONS_TABLE)
            # Idempotent column migrations — safe on every scoring pass.
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS posterior_source VARCHAR(20)")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS prior_age_days INTEGER")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_totals_decision VARCHAR(10)")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_totals_over_signal FLOAT")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_decision VARCHAR(10)")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_rule VARCHAR(20)")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_edge FLOAT")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS lineup_confirmed BOOLEAN")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS bullpen_z_score_home FLOAT")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS bullpen_z_score_away FLOAT")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS bullpen_signal_ood BOOLEAN")
            # A1.10 — feature-source observability
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS data_source VARCHAR(20)")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS feature_coverage_score FLOAT")
            # Story 28.3 — actual Bovada American moneyline for kill-criterion monitor
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_bovada_ml_home INTEGER")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_bovada_ml_away INTEGER")
            # Story 28.6b — conviction-gate overlay (self-healing across dev/prod schemas)
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_conviction_flag BOOLEAN")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS layer4_h2h_conviction_disagree FLOAT")
            # A2.5 — per-game imputation transparency
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS imputed_feature_count INTEGER")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS imputed_discriminative_count INTEGER")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS discriminative_coverage FLOAT")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS is_degraded BOOLEAN")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS imputed_features VARCHAR(4000)")
            cur.execute(f"ALTER TABLE {_ML_SCHEMA}.daily_model_predictions ADD COLUMN IF NOT EXISTS qualified_bet BOOLEAN")
            # A1.2 — overwrite semantics for post_lineup + lineup_confirmed runs:
            # delete existing rows for this date+type before inserting so re-runs
            # (pitcher changes, sensor re-fires) don't accumulate duplicate rows.
            if lineup_confirmed:
                cur.execute(
                    _post_lineup_delete_sql(_ML_SCHEMA, scoped_game_pks),
                    {"d": target_date, "pt": prediction_type},
                )
                _scope = (f"game_pks {sorted(scoped_game_pks)} (scoped overwrite)"
                          if scoped_game_pks else "(full-slate overwrite)")
                print(f"  Deleted existing {prediction_type} rows for {target_date} {_scope}")
            if is_backfill:
                # Story 30.7 — idempotent backfill: clear ONLY prior is_backfill rows of THIS
                # model_version for this date, so re-runs don't accumulate duplicates. Scoped by
                # (score_date, model_version, is_backfill=TRUE) → never touches live rows
                # (is_backfill=FALSE) or any other version's backfill.
                cur.execute(
                    f"DELETE FROM {_ML_SCHEMA}.daily_model_predictions "
                    f"WHERE score_date = %(d)s AND model_version = %(mv)s AND is_backfill = TRUE",
                    {"d": target_date, "mv": MODEL_VERSION},
                )
                print(f"  [is_backfill] cleared prior backfill rows for {target_date} "
                      f"model_version={MODEL_VERSION} ({cur.rowcount} row(s))")
            cur.executemany(_INSERT_PREDICTION, rows)
            conn.commit()
            print(f"\nWrote {len(rows)} prediction row(s) to "
                  f"{_ML_SCHEMA}.daily_model_predictions "
                  f"(model_version={MODEL_VERSION}, inserted_at={inserted_at.isoformat()})")
        finally:
            conn.close()
    except Exception as exc:
        print(f"\nWarning: Could not write predictions to Snowflake ({exc}). "
              "Parquet output is still valid.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ngb_cfg(path: str, target_label: str) -> tuple[int, str]:
    p = PROJECT_ROOT / path
    if not p.exists():
        raise FileNotFoundError(
            f"NGBoost tuning results not found: {path}. "
            f"Run Card 4.12 hyperparameter search first."
        )
    with open(p) as f:
        cfg = json.load(f)
    for key in ("best_n_estimators", "best_dist"):
        if key not in cfg:
            raise KeyError(f"Required key '{key}' missing from {path} ({target_label})")
    return int(cfg["best_n_estimators"]), str(cfg["best_dist"])


def _load_best_alpha() -> float:
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT alpha FROM baseball_data.betting_ml.alpha_tuning_results "
                "ORDER BY loaded_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is not None:
                return float(row[0])
            print("Warning: alpha_tuning_results is empty; trying local cache")
        finally:
            conn.close()
    except Exception as exc:
        print(f"Warning: Could not load alpha from Snowflake ({exc}); trying local cache")

    cache_path = PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return float(json.load(f)["best_alpha"])

    print("Warning: best_alpha.json not found; using 0.5")
    return 0.5


_CREATE_PREDICTION_LOG = """
CREATE TABLE IF NOT EXISTS baseball_data.config.prediction_log (
    prediction_date           DATE        NOT NULL,
    game_pk                   INTEGER     NOT NULL,
    market                    VARCHAR(20) NOT NULL,
    model_prob                FLOAT,
    market_prob_at_prediction FLOAT,
    closing_market_prob       FLOAT,
    actual_outcome            INTEGER,
    decimal_odds              FLOAT,
    ev                        FLOAT,
    kelly_fraction            FLOAT,
    model_version             VARCHAR(20),
    loaded_at                 TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
)
"""

_INSERT_PREDICTION_LOG = """
INSERT INTO baseball_data.config.prediction_log (
    prediction_date, game_pk, market, model_prob, market_prob_at_prediction,
    closing_market_prob, actual_outcome, decimal_odds, ev, kelly_fraction,
    model_version
) VALUES (
    %(prediction_date)s, %(game_pk)s, %(market)s, %(model_prob)s,
    %(market_prob_at_prediction)s, %(closing_market_prob)s, %(actual_outcome)s,
    %(decimal_odds)s, %(ev)s, %(kelly_fraction)s, %(model_version)s
)
"""


def _write_prediction_log(output_rows: list[dict], prediction_date: str) -> None:
    rows = []
    pred_date = date.fromisoformat(prediction_date)
    for r in output_rows:
        mkt_prob = r.get("market_implied_prob")
        model_prob = r.get("model_prob")
        if mkt_prob and mkt_prob > 0:
            decimal_odds = 1.0 / mkt_prob
            ev = model_prob * (decimal_odds - 1) - (1 - model_prob) if model_prob is not None else None
        else:
            decimal_odds = None
            ev = None
        try:
            game_pk = int(r["game_key"])
        except (ValueError, TypeError):
            game_pk = None
        rows.append({
            "prediction_date":           pred_date,
            "game_pk":                   game_pk,
            "market":                    r.get("market"),
            "model_prob":                r.get("model_prob"),
            "market_prob_at_prediction": mkt_prob,
            "closing_market_prob":       None,
            "actual_outcome":            None,
            "decimal_odds":              decimal_odds,
            "ev":                        ev,
            "kelly_fraction":            r.get("implied_kelly_fraction"),
            "model_version":             MODEL_VERSION,
        })
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_CREATE_PREDICTION_LOG)
        cur.execute(
            f"DELETE FROM baseball_data.config.prediction_log "
            f"WHERE prediction_date = '{prediction_date}'"
        )
        if rows:
            cur.executemany(_INSERT_PREDICTION_LOG, rows)
        conn.commit()
        print(f"\nWrote {len(rows)} rows to prediction_log for {prediction_date}")
    finally:
        conn.close()


_BACKFILL_OUTCOME_H2H_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET actual_outcome = CASE WHEN mgr.home_team_won THEN 1.0 ELSE 0.0 END
FROM baseball_data.betting.mart_game_results mgr
WHERE pl.game_pk = mgr.game_pk
  AND pl.market = 'h2h'
  AND pl.actual_outcome IS NULL
"""

_BACKFILL_OUTCOME_TOTALS_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET actual_outcome = CASE
    WHEN (mgr.home_final_score + mgr.away_final_score) > fpof.total_line_consensus THEN 1.0
    WHEN (mgr.home_final_score + mgr.away_final_score) < fpof.total_line_consensus THEN 0.0
    ELSE NULL
END
FROM baseball_data.betting.mart_game_results mgr
JOIN baseball_data.betting_features.feature_pregame_odds_features fpof
    ON mgr.game_pk = fpof.game_pk
WHERE pl.game_pk = mgr.game_pk
  AND pl.market = 'totals'
  AND pl.actual_outcome IS NULL
  AND fpof.total_line_consensus IS NOT NULL
"""

_BACKFILL_CLOSING_H2H_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    JOIN (
        SELECT bridge2.game_pk, MAX(moe2.ingestion_ts) AS last_ts
        FROM baseball_data.betting.mart_odds_outcomes moe2
        JOIN baseball_data.betting.mart_game_odds_bridge bridge2 ON moe2.event_id = bridge2.event_id
        WHERE moe2.market_key = 'h2h'
          AND moe2.ingestion_ts < moe2.commence_time
        GROUP BY bridge2.game_pk
    ) ls ON bridge.game_pk = ls.game_pk AND moe.ingestion_ts = ls.last_ts
    WHERE moe.market_key = 'h2h'
      AND moe.is_home_outcome = TRUE
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'h2h'
  AND pl.closing_market_prob IS NULL
"""

_BACKFILL_CLOSING_TOTALS_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    JOIN (
        SELECT bridge2.game_pk, MAX(moe2.ingestion_ts) AS last_ts
        FROM baseball_data.betting.mart_odds_outcomes moe2
        JOIN baseball_data.betting.mart_game_odds_bridge bridge2 ON moe2.event_id = bridge2.event_id
        WHERE moe2.market_key = 'totals'
          AND moe2.ingestion_ts < moe2.commence_time
        GROUP BY bridge2.game_pk
    ) ls ON bridge.game_pk = ls.game_pk AND moe.ingestion_ts = ls.last_ts
    WHERE moe.market_key = 'totals'
      AND moe.outcome_name = 'Over'
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'totals'
  AND pl.closing_market_prob IS NULL
"""

_BACKFILL_CLOSING_H2H_FALLBACK_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    WHERE moe.market_key = 'h2h'
      AND moe.is_home_outcome = TRUE
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'h2h'
  AND pl.closing_market_prob IS NULL
"""

_BACKFILL_CLOSING_TOTALS_FALLBACK_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    WHERE moe.market_key = 'totals'
      AND moe.outcome_name = 'Over'
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'totals'
  AND pl.closing_market_prob IS NULL
"""


def _backfill_outcomes() -> None:
    """Backfill actual_outcome and closing_market_prob for settled games."""
    steps = [
        ("actual_outcome h2h",              _BACKFILL_OUTCOME_H2H_SQL),
        ("actual_outcome totals",           _BACKFILL_OUTCOME_TOTALS_SQL),
        ("closing_market_prob h2h",         _BACKFILL_CLOSING_H2H_SQL),
        ("closing_market_prob totals",      _BACKFILL_CLOSING_TOTALS_SQL),
        ("closing_market_prob h2h fallback",    _BACKFILL_CLOSING_H2H_FALLBACK_SQL),
        ("closing_market_prob totals fallback", _BACKFILL_CLOSING_TOTALS_FALLBACK_SQL),
    ]
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        for label, sql in steps:
            cur.execute(sql)
            print(f"  Backfill [{label}]: {cur.rowcount or 0} row(s) updated")
    finally:
        conn.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score today's MLB games using the Phase 5 production models."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=date.today().isoformat(),
        help="Target game date (default: today)",
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "RANGE mode: score every completed-game date from --start through --end "
            "(default today) in ONE process — the registry models, historical features, and "
            "imputation pipeline are built once and reused per date. Intended for the Story 30.7 "
            "backfill: combine with --is-backfill. Overrides --date when set."
        ),
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        default=None,
        help="RANGE mode end date (inclusive; default today). Only used with --start.",
    )
    parser.add_argument(
        "--no-log-snowflake",
        action="store_true",
        default=False,
        help="Skip writing to prediction_log (dry-run mode)",
    )
    parser.add_argument(
        "--game-pks",
        metavar="PK1,PK2,...",
        default=None,
        help="Comma-separated game_pks to score (default: all games on --date)",
    )
    parser.add_argument(
        "--prediction-type",
        choices=["morning", "post_lineup"],
        default="morning",
        help="Label written to prediction_type column (default: morning)",
    )
    parser.add_argument(
        "--lineup-confirmed",
        action="store_true",
        default=False,
        help=(
            "Mark predictions as lineup_confirmed=True and overwrite any existing "
            "rows for today's prediction_type before inserting. Use when lineups "
            "are confirmed (post-lineup re-run via lineup_monitor_sensor)."
        ),
    )
    parser.add_argument(
        "--is-backfill",
        action="store_true",
        default=False,
        help=(
            "Story 30.7 — mark these rows is_backfill=TRUE (generated after the fact for a "
            "historical --date, NOT served live). Idempotent: re-running a date deletes only "
            "the prior is_backfill rows of THIS model_version for that date (never live rows "
            "or other versions) before inserting. Use ONLY to backfill a promoted model over "
            "past games; never for live morning/post_lineup runs."
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Setup memoization — the registry models, the historical feature pull, and the
# fitted imputation pipeline are date-INDEPENDENT. Caching them lets a multi-date
# backfill (--start/--end) build them ONCE and reuse across every date instead of
# re-loading + re-fitting per date (the dominant cost). A single live --date run
# hits each cache exactly once, so behaviour is unchanged.
# ---------------------------------------------------------------------------

_PIPELINE_CACHE: dict = {}


@_functools.lru_cache(maxsize=2)
def _load_hist_features_cached(min_games_played: int) -> pd.DataFrame:
    return load_features(min_games_played=min_games_played)


@_functools.lru_cache(maxsize=8)
def _load_model_cached(target: str, variant: str):
    return load_model(target, variant)


def _fit_pipeline_cached(X_hist: pd.DataFrame):
    """Fit the imputation pipeline ONCE per (column-set) and cache (pipeline, imputed-cols).
    X_hist is derived from the cached historical frame, so the same column set means the
    same data → a cached fit is valid."""
    key = tuple(X_hist.columns)
    hit = _PIPELINE_CACHE.get(key)
    if hit is None:
        pipeline = build_imputation_pipeline()
        X_hist_imp = pipeline.fit_transform(X_hist)
        X_hist_imp = X_hist_imp.select_dtypes(include=[np.number])
        hit = (pipeline, X_hist_imp)
        _PIPELINE_CACHE[key] = hit
    return hit


def _resolve_target_dates(args) -> list[str]:
    """Single --date (default) or the list of completed-game dates in [--start, --end].
    Range mode powers the Story 30.7 backfill: one process, setup built once."""
    if not getattr(args, "start", None):
        return [args.date]
    end = args.end or date.today().isoformat()
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT game_date FROM baseball_data.betting.mart_game_results "
            "WHERE game_date BETWEEN %(s)s AND %(e)s "
            "AND home_final_score IS NOT NULL AND away_final_score IS NOT NULL "
            "ORDER BY game_date",
            {"s": args.start, "e": end},
        )
        dates = [r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])
                 for r in cur.fetchall()]
    finally:
        conn.close()
    print(f"Range mode: {len(dates)} completed-game date(s) {args.start} → {end}")
    return dates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(target_date: str, args) -> None:
    print(f"Scoring games for {target_date}")

    df_today = load_todays_features(target_date)

    if df_today.empty:
        print(f"No games found for {target_date}.")
        return

    print(f"  Found {len(df_today)} game(s) for {target_date}")

    # A1.12 — when --lineup-confirmed, restrict to games whose BOTH lineups are
    # actually posted today. Uses home/away_has_full_lineup (set per-game by the
    # feature store, and forced to reflect today's overlay by the intraday
    # assembly). The previous filter targeted home_lineup_slot_1/away_lineup_slot_1
    # which exist in NEITHER path, so it silently no-op'd and every scheduled game
    # was written as post_lineup / lineup_confirmed regardless of real status.
    # Gated on --lineup-confirmed so the morning (projected-lineup) run is unaffected.
    if args.lineup_confirmed:
        lineup_cols = ("home_has_full_lineup", "away_has_full_lineup")
        if all(c in df_today.columns for c in lineup_cols):
            before = len(df_today)
            df_today = df_today[
                df_today["home_has_full_lineup"].fillna(False).astype(bool)
                & df_today["away_has_full_lineup"].fillna(False).astype(bool)
            ]
            print(f"  Lineup-confirmed filter: {before} → {len(df_today)} game(s) with both lineups confirmed")
            if df_today.empty:
                print("No games with confirmed lineups found.")
                return
        else:
            print("[WARN] --lineup-confirmed set but has_full_lineup columns absent; not filtering.")

    scoped_game_pks: list[int] | None = None
    if args.game_pks:
        target_pks = {int(pk.strip()) for pk in args.game_pks.split(",") if pk.strip()}
        before = len(df_today)
        if "game_pk" in df_today.columns:
            df_today = df_today[df_today["game_pk"].isin(target_pks)]
        print(f"  game-pks filter: {before} → {len(df_today)} game(s) matching {sorted(target_pks)}")
        if df_today.empty:
            print("No matching games found for the specified game_pks.")
            return
        # A1.12 — remember the explicit subset so the post_lineup overwrite DELETE
        # is scoped to just these games (and doesn't wipe the rest of the slate).
        scoped_game_pks = sorted(int(pk) for pk in df_today["game_pk"].tolist())

    for col in ("has_odds", "home_win_prob_consensus"):
        if col not in df_today.columns:
            raise ValueError(
                f"Required column '{col}' not found in today's feature data. "
                f"Available columns: {sorted(df_today.columns.tolist())}"
            )

    # Load model registry once to get per-model dist and feature column paths.
    _registry_path = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
    with open(_registry_path) as _rf:
        _registry = yaml.safe_load(_rf)

    # Derive MODEL_VERSION from the registry so promotions are reflected automatically.
    global MODEL_VERSION
    MODEL_VERSION = _registry["home_win"]["model_version"]

    def _registry_feat_cols(target: str) -> list[str]:
        path = PROJECT_ROOT / _registry[target]["feature_columns_path"]
        with open(path) as _f:
            raw = json.load(_f)
        return raw["feature_cols"] if isinstance(raw, dict) else raw

    ngb_tot_dist  = _registry["total_runs"]["dist"]
    ngb_diff_dist = _registry["run_differential"]["dist"]
    tot_feat_cols  = _registry_feat_cols("total_runs")
    diff_feat_cols = _registry_feat_cols("run_differential")
    hw_feat_cols   = _registry_feat_cols("home_win")
    print(f"  total_runs dist={ngb_tot_dist}, features={len(tot_feat_cols)}")
    print(f"  run_differential dist={ngb_diff_dist}, features={len(diff_feat_cols)}")
    print(f"  home_win features={len(hw_feat_cols)}")

    print("Loading historical features for imputation pipeline fitting...")
    df_hist = _load_hist_features_cached(15)   # cached across dates in a backfill range
    print(f"  Loaded {len(df_hist):,} historical rows")

    # Build a superset of all features needed by any NGBoost model so the imputer
    # sees every column. The retained list from feature_selection.md covers the
    # base set; per-model lists add any model-specific extras.
    retained_cols = load_retained_features()
    all_feat_cols = list(dict.fromkeys(retained_cols + tot_feat_cols + diff_feat_cols))

    feature_cols_hist  = [c for c in all_feat_cols if c in df_hist.columns]
    feature_cols_today = [c for c in all_feat_cols if c in df_today.columns]
    missing = set(all_feat_cols) - set(feature_cols_today)
    if missing:
        warnings.warn(
            f"{len(missing)} features missing from today's data (will fill NaN): "
            f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
        )

    X_hist = df_hist[[c for c in feature_cols_hist if c in df_hist.columns]]
    X_today_raw = df_today[[c for c in feature_cols_today if c in df_today.columns]]
    X_today_raw = X_today_raw.reindex(columns=X_hist.columns, fill_value=np.nan)

    pipeline, X_hist_imp = _fit_pipeline_cached(X_hist)   # fit once, reused across dates

    X_today_imp = pipeline.transform(X_today_raw)
    X_today_imp = X_today_imp.reindex(columns=X_hist_imp.columns, fill_value=0.0)

    # A2.5 — per-game imputation transparency, computed from the PRE-imputation
    # matrix (X_today_raw carries real NaN for unserved features). Persisted to
    # daily_model_predictions so the app can flag degraded picks.
    _model_union_cols = list(dict.fromkeys(tot_feat_cols + diff_feat_cols + hw_feat_cols))
    _disc_cols = _discriminative_cols(_model_union_cols)
    imputation_summary = _build_imputation_summary(X_today_raw, _model_union_cols, _disc_cols)
    _n_degraded = sum(1 for s in imputation_summary if s["is_degraded"])
    print(
        f"[A2.5] Imputation transparency: {len(_disc_cols)} discriminative features tracked | "
        f"{_n_degraded}/{len(imputation_summary)} game(s) below the {_DISC_COVERAGE_FLOOR:.0%} "
        f"discriminative-coverage floor (flagged degraded)."
    )

    print("Loading production models from registry...")
    ngb_total = _load_model_cached("total_runs", "prod")
    ngb_diff  = _load_model_cached("run_differential", "prod")
    clf_hw    = _load_model_cached("home_win", "prod")
    print(f"  total_runs: {type(ngb_total).__name__}")
    print(f"  run_differential: {type(ngb_diff).__name__}")
    print(f"  home_win: {type(clf_hw).__name__}")

    # --- Contract/model feature-count guard (fail fast) -----------------------
    # The registry sidecar (feature_columns_*.json) and the trained model MUST
    # agree on feature count. A mismatch means the JSON was written from a
    # different (e.g. pre-imputation) column set than the model was fit on —
    # build_imputation_pipeline appends `has_starter_platoon_data`/`is_new_venue`,
    # so a contract that omits them is 2 short. Models score by COLUMN POSITION,
    # so a short contract surfaces as an opaque `IndexError: index N is out of
    # bounds` deep inside NGBoost/XGBoost. Assert it here with a clear message
    # instead (the 2026-06-11 Story 30.1 promotion bug).
    def _model_n_features(_m) -> int | None:
        for _attr in ("n_features", "n_features_in_"):
            _v = getattr(_m, _attr, None)
            if _v is not None:
                return int(_v)
        return None  # unknown model type → skip (never false-fail)

    for _tgt, _model, _cols in (("total_runs", ngb_total, tot_feat_cols),
                                ("run_differential", ngb_diff, diff_feat_cols),
                                ("home_win", clf_hw, hw_feat_cols)):
        _n_model = _model_n_features(_model)
        if _n_model is not None and _n_model != len(_cols):
            raise RuntimeError(
                f"[CONTRACT-GUARD] {_tgt}: registry contract "
                f"({_registry[_tgt]['feature_columns_path']}) lists {len(_cols)} "
                f"features but the trained {type(_model).__name__} expects {_n_model}. "
                f"These must match — the model scores by column position, so a "
                f"mismatch yields a silent IndexError. Likely cause: the contract was "
                f"written pre-imputation and is missing the imputation indicator "
                f"columns (has_starter_platoon_data, is_new_venue). Regenerate the "
                f"contract from the post-imputation training matrix and re-upload."
            )

    best_alpha = _load_best_alpha()
    print(f"  best_alpha={best_alpha}")
    if best_alpha is not None and float(best_alpha) <= 0.0:
        warnings.warn(
            "[A2.5][EDGE-GUARD] best_alpha=0 → the alpha tuner gives the model zero weight "
            "(posterior == market): the model adds no skill over the market right now. "
            "Actionable h2h_edge/totals_edge and their Kelly fractions are computed from the "
            "POSTERIOR (≈0), so no phantom edges/picks are surfaced. The raw model-vs-market "
            "gap remains in layer4_h2h_edge for diagnostics. This guard auto-releases once the "
            "model regains skill and re-tuning lifts alpha > 0 (A2.6 exit criterion).",
            stacklevel=2,
        )

    # --- A2.2: served feature-matrix alignment guard + degradation log --------
    # Models score by COLUMN POSITION; reindex(columns=feat_cols) aligns by name
    # to the training order. A model-expected column ABSENT from the assembled +
    # imputed matrix would be silently 0.0-filled — a value never seen at train
    # time (the "379-feature model scoring a 373-col matrix" failure). Verify
    # every model column is structurally present and FAIL LOUD if not. Separately
    # log value-level degradation: columns served-but-entirely-null across the
    # slate get imputed to a SINGLE constant for every game, which flattens
    # discrimination without any structural mismatch (the 2026-06-10 corr~0
    # finding — see Epic A2). This is observability, not a fatal condition.
    served_cols = set(X_today_imp.columns)
    n_today = len(df_today)
    for _tgt, _cols in (("total_runs", tot_feat_cols),
                        ("run_differential", diff_feat_cols),
                        ("home_win", hw_feat_cols)):
        _absent = [c for c in _cols if c not in served_cols]
        _present_raw = [c for c in _cols if c in df_today.columns]
        _all_null = [c for c in _present_raw if df_today[c].isna().all()]
        print(
            f"[FEATURE-ALIGN] {_tgt}: {len(_cols)} expected | "
            f"{len(_absent)} absent(structural) | "
            f"{len(_all_null)} served-but-all-null→constant-impute | "
            f"{len(_cols) - len(_absent)} structurally served"
        )
        if _all_null:
            warnings.warn(
                f"[FEATURE-ALIGN] {_tgt}: {len(_all_null)} model features are entirely "
                f"NULL across today's {n_today} game(s) and will be imputed to a single "
                f"constant for every game (discrimination loss, NOT a structural error): "
                f"{sorted(_all_null)[:12]}{'...' if len(_all_null) > 12 else ''}"
            )
        if _absent:
            raise RuntimeError(
                f"[FEATURE-ALIGN] {_tgt} expects {len(_cols)} features but {len(_absent)} "
                f"are ABSENT from the served matrix and would be silently 0.0-filled (a "
                f"value the model never saw at train time): "
                f"{_absent[:20]}{'...' if len(_absent) > 20 else ''}. Refusing to score a "
                f"structurally-misaligned matrix — fix the feature pipeline (dbt rebuild / "
                f"restore renamed columns) so these columns are present, then re-run."
            )

    # Slice to each model's exact expected feature set and order.
    X_tot  = X_today_imp.reindex(columns=tot_feat_cols,  fill_value=0.0).values
    X_diff = X_today_imp.reindex(columns=diff_feat_cols, fill_value=0.0).values

    pred_dist_tot = ngb_total.pred_dist(X_tot)
    loc_tot   = pred_dist_tot.params["loc"]
    scale_tot = pred_dist_tot.params["scale"]

    total_line_vals = (
        df_today["total_line_consensus"].values
        if "total_line_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )
    p_over_total = p_over_line(
        ngb_tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line_vals
    )

    pred_dist_diff = ngb_diff.pred_dist(X_diff)
    loc_diff   = pred_dist_diff.params["loc"]
    scale_diff = pred_dist_diff.params["scale"]
    p_home_win_ngb = p_over_line(
        ngb_diff_dist, {"loc": loc_diff, "scale": scale_diff}, total_line=0
    )

    X_clf = X_today_imp.reindex(columns=hw_feat_cols, fill_value=0.0).values.astype(np.float32)
    p_home_win_clf = clf_hw.predict_proba(X_clf)[:, 1]

    has_odds_col = df_today["has_odds"].fillna(False).astype(bool)
    h2h_mkt  = (
        df_today["home_win_prob_consensus"].values
        if "home_win_prob_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )
    over_mkt = (
        df_today["over_prob_consensus"].values
        if "over_prob_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )

    output_rows: list[dict] = []
    for i, row_idx in enumerate(df_today.index):
        game_key = str(row_idx)
        if "game_pk" in df_today.columns:
            game_key = str(df_today.loc[row_idx, "game_pk"])

        if not has_odds_col.iloc[i]:
            continue

        if pd.notna(h2h_mkt[i]):
            cons_prob = float(p_home_win_ngb[i]) * 0.5 + float(p_home_win_clf[i]) * 0.5
            calibrated_win_prob = _apply_calibrator(cons_prob)
            mkt = float(h2h_mkt[i])
            edge = compute_edge(calibrated_win_prob, mkt)
            output_rows.append({
                "game_key":             game_key,
                "market":               "h2h",
                "model_prob":           calibrated_win_prob,
                "market_implied_prob":  mkt,
                "alpha":                best_alpha,
                "posterior_prob":       compute_posterior(calibrated_win_prob, mkt, best_alpha),
                "edge":                 edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

        if pd.notna(over_mkt[i]):
            mp  = float(p_over_total[i])
            mkt = float(over_mkt[i])
            edge = compute_edge(mp, mkt)
            output_rows.append({
                "game_key":             game_key,
                "market":               "totals",
                "model_prob":           mp,
                "market_implied_prob":  mkt,
                "alpha":                best_alpha,
                "posterior_prob":       compute_posterior(mp, mkt, best_alpha),
                "edge":                 edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

    output_rows.sort(key=lambda r: abs(r.get("edge") or 0.0), reverse=True)

    def _matchup(idx: int) -> str:
        row = df_today.iloc[idx]
        for home_col, away_col in [
            ("home_team_abbrev", "away_team_abbrev"),
            ("home_team", "away_team"),
        ]:
            if home_col in df_today.columns and away_col in df_today.columns:
                return f"{row[away_col]} @ {row[home_col]}"
        return str(df_today.index[idx])

    def _game_time(idx: int) -> str:
        row = df_today.iloc[idx]
        if "game_datetime" in df_today.columns and pd.notna(row.get("game_datetime")):
            return str(row["game_datetime"])
        if "game_date" in df_today.columns:
            return str(row["game_date"])
        return "—"

    def _pct(val) -> str:
        if pd.isna(val):
            return "—"
        return f"{float(val)*100:.1f}%"

    pred_total = loc_tot
    picks_list: list[str] = []

    rows_table = []
    for i in range(len(df_today)):
        has_odds = has_odds_col.iloc[i]
        ngb_win = float(p_home_win_ngb[i])
        clf_win = float(p_home_win_clf[i])
        consensus_win = ngb_win * 0.5 + clf_win * 0.5
        calibrated_win = _apply_calibrator(consensus_win)

        if calibrated_win >= 0.55:
            pick = f"HOME ({calibrated_win*100:.0f}%)"
        elif calibrated_win <= 0.45:
            pick = f"AWAY ({(1-calibrated_win)*100:.0f}%)"
        elif calibrated_win > 0.50:
            pick = f"TOSS-UP (lean HOME {calibrated_win*100:.0f}%)"
        elif calibrated_win < 0.50:
            pick = f"TOSS-UP (lean AWAY {(1-calibrated_win)*100:.0f}%)"
        else:
            pick = "EVEN"

        picks_list.append(pick)

        # A2.5: display the alpha-aware actionable edge (posterior − market), so the
        # printed Edge/Kelly match the stored columns and collapse to ~0 at best_alpha=0
        # instead of showing the calibrated flat-prob artifact.
        _h2h_v = float(h2h_mkt[i]) if pd.notna(h2h_mkt[i]) else None
        _post_v = compute_posterior(calibrated_win, _h2h_v, best_alpha) if (has_odds and _h2h_v is not None) else None
        _edge_v = compute_actionable_edge(calibrated_win, _h2h_v, best_alpha) if (has_odds and _h2h_v is not None) else None
        _kelly_v = compute_kelly(_edge_v, _h2h_v) if (_edge_v is not None and _h2h_v is not None) else None

        rows_table.append({
            "Matchup":            _matchup(i),
            "Pick":               pick,
            "Game Time":          _game_time(i),
            "Pred Total":         f"{pred_total[i]:.1f}",
            "Model Win% (NGBoost)": _pct(p_home_win_ngb[i]),
            "Classifier Win%":    _pct(p_home_win_clf[i]),
            "Calibrated Win%":    _pct(calibrated_win),
            "Market Win%":        _pct(_h2h_v) if has_odds else "—",
            "Posterior%":         _pct(_post_v),
            "Edge":               f"{_edge_v*100:.1f}%" if _edge_v is not None else "—",
            "Kelly%":             f"{_kelly_v*100:.2f}%" if _kelly_v is not None else "—",
        })

    df_table = pd.DataFrame(rows_table)
    print("\n" + df_table.to_string(index=False))

    n_h2h = sum(1 for r in output_rows if r["market"] == "h2h")
    n_tot = sum(1 for r in output_rows if r["market"] == "totals")
    if output_rows:
        print(f"\n{len(output_rows)} output rows ({n_h2h} h2h, {n_tot} totals) ready for Snowflake logging.")
    else:
        print("\n0 output rows (no odds available — picks table above uses model probabilities only).")

    if not args.no_log_snowflake:
        _write_prediction_log(output_rows, target_date)
        _backfill_outcomes()

    run_ts = datetime.now(timezone.utc).replace(tzinfo=None)
    _write_predictions_to_snowflake(
        df_today=df_today,
        target_date=target_date,
        inserted_at=run_ts,
        prediction_type=args.prediction_type,
        lineup_confirmed=args.lineup_confirmed,
        scoped_game_pks=scoped_game_pks,
        is_backfill=args.is_backfill,
        p_home_win_ngb=p_home_win_ngb,
        p_home_win_clf=p_home_win_clf,
        loc_tot=loc_tot,
        scale_tot=scale_tot,
        loc_diff=loc_diff,
        scale_diff=scale_diff,
        p_over_total=p_over_total,
        h2h_mkt=h2h_mkt,
        over_mkt=over_mkt,
        total_line_vals=total_line_vals,
        has_odds_col=has_odds_col,
        best_alpha=best_alpha,
        picks=picks_list,
        imputation_summary=imputation_summary,
    )


if __name__ == "__main__":
    _args = _parse_args()
    _dates = _resolve_target_dates(_args)
    _failures: list[str] = []
    for _i, _d in enumerate(_dates, 1):
        if len(_dates) > 1:
            print(f"\n===== [{_i}/{len(_dates)}] {_d} =====")
        try:
            main(_d, _args)
        except Exception as _exc:  # one bad date must not abort a multi-date backfill
            if len(_dates) == 1:
                raise
            print(f"  ✗ {_d} failed: {_exc} — continuing")
            _failures.append(_d)
    if _failures:
        print(f"\n{len(_failures)}/{len(_dates)} date(s) failed (re-run is idempotent per "
              f"date+version): {_failures}")
        sys.exit(1)
