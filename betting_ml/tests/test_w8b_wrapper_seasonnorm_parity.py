"""E9.53 — the `_seasonnorm` expression exists TWICE and the two copies must not drift.

THE TRAP: `feature_pregame_game_features` is the public served feature surface, but its
contact_quality_columns() for-loop cannot be rendered by run_w1_lakehouse's `extract_duckdb_sql`.
So the DuckDB → S3 parquet that predict_today and the serving writers actually read is generated
by a PYTHON PORT — `scripts/run_w1_lakehouse.py::_game_features_wrapper_sql` — not from the .sql
file. Editing only the dbt model is a NO-OP on the served store (and vice versa): the dbt model
and the served parquet silently diverge, which is invisible to CI (all IO mocked), to
`dbtf compile` (the .sql file is fine on its own) and to parity-over-parquet (both sides read the
same already-wrong parquet).

`test_python_port_matches_the_dbt_model_expression` renders the dbt model's Jinja loop body for a
concrete column and compares it to the Python port's line for that same column, so a change made
in one place and not the other goes RED regardless of what the change is.

✅ E1.13 (2026-08-14): the E9.53 NULL cure is APPLIED in both copies. The expression is now
`case when raw.<c> is null then null else coalesce(..., 0) end` — a missing RAW feature carries a
real NULL (imputer + discriminative_coverage see it) while a missing/zero-variance BASELINE with a
present raw still coalesces to 0 (the documented regime-neutral behaviour).
`TestE1_13CureAMissingRawIsNull` pins the CURED behaviour (these are the three tests the E1.12/E1.13
deferral named to flip); the two baseline-coalesce tests survive unchanged.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import duckdb
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "run_w1_lakehouse.py"
_MODEL = _PROJECT_ROOT / "dbt" / "models" / "feature" / "feature_pregame_game_features.sql"

_PROBE = "home_bp_eb_xwoba"   # a real contact-quality column, and a core discriminative one


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_w1_lakehouse", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rwl = _load_runner()
WRAPPER_SQL = rwl._game_features_wrapper_sql()


def _norm(s: str) -> str:
    """Normalise to SEMANTICS, so formatting is not mistaken for drift.

    The dbt model wraps its coalesce over several lines while the Python port emits one line; both
    are the same expression. Collapse whitespace runs, then drop whitespace adjacent to `(`, `)`
    and `,` so only real token differences survive.
    """
    s = re.sub(r"\s+", " ", s).strip().rstrip(",")
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s*,\s*", ",", s)
    return s


def _dbt_expression_for(col: str) -> str:
    """Render the dbt model's `{%- for c in cc %}` body for one column.

    Extracts the loop body, drops the trailing comma control tag, and substitutes the column —
    i.e. exactly what dbt would emit for that column.
    """
    src = _MODEL.read_text()
    m = re.search(r"\{%-?\s*for c in cc\s*%\}(.*?)\{%-?\s*endfor\s*%\}", src, re.S)
    assert m, "could not find the contact-quality for-loop in the dbt model"
    body = m.group(1)
    body = re.sub(r"\{\{\s*\",\" if not loop\.last\s*\}\}", "", body)
    return _norm(body.replace("{{ c }}", col))


def _port_expression_for(col: str) -> str:
    """The Python port's emitted line for one column (the SERVED build)."""
    for line in WRAPPER_SQL.splitlines():
        if line.strip().endswith(f"as {col}_seasonnorm") or f"as {col}_seasonnorm" in line:
            return _norm(line)
    pytest.fail(f"the Python port emits no _seasonnorm expression for {col}")


class TestTheTwoCopiesAgree:
    """The durable guard: whatever the expression IS, both copies must say the same thing."""

    def test_python_port_matches_the_dbt_model_expression(self):
        assert _port_expression_for(_PROBE) == _dbt_expression_for(_PROBE), (
            "the SERVED Python port (run_w1_lakehouse._game_features_wrapper_sql) and the dbt "
            "model feature_pregame_game_features.sql have DRIFTED. The port is what builds the "
            "served parquet; editing only the .sql file is a no-op on serving. Change both."
        )

    @pytest.mark.parametrize("col", ["home_bp_eb_xwoba", "home_team_sequential_bullpen_xwoba",
                                    "away_team_sequential_bullpen_xwoba"])
    def test_parity_holds_for_the_e9_53_blocks_specifically(self, col):
        assert _port_expression_for(col) == _dbt_expression_for(col)

    def test_both_cover_the_same_column_set(self):
        # The dbt model loops over contact_quality_columns(); the port must use the same list, or a
        # column is season-normalized on one side only.
        py_cols = {n[: -len("_seasonnorm")] for n in
                   re.findall(r"::double as (\w+_seasonnorm)", WRAPPER_SQL)}
        assert py_cols == set(rwl._contact_quality_columns())
        assert len(py_cols) == len(rwl._contact_quality_columns())   # no dupes
        # …and the blocks this story is about are in it.
        assert "home_team_sequential_bullpen_xwoba" in py_cols
        assert "home_bp_eb_xwoba" in py_cols

    def test_python_port_keeps_the_inc19_double_pin(self):
        assert ")::double as " in WRAPPER_SQL, "the INC-19 ::double pin was lost in the port"
        names = re.findall(r"::double as (\w+_seasonnorm)", WRAPPER_SQL)
        assert len(names) == len(set(names)) == len(rwl._contact_quality_columns())


class TestE1_13CureAMissingRawIsNull:
    """✅ E1.13 — these pin the CURED behaviour (the three tests the deferral named, flipped).

    A missing RAW feature now carries NULL through to the _seasonnorm column; a missing or
    zero-variance BASELINE with a present raw still coalesces to 0 (correct and intended).
    """

    @pytest.fixture()
    def con(self):
        c = duckdb.connect(":memory:")
        yield c
        c.close()

    def _seasonnorm(self, con, raw, mu, sd):
        """Execute the SERVED expression verbatim for one (raw, mu, sd)."""
        expr = _port_expression_for(_PROBE).rsplit(" as ", 1)[0]
        sql = (f"select {expr} as v from "
               f"(select {'null' if raw is None else raw}::double as {_PROBE}) raw, "
               f"(select {'null' if mu is None else mu}::double as {_PROBE}__mu, "
               f"{'null' if sd is None else sd}::double as {_PROBE}__sd) b")
        (v,) = con.execute(sql).fetchone()
        return v

    def test_a_missing_raw_feature_is_served_as_null(self, con):
        # ✅ THE E1.13 CURE. A missing core feature is served as NULL ("we don't know"),
        # never as a fabricated "exactly league average" 0.0.
        assert self._seasonnorm(con, None, 0.310, 0.020) is None

    def test_a_missing_raw_is_distinguishable_from_a_genuinely_average_one(self, con):
        # The masking E9.53 diagnosed is gone: a MISSING feature (NULL) and a genuinely
        # league-average one (0.0) now produce different served values, so imputed-count /
        # not-null checks can tell them apart.
        missing = self._seasonnorm(con, None, 0.310, 0.020)
        genuinely_average = self._seasonnorm(con, 0.310, 0.310, 0.020)
        assert missing is None
        assert genuinely_average == pytest.approx(0.0)

    def test_the_seasonnorm_column_is_null_when_its_raw_is_null(self, con):
        # A missing raw dominates a missing baseline: still NULL, never a fabricated 0.
        # (check_feature_block_coverage.py keeps probing RAW columns — raw remains the
        # sharper detector and that rule is unchanged.)
        assert self._seasonnorm(con, None, None, None) is None

    # ── these two are CORRECT behaviour and survived E1.13 unchanged ──
    def test_a_missing_baseline_correctly_coalesces_to_zero(self, con):
        # No baseline → regime-neutral 0. Documented + intended; keep it.
        assert self._seasonnorm(con, 0.330, None, None) == pytest.approx(0.0)

    def test_zero_variance_correctly_coalesces_to_zero(self, con):
        assert self._seasonnorm(con, 0.330, 0.310, 0.0) == pytest.approx(0.0)

    def test_a_present_raw_with_a_healthy_baseline_z_scores(self, con):
        assert self._seasonnorm(con, 0.330, 0.310, 0.020) == pytest.approx(1.0)
