"""E7.8 — does FanGraphs FV/rank translate to realized MLB fantasy value? (fast-gate tests)

The study's whole value is that it CANNOT manufacture a mirage, so the tests are aimed at the four
ways it could:

  1. the fantasy target is mis-computed (or a never-arrived prospect is dropped instead of scored 0,
     which would hand the survivorship confound straight back);
  2. the level confound leaks (age-relative-to-level fitted on the eval cohort);
  3. the CV leaks (the same prospect trains and evaluates — he sits on 3–5 consecutive boards);
  4. the selection metric is inverted (E2.1-r) — guarded by an explicit oracle floor.

Plus the two outcomes the study must be able to reach honestly: a PLANTED FV signal is FOUND, and a
FV column that is pure noise yields a NULL rather than a forced survivor.

Import-safe (no `pipeline`, no network, no S3) per the fast-gate rule.
"""
import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.fv_translation.fv_translation import (
    BLOCK_FV,
    BLOCK_NULL,
    BLOCK_PERF,
    Designer,
    FeatureSet,
    Learner,
    PRIMARY_CONTRAST,
    SECONDARY_CONTRAST,
    attach_outcome,
    auc,
    batter_fantasy_points,
    bh_fdr,
    cohort_folds,
    config_name,
    draft_takeaway,
    feature_sets,
    is_pitcher_position,
    onesided_paired_pvalue,
    oracle_is_the_scoring_floor,
    pitcher_fantasy_points,
    run_stage,
    spearman,
    stage_verdict,
)

LINEAR_ONLY = [Learner("linear", "linear")]


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The fantasy target
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_batter_fantasy_points_matches_the_documented_formula():
    # 100 H (20 HR), 50 BB, 150 K → 1.3·80 + 4·20 + 1·50 − 0.5·150 = 104 + 80 + 50 − 75 = 159
    fp = batter_fantasy_points([100], [20], [50], [150])
    assert fp[0] == pytest.approx(159.0)


def test_pitcher_fantasy_points_reconstructs_innings_from_batters_faced():
    # BF 400, H 90, BB 30 → IP = (400−90−30)/3 = 93.33; 3·93.33 + 1·110 − 90 − 30 − 3·10 = 240.0
    fp = pitcher_fantasy_points([400], [90], [30], [110], [10])
    assert fp[0] == pytest.approx(3 * (400 - 90 - 30) / 3 + 110 - 90 - 30 - 30)


def test_pitcher_innings_never_go_negative_on_a_disaster_cameo():
    """More baserunners than outs must floor at 0 IP, not pay a negative innings bonus."""
    fp = pitcher_fantasy_points([5], [4], [3], [0], [1])
    assert np.isfinite(fp[0]) and fp[0] == pytest.approx(0.0 - 4 - 3 - 3)


def test_a_prospect_who_never_reached_mlb_scores_zero_not_null():
    """⭐ THE SURVIVORSHIP CURE. If a non-arrival were dropped (or NaN'd) the study would only ever
    see survivors and would credit FV for the org's own belief in its top prospects."""
    cohort = pd.DataFrame({
        "player_type": ["batter", "batter"],
        "mlb_pa": [0, 500], "mlb_hits": [0, 130], "mlb_home_runs": [0, 20],
        "mlb_walks": [0, 40], "mlb_strikeouts": [0, 110],
    })
    out = attach_outcome(cohort)
    assert len(out) == 2, "a non-arrival must stay in the population"
    assert out.loc[0, "fantasy_points"] == 0.0
    assert not out.loc[0, "debuted"] and out.loc[1, "debuted"]


def test_a_sub_threshold_cameo_is_not_a_debut_but_keeps_its_real_points():
    cohort = pd.DataFrame({
        "player_type": ["batter"], "mlb_pa": [20], "mlb_hits": [5], "mlb_home_runs": [1],
        "mlb_walks": [2], "mlb_strikeouts": [6],
    })
    out = attach_outcome(cohort)
    assert not out.loc[0, "debuted"]
    assert out.loc[0, "fantasy_points"] > 0


def test_pitcher_positions_route_to_the_pitcher_target():
    assert all(is_pitcher_position(p) for p in ("RHP", "LHP", "SP", "rp", "P"))
    assert not any(is_pitcher_position(p) for p in ("SS", "CF", "1B", "C", "DH", None))


def test_the_2021_fangraphs_role_vocabulary_is_classified_as_pitching():
    """🚨 REGRESSION — the defect the first real run exposed. FanGraphs relabelled arms in 2021:
    RHP/LHP → SP / SIRP (single-inning reliever) / MIRP (multi-inning reliever). The old regex typed
    666 relievers as BATTERS, who then scored ~0 on the batter formula and entered the two most recent
    folds as fake 'never arrived' prospects — flipping the headline verdict."""
    from betting_ml.scripts.fv_translation.fv_translation import classify_position

    for pos in ("SP", "SIRP", "MIRP", "RHP", "LHP", "rhp"):
        assert classify_position(pos) == "pitcher", pos
    for pos in ("SS", "CF", "1B", "C", "DH", "UTIL", "INF", "MIF", "4C", "OF"):
        assert classify_position(pos) == "batter", pos


def test_a_two_way_or_unknown_position_defers_to_the_game_logs_never_a_silent_default():
    """A slash position (`SIRP/SS`) and an UNRECOGNISED token must both hand the decision to the
    objective evidence. Silently defaulting an unknown token to 'batter' is exactly how the 2021
    relabel slipped through."""
    from betting_ml.scripts.fv_translation.fv_translation import (
        classify_position,
        resolve_player_type,
    )

    assert classify_position("SIRP/SS") is None
    assert classify_position("QQQ") is None
    assert resolve_player_type("SIRP/SS", 20, 3) == ("pitcher", "milb_game_logs")
    assert resolve_player_type("SIRP/SS", 3, 40) == ("batter", "milb_game_logs")
    assert resolve_player_type("QQQ", 25, 0) == ("pitcher", "milb_game_logs")
    # no position signal AND no logs → a STATED default, counted in the coverage report
    assert resolve_player_type(None, 0, 0) == ("batter", "default")


def test_unknown_position_tokens_are_surfaced_for_the_next_vocabulary_change():
    from betting_ml.scripts.fv_translation.fv_translation import unknown_position_tokens

    assert unknown_position_tokens(["SP", "SS", "ZZZ/CF"]) == {"ZZZ"}
    assert unknown_position_tokens(["SIRP", "MIRP", "4C"]) == set()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The level-confound control must be fitted IN-FOLD
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _rows(levels, ages, **extra):
    n = len(levels)
    base = {"level": levels, "age": ages, "pro_experience_years": [2] * n,
            "pre_board_mlb_exposure": [0] * n, "board_season": [2021] * n,
            "fv": [50.0] * n, "eta": [2023] * n, "risk": ["High"] * n,
            "overall_rank": [None] * n, "org_rank": [5] * n, "fantasy_dynasty_rank": [None] * n,
            "minor_pa": [400] * n, "minor_woba": [0.35] * n, "minor_k_pct": [0.22] * n,
            "minor_bb_pct": [0.09] * n, "minor_iso": [0.18] * n}
    base.update(extra)
    return pd.DataFrame(base)


def test_age_relative_to_level_uses_train_means_only():
    """The level confound is controlled by age-MINUS-the-level-mean. If that mean were computed on
    the eval cohort the control would peek at the fold it is meant to protect."""
    train = _rows(["AA", "AA", "AAA", "AAA"], [21.0, 23.0, 24.0, 26.0])
    test = _rows(["AA"], [22.0])
    dz = Designer(FeatureSet("null", (BLOCK_NULL,)), "batter").fit(train)
    X = dz.transform(test)
    idx = dz.feature_names_.index("age_rel_level")
    # train mean age at AA = 22.0 → the eval row's own age must NOT shift the reference
    assert X[0, idx] == pytest.approx(0.0)


def test_an_unseen_eval_level_falls_back_to_the_global_train_age():
    train = _rows(["AA", "AA"], [21.0, 23.0])
    test = _rows(["Rookie"], [20.0])
    dz = Designer(FeatureSet("null", (BLOCK_NULL,)), "batter").fit(train)
    X = dz.transform(test)
    idx = dz.feature_names_.index("age_rel_level")
    assert X[0, idx] == pytest.approx(20.0 - 22.0)


def test_unranked_prospects_get_a_state_flag_not_an_imputed_rank():
    """Most of the board carries an org rank and only the top tier an overall rank — 'unranked' is a
    real state. Imputing a numeric rank would invent an ordering FanGraphs never published."""
    df = _rows(["AA", "AA"], [21.0, 22.0], overall_rank=[None, 12])
    dz = Designer(FeatureSet("null+rank", (BLOCK_NULL, "rank")), "batter").fit(df)
    X = dz.transform(df)
    score = dz.feature_names_.index("ovr_rank_score")
    flag = dz.feature_names_.index("is_ovr_ranked")
    assert X[0, score] == 0.0 and X[0, flag] == 0.0
    assert X[1, score] > 0.0 and X[1, flag] == 1.0


def test_fv_bucket_transform_is_a_distinct_design_from_linear():
    df = _rows(["AA"] * 4, [21.0, 22.0, 23.0, 24.0], fv=[40.0, 45.0, 55.0, 60.0])
    lin = Designer(FeatureSet("null+fv", (BLOCK_NULL, BLOCK_FV), "linear"), "batter").fit(df)
    buc = Designer(FeatureSet("null+fv#bucket", (BLOCK_NULL, BLOCK_FV), "bucket"), "batter").fit(df)
    lin.transform(df), buc.transform(df)
    assert "fv" in lin.feature_names_
    assert "fv" not in buc.feature_names_
    assert any(n.startswith("fv__") for n in buc.feature_names_)


def test_the_pre_registered_contrast_pairs_exist_in_the_grid():
    """The headline number is a FIXED pair, so both arms must actually be built."""
    names = {fs.name for fs in feature_sets()}
    for pair in (PRIMARY_CONTRAST, SECONDARY_CONTRAST):
        assert set(pair) <= names
    # and the pair must differ by exactly the FV block
    by_name = {fs.name: fs for fs in feature_sets()}
    fv_arm, base = by_name[PRIMARY_CONTRAST[0]], by_name[PRIMARY_CONTRAST[1]]
    assert set(fv_arm.blocks) - set(base.blocks) == {BLOCK_FV}
    assert fv_arm.has_fv and base.is_fangraphs_free


def test_the_null_arm_never_reads_a_fangraphs_column():
    """The foil must be FanGraphs-free or the 'incremental lift over the null' question is void."""
    df = _rows(["AA", "AAA"], [21.0, 24.0])
    dz = Designer(FeatureSet("null+perf", (BLOCK_NULL, BLOCK_PERF)), "batter").fit(df)
    dz.transform(df)
    banned = ("fv", "risk__", "rank", "eta")
    assert not [n for n in dz.feature_names_ if any(b in n for b in banned)]


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. The CV must purge the player, not just the cohort
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _player_key(cohort: int, first_cohort: int, i: int, n_per_cohort: int) -> str:
    """A sliding id window: consecutive boards share ~2/3 of their names and distant boards share
    none — the real churn shape (prospects graduate or age off the board)."""
    return f"p{i + (cohort - first_cohort) * (n_per_cohort // 3)}"


def _panel(n_per_cohort=60, cohorts=(2018, 2019, 2020, 2021, 2022), repeat_players=True, seed=0):
    """A synthetic board panel: prospects RECUR across cohorts, as they really do."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in cohorts:
        for i in range(n_per_cohort):
            pid = (_player_key(c, cohorts[0], i, n_per_cohort) if repeat_players
                   else f"p{c}_{i}")
            rows.append({"board_season": c, "player_key": pid,
                         "value": float(rng.normal())})
    return pd.DataFrame(rows)


def test_a_player_in_the_eval_cohort_is_purged_from_training():
    """⭐ THE LEAKAGE GUARD. A prospect sits on several consecutive boards sharing ONE overlapping
    outcome window — leaving him in train turns a projection into a recollection."""
    panel = _panel()
    folds = cohort_folds(panel)
    assert folds, "expanding folds must exist"
    for f in folds:
        train_players = set(panel.iloc[f.train_idx]["player_key"])
        test_players = set(panel.iloc[f.test_idx]["player_key"])
        assert not (train_players & test_players)
        assert f.n_purged > 0, "the recurring-prospect panel must actually purge someone"


def test_folds_are_expanding_and_never_train_on_the_future():
    panel = _panel(repeat_players=False)
    for f in cohort_folds(panel):
        assert (panel.iloc[f.train_idx]["board_season"] < f.cohort).all()


def test_strict_realtime_only_trains_on_closed_outcome_windows():
    """The sensitivity variant: a model tested on cohort S may only use cohorts whose full outcome
    window had closed by S. It is far stricter — and usually leaves too few folds for PBO, which is
    exactly why it is a sensitivity and not the primary."""
    panel = _panel(repeat_players=False)
    strict = cohort_folds(panel, horizon=3, strict_realtime=True)
    loose = cohort_folds(panel, horizon=3, strict_realtime=False)
    assert len(strict) < len(loose)
    for f in strict:
        assert (panel.iloc[f.train_idx]["board_season"] + 3 <= f.cohort).all()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. Selection-metric hygiene (E2.1-r)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def test_oracle_is_the_scoring_floor():
    """A candidate cannot beat a target-seeing oracle on a rank metric; one that does is the tell the
    metric is INVERTED (the E2.1-r coverage-target lesson)."""
    assert oracle_is_the_scoring_floor({"a": 0.4, "b": 0.9}, oracle=1.0)
    assert not oracle_is_the_scoring_floor({"a": 0.4, "b": 1.2}, oracle=1.0)


def test_contender_spread_ignores_the_crippled_reference_arms():
    """⭐ THE PBO DISCRIMINATOR (E2.1-r). `fv_only` carries no level or age and always trails, so a
    min→max spread would call every tied field 'wide'. The tie read uses the CONTENDERS."""
    from betting_ml.scripts.fv_translation.fv_translation import contender_spread

    # eight near-tied contenders plus one deliberately crippled arm far below
    scores = np.array([0.50, 0.505, 0.51, 0.502, 0.508, 0.499, 0.504, 0.507, 0.10])
    contenders, full = contender_spread(scores)
    assert contenders < 0.05, "the top configs genuinely tie → must read as the NULL"
    assert full > 0.35, "the full range is still reported, for transparency"


def test_rank_metrics_behave():
    y = [0, 0, 1, 3, 10]
    assert spearman(y, y) == pytest.approx(1.0)
    assert spearman([5, 4, 3, 2, 1], [1, 2, 3, 4, 5]) == pytest.approx(-1.0)
    assert auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == pytest.approx(1.0)


def test_degenerate_folds_return_none_not_a_fabricated_zero():
    """A cohort where nobody produced carries no ordering — say None, never invent a 0."""
    assert spearman([1, 2, 3, 4, 5], [0, 0, 0, 0, 0]) is None
    assert auc([1, 2, 3], [1, 1, 1]) is None


def test_bh_fdr_never_passes_an_unscorable_test():
    out = bh_fdr({"a": 0.001, "b": None, "c": 0.9}, q=0.10)
    assert out["a"] and not out["b"] and not out["c"]


def test_onesided_pvalue_is_none_when_too_thin():
    assert onesided_paired_pvalue([0.1, 0.2]) is None
    assert onesided_paired_pvalue([0.5, 0.6, 0.7]) < 0.05


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. End-to-end: the study finds a planted signal, and returns a NULL when there is none
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _synthetic_cohort(*, fv_signal: float, n_per_cohort=140,
                      cohorts=(2018, 2019, 2020, 2021, 2022), seed=7) -> pd.DataFrame:
    """A board panel with a TUNABLE FV→outcome relationship, everything else held realistic.

    `fv_signal=0` makes FV pure noise (the null the study must be able to return); a large value
    plants a real, level/age-orthogonal effect the study must be able to find.
    """
    rng = np.random.default_rng(seed)
    levels = np.array(["A", "A+", "AA", "AAA"])
    rows = []
    for c in cohorts:
        for i in range(n_per_cohort):
            lvl = levels[rng.integers(0, 4)]
            lvl_i = int(np.where(levels == lvl)[0][0])
            age = 19.5 + 1.1 * lvl_i + rng.normal(0, 1.0)
            age_rel = age - (19.5 + 1.1 * lvl_i)
            fv = float(rng.choice([35, 40, 45, 50, 55, 60], p=[.2, .3, .2, .15, .1, .05]))
            # latent talent: level proximity + being YOUNG for the level, + optional FV effect
            latent = 0.55 * lvl_i - 0.45 * age_rel + fv_signal * (fv - 45) / 10.0 + rng.normal(0, 1.0)
            pa = max(0.0, 900.0 * (latent > 0.9) * rng.uniform(0.3, 1.5))
            rows.append({
                "board_season": c, "player_key": _player_key(c, cohorts[0], i, n_per_cohort),
                "player_type": "batter", "level": lvl, "age": age,
                "pro_experience_years": float(rng.integers(0, 6)), "pre_board_mlb_exposure": 0.0,
                "fv": fv, "risk": str(rng.choice(["High", "Medium"])), "eta": c + 2,
                "overall_rank": None, "org_rank": int(rng.integers(1, 40)),
                "fantasy_dynasty_rank": None,
                "minor_pa": float(rng.integers(150, 550)),
                "minor_woba": 0.32 + 0.03 * rng.normal(), "minor_k_pct": 0.23 + 0.03 * rng.normal(),
                "minor_bb_pct": 0.09 + 0.02 * rng.normal(), "minor_iso": 0.16 + 0.04 * rng.normal(),
                "mlb_pa": pa, "mlb_hits": 0.25 * pa, "mlb_home_runs": 0.03 * pa,
                "mlb_walks": 0.08 * pa, "mlb_strikeouts": 0.22 * pa,
            })
    return attach_outcome(pd.DataFrame(rows))


def test_a_planted_fv_signal_is_found_at_the_headline_stage():
    cohort = _synthetic_cohort(fv_signal=2.5)
    res = run_stage(cohort, player_type="batter", stage="unconditional",
                    learner_set=LINEAR_ONLY)
    c = res.contrasts["primary"]["linear"]
    assert c["mean_lift"] > 0, "a strong planted FV effect must show up in the FIXED contrast"
    assert res.oracle_ok
    best_fv = res.leaderboard[res.leaderboard["uses_fangraphs"]]["oos_metric"].max()
    best_free = res.leaderboard[~res.leaderboard["uses_fangraphs"]]["oos_metric"].max()
    assert best_fv > best_free


def test_a_noise_fv_column_yields_a_null_verdict_not_a_forced_survivor():
    """⭐ THE ANTI-MIRAGE TEST. With FV as pure noise the pre-registered contrast must NOT clear the
    deflated gates. A study that 'finds' something here would find something on the real board too."""
    cohort = _synthetic_cohort(fv_signal=0.0, seed=11)
    res = run_stage(cohort, player_type="batter", stage="unconditional", learner_set=LINEAR_ONLY)
    v = stage_verdict(res, fdr_pass=True)          # hand it the benefit of the doubt on FDR
    assert not v["adds_lift"]
    assert v["pbo_read"]


def test_the_debut_stage_scores_the_full_cohort_and_the_conditional_stage_only_survivors():
    cohort = _synthetic_cohort(fv_signal=1.5)
    debut = run_stage(cohort, player_type="batter", stage="debut", learner_set=LINEAR_ONLY)
    cond = run_stage(cohort, player_type="batter", stage="conditional", learner_set=LINEAR_ONLY)
    assert debut.n_test_rows > cond.n_test_rows, (
        "the conditional stage is survivorship-EXPOSED by construction — it must be evaluated on a "
        "strictly smaller (survivor) population than the debut stage")


def test_every_config_in_the_leaderboard_is_scored_on_every_fold():
    cohort = _synthetic_cohort(fv_signal=1.0)
    res = run_stage(cohort, player_type="batter", stage="unconditional", learner_set=LINEAR_ONLY)
    assert res.per_fold.notna().all().all()
    assert len(res.leaderboard) == len(feature_sets()) * len(LINEAR_ONLY)
    assert config_name(feature_sets()[0], LINEAR_ONLY[0]) in set(res.per_fold.index)


def test_too_few_cohorts_raises_rather_than_reporting_a_one_fold_verdict():
    cohort = _synthetic_cohort(fv_signal=1.0, cohorts=(2018, 2019))
    with pytest.raises(ValueError, match="evaluable board cohort"):
        run_stage(cohort, player_type="batter", stage="unconditional", learner_set=LINEAR_ONLY)


def test_block_decomposition_separates_our_own_read_from_what_FV_adds_on_top():
    """The mechanism question the headline contrast cannot answer: a positive contrast says FV adds
    something, not whether it adds something our own MLE already knew."""
    from betting_ml.scripts.fv_translation.fv_translation import block_decomposition

    lb = pd.DataFrame({
        "feature_set": ["null", "null", "null+perf", "null+perf+fv"],
        "oos_metric": [0.60, 0.58, 0.65, 0.67],      # two learners for `null`; the best is taken
    })
    d = block_decomposition(lb)
    assert d["null"] == pytest.approx(0.60)
    assert d["perf_adds"] == pytest.approx(0.05)
    assert d["fv_adds_over_perf"] == pytest.approx(0.02)


def test_mechanism_read_is_computed_and_can_swing_either_way():
    """The substitute/complement sentence must follow the numbers — a future re-run has to be able to
    overturn it, so it can never be hardcoded prose."""
    from betting_ml.scripts.fv_translation.fv_translation import mechanism_read

    subs = [{"player_type": "batter", "perf_adds": 0.05, "fv_adds_over_perf": 0.004}]
    comp = [{"player_type": "pitcher", "perf_adds": -0.015, "fv_adds_over_perf": 0.018}]
    assert "SUBSTITUTES" in mechanism_read(subs)["batter"]
    assert "COMPLEMENTS" in mechanism_read(comp)["pitcher"]


def test_draft_takeaway_tells_the_LOSING_types_what_to_do_too():
    """Silence about a type that failed the gates reads as 'the finding applies to everyone' — the
    exact misuse this study exists to prevent."""
    vs = [{"stage": "unconditional", "player_type": "pitcher", "adds_lift": True},
          {"stage": "unconditional", "player_type": "batter", "adds_lift": False}]
    msg = draft_takeaway(vs)
    assert "PITCHER" in msg
    assert "batter" in msg and "did NOT clear" in msg


def test_draft_takeaway_covers_every_verdict_shape():
    null_v = [{"stage": s, "player_type": "batter", "adds_lift": False} for s in
              ("debut", "conditional", "unconditional")]
    assert "CLEAN NULL" in draft_takeaway(null_v)
    debut_only = [dict(v, adds_lift=v["stage"] == "debut") for v in null_v]
    assert "PARTIAL" in draft_takeaway(debut_only)
    win = [dict(v, adds_lift=v["stage"] == "unconditional") for v in null_v]
    assert "TRUST FV" in draft_takeaway(win)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. The assembly's pandas half (SQL-free, so the fast gate can exercise it)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _raw_board_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {  # a bat who arrived
            "board_season": 2019, "as_of_date": "2019-07-01", "fg_minor_id": "sa1",
            "mlbam_id": "111", "player_name": "Bat One", "position": "SS", "level": "AA",
            "age": 21.0, "fv": 55.0, "risk": "High", "eta": 2021, "overall_rank": 20,
            "org_rank": 2, "fantasy_dynasty_rank": 30,
            "bat_plate_appearances": 500, "bat_at_bats": 450, "bat_hits": 130, "bat_doubles": 25,
            "bat_triples": 3, "bat_home_runs": 15, "bat_walks": 45, "bat_intentional_walks": 2,
            "bat_hit_by_pitch": 5, "bat_sac_flies": 3, "bat_strike_outs": 110,
            "bat_total_bases": 206,
            "pit_batters_faced": 0, "pit_strike_outs": 0, "pit_walks": 0, "pit_home_runs": 0,
            "pit_ground_outs": 0, "pit_air_outs": 0, "pit_games_played": 0, "pit_games_started": 0,
            "first_milb_season": 2017, "milb_batter_games": 120, "milb_pitcher_games": 0,
            "top_level_pre_board": "Double-A",
            "mlb_pa": 600, "mlb_hits": 150, "mlb_home_runs": 22, "mlb_walks": 55,
            "mlb_strikeouts": 140, "pre_board_mlb_pa": 0, "pre_board_mlb_bf": 0,
        },
        {  # an arm who never arrived
            "board_season": 2019, "as_of_date": "2019-07-01", "fg_minor_id": "sa2",
            "mlbam_id": "222", "player_name": "Arm Two", "position": "RHP", "level": "A+",
            "age": 20.0, "fv": 45.0, "risk": "Extreme", "eta": 2023, "overall_rank": None,
            "org_rank": 14, "fantasy_dynasty_rank": None,
            "bat_plate_appearances": 0, "bat_at_bats": 0, "bat_hits": 0, "bat_doubles": 0,
            "bat_triples": 0, "bat_home_runs": 0, "bat_walks": 0, "bat_intentional_walks": 0,
            "bat_hit_by_pitch": 0, "bat_sac_flies": 0, "bat_strike_outs": 0, "bat_total_bases": 0,
            "pit_batters_faced": 400, "pit_strike_outs": 100, "pit_walks": 40, "pit_home_runs": 8,
            "pit_ground_outs": 120, "pit_air_outs": 80, "pit_games_played": 22,
            "pit_games_started": 20,
            "first_milb_season": 2018, "milb_batter_games": 0, "milb_pitcher_games": 22,
            "top_level_pre_board": "High-A",
            "mlb_pa": None, "mlb_hits": None, "mlb_home_runs": None, "mlb_walks": None,
            "mlb_strikeouts": None, "pre_board_mlb_pa": 0, "pre_board_mlb_bf": 0,
        },
        {  # unresolved identity — no MLBAM id ⇒ its outcome is UNOBSERVABLE, must be excluded
            "board_season": 2019, "as_of_date": "2019-07-01", "fg_minor_id": "sa3",
            "mlbam_id": None, "player_name": "Signee Three", "position": "OF", "level": None,
            "age": 17.0, "fv": 40.0, "risk": "Extreme", "eta": 2025, "overall_rank": None,
            "org_rank": 25, "fantasy_dynasty_rank": None,
            "bat_plate_appearances": 0, "bat_at_bats": 0, "bat_hits": 0, "bat_doubles": 0,
            "bat_triples": 0, "bat_home_runs": 0, "bat_walks": 0, "bat_intentional_walks": 0,
            "bat_hit_by_pitch": 0, "bat_sac_flies": 0, "bat_strike_outs": 0, "bat_total_bases": 0,
            "pit_batters_faced": 0, "pit_strike_outs": 0, "pit_walks": 0, "pit_home_runs": 0,
            "pit_ground_outs": 0, "pit_air_outs": 0, "pit_games_played": 0, "pit_games_started": 0,
            "first_milb_season": None, "milb_batter_games": 0, "milb_pitcher_games": 0,
            "top_level_pre_board": None,
            "mlb_pa": None, "mlb_hits": None, "mlb_home_runs": None, "mlb_walks": None,
            "mlb_strikeouts": None, "pre_board_mlb_pa": 0, "pre_board_mlb_bf": 0,
        },
    ])


def test_derive_types_players_and_excludes_the_unobservable():
    from betting_ml.scripts.fv_translation.build_fv_cohort import _derive

    df, rep = _derive(_raw_board_rows(), horizon=3, min_debut_pa=100, min_debut_bf=150)
    assert rep["unresolved_no_mlbam"] == 1
    assert len(df) == 2, "a prospect with no MLBAM id has NO observable outcome — excluding him is "\
                         "honest; scoring him 0 would fabricate a failure"
    assert list(df["player_type"]) == ["batter", "pitcher"]
    assert df.loc[df.player_type == "pitcher", "debuted"].iloc[0] == False   # noqa: E712
    assert df.loc[df.player_type == "pitcher", "fantasy_points"].iloc[0] == 0.0
    assert df.loc[df.player_type == "batter", "fantasy_points"].iloc[0] > 0


def test_derive_computes_the_as_of_minor_rates_per_player_type():
    from betting_ml.scripts.fv_translation.build_fv_cohort import _derive

    df, _ = _derive(_raw_board_rows(), horizon=3, min_debut_pa=100, min_debut_bf=150)
    bat = df[df.player_type == "batter"].iloc[0]
    pit = df[df.player_type == "pitcher"].iloc[0]
    assert bat["minor_pa"] == pytest.approx(500)          # PA
    assert bat["minor_k_pct"] == pytest.approx(110 / 500)
    assert np.isnan(bat["minor_gb_pct"])                  # a bat has no pitcher rate
    assert pit["minor_pa"] == pytest.approx(400)          # TBF shares the column by design
    assert pit["minor_gb_pct"] == pytest.approx(120 / 200)
    assert np.isnan(pit["minor_woba"])


def test_derive_pedigree_proxy_is_pro_experience_not_a_fangraphs_field():
    from betting_ml.scripts.fv_translation.build_fv_cohort import _derive

    df, _ = _derive(_raw_board_rows(), horizon=3, min_debut_pa=100, min_debut_bf=150)
    assert df.loc[df.player_type == "batter", "pro_experience_years"].iloc[0] == 2   # 2019 − 2017
    assert df.loc[df.player_type == "pitcher", "pro_experience_years"].iloc[0] == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 7. The assembly SQL, EXECUTED — the CI-blind lakehouse read, bought down against fixtures
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# CLAUDE.md's runtime gate: CI mocks all IO, so a broken S3 read is normally found only on a real
# multi-minute run. The SQL is injectable (like E7.4's), so the fast gate runs the EXACT string
# against local DuckDB tables. What it proves is the part that actually goes wrong: the joins bind,
# the two MLBAM bridge legs fire, and — the ones that would silently poison the study — the AS-OF
# GUARD and the OUTCOME WINDOW are on the right side of the board date.

@pytest.fixture()
def sql_conn():
    duckdb = pytest.importorskip("duckdb")
    conn = duckdb.connect()
    conn.execute("""
        create table board_src as select * from (values
            ('sa1','9001',NULL,'Bat One','SDP','SS','AA',21.0,55.0,'High',2021,20,2,30,NULL,
             '2019prospect',2019,'2019-07-01','2019-07-02T00:00:00Z','{}'),
            ('sa2','sa2', NULL,'Arm Two','TEX','RHP','A+',20.0,45.0,'Extreme',2023,NULL,14,NULL,NULL,
             '2019prospect',2019,'2019-07-01','2019-07-02T00:00:00Z','{}')
        ) t(fg_minor_id, fg_player_id, mlbam_id, player_name, org, position, level, age, fv, risk,
            eta, overall_rank, org_rank, fantasy_dynasty_rank, fantasy_redraft_rank, board_slug,
            season, as_of_date, ingested_at_utc, raw_json)
    """)
    # HOP 1+2: the leaderboard carries the MLBAM id THE BOARD lacks (E7.4's bridge)
    conn.execute("""
        create table lb_src as select * from (values
            ('sa2','222','2019-07-01',2019)
        ) t(fg_minor_id, mlbam_id, as_of_date, season)
    """)
    # HOP 3: the graduate leg — a NUMERIC board fg_player_id against the MLB FanGraphs feeds
    conn.execute("""
        create table fg_hit_src as select * from (values
            ('{"playerid":"9001","xMLBAMID":"111"}', 2019, '2019-07-01')
        ) t(raw_json, season, dt)
    """)
    conn.execute("create table fg_pit_src as select * from fg_hit_src limit 0")
    conn.execute("""
        create table milb_logs as select * from (values
            -- Bat One: one game BEFORE the board date, one AFTER (the after-game must NOT count)
            (111,'2019-05-01',2019,'Double-A','R',true,false, 4,4,2,1,0,0,0,0,0,0,1,3,
             0,0,0,0,0,0,0,0),
            (111,'2019-08-01',2019,'Double-A','R',true,false, 99,99,99,99,99,99,99,99,99,99,99,99,
             0,0,0,0,0,0,0,0),
            -- Arm Two: a pre-board start
            (222,'2019-06-01',2019,'High-A','R',false,true, 0,0,0,0,0,0,0,0,0,0,0,0,
             20,7,2,1,6,4,1,1)
        ) t(player_id, official_date, season, level_name, game_type, is_batter, is_pitcher,
            bat_plate_appearances, bat_at_bats, bat_hits, bat_doubles, bat_triples, bat_home_runs,
            bat_walks, bat_intentional_walks, bat_hit_by_pitch, bat_sac_flies, bat_strike_outs,
            bat_total_bases,
            pit_batters_faced, pit_strike_outs, pit_walks, pit_home_runs, pit_ground_outs,
            pit_air_outs, pit_games_played, pit_games_started)
    """)
    conn.execute("""
        create table mart_batter_rolling_stats as select * from (values
            -- BEFORE the board date → pre-board exposure, NOT outcome
            (111,'2019-04-15',2019, 3, 1, 0, 0, 1),
            -- inside the window
            (111,'2021-05-01',2021, 500, 130, 20, 45, 110),
            -- AFTER the 3-season window (2019+3 = 2022 is the last included year)
            (111,'2023-05-01',2023, 600, 160, 30, 60, 130)
        ) t(batter_id, game_date, game_year, pa_count, hits, home_runs, walks, strikeouts)
    """)
    conn.execute("""
        create table mart_pitcher_rolling_stats as select * from (values
            (999,'2021-05-01',2021, 400, 90, 30, 110, 10)
        ) t(pitcher_id, game_date, game_year, batters_faced, hits_allowed, walks, strikeouts,
            home_runs_allowed)
    """)
    return conn


def _fixture_sources():
    from betting_ml.scripts.milb_xref.player_xref import XrefSources

    return XrefSources(board="board_src", leaderboards="lb_src",
                       milb_game_logs="milb_logs", mlb_player_profiles="milb_logs",
                       fg_mlb_hitting_raw="fg_hit_src", fg_mlb_pitching_raw="fg_pit_src")


def _run_assembly(conn, horizon=3):
    from betting_ml.scripts.fv_translation.build_fv_cohort import _assembly_sql

    return conn.execute(_assembly_sql(horizon, None, None, src=_fixture_sources())).df()


def test_assembly_sql_executes_and_resolves_both_mlbam_bridge_legs(sql_conn):
    df = _run_assembly(sql_conn)
    assert len(df) == 2
    by_id = dict(zip(df["fg_minor_id"], df["mlbam_id"]))
    assert by_id["sa2"] == "222", "the leaderboard xMLBAMID leg must resolve"
    assert by_id["sa1"] == "111", "the numeric graduate leg must resolve"


def test_assembly_sql_minor_line_stops_at_the_board_date(sql_conn):
    """⭐ THE AS-OF GUARD. A MiLB game played AFTER the board snapshot is hindsight the grade could
    not have contained — the planted 99-count game must be absent."""
    df = _run_assembly(sql_conn)
    bat = df[df.fg_minor_id == "sa1"].iloc[0]
    assert bat["bat_plate_appearances"] == 4, "only the pre-board game may be summed"
    assert bat["bat_hits"] == 2


def test_assembly_sql_outcome_window_opens_after_the_board_and_closes_at_the_horizon(sql_conn):
    """The 2019 pre-board MLB game is exposure, not outcome; the 2023 season is past the 3-season
    window. Only the 2021 line may land in the target."""
    df = _run_assembly(sql_conn)
    bat = df[df.fg_minor_id == "sa1"].iloc[0]
    assert bat["mlb_pa"] == 500 and bat["mlb_hits"] == 130
    assert bat["pre_board_mlb_pa"] == 3


def test_assembly_sql_gives_a_never_arrived_prospect_a_null_window_that_derive_turns_into_zero(sql_conn):
    from betting_ml.scripts.fv_translation.build_fv_cohort import _derive

    raw = _run_assembly(sql_conn)
    arm = raw[raw.fg_minor_id == "sa2"].iloc[0]
    assert pd.isna(arm["mlb_batters_faced"])          # no MLB rows at all
    out, rep = _derive(raw, horizon=3, min_debut_pa=100, min_debut_bf=150)
    assert rep["unresolved_no_mlbam"] == 0
    arm_out = out[out.fg_minor_id == "sa2"].iloc[0]
    assert arm_out["player_type"] == "pitcher"
    assert arm_out["fantasy_points"] == 0.0 and not arm_out["debuted"]


def test_a_relabelled_pitcher_cohort_RAISES_instead_of_running_the_study():
    """⭐ THE TRIPWIRE THE FIRST RUN LACKED. Mislabelled players are wrong BEFORE any model runs, so
    no CV split or deflation gate can see them. This is the only place the class is catchable."""
    from betting_ml.scripts.fv_translation.build_fv_cohort import (
        CohortValidationError,
        _derive,
    )

    raw = _raw_board_rows()
    # simulate the next vocabulary change: an unrecognised arm label whose logs are NOT loaded either,
    # so the cascade cannot rescue it and it lands in the batter pool
    poisoned = pd.concat([raw] * 6, ignore_index=True)
    poisoned.loc[:, "fg_minor_id"] = [f"sa{i}" for i in range(len(poisoned))]
    poisoned.loc[:, "mlbam_id"] = [str(1000 + i) for i in range(len(poisoned))]
    arms = poisoned.index[: len(poisoned) // 2]
    poisoned.loc[arms, "position"] = "ZZZ"          # unknown token
    poisoned.loc[arms, "milb_pitcher_games"] = 25   # the logs KNOW he is an arm
    poisoned.loc[arms, "milb_batter_games"] = 0
    # the cascade rescues them → no raise
    ok, rep = _derive(poisoned, horizon=3, min_debut_pa=100, min_debut_bf=150)
    assert (ok["player_type"] == "pitcher").sum() >= len(arms)
    assert rep["unknown_position_tokens"] == ["ZZZ"]

    # …but if the logs are ALSO blind (nothing to fall back on) the mismatch must RAISE, not run
    blind = poisoned.copy()
    blind.loc[arms, "position"] = "1B"              # confidently wrong label
    with pytest.raises(CohortValidationError, match="PLAYER-TYPE MISMATCH"):
        _derive(blind, horizon=3, min_debut_pa=100, min_debut_bf=150)


def test_derive_is_idempotent_so_a_cohort_can_be_re_derived_without_another_s3_read():
    """A derive step must never destroy its own raw input — otherwise a fix to classification forces
    a multi-minute lakehouse re-read (and a second pass would read the pitcher exposure back through
    the batter branch)."""
    from betting_ml.scripts.fv_translation.build_fv_cohort import _derive

    once, _ = _derive(_raw_board_rows(), horizon=3, min_debut_pa=100, min_debut_bf=150)
    twice, _ = _derive(once, horizon=3, min_debut_pa=100, min_debut_bf=150)
    for col in ("player_type", "fantasy_points", "debuted", "pre_board_mlb_exposure",
                "minor_pa", "pro_experience_years"):
        pd.testing.assert_series_equal(once[col].reset_index(drop=True),
                                       twice[col].reset_index(drop=True), check_names=False)


def _patch_delta(monkeypatch, writer):
    """Stub the Delta writer + the credential resolver so the mirror path is testable offline."""
    import deltalake

    import scripts.utils.delta_lake as dl

    monkeypatch.setattr(deltalake, "write_deltalake", writer)
    monkeypatch.setattr(dl, "storage_options", lambda: {})


def test_the_s3_mirror_overwrites_the_SCHEMA_not_just_the_data(monkeypatch):
    """🚨 REGRESSION (2026-07-27): `mode='overwrite'` replaces the DATA but KEEPS the existing table
    schema, so once the derive gained columns the write died with `SchemaMismatchError: 73 vs 71`.
    This table is a full-replace research artifact ⇒ `schema_mode='overwrite'` (the sibling INGESTS
    use 'merge' because their column sets only grow)."""
    from betting_ml.scripts.fv_translation.build_fv_cohort import _land_on_s3

    seen = {}

    def writer(uri, data, **kwargs):
        seen.update(kwargs)

    _patch_delta(monkeypatch, writer)
    assert _land_on_s3(pd.DataFrame({"a": [1]})) is True
    assert seen.get("mode") == "overwrite"
    assert seen.get("schema_mode") == "overwrite"


def test_a_failed_s3_mirror_never_discards_the_assembled_cohort(monkeypatch, capsys):
    """ALERT-loud-but-continue: the study's input is the LOCAL parquet, so a Delta hiccup must not
    raise and force the whole multi-minute lakehouse read again — but it must never be silent."""
    from betting_ml.scripts.fv_translation.build_fv_cohort import _land_on_s3

    def boom(*a, **k):
        raise RuntimeError("SchemaMismatchError: 73 vs 71")

    _patch_delta(monkeypatch, boom)
    assert _land_on_s3(pd.DataFrame({"a": [1]})) is False      # no raise
    assert "[ALERT]" in capsys.readouterr().err                # and loudly reported


def test_the_default_season_ceiling_excludes_cohorts_whose_window_is_still_open():
    """⭐ The silently-wrong class: a board cohort whose outcome window has not closed sees a
    TRUNCATED label, so its prospects look like busts. The cap must be the DEFAULT, not a flag the
    operator has to remember."""
    from datetime import date

    from betting_ml.scripts.fv_translation.build_fv_cohort import default_season_ceiling

    # mid-2026 ⇒ the last COMPLETE MLB season is 2025 ⇒ a 3-season window closes for the 2022 board
    assert default_season_ceiling(3, today=date(2026, 7, 27)) == 2022
    assert default_season_ceiling(2, today=date(2026, 7, 27)) == 2023
    # January still counts the prior year as the last complete season
    assert default_season_ceiling(3, today=date(2026, 1, 5)) == 2022


def test_assembly_sql_horizon_is_honoured(sql_conn):
    """A 4-season window reaches 2023 and must pick up the extra line the 3-season window excluded."""
    wide = _run_assembly(sql_conn, horizon=4)
    bat = wide[wide.fg_minor_id == "sa1"].iloc[0]
    assert bat["mlb_pa"] == 1100
