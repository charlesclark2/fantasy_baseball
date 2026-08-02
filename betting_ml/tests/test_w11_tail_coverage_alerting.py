"""INC-37 — the paging decision for the W11 serving-tail guard (betting_ml.monitoring.w11_tail_coverage).

The check itself (scripts/check_w11_tail_coverage.py, tested in test_w11_tail_coverage.py) is a
three-way discrimination; this module is the layer that decides WHICH of those verdicts is worth
waking someone for, and on WHICH slate each block is allowed to be judged.

Two things must both hold or the monitor is worthless:

  1. BUILD_GAP pages CRITICAL — the INC-37 fingerprint (the raw feed HAS the slate, the built
     feature table does not ⇒ the W11 tail was built on a stale game universe). On 2026-08-01
     that meant a blank front-end panel while the six-block coverage gate read a healthy 0.878.
  2. It stays SILENT on the normal build cadence. FEED_PENDING is the daily steady state, and —
     the part that is easy to get wrong — umpire and weather CANNOT be judged on the current
     slate at all: their feeds land AFTER the lakehouse_w11_nightly_op build that consumes them
     (measured 2026-08-01 UTC: ingest_weather writes forecast_pregame at 12:50 and
     ingest_umpires.py at 12:0x-16:39, vs the ~12:40 build), so a same-day page on them would
     fire CRITICAL every single morning and the monitor would be muted inside a week.

Fast-gate-safe: pure functions, no IO, no `pipeline` import.
"""

from __future__ import annotations

from betting_ml.monitoring.w11_tail_coverage import (
    ALL_BLOCKS,
    BUILD_LAGGED_BLOCKS,
    SAME_DAY_BLOCKS,
    classify,
    parse_block_coverage,
    parse_block_verdicts,
    parse_evaluated,
)


def _stdout(evaluated: bool = True, **verdicts: str) -> str:
    """Build the script's stdout for a set of block verdicts (n/m is cosmetic here)."""
    lines = [f"[METRIC] w11_tail_evaluated={'1' if evaluated else '0'}"]
    if evaluated:
        lines.append(f"[METRIC] w11_tail_problem_count={sum(1 for v in verdicts.values() if v in ('BUILD_GAP', 'PARTIAL'))}")
        for block, verdict in verdicts.items():
            n = 0 if verdict == "BUILD_GAP" else 15
            lines.append(f"[METRIC] w11_tail_{block}_covered={n}/15 verdict={verdict}")
    return "\n".join(lines) + "\n"


def _all_ok() -> str:
    return _stdout(**{b: "OK" for b in ALL_BLOCKS})


class TestParsers:
    def test_parses_verdicts_and_counts(self):
        out = _stdout(umpire="OK", weather="PARTIAL", public_betting="BUILD_GAP")
        assert parse_block_verdicts(out) == {
            "umpire": "OK", "weather": "PARTIAL", "public_betting": "BUILD_GAP"}
        assert parse_block_coverage(out)["public_betting"] == (0, 15)
        assert parse_evaluated(out) is True

    def test_unevaluated_run_is_distinguishable_from_a_missing_line(self):
        assert parse_evaluated("[METRIC] w11_tail_evaluated=0") is False
        assert parse_evaluated("") is None
        assert parse_block_verdicts("") == {}

    def test_ignores_the_human_readable_table_rows(self):
        """The script prints a `umpire 15 15 0 BUILD_GAP` table above the metrics; only the
        [METRIC] lines are the contract."""
        noisy = "  umpire               15     15        0   BUILD_GAP\n" + _all_ok()
        assert parse_block_verdicts(noisy) == {b: "OK" for b in ALL_BLOCKS}


class TestTheInc37FingerprintPages:
    def test_public_betting_build_gap_today_pages_critical(self):
        """The same-day detector: public_betting_raw is ingested at 12:00, BEFORE the ~12:40 W11
        build, so a zero in the built table is a stale-game-universe defect — exactly what
        happened on 2026-08-01 (240 raw rows for the slate, 0 built)."""
        sev, msg = classify(_stdout(public_betting="BUILD_GAP"), _all_ok())
        assert sev == "CRITICAL"
        assert "BUILD GAP" in msg and "public_betting" in msg

    def test_lagged_block_build_gap_on_the_prior_slate_pages_critical(self):
        """umpire/weather get one build cycle before they are judged; a gap that survives it is
        real."""
        for block in BUILD_LAGGED_BLOCKS:
            sev, msg = classify(_all_ok(), _stdout(**{block: "BUILD_GAP"}))
            assert sev == "CRITICAL", block
            assert block in msg

    def test_partial_pages_warn_not_critical(self):
        sev, _ = classify(_stdout(public_betting="PARTIAL"), _all_ok())
        assert sev == "WARN"

    def test_critical_wins_over_a_concurrent_partial(self):
        sev, msg = classify(_stdout(public_betting="BUILD_GAP"),
                            _stdout(umpire="PARTIAL", weather="OK"))
        assert sev == "CRITICAL"
        assert "PARTIAL" in msg  # both are still reported in the body


class TestItDoesNotCryWolf:
    def test_feed_pending_is_silent(self):
        """The HP-umpire assignment posts in the afternoon; paging on an empty morning block
        every day is how a monitor gets muted (E11.27 / the injury feed-freshness carve-out)."""
        sev, _ = classify(_stdout(public_betting="FEED_PENDING"),
                          _stdout(umpire="FEED_PENDING", weather="FEED_PENDING"))
        assert sev is None

    def test_no_slate_is_silent(self):
        sev, _ = classify(_stdout(public_betting="NO_SLATE"),
                          _stdout(umpire="NO_SLATE", weather="NO_SLATE"))
        assert sev is None

    def test_clean_slate_is_silent(self):
        assert classify(_all_ok(), _all_ok())[0] is None

    def test_the_normal_morning_never_pages(self):
        """⭐ THE REGRESSION THIS EXISTS FOR. On a normal morning the current slate looks like a
        BUILD_GAP for umpire and weather — their feeds land AFTER the build that consumes them —
        while the prior slate is clean. That must be SILENT. A version of this op that judged
        every block on the current slate would page CRITICAL every single day."""
        today = _stdout(public_betting="OK", umpire="BUILD_GAP", weather="BUILD_GAP")
        sev, _ = classify(today, _all_ok())
        assert sev is None

    def test_and_the_mirror_image_still_pages(self):
        """The same-day-blind spot must not become a blanket exemption: a lagged block that is
        still gapped a full cycle later IS a defect."""
        today = _stdout(public_betting="OK", umpire="BUILD_GAP", weather="BUILD_GAP")
        sev, _ = classify(today, _stdout(umpire="BUILD_GAP", weather="OK"))
        assert sev == "CRITICAL"


class TestUnevaluableIsNeverHealthy:
    def test_a_failed_run_pages_warn(self):
        """NF1.7 (a) / spine_horizon: an anchor that fails to evaluate makes its assertion
        vacuously true. WARN, not CRITICAL — "we could not verify" is not "we found a problem"."""
        sev, msg = classify("", _all_ok())
        assert sev == "WARN"
        assert "UNVERIFIED" in msg

    def test_an_evaluated_zero_run_pages_warn(self):
        sev, msg = classify(_stdout(evaluated=False), _all_ok())
        assert sev == "WARN"
        assert "UNVERIFIED" in msg

    def test_a_missing_block_line_is_unverified_not_ok(self):
        """A block the script never reported must not be silently scored healthy."""
        sev, msg = classify(_all_ok(), _stdout(umpire="OK"))  # weather line absent
        assert sev == "WARN"
        assert "weather" in msg

    def test_only_the_leg_that_failed_is_reported_unverified(self):
        _, msg = classify("", _all_ok())
        assert "public_betting" in msg
        for block in BUILD_LAGGED_BLOCKS:
            assert f"{block} (" not in msg


class TestPolicyRegistry:
    def test_every_block_is_judged_on_exactly_one_slate(self):
        assert set(SAME_DAY_BLOCKS) & set(BUILD_LAGGED_BLOCKS) == set()
        assert set(SAME_DAY_BLOCKS) | set(BUILD_LAGGED_BLOCKS) == set(ALL_BLOCKS)

    def test_public_betting_is_the_same_day_detector(self):
        """It is the only block whose feed (ingest_action_network, s4 @ 12:00) precedes the
        lakehouse_w11_nightly_op build (s5c, ~12:40) — so it is the only one that can catch an
        INC-37 month-boundary hole on the day it happens."""
        assert SAME_DAY_BLOCKS == ("public_betting",)
        assert set(BUILD_LAGGED_BLOCKS) == {"umpire", "weather"}

    def test_the_message_names_the_remediation(self):
        _, msg = classify(_stdout(public_betting="BUILD_GAP"), _all_ok())
        assert "--lookahead-days 3" in msg          # the INC-37 month-boundary cure
        assert "--w11d-only" in msg                 # the targeted rebuild
        assert "check_w11_tail_coverage.py --strict" in msg  # the re-verification gate
