"""NF-D14 — the rookie-QB AVAILABILITY prior.

These tests pin the things a §0.5 story can get SILENTLY wrong, in the order CLAUDE.md's landmines
were learned:

  1. **The selection metric is not inverted** — the discrete CRPS is monotone in accuracy, the oracle
     is its floor, and the `all_zero` degenerate that WINS MAE on a zero-heavy cohort LOSES it. The
     MAE inversion is asserted here as a property, so the harness's report of it can never become a
     claim nobody checks (E2.1-r (b)/(d), NF-D11).
  2. **The availability channel is INERT by default** — a `RookieBandModel` built without the NF-D14
     fields is byte-identical to the NF1.8 band that ships today. This is the guard that lets the
     plumbing land while the story records a NULL.
  3. **The widener is WIDEN-ONLY** — `clip(z, 0, 2)`, so an unusually CERTAIN availability read buys
     nothing. NF1.7 lesson (d): a two-sided `exp(gain·z)` sharpens half the field off an uncertainty
     covariate, i.e. buys the selection metric by narrowing bands.
  4. **A missing anchor is a hard failure, never a pass** (NF1.7 lesson (a)).
  5. **The cohort is LEFT-joined** — a rookie who never played is a real 0, and `blend = 0` is exactly
     the null (so the shrink grid cannot quietly change shape at its own endpoint).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import rookie_availability as AV
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a synthetic drafted-rookie cohort with a QB-like zero atom
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cohort(n_per_class: int = 40, classes: tuple[int, ...] = (2019, 2020, 2021, 2022),
            seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for y in classes:
        for i in range(n_per_class):
            pos = ("QB", "RB", "WR", "TE")[i % 4]
            overall = float(1 + (i * 260) // n_per_class)
            rnd = float(min(7, 1 + overall // 33))
            # a real availability mechanism: early picks play, late picks often do not, and the QB
            # zero atom is much fatter than the others
            p_play = float(np.clip(1.05 - 0.0035 * overall - (0.25 if pos == "QB" else 0.0), 0.02, 0.98))
            games = 0.0 if rng.random() > p_play else float(rng.integers(1, 18))
            rows.append({
                "gsis_id": f"{y}-{i}", "player_name": f"P{y}{i}", "draft_year": y,
                "position_group": pos, "nfl_position": pos, "draft_overall": overall,
                "draft_round": rnd, "rookie_games": games,
                "rookie_fp_ppr": games * (6.0 + rng.normal(0, 2)),
                "projected_nfl_z": float(rng.normal(0, 1)),
                "projected_nfl_z_sd": float(abs(rng.normal(0.4, 0.1))),
                "depth_rank": (np.nan if rng.random() < 0.2 else float(rng.integers(1, 4))),
            })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def cohort() -> pd.DataFrame:
    return _cohort()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The selection metric is not inverted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_crps_is_monotone_in_accuracy():
    """A PMF concentrated on the truth must score better than one concentrated away from it, and a
    diffuse PMF must sit between them. This is the direction check the E2.1-r oracle-floor pattern
    exists to make mechanical."""
    y = np.array([5, 5, 5])
    sharp = np.zeros((3, AV.GAMES_MAX + 1)); sharp[:, 5] = 1.0
    near = np.zeros((3, AV.GAMES_MAX + 1)); near[:, 6] = 1.0
    far = np.zeros((3, AV.GAMES_MAX + 1)); far[:, 17] = 1.0
    diffuse = np.full((3, AV.GAMES_MAX + 1), 1.0 / (AV.GAMES_MAX + 1))
    s = [float(np.mean(AV.discrete_crps(p, y))) for p in (sharp, near, diffuse, far)]
    assert s[0] == pytest.approx(0.0, abs=1e-12)
    assert s[0] < s[1] < s[2] < s[3]


def test_oracle_is_the_scoring_floor():
    """The perfect-knowledge PMF scores 0 and nothing can go below it — the direction/sign check."""
    y = np.array([0, 3, 17, 9])
    oracle = np.zeros((4, AV.GAMES_MAX + 1))
    oracle[np.arange(4), y] = 1.0
    assert float(np.mean(AV.discrete_crps(oracle, y))) == pytest.approx(0.0, abs=1e-12)
    rng = np.random.default_rng(3)
    for _ in range(25):
        p = rng.random((4, AV.GAMES_MAX + 1))
        p = p / p.sum(axis=1, keepdims=True)
        assert float(np.mean(AV.discrete_crps(p, y))) >= -1e-12


def test_the_all_zero_degenerate_WINS_mae_and_LOSES_crps_on_a_zero_heavy_cohort():
    """⭐ THE NF-D11 / E2.1-r LANDMINE, PINNED AS A PROPERTY rather than left as a report sentence.

    On a cohort whose conditional MEDIAN is 0, MAE is minimised by projecting zero for everyone — so a
    nihilist arm BEATS every honest one. A metric a nihilist wins cannot select a projection. CRPS is
    proper and reverses the ordering. If this test ever fails, either the cohort stopped being
    zero-heavy or someone made MAE selectable."""
    # 70% zeros ⇒ the conditional median is 0
    y = np.array([0] * 70 + list(range(1, 31)), dtype=float)
    n = len(y)
    honest = np.tile(AV.empirical_pmf(y), (n, 1))          # the true marginal — the best honest arm
    degenerate = AV.degenerate_pmf("all_zero", n)

    mae = lambda p: float(np.mean(np.abs(AV.pmf_stats(p)["e_games"] - y)))  # noqa: E731
    crps = lambda p: float(np.mean(AV.discrete_crps(p, y)))                 # noqa: E731

    assert mae(degenerate) < mae(honest), "the cohort is no longer zero-heavy enough to show the trap"
    assert crps(degenerate) > crps(honest), "CRPS must reject the nihilist arm"


def test_the_all_mean_degenerate_loses_crps():
    """The other degenerate ceiling: a point mass at the pooled mean is 'unbiased' in level and
    useless in shape. A proper score must reject it too."""
    y = np.array([0] * 30 + list(range(1, 41)), dtype=float)
    honest = np.tile(AV.empirical_pmf(y), (len(y), 1))
    degenerate = AV.degenerate_pmf("all_mean", len(y), float(np.mean(y)))
    assert float(np.mean(AV.discrete_crps(degenerate, y))) > float(np.mean(AV.discrete_crps(honest, y)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The prior itself
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("form,tier", [("pos_empirical", "round"), ("tier_empirical", "round"),
                                       ("tier_empirical", "depth"), ("tier_empirical", "round_depth"),
                                       ("hurdle_logit", "round"), ("haircut_ratio", "round"),
                                       ("learned_gbm", "round")])
def test_every_form_emits_a_valid_pmf(cohort, form, tier):
    tr, te = cohort[cohort.draft_year < 2022], cohort[cohort.draft_year == 2022]
    p = AV.AvailabilityPrior(form=form, tier=tier, blocks=("capital", "depth")).fit(tr).pmf(te)
    assert p.shape == (len(te), AV.GAMES_MAX + 1)
    assert (p >= -1e-12).all()
    assert np.allclose(p.sum(axis=1), 1.0)


@pytest.mark.parametrize("form", ["tier_empirical", "hurdle_logit", "haircut_ratio", "learned_gbm"])
def test_blend_zero_IS_the_null_exactly(cohort, form):
    """The shrink grid's endpoint must reproduce the null BYTE-FOR-BYTE. A blend implemented as a
    parameter interpolation rather than a MIXTURE would quietly change shape at its own endpoint, and
    then 'blend 0.3' would not mean what the report says it means."""
    tr, te = cohort[cohort.draft_year < 2022], cohort[cohort.draft_year == 2022]
    null = AV.AvailabilityPrior(form="pos_empirical").fit(tr).pmf(te)
    got = AV.AvailabilityPrior(form=form, blocks=("capital", "depth"), blend=0.0).fit(tr).pmf(te)
    assert np.allclose(got, null, atol=1e-12)


def test_a_real_availability_signal_beats_the_null_on_the_cohort_that_has_one(cohort):
    """The synthetic cohort has a REAL draft-capital availability mechanism, so a form that can see
    draft capital must beat the position-empirical null. (This is a wiring check on the harness's
    central claim, not a claim about the NFL.)"""
    tr, te = cohort[cohort.draft_year < 2022], cohort[cohort.draft_year == 2022]
    y = te["rookie_games"].to_numpy(dtype=float)
    null = AV.AvailabilityPrior(form="pos_empirical").fit(tr)
    arm = AV.AvailabilityPrior(form="hurdle_logit", blocks=("capital",)).fit(tr)
    assert float(np.mean(AV.discrete_crps(arm.pmf(te), y))) < \
           float(np.mean(AV.discrete_crps(null.pmf(te), y)))


def test_a_never_played_rookie_is_a_real_zero_not_a_dropped_row(cohort):
    """The NF1.4 survivorship bug / NF1.9 population lesson: the prior must FIT on the zeros. If a form
    silently dropped them, `p_play` would be ~1 everywhere and the whole story would be invisible."""
    tr = cohort[cohort.draft_year < 2022]
    assert (tr["rookie_games"] == 0).sum() > 0, "fixture no longer exercises the zero atom"
    pri = AV.AvailabilityPrior(form="pos_empirical").fit(tr)
    for p, pmf in pri.pos_pmf_.items():
        assert pmf[0] > 0.0, f"{p}: the fitted PMF has no mass at zero games"
    st = pri.stats(tr)
    assert st["p_play"].max() < 1.0


def test_p_short_and_sd_games_are_DIFFERENT_drivers(cohort):
    """⭐ The pre-registration's substance: availability RISK is not monotone in bust risk. `sd_games`
    peaks where the outcome is a coin flip; `p_short` is maximal at the hopeless end. If these two
    ranked players identically the two pre-registered leg-2 drivers would be one driver wearing two
    names, and the report's claim about them would be empty."""
    tr = cohort[cohort.draft_year < 2022]
    st = AV.AvailabilityPrior(form="hurdle_logit", blocks=("capital",)).fit(tr).stats(tr)
    rho = float(pd.Series(st["p_short"]).corr(pd.Series(st["sd_games"]), method="spearman"))
    assert rho < 0.95, f"the two drivers are effectively identical (rho={rho})"


def test_depth_tier_keeps_ABSENCE_as_a_real_tier():
    """A rookie with no week-1 depth-chart row is not missing data — he is the most informative state
    in the QB cohort. Imputing him away would delete the story's strongest single signal."""
    got = AV.depth_tier([np.nan, 1, 2, 5])
    assert list(got) == ["none", "1", "2", "3+"]


def test_transport_pushes_mass_into_the_zero_atom_when_the_haircut_bites():
    """NF-D11's multiplicative haircut, on a distribution: haircutting a 3-game rookie does not produce
    a fractional season, it produces a rookie who does not play."""
    base = np.array([0, 1, 2, 3, 10, 17], dtype=float)
    assert AV.transport_pmf(base, 1.0)[0] == pytest.approx(1 / 6)
    assert AV.transport_pmf(base, 0.1)[0] > AV.transport_pmf(base, 1.0)[0]
    assert AV.transport_pmf(base, 0.0)[0] == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The band channel — inert by default, widen-only when on
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _band_frame(n: int = 120, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pos = np.array([("QB", "RB", "WR", "TE")[i % 4] for i in range(n)])
    return pd.DataFrame({
        "position_group": pos,
        "draft_overall": rng.integers(1, 260, n).astype(float),
        "projected_nfl_z_sd": np.abs(rng.normal(0.4, 0.12, n)),
        "avail_risk_z": rng.normal(0.0, 1.0, n),
        "rookie_fp_ppr": np.clip(rng.normal(80, 60, n), 0, None),
    })


def test_the_availability_channel_is_inert_by_default():
    """⭐ THE SHIP-SAFETY GUARD. A band fitted without the NF-D14 arguments must be byte-identical to
    the NF1.8 band that ships today, even when the frame CARRIES an `avail_risk_z` column. NF-D14
    records a NULL, so the plumbing lands switched off — and 'switched off' has to mean bit-identical,
    not 'nearly the same'."""
    f = _band_frame()
    pred = np.clip(np.linspace(2, 260, len(f)), 0, None)
    kw = dict(form="qreg_sqrt", qreg_alpha=0.01, cqr_mode="pos", cqr_scale="add")
    base = SP.fit_rookie_band_model(f.drop(columns=["avail_risk_z"]), pred, **kw)
    withcol = SP.fit_rookie_band_model(f, pred, **kw)
    assert base is not None and withcol is not None
    a = base.band_many(f["position_group"], pred, overall=f["draft_overall"],
                       resid_sd=f["projected_nfl_z_sd"])
    b = withcol.band_many(f["position_group"], pred, overall=f["draft_overall"],
                          resid_sd=f["projected_nfl_z_sd"], avail=f["avail_risk_z"])
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    # both defaults are pinned: the DATACLASS field (what a hand-built model gets) and the FITTER
    # kwarg (the load-bearing one — every production path goes through `fit_rookie_band_model`).
    assert SP.RookieBandModel().avail_feature is False
    assert SP.RookieBandModel().avail_gain == 0.0
    assert base.avail_feature is False and base.avail_gain == 0.0


def test_the_availability_widener_is_widen_only():
    """NF1.7 lesson (d), applied to the new knob. `exp(gain·z)` unclamped is TWO-SIDED — it would
    SHARPEN every player whose availability read is unusually certain, i.e. buy the primary metric by
    narrowing bands, which is exactly the trade the coverage floor exists to forbid."""
    f = _band_frame()
    pred = np.clip(np.linspace(2, 260, len(f)), 0, None)
    kw = dict(form="qreg_sqrt", qreg_alpha=0.01, cqr_mode="pos", cqr_scale="add")
    base = SP.fit_rookie_band_model(f, pred, **kw)
    wide = SP.fit_rookie_band_model(f, pred, avail_gain=0.35, **kw)
    lo0, hi0 = base.band_many(f["position_group"], pred, overall=f["draft_overall"],
                              resid_sd=f["projected_nfl_z_sd"], avail=f["avail_risk_z"])
    lo1, hi1 = wide.band_many(f["position_group"], pred, overall=f["draft_overall"],
                              resid_sd=f["projected_nfl_z_sd"], avail=f["avail_risk_z"])
    assert np.all((hi1 - lo1) >= (hi0 - lo0) - 1e-9), "the widener SHARPENED a row — it is two-sided"
    assert np.any((hi1 - lo1) > (hi0 - lo0) + 1e-9), "the widener did nothing at all"


def test_the_availability_feature_actually_enters_the_design():
    """The other channel has to be real too — turning `avail_feature` on must change the fitted band,
    or the leg-2 'FEATURE' arms would be silently scoring the null under a different label."""
    f = _band_frame()
    pred = np.clip(np.linspace(2, 260, len(f)), 0, None)
    kw = dict(form="qreg_sqrt", qreg_alpha=0.01, cqr_mode="pos", cqr_scale="add")
    base = SP.fit_rookie_band_model(f, pred, **kw)
    feat = SP.fit_rookie_band_model(f, pred, avail_feature=True, **kw)
    assert "avail_z" in feat.qreg_lo and "avail_z" not in base.qreg_lo
    lo0, hi0 = base.band_many(f["position_group"], pred, overall=f["draft_overall"],
                              resid_sd=f["projected_nfl_z_sd"], avail=f["avail_risk_z"])
    lo1, hi1 = feat.band_many(f["position_group"], pred, overall=f["draft_overall"],
                              resid_sd=f["projected_nfl_z_sd"], avail=f["avail_risk_z"])
    assert not (np.array_equal(lo0, lo1) and np.array_equal(hi0, hi1))


def test_the_band_still_brackets_its_own_point_with_the_channel_on():
    """The coherence contract NF1.7 shipped must survive the new knob: a displayed interval that
    excludes its own point estimate is the very symptom NF3 surfaced."""
    f = _band_frame()
    pred = np.clip(np.linspace(2, 260, len(f)), 0, None)
    m = SP.fit_rookie_band_model(f, pred, form="qreg_sqrt", qreg_alpha=0.01, cqr_mode="pos",
                                 cqr_scale="add", avail_feature=True, avail_gain=0.2)
    lo, hi = m.band_many(f["position_group"], pred, overall=f["draft_overall"],
                         resid_sd=f["projected_nfl_z_sd"], avail=f["avail_risk_z"])
    assert np.all(lo <= pred + 1e-9) and np.all(hi >= pred - 1e-9)
    assert np.all(lo >= -1e-9)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Harness discipline
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_missing_anchor_is_a_hard_failure_never_a_pass():
    """NF1.7 lesson (a): an anchor that fails to fit makes its own check VACUOUSLY TRUE. The harness
    must refuse to report a selection rather than compare against nothing."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_d14_availability as NFD14

    full = {k: {"crps": 1.0} for k in NFD14._REQUIRED_LEG1_ANCHORS}
    NFD14.require_leg1_anchors(full)                       # complete set → no raise
    for drop in NFD14._REQUIRED_LEG1_ANCHORS:
        with pytest.raises(SystemExit):
            NFD14.require_leg1_anchors({k: v for k, v in full.items() if k != drop})
    with pytest.raises(SystemExit):                        # present but unscored is also a failure
        NFD14.require_leg1_anchors({**full, "permuted": {"crps": None}})


def test_the_candidate_grid_is_pre_registered_and_covers_the_required_classes():
    """§0.5 needs ≥3 candidate classes plus a DIRECT-LEARNED foil, and the null has to be in the field
    (a search whose baseline is not scored cannot report a lift)."""
    cfgs = AV.candidate_configs()
    forms = {c["form"] for c in cfgs}
    assert {"pos_empirical", "tier_empirical", "hurdle_logit", "haircut_ratio"} <= forms
    assert "learned_gbm" in forms, "the direct-learned foil is missing"
    assert len(forms - {"pos_empirical"}) >= 3
    assert sum(c["form"] == "pos_empirical" for c in cfgs) == 1
    assert len({c["label"] for c in cfgs}) == len(cfgs), "duplicate config labels"


def test_the_verdicts_require_every_check():
    """Neither verdict may pass on a subset — a gate that can be satisfied by most of its conditions is
    not the gate the report claims it is."""
    ok = dict(beats_null=True, oracle_respected=True, degenerates_lose=True,
              permutation_beaten=True, pbo=0.0, dsr=1.0, fdr_pass=True)
    assert AV.availability_verdict(**ok)["prior_is_real"]
    for k, bad in (("beats_null", False), ("oracle_respected", False), ("degenerates_lose", False),
                   ("permutation_beaten", False), ("pbo", 0.9), ("dsr", 0.1), ("fdr_pass", False)):
        assert not AV.availability_verdict(**{**ok, k: bad})["prior_is_real"]

    ok2 = dict(qb_coverage_base=0.80, qb_coverage_arm=0.85, floors_met=True,
               beats_base_interval_score=True, pbo=0.0, point_invariant=True)
    assert AV.interval_verdict(**ok2)["ship"]
    for k, bad in (("qb_coverage_arm", 0.79), ("floors_met", False),
                   ("beats_base_interval_score", False), ("pbo", 0.9), ("point_invariant", False)):
        assert not AV.interval_verdict(**{**ok2, k: bad})["ship"]


def test_the_dsr_gate_is_the_story_s_own_stricter_level():
    """NF-D14 pre-registered DSR ≥ 0.95, stricter than NF1.1/NF1.4's 0.0. Pinned so a later session
    cannot quietly relax it to make a thin-cohort claim clear — which is the E2.1-r floor-moving sin
    wearing a deflation hat."""
    assert AV.DSR_MIN == 0.95
    assert AV.PBO_MAX == 0.2
