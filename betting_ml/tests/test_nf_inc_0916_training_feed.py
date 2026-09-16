"""NF-INC-0916 node 1 — the weekly model's TRAINING FEEDS have an owner, an order and an SLA.

⛔ THE DEFECT THIS GUARDS IS AN ABSENCE, which is the hardest kind to keep fixed. `stats_player_week`
and `snap_counts` were ingested by nothing, on no cadence, for a whole season — and every job that
read them returned SUCCESS, because a missing stat line is not an error anywhere downstream:
`attach_labels` fills it with a zero under the retained-zero convention and the fit learns from it.
Nothing was red. The clauses below make the ABSENCE itself a failing test.

⚠️ EVERY CLAUSE HERE IS ABOUT A PROPERTY THAT CANNOT BE SEEN FROM ONE FILE. The ownership clause
spans two registries, the ordering clause reads the COMPILED Dagster graph (source order is
meaningless — `in_process_executor` runs topologically, so a source-line assertion is vacuous,
INC-38), and the classifier clauses drive the real function on the five shapes it must tell apart.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from betting_ml.monitoring import nfl_weekly_stats_freshness as SF
from quant_sports_intel_models.football.nfl.ingest.in_season_stats import WEEKLY_STAT_SOURCES
from quant_sports_intel_models.football.nfl.ingest.sources import ROLL_FORWARD_SOURCES, SOURCES

_NOW = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
_WK1_ENDED = datetime(2026, 9, 15, 6, 30, tzinfo=timezone.utc)   # measured: wk1's MNF close


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — THE FEEDS EXIST, AND THEY HAVE EXACTLY ONE INGEST OWNER
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_two_training_feeds_are_registered_free_nflverse_sources():
    """Non-vacuity first: a clause about a set that turned out to be empty would pass on nothing,
    and the COST clause matters because this set is pulled before EVERY daily build."""
    assert WEEKLY_STAT_SOURCES, "the training-feed set is empty — every clause below is vacuous"
    assert set(WEEKLY_STAT_SOURCES) == {"stats_player_week", "snap_counts"}, (
        f"the training-feed set has changed to {WEEKLY_STAT_SOURCES}. That is a real decision — "
        "this set is pulled before every daily weekly build — so it should be a deliberate edit "
        "here as well as there."
    )
    for name in WEEKLY_STAT_SOURCES:
        assert name in SOURCES, f"{name} is not in the source registry"
        assert SOURCES[name].tier == "nflverse", f"{name} is not a free nflverse source"
        assert not SOURCES[name].on_demand, (
            f"{name} is an on_demand source. This set is pulled before EVERY daily build, so a "
            "paid or per-event source here would bill daily."
        )


def test_the_training_feeds_have_exactly_one_ingest_owner():
    """⛔ TWO WRITERS ON ONE DELTA TABLE is the defect class this repo has paid for repeatedly
    (INC-30's two crontabs, INC-36's two deploys, INC-38's four callers). Here it would not even be
    a harmless duplicate: the roll-forward's WEEKLY Monday-morning fire would periodically write a
    STALER view of the same season than the daily one had already landed."""
    overlap = sorted(set(WEEKLY_STAT_SOURCES) & set(ROLL_FORWARD_SOURCES))
    assert not overlap, (
        f"{overlap} are in BOTH WEEKLY_STAT_SOURCES and ROLL_FORWARD_SOURCES — two ingest owners "
        "for one table, on different cadences."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — THE ORDER, ON THE COMPILED GRAPH (INC-25 / INC-40)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _edges():
    """(downstream, upstream) pairs from the COMPILED job graph.

    ⚠️ NOT A SOURCE-ORDER CHECK. `in_process_executor` runs ops in TOPOLOGICAL order, so where an
    op is DEFINED in the file says nothing about when it runs; a guard reading source lines would
    be satisfied by a job whose ops execute in the wrong order (INC-38/INC-40).
    """
    from pipeline.jobs.sports_nfl_weekly_serving_job import sports_nfl_weekly_serving_job as job

    out = []
    for node, deps in job.graph.dependencies.items():
        for dep in deps.values():
            out.append((node.alias or node.name, dep.node))
    return out


def test_the_ingest_runs_before_the_build_that_learns_from_it():
    """⭐ THE INC-25 RULE AS A GRAPH PROPERTY. A consumer refreshed on a different cron from its
    feed is a consumer that can read a lake the feed has not touched; an EDGE makes that
    impossible by construction rather than by two schedules happening to line up."""
    edges = _edges()
    assert edges, "the job graph has no dependencies at all — this clause would pass on nothing"
    names = {d for d, _ in edges} | {u for _, u in edges}
    assert "nfl_weekly_stats_ingest_op" in names, (
        "the training-feed ingest is not in the weekly serving job. Nothing else ingests these "
        "feeds, so without it the build trains on whatever last happened to land — NF-INC-0916."
    )

    # Transitive reachability: the build must be downstream of the ingest, however many legs sit
    # between them.
    upstream: dict[str, set[str]] = {}
    for d, u in edges:
        upstream.setdefault(d, set()).add(u)

    def reaches(node: str, target: str, seen=None) -> bool:
        seen = seen or set()
        for u in upstream.get(node, ()):
            if u == target or (u not in seen and reaches(u, target, seen | {u})):
                return True
        return False

    assert reaches("nfl_weekly_serving_op", "nfl_weekly_stats_ingest_op"), (
        "the build op is NOT downstream of the training-feed ingest — the ordering that makes "
        "'the build reads a feed this run refreshed' true is missing."
    )


def test_the_freshness_leg_is_downstream_of_the_ingest_it_judges():
    """⛔ INC-40: a guard positioned UPSTREAM of the op that writes what it checks reads a store one
    cycle behind and pages on a state the same run heals moments later. The tell there was that the
    date it named read healthy by the time a human looked."""
    edges = _edges()
    upstream = {d: {u for dd, u in edges if dd == d} for d, _ in edges}
    assert "nfl_weekly_stats_ingest_op" in upstream.get("nfl_weekly_stats_freshness_op", set()), (
        "the training-feed freshness leg does not sit downstream of the ingest — it would judge "
        "the lake as it was BEFORE this run refreshed it"
    )


def test_the_ingest_subprocess_carries_a_finite_timeout():
    """INC-32 — every subprocess on a Dagster path is bounded, and `run_bounded` kills the whole
    process group rather than orphaning a grandchild."""
    import importlib
    from pathlib import Path

    # ⚠️ `importlib`, NOT `from pipeline.jobs import sports_nfl_weekly_serving_job`. The package
    # re-exports the JOB under the module's own name, so the plain form binds a `JobDefinition`
    # and every attribute read below fails for a reason that has nothing to do with the property
    # under test.
    J = importlib.import_module("pipeline.jobs.sports_nfl_weekly_serving_job")
    module_src = Path(J.__file__).read_text()
    start = module_src.index("def nfl_weekly_stats_ingest_op(")
    end = module_src.index("def _slate_end_utc(")
    assert start < end, "the ingest op no longer precedes the slate helper — re-anchor this slice"
    src = module_src[start:end]
    assert "run_bounded(" in src, "the ingest does not use the bounded-subprocess helper"
    assert "timeout=NFL_WEEKLY_STATS_INGEST_TIMEOUT_SECONDS" in src, (
        "the ingest subprocess has no finite timeout"
    )
    assert J.NFL_WEEKLY_STATS_INGEST_TIMEOUT_SECONDS > 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — THE FRESHNESS CONTRACT, on the shapes it has to tell apart
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _judge(last_week, *, completed, ended=_WK1_ENDED, err=None, rows=100):
    return SF.classify(
        SF.FeedReading("stats_player_week", last_week, rows, error=err),
        season=2026, last_completed_week=completed, slate_ended=ended, now=_NOW,
    )


@pytest.mark.parametrize("last_week, completed, expected, severity", [
    # The feed carries the last week that was played.
    (1, 1, "OK", None),
    (5, 5, "OK", None),
    # ⭐ PENDING IS A REAL STATE, not a courtesy. A week ends Monday night and the vendor publishes
    # it the next morning (measured: 04:25–07:21 PT). A monitor without this pages every Monday on
    # healthy behaviour, and a monitor that cries wolf gets muted — the INC-37 lesson.
    (None, 1, "PENDING", None),
    (4, 5, "PENDING", None),
    # ⛔ AND THE HOLE THE FIRST CUT OF THIS MODULE HAD. Only the NEWEST week can legitimately be
    # missing; week W−1 closed at least a week ago, so a feed lacking it is behind for a reason no
    # publication delay explains. Without this, the incident's own signature — a season with no
    # rows at all — read as PENDING for a day after every slate.
    (None, 5, "NEVER_INGESTED", "CRITICAL"),
    (3, 5, "STALE", "CRITICAL"),
])
def test_the_feed_is_judged_against_the_week_that_was_actually_played(
    last_week, completed, expected, severity,
):
    v = _judge(last_week, completed=completed)
    assert v["verdict"] == expected, f"{v['verdict']}: {v['detail']}"
    assert v["severity"] == severity


def test_a_feed_that_cannot_be_read_is_warned_about_and_never_scored_healthy():
    """NF1.7(a) — a check that could not run is not a check that passed, and this module exists
    precisely because a year of green runs examined nothing."""
    v = _judge(None, completed=5, err="delta_scan blew up")
    assert v["verdict"] == "UNREADABLE"
    assert v["severity"] == "WARN"
    assert SF.is_problem(v)


def test_the_off_season_carries_no_sla():
    v = _judge(None, completed=None, ended=None)
    assert v["verdict"] == "NO_COMPLETED_WEEK"
    assert v["severity"] is None


def test_the_grace_window_expires():
    """The other side of PENDING: once the vendor has had its window, silence would be the defect."""
    late = _WK1_ENDED + timedelta(hours=SF.SETTLE_HOURS + 1)
    v = SF.classify(SF.FeedReading("snap_counts", None, 0), season=2026,
                    last_completed_week=1, slate_ended=_WK1_ENDED, now=late)
    assert v["verdict"] == "NEVER_INGESTED"
    assert v["severity"] == "CRITICAL"


def test_one_stale_feed_pages_even_when_its_sibling_is_healthy():
    """⛔ The failure would be silent-by-aggregation: judging the pair together and reporting the
    best answer. Both feeds train the model; either one stalling is a finding."""
    ok = _judge(5, completed=5)
    bad = _judge(3, completed=5)
    assert SF.worst([ok, bad]) == "CRITICAL"
    assert SF.worst([ok, ok]) is None


def test_the_settle_window_is_longer_than_the_measured_publication_lag():
    """A design quantity, checked against the measurement it was derived from. The observed lag is
    ~5-8 h (week 1 closed 2026-09-15T06:30Z; the two assets republished 11:25Z and 14:21Z). A
    window at or below that would page on the vendor's normal cadence."""
    measured_lag_hours = 8.0
    assert SF.SETTLE_HOURS > measured_lag_hours * 2, (
        f"SETTLE_HOURS={SF.SETTLE_HOURS} leaves no headroom over the measured ~{measured_lag_hours}h "
        "publication lag — it would page on healthy behaviour, which is how a monitor gets muted"
    )
