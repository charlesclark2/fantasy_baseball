"""
check_signal_freshness.py — Epic O.2

Verifies that sub-model signals are current in
`feature_pregame_sub_model_signals` for the most recently completed slate of
games. Runs in the Dagster `daily_ingestion_job` after
`dbt_sub_model_signals_rebuild`.

Semantics (important):
    The five signal generators are anchored on `mart_game_results`, which is
    pitch-derived and therefore contains *completed* games only. They cannot
    score today's upcoming slate (that requires Epic 9 + a generator change).
    So this check validates the latest **completed** game date — the freshest
    slate the generators are actually able to produce — not today's games.

Checks (per the Epic O.2 design, adapted to completed-game semantics):
    - Reference date = max(game_date) of completed regular-season games in
      mart_game_results.
    - For each signal group, count non-null coverage on that date. A group with
      zero coverage logs a WARNING (non-fatal).
    - signal_completeness_score per game-side = (# floor groups present) / 5,
      over the five core groups. The matchup group (Epic 8.6) is reported but
      excluded from the floor — it is legitimately null for availability-gated
      games (early-season call-ups, sparse archetype history, pre-bat-tracking).
      If EVERY game-side on the reference date scores < 0.40 (catastrophic
      signal loss), exit non-zero. Otherwise exit 0.

The Dagster op wraps this NON-BLOCKING for now (warnings only) because
predict_today does not yet consume these signals — failing the run on signal
loss would needlessly block predictions. Flip the op to blocking once Epic 9
wires the signals into predict_today.

Usage:
    uv run python scripts/check_signal_freshness.py --env prod
    uv run python scripts/check_signal_freshness.py --env dev --date 2026-05-31
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Completeness floor: if every recent game-side is below this, fail.
_COMPLETENESS_FLOOR = 0.40

# Story 9.4 — promoted-signal staleness observability.
# The Layer 3 stacked model (Epics 10/11) consumes only the PROMOTED signals, so
# their staleness is what matters for those predictions. We read the promoted set
# from stacking_weights.json so this stays in sync with 9.3, and log a
# non-blocking warning (+ MLflow metrics) when the freshest available signal slate
# is more than 1 day stale. NOTE: like the coverage check, staleness is measured
# against the latest *completed* slate, not today's scheduled games — the signal
# generators are anchored on mart_game_results (completed games only), so this is
# the age of the freshest slate they can produce relative to today. A true
# scheduled-game check waits on the generator change that lets sub-models score
# upcoming games (Epic 10+).
_STACKING_WEIGHTS_PATH = (
    _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "stacking_weights.json"
)
_MAX_PROMOTED_STALENESS_DAYS = 1
_MLFLOW_EXPERIMENT = "layer3_signal_freshness"

# (label, pivot column, in_floor) per signal group.
# in_floor=True groups count toward the catastrophic completeness floor. matchup
# (Epic 8.6) is reported but excluded from the floor: it is legitimately null for
# games without enough lineup/pitcher archetype-posterior coverage (early-season
# call-ups, sparse history) and for pre-bat-tracking games, so it should not drag
# the floor down on an otherwise-healthy slate.
_SIGNAL_GROUPS = [
    ("run_env",    "run_env_mu_v4",             True),
    ("offense",    "pred_runs_mu_v2",           True),
    ("starter",    "starter_suppression_mu_v1", True),
    ("starter_ip", "starter_ip_mu_v1",          True),
    ("bullpen",    "bullpen_mu_v2",             True),
    ("matchup",    "matchup_advantage_mu_v1",   False),
]
_N_FLOOR_GROUPS = sum(1 for *_, in_floor in _SIGNAL_GROUPS if in_floor)


def _schemas(env: str) -> tuple[str, str]:
    """Return (features_schema, mart_schema) for the environment."""
    if env == "prod":
        return "baseball_data.betting_features", "baseball_data.betting"
    return "baseball_data.dev_betting_features", "baseball_data.dev_betting"


def _promoted_groups() -> list[str]:
    """Promoted signal groups across all targets, read from stacking_weights.json
    (Story 9.3). Falls back to the known 9.2 promotions if the file is absent."""
    if _STACKING_WEIGHTS_PATH.exists():
        try:
            weights = json.loads(_STACKING_WEIGHTS_PATH.read_text())
            groups: set[str] = set()
            for per_target in weights.get("targets", {}).values():
                groups.update(per_target.keys())
            if groups:
                return sorted(groups)
        except Exception as exc:  # noqa: BLE001 — never let a bad file break the check
            log.warning("Could not read stacking_weights.json (%s); using fallback promoted set.", exc)
    return ["bullpen", "offense", "run_env"]  # 9.2 promotions


def _log_mlflow_freshness(env: str, ref_date: str, staleness_days: int,
                          promoted: list[str], rec: dict, game_sides: int) -> None:
    """Best-effort MLflow log of promoted-signal freshness (Story 9.4, observable,
    never blocking — MLflow being unavailable must not fail the daily op)."""
    try:
        import mlflow
        from betting_ml.utils.mlflow_utils import get_or_create_experiment

        exp_id = get_or_create_experiment(_MLFLOW_EXPERIMENT)
        with mlflow.start_run(experiment_id=exp_id, run_name=f"freshness_{ref_date}"):
            mlflow.log_params({"env": env, "ref_date": ref_date,
                               "promoted_groups": ",".join(promoted)})
            mlflow.log_metric("promoted_staleness_days", staleness_days)
            mlflow.log_metric("game_sides", game_sides)
            for label in promoted:
                if label in rec and game_sides:
                    mlflow.log_metric(f"coverage__{label}", int(rec[label]) / game_sides)
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow freshness logging skipped: %s", exc)


def _check_promoted_staleness(env: str, ref_date: str, rec: dict, game_sides: int) -> None:
    """Story 9.4: warn (non-blocking) if promoted signals are stale or incomplete,
    and record freshness to MLflow for observability."""
    promoted = _promoted_groups()
    staleness_days = (date.today() - date.fromisoformat(str(ref_date))).days

    incomplete = [g for g in promoted if g in rec and int(rec[g]) < game_sides]
    if staleness_days > _MAX_PROMOTED_STALENESS_DAYS:
        log.warning("Promoted-signal staleness: freshest slate %s is %d day(s) old "
                    "(> %d) — Layer 3 inputs are stale for today's games.",
                    ref_date, staleness_days, _MAX_PROMOTED_STALENESS_DAYS)
    if incomplete:
        log.warning("Promoted signals with partial coverage on %s: %s "
                    "(non-blocking; Layer 3 is inert until Epic 10).",
                    ref_date, ", ".join(incomplete))
    if staleness_days <= _MAX_PROMOTED_STALENESS_DAYS and not incomplete:
        log.info("Promoted signals %s fresh (%d day(s) old) and fully covered on %s.",
                 promoted, staleness_days, ref_date)

    _log_mlflow_freshness(env, str(ref_date), staleness_days, promoted, rec, game_sides)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check sub-model signal freshness (Epic O.2)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod",
                        help="Environment whose schemas to check. Default: prod.")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Reference date to check. Default: latest completed game date.")
    args = parser.parse_args()

    features_schema, mart_schema = _schemas(args.env)
    log.info(f"[{args.env.upper()}] checking {features_schema}.feature_pregame_sub_model_signals")

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        # Reference date: explicit, or the latest completed regular-season slate.
        if args.date:
            ref_date = args.date
        else:
            cur.execute(
                f"select max(game_date) from {mart_schema}.mart_game_results "
                f"where game_type = 'R' and home_final_score is not null"
            )
            row = cur.fetchone()
            ref_date = str(row[0]) if row and row[0] is not None else None

        if ref_date is None:
            log.warning("No completed regular-season games found — nothing to check.")
            return

        # Per-group non-null coverage + completeness distribution on the slate.
        # Completeness floor is computed only over in_floor groups (the matchup
        # group is reported but excluded — see _SIGNAL_GROUPS).
        completeness_expr = " + ".join(
            f"iff(f.{col} is not null, 1, 0)" for _, col, in_floor in _SIGNAL_GROUPS if in_floor
        )
        count_exprs = ", ".join(
            f"count({col}) as {label}" for label, col, _ in _SIGNAL_GROUPS
        )
        cur.execute(f"""
            with sig as (
                select f.game_pk, f.side, ({completeness_expr}) as n_groups,
                       {", ".join(f"f.{col}" for _, col, _ in _SIGNAL_GROUPS)}
                from {features_schema}.feature_pregame_sub_model_signals f
                join {mart_schema}.mart_game_results g on g.game_pk = f.game_pk
                where g.game_date = '{ref_date}'
            )
            select count(*) as game_sides,
                   {count_exprs},
                   coalesce(avg(n_groups / {_N_FLOOR_GROUPS}.0), 0) as avg_completeness,
                   coalesce(sum(iff(n_groups / {_N_FLOOR_GROUPS}.0 >= {_COMPLETENESS_FLOOR}, 1, 0)), 0) as n_ok
            from sig
        """)
        cols = [d[0].lower() for d in cur.description]
        rec = dict(zip(cols, cur.fetchone()))
    finally:
        conn.close()

    game_sides = int(rec["game_sides"])
    log.info(f"Reference slate {ref_date}: {game_sides} game-sides; "
             f"avg completeness {float(rec['avg_completeness']):.2f}")

    if game_sides == 0:
        log.warning(f"No signal rows joined to completed games on {ref_date} "
                    f"(off-day, or signals not yet generated for this slate).")
        return

    # Per-group zero-coverage warnings (non-fatal for secondary signals).
    for label, _, in_floor in _SIGNAL_GROUPS:
        n = int(rec[label])
        status = "OK" if n == game_sides else ("WARN" if n > 0 else "MISSING")
        msg = f"  {label:11s}: {n}/{game_sides} game-sides covered [{status}]"
        if n == 0:
            log.warning(msg + " — signal group has ZERO coverage on the latest slate")
        elif n < game_sides and in_floor:
            log.warning(msg + " — partial coverage")
        elif n < game_sides:
            # matchup: partial coverage is expected (availability-gated per game).
            log.info(msg + " — partial coverage expected (availability-gated)")
        else:
            log.info(msg)

    # Emit completeness score for Dagster metadata (before any exit so it appears in logs).
    avg_completeness = float(rec["avg_completeness"])
    print(f"[METRIC] signal_completeness_score={avg_completeness:.4f}")

    # A1.3 blocking gate: run_env and offense are the minimum required signals.
    # If either has zero coverage on the latest completed slate, predict_today must
    # not run — it would produce predictions with NULL sub-model inputs.
    missing_critical = []
    if int(rec["run_env"]) == 0:
        missing_critical.append("run_env")
    if int(rec["offense"]) == 0:
        missing_critical.append("offense")
    if missing_critical:
        log.error(
            f"BLOCKING: minimum required signals absent on {ref_date}: "
            f"{', '.join(missing_critical)}. predict_today will not run until "
            f"these signals are present. Check signal generator logs."
        )
        sys.exit(1)

    # Catastrophic-loss guard: every game-side below the completeness floor.
    n_ok = int(rec["n_ok"])
    if n_ok == 0:
        log.error(f"CATASTROPHIC: 0/{game_sides} game-sides on {ref_date} clear the "
                  f"{_COMPLETENESS_FLOOR:.0%} completeness floor — signals are effectively absent.")
        sys.exit(1)

    log.info(f"Signal freshness OK: {n_ok}/{game_sides} game-sides clear the "
             f"{_COMPLETENESS_FLOOR:.0%} completeness floor on {ref_date}.")

    # Story 9.4 — promoted-signal staleness + MLflow observability (non-blocking).
    _check_promoted_staleness(args.env, ref_date, rec, game_sides)


if __name__ == "__main__":
    main()
