"""test_ncaaf_odds_live.py — NCAAF-ODDS-LIVE: the ahead-of-kickoff board.

Football is bet days ahead. The P0.6b `/historical` catch-up structurally cannot serve that — it
only asks for a kickoff once `K − buffer` has passed — so a Saturday game had no line until
Friday at the earliest and, on the weekly cadence, not until after it was played. This feed adds
the missing half: the live bulk `/odds` board, captured on a tiered in-season cadence.

WHAT THESE GUARDS DEFEND, each a property rather than a preference:

  1. ⛔ **THE TABLE SEPARATION.** Live rows must never reach `odds_ncaaf_historical`.
     `build_clv_staging`'s default leg takes the latest pre-commence snapshot per event, so a live
     snapshot minutes before kickoff would silently BECOME "the close" — and P1.4's model
     selection and VAL1's CLV null were both decided on that mart. A serving convenience must not
     be able to move a recorded result.
  2. ⛔ **THE OVERWRITE LANDMINE.** `s3io.write_season_partition` is a season-grained
     `replaceWhere`. A naive fetch→write on an hourly cadence deletes the season every fire. The
     merge must ADD observations, and two snapshots of one event at different instants are two
     rows — that history IS the line-movement asset.
  3. 🔒 **IN-PLAY PRICES.** The live endpoint returns games already underway. An in-play price
     reaching a store a PRE-GAME line is served from is the one thing this surface must never do.
     Two independent defences, because a request parameter is one edit away from being dropped.
  4. ⏱️ **THE TIER IS A PURE FUNCTION**, so one rule answers for both the CLI and the op, and a
     non-capturing tick is legible rather than silent (the NF-FRESH1 19-green-runs class).
  5. 🕐 **FRESHEST WINS**, superseding NCAAF-P3.1b's fixed T-1-before-close order — and the
     leakage guard still binds every candidate.

⛔ `best_alpha = 0`. A market line is context beside the model, never a pick, and nothing here
computes a vs-market performance reading (VAL1's null stands).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.ingest import odds_live_capture as L
from quant_sports_intel_models.football.ncaaf.serving import payloads

_REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)


def _executable_only(src: str) -> str:
    """Source with docstrings and `#` comments removed, so a scan cannot be satisfied — or
    defeated — by prose (INC-38)."""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return "\n".join(re.sub(r"#.*$", "", line) for line in src.splitlines())


def _event(event_id: str, hours_ahead: float, home="TCU Horned Frogs",
           away="North Carolina Tar Heels") -> dict:
    return {"id": event_id, "home_team": home, "away_team": away,
            "commence_time": (NOW + timedelta(hours=hours_ahead)).isoformat().replace(
                "+00:00", "Z"),
            "bookmakers": [{"key": "bovada", "markets": []}]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The table separation — the one that can move a recorded result
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_live_feed_writes_its_own_table_never_the_clv_benchmark():
    """⛔ `odds_ncaaf_historical` is the leakage-safe CLV mart P1.4 and VAL1 were decided on. A
    live snapshot taken minutes before kickoff would become "the close" there, silently."""
    assert L.ODDS_LIVE_SOURCE == "odds_ncaaf_live"
    body = _executable_only(
        (_REPO / "quant_sports_intel_models/football/ncaaf/ingest/odds_live_capture.py").read_text())
    assert "odds_ncaaf_historical" not in body, (
        "the live capture names the CLV benchmark table in executable code")


def test_the_clv_mart_default_frame_cannot_see_the_live_feed():
    """The separation is the TABLE, and the default staging frame must carry no live column."""
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bake
    import inspect
    assert inspect.signature(bake.build_clv_staging).parameters["with_live"].default is False
    close_sql = bake._clv_sql("O", "G", 2020, kind=None, prefix="close_")
    assert bake._ODDS_LIVE_SOURCE not in close_sql
    # And a live_ column would be model-eligible, so it must never reach the default frame.
    frame = pd.DataFrame([{"live_home_spread": -6.5, "game_id": 1}])
    assert "live_home_spread" in bake.feature_columns(frame), (
        "premise stale — re-read why with_live must stay opt-in")


def test_the_live_source_name_matches_the_module_that_writes_it():
    """A staging read pointed at a table nothing writes returns silently EMPTY — a null that looks
    exactly like 'nobody priced this kickoff'."""
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bake
    assert bake._ODDS_LIVE_SOURCE == L.ODDS_LIVE_SOURCE


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The overwrite landmine — the merge must ADD, and keep the movement history
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_second_snapshot_of_the_same_event_is_a_second_row(tmp_path):
    """Two observations at different instants are two rows — that history IS the product."""
    first = L._tag([_event("evt-1", 48)], NOW)
    L._merge_and_write(2026, [dict(r) for r in first], local_root=str(tmp_path))
    later = L._tag([_event("evt-1", 48)], NOW + timedelta(hours=1))
    rows = L._merge_and_write(2026, [dict(r) for r in later], local_root=str(tmp_path))
    assert rows == 2, f"the hourly cadence collapsed its own movement history ({rows} row(s))"


def test_re_observing_the_same_instant_is_idempotent_not_a_duplicate(tmp_path):
    """A re-run of one tick must be a value-identical rewrite, not a second row."""
    recs = L._tag([_event("evt-1", 48), _event("evt-2", 72)], NOW)
    L._merge_and_write(2026, [dict(r) for r in recs], local_root=str(tmp_path))
    rows = L._merge_and_write(2026, [dict(r) for r in recs], local_root=str(tmp_path))
    assert rows == 2


def test_a_new_tick_never_deletes_a_prior_season_partition(tmp_path):
    """⛔ THE LANDMINE: `write_season_partition` is a season-grained `replaceWhere`, so a naive
    fetch→write would delete every prior observation on EVERY fire."""
    L._merge_and_write(2026, L._tag([_event("a", 48)], NOW), local_root=str(tmp_path))
    L._merge_and_write(2026, L._tag([_event("b", 50)], NOW + timedelta(hours=1)),
                       local_root=str(tmp_path))
    rows = L._merge_and_write(2026, L._tag([_event("c", 52)], NOW + timedelta(hours=2)),
                              local_root=str(tmp_path))
    assert rows == 3, f"a later tick destroyed earlier observations ({rows} row(s) survive)"


def test_the_merge_key_is_the_event_and_the_instant():
    """Keying on the event alone would keep one row per game and throw the movement away."""
    tagged = L._tag([_event("evt-1", 48)], NOW)[0]
    assert L._event_key(json.dumps(tagged)) == ("evt-1", L._iso(NOW))


def test_an_unreadable_existing_partition_raises_rather_than_overwriting(tmp_path, monkeypatch):
    """`_merge_and_write` treats `None` as 'nothing captured yet' and overwrites. So a transient
    read failure must RAISE on the way in, never be guessed as empty."""
    monkeypatch.setattr(L.query_lake, "query_or_missing",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("s3 blip")))
    with pytest.raises(RuntimeError):
        L._merge_and_write(2026, L._tag([_event("a", 48)], NOW), local_root=str(tmp_path))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. In-play prices — two independent defences
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_game_already_underway_is_dropped_before_it_can_be_stored():
    kept, dropped = L._pre_kickoff_only(
        [_event("upcoming", 48), _event("in_play", -0.5), _event("kicking_off_now", 0)], NOW)
    assert [r["id"] for r in kept] == ["upcoming"]
    assert dropped == 2, "a game at or past kickoff reached the store"


def test_an_unreadable_kickoff_is_dropped_rather_than_guessed():
    """A check that cannot run is not a pass (NF1.7 (a))."""
    bad = {"id": "x", "commence_time": "not-a-timestamp", "home_team": "a", "away_team": "b"}
    missing = {"id": "y", "home_team": "a", "away_team": "b"}
    kept, dropped = L._pre_kickoff_only([bad, missing], NOW)
    assert kept == [] and dropped == 2


def test_the_request_itself_excludes_started_games():
    """The FIRST defence: without `commenceTimeFrom` the endpoint returns in-play games at all."""
    captured = {}

    class _Ctx:
        odds_regions = "us"

    def _fake(ctx, path, params):
        captured.update(params)
        return []

    import quant_sports_intel_models.football.ncaaf.ingest.sources as S
    original = S._odds_get
    S._odds_get = _fake
    try:
        S._odds_ncaaf(_Ctx(), 2026, commence_from="2026-08-27T18:00:00Z")
    finally:
        S._odds_get = original
    assert captured.get("commenceTimeFrom") == "2026-08-27T18:00:00Z"


def test_the_capture_actually_passes_the_snapshot_instant_as_the_request_bound():
    """WIRED ≠ INVOKED (NF-C0e). `_odds_ncaaf` ACCEPTING a `commence_from` proves nothing about
    whether the capture SENDS one — that wiring is the first defence, and it needs its own
    assertion or deleting it is invisible."""
    captured = {}

    class _Ctx:
        odds_regions = "us"

    import quant_sports_intel_models.football.ncaaf.ingest.sources as S
    original = S._odds_get
    S._odds_get = lambda ctx, path, params: (captured.update(params), [])[1]
    try:
        L.fetch_live_board(_Ctx(), now=NOW)
    finally:
        S._odds_get = original
    assert captured.get("commenceTimeFrom") == L._iso(NOW), (
        "the capture does not bound its own request to upcoming games")


def test_the_two_defences_are_independent():
    """If the request parameter were the only guard, dropping it would silently re-open the hole.
    `_pre_kickoff_only` runs on whatever came back, regardless of what was asked for."""
    kept, dropped = L._pre_kickoff_only([_event("in_play", -1)], NOW)
    assert kept == [] and dropped == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The tier — one rule, and it says why on both branches
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_inside_the_dense_window_every_hour_captures():
    kicks = [NOW + timedelta(hours=6)]
    for hour in range(24):
        now = NOW.replace(hour=hour)
        capture, why = L.should_capture([now + timedelta(hours=6)], now=now)
        assert capture, f"hour {hour} skipped inside the dense window: {why}"
        assert "dense" in why


def test_outside_the_dense_window_only_a_six_hourly_tick_captures():
    kicks = [NOW + timedelta(days=5)]
    fired = [h for h in range(24)
             if L.should_capture(kicks, now=NOW.replace(hour=h))[0]]
    assert fired == [0, 6, 12, 18], f"the baseline tier is not 6-hourly: {fired}"


def test_the_boundary_of_the_dense_window_is_inclusive_and_stated():
    # ⚠️ The kickoffs are built relative to `at`, NOT to NOW: an hour-3 tick is 39h from a
    # NOW+24h kickoff, so a NOW-relative fixture would test a different window than it names.
    at = NOW.replace(hour=3)   # not a baseline tick, so ONLY the dense rule can fire
    assert L.should_capture([at + timedelta(hours=L.DENSE_WINDOW_HOURS)], now=at)[0] is True
    assert L.should_capture(
        [at + timedelta(hours=L.DENSE_WINDOW_HOURS, minutes=1)], now=at)[0] is False


def test_a_skipped_tick_says_why_and_costs_nothing():
    """A silent skip is indistinguishable from a schedule that stopped firing (NF-FRESH1)."""
    capture, why = L.should_capture([NOW + timedelta(days=5)], now=NOW.replace(hour=3))
    assert capture is False
    assert "0 credits" in why and "kickoff" in why


def test_an_off_season_tick_with_no_kickoffs_still_keeps_the_baseline():
    capture, why = L.should_capture([], now=NOW.replace(hour=12))
    assert capture is True and "baseline" in why
    assert L.should_capture([], now=NOW.replace(hour=13))[0] is False


def test_the_tier_is_pure_so_the_cli_and_the_op_ask_the_same_question():
    """E9.61: two callers of one rule must not become two rules."""
    import inspect
    src = inspect.getsource(L.run_live_capture)
    assert "should_capture(" in src
    # ⚠️ Comment- and docstring-stripped: the op's docstring EXPLAINS the tier and names
    # `should_capture`, so a raw scan is satisfied by the prose it was written to police —
    # INC-38's lesson pointing the other way (prose DEFEATING a guard rather than satisfying one).
    job = _executable_only((_REPO / "pipeline/jobs/sports_ncaaf_odds_live_job.py").read_text())
    assert "run_live_capture(" in job, "the op does not call the shared driver at all"
    assert "should_capture" not in job, (
        "the op re-implements the tier decision instead of delegating to it")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Season placement, cost, and the serving read
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_january_bowl_is_filed_under_the_season_that_began_in_august():
    """The live board reaches ~93 days out, so in December it spans a season boundary. Filing a
    January bowl under the wrong season puts it in a partition the serving read never looks at."""
    assert L.season_for_kickoff("2026-08-29T16:00:00Z") == 2026
    assert L.season_for_kickoff("2027-01-09T00:30:00Z") == 2026
    assert L.season_for_kickoff("2027-08-28T16:00:00Z") == 2027


def test_one_live_call_prices_the_whole_board_far_cheaper_than_the_historical_loop():
    """The measured asymmetry this feed rests on: 3 credits for every upcoming game at once,
    against 30 per ±30-min kickoff window for `/historical`."""
    from quant_sports_intel_models.football.ncaaf.ingest import odds_recurring_capture as C
    assert L.estimate_credits("us") == 3
    assert C._estimate_credits(1, "us")["credits"] == 30


def test_the_serving_read_opts_into_the_live_leg():
    src = (_REPO / "scripts/write_ncaaf_serving_store.py").read_text()
    assert "build_clv_staging(min_year=int(season), with_t1=True, with_live=True)" in src


def test_the_live_line_wins_when_it_is_the_freshest_observation():
    """The upcoming-board case: a live line captured today beside a T-1 from a prior slate."""
    kickoff = "2026-08-29T23:30:00.000Z"
    row = {"live_home_spread": -9.0, "live_total": 46.5, "live_home_ml_american": -340.0,
           "live_home_ml_prob": 0.77, "live_snapshot_ts": "2026-08-28T01:38:24Z",
           "t1_home_spread": -6.5, "t1_total": 55.5, "t1_home_ml_american": -240.0,
           "t1_home_ml_prob": 0.70, "t1_snapshot_ts": "2026-08-27T12:00:00Z"}
    block = payloads._market(row, read_failed=False, commence_time=kickoff, game_id=1)
    assert block["source"] == payloads.MARKET_SOURCE_LIVE
    assert block["home_spread"] == -9.0
    assert block["as_of"] == "2026-08-28T01:38:24Z"


def test_a_live_line_after_kickoff_is_refused_like_any_other():
    """The serving-side leakage guard binds the live leg too — a third defence behind the two in
    the capture, because an in-play price is the failure this whole design is shaped around."""
    kickoff = "2026-08-29T23:30:00.000Z"
    row = {"live_home_spread": -9.0, "live_total": 46.5, "live_home_ml_american": -340.0,
           "live_home_ml_prob": 0.77, "live_snapshot_ts": "2026-08-30T01:00:00Z"}
    block = payloads._market(row, read_failed=False, commence_time=kickoff, game_id=1)
    assert block["status"] == "unavailable"
    assert block["reason"] == payloads.MARKET_REASON_NOT_PRE_KICKOFF


def test_the_accent_fold_is_live_leg_only_so_the_clv_mart_population_is_unchanged():
    """⭐ Measured 2026-08-27: the raw prefix join misses `San José State` and `Hawai'i` — 2 of the
    8 opener games. Folding fixes them, but applying it to the DEFAULT leg would ADD rows to the
    mart P1.4's selection and VAL1's null were decided on, so it stays opt-in."""
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bake
    plain = bake._clv_sql("O", "G", 2026, kind=None, prefix="close_")
    folded = bake._clv_sql("O", "G", 2026, kind=None, prefix="live_", accent_fold=True)
    assert "strip_accents" not in plain, "the DEFAULT leg's join predicate changed"
    assert "strip_accents" in folded
    src = (_REPO / "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_game.py").read_text()
    assert re.search(r"prefix=\"live_\",\s*\n\s*missing_ok=True, accent_fold=True", src), (
        "accent folding is not scoped to the live leg")


def test_the_fold_still_refuses_a_genuinely_different_school():
    """A looser join must not become a WRONG one: Miami (OH) is not Miami."""
    import duckdb
    c = duckdb.connect()
    n = "lower(regexp_replace(strip_accents(?), '[^a-zA-Z0-9 ]', '', 'g'))"
    q = f"select {n} like {n} || '%'"
    assert c.execute(q, ["San Jose State Spartans", "San José State"]).fetchone()[0] is True
    assert c.execute(q, ["Hawaii Rainbow Warriors", "Hawai'i"]).fetchone()[0] is True
    assert c.execute(q, ["Miami Hurricanes", "Miami (OH)"]).fetchone()[0] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Orchestration — one owner, gated, and it logs on both branches
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_there_is_exactly_one_cron_for_this_job():
    """Two crons for one logical job is this repo's most-repeated operational defect (INC-30 /
    INC-36 / INC-38). The tier lives in the op, not in a second schedule."""
    from pipeline.schedules import sports_odds_capture_schedules as sch
    crons = [v for k, v in vars(sch).items()
             if k.startswith("NCAAF_ODDS_LIVE") and isinstance(v, str)]
    assert crons == ["0 * * 8-12,1 *"], crons
    assert sch.sports_ncaaf_odds_live_schedule.cron_schedule == crons[0]


def test_the_paid_schedule_ships_stopped():
    """It spends real credits on every capturing tick; turning it on is a deliberate operator act
    (the E11.23 carve-out the sibling paid capture already takes)."""
    from dagster import DefaultScheduleStatus
    from pipeline.schedules import sports_ncaaf_odds_live_schedule as s
    assert s.default_status == DefaultScheduleStatus.STOPPED


def test_the_job_and_schedule_are_registered():
    from pipeline.jobs import sports_ncaaf_odds_live_job
    from pipeline.schedules import sports_ncaaf_odds_live_schedule
    assert sports_ncaaf_odds_live_job.name == "sports_ncaaf_odds_live_job"
    assert sports_ncaaf_odds_live_schedule.job.name == sports_ncaaf_odds_live_job.name


def test_the_op_logs_on_both_branches_so_a_quiet_tick_is_legible():
    """An op that succeeds silently over a frozen artifact is the NF-FRESH1 19-green-runs class,
    and a cheap always-succeeding tick is exactly the shape that invites it."""
    body = _executable_only((_REPO / "pipeline/jobs/sports_ncaaf_odds_live_job.py").read_text())
    assert 'if not manifest.get("captured")' in body and body.count("context.log") >= 4
    assert 'if not manifest.get("events")' in body, (
        "a capture that stored ZERO events during the season passes silently")


def test_the_capture_is_warn_tier_and_never_fails_its_job():
    src = (_REPO / "pipeline/jobs/sports_ncaaf_odds_live_job.py").read_text()
    assert "except Exception as exc:" in src and "raise" not in src.split("def ncaaf_odds")[1]
