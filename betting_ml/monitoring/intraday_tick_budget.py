"""E11.26 — the time budget for `intraday_schedule_job`, derived from its own cron cadence.

ROOT CAUSE (2026-07-29, the >1h run that triggered INC-36's deploy race).

The reflex reading was INC-32 — "an un-timed-out subprocess on a serialized path". It is NOT that:
every subprocess on this job's chain already carries a finite `timeout=` (the A2.16/INC-32 cure
reached `intraday_ops._run_script` in 2026-06-15). The defect is the SIZE of those timeouts
relative to the job's own cadence, plus the absence of any ceiling on the job as a whole:

    tick cadence (cron `*/30 14-23` + `0,30 0-3` UTC) .......  1800 s
    per-leg timeout, every leg (module default) .............  1800 s   ← each leg alone may
                                                                          consume the whole tick
    live budget, TICK_SF_FREE=1 (ingest + w3pre + w7b) ......  5400 s = 3.0x the cadence
    rollback budget, TICK_SF_FREE=0 (+ ext refresh + dbt,
      incl. the dbt-runner 409 RetryRequested 40x30s) ....... 10200 s = 5.7x the cadence
    global run_monitoring.max_runtime_seconds ..............  14400 s = 8x the cadence

So a run of ">1 hour" needs NO hang at all — it is inside the budget the job was granted. Nothing
terminated it, because the only ceiling in the system is a 4-hour global cap sized for the Sunday
full-refresh build. That is what parked `deploy.sh`'s drain loop for its full DRAIN_TIMEOUT and let
a second deploy race the first (INC-36). INC-36 made the DEPLOY survive it; this module bounds the
JOB, which is the half that was still open.

⭐ THE GENERALISABLE SHAPE: a periodic job's per-attempt budget is a claim about how long a tick may
run, and it is only meaningful RELATIVE TO THE CADENCE. A default timeout copied from a daily batch
job (30 min) is, on a 30-minute tick, the same as no timeout at all — the run is "bounded" and still
outlives its own successor. Size a tick's budget from its cron, not from the module default.

THE INVARIANTS (pinned by betting_ml/tests/test_e11_26_intraday_tick_budget.py):

  I1  every leg cap < MAX_RUNTIME_SECONDS
        A single wedged leg is ALWAYS caught in-op, so it produces the clean per-leg failure +
        page that INC-41 built (one poisoned leg costs at most its own table) rather than being
        swept away by a run-level termination that says nothing about which leg died.
  I2  MAX_RUNTIME_SECONDS < TICK_CADENCE_SECONDS
        A run is dead before its own successor fires. Ticks cannot stack, so they cannot compound
        into the CPU saturation that starves the Dagster daemon (INC-32), and `deploy.sh`'s drain
        can never find an in-flight run older than one cadence (INC-36).
  I3  sum(live legs) <= MAX_RUNTIME_SECONDS
        In the configuration actually deployed (TICK_SF_FREE=1), even EVERY leg timing out is
        still caught in-op. In the rollback configuration the sum exceeds the ceiling on purpose —
        that is the "everything is broken" case, where a loud run-level termination is the correct
        and sufficient outcome, and sizing every leg for the simultaneous failure of all the
        others would squeeze each one below its honest working time.
  I4  no leg runs on the module default
        The 1800 s default IS the cadence; a leg left on it re-opens the defect silently.

⚠️ I1 IS CURRENTLY IMPLIED BY I3 AND SO CANNOT BE ISOLATED BY A RED PROOF. With three live legs,
I3 (3 x LEG <= MAX) entails I1 (LEG < MAX), so no mutation of these constants breaks I1 alone —
the NF-D17/NF-W7j shape (an isolating fixture is meaningless when one clause re-tests another).
It is kept rather than deleted because it is the clause that states the DESIGN INTENT (a single
wedged leg must fail in-op with its own name attached), and it becomes independently binding the
moment LIVE_LEGS shrinks or the ceiling is re-derived. The guard test records the implication
explicitly instead of shipping a fixture that pretends to isolate it.

WHY 480 s PER LEG: measured, not guessed. The event log for this job (INC-42 diagnostics,
2026-08-12) shows a healthy tick completing in UNDER 10 MINUTES for all three live legs together
(the 00:00 run), i.e. ~200 s per leg, and a pathological w3pre leg erroring on its own at 1044 s.
480 s is ~2.4x the healthy per-leg time and still kills the pathological leg. The cost of a false
kill is bounded and visible: the leg pages CRITICAL through the existing INC-41 path and the next
tick retries it 30 minutes later — strictly better than the current behaviour, where the same leg
runs to 1800 s and takes the whole tick past its cadence.
"""
from __future__ import annotations

__all__ = [
    "TICK_CADENCE_SECONDS",
    "MAX_RUNTIME_SECONDS",
    "LEG_TIMEOUT_SECONDS",
    "LIVE_LEGS",
    "RETIRED_LEGS",
    "invariant_failures",
]

# From the cron in pipeline/schedules/intraday_schedules.py (`*/30 14-23` and `0,30 0-3` UTC).
# A DESIGN quantity, not a measurement — which is what makes the budget below derivable rather
# than reverse-engineered from an observed duration.
TICK_CADENCE_SECONDS = 1800

# The job-level ceiling, published as the `dagster/max_runtime` run tag so the daemon's
# run-monitoring terminates the run. 5 minutes of slack under the cadence leaves the queued
# successor a clean start.
MAX_RUNTIME_SECONDS = 1500

# One uniform per-leg cap. Uniform on purpose: the legs have no measured reason to differ, and a
# per-leg table of hand-tuned numbers is a set of unverifiable claims a future reader cannot check.
LEG_TIMEOUT_SECONDS = 480

# The legs that run in the DEPLOYED configuration (TICK_SF_FREE=1, flipped 2026-07-26).
LIVE_LEGS = (
    "ingest_statsapi.py schedule",
    "run_w1_lakehouse.py --w3pre-only",
    "run_w1_lakehouse.py --w7b-only",
)

# Retired under TICK_SF_FREE=1 but still reachable on a rollback, so they are budgeted too — an
# unbudgeted rollback path is the "documented but never set" class facing the other way.
RETIRED_LEGS = (
    "refresh_w1_external_tables.py",
    "dbt run (intraday lineup rebuild)",
)


def invariant_failures() -> list[str]:
    """Return a human-readable failure per violated invariant; empty list == the budget is sound.

    Exposed as data rather than asserted at import so the guard test can name WHICH invariant broke,
    and so a future tuning change is forced through a check that states its reasoning.
    """
    failures: list[str] = []
    if not LEG_TIMEOUT_SECONDS < MAX_RUNTIME_SECONDS:
        failures.append(
            f"I1: a leg cap ({LEG_TIMEOUT_SECONDS}s) is not below the job ceiling "
            f"({MAX_RUNTIME_SECONDS}s) — a single wedged leg would be swept away by a run-level "
            f"termination instead of producing its own named failure"
        )
    if not MAX_RUNTIME_SECONDS < TICK_CADENCE_SECONDS:
        failures.append(
            f"I2: the job ceiling ({MAX_RUNTIME_SECONDS}s) is not below the tick cadence "
            f"({TICK_CADENCE_SECONDS}s) — a run could still outlive its own successor"
        )
    live_budget = LEG_TIMEOUT_SECONDS * len(LIVE_LEGS)
    if live_budget > MAX_RUNTIME_SECONDS:
        failures.append(
            f"I3: the live-configuration budget ({live_budget}s over {len(LIVE_LEGS)} legs) exceeds "
            f"the job ceiling ({MAX_RUNTIME_SECONDS}s) — all-legs-timeout would no longer be caught "
            f"in-op in the configuration that is actually deployed"
        )
    return failures
