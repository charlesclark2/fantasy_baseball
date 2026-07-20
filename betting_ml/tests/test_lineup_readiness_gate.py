"""INC-32 (2026-07-19) — per-game lineup-readiness gate.

Guards select_ready_games (scripts/lineup_monitor.py): a post_lineup re-score must NOT fire on
a partially-posted batting order (the 0.811-coverage race — a partial first attempt was frozen
one-and-done). A game is READY only when BOTH sides carry a complete 9-slot order, EXCEPT the
SLA safety valve: a still-incomplete lineup within _SLA_FALLBACK_MINUTES of first pitch scores
best-effort so the readiness gate can never blow the Epic A1 30-min SLA.

Pure logic, no IO — belongs in the fast gate.
"""
from datetime import datetime, timedelta, timezone

from scripts.lineup_monitor import (
    _FULL_LINEUP_SLOTS,
    _SLA_FALLBACK_MINUTES,
    is_real_pitcher_change,
    select_ready_games,
)

NOW = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)
FAR = NOW + timedelta(hours=3)      # well outside the SLA window
NEAR = NOW + timedelta(minutes=20)  # inside the SLA window


def _cand(home, away, filled):
    return {"home": home, "away": away, "min_slots_filled": filled}


def test_complete_lineup_is_ready():
    cands = {111: _cand(1, 2, _FULL_LINEUP_SLOTS)}
    ready, held = select_ready_games(cands, {111: FAR}, NOW)
    assert ready == {111: (1, 2)}
    assert held == []


def test_partial_lineup_is_held_far_from_first_pitch():
    # 5/9 slots, first pitch 3h out → HELD (retry next tick), NOT scored.
    cands = {222: _cand(3, 4, 5)}
    ready, held = select_ready_games(cands, {222: FAR}, NOW)
    assert ready == {}
    assert len(held) == 1
    pk, filled, reason = held[0]
    assert pk == 222 and filled == 5
    assert reason.startswith("held")


def test_partial_lineup_scores_best_effort_inside_sla_window():
    # 5/9 slots but first pitch 20 min out → SLA fallback: score best-effort so we don't
    # miss the Epic A1 deadline. Still recorded in `held` (with an SLA-fallback reason) so the
    # monitor can page.
    cands = {333: _cand(5, 6, 5)}
    ready, held = select_ready_games(cands, {333: NEAR}, NOW)
    assert ready == {333: (5, 6)}
    assert len(held) == 1
    assert held[0][2].startswith("SLA-fallback")


def test_missing_first_pitch_holds_incomplete_game():
    # No first-pitch known (lakehouse miss) → fail-open to the completeness gate: an incomplete
    # game is HELD, never blindly SLA-fallback-scored.
    cands = {444: _cand(7, 8, 3)}
    ready, held = select_ready_games(cands, {}, NOW)
    assert ready == {}
    assert held[0][0] == 444


def test_sla_boundary_is_inclusive():
    exactly = NOW + timedelta(minutes=_SLA_FALLBACK_MINUTES)
    cands = {555: _cand(9, 10, 4)}
    ready, _ = select_ready_games(cands, {555: exactly}, NOW)
    assert 555 in ready


def test_mixed_slate_partitions_correctly():
    cands = {
        1: _cand(1, 2, 9),   # complete → ready
        2: _cand(3, 4, 4),   # partial, far → held
        3: _cand(5, 6, 2),   # partial, near → sla-fallback ready
        4: _cand(7, 8, 9),   # complete → ready
    }
    fp = {1: FAR, 2: FAR, 3: NEAR, 4: FAR}
    ready, held = select_ready_games(cands, fp, NOW)
    assert set(ready) == {1, 3, 4}
    assert {h[0] for h in held} == {2, 3}  # game 3 is both ready (scored) and logged as fallback


def test_none_slot_count_treated_as_zero():
    # A NULL min_slots_filled (defensive) is treated as 0 → held far from first pitch.
    cands = {666: {"home": 1, "away": 2, "min_slots_filled": None}}
    ready, held = select_ready_games(cands, {666: FAR}, NOW)
    assert ready == {}
    assert held[0][0] == 666


# ── is_real_pitcher_change — the 823523 flip-flop guard ──────────────────────────
def test_real_starter_change_is_detected():
    assert is_real_pitcher_change((100, 200), (100, 999)) is True   # away starter scratched
    assert is_real_pitcher_change((100, 200), (111, 200)) is True   # home starter scratched


def test_no_change_is_not_a_change():
    assert is_real_pitcher_change((100, 200), (100, 200)) is False


def test_type_mismatch_is_not_a_change():
    # stored INT vs a str/Decimal staging read of the SAME id must NOT read as a change
    # (the verbatim `!=` flip-flop that re-triggered 823523 every tick).
    from decimal import Decimal
    assert is_real_pitcher_change((100, 200), ("100", "200")) is False
    assert is_real_pitcher_change((100, 200), (Decimal("100"), Decimal("200"))) is False


def test_null_current_probable_is_not_a_change():
    # A transient LEFT-JOIN gap (current probable comes back None) is a data gap, not a scratch —
    # must not churn a re-score.
    assert is_real_pitcher_change((100, 200), (100, None)) is False
    assert is_real_pitcher_change((100, 200), (None, None)) is False


def test_null_stored_waits_rather_than_churns():
    # Pre-migration / not-yet-populated stored starters → wait (no re-trigger).
    assert is_real_pitcher_change((None, 200), (100, 999)) is False
    assert is_real_pitcher_change((None, None), (100, 200)) is False
