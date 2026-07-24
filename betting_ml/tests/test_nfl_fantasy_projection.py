"""Fast-gate unit tests for the NF-FASTPATH 2026 fantasy season projection (pure model logic).

Imports ONLY the pure `season_projection` module (numpy/pandas — no `pipeline`, no IO), per the
fast-gate discipline. Covers the two behavioural contracts the story's gate rests on: the
expected-games playing-time fix (small-sample backups must NOT project like full-time starters) and
the rookie model staying physically bounded (no per-stat blow-up, an internally-consistent line).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

sp = pytest.importorskip(
    "quant_sports_intel_models.football.nfl.fantasy.season_projection"
)


# ── scoring ─────────────────────────────────────────────────────────────────────────────────────
def test_score_line_matches_standard_ppr():
    df = pd.DataFrame([{
        "proj_pass_yds": 4000, "proj_pass_td": 30, "proj_pass_int": 10,
        "proj_rush_yds": 300, "proj_rush_td": 3,
        "proj_rec_yds": 0, "proj_rec_td": 0, "proj_rec": 0,
        "proj_fumbles_lost": 2, "proj_two_pt": np.nan,
    }])
    out = sp.score_line(df, prefix="proj_")
    # 4000*.04 + 30*4 + 10*-2 + 300*.1 + 3*6 + 2*-2 = 160+120-20+30+18-4 = 304
    assert out["proj_fp_std"].iloc[0] == pytest.approx(304.0)
    # no receptions ⇒ ppr == std == half
    assert out["proj_fp_ppr"].iloc[0] == pytest.approx(304.0)


def test_ppr_reception_premium():
    df = pd.DataFrame([{"proj_rec_yds": 1000, "proj_rec": 100, "proj_rec_td": 5}])
    out = sp.score_line(df, prefix="proj_")
    # std = 100 + 30 = 130; half = +50 ; ppr = +100
    assert out["proj_fp_std"].iloc[0] == pytest.approx(130.0)
    assert out["proj_fp_half"].iloc[0] == pytest.approx(180.0)
    assert out["proj_fp_ppr"].iloc[0] == pytest.approx(230.0)


# ── expected games (the backup-QB fix) ──────────────────────────────────────────────────────────
def test_expected_games_demotes_small_sample_backup():
    pos = pd.Series(["QB", "QB", "RB"])
    rank = pd.Series([1.0, 2.0, 1.0])
    games = pd.Series([16.0, 4.0, 17.0])
    eg = sp.expected_games(games, rank, pos)
    assert eg.iloc[0] >= 15.5          # a rank-1 16-game QB stays near full-time
    assert eg.iloc[1] <= 6.0           # a rank-2 4-game backup projects to a handful of games
    assert eg.iloc[2] <= 17.0 and eg.iloc[2] >= 15.5


def test_expected_games_is_clamped():
    eg = sp.expected_games(pd.Series([0.0, 99.0]), pd.Series([9.0, 1.0]), pd.Series(["WR", "WR"]))
    assert (eg >= 1.0).all() and (eg <= 17.0).all()


def test_expected_games_unknown_rank_uses_durability_proxy():
    # missing depth rank must not silently default to full-time
    eg = sp.expected_games(pd.Series([3.0]), pd.Series([np.nan]), pd.Series(["RB"]))
    assert eg.iloc[0] < 8.0


# ── shrinkage ───────────────────────────────────────────────────────────────────────────────────
def test_shrink_pulls_small_sample_harder():
    prior = np.array([10.0, 10.0])
    player = np.array([40.0, 40.0])
    games = np.array([2.0, 16.0])
    out = sp._shrink_pergame(player, games, prior, 5.0)
    # the 2-game line is pulled further toward the prior than the 16-game line
    assert out[0] < out[1]
    assert out[1] > 30.0  # a full season is trusted


# ── veteran projection end-to-end (synthetic) ────────────────────────────────────────────────────
def _synth_base():
    def row(pid, name, pos, rank, g, **pg):
        base = {"player_id": pid, "player_name": name, "team_id": "AAA", "position": pos,
                "games_played": g, "depth_chart_position_rank": rank, "fp_ppr_sd": 6.0}
        for s in sp._VET_PERGAME_STATS:
            base[s + "_pg"] = pg.get(s, 0.0)
        return base
    return pd.DataFrame([
        row("1", "STARTER RB", "RB", 1, 16, rush_att=18, rush_yds=85, rush_td=0.6, targets=4, rec=3, rec_yds=25),
        row("2", "STARTER RB2", "RB", 1, 15, rush_att=16, rush_yds=72, rush_td=0.5, targets=3, rec=2.4, rec_yds=18),
        row("3", "BACKUP RB", "RB", 3, 3, rush_att=15, rush_yds=80, rush_td=0.7, targets=3, rec=2, rec_yds=20),
        row("4", "STARTER QB", "QB", 1, 16, pass_att=34, pass_cmp=22, pass_yds=250, pass_td=1.6, pass_int=0.7,
            rush_att=4, rush_yds=20, rush_td=0.2),
        row("5", "BACKUP QB", "QB", 2, 3, pass_att=33, pass_cmp=21, pass_yds=240, pass_td=1.5, pass_int=0.6,
            rush_att=6, rush_yds=35, rush_td=0.4),
    ])


def test_veteran_backup_projects_below_starter_despite_similar_rate():
    base = _synth_base()
    priors = sp.positional_pergame_priors(base)
    proj = sp.project_veterans(base, priors, 2026).set_index("player_name")
    # the backup RB has a HIGHER per-game rate than the starters but must project to far fewer season
    # points because expected games collapses (the mart_projections_preseason failure this fixes)
    assert proj.loc["BACKUP RB", "proj_fp_ppr"] < proj.loc["STARTER RB", "proj_fp_ppr"]
    assert proj.loc["BACKUP QB", "proj_fp_ppr"] < proj.loc["STARTER QB", "proj_fp_ppr"]
    # raw line internal consistency
    assert (proj["proj_rec"] <= proj["proj_targets"] + 1e-6).all()
    assert (proj["proj_pass_cmp"] <= proj["proj_pass_att"] + 1e-6).all()


def test_veteran_output_has_full_schema_and_interval():
    base = _synth_base()
    proj = sp.project_veterans(base, sp.positional_pergame_priors(base), 2026)
    for c in sp.RAW_STAT_COLS:
        assert c in proj.columns
    assert (proj["fp_ppr_p10"] <= proj["proj_fp_ppr"] + 1e-6).all()
    assert (proj["fp_ppr_p90"] >= proj["proj_fp_ppr"] - 1e-6).all()
    assert (proj["fp_ppr_p10"] >= 0).all()  # floored
    assert (proj["proj_games"] <= 17.0).all()


# ── rookie projection (synthetic) ────────────────────────────────────────────────────────────────
def _synth_rookie_hist():
    rng = np.random.default_rng(0)
    rows = []
    for pos, base_yds, base_fp in [("RB", 900, 170), ("WR", 850, 150), ("QB", 3600, 240), ("TE", 450, 90)]:
        for i in range(40):
            overall = int(rng.integers(1, 255))
            scale = max(0.05, (260 - overall) / 260.0)  # earlier pick ⇒ more production
            fp = max(2.0, base_fp * scale * rng.uniform(0.6, 1.4))
            rows.append({
                "position_group": pos, "draft_overall": overall, "games": min(17, 6 + scale * 11),
                "rookie_fp_ppr": fp,
                "pass_att": (base_yds / 8) * scale if pos == "QB" else 0.0,
                "pass_cmp": (base_yds / 12) * scale if pos == "QB" else 0.0,
                "pass_yds": base_yds * scale if pos == "QB" else 0.0,
                "pass_td": 22 * scale if pos == "QB" else 0.0,
                "pass_int": 12 * scale if pos == "QB" else 0.0,
                "rush_att": 200 * scale if pos == "RB" else (60 * scale if pos == "QB" else 0.0),
                "rush_yds": base_yds * scale if pos == "RB" else (300 * scale if pos == "QB" else 0.0),
                "rush_td": 7 * scale if pos == "RB" else 0.0,
                "targets": 90 * scale if pos in ("WR", "TE", "RB") else 0.0,
                "rec": 60 * scale if pos in ("WR", "TE", "RB") else 0.0,
                "rec_yds": (base_yds if pos in ("WR", "TE") else 250) * scale if pos != "QB" else 0.0,
                "rec_td": 5 * scale if pos in ("WR", "TE", "RB") else 0.0,
            })
    return pd.DataFrame(rows)


def _synth_incoming():
    return pd.DataFrame([
        {"gsis_id": "R1", "player_name": "Elite RB", "position_group": "RB", "nfl_position": "RB",
         "draft_overall": 3, "projected_nfl_z": 1.0},
        {"gsis_id": "R2", "player_name": "Mid WR", "position_group": "WR", "nfl_position": "WR",
         "draft_overall": 60, "projected_nfl_z": 0.0},
        {"gsis_id": "R3", "player_name": "Late TE", "position_group": "TE", "nfl_position": "TE",
         "draft_overall": 200, "projected_nfl_z": -0.5},
        {"gsis_id": "R4", "player_name": "DL guy", "position_group": "DL", "nfl_position": "DT",
         "draft_overall": 10, "projected_nfl_z": 1.5},  # must be dropped (no fantasy line)
    ])


def test_rookies_are_bounded_and_consistent():
    curve = sp.fit_rookie_slot_curves(_synth_rookie_hist())
    proj = sp.project_rookies(_synth_incoming(), curve, 2026)
    # defensive rookie is excluded
    assert "DL guy" not in set(proj["player_name"])
    # every rookie fp is bounded by the positional ceiling (no per-stat blow-up)
    for _, r in proj.iterrows():
        ceiling = curve.fp_ceiling.get(
            _synth_incoming().set_index("player_name").loc[r["player_name"], "position_group"], 1e9)
        assert r["proj_fp_ppr"] <= ceiling * 1.01 + 1.0
    # earlier pick ⇒ more projected value (within reason), line internally consistent
    p = proj.set_index("player_name")
    assert p.loc["Elite RB", "proj_fp_ppr"] > p.loc["Late TE", "proj_fp_ppr"]
    assert (p["proj_rec"] <= p["proj_targets"] + 1e-6).all()
    assert (p["proj_rush_yds"] < 2100).all()  # physically plausible — no 2,400-yd rookie
    assert p["is_rookie"].all()
    assert (p["uncertainty_type"] == "parameter").all()


def test_rookie_residual_nudge_orders_equal_slot_by_talent():
    curve = sp.fit_rookie_slot_curves(_synth_rookie_hist())
    incoming = pd.DataFrame([
        {"gsis_id": f"W{i}", "player_name": f"WR{i}", "position_group": "WR", "nfl_position": "WR",
         "draft_overall": 50, "projected_nfl_z": z}
        for i, z in enumerate([2.0, 1.0, 0.0, -1.0, -2.0, 0.5])
    ])
    proj = sp.project_rookies(incoming, curve, 2026).set_index("player_name")
    # same slot: the higher-talent (P1A z) rookie projects higher
    assert proj.loc["WR0", "proj_fp_ppr"] > proj.loc["WR4", "proj_fp_ppr"]
