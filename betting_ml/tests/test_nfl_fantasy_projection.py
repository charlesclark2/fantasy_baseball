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


# ── NF-D2 slice 1: usage-share role → expected games ─────────────────────────────────────────────
def test_usage_blend_is_noop_when_off_or_absent():
    base_eg = pd.Series([10.0, 12.0, 8.0])
    pos = pd.Series(["RB", "WR", "TE"])
    snap = pd.Series([0.8, 0.9, 0.7])
    tgt = pd.Series([0.1, 0.2, 0.15])
    # blend=0 ⇒ exact MVP-1 baseline (the ablation "off" arm)
    off = sp.blend_usage_into_games(base_eg, pos, snap, tgt, blend=0.0)
    assert np.allclose(off.to_numpy(), base_eg.to_numpy())
    # missing usage columns ⇒ fall through to base_eg unchanged
    none = sp.blend_usage_into_games(base_eg, pos, None, None, blend=0.4)
    assert np.allclose(none.to_numpy(), base_eg.to_numpy())


def test_usage_blend_position_scoping():
    # RB/WR use SNAP share; TE uses TARGET share; QB is untouched (depth rank governs)
    base_eg = pd.Series([9.0, 9.0, 9.0, 9.0])
    pos = pd.Series(["RB", "TE", "QB", "WR"])
    # high snap share, zero target share
    snap = pd.Series([0.95, 0.95, 0.95, 0.95])
    tgt = pd.Series([0.0, 0.0, 0.0, 0.0])
    eg = sp.blend_usage_into_games(base_eg, pos, snap, tgt, blend=0.5)
    # RB & WR (snap-driven) get lifted toward a full-time role by high snap share
    assert eg.iloc[0] > 9.0 and eg.iloc[3] > 9.0
    # QB is untouched regardless of snap share
    assert eg.iloc[2] == pytest.approx(9.0)
    # TE keys off TARGET share (0 here) not snap share ⇒ pulled DOWN, not up like the RB/WR
    assert eg.iloc[1] < 9.0


def test_usage_blend_high_snap_entrenched_starter_beats_low_snap_body():
    # two RBs with the SAME crude role/durability estimate; the entrenched (high-snap) one should end
    # up with more expected games than the rotational (low-snap) body — the volume-earner separation
    base_eg = pd.Series([11.0, 11.0])
    pos = pd.Series(["RB", "RB"])
    snap = pd.Series([0.85, 0.30])
    tgt = pd.Series([0.10, 0.05])
    eg = sp.blend_usage_into_games(base_eg, pos, snap, tgt, blend=0.4)
    assert eg.iloc[0] > eg.iloc[1]
    assert (eg >= 1.0).all() and (eg <= 17.0).all()


def test_usage_blend_partial_coverage_falls_through():
    # a player with a snap-count gap (NaN) keeps the baseline estimate; the covered one is adjusted
    base_eg = pd.Series([10.0, 10.0])
    pos = pd.Series(["WR", "WR"])
    snap = pd.Series([np.nan, 0.9])
    eg = sp.blend_usage_into_games(base_eg, pos, snap, pd.Series([np.nan, np.nan]), blend=0.4)
    assert eg.iloc[0] == pytest.approx(10.0)   # NaN snap ⇒ unchanged
    assert eg.iloc[1] > 10.0                   # covered high-snap WR lifted


def test_veteran_usage_role_reorders_equal_line_by_snap_share():
    # two RBs with an IDENTICAL per-game line + same depth rank/games, differing ONLY in base-season
    # snap share — the higher-snap-share (entrenched volume-earner) must project higher season points.
    def rb(pid, snap):
        base = {"player_id": pid, "player_name": pid, "team_id": "AAA", "position": "RB",
                "games_played": 14, "depth_chart_position_rank": 1, "fp_ppr_sd": 6.0,
                "snap_share": snap, "target_share": 0.08}
        for s in sp._VET_PERGAME_STATS:
            base[s + "_pg"] = 0.0
        base.update(rush_att_pg=15, rush_yds_pg=70, rush_td_pg=0.5, targets_pg=3, rec_pg=2.4, rec_yds_pg=18)
        return base
    base = pd.DataFrame([rb("HIGH_SNAP", 0.85), rb("LOW_SNAP", 0.35)])
    priors = sp.positional_pergame_priors(base)
    on = sp.project_veterans(base, priors, 2026, usage_role_blend=0.4).set_index("player_name")
    off = sp.project_veterans(base, priors, 2026, usage_role_blend=0.0).set_index("player_name")
    # with the feature ON, the entrenched RB outranks the committee body
    assert on.loc["HIGH_SNAP", "proj_fp_ppr"] > on.loc["LOW_SNAP", "proj_fp_ppr"]
    # with the feature OFF (baseline) the identical lines tie
    assert off.loc["HIGH_SNAP", "proj_fp_ppr"] == pytest.approx(off.loc["LOW_SNAP", "proj_fp_ppr"])


# ── NF-D2 slice 3: team-change / depth-jump opportunity ──────────────────────────────────────────
def test_role_volume_prior_orders_by_depth_rank():
    base = _synth_base()
    # add a depth spread so the prior has rank-1 and rank-3 buckets
    rvp = sp.role_volume_prior(base)
    # every entry is a (position, rank)->float; a rank-1 RB should out-produce a rank-3 RB if both exist
    assert all(isinstance(k, tuple) and isinstance(v, float) for k, v in rvp.items())
    assert ("RB", 1) in rvp


def test_mover_scale_boosts_upgrade_and_no_ops_non_movers():
    df = pd.DataFrame({
        "player_id": ["A", "B", "C", "D"],
        "position": ["RB", "RB", "QB", "WR"],
        "base_team": ["AAA", "AAA", "AAA", "AAA"],
        "proj_team": ["BBB", "AAA", "BBB", None],           # A moved, B stayed, C moved(QB), D no proj team
        "depth_chart_position_rank": [1.0, 1.0, 1.0, 1.0],
    })
    rvp = {("RB", 1): 18.0, ("WR", 1): 15.0}                # new-role level well above the current fp
    fp_pg = np.array([9.0, 9.0, 9.0, 9.0])                  # everyone currently at 9/gm
    scale = sp.mover_opportunity_scale(df, rvp, fp_pg, blend=0.5, cap=1.6)
    assert scale[0] > 1.0                                   # A: RB mover upgraded toward 18 → boosted
    assert scale[1] == pytest.approx(1.0)                   # B: not a mover → no-op
    assert scale[2] == pytest.approx(1.0)                   # C: QB out of scope → no-op
    assert scale[3] == pytest.approx(1.0)                   # D: unknown proj team → no-op
    assert (scale <= 1.6 + 1e-9).all() and (scale >= 1 / 1.6 - 1e-9).all()  # clamped


def test_mover_scale_is_noop_without_prior_or_columns():
    df = pd.DataFrame({"player_id": ["A"], "position": ["RB"]})  # no base_team/proj_team
    assert sp.mover_opportunity_scale(df, {("RB", 1): 18.0}, np.array([9.0])) [0] == pytest.approx(1.0)
    df2 = pd.DataFrame({"player_id": ["A"], "position": ["RB"], "base_team": ["X"], "proj_team": ["Y"]})
    assert sp.mover_opportunity_scale(df2, {}, np.array([9.0]))[0] == pytest.approx(1.0)  # empty prior


def test_veteran_mover_into_bigger_role_projects_higher():
    # a backup-usage RB (low per-game line) who CHANGES teams into a lead role should project higher
    # with the mover feature ON than OFF — the stale old-team line understates the new opportunity.
    def rb(pid, base_team, proj_team, rank):
        base = {"player_id": pid, "player_name": pid, "team_id": proj_team, "position": "RB",
                "games_played": 14, "depth_chart_position_rank": rank, "fp_ppr_sd": 6.0,
                "base_team": base_team, "proj_team": proj_team}
        for s in sp._VET_PERGAME_STATS:
            base[s + "_pg"] = 0.0
        base.update(rush_att_pg=8, rush_yds_pg=34, rush_td_pg=0.2, targets_pg=2, rec_pg=1.5, rec_yds_pg=11)
        return base
    # a fuller field so the role-volume prior has a believable rank-1 level to pull toward
    rows = [rb(f"S{i}", "AAA", "AAA", 1) for i in range(6)]      # incumbent rank-1 starters (higher volume)
    for r in rows:
        r.update(rush_att_pg=17, rush_yds_pg=78, rush_td_pg=0.5, targets_pg=3, rec_pg=2.4, rec_yds_pg=18)
    rows.append(rb("MOVER", "OLD", "NEW", 1))                    # our backup-line RB moving into a rank-1 role
    base = pd.DataFrame(rows)
    priors = sp.positional_pergame_priors(base)
    rvp = sp.role_volume_prior(base)
    on = sp.project_veterans(base, priors, 2026, role_vol_prior=rvp, mover_opportunity_blend=0.35).set_index("player_id")
    off = sp.project_veterans(base, priors, 2026, role_vol_prior=None).set_index("player_id")
    assert on.loc["MOVER", "proj_fp_ppr"] > off.loc["MOVER", "proj_fp_ppr"]   # boosted by the new role
    assert on.loc["S0", "proj_fp_ppr"] == pytest.approx(off.loc["S0", "proj_fp_ppr"])  # stayer unchanged


# ── NF-D2 slice 4: Vegas team environment (QB) ───────────────────────────────────────────────────
def test_environment_tilt_boosts_high_env_qb_and_no_ops_others():
    df = pd.DataFrame({
        "position": ["QB", "QB", "QB", "RB"],
        "team_env": [30.0, 22.0, 14.0, 30.0],   # a high / mid / low scoring environment; RB is out of scope
    })
    # pad to ≥10 QBs so the z-score path activates
    extra = pd.DataFrame({"position": ["QB"] * 8, "team_env": [22.0] * 8})
    d = pd.concat([df, extra], ignore_index=True)
    scale = sp.environment_tilt_scale(d, blend=0.15)
    assert scale[0] > 1.0            # high-env QB boosted
    assert scale[2] < 1.0            # low-env QB cut
    assert scale[3] == pytest.approx(1.0)   # RB out of scope
    assert (scale >= sp._ENV_TILT_LO - 1e-9).all() and (scale <= sp._ENV_TILT_HI + 1e-9).all()


def test_environment_tilt_is_noop_without_column_or_blend():
    d = pd.DataFrame({"position": ["QB"] * 12})   # no team_env column
    assert np.allclose(sp.environment_tilt_scale(d, blend=0.15), 1.0)
    d2 = pd.DataFrame({"position": ["QB"] * 12, "team_env": [25.0] * 12})
    assert np.allclose(sp.environment_tilt_scale(d2, blend=0.0), 1.0)   # blend 0 = off


def test_veteran_env_tilt_orders_qbs_by_team_environment():
    # two identical QBs differing only in team environment — the higher-env one projects higher
    def qb(pid, env):
        base = {"player_id": pid, "player_name": pid, "team_id": "AAA", "position": "QB",
                "games_played": 16, "depth_chart_position_rank": 1, "fp_ppr_sd": 6.0, "team_env": env}
        for s in sp._VET_PERGAME_STATS:
            base[s + "_pg"] = 0.0
        base.update(pass_att_pg=34, pass_cmp_pg=22, pass_yds_pg=250, pass_td_pg=1.6, pass_int_pg=0.7,
                    rush_att_pg=4, rush_yds_pg=20, rush_td_pg=0.2)
        return base
    rows = [qb(f"Q{i}", 20.0 + (i % 5)) for i in range(12)]     # a spread of environments
    rows.append(qb("HIGH", 30.0))
    rows.append(qb("LOW", 15.0))
    base = pd.DataFrame(rows)
    priors = sp.positional_pergame_priors(base)
    on = sp.project_veterans(base, priors, 2026, env_tilt_blend=0.15).set_index("player_id")
    off = sp.project_veterans(base, priors, 2026, env_tilt_blend=0.0).set_index("player_id")
    assert on.loc["HIGH", "proj_fp_ppr"] > off.loc["HIGH", "proj_fp_ppr"]   # boosted
    assert on.loc["LOW", "proj_fp_ppr"] < off.loc["LOW", "proj_fp_ppr"]     # cut
    assert on.loc["HIGH", "proj_fp_ppr"] > on.loc["LOW", "proj_fp_ppr"]


# ── NF-D2 slice 5: injury / availability ─────────────────────────────────────────────────────────
def test_injury_games_caps_flagged_status_and_no_ops_others():
    df = pd.DataFrame({
        "proj_status": ["ACT", "RES", "PUP", "SUS", None],
        "proj_games": [16.0, 16.0, 15.0, 16.0, 14.0],
    })
    eg = sp.injury_availability_games(df, blend=1.0)   # hard cap
    assert eg[0] == pytest.approx(16.0)                # ACT untouched
    assert eg[1] == pytest.approx(sp._INJURY_STATUS_GAMES_CAP["RES"])   # IR capped
    assert eg[2] == pytest.approx(sp._INJURY_STATUS_GAMES_CAP["PUP"])   # PUP capped
    assert eg[3] == pytest.approx(sp._INJURY_STATUS_GAMES_CAP["SUS"])   # SUS capped
    assert eg[4] == pytest.approx(14.0)                # unknown status untouched
    # cap only moves games DOWN — a flagged player already below the cap is unchanged
    df2 = pd.DataFrame({"proj_status": ["RES"], "proj_games": [2.0]})
    assert sp.injury_availability_games(df2, blend=1.0)[0] == pytest.approx(2.0)


def test_injury_games_is_noop_without_column_or_blend():
    df = pd.DataFrame({"proj_games": [16.0]})          # no proj_status
    assert sp.injury_availability_games(df, blend=0.7)[0] == pytest.approx(16.0)
    df2 = pd.DataFrame({"proj_status": ["RES"], "proj_games": [16.0]})
    assert sp.injury_availability_games(df2, blend=0.0)[0] == pytest.approx(16.0)


def test_veteran_injured_player_projects_far_below_healthy_twin():
    # two identical every-down RBs; one is flagged RES (IR) for the projection season → far fewer games
    def rb(pid, status):
        base = {"player_id": pid, "player_name": pid, "team_id": "AAA", "position": "RB",
                "games_played": 16, "depth_chart_position_rank": 1, "fp_ppr_sd": 6.0, "proj_status": status}
        for s in sp._VET_PERGAME_STATS:
            base[s + "_pg"] = 0.0
        base.update(rush_att_pg=17, rush_yds_pg=80, rush_td_pg=0.6, targets_pg=4, rec_pg=3, rec_yds_pg=25)
        return base
    base = pd.DataFrame([rb("HEALTHY", "ACT"), rb("INJURED", "RES")])
    proj = sp.project_veterans(base, sp.positional_pergame_priors(base), 2026,
                               injury_override_blend=0.7).set_index("player_name")
    assert proj.loc["INJURED", "proj_games"] < proj.loc["HEALTHY", "proj_games"]
    assert proj.loc["INJURED", "proj_fp_ppr"] < 0.5 * proj.loc["HEALTHY", "proj_fp_ppr"]  # materially demoted


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


# ── NF-D2 #6 / NF-D3: ADP market-consensus prior + benchmark ─────────────────────────────────────
adp = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.adp_source")


def _adp_frame(fps, adps, positions):
    return pd.DataFrame({
        "player_id": [f"P{i}" for i in range(len(fps))],
        "position": positions,
        "proj_fp_ppr": fps,
        "adp": adps,
    })


def test_zscore_is_finite_safe():
    z = sp._zscore(np.array([1.0, 2.0, 3.0, np.nan]))
    assert np.isnan(z[3])
    assert z[0] < z[1] < z[2]
    # a degenerate (all-equal) group yields zeros, not NaN/inf
    assert np.allclose(sp._zscore(np.array([5.0, 5.0, 5.0])), 0.0)


def test_blend_adp_prior_is_noop_when_off_or_absent():
    df = _adp_frame([100.0, 90.0, 80.0], [3.0, 1.0, 2.0], ["RB", "RB", "RB"])
    # blend=0 ⇒ EXACT no-op (the market-blind product / model-only arm)
    assert np.allclose(sp.blend_adp_prior(df, blend=0.0), df["proj_fp_ppr"].to_numpy())
    # missing adp column ⇒ no-op
    assert np.allclose(sp.blend_adp_prior(df.drop(columns=["adp"]), blend=0.7),
                       df["proj_fp_ppr"].to_numpy())


def test_blend_adp_prior_preserves_point_multiset():
    # the quantile remap reorders WITHIN a position but must keep the exact set of projected points
    df = _adp_frame([100.0, 90.0, 80.0, 70.0], [4.0, 3.0, 2.0, 1.0], ["WR"] * 4)
    out = sp.blend_adp_prior(df, blend=0.6)
    assert sorted(out.tolist()) == sorted(df["proj_fp_ppr"].tolist())


def test_blend_adp_prior_reorders_toward_adp():
    # model ranks A>B>C>D; ADP ranks them exactly REVERSED (D best). A full blend to ADP must flip the
    # order so the lowest-ADP (best) player gets the top points.
    df = _adp_frame([100.0, 90.0, 80.0, 70.0], [4.0, 3.0, 2.0, 1.0], ["RB"] * 4)
    out = sp.blend_adp_prior(df, blend=1.0)
    # player P3 (adp=1, the consensus #1) should now carry the position's top points (100)
    assert out[3] == pytest.approx(100.0)
    assert out[0] == pytest.approx(70.0)  # model's #1 (worst ADP) drops to the bottom


def test_blend_adp_prior_position_scoping():
    # QB/RB scoped: RB reorders toward ADP; WR is left exactly at the model line
    df = _adp_frame([100.0, 90.0, 60.0, 50.0], [2.0, 1.0, 2.0, 1.0], ["RB", "RB", "WR", "WR"])
    out = sp.blend_adp_prior(df, blend=1.0, positions=("QB", "RB"))
    # RB pair flips toward ADP (P1 has better adp ⇒ gets 100)
    assert out[1] == pytest.approx(100.0) and out[0] == pytest.approx(90.0)
    # WR pair is untouched (scoped out) ⇒ exactly the model line
    assert out[2] == pytest.approx(60.0) and out[3] == pytest.approx(50.0)


def test_blend_adp_prior_no_adp_player_keeps_model_score():
    # a player with NaN ADP falls through in place (keeps the model score) while the covered ones blend
    df = _adp_frame([100.0, 90.0, 80.0], [np.nan, 1.0, 2.0], ["RB"] * 3)
    out = sp.blend_adp_prior(df, blend=1.0)
    # still a valid permutation of the point multiset
    assert sorted(out.tolist()) == [80.0, 90.0, 100.0]


def test_adp_name_normalization_and_aliases():
    n = adp._normalize_name
    assert n("Marquise Brown") == n("Hollywood Brown")     # nickname alias
    assert n("Kenneth Walker III") == "kenneth walker"     # generational suffix stripped
    assert n("Ja'Marr Chase") == "jamarr chase"            # punctuation removed
    assert n("Amon-Ra St. Brown") == "amonra st brown"


# ── NF-D3: FantasyPros ECR benchmark + the standing scorecard ─────────────────────────────────────
fp = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.fantasypros_source")
bs = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.benchmark_scorecard")


def _fp_payload():
    return {
        "total_experts": 200, "last_updated": "9/06",
        "players": [
            {"player_name": "Christian McCaffrey", "player_position_id": "RB", "player_team_id": "SF",
             "rank_ecr": 1, "rank_ave": "2.38", "rank_std": "4.45", "rank_min": "1", "rank_max": "55",
             "pos_rank": "RB1", "tier": 1},
            {"player_name": "Ja'Marr Chase", "player_position_id": "WR", "player_team_id": "CIN",
             "rank_ecr": 2, "rank_ave": "3.1", "rank_std": "3.0", "rank_min": "1", "rank_max": "20",
             "pos_rank": "WR1", "tier": 1},
            # a K row that must be dropped from the skill crosswalk
            {"player_name": "Justin Tucker", "player_position_id": "PK", "player_team_id": "BAL",
             "rank_ecr": 200, "rank_ave": "200", "rank_std": "1", "rank_min": "190", "rank_max": "210",
             "pos_rank": "K1", "tier": 15},
        ],
    }


def test_fp_ecr_parses_from_cache(tmp_path):
    # priming the cache means fetch does NO network call — pure parse of a frozen preseason snapshot
    import json
    (tmp_path / "fp_ecr_PPR_2024.json").write_text(json.dumps(_fp_payload()))
    df = fp.fetch_fp_ecr(2024, scoring="PPR", cache_dir=tmp_path)
    assert set(["rank_ecr", "rank_ave", "pos_rank", "position", "player_name"]).issubset(df.columns)
    assert (df["season"] == 2024).all() and (df["source"] == "fantasypros").all()
    cmc = df[df["player_name"] == "Christian McCaffrey"].iloc[0]
    assert cmc["rank_ecr"] == 1 and cmc["position"] == "RB"
    assert df[df["player_name"] == "Justin Tucker"].iloc[0]["position"] == "K"  # PK→K normalized
    # dispersion fields coerced to numeric
    assert float(cmc["rank_ave"]) == pytest.approx(2.38)


def test_fp_ecr_empty_when_no_players(tmp_path):
    import json
    (tmp_path / "fp_ecr_PPR_2099.json").write_text(json.dumps({"players": []}))
    df = fp.fetch_fp_ecr(2099, cache_dir=tmp_path)
    assert df.empty and "rank_ecr" in df.columns


# ── scorecard metric primitives (pure DataFrame logic, no con) ────────────────────────────────────
def _scored(us, sys_score, real, positions):
    return pd.DataFrame({
        "player_id": [f"P{i}" for i in range(len(us))],
        "position": positions,
        "proj_fp_ppr": us,
        "sys_score": sys_score,
        "real_fp_ppr": real,
    })


def test_rank_mae_zero_for_perfect_order():
    # a system whose within-position order EXACTLY matches realized has rank-MAE 0
    d = _scored([50, 40, 30, 20, 10], [50, 40, 30, 20, 10], [90, 80, 70, 60, 50], ["RB"] * 5)
    assert bs._rank_mae(d, "sys_score") == 0.0
    # a REVERSED order is maximally wrong (non-zero)
    d2 = _scored([50, 40, 30, 20, 10], [10, 20, 30, 40, 50], [90, 80, 70, 60, 50], ["RB"] * 5)
    assert bs._rank_mae(d2, "sys_score") > 0


def test_within_position_rho_and_delta_favours_better_orderer():
    # our model orders RB perfectly; the "system" orders it reversed → +Δρ for us
    n = 12
    real = list(range(n, 0, -1))
    us = list(range(n, 0, -1))          # perfect
    syss = list(range(1, n + 1))        # reversed
    d = _scored(us, syss, real, ["RB"] * n)
    res = bs._score_pair(d, "proj_fp_ppr", "sys_score")
    assert res["us"]["rho_pooled"] == pytest.approx(1.0)
    assert res["system"]["rho_pooled"] == pytest.approx(-1.0)
    assert res["delta_rho_pooled"] > 0                      # +Δ favours us
    assert res["delta_rank_mae"] < 0                        # lower rank-MAE for us


def test_disagreement_panel_credits_the_right_side():
    # build a WR pool where, on the biggest us-vs-system disagreements, US predicts realized better
    rng = np.random.default_rng(0)
    n = 40
    real = rng.normal(0, 1, n)
    us = real + rng.normal(0, 0.2, n)        # us tracks realized closely
    syss = rng.normal(0, 1, n)               # system is noise
    d = _scored(list(us), list(syss), list(real), ["WR"] * n)
    dz = bs._disagreement(d, "proj_fp_ppr", "sys_score")
    assert dz and dz["us"] > dz["system"]


def test_find_col_matches_case_and_space_insensitively():
    assert bs._find_col(["Player Name", "Pos", "Overall Rank"], bs._RANK_COLS) == "Overall Rank"
    assert bs._find_col(["player", "position", "FPTS"], bs._POINTS_COLS) == "FPTS"
    assert bs._find_col(["a", "b"], bs._RANK_COLS) is None


def test_discover_file_benchmarks_parses_system_and_season(tmp_path):
    (tmp_path / "fantasy_footballers_2025.csv").write_text("player_name,position,rank\nX,RB,1\n")
    (tmp_path / "pff_2024.csv").write_text("name,pos,points\nY,WR,300\n")
    (tmp_path / "junk.csv").write_text("a,b\n1,2\n")            # no _season suffix → skipped
    got = {(f["system"], f["season"]) for f in bs.discover_file_benchmarks(tmp_path)}
    assert ("fantasy_footballers", 2025) in got and ("pff", 2024) in got
    assert not any(f["system"] == "junk" for f in bs.discover_file_benchmarks(tmp_path))


def test_load_file_benchmark_points_and_rank(tmp_path, monkeypatch):
    # attach_gsis needs a con; stub it to assign a deterministic player_id per row (skill only)
    def _fake_xw(con, df, season, schema="main_nfl_marts"):
        out = df.copy()
        out["player_id"] = ["G" + str(i) for i in range(len(out))]
        return out
    monkeypatch.setattr(bs.A, "attach_gsis", _fake_xw)
    # POINTS file → score == points (higher better)
    pts = tmp_path / "fantasy_footballers_2025.csv"
    pts.write_text("Player,Position,Proj FP PPR\nA,RB,300\nB,WR,250\n")
    fpts = bs.load_file_benchmark(None, pts, 2025)
    assert set(fpts.columns) == {"player_id", "position", "score"}
    assert fpts.sort_values("score", ascending=False).iloc[0]["score"] == 300
    # RANK file → score == -rank (rank 1 is best → highest score)
    rk = tmp_path / "espn_2025.csv"
    rk.write_text("name,pos,overall_rank\nA,RB,1\nB,WR,5\n")
    frk = bs.load_file_benchmark(None, rk, 2025)
    assert frk.sort_values("score", ascending=False).iloc[0]["score"] == -1


def test_load_file_benchmark_raises_on_missing_columns(tmp_path):
    bad = tmp_path / "x_2025.csv"
    bad.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError):
        bs.load_file_benchmark(None, bad, 2025)


def test_sleeper_parses_projection_and_filters_to_skill(tmp_path):
    import json
    sl = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.sleeper_source")
    payload = [
        {"company": "rotowire", "team": "SF", "player_id": "1",
         "player": {"first_name": "Christian", "last_name": "McCaffrey", "position": "RB"},
         "stats": {"pts_ppr": 363.3, "pts_half_ppr": 320.0, "pts_std": 280.0, "gp": 17.0}},
        {"company": "rotowire", "team": "BAL", "player_id": "2",
         "player": {"first_name": "Justin", "last_name": "Tucker", "position": "K"},  # dropped (non-skill)
         "stats": {"pts_ppr": 150.0, "gp": 17.0}},
    ]
    (tmp_path / "sleeper_2021.json").write_text(json.dumps(payload))
    df = sl.fetch_sleeper_proj(2021, cache_dir=tmp_path)
    assert list(df["position"].unique()) == ["RB"]                 # K filtered out
    cmc = df.iloc[0]
    assert cmc["player_name"] == "Christian McCaffrey"
    assert cmc["proj_pts_ppr"] == pytest.approx(363.3) and cmc["proj_games"] == pytest.approx(17.0)
    assert cmc["provider"] == "rotowire"


def test_espn_parses_ppr_draftrank_and_skips_unranked(tmp_path):
    import json
    es = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.espn_source")
    payload = {"players": [
        {"fullName": "Ja'Marr Chase", "defaultPositionId": 3, "id": 100,
         "draftRanksByRankType": {"PPR": {"rank": 2}}},
        {"fullName": "Some Kicker", "defaultPositionId": 5, "id": 101,      # K → dropped (non-skill)
         "draftRanksByRankType": {"PPR": {"rank": 180}}},
        {"fullName": "Unranked Guy", "defaultPositionId": 2, "id": 102,     # no PPR rank → dropped
         "draftRanksByRankType": {}},
    ]}
    (tmp_path / "espn_2024.json").write_text(json.dumps(payload))
    df = es.fetch_espn_draftranks(2024, cache_dir=tmp_path)
    assert len(df) == 1 and df.iloc[0]["player_name"] == "Ja'Marr Chase"
    assert df.iloc[0]["position"] == "WR" and df.iloc[0]["ppr_draft_rank"] == 2.0


def test_espn_empty_when_no_ranks(tmp_path):
    import json
    es = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.espn_source")
    (tmp_path / "espn_2019.json").write_text(json.dumps({"players": []}))
    df = es.fetch_espn_draftranks(2019, cache_dir=tmp_path)
    assert df.empty and "ppr_draft_rank" in df.columns


def test_sleeper_scores_by_points_espn_by_negrank(tmp_path, monkeypatch):
    # the registry: sleeper score = +points (higher better); espn score = -rank (rank 1 → highest)
    def _fake_xw(con, df, season, schema="main_nfl_marts"):
        out = df.copy(); out["player_id"] = ["G" + str(i) for i in range(len(out))]
        return out
    monkeypatch.setattr(bs.S, "load_sleeper_for_season",
                        lambda con, s, schema="main_nfl_marts": _fake_xw(con, pd.DataFrame(
                            {"position": ["RB", "WR"], "proj_pts_ppr": [300.0, 250.0]}), s))
    monkeypatch.setattr(bs.E, "load_espn_for_season",
                        lambda con, s, schema="main_nfl_marts": _fake_xw(con, pd.DataFrame(
                            {"position": ["RB", "WR"], "ppr_draft_rank": [1.0, 5.0]}), s))
    sfr = bs._sleeper_system(None, 2024, "main_nfl_marts")
    assert sfr.sort_values("score", ascending=False).iloc[0]["score"] == 300.0     # points, higher better
    efr = bs._espn_system(None, 2024, "main_nfl_marts")
    assert efr.sort_values("score", ascending=False).iloc[0]["score"] == -1.0       # rank 1 → top score


def test_aggregate_averages_across_seasons():
    per_season = [
        {"season": 2023, "systems": {"ecr": {
            "delta_rho_pooled": 0.02, "delta_rank_mae": -1.0, "delta_rho_by_pos": {"WR": 0.04},
            "us": {"rho_pooled": 0.60}, "system": {"rho_pooled": 0.58}, "disagreement": {"us": 0.5, "system": 0.3}}}},
        {"season": 2024, "systems": {"ecr": {
            "delta_rho_pooled": 0.04, "delta_rank_mae": -3.0, "delta_rho_by_pos": {"WR": 0.06},
            "us": {"rho_pooled": 0.62}, "system": {"rho_pooled": 0.58}, "disagreement": {"us": 0.5, "system": 0.3}}}},
    ]
    agg = bs._aggregate(per_season)
    assert agg["ecr"]["n_seasons"] == 2
    assert agg["ecr"]["delta_rho_pooled"] == pytest.approx(0.03)
    assert agg["ecr"]["delta_rho_by_pos"]["WR"] == pytest.approx(0.05)
