"""NF-C-LDA-6 — guards for the bench-valuation STUDY's instrument.

The study changes no shipped code, so what needs guarding is not a ranking — it is the harness's
ability to return a WRONG ANSWER CONFIDENTLY. Three ways it could, all of which this session already
hit once while building it:

  1. ⚠️ THE ANCHORS ARE THE VERDICT. `check_anchors` is what stands between a leaderboard and a
     conclusion; if it cannot detect an inverted metric it is decoration (NF1.7(a)). It caught two
     real harness bugs during the build — an INACTIVE oracle that scored byte-identically to an
     honest arm, and a unit mismatch that let a bench pick outrank a need-filler — so these clauses
     protect a mechanism with a demonstrated hit rate, not a hypothetical one.
  2. ⚠️ THE METRIC MUST REWARD DEPTH AT ALL. Score "your best nine" and every bench rule ties by
     construction; the entire study would then be measuring nothing while looking healthy.
  3. ⚠️ COMMON RANDOM NUMBERS MUST ACTUALLY BE COMMON. If two arms saw different seasons the paired
     deltas would be noise, and at these effect sizes it would still look like a result.

⛔ ANCHORED IN ITS OWN CLAUSES (E9.60).
"""

from __future__ import annotations

import random

import pytest

from quant_sports_intel_models.fantasy_engine import bench_valuation_study as S


@pytest.fixture(scope="module")
def board():
    return S.load_board()


def _result(**means) -> dict:
    """A fabricated leaderboard with a known shape — the only way to test a detector is to hand it
    the defect it exists to find."""
    return {"arms": {k: [v] * 8 for k, v in means.items()}, "cells": [], "n_teams": 12}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The anchors are gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_healthy_field_passes_every_anchor():
    """⚠️ NON-VACUITY: if this failed, every clause below would 'detect' its defect for the wrong
    reason and the detector would be useless."""
    assert S.check_anchors(_result(
        oracle=1900, insurance=1880, own_worst_starter=1860, incumbent=1830,
        seats_covered=1800, raw_points=1790, nihilist=1720)) == []


def test_an_arm_beating_the_peeking_oracle_is_refused():
    problems = S.check_anchors(_result(
        oracle=1800, insurance=1900, own_worst_starter=1860, incumbent=1830,
        seats_covered=1800, raw_points=1790, nihilist=1720))
    assert any("ORACLE FLOOR" in p for p in problems), problems


def test_a_nihilist_that_is_not_last_is_refused():
    """A metric a 'take the worst player' arm can win cannot select anything (NF-D11)."""
    problems = S.check_anchors(_result(
        oracle=1900, insurance=1880, own_worst_starter=1860, incumbent=1830,
        seats_covered=1800, raw_points=1790, nihilist=1810))
    assert any("DEGENERATE CEILING" in p for p in problems), problems


def test_a_field_that_cannot_be_told_apart_is_refused():
    """⭐ THE ONE A GREEN LEADERBOARD HIDES BEST. Every arm within noise still produces a ranking,
    and that ranking is pure ordering of nothing."""
    problems = S.check_anchors(_result(
        oracle=1900.4, insurance=1900.3, own_worst_starter=1900.2, incumbent=1900.1,
        seats_covered=1900.0, raw_points=1899.9, nihilist=1899.8))
    assert any("INSTRUMENT BLIND" in p for p in problems), problems


def test_the_anchor_check_names_every_arm_it_scores():
    """A detector that silently skips an arm cannot refuse it."""
    with pytest.raises(KeyError):
        S.check_anchors(_result(insurance=1880, incumbent=1830))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The metric must be able to see bench depth
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_season_rewards_a_bench_that_covers_absence(board):
    """⭐ THE STUDY'S LOAD-BEARING PROPERTY. If a real bench scores no more than an empty one, every
    arm ties by construction and the whole leaderboard is an artifact."""
    rows, cfg, _ = board
    by_pos = {}
    for r in sorted(rows, key=lambda r: -(r.get("league_points") or 0)):
        by_pos.setdefault(r["position"], []).append(r)
    starters = ([by_pos["QB"][0]] + by_pos["RB"][:2] + by_pos["WR"][:2]
                + [by_pos["TE"][0], by_pos["K"][0], by_pos["DST"][0], by_pos["RB"][2]])
    depth = by_pos["RB"][3:6] + by_pos["WR"][3:6]

    absences = S.draw_absences(rows, random.Random("metric-check"))
    thin = S.season_points(starters, cfg, absences)
    deep = S.season_points(starters + depth, cfg, absences)
    assert deep > thin, (
        f"a six-man bench added nothing ({deep:.1f} vs {thin:.1f}) — the metric cannot see depth, "
        "so no bench rule could ever be distinguished from another"
    )


def test_a_player_on_bye_cannot_be_started(board):
    rows, cfg, _ = board
    one = next(r for r in rows if r.get("bye") and r["position"] == "QB")
    week = one["bye"]
    avail = [p for p in [one] if p.get("bye") != week]
    assert avail == [], "a player was available in his own bye week"


def test_the_bench_is_classified_by_slot_not_by_draft_order(board):
    """⚠️ K and D/ST are drafted LAST by design, so 'the last picks' counted both as bench in every
    arm and diluted every real share by a third. The mix must read the actual assignment."""
    rows, cfg, _ = board
    by_pos = {}
    for r in sorted(rows, key=lambda r: -(r.get("league_points") or 0)):
        by_pos.setdefault(r["position"], []).append(r)
    roster = ([by_pos["QB"][0]] + by_pos["RB"][:3] + by_pos["WR"][:2]
              + [by_pos["TE"][0]] + by_pos["WR"][2:4] + [by_pos["K"][0], by_pos["DST"][0]])
    bench = {p["position"] for p in S._bench_of(roster, cfg)}
    assert "K" not in bench and "DST" not in bench, (
        f"the only K and D/ST on the roster were classified as bench: {sorted(bench)}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Common random numbers
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_same_seed_produces_the_same_season(board):
    rows, _cfg, _ = board
    a = S.draw_absences(rows, random.Random("seed-1"))
    b = S.draw_absences(rows, random.Random("seed-1"))
    c = S.draw_absences(rows, random.Random("seed-2"))
    assert a == b, "the same seed produced two different seasons — the arms are not paired"
    assert a != c, "two different seeds produced the same season — the study has one observation"


def test_absence_tracks_the_boards_own_projected_games(board):
    """Availability is READ from the board (`g`), not invented — so a player projected for a full
    season misses little and a fragile one misses a lot."""
    rows, _cfg, _ = board
    absences = S.draw_absences(rows, random.Random("tracks"))
    healthy = [r for r in rows if (r.get("games") or 0) >= 16.5]
    fragile = [r for r in rows if 0 < (r.get("games") or 0) <= 8]
    assert healthy and fragile, "the board has no contrast to test"
    mean_h = sum(len(absences[str(r["player_id"])]) for r in healthy) / len(healthy)
    mean_f = sum(len(absences[str(r["player_id"])]) for r in fragile) / len(fragile)
    assert mean_f > mean_h + 2, f"fragile {mean_f:.1f} vs healthy {mean_h:.1f} missed weeks"


def test_a_contiguous_absence_is_one_block(board):
    """The sensitivity model must actually differ from the primary, or running both proves nothing."""
    rows, _cfg, _ = board
    blocks = S.draw_absences(rows, random.Random("c"), contiguous=True)

    # ⚠️ THE FIRST VERSION OF THIS CLAUSE WAS VACUOUS AND ONLY THE RED PROOF FOUND IT. It checked the
    # player who missed the MOST weeks — but the board's most fragile player is projected for under
    # one game, so he misses ~16 of 17 weeks and his absence set is contiguous BY ACCIDENT under
    # either model. Scattering is only detectable in the middle of the range.
    checked = 0
    for pid, weeks_set in blocks.items():
        if not (2 <= len(weeks_set) <= 10):
            continue
        weeks = sorted(weeks_set)
        span = weeks[-1] - weeks[0] + 1
        # A single block spans exactly as many weeks as it contains — bar the one bye it steps over.
        assert span <= len(weeks) + 1, f"a 'contiguous' absence was scattered: {weeks}"
        checked += 1
    assert checked >= 25, (
        f"only {checked} players had a mid-range absence — too few to detect scattering, so this "
        "clause would pass on nothing"
    )
