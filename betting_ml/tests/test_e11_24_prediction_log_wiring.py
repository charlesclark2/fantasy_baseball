"""test_e11_24_prediction_log_wiring.py  (E11.24 P1 — fast gate)
================================================================================
The call sites, not the helpers.

`prediction_log_store` being correct buys nothing if a consumer still reads Snowflake,
if the nightly enrichment can reach today's partition, or if the daily job still runs the
reader BEFORE its own producer. Each of those was a real defect in the pre-P1 source and
each is pinned here.

⚠️ This file must NOT import `pipeline` — `pipeline/__init__.py` reads the dbt manifest,
which is ABSENT in the fast gate, so importing it kills the whole module at COLLECTION
(the E11.23 rule). The job graph is therefore read with `ast`, which also makes every
clause comment-immune by construction (INC-38).
"""
from __future__ import annotations

import ast
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
JOB = REPO / "pipeline" / "jobs" / "daily_ingestion_job.py"
HEALTH = REPO / "scripts" / "compute_model_health.py"
BACKFILL = REPO / "scripts" / "backfill_prediction_log.py"
MIGRATE = REPO / "scripts" / "migrate_prediction_log_to_s3.py"


def _code_only(path: pathlib.Path) -> str:
    """Source with comments AND docstrings removed.

    Both halves are load-bearing. Every clause below looks for the ABSENCE of something,
    and this migration deliberately left long comments and docstrings that NAME the
    statements it removed ("the DELETE was the #2 waker", "UPDATE sweeps") — so a scan
    over raw source would be satisfied by the prose describing the fix and would stay
    green if the fix itself were reverted. That is the INC-38 vacuous-guard class, and it
    fired here on the first cut: three clauses failed on their own explanatory text.

    Docstrings are removed structurally (bare string expressions in the AST), NOT by a
    quote-matching regex, so a SQL constant assigned to a name — which is what the
    clauses about `commence_time::timestamp` and `prediction_date < ?` need to see —
    survives untouched.
    """
    src = path.read_text()
    lines = src.splitlines()
    blank: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        body = getattr(node, "body", None)
        if not isinstance(body, list):   # Lambda / IfExp carry a single node, not a list
            continue
        for child in body:
            if (isinstance(child, ast.Expr)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)):
                blank.update(range(child.lineno, (child.end_lineno or child.lineno) + 1))
    return "\n".join(
        "" if (i + 1) in blank else l
        for i, l in enumerate(lines)
        if not l.lstrip().startswith("#")
    )


def test_code_only_strips_prose_but_keeps_sql():
    """The stripper itself, pinned — if it stopped removing docstrings every absence
    clause in this file would silently go vacuous."""
    assert "Snowflake-free" not in _code_only(BACKFILL)             # module docstring
    assert "commence_time::timestamp" in _code_only(BACKFILL)      # a SQL constant


# ═══════════════════════════════════════════════════════════════════════════════
# INC-25 — the reader must run DOWNSTREAM of its own producer
# ═══════════════════════════════════════════════════════════════════════════════


class TestDailyJobOrdering:
    """`backfill_prediction_log` WRITES actual_outcome/closing_market_prob;
    `compute_model_health` READS them over a rolling 14-day window. Pre-P1 the reader ran
    FIRST, so the health metric was permanently one enrichment cycle behind its producer.

    Asserted as a dependency EDGE, never as source-line order: `in_process_executor` runs
    the graph TOPOLOGICALLY, so "which line comes first" is not the thing that decides
    execution order (INC-40) — a line-order test would be vacuous.
    """

    @staticmethod
    def _edges() -> dict[str, str]:
        """{callee: the op whose result was passed as its `start`}, resolved through the
        intermediate variable assignments the job uses (`s22 = backfill(...)`)."""
        tree = ast.parse(JOB.read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "daily_ingestion_job")
        produced_by: dict[str, str] = {}
        edges: dict[str, str] = {}

        def call_name(node):
            return node.func.id if isinstance(node.func, ast.Name) else None

        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                name = call_name(node.value)
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and name:
                        produced_by[tgt.id] = name
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and call_name(node):
                for kw in node.keywords:
                    if kw.arg == "start" and isinstance(kw.value, ast.Name):
                        edges[call_name(node)] = produced_by.get(kw.value.id, kw.value.id)
        return edges

    def test_the_graph_was_parsed(self):
        """Non-vacuity: an empty edge map would pass every clause below on nothing."""
        edges = self._edges()
        assert "compute_model_health" in edges and "backfill_prediction_log" in edges

    def test_model_health_depends_on_the_backfill(self):
        assert self._edges()["compute_model_health"] == "backfill_prediction_log", (
            "compute_model_health READS what backfill_prediction_log writes — it must "
            "sit downstream of it in the SAME run (INC-25)"
        )

    def test_the_backfill_does_not_depend_on_model_health(self):
        """The clause that makes the one above non-trivial: the edge must not be a cycle
        or simply reversed."""
        assert self._edges()["backfill_prediction_log"] != "compute_model_health"


# ═══════════════════════════════════════════════════════════════════════════════
# compute_model_health — the read left Snowflake
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelHealthReadsS3:
    def test_no_snowflake_query_against_the_prediction_log(self):
        code = _code_only(HEALTH)
        assert not re.search(r"FROM\s+baseball_data\.config\.prediction_log", code, re.I)

    def test_it_goes_through_the_store(self):
        assert "prediction_log_store" in _code_only(HEALTH)

    def test_the_reader_is_actually_invoked(self):
        """Wired ≠ invoked (NF-C0e): the helper must be CALLED from `run`, not merely
        defined."""
        tree = ast.parse(HEALTH.read_text())
        run = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "run")
        called = {n.func.id for n in ast.walk(run)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_fetch_prediction_log" in called

    def test_the_project_root_is_on_sys_path(self, monkeypatch):
        """`_run_script` invokes this by ABSOLUTE path, so sys.path[0] is scripts/, NOT the
        repo root — `from scripts.utils import ...` does not resolve without an explicit
        insert. That fails at runtime only, i.e. exactly where CI cannot see it.

        Measured on the EFFECT, not on the presence of the line: wrapping the insert in a
        dead branch leaves `sys.path.insert(...)` in the source, so a text scan for it
        stays green. (And a subprocess probe cannot discriminate either — the project is
        pip-installed into the venv, so `scripts.utils` resolves from site-packages
        whatever the module does. The RED proof caught both.)
        """
        import importlib.util

        monkeypatch.setattr(
            "sys.path", [p for p in __import__("sys").path if p != str(REPO)]
        )
        spec = importlib.util.spec_from_file_location("_cmh_path_probe", HEALTH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert str(REPO) in __import__("sys").path, (
            "compute_model_health must put the repo root on sys.path itself — the box "
            "sets PYTHONPATH=/app, but a laptop/hand run has neither that nor the repo "
            "root on the path"
        )

    def test_the_model_health_log_write_is_still_snowflake(self):
        """Stated, not assumed: this script is NOT fully Snowflake-free after P1. The
        `model_health_log` INSERT remains, so the op still resumes COMPUTE_WH once a day.
        If a later story moves it, this clause is the one to update — deliberately, so
        the residual can never be quietly mis-reported as already handled."""
        assert "INSERT INTO" in _code_only(HEALTH)


# ═══════════════════════════════════════════════════════════════════════════════
# backfill_prediction_log — Snowflake-free, and bounded away from today
# ═══════════════════════════════════════════════════════════════════════════════


class TestBackfillIsSnowflakeFree:
    def test_no_snowflake_import(self):
        tree = ast.parse(BACKFILL.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith("snowflake") for a in node.names)
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("snowflake")

    def test_no_update_statements_survive(self):
        assert not re.search(r"UPDATE\s+baseball_data", _code_only(BACKFILL), re.I)

    def test_it_reads_through_the_store(self):
        assert "prediction_log_store" in _code_only(BACKFILL)


class TestBackfillCannotReachTodaysPartition:
    """The `dt < today` bound is load-bearing TWICE and is easy to lose in a refactor.

    CORRECTNESS: the pre-game filter (`ingestion_ts < commence_time`) is satisfied by a
    MORNING snapshot too, so enriching a game that has not started freezes a "closing"
    price hours early — and because enrichment only fills NULLs, it sticks. Measured on
    game 822859 (2026-08-18): stored 0.605935, an ~18:00-21:00 UTC snapshot, against a
    true last pre-game price of 0.592235.
    CONCURRENCY: today's partition is the only one an overlapping predict run can append
    to, and compaction rewrites a partition.
    """

    def test_the_candidate_query_is_strictly_before_the_bound(self):
        code = _code_only(BACKFILL)
        assert re.search(r"prediction_date\s*<\s*\?", code), (
            "candidate partitions must be bounded strictly BELOW the end date — a `<=` "
            "would let the enrichment reach today"
        )
        assert not re.search(r"prediction_date\s*<=\s*\?", code)

    def test_the_default_bound_is_the_current_baseball_day(self):
        """`date.today()` on the box is the UTC day, which rolls over during US evening
        games (INC-22). The bound must come from the baseball-day helper."""
        code = _code_only(BACKFILL)
        assert "current_game_date" in code
        assert not re.search(r"\bdate\.today\(\)", code)
        assert not re.search(r"utcnow\(\)\.date\(\)", code)

    def test_compaction_only_deletes_the_keys_it_listed(self):
        """A part appended between the listing and the write must survive — compaction is
        not allowed to be a truncate."""
        code = _code_only(BACKFILL)
        assert re.search(r"replace_keys\s*=\s*pred_log\.list_partition_keys", code) or \
               re.search(r"replace_keys\s*=\s*replace_keys", code)
        assert "list_partition_keys" in code

    def test_a_commence_time_comparison_casts_the_string_column(self):
        """`commence_time` is a string-wrapped timestamp in the lakehouse parquet (the W8a
        binary-timestamp cure). An un-cast comparison against a TIMESTAMP is the INC-23
        binder failure; an un-cast `=` is the E9.52 silent-empty."""
        code = _code_only(BACKFILL)
        assert "commence_time::timestamp" in code
        assert not re.search(r"commence_time(?!::)\s*(?:<|>|=)", code)


# ═══════════════════════════════════════════════════════════════════════════════
# The one-time migration
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigrationReconstruction:
    def test_kelly_is_recomputed_not_copied(self):
        """The two tables mean different things by `kelly_fraction`: prediction_log stores
        the RAW calibrated-vs-market Kelly, daily_model_predictions the POSTERIOR one,
        which is ~0 because best_alpha = 0. Copying the column silently zeroes every
        reconstructed row — caught by diffing a reconstruction of four healthy dates
        against what predict_today really logged (112/112 keys, kelly the ONLY column
        that disagreed)."""
        code = _code_only(MIGRATE)
        assert "compute_kelly" in code and "compute_edge" in code
        assert "h2h_kelly_fraction" not in code
        assert "totals_kelly_fraction" not in code

    def test_it_writes_nothing_to_snowflake(self):
        code = _code_only(MIGRATE)
        for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE"):
            assert verb not in code.upper().replace("CREATE OR REPLACE TEMP TABLE", "")

    def test_the_repair_only_adds_missing_keys(self):
        """A surviving Snowflake row is migrated verbatim; the repair must never overwrite
        a real logged value with a reconstruction."""
        code = _code_only(MIGRATE)
        assert re.search(r"if\s+_key\(r\)\s+not\s+in\s+have", code)

    def test_loaded_at_is_normalised_per_game(self):
        """The view resolves a game to the latest batch that OWNED it, so two markets of
        one game carrying different stamps would drop the older one."""
        assert "_normalise_loaded_at" in _code_only(MIGRATE)
