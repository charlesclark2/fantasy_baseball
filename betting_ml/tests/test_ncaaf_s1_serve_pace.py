"""NCAAF-P2.1 S1-serve — guards for the served pace contract, the mean artifact, and the sim term.

Fast-gate compatible (`football` shard): imports only `betting_ml` + the NCAAF model modules, never
`pipeline`, and does no lake / DuckDB / network IO.

WHAT IS PINNED, AND WHY EACH ONE WOULD OTHERWISE FAIL SILENTLY
--------------------------------------------------------------
1. **ONE pace derivation.** The serving assemble and P2.1's battery assemble must produce the SAME
   `pace_sum`/`pace_diff`, or the columns that serve are not the columns S1 certified (the E9.61
   "two renderers of one field are two rule sets" class).
2. **The frozen P1.4 record is untouched.** Adding two columns to the frame must not move `full`,
   `top_k`, `clustered` or `strength_only` — including the in-fold importance RANKING that the
   latter two are built from, which two extra columns in the LightGBM fit would silently shift.
3. **A missing pace column RAISES.** Serving `strength_only` under a `strength_pace` contract would
   pair a σ fitted on pace residuals with a pace-free μ — the E7.9 mismatch, invisible at runtime.
4. **The mean artifact reproduces the sklearn pipeline** — a coefficient table that does not
   describe the served model is worse than no artifact.
5. ⭐ **A NULL feature is EXACTLY inert** — the identity the pre-season byte-identity rests on,
   asserted on the artifact math AND end-to-end through the simulator.
6. ⭐ **Two-sided:** the inertness guard is paired with a control proving the term CAN act, so
   "the board did not move" can never pass because the wiring is dead (the NF-D20 inactive-vs-
   passing distinction; a guard that cannot fail is not a guard).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bg
from quant_sports_intel_models.football.ncaaf.models import ncaaf_game_mean as gm
from quant_sports_intel_models.football.ncaaf.models import ncaaf_game_predictor as gp
from quant_sports_intel_models.football.ncaaf.models import p2_1_blocks as blocks
from quant_sports_intel_models.football.ncaaf.models import season_simulation as ss
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    NcaafGameDistributionParams,
)

_RESULTS_DIR = (blocks.__file__.rsplit("/models/", 1)[0] + "/ablation_results")


def _source(module) -> str:
    """Module source with `#` comment lines stripped — a source-inspection clause that PROSE can
    satisfy is vacuous (INC-38)."""
    from pathlib import Path
    return "\n".join(ln for ln in Path(module.__file__).read_text().splitlines()
                     if not ln.lstrip().startswith("#"))


# ═══════════════════════════════════════════════════════════════════════ helpers

def _frame(n: int = 400, *, seed: int = 7, null_first: int = 40) -> pd.DataFrame:
    """A synthetic P1.4-shaped frame: strength columns, a few non-strength features, per-side pace
    (NULL on the first `null_first` rows — the week-1 regime), and both labels."""
    rng = np.random.default_rng(seed)
    hm, am = rng.normal(0, 10, n), rng.normal(0, 10, n)
    spp_h, spp_a = rng.normal(26.5, 2.0, n), rng.normal(26.5, 2.0, n)
    spp_h[:null_first] = np.nan
    spp_a[:null_first] = np.nan
    df = pd.DataFrame({
        "game_id": np.arange(n), "season": 2018 + (np.arange(n) % 6),
        "season_order_week": 1 + (np.arange(n) % 14),
        "home_strength_margin": hm, "away_strength_margin": am,
        "home_strength_offense": hm / 2, "away_strength_offense": am / 2,
        "home_strength_defense": hm / 2, "away_strength_defense": am / 2,
        "home_strength_margin_sd": rng.uniform(3, 7, n), "away_strength_margin_sd": rng.uniform(3, 7, n),
        "strength_margin_diff": hm - am,
        "home_off_ppa": rng.normal(0, 1, n), "away_off_ppa": rng.normal(0, 1, n),
        "home_success_rate": rng.normal(0.42, 0.05, n), "away_success_rate": rng.normal(0.42, 0.05, n),
        "home_seconds_per_play": spp_h, "away_seconds_per_play": spp_a,
        "home_off_plays_per_game": rng.normal(69, 5, n), "away_off_plays_per_game": rng.normal(69, 5, n),
        "home_possession_seconds_per_game": spp_h * 69, "away_possession_seconds_per_game": spp_a * 69,
    })
    df["game_year"] = df["season"]
    df["label_home_margin"] = (hm - am) + 2.0 - 0.6 * np.nan_to_num(spp_h + spp_a - 53.0) \
        + rng.normal(0, 14, n)
    df["label_total_points"] = 54.0 - 1.4 * np.nan_to_num(spp_h + spp_a - 53.0) + rng.normal(0, 15, n)
    return df


def _mean_params(frame: pd.DataFrame | None = None, contract: str = "strength_pace"
                 ) -> tuple[gm.NcaafGameMeanParams, list[str], np.ndarray]:
    df = blocks.derive_pace_composites(frame if frame is not None else _frame())
    feat = bg.feature_columns(df)
    X, _, _ = bg._prepare_matrix(df, df.head(1), feat)
    cols = bg.resolve_contract(contract, X, feat, list(feat))
    idx = [feat.index(c) for c in cols]
    mp = gm.fit_mean_params(
        X[:, idx], df["label_home_margin"].to_numpy(float), df["label_total_points"].to_numpy(float),
        cols, learner="ridge", contract=contract, alpha=10.0,
        pace_columns=[c for c in bg.SERVED_PACE_COLS if c in cols])
    return mp, cols, X[:, idx]


# ═══════════════════════════════════════════════ 1 · one derivation, two callers

def test_the_serving_assemble_and_the_p2_1_battery_derive_the_same_pace_columns():
    """If these two ever diverge, the columns that SERVE are not the columns S1 certified."""
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_p2_1 as p21

    df = _frame()
    # the P2.1 battery path needs the extra columns its OTHER simple blocks read
    df2 = df.assign(home_rest_days=7.0, away_rest_days=7.0, is_postseason=False)
    shared = blocks.derive_pace_composites(df)
    battery = p21._simple_blocks(df2)
    for c in blocks.PACE_COMPOSITE_COLS:
        a = shared[c].to_numpy(float)
        b = battery[c].to_numpy(float)
        assert np.array_equal(a, b, equal_nan=True), f"{c} differs between the two assembles"


def test_the_composites_are_the_sum_and_difference_of_the_two_seconds_per_play_levels():
    """The equality guard above proves the two callers AGREE; it cannot prove they are RIGHT (break
    the shared function and both move together). This clause pins the arithmetic itself — the
    coordinates P2.1 H9 registered: the SUM is the total axis, the DIFFERENCE the margin axis."""
    out = blocks.derive_pace_composites(pd.DataFrame({
        "home_seconds_per_play": [26.0, 31.5], "away_seconds_per_play": [27.0, 24.25]}))
    assert out["pace_sum"].tolist() == [53.0, 55.75]
    assert out["pace_diff"].tolist() == [-1.0, 7.25]


def test_the_pace_derivation_raises_when_its_source_column_is_absent():
    with pytest.raises(KeyError, match="pace"):
        blocks.derive_pace_composites(pd.DataFrame({"home_seconds_per_play": [25.0]}))


def test_a_null_side_makes_both_composites_null_which_is_what_makes_week_one_inert():
    out = blocks.derive_pace_composites(pd.DataFrame({
        "home_seconds_per_play": [26.0, np.nan, 26.0],
        "away_seconds_per_play": [27.0, 27.0, np.nan]}))
    assert out["pace_sum"].notna().tolist() == [True, False, False]
    assert out["pace_diff"].notna().tolist() == [True, False, False]


# ═══════════════════════════════════════════ 2 · the frozen P1.4 record is untouched

@pytest.fixture(scope="module")
def frozen_contract_resolutions() -> dict[str, dict[str, list[str]]]:
    """Resolve the four frozen P1.4 contracts on the SAME frame with and without the composites.
    Module-scoped because each side pays one LightGBM importance fit."""
    out: dict[str, dict[str, list[str]]] = {}
    for label, df in (("base", _frame()), ("with_pace", blocks.derive_pace_composites(_frame()))):
        feat = bg.feature_columns(df)
        X, _, _ = bg._prepare_matrix(df, df.head(1), feat)
        b = bg.base_feature_columns(feat)
        ranking = bg.infold_importance(X[:, [feat.index(c) for c in b]],
                                       df["label_home_margin"].to_numpy(float), b)
        out[label] = {c: bg.resolve_contract(c, X, feat, ranking, top_k=12) for c in bg.CONTRACTS}
    return out


@pytest.mark.parametrize("contract", ["full", "strength_only", "top_k", "clustered"])
def test_the_four_frozen_p1_4_contracts_resolve_identically_with_and_without_the_pace_composites(
        contract, frozen_contract_resolutions):
    """The composites are appended to the frame but must be invisible to every contract that
    existed when P1.4 was decided — including through the importance RANKING."""
    r = frozen_contract_resolutions
    assert r["base"][contract] == r["with_pace"][contract]
    assert r["base"][contract], "non-vacuity: an empty resolution would make this pass on nothing"


def test_neither_pace_composite_can_reach_a_pre_s1_contract():
    df = blocks.derive_pace_composites(_frame())
    feat = bg.feature_columns(df)
    assert set(blocks.PACE_COMPOSITE_COLS) <= set(feat), "the composites must be model-eligible"
    X, _, _ = bg._prepare_matrix(df, df.head(1), feat)
    ranking = list(bg.base_feature_columns(feat))
    for contract in bg.CONTRACTS:
        cols = bg.resolve_contract(contract, X, feat, ranking, top_k=12)
        assert not (set(cols) & set(blocks.PACE_COMPOSITE_COLS)), \
            f"contract {contract!r} (a FROZEN P1.4 contract) picked up a pace composite"


def test_the_pace_contract_is_registered_outside_the_frozen_p1_4_search_field():
    assert bg.CONTRACTS == ("full", "strength_only", "clustered", "top_k")
    assert "strength_pace" in bg.POST_P1_4_CONTRACTS
    assert "strength_pace" not in bg.CONTRACTS, \
        "adding a post-P1.4 contract to the frozen search would silently widen a decided deflation"
    assert set(bg.ALL_CONTRACTS) == set(bg.CONTRACTS) | set(bg.POST_P1_4_CONTRACTS)


# ═══════════════════════════════════════════════════ 3 · the pace contract itself

def test_strength_pace_is_strength_only_plus_the_served_pace_representation():
    df = blocks.derive_pace_composites(_frame())
    feat = bg.feature_columns(df)
    X, _, _ = bg._prepare_matrix(df, df.head(1), feat)
    ranking = list(bg.base_feature_columns(feat))
    strength = bg.resolve_contract("strength_only", X, feat, ranking)
    paced = bg.resolve_contract("strength_pace", X, feat, ranking)
    assert paced == strength + list(bg.SERVED_PACE_COLS)


def test_the_served_representation_is_the_s1b_two_column_composite():
    """S1b (`ablation_results/ncaaf_p2_1_s1b_registration.md`): the composite serves, not the
    8-column S1 primary. Pinned so the registration cannot drift out of the code."""
    assert bg.SERVED_PACE_COLS == ("pace_sum", "pace_diff")
    assert tuple(blocks.PACE_COMPOSITE_COLS) == bg.SERVED_PACE_COLS
    # every served column must be a strict subset of the certified P2.1 H9 block
    assert set(bg.SERVED_PACE_COLS) <= set(blocks.BLOCK_BY_ARM["pace"].raw)


def test_strength_pace_raises_rather_than_silently_serving_strength_only():
    """A missing pace column must RAISE — a σ refitted on pace residuals served against a pace-free
    μ is the E7.9 mismatch, and it is invisible at runtime (NF1.7 a)."""
    df = _frame()                                   # NOT passed through derive_pace_composites
    feat = bg.feature_columns(df)
    X, _, _ = bg._prepare_matrix(df, df.head(1), feat)
    with pytest.raises(KeyError, match="strength_pace"):
        bg.resolve_contract("strength_pace", X, feat, list(feat))


def test_a_post_p1_4_finalize_writes_to_its_own_paths_and_never_over_the_frozen_p1_4_record():
    """A post-P1.4 contract must not overwrite the DECIDED P1.4 story's served params or its
    calibration audit trail. This is not hypothetical — the first S1-serve finalize clobbered
    `ncaaf_p1_4_calibration.{json,md}` and `git status` caught it before the commit."""
    frozen = {bg._SERVED_JSON, bg._CALIB_JSON, bg._CALIB_MD}
    post = {bg._SERVED_JSON_V2, bg._CALIB_JSON_S1, bg._CALIB_MD_S1}
    assert not (frozen & post), "a post-P1.4 output path collides with a frozen P1.4 record"
    assert bg._SERVED_MEAN_JSON not in frozen
    # ...and the routing is keyed on the contract, both ways
    src = _source(bg)
    assert "if post_p1_4 else _CALIB_JSON" in src and "if post_p1_4 else _SERVED_JSON" in src
    assert "post_p1_4 = contract in POST_P1_4_CONTRACTS" in src


def test_the_s1b_registration_record_exists_and_names_the_served_representation():
    from pathlib import Path
    p = Path(_RESULTS_DIR) / "ncaaf_p2_1_s1b_registration.md"
    assert p.exists(), "the served representation must have a written registration record"
    text = p.read_text()
    for token in ("pace_sum", "pace_diff", "strength_pace", "best_alpha = 0"):
        assert token in text


# ═══════════════════════════════════════════════════════ 4 · the mean artifact

def test_the_mean_artifact_reproduces_the_sklearn_pipeline_it_claims_to_describe():
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    mp, cols, X = _mean_params()
    df = blocks.derive_pace_composites(_frame())
    for target, label in (("margin", "label_home_margin"), ("total", "label_total_points")):
        sc = StandardScaler().fit(X)
        ref = Ridge(alpha=10.0).fit(sc.transform(X), df[label].to_numpy(float)).predict(sc.transform(X))
        got = mp.predict({c: X[:, i] for i, c in enumerate(cols)}, target)
        assert np.allclose(got, ref, atol=1e-9), f"{target}: artifact ≠ the fitted pipeline"


def test_the_mean_artifact_round_trips_through_json():
    mp, _, _ = _mean_params()
    back = gm.NcaafGameMeanParams.from_dict(json.loads(json.dumps(mp.to_dict())))
    assert back.to_dict() == mp.to_dict()


def test_the_mean_artifact_declares_exactly_the_served_pace_columns():
    """Declaration ↔ production: a `pace_columns` list that disagrees with the served contract is
    the wired-but-never-invoked class (NF-C0e)."""
    mp, cols, _ = _mean_params()
    assert list(mp.pace_columns) == [c for c in bg.SERVED_PACE_COLS if c in cols]
    assert mp.pace_columns, "the served pace contract must declare its pace columns"


def test_a_mean_artifact_whose_vectors_disagree_with_its_columns_is_refused():
    mp, _, _ = _mean_params()
    d = mp.to_dict()
    d["coef_margin"] = d["coef_margin"][:-1]
    with pytest.raises(ValueError, match="coef_margin"):
        gm.NcaafGameMeanParams.from_dict(d)


def test_a_non_linear_learner_raises_instead_of_writing_a_table_that_does_not_describe_it():
    with pytest.raises(ValueError, match="LINEAR"):
        gm.fit_mean_params(np.zeros((10, 2)), np.zeros(10), np.zeros(10), ["a", "b"],
                           learner="lgbm", contract="strength_pace", alpha=1.0)


def test_fitting_on_an_unimputed_matrix_raises_because_it_would_break_the_inertness_identity():
    X = np.array([[1.0, np.nan], [2.0, 3.0]])
    with pytest.raises(ValueError, match="non-finite"):
        gm.fit_mean_params(X, np.zeros(2), np.zeros(2), ["a", "b"], learner="ridge",
                           contract="strength_pace", alpha=1.0)


# ═════════════════════════════════════════════ 5 · a NULL feature is EXACTLY inert

def test_a_missing_pace_value_moves_mu_by_exactly_zero():
    """Not "within tolerance" — bit-for-bit. Everything about the pre-season byte-identity claim
    rests on this one identity (the scaler mean equals the NaN fill)."""
    mp, cols, X = _mean_params()
    row = {c: X[-1, i] for i, c in enumerate(cols)}   # a LATE row — it has real (non-week-1) pace
    for target in ("margin", "total"):
        with_pace = mp.predict(row, target)
        no_pace = mp.predict({**row, "pace_sum": np.nan, "pace_diff": np.nan}, target)
        base = mp.predict({k: v for k, v in row.items() if k not in bg.SERVED_PACE_COLS}, target)
        assert float(no_pace[0]) == float(base[0]), "absent and NaN must behave identically"
        assert float(mp.pace_delta({**row, "pace_sum": np.nan, "pace_diff": np.nan}, target)[0]) == 0.0
        # and the delta is exactly the difference the columns make (non-vacuity: it is not 0 here)
        assert float(mp.pace_delta(row, target)[0]) == pytest.approx(
            float(with_pace[0] - no_pace[0]), abs=1e-9)
        assert abs(float(mp.pace_delta(row, target)[0])) > 1e-6, \
            "control: on a row WITH pace the term must actually move μ, else the guard above is vacuous"


def test_a_pace_value_sitting_exactly_at_its_train_mean_also_contributes_zero():
    mp, _, _ = _mean_params()
    centred = {c: mp.center(c) for c in mp.pace_columns}
    assert float(mp.pace_delta(centred, "margin")[0]) == pytest.approx(0.0, abs=1e-12)


# ══════════════════════════════════════════ 6 · the simulator: inert, but able to act

def _league(n_conf: int = 2, per_conf: int = 8, seed: int = 3):
    rng = np.random.default_rng(seed)
    posts, sched, tid = [], [], 0
    conf_ids: dict[str, list[int]] = {}
    for c in ["SEC", "Big Ten"][:n_conf]:
        ids = []
        for _ in range(per_conf):
            m = float(rng.normal(0, 12))
            posts.append(ss.TeamPosterior(tid, f"T{tid}", c, m, 5.0, m / 2, 6.0, m / 2, 6.0))
            ids.append(tid)
            tid += 1
        conf_ids[c] = ids
    for ids in conf_ids.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                sched.append(ss.ScheduledGame(ids[i], ids[j], is_conference_game=True))
    a, b = list(conf_ids.values())
    for i in range(len(a)):
        sched.append(ss.ScheduledGame(a[i], b[i]))
    return posts, sched


def _sim_params() -> NcaafGameDistributionParams:
    return NcaafGameDistributionParams(
        form="strength_posterior", sigma_margin=16.1, sigma_total=16.7, rho=0.05,
        sigma0_margin=15.6, k_margin=0.57, sigma0_total=16.4, k_total=0.50,
        learner="ridge", contract="strength_pace")


def _board(pace, seed: int = 11):
    posts, sched = _league()
    return ss.simulate_season(posts, sched, _sim_params(), hfa=2.4, league_base=27.0,
                              fmt=ss.CfpFormat(), cfg=ss.SeasonSimConfig(n_sims=400, seed=seed),
                              season=2026, pace=pace)


def _pace(values: np.ndarray) -> ss.PaceAdjustment:
    return ss.PaceAdjustment(coef_pace_sum=-0.35, coef_pace_diff=0.20,
                             center_pace_sum=53.0, center_pace_diff=0.0,
                             team_seconds_per_play=values)


def test_a_preseason_board_is_byte_identical_with_and_without_the_pace_term():
    """⭐ THE RUNTIME CLAIM, as a unit guard: at week 1 nobody has a tempo, so the adjustment must
    leave every probability bit-for-bit unchanged."""
    posts, _ = _league()
    all_null = _pace(np.full(len(posts), np.nan))
    assert _board(None).teams == _board(all_null).teams


def test_but_a_real_pace_vector_DOES_move_the_board_so_the_guard_above_is_not_vacuous():
    """The NF-D20 two-sided control: "the board did not move" is only evidence if the term COULD
    have moved it. A dead wiring would satisfy the inertness guard perfectly."""
    posts, _ = _league()
    rng = np.random.default_rng(5)
    live = _pace(rng.normal(26.5, 2.5, len(posts)))
    assert _board(None).teams != _board(live).teams


def test_the_pace_term_reaches_the_REGULAR_SEASON_draw():
    """⭐ Isolating clause. The board-level control above is satisfied by the CCG/bracket legs
    alone, so it stays green if the regular-season draw silently drops `pace` — an AND-composed
    wiring needs one fixture per leg (NF-D17). This one reads the standings directly."""
    posts, sched = _league()
    rng_seed, params = 21, _sim_params()
    idx = ss.build_team_index(posts)
    live = _pace(np.random.default_rng(5).normal(26.5, 2.5, len(posts)))

    def standings(pace):
        rng = np.random.default_rng(rng_seed)
        strengths = ss.draw_season_strengths(idx, 400, rng)
        return ss.simulate_regular_season(idx, sched, strengths, 2.4, 27.0, params, rng, pace).wins

    assert not np.array_equal(standings(None), standings(live))
    assert np.array_equal(standings(None), standings(_pace(np.full(len(posts), np.nan))))


def test_the_pace_term_reaches_the_NEUTRAL_batch_draw_used_by_the_ccg_and_the_bracket():
    """The other leg of the same AND: conference-title games and every playoff game go through
    `_batch_neutral`, not the regular-season draw."""
    posts, _ = _league()
    idx = ss.build_team_index(posts)
    live = _pace(np.random.default_rng(5).normal(26.5, 2.5, len(posts)))
    home = np.tile(np.array([[0, 2]]), (50, 1))
    away = np.tile(np.array([[1, 3]]), (50, 1))

    def margins(pace):
        rng = np.random.default_rng(9)
        strengths = ss.draw_season_strengths(idx, 50, rng)
        return ss._batch_neutral(strengths, home, away, _sim_params(), rng, pace)

    assert not np.allclose(margins(None), margins(live))
    assert np.array_equal(margins(None), margins(_pace(np.full(len(posts), np.nan))))


def test_the_board_records_whether_the_pace_term_actually_acted():
    posts, _ = _league()
    inert = _board(_pace(np.full(len(posts), np.nan))).meta["pace_term"]
    assert inert["applied"] is True and inert["acted"] is False
    assert inert["games_with_pace_delta"] == 0 and inert["teams_with_pace"] == 0

    rng = np.random.default_rng(5)
    live = _board(_pace(rng.normal(26.5, 2.5, len(posts)))).meta["pace_term"]
    assert live["applied"] is True and live["acted"] is True
    assert live["games_with_pace_delta"] == live["simulated_games"] > 0
    assert live["max_abs_margin_delta"] > 0

    assert _board(None).meta["pace_term"] == {
        "applied": False, "reason": "no pace adjustment supplied", "acted": False}


def test_one_team_with_unknown_pace_zeroes_only_its_own_games():
    posts, _ = _league()
    v = np.full(len(posts), 26.0)
    v[0] = np.nan
    p = _pace(v)
    home = np.array([0, 1, 2])
    away = np.array([1, 2, 3])
    d = p.margin_delta(home, away)
    assert d[0] == 0.0, "a game whose team has no tempo must contribute exactly 0"
    assert d[1] != 0.0 and d[2] != 0.0


def test_a_pace_vector_of_the_wrong_length_raises_rather_than_mixing_up_teams():
    posts, sched = _league()
    with pytest.raises(ValueError, match="team entries"):
        ss.simulate_season(posts, sched, _sim_params(), 2.4, 27.0, ss.CfpFormat(),
                           ss.SeasonSimConfig(n_sims=10), season=2026,
                           pace=_pace(np.full(len(posts) - 1, 26.0)))


def test_the_sim_term_equals_the_served_ridge_contribution_it_claims_to_reproduce():
    """`PaceAdjustment` built from the artifact must reproduce `pace_delta` exactly — otherwise the
    sim carries a pace term that is not the served one."""
    mp, _, _ = _mean_params()
    spp = np.array([25.0, 28.0, np.nan])
    adj = ss.PaceAdjustment.from_mean_params(mp, spp)
    got = adj.margin_delta(np.array([0, 0]), np.array([1, 2]))
    want = mp.pace_delta({"pace_sum": np.array([53.0, np.nan]),
                          "pace_diff": np.array([-3.0, np.nan])}, "margin")
    assert np.allclose(got, want, atol=1e-12)
    assert got[0] != 0.0 and got[1] == 0.0


def test_building_a_pace_adjustment_from_a_pace_free_artifact_raises():
    mp, _, _ = _mean_params(contract="strength_only")
    assert mp.pace_columns == []
    with pytest.raises(ValueError, match="pace"):
        ss.PaceAdjustment.from_mean_params(mp, np.array([26.0]))


# ═════════════════════════════════════ 7 · the served pair cannot be mismatched

def test_a_dispersion_and_mean_fitted_on_different_contracts_are_refused(tmp_path):
    disp = NcaafGameDistributionParams(form="gaussian", sigma_margin=16.0, sigma_total=16.5,
                                       learner="ridge", contract="strength_pace",
                                       version="ncaaf_game_distribution_v2")
    (tmp_path / "ncaaf_game_distribution_v2.json").write_text(json.dumps(disp.to_dict()))
    mp, _, _ = _mean_params(contract="strength_only")
    mp.save(tmp_path / "ncaaf_game_mean_v2.json")
    with pytest.raises(ValueError, match="train/serve mismatch"):
        gp.load_served_pair(tmp_path)


def test_a_matched_pair_loads_and_reports_which_dispersion_was_chosen(tmp_path):
    mp, _, _ = _mean_params()
    disp = NcaafGameDistributionParams(form="gaussian", sigma_margin=16.0, sigma_total=16.5,
                                       learner="ridge", contract="strength_pace",
                                       version="ncaaf_game_distribution_v2")
    (tmp_path / "ncaaf_game_distribution_v2.json").write_text(json.dumps(disp.to_dict()))
    mp.save(tmp_path / "ncaaf_game_mean_v2.json")
    d, m, path = gp.load_served_pair(tmp_path)
    assert path.name == "ncaaf_game_distribution_v2.json"
    assert d.contract == m.contract == "strength_pace"


def test_v2_is_preferred_over_v1_when_both_are_present(tmp_path):
    for name, contract in (("ncaaf_game_distribution_v1.json", "strength_only"),
                           ("ncaaf_game_distribution_v2.json", "strength_pace")):
        (tmp_path / name).write_text(json.dumps(NcaafGameDistributionParams(
            form="gaussian", sigma_margin=16.0, sigma_total=16.5, learner="ridge",
            contract=contract).to_dict()))
    assert gp.resolve_served_dispersion(tmp_path).name == "ncaaf_game_distribution_v2.json"


def test_an_absent_mean_artifact_is_the_pre_s1_state_not_a_crash(tmp_path):
    (tmp_path / "ncaaf_game_distribution_v1.json").write_text(json.dumps(
        NcaafGameDistributionParams(form="gaussian", sigma_margin=16.0, sigma_total=16.5,
                                    learner="ridge", contract="strength_only").to_dict()))
    d, m, path = gp.load_served_pair(tmp_path)
    assert m is None and d.contract == "strength_only" and path.name.endswith("v1.json")
