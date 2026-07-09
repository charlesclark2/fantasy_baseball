"""test_props_force_recent.py — the --force-recent N window math for the K-prop backfill.

--force-recent N re-pulls the last N calendar days (inclusive of today) even when their S3
partitions already exist, so the daily historical backfill overwrites the thin end-of-day file
the LIVE cron leaves behind (the sparse-recent-date bug: 7/2–7/8 stuck at 1–7 of ~30 pitchers).
Pure boundary math — no S3/API — so it runs in the fast gate.
"""

from __future__ import annotations

from datetime import date

from scripts.backfill_multisport_props_to_s3 import _force_recent_cutoff

_TODAY = date(2026, 7, 9)


def test_unset_or_nonpositive_means_no_forcing():
    assert _force_recent_cutoff(_TODAY, None) is None
    assert _force_recent_cutoff(_TODAY, 0) is None
    assert _force_recent_cutoff(_TODAY, -1) is None


def test_n1_forces_today_only():
    assert _force_recent_cutoff(_TODAY, 1) == date(2026, 7, 9)


def test_n2_forces_today_and_yesterday():
    assert _force_recent_cutoff(_TODAY, 2) == date(2026, 7, 8)


def test_n3_window():
    assert _force_recent_cutoff(_TODAY, 3) == date(2026, 7, 7)


def test_window_membership_matches_run_backfill_predicate():
    # Mirrors the `recent_cutoff <= d <= today` gate used in run_backfill.
    cutoff = _force_recent_cutoff(_TODAY, 2)
    forced = [d for d in (date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9))
              if cutoff <= d <= _TODAY]
    assert forced == [date(2026, 7, 8), date(2026, 7, 9)]  # exactly the last 2 days
