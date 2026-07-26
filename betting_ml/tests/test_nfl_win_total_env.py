"""NF-D4 — forward-Vegas SEASON win-total team environment. Unit tests for the static win-total
source, the Week-1×win-total z-blend, and the widen-past-QB env-tilt positions knob. Pure/offline
(no IO) so they land in the fast gate."""
import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp
from quant_sports_intel_models.football.nfl.fantasy import win_total_source as wt


def test_win_totals_cover_all_32_teams_every_season():
    # the transcription guard: every backfilled season carries all 32 nflverse codes exactly once
    assert len(wt.TEAM_CODES) == 32
    for yr, tots in wt.WIN_TOTALS.items():
        assert set(tots) == set(wt.TEAM_CODES), yr
        assert all(2.0 <= v <= 17.0 for v in tots.values()), yr


def test_win_total_env_shape_and_missing_season():
    env = wt.win_total_env(2024)
    assert list(env.columns) == ["proj_team", "env_wt"]
    assert len(env) == 32 and env["env_wt"].notna().all()
    assert wt.win_total_env(1901).empty            # uncovered season → empty frame (graceful)


def test_blend_replaces_env_with_teamlevel_zblend():
    # a 3-team Week-1 env; blend with a win total that AGREES on order → the blend keeps the order
    df = pd.DataFrame({"proj_team": ["BAL", "KC", "ARI"], "team_env": [28.0, 26.0, 18.0]})
    # monkey a tiny WIN_TOTALS season so the test is self-contained
    wt.WIN_TOTALS[9999] = {c: 8.0 for c in wt.TEAM_CODES}
    wt.WIN_TOTALS[9999].update({"BAL": 12.0, "KC": 10.0, "ARI": 5.0})
    try:
        out = wt.blend_env_with_win_total(df, 9999)
        assert "env_wt" not in out.columns and "team_env" in out.columns
        # highest raw env (BAL) stays highest, lowest (ARI) stays lowest after the z-blend
        s = out.set_index("proj_team")["team_env"]
        assert s["BAL"] > s["KC"] > s["ARI"]
    finally:
        del wt.WIN_TOTALS[9999]


def test_blend_falls_back_to_week1_when_season_absent():
    df = pd.DataFrame({"proj_team": ["BAL", "KC"], "team_env": [28.0, 26.0]})
    out = wt.blend_env_with_win_total(df, 1901)     # no win totals for 1901
    pd.testing.assert_frame_equal(out, df)          # unchanged ⇒ exact slice-4 Week-1-only behavior


def test_blend_keeps_week1_z_for_team_missing_a_win_total():
    df = pd.DataFrame({"proj_team": ["BAL", "KC", "ZZZ"], "team_env": [28.0, 26.0, 10.0]})
    wt.WIN_TOTALS[9998] = {c: 8.0 for c in wt.TEAM_CODES}   # covers BAL/KC, not the fake ZZZ
    try:
        out = wt.blend_env_with_win_total(df, 9998)
        assert np.isfinite(out.set_index("proj_team").loc["ZZZ", "team_env"])  # no NaN contamination
    finally:
        del wt.WIN_TOTALS[9998]


def test_env_tilt_positions_widens_past_qb():
    # a skill (WR) row with a high env is NOT tilted under the shipped QB-only scope, but IS when the
    # positions knob is widened — the NF-D4 'consider extending beyond QB' mechanism.
    d = pd.DataFrame({"position": ["WR"] * 12,
                      "team_env": [30.0] + [20.0] * 11})
    qb_only = sp.environment_tilt_scale(d, blend=0.15)                       # default ("QB",)
    widened = sp.environment_tilt_scale(d, blend=0.15, positions=("QB", "WR"))
    assert np.allclose(qb_only, 1.0)                                        # WR untouched by default
    assert widened[0] > 1.0                                                  # high-env WR tilted up


def test_env_tilt_positions_noop_preserves_qb_only_default():
    d = pd.DataFrame({"position": ["QB", "WR"], "team_env": [30.0, 30.0]})
    extra = pd.DataFrame({"position": ["QB"] * 10, "team_env": [20.0] * 10})
    d = pd.concat([d, extra], ignore_index=True)
    scale = sp.environment_tilt_scale(d, blend=0.15)
    assert scale[0] > 1.0 and np.isclose(scale[1], 1.0)   # QB tilted, WR (out of scope) not
