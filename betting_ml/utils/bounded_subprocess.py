"""E11.26 — a subprocess runner that CANNOT outlive its budget or orphan its children.

WHY THIS EXISTS (and why "we already pass timeout=" was not enough):

``subprocess.run(..., timeout=N)`` bounds the WAIT and kills the DIRECT child — but it does
two things that matter on a 2-vCPU box running a 30-minute tick:

  1. It kills only the direct child. Any grandchild the script spawned is REPARENTED and keeps
     running, so a "killed" leg can still hold a vCPU. On an r6g.large that is half the box, and
     a pinned box starves the Dagster daemon — the INC-32 failure mode, reached from the other
     side (there a subprocess blocked the daemon THREAD; here an orphan starves the daemon's CPU).
  2. It only kills on TimeoutExpired. When Dagster's run monitoring TERMINATES a run (a SIGTERM
     that surfaces in the op as ``DagsterExecutionInterruptedError``), CPython's ``run()`` does
     kill the child via its ``BaseException`` handler — but again only the direct child. E11.26
     puts a ``dagster/max_runtime`` ceiling on ``intraday_schedule_job``, which makes that
     termination path a ROUTINE occurrence rather than a rarity, so it has to be clean.

So the child is started in its OWN process group (``start_new_session=True``) and the whole group
is signalled on timeout AND on any BaseException. The public surface is deliberately identical to
``subprocess.run``'s: a ``CompletedProcess`` on success, ``subprocess.TimeoutExpired`` on expiry —
so callers keep the handling they already have.

Import-safe by construction (stdlib only, no ``pipeline`` import), so the fast gate can drive it
against a real slow child instead of only inspecting source (the repo's vacuous-guard rule).
"""
from __future__ import annotations

import os
import signal
import subprocess

__all__ = ["run_bounded", "GRACE_SECONDS"]

# After SIGTERM, how long the group gets to exit before SIGKILL. Short on purpose: this fires only
# on a path we have already decided to abandon, and every extra second is a second the wedged
# process keeps a vCPU on a two-vCPU box.
GRACE_SECONDS = 5.0

# Ceiling on draining the pipes after the group has been killed. Without it, a bare post-kill
# ``communicate()`` could itself block forever on a pipe an unkillable grandchild still holds —
# i.e. the timeout handler would reintroduce the hang it exists to remove.
_DRAIN_SECONDS = 10.0


def _terminate_group(proc: subprocess.Popen) -> None:
    """SIGTERM the child's process group, then SIGKILL whatever is left. Never raises.

    ⚠️⚠️ THE `pgid == os.getpgid(0)` GUARD IS LOAD-BEARING, and this is not hypothetical — the
    E11.26 RED proof discovered it by deleting `start_new_session=True` and watching the whole
    proof run die with a signal. Without `start_new_session` the child shares the CALLER's process
    group, so `killpg` signals the caller: in production that is the Dagster run worker SIGKILLing
    itself, turning a bounded leg timeout into a lost run with no diagnosis. A process-group kill
    is only ever safe against a group we are not a member of, so never signal one we are.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:  # already reaped
        return
    if pgid == os.getpgid(0):
        # Not our own group's problem to solve — fall back to the direct child. The caller loses
        # the grandchild-reaping property, which is exactly why the guard test pins
        # start_new_session separately rather than trusting this fallback.
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return  # gone, or not ours to signal
        try:
            proc.wait(timeout=GRACE_SECONDS)
            return  # exited on SIGTERM — no need to escalate
        except subprocess.TimeoutExpired:
            continue


def _drain(proc: subprocess.Popen) -> tuple[str, str]:
    """Collect whatever the (now dead) child wrote, without ever blocking indefinitely."""
    try:
        out, err = proc.communicate(timeout=_DRAIN_SECONDS)
    except subprocess.TimeoutExpired:
        return "", ""
    except ValueError:  # pipes already closed
        return "", ""
    return out or "", err or ""


def run_bounded(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` with a hard wall-clock ceiling, killing the whole process group on expiry.

    Raises ``subprocess.TimeoutExpired`` (with the partial stdout/stderr attached, so a caller
    can page the diagnostic TAIL — INC-42) once the group has actually been killed. A finite
    ``timeout`` is REQUIRED: it is keyword-only and has no default precisely so a new call site
    cannot inherit an unbounded wait by omission.
    """
    if timeout is None or timeout <= 0:
        raise ValueError("run_bounded requires a finite positive timeout")

    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,  # own process group → the whole tree is killable
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_group(proc)
        stdout, stderr = _drain(proc)
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr) from None
    except BaseException:
        # Dagster run-monitoring termination / KeyboardInterrupt / anything else. The child must
        # NOT survive the op that started it.
        _terminate_group(proc)
        _drain(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
