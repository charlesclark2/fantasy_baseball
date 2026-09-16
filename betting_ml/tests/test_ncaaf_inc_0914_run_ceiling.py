"""NCAAF-INC-0914 (2026-09-14) — the sports dbt builds had no run-level ceiling and no
concurrency group, and both gaps were measured on the box the day the incident fired.

WHAT HAPPENED. The 18:00:15Z Orchestration-CD deploy recreated `dagster-codeloc` — which is both
the code server and the run worker — 1 second after run 06d7352c logged its first dbt command.
Five runs died in that one event, and they surfaced at THREE different latencies:

  * three runs still in STARTING  -> Dagster's 180 s start-timeout           -> ~3 minutes
  * `intraday_schedule_job`       -> its own E11.26 `dagster/max_runtime` 1500 -> 26 minutes
  * `sports_ncaaf_dbt_build_job`  -> the instance-wide 14400 s cap            -> 4 HOURS

The difference was entirely whether the job carried a ceiling of its own. `DefaultRunLauncher`
does not implement `supports_check_run_worker_health`, so once a run reaches STARTED this
instance never checks whether its worker is alive — there is no backstop but the cap, and the
alert that eventually fires ("This job is being forcibly marked as failed…") names no cause.

⚠️ These clauses pin a DETECTION-LATENCY BOUND, not the cure. The cause — a drain that could not
see a run in STARTING — is fixed in `services/dagster/aws/deploy.sh` and pinned by
`test_deploy_concurrency_guard.py::TestTheDrainDoesNotFailOpen`.

Source-inspection + AST, so the suite imports nothing from `pipeline` and stays in the fast gate
(E11.23: `pipeline/__init__.py` reads the dbt manifest at import and dies at COLLECTION without
it). AST rather than substring matching because a comment mentioning a tag must not satisfy a
clause that a missing tag should fail (INC-38).
"""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_JOB_FILE = _ROOT / "pipeline" / "jobs" / "sports_dbt_job.py"

#: The two jobs that build the shared sports DuckDB.
_DBT_BUILD_JOBS = ("sports_ncaaf_dbt_build_job", "sports_nfl_dbt_build_job")

#: Dagster's own tag key. Hardcoded rather than imported so this file never imports dagster.
_MAX_RUNTIME_TAG = "dagster/max_runtime"

#: These schedules fire daily in season, so the cadence the ceiling must sit under is one day.
_CADENCE_SECONDS = 86_400


@pytest.fixture(scope="module")
def job_src() -> str:
    assert _JOB_FILE.exists(), f"missing {_JOB_FILE}"
    return _JOB_FILE.read_text()


@pytest.fixture(scope="module")
def job_tree(job_src: str) -> ast.Module:
    return ast.parse(job_src)


def _job_decorator(tree: ast.Module, fn_name: str) -> ast.Call:
    """The `@job(...)` decorator Call node for `fn_name`. Fails loudly if the job is gone."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", None) == "job":
                    return dec
            pytest.fail(f"{fn_name} is not decorated with a @job(...) call")
    pytest.fail(f"{fn_name} not found in {_JOB_FILE.name}")


def _resolved_tags(tree: ast.Module, src: str, fn_name: str) -> dict[str, str]:
    """The job's `tags=` mapping, resolving a module-level dict alias to its literal value.

    Follows the alias deliberately: writing the tags into a shared constant is the right way to
    express "these two jobs share one group", and a guard that only understood an inline literal
    would push the source toward duplication to satisfy it.
    """
    dec = _job_decorator(tree, fn_name)
    tags = next((kw.value for kw in dec.keywords if kw.arg == "tags"), None)
    assert tags is not None, (
        f"{fn_name} carries no `tags=`. Without them it inherits the instance-wide "
        f"max_runtime_seconds (14400 s, sized for the Sunday MLB full refresh) and nothing "
        f"serialises it against its sibling build on the shared DuckDB file (NCAAF-INC-0914)."
    )
    if isinstance(tags, ast.Name):
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == tags.id for t in node.targets
            ):
                tags = node.value
                break
    assert isinstance(tags, ast.Dict), f"{fn_name}'s tags must resolve to a dict literal"
    out: dict[str, str] = {}
    for k, v in zip(tags.keys, tags.values):
        key = k.value if isinstance(k, ast.Constant) else _MAX_RUNTIME_TAG
        out[str(key)] = ast.unparse(v)
    return out


def _constants(tree: ast.Module) -> dict[str, int]:
    """Evaluate the module's integer constants with `os.environ` empty, i.e. the committed
    defaults — the values that are actually in force on the box unless someone overrides them."""
    ns: dict[str, object] = {"os": types.SimpleNamespace(environ={})}
    wanted = {"DBT_TIMEOUT_SECONDS", "_DBT_LEGS_PER_JOB", "JOB_MAX_RUNTIME_SECONDS"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in wanted for t in node.targets
        ):
            exec(compile(ast.Module([node], []), "<consts>", "exec"), ns)  # noqa: S102
    return {k: v for k, v in ns.items() if k in wanted and isinstance(v, int)}


class TestEverySportsDbtBuildCarriesItsOwnCeiling:
    """E11.26's rule, applied to the job family that never got it."""

    @pytest.mark.parametrize("fn_name", _DBT_BUILD_JOBS)
    def test_the_job_declares_a_max_runtime(self, job_tree, job_src, fn_name) -> None:
        tags = _resolved_tags(job_tree, job_src, fn_name)
        assert _MAX_RUNTIME_TAG in tags, (
            f"{fn_name} must declare `{_MAX_RUNTIME_TAG}`. On 2026-09-14 the run without one sat "
            f"invisible for 4 h against a job whose measured runtime is ~3 min, while a sibling "
            f"killed by the SAME event was caught in 26 min by its own ceiling."
        )

    def test_the_ceiling_is_sized_from_the_legs_rather_than_guessed(self, job_tree) -> None:
        """E11.26: `leg_cap < job_ceiling < cadence`, derived from a design quantity."""
        c = _constants(job_tree)
        for name in ("DBT_TIMEOUT_SECONDS", "_DBT_LEGS_PER_JOB", "JOB_MAX_RUNTIME_SECONDS"):
            assert name in c, f"{name} must be a module-level int constant (got {sorted(c)})"
        worst_case = c["_DBT_LEGS_PER_JOB"] * c["DBT_TIMEOUT_SECONDS"]
        assert c["JOB_MAX_RUNTIME_SECONDS"] > worst_case, (
            f"the ceiling ({c['JOB_MAX_RUNTIME_SECONDS']}s) must exceed the worst case the legs "
            f"can legitimately take ({c['_DBT_LEGS_PER_JOB']} x {c['DBT_TIMEOUT_SECONDS']} = "
            f"{worst_case}s). A ceiling BELOW the legs would preempt a slow-but-healthy build and "
            f"replace its diagnosable leg timeout with the cause-free forcible-failure message."
        )
        assert c["DBT_TIMEOUT_SECONDS"] < c["JOB_MAX_RUNTIME_SECONDS"] < _CADENCE_SECONDS, (
            f"E11.26 invariant `leg_cap < job_ceiling < cadence` violated: "
            f"{c['DBT_TIMEOUT_SECONDS']} < {c['JOB_MAX_RUNTIME_SECONDS']} < {_CADENCE_SECONDS}"
        )

    def test_the_ceiling_default_is_derived_from_the_leg_cap_not_a_literal(self, job_src) -> None:
        """A hardcoded number drifts silently the day someone moves the leg cap."""
        assert "_DBT_LEGS_PER_JOB * DBT_TIMEOUT_SECONDS" in job_src, (
            "JOB_MAX_RUNTIME_SECONDS's default must be COMPUTED from the leg cap, so the "
            "`leg_cap < job_ceiling` invariant cannot be broken by editing one of them alone"
        )


class TestTheTwoBuildsCannotRaceOnTheSharedDuckDB:
    """`sports_ncaaf_dbt_schedule` and `sports_nfl_dbt_schedule` carry the IDENTICAL cron
    (`0 11` America/Los_Angeles) and materialize into ONE DuckDB file (profiles.yml resolves a
    single `SPORTS_DUCKDB_PATH` for both sports, separate schemas). DuckDB's write lock is
    exclusive, so on any day both game-day gates open, whichever opens second dies on the lock.
    Both schedules were verified RUNNING on the box 2026-09-15."""

    @pytest.mark.parametrize("fn_name", _DBT_BUILD_JOBS)
    def test_the_job_declares_a_concurrency_group(self, job_tree, job_src, fn_name) -> None:
        tags = _resolved_tags(job_tree, job_src, fn_name)
        assert "concurrency_group" in tags, (
            f"{fn_name} must declare a `concurrency_group` — `tag_concurrency_limits` in "
            f"services/dagster/dagster.yaml caps it at 1 run per unique value, which is what "
            f"queues one build behind the other instead of racing the DuckDB write lock"
        )

    def test_both_builds_share_one_group(self, job_tree, job_src) -> None:
        groups = {
            fn: _resolved_tags(job_tree, job_src, fn)["concurrency_group"]
            for fn in _DBT_BUILD_JOBS
        }
        assert len(set(groups.values())) == 1, (
            f"the NCAAF and NFL builds must share ONE concurrency group — they contend for the "
            f"same DuckDB file, so per-job groups serialise each job against itself and leave the "
            f"cross-sport collision wide open. Got: {groups}"
        )
