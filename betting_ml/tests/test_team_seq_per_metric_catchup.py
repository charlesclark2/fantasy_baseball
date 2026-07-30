"""E9.53 — the team sequential catch-up frontier must be PER METRIC.

THE BUG (root cause of the whole-block outages this story exists for):
    The 2026-07-22 `--catchup` cure ran ONE metric-blind frontier
    (`MAX(game_date) WHERE season = …`) and gated per-date readiness on the TOTAL row count
    across all three metric chains. So a date whose bullpen branch produced ZERO observations
    (its eb_bullpen_posteriors rows not yet built) but whose offense + win branches produced
    rows still returned `rows > 0`, the loop advanced the shared frontier past it, and — the
    chain being NON-IDEMPOTENT — that date's bullpen_xwoba could never be re-processed.
    A PERMANENT per-metric hole. Measured symptom: `*_team_sequential_bullpen_xwoba` NULL for
    every game on 2026-07-22/23/24/27/28 while `_woba` / `_win_prob` were fine on those same
    dates, which set is_degraded on served slates (team_sequential_* is unconditional-core
    discriminative).

WHY PER-METRIC FRONTIERS AND NOT A STRICTER AGGREGATE GATE:
    A stricter gate ("stall the date unless ALL THREE metrics produced rows") would WEDGE the
    offense and win chains behind a late bullpen source — a permanent stall is not an
    improvement on a permanent skip. The three chains are genuinely independent (`_apply_updates`
    keys working state on (team, metric); `_write_updates` closes is_current per (team, metric)),
    so each metric gets its own frontier and its own stall.
"""

from __future__ import annotations

import re
from datetime import date
from unittest import mock

import pytest

from betting_ml.scripts.sequential_bayes import catchup as ct
from betting_ml.scripts.sequential_bayes import update_team_posteriors as utp

_TODAY = date(2026, 7, 29)
# Every date in the window has completed games.
_COMPLETED = [date(2026, 7, d) for d in range(21, 29)]   # 07-21 .. 07-28
# The date whose bullpen source was not ready (eb_bullpen_posteriors unbuilt for it).
_PEN_NOT_READY = date(2026, 7, 24)


class TestTheAggregateGateIsWhatSkippedTheMetric:
    """Pin the pre-fix mechanism at the loop level, so the regression can't quietly return."""

    def test_a_metric_blind_row_count_advances_past_a_metric_hole(self):
        # PRE-FIX: process_date returned the TOTAL across metrics. off(30) + win(30) + pen(0) = 60,
        # which is truthy → the loop advances, and the shared frontier moves past the date.
        def process_aggregate(gd):
            return 0 + 60 if gd == _PEN_NOT_READY else 90

        processed, stalled = ct.run_catchup_loop(_COMPLETED, process_aggregate, "pre-fix")
        assert stalled is None, "pre-fix: nothing stalls"
        assert _PEN_NOT_READY in processed, (
            "pre-fix: the metric-incomplete date is ACCEPTED and the frontier advances past it — "
            "this is the permanent per-metric skip"
        )

    def test_a_per_metric_count_stalls_on_the_same_input(self):
        # POST-FIX: the bullpen pass sees ONLY its own rows → 0 → stall, retry next run.
        def process_pen_only(gd):
            return 0 if gd == _PEN_NOT_READY else 30

        processed, stalled = ct.run_catchup_loop(_COMPLETED, process_pen_only, "post-fix")
        assert stalled == _PEN_NOT_READY
        assert _PEN_NOT_READY not in processed
        # …and it does NOT advance past it (ordering preserved — the chain is non-idempotent).
        assert all(d < _PEN_NOT_READY for d in processed)


class TestCollectObservationsHonoursTheMetricFilter:
    def _conn_with(self, rows_by_sql):
        def fake_fetch(conn, sql, params):
            for needle, rows in rows_by_sql.items():
                if needle in sql:
                    return rows
            return []
        return fake_fetch

    def test_only_the_requested_metric_is_queried(self):
        calls: list[str] = []

        def fake_fetch(conn, sql, params):
            calls.append(sql)
            return []

        with mock.patch.object(utp, "_fetch_dicts", fake_fetch):
            utp._collect_observations(mock.MagicMock(), _TODAY,
                                      frozenset({utp._M_PEN}))
        assert len(calls) == 1, "a filtered collect must not issue the other metrics' queries"
        assert "eb_bullpen_posteriors" in calls[0], "expected the bullpen query"

    def test_no_filter_queries_all_three(self):
        calls: list[str] = []

        def fake_fetch(conn, sql, params):
            calls.append(sql)
            return []

        with mock.patch.object(utp, "_fetch_dicts", fake_fetch):
            utp._collect_observations(mock.MagicMock(), _TODAY, None)
        assert len(calls) == 3

    def test_filtered_observations_carry_only_that_metric(self):
        rows = [{"game_pk": 1, "game_date": "2026-07-28", "team": "NYY",
                 "obs_mean": 0.33, "n_obs": 40}]

        def fake_fetch(conn, sql, params):
            return rows if "eb_bullpen_posteriors" in sql else []

        with mock.patch.object(utp, "_fetch_dicts", fake_fetch):
            obs = utp._collect_observations(mock.MagicMock(), _TODAY, frozenset({utp._M_PEN}))
        assert obs and {o["metric"] for o in obs} == {utp._M_PEN}


def _run_catchup_capturing(process_results):
    """Drive the real run_catchup with mocked IO. Returns (frontier_sqls, processed_by_metric).

    `process_results(gd, metrics) -> int` stands in for update_for_date's row count.
    """
    frontier_sqls: list[str] = []
    processed: dict[str, list[date]] = {m: [] for m in utp._CATCHUP_METRICS}
    # Every metric starts at 07-20, so the whole 07-21..07-28 window is eligible for each.
    frontier = date(2026, 7, 20)

    def fake_fetch(conn, sql, params):
        if "MAX(game_date)" in sql:
            frontier_sqls.append(sql)
            return [{"d": frontier}]
        if "DISTINCT game_date" in sql:
            return [{"d": d} for d in _COMPLETED]
        return []

    def fake_update(gd, *a, metrics=None, **kw):
        (metric,) = metrics
        n = process_results(gd, metric)
        if n:
            processed[metric].append(gd)
        return {"rows": n}

    with mock.patch.object(utp, "_fetch_dicts", fake_fetch), \
         mock.patch.object(utp, "update_for_date", fake_update), \
         mock.patch.object(utp, "_prep", lambda *a, **kw: None), \
         mock.patch.object(utp, "get_snowflake_connection", mock.MagicMock()), \
         mock.patch("betting_ml.utils.game_day.current_game_date", lambda: _TODAY):
        utp.run_catchup(10, 0.385, 60, 8.0, dry_run=False)
    return frontier_sqls, processed


class TestRunCatchupIsPerMetric:
    def test_each_metric_gets_its_own_frontier_query(self):
        frontier_sqls, _ = _run_catchup_capturing(lambda gd, m: 30)
        assert len(frontier_sqls) == 3, "expected one frontier read per metric chain"
        got = set()
        for sql in frontier_sqls:
            m = re.search(r"metric = '([a-z_]+)'", sql)
            assert m, f"frontier query is METRIC-BLIND (the E9.53 defect): {sql}"
            got.add(m.group(1))
        assert got == set(utp._CATCHUP_METRICS)

    def test_a_late_bullpen_source_stalls_only_the_bullpen_chain(self, capsys):
        # THE REGRESSION TEST. 07-24's bullpen source is not ready; offense and win are fine.
        _, processed = _run_catchup_capturing(
            lambda gd, m: 0 if (m == utp._M_PEN and gd == _PEN_NOT_READY) else 30
        )
        # off + win advance over the WHOLE window — they are not held hostage by bullpen.
        assert processed[utp._M_OFF] == _COMPLETED
        assert processed[utp._M_WIN] == _COMPLETED
        # bullpen stops AT the un-ready date and does not skip it.
        assert processed[utp._M_PEN] == [d for d in _COMPLETED if d < _PEN_NOT_READY]
        assert _PEN_NOT_READY not in processed[utp._M_PEN]

    def test_the_stall_is_loudly_alerted(self, capsys):
        _run_catchup_capturing(
            lambda gd, m: 0 if (m == utp._M_PEN and gd == _PEN_NOT_READY) else 30
        )
        err = capsys.readouterr().err
        assert "[ALERT]" in err, "a stalled metric chain must ALERT loudly (E11.7 ALERT tier)"
        assert utp._M_PEN in err
        assert "2026-07-24" in err

    def test_a_healthy_run_advances_every_metric_and_is_silent(self, capsys):
        _, processed = _run_catchup_capturing(lambda gd, m: 30)
        for m in utp._CATCHUP_METRICS:
            assert processed[m] == _COMPLETED
        assert "[ALERT]" not in capsys.readouterr().err

    def test_no_metric_is_ever_skipped_when_a_later_date_is_ready(self):
        # The ordering invariant: a stall must not let LATER dates through for that metric,
        # or the non-idempotent chain is corrupted (catchup.py failure mode 2).
        _, processed = _run_catchup_capturing(
            lambda gd, m: 0 if (m == utp._M_PEN and gd == _PEN_NOT_READY) else 30
        )
        assert all(d < _PEN_NOT_READY for d in processed[utp._M_PEN])


class TestMetricsAreTheThreeChains:
    def test_catchup_covers_every_metric_the_producer_writes(self):
        assert set(utp._CATCHUP_METRICS) == {utp._M_OFF, utp._M_PEN, utp._M_WIN}

    @pytest.mark.parametrize("metric", ["off_xwoba", "bullpen_xwoba", "win_prob"])
    def test_metric_names_match_the_consumer_pivot(self, metric):
        # feature_pregame_game_features_raw pivots on these exact literals; a rename here would
        # silently null the block in the served store.
        assert metric in utp._CATCHUP_METRICS
