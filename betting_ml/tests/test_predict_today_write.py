"""Regression tests for production-write correctness in the scorer.

A1.12 — the two foot-guns that story fixes:
  1. The post_lineup overwrite DELETE must be SCOPED to the supplied game_pks
     (a partial re-score must not wipe the rest of the slate's post_lineup rows).
  2. The write schema must resolve from TARGET_ENV via the shared resolver, so
     the two scorers and the app can't diverge (read prod / write dev).

E11.24 (bottom of the file) — the SAME rule as (1), applied to `prediction_log`,
where it had never been applied. E11.24 P1 then moved that table OUT of Snowflake:
the overwrite semantics were re-anchored onto the S3 store in
`test_e11_24_prediction_log_s3.py`, and what remains here is predict_today-specific.
Its clauses are kept separate from A1.12's so a failure names one story; nothing above
this line was changed for E11.24.
"""

import importlib.util
from pathlib import Path

import pytest

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


# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# E11.24 P1 — prediction_log left Snowflake
#
# The A1.12 overwrite rule (above, for `daily_model_predictions`) was extended to
# `prediction_log` at #885: the lineup sensor fires a SCOPED `--game-pks` run per
# completing lineup, and a date-wide DELETE per scoped run left the log holding only the
# LAST batch (prod 2026-08-16: 1-2 games/date against 8-15 in daily_model_predictions;
# compute_model_health's 14-day h2h sample was 18 rows instead of ~180).
#
# P1 moved the whole table to S3 parquet. That rule is NOT retired — it is re-expressed
# as append-and-dedup in `scripts/utils/prediction_log_store`, and the behavioural replay
# that pinned it is RE-ANCHORED onto the new implementation in
# `test_e11_24_prediction_log_s3.py` (a guard suite must not keep encoding a retired
# world, and must not be deleted either).
#
# What stays HERE is what is specific to predict_today: the pure projection onto the
# prediction_log column contract, the scope being wired from main(), and the two
# statements that must no longer exist anywhere in this file.
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re


class TestPredictionLogRowProjection:
    """`_prediction_log_rows` is the pure half of the writer — the derived columns."""

    _ROW = {"game_key": "824998", "market": "h2h", "model_prob": 0.6,
            "market_implied_prob": 0.5, "implied_kelly_fraction": 0.07}

    def _one(self, **over):
        row = {**self._ROW, **over}
        return predict_today._prediction_log_rows([row], "2026-08-16")[0]

    def test_derives_decimal_odds_from_the_market_price(self):
        assert self._one()["decimal_odds"] == pytest.approx(2.0)

    def test_derives_ev_from_model_prob_and_decimal_odds(self):
        # 0.6 * (2.0 - 1) - (1 - 0.6)
        assert self._one()["ev"] == pytest.approx(0.2)

    def test_a_missing_market_price_leaves_odds_and_ev_null(self):
        r = self._one(market_implied_prob=None)
        assert r["decimal_odds"] is None and r["ev"] is None

    def test_a_zero_market_price_does_not_divide_by_zero(self):
        r = self._one(market_implied_prob=0.0)
        assert r["decimal_odds"] is None and r["ev"] is None

    def test_outcome_columns_start_null(self):
        r = self._one()
        assert r["actual_outcome"] is None and r["closing_market_prob"] is None

    def test_kelly_is_the_implied_kelly_not_the_posterior_one(self):
        """prediction_log stores the RAW calibrated-vs-market Kelly. The posterior Kelly
        (what daily_model_predictions stores) is ~0 because best_alpha = 0, so confusing
        the two silently zeroes the column."""
        assert self._one()["kelly_fraction"] == pytest.approx(0.07)


class TestPredictionLogScopeIsWiredFromMain:
    """`prediction_log_store` being correct is worthless if `main()` never scopes.

    Guards the call site, not just the helper (the NF-C0e 'wired ≠ invoked' class).
    """

    _SRC = _SCORER_PATH.read_text()

    @staticmethod
    def _code_only(src: str) -> str:
        # A comment mentioning the identifier must not satisfy these clauses (INC-38).
        return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    def test_main_passes_a_scope_to_the_writer(self):
        code = self._code_only(self._SRC)
        assert _re.search(
            r"_write_prediction_log\([^)]*scoped_game_pks\s*=\s*prediction_log_scope",
            code, _re.S,
        ), "main() must hand _write_prediction_log the scored game set"

    def test_the_scope_is_none_only_for_an_unnarrowed_slate(self):
        code = self._code_only(self._SRC)
        assert "prediction_log_scope" in code and "slate_narrowed" in code
        # Both narrowing filters must set the flag.
        assert code.count("slate_narrowed = True") == 2, (
            "both the --game-pks filter and the lineup-confirmed filter must mark the "
            "slate narrowed, or one path keeps the date-wide overwrite"
        )

    def test_the_writer_delegates_to_the_store(self):
        code = self._code_only(self._SRC)
        assert "prediction_log_store" in code, (
            "the prediction_log write must go through the store module — a second, local "
            "implementation of the overwrite semantics is how they drift apart"
        )


class TestSnowflakePredictionLogIsGone:
    """The whole point of P1: these statements must not exist any more.

    Comment lines are stripped first, so the explanatory comments this migration left
    behind (which NAME the removed statements) cannot satisfy the guard — a source scan
    a comment can satisfy is not a guard (INC-38).
    """

    _SRC = _SCORER_PATH.read_text()

    @property
    def _code(self) -> str:
        return "\n".join(
            l for l in self._SRC.splitlines() if not l.lstrip().startswith("#")
        )

    def test_no_delete_against_the_snowflake_prediction_log(self):
        assert not _re.search(
            r"DELETE\s+FROM\s+baseball_data\.config\.prediction_log", self._code, _re.I
        ), "the DELETE was the #2 COMPUTE_WH waker — it must not survive the migration"

    def test_no_insert_against_the_snowflake_prediction_log(self):
        assert not _re.search(
            r"INSERT\s+INTO\s+baseball_data\.config\.prediction_log", self._code, _re.I
        )

    def test_no_intraday_update_sweeps(self):
        """`_backfill_outcomes()` re-ran six unbounded UPDATE sweeps on EVERY predict
        invocation — 36% of all billable COMPUTE_WH elapsed, and it FROZE
        closing_market_prob mid-slate. The nightly op is the only enrichment now."""
        assert not _re.search(
            r"UPDATE\s+baseball_data\.config\.prediction_log", self._code, _re.I
        )
        assert "def _backfill_outcomes" not in self._code

    def test_the_guard_is_not_vacuous(self):
        """If the file stopped mentioning prediction_log at all, the three clauses above
        would pass on nothing."""
        assert "prediction_log" in self._code
