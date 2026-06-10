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
