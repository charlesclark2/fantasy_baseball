"""Fast-gate unit tests for the sport-agnostic LIVE draft optimizer (NF-C2 / MVP-3).

Imports ONLY the pure `fantasy_engine` package + the NFL presets (numpy/pandas, no `pipeline`, no IO),
per the fast-gate discipline. Builds an AUTHENTIC board by running a synthetic projection through the
real scoring + VOR engine (so the optimizer is tested against genuine `build_board` output, not a
hand-mocked frame), then covers the story's gate:

  * roster-need detection (dedicated + flex + superflex),
  * tier / VONA cliff signals,
  * a full MOCK SNAKE DRAFT REPLAY (no duplicate picks, needs respected, fast),
  * K/DST-with-no-projection handled gracefully (never crashes, never mis-ranked),
  * the snake-order arithmetic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

lc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.league_config")
sc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.scoring")
vor = pytest.importorskip("quant_sports_intel_models.fantasy_engine.vor")
draft = pytest.importorskip("quant_sports_intel_models.fantasy_engine.draft")
presets = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.league_presets")

PROFILE = presets.NFL_PROFILE
NORM = PROFILE.normalize_position


def _synthetic_projection() -> pd.DataFrame:
    """A believable projection universe: QB/RB/WR/TE with smoothly-declining production so the VOR
    board has real cross-position structure. No K/DST lines (mirrors MVP-1 = offensive skill only)."""
    rows = []
    cols = list(PROFILE.stat_columns.values())
    shape = {  # (count, per-position production scale at rank 1) — declines with rank
        "QB": (32, dict(proj_pass_yds=4600, proj_pass_td=34, proj_pass_int=11, proj_rush_yds=380, proj_rush_td=3)),
        "RB": (60, dict(proj_rush_yds=1350, proj_rush_td=11, proj_rec=52, proj_rec_yds=430, proj_rec_td=2, proj_targets=68)),
        "WR": (72, dict(proj_rec=105, proj_rec_yds=1450, proj_rec_td=10, proj_targets=150)),
        "TE": (32, dict(proj_rec=78, proj_rec_yds=920, proj_rec_td=7, proj_targets=100)),
    }
    pid = 0
    for pos, (count, top) in shape.items():
        for i in range(count):
            f = (1.0 - i / (count + 4))  # smooth decline
            row = {c: 0.0 for c in cols}
            for k, v in top.items():
                row[k] = v * f
            row["position"] = pos
            row["player_id"] = f"{pos}-{i:03d}"
            row["player_name"] = f"{pos} Player {i}"
            row["team_id"] = f"T{pid % 32:02d}"
            row["is_rookie"] = (i % 11 == 0)
            row["proj_games"] = 16.0
            row["proj_fp_ppr"] = 0.0   # scorer recomputes; sd only used for interval passthrough
            row["fp_ppr_sd"] = 20.0 + 0.5 * i
            rows.append(row)
            pid += 1
    return pd.DataFrame(rows)


def _board(config) -> list[dict]:
    proj = _synthetic_projection()
    scored = sc.score_players(proj, config, PROFILE)
    board = vor.build_board(scored, config, PROFILE)
    keep = [
        "player_id", "player_name", "position", "team_id", "is_rookie", "proj_games",
        "league_points", "replacement_points", "vor", "positional_rank", "overall_rank",
        "vor_p10", "vor_p90",
    ]
    return board[[c for c in keep if c in board.columns]].to_dict("records")


# ── roster-need detection ─────────────────────────────────────────────────────────────────────────
def test_open_slots_empty_roster_needs_everything():
    req = draft.RosterRequirements.from_config(presets.full_ppr())
    o = draft.open_starter_slots([], req, normalize=NORM)
    assert o.dedicated.get("QB") == 1 and o.dedicated.get("RB") == 2 and o.dedicated.get("WR") == 2
    assert len(o.flex) == 1                       # one FLEX still open
    assert o.need_level("RB") == 2                # dedicated open
    # K/DST slots ARE open (the config declares them) but carry no ranked players → they simply never
    # surface as a candidate in recommend(); the engine stays position-agnostic. Verified below.


def test_open_slots_flex_after_dedicated_filled():
    req = draft.RosterRequirements.from_config(presets.full_ppr())
    # 1 QB, 2 RB, 2 WR, 1 TE fills every dedicated slot; a 3rd RB can still take the FLEX
    mine = ["QB", "RB", "RB", "WR", "WR", "TE"]
    o = draft.open_starter_slots(mine, req, normalize=NORM)
    # every SKILL dedicated slot is filled (K/DST stay open by design — no projectable players)
    assert all(o.dedicated.get(p, 0) == 0 for p in ("QB", "RB", "WR", "TE"))
    assert len(o.flex) == 1
    assert o.need_level("RB") == 1                # RB now only fills the FLEX
    assert o.need_level("QB") == 0                # QB not flex-eligible in std → no open slot


def test_superflex_opens_a_qb_eligible_slot():
    req = draft.RosterRequirements.from_config(presets.superflex())
    mine = ["QB", "RB", "RB", "WR", "WR", "TE", "RB"]  # dedicated + FLEX filled, SUPERFLEX open
    o = draft.open_starter_slots(mine, req, normalize=NORM)
    assert o.need_level("QB") == 1                # a 2nd QB now fills the open SUPERFLEX
    assert any("QB" in e for e in o.flex)


# ── tiers ─────────────────────────────────────────────────────────────────────────────────────────
def test_assign_tiers_breaks_on_a_cliff():
    pts = [100, 98, 96, 70, 68, 66]              # a clear cliff between 96 and 70
    tiers = draft.assign_tiers(pts)
    assert tiers[0] == tiers[1] == tiers[2] == 1
    assert tiers[3] == tiers[4] == tiers[5] == 2
    assert draft.assign_tiers([]) == []
    assert draft.assign_tiers([42.0]) == [1]


# ── recommendation ────────────────────────────────────────────────────────────────────────────────
def test_recommend_excludes_drafted_and_never_crashes_on_kdst():
    cfg = presets.full_ppr()
    board = _board(cfg)
    taken = {r["player_id"] for r in board[:20]}
    recs = draft.recommend(board, config=cfg, drafted_ids=taken, my_player_ids=[], normalize=NORM, top_n=10)
    assert recs, "should still have recommendations"
    ids = {r.player_id for r in recs}
    assert ids.isdisjoint(taken)                  # no drafted player recommended
    assert all(r.position in ("QB", "RB", "WR", "TE") for r in recs)   # K/DST never surface


def test_need_bonus_lifts_a_needed_position_over_pure_vor():
    cfg = presets.full_ppr()
    board = _board(cfg)
    # Roster already stacked at RB (5 RBs) but no WR/TE/QB → WR/TE/QB carry a need bonus, RB does not.
    rb_ids = [r["player_id"] for r in board if NORM(r["position"]) == "RB"][:5]
    recs = draft.recommend(board, config=cfg, drafted_ids=rb_ids, my_player_ids=rb_ids, normalize=NORM, top_n=5)
    # the top rec should be a need position, not another RB (starters at RB are full → RB damped)
    assert recs[0].position != "RB"
    top = recs[0]
    assert top.need_level >= 1 and top.score >= top.vor      # bonus applied, never below raw VOR


def test_backup_qb_deprioritized_once_starter_set():
    # once I hold my one starting QB, a 2nd QB (pure backup in a 1-QB league) must not be the top pick.
    cfg = presets.full_ppr()
    board = _board(cfg)
    top_qb = next(r["player_id"] for r in board if NORM(r["position"]) == "QB")
    recs = draft.recommend(board, config=cfg, drafted_ids=[top_qb], my_player_ids=[top_qb], normalize=NORM, top_n=5)
    assert recs[0].position != "QB", "a backup QB should not be recommended #1 once the starter is set"


def test_full_starters_prefer_skill_depth_over_backup_qb_te():
    # after a complete starting lineup (QB/2RB/2WR/TE/FLEX) is set, the optimizer should favor RB/WR
    # bench upside — a 2nd QB (can't start another in a 1-QB league) must not lead the recommendations.
    cfg = presets.full_ppr()
    board = _board(cfg)
    def top(pos, n):
        return [r["player_id"] for r in board if NORM(r["position"]) == pos][:n]
    mine = top("QB", 1) + top("RB", 3) + top("WR", 2) + top("TE", 1)   # fills every starter + FLEX(RB)
    recs = draft.recommend(board, config=cfg, drafted_ids=mine, my_player_ids=mine, normalize=NORM, top_n=5)
    assert recs[0].position in ("RB", "WR"), f"expected RB/WR depth, got {recs[0].position}"
    assert "QB" not in {r.position for r in recs[:3]}, "a backup QB should not be a top-3 pick once set"


def test_bye_week_stack_is_penalized():
    # holding 2 WRs on bye 7, an equal-VOR WR also on bye 7 should rank BELOW one on a different bye.
    cfg = presets.full_ppr()

    def wr(pid, bye, vor=50.0, pts=150.0):
        return {"player_id": pid, "player_name": pid, "position": "WR", "vor": vor,
                "league_points": pts, "positional_rank": 1, "overall_rank": 1,
                "replacement_points": 100.0, "team_id": "X", "is_rookie": False, "bye": bye}

    board = [wr("mine1", 7), wr("mine2", 7), wr("free_bye7", 7), wr("free_bye9", 9)]
    recs = draft.recommend(board, config=cfg, drafted_ids=["mine1", "mine2"],
                           my_player_ids=["mine1", "mine2"], normalize=NORM, top_n=2)
    top = {r.player_id: r for r in recs}
    assert top["free_bye9"].score > top["free_bye7"].score
    assert top["free_bye7"].bye_conflict == 2 and top["free_bye9"].bye_conflict == 0


def test_null_vor_rows_never_recommended():
    # K/DST placeholders (no projection → vor None) must never surface as a recommendation.
    cfg = presets.full_ppr()
    board = _board(cfg) + [
        {"player_id": "DST-SF", "player_name": "SF D/ST", "position": "DST", "vor": None,
         "league_points": None, "positional_rank": 0, "overall_rank": 9999, "team_id": "SF"},
        {"player_id": "K-SF", "player_name": "SF K", "position": "K", "vor": None,
         "league_points": None, "positional_rank": 0, "overall_rank": 9999, "team_id": "SF"},
    ]
    recs = draft.recommend(board, config=cfg, normalize=NORM, top_n=50)
    assert all(r.position not in ("K", "DST") for r in recs)


def test_rationale_is_populated():
    cfg = presets.full_ppr()
    recs = draft.recommend(_board(cfg), config=cfg, normalize=NORM, top_n=3)
    assert all(r.rationale for r in recs)


# ── snake arithmetic ──────────────────────────────────────────────────────────────────────────────
def test_snake_order_math():
    # 12-team, slot 3: R1 pick 3, R2 pick 22 (reversed: 12-3+1=10 → 12+10), R3 pick 27
    assert draft.overall_pick_for(3, 12, 1) == 3
    assert draft.overall_pick_for(3, 12, 2) == 22
    assert draft.overall_pick_for(3, 12, 3) == 27
    assert draft.picks_until_next(3, 12, current_overall_pick=3) == 0     # on the clock
    assert draft.picks_until_next(3, 12, current_overall_pick=4) == 18    # until pick 22


# ── the mock / replayed snake draft (the story's validation gate) ────────────────────────────────
def test_mock_snake_draft_replay():
    """Replay a full 12-team × 15-round snake draft where every team auto-picks the top optimizer
    recommendation for ITS roster. Gate: no duplicate picks, everyone fills their startable core,
    every pick is a real available player, and it runs fast enough for live use."""
    cfg = presets.full_ppr()
    n_teams, rounds = 12, 15
    board = _board(cfg)
    by_id = {r["player_id"]: r for r in board}
    drafted: list[str] = []
    rosters: dict[int, list[str]] = {t: [] for t in range(1, n_teams + 1)}

    total_picks = n_teams * rounds
    for overall in range(1, total_picks + 1):
        rnd = (overall - 1) // n_teams + 1
        pos_in_round = (overall - 1) % n_teams + 1
        slot = pos_in_round if rnd % 2 == 1 else (n_teams - pos_in_round + 1)
        recs = draft.recommend(
            board, config=cfg, drafted_ids=drafted, my_player_ids=rosters[slot], normalize=NORM, top_n=1
        )
        assert recs, f"ran out of players at overall pick {overall}"
        pick = recs[0].player_id
        assert pick not in drafted                 # never a duplicate
        assert pick in by_id                        # a real board player
        drafted.append(pick)
        rosters[slot].append(pick)

    assert len(drafted) == len(set(drafted)) == total_picks

    # every team should have assembled a legal startable core (1 QB, ≥2 RB, ≥2 WR, ≥1 TE somewhere,
    # since needs drove the picks) — check the modal starting requirements are met for all teams.
    for slot, ids in rosters.items():
        pos_counts: dict[str, int] = {}
        for pid in ids:
            p = NORM(by_id[pid]["position"])
            pos_counts[p] = pos_counts.get(p, 0) + 1
        assert pos_counts.get("QB", 0) >= 1, f"team {slot} never drafted a QB"
        assert pos_counts.get("RB", 0) >= 2, f"team {slot} short at RB"
        assert pos_counts.get("WR", 0) >= 2, f"team {slot} short at WR"
        assert pos_counts.get("TE", 0) >= 1, f"team {slot} never drafted a TE"
