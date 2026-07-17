"""INC-31-B2 (2026-07-16): the intraday lineup chain must rebuild the FLATTEN, not just
the pivot.

INCIDENT: the 7/16 PHI@NYM slate got no post_lineup re-score with confirmed lineups
sitting in lakehouse_raw 2.6h before first pitch — and lineup_monitor_state shows ZERO
organic detections since 2026-07-07. Root cause: the INC-31 (7/10) fix put
`run_w1_lakehouse.py --w7b-only` on the intraday cadence, but `stg_statsapi_lineups_wide`
(what lineup_monitor.py reads, via the SF ext view) is a pure PIVOT of
`stg_statsapi_lineups` — a W6 stg model materialized only by the DAILY-morning build,
hours before any lineup posts. A fresh pivot over a morning-stale flatten is still
stale, so same-day lineups could never reach the monitor.

CURE: `_build_w7b` rebuilds `stg_statsapi_lineups` from the raw (its duckdb branch reads
lakehouse_raw/monthly_schedule directly) BEFORE the W7B_BACKLOG_MODELS pivot loop.

Source-inspection (fast-gate rule: never import `pipeline`; run_w1_lakehouse is a script
with heavy imports — inspect, don't import).
"""
from __future__ import annotations

from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "scripts" / "run_w1_lakehouse.py").read_text()


def _w7b_body() -> str:
    start = SRC.find("def _build_w7b")
    end = SRC.find("\ndef ", start + 1)
    return SRC[start:end]


def test_w7b_rebuilds_the_lineups_flatten():
    body = _w7b_body()
    assert '_build_marts(conn, ["stg_statsapi_lineups"]' in body, (
        "_build_w7b no longer rebuilds the stg_statsapi_lineups FLATTEN — the intraday "
        "lineups_wide pivot would read the daily-morning parquet again and the lineup "
        "monitor goes structurally blind to same-day confirmed lineups (zero organic "
        "detections 2026-07-08→07-16)."
    )


def test_flatten_rebuild_precedes_the_pivot():
    body = _w7b_body()
    flatten = body.find('_build_marts(conn, ["stg_statsapi_lineups"]')
    pivot_loop = body.find("for model in W7B_BACKLOG_MODELS")
    assert flatten != -1 and pivot_loop != -1 and flatten < pivot_loop, (
        "the flatten rebuild must run BEFORE the W7B_BACKLOG_MODELS loop — "
        "stg_statsapi_lineups_wide pivots it, so order is the whole fix."
    )


def test_wide_pivot_still_reads_the_flatten():
    """If the pivot is ever repointed off stg_statsapi_lineups (e.g. straight to raw),
    this suite's premise changes — re-evaluate the flatten rebuild rather than silently
    keeping a now-redundant build step."""
    wide = (Path(__file__).resolve().parents[2] /
            "dbt" / "models" / "staging" / "stg_statsapi_lineups_wide.sql").read_text()
    assert "from stg_statsapi_lineups" in wide
