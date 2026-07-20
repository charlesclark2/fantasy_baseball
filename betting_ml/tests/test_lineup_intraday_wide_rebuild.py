"""test_lineup_intraday_wide_rebuild.py — INC-31 intraday lineups-wide refresh.

The lineup monitor (lineup_monitor.py) detects a slate's confirmed lineups by reading
betting.stg_statsapi_lineups_wide → lakehouse_ext → the S3 stg_statsapi_lineups_wide parquet, and
the --s3 serving reads build the pick-detail lineup card from the same parquet. That parquet was
rebuilt ONLY by the once-daily morning run, so lineups that post during the slate were invisible all
day: the monitor never fired post_lineup, and the lineup card stayed empty. The fix rebuilds the
parquet on the INTRADAY schedule-capture cadence (upstream of the monitor) + refreshes its ext table.

Source-inspection only (fast-gate-safe: does NOT import the `pipeline` package, which pulls in the
dbt manifest that is absent in the fast CI job).
"""
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).parents[2]
_INTRADAY = _REPO / "pipeline" / "ops" / "intraday_ops.py"
_REFRESH = _REPO / "scripts" / "refresh_w1_external_tables.py"


def _slice(src: str, start: str, end: str) -> str:
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def test_intraday_schedule_rebuilds_lineups_wide_after_games_and_before_refresh():
    src = _INTRADAY.read_text()
    body = _slice(src, "def _schedule_lakehouse_intraday", "\ndef _w6_lakehouse_intraday")
    # The wide-lineup rebuild must be present…
    assert '"--w7b-only"' in body, "intraday schedule capture must rebuild stg_statsapi_lineups_wide (--w7b-only)"
    # …and ordered: games flatten (--w3pre-only) → lineups (--w7b-only) → ext refresh. Match the
    # QUOTED _run_script call args so the docstring's prose copies don't skew the offsets.
    i_w3 = body.index('["--w3pre-only"]')
    i_w7 = body.index('["--w7b-only"]')
    i_refresh = body.index('"refresh_w1_external_tables.py")')
    assert i_w3 < i_w7 < i_refresh, "order must be --w3pre-only → --w7b-only → refresh"


def test_default_refresh_covers_lineups_wide_ext_table():
    src = _REFRESH.read_text()
    assert "W7B_SERVING_TABLES" in src
    # The constant carries the wide lineup table…
    const = _slice(src, "W7B_SERVING_TABLES = [", "]")
    assert "stg_statsapi_lineups_wide" in const
    # …and it is wired into the DEFAULT (no-flag) refresh call so the monitor's SF view reflects it.
    # (Anchor updated for E11.20 phase 1.5: W1_TABLES left the daily refresh list.)
    default_refresh = _slice(src, "STG_BATTER_PITCHES_TABLE + W2_TABLES", "required=required,")
    assert "W7B_SERVING_TABLES" in default_refresh, "W7B_SERVING_TABLES must be in the default refresh set"
