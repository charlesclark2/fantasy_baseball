"""Fast-gate unit tests for the NCAAF-P0.7 pre-season season roll-forward.

Pure logic only — no network, no S3 (the ingest itself is mocked). Guards:
  * `current_season()` is CLOCK-DERIVED and never pinned (the P0.6 stale-by-a-season landmine),
    and stays the exact complement of `last_completed_season()`.
  * `ROLL_FORWARD_SOURCES` is the cheap schedule+covariate set only — no paid/on_demand odds
    source and no expensive per-game endpoint can slip into the recurring cadence.
  * `run_roll_forward()` pins the season to the clock-derived target + the source set to
    ROLL_FORWARD_SOURCES, and surfaces not-yet-published (0-row) covariates.

Fast-gate discipline: imports only from the ncaaf ingest package (import-safe — no `pipeline`,
no dbt manifest), so it collects cleanly in the fast gate.
"""
from __future__ import annotations

import pathlib
import re
from datetime import date

from quant_sports_intel_models.football.ncaaf.ingest import roll_forward as rf
from quant_sports_intel_models.football.ncaaf.ingest import sources as src

_REPO = pathlib.Path(__file__).resolve().parents[2]


# ── current_season(): clock-derived, the roll-forward target ─────────────────────────────
def test_current_season_is_clock_derived():
    # Mid-summer 2026: the upcoming season is 2026 (opens Aug 2026).
    assert src.current_season(date(2026, 7, 24)) == 2026
    # February onward: the upcoming season is THIS calendar year.
    assert src.current_season(date(2026, 2, 1)) == 2026
    # In-progress season (Oct 2026): still 2026.
    assert src.current_season(date(2026, 10, 1)) == 2026
    # January 2027: the 2026 season is still finishing its bowls/CFP → still current.
    assert src.current_season(date(2027, 1, 5)) == 2026
    # February 2027: the roll-forward target advances to 2027 — re-runnable next year, no code change.
    assert src.current_season(date(2027, 2, 1)) == 2027
    # Next August: 2027, unchanged code path (the annual cadence).
    assert src.current_season(date(2027, 8, 15)) == 2027


def test_current_season_is_complement_of_last_completed():
    # By construction current == last_completed + 1 at EVERY point on the calendar.
    for d in [date(2026, 1, 15), date(2026, 7, 24), date(2026, 12, 31),
              date(2027, 1, 5), date(2027, 2, 1), date(2027, 8, 15)]:
        assert src.current_season(d) == src.last_completed_season(d) + 1


# ── ROLL_FORWARD_SOURCES: the cheap schedule + covariate set only ────────────────────────
def test_roll_forward_sources_all_registered_and_free():
    assert src.ROLL_FORWARD_SOURCES, "the roll-forward set must not be empty"
    for name in src.ROLL_FORWARD_SOURCES:
        assert name in src.SOURCES, f"{name} is not a registered source"
        spec = src.SOURCES[name]
        # A routine pre-season refresh must never burn Odds credits or hit an on_demand pull.
        assert spec.tier == "cfbd", f"{name} is not a (free) CFBD source"
        assert not spec.on_demand, f"{name} is an on_demand/paid source — must not be in the cadence"


def test_roll_forward_excludes_expensive_per_game_endpoints():
    # The ~960-call/season per-game endpoints (and every odds source) are DELIBERATELY excluded —
    # they only exist once games are played and would blow the cheap-weekly-refresh budget.
    for expensive in ("plays", "play_stats", "box_advanced", "drives",
                      "odds_ncaaf", "odds_ncaaf_historical"):
        assert expensive not in src.ROLL_FORWARD_SOURCES


def test_roll_forward_covers_schedule_and_the_p1_2_covariates():
    # The schedule + structure, and the exact P0.4/P0.5/P1.2b covariate priors P1.2 fits on.
    for required in ("games", "teams", "returning_production", "transfer_portal", "roster",
                     "talent", "coaches", "recruiting_players"):
        assert required in src.ROLL_FORWARD_SOURCES


# ── run_roll_forward(): pins season + source set, surfaces empty covariates ───────────────
def test_run_roll_forward_defaults_to_current_season_and_source_set(monkeypatch):
    captured = {}

    def fake_run_ingest(seasons, *, sources, bucket, local_root, ctx):
        captured["seasons"] = seasons
        captured["sources"] = sources
        # a realistic pre-season manifest: schedule + some covariates landed, some not published yet
        return {
            f"games/{seasons[0]}": 888,
            f"teams/{seasons[0]}": 138,
            f"transfer_portal/{seasons[0]}": 4433,
            f"recruiting_players/{seasons[0]}": 3107,
            f"returning_production/{seasons[0]}": 0,   # not yet published
            f"talent/{seasons[0]}": 0,
            f"coaches/{seasons[0]}": 0,
            f"roster/{seasons[0]}": 0,
            "_cfbd_calls_remaining": 58800,
        }

    monkeypatch.setattr(rf, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(rf, "build_ctx", lambda: object())  # no real CFBD client

    manifest = rf.run_roll_forward(season=2026)
    assert captured["seasons"] == [2026]
    assert captured["sources"] == list(src.ROLL_FORWARD_SOURCES)
    # the four not-yet-published covariates are reported as 0-row, not errors
    assert manifest["returning_production/2026"] == 0
    assert manifest["games/2026"] == 888


def test_run_roll_forward_uses_clock_derived_season_when_unset(monkeypatch):
    seen = {}

    def fake_run_ingest(seasons, *, sources, bucket, local_root, ctx):
        seen["season"] = seasons[0]
        return {f"games/{seasons[0]}": 1}

    monkeypatch.setattr(rf, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(rf, "build_ctx", lambda: object())
    rf.run_roll_forward()  # no season → current_season()
    assert seen["season"] == src.current_season()


# ══════════════════════════════════════════════════════════════════════════════════════════
# NCAAF-RF1 — the roll-forward WINDOW guard (2026-08-24)
# ══════════════════════════════════════════════════════════════════════════════════════════
# `NCAAF_ROLL_FORWARD_CRON` used to be `0 6 * 2-8 1` (Mondays, Feb–Aug). Its last fire was Mon
# 2026-08-31, after which every roll-forward feed would have stopped advancing until Feb 2027 —
# through the whole season. That is the E9.48(c) / INC-37 month-scoped-cron class; RF1 widened the
# window to one full season cycle and these guards keep it there.
#
# SOURCE-READ, NOT IMPORT: the constant lives in `pipeline/schedules/`, and `pipeline/__init__.py`
# reads the gitignored dbt manifest at IMPORT — a fast-gate test that imports it dies at COLLECTION
# (E11.23). Reading the file keeps this module fast-gate-clean.

_SCHEDULE_SRC = _REPO / "pipeline/schedules/sports_rollforward_schedules.py"
_BOX_OPS = _REPO / "services/dagster/aws/BOX_OPERATIONS.md"


def _declared_cron() -> str:
    """The cron literal as the SCHEDULE declares it (code, not prose)."""
    m = re.search(r'^NCAAF_ROLL_FORWARD_CRON = "([^"]+)"', _SCHEDULE_SRC.read_text(), re.M)
    assert m, "NCAAF_ROLL_FORWARD_CRON assignment not found — did the constant move or rename?"
    return m.group(1)


def _expand_months(field: str) -> set[int]:
    """`2-12,1` → {1,…,12}. A cron month field is comma-separated ranges/singletons."""
    months: set[int] = set()
    for part in field.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            months.update(range(lo, hi + 1))
        else:
            months.add(int(part))
    return months


def test_the_roll_forward_cron_covers_a_full_season_cycle():
    """The whole point of RF1: the window must not end in August.

    Asserted on the cron VALUE, so no amount of explanatory comment can satisfy it (INC-38).
    """
    minute, hour, dom, month, dow = _declared_cron().split()
    # Unchanged by RF1 — the cadence itself (weekly Monday 06:00 PT) is not what was broken.
    assert (minute, hour, dom, dow) == ("0", "6", "*", "1"), (
        f"expected a weekly Monday 06:00 fire, got {_declared_cron()!r}")

    months = _expand_months(month)
    # The IN-SEASON months are the regression this guard exists for. Sep–Dec plus January (bowls /
    # the CFP run into mid-January) is the Aug–Jan convention every other NCAAF schedule uses.
    missing = {9, 10, 11, 12, 1} - months
    assert not missing, (
        f"SEASONAL BOUNDARY HOLE (E9.48(c) / INC-37): the roll-forward cron {_declared_cron()!r} "
        f"does not fire in month(s) {sorted(missing)}. Every roll-forward feed — `talent` above "
        f"all — would stop advancing for the season, and the NCAAF-PS snapshots are IMMUTABLE, so "
        f"the forward track record would be permanently missing it.")
    # …and the pre-season churn window RF1 must not have traded away to buy the in-season half.
    assert {2, 3, 4, 5, 6, 7, 8} <= months, (
        f"the Feb–Aug pre-season window regressed: {_declared_cron()!r}")


def test_the_retired_february_to_august_window_is_gone():
    """A presence-only check cannot see a partial edit. Assert the RETIRED expression ABSENT from
    the constant itself (NF-DTB-1) — while allowing the comment to keep NAMING `2-8`, which is
    exactly what the incident note must do to stay legible."""
    assert _declared_cron() != "0 6 * 2-8 1", (
        "the pre-RF1 Feb–Aug cron is back — see the ⚠️ NCAAF-RF1 note at the constant")
    assert "2-8" not in _declared_cron().split()[3], (
        f"the month field still carries the retired `2-8` range: {_declared_cron()!r}")


def test_the_documented_window_matches_the_cron_constant():
    """ONE THING, ONE OWNER: `BOX_OPERATIONS.md §10` is the operator's intended-state table, and a
    doc that disagrees with the schedule is the `W7B_LAKEHOUSE_S3` documented-but-never-set class.
    The §10 row quotes the cron literally; this pins the two together so drift fails CI."""
    rows = [ln for ln in _BOX_OPS.read_text().splitlines()
            if ln.startswith("|") and "`sports_ncaaf_roll_forward_schedule`" in ln]
    assert len(rows) == 1, (
        f"expected exactly one §10 intended-state row for the NCAAF roll-forward, found {len(rows)}")
    m = re.search(r"declared cron `([^`]+)`", rows[0])
    assert m, ("the §10 row must state the schedule's cron as ``declared cron `<expr>` `` so it can "
               "be pinned against the code")
    assert m.group(1) == _declared_cron(), (
        f"BOX_OPERATIONS.md §10 documents cron {m.group(1)!r} but the schedule declares "
        f"{_declared_cron()!r} — update BOTH in the same change.")


def test_the_cron_carries_the_incident_and_the_defect_class():
    """AC1: a future reader must find out from the code WHY the window is a full cycle.

    ⚠️ Deliberately a COMMENT scan — the requirement here IS about the comment. Every assertion on
    the cron's BEHAVIOUR above reads the value instead, so prose can satisfy this one and only this
    one (the INC-38 rule is that a *behavioural* guard must not be comment-satisfiable)."""
    lines = _SCHEDULE_SRC.read_text().splitlines()
    idx = next(i for i, ln in enumerate(lines)
               if ln.startswith('NCAAF_ROLL_FORWARD_CRON = "'))
    # Walk back over the CONTIGUOUS comment block immediately above the constant — not the whole
    # module docstring, which already says "talent" for unrelated reasons and would make this pass
    # on prose that has nothing to do with the incident.
    j = idx
    while j > 0 and lines[j - 1].lstrip().startswith("#"):
        j -= 1
    note = "\n".join(lines[j:idx])
    assert note.strip(), "the cron constant carries no comment block at all"
    for token in ("NCAAF-RF1", "E9.48", "INC-37", "talent"):
        assert token in note, (
            f"the comment block at NCAAF_ROLL_FORWARD_CRON must name {token!r} — a future reader "
            f"has to be able to find out from the code why this window is a full season cycle")
