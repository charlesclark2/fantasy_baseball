"""Fast-gate unit tests for NF1.2 — the projection-refinement feature families.

Imports ONLY the pure `nf1_2_model` module (numpy/pandas — no `pipeline`, no IO), per the
fast-gate discipline. Covers the family-construction contracts the NF1.2 gate rests on:
  • team-code normalisation crosses every source boundary (LA→LAR, OAK→LV, …);
  • H-SOS aggregates the projection season's ACTUAL schedule to a mean opponent strength and
    joins by the FORWARD team;
  • H-SYSTEM reads the destination team's BASE-season rate (leakage-safe) and a mover's
    pass-rate delta is destination − origin (0 for a stayer);
  • H-CORR (team_qb_quality) is the projection team's best QB MVP-1 projection, on WR/TE rows;
  • H-SPILL's teammate_fp excludes the player himself; vacated_volume sums ONLY departing
    players' base-season usage (the survivorship-order contract);
  • H-OPP joins by base season; H-CONTRACT joins player $ by projection season and TEAM cap
    aggregates by the FORWARD team;
  • the pre-registered per-position sets: WR drops xFP (NF1.1's settled null), families apply
    only where registered, every family column exists in the ablation groups;
  • empty inputs leave NaN columns (never a crash / never a dropped row).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

M12 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_2_model")


# ── synthetic two-team frame (one base season) ─────────────────────────────────────────────────
def _frame():
    """Six players across two teams for projecting 2024 from base 2023: a QB+WR+RB per team, one
    WR mover (KC → BUF), one RB leaving BUF for a team outside the frame (vacates volume)."""
    return pd.DataFrame({
        "player_id": ["qb1", "wr1", "rb1", "qb2", "wr2", "rb2"],
        "player_name": ["QB One", "WR One", "RB One", "QB Two", "WR Two", "RB Two"],
        "position": ["QB", "WR", "RB", "QB", "WR", "RB"],
        "base_team": ["KC", "KC", "BUF", "BUF", "KC", "BUF"],
        "proj_team": ["KC", "BUF", "BUF", "BUF", "KC", "DEN"],
        "base_season": 2023, "projection_season": 2024,
        "mvp1_fp": [320.0, 210.0, 180.0, 280.0, 190.0, 150.0],
        "target_share": [0.0, 0.24, 0.10, 0.0, 0.18, 0.08],
        "carry_share": [0.05, 0.0, 0.55, 0.08, 0.0, 0.40],
    })


def _schedule():
    # 2024: KC plays BUF twice + LA once (tests the LA→LAR norm); BUF plays KC twice + DEN once.
    return pd.DataFrame({
        "season": [2024] * 4,
        "home_team": ["KC", "BUF", "LA", "DEN"],
        "away_team": ["BUF", "KC", "KC", "BUF"],
    })


def _defense():
    return pd.DataFrame({
        "projection_season": [2024] * 4,
        "team": ["KC", "BUF", "LA", "DEN"],
        "pass_def_strength": [1.0, 0.5, -0.5, 0.0],
        "rush_def_strength": [-1.0, 0.25, 0.75, 0.5],
    })


# ══════════════════════════════════════════════════════════════════════════════════════════════
# norm_team
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_norm_team_maps_legacy_and_alias_codes():
    assert M12.norm_team("LA") == "LAR"
    assert M12.norm_team("STL") == "LAR"
    assert M12.norm_team("SD") == "LAC"
    assert M12.norm_team("OAK") == "LV"
    assert M12.norm_team("KC") == "KC"
    assert M12.norm_team(None) is np.nan or np.isnan(M12.norm_team(None))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# H-SOS
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_schedule_sos_mean_opponent_strength_and_normalisation():
    sos = M12.schedule_sos(_schedule(), _defense())
    kc = sos[sos["team"] == "KC"].iloc[0]
    # KC's opponents: BUF, BUF, LAR (from the 'LA' home row) → pass = mean(0.5, 0.5, −0.5)
    assert kc["sos_pass_strength"] == pytest.approx((0.5 + 0.5 - 0.5) / 3)
    assert kc["sos_rush_strength"] == pytest.approx((0.25 + 0.25 + 0.75) / 3)
    # the LA row normalised to LAR appears as a team too
    assert "LAR" in set(sos["team"])


def test_attach_sos_joins_on_forward_team():
    out = M12.attach_sos(_frame(), M12.schedule_sos(_schedule(), _defense()))
    wr1 = out[out["player_id"] == "wr1"].iloc[0]     # mover: proj_team=BUF
    buf = M12.schedule_sos(_schedule(), _defense())
    buf_row = buf[buf["team"] == "BUF"].iloc[0]
    assert wr1["sos_pass_strength"] == pytest.approx(buf_row["sos_pass_strength"])


def test_attach_sos_empty_inputs_leave_nan():
    out = M12.attach_sos(_frame(), pd.DataFrame())
    assert out["sos_pass_strength"].isna().all()
    assert len(out) == 6


# ══════════════════════════════════════════════════════════════════════════════════════════════
# H-SYSTEM
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _team_rates():
    return pd.DataFrame({
        "season": [2023, 2023, 2023],
        "team": ["KC", "BUF", "DEN"],
        "off_pass_rate": [0.65, 0.55, 0.50],
        "off_plays_per_game": [65.0, 62.0, 60.0],
    })


def test_attach_system_stayer_delta_zero_mover_delta_directional():
    out = M12.attach_system(_frame(), _team_rates())
    qb1 = out[out["player_id"] == "qb1"].iloc[0]     # KC stayer
    assert qb1["team_pass_rate"] == pytest.approx(0.65)
    assert qb1["team_pace"] == pytest.approx(65.0)
    assert qb1["pass_rate_delta"] == pytest.approx(0.0)
    wr1 = out[out["player_id"] == "wr1"].iloc[0]     # KC → BUF mover
    assert wr1["team_pass_rate"] == pytest.approx(0.55)          # destination's base-season rate
    assert wr1["pass_rate_delta"] == pytest.approx(0.55 - 0.65)  # destination − origin


def test_attach_system_missing_rates_leave_nan():
    out = M12.attach_system(_frame(), pd.DataFrame())
    assert out["team_pass_rate"].isna().all()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# H-CORR
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_attach_qb_quality_is_projection_teams_best_qb():
    out = M12.attach_qb_quality(_frame())
    wr2 = out[out["player_id"] == "wr2"].iloc[0]     # stays on KC; KC's only QB projects 320
    assert wr2["team_qb_quality"] == pytest.approx(320.0)
    wr1 = out[out["player_id"] == "wr1"].iloc[0]     # moves to BUF; BUF's QB projects 280
    assert wr1["team_qb_quality"] == pytest.approx(280.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# H-SPILL
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_attach_spillover_teammate_excludes_self_and_vacated_counts_leavers_only():
    out = M12.attach_spillover(_frame())
    # BUF projection roster: wr1 (210) + rb1 (180) + qb2 (280)
    wr1 = out[out["player_id"] == "wr1"].iloc[0]
    assert wr1["teammate_fp"] == pytest.approx(180.0 + 280.0)
    # vacated from BUF: rb2 left (target 0.08 + carry 0.40); rb1 stayed; qb2 stayed
    assert wr1["vacated_volume"] == pytest.approx(0.48)
    # KC vacated: wr1 departed (0.24 + 0.0)
    qb1 = out[out["player_id"] == "qb1"].iloc[0]
    assert qb1["vacated_volume"] == pytest.approx(0.24)
    # a team with no departures reads 0, not NaN (DEN has no base-season rows here)
    rb2 = out[out["player_id"] == "rb2"].iloc[0]
    assert rb2["vacated_volume"] == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# H-OPP + H-CONTRACT
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_attach_opportunity_joins_on_base_season():
    shares = pd.DataFrame({"season": [2023, 2022], "player_id": ["wr1", "wr1"],
                           "air_yards_share": [0.30, 0.99], "wopr": [0.60, 0.99]})
    out = M12.attach_opportunity(_frame(), shares)
    wr1 = out[out["player_id"] == "wr1"].iloc[0]
    assert wr1["air_yards_share"] == pytest.approx(0.30)   # the 2023 base row, not 2022
    assert out[out["player_id"] == "qb1"]["wopr"].isna().all()


def test_attach_contract_player_by_projection_season_team_caps_by_forward_team():
    players = pd.DataFrame({
        "season": [2024], "player_id": ["wr1"],
        "log_investment": [2.5], "guaranteed_ratio": [0.8], "cap_hit_pct_team": [0.05],
    })
    teams = pd.DataFrame({
        "season": [2024, 2024], "team_abbr": ["BUF", "KC"],
        "team_ol_cap_pct": [0.22, 0.15], "team_skill_cap_concentration": [0.4, 0.6],
    })
    out = M12.attach_contract(_frame(), players, teams)
    wr1 = out[out["player_id"] == "wr1"].iloc[0]
    assert wr1["log_investment"] == pytest.approx(2.5)
    # the mover carries his FORWARD team's (BUF) line, not his old team's
    assert wr1["team_ol_cap_pct"] == pytest.approx(0.22)
    wr2 = out[out["player_id"] == "wr2"].iloc[0]           # stays KC
    assert wr2["team_ol_cap_pct"] == pytest.approx(0.15)
    assert np.isnan(wr2["log_investment"])                  # no contract row → NaN


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Registration contracts
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_wr_base_set_drops_xfp_qb_rb_te_keep_it():
    assert not any(c in M12.BASE_POSITION_FEATURES["WR"] for c in M12.XFP_FEATURES)
    for pos in ("QB", "RB", "TE"):
        assert any(c in M12.BASE_POSITION_FEATURES[pos] for c in M12.XFP_FEATURES)


def test_families_apply_only_where_registered():
    # QB is never targeted: no opp / qbcorr columns in the QB set
    assert "wopr" not in M12.POSITION_FEATURES["QB"]
    assert "team_qb_quality" not in M12.POSITION_FEATURES["QB"]
    # O-line cap is a QB/RB hypothesis
    assert "team_ol_cap_pct" in M12.POSITION_FEATURES["QB"]
    assert "team_ol_cap_pct" in M12.POSITION_FEATURES["RB"]
    assert "team_ol_cap_pct" not in M12.POSITION_FEATURES["WR"]
    # WR/TE SOS is pass-only; QB/RB carry both legs
    assert "sos_rush_strength" not in M12.POSITION_FEATURES["WR"]
    assert "sos_rush_strength" in M12.POSITION_FEATURES["RB"]
    # qbcorr on the pass-catchers
    assert "team_qb_quality" in M12.POSITION_FEATURES["WR"]
    assert "team_qb_quality" in M12.POSITION_FEATURES["TE"]


def test_every_family_column_is_in_the_ablation_groups():
    grouped = {c for cols in M12.FEATURE_GROUPS.values() for c in cols}
    for c in M12.REFINEMENT_COLS:
        assert c in grouped, c
    # and the legacy NF1.1 groups are still present (deflation counts the whole search)
    for legacy in ("usage", "mover", "env", "xfp"):
        assert legacy in M12.FEATURE_GROUPS


def test_position_sets_have_no_duplicates():
    for pos, feats in M12.POSITION_FEATURES.items():
        assert len(feats) == len(set(feats)), pos


# ══════════════════════════════════════════════════════════════════════════════════════════════
# End-to-end pure pipeline
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_add_refinement_features_end_to_end_and_empty_inputs():
    inputs = M12.RefinementInputs(schedule=_schedule(), defense=_defense(),
                                  team_rates=_team_rates())
    out = M12.add_refinement_features(_frame(), inputs)
    assert len(out) == 6
    for c in M12.REFINEMENT_COLS:
        assert c in out.columns, c
    # frame-derived families populate even with no external inputs for them
    assert out["teammate_fp"].notna().all()
    # pass-catchers on a team WITH a projected QB get the coupling; rb2's DEN has no QB row → NaN
    assert out[out["player_id"].isin(["wr1", "wr2"])]["team_qb_quality"].notna().all()
    assert out[out["player_id"] == "rb2"]["team_qb_quality"].isna().all()
    # externally-fed families with empty inputs stay NaN but never drop rows
    assert out["wopr"].isna().all()
    assert out["log_investment"].isna().all()

    empty = M12.add_refinement_features(_frame(), M12.RefinementInputs())
    assert len(empty) == 6
    assert empty["sos_pass_strength"].isna().all()


def test_learners_fit_on_extended_set_via_nf11_registry():
    """The extended sets flow through NF1.1's learner registry unchanged (the harness contract)."""
    rng = np.random.default_rng(3)
    n = 60
    df = pd.DataFrame({c: rng.normal(size=n) for c in M12.POSITION_FEATURES["WR"]})
    df["mvp1_fp"] = np.clip(rng.normal(150, 40, n), 10, None)
    y = df["mvp1_fp"].to_numpy() + rng.normal(0, 10, n)
    lr = M12.make_pos_learner("pos_ridge", feats=M12.POSITION_FEATURES["WR"], alpha=5.0)
    lr.fit(df, y)
    pred = lr.predict(df)
    assert np.isfinite(pred).all() and len(pred) == n
