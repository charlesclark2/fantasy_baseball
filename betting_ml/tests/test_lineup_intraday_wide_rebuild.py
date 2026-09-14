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

import re
from pathlib import Path

_REPO = Path(__file__).parents[2]
_INTRADAY = _REPO / "pipeline" / "ops" / "intraday_ops.py"
_REFRESH = _REPO / "scripts" / "refresh_w1_external_tables.py"


def _slice(src: str, start: str, end: str) -> str:
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def _decommented(src: str) -> str:
    """Strip `#` comment lines — INC-38: a guard a COMMENT can satisfy is not a guard.

    MLB-LAKE2 found this the honest way: its RED proof deleted the W3pre leg from the tick's loop
    and this test stayed GREEN, because the explanatory comment above the loop still contained the
    flag literal. The ordering assertion below must read CODE.
    """
    return re.sub(r"^\s*#.*$", "", src, flags=re.MULTILINE)


def test_intraday_schedule_rebuilds_lineups_wide_after_games_and_before_refresh():
    src = _INTRADAY.read_text()
    body = _decommented(
        _slice(src, "def _schedule_lakehouse_intraday", "\ndef _w6_lakehouse_intraday"))
    # The wide-lineup rebuild must be present…
    assert '"--w7b-only"' in body, "intraday schedule capture must rebuild stg_statsapi_lineups_wide (--w7b-only)"
    # …and ordered: games flatten (--w3pre-serving-only) → lineups (--w7b-only) → ext refresh.
    #
    # INC-41 (2026-08-06): the two rebuilds moved from consecutive bare `_run_script(...)` calls
    # under ONE try block into a per-leg loop, so that a failure in the odds/game flatten can no
    # longer skip the lineups rebuild entirely (it did exactly that for 6.5h). The ORDERING
    # invariant this test exists for is UNCHANGED and still load-bearing — the loop's tuple is
    # ordered — so we anchor on the flag literals rather than the old call syntax. Deliberately
    # matched WITHOUT the surrounding `["..."]` so this keeps passing whether the flags are
    # written as literal call args or as loop items.
    # MLB-LAKE2 re-anchor (2026-09-14): the tick now asks for the SCOPED W3pre build
    # (--w3pre-serving-only) — it stopped paying ~163 s for daily-cadence odds staging inside a
    # 480 s leg, which by then was killing the tier outright. The ORDERING invariant this test
    # exists for is UNCHANGED and still load-bearing; only the flag's name moved. Requiring
    # EXACTLY ONE known W3pre flag keeps this strict — it cannot pass on a leg that has no W3pre
    # build at all, which a bare prefix match would allow.
    w3_flags = [f for f in ('"--w3pre-serving-only"', '"--w3pre-only"') if f in body]
    assert len(w3_flags) == 1, (
        f"expected exactly one W3pre flag in the intraday schedule leg, found {w3_flags}"
    )
    i_w3 = body.index(w3_flags[0])
    i_w7 = body.index('"--w7b-only"')
    # E11.26 re-anchor: the refresh call gained `timeout=_TICK_LEG_TIMEOUT`, so the trailing `)`
    # is no longer adjacent. The ORDERING invariant this test exists for is untouched.
    i_refresh = body.index('"refresh_w1_external_tables.py"')
    assert i_w3 < i_w7 < i_refresh, (
        f"order must be {w3_flags[0]} → --w7b-only → refresh")


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
