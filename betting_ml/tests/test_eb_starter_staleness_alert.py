"""E11.20 phase-2b — the eb_starter_posteriors staleness ALERT at the source.

WHY. On 2026-07-27 the published S3 `eb_starter_posteriors` parquet held ZERO rows for
7/25, 7/26 and 7/27 while Snowflake had 23 for the live slate. A rebuild from the SAME S3
precursors reproduced Snowflake exactly, so neither the model nor its inputs were at fault
— the published parquet had simply been left behind by the daily cycle, silently, for
days. Nothing noticed because nothing looked: the eb_batter sibling has a staleness guard
(`_alert_stale_eb_batter`), eb_starter had none.

⭐ THE LOAD-BEARING DESIGN DETAIL — a max(game_date) check CANNOT catch this. The
probable-pitcher spine carries far-FUTURE rows (the documented 2026-06-15 incident: the
spine ran to 2026-09-22), so `eb_starter_posteriors`'s max game_date is ~9/22 whether the
current slate is present or not. Verified live: with the stale parquet AND with a fresh
rebuild, max game_date was 2026-09-22 in BOTH cases — the eb_batter pattern
(`max(game_date) >= current_date`) would have passed silently through the whole outage.
The guard therefore compares TODAY's COVERAGE against the probable-pitcher spine, which is
also what makes a legitimately dark day (no games) a non-warning instead of a false alarm.

Source-inspection: importing run_w1_lakehouse pulls duckdb/boto3 and the module reads S3
at call time, which is not fast-gate material. The behaviour itself was exercised against
real S3 on both a stale and a fresh parquet when it was written.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "scripts" / "run_w1_lakehouse.py").read_text()


def _alert_body() -> str:
    return SRC.split("def _alert_stale_eb_starter")[1].split("\ndef ")[0]


def test_the_alert_exists_and_runs_after_the_w8a_eb_build():
    assert "def _alert_stale_eb_starter" in SRC, (
        "the eb_starter staleness guard is gone — a stale published parquet goes back to "
        "rotting silently, and an S3-routed serving freshness gate abstains the whole slate."
    )
    w8a = SRC.split("def _build_w8a")[1].split("\ndef ")[0]
    assert "_alert_stale_eb_starter(conn)" in w8a, (
        "_build_w8a must call the guard after building the EB posteriors — the alert has to "
        "fire where the parquet is written, not somewhere a reader might later notice."
    )


def test_alert_compares_coverage_to_the_spine_not_max_game_date():
    """The whole point. The probable-pitcher spine carries far-future rows, so eb_starter's
    max game_date sits months out even when the live slate is entirely missing."""
    body = _alert_body()
    assert "stg_statsapi_probable_pitchers" in body, (
        "the guard must measure against the probable-pitcher spine (the model's own game "
        "universe), not a bare date comparison."
    )
    assert "spine_today" in body and "eb_today" in body, (
        "compare TODAY's coverage (eb rows vs scheduled probable starters). A "
        "max(game_date) >= current_date check is BLIND here — the spine's future rows keep "
        "max game_date ~months ahead whether or not the current slate was built."
    )
    assert not re.search(r"max\(game_date::date\)\s*>=\s*current_date", body), (
        "this is exactly the eb_batter-style check that cannot detect the 7/27 outage."
    )


def test_a_dark_day_does_not_warn():
    """No probable starters scheduled ⇒ an empty build is correct, not a defect. A guard
    that cries wolf on every off-day gets muted, and then it protects nothing."""
    body = _alert_body()
    assert "if spine_today == 0:" in body and "return" in body
    dark_branch = body.split("if spine_today == 0:")[1].split("return")[0]
    assert "WARNING" not in dark_branch, (
        "a dark day (zero scheduled probable starters) must not emit a WARNING."
    )


def test_partial_coverage_is_also_reported():
    body = _alert_body()
    assert "elif eb_today < spine_today:" in body, (
        "partial coverage (some games built, some missing) degrades the served starter block "
        "for the missing games and must warn, not pass as OK."
    )


def test_alert_is_alert_tier_never_raises():
    """ALERT-loud-but-continue: warn to stderr, never HALT a build. A build-time guard that
    can raise turns an observability improvement into a new outage mode."""
    body = _alert_body()
    assert "file=sys.stderr" in body, "warnings must reach stderr (ALERT tier), not a silent print"
    assert "except Exception" in body and "return" in body, (
        "a failed staleness probe must degrade to a skip, never propagate."
    )
    # Match a `raise` STATEMENT, not the word in prose — the docstring says "never raises".
    assert not re.search(r"^\s*raise\b", body, re.M), (
        "the guard must never raise — it is observability, not a gate."
    )
