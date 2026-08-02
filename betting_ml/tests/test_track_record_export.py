"""NF3.2 — the fantasy football past-season track-record backtest surface.

Pure/offline: tiny synthetic frames, no DuckDB/S3/network. Covers:
  * `benchmark_scorecard.player_track_record_frame` — the per-player materialization behind the
    NF-D3 scorecard's aggregate "adp" numbers (rank directions, the g>=6 filter, and — the important
    one — that its `is_fade` flag is EXACTLY the same set `_disagreement_frame` would compute on the
    identical merged input, never a parallel re-derivation).
  * `export_track_record_json.build_headline` — the honest-claim denylist (reused verbatim from
    `test_nf1_5b_served_board.py`) plus the "no ADP aggregate -> refuse" guard.
  * `export_track_record_json._parse_seasons` — the structural guard that the public export can never
    be asked to emit the current LOCKED season.
  * `export_track_record_json.season_records` — the JSON record shape.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as bs
from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex


# ── fixture builders ──────────────────────────────────────────────────────────────────────────────
def _proj_frame(ids, names, positions, points):
    return pd.DataFrame({
        "player_id": ids, "player_name": names, "position": positions, "proj_fp_ppr": points,
    })


def _real_frame(ids, games, points):
    return pd.DataFrame({"player_id": ids, "g": games, "real_fp_ppr": points})


def _adp_frame(ids, positions, adp_vals):
    return pd.DataFrame({"player_id": ids, "position": positions, "adp": adp_vals})


def _big_frames(n_per_pos=14, seed=0):
    """Enough rows per position (>=12) to clear `_disagreement_frame`'s pooling threshold."""
    rng = np.random.default_rng(seed)
    positions = ["RB"] * n_per_pos + ["WR"] * n_per_pos
    ids = [f"P{i}" for i in range(len(positions))]
    names = [f"Player {i}" for i in range(len(positions))]
    our_pts = rng.normal(100, 30, len(positions))
    real_pts = rng.normal(100, 30, len(positions))
    adp_vals = np.abs(rng.normal(50, 20, len(positions))) + 1.0
    games = [10] * len(positions)
    proj = _proj_frame(ids, names, positions, our_pts)
    real = _real_frame(ids, games, real_pts)
    adp = _adp_frame(ids, positions, adp_vals)
    return proj, real, adp


# ── benchmark_scorecard.player_track_record_frame ────────────────────────────────────────────────
def test_player_track_record_frame_fade_matches_disagreement_frame(monkeypatch):
    """The core parity guard: `player_track_record_frame`'s `is_fade` set must be IDENTICAL to what
    `_disagreement_frame` computes on the same merged (proj, real, adp) input — never a re-derived
    fade definition that could silently drift from the aggregate scorecard's own numbers."""
    proj, real, adp = _big_frames()

    def project_fn(con, season, schema):
        return proj.copy()

    def load_realized_fn(con, season, schema):
        return real.copy()

    monkeypatch.setattr(bs.A, "load_adp_for_season", lambda con, season, schema=None: adp.copy())

    out = bs.player_track_record_frame(
        None, 2099, "sch", project_fn=project_fn, load_realized_fn=load_realized_fn,
    )

    # Independently rebuild the aligned merge (same shape `build_scorecard` grades) and ask
    # `_disagreement_frame` directly — this is the function under test's own dependency, so this
    # asserts ROUTING (never a parallel computation), which is the property that matters here.
    p = proj.copy()
    p["player_id"] = p["player_id"].astype(str)
    r = real.copy()
    r["player_id"] = r["player_id"].astype(str)
    base = p.merge(r, on="player_id", how="inner")
    base = base[base["g"] >= 6]
    a = adp.copy()
    a["player_id"] = a["player_id"].astype(str)
    a["sys_score"] = -a["adp"]
    m = base.merge(a[["player_id", "sys_score"]], on="player_id", how="inner")
    disagreement = bs._disagreement_frame(m, "proj_fp_ppr", "sys_score")
    expected_fade_ids = set(disagreement.loc[disagreement["is_fade"], "player_id"])

    got_fade_ids = set(out.loc[out["is_fade"], "player_id"])
    assert got_fade_ids == expected_fade_ids
    assert len(got_fade_ids) > 0, "fixture must be large enough to trigger the >=12-per-position gate"

    # fade_result is graded ONLY on fade rows (nothing to grade on a row we didn't flag) and always
    # one of the three defined outcomes there — never silently blank on a real fade.
    assert out.loc[out["is_fade"], "fade_result"].isin(["hit", "miss", "push"]).all()
    assert out.loc[~out["is_fade"], "fade_result"].isna().all()


def test_fade_result_hit_vs_miss_vs_push():
    """Pure-function unit test for the hit/miss/push readout itself — our rank distance to the actual
    finish vs ADP's, the only apples-to-apples per-row comparison since ADP isn't on a points scale."""
    assert bs._fade_result(our_rank=2, adp_rank=8, actual_rank=3) == "hit"   # we were closer
    assert bs._fade_result(our_rank=8, adp_rank=2, actual_rank=3) == "miss"  # ADP was closer
    assert bs._fade_result(our_rank=2, adp_rank=4, actual_rank=3) == "push"  # tied distance (1 vs 1)
    assert bs._fade_result(our_rank=None, adp_rank=4, actual_rank=3) is None
    assert bs._fade_result(our_rank=2, adp_rank=pd.NA, actual_rank=3) is None


def test_player_track_record_frame_rank_directions(monkeypatch):
    ids = ["P1", "P2", "P3"]
    positions = ["QB", "QB", "QB"]
    proj = _proj_frame(ids, ["A", "B", "C"], positions, [300.0, 200.0, 100.0])  # our_rank 1,2,3
    real = _real_frame(ids, [10, 10, 10], [50.0, 150.0, 250.0])                # actual_rank 3,2,1
    adp = _adp_frame(ids, positions, [5.0, 1.0, 10.0])                          # adp_rank 2,1,3

    def project_fn(con, season, schema):
        return proj.copy()

    def load_realized_fn(con, season, schema):
        return real.copy()

    monkeypatch.setattr(bs.A, "load_adp_for_season", lambda con, season, schema=None: adp.copy())

    out = bs.player_track_record_frame(
        None, 2099, "sch", project_fn=project_fn, load_realized_fn=load_realized_fn,
    ).set_index("player_id")

    assert out.loc["P1", "our_rank"] == 1
    assert out.loc["P3", "our_rank"] == 3
    assert out.loc["P2", "adp_rank"] == 1  # lowest ADP (best draft slot) = rank 1
    assert out.loc["P3", "adp_rank"] == 3
    assert out.loc["P3", "actual_rank"] == 1  # highest realized points = rank 1
    assert out.loc["P1", "actual_rank"] == 3


def test_player_track_record_frame_excludes_under_6_games(monkeypatch):
    ids = ["P1", "P2"]
    positions = ["QB", "QB"]
    proj = _proj_frame(ids, ["A", "B"], positions, [200.0, 150.0])
    real = _real_frame(ids, [10, 3], [100.0, 90.0])  # P2 played only 3 games
    adp = _adp_frame(ids, positions, [5.0, 6.0])

    def project_fn(con, season, schema):
        return proj.copy()

    def load_realized_fn(con, season, schema):
        return real.copy()

    monkeypatch.setattr(bs.A, "load_adp_for_season", lambda con, season, schema=None: adp.copy())

    out = bs.player_track_record_frame(
        None, 2099, "sch", project_fn=project_fn, load_realized_fn=load_realized_fn,
    )
    assert set(out["player_id"]) == {"P1"}


def test_player_track_record_frame_ships_our_vs_actual_when_no_adp_source_has_the_season(monkeypatch):
    """NF3.2 / 2026-08-02: when NEITHER FFC nor its MFL fallback has this season, the frame must NOT
    blank the whole season — it ships real our_points/our_rank/actual_points/actual_rank, with
    adp/adp_rank/adp_source null and is_fade False (never fabricated or backfilled from anywhere)."""
    ids = ["P1", "P2", "P3"]
    positions = ["QB", "QB", "QB"]
    proj = _proj_frame(ids, ["A", "B", "C"], positions, [300.0, 200.0, 100.0])  # our_rank 1,2,3
    real = _real_frame(ids, [10, 10, 10], [50.0, 150.0, 250.0])                # actual_rank 3,2,1

    def project_fn(con, season, schema):
        return proj.copy()

    def load_realized_fn(con, season, schema):
        return real.copy()

    empty_adp = pd.DataFrame(columns=["player_id", "position", "adp"])
    monkeypatch.setattr(bs.A, "load_adp_for_season", lambda con, season, schema=None: empty_adp.copy())
    monkeypatch.setattr(bs.MFL, "load_adp_for_season", lambda con, season, schema=None: empty_adp.copy())

    out = bs.player_track_record_frame(
        None, 2025, "sch", project_fn=project_fn, load_realized_fn=load_realized_fn,
    ).set_index("player_id")

    assert set(out.index) == {"P1", "P2", "P3"}
    assert out.loc["P1", "our_rank"] == 1
    assert out.loc["P3", "actual_rank"] == 1
    assert out["adp"].isna().all()
    assert out["adp_rank"].isna().all()
    assert out["adp_source"].isna().all()
    assert (out["is_fade"] == False).all()  # noqa: E712 — explicit False check reads clearer here
    assert out["fade_result"].isna().all()  # nothing to grade without an ADP to disagree with


def test_player_track_record_frame_falls_back_to_mfl_when_ffc_is_empty(monkeypatch):
    """NF3.2 / 2026-08-02: when FFC has no archive for a season (2025 confirmed live via its own
    API — see mfl_adp_source.py's docstring) but MFL DOES have it, the frame uses MFL's real ADP
    rather than falling all the way through to the no-ADP-at-all fallback. `adp_source` names it
    explicitly so a consumer never mistakes a fallback season for FFC's primary source."""
    ids = ["P1", "P2", "P3"]
    positions = ["QB", "QB", "QB"]
    proj = _proj_frame(ids, ["A", "B", "C"], positions, [300.0, 200.0, 100.0])  # our_rank 1,2,3
    real = _real_frame(ids, [10, 10, 10], [50.0, 150.0, 250.0])                # actual_rank 3,2,1
    mfl_adp = _adp_frame(ids, positions, [5.0, 1.0, 10.0])                     # adp_rank 2,1,3

    def project_fn(con, season, schema):
        return proj.copy()

    def load_realized_fn(con, season, schema):
        return real.copy()

    empty_adp = pd.DataFrame(columns=["player_id", "position", "adp"])
    monkeypatch.setattr(bs.A, "load_adp_for_season", lambda con, season, schema=None: empty_adp.copy())
    monkeypatch.setattr(bs.MFL, "load_adp_for_season", lambda con, season, schema=None: mfl_adp.copy())

    out = bs.player_track_record_frame(
        None, 2025, "sch", project_fn=project_fn, load_realized_fn=load_realized_fn,
    ).set_index("player_id")

    assert set(out.index) == {"P1", "P2", "P3"}
    assert (out["adp_source"] == "mfl").all()
    assert out.loc["P2", "adp_rank"] == 1  # lowest ADP (best draft slot) = rank 1, same as FFC's convention
    assert out.loc["P3", "adp_rank"] == 3
    assert out["adp"].notna().all()


# ── export_track_record_json.build_headline ──────────────────────────────────────────────────────
def _fake_scorecard(adp_seasons=(2019, 2020, 2021, 2022, 2023, 2024), extra_seasons=(), **overrides):
    """`adp_seasons` drives `per_season` (what the span is derived from); `extra_seasons` are seasons
    scored by OTHER systems only (e.g. 2025, where FFC has no archive) — present in `seasons_scored`
    but deliberately absent from any row's `systems.adp`, mirroring the real scorecard JSON shape."""
    agg = {
        "n_seasons": len(adp_seasons), "us_rho_pooled": 0.517, "system_rho_pooled": 0.494,
        "delta_rho_pooled": 0.022, "disagreement_us": 0.498, "disagreement_system": 0.416,
    }
    agg.update(overrides)
    per_season = [{"season": y, "systems": {"adp": {}}} for y in adp_seasons]
    per_season += [{"season": y, "systems": {"ecr": {}}} for y in extra_seasons]
    return {
        "aggregate": {"adp": agg},
        "seasons_scored": sorted(list(adp_seasons) + list(extra_seasons)),
        "per_season": per_season,
    }


def test_build_headline_avoids_overclaims_and_uses_scorecard_numbers():
    headline = ex.build_headline(_fake_scorecard())
    lowered = headline.lower()
    for banned in ex._CLAIM_DENYLIST:
        assert banned not in lowered, f"headline drifted into a banned overclaim: {banned!r}"
    assert "0.517" in headline and "0.494" in headline
    assert "2019" in headline and "2024" in headline


def test_build_headline_span_reflects_adp_seasons_not_every_scored_season():
    """The self-contradiction bug this guards against: `seasons_scored` includes 2025 (ecr/sleeper/
    espn cover it) but FFC has no ADP archive for it, so `agg['n_seasons']` stays 6. The headline must
    say "...2024", never "...2025" — otherwise it reads "6 past seasons (2019-2025)", a visible
    internal contradiction on a page whose whole point is honest numbers."""
    headline = ex.build_headline(_fake_scorecard(extra_seasons=(2025,)))
    assert "2024" in headline
    assert "2025" not in headline


def test_build_headline_raises_without_adp_aggregate():
    with pytest.raises(ValueError):
        ex.build_headline({"aggregate": {}, "seasons_scored": [], "per_season": []})


# ── export_track_record_json._parse_seasons — the locked-season structural guard ────────────────
def test_parse_seasons_refuses_the_locked_season():
    with pytest.raises(SystemExit):
        ex._parse_seasons(f"2019-{ex.LOCKED_SEASON}")
    with pytest.raises(SystemExit):
        ex._parse_seasons(f"{ex.LOCKED_SEASON}-{ex.LOCKED_SEASON}")


def test_parse_seasons_accepts_a_past_range():
    assert ex._parse_seasons("2019-2021") == [2019, 2020, 2021]


# ── export_track_record_json.season_records ──────────────────────────────────────────────────────
def test_season_records_shape():
    df = pd.DataFrame([{
        "season": 2024, "player_id": "P1", "player_name": "A", "position": "RB",
        "our_points": 200.4, "our_rank": 1, "adp": 5.2, "adp_rank": 2,
        "actual_points": 190.1, "actual_rank": 1, "is_fade": True, "fade_result": "hit",
        "adp_source": "ffc",
    }])
    recs = ex.season_records(df)
    assert recs == [{
        "season": 2024, "playerId": "P1", "playerName": "A", "position": "RB",
        "ourPoints": 200.4, "ourRank": 1, "adp": 5.2, "adpRank": 2,
        "actualPoints": 190.1, "actualRank": 1, "isFade": True, "fadeResult": "hit",
        "adpSource": "ffc",
    }]


def test_season_records_null_adp_rank_when_no_source_has_the_season():
    """2025-shaped row with NEITHER source available: `adp`/`adp_rank`/`adp_source`/`fade_result` are
    `pd.NA`/`None` (the no-ADP-at-all fallback in `player_track_record_frame`) — must serialize to
    JSON `null`, not raise or coerce to 0/empty-string."""
    df = pd.DataFrame([{
        "season": 2025, "player_id": "P1", "player_name": "A", "position": "RB",
        "our_points": 200.4, "our_rank": 1, "adp": pd.NA, "adp_rank": pd.NA,
        "actual_points": 190.1, "actual_rank": 1, "is_fade": False, "fade_result": None,
        "adp_source": None,
    }])
    recs = ex.season_records(df)
    assert recs[0]["adp"] is None
    assert recs[0]["adpRank"] is None
    assert recs[0]["fadeResult"] is None
    assert recs[0]["adpSource"] is None


def test_adp_source_for_season_reads_the_uniform_per_row_value():
    df = pd.DataFrame([
        {"adp_source": "mfl"}, {"adp_source": "mfl"},
    ])
    assert ex.adp_source_for_season(df) == "mfl"
    assert ex.adp_source_for_season(pd.DataFrame(columns=["adp_source"])) is None
