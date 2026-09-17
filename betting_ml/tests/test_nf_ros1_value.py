"""NF-ROS1 — guards on the rest-of-season value machinery (registration §9).

Fast gate: imports `ros_value` (pure) and drives `run_nf_ros1.assemble` with its three IO loaders
stubbed, so the real assembly code path runs with no lake and no credentials.
"""
from __future__ import annotations

import ast
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from quant_sports_intel_models.football.nfl.fantasy import ros_value as V

REPO = Path(__file__).resolve().parents[2]
FANT = REPO / "quant_sports_intel_models/football/nfl/fantasy"


# ── the form ──────────────────────────────────────────────────────────────────────────────────────
def _toy(n=6):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "r0_full_ppr": rng.uniform(5, 20, n), "a0": rng.uniform(0.3, 1.0, n),
        "n": rng.integers(0, 5, n).astype(float), "t": np.full(n, 5.0),
        "g_rem": np.full(n, 12.0), "k": np.full(n, 5), "pos": ["RB"] * n,
    })
    df["xsum_full_ppr"] = df["n"] * rng.uniform(0, 25, n)
    df["y_full_ppr"] = rng.uniform(0, 200, n)
    return df


def test_infinite_prior_strength_reproduces_the_prorated_incumbent_exactly():
    df = _toy()
    got = V.ros_point(df, "full_ppr", V.FormParams(math.inf, math.inf))
    want = df["r0_full_ppr"] * df["a0"] * df["g_rem"]
    assert np.max(np.abs(got - want)) <= V.REPRO_TOL


def test_a_player_with_no_games_keeps_the_prior_rate_at_any_finite_m():
    for m in V.M_GRID[:-1]:
        r = V.credibility_rate([12.0], [0.0], [0.0], m)
        assert r[0] == pytest.approx(12.0, abs=1e-12)


def test_realized_evidence_moves_the_rate_toward_the_observed_mean():
    r = V.credibility_rate([10.0], [4.0], [4 * 20.0], 4.0)
    assert r[0] == pytest.approx(15.0)


def test_availability_is_a_probability():
    a = V.credibility_avail([1.0, 0.0], [9.0, 0.0], [5.0, 5.0], 0.5)
    assert (a >= 0).all() and (a <= 1).all()


def test_a_fit_that_lands_on_infinity_is_flagged_as_a_collapse_not_a_win():
    df = _toy(40)
    # a target that IS the prorated prior: the best fit is the incumbent itself
    df["y_full_ppr"] = df["r0_full_ppr"] * df["a0"] * df["g_rem"]
    df["xsum_full_ppr"] = df["n"] * 1000.0          # realized data that is pure noise away from it
    p, d = V.fit_params(df, "eb_rate_avail")
    assert math.isinf(p.m_r) and math.isinf(p.m_a)
    assert d["collapsed_to_incumbent"] is True


def test_a_real_signal_is_not_flagged_as_a_collapse():
    df = _toy(40)
    df["y_full_ppr"] = (df["xsum_full_ppr"] / df["n"].clip(lower=1)) * df["g_rem"]
    df.loc[df["n"] == 0, "y_full_ppr"] = df["r0_full_ppr"] * df["g_rem"]
    _, d = V.fit_params(df, "eb_rate")
    assert d["collapsed_to_incumbent"] is False


# ── the scores ────────────────────────────────────────────────────────────────────────────────────
def test_crps_q_is_twice_the_mean_pinball_loss():
    q = np.sort(np.random.default_rng(1).uniform(0, 50, (3, 19)), axis=1)
    y = np.array([0.0, 25.0, 80.0])
    brute = [2 * np.mean([max(L * (yy - qq), (L - 1) * (yy - qq)) for L, qq in zip(V.LEVELS, row)])
             for yy, row in zip(y, q)]
    assert np.allclose(V.crps_q(y, q), brute, atol=1e-12)


def test_the_pit_reads_flat_on_a_correctly_specified_censored_predictive():
    """Positive control for C9's instrument — a zero-atom law the knots describe exactly must pass.
    (Found in node 3: the amendment-1 atom rule passes this at 0.005; it was NOT repaired.)"""
    rng = np.random.default_rng(3)
    n = 20000
    mu, s = rng.uniform(-40, 120, n), rng.uniform(10, 60, n)
    qg = np.maximum(0, mu[:, None] + s[:, None] * norm.ppf(V.LEVELS)[None, :])
    y = np.maximum(0, mu + s * rng.standard_normal(n))
    assert V.max_decile_dev(V.randomized_pit(y, qg, np.random.default_rng(4))) < 0.02


def test_the_pit_detects_a_miscalibrated_predictive():
    """…and it is not blind: the same law scored against knots half as wide must fail C9."""
    rng = np.random.default_rng(5)
    n = 20000
    mu, s = rng.uniform(20, 120, n), rng.uniform(10, 60, n)
    qg = np.maximum(0, mu[:, None] + 0.5 * s[:, None] * norm.ppf(V.LEVELS)[None, :])
    y = np.maximum(0, mu + s * rng.standard_normal(n))
    assert V.max_decile_dev(V.randomized_pit(y, qg, np.random.default_rng(6))) > V.PIT_MAX_DECILE_DEV


def test_residual_table_applies_identically_to_a_per_row_lookup():
    rng = np.random.default_rng(7)
    n = 900
    pos = rng.choice(["QB", "RB"], n)
    k = rng.integers(1, 13, n)
    pred = rng.uniform(0, 200, n)
    y = np.maximum(0, pred + rng.normal(0, 30, n))
    tab = V.fit_residual_table(pos, k, pred, y)
    got, _ = V.apply_residual_table(tab, pos, k, pred)
    kb = V.k_bucket(k)
    for i in range(0, n, 37):
        tt = int(np.searchsorted(tab["edges"][pos[i]], pred[i], side="right"))
        q = tab["cell"].get((pos[i], kb[i], tt))
        q = q if q is not None else tab["kb"].get((pos[i], kb[i]), tab["pos"][pos[i]])
        assert np.allclose(got[i], np.sort(np.maximum(pred[i] + q, 0)))


def test_expected_excess_is_zero_for_a_predictive_entirely_below_the_cutoff():
    q = np.tile(np.linspace(100, 130, 19), (2, 1))
    assert np.allclose(V.expected_excess(q, [200.0, 110.0]), [0.0, np.maximum(q[1] - 110, 0).mean()])


def test_a_narrow_position_does_not_float_on_expected_excess():
    """The WVR1 float mechanism in miniature: a kicker 3 pts under his cutoff with a 6-pt band
    beats a running back 60 under his cutoff with a 200-pt band on VOR, and loses on excess."""
    pos = np.array(["K"] * 13 + ["RB"] * 25)
    ros = np.concatenate([np.linspace(140, 128, 13), np.linspace(250, 150, 24), [90.0]])
    q = ros[:, None] + np.where(pos == "K", 3.0, 100.0)[:, None] * norm.ppf(V.LEVELS)[None, :]
    k13, rb25 = 12, 37
    assert pos[k13] == "K" and pos[rb25] == "RB"
    fa = np.zeros(len(pos), bool)
    fa[[k13, rb25]] = True
    vor = V.waiver_scores("starter_vor_ros", ros, q, pos, fa)
    ex = V.waiver_scores("expected_excess", ros, q, pos, fa)
    assert vor[k13] == pytest.approx(-1.0) and vor[rb25] == pytest.approx(-60.0)
    assert vor[k13] > vor[rb25]          # the float, reproduced
    assert ex[rb25] > ex[k13]            # …and cured


# ── registered constants ──────────────────────────────────────────────────────────────────────────
def test_the_pace_anchor_mirrors_the_frontend_constant():
    src = (REPO / "frontend/lib/fantasy.ts").read_text()
    block = src[src.index("export const REALIZED_MAX_SEASON_PACE"):]
    block = block[:block.index("}")]
    ts = {m.group(1): float(m.group(2)) for m in re.finditer(r"(\w+):\s*([\d.]+)", block)
          if m.group(1) in ("QB", "RB", "WR", "TE")}
    assert ts == V.REALIZED_MAX_SEASON_PACE


def test_the_fold_clause_constant_matches_the_instrument():
    from betting_ml.utils import cv_power as CP
    assert CP.fold_consistency_clause(len(V.EVAL_SEASONS)).wins_required == V.FOLD_WINS_REQUIRED


def test_ros_value_never_imports_pipeline_or_does_io():
    tree = ast.parse((FANT / "ros_value.py").read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods, "the scan found no imports at all — it is not reading the module"
    assert not mods & {"pipeline", "boto3", "deltalake", "duckdb", "requests"}


# ── the real assembly path, IO stubbed ────────────────────────────────────────────────────────────
def _fake_inputs():
    board = pd.DataFrame([
        # a starter who plays every week, a player who never plays, an unsigned player, a kicker
        dict(player_id="P1", player_name="Alpha Back", position="RB", team_id="LAR",
             proj_games=16.0, proj_rush_yds=1200.0, proj_rush_td=8.0, proj_rec=40.0,
             proj_rec_yds=300.0, is_rookie=False),
        dict(player_id="P2", player_name="Bench Guy", position="WR", team_id="KC",
             proj_games=10.0, proj_rec=30.0, proj_rec_yds=350.0, is_rookie=True),
        dict(player_id="P3", player_name="Free Agent", position="QB", team_id=None,
             proj_games=4.0, proj_pass_yds=900.0, proj_pass_td=5.0, is_rookie=False),
        dict(player_id="K1", player_name="Kick Er", position="K", team_id="KC",
             proj_games=17.0, proj_fg_made_0_39=20.0, proj_pat_made=40.0, is_rookie=False),
    ])
    weeks = list(range(1, 19))
    sched = pd.DataFrame(
        [dict(season=2021, week=w, game_type="REG", home_team="LA", away_team="KC") for w in weeks
         if w != 9]
        + [dict(season=2021, week=w, game_type="REG", home_team="NE", away_team="BUF")
           for w in weeks if w != 10])
    real = []
    for w in weeks:
        if w == 9:
            continue
        real.append(dict(player_id="P1", player_display_name="Alpha Back", position="RB",
                         team="LA", opponent_team="KC", season=2021, week=w, season_type="REG",
                         game_id=f"g{w}", carries=15.0, rushing_yards=80.0 + w, rushing_tds=0.0,
                         receptions=3.0, receiving_yards=20.0, fg_made_0_19=0.0))
        real.append(dict(player_id="K1", player_display_name="Kick Er", position="K",
                         team="KC", opponent_team="LA", season=2021, week=w, season_type="REG",
                         game_id=f"g{w}", fg_made_20_29=1.0, pat_made=2.0))
    return board, pd.DataFrame(real), sched


@pytest.fixture
def assembled(monkeypatch):
    from quant_sports_intel_models.football.nfl.entity.names import normalize_team
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1 as N

    board, real, sched = _fake_inputs()

    def fake_board(d, s):
        b = board.copy()
        b["season"] = s
        b["team_id"] = [normalize_team(t) or None for t in b["team_id"]]
        return b

    def fake_real(seasons, version):
        r = real.copy()
        for c in N.R.REALIZED_STAT_COLUMNS:
            if c not in r.columns:
                r[c] = 0.0
        r["fantasy_points_ppr"] = 0.0
        # the real table carries every stat column populated (0, not null) on every row — measured
        # on 2021 kickers; a NaN would propagate through flatten_realized_row's sums, by design
        r[list(N.R.REALIZED_STAT_COLUMNS)] = r[list(N.R.REALIZED_STAT_COLUMNS)].fillna(0.0)
        r["team"] = [normalize_team(t) for t in r["team"]]
        return r

    def fake_sched(seasons, version):
        s = sched.copy()
        for c in ("home_team", "away_team"):
            s[c] = [normalize_team(t) for t in s[c]]
        return s

    monkeypatch.setattr(N, "load_board", fake_board)
    monkeypatch.setattr(N, "load_realized", fake_real)
    monkeypatch.setattr(N, "load_schedule", fake_sched)
    frame, diag = N.assemble((2021,), stats_version=None, schedules_version=None, d=Path("."))
    return frame, diag, real


def test_assembly_runs_and_carries_every_evaluated_player(assembled):
    frame, diag, _ = assembled
    assert set(frame["player_id"]) == {"P1", "P2", "P3", "K1"}
    assert len(frame) == 4 * len(V.EVAL_WEEKS)
    assert diag["unresolved_team_rows"] == 0


def test_the_era_code_resolves_to_the_schedule_team(assembled):
    frame, _, _ = assembled
    # board LAR, schedule LA — one canon on both sides (amendment 2 item 1)
    p1 = frame[(frame["player_id"] == "P2")]
    assert (p1["team_basis"] == "team").all()


def test_an_unsigned_never_played_player_gets_the_league_median_schedule(assembled):
    frame, diag, _ = assembled
    p3 = frame[frame["player_id"] == "P3"]
    assert (p3["team_basis"] == "league_median").all()
    assert diag["league_median_basis_rows"] == len(V.EVAL_WEEKS)
    assert (p3["y_full_ppr"] == 0).all() and (p3["n"] == 0).all()


def test_no_row_reads_a_week_after_k(assembled):
    frame, _, real = assembled
    p1 = frame[frame["player_id"] == "P1"].set_index("k")
    played = sorted(real.loc[real["player_id"] == "P1", "week"])
    for k in V.EVAL_WEEKS:
        assert p1.loc[k, "n"] == sum(1 for w in played if w <= k)
        # realized-to-date and the target partition the season exactly
        tot = p1.loc[k, "xsum_full_ppr"] + p1.loc[k, "y_full_ppr"]
        assert tot == pytest.approx(p1.loc[1, "xsum_full_ppr"] + p1.loc[1, "y_full_ppr"])


def test_bye_weeks_are_not_games(assembled):
    frame, _, _ = assembled
    p1 = frame[frame["player_id"] == "P1"].set_index("k")
    assert p1.loc[9, "t"] == 8 and p1.loc[8, "t"] == 8          # week 9 is the bye
    assert p1.loc[12, "t"] + p1.loc[12, "g_rem"] == 17


def test_kickers_are_scored_by_the_existing_scorer(assembled):
    frame, _, _ = assembled
    k1 = frame[frame["player_id"] == "K1"].set_index("k")
    # 1 FG (0-39 bucket, 3 pts) + 2 PAT (1 pt each) per game
    assert k1.loc[4, "xsum_full_ppr"] == pytest.approx(4 * 5.0)


def test_prior_and_realized_are_scored_on_the_same_term_set(assembled):
    _, diag, _ = assembled
    for p in V.PRESETS:
        terms = diag["scoring_terms"][p]
        assert "rec" in terms["applied"] or p == "standard"
        assert "two_pt" in terms["captured"]      # the board line carries no proj_two_pt here
        assert not set(terms["applied"]) & set(terms["captured"])
