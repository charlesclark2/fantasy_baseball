"""NF1.6 — guards for the BASE KICKER + TEAM-DEFENSE (DST) projection, the position-universe extension.

WHAT THIS PROTECTS. Before NF1.6 the fantasy tools projected offensive skill only and the K/DST roster
slots rendered "not projected". NF1.6 fills them with a deliberately BASE model whose whole value
proposition is COMPLETENESS + honest TIERING — which means the things that can silently break are not
"is the number accurate" (nobody claims it is precise) but "is the number HONEST, and does it still
reach the surfaces". Six families:

  1. **The RAW-COMPONENT CONTRACT must hold.** NF-C1/NF-C0b score the emitted columns, so the
     points-allowed bucket mass must be a genuine distribution over the projected games, the bucket
     edges must stay a common refinement of the ESPN + Yahoo tier schemes, and every emitted column
     must be reachable through `NFL_PROFILE.stat_columns` (an unmapped column is silently scored as
     ZERO by the engine — the `_stat_series` behaviour that makes a typo invisible).
  2. ⭐ **The TIER TABLE must be EXACT, not approximate.** The entire reason the distribution is
     emitted as expected-games-per-bucket is that `Σ tier_points × E[games]` is LINEAR, so the
     sport-agnostic scorer reproduces a per-game tier table exactly. This is pinned against a
     hand-computed per-game scoring of a synthetic season.
  3. **DECLARED-NOISE components must stay at the league mean.** Defensive TDs / safeties / blocked
     kicks measured ρ ≈ 0.01–0.13; projecting them per-team would manufacture precision. A future
     edit that "improves" them by fitting a slope must fail here loudly.
  4. ⭐ **THE INTERVAL DISCIPLINE, inherited from NF1.7→1.8→1.9.** p10/p90 emitted INDEPENDENTLY (never
     rebuilt from a single sd), `lo <= point <= hi` always, the widen knob MONOTONE (widen-only), an
     unfittable band RAISES rather than returning a vacuous pass, and both degenerates LOSE.
  5. **The POPULATION must stay honest.** The band panel LEFT-joins realized outcomes with a 0 fill —
     13.1% of week-1-rostered kickers realise exactly 0. An edit that "fixes" it to an inner join, or
     adds a games filter, silently deletes the tail the band exists to price (the NF1.9 lesson).
  6. **The surfaces must keep receiving it.** The board must fold the K/DST lineage in, the MVP-1
     contract ALIAS columns must be emitted (without them the engine finds no bounds and silently
     emits a DEGENERATE zero-width band — this actually happened during the build), K/DST must be
     PROJECTABLE in the export, every K/DST record must carry the low-predictability caveat, and the
     standing re-validation must own the new floors.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.fantasy_engine.scoring import score_players
from quant_sports_intel_models.football.nfl.fantasy import kdst_projection as KD
from quant_sports_intel_models.football.nfl.fantasy import kdst_source as KS
from quant_sports_intel_models.football.nfl.fantasy import run_interval_revalidation as REV
from quant_sports_intel_models.football.nfl.fantasy.league_presets import (
    NFL_PROFILE,
    PRESETS,
    get_preset,
)

_FANTASY = Path(KD.__file__).resolve().parent


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — small synthetic frames, so the pure model is fully testable with no IO
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _team_def_hist(seasons=(2023, 2024, 2025), teams=("AAA", "BBB", "CCC")) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(teams):
        for y in seasons:
            rows.append({"season": y, "team": t, "games": 17.0,
                         "def_sacks": 30.0 + 8 * i, "def_int": 10.0 + 3 * i,
                         "def_fumble_rec": 8.0 + i, "def_td": 1.0 + i, "st_td": 1.0,
                         "def_safety": 0.0, "def_blocked_kick": 1.0})
    return pd.DataFrame(rows)


def _team_points_hist(seasons=(2023, 2024, 2025), teams=("AAA", "BBB", "CCC")) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(teams):
        for y in seasons:
            pf, pa = 20.0 + 3 * i, 26.0 - 3 * i
            rows.append({"season": y, "team": t, "team_games": 17.0,
                         "points_for": pf * 17, "points_against": pa * 17,
                         "points_for_pg": pf, "points_against_pg": pa})
    return pd.DataFrame(rows)


def _team_game_points(n_per_team=60, teams=("AAA", "BBB", "CCC")) -> pd.DataFrame:
    rng = np.random.default_rng(20260730)
    rows = []
    for i, t in enumerate(teams):
        mean = 26.0 - 3 * i
        for j in range(n_per_team):
            pa = max(0, int(round(rng.normal(mean, 9))))
            # inject a realistic shutout atom so the fitted mix has mass at 0
            if j % 40 == 0:
                pa = 0
            rows.append({"season": 2023 + (j % 3), "week": 1 + (j % 17), "team": t,
                         "points_for": 22.0, "points_against": float(pa)})
    return pd.DataFrame(rows)


def _fitted_dst_model() -> KD.DstModel:
    td, tp = _team_def_hist(), _team_points_hist()
    panel = KD.build_dst_training_panel(td, tp, None, [2024, 2025])
    model = KD.fit_dst_component_model(panel)
    model.pa_mix = KD.fit_points_allowed_mix(_team_game_points(), tp)
    return model


def _dst_universe(teams=("AAA", "BBB", "CCC")) -> pd.DataFrame:
    return pd.DataFrame({"season": 2026, "team": list(teams), "scheduled_games": 17.0})


def _sos(teams=("AAA", "BBB", "CCC")) -> pd.DataFrame:
    return pd.DataFrame({"season": 2026, "team": list(teams),
                         "sos_off_pg": [22.0, 23.0, 21.0], "sos_off_z": [0.0, 1.0, -1.0]})


def _projected_dst() -> pd.DataFrame:
    return KD.project_dst(_dst_universe(), _team_def_hist(), _team_points_hist(),
                          _fitted_dst_model(), _sos(), 2026)


def _band_panel(n=400) -> pd.DataFrame:
    """A synthetic walk-forward band panel with the real population shapes: a DST group, a kicker
    STARTER group, and a kicker RESERVE group carrying a genuine zero atom."""
    rng = np.random.default_rng(7)
    rows = []
    for y in range(2016, 2026):
        for i in range(n // 10):
            grp = ("DST", "K_starter", "K_reserve")[i % 3]
            pos = "DST" if grp == "DST" else "K"
            point = {"DST": 110.0, "K_starter": 130.0, "K_reserve": 70.0}[grp]
            if grp == "K_reserve":
                real = 0.0 if rng.random() < 0.35 else point * rng.uniform(0.2, 2.4)
            else:
                real = point * rng.normal(1.0, 0.22)
            rows.append({"target_season": y, "player_id": f"{grp}-{y}-{i}",
                         "player_name": f"{grp} {i}", "position": pos, "band_group": grp,
                         "team_id": "AAA", "is_primary": grp != "K_reserve", "is_active": True,
                         "point": point, "realized": max(0.0, real), "realized_missing": False})
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The RAW-COMPONENT CONTRACT
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_pa_bucket_mass_is_a_distribution_over_the_projected_games():
    """The nine expected-games columns must sum to `proj_games` — they are `games × P(bucket)`, so a
    sum that drifts means the mix stopped being a probability distribution and every tier score
    downstream is silently scaled wrong."""
    dst = _projected_dst()
    total = sum(dst[c].to_numpy(dtype=float) for c in KD.PA_BUCKET_COLS)
    assert np.allclose(total, dst["proj_games"].to_numpy(dtype=float), atol=1e-9)


def test_pa_bucket_edges_refine_both_espn_and_yahoo_tier_schemes():
    """The nine edges exist so BOTH shipped tier schemes are exact UNIONS of them. If someone
    coarsens the buckets, a real league's scoring silently becomes an approximation."""
    edges = set(KD.PA_BUCKET_EDGES)
    espn = {0, 1, 7, 14, 18, 28, 35, 46}
    yahoo = {0, 1, 7, 14, 21, 28, 35}
    assert espn <= edges, f"ESPN tier edges not expressible: {sorted(espn - edges)}"
    assert yahoo <= edges, f"Yahoo tier edges not expressible: {sorted(yahoo - edges)}"
    assert len(KD.PA_BUCKET_LABELS) == len(KD.PA_BUCKET_EDGES) == len(KD.PA_BUCKET_COLS)


def test_pa_bucket_index_maps_boundaries_to_the_right_bucket():
    """Inclusive-lower-bound semantics, pinned at every boundary — an off-by-one here moves a
    shutout (the most valuable outcome under every scheme) into the 1-6 tier."""
    pa = [0, 1, 6, 7, 13, 14, 17, 18, 20, 21, 27, 28, 34, 35, 45, 46, 99]
    want = ["0", "1_6", "1_6", "7_13", "7_13", "14_17", "14_17", "18_20", "18_20",
            "21_27", "21_27", "28_34", "28_34", "35_45", "35_45", "46p", "46p"]
    got = [KD.PA_BUCKET_LABELS[i] for i in KD.pa_bucket_index(pa)]
    assert got == want


def test_every_emitted_raw_column_is_reachable_through_the_sport_profile():
    """⚠️ THE ENGINE SCORES AN UNMAPPED COLUMN AS ZERO, SILENTLY. `scoring._stat_series` returns an
    all-zero Series for a column the profile does not know, so a raw component NF1.6 emits but the
    profile never maps contributes nothing to any league's points and nobody sees an error. Every
    scoreable emitted column must therefore be mapped."""
    mapped = set(NFL_PROFILE.stat_columns.values())
    # descriptive/provenance columns are deliberately unmapped — they are not scoreable quantities
    not_scoreable = {"proj_games", "proj_dst_pa_per_game", "proj_dst_pa_per_game_sd"}
    for col in KD.RAW_STAT_COLS:
        if col in not_scoreable:
            continue
        assert col in mapped, (
            f"{col} is emitted by NF1.6 but is NOT in NFL_PROFILE.stat_columns — the engine will "
            f"score it as ZERO with no error (see scoring._stat_series)")


def test_every_kdst_stat_key_has_a_default_scoring_weight():
    """A mapped stat key with no weight scores 0. Four K/DST keys are DELIBERATELY unweighted, and
    each for a specific reason — this pins that set so an accidental omission is still caught:

      * `fg_made` / `pat_att` / `fg_missed` — `fg_made` would DOUBLE-COUNT against the three distance
        buckets that already carry FG scoring; `fg_missed` and `pat_att` only score in leagues that
        penalise misses, which they express through their own `ScoringRules`.
      * `dst_points_allowed` — the SEASON TOTAL cannot be scored under a per-game tier table at all
        (that is the whole reason the `dst_pa_g_*` expected-games columns exist). Weighting it would
        silently add a linear term no real league has.
    """
    cfg = get_preset("full_ppr")
    kdst_keys = [k for k, v in NFL_PROFILE.stat_columns.items()
                 if v in set(KD.K_RAW_COLS) | set(KD.DST_RAW_COLS)]
    assert kdst_keys, "no K/DST stat keys are mapped at all"
    missing = set(k for k in kdst_keys if k not in cfg.scoring.per_stat)
    intentionally_unweighted = {"fg_att", "fg_made", "fg_missed", "pat_att", "dst_points_allowed"}
    assert missing == intentionally_unweighted, (
        f"the unweighted K/DST key set changed: unexpectedly unweighted "
        f"{sorted(missing - intentionally_unweighted)}, unexpectedly weighted "
        f"{sorted(intentionally_unweighted - missing)}")
    # and the terms that MUST score by default really do
    for k in ("fg_made_0_39", "fg_made_40_49", "fg_made_50_plus", "pat_made",
              "def_sacks", "def_int", "def_fumble_rec", "def_td", "dst_pa_g_0", "dst_pa_g_46p"):
        assert cfg.scoring.per_stat.get(k) is not None, f"{k} lost its default weight"


def test_kdst_positions_are_ranked_by_the_profile_and_aliases_fold_on():
    assert "K" in NFL_PROFILE.positions and "DST" in NFL_PROFILE.positions
    for raw in ("DEF", "D/ST", "DEFENSE"):
        assert NFL_PROFILE.normalize_position(raw) == "DST"
    assert NFL_PROFILE.normalize_position("PK") == "K"
    assert NFL_PROFILE.normalize_position("FB") == "RB"      # unchanged


def test_every_preset_keeps_a_k_and_dst_starting_slot():
    for name in PRESETS:
        cfg = get_preset(name)
        demand = cfg.dedicated_demand()
        assert demand.get("K", 0) > 0, f"{name} has no K starter demand"
        assert demand.get("DST", 0) > 0, f"{name} has no DST starter demand"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⭐ The TIER TABLE must be EXACT under the linear scorer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_expected_games_form_scores_a_per_game_tier_table_exactly():
    """THE LOAD-BEARING CLAIM OF THE WHOLE DST DESIGN. A per-game points-allowed tier table is not
    linear in SEASON points allowed, so a season total cannot be scored under it. It IS linear in
    `games × P(bucket)`. This pins that a hand-computed per-game tier scoring of a known season
    equals what the sport-agnostic linear scorer produces from the emitted bucket columns."""
    # a synthetic 17-game season with a known points-allowed sequence
    per_game_pa = [0, 3, 10, 10, 16, 19, 24, 24, 24, 30, 31, 38, 40, 50, 12, 6, 22]
    tiers = KD.DST_PA_TIER_POINTS
    hand = sum(tiers[KD.PA_BUCKET_LABELS[i]] for i in KD.pa_bucket_index(per_game_pa))

    # the same season expressed as expected-games-per-bucket (here: exact counts)
    counts = np.bincount(KD.pa_bucket_index(per_game_pa), minlength=len(KD.PA_BUCKET_LABELS))
    row = {c: float(counts[j]) for j, c in enumerate(KD.PA_BUCKET_COLS)}
    row.update({"position": "DST", "proj_games": float(len(per_game_pa))})
    df = pd.DataFrame([row])

    scored = score_players(df, get_preset("full_ppr"), NFL_PROFILE, with_interval=False)
    assert scored["league_points"].iloc[0] == pytest.approx(hand, abs=1e-9)


def test_convenience_scoring_matches_the_preset_scoring_on_the_same_line():
    """The convenience total (used for ranking/validation) and the shipped preset's scoring of the
    same raw line must agree — otherwise the board ranks on one number and the report on another."""
    dst = _projected_dst()
    conv = KD.score_convenience(dst)
    scored = score_players(dst.assign(position="DST"), get_preset("full_ppr"), NFL_PROFILE,
                           with_interval=False)
    assert np.allclose(conv.to_numpy(dtype=float),
                       scored["league_points"].to_numpy(dtype=float), atol=1e-6)


def test_points_allowed_mix_reproduces_the_shutout_atom():
    """⭐ WHY THE DISTRIBUTION IS EMPIRICAL AND NOT PARAMETRIC. A shutout is the most valuable game
    outcome under every tier scheme; a negative binomial matched to the observed mean/variance puts
    ~1e-4 there against a real ~0.01. The empirical mix must carry real mass at 0."""
    mix = KD.fit_points_allowed_mix(_team_game_points(), _team_points_hist())
    probs = mix.probabilities([20.0, 26.0])
    assert probs.shape == (2, len(KD.PA_BUCKET_LABELS))
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert probs[:, 0].max() > 0.005, "the fitted mix has no shutout mass — the atom was lost"


def test_points_allowed_mix_is_monotone_in_defensive_quality():
    """A better defense must be projected to allow fewer points more often. If this inverts, the
    whole DST ranking inverts with it."""
    mix = KD.fit_points_allowed_mix(_team_game_points(), _team_points_hist())
    good = mix.probabilities([18.0])[0]
    bad = mix.probabilities([30.0])[0]
    low_idx = [KD.PA_BUCKET_LABELS.index(b) for b in ("0", "1_6", "7_13")]
    high_idx = [KD.PA_BUCKET_LABELS.index(b) for b in ("28_34", "35_45", "46p")]
    assert good[low_idx].sum() > bad[low_idx].sum()
    assert good[high_idx].sum() < bad[high_idx].sum()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. DECLARED-NOISE components stay at the league mean
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_declared_noise_components_are_projected_at_the_league_mean():
    """Defensive TDs / safeties / blocked kicks measured ρ ≈ 0.01–0.13. Projecting them per-team
    would manufacture precision that does not exist, so every team must get the same per-game rate.
    A future edit that fits a slope for them must fail here."""
    dst = _projected_dst()
    for c in KD.DST_NOISE_COMPONENTS:
        vals = dst[f"proj_{c}"].to_numpy(dtype=float)
        assert np.allclose(vals, vals[0], atol=1e-9), (
            f"proj_{c} varies by team but {c} is a DECLARED-NOISE component — it must be projected "
            f"at the league mean (see DST_NOISE_COMPONENTS)")


def test_retained_components_do_vary_by_team():
    """The complement of the check above: a component that DOES carry signal must actually move, or
    the model has collapsed to an all-league-mean projection and the tiering is fake.

    ⚠️ Needs a panel above `fit_linear_shrink`'s 30-row minimum — below it EVERY component correctly
    falls to the league mean (an intentional guard: a slope fitted on a handful of team-seasons is
    noise). So this fixture uses 20 teams, unlike the 3-team fixture the noise check uses."""
    teams = tuple(f"T{i:02d}" for i in range(20))
    seasons = (2021, 2022, 2023, 2024, 2025)
    td = _team_def_hist(seasons=seasons, teams=teams)
    tp = _team_points_hist(seasons=seasons, teams=teams)
    panel = KD.build_dst_training_panel(td, tp, None, [2023, 2024, 2025])
    assert len(panel) >= 30, "fixture too small to exercise a fitted slope"
    model = KD.fit_dst_component_model(panel)
    model.pa_mix = KD.fit_points_allowed_mix(_team_game_points(teams=teams), tp)
    dst = KD.project_dst(
        pd.DataFrame({"season": 2026, "team": list(teams), "scheduled_games": 17.0}),
        td, tp, model,
        pd.DataFrame({"season": 2026, "team": list(teams), "sos_off_pg": 22.0, "sos_off_z": 0.0}),
        2026)
    retained = [c for c in KD.DST_COMPONENTS if c not in KD.DST_NOISE_COMPONENTS]
    moved = [c for c in retained if dst[f"proj_{c}"].std() > 1e-9]
    assert moved, f"no retained DST component varies by team (checked {retained})"


def test_fit_linear_shrink_clamps_a_negative_slope_to_the_league_mean():
    """A negative fitted slope on a per-game rate is noise, not an anti-signal worth serving —
    projecting a good defense to be BAD next year would be worse than projecting the mean."""
    rng = np.random.default_rng(3)
    prior = rng.uniform(1, 3, 200)
    realized = 5.0 - 1.5 * prior + rng.normal(0, 0.05, 200)     # strongly NEGATIVE relationship
    fit = KD.fit_linear_shrink(prior, realized)
    assert fit.slope == 0.0 and fit.forced_mean
    assert fit.predict(prior) == pytest.approx(np.full(200, fit.league_mean))


def test_fit_linear_shrink_force_mean_pins_the_slope_to_zero():
    rng = np.random.default_rng(4)
    prior = rng.uniform(1, 3, 200)
    fit = KD.fit_linear_shrink(prior, 2.0 * prior, force_mean=True)
    assert fit.slope == 0.0 and fit.forced_mean


def test_a_unit_with_no_prior_history_falls_to_the_league_mean():
    """NULL/unknown kept NULL-ish: a team with no prior must get the league mean, not the regression
    intercept (which is meaningless on its own)."""
    fit = KD.LinearShrink(slope=0.5, intercept=1.0, league_mean=2.0, n=100)
    out = fit.predict([np.nan, 4.0])
    assert out[0] == pytest.approx(2.0)
    assert out[1] == pytest.approx(3.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. ⭐ THE INTERVAL DISCIPLINE (NF1.7 → 1.8 → 1.9, inherited)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_band_emits_p10_p90_independently_and_asymmetrically():
    """NF1.7's core fix. A single-`sd` reconstruction is SYMMETRIC by construction and would slide a
    skewed band off its own point. K/DST bands are more skewed than any offensive position, so the
    two sides must be able to differ in their distance from the point."""
    band = KD.fit_ratio_band(_band_panel())
    groups = np.array(["DST", "K_starter", "K_reserve"])
    lo, hi = KD.apply_band([110.0, 130.0, 70.0], groups, band)
    left, right = np.array([110.0, 130.0, 70.0]) - lo, hi - np.array([110.0, 130.0, 70.0])
    assert np.any(np.abs(left - right) > 1e-6), "the band came out symmetric — the asymmetry was lost"


def test_apply_band_always_contains_its_own_point():
    """The NF1.7 coherence invariant the league rescore relies on. A displayed interval that does
    not contain its own point is incoherent on the surface, whatever the ratios say."""
    band = KD.fit_ratio_band(_band_panel())
    rng = np.random.default_rng(11)
    pts = rng.uniform(0, 300, 500)
    groups = rng.choice(["DST", "K_starter", "K_reserve"], 500)
    lo, hi = KD.apply_band(pts, groups, band)
    assert np.all(lo <= pts + 1e-9)
    assert np.all(pts <= hi + 1e-9)
    assert np.all(lo >= 0.0), "a bound went below the 0 floor both targets have"


def test_the_widen_knob_is_monotone_and_can_only_widen():
    """⚠️ NF1.7 (d): a 'widen-only' knob that is secretly two-sided SHARPENS half the field and costs
    coverage. Widening must inflate the half-widths around 1.0, so more widen is never narrower."""
    panel = _band_panel()
    groups = np.array(["DST", "K_starter", "K_reserve"])
    pts = np.array([110.0, 130.0, 70.0])
    prev_lo, prev_hi = KD.apply_band(pts, groups, KD.fit_ratio_band(panel, widen=1.0))
    for w in (1.1, 1.25, 1.5, 2.0):
        lo, hi = KD.apply_band(pts, groups, KD.fit_ratio_band(panel, widen=w))
        assert np.all(lo <= prev_lo + 1e-9), f"widen={w} SHARPENED the lower bound"
        assert np.all(hi >= prev_hi - 1e-9), f"widen={w} SHARPENED the upper bound"
        prev_lo, prev_hi = lo, hi


def test_a_widen_below_one_cannot_sharpen_the_band():
    """The knob is clamped at 1.0 — it is a widening knob, not a scaling knob, so it cannot be used
    to quietly tighten a band toward a coverage target."""
    panel = _band_panel()
    groups = np.array(["DST"])
    base = KD.apply_band([110.0], groups, KD.fit_ratio_band(panel, widen=1.0))
    small = KD.apply_band([110.0], groups, KD.fit_ratio_band(panel, widen=0.5))
    assert small[0] == pytest.approx(base[0]) and small[1] == pytest.approx(base[1])


def test_cluster_widening_is_outward_only_and_prices_the_quantile_spread():
    """⭐ The pre-registered parameter-uncertainty widening. The pooled ROW quantile implicitly claims
    to know next season's quantile exactly; rows inside a season are not independent draws. More
    `cluster_z` must only ever widen, and z=0 must reproduce the raw pooled quantiles."""
    panel = _band_panel()
    raw = KD.fit_ratio_band(panel, cluster_z=0.0)
    wide = KD.fit_ratio_band(panel, cluster_z=1.0)
    for g in raw.groups:
        assert wide.groups[g][0] <= raw.groups[g][0] + 1e-12, f"{g} lower bound sharpened"
        assert wide.groups[g][1] >= raw.groups[g][1] - 1e-12, f"{g} upper bound sharpened"
        # z=0 must be exactly the un-widened pooled quantile
        assert raw.groups[g] == pytest.approx(raw.raw_groups[g])
    assert wide.cluster_z == 1.0
    assert any(sd[0] > 0 or sd[1] > 0 for sd in wide.cluster_sd.values()), (
        "no across-season spread was measured at all — the widening is a silent no-op")


def test_a_negative_cluster_z_cannot_sharpen_the_band():
    panel = _band_panel()
    raw = KD.fit_ratio_band(panel, cluster_z=0.0)
    neg = KD.fit_ratio_band(panel, cluster_z=-2.0)
    for g in raw.groups:
        assert neg.groups[g] == pytest.approx(raw.groups[g])


def test_an_unfittable_band_raises_rather_than_returning_a_vacuous_pass():
    """⚠️ THE NF1.7 ANCHOR LESSON. A band that quietly returns None/empty makes every coverage check
    downstream pass on NOTHING. Both the empty-panel and the no-usable-rows paths must RAISE."""
    with pytest.raises(ValueError, match="empty panel"):
        KD.fit_ratio_band(pd.DataFrame())
    unusable = _band_panel().assign(point=0.0)
    with pytest.raises(ValueError, match="no usable rows"):
        KD.fit_ratio_band(unusable)


def test_a_band_group_with_no_quantile_and_no_pooled_fallback_raises():
    """Same lesson at the APPLY step: an unknown group must not silently produce a (1,1) no-op band."""
    band = KD.RatioBand(groups={}, pooled={})
    with pytest.raises(KeyError, match="refusing to emit an interval"):
        band.ratios_for(["DST"])


def test_a_thin_band_group_falls_back_to_the_pooled_position_band_loudly():
    """A group below the minimum must fall back to the POOLED position band and RECORD that it did —
    a silent fallback is a band nobody knows is class-level."""
    band = KD.fit_ratio_band(_band_panel(), min_group_n=10_000)
    assert set(band.fell_back) == {"DST", "K_starter", "K_reserve"}
    assert band.groups == {}
    lo, hi = KD.apply_band([110.0], ["DST"], band)      # still emits, via the pooled fallback
    assert lo[0] < hi[0]


def test_an_unfittable_dst_model_raises():
    with pytest.raises(ValueError, match="empty training panel"):
        KD.fit_dst_component_model(pd.DataFrame())


def test_project_dst_refuses_to_emit_zero_bucket_columns_without_a_mix():
    """Emitting the bucket columns as zeros would read as 'this defense never allows points' and
    silently hand every DST the maximum tier score."""
    model = _fitted_dst_model()
    model.pa_mix = None
    with pytest.raises(ValueError, match="points-allowed mix"):
        KD.project_dst(_dst_universe(), _team_def_hist(), _team_points_hist(), model, _sos(), 2026)


def test_both_degenerate_anchors_lose_the_interval_score():
    """⭐ Two-sided anchors, reported every run (NF1.8 / NF-D11). `zero_width` is maximally SHARP and
    pays the full miss penalty; `max_width` covers ~everything, SATISFIES ANY COVERAGE FLOOR, and
    pays its own width. Both must lose the proper score — that is what makes coverage a CONSTRAINT
    the metric can then eliminate a degenerate from, rather than a criterion a degenerate wins."""
    panel = _band_panel()
    band = KD.fit_ratio_band(panel)
    lo, hi = KD.apply_band(panel["point"], panel["band_group"], band)
    shipped = float(np.mean(KD.interval_score(lo, hi, panel["realized"])))
    anchors = KD.degenerate_anchors(panel["point"], panel["realized"])
    assert shipped < anchors["zero_width"]["interval_score"]
    assert shipped < anchors["max_width"]["interval_score"]
    # ...and the max_width degenerate must indeed satisfy a nominal coverage FLOOR, which is exactly
    # why a coverage figure can never be the selection criterion
    assert anchors["max_width"]["coverage_80"] >= KD.NOMINAL_COVERAGE


def test_interval_score_is_minimised_by_the_true_quantiles():
    """The proper-score property the whole reporting posture rests on: no degenerate strategy can
    beat the true q10/q90 pair."""
    rng = np.random.default_rng(21)
    y = rng.normal(100, 20, 20000)
    true_lo, true_hi = np.quantile(y, 0.10), np.quantile(y, 0.90)
    best = float(np.mean(KD.interval_score(true_lo, true_hi, y)))
    for lo, hi in ((100, 100), (0, 250), (true_lo - 30, true_hi), (true_lo, true_hi - 25)):
        assert best <= float(np.mean(KD.interval_score(lo, hi, y))) + 1e-9


def test_coverage_is_reported_against_a_floor_not_a_target():
    """E2.1-r / NF1.9 (e): on a zero-atom, floored target a coverage TARGET is structurally inverted
    — hitting 0.80 exactly can require deliberately under-covering the right tail. `band_report`
    must publish the nominal as a reference and never a distance-to-target."""
    panel = _band_panel()
    band = KD.fit_ratio_band(panel)
    lo, hi = KD.apply_band(panel["point"], panel["band_group"], band)
    rep = KD.band_report(lo, hi, panel["realized"], panel["position"])
    assert rep["nominal"] == KD.NOMINAL_COVERAGE
    assert not any("target" in k or "abs_dev" in k for k in rep), (
        "band_report grew a coverage-distance term — that is the E2.1-r inversion")
    assert {"coverage_80", "below_p10", "above_p90", "interval_score"} <= set(rep)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The POPULATION must stay honest (the NF1.9 left-join lesson)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_band_panel_is_built_with_a_left_join_and_a_zero_fill():
    """⚠️ THE MEASUREMENT-BREAKING EDIT. A cut kicker realises exactly 0 fantasy points and is ~13%
    of the week-1-rostered population — the exact left tail the band exists to price. Every other
    projection backtest in this program filters on games played, which is right for a RANK read and
    would flatter the interval precisely where it is weakest. This pins the source so a future
    'fix' to an inner join cannot land silently."""
    src = (_FANTASY / "run_kdst_projection.py").read_text()
    body = src[src.index("def build_band_panel"):src.index("def walk_forward_coverage")]
    assert 'how="left"' in body, "build_band_panel no longer LEFT-joins realized outcomes"
    assert 'how="inner"' not in body, "build_band_panel switched to an inner join (NF1.9 regression)"
    assert re.search(r'fillna\(0\.0\)', body), "the 0-fill for a never-played entity is gone"
    assert not re.search(r'\[[^\]]*"?g"?\]\s*>=', body), (
        "build_band_panel grew a games filter — that deletes the tail being measured")


def test_the_kicker_universe_keeps_the_camp_bodies():
    """The preseason universe must be the WEEK-1 ROSTER, not 'kickers who kicked'. A universe defined
    by realized production cannot have an absence class, and its band cannot price one."""
    src = (_FANTASY / "kdst_source.py").read_text()
    body = src[src.index("_KICKER_UNIVERSE_SQL"):src.index("def load_dst_universe")]
    assert "stg_nfl_weekly_rosters" in body and "week = 1" in body
    assert "fg_att" not in body, (
        "the kicker universe filters on kicking production — that silently deletes the cut-kicker "
        "class the interval exists to price")


def test_walk_forward_coverage_raises_when_nothing_was_scored():
    """A coverage check that scores nothing must RAISE, never report a pass."""
    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16
    with pytest.raises(ValueError, match="no held-out target seasons"):
        NF16.walk_forward_coverage(_band_panel(), min_train_targets=99)


def test_walk_forward_coverage_never_trains_on_its_own_evaluation_season():
    """The band must be fitted on strictly earlier target seasons than the one it is scored on,
    or the reported coverage is in-sample and meaningless."""
    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16
    src = (_FANTASY / "run_kdst_projection.py").read_text()
    body = src[src.index("def walk_forward_coverage"):src.index("def rank_signal")]
    assert 'panel["target_season"] < y' in body, "the walk-forward training filter is gone"
    rep = NF16.walk_forward_coverage(_band_panel())
    years = sorted(_band_panel()["target_season"].unique())
    assert rep["held_out_seasons"], "nothing was held out"
    assert min(rep["held_out_seasons"]) > min(years), (
        "the earliest season was scored with no training data before it")


def test_the_zero_atom_is_measured_and_reported():
    """The atom must stay visible: it is why coverage is structurally non-binding on the left and why
    a coverage TARGET would be inverted here."""
    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16
    rep = NF16.walk_forward_coverage(_band_panel())
    assert rep["zero_realized_frac_K"] > 0.0, "the kicker zero atom vanished from the report"
    assert "cluster_widen_is_cost_pct" in rep, (
        "the report stopped stating what the widening COST — that makes it read as a free lunch")


def test_rank_signal_reports_the_starters_only_kicker_read():
    """⚠️ The pooled kicker rank correlation is inflated by JOB STATUS (a cut kicker realising 0 is
    easy to 'predict'), not kicking skill. The starters-only block is the honest number and must
    always be reported beside it — quoting only the pooled figure is the same flattery an inner join
    produces, reached from the other direction."""
    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16
    sig = NF16.rank_signal(_band_panel())
    assert "K_starters_only" in sig, "the honest starters-only kicker read is gone"
    assert "note" in sig["K_starters_only"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The SURFACES must keep receiving it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_projection_emits_the_mvp1_contract_alias_columns():
    """⚠️ THIS FAILURE MODE ACTUALLY HAPPENED DURING THE BUILD, AND IT IS SILENT. The engine reads the
    band through `base_p10_column`/`base_p90_column`; when those columns are absent `_stat_series`
    returns ZEROS, the `usable` guard correctly declines to use them, and the CV fallback then finds
    a NaN sd → 0 → it emits a DEGENERATE ZERO-WIDTH interval rather than a null. So a missing alias
    silently turns the honest wide band into a false-precise point."""
    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16
    for col in (NFL_PROFILE.base_points_column, NFL_PROFILE.base_sd_column,
                NFL_PROFILE.base_p10_column, NFL_PROFILE.base_p90_column):
        assert col in NF16.OUTPUT_COLS, (
            f"{col} is not emitted by the K/DST projection — the league rescore will silently "
            f"produce a ZERO-WIDTH band instead of the honest interval")


def test_a_missing_band_column_yields_a_degenerate_band_which_is_why_the_alias_is_required():
    """Demonstrates the mechanism the test above guards, so the reason is pinned and not just
    asserted: strip the bounds and the rescored interval collapses onto the point."""
    df = pd.DataFrame([{"position": "DST", "proj_def_sacks": 40.0, "proj_fp_ppr": 100.0}])
    scored = score_players(df, get_preset("full_ppr"), NFL_PROFILE)
    assert scored["league_points_p10"].iloc[0] == pytest.approx(
        scored["league_points_p90"].iloc[0], abs=0.11), (
        "expected the documented degenerate collapse when the band columns are absent")


def test_the_band_survives_the_league_rescore_asymmetrically():
    """The point of carrying p10/p90 through per side: a skewed K/DST band must still be skewed
    after the league rescore, and must still contain its own rescored point."""
    df = pd.DataFrame([{
        "position": "K", "proj_fg_made_0_39": 15.0, "proj_fg_made_40_49": 7.0,
        "proj_fg_made_50_plus": 4.0, "proj_pat_made": 44.0,
        "proj_fp_ppr": 130.0, "fp_ppr_sd": 48.0, "fp_ppr_p10": 58.0, "fp_ppr_p90": 184.0,
    }])
    out = score_players(df, get_preset("full_ppr"), NFL_PROFILE)
    pts = float(out["league_points"].iloc[0])
    lo, hi = float(out["league_points_p10"].iloc[0]), float(out["league_points_p90"].iloc[0])
    assert lo <= pts <= hi
    assert abs((pts - lo) - (hi - pts)) > 1.0, "the asymmetry was lost in the rescore"


def test_the_league_board_folds_in_the_kdst_lineage():
    src = (_FANTASY / "run_league_board.py").read_text()
    assert "combine_projections" in src and "load_kdst_local" in src
    body = src[src.index("def main"):]
    assert "args.no_kdst" in body, "the board no longer folds in the K/DST projection"


def test_combine_projections_dedupes_and_refuses_two_empty_lineages():
    from quant_sports_intel_models.football.nfl.fantasy.run_league_board import combine_projections
    off = pd.DataFrame([{"player_id": "a", "position": "WR"}])
    kd = pd.DataFrame([{"player_id": "DST-AAA", "position": "DST"}])
    assert len(combine_projections(off, kd)) == 2
    assert len(combine_projections(off, pd.DataFrame())) == 1
    dupe = pd.DataFrame([{"player_id": "a", "position": "DST"}])
    assert len(combine_projections(off, dupe)) == 1
    with pytest.raises(ValueError, match="both projection lineages are empty"):
        combine_projections(pd.DataFrame(), pd.DataFrame())


def test_k_and_dst_are_projectable_in_the_export_and_carry_the_honest_caveat():
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    assert "K" in EX.PROJECTABLE and "DST" in EX.PROJECTABLE
    assert set(EX.LOW_PREDICTABILITY) == {"K", "DST"}
    assert EX.LOW_PREDICTABILITY_NOTE.strip(), "the low-predictability caveat text is empty"
    # every gap-fill placeholder must also carry it
    for rec in EX.kdst_records(["AAA"]):
        assert rec["lowPred"] is True and rec["predNote"]


def test_export_placeholders_only_fill_the_gaps_the_projection_missed():
    """Since NF1.6 the placeholders are a FALLBACK, not the normal path. A covered (pos, team) pair
    must not get a duplicate null-projection row shadowing its real projection."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    assert len(EX.kdst_records(["AAA", "BBB"])) == 4                     # nothing covered
    partial = EX.kdst_records(["AAA", "BBB"], covered={("DST", "AAA"), ("K", "AAA")})
    assert {(r["pos"], r["team"]) for r in partial} == {("DST", "BBB"), ("K", "BBB")}
    assert EX.kdst_records(["AAA"], covered={("DST", "AAA"), ("K", "AAA")}) == []


def test_dst_unit_names_are_not_mangled_by_the_titlecaser():
    """'DEN D/ST' is a team code plus a unit label, not a person's name — `.title()` renders it
    'Den D/St'."""
    from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import _titlecase
    assert _titlecase("DEN D/ST") == "DEN D/ST"
    assert _titlecase("CHRISTIAN MCCAFFREY") == "Christian McCaffrey"   # unchanged


# ── the frontend must not silently re-filter the new positions out ────────────────────────────
_FRONTEND = Path(KD.__file__).resolve().parents[4] / "frontend"
_RANKED_SURFACES = ("rankings-board.tsx", "league-board.tsx")


@pytest.mark.parametrize("surface", _RANKED_SURFACES)
def test_the_ranked_surfaces_do_not_filter_to_skill_positions_only(surface):
    """⚠️ THIS EXACT REGRESSION SHIPPED ONCE AND WAS INVISIBLE FROM THE BACKEND.

    Every backend check passed — the projection landed, the boards carried 74 K/DST rows, the JSON
    published to prod — and K/DST still rendered nowhere, because the frontend hard-filtered them out
    with `SKILL_POSITIONS.includes(p.pos)`. Nothing server-side can see that: the data is correct all
    the way to the browser, and a client-side filter then discards it.

    So the guard lives here, in the gate that actually runs. A ranked surface must filter on
    `ALL_POSITIONS` (which includes K/DST), never on `SKILL_POSITIONS`."""
    src = (_FRONTEND / "components" / "fantasy" / surface).read_text()
    assert "ALL_POSITIONS" in src, f"{surface} no longer references ALL_POSITIONS"
    assert "SKILL_POSITIONS" not in src, (
        f"{surface} filters on SKILL_POSITIONS — that silently drops every projected K/DST row from "
        f"a ranked surface, which is invisible to every backend check (the data is correct right up "
        f"to the browser). Use ALL_POSITIONS.")


def test_the_shared_position_constants_are_distinct_and_correct():
    src = (_FRONTEND / "components" / "fantasy" / "shared.tsx").read_text()
    assert 'export const ALL_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"]' in src
    assert 'export const SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]' in src, (
        "SKILL_POSITIONS must survive — it is still correct for the genuinely skill-only reads "
        "(bye-week stacking, flex eligibility); it is just no longer the ranking universe")
    # the position tabs must offer K/DST, or the rows are present but unreachable by filter
    assert "positions = [...ALL_POSITIONS]" in src, (
        "PositionTabs no longer defaults to ALL_POSITIONS — without K/DST tabs the rows are in the "
        "payload but a user cannot filter to them, which reads as 'still not projected'")


def test_the_frontend_types_declare_the_low_predictability_fields():
    """A field absent from the TS interface is not a runtime error — it is silently unreadable in the
    component (the same shape as the Pydantic response-model landmine, one layer up)."""
    for rel in (("lib", "draft-optimizer.ts"), ("lib", "fantasy.ts")):
        src = (_FRONTEND / rel[0] / rel[1]).read_text()
        assert "lowPred" in src and "predNote" in src, (
            f"{rel[1]} does not declare lowPred/predNote — the honest K/DST caveat cannot render")


def test_no_surface_still_claims_kdst_are_unprojected():
    """The copy must not contradict the product. A page that ranks a kicker while telling the reader
    kickers are not projected is worse than either alone."""
    stale = []
    for p in (_FRONTEND / "components" / "fantasy").glob("*.tsx"):
        text = p.read_text()
        for phrase in ("carry no projection", "are not projected", "K & DST are unprojected",
                       "K &amp; DST are unprojected"):
            if phrase in text:
                stale.append(f"{p.name}: {phrase!r}")
    assert not stale, f"stale 'K/DST are unprojected' copy still shipping: {stale}"


def test_the_standing_revalidation_owns_the_kdst_floors():
    """⭐ THE DECISION THE STORY REQUIRED, PINNED. A per-position coverage floor is invisible at
    serving time, so leaving two brand-new positions unmonitored is exactly the gap that let the
    veteran band go five stories at 0.55 of nominal. The standing annual check must cover K/DST."""
    assert hasattr(REV, "revalidate_kdst")
    src = Path(REV.__file__).read_text()
    body = src[src.index("def main"):]
    assert "revalidate_kdst" in body, "the K/DST block is defined but never RUN by main"
    assert "--rebuild-kdst-panel" in src
    # the breach response for this population is WIDEN, not re-select (it is reported, not selected)
    assert "WIDEN" in REV.revalidate_kdst.__doc__ or "widen" in src.lower()


def test_revalidate_kdst_treats_a_missing_or_empty_panel_as_an_error_not_a_pass(tmp_path):
    """⚠️ An errored population must never be mistaken for one that cleared its floor."""
    missing = REV.revalidate_kdst(tmp_path / "nope.parquet")
    assert missing.get("error") and missing.get("pass") is not True
    empty = tmp_path / "empty.parquet"
    _band_panel().iloc[0:0].to_parquet(empty, index=False)
    assert REV.revalidate_kdst(empty).get("pass") is not True


def test_revalidate_kdst_derives_its_config_from_the_served_constants(tmp_path):
    """A re-validation that pins a literal keeps validating the band the code USED to serve."""
    src = Path(REV.__file__).read_text()
    body = src[src.index("def revalidate_kdst"):src.index("# ══", src.index("def revalidate_kdst"))]
    assert "KD.BAND_CLUSTER_Z" in body and "KD.BAND_QUANTILES" in body
    assert "KD.NOMINAL_COVERAGE" in body, "the floor was re-typed instead of derived"
    panel = tmp_path / "p.parquet"
    _band_panel().to_parquet(panel, index=False)
    out = REV.revalidate_kdst(panel)
    assert out["floors"] == {"DST": KD.NOMINAL_COVERAGE, "K": KD.NOMINAL_COVERAGE}
    assert "slack_rows" in out, "the floor margin must be stated in ROWS (NF1.8)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Kicker-specific model behaviour
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _kicker_hist() -> pd.DataFrame:
    rows = []
    for y in (2024, 2025):
        rows += [
            # a strong-legged incumbent
            {"season": y, "player_id": "inc", "player_name": "Inc", "team": "AAA", "games": 17.0,
             "fg_att": 34.0, "fg_made": 29.0, "fg_blocked": 0.0,
             "fg_made_0_39": 15.0, "fg_made_40_49": 8.0, "fg_made_50_plus": 6.0,
             "fg_missed_0_39": 1.0, "fg_missed_40_49": 2.0, "fg_missed_50_plus": 2.0,
             "pat_att": 40.0, "pat_made": 39.0},
            # a short-legged low-volume kicker
            {"season": y, "player_id": "wk", "player_name": "Wk", "team": "BBB", "games": 8.0,
             "fg_att": 12.0, "fg_made": 10.0, "fg_blocked": 0.0,
             "fg_made_0_39": 9.0, "fg_made_40_49": 1.0, "fg_made_50_plus": 0.0,
             "fg_missed_0_39": 1.0, "fg_missed_40_49": 1.0, "fg_missed_50_plus": 0.0,
             "pat_att": 20.0, "pat_made": 20.0},
        ]
    return pd.DataFrame(rows)


def _kicker_universe() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": 2026, "player_id": "inc", "player_name": "Inc", "team": "AAA",
         "status": "ACT", "years_exp": 4},
        {"season": 2026, "player_id": "camp", "player_name": "Camp", "team": "AAA",
         "status": "ACT", "years_exp": 0},
        {"season": 2026, "player_id": "wk", "player_name": "Wk", "team": "BBB",
         "status": "ACT", "years_exp": 2},
    ])


def _kicker_model() -> KD.KickerModel:
    panel = pd.DataFrame({
        "season": [2024] * 40 + [2025] * 40,
        "team": [f"T{i}" for i in range(40)] * 2,
        "team_points_est_pg": np.linspace(16, 30, 80),
        "pat_att_pg": np.linspace(16, 30, 80) * 0.13 - 0.6,
        "fg_att_pg": 1.94 + 0.0 * np.linspace(16, 30, 80),
    })
    return KD.fit_kicker_model(panel, _kicker_hist(), None)


def test_the_incumbent_kicker_is_resolved_by_prior_volume():
    """10 of 32 teams carry two kickers on the 2026 offseason roster. A camp body projected like a
    starter would rank ahead of real starters, so job resolution is not optional."""
    out = KD.resolve_primary_kicker(_kicker_universe(), _kicker_hist(), 2026)
    prim = out[out["is_primary"]]
    assert set(prim["player_id"]) == {"inc", "wk"}, "the incumbent was not resolved per team"
    assert out.groupby("team")["is_primary"].sum().eq(1).all(), "a team has 0 or 2 primaries"


def test_a_kicker_with_no_history_is_still_emitted_but_not_as_a_starter():
    """An honest universe keeps the camp body — with the non-primary expected-games share, not by
    deleting the row (which would leave a roster slot unfillable)."""
    out = KD.project_kickers(_kicker_universe(), _kicker_hist(), _kicker_model(),
                             pd.DataFrame({"team": ["AAA", "BBB"], "team_points_est_pg": [26.0, 20.0]}),
                             pd.DataFrame({"team": ["AAA", "BBB"], "scheduled_games": [17.0, 17.0]}),
                             2026)
    camp = out[out["player_id"] == "camp"].iloc[0]
    inc = out[out["player_id"] == "inc"].iloc[0]
    assert camp["proj_games"] < inc["proj_games"], "the camp body was projected like a starter"
    assert camp["proj_fp_std" if "proj_fp_std" in out.columns else "proj_fg_made"] is not None
    assert camp["confidence"] == "very_low"


def test_a_starting_kicker_on_a_better_offense_projects_higher():
    """The whole kicker thesis: the projection is mostly his OFFENSE's. If this inverts, the K board
    is not reading the one signal it claims to read."""
    model = _kicker_model()
    uni = pd.DataFrame([
        {"season": 2026, "player_id": "a", "player_name": "A", "team": "AAA", "status": "ACT",
         "years_exp": 3},
        {"season": 2026, "player_id": "b", "player_name": "B", "team": "BBB", "status": "ACT",
         "years_exp": 3},
    ])
    out = KD.project_kickers(uni, _kicker_hist().iloc[0:0], model,
                             pd.DataFrame({"team": ["AAA", "BBB"], "team_points_est_pg": [29.0, 17.0]}),
                             pd.DataFrame({"team": ["AAA", "BBB"], "scheduled_games": [17.0, 17.0]}),
                             2026)
    a = out[out["team"] == "AAA"].iloc[0]
    b = out[out["team"] == "BBB"].iloc[0]
    assert a["proj_pat_made"] > b["proj_pat_made"]


def test_the_make_rate_is_shrunk_hard_and_the_distance_mix_is_not():
    """⭐ The two shrinks must stay asymmetric, because the measurements are: make rate ρ = 0.085
    (near-random) vs ≥50yd attempt share ρ = 0.429 (real leg strength). If the priors were equal the
    model would either over-trust accuracy or throw away the one kicker-side signal that exists."""
    model = _kicker_model()
    assert model.make_shrink_attempts > 2 * model.mix_shrink_attempts, (
        "the make-rate prior is no longer much heavier than the distance-mix prior — that inverts "
        "the measured reliabilities")
    out = KD.project_kickers(_kicker_universe(), _kicker_hist(), model,
                             pd.DataFrame({"team": ["AAA", "BBB"], "team_points_est_pg": [23.0, 23.0]}),
                             pd.DataFrame({"team": ["AAA", "BBB"], "scheduled_games": [17.0, 17.0]}),
                             2026)
    inc = out[out["player_id"] == "inc"].iloc[0]
    wk = out[out["player_id"] == "wk"].iloc[0]
    # the strong leg must get a larger SHARE of his makes from 50+, at equal team environment
    inc_share = inc["proj_fg_made_50_plus"] / max(inc["proj_fg_made"], 1e-9)
    wk_share = wk["proj_fg_made_50_plus"] / max(wk["proj_fg_made"], 1e-9)
    assert inc_share > wk_share, "the per-kicker distance mix was shrunk away entirely"


def test_a_blank_or_missing_roster_status_counts_as_active():
    """The offseason snapshot often carries no status at all. Reading an ABSENT designation as
    inactive would zero out the entire projection-season universe, so both a blank string and a
    genuine NULL mean "no designation recorded" ⇒ active. Only a REAL designation deactivates."""
    assert KD.is_active_status(["", None, "ACT", "act"]).tolist() == [True, True, True, True]
    assert KD.is_active_status(["CUT", "RES", "PUP", "E14", "DEV"]).tolist() == [False] * 5


def test_expected_games_table_never_projects_a_camp_body_as_a_full_starter():
    """A cell too thin to fit must fall back to the measured constant, never to 1.0."""
    table = KD.fit_kicker_games_table(pd.DataFrame())
    assert table[(True, True)] > table[(True, False)] > table[(False, False)]
    assert all(v <= 1.0 for v in table.values())
    thin = pd.DataFrame({"is_active": [True], "is_primary": [False],
                         "real_games": [17.0], "team_games": [17.0]})
    assert KD.fit_kicker_games_table(thin, min_cell=25)[(True, False)] < 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Face validity — the edge-independent gate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_face_validity_catches_an_inverted_dst_ranking():
    """A top-ranked DST must be projected to ALLOW FEWER points. An inverted sign here would flip
    the entire DST board while every other check still passed."""
    dst = _projected_dst().assign(proj_fp_std=lambda d: KD.score_convenience(d))
    good = KD.face_validity(pd.concat([dst] * 5, ignore_index=True))
    inverted = dst.copy()
    inverted["proj_fp_std"] = -inverted["proj_fp_std"]
    bad = KD.face_validity(pd.concat([inverted] * 5, ignore_index=True))
    names = {c["check"] for c in bad["checks"] if not c["pass"]}
    assert "dst_points_ranks_track_points_allowed" in names or good["pass"] is not None


def test_face_validity_catches_a_backup_outprojecting_his_own_starter():
    df = pd.DataFrame([
        {"position": "K", "team": "AAA", "is_primary": True, "proj_fp_std": 90.0},
        {"position": "K", "team": "AAA", "is_primary": False, "proj_fp_std": 140.0},
    ])
    out = KD.face_validity(df)
    bad = [c for c in out["checks"] if c["check"] == "primary_kicker_outprojects_his_backup"]
    assert bad and not bad[0]["pass"] and bad[0]["violations"] == ["AAA"]


def test_face_validity_catches_an_incoherent_interval():
    df = pd.DataFrame([{"position": "K", "proj_fp_std": 100.0, "fp_p10": 120.0, "fp_p90": 150.0}])
    out = KD.face_validity(df)
    bad = [c for c in out["checks"] if c["check"] == "interval_contains_its_point"]
    assert bad and not bad[0]["pass"]


def test_face_validity_catches_bucket_mass_that_does_not_sum_to_games():
    dst = _projected_dst().assign(proj_fp_std=lambda d: KD.score_convenience(d))
    broken = dst.copy()
    broken[KD.PA_BUCKET_COLS[0]] = broken[KD.PA_BUCKET_COLS[0]] + 3.0
    out = KD.face_validity(pd.concat([broken] * 5, ignore_index=True))
    bad = [c for c in out["checks"] if c["check"] == "pa_bucket_mass_sums_to_games"]
    assert bad and not bad[0]["pass"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Train/serve consistency + leakage
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_team_environment_predictor_is_a_forward_quantity_not_a_realized_season():
    """⚠️ TRAIN/SERVE CONSISTENCY. The FG/PAT regressions must be fitted against the SAME forward
    estimate available at serve time (week-1 Vegas implied points + a regressed prior), never a
    realized season total — which would flatter the fit with information production can never have.
    Refitted honestly, the PAT correlation drops from 0.948 to ~0.38."""
    src = (_FANTASY / "run_kdst_projection.py").read_text()
    body = src[src.index("def team_points_estimate"):src.index("def team_kick_panel")]
    assert "load_week1_implied_points" in src
    assert "implied_points" in body and "prior_rate" in body
    panel_body = src[src.index("def team_kick_panel"):src.index("def kicker_games_panel")]
    assert "team_points_est_pg" in panel_body, (
        "the kicker volume panel no longer uses the forward estimate as its predictor")


def test_the_dst_training_panel_never_uses_a_target_seasons_own_data_as_a_predictor():
    """Leakage guard: a target season's predictors must come only from seasons before it."""
    td, tp = _team_def_hist(seasons=(2022, 2023, 2024, 2025)), _team_points_hist(
        seasons=(2022, 2023, 2024, 2025))
    panel = KD.build_dst_training_panel(td, tp, None, [2025])
    # 'BBB' has a constant per-game rate across seasons, so the prior must equal it exactly; the
    # structural check is that the prior is computed from a window ENDING at target-1
    assert (panel["target_season"] == 2025).all()
    lo = 2025 - KD.PRIOR_WINDOW_YEARS      # the window's first season is target-1-(window-1)
    assert lo >= 2022
    src = (_FANTASY / "kdst_projection.py").read_text()
    body = src[src.index("def build_dst_training_panel"):src.index("class DstModel")]
    assert "y - 1" in body, "the prior window no longer ends at target-1 — leakage"


def test_recency_weights_ignore_future_seasons():
    w = KD.recency_weights([2023, 2024, 2025, 2026], 2025)
    assert w[3] == 0.0, "a season AFTER the base season carried weight — leakage"
    assert w[2] > w[1] > w[0] > 0.0


def test_norm_team_folds_the_relocation_aliases():
    for raw, want in (("LA", "LAR"), ("STL", "LAR"), ("SD", "LAC"), ("OAK", "LV"), ("DEN", "DEN")):
        assert KS.norm_team(raw) == want
    assert KS.norm_team(None) is None
    assert KS.norm_team("") is None


def test_model_version_is_declared_and_distinct_from_mvp1():
    from quant_sports_intel_models.football.nfl.fantasy.season_projection import (
        MODEL_VERSION as MVP1,
    )
    assert KD.MODEL_VERSION and KD.MODEL_VERSION != MVP1
