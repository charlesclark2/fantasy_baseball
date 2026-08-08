"""E9.46 — the ONE public current-season fantasy player (`fantasy_public.featured_router`).

This route is a DELIBERATE, BOUNDED exception to the rule every other public fantasy route obeys.
The others are public because the data behind them is public — a past season the exporter will never
write a locked value into (`fantasy_public.py`'s module docstring). This one reads the LOCKED
season's `projections.json` and serves real model output: the projection, its 80% range, our rank
and the drivers, all of which `entitlement.lock_projections_payload` strips for anonymous callers.

So what keeps it safe is not the data layer but three bounds, and this file's job is to make each of
them a red build rather than a comment: exactly ONE player, a FIXED field allow-list, and NO
caller-supplied parameters.

The other half is that the card must not print a plausible-looking wrong number. The rank is the
place that bites — see `test_ranks_are_computed_over_the_full_position_field`, which pins a bug this
endpoint actually shipped in its first cut.

Pure/offline (fast gate): the endpoint functions are called directly against a local-dir fixture,
mirroring `test_fantasy_public_router.py`. No S3, no network.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.backend import dependencies as deps
from app.backend.routers import fantasy, fantasy_public


def _player(pid, name, pos, adp, pts, *, drivers=True, **extra):
    p = {
        "id": pid, "name": name, "pos": pos, "team": "SF", "bye": 8,
        "adp": adp, "fpPpr": pts, "fpHalf": pts * 0.8, "fpStd": pts * 0.65,
        "fpP10": pts * 0.3, "fpP90": pts * 1.8, "g": 14.0, "conf": "high",
        "headshot": "https://example.invalid/h.png", "mktLean": "market-blend",
        # The served artifact carries a full stat line. Present here on purpose: the allow-list
        # test below is only meaningful if there is something for a spread to leak.
        "passYds": 3504.4, "rushTd": 10.3, "recYds": 1.6, "college": "Iowa",
    }
    if drivers:
        p["contrib"] = {"drivers": [
            {"feature": "pergame_fp", "pts": 17.3},
            {"feature": "age", "pts": -13.9},
            {"feature": "carry_share", "pts": -2.3},
            {"feature": "snap_share", "pts": -1.6},
        ]}
    else:
        p["contrib"] = None
    p.update(extra)
    return p


@pytest.fixture()
def board_dir(tmp_path, monkeypatch):
    """A two-position board built so the RANK POPULATION is observable.

    ⭐ `t0` is the load-bearing row: a TE with the best projection at the position and an ADP well
    outside the feature ceiling. He can never be featured, but he must still occupy TE1 — so the
    featured player's `ourRank` comes out 4 when ranks are computed over the full field and 3 when
    they are (wrongly) computed inside the filtered universe. Without a row like this every player
    passes the filter, the two populations coincide, and the rank test cannot fail.

        pts desc → t0 1, t1 2, t2 3, t3 4        adp asc → t3 1, t2 2, t1 3, t0 4
        gaps (adpRank − ourRank) → t0 +3, t1 +1, t2 −1, t3 −3
        eligible to feature → t1, t2, t3   ⇒ largest |gap| is t3 at −3
    """
    d = tmp_path / "2026"
    d.mkdir()
    players = [
        _player("t0", "Undraftable TE", "TE", adp=400.0, pts=500.0),
        _player("t1", "Top TE", "TE", adp=100.0, pts=200.0),
        _player("t2", "Mid TE", "TE", adp=50.0, pts=150.0),
        _player("t3", "Low TE", "TE", adp=10.0, pts=100.0),
        # WR: our order matches ADP order exactly → gap 0 for everyone, so TE wins the board.
        _player("w1", "One WR", "WR", adp=5.0, pts=300.0),
        _player("w2", "Two WR", "WR", adp=20.0, pts=250.0),
    ]
    (d / "projections.json").write_text(json.dumps({
        "season": 2026, "generated_at": "2026-08-04T04:49:33+00:00",
        "adp_format": "ppr", "adp_teams": 12,
        "market_lean_note": "the standing caveat", "players": players,
    }))
    (d / "manifest.json").write_text(json.dumps({
        "featureLegend": {"pergame_fp": {"label": "Recent per-game scoring pace"},
                          "age": {"label": "Player age"}}
    }))
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)
    return tmp_path


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The three bounds that stand in for the data-layer guarantee
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_exactly_one_player_is_ever_returned(board_dir):
    """Bound 1. Not a list, not a page, not a top-N — one record, so there is no offset or limit a
    caller could walk to enumerate the paid board."""
    out = fantasy_public.featured_player()
    assert isinstance(out["player"], dict)
    assert not any(isinstance(v, list) and v and isinstance(v[0], dict) and "name" in v[0]
                   for v in out.values()), "a list of player-shaped records is being returned"


def test_the_payload_is_a_fixed_allow_list_not_a_spread(board_dir):
    """⭐ Bound 2, and the one most likely to rot. The served artifact carries a full per-player
    stat line plus the K/DST distributions; a `{**player}`-minus-a-few-keys implementation would
    publish every one of them the moment the exporter adds a field.

    Asserted as ABSENCE of fields the fixture deliberately contains, so it fails on a spread rather
    than merely describing the intent."""
    out = fantasy_public.featured_player()
    flat = json.dumps(out)
    for leaked in ("passYds", "rushTd", "recYds", "college"):
        assert leaked not in flat, f"the stat-line field {leaked!r} leaked into the public payload"
    assert set(out["player"]) == {"id", "name", "pos", "team", "bye", "headshot"}
    assert set(out["projection"]) == {"ptsStd", "ptsHalf", "ptsPpr", "p10", "p90", "games", "conf"}


def test_the_route_accepts_no_caller_parameters():
    """Bound 3. A `player_id` / `position` / `limit` parameter would turn one public player into a
    steerable read of the paid board, so the signature itself is the guard."""
    import inspect
    sig = inspect.signature(fantasy_public.featured_player)
    assert not sig.parameters, f"the featured route takes parameters: {list(sig.parameters)}"


def test_the_router_carries_no_entitlement_gate_and_is_mounted():
    """Public by construction — and actually reachable. A router nobody mounts is not an endpoint."""
    dep_calls = [d.dependency for d in fantasy_public.featured_router.dependencies]
    assert deps.require_fantasy_access not in dep_calls
    from app.backend.main import app
    assert any(getattr(r, "path", None) == "/fantasy/nfl/featured-player" for r in app.routes), (
        "featured_router is not mounted on the app"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The numbers on the card
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_ranks_are_computed_over_the_full_position_field(board_dir):
    """⭐⭐ THE BUG THIS ENDPOINT SHIPPED IN ITS FIRST CUT, pinned.

    Selection is restricted to draftable, explainable players; the RANKS must not be. Ranking inside
    that filtered universe renders "our TE21" meaning twenty-first of the filtered subset rather
    than twenty-first on the board — a number that looks right, is not what the label claims, and on
    the live artifact also changed which player won.

    The fixture separates the two (see `board_dir`): `t0` is unfeaturable but still occupies TE1, so
    the featured player is our TE4. Ranking inside the filtered universe would print TE3 — the same
    winner, a different and wrong number, which is exactly why this asserts the RANK and not just
    the identity."""
    out = fantasy_public.featured_player()
    m = out["market"]
    assert out["player"]["id"] == "t3"
    assert (m["ourRank"], m["adpRank"], m["rankGap"]) == (4, 1, -3), out


def test_a_player_outside_the_adp_ceiling_still_counts_toward_the_ranks(tmp_path, monkeypatch):
    """The sharpest form of the clause above: an undraftable player who cannot be FEATURED must
    still occupy a rank, or every rank on the card is shifted up by however many the filter removed."""
    d = tmp_path / "2026"
    d.mkdir()
    # pts desc → x 1, b 2, c 3     adp asc → c 1, b 2, x 3
    # gaps → x +2, b 0, c −2 ; eligible → b, c ⇒ c wins at |−2|, and his rank is TE3 of the full
    # field but would be TE2 of the two-player filtered universe.
    players = [
        _player("x", "Undraftable", "TE", adp=500.0, pts=1000.0),
        _player("b", "Middle", "TE", adp=100.0, pts=200.0),
        _player("c", "Feature", "TE", adp=10.0, pts=50.0),
    ]
    (d / "projections.json").write_text(json.dumps({
        "season": 2026, "adp_format": "ppr", "adp_teams": 12, "players": players}))
    (d / "manifest.json").write_text(json.dumps({"featureLegend": {}}))
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)

    out = fantasy_public.featured_player()
    assert out["player"]["name"] == "Feature"
    assert out["market"]["ourRank"] == 3, (
        "a player excluded from the FEATURE universe was also dropped from the RANKS — the card "
        "would print a rank flattered by however many the filter removed"
    )


def test_the_selection_is_deterministic_and_direction_agnostic(board_dir):
    """Repeated calls agree, and a player we rank LOWER than the market is eligible to win.

    Constraining the direction to the flattering one would be exactly the curation the computed
    rule exists to avoid — so this asserts the rule can pick a fade, using a board where the only
    disagreement is negative."""
    monkeypatch_free = fantasy_public.featured_player()
    fantasy_public._featured_memo = None
    assert fantasy_public.featured_player() == monkeypatch_free

    # `t3` wins outright at |−3| and is a player we rank LOWER than the market drafts him, so the
    # rule demonstrably does not require the flattering direction.
    assert monkeypatch_free["player"]["id"] == "t3"
    assert monkeypatch_free["market"]["rankGap"] < 0


def test_a_negative_gap_player_wins_when_it_is_the_largest(tmp_path, monkeypatch):
    d = tmp_path / "2026"
    d.mkdir()
    players = [
        _player("f", "Faded", "TE", adp=10.0, pts=50.0),    # market loves him, we do not
        _player("g", "Good", "TE", adp=60.0, pts=200.0),
        _player("h", "Mid", "TE", adp=80.0, pts=100.0),
    ]
    (d / "projections.json").write_text(json.dumps({
        "season": 2026, "adp_format": "ppr", "adp_teams": 12, "players": players}))
    (d / "manifest.json").write_text(json.dumps({"featureLegend": {}}))
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)

    out = fantasy_public.featured_player()
    assert out["player"]["name"] == "Faded"
    assert out["market"]["rankGap"] < 0, "the endpoint refuses to feature a player we rank lower"


def test_rookies_without_drivers_are_never_featured(tmp_path, monkeypatch):
    """The card has to EXPLAIN the difference, and a slot-curve rookie carries `contrib: null`.

    Measured on the live artifact: the biggest raw disagreements are all rookies with no drivers,
    so without this clause the homepage would lead with a projection it cannot account for."""
    # ⚠️ THE ROOKIE MUST WIN OUTRIGHT WITHOUT THE FILTER, OR THIS CLAUSE IS VACUOUS. The first cut
    # used three players, which forces the gaps into a ± symmetry: the rookie tied on magnitude with
    # a veteran and LOST the documented lower-ADP tie-break, so deleting the drivers requirement
    # changed nothing and the guard stayed green (the NF-D17 and-composed-guard trap, arriving via a
    # tie-break). Four players give the rookie a strictly larger gap than anyone else:
    #     pts desc → r 1, a 2, b 3, c 4     adp asc → a 1, b 2, c 3, r 4
    #     gaps → r +3, a −1, b −1, c −1
    # With the filter the eligible three all sit at |1| and `a` wins on lowest ADP; without it the
    # rookie wins at |3|.
    d = tmp_path / "2026"
    d.mkdir()
    players = [
        _player("r", "Rookie", "TE", adp=120.0, pts=500.0, drivers=False),
        _player("a", "Vet A", "TE", adp=10.0, pts=400.0),
        _player("b", "Vet B", "TE", adp=40.0, pts=300.0),
        _player("c", "Vet C", "TE", adp=80.0, pts=200.0),
    ]
    (d / "projections.json").write_text(json.dumps({
        "season": 2026, "adp_format": "ppr", "adp_teams": 12, "players": players}))
    (d / "manifest.json").write_text(json.dumps({"featureLegend": {}}))
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)

    out = fantasy_public.featured_player()
    assert out["player"]["name"] != "Rookie"
    assert out["drivers"], "a featured player must carry drivers"


def test_drivers_are_labelled_from_the_legend_and_degrade_to_the_raw_key(board_dir):
    """Plain-English wording has one home (the manifest legend, already used by the player page).

    ⛔ A driver whose label is missing is rendered with its raw key, never DROPPED: a card that
    silently omitted the biggest negative driver would be a more flattering card than the model
    supports. `carry_share` is deliberately absent from the fixture's legend."""
    out = fantasy_public.featured_player()
    labels = {d["feature"]: d["label"] for d in out["drivers"]}
    assert labels["pergame_fp"] == "Recent per-game scoring pace"
    assert labels["carry_share"] == "carry_share", "an unlabelled driver was dropped or renamed"
    assert len(out["drivers"]) == fantasy_public._FEATURED_DRIVER_COUNT


def test_the_market_lean_caveat_always_ships_with_the_card(board_dir):
    """⭐ Every eligible player's ranking blends market consensus — measured on the live artifact,
    ZERO of the 111 players carrying drivers have `mktLean == "independent"`, because `independent`
    is precisely the thin-data rookie case that has no drivers.

    So the rank gap is a real disagreement but never an independent one, and the caveat is not
    optional garnish: without it the card overstates what the gap means."""
    out = fantasy_public.featured_player()
    assert out["lean"] == "market-blend"
    assert out["leanNote"] == "the standing caveat"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Degradation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_404_when_the_artifact_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)
    with pytest.raises(HTTPException) as exc:
        fantasy_public.featured_player()
    assert exc.value.status_code == 404


def test_404_when_nobody_qualifies(tmp_path, monkeypatch):
    """An all-rookie or all-undraftable board is a 404, not a half-built card."""
    d = tmp_path / "2026"
    d.mkdir()
    (d / "projections.json").write_text(json.dumps({"season": 2026, "players": [
        _player("r", "Rookie", "TE", adp=90.0, pts=250.0, drivers=False)]}))
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)
    with pytest.raises(HTTPException) as exc:
        fantasy_public.featured_player()
    assert exc.value.status_code == 404


def test_a_miss_is_not_memoized(tmp_path, monkeypatch):
    """⚠️ Caching a 404 would hold the homepage card down for the full TTL after the publish that
    fixed it — a self-inflicted outage measured in quarter-hours."""
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    monkeypatch.setattr(fantasy_public, "_featured_memo", None)
    with pytest.raises(HTTPException):
        fantasy_public.featured_player()
    assert fantasy_public._featured_memo is None, "a 404 was cached"
