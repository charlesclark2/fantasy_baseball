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
#
# 🪤 THE DEFECT THIS GUARD EXISTS TO PREVENT, AND ITS FIRST CUT *HAD*: the workflow set
# `SNOWFLAKE_WAREHOUSE`, which dbt NEVER READS — `dbt/profiles.yml` hardcoded the warehouse in
# every target. A declaration with no consumer (NF-C0e "wired ≠ invoked"), and a guard asserting
# only the declaration passes on nothing. So this asserts BOTH ENDS: the `ci` target must be
# env-driven, AND the job that runs `--target ci` must supply that var non-empty.

DBT_CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dbt_build_ci.yml"
DBT_PROFILES = Path(__file__).resolve().parents[2] / "dbt" / "profiles.yml"
_CI_WH_ENV = "SNOWFLAKE_CI_WAREHOUSE"


def test_the_ci_target_actually_reads_the_ci_warehouse_env_var():
    """THE CONSUMER END. dbt resolves its warehouse from profiles.yml, not from the shell, so
    only an `env_var()` here can move CI off COMPUTE_WH."""
    outputs = yaml.safe_load(DBT_PROFILES.read_text())["baseball_betting_and_fantasy"]["outputs"]
    ci_wh = outputs["ci"]["warehouse"]
    assert _CI_WH_ENV in ci_wh, (
        f"the `ci` dbt target must resolve its warehouse from {_CI_WH_ENV} — a workflow env var "
        f"alone is inert, because dbt reads profiles.yml. Found: {ci_wh!r}"
    )
    assert "COMPUTE_WH" in ci_wh, (
        "the env_var() must default to COMPUTE_WH so the change is a no-op until the warehouse "
        "exists (no red-CI window)."
    )


def test_only_the_ci_target_is_env_driven():
    """BLAST-RADIUS. A stray SNOWFLAKE_CI_WAREHOUSE must never be able to steer the production
    daily build or the dev target onto another warehouse."""
    outputs = yaml.safe_load(DBT_PROFILES.read_text())["baseball_betting_and_fantasy"]["outputs"]
    checked = 0
    for name, cfg in outputs.items():
        if name == "ci" or "warehouse" not in cfg:
            continue
        checked += 1
        assert "env_var" not in str(cfg["warehouse"]), (
            f"target {name!r} must keep a hardcoded warehouse; only `ci` is env-driven."
        )
    assert checked >= 2, "expected at least the default and `dev` targets to check — guard is vacuous."


def test_the_ci_job_supplies_that_env_var_and_never_empty():
    """THE SUPPLY END, plus the unset-vs-empty trap: an unset GitHub secret interpolates to an
    EMPTY STRING, and dbt's env_var() returns its default only for an UNSET var — an empty one
    is passed through verbatim as `warehouse: ""`. So the workflow needs its own `||` fallback.
    (Same class as the delta-rs empty-AKID landmine.)"""
    src = DBT_CI_WORKFLOW.read_text()
    # Strip BOTH comment forms — prose naming the var must not satisfy this (INC-38). The
    # trailing form is the one that bites: a whole-line strip alone left a trailing
    # `# use SNOWFLAKE_CI_WAREHOUSE` passing, measured in this guard's own RED-proof.
    code = "\n".join(
        ln.split(" #", 1)[0] for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assignments = re.findall(rf"^\s*{_CI_WH_ENV}:\s*(.+)$", code, re.MULTILINE)
    assert assignments, (
        f"the dbt-build-ci job must export {_CI_WH_ENV} — without it the profiles.yml env_var() "
        "falls back to COMPUTE_WH and the repoint silently never happens."
    )
    for value in assignments:
        assert "||" in value, (
            f"{_CI_WH_ENV} must carry a `||` fallback so it is never the empty string. Found: {value!r}"
        )
        assert "MONITOR_WH" not in value, (
            "⛔ CI must NOT share MONITOR_WH — that is the wake census's own read path, so CI "
            "would become a line in the instrument that measures CI (target 3's defect)."
        )


# ── E11.24 (2026-08-14) — the workflow_dispatch verification door ────────────────────────
#
# 🪤 THE DEFECT THIS BLOCK EXISTS TO PREVENT. `dbt-build-ci` is the ONLY job that passes
# `--target ci`, i.e. the only place the CI_WH repoint applies. A `workflow_dispatch` trigger was
# added so the repoint could be PROVEN under real load (measured 2026-08-14: CI_WH had carried 12
# statements ever, ALL `warehouse_size IS NULL` — cloud-services only — because the run that was
# recorded as proof selected zero models; a build that builds nothing puts zero statements on
# COMPUTE_WH whether or not the repoint works). The hazard the door introduces is that a future
# dbt invocation reachable from it could run on the DEFAULT (production) profile and quietly bill
# COMPUTE_WH again — the exact thing the repoint removed.


def _dbt_ci_jobs() -> dict:
    return yaml.safe_load(DBT_CI_WORKFLOW.read_text())["jobs"]


def _run_bodies(job: dict) -> list[str]:
    return [str(s.get("run", "")) for s in (job.get("steps") or []) if isinstance(s, dict) and s.get("run")]


def test_no_dbt_invocation_reachable_from_dispatch_runs_off_the_ci_target():
    """THE BLAST RADIUS OF THE NEW DOOR. A job is admissible either because it explicitly
    excludes workflow_dispatch, or because every `dbtf` call it makes carries `--target ci`.
    Anything else can reach Snowflake on the production profile from a manual button.

    Walks the jobs rather than naming them, so a job added later inherits the requirement.
    """
    offenders, dbt_jobs = [], 0
    for name, job in _dbt_ci_jobs().items():
        bodies = [b for b in _run_bodies(job) if "dbtf " in b]
        if not bodies:
            continue
        dbt_jobs += 1
        if "!= 'workflow_dispatch'" in str(job.get("if", "")):
            continue  # cannot be reached from the dispatch door at all
        for body in bodies:
            # Join shell line-continuations FIRST — every dbtf call here is written multi-line,
            # so matching per physical line would see `dbtf build \` alone and report every
            # correctly-targeted call as an offender (measured while writing this guard).
            flat = re.sub(r"\\\n\s*", " ", body)
            for call in re.findall(r"dbtf\s+(?:build|run|test|compile|run-operation)[^\n]*", flat):
                # EXACTLY ONE --target, and it must be `ci`. A mere `"--target ci" in call`
                # substring test is satisfiable by `--target ci --target dev`, where dbt takes
                # the LAST one — i.e. the obvious form of this guard cannot detect an override.
                # (Found by RED-proving this guard: that break flipped nothing.)
                targets = re.findall(r"--target\s+(\S+)", call)
                if targets != ["ci"]:
                    offenders.append((name, f"targets={targets} :: " + " ".join(call.split())[:60]))

    assert dbt_jobs >= 2, f"expected both dbt jobs to be walked, saw {dbt_jobs} — guard is vacuous."
    assert not offenders, (
        "these dbt invocations are reachable from workflow_dispatch without `--target ci`, so a "
        f"manual run would bill the PRODUCTION warehouse: {offenders}"
    )


def test_the_compile_job_cannot_run_on_dispatch_so_the_proof_window_is_unambiguous():
    """`dbt-compile` runs with NO `--target`, i.e. on the production profile. Excluding it from
    workflow_dispatch is what makes the query_history assertion DISCRIMINATING: in a dispatch
    window, ANY DBT_RW statement on COMPUTE_WH means the repoint did not hold. Without this, a
    COMPUTE_WH statement would be ambiguous between "the repoint failed" and "that was compile."
    """
    compile_if = str(_dbt_ci_jobs()["dbt-compile"].get("if", ""))
    assert "workflow_dispatch" in compile_if and "!=" in compile_if, (
        "dbt-compile must be excluded from workflow_dispatch (it runs on the production profile), "
        f"or a verification dispatch cannot produce a clean COMPUTE_WH-free window. Found: {compile_if!r}"
    )


def test_the_dispatch_input_is_never_interpolated_into_a_shell_body():
    """A `${{ inputs.* }}` expanded inside a `run:` body is a shell-injection sink — GitHub
    substitutes the raw text before bash ever sees it. It must arrive via `env:` and be read as
    "$VAR". (Dispatch requires write access, so this is defence in depth, not the last line.)"""
    bodies, checked = [], 0
    for name, job in _dbt_ci_jobs().items():
        for body in _run_bodies(job):
            checked += 1
            if "${{ inputs." in body or "${{inputs." in body:
                bodies.append(name)
    assert checked >= 5, f"only {checked} run-bodies walked — guard is vacuous."
    assert not bodies, (
        f"job(s) {bodies} interpolate a workflow_dispatch input directly into a shell body; pass "
        "it through `env:` and quote it instead."
    )


# ── E11.24 target 4 (2026-08-17) — the clause-2 predicate must not be vacuous ─────────────
#
# `scripts/verify_ci_warehouse_repoint.py` decides "is the dbt-CI repoint onto CI_WH proven?" on
# two clauses. Clause (2) — "no CI statement ran on COMPUTE_WH" — was keyed on
# `schema_name = 'CI_BETTING'`. MEASURED 2026-08-17 over ALL of CI_WH's history: that test catches
# **14 of 64** billable CI statements. `schema_name` is the SESSION schema, and dbt-fusion issues
# its TEST queries with none set, so they land `NULL` while naming `baseball_data.ci_betting…` in
# the SQL text.
#
# That is a FALSE PASS on the commonest run shape, not an under-count. A `state:modified+` PR that
# touches a VIEW model materializes nothing billable (a CREATE VIEW is cloud-services-only), so
# EVERY billable statement in that run is a NULL-schema dbt test — exactly the 2026-08-16
# 04:53/04:58 PR runs. Under the failure clause (2) exists to catch (an EMPTY
# SNOWFLAKE_CI_WAREHOUSE → the `warehouse` key vanishes → fallback to DBT_RW's default =
# COMPUTE_WH) that whole run leaks and the old clause reported ✅.
#
# These guards run the REAL predicate string from the script against DuckDB, over statement shapes
# copied from measured `query_history` rows — not a Python restatement of it, which could only ever
# agree with itself (the NF-C0e wrong-key class).

_CI_WH_VERIFIER = Path(__file__).resolve().parents[2] / "scripts" / "verify_ci_warehouse_repoint.py"


def _verifier_module():
    """Load the verifier by path. Its Snowflake/dotenv imports live inside main(), so importing
    the module opens no connection and touches no network."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_ci_wh_verifier", _CI_WH_VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (shape, schema_name, query_text, must_be_flagged_as_CI)
# Every row is a real shape observed in `snowflake.account_usage.query_history` on 2026-08-17.
_STATEMENT_SHAPES = [
    (
        "dbt test, NULL session schema — 50 of 64 billable CI statements look like this",
        None,
        "select count(*) as failures, count(*) != 0 as should_warn from ( select side from "
        "baseball_data.ci_betting_features.feature_pregame_team_features where side is null ) "
        "dbt_internal_test /* job=dbt_manual model=not_null_feature_pregame_team_features_side */",
        True,
    ),
    (
        "the ref_teams seed INSERT — the occupying write the proof dispatch exists to issue",
        "CI_BETTING",
        "insert overwrite into baseball_data.ci_betting.ref_teams (TEAM_ID, TEAM_ABBREV) values (1,'ARI')",
        True,
    ),
    (
        "box pipeline EB merge — must never be mistaken for CI (it runs 19 of 24 hours)",
        "BETTING",
        "merge into baseball_data.betting.eb_batter_posteriors_raw as t using (select 1) as s on t.id = s.id",
        False,
    ),
    (
        "THIS VERIFIER'S OWN monitoring read — a bare %ci_betting% would make it self-disqualifying",
        None,
        "select iff(schema_name = 'CI_BETTING', 'CI — DISQUALIFYING', 'box') as who, count(*) "
        "from snowflake.account_usage.query_history where warehouse_name = 'COMPUTE_WH'",
        False,
    ),
]


def _classify_with_the_real_predicate():
    """Evaluate the script's own `_IS_CI_STATEMENT` SQL over the fixtures, in DuckDB.

    ⚠️ Wrapped in `iff(...)` exactly as the script wraps it, NOT read as a bare boolean. SQL is
    three-valued: a NULL `schema_name` that fails the text match yields `NULL OR FALSE = NULL`,
    not FALSE. The script routes that through `iff(pred, 'CI…', 'box…')`, where NULL takes the
    else-branch and is correctly classified as non-CI — so testing the bare predicate would
    measure something the script never evaluates.
    """
    import duckdb

    predicate = _verifier_module()._IS_CI_STATEMENT
    con = duckdb.connect()
    try:
        con.execute("create table qh (shape varchar, schema_name varchar, query_text varchar)")
        con.executemany(
            "insert into qh values (?, ?, ?)",
            [(s, sch, txt) for s, sch, txt, _ in _STATEMENT_SHAPES],
        )
        # `CASE WHEN` rather than Snowflake's `IFF` (DuckDB has no `iff`) — the two are identical
        # on the point that matters here: a NULL condition takes the ELSE branch in both.
        rows = con.execute(
            f"select shape, case when {predicate} then true else false end from qh"
        ).fetchall()
    finally:
        con.close()
    return dict(rows)


def test_clause_two_flags_a_null_schema_dbt_test():
    """RED-proves the QUALIFIED-TEXT half. Delete it from `_IS_CI_STATEMENT` and this fixture — a
    NULL-schema dbt test, the shape 78% of billable CI statements take — escapes clause (2), which
    is the false-PROVEN bug this change fixes. The other fixtures cannot trip this assertion."""
    verdicts = _classify_with_the_real_predicate()
    shape = _STATEMENT_SHAPES[0][0]
    assert verdicts[shape] is True, (
        "clause (2) does not flag a NULL-session-schema dbt test naming a ci_betting relation. "
        "A schema_name-only test misses 50 of 64 billable CI statements and reports PROVEN on a "
        "fully leaked view+tests run."
    )


def test_clause_two_does_not_self_match_the_verifiers_own_monitoring_sql():
    """RED-proves the QUALIFICATION. Relax the text match to a bare `%ci_betting%` and this
    fixture — the verifier's own query_history read, which contains the literal `'CI_BETTING'` —
    becomes its own disqualifying evidence, so the check can never return PROVEN. Only the
    `baseball_data.` qualifier separates the two; no other fixture exercises it."""
    verdicts = _classify_with_the_real_predicate()
    shape = _STATEMENT_SHAPES[3][0]
    assert verdicts[shape] is False, (
        "clause (2) flags the verifier's own monitoring SQL as a CI statement — the text match "
        "must be FULLY QUALIFIED (`baseball_data.ci_betting`), never a bare `ci_betting`."
    )


def test_clause_two_does_not_fire_on_the_box_pipeline():
    """The false-fire floor. The box puts DBT_RW on COMPUTE_WH in 19 of 24 hours; if ordinary
    pipeline traffic disqualified, the verdict would be NOT PROVEN in almost any window and the
    check would be as useless as one that always passes."""
    verdicts = _classify_with_the_real_predicate()
    shape = _STATEMENT_SHAPES[2][0]
    assert verdicts[shape] is False, (
        "clause (2) flags a box-pipeline statement as CI — the predicate is over-broad and would "
        "report NOT PROVEN on a healthy repoint."
    )


def test_the_fixture_set_is_two_sided_so_the_guards_above_are_not_vacuous():
    """A classifier fixture set that is all-True (or all-False) proves nothing — it is satisfied by
    a predicate hardcoded to that constant. Assert both verdicts are actually represented."""
    verdicts = _classify_with_the_real_predicate()
    assert len(verdicts) == len(_STATEMENT_SHAPES) >= 4, "fixtures were dropped — guards are vacuous."
    assert any(verdicts.values()), "no fixture is classified as CI — the guards pass on nothing."
    assert not all(verdicts.values()), "every fixture is classified as CI — a constant-True predicate passes."


def test_the_sql_builder_survives_a_like_pattern():
    """RED-proves the `_rows` substitution fix. The queries were interpolated with
    `sql % {"mins": mins}`, under which the `%` in `LIKE '%baseball_data.ci_betting%'` is a format
    specifier — so the moment clause (2) grew a LIKE, every query raised
    `ValueError: unsupported format character 'b'` at runtime. CI cannot catch that (it mocks IO),
    so it is asserted here against a fake cursor."""
    mod = _verifier_module()

    class _FakeCursor:
        def __init__(self):
            self.sql = None

        def execute(self, sql):
            self.sql = sql

        def fetchall(self):
            return []

    # Deliberately a LITERAL LIKE, not `_IS_CI_STATEMENT`. This guard defends `_rows`' contract
    # ("any LIKE pattern reaches Snowflake intact"), and coupling it to the predicate's current
    # text would make it fail for changes it does not defend — the NF-D17 isolation rule. The
    # predicate's own content is pinned by the three clause-2 guards above.
    cur = _FakeCursor()
    sql = "select 1 from t where ts >= dateadd(minute, -%(mins)s, current_timestamp()) " \
          "and lower(query_text) like '%baseball_data.ci_betting%'"
    mod._rows(cur, sql, 90)

    assert "-90," in cur.sql, f"the minutes placeholder was not substituted: {cur.sql!r}"
    assert "%(mins)s" not in cur.sql, "the placeholder survived substitution."
    assert "'%baseball_data.ci_betting%'" in cur.sql, (
        "the LIKE pattern was mangled or escaped away — Snowflake must receive a single-`%` "
        f"wildcard on each side. Got: {cur.sql!r}"
    )
