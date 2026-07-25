"""Fast-gate unit tests for the NF-D1 NFL season roll-forward.

Pure logic only — no network, no S3 (the ingest itself is mocked). Guards:
  * `current_season()` is CLOCK-DERIVED and never pinned (the NCAAF-P0.6 stale-by-a-season
    landmine), and stays the exact complement of `last_completed_season()`.
  * `ROLL_FORWARD_SOURCES` is the cheap roster/schedule/depth-chart/injuries/rookie-class set
    only — no paid/on_demand odds source and no realized-game (pbp/stats/snap/NGS/PFR) endpoint
    can slip into the recurring cadence.
  * `run_roll_forward()` pins the season to the clock-derived target + the source set to
    ROLL_FORWARD_SOURCES, and surfaces not-yet-published (0-row) feeds.

Fast-gate discipline: imports only from the nfl ingest package (import-safe — no `pipeline`,
no dbt manifest), so it collects cleanly in the fast gate. Mirrors
`test_ncaaf_roll_forward.py` (NCAAF-P0.7).
"""
from __future__ import annotations

from datetime import date

from quant_sports_intel_models.football.nfl.ingest import roll_forward as rf
from quant_sports_intel_models.football.nfl.ingest import sources as src


# ── current_season(): clock-derived, the roll-forward target ─────────────────────────────
def test_current_season_is_clock_derived():
    # Draft season / mid-summer 2026: the upcoming season is 2026 (opens Sep 2026).
    assert src.current_season(date(2026, 7, 25)) == 2026
    # March onward: the upcoming season is THIS calendar year (free agency under way).
    assert src.current_season(date(2026, 3, 1)) == 2026
    # In-progress season (Oct 2026): still 2026.
    assert src.current_season(date(2026, 10, 1)) == 2026
    # January 2027: the 2026 season's playoffs/Super Bowl may still be in progress → still current.
    assert src.current_season(date(2027, 1, 15)) == 2026
    # February 2027: the Super Bowl window — still conservatively current (mirrors NCAAF's
    # January-bowls conservatism, just with NFL's later championship pushing the threshold to Mar).
    assert src.current_season(date(2027, 2, 10)) == 2026
    # March 2027: the roll-forward target advances to 2027 — re-runnable next year, no code change.
    assert src.current_season(date(2027, 3, 1)) == 2027
    # Next August: 2027, unchanged code path (the annual cadence).
    assert src.current_season(date(2027, 8, 15)) == 2027


def test_current_season_is_complement_of_last_completed():
    # By construction current == last_completed + 1 at EVERY point on the calendar.
    for d in [date(2026, 1, 15), date(2026, 3, 1), date(2026, 7, 25), date(2026, 12, 31),
              date(2027, 1, 15), date(2027, 3, 1), date(2027, 8, 15)]:
        assert src.current_season(d) == src.last_completed_season(d) + 1


# ── ROLL_FORWARD_SOURCES: the cheap roster/schedule/depth-chart/rookie-class set only ─────
def test_roll_forward_sources_all_registered_and_free():
    assert src.ROLL_FORWARD_SOURCES, "the roll-forward set must not be empty"
    for name in src.ROLL_FORWARD_SOURCES:
        assert name in src.SOURCES, f"{name} is not a registered source"
        spec = src.SOURCES[name]
        # A routine roll-forward refresh must never burn Odds credits or hit an on_demand pull.
        assert spec.tier == "nflverse", f"{name} is not a (free) nflverse source"
        assert not spec.on_demand, f"{name} is an on_demand/paid source — must not be in the cadence"


def test_roll_forward_excludes_realized_game_and_odds_endpoints():
    # The realized-game stack (only exists once games are PLAYED) and every odds source are
    # DELIBERATELY excluded — they'd just be repeated 404-clean-skips for an unplayed season and
    # would blow the cheap-weekly-refresh budget / burn Odds credits.
    for excluded in (
        "pbp", "pbp_participation", "ftn_charting", "snap_counts",
        "stats_player_week", "stats_player_reg", "stats_player_post", "stats_team_week",
        "ngs_passing", "ngs_rushing", "ngs_receiving",
        "pfr_advstats_week_pass", "pfr_advstats_season_pass",
        "qbr_week", "qbr_season", "officials", "nflverse_players",
        "odds_nfl", "odds_nfl_scores", "odds_nfl_props",
        "odds_nfl_historical", "odds_nfl_props_historical",
    ):
        assert excluded not in src.ROLL_FORWARD_SOURCES


def test_roll_forward_covers_rosters_schedule_depth_charts_and_rookie_class():
    for required in ("rosters", "weekly_rosters", "schedules", "depth_charts",
                      "injuries", "nflverse_draft_picks", "nflverse_combine"):
        assert required in src.ROLL_FORWARD_SOURCES


# ── run_roll_forward(): pins season + source set, surfaces empty feeds ────────────────────
def test_run_roll_forward_defaults_to_current_season_and_source_set(monkeypatch):
    captured = {}

    def fake_run_ingest(seasons, *, sources, bucket, local_root, ctx):
        captured["seasons"] = seasons
        captured["sources"] = sources
        # a realistic pre-camp manifest: rosters/schedule/depth_charts/draft/combine landed,
        # injuries not yet published (pre-camp).
        return {
            f"rosters/{seasons[0]}": 2930,
            f"weekly_rosters/{seasons[0]}": 2930,
            f"schedules/{seasons[0]}": 272,
            f"depth_charts/{seasons[0]}": 365771,
            f"nflverse_draft_picks/{seasons[0]}": 257,
            f"nflverse_combine/{seasons[0]}": 319,
            f"injuries/{seasons[0]}": 0,   # not yet published
        }

    monkeypatch.setattr(rf, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(rf, "build_ctx", lambda: object())  # no real Odds client needed

    manifest = rf.run_roll_forward(season=2026)
    assert captured["seasons"] == [2026]
    assert captured["sources"] == list(src.ROLL_FORWARD_SOURCES)
    # the not-yet-published feed is reported as 0-row, not an error
    assert manifest["injuries/2026"] == 0
    assert manifest["rosters/2026"] == 2930


def test_run_roll_forward_uses_clock_derived_season_when_unset(monkeypatch):
    seen = {}

    def fake_run_ingest(seasons, *, sources, bucket, local_root, ctx):
        seen["season"] = seasons[0]
        return {f"schedules/{seasons[0]}": 1}

    monkeypatch.setattr(rf, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(rf, "build_ctx", lambda: object())
    rf.run_roll_forward()  # no season → current_season()
    assert seen["season"] == src.current_season()
