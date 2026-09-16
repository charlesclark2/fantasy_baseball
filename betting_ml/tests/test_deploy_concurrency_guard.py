"""INC-36 (2026-07-29) — guards for the concurrent-deploy race that cost a rollback + a
dagster-daemon outage.

ROOT-CAUSE CHAIN (all five links are pinned by a test below):
  1. `intraday_schedule_job` HUNG (>1h) → deploy.sh's drain loop parked for its full
     DRAIN_TIMEOUT (600s).
  2. That pushed the deploy past the CD workflow's poll budget (120 * 10s = 20 min) while
     SSM's `executionTimeout` allowed 1800s (30 min) on the box.
  3. The poll loop exited with a NON-TERMINAL status → the job failed → **the
     `orchestration-cd` concurrency group RELEASED while the SSM command was still running**.
     A concurrency group serializes GitHub JOBS, not the async SSM commands they spawn.
  4. The queued run launched a SECOND deploy.sh into a live one → two concurrent
     `docker compose up` → `removal of container ... is already in progress` → auto-rollback.
  5. The rollback did NOT verify the box came back → `dagster-daemon` was left GONE, so no
     schedule and no sensor ticked (and a dead daemon cannot page about itself).

These are source-inspection tests (the established repo pattern — cf.
test_boto3_credential_lint.py, test_lean_capture_images_selfcontained.py). They import nothing
from `pipeline`, so they stay in the fast gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEPLOY_SH = _ROOT / "services" / "dagster" / "aws" / "deploy.sh"
_CD_WORKFLOW = _ROOT / ".github" / "workflows" / "orchestration_cd.yml"


@pytest.fixture(scope="module")
def deploy_src() -> str:
    assert _DEPLOY_SH.exists(), f"missing {_DEPLOY_SH}"
    return _DEPLOY_SH.read_text()


@pytest.fixture(scope="module")
def cd_src() -> str:
    assert _CD_WORKFLOW.exists(), f"missing {_CD_WORKFLOW}"
    return _CD_WORKFLOW.read_text()


class TestTheDeployLockIsAMutexNotJustASignal:
    """Link 4: the box-side lock is the authoritative guard against two deploys."""

    def test_the_lock_checks_whether_the_owner_is_still_alive(self, deploy_src: str) -> None:
        # A bare `touch` + trap is only a SIGNAL to healthcheck.sh. Refusing to race requires
        # actually testing the recorded owner pid.
        assert "kill -0" in deploy_src, (
            "the deploy lock must test whether its owner process is ALIVE (kill -0) and refuse "
            "to race a live deploy — a bare `touch` is a healthcheck signal, NOT a mutex (INC-36)"
        )
        assert re.search(r'echo\s+"\$\$"\s*>\s*"\$DEPLOY_LOCK"', deploy_src), (
            "the deploy lock must record the owning pid so a later deploy can test liveness"
        )

    def test_it_refuses_rather_than_proceeding_when_a_deploy_is_live(self, deploy_src: str) -> None:
        block = _lock_block(deploy_src)
        assert "die " in block, (
            "a deploy that finds a LIVE lock owner must die(), not proceed — proceeding is the "
            "concurrent-`docker compose up` race that produces "
            "'removal of container ... is already in progress'"
        )

    def test_the_exit_trap_is_armed_only_after_the_lock_is_owned(self, deploy_src: str) -> None:
        # Ordering bug this pins: if the trap is armed BEFORE the ownership check, a REFUSED
        # deploy deletes the HOLDER's lock on its way out, un-protecting the live deploy.
        trap_at = deploy_src.index("trap 'rm -f \"$DEPLOY_LOCK\"' EXIT")
        claim_at = deploy_src.index('echo "$$" > "$DEPLOY_LOCK"')
        assert claim_at < trap_at, (
            "the EXIT trap must be armed AFTER claiming the lock — otherwise a deploy that "
            "REFUSES to race deletes the running deploy's lock as it exits (INC-36)"
        )

    def test_a_stale_lock_can_still_be_reclaimed(self, deploy_src: str) -> None:
        # Without this a SIGKILLed deploy would wedge CD permanently (the trap can't run).
        assert "LOCK_STALE_SECONDS" in deploy_src, (
            "a lock whose owner is dead must be reclaimable after a bounded age, or a SIGKILLed "
            "deploy wedges every future deploy forever"
        )


class TestTheDrainDoesNotFailOpen:
    """A failed probe must not read as 'zero runs in flight'."""

    def test_in_flight_does_not_swallow_a_failed_probe_as_zero(self, deploy_src: str) -> None:
        fn = _in_flight_block(deploy_src)
        assert "|| echo 0" not in fn, (
            "in_flight() must not end in `|| echo 0` — that makes an UNREACHABLE Dagit "
            "indistinguishable from 'drained', so the deploy recreates containers on top of a "
            "live run (INC-36; same swallowed-error class as INC-32)"
        )
        assert "unknown" in fn, (
            "in_flight() must return an `unknown` sentinel on probe failure so the caller can "
            "distinguish 'cannot verify' from 'nothing running'"
        )

    def test_the_drain_waits_for_runs_that_have_not_reached_started_yet(self, deploy_src: str) -> None:
        """NCAAF-INC-0914 — the hole that survived INC-36 and cost five runs in one deploy.

        The instance runs `QueuedRunCoordinator`, so every scheduled run passes
        QUEUED -> STARTING -> STARTED. A filter of `[STARTED]` alone is blind for the whole
        launch window. MEASURED 2026-09-14: run 06d7352c was ENQUEUED 18:00:00.77, went STARTING
        18:00:09.44 and did not reach STARTED until 18:00:47.67; the probe ran at 18:00:23,
        reported 0, and the recreate tore down the run worker 1s after it logged its first dbt
        command. Every in-flight run is a subprocess of dagster-codeloc, so a recreate kills all
        of them by construction — the drain must wait for every NON-TERMINAL run.
        """
        fn = _in_flight_block(deploy_src)
        statuses = re.search(r"statuses:\[([A-Z_,\s]+)\]", fn)
        assert statuses, "in_flight() must filter runs by status"
        listed = {s.strip() for s in statuses.group(1).split(",") if s.strip()}
        for required in ("QUEUED", "STARTING", "STARTED"):
            assert required in listed, (
                f"in_flight() must count runs in {required}. A run is not STARTED for its first "
                f"~47s under QueuedRunCoordinator, and a deploy authorised during that window "
                f"kills it (NCAAF-INC-0914). Listed: {sorted(listed)}"
            )

    def test_a_graphql_level_error_is_unknown_rather_than_drained(self, deploy_src: str) -> None:
        """NCAAF-INC-0914 — the same swallowed-error class INC-36 removed, one layer deeper.

        INC-36 hardened the TRANSPORT failure. But `runsOrError` resolving to `PythonError`
        returns HTTP 200 with a body carrying no `results` key, so `.get('results', [])` read a
        server-side error as "drained". The query already asks for `__typename`; the answer must
        be REQUIRED to be `Runs` or a failed probe is indistinguishable from an idle box.
        """
        fn = _in_flight_block(deploy_src)
        assert "__typename" in fn and "Runs" in fn, (
            "in_flight() must ask for __typename and require it to be `Runs` — otherwise a "
            "GraphQL-level error (PythonError) is read as zero in-flight runs"
        )
        assert re.search(r"__typename.{0,40}!=.{0,20}Runs|__typename.{0,20}==.{0,20}Runs", fn, re.S), (
            "asking for __typename is not enough — in_flight() must BRANCH on it. Without the "
            "check the field is decoration and a PythonError still reads as 'drained'."
        )

    def test_an_unverifiable_drain_is_loud_and_bounded(self, deploy_src: str) -> None:
        assert "DRAIN_UNKNOWN_MAX" in deploy_src, (
            "repeated probe failures must be bounded — blocking forever is as bad as failing open"
        )
        assert "ALERT" in deploy_src, (
            "proceeding without a verified drain must be ALERT-loud (E11.7 tier contract), never silent"
        )


class TestADeployAttributesTheRunsItKills:
    """NCAAF-INC-0914 Decision 1 (PM, 2026-09-15) — fail-and-attribute.

    The drain does not wait forever: past `DRAIN_TIMEOUT` it proceeds with a WARN, and
    `daily_ingestion_job` alone runs ~86 min. When that happens the runs die anyway. Before this,
    they died SILENTLY and surfaced hours later carrying Dagster's cause-free "This job is being
    forcibly marked as failed" — measured at 4h02m for run 06d7352c on 2026-09-14.

    Safe to automate ONLY because it is true by construction rather than by heuristic: a run with
    a live worker is a subprocess of `dagster-codeloc`, so recreating that container kills it.
    """

    def test_the_snapshot_is_taken_before_the_recreate(self, deploy_src: str) -> None:
        """The victim set must be fixed while the OLD worker still owns it.

        Deriving it AFTER the recreate would sweep in runs the NEW worker has since started —
        marking a live, working run as failed. Ordering is the whole guarantee.
        """
        snap_at = deploy_src.index('DOOMED_RUNS="$(doomed_runs)"')
        recreate_at = deploy_src.index("compose_up_core || rollback")
        assert snap_at < recreate_at, (
            "the doomed-run snapshot must be taken BEFORE `compose_up_core` recreates the "
            "containers — a set derived afterwards can contain runs the NEW worker started, and "
            "failing one of those is a worse defect than the silence this block removes"
        )

    def test_the_doomed_set_excludes_queued_runs(self, deploy_src: str) -> None:
        """⚠️ THE TRAP: the doomed set is NARROWER than the drain set, and reusing one for the
        other is a false attribution against a run that is alive.

        "Every in-flight run is a subprocess of dagster-codeloc" holds for STARTING/STARTED. A
        QUEUED run is a ROW IN POSTGRES awaiting dequeue: it survives the recreate untouched and
        the new daemon launches it moments later.
        """
        fn = _function_block(deploy_src, "doomed_runs")
        statuses = re.search(r"statuses:\[([A-Z_,\s]+)\]", fn)
        assert statuses, "doomed_runs() must filter runs by status"
        listed = {s.strip() for s in statuses.group(1).split(",") if s.strip()}
        assert listed == {"STARTING", "STARTED"}, (
            f"the doomed set must be exactly STARTING+STARTED — the states in which a worker "
            f"PROCESS exists. QUEUED/NOT_STARTED runs survive a recreate and marking them failed "
            f"is a false attribution; CANCELING is already being terminated deliberately. "
            f"Got: {sorted(listed)}"
        )

    def test_the_drain_waits_on_strictly_more_than_the_doomed_set(self, deploy_src: str) -> None:
        """The two lists are deliberately different and must not be 'unified' by a later tidy-up:
        we WAIT for queued work (it is about to launch), but we never ATTRIBUTE its death."""
        drain = _in_flight_block(deploy_src)
        doomed = _function_block(deploy_src, "doomed_runs")
        drain_set = set(re.search(r"statuses:\[([A-Z_,\s]+)\]", drain).group(1).replace(" ", "").split(","))
        doomed_set = set(re.search(r"statuses:\[([A-Z_,\s]+)\]", doomed).group(1).replace(" ", "").split(","))
        assert doomed_set < drain_set, (
            f"the doomed set must be a STRICT subset of the drain set — the drain waits for "
            f"queued work, the attribution never claims it. drain={sorted(drain_set)} "
            f"doomed={sorted(doomed_set)}"
        )
        assert "QUEUED" in drain_set - doomed_set, (
            "QUEUED must be waited for but never attributed"
        )

    def test_the_attribution_iterates_only_the_snapshot(self, deploy_src: str) -> None:
        """A fresh query inside the attribution block would re-derive the victim set after the
        recreate — the exact defect `test_the_snapshot_is_taken_before_the_recreate` forbids,
        reintroduced one layer down."""
        block = _attribution_block(deploy_src)
        assert "DOOMED_RUNS" in block, "the attribution must read the pre-teardown snapshot"
        assert "runsOrError" not in block, (
            "the attribution block must NOT re-query Dagster for in-flight runs — it must iterate "
            "ONLY the ids snapshotted before the recreate, or a run the new worker started can be "
            "marked failed"
        )

    def test_the_failure_message_names_the_deploy_and_the_commit(self, deploy_src: str) -> None:
        """PM constraint: a bare FAILED reproduces the cause-free alert one layer down. The
        attribution IS the point."""
        block = _attribution_block(deploy_src)
        assert "DEPLOY_SHA" in block and "NEW_HEAD" in block, (
            "the deploy's commit SHA must be passed into the attribution so the run's failure "
            "event names WHICH deploy killed it"
        )
        assert "deploy" in block.lower(), "the failure message must name the deploy as the cause"

    def test_a_run_that_finished_on_its_own_is_skipped(self, deploy_src: str) -> None:
        """Between the snapshot and the marking, a run may have completed — or Dagster's own 180 s
        start-timeout may have failed it. Overwriting a terminal status would destroy the real
        outcome."""
        block = _attribution_block(deploy_src)
        assert "is_finished" in block, (
            "the attribution must skip a run that already reached a terminal status"
        )

    def test_an_unverifiable_snapshot_attributes_nothing_and_says_so(self, deploy_src: str) -> None:
        """NF1.7(a): a probe that could not be evaluated is never scored as 'nothing to do'."""
        assert 'if [ "$DOOMED_RUNS" = "UNKNOWN" ]' in deploy_src, (
            "an unverifiable snapshot must be handled explicitly, not treated as an empty set"
        )
        unknown_branch = deploy_src[deploy_src.index('if [ "$DOOMED_RUNS" = "UNKNOWN" ]'):]
        unknown_branch = unknown_branch[: unknown_branch.index("# --- 5.")]
        assert "ALERT" in unknown_branch, (
            "an unverifiable snapshot must be LOUD — its consequence is a run that dies "
            "unattributed, i.e. exactly the pre-fix behaviour"
        )

    def test_a_failed_attribution_never_rolls_back_a_healthy_deploy(self, deploy_src: str) -> None:
        """The runs are already dead either way; losing a good deploy over the bookkeeping would
        be a strictly worse outcome (INC-36's rollback left the daemon down)."""
        block = _attribution_block(deploy_src)
        assert "rollback" not in block, (
            "the attribution step is best-effort — it must never roll back a deploy that is "
            "otherwise healthy"
        )


class TestATransientRemovalRaceDoesNotCostARollback:
    def test_the_core_up_is_retried(self, deploy_src: str) -> None:
        assert "compose_up_core" in deploy_src, "the core `up -d --build` must go through a retry wrapper"

    def test_the_retry_is_scoped_to_the_removal_race_signature(self, deploy_src: str) -> None:
        fn = _function_block(deploy_src, "compose_up_core")
        assert "already in progress" in fn, (
            "the retry must key on the container-removal-race signature specifically"
        )
        # Retrying a genuine build failure just burns a slate before rolling back anyway.
        assert "attempt" in fn and "-lt 2" in fn, (
            "the retry must be bounded to a single extra attempt, and only for the race — a real "
            "build error must roll back immediately"
        )


class TestTheRollbackVerifiesTheBoxCameBack:
    """Link 5 — the one that actually took the daemon down."""

    def test_rollback_checks_core_services_are_running(self, deploy_src: str) -> None:
        fn = _function_block(deploy_src, "rollback")
        assert "missing_core" in fn, (
            "rollback() must VERIFY the core services came back. On 2026-07-29 it reported a "
            "successful rollback while dagster-daemon was GONE — a rollback that leaves a "
            "service down is a worse outcome than the failed deploy it was reacting to"
        )

    def test_the_daemon_is_in_the_verified_set(self, deploy_src: str) -> None:
        core = _core_services(deploy_src)
        assert "dagster-daemon" in core, (
            "dagster-daemon MUST be verified: with no daemon NO schedule and NO sensor ticks "
            "(the E11.23 'silently never runs' class) and the daemon cannot page about itself"
        )
        for svc in ("dagster-codeloc", "dbt-runner"):
            assert svc in core, f"{svc} must be in the verified core set"

    def test_an_incomplete_rollback_pages_critical(self, deploy_src: str) -> None:
        fn = _function_block(deploy_src, "rollback")
        assert fn.count("notify CRITICAL") >= 2, (
            "an INCOMPLETE rollback (services still down) needs its OWN CRITICAL page, distinct "
            "from the ordinary 'rolled back, box is serving' one — they are very different states"
        )


class TestTheCdPollBudgetOutlastsTheBoxCommand:
    """Links 2+3 — the structural mismatch that released the concurrency group early."""

    def test_poll_budget_exceeds_ssm_execution_timeout(self, cd_src: str) -> None:
        exec_timeout = int(
            re.search(r'executionTimeout=\[\\?"(\d+)\\?"\]', cd_src).group(1)
        )
        polls = int(re.search(r"seq 1 (\d+)", cd_src).group(1))
        sleep_s = int(re.search(r"sleep (\d+)", cd_src).group(1))
        budget = polls * sleep_s
        assert budget > exec_timeout, (
            f"CD poll budget ({polls} x {sleep_s}s = {budget}s) must EXCEED SSM "
            f"executionTimeout ({exec_timeout}s). When it does not, a slow deploy makes the poll "
            "loop exit non-terminally → the job fails → the orchestration-cd concurrency group "
            "RELEASES while the command is still live on the box → the next queued run starts a "
            "SECOND deploy.sh and races it (INC-36). A concurrency group serializes GitHub jobs, "
            "not the async SSM commands they spawn."
        )

    def test_an_abandoned_command_is_cancelled(self, cd_src: str) -> None:
        assert "ssm cancel-command" in cd_src, (
            "if the poll loop still has no terminal status the command may be live on the box — "
            "cancel it so it cannot outlive the job and race the next deploy"
        )

    def test_deploys_are_still_serialized_at_the_workflow_level(self, cd_src: str) -> None:
        # Necessary but NOT sufficient (that was the false comfort in INC-36) — keep it anyway.
        cfg = yaml.safe_load(cd_src)
        assert cfg.get("concurrency", {}).get("group") == "orchestration-cd"
        assert cfg["concurrency"].get("cancel-in-progress") is False, (
            "cancel-in-progress must stay false — cancelling a deploy mid-`docker compose up` "
            "is precisely how you get a half-deployed box"
        )


# --- helpers ---------------------------------------------------------------------------


def _lock_block(src: str) -> str:
    start = src.index('if [ -f "$DEPLOY_LOCK" ]')
    return src[start : src.index('trap \'rm -f "$DEPLOY_LOCK"\' EXIT')]


def _attribution_block(src: str) -> str:
    """The NCAAF-INC-0914 fail-and-attribute section (7b), **comment-stripped**.

    ⚠️ The stripping is load-bearing, and the RED proof is what proved it: the section carries a
    comment explaining that `is_finished` skips an already-terminal run, so a raw substring scan
    for `is_finished` stayed GREEN with the actual check deleted. That is the INC-38
    prose-satisfies-the-guard class, inside a guard written for this incident.
    """
    start = src.index("# --- 7b.")
    block = src[start : src.index("# --- success", start)]
    return "\n".join(ln for ln in block.splitlines() if not ln.lstrip().startswith("#"))


def _in_flight_block(src: str) -> str:
    return _function_block(src, "in_flight")


def _function_block(src: str, name: str) -> str:
    """Body of a `name() { ... }` shell function, by brace balance."""
    start = src.index(f"{name}() {{")
    depth, i = 0, start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError(f"unterminated function {name}")


def _core_services(src: str) -> list[str]:
    return re.search(r"CORE_SERVICES=\(([^)]*)\)", src).group(1).split()
