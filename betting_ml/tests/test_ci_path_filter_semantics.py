"""E9.63b — the CI path filter must actually subtract.

WHY THIS EXISTS. `.github/workflows/ci.yml`'s `changes` job decides whether the six pytest shards,
the slow gate and the model smoke test run at all. It expresses that as a `dorny/paths-filter` rule:

    backend:
      - '**'
      - '!frontend/**'
      - '!**/*.md'
      - '!docs/**'

which reads as "everything, minus the frontend and the docs" and is NOT what the action does by
default. The action compiles each list entry into its own picomatch matcher and defaults to
`predicate-quantifier: some` — a file selects the filter if ANY ONE pattern matches. `'**'` matches
every path on earth, so `some` is satisfied before the `!` lines are consulted and they subtract
nothing whatsoever. The filter returned `true` for every possible diff from E9.7 (2026) until
E9.63b, i.e. the behaviour the job exists to provide had never once occurred.

MEASURED against picomatch 4 with the action's own MatchOptions (`{dot: true}`):

    file                     some (the bug)   every (correct)
    frontend/package.json         True             False
    docs/readme.md                True             False
    README.md                     True             False
    betting_ml/x.py               True             True

It stayed invisible because `ci.yml` only triggered on `dev` → `main` release PRs, whose
accumulated diff always contains backend files — so the filter was never asked a question whose
right answer was `false`. Zero skipped jobs across the last 30 runs at the time of writing.

⚠️ THIS TEST IS THE ONLY THING STANDING BETWEEN THAT DEFECT AND ITS RETURN. It is a one-line
deletion away, it fails open (silently over-running CI rather than breaking anything), and the
symptom — "CI is a bit slow on frontend PRs" — is one nobody files a bug about. Deleting
`predicate-quantifier` must fail this test; that is verified by `e2e`-style red-proof in the E9.63b
handoff and is trivially re-checkable by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _paths_filter_steps() -> list[dict]:
    """Every `dorny/paths-filter` step in ci.yml, across all jobs."""
    if not CI_WORKFLOW.is_file():
        return []
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    steps = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            if isinstance(step, dict) and "dorny/paths-filter" in str(step.get("uses", "")):
                steps.append(step)
    return steps


def test_ci_workflow_is_present_and_parses():
    # A guard that cannot find its subject passes vacuously. Fail loudly instead.
    assert CI_WORKFLOW.is_file(), f"{CI_WORKFLOW} not found — did the workflow move?"
    assert _paths_filter_steps(), "no dorny/paths-filter step found in ci.yml"


def test_a_negating_filter_must_use_the_every_quantifier():
    """A `!`-negated pattern beside a broad one is inert under the default quantifier.

    This is the exact signature of the shipped defect: a list that MIXES an all-matching pattern
    with `!` exclusions, without `predicate-quantifier: every`. Under `some` the exclusions are
    decorative and the filter is always true.

    ⚠️ Deliberately a LOOP, not `@pytest.mark.parametrize`. Parametrising over
    `_paths_filter_steps()` evaluates it at COLLECTION time, so a workflow that moved or failed to
    parse would produce an empty parameter set — and a parametrised test with zero cases does not
    fail, it silently does not run. That is the vacuous-guard shape this repo keeps getting bitten
    by; asserting the set is non-empty inside the test is what makes it impossible here.
    """
    steps = _paths_filter_steps()
    assert steps, "no dorny/paths-filter step found in ci.yml — this guard has nothing to check"

    for step in steps:
        with_block = step.get("with", {}) or {}
        filters = yaml.safe_load(with_block.get("filters", "") or "{}") or {}

        negating = {
            name: patterns
            for name, patterns in filters.items()
            if isinstance(patterns, list) and any(str(p).startswith("!") for p in patterns)
        }
        if not negating:
            continue  # no exclusions in this step, so the quantifier cannot matter

        quantifier = with_block.get("predicate-quantifier")
        assert quantifier == "every", (
            f"filters {sorted(negating)} use `!` exclusions, which the action's DEFAULT "
            f"`predicate-quantifier: some` makes INERT — any single pattern matching is enough, "
            f"and a broad pattern like '**' matches everything. Got "
            f"predicate-quantifier={quantifier!r}; set it to 'every' so the exclusions subtract."
        )


def test_the_backend_filter_still_excludes_the_frontend_and_docs():
    """The intent, pinned separately from the mechanism.

    The test above pins HOW (the quantifier). This pins WHAT: whichever way the rule is expressed,
    the `backend` filter must still name the frontend and the docs as things it excludes. A future
    rewrite that quietly drops `!frontend/**` would satisfy the quantifier check and silently put
    six pytest shards back on every frontend PR.
    """
    step = _paths_filter_steps()[0]
    filters = yaml.safe_load((step.get("with", {}) or {}).get("filters", "") or "{}") or {}
    backend = [str(p) for p in filters.get("backend", [])]

    assert backend, "ci.yml has no `backend` filter — the test jobs' `if:` gate reads its output"
    assert "!frontend/**" in backend, f"`backend` no longer excludes the frontend: {backend}"
    assert "!docs/**" in backend, f"`backend` no longer excludes docs/: {backend}"


def test_every_job_that_runs_pytest_is_gated_on_the_filter():
    """The filter is only as good as its consumers.

    `changes` computing `backend=false` achieves nothing if a test job forgets its `if:`. This
    walks the jobs rather than trusting the comment above them — a job added later inherits the
    requirement automatically.
    """
    assert CI_WORKFLOW.is_file(), f"{CI_WORKFLOW} not found — did the workflow move?"
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    ungated = []
    for name, job in workflow.get("jobs", {}).items():
        runs_pytest = any(
            "pytest" in str(step.get("run", "")) for step in (job.get("steps") or []) if isinstance(step, dict)
        )
        if not runs_pytest:
            continue
        if "needs.changes.outputs.backend" not in str(job.get("if", "")):
            ungated.append(name)

    assert not ungated, (
        f"job(s) {ungated} run pytest without gating on `needs.changes.outputs.backend` — they will "
        f"run on a frontend-only PR no matter what the filter decides"
    )


# ── E11.24 — the dbt CI must not bill the warehouse the story is quieting ────────────────

DBT_CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dbt_build_ci.yml"


def test_dbt_ci_prefers_a_dedicated_warehouse_over_the_production_one():
    """E11.24 — `dbt Build CI` fires on push/PR to `main` whenever `dbt/**` changes, i.e. on
    exactly the promotion days E11.24 reads its soak baselines from.

    Measured 2026-08-10: the `CI on the prod WH` family is the largest single wait bucket on the
    census board, and on the #720 promotion day its 39 waits were the ENTIRE apparent eb_*
    "regression" — a session nearly read them as a serving defect. Pin the indirection so a future
    sweep over `secrets.SNOWFLAKE_WAREHOUSE` cannot quietly put CI back on COMPUTE_WH.

    The `||` fallback is what makes this safe to ship before the warehouse exists: an unset GitHub
    secret is the empty string (falsy), so CI keeps today's behaviour until the operator creates
    the warehouse and sets `SNOWFLAKE_CI_WAREHOUSE`.
    """
    assert DBT_CI_WORKFLOW.exists(), "dbt_build_ci.yml is missing."
    src = DBT_CI_WORKFLOW.read_text()
    # Strip comments — prose naming the secret must not be able to satisfy this (INC-38).
    # ⚠️ BOTH forms, and the trailing one is the one that bites: a whole-line strip alone left
    #   `SNOWFLAKE_WAREHOUSE: ${{ secrets.SNOWFLAKE_WAREHOUSE }}  # use SNOWFLAKE_CI_WAREHOUSE`
    # passing — measured, in this guard's own RED-proof. YAML starts a comment at a ` #` that is
    # not inside the value; no expression here contains a literal '#'.
    code = "\n".join(
        ln.split(" #", 1)[0] for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )

    assignments = re.findall(r"^\s*SNOWFLAKE_WAREHOUSE:\s*(.+)$", code, re.MULTILINE)
    assert assignments, "no SNOWFLAKE_WAREHOUSE assignment found in dbt_build_ci.yml."
    for value in assignments:
        assert "SNOWFLAKE_CI_WAREHOUSE" in value, (
            "every dbt-CI job must resolve SNOWFLAKE_WAREHOUSE through SNOWFLAKE_CI_WAREHOUSE "
            f"first (with a fallback), not straight from the production secret. Found: {value!r}"
        )
        assert "MONITOR_WH" not in value, (
            "⛔ dbt CI must NOT share MONITOR_WH — that is the wake census's own read path, so "
            "CI would become a line in the instrument that measures CI (target 3's "
            "self-inflicted-wake defect)."
        )
