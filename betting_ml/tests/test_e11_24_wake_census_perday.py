"""E11.24 — tests for the wake census's per-day × family cut and its measurement hygiene.

WHY THE PER-DAY CUT EXISTS (the landmine it closes):
    The census's aggregate family table (Table 4) sums a family over the WHOLE lookback window,
    so a lever flipped mid-window still shows a large total. That is structurally unable to
    distinguish "still firing" from "pre-flip residue", and it burned the story in BOTH
    directions on 2026-08-03:
      · the `6 tick CTAS` family was LABELLED "dead 7/25" and was in fact the top waking
        statement in the whole account (49 waits / 10 days, incl. the zero-game overnight band);
      · `compute_elo` showed 27 waits and was ENTIRELY dead — executions held (73→46) while waits
        collapsed to 0 from 7/30, i.e. every one of those 27 was pre-flip residue.
    Table 4b reports EXECUTIONS and WAITS per day per family, which separates the three cases:
      executions hold + waits→0  = the gate fired (dead lever, residue only)
      executions and waits both collapse = the caller stopped (a dead job), NOT a lever
      executions hold + waits hold = still firing (a real waker)

WHY THE WAREHOUSE GUARD EXISTS:
    The census must run on MONITOR_WH. Running it on the warehouse under measurement makes the
    audit a line in its own results — that is target 3's "self-inflicted wake" defect, and it
    would also pollute the very baseline the story is trying to read (as happened to 2026-08-03,
    which was contaminated by ad-hoc COMPUTE_WH diagnostics and had to be discarded).

SOURCE-INSPECTION for the wiring assertions, not an import of `pipeline` (E11.23): the census
script itself is import-safe, so the pure shaping function is loaded by path.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CENSUS = REPO_ROOT / "scripts" / "report_e11_24_wake_census.py"


def _load():
    spec = importlib.util.spec_from_file_location("wake_census", CENSUS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _src() -> str:
    return CENSUS.read_text()


# ── the pure shaping function ────────────────────────────────────────────────────────────

def test_pivot_shapes_family_by_day_with_execs_over_waits():
    mod = _load()
    rows = [
        ("2 weather slate", "2026-07-28", 24, 6),
        ("2 weather slate", "2026-07-29", 24, 0),
        ("1b/1 compute_elo read", "2026-07-28", 81, 6),
    ]
    families, days, cells = mod.pivot_family_by_day(rows)
    assert families == ["1b/1 compute_elo read", "2 weather slate"], "families must be sorted"
    assert days == ["2026-07-28", "2026-07-29"], "days must be sorted ascending"
    assert cells[("2 weather slate", "2026-07-28")] == "24/6"
    # The zero-wait cell must render as "24/0", NOT be dropped — "executions held while waits
    # went to zero" is the single most important reading in the table and an absent cell would
    # be indistinguishable from "the caller stopped".
    assert cells[("2 weather slate", "2026-07-29")] == "24/0"


def test_pivot_leaves_a_genuinely_absent_day_absent():
    """A family with NO rows on a day must not be fabricated as 0/0.

    That distinction is load-bearing: "no executions at all" (caller gone) and "executions with
    zero waits" (lever fired) are the two readings the table exists to separate.
    """
    mod = _load()
    families, days, cells = mod.pivot_family_by_day([
        ("A", "2026-07-28", 5, 1),
        ("B", "2026-07-29", 7, 0),
    ])
    assert days == ["2026-07-28", "2026-07-29"]
    assert ("A", "2026-07-29") not in cells
    assert ("B", "2026-07-28") not in cells


# ── measurement hygiene ──────────────────────────────────────────────────────────────────

def test_census_runs_on_the_monitoring_warehouse_only():
    src = _src()
    assert "get_monitoring_connection" in src, (
        "the census must connect via get_monitoring_connection (MONITOR_WH)."
    )
    assert not re.search(r"\bget_snowflake_connection\b", src), (
        "the census must NOT use get_snowflake_connection — that resolves to the warehouse under "
        "measurement (COMPUTE_WH), making the audit a line in its own results (target 3's "
        "self-inflicted-wake defect) and contaminating the baseline it is trying to read."
    )


def test_census_bounds_every_statement():
    """INC-32 — the per-day cut scans query_history unfiltered by wait (it needs the executions
    denominator), so it is the heaviest read in the script. An unbounded statement holds a
    MONITOR_WH session open indefinitely."""
    src = _src()
    assert re.search(r"STATEMENT_TIMEOUT_IN_SECONDS\s*=\s*\d+", src), (
        "the census must set a finite STATEMENT_TIMEOUT_IN_SECONDS (INC-32)."
    )


def test_perday_cut_selects_executions_as_well_as_waits():
    """The whole point is the executions DENOMINATOR — a waits-only cut cannot tell a fired gate
    from a stopped caller. Pin that the 4b query is not filtered down to waiting rows only."""
    src = _src()
    start = src.find("4b. PER-DAY")
    assert start != -1, "Table 4b (per-day × family) is missing from the census."
    block = src[start:start + 1400]
    assert "count(*) as execs" in block, "4b must report executions, not only waits."
    assert "sum(is_wait) as waits" in block, "4b must report waits alongside executions."
    assert "queued_provisioning_time > 0\n" not in block.replace("iff(queued_provisioning_time > 0", ""), (
        "4b must NOT filter to queued_provisioning_time > 0 in its WHERE clause — that would drop "
        "the executions denominator and reduce this cut to the aggregate it exists to replace."
    )
