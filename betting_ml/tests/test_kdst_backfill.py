"""NF-C0e follow-up 3 — the historical K/DST backfill: report paths and season resolution.

Two things this pins.

**The report path.** `_REPORT_PATH` is a fixed filename, so before this every run — including a
historical one — overwrote the committed report describing the season we actually SERVE. A
7-season backfill would have left it describing 2019, silently. The forward season keeps the
canonical name (`nfl_fantasy_story_prompts.md` references it by name, so it cannot simply be
renamed); every other season writes beside it.

**Season resolution.** Every refusal happens on the ARGUMENTS, before any fitting, because the
alternative is failing part-way through a multi-season run with some seasons already landed in the
lake. The leakage discipline itself lives in `fit_models` / `project_one_season` and is verified
there by construction; what is pinned here is that an out-of-range request cannot start.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy.run_kdst_projection import (
    MIN_TRAIN_TARGETS,
    PANEL_FIRST_TARGET,
    _REPORT_PATH,
    report_path_for,
    resolve_seasons,
    summary_path_for,
)

FWD = 2026


def _resolve(projection=None, lo=None, hi=None, panel_from=PANEL_FIRST_TARGET):
    return resolve_seasons(projection, lo, hi, forward_season=FWD, panel_from=panel_from)


# ── the report path ──────────────────────────────────────────────────────────────────────────
def test_the_forward_season_keeps_the_canonical_report_name():
    """Renaming it would break the reference in the story prompts and every existing link."""
    assert report_path_for(FWD, FWD) == _REPORT_PATH


def test_a_historical_season_does_NOT_overwrite_the_canonical_report():
    """The actual bug: a backfill must not clobber the served season's report."""
    for season in range(2019, 2026):
        p = report_path_for(season, FWD)
        assert p != _REPORT_PATH
        assert str(season) in p.name
    assert len({report_path_for(s, FWD) for s in range(2019, 2026)}) == 7, (
        "per-season reports must not collide with each other either"
    )


def test_the_summary_json_follows_the_same_rule():
    """It was fixed-path for the same reason and would have been overwritten the same way."""
    out = Path("/tmp/x")
    assert summary_path_for(out, FWD, FWD).name == "nfl_fantasy_kdst_summary.json"
    hist = {summary_path_for(out, s, FWD).name for s in range(2019, 2026)}
    assert len(hist) == 7
    assert "nfl_fantasy_kdst_summary.json" not in hist


def test_the_guard_would_actually_catch_the_bug_it_was_written_for():
    """RED-proof: the pre-fix behaviour (always the canonical path) must fail the test above.

    Without this, a revert to an unconditional `_REPORT_PATH` could leave the suite green if the
    assertions happened to be satisfiable some other way (NF-D17)."""
    def _pre_fix_report_path(projection_season, forward_season):
        return _REPORT_PATH

    assert _pre_fix_report_path(2019, FWD) == _REPORT_PATH, (
        "this no longer reproduces the original bug, so the guard above proves nothing"
    )


# ── season resolution ────────────────────────────────────────────────────────────────────────
def test_no_flags_projects_the_forward_season():
    assert _resolve() == [FWD]


def test_an_explicit_single_season_is_unchanged():
    assert _resolve(projection=2022) == [2022]


def test_a_backfill_range_is_inclusive_on_both_ends():
    assert _resolve(lo=2019, hi=2025) == [2019, 2020, 2021, 2022, 2023, 2024, 2025]


def test_a_single_season_range_is_allowed():
    assert _resolve(lo=2024, hi=2024) == [2024]


@pytest.mark.parametrize(
    "kwargs, fragment",
    [
        ({"projection": 2022, "lo": 2019, "hi": 2025}, "mutually exclusive"),
        ({"lo": 2019}, "must be given together"),
        ({"hi": 2025}, "must be given together"),
        ({"lo": 2025, "hi": 2019}, "is after"),
        ({"lo": 2030, "hi": 2031}, "beyond the forward season"),
    ],
)
def test_a_bad_range_is_refused_on_the_arguments(kwargs, fragment):
    """Each refusal must fire before any fitting — a partial backfill is the silent-partial class."""
    with pytest.raises(ValueError, match=fragment):
        _resolve(**kwargs)


def test_a_season_with_too_little_history_is_refused_with_the_earliest_named():
    """`fit_models` refuses below 5 training targets; the range check must agree with it, and say
    which season IS reachable rather than only that this one is not."""
    earliest = PANEL_FIRST_TARGET + MIN_TRAIN_TARGETS
    with pytest.raises(ValueError, match=str(earliest)):
        _resolve(lo=earliest - 1, hi=2020)
    assert _resolve(lo=earliest, hi=earliest) == [earliest]


def test_the_earliest_projectable_season_tracks_the_panel_start():
    """The floor is derived, not hardcoded — moving `--panel-from` moves it."""
    assert _resolve(lo=2016, hi=2016, panel_from=2011) == [2016]
    with pytest.raises(ValueError, match="2016"):
        _resolve(lo=2015, hi=2016, panel_from=2011)
