"""NCAAF-ODDS-LIVE followUp ⑦ — the in-window RE-SERVE tier.

WHAT THIS DEFENDS, and why it is a story at all
-----------------------------------------------
NCAAF-ODDS-LIVE made the market-line PRODUCER hourly inside 24h of kickoff. Its CONSUMER — the
serving write that puts the line in front of a reader — stayed on a daily 06:00 PT schedule. So a
line that moved on a Saturday morning reached the reader only after the games: the INC-25
consumer/producer ordering mismatch, on the REFRESH axis rather than the build axis. The operator
chose option (b): give the re-serve the same tiering the capture has.

The four properties that make that safe, each pinned below:

  1. ONE window, SHARED BY IMPORT. `should_reserve` and `should_capture` must read the same
     `DENSE_WINDOW_HOURS` through `in_dense_window`. A second `24` elsewhere is a second rule free
     to drift the moment either is tuned (E9.61).
  2. MONOTONE. The 06:00 PT baseline is preserved exactly, so every write that happened under the
     old daily schedule still happens. A cadence change whose worst case is "no better than
     before" is one that can land in-season.
  3. FAILS OPEN. The gate exists to skip redundant writes, so an unevaluable gate must fall
     through to the write. A gate that failed closed would turn a transient lake read into a
     silently frozen board — the NF-FRESH1 outage this tier exists to make LESS likely.
  4. THE CHAINED OP IS NOT GATED. `ncaaf_serving_write_after_snapshot_op` must publish whenever
     the snapshot run does, whatever the clock says (INC-25).

⚠️ Everything touching `pipeline/` is SOURCE INSPECTION, never an import: `pipeline/__init__.py`
reads the dbt manifest, a gitignored build artifact CI does not have, so an importing test dies at
COLLECTION in the only environment that runs it (E11.23). ⛔ And NOT `skipif` — a skip would make
these vacuous in exactly that environment.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import scripts.write_ncaaf_serving_store as W
from quant_sports_intel_models.football.ncaaf.ingest import odds_live_capture as L

_REPO = Path(__file__).resolve().parents[2]
_JOB = _REPO / "pipeline/jobs/sports_ncaaf_serving_write_job.py"
_SCHED = _REPO / "pipeline/schedules/sports_ncaaf_serving_write_schedules.py"
_LIVE_SCHED = _REPO / "pipeline/schedules/sports_odds_capture_schedules.py"

PT = ZoneInfo("America/Los_Angeles")

#: The local hour the RETIRED daily cron fired at ("0 6 * 8-12,1 *", America/Los_Angeles).
#: ⭐ A LITERAL, deliberately, and not `W.SERVING_BASELINE_HOUR_LOCAL`. The monotone claim is
#: "every write the OLD schedule made still happens", and the old schedule's hour is a fact
#: about history that the new constant cannot change. Reading it from the constant would make
#: the whole claim vacuous — move the constant and both sides of the comparison move with it,
#: which is the test restating the code rather than checking it (NF-C0e).
_RETIRED_DAILY_HOUR_PT = 6


def _executable_only(src: str) -> str:
    """Source with docstrings and `#` comments stripped, so a scan cannot be satisfied — or
    defeated — by prose (INC-38)."""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return "\n".join(re.sub(r"#.*$", "", line) for line in src.splitlines())


def _at(local_hour: int, day: int = 29) -> datetime:
    """A UTC instant that is `local_hour` in America/Los_Angeles."""
    return datetime(2026, 8, day, local_hour, 0, tzinfo=PT).astimezone(timezone.utc)


def _func(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name} — the guard has rotted, not passed")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ONE window, shared with the capture by import (E9.61)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("hours", [0.1, 1, 6, 12, 23.9, 24.1, 30, 72, 240])
def test_the_reserve_and_the_capture_agree_on_the_dense_window_at_every_distance(hours):
    """The consumer's window must BE the producer's, not a copy that happens to match today.

    Swept across the boundary in both directions: a copy that drifted by even an hour would show
    up here as a disagreement at 23.9h or 24.1h.
    """
    now = _at(13)                      # 13:00 PT — deliberately NOT the baseline hour, so the
    kicks = [now + timedelta(hours=hours)]   # dense branch is the ONLY thing that can fire.
    dense, _ = L.in_dense_window(kicks, now=now)
    serve, why = W.should_reserve(kicks, now=now)
    assert serve is dense, (
        f"at {hours}h to kickoff the capture says dense={dense} but the re-serve says "
        f"serve={serve} ({why}) — the two have drifted apart")


def test_the_reserve_does_not_carry_its_own_copy_of_the_window():
    """A literal window in `should_reserve` would be a second rule set. It must delegate."""
    body = _executable_only(
        ast.get_source_segment(W.__file__ and Path(W.__file__).read_text(encoding="utf-8"),
                               _func(Path(W.__file__), "should_reserve")) or "")
    assert "in_dense_window" in body, "should_reserve must delegate the window to the capture"
    assert not re.search(r"\b24\b", body), (
        "should_reserve carries a literal window — tuning DENSE_WINDOW_HOURS would now move the "
        "capture and leave the re-serve behind")


def test_the_reserve_inherits_the_shared_window_rather_than_overriding_it():
    """The precise mechanism, since the obvious test of it cannot work.

    `in_dense_window`'s window is a DEFAULT ARGUMENT, so it is bound at import — which means a
    monkeypatch of `DENSE_WINDOW_HOURS` cannot reach it, and a test that tried would be asserting
    Python's default-arg semantics rather than this design. What actually makes the two one rule
    is that `should_reserve` calls `in_dense_window` and passes NO window of its own, inheriting
    the capture's. An override keyword here would be a second window wearing a delegation's
    clothes, and it is the one thing this file can check that the agreement sweep above cannot.
    """
    fn = _func(Path(W.__file__), "should_reserve")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", None)) == "in_dense_window"]
    assert calls, "should_reserve does not call in_dense_window — the window is not shared"
    for call in calls:
        overrides = [k.arg for k in call.keywords if k.arg == "dense_window_hours"]
        assert not overrides, (
            "should_reserve passes its own dense_window_hours — it no longer inherits the "
            "capture's window, so tuning DENSE_WINDOW_HOURS would move only one of them")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. MONOTONE — the old daily write is preserved exactly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_baseline_hour_still_matches_the_retired_daily_cron():
    """The monotone claim rests on this equality, so it is asserted rather than assumed —
    and asserted against the literal the retired cron used, not against itself."""
    assert W.SERVING_BASELINE_HOUR_LOCAL == _RETIRED_DAILY_HOUR_PT, (
        "the baseline write moved off 06:00 PT — the new tier no longer contains every write "
        "the old daily schedule made, so the monotone safety argument no longer holds")


@pytest.mark.parametrize("local_hour", range(24))
def test_outside_the_window_only_the_old_daily_baseline_hour_publishes(local_hour):
    """With no kickoff anywhere near, the new hourly schedule must behave EXACTLY like the daily
    one it replaced: one write a day, at 06:00 PT."""
    now = _at(local_hour)
    serve, why = W.should_reserve([now + timedelta(days=6)], now=now)
    assert serve is (local_hour == _RETIRED_DAILY_HOUR_PT), (
        f"{local_hour:02d}:00 PT: serve={serve} ({why})")


@pytest.mark.parametrize("local_hour", range(24))
def test_the_baseline_write_still_happens_on_a_day_with_no_games_at_all(local_hour):
    """An empty kickoff list is the out-of-season / nothing-snapshotted case. The daily write must
    survive it — the manifest's `current_game_day` rolls whether or not anyone is playing."""
    now = _at(local_hour)
    serve, _ = W.should_reserve([], now=now)
    assert serve is (local_hour == _RETIRED_DAILY_HOUR_PT)


@pytest.mark.parametrize("local_hour", range(24))
def test_inside_the_window_every_hour_publishes(local_hour):
    """The point of the story: a moving line reaches the reader within the hour, not tomorrow."""
    now = _at(local_hour)
    serve, why = W.should_reserve([now + timedelta(hours=3)], now=now)
    assert serve is True, f"{local_hour:02d}:00 PT inside the dense window did not publish ({why})"


def test_the_new_tier_is_a_strict_superset_of_the_old_daily_schedule():
    """Stated as the property, not as a sample: over a full day × a range of kickoff distances,
    there is NO hour at which the old schedule wrote and the new tier does not."""
    missed = []
    for hour in range(24):
        now = _at(hour)
        for days in (0.05, 0.5, 1.5, 4, 30):
            old_would_write = hour == _RETIRED_DAILY_HOUR_PT
            new_writes, _ = W.should_reserve([now + timedelta(days=days)], now=now)
            if old_would_write and not new_writes:
                missed.append((hour, days))
    assert not missed, f"the new tier DROPS writes the old schedule made: {missed}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. A skip must say why (NF-FRESH1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_skipped_tick_names_the_clock_and_the_kickoff_distance():
    """A cheap always-succeeding op that skips silently is how a store freezes behind 19 green
    runs. The reason must let an operator tell "skipped on purpose" from "stopped firing"."""
    now = _at(13)
    serve, why = W.should_reserve([now + timedelta(days=5)], now=now)
    assert serve is False
    assert "13:00" in why and "120.0h" in why and "0 writes" in why, why


@pytest.mark.parametrize("hours,expect", [(3, "dense tier"), (200, "skip")])
def test_every_branch_returns_a_non_empty_reason(hours, expect):
    now = _at(13)
    _, why = W.should_reserve([now + timedelta(hours=hours)], now=now)
    assert why.startswith(expect) and len(why) > 20, why


def test_the_baseline_branch_says_it_is_the_baseline():
    now = _at(_RETIRED_DAILY_HOUR_PT)
    serve, why = W.should_reserve([now + timedelta(days=5)], now=now)
    assert serve is True and "baseline tier" in why, why


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The kickoff read is LAKE-ONLY (the job's stated no-CFBD contract)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_kickoff_read_does_not_reach_for_cfbd():
    """A CFBD dependency behind a HALT-tier serving write means a missing key could stop the board
    refreshing — strictly worse than the staleness this tier fixes. The job docstring PROMISES
    lake-only; this is that promise made mechanical."""
    src = Path(W.__file__).read_text(encoding="utf-8")
    body = _executable_only(ast.get_source_segment(src, _func(Path(W.__file__),
                                                              "upcoming_kickoffs")) or "")
    assert "_season_kickoffs" not in body and "cfbd" not in body.lower(), body
    assert "read_snapshots" in body, "the kickoff read must come from the snapshot table"


def test_upcoming_kickoffs_returns_only_future_kickoffs(monkeypatch):
    import pandas as pd
    now = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)
    frame = pd.DataFrame({"commence_time": [
        "2026-08-29T16:00:00.000Z",   # already kicked off
        "2026-08-29T23:00:00.000Z",   # upcoming
        "2026-08-30T02:30:00.000Z",   # upcoming
        "2026-08-29T23:00:00.000Z",   # a duplicate snapshot row for the same game
    ]})
    monkeypatch.setattr(W, "read_snapshots", lambda *a, **k: frame)
    kicks = W.upcoming_kickoffs(2026, now=now)
    assert len(kicks) == 2, f"expected 2 distinct upcoming kickoffs, got {kicks}"
    assert all(k > now for k in kicks)


def test_an_absent_snapshot_table_yields_no_kickoffs_rather_than_raising(monkeypatch):
    """Pre-opener the table legitimately has nothing. That is the baseline-only case, not an error
    — and it must not be able to fail the HALT-tier op."""
    monkeypatch.setattr(W, "read_snapshots", lambda *a, **k: None)
    assert W.upcoming_kickoffs(2026) == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The op — fails OPEN, logs BOTH branches, and does not gate the chained write
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_tier_gate_fails_open_to_a_write():
    """Structural, not a substring: the except handler must RETURN a tuple whose first element is
    literally True. A gate that failed closed would freeze the board on a transient lake read."""
    fn = _func(_JOB, "_tier_decision")
    handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
    assert handlers, "_tier_decision has no exception handler — an unevaluable gate would raise"
    returns = [n for h in handlers for n in ast.walk(h) if isinstance(n, ast.Return)]
    assert returns, "the handler does not return — it cannot be failing open"
    for r in returns:
        assert isinstance(r.value, ast.Tuple) and len(r.value.elts) >= 1, ast.dump(r)
        first = r.value.elts[0]
        assert isinstance(first, ast.Constant) and first.value is True, (
            "the tier gate FAILS CLOSED on an unevaluable read — a transient lake failure would "
            "silently stop publishing the board")


def test_the_chained_snapshot_write_is_not_tier_gated():
    """INC-25: the authoritative write runs downstream of the snapshot run, in the same run. It
    must publish whatever the clock says — gating it would make the week's fresh vintage wait for
    an arbitrary hour."""
    fn = _func(_JOB, "ncaaf_serving_write_after_snapshot_op")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_tier_decision" not in called, (
        "the chained op is tier-gated — the snapshot run's own publish would be skipped by the "
        "clock (INC-25)")
    assert "_run_serving_write" in called


def test_the_gated_op_logs_on_both_branches():
    """Both, because a skip that says nothing reads exactly like a schedule that stopped."""
    fn = _func(_JOB, "ncaaf_serving_write_op")
    skip = [n for n in ast.walk(fn) if isinstance(n, ast.If)]
    assert skip, "the op has no branch — it is not gated at all"
    logs = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr in {"info", "warning"}]
    assert len(logs) >= 2, f"the op logs on {len(logs)} branch(es); both branches must speak"


def test_the_gated_op_still_calls_the_write_when_the_tier_says_serve():
    fn = _func(_JOB, "ncaaf_serving_write_op")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"_tier_decision", "_run_serving_write"} <= called, called


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The schedule — hourly, offset from its producer, still operator-gated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cron(path: Path, const: str) -> str:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(getattr(t, "id", None) == const for t in node.targets)):
            return node.value.value
    raise AssertionError(f"{const} not found in {path.name}")


def test_the_serving_write_ticks_hourly():
    minute, hour = _cron(_SCHED, "NCAAF_SERVING_WRITE_CRON").split()[:2]
    assert hour == "*", "the serving write is not hourly — the dense tier can never fire"
    assert minute.isdigit()


def test_the_reserve_runs_AFTER_the_capture_within_the_hour():
    """A consumer that ticks at the same instant as its producer races it, and would publish the
    previous hour's line. The offset is the ordering mechanism between two separate jobs."""
    serve_min = int(_cron(_SCHED, "NCAAF_SERVING_WRITE_CRON").split()[0])
    cap_min = int(_cron(_LIVE_SCHED, "NCAAF_ODDS_LIVE_CRON").split()[0])
    assert serve_min > cap_min, (
        f"the re-serve fires at :{serve_min:02d} and the capture at :{cap_min:02d} — the consumer "
        "does not run after its producer")


def test_the_serving_schedule_still_ships_stopped():
    """⛔ Read off the NAMED schedule, not a bare scan: another schedule in the same file would
    satisfy a loose `default_status=` match (the E11.26 lesson)."""
    fn = _func(_SCHED, "sports_ncaaf_serving_write_schedule")
    decorators = [d for d in fn.decorator_list if isinstance(d, ast.Call)]
    kw = {k.arg: k for d in decorators for k in d.keywords}
    assert "default_status" in kw, "the schedule no longer declares a default status"
    assert "STOPPED" in ast.dump(kw["default_status"].value), (
        "the NCAAF serving-write schedule would now self-start — every NCAAF schedule is "
        "operator-gated (E11.23 carve-out)")


def test_the_schedule_window_still_covers_the_bowl_season():
    months = _cron(_SCHED, "NCAAF_SERVING_WRITE_CRON").split()[3]
    assert months == "8-12,1", f"the in-season window changed to {months!r}"


def test_the_documented_cron_matches_the_code():
    """⛔ The operator's intended-state table names this cron literally. One thing, one owner —
    the same pin `sports_ncaaf_roll_forward_schedule` already carries, for the same reason: a
    runbook that has drifted from the code is worse than no runbook, because it is believed."""
    cron = _cron(_SCHED, "NCAAF_SERVING_WRITE_CRON")
    doc = (_REPO / "services/dagster/aws/BOX_OPERATIONS.md").read_text(encoding="utf-8")
    row = [ln for ln in doc.splitlines()
           if ln.startswith("| `sports_ncaaf_serving_write_schedule`")]
    assert len(row) == 1, "the §10 row for the serving-write schedule is missing or duplicated"
    assert f"`{cron}`" in row[0], (
        f"BOX_OPERATIONS §10 does not name the live cron {cron!r} — the runbook and the schedule "
        "have drifted apart")
