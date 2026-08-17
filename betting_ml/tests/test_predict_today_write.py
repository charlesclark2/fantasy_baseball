"""Regression tests for production-write correctness in the scorer.

A1.12 — the two foot-guns that story fixes:
  1. The post_lineup overwrite DELETE must be SCOPED to the supplied game_pks
     (a partial re-score must not wipe the rest of the slate's post_lineup rows).
  2. The write schema must resolve from TARGET_ENV via the shared resolver, so
     the two scorers and the app can't diverge (read prod / write dev).

E11.24 (bottom of the file) — the SAME rule as (1), applied to `prediction_log`,
where it had never been applied. Its clauses are kept separate from A1.12's so a
failure names one story; nothing above this line was changed for E11.24.
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


# ═══════════════════════════════════════════════════════════════════════════════
# E11.24 — prediction_log overwrite scope
#
# The A1.12 rule above was applied to `daily_model_predictions` ONLY. `prediction_log`
# kept a date-wide `DELETE ... WHERE prediction_date = '<date>'` while the lineup sensor
# fires a SCOPED `--game-pks` run per completing lineup, so every scoped run wiped the
# previous runs' rows and the log ended each day holding only the LAST batch.
#
# Measured on prod 2026-08-16 before the fix: prediction_log held 1-2 games/date against
# 8-15 in daily_model_predictions (August avg 1.25 games/date vs ~10 historically), and
# compute_model_health's 14-day h2h sample was 18 rows instead of ~180.
#
# These clauses are independently RED-provable: each fixture satisfies every OTHER
# condition of the rule it tests, so only the named clause can flip the result.
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re


class TestPredictionLogDeleteSql:
    def test_full_slate_delete_is_date_wide(self):
        sql = predict_today._prediction_log_delete_sql(None)
        assert "baseball_data.config.prediction_log" in sql
        assert "prediction_date = %(d)s" in sql
        # A full-slate run keeps the date-wide overwrite (dropped/postponed cleanup).
        assert "game_pk IN" not in sql

    def test_scoped_delete_restricts_to_supplied_game_pks(self):
        # THE regression: a subset run must not reach beyond its own games.
        sql = predict_today._prediction_log_delete_sql([824998])
        assert "game_pk IN (824998)" in sql
        assert "prediction_date = %(d)s" in sql

    def test_scoped_delete_lists_all_pks(self):
        sql = predict_today._prediction_log_delete_sql([3, 1, 2])
        assert "game_pk IN (3, 1, 2)" in sql

    def test_empty_list_is_treated_as_full_slate(self):
        # Must not emit `game_pk IN ()` (invalid SQL).
        assert "game_pk IN" not in predict_today._prediction_log_delete_sql([])

    def test_pks_are_coerced_to_int(self):
        sql = predict_today._prediction_log_delete_sql(["824998", 824999])
        assert "game_pk IN (824998, 824999)" in sql

    def test_date_is_a_bound_parameter_not_an_inlined_literal(self):
        """The pre-fix statement inlined the date with an f-string.

        Two consequences, both real: an injection surface on a serving write, and one
        DISTINCT query_text per date in query_history — which fragmented this statement
        across the wake census's family buckets and is why it went unattributed.
        """
        for scope in (None, [1, 2]):
            sql = predict_today._prediction_log_delete_sql(scope)
            assert "%(d)s" in sql
            # No quoted date literal anywhere in the emitted SQL.
            assert not _re.search(r"'\d{4}-\d{2}-\d{2}'", sql)


class _FakePredictionLogTable:
    """In-memory stand-in that actually APPLIES the DELETE/INSERT.

    A source-substring assertion cannot show that a sequence of scoped runs preserves the
    slate — only replaying the real statement sequence against a table can, so this
    interprets the two statement shapes `_prediction_log_delete_sql` can emit.
    """

    def __init__(self):
        self.rows: list[dict] = []
        self.rowcount = 0
        self.deletes: list[str] = []

    # -- cursor protocol -----------------------------------------------------
    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        if s.upper().startswith("CREATE TABLE"):
            self.rowcount = 0
            return
        if not s.upper().startswith("DELETE"):
            raise AssertionError(f"unexpected statement: {s[:80]}")
        self.deletes.append(s)
        assert params and "d" in params, "the DELETE must bind its date"
        target_date = str(params["d"])
        m = _re.search(r"game_pk IN \(([^)]*)\)", s)
        pks = {int(p) for p in m.group(1).split(",")} if m else None
        before = len(self.rows)
        self.rows = [
            r for r in self.rows
            if not (str(r["prediction_date"]) == target_date
                    and (pks is None or r["game_pk"] in pks))
        ]
        self.rowcount = before - len(self.rows)

    def executemany(self, sql, rows):
        assert "INSERT INTO baseball_data.config.prediction_log" in " ".join(sql.split())
        self.rows.extend(rows)
        self.rowcount = len(rows)

    # -- connection protocol -------------------------------------------------
    def cursor(self):
        return self

    def commit(self):
        pass

    def close(self):
        pass

    # -- helpers -------------------------------------------------------------
    def games_on(self, d: str) -> set[int]:
        return {r["game_pk"] for r in self.rows if str(r["prediction_date"]) == d}


_DATE = "2026-08-16"


def _output_rows(game_pks):
    """Two markets per game — exactly the shape `main()` hands the writer."""
    return [
        {"game_key": str(pk), "market": mkt, "model_prob": 0.5,
         "market_implied_prob": 0.5, "implied_kelly_fraction": 0.0}
        for pk in game_pks for mkt in ("h2h", "totals")
    ]


class TestPredictionLogOverwriteSemantics:
    """Behavioural replay — these are the clauses that go RED on the pre-fix source."""

    def _write(self, monkeypatch, table, game_pks, scoped):
        monkeypatch.setattr(predict_today, "get_snowflake_connection", lambda: table)
        predict_today._write_prediction_log(
            _output_rows(game_pks), _DATE,
            scoped_game_pks=sorted(game_pks) if scoped else None,
        )

    def test_a_sequence_of_scoped_runs_preserves_the_whole_slate(self, monkeypatch):
        """The measured production defect, replayed.

        Morning scores the full slate; the lineup sensor then re-scores games one at a
        time. Pre-fix each scoped run issued a date-wide DELETE, so the log finished the
        day holding ONLY the last game (prod: 1-2 games/date against a 15-game slate).
        """
        slate = list(range(824000, 824015))  # 15 games, as on 2026-08-16
        table = _FakePredictionLogTable()
        self._write(monkeypatch, table, slate, scoped=False)          # morning, full slate
        assert table.games_on(_DATE) == set(slate)

        for pk in slate[:6]:                                          # sensor, one game each
            self._write(monkeypatch, table, [pk], scoped=True)

        assert table.games_on(_DATE) == set(slate), (
            "a per-game post_lineup re-score wiped the rest of the slate's log rows"
        )
        assert len(table.rows) == 2 * len(slate)  # 2 markets/game, no duplicates

    def test_a_scoped_run_deletes_only_the_keys_it_restores(self, monkeypatch):
        """Row-count equivalence: the DELETE's reach == the INSERT's reach."""
        table = _FakePredictionLogTable()
        self._write(monkeypatch, table, [1, 2, 3], scoped=False)
        assert len(table.rows) == 6
        self._write(monkeypatch, table, [2], scoped=True)
        assert table.rowcount == 2          # the INSERT restored what the DELETE cleared
        assert table.deletes[-1].count("game_pk IN (2)") == 1
        assert len(table.rows) == 6         # net zero — an upsert, not a truncate

    def test_re_running_the_same_scoped_batch_is_idempotent(self, monkeypatch):
        table = _FakePredictionLogTable()
        self._write(monkeypatch, table, [1, 2], scoped=False)
        for _ in range(3):
            self._write(monkeypatch, table, [2], scoped=True)
        assert len(table.rows) == 4
        assert table.games_on(_DATE) == {1, 2}

    def test_a_full_slate_run_still_clears_dropped_games(self, monkeypatch):
        """The date-wide overwrite is PRESERVED for a full-slate run.

        This is the clause that keeps the fix from over-reaching: a postponed game that
        drops off the slate must still lose its stale row.
        """
        table = _FakePredictionLogTable()
        self._write(monkeypatch, table, [1, 2, 3], scoped=False)
        self._write(monkeypatch, table, [1, 2], scoped=False)   # game 3 postponed
        assert table.games_on(_DATE) == {1, 2}
        assert "game_pk IN" not in table.deletes[-1]

    def test_a_scoped_run_does_not_touch_another_date(self, monkeypatch):
        table = _FakePredictionLogTable()
        table.rows.append({"prediction_date": "2026-08-15", "game_pk": 1, "market": "h2h"})
        self._write(monkeypatch, table, [1], scoped=True)
        assert table.games_on("2026-08-15") == {1}

    def test_a_scoped_run_that_produced_no_rows_still_clears_only_its_own_games(
        self, monkeypatch
    ):
        """A scored game with no loggable row (no odds) must not leave a stale row behind,
        and must not reach the rest of the slate either."""
        table = _FakePredictionLogTable()
        self._write(monkeypatch, table, [1, 2, 3], scoped=False)
        monkeypatch.setattr(predict_today, "get_snowflake_connection", lambda: table)
        predict_today._write_prediction_log([], _DATE, scoped_game_pks=[2])
        assert table.games_on(_DATE) == {1, 3}


class TestPredictionLogScopeIsWiredFromMain:
    """`_prediction_log_delete_sql` being correct is worthless if `main()` never scopes.

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
            "slate narrowed, or one path keeps the date-wide DELETE"
        )

    def test_the_writer_no_longer_inlines_the_date(self):
        code = self._code_only(self._SRC)
        assert not _re.search(
            r"DELETE FROM baseball_data\.config\.prediction_log[^\"']*"
            r"WHERE prediction_date = '", code,
        ), "the prediction_log DELETE must bind its date, not f-string it"
