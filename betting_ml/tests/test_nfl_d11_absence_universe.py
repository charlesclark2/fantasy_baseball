"""NF-D11 fast-gate tests — the projection-UNIVERSE fix + the return-from-absence availability prior.

The defect these lock down: `load_base_season` anchored the universe on an INNER JOIN to the base
season, so a player who missed the ENTIRE base season was DELETED from the board even when the 3-year
window held a WR1 season (2026: Brandon Aiyuk, Tank Dell, Jonathon Brooks, MarShawn Lloyd — all
actively drafted). The anchor's PURPOSE (keep retired / out-of-league players out) is sound, so the
fix is a decided FALLBACK, not a deletion of the rule:

  1. the anchor falls back to the MOST-RECENT PLAYED season — but ONLY with projection-season roster
     evidence, so retired players stay out (`resolve_base_anchor`);
  2. a rescued player is DISCOUNTED by the return-from-absence availability prior and carries an
     HONEST wide band, never a rosy point (`absence_return_games` / `absence_games_sd`);
  3. the rescue is strictly ADDITIVE — no incumbent player's projection may move (`base_anchored_rows`
     + the env-tilt standardisation population);
  4. the standing ADP coverage diagnostic separates a NAME-ALIAS miss from a genuine universe
     absence, because reporting them as one pile is what let this hide for a whole build
     (`projection_coverage.audit_adp_coverage`).

Pure-module only (numpy/pandas) — no `pipeline`, no DuckDB, no network, per the fast-gate discipline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

sp = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.season_projection")
rsp = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.run_season_projection")
pc = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.projection_coverage")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The universe rule — resolve_base_anchor
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _per_season() -> pd.DataFrame:
    """A 3-season window (2023–2025, base = 2025) with four archetypes:
      · healthy   — played the base season (must anchor there, exactly as before);
      · injured   — real 2023/2024 production, ZERO base-season games, still rostered ⇒ rescue;
      · retired   — same shape, but NO projection-season roster row ⇒ stays excluded;
      · gone_2yr  — last played 2023, still rostered ⇒ rescued with seasons_missed = 2.
    """
    rows = [
        ("healthy", 2023, 16, 12.0, "WR", 210.0),
        ("healthy", 2024, 17, 11.0, "WR", 240.0),
        ("healthy", 2025, 17, 10.5, "WR", 250.0),
        ("injured", 2023, 16, 10.0, "WR", 249.0),
        ("injured", 2024, 7, 9.0, "WR", 62.0),
        ("retired", 2023, 15, 9.5, "RB", 174.0),
        ("retired", 2024, 12, 8.0, "RB", 120.0),
        ("gone_2yr", 2023, 14, 7.0, "TE", 95.0),
    ]
    return pd.DataFrame(rows, columns=["player_id", "season", "games_played", "fp_ppr_sd",
                                       "position", "fp_ppr_tot"])


def test_base_season_player_anchors_on_the_base_season_unchanged():
    out = rsp.resolve_base_anchor(_per_season(), 2025, forward_ids={"healthy", "injured", "gone_2yr"})
    h = out[out.player_id == "healthy"].iloc[0]
    assert h.base_anchor == "base_season"
    assert h.anchor_season == 2025 and h.seasons_missed == 0
    assert h.games_played == 17 and h.fp_ppr_sd == 10.5      # the BASE row, not a window blend


def test_injured_all_year_player_is_rescued_on_his_most_recent_played_season():
    out = rsp.resolve_base_anchor(_per_season(), 2025, forward_ids={"healthy", "injured", "gone_2yr"})
    i = out[out.player_id == "injured"].iloc[0]
    assert i.base_anchor == "most_recent_played"
    assert i.anchor_season == 2024 and i.seasons_missed == 1
    # role/durability/sd come from the FALLBACK season (2024), not the last healthy one
    assert i.games_played == 7 and i.fp_ppr_sd == 9.0
    # the prior-production signal is the BEST season in the window (his 2023 WR1 year)
    assert i.prior_best_fp == 249.0


def test_retired_player_without_roster_evidence_stays_excluded():
    """The anchor's original purpose. A base-season absence with NO projection-season roster row is
    a retirement, and must NOT be swept back in by the multi-year window."""
    out = rsp.resolve_base_anchor(_per_season(), 2025, forward_ids={"healthy", "injured", "gone_2yr"})
    assert "retired" not in set(out.player_id)


def test_multi_season_absence_carries_the_right_seasons_missed():
    out = rsp.resolve_base_anchor(_per_season(), 2025, forward_ids={"gone_2yr"})
    g = out[out.player_id == "gone_2yr"].iloc[0]
    assert g.anchor_season == 2023 and g.seasons_missed == 2


@pytest.mark.parametrize("forward", [None, set()])
def test_no_forward_roster_evidence_disables_the_rescue_entirely(forward):
    """A backtest season with no roster snapshot must degrade to the MVP-1 universe — never guess."""
    out = rsp.resolve_base_anchor(_per_season(), 2025, forward_ids=forward)
    assert set(out.player_id) == {"healthy"}
    assert (out.base_anchor == "base_season").all()


def test_resolve_base_anchor_is_empty_safe():
    out = rsp.resolve_base_anchor(pd.DataFrame(), 2025, forward_ids={"x"})
    assert out.empty and "base_anchor" in out.columns


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The availability prior — fit, apply, widen
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _history(n: int = 120, seed: int = 7) -> pd.DataFrame:
    """A synthetic returner history whose SIGNAL is the real one: productive returners come back for
    more games than fringe ones, and a large minority play zero."""
    rng = np.random.default_rng(seed)
    fp = rng.choice([10.0, 80.0, 200.0], size=n, p=[0.6, 0.25, 0.15])
    base = np.where(fp > 120, 8.0, np.where(fp > 50, 5.0, 3.0))
    g = np.clip(np.round(rng.normal(base, 4.0)), 0, 17)
    return pd.DataFrame({
        "target_season": rng.integers(2016, 2025, n),
        "prior_best_fp": fp, "prior_games": rng.integers(8, 17, n),
        "seasons_missed": rng.choice([1, 2], size=n, p=[0.85, 0.15]),
        "position": rng.choice(["RB", "WR", "TE", "QB"], size=n),
        "realized_games": g, "healthy_mean_games": np.full(n, 10.4),
    })


@pytest.mark.parametrize("family", ["flat", "tier", "missed", "ratio", "learned"])
def test_every_candidate_family_fits_and_produces_a_sane_level(family):
    prior = sp.fit_absence_return_prior(_history(), family=family)
    df = pd.DataFrame({"proj_games": [14.0, 14.0], "prior_best_fp": [200.0, 10.0],
                       "seasons_missed": [1, 1], "position": ["WR", "RB"]})
    lvl = prior.level(df)
    assert np.isfinite(lvl).all()
    assert (lvl >= 0).all() and (lvl <= 17).all()
    # every family must discount a stale 14-game durability estimate
    assert (lvl < 14.0).all()


def test_tier_family_gives_a_productive_returner_a_higher_level_than_a_fringe_one():
    prior = sp.fit_absence_return_prior(_history(), family="tier")
    df = pd.DataFrame({"proj_games": [14.0, 14.0], "prior_best_fp": [200.0, 10.0],
                       "seasons_missed": [1, 1], "position": ["WR", "WR"]})
    lvl = prior.level(df)
    assert lvl[0] > lvl[1]


def test_ratio_family_preserves_the_ordering_among_returners():
    """Why `ratio` won the bake-off: a multiplicative haircut keeps a returning WR1 above a fringe
    returner, where a flat absolute level flattens them into each other."""
    prior = sp.fit_absence_return_prior(_history(), family="ratio")
    df = pd.DataFrame({"proj_games": [15.0, 5.0], "prior_best_fp": [200.0, 10.0],
                       "seasons_missed": [1, 1], "position": ["WR", "WR"]})
    lvl = prior.level(df)
    assert lvl[0] > lvl[1]
    assert 0.0 < prior.levels["ratio"] < 1.0


def test_a_thin_history_falls_back_to_the_pooled_constants_not_a_noisy_fit():
    prior = sp.fit_absence_return_prior(_history(n=3), family="tier")
    assert prior.levels == {}
    df = pd.DataFrame({"proj_games": [14.0], "prior_best_fp": [200.0], "seasons_missed": [1],
                       "position": ["WR"]})
    assert prior.level(df)[0] == pytest.approx(sp._ABSENCE_FALLBACK_LEVEL)


def test_absence_prior_only_moves_expected_games_DOWN_and_only_for_returners():
    prior = sp.fit_absence_return_prior(_history(), family="tier")
    df = pd.DataFrame({"proj_games": [14.0, 14.0, 2.0], "prior_best_fp": [200.0, 200.0, 10.0],
                       "seasons_missed": [0.0, 1.0, 1.0], "position": ["WR", "WR", "RB"]})
    out = sp.absence_return_games(df, prior, blend=1.0)
    assert out[0] == 14.0                       # a base-season player is untouched
    assert out[1] < 14.0                        # the returner is discounted
    assert out[2] <= 2.0                        # a cap can only move DOWN, never rebound upward


@pytest.mark.parametrize("kwargs", [{"blend": 0.0}, {"prior": None}])
def test_absence_prior_is_a_noop_when_off(kwargs):
    prior = sp.fit_absence_return_prior(_history(), family="tier")
    df = pd.DataFrame({"proj_games": [14.0], "prior_best_fp": [200.0], "seasons_missed": [1.0],
                       "position": ["WR"]})
    args = {"prior": prior, "blend": 1.0, **kwargs}
    assert sp.absence_return_games(df, args["prior"], blend=args["blend"])[0] == 14.0


def test_absence_prior_is_a_noop_without_the_seasons_missed_column():
    prior = sp.fit_absence_return_prior(_history(), family="tier")
    df = pd.DataFrame({"proj_games": [14.0], "prior_best_fp": [200.0], "position": ["WR"]})
    assert sp.absence_return_games(df, prior, blend=1.0)[0] == 14.0


def test_returner_band_can_only_get_WIDER():
    prior = sp.fit_absence_return_prior(_history(), family="tier")
    df = pd.DataFrame({"proj_games": [8.0, 8.0], "prior_best_fp": [200.0, 200.0],
                       "seasons_missed": [0.0, 1.0], "position": ["WR", "WR"]})
    base_sd = np.array([2.6, 2.6])
    out = sp.absence_games_sd(base_sd, df, prior)
    assert out[0] == 2.6                        # untouched for a base-season player
    assert out[1] >= 2.6                        # widen-only for the returner
    # and a returner whose role sd is ALREADY huge keeps it (max, not overwrite)
    assert sp.absence_games_sd(np.array([99.0, 99.0]), df, prior)[1] == 99.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. End-to-end through project_veterans — the honest-band contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _twins() -> pd.DataFrame:
    """Two identical WRs — same per-game line, same last-healthy-season durability. One played the
    base season; the other missed it entirely and was rescued."""
    row = {"rec_pg": 5.0, "rec_yds_pg": 70.0, "rec_td_pg": 0.5, "targets_pg": 7.0,
           "pass_att_pg": 0.0, "pass_cmp_pg": 0.0, "pass_yds_pg": 0.0, "pass_td_pg": 0.0,
           "pass_int_pg": 0.0, "rush_att_pg": 0.5, "rush_yds_pg": 3.0, "rush_td_pg": 0.0,
           "games_played": 16, "fp_ppr_sd": 8.0, "position": "WR",
           "depth_chart_position_rank": 1.0, "prior_best_fp": 249.0}
    return pd.DataFrame([
        {**row, "player_id": "healthy", "seasons_missed": 0.0, "base_anchor": "base_season"},
        {**row, "player_id": "returning", "seasons_missed": 1.0, "base_anchor": "most_recent_played"},
    ])


def test_a_returning_player_projects_below_his_healthy_twin_with_a_wider_band():
    base = _twins()
    prior = sp.fit_absence_return_prior(_history(), family="ratio")
    out = sp.project_veterans(base, sp.positional_pergame_priors(base), 2026,
                              absence_prior=prior, absence_prior_blend=1.0).set_index("player_id")
    h, r = out.loc["healthy"], out.loc["returning"]
    assert r.proj_games < h.proj_games
    assert r.proj_fp_ppr < h.proj_fp_ppr
    # HONEST framing: the point is discounted AND the uncertainty is wider — never a rosy point
    assert (r.fp_ppr_p90 - r.fp_ppr_p10) / max(r.proj_fp_ppr, 1e-6) > \
           (h.fp_ppr_p90 - h.fp_ppr_p10) / max(h.proj_fp_ppr, 1e-6)
    assert r.confidence == "low"
    assert r.source == "veteran_returning"
    assert h.source == "veteran"


def test_a_returning_player_is_never_projected_above_his_own_stale_line():
    base = _twins()
    prior = sp.fit_absence_return_prior(_history(), family="ratio")
    off = sp.project_veterans(base, sp.positional_pergame_priors(base), 2026,
                              absence_prior_blend=0.0).set_index("player_id")
    on = sp.project_veterans(base, sp.positional_pergame_priors(base), 2026,
                             absence_prior=prior, absence_prior_blend=1.0).set_index("player_id")
    assert on.loc["returning"].proj_fp_ppr <= off.loc["returning"].proj_fp_ppr


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The rescue is strictly ADDITIVE — an incumbent player may not move
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_in_fold_priors_are_computed_over_base_anchored_rows_only():
    """A rescued player's stale line must not shift the positional prior / role-volume prior that
    every INCUMBENT player is shrunk toward — otherwise the universe change silently reprices the
    whole board."""
    base = _twins()
    only_healthy = base[base.base_anchor == "base_season"]
    pd.testing.assert_frame_equal(
        sp.positional_pergame_priors(base).reset_index(drop=True),
        sp.positional_pergame_priors(only_healthy).reset_index(drop=True))
    assert sp.role_volume_prior(base) == sp.role_volume_prior(only_healthy)


def test_env_tilt_standardises_on_the_base_anchored_field():
    """The env tilt z-scores team_env across the position's field, so admitting returners would
    otherwise nudge every incumbent QB. The moments must come from base-anchored rows only."""
    n = 14
    incumbent = pd.DataFrame({
        "position": ["QB"] * n, "team_env": np.linspace(18.0, 26.0, n),
        "seasons_missed": [0.0] * n})
    scale_alone = sp.environment_tilt_scale(incumbent, blend=0.06)
    with_returners = pd.concat([
        incumbent,
        pd.DataFrame({"position": ["QB"] * 4, "team_env": [40.0, 41.0, 42.0, 43.0],
                      "seasons_missed": [1.0] * 4})], ignore_index=True)
    scale_both = sp.environment_tilt_scale(with_returners, blend=0.06)
    np.testing.assert_allclose(scale_alone, scale_both[:n])


def test_base_anchored_rows_passes_through_a_frame_without_the_column():
    df = pd.DataFrame({"position": ["WR"], "games_played": [10]})
    pd.testing.assert_frame_equal(sp.base_anchored_rows(df), df)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The standing ADP coverage diagnostic
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _proj() -> pd.DataFrame:
    return pd.DataFrame({
        "player_name": ["MICHAEL EVANS", "Bijan Robinson", "Brandon Aiyuk"],
        "position": ["WR", "RB", "WR"],
    })


def _adp(names) -> pd.DataFrame:
    return pd.DataFrame(names, columns=["player_name", "position", "adp"])


def test_a_nickname_miss_is_classified_as_an_ALIAS_candidate_with_the_surname_match():
    """The `Kenny Gainwell` vs `KENNETH GAINWELL` class (here `Mike` vs `MICHAEL`, since the real
    Gainwell miss is now IN the alias map): our universe HAS him, the name map does not. Fix = a
    `_NAME_ALIASES` entry, NOT a model change."""
    audit = pc.audit_adp_coverage(_adp([("Mike Evans", "WR", 30.0)]), _proj())
    assert audit["n_alias_candidates"] == 1 and audit["n_true_absences"] == 0
    assert audit["alias_candidates"][0]["projection_surname_matches"] == ["michael evans"]


def test_an_alias_the_map_already_fixes_is_not_re_reported_as_a_miss():
    """The audit runs BOTH sides through the production normalizer, so a nickname the map already
    resolves counts as MATCHED — the audit reports only genuinely-open gaps."""
    proj = pd.DataFrame({"player_name": ["KENNETH GAINWELL"], "position": ["RB"]})
    audit = pc.audit_adp_coverage(_adp([("Kenny Gainwell", "RB", 90.0)]), proj)
    assert audit["n_matched"] == 1
    assert audit["n_alias_candidates"] == 0 and audit["n_true_absences"] == 0


def test_a_player_absent_from_the_universe_is_classified_as_a_TRUE_absence():
    """The NF-D11 class: no surname match at that position ⇒ the player is genuinely NOT projected.
    Fix = a MODEL/universe change. Conflating this with the alias class is what hid this bug."""
    audit = pc.audit_adp_coverage(_adp([("Tank Dell", "WR", 88.0)]), _proj())
    assert audit["n_true_absences"] == 1 and audit["n_alias_candidates"] == 0
    assert audit["true_absences"][0]["adp_name"] == "Tank Dell"
    assert audit["n_actionable_true_absences"] == 1        # inside the draftable range


def test_a_deep_bench_absence_is_reported_but_not_counted_as_actionable():
    audit = pc.audit_adp_coverage(_adp([("Some Camp Body", "WR", 240.0)]), _proj())
    assert audit["n_true_absences"] == 1
    assert audit["n_actionable_true_absences"] == 0


def test_matched_names_and_non_covered_positions_are_not_reported_as_gaps():
    audit = pc.audit_adp_coverage(
        _adp([("Bijan Robinson", "RB", 1.0), ("Justin Tucker", "PK", 150.0)]), _proj())
    assert audit["n_matched"] == 1
    assert audit["n_adp_covered_positions"] == 1           # the kicker is not a universe gap
    assert audit["n_true_absences"] == 0 and audit["n_alias_candidates"] == 0
    assert audit["pct_matched"] == 100.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The BAKE-OFF's selection metric itself (CLAUDE.md: sanity-check every selection metric)
# ══════════════════════════════════════════════════════════════════════════════════════════════
abl = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.run_absence_prior_ablation")


def test_crps_is_a_proper_score_the_true_predictive_wins():
    """CRPS replaced MAE as the NF-D11 primary metric precisely because it is PROPER. Lock that in:
    the correctly-specified predictive must beat both an under-dispersed one and a shifted one."""
    rng = np.random.default_rng(3)
    y = rng.normal(100.0, 30.0, 4000)
    correct = abl.crps_normal(y, np.full_like(y, 100.0), np.full_like(y, 30.0)).mean()
    too_tight = abl.crps_normal(y, np.full_like(y, 100.0), np.full_like(y, 8.0)).mean()
    too_wide = abl.crps_normal(y, np.full_like(y, 100.0), np.full_like(y, 120.0)).mean()
    shifted = abl.crps_normal(y, np.full_like(y, 40.0), np.full_like(y, 30.0)).mean()
    assert correct < too_tight and correct < too_wide and correct < shifted


def test_under_MAE_the_degenerate_zero_projection_WINS_but_under_crps_it_loses():
    """The metric inversion this bake-off actually caught, reproduced in miniature.

    On the realized returner distribution (~43% play zero games, a long right tail) MAE is minimised
    far below the mean — so the DEGENERATE arm ("project zero for every returner") beats the best
    real candidate on MAE. It did so on the live data too (degenerate MAE 15.47 vs the winner's
    18.96), which is exactly why MAE was rejected as the selection metric. CRPS reverses that
    ordering (degenerate 15.62 vs the winner's 13.52) because it scores the whole predictive, not a
    point. This test is the regression guard against quietly switching the metric back."""
    y = np.concatenate([np.zeros(43), np.full(45, 10.0), np.full(12, 200.0)])
    sd = np.full_like(y, 60.0)
    degenerate, candidate = np.zeros_like(y), np.full_like(y, 25.0)
    assert np.abs(degenerate - y).mean() < np.abs(candidate - y).mean()        # MAE: nihilism wins
    assert abl.crps_normal(y, candidate, sd).mean() < abl.crps_normal(y, degenerate, sd).mean()


def test_pbo_is_zero_for_a_uniformly_dominant_config_and_high_for_pure_noise():
    seasons = list(range(2017, 2025))
    dominant = pd.DataFrame({"good": [1.0] * len(seasons), "bad": [2.0] * len(seasons),
                             "worse": [3.0] * len(seasons)}, index=seasons)
    assert abl.pbo(dominant)["pbo"] == 0.0
    rng = np.random.default_rng(11)
    noise = pd.DataFrame(rng.normal(size=(len(seasons), 12)), index=seasons)
    noise.columns = [f"cfg{i}" for i in range(12)]
    assert abl.pbo(noise)["pbo"] > 0.2            # a tied/noise field is NOT a robust selection


def test_pbo_declines_to_score_a_too_small_panel():
    assert abl.pbo(pd.DataFrame({"a": [1.0, 2.0]}, index=[2024, 2025]))["pbo"] is None


def test_audit_is_empty_input_safe():
    empty = pd.DataFrame(columns=["player_name", "position", "adp"])
    assert pc.audit_adp_coverage(empty, _proj())["n_matched"] == 0
    assert pc.audit_adp_coverage(_adp([("A B", "WR", 1.0)]), pd.DataFrame())["n_matched"] == 0
    assert pc.audit_adp_coverage(None, None)["n_adp_rows"] == 0
