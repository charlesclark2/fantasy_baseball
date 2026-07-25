"""Fast-gate unit tests for the sport-agnostic fantasy league-config / scoring / VOR engine (NF-C1-lite).

Imports ONLY the pure `fantasy_engine` package + the NFL presets (numpy/pandas — no `pipeline`, no IO),
per the fast-gate discipline. Covers the story's gate: (1) SCORING CORRECTNESS against hand-computed
examples, (2) the config schema round-tripping (the shared contract), and (3) the VOR / positional
scarcity math — including the two face-validity proofs: full-PPR lifts pass-catchers and superflex
lifts QBs (the direct check the flex-allocation is right).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

lc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.league_config")
sc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.scoring")
vor = pytest.importorskip("quant_sports_intel_models.fantasy_engine.vor")
presets = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.league_presets")

PROFILE = presets.NFL_PROFILE


def _line(**kw) -> pd.DataFrame:
    """A one-row raw projection frame keyed by canonical MVP-1 columns (proj_*), with a position."""
    base = {c: 0.0 for c in PROFILE.stat_columns.values()}
    base["position"] = kw.pop("position", "WR")
    base.update({PROFILE.stat_columns.get(k, k): v for k, v in kw.items()})
    return pd.DataFrame([base])


# ── 1. SCORING CORRECTNESS (hand-calc; the gate) ──────────────────────────────────────────────────
def test_standard_scoring_hand_calc():
    # 4000*.04 + 30*4 + 10*-2 + 300*.1 + 3*6 + 2*-2 = 160 + 120 - 20 + 30 + 18 - 4 = 304
    df = _line(position="QB", pass_yds=4000, pass_td=30, pass_int=10, rush_yds=300, rush_td=3,
               fumbles_lost=2)
    out = sc.score_players(df, presets.standard(), PROFILE)
    assert out["league_points"].iloc[0] == pytest.approx(304.0)


def test_ppr_variants_hand_calc():
    # rec_yds=1000 → 100 ; rec_td=5 → 30 ; base(non-rec) = 130. +0/0.5/1.0 per reception (100 rec).
    df = _line(position="WR", rec_yds=1000, rec=100, rec_td=5)
    assert sc.score_players(df, presets.standard(), PROFILE)["league_points"].iloc[0] == pytest.approx(130.0)
    assert sc.score_players(df, presets.half_ppr(), PROFILE)["league_points"].iloc[0] == pytest.approx(180.0)
    assert sc.score_players(df, presets.full_ppr(), PROFILE)["league_points"].iloc[0] == pytest.approx(230.0)


def test_te_premium_applies_only_to_te():
    # full-PPR + 0.5 TE-premium ⇒ a TE gets 1.5/reception, a WR still 1.0/reception.
    cfg = presets.te_premium(premium=0.5)
    te = _line(position="TE", rec_yds=1000, rec=100, rec_td=5)
    wr = _line(position="WR", rec_yds=1000, rec=100, rec_td=5)
    assert sc.score_players(te, cfg, PROFILE)["league_points"].iloc[0] == pytest.approx(280.0)  # 130+150
    assert sc.score_players(wr, cfg, PROFILE)["league_points"].iloc[0] == pytest.approx(230.0)  # 130+100


def test_null_stat_contributes_zero_not_nan():
    # a WR with only a receiving line: the (missing) passing/rushing terms must be 0, not NaN.
    df = _line(position="WR", rec=80, rec_yds=1100, rec_td=8)
    out = sc.score_players(df, presets.full_ppr(), PROFILE)
    assert np.isfinite(out["league_points"].iloc[0])
    assert out["league_points"].iloc[0] == pytest.approx(80.0 + 110.0 + 48.0)  # 1*80 + .1*1100 + 6*8


def test_uncertainty_passthrough_scales_by_cv():
    # league_sd = (base_sd/base_points) * league_points ; interval rebuilt at z80.
    df = _line(position="WR", rec_yds=1000, rec=100, rec_td=5)
    df["proj_fp_ppr"] = 230.0      # matches the full-PPR score exactly
    df["fp_ppr_sd"] = 46.0         # cv = 0.2
    out = sc.score_players(df, presets.full_ppr(), PROFILE)
    assert out["league_points_sd"].iloc[0] == pytest.approx(46.0, abs=0.1)      # cv 0.2 * 230
    assert out["league_points_p90"].iloc[0] > out["league_points"].iloc[0]
    assert out["league_points_p10"].iloc[0] < out["league_points"].iloc[0]


# ── 2. CONFIG SCHEMA — the shared contract round-trips ────────────────────────────────────────────
@pytest.mark.parametrize("name", ["standard", "half_ppr", "full_ppr", "superflex", "te_premium"])
def test_config_roundtrips_through_dict(name):
    cfg = presets.get_preset(name)
    back = lc.LeagueConfig.from_dict(cfg.to_dict())
    assert back.to_dict() == cfg.to_dict()
    assert back.name == cfg.name and back.superflex == cfg.superflex


def test_validation_rejects_bad_config():
    good = presets.full_ppr()
    with pytest.raises(ValueError):
        good.with_overrides(n_teams=0)
    with pytest.raises(ValueError):
        lc.LeagueConfig(name="x", sport="nfl", n_teams=12,
                        scoring=lc.ScoringRules(per_stat={}), roster=good.roster).validate()


def test_superflex_preset_has_a_qb_eligible_flex():
    cfg = presets.superflex()
    flex = cfg.flex_slot_specs()
    assert any("QB" in elig for elig, _ in flex), "superflex must have a QB-eligible flex slot"
    assert cfg.dedicated_demand()["QB"] == cfg.n_teams  # exactly one dedicated QB per team


# ── 3. VOR / positional scarcity ──────────────────────────────────────────────────────────────────
def _pool() -> pd.DataFrame:
    """A tiny controlled pool with pre-set league_points, so replacement levels are hand-computable."""
    rows = [
        ("QB", "q1", 300), ("QB", "q2", 290), ("QB", "q3", 280), ("QB", "q4", 270),
        ("RB", "r1", 200), ("RB", "r2", 180), ("RB", "r3", 160), ("RB", "r4", 140), ("RB", "r5", 120),
        ("WR", "w1", 190), ("WR", "w2", 170), ("WR", "w3", 150),
    ]
    return pd.DataFrame(
        [{"position": p, "player_id": i, "player_name": i, "league_points": float(v)} for p, i, v in rows]
    )


def _mini_config(name, roster, n_teams=2):
    return lc.LeagueConfig(name=name, sport="nfl", n_teams=n_teams,
                           scoring=lc.ScoringRules(per_stat={"x": 1.0}), roster=roster).validate()


def test_flex_allocation_and_replacement_hand_calc():
    # 2 teams; 1 QB + 1 RB dedicated + 1 FLEX(RB/WR/TE). dedicated QB=2, RB=2, flex spots=2.
    roster = (
        lc.RosterSlot("QB", 1, ("QB",)),
        lc.RosterSlot("RB", 1, ("RB",)),
        lc.RosterSlot("FLEX", 1, ("RB", "WR", "TE")),
    )
    cfg = _mini_config("mini", roster)
    repl, started = vor.compute_replacement_levels(_pool(), cfg, PROFILE)
    # after dedicated (RB idx2=160, WR idx0=190): flex spot1 → w1(190), spot2 → w2(170); both WR.
    assert started["QB"] == 2 and started["RB"] == 2 and started["WR"] == 2
    assert repl["QB"] == pytest.approx(280.0)   # q3
    assert repl["RB"] == pytest.approx(160.0)   # r3
    assert repl["WR"] == pytest.approx(150.0)   # w3


def test_superflex_lifts_qb_replacement_and_vor():
    """The story's key face-validity check: a QB-eligible SUPERFLEX slot must raise QB starter demand,
    drop QB replacement level, and lift QB VOR — the proof the flex-allocation math is right."""
    std_roster = (
        lc.RosterSlot("QB", 1, ("QB",)),
        lc.RosterSlot("RB", 1, ("RB",)),
        lc.RosterSlot("FLEX", 1, ("RB", "WR", "TE")),
    )
    sf_roster = std_roster + (lc.RosterSlot("SUPERFLEX", 1, ("QB", "RB", "WR", "TE")),)
    std = _mini_config("std", std_roster)
    sf = _mini_config("sf", sf_roster)

    r_std, s_std = vor.compute_replacement_levels(_pool(), std, PROFILE)
    r_sf, s_sf = vor.compute_replacement_levels(_pool(), sf, PROFILE)

    assert s_sf["QB"] > s_std["QB"]                 # more QBs started under superflex
    assert r_sf["QB"] < r_std["QB"]                 # QB replacement level drops
    # QB VOR of the top QB rises
    vor_std = 300 - r_std["QB"]
    vor_sf = 300 - r_sf["QB"]
    assert vor_sf > vor_std


def test_superflex_lifts_qb_overall_rank_on_real_shaped_board():
    """End-to-end on a realistic QB-heavy pool: the best QB's overall rank must improve from a 1-QB
    league to superflex."""
    # QBs outscore skill players in raw points (they do in reality); many startable QBs.
    rows = []
    for k in range(20):
        rows.append(("QB", f"q{k}", 320 - 4 * k))
    for k in range(40):
        rows.append(("RB", f"r{k}", 260 - 4 * k))
    for k in range(50):
        rows.append(("WR", f"w{k}", 255 - 3 * k))
    for k in range(20):
        rows.append(("TE", f"t{k}", 180 - 5 * k))
    pool = pd.DataFrame(
        [{"position": p, "player_id": i, "player_name": i, "league_points": float(v)} for p, i, v in rows]
    )
    std_roster = (
        lc.RosterSlot("QB", 1, ("QB",)),
        lc.RosterSlot("RB", 2, ("RB",)),
        lc.RosterSlot("WR", 2, ("WR",)),
        lc.RosterSlot("TE", 1, ("TE",)),
        lc.RosterSlot("FLEX", 1, ("RB", "WR", "TE")),
    )
    sf_roster = std_roster + (lc.RosterSlot("SUPERFLEX", 1, ("QB", "RB", "WR", "TE")),)
    std = _mini_config("std", std_roster, n_teams=12)
    sf = _mini_config("sf", sf_roster, n_teams=12)

    b_std = vor.build_board(pool, std, PROFILE)
    b_sf = vor.build_board(pool, sf, PROFILE)
    best_qb_rank_std = int(b_std[b_std["position"] == "QB"]["overall_rank"].min())
    best_qb_rank_sf = int(b_sf[b_sf["position"] == "QB"]["overall_rank"].min())
    assert best_qb_rank_sf < best_qb_rank_std   # superflex pulls the top QB up the overall board


def test_full_ppr_lifts_pass_catchers_vs_standard():
    """Face validity: WR/TE points should gain relative to RB/QB going standard → full PPR (more
    pass-catchers near the top). Uses realistic reception volumes so the reception weight bites."""
    df = pd.DataFrame([
        {"position": "RB", "player_id": "rb", "player_name": "rb",
         **{PROFILE.stat_columns[k]: v for k, v in {"rush_yds": 1200, "rush_td": 10, "rec": 30, "rec_yds": 250}.items()}},
        {"position": "WR", "player_id": "wr", "player_name": "wr",
         **{PROFILE.stat_columns[k]: v for k, v in {"rec": 110, "rec_yds": 1400, "rec_td": 10}.items()}},
    ])
    for col in PROFILE.stat_columns.values():
        if col not in df.columns:
            df[col] = 0.0
    std = sc.score_players(df, presets.standard(), PROFILE).set_index("player_id")["league_points"]
    ppr = sc.score_players(df, presets.full_ppr(), PROFILE).set_index("player_id")["league_points"]
    # the WR's share of the two players' points must rise under PPR
    std_share = std["wr"] / (std["wr"] + std["rb"])
    ppr_share = ppr["wr"] / (ppr["wr"] + ppr["rb"])
    assert ppr_share > std_share


def test_build_board_ranks_by_vor_and_carries_interval():
    pool = _pool().copy()
    pool["league_points_p10"] = pool["league_points"] - 20
    pool["league_points_p90"] = pool["league_points"] + 20
    roster = (
        lc.RosterSlot("QB", 1, ("QB",)),
        lc.RosterSlot("RB", 1, ("RB",)),
        lc.RosterSlot("FLEX", 1, ("RB", "WR", "TE")),
    )
    board = vor.build_board(pool, _mini_config("m", roster), PROFILE)
    assert list(board["overall_rank"]) == list(range(1, len(board) + 1))
    assert board["vor"].is_monotonic_decreasing
    # interval shifts by the replacement level
    top = board.iloc[0]
    assert top["vor_p90"] == pytest.approx(top["vor"] + 20)
    assert top["vor_p10"] == pytest.approx(top["vor"] - 20)


def test_replacement_never_negative_when_pool_thinner_than_demand():
    # only 1 TE but a league demanding many — replacement falls to the weakest, floored at 0.
    pool = pd.DataFrame([{"position": "TE", "player_id": "t1", "player_name": "t1", "league_points": 90.0}])
    roster = (lc.RosterSlot("TE", 3, ("TE",)),)
    repl, started = vor.compute_replacement_levels(pool, _mini_config("m", roster, n_teams=12), PROFILE)
    assert repl["TE"] >= 0.0
