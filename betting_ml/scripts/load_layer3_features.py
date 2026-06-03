"""
load_layer3_features.py — Epic 9, Story 9.1

Builds the **Layer 3 feature matrix**: a purpose-built, game-level training table
whose primary inputs are the six sub-model distributional signals (which REPLACE
the raw park/weather/umpire/lineup features they encode — Epic 3.Z / 4D), plus
minimal residual game context and the Layer 3 targets (`total_runs`, `home_win`).
Epics 10 (totals) and 11 (H2H) train on this matrix.

Source: `baseball_data.betting_features.feature_pregame_sub_model_signals` (the
wide PIVOT, grain `game_pk × side`, built `is_current = true`) joined to
`baseball_data.betting.mart_game_results` for targets/context.

Grain: ONE ROW PER GAME. The pivot's home/away sides are reshaped into
`home_*` / `away_*` columns; `run_env` is environment-level (identical home/away
— verified) and collapses to one value per game.

Leakage model (9.1): the pivot is `is_current` (latest version), not an
as-of-game-date reconstruction. Temporal leakage-freedom is an ARCHITECTURAL
property of the sub-models (they score each game from pre-game features + EB
priors only), so the value is leakage-free regardless of `computed_at`. It
CANNOT be verified from SCD-2 timestamps: all historical signals were backfilled
post-hoc, so `computed_at > game_date` holds for essentially every game — normal
backfill, not leakage. What the SCD-2 history does expose is *signal version
churn* (values that changed across regenerations as the sub-models were
improved); `validate_layer3_matrix` reports that as a DIAGNOSTIC, not a leakage
verdict. The enforced, meaningful guards are structural: no target columns and no
raw park/weather/umpire/lineup columns. `strict_asof=True` is reserved for a
future true as-of join if per-version reconstruction is ever needed (e.g. once
signals are revised live in-season).

predict_today does NOT consume this matrix yet (Epic 9.4+).

Usage:
    uv run python betting_ml/scripts/load_layer3_features.py --start-date 2021-01-01 --env prod
    uv run python betting_ml/scripts/load_layer3_features.py --env prod --out /tmp/layer3.parquet --no-mlflow
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# (group_label, mu, spread, uncertainty, available, in_floor).
# in_floor groups count toward signal_completeness_score; matchup is reported but
# excluded (availability-gated), mirroring scripts/check_signal_freshness.py.
_SIGNAL_GROUPS = [
    ("run_env",    "run_env_mu_v4",              "run_env_dispersion_v4",       "run_env_mu_v4_uncertainty",           "run_env_mu_v4_available",             True),
    ("offense",    "pred_runs_mu_v2",            "pred_runs_dispersion_v2",     "pred_runs_uncertainty_v2",            "pred_runs_mu_v2_available",           True),
    ("starter",    "starter_suppression_mu_v1",  "starter_suppression_sigma_v1","starter_uncertainty_v1",              "starter_suppression_mu_v1_available", True),
    ("starter_ip", "starter_ip_mu_v1",           "starter_ip_dispersion_v1",    "starter_ip_uncertainty_v1",           "starter_ip_mu_v1_available",          True),
    ("bullpen",    "bullpen_mu_v2",              "bullpen_dispersion_v2",       "bullpen_uncertainty_v2",              "bullpen_mu_v2_available",             True),
    ("matchup",    "matchup_advantage_mu_v1",    "matchup_advantage_sigma_v1",  "matchup_advantage_mu_v1_uncertainty", "matchup_advantage_mu_v1_available",   False),
]

# run_env is environment-level (identical home/away — verified across all games);
# collapse to one value per game rather than emitting home_/away_ duplicates.
_ENV_GROUPS = {"run_env"}

# Raw features the sub-models REPLACE — must never appear in the matrix.
_RAW_FEATURE_PREFIXES = ("park_", "weather_", "umpire_", "avg_woba", "avg_xwoba")

# Columns that are targets/identifiers/derived, not model inputs.
_TARGET_COLS = {"total_runs", "home_win", "home_final_score", "away_final_score", "winning_team"}
_NON_FEATURE_COLS = _TARGET_COLS | {
    "game_pk", "game_date", "season", "home_team", "away_team",
    "signal_completeness_score", "low_signal_completeness",
}

_N_FLOOR_GROUPS = sum(1 for *_, in_floor in _SIGNAL_GROUPS if in_floor)  # = 5
_COMPLETENESS_FLOOR = 0.40
_MLFLOW_EXPERIMENT = "layer3_matrix"

# Story 9.4 — Layer 3 training/inference targets and the canonical column contract.
_TARGETS = ("total_runs", "home_win")
_LAYER3_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "layer3"
_FEATURE_COLUMNS_PATH = _LAYER3_DIR / "layer3_feature_columns.json"
_STACKING_WEIGHTS_PATH = _LAYER3_DIR / "stacking_weights.json"

_AUDIT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "layer3_matrix_audit.md"
)

# Story 10.1 — totals dataset construction.
# Eval-only Bovada total line: sourced from the Card 7.P2 historical snapshot
# store (game_pk-keyed, Bovada-specific, dense 2021-2025 incl. 2023). The latest
# snapshot per game is the closing line. Games without a Bovada line fall back to
# the consensus CLOSE_TOTAL_LINE so eval coverage stays complete; a per-game
# `total_line_source` flag records which. This line NEVER enters the training
# matrix (market-blind guarantee) — it is consumed only post-inference (10.4/10.6).
_ODDS_SNAPSHOTS = "baseball_data.oddsapi.odds_snapshots_historical"
_TOTALS_AUDIT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "totals_v1_dataset_audit.md"
)
_H2H_AUDIT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "h2h_v2_dataset_audit.md"
)


def _schemas(env: str) -> tuple[str, str]:
    """Return (features_schema, mart_schema) for the environment.

    Prod holds the complete signal coverage (the daily pipeline writes prod);
    dev is for local/branch testing against partial data.
    """
    if env == "prod":
        return "baseball_data.betting_features", "baseball_data.betting"
    return "baseball_data.dev_betting_features", "baseball_data.dev_betting"


def _all_signal_columns() -> list[str]:
    cols: list[str] = []
    for _, mu, spread, unc, avail, _ in _SIGNAL_GROUPS:
        cols += [mu, spread, unc, avail]
    return cols


def _numeric_signal_columns() -> list[str]:
    """mu/spread/uncertainty columns (the float-valued signal columns)."""
    cols: list[str] = []
    for _, mu, spread, unc, _, _ in _SIGNAL_GROUPS:
        cols += [mu, spread, unc]
    return cols


# ---------------------------------------------------------------------------
# Story 9.4 — canonical Layer 3 column contract
#
# `layer3_feature_columns.json` is the single source of truth for the Layer 3
# matrix's model-input columns, mirroring `elasticnet_feature_columns.json` and
# the sub-model `feature_columns.json` files. It is derived deterministically
# from `_SIGNAL_GROUPS` (no Snowflake read needed) so it always matches the
# columns `load_layer3_features` actually produces, and it carries a
# `promoted_by_target` block sourced from `stacking_weights.json` so Epic 10
# (totals) / Epic 11 (h2h) can subset to the promoted signals while the contract
# itself stays complete.
# ---------------------------------------------------------------------------

def _reshaped_group_columns(label: str, mu: str, spread: str, unc: str, avail: str) -> list[str]:
    """The matrix column names a signal group contributes, in matrix order.

    Mirrors `_reshape_to_game_level`: environment groups keep one copy; per-side
    groups emit home_/away_ pairs, iterating mu→spread→unc→avail.
    """
    if label in _ENV_GROUPS:
        return [mu, spread, unc, avail]
    cols: list[str] = []
    for c in (mu, spread, unc, avail):
        cols += [f"home_{c}", f"away_{c}"]
    return cols


def layer3_feature_columns() -> list[str]:
    """Ordered list of Layer 3 model-input columns (the feature contract).

    Equals `[c for c in load_layer3_features(...).columns if c not in _NON_FEATURE_COLS]`,
    computed without a Snowflake read.
    """
    cols: list[str] = []
    for label, mu, spread, unc, avail, _ in _SIGNAL_GROUPS:
        cols += _reshaped_group_columns(label, mu, spread, unc, avail)
    return cols


def _promoted_by_target() -> dict:
    """Map each target → promoted signal groups + their matrix columns, from
    stacking_weights.json. Empty (with a note) if weights aren't written yet."""
    if not _STACKING_WEIGHTS_PATH.exists():
        return {t: {"groups": [], "columns": [], "note": "stacking_weights.json not found"} for t in _TARGETS}

    weights = json.loads(_STACKING_WEIGHTS_PATH.read_text())
    targets = weights.get("targets", {})
    group_lookup = {label: (label, mu, spread, unc, avail)
                    for label, mu, spread, unc, avail, _ in _SIGNAL_GROUPS}

    out: dict = {}
    for target in _TARGETS:
        promoted = sorted(targets.get(target, {}).keys())
        columns: list[str] = []
        for label in promoted:
            if label in group_lookup:
                columns += _reshaped_group_columns(*group_lookup[label])
        out[target] = {"groups": promoted, "columns": columns}
    return out


def write_feature_columns_contract() -> Path:
    """Write `layer3_feature_columns.json`. Deterministic; no Snowflake read."""
    _LAYER3_DIR.mkdir(parents=True, exist_ok=True)
    contract = {
        "version": "9.4",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grain": "one row per game_pk",
        "completeness_floor": _COMPLETENESS_FLOOR,
        "feature_columns": layer3_feature_columns(),
        "signal_groups": {
            label: {
                "mu": mu, "spread": spread, "uncertainty": unc, "available": avail,
                "env_level": label in _ENV_GROUPS, "counts_toward_completeness": in_floor,
                "columns": _reshaped_group_columns(label, mu, spread, unc, avail),
            }
            for label, mu, spread, unc, avail, in_floor in _SIGNAL_GROUPS
        },
        "promoted_by_target": _promoted_by_target(),
        "non_feature_columns": sorted(_NON_FEATURE_COLS),
        "notes": (
            "Single source of truth for the Layer 3 column contract (Story 9.4). "
            "feature_columns lists ALL signal columns; promoted_by_target (from "
            "stacking_weights.json) is the subset Epic 10/11 should train on."
        ),
    }
    _FEATURE_COLUMNS_PATH.write_text(json.dumps(contract, indent=2, sort_keys=False) + "\n")
    log.info("Wrote feature-column contract → %s (%d feature columns)",
             _FEATURE_COLUMNS_PATH, len(contract["feature_columns"]))
    return _FEATURE_COLUMNS_PATH


def _load_feature_contract() -> list[str]:
    """Load the contract's ordered feature columns; build it on first use if absent."""
    if not _FEATURE_COLUMNS_PATH.exists():
        write_feature_columns_contract()
    contract = json.loads(_FEATURE_COLUMNS_PATH.read_text())
    return list(contract["feature_columns"])


def load_layer3_features_for_training(
    target: str = "total_runs",
    start_date: str = "2021-01-01",
    min_games_played: int = 15,
    env: str = "prod",
) -> tuple[pd.DataFrame, pd.Series]:
    """Canonical training contract for Epic 10 (`train_totals`) / 11 (`train_h2h`).

    Returns ``(X_train, y_train)`` ready for walk-forward CV:
      * rows filtered to ``signal_completeness_score >= 0.40`` — below this floor a
        game has fewer than 2 of the 5 core signal groups present, so the row is
        mostly imputation and would inject noise into the conditional-mean fit;
        0.40 matches the matrix's ``low_signal_completeness`` flag and the 9.1
        completeness audit. Inference (below) keeps these rows and flags them
        instead, so coverage at score time is never silently dropped.
      * ``X`` columns are exactly ``layer3_feature_columns.json`` order — BOTH
        targets, identifiers, game context, and completeness columns are dropped
        (target-leakage guard). No raw park/weather/umpire/lineup columns exist
        in the matrix to begin with (architectural, enforced by
        ``validate_layer3_matrix``).
    """
    if target not in _TARGETS:
        raise ValueError(f"target must be one of {_TARGETS}, got {target!r}")

    df = load_layer3_features(
        min_games_played=min_games_played, start_date=start_date, env=env,
    )
    df = df[df["signal_completeness_score"] >= _COMPLETENESS_FLOOR].reset_index(drop=True)

    feature_cols = _load_feature_contract()
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Matrix is missing contract feature columns: {missing}")

    y = df[target].copy()
    X = df[feature_cols].copy()  # contract order; targets/context excluded by construction
    log.info("[training] target=%s: X=%s, y=%d (completeness >= %.2f)",
             target, X.shape, len(y), _COMPLETENESS_FLOOR)
    return X, y


def load_layer3_features_for_inference(
    game_pks: list[int],
    env: str = "prod",
) -> pd.DataFrame:
    """Canonical inference contract: one Layer 3 feature row per requested game_pk.

    Unlike training, NO rows are dropped — every ``game_pk`` in ``game_pks`` gets a
    row even if some (or all) signals are missing, using the ``*_available`` flags
    rather than completeness filtering. ``signal_completeness_score`` and
    ``low_confidence`` are always non-null. Final scores are NOT required (today's
    games are unplayed), so no targets are derived.

    NOTE: the live wiring into ``predict_today`` (routing to the Layer 3 champion)
    is finalized in Epic 10, when that champion artifact exists. This function
    establishes the inference data contract Epic 10 consumes.
    """
    if not game_pks:
        raise ValueError("game_pks must be a non-empty list")

    features_schema, mart_schema = _schemas(env)
    sig_cols = _all_signal_columns()
    select_sig = ",\n            ".join(f"f.{c}" for c in sig_cols)
    pk_list = ", ".join(str(int(pk)) for pk in game_pks)

    sql = f"""
        select
            f.game_pk,
            f.side,
            {select_sig},
            g.game_date,
            g.game_year,
            g.home_team,
            g.away_team
        from {features_schema}.feature_pregame_sub_model_signals f
        left join {mart_schema}.mart_game_results g on g.game_pk = f.game_pk
        where f.game_pk in ({pk_list})
    """

    log.info("[inference] loading Layer 3 signals for %d game_pk(s)", len(game_pks))
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        long_df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()

    # Context columns may be absent for unplayed games; ensure they exist so the
    # shared reshape works, and add the score/winner placeholders it references.
    for c in ("home_final_score", "away_final_score", "winning_team"):
        if c not in long_df.columns:
            long_df[c] = pd.NA
    for c in _numeric_signal_columns():
        if c in long_df.columns:
            long_df[c] = pd.to_numeric(long_df[c], errors="coerce")
    if "game_date" in long_df.columns:
        long_df["game_date"] = pd.to_datetime(long_df["game_date"], errors="coerce")

    out = _reshape_to_game_level(long_df) if not long_df.empty else pd.DataFrame(columns=["game_pk"])

    # Guarantee one row per requested game_pk (missing → NaN signals → available=False).
    out = out.set_index("game_pk").reindex([int(pk) for pk in game_pks]).reset_index()
    out = _add_completeness(out)
    out["low_confidence"] = (out["signal_completeness_score"] < _COMPLETENESS_FLOOR).astype(bool)

    feature_cols = _load_feature_contract()
    keep = ["game_pk"] + [c for c in feature_cols if c in out.columns] + \
           ["signal_completeness_score", "low_signal_completeness", "low_confidence"]
    log.info("[inference] returned %d rows (%d low_confidence)",
             len(out), int(out["low_confidence"].sum()))
    return out[keep]


# ---------------------------------------------------------------------------
# Story 10.1 — totals training dataset (eval-only Bovada line + overdispersion)
# ---------------------------------------------------------------------------

def load_total_line_bovada(
    game_pks: list[int] | None = None,
    env: str = "prod",
    fallback_consensus: bool = True,
) -> pd.DataFrame:
    """Eval-only closing total line per game_pk — Bovada-preferred (Story 10.1).

    Bovada closing line comes from TWO Bovada-specific, game_pk-keyed sources:
      * historical snapshot store (`odds_snapshots_historical`) — dense through 2025;
      * the live odds mart (`mart_odds_outcomes` ⋈ `mart_game_odds_bridge`) — the
        current season, which the historical store does NOT cover (added Story 10.6
        when the 2026 OOS gate hit zero historical-Bovada 2026 coverage).
    Games with no Bovada line in either source fall back to the consensus
    CLOSE_TOTAL_LINE when ``fallback_consensus`` so coverage stays complete;
    `total_line_source` ∈ {"bovada", "consensus_fallback"} records which.

    Returns columns: game_pk, total_line_bovada, over_price, under_price,
    total_line_source. This is EVALUATION-ONLY — it must never be joined into the
    training feature matrix (10.4/10.6 consume it post-inference).
    """
    _, mart_schema = _schemas(env)

    bov_sql = f"""
        with snaps as (
            select game_pk, total_line, over_price, under_price,
                   row_number() over (partition by game_pk order by snapshot_ts desc) rn
            from {_ODDS_SNAPSHOTS}
            where lower(bookmaker) = 'bovada' and total_line is not null
        )
        select game_pk, total_line as total_line_bovada, over_price, under_price
        from snaps where rn = 1
    """
    # Live Bovada totals (current season) — keyed by game_pk via the odds bridge.
    # mart_odds_outcomes is long-format and carries BOTH source systems; join each
    # row to the bridge on its source-specific event id (odds_api vs parlay_api),
    # take the closing (latest) snapshot per game/side, then pivot Over/Under.
    bov_live_sql = f"""
        with raw as (
            select b.game_pk, lower(o.outcome_name) as side,
                   o.outcome_point, o.outcome_price_american,
                   row_number() over (partition by b.game_pk, lower(o.outcome_name)
                                      order by o.market_last_update desc nulls last) as rn
            from {mart_schema}.mart_odds_outcomes o
            join {mart_schema}.mart_game_odds_bridge b
              on (o.source_system = 'odds_api'  and o.event_id = b.odds_api_event_id)
              or (o.source_system = 'parlay_api' and o.event_id = b.parlay_api_event_id)
            where lower(o.bookmaker_key) = 'bovada' and o.is_totals_market = true
              and b.game_pk is not null
        ),
        closing as (select game_pk, side, outcome_point, outcome_price_american from raw where rn = 1)
        select game_pk,
               max(case when side = 'over'  then outcome_point end)          as total_line_bovada,
               max(case when side = 'over'  then outcome_price_american end) as over_price,
               max(case when side = 'under' then outcome_price_american end) as under_price
        from closing
        group by game_pk
    """
    cons_sql = f"""
        select game_pk, close_total_line as total_line_bovada
        from {mart_schema}.mart_closing_line_value
        where close_total_line is not null
    """

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(bov_sql)
        bov = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
        cur.execute(bov_live_sql)
        bov_live = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
        cons = pd.DataFrame()
        if fallback_consensus:
            cur.execute(cons_sql)
            cons = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
    finally:
        conn.close()

    for c in ("total_line_bovada", "over_price", "under_price"):
        bov[c] = pd.to_numeric(bov[c], errors="coerce")
        if c in bov_live.columns:
            bov_live[c] = pd.to_numeric(bov_live[c], errors="coerce")
    # Historical Bovada wins where both exist (seasons are disjoint in practice);
    # live Bovada fills the current season the historical store lacks.
    if not bov_live.empty:
        bov_live = bov_live[~bov_live["game_pk"].isin(set(bov["game_pk"]))]
        bov = pd.concat([bov, bov_live], ignore_index=True)
    bov["total_line_source"] = "bovada"

    if fallback_consensus and not cons.empty:
        cons["total_line_bovada"] = pd.to_numeric(cons["total_line_bovada"], errors="coerce")
        cons["over_price"] = pd.NA
        cons["under_price"] = pd.NA
        cons["total_line_source"] = "consensus_fallback"
        # Bovada wins; consensus only fills game_pks Bovada doesn't cover.
        cons = cons[~cons["game_pk"].isin(set(bov["game_pk"]))]
        out = pd.concat([bov, cons], ignore_index=True)
    else:
        out = bov

    if game_pks is not None:
        want = {int(pk) for pk in game_pks}
        out = out[out["game_pk"].isin(want)].reset_index(drop=True)
    return out


def compute_across_model_sigma(df: pd.DataFrame, base_floor: float = 0.5) -> pd.Series:
    """Epistemic uncertainty about total-runs `mu`, on the totals scale (Story 10.3).

    "Across-model disagreement" (the Var(E[X|model]) term): the spread among the
    promoted signals that *directly* estimate total runs —
      • run_env:  ``run_env_mu_v4`` (game-level total-runs environment, ~8 runs)
      • offense:  ``home_pred_runs_mu_v2 + away_pred_runs_mu_v2`` (per-side runs → total)
    (bullpen/starter are latent, not direct total estimators, so they don't enter
    the disagreement.) Plus a per-game variance floor so σ is never 0 (which would
    collapse the P(over) CI and make the bet gate falsely over-confident); the
    floor *grows when signal coverage is low* — fewer signals present → more
    uncertain about the mean → wider CI:

        floor² = (base_floor · (2 − signal_completeness_score))²
        σ = sqrt( Var_across{run_env, offense_total} + floor² )

    NOTE: the sub-model ``*_uncertainty`` columns are intentionally NOT used — in
    ``feature_pregame_sub_model_signals`` they are constant sentinel placeholders
    (run_env=10, offense=7, bullpen=6), not calibrated per-game values, so they
    would swamp σ. Behaves correctly (high disagreement / low coverage → wider σ)
    and complements the champion's *aleatoric* NegBin r. ``base_floor`` is tunable
    and can be calibrated empirically in Story 10.4.
    """
    est = pd.DataFrame(index=df.index)
    if "run_env_mu_v4" in df:
        est["run_env"] = pd.to_numeric(df["run_env_mu_v4"], errors="coerce")
    if {"home_pred_runs_mu_v2", "away_pred_runs_mu_v2"} <= set(df.columns):
        est["offense"] = (pd.to_numeric(df["home_pred_runs_mu_v2"], errors="coerce")
                          + pd.to_numeric(df["away_pred_runs_mu_v2"], errors="coerce"))
    disagree_var = est.var(axis=1, ddof=1) if est.shape[1] >= 2 else pd.Series(0.0, index=df.index)
    disagree_var = disagree_var.fillna(0.0)

    if "signal_completeness_score" in df.columns:
        completeness = pd.to_numeric(df["signal_completeness_score"], errors="coerce").fillna(1.0).clip(0.0, 1.0)
    else:
        completeness = pd.Series(1.0, index=df.index)
    floor = base_floor * (2.0 - completeness)            # base_floor at full coverage, up to 2× at 0 coverage

    return (disagree_var + floor ** 2) ** 0.5


def analyze_totals_target(y: pd.Series) -> dict:
    """Target-distribution / overdispersion check for `total_runs` (Story 10.1).

    Overdispersion ratio = variance / mean. A ratio > 1.5 means the count is
    materially overdispersed relative to a Poisson (where variance == mean),
    justifying the NegBin likelihood family over Poisson.
    """
    y = pd.to_numeric(y, errors="coerce").dropna()
    mean = float(y.mean())
    var = float(y.var(ddof=1))
    ratio = var / mean if mean else float("nan")
    return {
        "n": int(y.shape[0]),
        "mean": round(mean, 4),
        "variance": round(var, 4),
        "overdispersion_ratio": round(ratio, 4),
        "recommend_negbin": bool(ratio > 1.5),
    }


def build_totals_dataset(
    start_date: str = "2021-01-01",
    min_games_played: int = 15,
    env: str = "prod",
    return_meta: bool = False,
):
    """Canonical Layer 3 totals training dataset (Story 10.1).

    Returns ``(X, y, eval_lines, report)`` — or ``(X, y, eval_lines, report, meta)``
    when ``return_meta`` (``meta`` = game_pk/game_year/season/game_date aligned to
    X/y, for walk-forward CV in Story 10.2):
      * ``X``/``y`` — game-level training matrix for `total_runs` (completeness ≥
        0.40, contract columns, no leakage), per `load_layer3_features_for_training`.
      * ``eval_lines`` — eval-only Bovada-preferred total line per kept game_pk
        (NEVER part of X).
      * ``report`` — leakage validation + grain + overdispersion + line coverage.

    This is the contract Epic 10 Story 10.2 (`train_totals.py`) calls.
    """
    df = load_layer3_features(min_games_played=min_games_played, start_date=start_date, env=env)
    validation = validate_layer3_matrix(df, start_date=start_date, env=env)  # raises on leakage

    df = df[df["signal_completeness_score"] >= _COMPLETENESS_FLOOR].reset_index(drop=True)
    if not df["game_pk"].is_unique:
        raise ValueError("Layer 3 totals matrix is not one-row-per-game — grain violation.")

    feature_cols = _load_feature_contract()
    X = df[feature_cols].copy()
    y = df["total_runs"].astype(float).copy()
    meta = df[["game_pk", "game_year", "season", "game_date"]].copy()
    if "total_line_bovada" in X.columns:
        raise ValueError("Eval-only total_line_bovada leaked into training features.")

    overdispersion = analyze_totals_target(y)
    eval_lines = load_total_line_bovada(df["game_pk"].tolist(), env=env)
    n_bovada = int((eval_lines["total_line_source"] == "bovada").sum())
    line_coverage = {
        "n_games": len(df),
        "n_with_line": int(len(eval_lines)),
        "n_bovada": n_bovada,
        "n_consensus_fallback": int(len(eval_lines) - n_bovada),
        "pct_with_line": round(100.0 * len(eval_lines) / len(df), 1) if len(df) else 0.0,
    }
    report = {
        "n_games": len(df),
        "validation": validation,
        "overdispersion": overdispersion,
        "line_coverage": line_coverage,
    }
    log.info("[totals dataset] X=%s, y=%d | overdispersion var/mean=%.2f (NegBin=%s) | "
             "line coverage %d/%d (%d Bovada, %d consensus)",
             X.shape, len(y), overdispersion["overdispersion_ratio"],
             overdispersion["recommend_negbin"], line_coverage["n_with_line"],
             line_coverage["n_games"], n_bovada, line_coverage["n_consensus_fallback"])
    if return_meta:
        return X, y, eval_lines, report, meta
    return X, y, eval_lines, report


def write_totals_dataset_audit(report: dict, start_date: str) -> Path:
    """Write totals_v1_dataset_audit.md (Story 10.1)."""
    _TOTALS_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    od = report["overdispersion"]
    lc = report["line_coverage"]
    lines = [
        "# Layer 3 Totals Dataset Audit (Story 10.1)",
        "",
        f"- Source: `load_layer3_features_for_training(target='total_runs')`, start_date={start_date}, completeness ≥ {_COMPLETENESS_FLOOR}.",
        f"- Games (completeness-filtered): **{report['n_games']}**.",
        f"- Leakage guards: target columns **0**, raw-feature violations **{report['validation']['raw_feature_violations']}** (validated — raises otherwise).",
        "",
        "## Target distribution — `total_runs`",
        "",
        "| metric | value |",
        "|---|---|",
        f"| n | {od['n']} |",
        f"| mean | {od['mean']} |",
        f"| variance | {od['variance']} |",
        f"| overdispersion ratio (var/mean) | **{od['overdispersion_ratio']}** |",
        f"| NegBin justified (ratio > 1.5) | **{od['recommend_negbin']}** |",
        "",
        "_Variance materially exceeding the mean confirms NegBin over Poisson as the likelihood family._" if od["recommend_negbin"]
        else "_⚠️ Overdispersion ratio ≤ 1.5 — Poisson may suffice; revisit the NegBin assumption._",
        "",
        "## Eval-only Bovada total line coverage",
        "",
        f"- Games with a line: **{lc['n_with_line']}/{lc['n_games']}** ({lc['pct_with_line']}%).",
        f"- Bovada-specific (closing snapshot): **{lc['n_bovada']}**.",
        f"- Consensus fallback: **{lc['n_consensus_fallback']}**.",
        "",
        "_The total line is evaluation-only (10.4/10.6) and never enters the training matrix._",
        "",
    ]
    _TOTALS_AUDIT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote totals dataset audit → %s", _TOTALS_AUDIT_PATH)
    return _TOTALS_AUDIT_PATH


# ---------------------------------------------------------------------------
# Epic 11 (H2H) — Story 11.1: training dataset construction
# ---------------------------------------------------------------------------

def load_devig_home_prob_bovada(
    game_pks: list[int] | None = None,
    env: str = "prod",
    fallback_consensus: bool = True,
) -> pd.DataFrame:
    """Eval-only de-vigged closing P(home win) per game_pk — Bovada-preferred (Story 11.1).

    Two sources, mirroring `load_total_line_bovada`:
      * Bovada-specific moneyline from the live odds mart
        (`mart_odds_outcomes` ⋈ `mart_game_odds_bridge`, ``market_key='h2h'``):
        take the closing (latest) home and away American prices and de-vig with
        the additive method (`h2h_probability.devig_home_prob`). Dense for
        2021-2022 and 2024-2026; sparse for 2023.
      * Consensus fallback (`mart_closing_line_value.close_vf_home`, already a
        vig-free home probability) fills game_pks Bovada doesn't cover — notably
        the 2023 Bovada-h2h gap — when ``fallback_consensus``.

    Returns columns: game_pk, bovada_devig_home_prob, home_price, away_price,
    devig_home_source ∈ {"bovada", "consensus_fallback"}. EVALUATION-ONLY — it
    must never enter the training matrix (consumed post-inference in 11.2/11.5/11.7).
    """
    from betting_ml.utils.h2h_probability import devig_home_prob

    _, mart_schema = _schemas(env)

    # Bovada-specific h2h: closing home/away American prices per game_pk.
    bov_sql = f"""
        with raw as (
            select b.game_pk,
                   case when o.is_home_outcome then 'home'
                        when o.is_away_outcome then 'away' end as side,
                   o.outcome_price_american,
                   row_number() over (
                       partition by b.game_pk,
                           case when o.is_home_outcome then 'home'
                                when o.is_away_outcome then 'away' end
                       order by o.market_last_update desc nulls last) as rn
            from {mart_schema}.mart_odds_outcomes o
            join {mart_schema}.mart_game_odds_bridge b
              on (o.source_system = 'odds_api'  and o.event_id = b.odds_api_event_id)
              or (o.source_system = 'parlay_api' and o.event_id = b.parlay_api_event_id)
            where lower(o.bookmaker_key) = 'bovada' and o.market_key = 'h2h'
              and b.game_pk is not null
              and (o.is_home_outcome or o.is_away_outcome)
        ),
        closing as (select game_pk, side, outcome_price_american from raw where rn = 1)
        select game_pk,
               max(case when side = 'home' then outcome_price_american end) as home_price,
               max(case when side = 'away' then outcome_price_american end) as away_price
        from closing
        group by game_pk
    """
    cons_sql = f"""
        select game_pk, close_vf_home as bovada_devig_home_prob
        from {mart_schema}.mart_closing_line_value
        where close_vf_home is not null
    """

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(bov_sql)
        bov = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
        cons = pd.DataFrame()
        if fallback_consensus:
            cur.execute(cons_sql)
            cons = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
    finally:
        conn.close()

    for c in ("home_price", "away_price"):
        bov[c] = pd.to_numeric(bov[c], errors="coerce")
    # Keep only games where BOTH sides priced; de-vig additively.
    bov = bov[bov["home_price"].notna() & bov["away_price"].notna()].copy()
    bov["bovada_devig_home_prob"] = [
        devig_home_prob(h, a) for h, a in zip(bov["home_price"], bov["away_price"])
    ]
    bov = bov[bov["bovada_devig_home_prob"].notna()].reset_index(drop=True)
    bov["devig_home_source"] = "bovada"

    if fallback_consensus and not cons.empty:
        cons["bovada_devig_home_prob"] = pd.to_numeric(cons["bovada_devig_home_prob"], errors="coerce")
        cons = cons[cons["bovada_devig_home_prob"].notna()].copy()
        cons["home_price"] = pd.NA
        cons["away_price"] = pd.NA
        cons["devig_home_source"] = "consensus_fallback"
        # Bovada wins; consensus only fills game_pks Bovada doesn't cover.
        cons = cons[~cons["game_pk"].isin(set(bov["game_pk"]))]
        out = pd.concat([bov, cons], ignore_index=True)
    else:
        out = bov

    if game_pks is not None:
        want = {int(pk) for pk in game_pks}
        out = out[out["game_pk"].isin(want)].reset_index(drop=True)
    return out


def analyze_h2h_target(y: pd.Series) -> dict:
    """`home_win` base-rate check (Story 11.1).

    MLB home-field advantage should put the home win rate in [0.52, 0.56];
    outside that flags a potential data-quality issue.
    """
    y = pd.to_numeric(y, errors="coerce").dropna()
    rate = float(y.mean()) if len(y) else float("nan")
    return {
        "n": int(y.shape[0]),
        "base_rate": round(rate, 4),
        "expected_range": [0.52, 0.56],
        "in_expected_range": bool(0.52 <= rate <= 0.56),
    }


def build_h2h_dataset(
    start_date: str = "2021-01-01",
    min_games_played: int = 15,
    env: str = "prod",
    return_meta: bool = False,
):
    """Canonical Layer 3 H2H training dataset (Story 11.1).

    Returns ``(X, y, eval_probs, report)`` — or ``(X, y, eval_probs, report, meta)``
    when ``return_meta`` (``meta`` = game_pk/game_year/season/game_date aligned to
    X/y, for walk-forward CV in 11.2/11.3):
      * ``X``/``y`` — game-level matrix for `home_win` (completeness ≥ 0.40,
        contract columns, no leakage), via the same filtered matrix as totals
        (the matrix is target-agnostic — `home_win` and `total_runs` are both
        derived from identical rows, so the signal-completeness distribution is
        identical to the totals dataset).
      * ``eval_probs`` — eval-only Bovada-preferred de-vigged P(home win) per kept
        game_pk (NEVER part of X).
      * ``report`` — leakage validation + grain + base-rate + market coverage.

    This is the contract Epic 11 Stories 11.2 (Approach A) and 11.3 (Approach B) call.
    """
    df = load_layer3_features(min_games_played=min_games_played, start_date=start_date, env=env)
    validation = validate_layer3_matrix(df, start_date=start_date, env=env)  # raises on leakage

    df = df[df["signal_completeness_score"] >= _COMPLETENESS_FLOOR].reset_index(drop=True)
    if not df["game_pk"].is_unique:
        raise ValueError("Layer 3 H2H matrix is not one-row-per-game — grain violation.")

    feature_cols = _load_feature_contract()
    X = df[feature_cols].copy()
    y = df["home_win"].astype(int).copy()
    meta = df[["game_pk", "game_year", "season", "game_date"]].copy()
    if "bovada_devig_home_prob" in X.columns:
        raise ValueError("Eval-only bovada_devig_home_prob leaked into training features.")

    base_rate = analyze_h2h_target(y)
    completeness = {
        "mean": round(float(df["signal_completeness_score"].mean()), 4),
        "min": round(float(df["signal_completeness_score"].min()), 4),
        "p25": round(float(df["signal_completeness_score"].quantile(0.25)), 4),
        "median": round(float(df["signal_completeness_score"].median()), 4),
    }

    eval_probs = load_devig_home_prob_bovada(df["game_pk"].tolist(), env=env)
    n_bovada = int((eval_probs["devig_home_source"] == "bovada").sum())
    market_coverage = {
        "n_games": len(df),
        "n_with_prob": int(len(eval_probs)),
        "n_bovada": n_bovada,
        "n_consensus_fallback": int(len(eval_probs) - n_bovada),
        "pct_with_prob": round(100.0 * len(eval_probs) / len(df), 1) if len(df) else 0.0,
    }
    report = {
        "n_games": len(df),
        "validation": validation,
        "base_rate": base_rate,
        "completeness": completeness,
        "market_coverage": market_coverage,
    }
    log.info("[h2h dataset] X=%s, y=%d | home_win base_rate=%.4f (in_range=%s) | "
             "market coverage %d/%d (%d Bovada, %d consensus)",
             X.shape, len(y), base_rate["base_rate"], base_rate["in_expected_range"],
             market_coverage["n_with_prob"], market_coverage["n_games"],
             n_bovada, market_coverage["n_consensus_fallback"])
    if return_meta:
        return X, y, eval_probs, report, meta
    return X, y, eval_probs, report


def write_h2h_dataset_audit(report: dict, start_date: str) -> Path:
    """Write h2h_v2_dataset_audit.md (Story 11.1)."""
    _H2H_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    br = report["base_rate"]
    mc = report["market_coverage"]
    cp = report["completeness"]
    rng = br["expected_range"]
    range_note = (
        "_Home win rate within the expected MLB home-field-advantage band._"
        if br["in_expected_range"]
        else f"_⚠️ Home win rate outside [{rng[0]}, {rng[1]}] — investigate as a possible data-quality issue._"
    )
    lines = [
        "# Layer 3 H2H Dataset Audit (Story 11.1)",
        "",
        f"- Source: `load_layer3_features_for_training(target='home_win')` / `build_h2h_dataset`, "
        f"start_date={start_date}, completeness ≥ {_COMPLETENESS_FLOOR}.",
        f"- Games (completeness-filtered): **{report['n_games']}**.",
        f"- Leakage guards: target columns **0**, raw-feature violations "
        f"**{report['validation']['raw_feature_violations']}** (validated — raises otherwise); "
        f"`bovada_devig_home_prob` asserted absent from `X`.",
        "",
        "## Target — `home_win`",
        "",
        "| metric | value |",
        "|---|---|",
        f"| n | {br['n']} |",
        f"| base rate | **{br['base_rate']}** |",
        f"| expected range | [{rng[0]}, {rng[1]}] |",
        f"| in expected range | **{br['in_expected_range']}** |",
        "",
        range_note,
        "",
        "## Signal completeness (identical game set to the totals dataset)",
        "",
        f"- mean **{cp['mean']}**, median {cp['median']}, p25 {cp['p25']}, min {cp['min']} "
        f"(floor {_COMPLETENESS_FLOOR}). Same target-agnostic matrix rows as `build_totals_dataset`.",
        "",
        "## Eval-only de-vigged Bovada P(home win) coverage",
        "",
        f"- Games with a market prob: **{mc['n_with_prob']}/{mc['n_games']}** ({mc['pct_with_prob']}%).",
        f"- Bovada-specific (closing h2h, additive de-vig): **{mc['n_bovada']}**.",
        f"- Consensus fallback (`close_vf_home`): **{mc['n_consensus_fallback']}**.",
        "",
        "_The de-vigged home probability is evaluation-only (11.2/11.5/11.7) and never enters the training matrix._",
        "",
    ]
    _H2H_AUDIT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote H2H dataset audit → %s", _H2H_AUDIT_PATH)
    return _H2H_AUDIT_PATH


def load_layer3_features(
    min_games_played: int = 15,
    start_date: str = "2021-01-01",
    game_type: str = "R",
    env: str = "prod",
    strict_asof: bool = False,
) -> pd.DataFrame:
    """Build the game-level Layer 3 feature matrix.

    Returns one row per game_pk with home_*/away_* champion signal columns
    (run_env collapsed to one value), derived total_runs/home_win targets,
    minimal game context, and a signal_completeness_score.
    """
    if strict_asof:
        raise NotImplementedError(
            "strict_asof as-of-join mode is reserved for a future iteration; "
            "9.1 uses the is_current pivot with a leakage validation."
        )

    features_schema, mart_schema = _schemas(env)
    sig_cols = _all_signal_columns()
    select_sig = ",\n            ".join(f"f.{c}" for c in sig_cols)

    sql = f"""
        select
            f.game_pk,
            f.side,
            {select_sig},
            g.game_date,
            g.game_year,
            g.home_team,
            g.away_team,
            g.home_final_score,
            g.away_final_score,
            g.winning_team
        from {features_schema}.feature_pregame_sub_model_signals f
        join {mart_schema}.mart_game_results g on g.game_pk = f.game_pk
        where g.game_type = '{game_type}'
          and g.home_final_score is not null
          and g.game_date >= '{start_date}'
    """

    log.info("[%s] loading sub-model signals ⋈ mart_game_results since %s", env.upper(), start_date)
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        long_df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()

    if long_df.empty:
        raise RuntimeError("No signal rows joined to completed games — check env/start_date.")

    # Coerce Snowflake NUMBER/FLOAT (Decimal) → float for numeric columns.
    for c in _numeric_signal_columns() + ["home_final_score", "away_final_score", "game_year"]:
        long_df[c] = pd.to_numeric(long_df[c], errors="coerce")
    long_df["game_date"] = pd.to_datetime(long_df["game_date"])

    out = _reshape_to_game_level(long_df)
    out = _add_targets_and_context(out)
    out = _add_completeness(out)
    out = _apply_min_games_played(out, min_games_played)

    log.info("Built Layer 3 matrix: %d games, %d columns", len(out), out.shape[1])
    return out.reset_index(drop=True)


def _reshape_to_game_level(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot game_pk×side rows into one game-level row (home_*/away_* columns)."""
    home = long_df[long_df["side"] == "home"].set_index("game_pk")
    away = long_df[long_df["side"] == "away"].set_index("game_pk")

    game_fields = [
        "game_date", "game_year", "home_team", "away_team",
        "home_final_score", "away_final_score", "winning_team",
    ]
    out = home[game_fields].copy()

    for label, mu, spread, unc, avail, _ in _SIGNAL_GROUPS:
        group_cols = [mu, spread, unc, avail]
        if label in _ENV_GROUPS:
            # Environment signal: identical home/away → keep one copy.
            for c in group_cols:
                out[c] = home[c]
        else:
            for c in group_cols:
                out[f"home_{c}"] = home[c]
                out[f"away_{c}"] = away[c]

    return out.reset_index()


def _add_targets_and_context(out: pd.DataFrame) -> pd.DataFrame:
    out["total_runs"] = out["home_final_score"] + out["away_final_score"]
    out["home_win"] = (out["home_final_score"] > out["away_final_score"]).astype(int)
    out["season"] = out["game_year"].astype(int)
    return out


def _group_present(out: pd.DataFrame, label: str, avail: str) -> pd.Series:
    """Whether a signal group is available for the game.

    Per-side groups require BOTH sides present (Layer 3 needs both teams);
    environment groups need only their single availability flag.
    """
    if label in _ENV_GROUPS:
        return out[avail].eq(True)
    return out[f"home_{avail}"].eq(True) & out[f"away_{avail}"].eq(True)


def _add_completeness(out: pd.DataFrame) -> pd.DataFrame:
    """signal_completeness_score = fraction of the 5 core groups present (matchup excluded)."""
    n_present = pd.Series(0, index=out.index)
    for label, _, _, _, avail, in_floor in _SIGNAL_GROUPS:
        if in_floor:
            n_present = n_present + _group_present(out, label, avail).astype(int)
    out["signal_completeness_score"] = n_present / _N_FLOOR_GROUPS
    out["low_signal_completeness"] = out["signal_completeness_score"] < _COMPLETENESS_FLOOR
    return out


def _apply_min_games_played(out: pd.DataFrame, min_games_played: int) -> pd.DataFrame:
    """Drop games where either team has played fewer than min_games_played prior
    games that season (early-season noise). Counted within the loaded window."""
    if not min_games_played or min_games_played <= 0:
        return out
    long_games = pd.concat([
        out[["game_pk", "season", "game_date", "home_team"]].rename(columns={"home_team": "team"}),
        out[["game_pk", "season", "game_date", "away_team"]].rename(columns={"away_team": "team"}),
    ])
    long_games = long_games.sort_values("game_date")
    long_games["prior_games"] = long_games.groupby(["season", "team"]).cumcount()
    min_prior = long_games.groupby("game_pk")["prior_games"].min()
    keep = min_prior[min_prior >= min_games_played].index
    before = len(out)
    out = out[out["game_pk"].isin(keep)]
    log.info("min_games_played=%d: kept %d/%d games", min_games_played, len(out), before)
    return out


def _signal_version_churn_games(start_date: str, game_type: str, env: str) -> int:
    """Count games whose SCD-2 signal history shows a value-changing revision
    computed after the game.

    DATA-LINEAGE DIAGNOSTIC, not a leakage verdict. Historical signals were all
    backfilled post-hoc, so `computed_at > game_date` holds for nearly every
    game; a changed value across versions reflects sub-model/feature improvements
    during build-out (model-version churn), not temporal leakage — the signals
    are leakage-free by construction (pre-game features only). High counts here
    are expected. Covers only the SCD-2 mart signals (run_env / bullpen /
    matchup); offense / starter / starter_ip live in betting_features MERGE
    tables with no version history.
    """
    _, mart_schema = _schemas(env)
    sql = f"""
        with hist as (
            select s.game_pk, s.side, s.signal_name, s.signal_value,
                   s.computed_at, s.is_current, g.game_date
            from {mart_schema}.mart_sub_model_signals s
            join {mart_schema}.mart_game_results g on g.game_pk = s.game_pk
            where g.game_type = '{game_type}' and g.game_date >= '{start_date}'
        ),
        agg as (
            select game_pk, side, signal_name,
                   count(*) as n_versions,
                   count(distinct signal_value) as n_values,
                   max(case when is_current then computed_at end) as current_computed_at,
                   max(game_date) as game_date
            from hist
            group by 1, 2, 3
        )
        select count(distinct game_pk) as flagged_games
        from agg
        where n_versions > 1 and n_values > 1
          and current_computed_at > dateadd(day, 1, game_date)
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
    finally:
        conn.close()
    return int(row[0]) if row and row[0] is not None else 0


def validate_layer3_matrix(
    df: pd.DataFrame,
    start_date: str = "2021-01-01",
    game_type: str = "R",
    env: str = "prod",
) -> dict:
    """Assert leakage-free structure; return a validation report.

    Raises ValueError on a hard violation (target or raw-feature leakage).
    """
    report: dict = {}

    feature_cols = [c for c in df.columns if c not in _NON_FEATURE_COLS]
    report["n_feature_columns"] = len(feature_cols)

    # 1. No target leakage.
    target_leak = sorted(_TARGET_COLS & set(feature_cols))
    if target_leak:
        raise ValueError(f"Target columns leaked into features: {target_leak}")

    # 2. No raw features the sub-models are supposed to replace.
    raw_hits = [
        c for c in df.columns
        if any(c.lower().startswith(p) or p in c.lower() for p in _RAW_FEATURE_PREFIXES)
    ]
    if raw_hits:
        raise ValueError(f"Raw feature columns present (sub-models must replace them): {raw_hits}")
    report["raw_feature_violations"] = 0

    # 3. Null rates; foundational signals must be near-complete.
    null_rates = {c: round(float(df[c].isna().mean()), 6) for c in df.columns}
    report["null_rates"] = null_rates
    foundational = ["run_env_mu_v4", "home_pred_runs_mu_v2", "away_pred_runs_mu_v2"]
    report["foundational_coverage"] = {}
    for col in foundational:
        cov = 1.0 - null_rates.get(col, 1.0)
        report["foundational_coverage"][col] = round(cov, 6)
        if cov < 0.999:
            log.warning("Foundational signal %s coverage %.4f < 0.999", col, cov)

    # 4. Signal version churn — DIAGNOSTIC only (not leakage; see module docstring).
    churn = _signal_version_churn_games(start_date, game_type, env)
    report["signal_version_churn_games"] = churn
    log.info("Signal version churn: %d game(s) have a value-changing SCD-2 revision "
             "(expected for backfilled data — model-version churn, not leakage).", churn)

    # 5. Completeness distribution.
    report["completeness"] = {
        "mean": round(float(df["signal_completeness_score"].mean()), 4),
        "pct_ge_0.60": round(float((df["signal_completeness_score"] >= 0.60).mean()), 4),
        "n_low": int(df["low_signal_completeness"].sum()),
    }
    return report


def write_audit(df: pd.DataFrame, report: dict, start_date: str) -> Path:
    """Write layer3_matrix_audit.md (row counts by season, null rates, completeness, leakage)."""
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    by_season = df.groupby("season").size().sort_index()
    signal_cols = [c for c in df.columns if c not in _NON_FEATURE_COLS]

    lines = [
        "# Layer 3 Matrix Audit (Story 9.1)",
        "",
        f"- Built from `feature_pregame_sub_model_signals` (is_current) ⋈ `mart_game_results`, start_date={start_date}",
        f"- Grain: one row per game_pk. Games: **{len(df)}**. Feature columns: **{report['n_feature_columns']}**.",
        f"- Targets: `total_runs`, `home_win` (derived; never features).",
        "",
        "## Rows by season",
        "",
        "| season | games |",
        "|---|---|",
    ]
    lines += [f"| {int(s)} | {int(n)} |" for s, n in by_season.items()]

    lines += [
        "",
        "## Foundational signal coverage (must be ≥ 0.999)",
        "",
        "| column | coverage |",
        "|---|---|",
    ]
    lines += [f"| `{c}` | {cov:.4f} |" for c, cov in report["foundational_coverage"].items()]

    lines += [
        "",
        "## Signal completeness (5 core groups; matchup excluded)",
        "",
        f"- mean score: **{report['completeness']['mean']}**",
        f"- fraction ≥ 0.60: **{report['completeness']['pct_ge_0.60']}**",
        f"- low-completeness games (< {_COMPLETENESS_FLOOR}): **{report['completeness']['n_low']}**",
        "",
        "## Leakage guards (structural — enforced)",
        "",
        "- target-column leakage: **0** (validated — raises otherwise)",
        f"- raw-feature violations: **{report['raw_feature_violations']}**",
        "",
        "_Temporal leakage-freedom is architectural (sub-models score from pre-game features",
        "only); it is not verifiable from SCD-2 timestamps on backfilled data._",
        "",
        "## Signal version churn (diagnostic — NOT leakage)",
        "",
        f"- games with a value-changing SCD-2 revision (run_env/bullpen/matchup): "
        f"**{report['signal_version_churn_games']}** — expected for backfilled signals",
        "",
        "## Null rates by signal column",
        "",
        "| column | null rate |",
        "|---|---|",
    ]
    lines += [f"| `{c}` | {report['null_rates'].get(c, 0):.4f} |" for c in sorted(signal_cols)]

    _AUDIT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote audit → %s", _AUDIT_PATH)
    return _AUDIT_PATH


def _log_mlflow(df: pd.DataFrame, report: dict, start_date: str, env: str) -> None:
    import mlflow
    from betting_ml.utils.mlflow_utils import get_or_create_experiment

    exp_id = get_or_create_experiment(_MLFLOW_EXPERIMENT)
    with mlflow.start_run(experiment_id=exp_id, run_name="layer3_matrix_build"):
        mlflow.log_params({
            "env": env,
            "start_date": start_date,
            "n_games": len(df),
            "n_feature_columns": report["n_feature_columns"],
            "date_min": str(df["game_date"].min().date()),
            "date_max": str(df["game_date"].max().date()),
        })
        mlflow.log_metric("completeness_mean", report["completeness"]["mean"])
        mlflow.log_metric("completeness_pct_ge_060", report["completeness"]["pct_ge_0.60"])
        mlflow.log_metric("signal_version_churn_games", report["signal_version_churn_games"])
        for col, cov in report["foundational_coverage"].items():
            mlflow.log_metric(f"coverage__{col}", cov)
    log.info("Logged MLflow run under experiment '%s'", _MLFLOW_EXPERIMENT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Layer 3 feature matrix (Epic 9.1)")
    parser.add_argument("--start-date", default="2021-01-01", help="Earliest game_date to include")
    parser.add_argument("--min-games-played", type=int, default=15,
                        help="Drop games where either team has fewer prior games this season")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod",
                        help="Schemas to read (prod has full signal coverage). Default: prod.")
    parser.add_argument("--no-mlflow", action="store_true", help="Skip MLflow logging")
    parser.add_argument("--out", metavar="PATH", default=None,
                        help="Optional parquet path to persist the matrix for inspection")
    parser.add_argument("--write-contract", action="store_true",
                        help="Write layer3_feature_columns.json (Story 9.4) and exit "
                             "(deterministic; no Snowflake read).")
    parser.add_argument("--totals-audit", action="store_true",
                        help="Build the Story 10.1 totals dataset, run the overdispersion / "
                             "line-coverage analysis, and write totals_v1_dataset_audit.md.")
    args = parser.parse_args()

    if args.write_contract:
        write_feature_columns_contract()
        return

    if args.totals_audit:
        _X, _y, _lines, report = build_totals_dataset(
            start_date=args.start_date, min_games_played=args.min_games_played, env=args.env,
        )
        write_totals_dataset_audit(report, args.start_date)
        od = report["overdispersion"]
        log.info("Totals dataset: %d games | var/mean=%.2f (NegBin=%s) | line coverage %d/%d (%d Bovada).",
                 report["n_games"], od["overdispersion_ratio"], od["recommend_negbin"],
                 report["line_coverage"]["n_with_line"], report["n_games"],
                 report["line_coverage"]["n_bovada"])
        return

    df = load_layer3_features(
        min_games_played=args.min_games_played,
        start_date=args.start_date,
        env=args.env,
    )
    report = validate_layer3_matrix(df, start_date=args.start_date, env=args.env)
    write_audit(df, report, args.start_date)

    if not args.no_mlflow:
        try:
            _log_mlflow(df, report, args.start_date, args.env)
        except Exception as exc:  # noqa: BLE001 — MLflow is non-blocking for the matrix build
            log.warning("MLflow logging skipped: %s", exc)

    if args.out:
        df.to_parquet(args.out, index=False)
        log.info("Wrote matrix → %s", args.out)

    log.info("Done. %d games, completeness mean %.3f, %d version-churn games (diagnostic).",
             len(df), report["completeness"]["mean"], report["signal_version_churn_games"])


if __name__ == "__main__":
    main()
