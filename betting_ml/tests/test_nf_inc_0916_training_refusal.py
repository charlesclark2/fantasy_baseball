"""NF-INC-0916 node 2 — CLASS CLOSURE AT THE INSTRUMENT.

⛔ THE MECHANISM, stated once so every clause below is legible. `attach_labels` LEFT-joins the stat
feed onto the roster spine and RETAINS every non-match as `fantasy_points = 0.0`. That convention is
CORRECT and is not repealed here: a player who dressed, played and scored nothing is a true zero and
the model should learn him. What it cannot distinguish on its own is a week for which NO stat line
was ever joined — every row a fabricated zero — and that is what the weekly model trained on.

⭐ TWO GATES, TWO SUBSTRATES, ON PURPOSE:
  * `assert_training_stat_coverage` reads the FRAME (`_has_stat_row`) — the direct evidence.
  * `assert_stat_vintage_reaches_training` reads the MANIFEST — the artifact a human and the
    freshness monitor actually see, and the one on which this incident was provable from the start
    (`stats_as_of: "2025-W18"` beside `train_through: 2026 wk 1`, both computed correctly, nothing
    comparing them).
A change that fixed one substrate and not the other still cannot publish quietly.

⚠️ THE LOAD-BEARING TWO-SIDED CLAUSE IS `test_the_retained_zero_convention_is_not_repealed`. It is
easy to write a gate that refuses "too many zeros" and thereby refuses a legitimately low-scoring
week — which would be a worse defect than the one being fixed, because it would refuse to publish
rather than publish something wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS

TARGET = WS.TargetWeek(season=2026, week=2, first_kickoff=pd.Timestamp("2026-09-17T00:20:00Z"),
                       last_reg_week=18)


def _frame(rows):
    """A minimal frame carrying exactly the columns the coverage gate reads."""
    return pd.DataFrame(rows, columns=["season", "week", "_has_game", "_has_stat_row",
                                       "fantasy_points"])


def _week(season, week, *, n, covered, has_game=True, points=1.0):
    return [(season, week, has_game, i < covered, points) for i in range(n)]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — THE FRAME-SIDE GATE
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_it_refuses_a_training_week_whose_stat_line_never_landed():
    """The incident itself: a training week with 500 rows that had a game and not one stat row."""
    frame = _frame(_week(2026, 1, n=500, covered=0))
    with pytest.raises(WS.WeeklyServingError) as exc:
        WS.assert_training_stat_coverage(frame, target=TARGET)
    msg = str(exc.value)
    assert "2026 wk 1" in msg
    assert "NF-INC-0916" in msg


def test_the_refusal_names_the_two_manifest_fields_that_gave_it_away():
    """⭐ A refusal that does not name the evidence sends the next reader to re-derive it. These two
    fields were sitting in the published manifest for the whole incident."""
    frame = _frame(_week(2026, 1, n=500, covered=0))
    vintage = {"stats_as_of": "2025-W18", "train_through_season": 2026, "train_through_week": 1}
    with pytest.raises(WS.WeeklyServingError) as exc:
        WS.assert_training_stat_coverage(frame, target=TARGET, vintage=vintage)
    msg = str(exc.value)
    assert "2025-W18" in msg and "train_through" in msg


def test_a_healthy_week_passes_at_the_measured_coverage_level():
    """The other side. Measured over 2016-2026 the healthy band is 0.4157-0.7377 with a median of
    ~0.68; a gate that refused that would be an outage, not a fix."""
    frame = _frame(_week(2025, 18, n=500, covered=345))    # 0.69 — the measured median
    out = WS.assert_training_stat_coverage(frame, target=TARGET)
    assert out["n_weeks_checked"] == 1
    assert out["min_coverage"] == pytest.approx(0.69)


def test_the_retained_zero_convention_is_not_repealed():
    """⭐⭐ THE CLAUSE THAT KEEPS THIS GATE HONEST.

    A week in which every player is COVERED (each matched a real stat line) but every one scored
    0.0 is a legitimate — if absurd — week, and it must pass. The gate keys on whether a stat line
    was JOINED, never on the value that came back. A gate that refused "too many zeros" would
    refuse to publish a real low-scoring week, which is a worse failure than the one being fixed.
    """
    frame = _frame(_week(2025, 18, n=400, covered=400, points=0.0))
    out = WS.assert_training_stat_coverage(frame, target=TARGET)
    assert out["min_coverage"] == 1.0

    # …and the mirror image: every row scores WELL but none was ever joined. Same zero-count as a
    # healthy week would have, and it must still be refused.
    fabricated = _frame(_week(2025, 18, n=400, covered=0, points=9.9))
    with pytest.raises(WS.WeeklyServingError):
        WS.assert_training_stat_coverage(fabricated, target=TARGET)


def test_byes_are_excluded_from_coverage():
    """A bye has no stat line BY DEFINITION, so counting byes against coverage would make the
    gate's reading depend on how many teams were off that week — a number with nothing to do with
    whether the feed landed."""
    rows = _week(2025, 18, n=300, covered=207) + _week(2025, 18, n=200, covered=0, has_game=False)
    out = WS.assert_training_stat_coverage(_frame(rows), target=TARGET)
    assert out["min_coverage"] == pytest.approx(0.69), (
        "the bye rows dragged the coverage down — they are not evidence about the feed"
    )


def test_the_target_week_is_not_judged():
    """The target week legitimately has NO outcome — that is the whole point of projecting it.
    Measured live: 2026 wk 2 carried 500 rows with a game and 0.0000 coverage, correctly, because
    it had not been played. A gate that judged it would refuse every build there has ever been."""
    rows = _week(2025, 18, n=400, covered=276) + _week(2026, 2, n=500, covered=0)
    out = WS.assert_training_stat_coverage(_frame(rows), target=TARGET)
    assert out["n_weeks_checked"] == 1


def test_it_refuses_an_empty_examination():
    """NF1.7(a) — a gate that inspected nothing has not passed, and this incident is what a year of
    green runs examining nothing looks like."""
    with pytest.raises(WS.WeeklyServingError, match="ZERO weeks"):
        WS.assert_training_stat_coverage(_frame([]), target=TARGET)


def test_it_refuses_a_frame_that_lost_its_coverage_columns():
    """An UNEVALUABLE gate is not a passing gate. A frame without `_has_stat_row` would otherwise
    make every clause above silently vacuous."""
    bare = pd.DataFrame({"season": [2025], "week": [18]})
    with pytest.raises(WS.WeeklyServingError, match="cannot be evaluated"):
        WS.assert_training_stat_coverage(bare, target=TARGET)


def test_the_floor_sits_below_every_week_in_the_measured_history():
    """A recorded MEASUREMENT, not a preference — and the measurement overturned the instinctive
    choice. Built through the real code path over 2016-2026 (216 weeks, byes excluded): the worst
    healthy week is 2016 wk 1 at 0.4157, and a 0.50 floor would have refused it."""
    worst_healthy_week = 0.4157
    assert WS.TRAIN_STAT_COVERAGE_FLOOR < worst_healthy_week, (
        f"the floor {WS.TRAIN_STAT_COVERAGE_FLOOR} is at or above the worst healthy week ever "
        f"measured ({worst_healthy_week}) — it would refuse to publish on real historical data"
    )
    assert WS.TRAIN_STAT_COVERAGE_FLOOR > 0.0, (
        "a floor of zero is satisfied by the defect itself (measured 0.0000) — it would pass on "
        "exactly the week this gate exists to refuse"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — THE MANIFEST-SIDE GATE, driven with the EXACT historical state
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_manifest_gate_fires_on_the_exact_state_the_incident_published():
    """`stats_as_of: "2025-W18"` beside `train_through: 2026 wk 1` — the pair that sat in the
    published manifest for the whole incident with nothing comparing the two fields."""
    with pytest.raises(WS.WeeklyServingError) as exc:
        WS.assert_stat_vintage_reaches_training(
            {"stats_as_of": "2025-W18", "train_through_season": 2026, "train_through_week": 1})
    msg = str(exc.value)
    assert "2025-W18" in msg and "2026 wk 1" in msg


@pytest.mark.parametrize("stats_as_of, tt", [
    ("2026-W1", (2026, 1)),     # the feed reaches exactly the training boundary — healthy
    ("2026-W2", (2026, 1)),     # the feed is AHEAD of training — healthy (the target is excluded)
    ("2025-W22", (2025, 18)),   # a prior season, consistent
])
def test_the_manifest_gate_passes_a_consistent_pair(stats_as_of, tt):
    out = WS.assert_stat_vintage_reaches_training(
        {"stats_as_of": stats_as_of, "train_through_season": tt[0], "train_through_week": tt[1]})
    assert out["evaluable"] is True


@pytest.mark.parametrize("vintage", [
    {"stats_as_of": None, "train_through_season": 2026, "train_through_week": 1},
    {"stats_as_of": "garbage", "train_through_season": 2026, "train_through_week": 1},
    {"stats_as_of": "2026-W1", "train_through_season": None, "train_through_week": None},
])
def test_an_unparseable_pair_is_reported_unevaluable_rather_than_passed(vintage):
    """⚠️ It is SILENT, not healthy — and that is defensible only because the frame-side gate covers
    the same defect. The report says `evaluable: False` so a reader can tell the difference."""
    out = WS.assert_stat_vintage_reaches_training(vintage)
    assert out["evaluable"] is False


def test_the_vintage_parser_reads_the_served_shape_and_refuses_the_rest():
    assert WS.stat_vintage_tuple("2025-W18") == (2025, 18)
    assert WS.stat_vintage_tuple("2026-W1") == (2026, 1)
    for bad in (None, "", "2026", "2026-Wx", 2026, "W18"):
        assert WS.stat_vintage_tuple(bad) is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — BOTH GATES ARE ACTUALLY INVOKED (wired ≠ invoked — NF-C0e)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_build_invokes_both_refusals():
    """⛔ A gate defined and never called is the NF-C0e defect: the name appears in the profile, the
    catalogue and the export map, and nothing computes it. Read on comment-stripped source so this
    file's own prose cannot satisfy it (INC-38)."""
    import re
    from pathlib import Path

    import quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving as R

    src = Path(R.__file__).read_text()
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    for call in ("WS.assert_training_stat_coverage(", "WS.assert_stat_vintage_reaches_training("):
        assert call in src, f"the build never calls {call!r} — it is wired but not invoked"


def test_the_coverage_refusal_runs_before_the_fit():
    """⭐ ORDER MATTERS FOR A REASON BEYOND CORRECTNESS: the fit is the nine-minute step, and there
    is nothing to learn from a week of fabricated zeros except a wrong P(zero). Refusing after the
    fit would burn the run and reach the same verdict."""
    import re
    from pathlib import Path

    import quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving as R

    src = re.sub(r"^\s*#.*$", "", Path(R.__file__).read_text(), flags=re.M)
    assert src.index("WS.assert_training_stat_coverage(") < src.index("WS.fit_and_predict("), (
        "the stat-coverage refusal runs AFTER the fit — the run would spend nine minutes learning "
        "from fabricated labels before refusing"
    )
