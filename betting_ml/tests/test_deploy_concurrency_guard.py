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

    def test_an_unverifiable_drain_is_loud_and_bounded(self, deploy_src: str) -> None:
        assert "DRAIN_UNKNOWN_MAX" in deploy_src, (
            "repeated probe failures must be bounded — blocking forever is as bad as failing open"
        )
        assert "ALERT" in deploy_src, (
            "proceeding without a verified drain must be ALERT-loud (E11.7 tier contract), never silent"
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
