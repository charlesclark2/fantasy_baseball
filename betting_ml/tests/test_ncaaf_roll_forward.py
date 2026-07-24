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

from datetime import date

from quant_sports_intel_models.football.ncaaf.ingest import roll_forward as rf
from quant_sports_intel_models.football.ncaaf.ingest import sources as src


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
