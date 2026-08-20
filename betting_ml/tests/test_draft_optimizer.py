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
    rows = board[[c for c in keep if c in board.columns]].to_dict("records")
    # NF-C7 — the engine reads expected games as `games`; the projection frame calls it `proj_games`,
    # and the served board publishes it as `g` (see `draft_assistant.engine_row`). Without it every
    # row here would carry no availability at all and the bench-seat valuation could not act — a
    # fixture that cannot reach the rule is not a fixture that tests it (NF-D20).
    for r in rows:
        if "games" not in r and r.get("proj_games") is not None:
            r["games"] = r["proj_games"]
    return rows


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


# ── the scarcity bonus may never invert a position (draft-optimizer pre-launch check, 2026-08-12) ──
#
# ⛔ ANCHORED IN ITS OWN CLAUSE. These two tests fail ONLY for the property below — the scarcity
# (VONA) bonus must never rank a WORSE player above a BETTER one at the same position. Nothing here
# is bolted onto the K/DST tests above (the E9.60 coupling trap): those assert the PRE-NF1.6
# contract, that a null-VOR placeholder never surfaces, which is a different claim about a different
# input and must keep failing for its own reason.
#
# ⚠️ WHY THE EXISTING SUITE COULD NOT CATCH THIS. Every K/DST fixture above carries `vor: None`, so
# `recommend` skips it before any scoring happens — i.e. the suite tests the world MVP-3 shipped,
# where K/DST were placeholders. NF1.6 gave them a real BASE projection and made a deep
# sub-replacement tail live for the first time. `_kicker_pool` below is therefore shaped like the
# REAL live board (measured 2026-08-12 on 2026 full_ppr/12): a handful of startable kickers just
# above replacement, then a ~29-point cliff into a long tail far below it.


def _kicker_pool(pos: str = "K") -> list[dict]:
    """A kicker pool with the live board's defining feature: a cliff into a sub-replacement tail.

    Points are chosen so `vor = league_points - replacement_points` reproduces the measured shape —
    K1..K5 barely above replacement (+8.1 … +3.9), then a 29-point gap down to a tail at -10.8 and
    below. The player perched on the near side of that cliff is the one the uncapped bonus promoted.

    `pos` exists so the same measured shape can stand in for D/ST, whose live pool has the same
    character (a few startable units, then a long tail). `_board` carries NO K/DST rows at all, so a
    test that needs those slots to be FILLABLE must add them — otherwise "the slot is still open" is
    a property of the fixture, not of the engine.
    """
    repl = 129.5
    pts = [137.7, 136.1, 135.5, 134.7, 133.4]          # startable, just above replacement
    pts += [118.8]                                      # ← the cliff-sitter: 29.1 above the next row
    pts += [89.7, 89.0, 88.2, 87.1, 86.6, 85.9]         # the deep sub-replacement tail
    return [
        {
            "player_id": f"{pos}-{i:03d}",
            "player_name": f"{pos} Player {i}",
            "position": pos,
            "team_id": f"T{i:02d}",
            "is_rookie": False,
            "league_points": p,
            "replacement_points": repl,
            "vor": round(p - repl, 1),
            "positional_rank": i + 1,
            "overall_rank": 500 + i,
            # The exporter stamps this on every K/DST row (NF1.6) — the projection is a streaming
            # TIER, not a confident rank. The engine reads it to defer these positions.
            "low_pred": True,
        }
        for i, p in enumerate(pts)
    ]


def _full_board(cfg) -> list[dict]:
    """The skill board plus K and D/ST — every starter slot in `cfg` is actually fillable."""
    return _board(cfg) + _kicker_pool("K") + _kicker_pool("DST")


def test_scarcity_bonus_never_promotes_a_below_replacement_player_over_a_better_one():
    """The engine's top K must be the BEST K, not the one sitting above the biggest cliff.

    Measured on the live 2026 full_ppr/12 board before the fix: Andre Szmyt (K31, vor -10.8) scored
    -10.8 + 29.1 = 18.3 and beat Jake Bates (K1, vor +8.1) on 8.1 + 1.5 = 9.6 — putting the 31st-best
    kicker at #66 overall and drafting him in round 6 of a 12-team snake.
    """
    cfg = presets.full_ppr()
    board = _board(cfg) + _kicker_pool()
    recs = draft.recommend(board, config=cfg, normalize=NORM, top_n=len(board))

    ks = [r for r in recs if r.position == "K"]
    assert ks, "fixture must put kickers in front of the engine, or this guard proves nothing"

    best_by_vor = max(ks, key=lambda r: r.vor)
    assert ks[0].player_id == best_by_vor.player_id, (
        f"engine ranked {ks[0].player_name} (vor {ks[0].vor}) above the best kicker "
        f"{best_by_vor.player_name} (vor {best_by_vor.vor}) — the scarcity bonus inverted the position"
    )
    assert ks[0].vor > 0, "the top-ranked kicker must be above replacement"


def test_only_the_best_available_at_a_position_earns_the_scarcity_bonus():
    """The mechanism itself: at most ONE player per position carries a non-zero `need_bonus`.

    Separate from the ordering test above on purpose — ordering could be restored by an unrelated
    change (a penalty, a re-sort) while the bonus stayed per-player, and then the ordering test alone
    would pass over a defect that is still there.
    """
    cfg = presets.full_ppr()
    board = _board(cfg) + _kicker_pool()
    recs = draft.recommend(board, config=cfg, normalize=NORM, top_n=len(board))

    bonused: dict[str, list[str]] = {}
    for r in recs:
        if r.need_bonus:
            bonused.setdefault(r.position, []).append(f"{r.player_name}(vor {r.vor})")
    assert bonused, "no position earned a bonus — the fixture cannot prove the rule holds"

    for pos, names in bonused.items():
        assert len(names) == 1, f"{pos}: {len(names)} players carried a scarcity bonus: {names}"
        # …and it must be the position's BEST available, not merely a single arbitrary one.
        at_pos = [r for r in recs if r.position == pos]
        top = max(at_pos, key=lambda r: r.vor)
        assert names[0].startswith(top.player_name), (
            f"{pos}: the bonus went to {names[0]}, not to the best available {top.player_name}"
        )


def test_a_thin_position_still_gets_filled_when_everything_left_is_below_replacement():
    """Need-filling must survive the fix — the requirement `test_mock_snake_draft_replay` encodes.

    Late in a draft every remaining player at a needed position is below replacement. The best of
    them must still carry the full scarcity bonus, or a mandatory starter slot is never filled. This
    is the clause the naive `vor > 0` patch broke, pinned here in its own right so a future
    simplification cannot quietly reintroduce it.
    """
    cfg = presets.full_ppr()
    # Only the sub-replacement tail of the kicker pool is left — nothing here has vor > 0.
    tail = [r for r in _kicker_pool() if r["vor"] < 0]
    assert tail and all(r["vor"] < 0 for r in tail), "fixture must be entirely below replacement"
    recs = draft.recommend(_board(cfg) + tail, config=cfg, normalize=NORM, top_n=len(_board(cfg)) + len(tail))

    ks = [r for r in recs if r.position == "K"]
    assert ks, "kickers must reach the engine"
    best = max(ks, key=lambda r: r.vor)
    assert best.need_bonus > 0, (
        "the best available kicker earned no scarcity bonus despite an open K starter slot — "
        "a thin position would never be filled"
    )


# ── the reserve constraint: a mandatory starter slot may never be left unfilled ───────────────────
#
# ⛔ ANCHORED IN ITS OWN CLAUSE — these fail only for the reserve property, never for the scarcity
# ordering above (the E9.60 coupling trap). Operator call 2026-08-12: leaving a mandatory starter
# slot empty is not a trade-off the tool may offer, so this is a correctness bar, not a preference.


def _roster_size(cfg) -> int:
    return sum(s.count for s in cfg.roster)


def _num(v, default: float = 0.0) -> float:
    """`vor` off a board row as a plain float (rows carry numpy scalars / None)."""
    return default if v is None else float(v)


def test_the_reserve_constraint_is_inert_while_there_is_slack():
    """With picks to spare it must change NOTHING — every `must_fill` False, pure-score order kept.

    This is the half that keeps the constraint honest: a rule that quietly re-ranked normal drafting
    would be a preference smuggled in as a correctness fix. Written FIRST for that reason.
    """
    cfg = presets.full_ppr()
    board = _board(cfg)
    recs = draft.recommend(board, config=cfg, my_player_ids=[], normalize=NORM, top_n=40)
    assert all(not r.must_fill for r in recs), "the constraint bound on an EMPTY roster (maximum slack)"
    assert [r.score for r in recs] == sorted((r.score for r in recs), reverse=True)


def test_a_mandatory_starter_slot_is_never_left_unfilled():
    """Drive a full draft to the last pick and assert every starter slot ends up filled.

    The live failure this pins: with every above-replacement RB gone, a surplus-penalized BACKUP QB
    out-scored the best remaining RB, so the optimizer spent the closing picks on bench depth and
    finished 7/9. Here the whole roster is drafted by taking the engine's own top pick every time —
    if it ever prefers depth while a slot is stranded, the final assert fails.
    """
    cfg = presets.full_ppr()
    board = _full_board(cfg)
    by_id = {r["player_id"]: r for r in board}
    req = draft.RosterRequirements.from_config(cfg)
    total = _roster_size(cfg)

    # Everyone above replacement at RB is taken by rivals — the exact live state.
    drafted = [r["player_id"] for r in board if NORM(r["position"]) == "RB" and _num(r.get("vor")) > 0]
    mine: list[str] = []
    for _ in range(total):
        recs = draft.recommend(
            board, config=cfg, drafted_ids=drafted, my_player_ids=mine, normalize=NORM, top_n=1
        )
        if not recs:
            break
        drafted.append(recs[0].player_id)
        mine.append(recs[0].player_id)

    open_at_end = draft.open_starter_slots(
        [NORM(by_id[p]["position"]) for p in mine], req, normalize=NORM
    )
    stranded = dict(open_at_end.dedicated), len(open_at_end.flex)
    assert not open_at_end.dedicated and not open_at_end.flex, (
        f"the draft ended with starter slots unfilled: dedicated={stranded[0]}, flex={stranded[1]}"
    )


def test_when_the_reserve_binds_every_filler_outranks_every_non_filler():
    """The mechanism, stated directly and separately from the outcome above.

    The end-to-end test could pass by luck (a filler happening to score highest anyway); this asserts
    the ORDERING the constraint imposes, so it fails even when the outcome is accidentally fine.
    """
    cfg = presets.full_ppr()
    board = _full_board(cfg)
    req = draft.RosterRequirements.from_config(cfg)
    total = _roster_size(cfg)

    # A roster one pick from full with exactly one starter slot (TE) still open: every TE above
    # replacement is gone, so the filler is a weak one and bench depth would otherwise out-score it.
    by_pos: dict[str, list[dict]] = {}
    for r in board:
        by_pos.setdefault(NORM(r["position"]), []).append(r)
    for rows in by_pos.values():
        rows.sort(key=lambda r: -_num(r.get("vor")))

    mine = [by_pos["QB"][0]["player_id"]]
    mine += [r["player_id"] for r in by_pos["RB"][:2]]
    mine += [r["player_id"] for r in by_pos["WR"][:3]]          # 2 WR starters + the FLEX
    mine += [r["player_id"] for r in by_pos["QB"][1:total - len(mine) - 1 + 1]]  # bench out to full-1
    mine = mine[: total - 1]
    drafted = list(mine) + [r["player_id"] for r in by_pos["TE"] if _num(r.get("vor")) > 0]

    recs = draft.recommend(
        board, config=cfg, drafted_ids=drafted, my_player_ids=mine, normalize=NORM, top_n=200
    )
    fillers = [r for r in recs if r.must_fill]
    others = [r for r in recs if not r.must_fill]
    assert fillers, "the reserve constraint did not bind with 1 pick left and a starter slot open"
    assert others, "fixture must also offer non-fillers, or the ordering claim is vacuous"
    assert max(recs.index(f) for f in fillers) < min(recs.index(o) for o in others), (
        "a non-filler outranked a required filler while the reserve constraint was binding"
    )
    # …and the recommendation must SAY why it stopped offering the better-scoring bench players.
    # ⚠️ RE-ANCHORED (not dropped) by NF-C-LDA-1: the wording moved to the shipping TS engine's
    # spelling ("\u26a0 Must fill a starter") when the two were put back in lock-step. The PROPERTY
    # — the sentence names the reserve constraint — is unchanged (E9.60).
    assert "Must fill a starter" in recs[0].rationale


# ── low-predictability positions (K/DST) are deferred until the roster requires them ──────────────
#
# ⛔ ANCHORED IN ITS OWN CLAUSE — these fail only for the deferral property. Operator report
# 2026-08-12: a D/ST recommended in an early round is a credibility non-starter, and it reproduced —
# ROUND 6's six-slot panel on the live board came back five-sixths K/DST with DEN D/ST at #1.


def test_a_low_predictability_position_is_never_recommended_while_real_candidates_remain():
    """No K/DST anywhere above a real candidate on an open board.

    Not a scoring bug: the whole above-replacement VOR range is 8.1 at K and 10.4 at D/ST against a
    median 80% interval of 118.7 / 87.3 points on ONE player (signal-to-noise 0.07 / 0.12, vs
    0.55-0.61 at RB/WR/TE), so the rank an early pick would be buying is inside its own noise. The
    exporter says exactly that by stamping `low_pred`.
    """
    cfg = presets.full_ppr()
    recs = draft.recommend(_full_board(cfg), config=cfg, my_player_ids=[], normalize=NORM, top_n=400)
    deferred = [i for i, r in enumerate(recs) if r.deferred]
    real = [i for i, r in enumerate(recs) if not r.deferred]
    assert deferred and real, "fixture must contain BOTH kinds, or the ordering claim is vacuous"
    assert {r.position for r in recs if r.deferred} == {"K", "DST"}
    assert min(deferred) > max(real), (
        f"a low-predictability player ranked above a real candidate: "
        f"{recs[min(deferred)].player_name} at #{min(deferred) + 1} of {len(recs)}"
    )
    # The reported top-6 panel — what the operator actually saw — must be entirely real players.
    assert not any(r.deferred for r in recs[:6])


def test_a_deferred_position_is_surfaced_once_the_roster_requires_it():
    """The composition with the reserve constraint: deferred early, REQUIRED at the end.

    Absolute deferral is only safe because these two rules compose — when K/DST are the only thing a
    roster can still accept the bench is full, so `picks_remaining == open_starter_count` and the
    reserve constraint necessarily binds. This pins that, so a future change to either rule cannot
    quietly leave a deferred position permanently unreachable.
    """
    cfg = presets.full_ppr()
    board = _full_board(cfg)
    by_pos: dict[str, list[dict]] = {}
    for r in board:
        by_pos.setdefault(NORM(r["position"]), []).append(r)
    for rows in by_pos.values():
        rows.sort(key=lambda r: -_num(r.get("vor")))

    # A roster one pick from full with ONLY the K starter slot still open.
    mine = [by_pos["QB"][0]["player_id"]]
    mine += [r["player_id"] for r in by_pos["RB"][:2]]
    mine += [r["player_id"] for r in by_pos["WR"][:3]]        # 2 WR starters + the FLEX
    mine += [by_pos["TE"][0]["player_id"], by_pos["DST"][0]["player_id"]]
    mine += [r["player_id"] for r in by_pos["RB"][2:8]]       # bench
    mine = mine[: _roster_size(cfg) - 1]

    recs = draft.recommend(
        board, config=cfg, drafted_ids=list(mine), my_player_ids=mine, normalize=NORM, top_n=20
    )
    assert recs[0].position == "K", (
        f"with 1 pick left and only the K slot open, the top recommendation was "
        f"{recs[0].player_name} ({recs[0].position}) — a deferred position must resurface here"
    )
    assert recs[0].deferred and recs[0].must_fill, "it is surfaced BY the reserve constraint"


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
