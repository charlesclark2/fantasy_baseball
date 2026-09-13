"""NCAAF-P1.2W — the weekly P1.2 strength re-fit: the discriminator, the sequencing, the SLA.

WHAT THIS FILE DEFENDS. The served NCAAF ratings were the pre-season prior for three played weeks
because P1.2 is a once-per-season refit nothing scheduled. Scheduling it is easy; the hard part —
and every clause below — is that `run_team_strength` against STALE MARTS reproduces the cold start,
writes a full set of Delta commits, exits 0 and looks exactly like success. It did that on
2026-08-17. A job that merely RAN is the failure mode; a job that proves it WORKED is the story.

⭐⭐ THE MEASUREMENT THAT SHAPED THESE CLAUSES, taken on the live served table 2026-09-13:

    season 2026: 138 teams, as_of_week ∈ {1}, newest Delta commit 2026-08-18T06:16:36Z (v67)
    covariate_component_roster_flux non-zero on 136   ← the cold-start check PASSES
    covariate_component_coaching    non-zero on 136   ← the cold-start check PASSES
    covariate_component_talent      non-zero on 0     ← CFBD has not published 2026 talent at all

i.e. THE COVARIATE DISCRIMINATOR ALONE IS SATISFIED BY THE FROZEN ARTIFACT THIS STORY EXISTS TO
UNFREEZE. That is why `classify_refit` reads three things and why the clauses below test each of
them separately: a verification suite that only reproduced the NCAAF-PS report's SQL would have
certified doing nothing.

RED-proven by `betting_ml/tests/ncaaf_p1_2w_red_proof.py` (unique-anchor / baseline-pass /
NOT-SELECTED / resolve-every-node controls).
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from betting_ml.monitoring import ncaaf_strength_refit as REFIT
from betting_ml.monitoring import sports_delta_freshness as SDF

REPO = Path(__file__).resolve().parents[2]
JOB = REPO / "pipeline/jobs/sports_ncaaf_strength_refit_job.py"
SCHEDULE = REPO / "pipeline/schedules/sports_ncaaf_strength_refit_schedules.py"
SNAPSHOT_JOB = REPO / "pipeline/jobs/sports_ncaaf_prediction_snapshot_job.py"
BOX_OPS = REPO / "services/dagster/aws/BOX_OPERATIONS.md"

UTC = timezone.utc
NOW = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)


def _code_only(source: str) -> str:
    """Source with comment lines AND docstrings removed.

    INC-38 — a source-inspection clause that matches anywhere in the file is satisfied by the
    EXPLANATORY PROSE written above the thing it checks, and both halves of that bit here while
    these clauses were being written: the refit module's docstring says "never an S3
    LastModified", which satisfied a ban on that token, and the freshness op's says "never
    raises", which satisfied a ban on `raise`. A guard whose subject is the CODE must read only
    the code.
    """
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        first = node.body[0] if node.body else None
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            doc_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return "\n".join(
        "" if (i in doc_lines or line.lstrip().startswith("#")) else line
        for i, line in enumerate(source.splitlines(), start=1))


def _state(version, *, week=None, flux=136, coaching=136, teams=138, commit=NOW, error=None):
    return REFIT.RefitState(
        season=2026, version=version, commit=commit, teams=teams,
        covariate_nonzero={"roster_flux": flux, "coaching": coaching},
        max_as_of_week=week, error=error)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. The discriminator — three readings, each isolated so only its own defect can flip it
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_a_real_refit_is_the_only_thing_that_passes():
    """BASELINE-PASS. Everything below asserts a REFUSAL; without this clause they are all
    satisfiable by a classifier that refuses unconditionally."""
    verdict = REFIT.classify_refit(_state(67, week=1), _state(68, week=3), completed_games=1_402)
    assert verdict["verdict"] == "REFIT_LANDED"
    assert verdict["severity"] is None
    assert REFIT.is_problem(verdict) is False


def test_the_covariate_check_alone_would_certify_the_frozen_artifact():
    """⭐ THE CLAUSE THIS WHOLE FILE EXISTS FOR — the measured non-vacuity of readings 2 and 3.

    The NCAAF-PS report's operator SQL ("0/0/138 is a cold start; 136/136/138 is a real re-fit") is
    the obvious verification to schedule, and on its own it CERTIFIES THE BUG. Fed the live served
    state of 2026-09-13 — 136 / 136 / 138, as_of_week 1, and a vintage that did not move — the
    covariate reading is clean and the run must still FAIL. Anyone who later simplifies
    `classify_refit` down to the covariate check will be arguing with this fixture.
    """
    frozen = _state(67, week=1, flux=136, coaching=136)   # the live 2026-09-13 reading, verbatim
    verdict = REFIT.classify_refit(frozen, frozen, completed_games=1_402)

    assert verdict["metrics"]["covariate_nonzero_roster_flux"] == 136
    assert verdict["metrics"]["covariate_nonzero_coaching"] == 136
    assert verdict["verdict"] == "VINTAGE_DID_NOT_ADVANCE", (
        "the covariate counts are healthy on this fixture ON PURPOSE — it is the artifact that had "
        "been frozen since 2026-08-18. If this now reports a cold start, the fixture has drifted; "
        "if it reports REFIT_LANDED, the verification certifies doing nothing.")
    assert verdict["severity"] == "CRITICAL"


def test_a_cold_start_reproduction_fails_the_run_rather_than_passing_it():
    """Reading 2, isolated: the vintage DID advance and the week index DID move, so only the
    covariate collapse can flip this — the 2026-08-17 incident's own fingerprint."""
    verdict = REFIT.classify_refit(_state(67, week=1), _state(68, week=3, flux=0, coaching=0),
                                   completed_games=1_402)
    assert verdict["verdict"] == "COLD_START"
    assert verdict["severity"] == "CRITICAL"
    assert "marts" in verdict["detail"].lower(), (
        "a cold-start page must name the MARTS as the cause — that is the whole remedy, and an "
        "operator reading 'covariates are zero' has no first action without it")


@pytest.mark.parametrize("flux,coaching", [(0, 136), (136, 0)])
def test_either_discriminating_covariate_alone_is_enough_to_refuse(flux, coaching):
    """Both members of `DISCRIMINATING_COVARIATES` are load-bearing: dropping either from the
    tuple must not be survivable by a run in which only that one collapsed."""
    verdict = REFIT.classify_refit(_state(67, week=1), _state(68, week=3, flux=flux,
                                                              coaching=coaching),
                                   completed_games=1_402)
    assert verdict["verdict"] == "COLD_START"


def test_the_week_index_check_refuses_a_prior_that_absorbed_no_played_week():
    """Reading 3, isolated: covariates healthy, vintage advanced — only the frozen week index can
    flip this. It is the reading that would have caught THIS story's actual gap."""
    verdict = REFIT.classify_refit(_state(67, week=1), _state(68, week=1), completed_games=1_402)
    assert verdict["verdict"] == "WEEK_DID_NOT_ADVANCE"
    assert "1402" in verdict["detail"].replace(",", ""), (
        "the page must state HOW MANY completed rows the check acted on — an activity count is "
        "what separates 'the fit ignored three weeks of football' from 'there was nothing to "
        "absorb' (NF-D20)")


def test_the_week_index_check_declares_itself_inactive_pre_season_rather_than_passing():
    """NF1.7(a)/NF-D20 — before a snap is played `as_of_week = 1` is the ONLY correct answer, so
    reading 3 cannot act. It must say so: an inactive check reported as a pass is how a guard comes
    to look like coverage it never had."""
    verdict = REFIT.classify_refit(_state(67, week=1), _state(68, week=1), completed_games=0)
    assert verdict["verdict"] == "REFIT_LANDED"
    assert "INACTIVE" in verdict["detail"], (
        "a pre-season run must record that the week-index reading could not have failed, not "
        "merely that the run was green")
    assert verdict["metrics"]["completed_games"] == 0


def test_an_unreadable_completed_game_count_is_unevaluable_not_a_free_pass():
    """`read_completed_games` returns None (never 0) when the marts cannot be read, because 0
    would silently DISABLE reading 3 on exactly the runs where something is already wrong."""
    verdict = REFIT.classify_refit(_state(67, week=1), _state(68, week=1), completed_games=None)
    assert verdict["verdict"] == "REFIT_LANDED"
    assert "UNEVALUABLE" in verdict["detail"].upper()
    src = _code_only((REPO / "betting_ml/monitoring/ncaaf_strength_refit.py").read_text())
    body = src.split("def read_completed_games")[1].split("\ndef ")[0]
    assert "return None" in body and "return 0" not in body, (
        "an unreadable marts count must be None, never 0 — 0 reads as 'no completed games', which "
        "turns the week-index check off silently")


def test_an_unreadable_artifact_after_the_fit_fails_rather_than_passing():
    verdict = REFIT.classify_refit(_state(67, week=1),
                                   REFIT.RefitState(season=2026, error="IOException: no log"),
                                   completed_games=1_402)
    assert verdict["verdict"] == "UNREADABLE"
    assert verdict["severity"] == "CRITICAL"


def test_the_vintage_advance_is_decided_on_the_delta_version_not_a_clock():
    """Two commits can share a millisecond and a clock is not a sequence, so VERSION is the
    authority. A version that went BACKWARDS (a rollback, a different table) must refuse even
    though its timestamp is newer."""
    before = _state(68, week=3, commit=NOW - timedelta(hours=1))
    after = _state(67, week=3, commit=NOW)          # newer clock, OLDER version
    assert REFIT.classify_refit(before, after, completed_games=1_402)["verdict"] == \
        "VINTAGE_DID_NOT_ADVANCE"


def test_the_vintage_is_read_from_the_delta_log_and_never_from_an_mtime():
    """INC-41 — an object mtime is refreshed by a server-side rewrite that changes no data, and
    `aws s3 ls` prints SHELL-LOCAL time. Either would report the frozen artifact as fresh."""
    src = _code_only((REPO / "betting_ml/monitoring/ncaaf_strength_refit.py").read_text())
    for banned in ("LastModified", "getmtime", "st_mtime", "s3 ls"):
        assert banned not in src, f"the vintage read reached for {banned!r} — INC-41 forbids it"
    assert "sports_delta_freshness" in src, (
        "the commit read forked away from the shared owner; delta-rs has shipped the commit "
        "timestamp as both epoch-ms and a datetime, and two parsers is how they drift")


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. The job — the marts rebuild is INSIDE it, the verify step RAISES, and nothing is assumed
# ══════════════════════════════════════════════════════════════════════════════════════════

def _job_graph():
    """The COMPILED Dagster dependency edges — not source order.

    INC-40: `in_process_executor` runs steps topologically, so a test that reads the order op calls
    appear in the source is VACUOUS; the edges are the only thing that pins execution order.
    """
    pipeline = pytest.importorskip("pipeline")
    job = pipeline.defs.get_job_def("sports_ncaaf_strength_refit_job")
    edges = {}
    for node_name, deps in job.graph.dependencies.items():
        edges[node_name.name] = {d.node for d in deps.values()}
    return job, edges


@pytest.mark.slow
def test_the_marts_rebuild_runs_before_the_fit_inside_this_job():
    """⭐ THE STRUCTURAL HALF OF THE DISCRIMINATOR. `sports_ncaaf_dbt_schedule` does rebuild these
    marts most in-season mornings, and relying on that is the INC-25 shape — a consumer whose
    ordering lives in two crons is one slow upstream away from reading last cycle's inputs, and
    here that failure SUCCEEDS and stamps a fresh date on a stale fit."""
    _, edges = _job_graph()
    assert "ncaaf_strength_marts_rebuild_op" in edges["ncaaf_strength_fit_op"], (
        "the fit is no longer downstream of the marts rebuild — it would fit whatever vintage the "
        "marts happen to hold")
    assert "ncaaf_strength_precondition_op" in edges["ncaaf_strength_marts_rebuild_op"]
    assert "ncaaf_strength_fit_op" in edges["ncaaf_strength_verify_op"], (
        "the verification is no longer downstream of the fit — it would read the artifact before "
        "the fit wrote it and certify the previous run")


@pytest.mark.slow
def test_every_node_in_the_job_resolves_and_the_serving_write_is_last():
    """RESOLVE-EVERY-NODE. A job that compiles is not a job whose every op exists; and the serving
    publish must be downstream of the VERIFY, never of the fit — publishing a cold start to the
    product would be strictly worse than not publishing."""
    job, edges = _job_graph()
    names = {n.name for n in job.graph.node_defs}
    assert names == {
        "ncaaf_strength_precondition_op", "ncaaf_strength_marts_rebuild_op",
        "ncaaf_strength_fit_op", "ncaaf_strength_verify_op",
        "ncaaf_serving_write_after_snapshot_op",
    }, f"the job's op set changed: {sorted(names)}"
    assert edges["ncaaf_serving_write_after_snapshot_op"] == {"ncaaf_strength_verify_op"}


def test_the_verify_step_raises_rather_than_logging_a_warning():
    """A cold-start reproduction must be a PAGED FAILURE. An op that pages and returns leaves a
    GREEN run in Dagit, which is the NF-FRESH1 signal an operator reads as health."""
    src = _code_only(JOB.read_text())
    body = src.split("def ncaaf_strength_verify_op")[1].split("\ndef ")[0]
    assert "raise Exception(" in body, "the verify op no longer fails the run"
    assert "_page(" in body, "the verify op no longer pages"
    assert "is_problem(" in body, (
        "the verify op stopped asking the policy module for the verdict and is deciding for "
        "itself — a second owner of the discriminator")


def test_the_fit_invokes_the_shipped_p1_2_cli_rather_than_reimplementing_it():
    """⛔ THE FIT IS UNTOUCHED, and this is what keeps it that way. A second in-process caller that
    assembled the same fit would be free to drift from the model every P1.x calibration verdict was
    recorded against (the E9.61 two-renderers class)."""
    src = _code_only(JOB.read_text())
    assert "quant_sports_intel_models.football.ncaaf.models.run_team_strength" in src
    assert re.search(r'"--s3"', src), "the fit no longer lands the posterior in the lake"
    for banned in ("run_strength(", "StrengthConfig(", "load_marts("):
        assert banned not in src, (
            f"the job reached into P1.2's internals ({banned}) instead of invoking its CLI — that "
            f"is a second implementation of a model this story is forbidden to touch")


def test_the_fit_subprocess_is_bounded_and_kills_its_process_group():
    """INC-32 / E11.26 — an un-timed-out subprocess on a Dagster worker wedges it, and
    `subprocess.run`'s own timeout kills only the DIRECT child, leaving a grandchild holding one of
    the box's two vCPUs."""
    src = _code_only(JOB.read_text())
    assert "run_bounded(" in src and "timeout=REFIT_TIMEOUT_SECONDS" in src
    assert "subprocess.run(" not in src, (
        "the fit went back to subprocess.run — it kills the direct child only")


def test_the_job_resolves_the_duckdb_path_through_the_one_owner():
    """NF-INFRA1 — four owners each supplying their own default is how the NFL build wrote one file
    while the gate read another. A literal here would re-create the divergence."""
    src = _code_only(JOB.read_text())
    assert "sports_duckdb_env()" in src and "resolve_sports_duckdb()" in src
    assert "_run_sports_dbt(" in src, (
        "the marts rebuild stopped going through the shared dbt helper, which is what pins "
        "SPORTS_DUCKDB_PATH to the resolved absolute path")
    for literal in ("/tmp/sports_ncaaf.duckdb", "sports_dbt/sports.duckdb"):
        assert literal not in src, f"a hardcoded DuckDB path ({literal}) reappeared in the job"


@pytest.mark.slow
def test_the_job_carries_a_runtime_ceiling_above_its_own_legs_and_below_its_cadence():
    """E11.26 — `leg_cap < job_ceiling < cadence`, pinned so the three cannot drift apart. A
    default copied from a daily batch job IS 'no timeout' on a recurring tick."""
    job, _ = _job_graph()
    ceiling = int(job.tags["dagster/max_runtime"])
    # ⚠️ `import pipeline.jobs.X as J` binds the JOB, not the module: `pipeline/jobs/__init__.py`
    # re-exports a job whose name is identical to its module's, which overwrites the submodule
    # attribute. importlib asks for the module by name and cannot be shadowed.
    from importlib import import_module

    from pipeline.jobs.sports_dbt_job import DBT_TIMEOUT_SECONDS
    from pipeline.jobs.sports_ncaaf_serving_write_job import SERVING_WRITE_TIMEOUT_S

    module = import_module("pipeline.jobs.sports_ncaaf_strength_refit_job")
    legs = DBT_TIMEOUT_SECONDS * 2 + module.REFIT_TIMEOUT_SECONDS + SERVING_WRITE_TIMEOUT_S
    assert legs < ceiling, (
        f"the job's legs can consume {legs}s against a {ceiling}s ceiling — the ceiling is not a "
        f"ceiling")
    assert ceiling < 7 * 24 * 3600, "the ceiling exceeds the weekly cadence, so runs could stack"
    assert job.tags["concurrency_group"] == "ncaaf_strength_refit", (
        "the concurrency group is gone — a slow week would run two fits against two vCPUs and one "
        "DuckDB file (A2.16)")


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. Sequencing — the cron offset is a courtesy; the precondition is the guarantee
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_job_refuses_to_fit_on_stale_raw_rather_than_trusting_the_cron_offset():
    """INC-25 — an ordering that lives only in two crons is one slow ingest away from a consumer
    reading last cycle's inputs. Here the failure would SUCCEED: a re-fit over stale raw writes,
    exits 0, and stamps today's date on the served 'ratings as of' line."""
    src = _code_only(JOB.read_text())
    body = src.split("def ncaaf_strength_precondition_op")[1].split("\ndef ")[0]
    assert "RAW_MAX_LAG_HOURS" in body, "the raw-freshness bound is gone from the precondition"
    assert '"games"' in body, "the precondition stopped reading the raw games feed"

    # ⚠️ SCOPED TO THE STALE-RAW BRANCH, and that scoping is the whole clause. This op carries TWO
    # refusals — the missing-DuckDB one above it and this one — so a bare `"raise Exception(" in
    # body` stays TRUE with the stale-raw refusal deleted, which is exactly what it did when first
    # written (NF-D17: an `and`-composed clause satisfied by a different clause's subject). Read
    # the branch, not the function.
    branch = body.split("if SDF.is_problem(raw_verdict):")
    assert len(branch) == 2, (
        "the stale-raw branch was renamed or removed — re-anchor this clause on whatever now "
        "decides that the raw feed is too old")
    branch = branch[1]
    assert "raise Exception(" in branch, (
        "the stale-raw branch no longer refuses — the job would fit on whatever the roll-forward "
        "last managed to land, succeed, and stamp a fresh date on the served 'ratings as of' line")
    assert "_page(" in branch, "the stale-raw refusal stopped paging"


@pytest.mark.slow
def test_the_refit_fires_after_the_roll_forward_and_not_at_its_instant():
    """They share the box's two vCPUs and the roll-forward rebuilds the same marts; a shared
    instant is a race even where the precondition would still pass."""
    pipeline = pytest.importorskip("pipeline")
    import pipeline.schedules.sports_rollforward_schedules as RF

    refit = pipeline.defs.get_schedule_def("sports_ncaaf_strength_refit_schedule")
    assert refit.execution_timezone == "America/Los_Angeles"
    refit_m, refit_h = refit.cron_schedule.split()[:2]
    roll_m, roll_h = RF.NCAAF_ROLL_FORWARD_CRON.split()[:2]
    assert (int(refit_h), int(refit_m)) > (int(roll_h), int(roll_m)), (
        f"the re-fit ({refit.cron_schedule}) no longer fires after the roll-forward "
        f"({RF.NCAAF_ROLL_FORWARD_CRON}) — it would fit before its own inputs land")
    assert int(refit_h) * 60 + int(refit_m) - (int(roll_h) * 60 + int(roll_m)) >= 60, (
        "less than an hour of headroom over a job whose own mart rebuild takes ~90s")


@pytest.mark.slow
def test_the_refit_fires_on_a_monday_inside_the_declared_season():
    pipeline = pytest.importorskip("pipeline")
    from dagster._utils.schedules import cron_string_iterator

    refit = pipeline.defs.get_schedule_def("sports_ncaaf_strength_refit_schedule")
    fires = []
    cursor = datetime(2026, 8, 1, tzinfo=UTC).timestamp()
    it = cron_string_iterator(cursor, refit.cron_schedule, "America/Los_Angeles")
    for _ in range(30):
        fires.append(next(it))
    assert {f.weekday() for f in fires} == {0}, "the re-fit is no longer a Monday job"
    assert {f.month for f in fires} <= set(REFIT.SEASON_MONTHS), (
        "the cron fires outside the declared season window, so the freshness SLA's active months "
        "and the cadence they describe have drifted apart")


def test_the_schedule_reads_the_shared_enable_predicate_rather_than_declaring_its_own():
    """One owner. A second `os.environ.get(...) == "1"` beside the schedule would be a second rule
    for the same fact — and it would put the predicate back where the fast gate cannot reach it."""
    src = _code_only(SCHEDULE.read_text())
    assert "refit_enabled(" in src and "from betting_ml.monitoring.ncaaf_strength_refit import" in src
    assert "os.environ" not in src, (
        "the schedule reads the env directly again — the predicate has one owner in betting_ml, "
        "which is also the only place the fast gate can import it from (E11.23)")


def test_the_cron_month_field_is_built_from_the_season_window_not_retyped():
    """One logical thing, one owner (INC-30/36/38). A month range typed beside the SLA's own month
    tuple is the seasonal-hole class waiting for one of the two to be edited."""
    src = _code_only(SCHEDULE.read_text())
    assert "SEASON_MONTHS" in src, "the cron re-typed its month list"
    assert not re.search(r'NCAAF_STRENGTH_REFIT_CRON\s*=\s*"[^"]*8-12', src), (
        "the month field was hardcoded back into the cron string")


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. Monitoring — an active-SEASON SLA, and a monitor that is not hosted inside its subject
# ══════════════════════════════════════════════════════════════════════════════════════════

def _reading(hours_ago: float, *, now: datetime, version: int = 67):
    return SDF.DeltaReading(name="ncaaf_team_strength_week", version=version,
                            last_commit=now - timedelta(hours=hours_ago))


def test_the_ratings_have_a_freshness_contract_sized_to_the_weekly_cadence():
    contract = SDF.by_name("ncaaf_team_strength_week")
    assert (contract.sport, contract.source, contract.tier) == ("ncaaf", "team_strength_week",
                                                                "derived")
    assert 168 <= contract.max_lag_hours <= 336, (
        "the SLA no longer brackets a weekly cadence: below one week it pages on a healthy "
        "Monday-to-Monday gap; above two it cannot distinguish a missed week from a dead writer")


def test_a_missed_monday_is_stale_and_a_healthy_week_is_not():
    """TWO-SIDED. A floor that nothing can trip is not a floor, and one a healthy cadence trips is
    an alert-fatigue generator that ends up muted."""
    contract = SDF.by_name("ncaaf_team_strength_week")
    now = datetime(2026, 10, 12, 16, 0, tzinfo=UTC)          # mid-season, no window to confuse it
    healthy = SDF.classify(contract, _reading(168, now=now), now=now)
    assert healthy["verdict"] == "OK", f"a normal Monday-to-Monday gap paged: {healthy['detail']}"
    missed = SDF.classify(contract, _reading(24 * 12, now=now), now=now)
    assert missed["verdict"] == "STALE" and missed["severity"] == "WARN"
    dead = SDF.classify(contract, _reading(24 * 30, now=now), now=now)
    assert dead["severity"] == "CRITICAL", (
        "a writer that has been silent for a month must escalate past 'one missed cycle'")


def test_the_off_season_gap_is_idle_by_declaration_rather_than_a_breach():
    """⭐ The season-boundary behaviour, stated as a test. Between the CFP final and August there is
    nothing to re-fit, and a wall-clock SLA would page all spring — so lag accrues only inside the
    declared months. The clause is TWO-SIDED on purpose: a check that is merely suppressed
    off-season would still fire a false CRITICAL on its FIRST August read, because by then the raw
    gap spans the whole winter."""
    contract = SDF.by_name("ncaaf_team_strength_week")
    assert contract.active_months == REFIT.SEASON_MONTHS

    final_fit = datetime(2027, 1, 25, 15, 30, tzinfo=UTC)     # the season's last scheduled fire
    may = SDF.classify(contract, SDF.DeltaReading(name="x", version=67, last_commit=final_fit),
                       now=datetime(2027, 5, 20, 16, 0, tzinfo=UTC))
    assert may["verdict"] == "OK", (
        f"a January-final rating paged in May: {may['detail']} — an off-season gap is not a breach")

    first_august_read = SDF.classify(
        contract, SDF.DeltaReading(name="x", version=67, last_commit=final_fit),
        now=datetime(2027, 8, 3, 16, 0, tzinfo=UTC))
    assert first_august_read["verdict"] == "OK", (
        "the FIRST in-season read false-paged on the winter it just idled through — the check was "
        "suppressed off-season instead of counting only active minutes")

    deep_august = SDF.classify(
        contract, SDF.DeltaReading(name="x", version=67, last_commit=final_fit),
        now=datetime(2027, 8, 28, 16, 0, tzinfo=UTC))
    assert deep_august["verdict"] == "STALE", (
        "the ratings had not been re-fit four weeks into the season and nothing said so — idle by "
        "declaration must still start the clock on August 1")


def test_the_active_window_does_not_change_any_pre_existing_contract():
    """MH2.7 — changing a SHARED instrument means the guards that PIN its output are the ones to
    check. Every contract that predates this story declares no window, so its lag must stay plain
    wall-clock, byte-identical."""
    now = datetime(2026, 5, 20, 16, 0, tzinfo=UTC)            # deliberately an NCAAF off-season day
    for contract in SDF.REGISTRY:
        if contract.name == "ncaaf_team_strength_week":
            continue
        assert contract.active_months is None
        verdict = SDF.classify(contract, _reading(40, now=now), now=now)
        assert verdict["lag_hours"] == 40.0, (
            f"{contract.name}'s lag arithmetic changed: {verdict['lag_hours']}")


def test_the_active_lag_delegates_to_the_inc41_owner_rather_than_reimplementing_it():
    src = _code_only((REPO / "betting_ml/monitoring/sports_delta_freshness.py").read_text())
    assert "active_minutes_between" in src, (
        "the window arithmetic was re-implemented here instead of delegating to the INC-41 "
        "instrument that already owns it")


@pytest.mark.slow
def test_the_ratings_monitor_is_not_hosted_inside_the_job_it_watches():
    """⭐ NF-INFRA2 — the event to detect is the re-fit NOT RUNNING. A check inside the re-fit job
    only runs when that job runs, so it is structurally incapable of seeing its subject stop."""
    pipeline = pytest.importorskip("pipeline")
    refit = pipeline.defs.get_job_def("sports_ncaaf_strength_refit_job")
    assert "ncaaf_ratings_freshness_op" not in {n.name for n in refit.graph.node_defs}
    host = pipeline.defs.get_job_def("sports_ncaaf_prediction_snapshot_job")
    assert "ncaaf_ratings_freshness_op" in {n.name for n in host.graph.node_defs}
    deps = host.graph.dependencies
    for node_name, node_deps in deps.items():
        if node_name.name == "ncaaf_ratings_freshness_op":
            assert not node_deps, (
                "the ratings monitor was made downstream of the snapshot op — a snapshot outage "
                "would then blind it on exactly the days something is already wrong")


def test_the_ratings_monitor_pages_and_never_raises():
    """ALERT tier: by the time it runs it has only read S3, and failing the run would obscure a
    deadline-critical snapshot that already succeeded."""
    src = _code_only(SNAPSHOT_JOB.read_text())
    body = src.split("def ncaaf_ratings_freshness_op")[1].split("\ndef ")[0]
    assert "send_alert(" in body, (
        "the ratings SLA logs without paging — E11.30: an ALERT tier enforced only by a docstring "
        "is not enforced at all")
    assert "raise" not in body
    assert "[METRIC]" in body


def test_a_tick_fires_nothing_until_the_operator_sets_the_flag():
    """THE DEPLOY-HELD BOUNDARY, and it is a flag rather than a STOPPED default for a reason the
    next clause spells out. Merged must not mean running: the first real in-season fit moves ranks
    materially and is a supervised operator step.

    TWO-SIDED — a gate that never fires is as useless as one that never holds.

    ⚠️ Reads the predicate from `betting_ml`, NOT from the schedule module: importing anything
    under `pipeline` triggers the dbt-manifest read that is absent on a CI runner, and the fast
    gate's stated invariant is that no non-slow test imports `pipeline` (E11.23). This clause
    shipped importing the schedule and went red on the first CI run for exactly that reason, while
    passing on a laptop whose worktree carries a SYMLINK to the main checkout's manifest.
    """
    from betting_ml.monitoring.ncaaf_strength_refit import REFIT_ENABLED_FLAG, refit_enabled

    assert refit_enabled({REFIT_ENABLED_FLAG: "1"}) is True
    for absent in ({}, {REFIT_ENABLED_FLAG: ""}, {REFIT_ENABLED_FLAG: "0"},
                   {REFIT_ENABLED_FLAG: "true"}):
        assert refit_enabled(absent) is False, (
            f"{absent!r} armed the weekly re-fit — an env var that is present but empty shadows a "
            f"default, and anything but '1' must fail toward NOT firing")


@pytest.mark.slow
def test_the_skip_is_loud_and_names_the_flag_rather_than_being_silent():
    """A schedule that is RUNNING and silently produces no runs is indistinguishable from one that
    is working (NF-FRESH1's whole shape). The skip has to say what it is and what to do."""
    pipeline = pytest.importorskip("pipeline")
    from dagster import build_schedule_context

    from betting_ml.monitoring.ncaaf_strength_refit import REFIT_ENABLED_FLAG

    sched = pipeline.defs.get_schedule_def("sports_ncaaf_strength_refit_schedule")
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv(REFIT_ENABLED_FLAG, raising=False)
        result = sched.evaluate_tick(build_schedule_context(
            scheduled_execution_time=datetime(2026, 9, 14, 14, 30, tzinfo=UTC)))
    assert not result.run_requests, "the re-fit fired with the deploy-held flag unset"
    reason = result.skip_message or ""
    assert REFIT_ENABLED_FLAG in reason, "the skip does not name the flag that would arm it"
    assert "freshness" in reason, (
        "the skip does not say that the un-armed state is VISIBLE from the artifact side — which "
        "is the only thing separating this flag from the documented-but-never-set class")


@pytest.mark.slow
def test_the_schedule_self_starts_so_the_heartbeat_entry_is_not_vacuous():
    """⭐ WHY `RUNNING` RATHER THAN THE USUAL NCAAF `STOPPED` CARVE-OUT.

    `stopped_critical_instigators` flags an instigator only when Dagster holds a PERSISTED STOPPED
    row. A schedule sitting at a STOPPED DEFAULT has no row, so the revert that matters most — a
    Dagster-volume reset or a box re-host wiping the operator's toggle — leaves it silently off and
    UNFLAGGED. That is the NF-CAP1 reading, recorded there as the reason a paid-capture schedule is
    deliberately kept OUT of the set rather than listed vacuously. Here the spend objection does not
    apply (no key, no credits), so the schedule self-starts and the entry means something; the
    deploy-held boundary is the flag above.
    """
    pipeline = pytest.importorskip("pipeline")
    from dagster import DefaultScheduleStatus

    from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES

    sched = pipeline.defs.get_schedule_def("sports_ncaaf_strength_refit_schedule")
    assert sched.default_status is DefaultScheduleStatus.RUNNING, (
        "the re-fit no longer self-starts, so its CRITICAL_SCHEDULES entry cannot see a "
        "volume-reset revert and reads as coverage it does not have")
    assert "sports_ncaaf_strength_refit_schedule" in CRITICAL_SCHEDULES
    assert any(c.name == "ncaaf_team_strength_week" for c in SDF.REGISTRY), (
        "the heartbeat entry is now the ONLY coverage, and it still cannot see a lapsed enable "
        "flag — the artifact contract is the half that can")


def test_the_box_operations_table_records_the_intended_state():
    """E11.23 — an intended state that lives only in a code default is the documented-but-never-set
    class. The operator's table is the source of truth for what should be RUNNING."""
    doc = BOX_OPS.read_text()
    assert "sports_ncaaf_strength_refit_schedule" in doc, (
        "the new schedule is absent from BOX_OPERATIONS §10, so nothing tells the operator it is "
        "supposed to be ON")
