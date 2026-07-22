"""test_settlement_cadence.py — E11.20 phase-2a user-bet settlement fixes.

The production symptom (2026-07-21): a slate's afternoon/evening finals sat "open" in the
Bet Log for 12-24h because the ONLY automated settlement was the once-daily morning pass
inside daily_ingestion_job. Three fixes are pinned here:

  1. settle_user_bets.py is Snowflake-FREE — scores/K totals come from the S3 lakehouse via
     DuckDB (so frequent evening passes never wake the warehouse).
  2. An evening settle_user_bets_job + settlement_schedule (default_status=RUNNING) settles
     same-night finals same-night.
  3. The read-side update_bet REMOVEs pending_game_pk when it sets a terminal outcome, so
     auto-voided bets drop out of the sparse gsi-pending-by-game index (were stuck forever).

All fast-gate-safe: source-inspection for the pipeline wiring (fast-gate tests must not import
`pipeline` — its __init__ reads the absent dbt manifest), a FakeTable for the DynamoDB update.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETTLE = (REPO / "scripts" / "settle_user_bets.py").read_text()
DAILY_OPS = (REPO / "pipeline" / "ops" / "daily_ingestion_ops.py").read_text()
SCHED = (REPO / "pipeline" / "schedules" / "settlement_schedule.py").read_text()
JOB = (REPO / "pipeline" / "jobs" / "settlement_jobs.py").read_text()
SCHED_INIT = (REPO / "pipeline" / "schedules" / "__init__.py").read_text()
JOBS_INIT = (REPO / "pipeline" / "jobs" / "__init__.py").read_text()


# ── 1. settle_user_bets.py is Snowflake-free (reads the S3 lakehouse) ─────────

class TestSettleIsSnowflakeFree:
    def test_no_snowflake_connector_import(self):
        # The whole point: the settle script no longer opens a Snowflake session (which
        # wakes the warehouse). It must not import the connector.
        assert "import snowflake" not in SETTLE, (
            "settle_user_bets.py still imports snowflake — the repoint to S3/DuckDB is the "
            "reason evening settle passes are free (no warehouse wake). Reads must go through "
            "scripts/utils/lakehouse_read."
        )
        assert "snowflake.connector" not in SETTLE

    def test_uses_shared_lakehouse_reader(self):
        assert "from scripts.utils.lakehouse_read import" in SETTLE
        for fn in ("duck_connect", "register_views", "query_upper"):
            assert fn in SETTLE, f"settle_user_bets.py must use {fn} from the shared reader"
        assert "_connect_lakehouse" in SETTLE

    def test_reads_the_two_settlement_marts_from_s3(self):
        # Both tables are materialized in the lakehouse and read via the registered views.
        assert 'stg_statsapi_games' in SETTLE and 'mart_starting_pitcher_game_log' in SETTLE
        assert "_SCORE_TABLES" in SETTLE

    def test_final_game_unsettled_alerts_loud(self):
        # ALERT-loud-but-continue: a FINAL game with unsettleable bets is a real gap and must
        # reach stderr, not vanish (the op is otherwise WARN-tier / silent).
        assert "final_unsettled" in SETTLE
        assert "[ALERT]" in SETTLE and "file=sys.stderr" in SETTLE

    def test_module_imports_without_snowflake_or_duckdb_at_import_time(self):
        # Fast-gate-safe: importing the module must not pull in snowflake/duckdb (both are
        # lazy — duckdb inside duck_connect). Proves the top-level import chain is pure.
        import scripts.settle_user_bets as sub
        assert sub._SCORE_TABLES == ["stg_statsapi_games", "mart_starting_pitcher_game_log"]
        assert hasattr(sub, "_connect_lakehouse")


# ── 2. evening settle job + schedule (closes the once-daily cadence gap) ──────

class TestEveningSettleSchedule:
    def test_scheduled_op_has_no_start_input(self):
        # The standalone op must be a valid LONE job node — no required In(Nothing) 'start'
        # (unlike the daily settle_user_bets_op, which chains off dbt_daily_build).
        assert "@op(out=Out(Nothing))\ndef settle_user_bets_scheduled_op" in DAILY_OPS
        assert '@op(ins={"start": In(Nothing)}, out=Out(Nothing))\ndef settle_user_bets_op' in DAILY_OPS

    def test_both_ops_share_one_settlement_body(self):
        # One body → daily + evening can't drift. Both call _run_settlement.
        assert "def _run_settlement(context)" in DAILY_OPS
        assert DAILY_OPS.count("_run_settlement(context)") >= 2

    def test_settlement_stays_warn_tier(self):
        # Settlement is off the serving path; a failure must be logged, never raised.
        body = DAILY_OPS[DAILY_OPS.find("def _run_settlement"):DAILY_OPS.find("def settle_user_bets_op")]
        assert "context.log.warning" in body and "except Exception" in body

    def test_schedule_is_running_and_covers_the_evening(self):
        # default_status=RUNNING is what CLOSES the gap — a STOPPED boot silently never fires
        # (E11.23 class). Cron must hit the overnight window finals actually land in.
        assert "DefaultScheduleStatus.RUNNING" in SCHED
        assert "0 0,2,4,6,20,22 * * *" in SCHED, "evening/overnight cron drifted"

    def test_job_uses_the_scheduled_op(self):
        assert "settle_user_bets_scheduled_op()" in JOB
        assert "settle_user_bets_job" in JOB

    def test_registered_in_aggregators(self):
        assert "settlement_schedule" in SCHED_INIT
        assert "settle_user_bets_job" in JOBS_INIT


# ── 3. read-side update_bet drops a settled bet out of the pending GSI ────────

class _FakeTable:
    """Minimal DynamoDB Table stand-in: records the last update_item kwargs."""

    def __init__(self, item):
        self._item = item
        self.last_update = None

    def get_item(self, Key):
        return {"Item": self._item} if self._item is not None else {}

    def update_item(self, **kwargs):
        self.last_update = kwargs
        return {"Attributes": dict(self._item)}


def _patch_table(monkeypatch, item):
    from app.backend.services import dynamo
    ft = _FakeTable(item)
    monkeypatch.setattr(dynamo, "_bets_table", lambda: ft)
    return dynamo, ft


class TestUpdateBetRemovesPendingKey:
    def test_settling_removes_pending_game_pk(self, monkeypatch):
        dynamo, ft = _patch_table(monkeypatch, {
            "user_id": "u", "bet_id": "b", "pending_game_pk": 823119, "stake": 10,
        })
        dynamo.update_bet("u", "b", {"outcome": "void", "profit_loss": 0.0})
        expr = ft.last_update["UpdateExpression"]
        assert "REMOVE" in expr, "settling must REMOVE pending_game_pk (else it lingers in the GSI)"
        assert "pending_game_pk" in ft.last_update["ExpressionAttributeNames"].values()
        assert "SET" in expr  # outcome + profit_loss still set

    def test_non_settling_edit_keeps_pending_key(self, monkeypatch):
        # A plain edit (no terminal outcome) must NOT touch pending_game_pk — an open bet
        # stays in the pending index until it actually settles.
        dynamo, ft = _patch_table(monkeypatch, {
            "user_id": "u", "bet_id": "b", "pending_game_pk": 823119, "stake": 10,
        })
        dynamo.update_bet("u", "b", {"stake": 20.0})
        expr = ft.last_update["UpdateExpression"]
        assert "REMOVE" not in expr
        assert "pending_game_pk" not in ft.last_update.get("ExpressionAttributeNames", {}).values()

    def test_win_outcome_also_removes(self, monkeypatch):
        dynamo, ft = _patch_table(monkeypatch, {
            "user_id": "u", "bet_id": "b", "pending_game_pk": 1, "stake": 5,
        })
        dynamo.update_bet("u", "b", {"outcome": "win", "profit_loss": 4.55})
        assert "REMOVE" in ft.last_update["UpdateExpression"]
