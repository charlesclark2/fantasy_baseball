"""E11.24 — Gate-0 v2: build-day-aware structural normality.

Gate-0 v1 was a fixed band on TOTAL executions. On the 2026-08-12 soak read it FAILED (1,434 vs a
1,536 floor) on a day whose every per-family count was normal. It is confounded twice: build-day
bimodality, and — the one that matters — **the levers themselves delete statements, so total
executions fall as E11.24 succeeds**. A gate that fires because the fix worked is not a gate.

v2 classifies the day from a derived indicator and gates on a HEARTBEAT instead. These tests are
built on the REAL 2026-08-03..12 census counts, so the fixtures are measurements rather than an
author's idea of what the data looks like, and each clause has its own isolating case (NF-D17).
"""
from __future__ import annotations

import pytest

from report_e11_24_wake_census import (
    BUILD_CROSSCHECK,
    BUILD_INDICATOR,
    HEARTBEAT_FAMILIES,
    classify_gate0,
)

# ── The real census, 2026-08-03..12 (uv run python scripts/report_e11_24_wake_census.py) ──
# ⚠️ TOTAL is the day's REAL total executions from the census, not a sum of the four families
# modelled here — a fixture that does not reproduce the measured totals is a fictional dataset,
# and the first cut of this file silently tested one (its 08-10 total came out 1,082 against a
# measured 1,504, which inverted the volume-band assertion below).
_REAL = {                      # day: (TOTAL, weather_slate, signals_consumer, matchup, player)
    "2026-08-03": (1536, 0, 2, 10, 11),
    "2026-08-04": (1793, 0, 2, 10, 10),
    "2026-08-05": (3480, 5, 33, 10, 11),   # build
    "2026-08-06": (2184, 0, 2, 10, 11),
    "2026-08-07": (1712, 0, 2, 10, 11),
    "2026-08-08": (3172, 5, 33, 10, 11),   # build
    "2026-08-09": (3163, 5, 33, 13, 14),   # build
    "2026-08-10": (1504, 0, 2, 10, 11),    # #675 flip day
    "2026-08-11": (2531, 5, 33, 9, 9),     # build — INC-42 freeze day, contaminated
    "2026-08-12": (1434, 0, 2, 10, 11),    # the day v1 failed (1,434 < v1's 1,536 floor)
}


def _rows(table=None):
    """Expand to (day, family, execs) rows, with a `rest` family absorbing the balance so each
    day's summed executions equal the measured total."""
    table = table or _REAL
    out = []
    for day, (total, weather, consumer, matchup, player) in table.items():
        named = weather + consumer + (matchup or 0) + (player or 0)
        out.append((day, "other", total - named))
        if weather:
            out.append((day, BUILD_INDICATOR, weather))
        out.append((day, BUILD_CROSSCHECK, consumer))
        if matchup is not None:
            out.append((day, "4 matchup posteriors", matchup))
        if player is not None:
            out.append((day, "4 player posteriors", player))
    return out


def _by_day(result):
    return {str(r["day"]): r for r in result}


# ────────────────────────────────────────────────────────────────────────────────
# 1. Classification — derived from the data, not the calendar
# ────────────────────────────────────────────────────────────────────────────────
def test_build_days_are_derived_from_two_agreeing_indicators():
    got = _by_day(classify_gate0(_rows()))
    build = {d for d, r in got.items() if r["class"] == "BUILD"}
    assert build == {"2026-08-05", "2026-08-08", "2026-08-09", "2026-08-11"}
    assert all(got[d]["class"] == "NON-BUILD" for d in
               ("2026-08-03", "2026-08-04", "2026-08-06", "2026-08-07",
                "2026-08-10", "2026-08-12"))


def test_the_two_indicators_disagreeing_makes_the_day_UNVERIFIED_not_a_guess():
    """The partition is only trustworthy while its two independent signals agree."""
    t = dict(_REAL)
    t["2026-08-12"] = (1434, 5, 2, 10, 11)      # weather says build, consumer says not
    r = _by_day(classify_gate0(_rows(t)))["2026-08-12"]
    assert r["class"] == "UNKNOWN"
    assert r["verdict"] == "UNVERIFIED"
    assert any("disagree" in n for n in r["notes"])


# ────────────────────────────────────────────────────────────────────────────────
# 2. ⭐ The confound v2 exists to remove
# ────────────────────────────────────────────────────────────────────────────────
def test_the_day_gate0_v1_failed_now_passes():
    """08-12: 1,434 executions (below v1's 1,536 floor) but every family normal."""
    r = _by_day(classify_gate0(_rows()))["2026-08-12"]
    assert r["verdict"] == "PASS", r["notes"]
    assert r["class"] == "NON-BUILD"


def test_a_lever_landing_must_not_trip_the_gate():
    """⭐ The whole point. Halve `other` — as deleting statements does — heartbeat intact."""
    t = dict(_REAL)
    t["2026-08-12"] = (500, 0, 2, 10, 11)       # executions collapse, pipeline healthy
    r = _by_day(classify_gate0(_rows(t)))["2026-08-12"]
    assert r["verdict"] == "PASS", (
        "a gate that fires because the levers worked is not a gate — v2 must read the "
        "heartbeat, never the volume"
    )


def test_volume_band_is_reported_as_context_but_is_never_the_verdict():
    got = _by_day(classify_gate0(_rows()))
    assert got["2026-08-12"]["volume_band"] is not None       # reported…
    lo, _hi = got["2026-08-12"]["volume_band"]
    assert got["2026-08-12"]["executions"] < lo               # …and violated…
    assert got["2026-08-12"]["verdict"] == "PASS"             # …without failing the day


# ────────────────────────────────────────────────────────────────────────────────
# 3. The gate must still be able to FAIL — and must never pass on nothing
# ────────────────────────────────────────────────────────────────────────────────
def test_an_absent_heartbeat_family_is_UNVERIFIED_never_healthy():
    """NF1.7(a): an absent heartbeat is the outage signature this gate exists to catch."""
    t = dict(_REAL)
    t["2026-08-12"] = (1434, 0, 2, None, 11)    # the matchup writer never ran
    r = _by_day(classify_gate0(_rows(t)))["2026-08-12"]
    assert r["verdict"] == "UNVERIFIED"
    assert any("ABSENT" in n for n in r["notes"])


def test_a_collapsed_heartbeat_FAILS():
    """A real outage suppresses invocations wholesale — that must still be caught."""
    t = dict(_REAL)
    t["2026-08-12"] = (1434, 0, 2, 3, 11)       # matchup ran 3x instead of ~10
    r = _by_day(classify_gate0(_rows(t)))["2026-08-12"]
    assert r["verdict"] == "FAIL"
    assert any("below floor" in n for n in r["notes"])


def test_a_single_extra_or_missing_invocation_does_NOT_fail():
    """⭐ The floor is one-sided and tolerant on purpose.

    The first cut used a two-sided min/max over 2-5 peers, which FAILED 08-04 on `player=10`
    against a (11,11) range — a monitor that fires on ±1 gets muted, and an outage does not
    shave one invocation off, it removes them.
    """
    got = _by_day(classify_gate0(_rows()))
    assert got["2026-08-04"]["verdict"] == "PASS", got["2026-08-04"]["notes"]   # player 10 vs 11
    assert got["2026-08-09"]["verdict"] == "PASS", got["2026-08-09"]["notes"]   # 13/14 vs 10/11


def test_the_gate_is_not_vacuous_on_the_real_data():
    """A gate nothing can fail is not a gate — prove the real window contains a real verdict."""
    verdicts = {r["verdict"] for r in classify_gate0(_rows())}
    assert verdicts <= {"PASS", "FAIL", "UNVERIFIED"}
    assert "PASS" in verdicts, "the gate returned no PASS on a window of healthy days"


# ────────────────────────────────────────────────────────────────────────────────
# 4. Contaminated days must not widen the reference and mask a real failure
# ────────────────────────────────────────────────────────────────────────────────
def test_a_contaminated_day_is_excluded_from_the_reference_range():
    """08-11 (INC-42 freeze) ran matchup=9. If it seeded the range, a later 9 would pass."""
    got = _by_day(classify_gate0(_rows()))
    assert got["2026-08-11"]["contaminated"] is True

    # Asserted DIRECTLY on the reference the gate builds, not via a verdict flip: the peer
    # median is robust enough that 08-11's depressed 9s do not move it, so a verdict-based
    # check here would pass for the wrong reason and prove nothing about exclusion.
    t = dict(_REAL)
    t["2026-08-13"] = (3200, 5, 33, 10, 11)     # a fresh BUILD day
    band = _by_day(classify_gate0(_rows(t)))["2026-08-13"]["volume_band"]
    assert band == (3163, 3480), (
        f"BUILD reference band is {band}; it must come from 08-05/08/09 only. A band reaching "
        f"down to 2531 means the contaminated INC-42 freeze day seeded the reference."
    )


def test_contaminated_days_are_still_reported_not_hidden():
    got = _by_day(classify_gate0(_rows()))
    assert got["2026-08-11"]["executions"] == 2531   # the measured total, still reported


# ────────────────────────────────────────────────────────────────────────────────
# 5. The heartbeat set is a deliberate choice, not an accident
# ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lever_family", [
    "6a umpire chain",          # lever 6a
    "1b int_bullpen_ali",       # lever 1b
    "6 lineup/starter CTAS",    # #675 / #662
    "4b scd2 signal writers",   # target 4
])
def test_no_lever_target_is_in_the_heartbeat(lever_family):
    """A family a lever moves ON PURPOSE cannot also be the normality signal."""
    assert lever_family not in HEARTBEAT_FAMILIES
