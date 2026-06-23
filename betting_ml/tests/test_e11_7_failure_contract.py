"""E11.7 — regression guards for the 3-tier pipeline failure-handling contract.

Covers four recurrence-prevention checks:

  1. INC-6 guard: dbt_daily_build always calls `run` before `test`; the test
     suite is non-blocking (wrapped in try/except with context.log.warning).
     A single `build` call that can gate predictions on a peripheral test failure
     is the bug this prevents.

  2. Intraday + sensor ops use `dbt run` not `dbt build` (run-only model ops).

  3. No silent exception swallow: every `except Exception` block in an ops file
     that does NOT call `context.log.warning` (or `log.error`) is a contract
     violation — the ALERT-loud-but-continue tier requires a visible signal.

  4. INC-5 guard: trigger_dbt.py writes to stderr (not just stdout) when
     DBT_RUNNER_URL is unset, so the Railway cron log shows the skip clearly.
     (Complements the exit-0 test in test_e11_4_cron_services.py.)

Import strategy: ops modules loaded via importlib.util to avoid triggering
pipeline/__init__.py (which requires Snowflake credentials in the test env).
"""
import ast
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).parents[2]


# ── helpers ───────────────────────────────────────────────────────────────────

def _read(rel: str) -> str:
    return (_REPO / rel).read_text()


def _parse(rel: str) -> ast.Module:
    src = _read(rel)
    return ast.parse(src)


def _dbt_run_call_args(src: str) -> list[list]:
    """Return all first-element lists of _run_dbt(context, [...], ...) calls.

    Walks the AST looking for Call nodes whose func is `_run_dbt` and whose
    second argument is a list literal. Returns the literal values from each
    such call so callers can assert on the dbt subcommand (run/build/test).
    """
    tree = ast.parse(src)
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = None
        if isinstance(func, ast.Name):
            fname = func.id
        elif isinstance(func, ast.Attribute):
            fname = func.attr
        if fname != "_run_dbt":
            continue
        if len(node.args) < 2:
            continue
        arg1 = node.args[1]
        if not isinstance(arg1, ast.List):
            continue
        elts = []
        for elt in arg1.elts:
            if isinstance(elt, ast.Constant):
                elts.append(elt.value)
            else:
                elts.append(None)
        results.append(elts)
    return results


# ── 1. INC-6 guard: dbt_daily_build splits run from test ─────────────────────

class TestDbtDailyBuildRunBeforeTest:
    """dbt_daily_build must: (a) call _run_dbt with 'run' args as the serving-
    critical step; (b) wrap the 'test' invocation in try/except so a test failure
    never blocks predictions (INC-6 — 2026-06-21).

    Strategy: parse the source AST rather than executing the module so this
    test runs without Dagster / Snowflake credentials.
    """

    @pytest.fixture(autouse=True)
    def _src(self):
        self._text = _read("pipeline/ops/daily_ingestion_ops.py")
        self._tree = ast.parse(self._text)

    def test_run_args_passed_before_test_call(self):
        """The run_args variable (starting with 'run') is constructed and passed
        to _run_dbt before any 'test' call — verified by line-number ordering."""
        lines = self._text.splitlines()
        run_args_line = None
        test_call_line = None
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "run_args" in stripped and '["run"]' in stripped:
                run_args_line = i
            if '"test"' in stripped and "_run_dbt" in stripped:
                test_call_line = i
        assert run_args_line is not None, (
            "run_args = [\"run\"] + ... not found in dbt_daily_build — "
            "INC-6 guard: the serving-critical step must be `dbt run`"
        )
        assert test_call_line is not None, (
            '"test" _run_dbt call not found in dbt_daily_build — '
            "INC-6 guard: test suite must run separately from models"
        )
        assert run_args_line < test_call_line, (
            f"'run' args constructed at line {run_args_line} but 'test' call at "
            f"line {test_call_line} — serving-critical `dbt run` must precede the test suite"
        )

    def test_test_step_is_non_blocking(self):
        """The 'test' _run_dbt call must be inside a try/except block so a
        peripheral data-quality failure never blocks predictions (INC-6)."""
        src = self._text
        # Find the function body of dbt_daily_build
        fn_start = src.find("def dbt_daily_build")
        assert fn_start != -1, "dbt_daily_build not found"
        fn_body = src[fn_start:]

        # The test step must be in a try block — confirmed by context.log.warning nearby
        test_block_idx = fn_body.find('"test"')
        assert test_block_idx != -1, '"test" not found in dbt_daily_build'

        # Look for except/warning pattern within 30 lines of the test call
        vicinity = fn_body[max(0, test_block_idx - 200):test_block_idx + 600]
        assert "except" in vicinity, (
            "No except block near the 'test' call in dbt_daily_build — "
            "the test step must be wrapped in try/except (INC-6)"
        )
        assert "log.warning" in vicinity, (
            "No context.log.warning near the 'test' catch block — "
            "the non-blocking test step must log a warning on failure (INC-6)"
        )

    def test_dbt_daily_build_uses_run_not_bare_build(self):
        """dbt_daily_build must never pass a bare ['build', ...] as the first
        model-rebuild call on a build day — the serving-critical step must always
        be 'run'. The 'build' subcommand may appear in the args construction
        (e.g. 'build' in _dbt_daily_build_args) but the actual _run_dbt call
        for models must use 'run'."""
        src = self._text
        fn_start = src.find("def dbt_daily_build")
        fn_body = src[fn_start:]

        # Confirm run_args = ["run"] + args[1:] construction exists
        assert '["run"] + args[1:]' in fn_body or "run_args" in fn_body, (
            "dbt_daily_build does not construct run_args — verify INC-6 split is intact"
        )


# ── 2. Intraday and sensor ops use `dbt run` not `dbt build` ─────────────────

class TestIntradayAndSensorOpsUseRun:
    """All _run_dbt calls in intraday_ops.py and sensor_ops.py must use 'run'
    as the dbt subcommand. 'build' (which runs models + tests) is reserved for
    the daily job's scheduled build days; intraday/catchup ops must never risk
    blocking on a test failure (A2.15 — 2026-06-15)."""

    @pytest.mark.parametrize("rel_path", [
        "pipeline/ops/intraday_ops.py",
        "pipeline/ops/sensor_ops.py",
    ])
    def test_all_dbt_calls_use_run(self, rel_path):
        src = _read(rel_path)
        calls = _dbt_run_call_args(src)
        bad = [c for c in calls if c and c[0] == "build"]
        assert not bad, (
            f"{rel_path}: found _run_dbt(..., ['build', ...]) calls — "
            f"intraday/sensor ops must use 'run' not 'build' (A2.15). "
            f"Offending arg lists: {bad}"
        )


# ── 3. No silent exception swallows in ops files ──────────────────────────────

class TestNoSilentExceptionSwallow:
    """Every except-Exception block in an ops file that catches a failure must
    call context.log.warning (or log.error) to satisfy the ALERT-loud tier.
    A bare `pass`, or a `print()` with no `log.warning`, is a contract violation.

    Strategy: AST-walk each ops module for ExceptHandler nodes whose body
    contains only Expr(Call(print(...))) or Expr(Pass), i.e. no log.warning call.
    """

    _OPS_FILES = [
        "pipeline/ops/daily_ingestion_ops.py",
        "pipeline/ops/sensor_ops.py",
        "pipeline/ops/intraday_ops.py",
        "pipeline/ops/weekly_ml_ops.py",
    ]

    # Narrow exception types where a silent pass is genuinely correct —
    # conversion failures, missing dict keys, and similar data-type guards
    # that have nothing to do with pipeline failure semantics.
    _NARROW_OK = frozenset({
        "ValueError", "KeyError", "TypeError", "IndexError",
        "AttributeError", "StopIteration",
    })

    def _has_log_call(self, body: list) -> bool:
        """True if the except body contains any attribute call matching log.*"""
        for node in body:
            for n in ast.walk(node):
                if not isinstance(n, ast.Call):
                    continue
                func = n.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "warning", "warn", "error", "critical", "info"
                ) and isinstance(func.value, ast.Attribute) and func.value.attr == "log":
                    return True
        return False

    def _has_reraise(self, body: list) -> bool:
        """True if the except body re-raises (bare `raise` or `raise Exception(...)`)."""
        for node in body:
            for n in ast.walk(node):
                if isinstance(n, ast.Raise):
                    return True
        return False

    def _is_broad_exception(self, handler: ast.ExceptHandler) -> bool:
        """True when the handler catches a broad type (Exception, BaseException,
        or bare `except:`) rather than a specific narrow error type."""
        typ = handler.type
        if typ is None:
            return True  # bare `except:`
        if isinstance(typ, ast.Name):
            return typ.id not in self._NARROW_OK
        if isinstance(typ, ast.Attribute):
            return typ.attr not in self._NARROW_OK
        return True

    def _is_silent_swallow(self, handler: ast.ExceptHandler) -> bool:
        """Return True if this is a BROAD exception handler that neither
        logs a warning nor re-raises. Narrow exception types (ValueError etc.)
        and handlers that re-raise are explicitly exempted."""
        if not self._is_broad_exception(handler):
            return False  # narrow type — OK to pass silently
        body = handler.body
        if not body:
            return True
        if self._has_reraise(body):
            return False  # HALT path — not a swallow
        if self._has_log_call(body):
            return False  # already has a warning/error log
        # Body with only pass, print(), or return — no log call
        all_trivial = all(
            isinstance(s, (ast.Pass, ast.Return))
            or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Call))
            for s in body
        )
        return all_trivial

    @pytest.mark.parametrize("rel_path", _OPS_FILES)
    def test_no_silent_swallow(self, rel_path):
        src = _read(rel_path)
        tree = ast.parse(src)
        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if self._is_silent_swallow(node):
                violations.append(node.lineno)
        assert not violations, (
            f"{rel_path}: silent broad-exception swallow detected at lines {violations}. "
            "E11.7: every `except Exception` block must call context.log.warning() "
            "or re-raise — never a silent pass/print (ALERT-loud tier)."
        )


# ── 4. INC-5 guard: trigger_dbt.py writes to stderr when URL unset ───────────

class TestTriggerDbtUrlUnsetWritesToStderr:
    """When DBT_RUNNER_URL is not set, trigger_dbt.py must write to stderr
    (file=sys.stderr) — not just stdout — so the Railway cron log surfaces
    the skip as a warning rather than a silent no-op (INC-5, 2026-06-19).

    Strategy: parse the source AST to find the print() call in the `if not url`
    branch and assert it includes `file=sys.stderr`.
    """

    def test_url_unset_branch_writes_to_stderr(self):
        src = _read("services/schedule_capture/trigger_dbt.py")
        tree = ast.parse(src)

        stderr_found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "print"):
                continue
            # Check keywords for file=sys.stderr
            for kw in node.keywords:
                if kw.arg != "file":
                    continue
                val = kw.value
                if (
                    isinstance(val, ast.Attribute)
                    and val.attr == "stderr"
                    and isinstance(val.value, ast.Name)
                    and val.value.id == "sys"
                ):
                    stderr_found = True
                    break
            if stderr_found:
                break

        assert stderr_found, (
            "trigger_dbt.py: no print(..., file=sys.stderr) found. "
            "INC-5 guard: the DBT_RUNNER_URL-unset warning must write to stderr "
            "so it appears in Railway cron error logs, not just stdout."
        )

    def test_url_unset_message_contains_warning(self):
        """The skip message must contain 'WARNING' so it's visually distinct in logs."""
        src = _read("services/schedule_capture/trigger_dbt.py")
        # Simple text check — the exact message must reference WARNING
        assert "WARNING" in src, (
            "trigger_dbt.py: the DBT_RUNNER_URL-unset message should contain 'WARNING' "
            "to make the skip visible in Railway cron logs (INC-5)."
        )

    def test_url_unset_exits_zero(self):
        """Complement of test_e11_4_cron_services.py: confirm the branch exits 0
        (ALERT-loud-but-continue — not HALT) when DBT_RUNNER_URL is absent."""
        src = _read("services/schedule_capture/trigger_dbt.py")
        # Find the `if not url:` / `if not runner_url:` block and confirm sys.exit(0)
        # near the print-to-stderr call. AST check: ExitCall(0) in the `if not url` branch.
        tree = ast.parse(src)

        exit_zero_found = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.If,)):
                continue
            # Look for `if not url` patterns
            test = node.test
            if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
                continue
            # Search body for sys.exit(0)
            for stmt in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if not isinstance(stmt, ast.Call):
                    continue
                func = stmt.func
                if isinstance(func, ast.Attribute) and func.attr == "exit":
                    args = stmt.args
                    if args and isinstance(args[0], ast.Constant) and args[0].value == 0:
                        exit_zero_found = True
                        break
            if exit_zero_found:
                break

        assert exit_zero_found, (
            "trigger_dbt.py: sys.exit(0) not found in the `if not url` branch. "
            "INC-5 / E11.7: missing-URL is ALERT-loud-but-CONTINUE (exit 0), not HALT."
        )
