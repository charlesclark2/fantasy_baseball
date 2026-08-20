"""E11.26 — the intraday_schedule_job hang guard.

2026-07-29: `intraday_schedule_job` ran >1h and parked `deploy.sh`'s drain loop for its full
DRAIN_TIMEOUT, which is what let a second deploy race the first (INC-36). INC-36 hardened the
DEPLOY; this pins the fix to the JOB.

The guard is deliberately in two halves, because each catches a different way the fix can rot:

  BEHAVIOURAL (against a REAL slow child, in the fast gate) — proves `run_bounded` actually kills
  on expiry, actually kills the GRANDCHILD too, and actually kills on a non-timeout interruption.
  A source-inspection test cannot tell "we pass timeout=" from "the child dies", and this repo's
  recurring defect is a guard that can only observe the former (NF1.7(a), INC-38, INC-39).

  WIRING (AST over `pipeline/` source, never importing it — the fast-gate rule) — proves the
  budget reaches the call sites and the tags reach the job. The behavioural half cannot see a leg
  someone leaves on the 1800s default.

Both halves were RED-proven against deliberately broken source before being trusted; see
betting_ml/tests/e11_26_red_proof.py.
"""
from __future__ import annotations

import ast
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from betting_ml.monitoring import intraday_tick_budget as budget
from betting_ml.utils import bounded_subprocess
from betting_ml.utils.bounded_subprocess import run_bounded

_REPO = Path(__file__).resolve().parents[2]
_OPS = _REPO / "pipeline" / "ops" / "intraday_ops.py"
_JOBS = _REPO / "pipeline" / "jobs" / "intraday_jobs.py"
_DAGSTER_YAML = _REPO / "services" / "dagster" / "dagster.yaml"
_SCHEDULES = _REPO / "pipeline" / "schedules" / "intraday_schedules.py"


# ── the budget's own invariants ──────────────────────────────────────────────

def test_the_budget_invariants_hold():
    """I1/I2/I3 — see intraday_tick_budget's module docstring. Reported as data so a violation
    names WHICH invariant broke rather than just failing an inequality."""
    assert budget.invariant_failures() == []


def test_i1_is_implied_by_i3_and_is_not_independently_falsifiable():
    """Recorded, not hidden. With len(LIVE_LEGS) == 3, I3 (3 x LEG <= MAX) entails I1
    (LEG < MAX), so the RED proof cannot isolate I1 — an isolating fixture per clause is
    necessary but NOT sufficient when one clause re-tests another (NF-D17, NF-W7j). I1 stays
    because it states the design intent and becomes independent if LIVE_LEGS ever shrinks."""
    assert len(budget.LIVE_LEGS) > 1, (
        "LIVE_LEGS is down to one leg — I1 is now independently binding and the RED proof should "
        "gain a fixture that isolates it"
    )
    assert budget.LEG_TIMEOUT_SECONDS * len(budget.LIVE_LEGS) <= budget.MAX_RUNTIME_SECONDS


def _schedule_cron(name: str) -> str:
    """The cron of ONE named ScheduleDefinition. Reading it off the specific assignment matters:
    a bare `"*/30 14-23 * * *" in src` is satisfied by artifact_freshness_daytime, which carries
    the identical cron — so it would stay green with the intraday cadence changed underneath it
    (the E9.61 two-renderers shape, and exactly what the RED proof caught here)."""
    for node in ast.walk(ast.parse(_SCHEDULES.read_text())):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        for kw in node.value.keywords:
            if kw.arg == "cron_schedule":
                return ast.literal_eval(kw.value)
    pytest.fail(f"{name} not found in {_SCHEDULES.name}")


@pytest.mark.parametrize("schedule_name", [
    "intraday_schedule_capture_daytime",
    "intraday_schedule_capture_overnight",
])
def test_the_cadence_constant_matches_the_actual_cron(schedule_name):
    """The whole budget is derived from the cadence, so a cron change must break this test rather
    than silently invalidate every number downstream of it."""
    cron = _schedule_cron(schedule_name)
    minute_field = cron.split()[0]
    # `*/30` and `0,30` are both 30-minute cadences; anything else invalidates the budget.
    assert minute_field in {"*/30", "0,30"}, (
        f"{schedule_name} now fires on `{cron}` — re-derive "
        f"intraday_tick_budget.TICK_CADENCE_SECONDS (and the leg caps) from the new cadence"
    )
    assert budget.TICK_CADENCE_SECONDS == 30 * 60


# ── behavioural: the child really dies ───────────────────────────────────────

def test_a_slow_child_is_killed_at_the_timeout():
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", "import time; time.sleep(300)"], timeout=1.0)
    elapsed = time.monotonic() - started
    assert elapsed < 30, f"run_bounded returned only after {elapsed:.1f}s — it did not kill the child"


def test_the_grandchild_is_killed_too(tmp_path):
    """subprocess.run kills only the DIRECT child; an orphaned grandchild keeps a vCPU on a
    2-vCPU box, and a pinned box starves the Dagster daemon (the compounding half of INC-32).
    The grandchild writes its pid, outlives its parent by design, and must still be dead."""
    pidfile = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time, os\n"
        f"c = subprocess.Popen([sys.executable, '-c', \"import time; time.sleep(300)\"])\n"
        f"open({str(pidfile)!r}, 'w').write(str(c.pid))\n"
        "time.sleep(300)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", script], timeout=3.0)

    assert pidfile.exists(), "the fixture never spawned a grandchild — the test would be vacuous"
    gpid = int(pidfile.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(gpid, 0)
        except OSError:
            return  # gone — the process group was killed
        time.sleep(0.2)
    try:  # do not leak a sleeping process into the rest of the suite
        os.kill(gpid, signal.SIGKILL)
    except OSError:
        pass
    pytest.fail(f"grandchild {gpid} survived the timeout — only the direct child was killed")


def test_an_interruption_also_kills_the_child(tmp_path):
    """Dagster run-monitoring terminates a run with a signal that surfaces in the op as an
    exception, NOT as a TimeoutExpired. `dagster/max_runtime` makes that a routine path now, so
    the child must die there too — otherwise the new ceiling would leave a subprocess running
    after the run it belonged to is gone."""
    marker = tmp_path / "child.pid"
    script = f"import os, time; open({str(marker)!r}, 'w').write(str(os.getpid())); time.sleep(300)"

    class _Boom(BaseException):
        pass

    real_communicate = subprocess.Popen.communicate
    calls = {"n": 0}

    def fake_communicate(self, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            # wait until the child has registered itself, then simulate the interruption
            for _ in range(100):
                if marker.exists():
                    break
                time.sleep(0.05)
            raise _Boom()
        return real_communicate(self, *a, **kw)

    subprocess.Popen.communicate = fake_communicate
    try:
        with pytest.raises(_Boom):
            run_bounded([sys.executable, "-c", script], timeout=60)
    finally:
        subprocess.Popen.communicate = real_communicate

    assert marker.exists(), "the child never started — the test would be vacuous"
    pid = int(marker.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    pytest.fail(f"child {pid} survived an interruption — run_bounded orphaned it")


def test_a_child_that_IGNORES_sigterm_is_still_killed(monkeypatch, tmp_path):
    """The escalation to SIGKILL is the whole point of the ladder, and a `time.sleep` child dies
    on SIGTERM — so without a SIGTERM-ignoring child the escalation is untested. A process that
    will not take a polite signal is also the realistic wedge: this repo has already been bitten
    by it (the autoheal stop-timeout finding — a container's PID 1 gets no default signal handling).

    ⚠️ The assertion is THE CHILD IS DEAD, not "run_bounded returned quickly". The RED proof caught
    an earlier elapsed-time version staying green against a SIGTERM-only runner: that runner still
    returns in ~11s (the post-kill drain bounds it), so a wall-clock threshold cannot tell a
    successful kill from a failed one — it measures the wrong thing entirely."""
    pidfile = tmp_path / "stubborn.pid"
    script = (
        "import os, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(300)\n"
    )
    # The GRACE is a tuning constant, not the mechanism under test — the mechanism is that the
    # ladder ESCALATES at all. Shortening it keeps this in the fast gate; the production value is
    # asserted separately just below.
    monkeypatch.setattr(bounded_subprocess, "GRACE_SECONDS", 0.5)
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", script], timeout=2.0)

    assert pidfile.exists(), "the child never armed its SIGTERM handler — the test would be vacuous"
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return  # SIGKILL landed
        time.sleep(0.2)
    try:  # never leak a 300s sleeper into the rest of the suite
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    pytest.fail(
        f"child {pid} ignored SIGTERM and survived — _terminate_group never escalated to SIGKILL, "
        f"so a wedged leg would outlive the timeout that exists to bound it"
    )


def test_the_production_grace_is_short_and_finite():
    """The value the box actually runs with. Short on purpose: this fires only on a path we have
    already decided to abandon, and every extra second is a second a wedged process keeps one of
    the box's two vCPUs."""
    assert 0 < bounded_subprocess.GRACE_SECONDS <= 10


def test_it_never_signals_the_callers_own_process_group(monkeypatch):
    """Found by the RED proof, not by review: deleting `start_new_session=True` made the proof run
    itself die with a signal, because the child then shares OUR process group and `killpg` reaches
    the caller. In production that is the Dagster run worker SIGKILLing itself — a bounded leg
    timeout turned into a lost run with no diagnosis, which is worse than the hang being fixed.

    The spy deliberately does NOT signal when the group is ours: with the guard removed this test
    must FAIL, never kill the test runner (a RED proof that takes the harness down proves nothing)."""
    called: list[int] = []
    real_killpg = os.killpg

    def spy(pgid, sig):
        called.append(pgid)
        if pgid == os.getpgid(0):
            return  # ⛔ swallowed on purpose — see the docstring
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", spy)
    # NO start_new_session → the child is in the caller's own process group.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        bounded_subprocess._terminate_group(proc)
        assert os.getpgid(0) not in called, (
            "_terminate_group signalled the CALLER's own process group — in the Dagster run worker "
            "that is the run killing itself"
        )
        assert proc.poll() is not None, (
            "the child survived the same-group fallback — it must still be killed directly"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def test_run_bounded_refuses_an_unbounded_call():
    """No default and no escape hatch: a new call site cannot inherit an unbounded wait."""
    with pytest.raises(ValueError):
        run_bounded([sys.executable, "-c", "pass"], timeout=0)
    with pytest.raises(TypeError):
        run_bounded([sys.executable, "-c", "pass"])  # timeout is keyword-only and required


def test_a_normal_child_still_returns_its_output_and_code():
    ok = run_bounded([sys.executable, "-c", "print('hi')"], timeout=30)
    assert ok.returncode == 0 and "hi" in ok.stdout
    bad = run_bounded([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
                      timeout=30)
    assert bad.returncode == 3 and "boom" in bad.stderr


# ── wiring: the budget reaches the call sites ────────────────────────────────

def _func(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in {path.name}")


def _script_calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in {"_run_script", "_run_dbt"}
    ]


@pytest.mark.parametrize("func_name", [
    "intraday_schedule_capture",       # the ingest leg
    "_schedule_lakehouse_intraday",    # the two rebuild legs + the ext refresh
    "intraday_lineup_rebuild",         # the SF dbt leg (retired under TICK_SF_FREE)
])
def test_every_tick_leg_passes_the_cadence_derived_timeout(func_name):
    """I4 — no leg may run on the module default. That default is 1800s, which IS this job's
    cadence, so a leg left on it re-opens the exact defect (a 'bounded' run that outlives its
    own successor) with nothing visibly wrong in the source."""
    fn = _func(_OPS, func_name)
    calls = _script_calls(fn)
    assert calls, f"{func_name} makes no _run_script/_run_dbt call — this guard would be vacuous"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "timeout" in kw, (
            f"{func_name}: a subprocess leg has no explicit timeout= and would inherit the "
            f"1800s module default — which equals the tick cadence"
        )
        assert ast.unparse(kw["timeout"]) == "_TICK_LEG_TIMEOUT", (
            f"{func_name}: the leg timeout must be the cadence-derived _TICK_LEG_TIMEOUT, not a "
            f"literal ({ast.unparse(kw['timeout'])}) — a hand-picked number drifts from the cron"
        )


def test_run_script_delegates_to_the_process_group_killer():
    """`subprocess.run` would satisfy a naive 'does it pass timeout=' check while still orphaning
    grandchildren, so pin the delegation to run_bounded specifically."""
    fn = _func(_OPS, "_run_script")
    body = ast.unparse(fn)
    assert "run_bounded(" in body, "_run_script must delegate to run_bounded (process-group kill)"
    assert "subprocess.run(" not in body, (
        "_run_script must not fall back to subprocess.run — it kills only the direct child"
    )


def test_the_job_carries_a_ceiling_below_its_cadence():
    """The authoritative guard: run-monitoring terminates the run whatever it is waiting on, so it
    does not depend on anyone having enumerated every wait in the chain."""
    tree = ast.parse(_JOBS.read_text())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "intraday_schedule_job"), None)
    assert fn is not None, "intraday_schedule_job not found"
    decorators = " ".join(ast.unparse(d) for d in fn.decorator_list)
    assert "MAX_RUNTIME_SECONDS_TAG" in decorators, (
        "intraday_schedule_job must carry the dagster/max_runtime tag — without it the only "
        "ceiling is the 4h global cap, 8x this job's own cadence"
    )
    assert "_TICK_MAX_RUNTIME" in decorators, (
        "the ceiling must be the cadence-derived constant, not a literal"
    )
    assert "concurrency_group" in decorators, (
        "intraday_schedule_job must carry a concurrency_group tag so ticks cannot stack"
    )


def test_the_dagster_instance_actually_enforces_the_concurrency_group():
    """A concurrency_group tag is inert unless the instance has the matching limit rule. Pinning
    both ends stops the tag becoming decoration (the 'documented but never set' class)."""
    cfg = _DAGSTER_YAML.read_text()
    assert "tag_concurrency_limits" in cfg and 'key: "concurrency_group"' in cfg, (
        "services/dagster/dagster.yaml no longer limits concurrency_group — the job tag is inert"
    )


def test_the_sns_publish_is_bounded():
    """The page fires exactly when the tick is already failing and slow, so an unbounded publish
    (botocore defaults: 60s connect + 60s read, up to 5 attempts) compounds the overrun it reports."""
    src = (_REPO / "pipeline" / "utils" / "alerting.py").read_text()
    tree = ast.parse(src)
    publish = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "publish"
    ]
    assert publish, "no SNS publish call found in alerting.py"
    for call in publish:
        client = call.func.value
        assert isinstance(client, ast.Call), "expected boto3.client(...).publish(...)"
        assert any(k.arg == "config" for k in client.keywords), (
            "the SNS client must pass an explicit botocore Config — the defaults allow a ~5 minute "
            "stall on the alerting path"
        )
