"""E7.6 — MiLB as-of leakage screen guards.

Fast-gate only: pure-function tests over SYNTHETIC comparison rows, no DuckDB, no S3, no
`pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).
`classify_side` is the entire decision surface; the live SQL queries are integration-only
(exercised for real on the box per the runtime gate — CI mocks all IO).
"""
from __future__ import annotations

from betting_ml.scripts.milb_mle.check_milb_leakage_screen import classify_side


def _row(player_id="p1", level="Triple-A", served_pa=0.0, all_time_pa=0.0,
         recomputed_pre_debut_pa=0.0) -> dict:
    return {
        "player_id": player_id,
        "level": level,
        "served_pa": served_pa,
        "all_time_pa": all_time_pa,
        "recomputed_pre_debut_pa": recomputed_pre_debut_pa,
    }


def test_no_rows_is_unevaluable_not_a_pass():
    state, messages, stats = classify_side([])
    assert state == "UNEVALUABLE"
    assert stats == {"n_rows": 0, "n_opportunities": 0, "n_violations": 0}
    assert messages


def test_no_post_debut_games_anywhere_is_unevaluable():
    # every row's all-time PA equals its pre-debut PA — no player ever had a post-debut game at
    # that level, so the screen had ZERO opportunity to catch a leak this pass.
    rows = [
        _row("p1", served_pa=200, all_time_pa=200, recomputed_pre_debut_pa=200),
        _row("p2", served_pa=50, all_time_pa=50, recomputed_pre_debut_pa=50),
    ]
    state, messages, stats = classify_side(rows)
    assert state == "UNEVALUABLE"
    assert stats["n_opportunities"] == 0
    assert stats["n_violations"] == 0
    assert messages


def test_served_matches_pre_debut_with_a_real_opportunity_is_verified():
    # p1 has a rehab-assignment style post-debut game at this level (all_time > pre_debut), but
    # the served value correctly excludes it — this is the case the screen exists to confirm.
    rows = [
        _row("p1", served_pa=200, all_time_pa=230, recomputed_pre_debut_pa=200),
        _row("p2", served_pa=50, all_time_pa=50, recomputed_pre_debut_pa=50),
    ]
    state, messages, stats = classify_side(rows)
    assert state == "VERIFIED"
    assert stats["n_opportunities"] == 1
    assert stats["n_violations"] == 0
    assert messages == []


def test_served_exceeding_pre_debut_is_leak_detected():
    # p1's served minor_pa (230) exceeds what pre-debut games alone could produce (200) — a
    # post-debut game's PA reached the served aggregate.
    rows = [
        _row("p1", served_pa=230, all_time_pa=230, recomputed_pre_debut_pa=200),
        _row("p2", served_pa=50, all_time_pa=50, recomputed_pre_debut_pa=50),
    ]
    state, messages, stats = classify_side(rows)
    assert state == "LEAK_DETECTED"
    assert stats["n_violations"] == 1
    assert any("p1" in m for m in messages)


def test_leak_takes_precedence_over_unevaluable_opportunity_count():
    # a leak on one row still reports LEAK_DETECTED even if it happens to be the only "opportunity"
    # row — the violation itself IS the opportunity that was missed.
    rows = [_row("p1", served_pa=210, all_time_pa=230, recomputed_pre_debut_pa=200)]
    state, messages, stats = classify_side(rows)
    assert state == "LEAK_DETECTED"
    assert stats["n_opportunities"] == 1


def test_epsilon_tolerance_absorbs_floating_point_noise():
    # served exceeds recomputed by less than epsilon — not a leak, just float noise from the
    # weighted-average pipeline upstream.
    rows = [_row("p1", served_pa=200.0000001, all_time_pa=230, recomputed_pre_debut_pa=200.0)]
    state, _, stats = classify_side(rows, epsilon=1e-4)
    assert state != "LEAK_DETECTED"
    assert stats["n_violations"] == 0


def test_a_ten_violation_cap_still_reports_the_overflow_count():
    rows = [
        _row(f"p{i}", served_pa=101 + i, all_time_pa=101 + i, recomputed_pre_debut_pa=100)
        for i in range(15)
    ]
    state, messages, stats = classify_side(rows)
    assert state == "LEAK_DETECTED"
    assert stats["n_violations"] == 15
    assert len(messages) == 11  # 10 detailed + 1 overflow line
    assert "5 more" in messages[-1]
