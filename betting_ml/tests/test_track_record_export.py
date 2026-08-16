"""NF3.2 — the fantasy football past-season track-record backtest surface.

Pure/offline: tiny synthetic frames, no DuckDB/S3/network. Covers:
  * `benchmark_scorecard.player_track_record_frame` — the per-player materialization behind the
    NF-D3 scorecard's aggregate "adp" numbers (rank directions, the g>=6 filter, and — the important
    one — that its `is_fade` flag is EXACTLY the same set `_disagreement_frame` would compute on the
    identical merged input, never a parallel re-derivation).
  * `export_track_record_json.build_headline` / `build_claim` — the honest-claim denylist (reused
    verbatim from `test_nf1_5b_served_board.py`) plus the "no ADP aggregate -> refuse" guard.
    NF-TR1's two-layer copy rules (which hedge lives where, what the plain lead may never say) are
    a separate suite: `betting_ml/tests/test_nf_tr1_claim_copy.py`.
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
    agg.setdefault("delta_rho_by_pos", {"QB": 0.031, "RB": -0.0, "WR": 0.037, "TE": 0.021})
    return {
        "aggregate": {"adp": agg},
        "seasons_scored": sorted(list(adp_seasons) + list(extra_seasons)),
        "per_season": per_season,
    }


def _fake_uncertainty(n_seasons=6, delta=0.022, lo=-0.006, hi=0.051):
    """NF-TR1: `build_claim` reads the interval + player count from the NF-D17 artifact, so every
    headline test now needs one. Defaults mirror the committed P0_shipped × `adp` row."""
    return {"results": [{
        "population": "P0_shipped", "source": "adp", "n_seasons": n_seasons,
        "n_mean": 162.0, "n_min": 140, "n_max": 172, "delta_rho_mean": delta,
        "bootstrap": {"evaluated": True, "draws": 1000, "level": 0.9, "lo": lo, "hi": hi,
                      "median": 0.021, "excludes_zero": not (lo <= 0.0 <= hi)},
    }], "reproduction": {"all_pass": True}, "anchor_summary": {"all_pass": True},
        "decision": {"recommendation": "KEEP"}}


def test_build_headline_avoids_overclaims_and_uses_scorecard_numbers():
    headline = ex.build_headline(_fake_scorecard(), _fake_uncertainty())
    lowered = headline.lower()
    for banned in ex._CLAIM_DENYLIST:
        assert banned not in lowered, f"headline drifted into a banned overclaim: {banned!r}"
    assert "2019" in headline and "2024" in headline
    # NF-TR1 moved the RHO FIGURES out of the consumer lead and into the precise layer — a casual
    # reader cannot use "0.517", and the operator's readability constraint is what this asserts.
    # The numbers are not lost; `test_the_precise_layer_carries_the_scorecards_own_numbers` below
    # holds them where they now live.
    assert "0.517" not in headline and "0.494" not in headline


def test_the_precise_layer_carries_the_scorecards_own_numbers():
    """The figures moved LAYER, not out of the artifact. Simplifying the prose is safe; losing the
    numbers would be the readability constraint used as cover for dropping the evidence."""
    precise = ex.build_claim(_fake_scorecard(), _fake_uncertainty())["precise"]
    assert "0.517" in precise and "0.494" in precise
    assert "2019" in precise and "2024" in precise
    for banned in ex._CLAIM_DENYLIST:
        assert banned not in precise.lower()


def test_build_headline_span_reflects_adp_seasons_not_every_scored_season():
    """The self-contradiction bug this guards against: `seasons_scored` includes 2025 (ecr/sleeper/
    espn cover it) but FFC has no ADP archive for it, so `agg['n_seasons']` stays 6. The headline must
    say "...2024", never "...2025" — otherwise it reads "6 past seasons (2019-2025)", a visible
    internal contradiction on a page whose whole point is honest numbers."""
    headline = ex.build_headline(_fake_scorecard(extra_seasons=(2025,)), _fake_uncertainty())
    assert "2024" in headline
    assert "2025" not in headline


def test_build_headline_raises_without_adp_aggregate():
    with pytest.raises(ValueError):
        ex.build_headline({"aggregate": {}, "seasons_scored": [], "per_season": []},
                          _fake_uncertainty())


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
        "adp_source": "ffc", "proj_games": 13.87,
    }])
    recs = ex.season_records(df)
    assert recs == [{
        "season": 2024, "playerId": "P1", "playerName": "A", "position": "RB",
        "ourPoints": 200.4, "projGames": 13.9, "ourRank": 1, "adp": 5.2, "adpRank": 2,
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


# ── the EXPECTED-POINTS disclosure: `proj_games` on the wire ─────────────────────────────────────
# `our_points` is an availability-weighted EXPECTED season total, so it sits below both an "if he
# plays every week" projection and a healthy player's finished season. Unlabelled that reads as a
# broken model. The label is frontend copy; the number that makes it CHECKABLE — how many games we
# actually expected — has to survive the export, and these are the clauses that hold it there.
def _track_record(monkeypatch, proj, real, adp):
    """`player_track_record_frame` over three in-memory frames — the same closure-over-fixtures
    shape the clauses above use, factored out only because the three below share it verbatim."""
    monkeypatch.setattr(bs.A, "load_adp_for_season", lambda con, season, schema=None: adp.copy())
    return bs.player_track_record_frame(
        None, 2099, "sch",
        project_fn=lambda con, season, schema: proj.copy(),
        load_realized_fn=lambda con, season, schema: real.copy(),
    )


def test_the_frame_carries_the_expected_games_the_points_were_scaled_by(monkeypatch):
    """The end-to-end path: a projection frame's `proj_games` reaches the track-record frame.

    ⭐ Asserted per PLAYER, not as "the column exists". A column that survived the merge with every
    row's value silently reindexed onto the wrong player would satisfy a presence check and publish
    a games figure belonging to somebody else — which is worse than publishing none, because it
    looks like an explanation. The fixture gives every player a DISTINCT value so a reindex cannot
    coincidentally land on the right number."""
    proj, real, adp = _big_frames()
    proj["proj_games"] = np.linspace(6.0, 16.5, len(proj))
    expected = dict(zip(proj["player_id"], proj["proj_games"]))

    out = _track_record(monkeypatch, proj, real, adp)

    assert "proj_games" in out.columns
    assert len(out) > 0
    for pid, games in zip(out["player_id"], out["proj_games"]):
        assert games == pytest.approx(expected[pid]), f"{pid} carries another player's games figure"


def test_a_projection_with_no_games_column_publishes_null_rather_than_a_fabricated_figure(monkeypatch):
    """⛔ The failure this forbids is a GUESS. A projection source carrying no `proj_games` (MVP-1,
    an older artifact) must publish `null` — never a full-season default, never one derived from
    `our_points`. A fabricated games figure would make the points discount look accounted for on
    exactly the rows where it cannot be, and no consumer could tell the two apart.

    It must also not RAISE: this is a display column, and taking the whole public export down over
    one would be a far worse trade than an em-dash."""
    proj, real, adp = _big_frames()
    assert "proj_games" not in proj.columns

    out = _track_record(monkeypatch, proj, real, adp)

    assert "proj_games" in out.columns
    assert len(out) > 0
    assert out["proj_games"].isna().all()
    assert all(r["projGames"] is None for r in ex.season_records(out))


def test_the_six_game_filter_still_counts_REALIZED_games_once_projected_games_is_carried(monkeypatch):
    """⚠️ THE REGRESSION THIS STORY COULD MOST EASILY HAVE CAUSED, and it would have been silent.

    `player_track_record_frame` merges proj+real with `suffixes=("", "_r")` and then filters
    `base["g"] >= 6`, where `g` is the REALIZED count. Carrying a second games column through that
    merge is exactly the change that could hand the filter the PROJECTED count instead — which
    would quietly change WHICH PLAYERS the public track record scores, and every number on the page
    with it.

    So: a player we projected for almost nothing who played every week must be IN, and one we
    projected for a full season who played twice must be OUT. Either substitution flips one of
    those, and the two directions are asserted separately so a red run names which way it broke."""
    proj, real, adp = _big_frames(n_per_pos=14)
    proj["proj_games"] = 16.0
    proj.loc[proj.index[0], "proj_games"] = 1.0   # projected for nothing…
    real.loc[real.index[0], "g"] = 17             # …and played every week  -> IN
    real.loc[real.index[1], "g"] = 2              # projected 16, played 2  -> OUT

    kept = set(_track_record(monkeypatch, proj, real, adp)["player_id"])

    assert proj["player_id"].iloc[0] in kept, (
        "the >=6 filter dropped a player who played 17 games — it is reading PROJECTED games"
    )
    assert proj["player_id"].iloc[1] not in kept, (
        "the >=6 filter kept a player who played 2 games — it is reading PROJECTED games"
    )


def test_adp_source_for_season_reads_the_uniform_per_row_value():
    df = pd.DataFrame([
        {"adp_source": "mfl"}, {"adp_source": "mfl"},
    ])
    assert ex.adp_source_for_season(df) == "mfl"
    assert ex.adp_source_for_season(pd.DataFrame(columns=["adp_source"])) is None


# ── E9.56c: display casing + a headline a casual fan can read ────────────────────────────────────


def test_display_name_leaves_an_already_cased_name_completely_alone():
    """Rookies arrive properly cased from the draft-class pipeline. Re-casing them is how you turn
    "TreVeyon Henderson" into "Treveyon Henderson" — a NEW bug introduced by the fix."""
    for name in ("Ashton Jeanty", "TreVeyon Henderson", "Ja'Marr Chase", "J.K. Dobbins"):
        assert ex.display_name(name) == name


def test_display_name_fixes_the_shouting_veterans():
    assert ex.display_name("JOSH ALLEN") == "Josh Allen"
    assert ex.display_name("JA'MARR CHASE") == "Ja'Marr Chase"
    assert ex.display_name("AMON-RA ST. BROWN") == "Amon-Ra St. Brown"
    assert ex.display_name("A.J. BROWN") == "A.J. Brown"


def test_display_name_handles_mc_names_that_plain_title_case_breaks():
    """`"CHRISTIAN MCCAFFREY".title()` is "Christian Mccaffrey" — wrong, and on the most recognisable
    name on the board. 12 Mc/Mac names in the live data."""
    assert "MCCAFFREY".title() == "Mccaffrey"  # the behaviour being corrected
    assert ex.display_name("CHRISTIAN MCCAFFREY") == "Christian McCaffrey"
    assert ex.display_name("TREY MCBRIDE") == "Trey McBride"
    assert ex.display_name("LADD MCCONKEY") == "Ladd McConkey"


def test_display_name_internal_capitals_are_a_lookup_because_they_are_undecidable():
    """The case that PROVES a rule alone cannot work: same uppercase input, two right answers.

    "DEVONTA FREEMAN" -> "Devonta Freeman" but "DEVONTA SMITH" -> "DeVonta Smith". Any future
    refactor that replaces the map with a token rule breaks exactly here.
    """
    assert ex.display_name("DEVONTA FREEMAN") == "Devonta Freeman"
    assert ex.display_name("DEVONTA SMITH") == "DeVonta Smith"
    assert ex.display_name("CEEDEE LAMB") == "CeeDee Lamb"
    assert ex.display_name("DK METCALF") == "DK Metcalf"


def test_no_published_name_is_ever_all_caps():
    """The structural guard: a name missing from `_KNOWN_CASINGS` still renders readably, so the
    failure mode of an un-mapped new player is a slightly-wrong internal capital, never SHOUTING."""
    df = pd.DataFrame([
        {"season": 2024, "player_id": f"P{i}", "player_name": n, "position": "WR",
         "our_points": 1.0, "our_rank": i + 1, "adp": 1.0, "adp_rank": i + 1,
         "actual_points": 1.0, "actual_rank": i + 1, "is_fade": False, "fade_result": None,
         "adp_source": "ffc"}
        for i, n in enumerate(["JOSH ALLEN", "Ashton Jeanty", "SOME BRANDNEW ROOKIE"])
    ])
    for rec in ex.season_records(df):
        assert not rec["playerName"].isupper(), f"published a SHOUTING name: {rec['playerName']!r}"


# ── E9.61: a name can be wrong WITHOUT shouting ──────────────────────────────────────────────────


def test_a_known_miscasing_is_repaired_even_though_it_is_not_shouting():
    """⭐ THE CASE THE SHOUTING GUARD STRUCTURALLY CANNOT SEE.

    A mixed-case name that is WRONG passes `test_no_published_name_is_ever_all_caps` perfectly —
    only a check that knows the right answer can see it. "MacK Hollins" is that case.

    ⚠️ E9.61 CORRECTED THE ATTRIBUTION, AND IT CHANGED THE FIX. This test previously asserted that
    the mixed-case spelling was repaired by a hand map, on the recorded finding that the defect was
    "CARRIED IN THE DATA" because no `Mac` rule existed in the repo. That grep was run against THIS
    module's regex (`\\bMc([a-z])`, which cannot match "Mack") — but the BOARD exporter had its own
    rule pass looping over `("Mc", "Mac")`, so `MACK HOLLINS` -> "Mack Hollins" -> **"MacK Hollins"**.
    We were producing it. The repair now comes from the roster authority (a pure case change), which
    is why the assertion takes one: with no authority there is nothing to repair a mixed-case name
    against, and inventing a "MacK" -> "Mack" rule would rewrite the real MacKenzie/MacKay family.
    """
    assert ex.display_name("MacK Hollins", "Mack Hollins") == "Mack Hollins"


def test_the_repair_reaches_the_shouting_spelling_of_the_same_name():
    """Both spellings land on one answer. Otherwise the correction depends on which form the source
    happens to ship that season, which is the drift the single authority exists to prevent.

    ⭐ This is the assertion that actually pins the LIVE defect, because ALL-CAPS is the form the
    source really ships (703 of the 784 rows in the 2026 frame). It goes red against the pre-E9.61
    board exporter."""
    assert ex.display_name("MACK HOLLINS") == "Mack Hollins"
    assert ex.display_name("MACK HOLLINS", "Mack Hollins") == "Mack Hollins"


def test_the_repair_does_not_touch_a_name_it_does_not_know():
    """The other side, and the reason this is a lookup/authority rather than a "MacK" -> "Mack"
    rule: that pattern would also rewrite the legitimately-capitalised MacKenzie/MacKay family. A
    repair that invents corrections is worse than the defect it treats."""
    for name in ("MacKenzie Morgan", "Mack Hollins", "Christian McCaffrey", "Ashton Jeanty"):
        assert ex.display_name(name) == name


def test_headline_carries_no_statistics_jargon():
    """The whole point of the rewrite: this is read by casual fans, not by us.

    NF-TR1 TIGHTENED this rather than relaxing it. "correlation" and "pooled" were already banned;
    "confidence interval" and "rank correlation" now join them, because the operator's readability
    constraint names those two phrases specifically as the register that shrinks the audience. They
    are not deleted from the product — `test_the_precise_layer_*` requires them one layer down."""
    headline = ex.build_headline(_fake_scorecard(), _fake_uncertainty())
    lowered = headline.lower()
    for jargon in ("correlation", "Δρ", "rho", "within-position ordering", "pooled",
                   "confidence interval", "bootstrap", "spearman"):
        assert jargon.lower() not in lowered, f"headline still says {jargon!r}"


def test_headline_direction_follows_the_measured_sign():
    """The plain-English rewrite reads as a CLAIM, so a negative delta must change the sentence.

    The old wording ("is X, against ADP's Y") asserted no direction and so stayed true either way;
    "turned out closer" does not. A future season where ADP wins must not print a false claim.
    """
    sc = _fake_scorecard()
    agg = sc["aggregate"]["adp"]
    agg.update(us_rho_pooled=0.470, system_rho_pooled=0.510, delta_rho_pooled=-0.040)
    behind = ex.build_headline(sc, _fake_uncertainty(delta=-0.040)).lower()
    assert "closer to how those years actually finished than the draft-day consensus" not in behind
    assert "held up better than ours" in behind


def test_headline_margin_adjective_is_derived_not_asserted():
    """"a little" is true at +0.022; it must stop being applied on its own if the gap ever grows."""
    sc = _fake_scorecard()
    assert "a little closer" in ex.build_headline(sc, _fake_uncertainty())
    sc["aggregate"]["adp"]["delta_rho_pooled"] = 0.20
    assert "much closer" in ex.build_headline(sc, _fake_uncertainty(delta=0.20))
