"""30.13 freshness gate × historical re-scores (2026-07-15).

The serve-time freshness gate asserts TODAY's serving-path blocks were rebuilt from
TODAY's ingestion — a live-serve invariant. For a HISTORICAL slate the EB build date can
never equal the game date, so an un-skipped gate abstains every past-date re-score
(observed: the 07-03→07-12 degraded-window correction had all 13 games forced to
sigma_tier='abstain', edge/Kelly nulled) while protecting nothing — the games are over.

The skip must key on BOTH escape hatches:
  * is_backfill (the original 30.7 skip), AND
  * target_date < today via the INC-22 game-day clock (the correction re-scores run
    post_lineup --lineup-confirmed WITHOUT --is-backfill, deliberately — backfill rows
    carry a user-facing indication the correction must not inherit).

Source-inspection (the predicate lives inline in main(); importing/mocking a full scoring
run is not fast-gate material).
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "scripts" / "predict_today.py").read_text()


def test_gate_skips_any_past_date_not_just_backfill():
    m = re.search(r"_is_historical_rescore\s*=\s*str\(target_date\)\[:10\]\s*<\s*current_game_date_iso\(\)", SRC)
    assert m, (
        "the 30.13 gate lost its historical-date skip — any past-date re-score "
        "(e.g. a degraded-window correction WITHOUT --is-backfill) would have every "
        "game abstained by a build-date-vs-game-date comparison that can never pass."
    )
    assert re.search(r"if\s+not\s+is_backfill\s+and\s+not\s+_is_historical_rescore:\s*\n\s*"
                     r"serving_stale, _serving_stale_reason = _serving_freshness_stale", SRC), (
        "_serving_freshness_stale must be called ONLY for a live (today, non-backfill) "
        "serve — both escape hatches are load-bearing."
    )


def test_historical_skip_uses_the_game_day_clock_not_utc():
    """INC-22: 'today' on the box is the US baseball-day, never date.today()/utcnow —
    a UTC 'today' rolls over at ~5pm PT and would mis-classify tonight's live serve as
    historical (silently disabling the gate for the evening slate)."""
    seg = SRC[SRC.find("_is_historical_rescore"):SRC.find("_is_historical_rescore") + 400]
    assert "current_game_date_iso()" in seg
    assert "date.today()" not in seg and "utcnow" not in seg
