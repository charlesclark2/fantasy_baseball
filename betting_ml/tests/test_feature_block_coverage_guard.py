"""Tests for scripts/check_feature_block_coverage.py — the served-feature-block coverage guard.

Guards the F2 / F2-recurrence incident (umpire z-scores collapsed to ~0% in served
feature_pregame_game_features on 2026-07-02 AND again 2026-07-03) while every other block +
the row count stayed intact. The classifier must fire DEGRADED on a normally-full block that
recently collapsed, SKIP a legitimately coverage-gapped block, and never false-fire on a
healthy block.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_feature_block_coverage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_feature_block_coverage", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fbc = _load_module()


class TestClassify:
    def test_no_data(self):
        assert fbc._classify(None, 0.5) == "NO_DATA"
        assert fbc._classify(0.9, None) == "NO_DATA"

    def test_skipped_low_baseline(self):
        # Coverage-gapped block (baseline < WELL_COVERED) with no healthy history — a drop
        # can't be asserted → SKIPPED (hist_cov defaults to None / low).
        assert fbc._classify(base_cov=0.70, recent_cov=0.10) == "SKIPPED"
        assert fbc._classify(base_cov=0.70, recent_cov=0.10, hist_cov=0.72) == "SKIPPED"

    def test_degraded_is_the_umpire_signature(self):
        # base ~1.0 → recent ~0.08 (the observed regression) → collapsed.
        assert fbc._classify(base_cov=1.0, recent_cov=0.077) == "DEGRADED"

    def test_degraded_just_below_relative_floor(self):
        # recent just below 0.70 * base.
        assert fbc._classify(base_cov=1.0, recent_cov=0.69) == "DEGRADED"

    def test_ok_at_relative_floor(self):
        # Exactly at 0.70 * base is not a collapse.
        assert fbc._classify(base_cov=1.0, recent_cov=0.70) == "OK"

    def test_ok_healthy(self):
        assert fbc._classify(base_cov=0.98, recent_cov=0.98) == "OK"

    # ── INC-31: persistently-/born-dead block collapsed vs a healthy HISTORICAL baseline ──
    def test_collapsed_vs_history_rescued_from_skip(self):
        # Dead across the WHOLE trailing window (base_cov=0, recent_cov=0) so the trailing
        # check would SKIP — but it was ~99% historically → RESCUED to DEGRADED (the umpire
        # ext-table-break signature after played-slate values also went null).
        assert fbc._classify(base_cov=0.0, recent_cov=0.0, hist_cov=0.99) == "DEGRADED"

    def test_collapsed_vs_history_partial_trailing(self):
        # Trailing baseline weak (0.40) AND recent near-dead (0.05), healthy history → DEGRADED.
        assert fbc._classify(base_cov=0.40, recent_cov=0.05, hist_cov=0.97) == "DEGRADED"

    def test_no_false_fire_when_history_also_gapped(self):
        # A genuinely era-gapped block (never well covered, incl. history) stays SKIPPED.
        assert fbc._classify(base_cov=0.0, recent_cov=0.0, hist_cov=0.0) == "SKIPPED"
        assert fbc._classify(base_cov=0.60, recent_cov=0.10, hist_cov=0.55) == "SKIPPED"

    def test_no_false_fire_when_history_missing(self):
        # Early-season: no historical games (hist_cov=None) → cannot rescue → SKIPPED.
        assert fbc._classify(base_cov=0.0, recent_cov=0.0, hist_cov=None) == "SKIPPED"

    def test_recovered_block_not_flagged_vs_history(self):
        # Historically healthy AND recently healthy (base weak only by coincidence) — recent
        # is NOT below 70% of history → not a collapse.
        assert fbc._classify(base_cov=0.80, recent_cov=0.95, hist_cov=0.98) == "SKIPPED"


def _spread(total_games: int, total_notnull: int, n_dates: int, zero_last: int = 0,
            zero_offset: int = 1) -> list[tuple[int, int]]:
    """Split (games, notnull) over `n_dates` per-date buckets, zeroing `zero_last` of them.

    `zero_offset` shifts WHICH dates are zeroed away from the end: offset 1 (the default) zeroes
    the dates ending just BEFORE the newest, because the guard exempts the newest played date (it
    legitimately lags one build cycle — see _DATE_OUTAGE_SKIP_NEWEST). Pass 0 to zero the newest
    date itself, which is what the lag-exemption tests do.

    Both games and notnull are spread as EVENLY as possible over their buckets (notnull over the
    NON-zeroed ones only, capped at each date's game count). Evenness matters: a greedy pack would
    leave trailing zero dates and fabricate the very whole-slate outage these tests control for.
    """
    if n_dates <= 0 or total_games <= 0:
        return []
    per, rem = divmod(total_games, n_dates)
    games = [per + (1 if i < rem else 0) for i in range(n_dates)]
    hi = n_dates - zero_offset
    zeroed = set(range(max(0, hi - zero_last), max(0, hi)))
    live_idx = [i for i in range(n_dates) if i not in zeroed]
    notnull = [0] * n_dates
    if live_idx:
        k = len(live_idx)
        for j, i in enumerate(live_idx):
            # Even split via cumulative floors, then clamp to the date's game count.
            share = (total_notnull * (j + 1)) // k - (total_notnull * j) // k
            notnull[i] = min(games[i], share)
    return list(zip(games, notnull))


def _run_main(present_cols, base_n, recent_n, block_counts, argv, capsys, hist_n=None,
              recent_dates=8, zero_dates=None, zero_offset=1):
    """Run main() with a mocked cursor. `block_counts` maps block-name -> (base_notnull,
    recent_notnull) OR (hist_notnull, base_notnull, recent_notnull). `present_cols` = the
    columns information_schema reports present. `hist_n` defaults to base_n (a populated
    historical window). Returns (return_code, stdout_text).

    E9.53 — main() now issues ONE per-game_date query and derives the window aggregates from it,
    so this builds per-date rows. The history and baseline windows collapse to a single synthetic
    date each (they only ever feed aggregates); the RECENT window is spread over `recent_dates`
    dates so the new per-date outage check has something real to look at. `zero_dates` maps
    block-name -> how many of the recent dates are FULLY zeroed for that block (the whole-slate
    outage signature), with the block's remaining notnull count packed into the other dates.
    """
    if hist_n is None:
        hist_n = base_n
    zero_dates = zero_dates or {}
    blocks = {b: c for b, c in fbc._BLOCKS.items()
              if c.lower() in {p.lower() for p in present_cols}}

    # main() anchors its windows off --date; mirror its arithmetic so the mocked dates land
    # inside the intended windows.
    anchor = date.fromisoformat(dict(zip(argv[::2], argv[1::2])).get("--date", "2026-07-03"))
    hist_date = anchor - timedelta(days=60)      # inside [anchor-120 .. anchor-46]
    base_date = anchor - timedelta(days=20)      # inside [anchor-45  .. anchor-9]

    description = [("game_date",), ("n_games",)] + [(f"cov_{b}",) for b in blocks]

    resolved: dict[str, tuple[int, int, int]] = {}
    for b in blocks:
        vals = block_counts.get(b, (base_n, recent_n))
        if len(vals) == 2:               # (base, recent) → healthy history
            bc, rc_ = vals
            hc = hist_n
        else:                            # (hist, base, recent)
            hc, bc, rc_ = vals
        resolved[b] = (hc, bc, rc_)

    rows: list[tuple] = []
    if hist_n:
        rows.append((hist_date, hist_n, *[resolved[b][0] for b in blocks]))
    if base_n:
        rows.append((base_date, base_n, *[resolved[b][1] for b in blocks]))
    # Recent window: one row per date, shared n_games, per-block notnull.
    per_block_dates = {
        b: _spread(recent_n, resolved[b][2], recent_dates, zero_dates.get(b, 0), zero_offset)
        for b in blocks
    }
    shared_games = _spread(recent_n, recent_n, recent_dates)
    for i in range(len(shared_games)):
        rows.append((
            anchor - timedelta(days=recent_dates - i),   # anchor-8 .. anchor-1
            shared_games[i][0],
            *[per_block_dates[b][i][1] for b in blocks],
        ))

    cur = mock.MagicMock()
    cur.fetchall.side_effect = [
        [(c,) for c in present_cols],   # _present_columns
        rows,                           # the per-date coverage query
    ]
    cur.description = description
    conn = mock.MagicMock()
    conn.cursor.return_value = cur
    with mock.patch.object(fbc, "get_snowflake_connection", return_value=conn), \
         mock.patch.object(sys, "argv", ["check_feature_block_coverage.py", *argv]):
        rc = fbc.main()
    return rc, capsys.readouterr().out


_ALL_COLS = list(fbc._BLOCKS.values())


class TestMain:
    def _healthy_counts(self, base_n, recent_n):
        return {b: (base_n, recent_n) for b in fbc._BLOCKS}   # every block ~100%

    def test_umpire_collapse_non_strict_alerts_but_exits_zero(self, capsys, caplog):
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (100, 2)   # base 1.0 → recent 0.10 → DEGRADED
        with caplog.at_level("WARNING"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03"], capsys)
        assert rc == 0
        assert "feature_block_min_cov_ratio=" in out
        assert "ALERT" in caplog.text and "umpire" in caplog.text

    def test_umpire_collapse_strict_halts(self, capsys, caplog):
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (100, 2)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 1
        assert "HALT" in caplog.text

    def test_all_healthy_passes(self, capsys):
        counts = self._healthy_counts(100, 20)
        rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                            ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "feature_block_min_cov_ratio=1.0000" in out

    def test_coverage_gapped_block_is_skipped_not_degraded(self, capsys, caplog):
        # A block that is coverage-gapped ACROSS ALL windows (history included, e.g. odds
        # market_bookmaker_count ~0.6-0.7 by tier) must be SKIPPED even if recent is far lower,
        # and must NOT HALT under --strict. (hist 0.55 < WELL_COVERED → no rescue.)
        counts = self._healthy_counts(100, 20)
        counts["odds_metadata"] = (55, 60, 2)   # hist 0.55, base 0.60 (gapped) → recent 0.10
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0   # gapped baseline + gapped history is never asserted

    def test_absent_column_is_skipped_gracefully(self, capsys, caplog):
        # If the umpire column is absent from the store, it is skipped with a warning,
        # not a crash — and the run still passes on the remaining healthy blocks.
        present = [c for c in _ALL_COLS if c != "ump_accuracy_zscore"]
        counts = self._healthy_counts(100, 20)
        with caplog.at_level("WARNING"):
            rc, out = _run_main(present, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "umpire" in caplog.text and "absent" in caplog.text

    def test_persistently_dead_block_alarms_vs_history(self, capsys, caplog):
        # INC-31 blind spot: umpire dead across the WHOLE trailing window (base 0, recent 0)
        # would be SKIPPED by the trailing-baseline check alone — but it was 99% historically,
        # so it must now ALARM (DEGRADED) and HALT under --strict.
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (99, 0, 0)   # (hist 0.99, base 0.0, recent 0.0)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-09", "--strict"], capsys,
                                hist_n=100)
        assert rc == 1
        assert "HALT" in caplog.text
        assert "umpire" in caplog.text and "history" in caplog.text.lower()

    def test_born_dead_without_history_stays_skipped(self, capsys, caplog):
        # A block dead everywhere (incl. history) is genuinely coverage-gapped → SKIPPED, no HALT.
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (0, 0, 0)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-09", "--strict"], capsys,
                                hist_n=100)
        assert rc == 0

    def test_insufficient_games_is_benign(self, capsys, caplog):
        # Empty windows (feature store not fresh) → benign ALERT, never a HALT.
        counts = self._healthy_counts(0, 0)
        with caplog.at_level("WARNING"):
            rc, out = _run_main(_ALL_COLS, 0, 0, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "insufficient played games" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════════════════
# E9.53 — the PER-DATE blind spot
#
# STORY: `*_team_sequential_bullpen_xwoba` was 0 games on 2026-07-22/23/24/27/28 and the whole
# `team_sequential_woba`/`_win_prob` family was 0 on 07-28, on PLAYED dates, in the served store.
# The guard did NOT alert. These tests pin down WHY (two independent blind spots) and prove both
# are closed.
# ═══════════════════════════════════════════════════════════════════════════════════════

class TestAggregateWindowIsBlindToIntermittentOutages:
    """BLIND SPOT 1 — every pre-E9.53 check was an 8-day WINDOW AGGREGATE, so a whole-slate
    outage on one or two individual dates dilutes below the relative-drop threshold and can
    never fire. This is arithmetic, not a tuning question: it takes THREE of eight dates fully
    dead before the aggregate notices."""

    def test_one_dead_date_is_invisible_to_the_aggregate(self):
        # 7 of 8 dates healthy → recent = 0.875 of a 1.0 baseline; _REL_DROP is 0.70.
        assert fbc._classify(base_cov=1.0, recent_cov=7 / 8) == "OK"

    def test_two_dead_dates_are_still_invisible_to_the_aggregate(self):
        assert fbc._classify(base_cov=1.0, recent_cov=6 / 8) == "OK"

    def test_three_dead_dates_is_the_first_the_aggregate_can_see(self):
        # 5/8 = 0.625 < 0.70 — so the aggregate only ever fires on a THREE-date outage.
        assert fbc._classify(base_cov=1.0, recent_cov=5 / 8) == "DEGRADED"

    def test_the_observed_e9_53_pattern_evades_the_aggregate(self):
        # As observed on the 07-29 anchor: bullpen_xwoba dead on 07-27 + 07-28 within the
        # recent window → 6/8 → the aggregate reads OK. The per-date check must catch it.
        assert fbc._classify(base_cov=1.0, recent_cov=6 / 8) == "OK"


class TestFindDateOutages:
    """BLIND SPOT 1, closed: assert PER PLAYED DATE, absolutely and low."""

    def test_a_fully_dead_date_is_an_outage(self):
        # A trailing healthy date is required: the NEWEST played date is exempt (it lags one
        # build cycle), so the dead date under test must not be the newest one.
        per_date = [("2026-07-27", 15, 15), ("2026-07-28", 16, 0), ("2026-07-29", 15, 15)]
        assert fbc.find_date_outages(per_date, baseline_cov=1.0) == [("2026-07-28", 0.0)]

    def test_all_healthy_dates_yield_nothing(self):
        per_date = [("2026-07-27", 15, 15), ("2026-07-28", 16, 16)]
        assert fbc.find_date_outages(per_date, baseline_cov=1.0) == []

    def test_a_partial_date_is_not_an_outage(self):
        # 60% covered on a date is a partial gap (a few games missing a starter etc.), NOT a
        # whole-slate block zeroing. The check must stay absolute+low so it never nags.
        per_date = [("2026-07-28", 15, 9), ("2026-07-29", 15, 15)]   # not vacuous: 07-28 is checked
        assert fbc.find_date_outages(per_date, baseline_cov=1.0) == []

    def test_multiple_outage_dates_are_all_reported_sorted(self):
        per_date = [("2026-07-28", 16, 0), ("2026-07-22", 15, 0), ("2026-07-23", 15, 15),
                    ("2026-07-29", 15, 15)]   # trailing healthy date — the newest is exempt
        assert fbc.find_date_outages(per_date, baseline_cov=1.0) == [
            ("2026-07-22", 0.0), ("2026-07-28", 0.0),
        ]

    def test_a_coverage_gapped_block_has_no_outages(self):
        # No healthy reference level (baseline AND history both weak) → a zero date cannot be
        # called an outage; that is the SKIPPED contract, preserved per-date.
        per_date = [("2026-07-28", 16, 0)]
        assert fbc.find_date_outages(per_date, baseline_cov=0.60, hist_cov=0.55) == []

    def test_history_alone_is_enough_of_a_reference(self):
        # INC-31 shape: trailing baseline dead too, but historically healthy → still an outage.
        per_date = [("2026-07-28", 16, 0), ("2026-07-29", 15, 15)]   # newest is exempt
        assert fbc.find_date_outages(per_date, baseline_cov=0.0, hist_cov=0.99) == [
            ("2026-07-28", 0.0),
        ]

    def test_a_tiny_date_is_ignored(self):
        # A 2-game date (all-star break / a suspended-game remnant) is too small to judge.
        per_date = [("2026-07-28", 2, 0), ("2026-07-29", 15, 15)]   # not vacuous: 07-28 is checked
        assert fbc.find_date_outages(per_date, baseline_cov=1.0) == []


class TestPerDateOutageEndToEnd:
    def _healthy_counts(self, base_n, recent_n):
        return {b: (base_n, recent_n) for b in fbc._BLOCKS}

    def test_single_date_whole_slate_outage_halts_under_strict(self, capsys, caplog):
        # THE REGRESSION TEST. recent_n=120 over 8 dates (15/date, realistic). The bullpen
        # sequential block is dead on exactly ONE date → aggregate 105/120 = 0.875 = OK, so the
        # pre-E9.53 guard passed. The per-date check must now HALT.
        counts = self._healthy_counts(120, 120)
        counts["team_sequential_bullpen"] = (120, 105)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(
                _ALL_COLS, 120, 120, counts,
                ["--env", "prod", "--date", "2026-07-29", "--strict"], capsys,
                hist_n=120, zero_dates={"team_sequential_bullpen": 1},
            )
        assert rc == 1, "a whole-slate one-date block outage must HALT under --strict"
        assert "team_sequential_bullpen" in caplog.text
        assert "WHOLE-SLATE OUTAGE" in caplog.text
        assert "feature_block_date_outage_count=1" in out

    def test_the_aggregate_would_have_passed_the_same_input(self, capsys):
        # Two-sided proof the per-date check is what fires: same coverage totals, but spread
        # EVENLY (no date fully dead) → no outage, and the aggregate ratio alone passes.
        counts = self._healthy_counts(120, 120)
        counts["team_sequential_bullpen"] = (120, 105)
        rc, out = _run_main(
            _ALL_COLS, 120, 120, counts,
            ["--env", "prod", "--date", "2026-07-29", "--strict"], capsys,
            hist_n=120, zero_dates=None,
        )
        assert rc == 0
        assert "feature_block_date_outage_count=0" in out

    def test_the_full_e9_53_pattern_reports_every_outage_date(self, capsys, caplog):
        # bullpen sequential dead on 2 of the 8 recent dates, ending just before the newest
        # (which is exempt) → aggregate 0.75 = OK, per-date reports BOTH dates.
        counts = self._healthy_counts(120, 120)
        counts["team_sequential_bullpen"] = (120, 90)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(
                _ALL_COLS, 120, 120, counts,
                ["--env", "prod", "--date", "2026-07-29", "--strict"], capsys,
                hist_n=120, zero_dates={"team_sequential_bullpen": 2},
            )
        assert rc == 1
        assert "feature_block_date_outage_count=2" in out
        assert "2026-07-27" in caplog.text and "2026-07-26" in caplog.text

    def test_a_coverage_gapped_block_with_dead_dates_still_does_not_halt(self, capsys):
        # odds_metadata is legitimately partial by tier — a zero date must not HALT.
        counts = self._healthy_counts(120, 120)
        counts["odds_metadata"] = (66, 72, 60)   # hist 0.55, base 0.60 → gapped
        rc, out = _run_main(
            _ALL_COLS, 120, 120, counts,
            ["--env", "prod", "--date", "2026-07-29", "--strict"], capsys,
            hist_n=120, zero_dates={"odds_metadata": 2},
        )
        assert rc == 0


class TestSeasonnormProbeIsRefused:
    """BLIND SPOT 2 — a `_seasonnorm` column is derived from its raw twin via a coalesce, so it
    read 100% NOT-NULL straight through a total outage of its own block. That is why the outage
    'looked like' the _seasonnorm variants came from a different path. A coverage guard keyed off
    one is a guard that silently passes forever, so it is refused outright."""

    def test_all_configured_probe_columns_are_raw(self):
        fbc._assert_representative_columns_are_raw(fbc._BLOCKS)   # must not raise

    def test_a_seasonnorm_probe_column_raises(self):
        bad = {"bullpen_eb": "home_bp_eb_xwoba_seasonnorm"}
        with pytest.raises(ValueError, match="_seasonnorm"):
            fbc._assert_representative_columns_are_raw(bad)

    def test_the_error_names_the_offending_block(self):
        bad = {"team_sequential_bullpen": "home_team_sequential_bullpen_xwoba_seasonnorm"}
        with pytest.raises(ValueError, match="team_sequential_bullpen"):
            fbc._assert_representative_columns_are_raw(bad)


class TestTeamSequentialBlocksAreGuarded:
    """BLIND SPOT 3 — the simplest one: `team_sequential_*` was not in _BLOCKS AT ALL, so the
    guard had nothing to look at. It is UNCONDITIONAL-CORE DISCRIMINATIVE (predict_today's
    _DISCRIMINATIVE_RE matches it), so a zero sets is_degraded on every served pick."""

    def test_all_three_metric_chains_are_separately_registered(self):
        # THREE blocks, not one: the producer advances the three metric chains independently and
        # they demonstrably failed independently (bullpen dead while off/win were fine), so a
        # single representative column would have missed the real outage.
        assert fbc._BLOCKS["team_sequential_off"] == "home_team_sequential_woba"
        assert fbc._BLOCKS["team_sequential_bullpen"] == "home_team_sequential_bullpen_xwoba"
        assert fbc._BLOCKS["team_sequential_win"] == "home_team_sequential_win_prob"

    def test_bullpen_eb_block_is_still_guarded(self):
        # `*_bp_eb_xwoba` was 0 games on 2026-07-27 — already registered, but it only ever had
        # the aggregate check, which the per-date check above now backstops.
        assert fbc._BLOCKS["bullpen_eb"] == "home_bp_eb_xwoba"


class TestNewestPlayedDateIsExemptFromTheLagAlarm:
    """⏳ The newest played date legitimately lags one build cycle — it must not ALERT.

    MEASURED 2026-07-31, right after the E9.53 repair: dates 07-20..07-29 were fully covered for
    every block and ONLY 07-30 (the newest) read bp_eb_xwoba 0/10 — while Snowflake's own
    mart_bullpen_effectiveness already had 07-30. The aggregator's precursor chain runs early in the
    daily job, before that day's EB posteriors exist, so the newest date populates on the FOLLOWING
    run. Without the exemption this guard ALERTs every single day on a self-resolving condition,
    which is alarm fatigue on the one detector for silent zeroing — and would make
    FEATURE_COVERAGE_STRICT=1 a guaranteed daily HALT, permanently blocking its promotion.
    """

    def test_a_zero_on_the_newest_date_alone_is_not_an_outage(self):
        # Today's exact live shape.
        live = [(f"2026-07-{d}", 15, 15) for d in range(23, 30)] + [("2026-07-30", 10, 0)]
        assert fbc.find_date_outages(live, baseline_cov=1.0) == []

    def test_and_the_exemption_is_the_ONLY_thing_suppressing_it(self):
        # Two-sided: with skip_newest=0 the very same input DOES report the outage, so the silence
        # above is the exemption doing its job — not the check failing to look.
        live = [(f"2026-07-{d}", 15, 15) for d in range(23, 30)] + [("2026-07-30", 10, 0)]
        assert fbc.find_date_outages(live, baseline_cov=1.0, skip_newest=0) == [("2026-07-30", 0.0)]

    def test_the_e9_53_pattern_is_still_caught_in_full(self):
        # The exemption must not reopen the blind spot. Real holes persist for DAYS (07-22 was
        # still dead on 07-29), so they always survive into the non-exempt window.
        e953 = [("2026-07-23", 15, 0), ("2026-07-24", 15, 15), ("2026-07-25", 15, 15),
                ("2026-07-26", 15, 15), ("2026-07-27", 11, 0), ("2026-07-28", 15, 0),
                ("2026-07-29", 16, 16), ("2026-07-30", 10, 10)]
        assert fbc.find_date_outages(e953, baseline_cov=1.0) == [
            ("2026-07-23", 0.0), ("2026-07-27", 0.0), ("2026-07-28", 0.0),
        ]

    def test_a_two_day_outage_reaching_the_newest_date_still_fires(self):
        # Only ONE date is exempt, so a genuine outage is reported a day late, never suppressed.
        two_day = [(f"2026-07-{d}", 15, 15) for d in range(23, 29)] + [
            ("2026-07-29", 16, 0), ("2026-07-30", 10, 0)]
        assert fbc.find_date_outages(two_day, baseline_cov=1.0) == [("2026-07-29", 0.0)]

    def test_exemption_picks_the_newest_by_DATE_not_by_row_order(self):
        # The query orders by game_date today, but a reordered query must not silently change WHICH
        # date is exempt — so the helper sorts explicitly.
        shuffled = [("2026-07-30", 10, 0), ("2026-07-25", 15, 15), ("2026-07-23", 15, 15),
                    ("2026-07-29", 16, 16), ("2026-07-24", 15, 15), ("2026-07-26", 15, 15),
                    ("2026-07-27", 11, 15), ("2026-07-28", 15, 15)]
        assert fbc.find_date_outages(shuffled, baseline_cov=1.0) == []

    def test_end_to_end_a_newest_date_outage_does_not_halt(self, capsys):
        counts = {b: (120, 120) for b in fbc._BLOCKS}
        counts["bullpen_eb"] = (120, 105)
        rc, out = _run_main(
            _ALL_COLS, 120, 120, counts,
            ["--env", "prod", "--date", "2026-07-31", "--strict"], capsys,
            hist_n=120, zero_dates={"bullpen_eb": 1}, zero_offset=0,   # zero the NEWEST date
        )
        assert rc == 0, "a newest-date-only zero must not HALT — it self-heals next run"
        assert "feature_block_date_outage_count=0" in out
