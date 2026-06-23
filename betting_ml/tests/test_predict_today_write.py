"""A1.12 — regression tests for production-write correctness in the scorer.

Covers the two foot-guns the story fixes:
  1. The post_lineup overwrite DELETE must be SCOPED to the supplied game_pks
     (a partial re-score must not wipe the rest of the slate's post_lineup rows).
  2. The write schema must resolve from TARGET_ENV via the shared resolver, so
     the two scorers and the app can't diverge (read prod / write dev).
"""

import importlib.util
from pathlib import Path

from betting_ml.utils import ml_env

# scripts/ is not a package — load predict_today.py by path for the pure helper.
_SCORER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "predict_today.py"
_spec = importlib.util.spec_from_file_location("predict_today_script", _SCORER_PATH)
predict_today = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(predict_today)


# ── post_lineup overwrite DELETE scope ─────────────────────────────────────────

class TestPostLineupDeleteScope:
    def test_full_slate_delete_is_date_and_type_scoped_only(self):
        sql = predict_today._post_lineup_delete_sql("baseball_data.betting_ml", None)
        assert "WHERE score_date = %(d)s AND prediction_type = %(pt)s" in sql
        # No game_pk filter on a full-slate run → date-wide overwrite (cleanup).
        assert "game_pk IN" not in sql

    def test_scoped_delete_restricts_to_supplied_game_pks(self):
        sql = predict_today._post_lineup_delete_sql("baseball_data.betting_ml", [824998])
        # The bug was that a --game-pks subset still wiped the whole slate.
        assert "game_pk IN (824998)" in sql
        assert "score_date = %(d)s AND prediction_type = %(pt)s" in sql

    def test_scoped_delete_lists_all_pks(self):
        sql = predict_today._post_lineup_delete_sql("s", [3, 1, 2])
        assert "game_pk IN (3, 1, 2)" in sql

    def test_empty_list_is_treated_as_full_slate(self):
        # An empty subset must not produce `game_pk IN ()` (invalid SQL); falls
        # back to the date-wide DELETE.
        sql = predict_today._post_lineup_delete_sql("s", [])
        assert "game_pk IN" not in sql

    def test_schema_is_interpolated(self):
        sql = predict_today._post_lineup_delete_sql("baseball_data.betting_ml_dev", [1])
        assert "baseball_data.betting_ml_dev.daily_model_predictions" in sql

    def test_pks_are_coerced_to_int(self):
        # Defends the inline-into-SQL path against non-int input.
        sql = predict_today._post_lineup_delete_sql("s", ["824998", 824999])
        assert "game_pk IN (824998, 824999)" in sql


# ── shared write-schema resolver ───────────────────────────────────────────────

class TestMlSchemaResolution:
    def test_prod_when_target_env_prod(self, monkeypatch):
        monkeypatch.setenv("TARGET_ENV", "prod")
        assert ml_env.is_prod() is True
        assert ml_env.ml_schema() == "baseball_data.betting_ml"

    def test_dev_when_target_env_unset(self, monkeypatch):
        monkeypatch.delenv("TARGET_ENV", raising=False)
        assert ml_env.is_prod() is False
        assert ml_env.ml_schema() == "baseball_data.betting_ml_dev"

    def test_dev_when_target_env_is_dev(self, monkeypatch):
        monkeypatch.setenv("TARGET_ENV", "dev")
        assert ml_env.ml_schema() == "baseball_data.betting_ml_dev"

    def test_non_prod_value_is_dev(self, monkeypatch):
        # Only the exact string "prod" selects prod — anything else is dev.
        monkeypatch.setenv("TARGET_ENV", "production")
        assert ml_env.ml_schema() == "baseball_data.betting_ml_dev"


# ── Story 30.3 — serving-health gate for the actionable edge ────────────────────

class TestServingDegradedGate:
    def test_healthy_matrix_is_not_degraded(self):
        # Full unconditional-core coverage + admitted game → bet as normal.
        imp = {"is_degraded": False, "discriminative_coverage": 1.0}
        degraded, reason = predict_today._serving_degraded(imp, True)
        assert degraded is False
        assert reason == ""

    def test_core_collapse_is_degraded(self):
        # The 2026-05-29 / 06-10 carry-forward incident: core families NULL.
        imp = {"is_degraded": True, "discriminative_coverage": 0.40}
        degraded, reason = predict_today._serving_degraded(imp, True)
        assert degraded is True
        assert "core-collapse" in reason

    def test_has_full_data_false_is_degraded(self):
        # Out-of-training-distribution game (serve query has no has_full_data filter).
        imp = {"is_degraded": False, "discriminative_coverage": 1.0}
        degraded, reason = predict_today._serving_degraded(imp, False)
        assert degraded is True
        assert "out-of-training-distribution" in reason

    def test_both_conditions_reported(self):
        imp = {"is_degraded": True, "discriminative_coverage": 0.2}
        degraded, reason = predict_today._serving_degraded(imp, False)
        assert degraded is True
        assert "core-collapse" in reason and "out-of-training-distribution" in reason

    def test_pre_lineup_morning_pick_is_NOT_degraded(self):
        # Ordinary pre-lineup sparseness: lineup-/pitcher-gated families are absent
        # but is_degraded (scoped to unconditional-core) stays False, and the game
        # is in-distribution (has_full_data TRUE). Must NOT abstain — that is the
        # Epic A1 timing question, not a serving defect.
        imp = {"is_degraded": False, "discriminative_coverage": 0.87}
        degraded, _ = predict_today._serving_degraded(imp, True)
        assert degraded is False

    def test_missing_summary_and_unknown_has_full_data_do_not_fire(self):
        # None summary + has_full_data absent (None, not False) → no false positive.
        degraded, reason = predict_today._serving_degraded(None, None)
        assert degraded is False
        assert reason == ""


# ── Story 30.3 — bind the actionable bet to the dense post_lineup serve ─────────

class TestLineupsConfirmedGate:
    @staticmethod
    def _df(home, away):
        import pandas as pd
        return pd.DataFrame([{"home_has_full_lineup": home, "away_has_full_lineup": away}])

    def test_both_confirmed_is_true(self):
        assert predict_today._lineups_confirmed(self._df(True, True), 0) is True

    def test_one_unconfirmed_is_false(self):
        assert predict_today._lineups_confirmed(self._df(True, False), 0) is False

    def test_nan_counts_as_not_confirmed(self):
        import numpy as np
        assert predict_today._lineups_confirmed(self._df(True, np.nan), 0) is False

    def test_missing_columns_returns_none_no_gate(self):
        import pandas as pd
        # Flags not served → None so the caller fails OPEN (doesn't gate on lineup state).
        assert predict_today._lineups_confirmed(pd.DataFrame([{"x": 1}]), 0) is None

    def test_actionable_logic_matches_gate(self):
        # Mirror the loop's combination: actionable iff not degraded AND lineups != False.
        def actionable(degraded, lineups_ok):
            return (not degraded) and (lineups_ok is not False)
        assert actionable(False, True) is True      # dense, confirmed → bet
        assert actionable(False, None) is True       # flags absent → fail-open → bet
        assert actionable(False, False) is False     # pre-lineup → defer to post_lineup
        assert actionable(True, True) is False        # degraded → abstain regardless


# ── E11.9 — daily_model_predictions column migration only ALTERs missing cols ───

class _FakeCursor:
    """Records SQL passed to execute(); fetchall() returns the configured columns."""
    def __init__(self, existing_columns):
        self._existing = [(c,) for c in existing_columns]
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._existing

    @property
    def alters(self):
        return [s for s, _ in self.executed if "ADD COLUMN" in s]


class TestPredictionColumnMigration:
    def test_no_alter_when_all_columns_present(self):
        # Steady state: every migrated column already exists → 1 metadata SELECT, 0 DDL.
        every_col = [c for c, _ in predict_today._PREDICTION_COLUMN_MIGRATIONS]
        cur = _FakeCursor(every_col)
        predict_today._migrate_prediction_columns(cur, "baseball_data.betting_ml")
        assert cur.alters == []
        assert len(cur.executed) == 1  # only the INFORMATION_SCHEMA read

    def test_alters_only_missing_columns(self):
        all_cols = [c for c, _ in predict_today._PREDICTION_COLUMN_MIGRATIONS]
        missing = {"sigma_tier", "abstain_reason"}
        cur = _FakeCursor([c for c in all_cols if c not in missing])
        predict_today._migrate_prediction_columns(cur, "baseball_data.betting_ml")
        assert len(cur.alters) == len(missing)
        for col in missing:
            assert any(f"ADD COLUMN IF NOT EXISTS {col} " in s for s in cur.alters)

    def test_column_match_is_case_insensitive(self):
        # Snowflake upper-cases identifiers; existing cols come back upper.
        all_cols = [c.upper() for c, _ in predict_today._PREDICTION_COLUMN_MIGRATIONS]
        cur = _FakeCursor(all_cols)
        predict_today._migrate_prediction_columns(cur, "baseball_data.betting_ml")
        assert cur.alters == []

    def test_information_schema_targets_correct_database(self):
        cur = _FakeCursor([])
        predict_today._migrate_prediction_columns(cur, "baseball_data.betting_ml_dev")
        select_sql, params = cur.executed[0]
        assert "baseball_data.information_schema.columns" in select_sql
        assert params == ["betting_ml_dev"]
        # All columns missing → every migration column gets an ALTER on the fq schema.
        assert len(cur.alters) == len(predict_today._PREDICTION_COLUMN_MIGRATIONS)
        assert all("baseball_data.betting_ml_dev.daily_model_predictions" in s for s in cur.alters)
