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
import logging
import sys
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

_AUDIT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "layer3_matrix_audit.md"
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
    args = parser.parse_args()

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
