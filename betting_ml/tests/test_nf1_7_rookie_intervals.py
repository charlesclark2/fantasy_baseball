"""NF1.7 — guards for the PER-PLAYER rookie 80% band.

WHAT THIS PROTECTS. NF3 surfacing found the rookie band was CLASS-LEVEL: 81 rookies on the served 2026
board carried **12** distinct intervals (3 per position) while 703 veterans carried 647, so every
top-bucket rookie QB shared an identical 26.5–277.0 against point projections spanning 25.1→268.3. NF1.7
replaced it with a per-player band selected on a PROPER interval score with coverage as a FLOOR.

The tests below split into the three things that can silently break:
  1. **The POINT must not move.** NF1.4 established the rookie point is ~unbiased and its model bake-off
     returned a NULL. An edit that lets the band's history or fit leak into the point curve would ship
     an unselected model, quietly.
  2. **The band must stay PER-PLAYER and COHERENT.** Re-quantising it (or reintroducing a shared
     bucket) is the original defect returning.
  3. ⭐ **THE SELECTION METRIC MUST STAY ORIENTED** — the CLAUDE.md §0.5 landmine, which is exactly how
     this defect got shipped in the first place: NF1.4 selected the band on COVERAGE, and a
     position-CONSTANT band hits nominal coverage while carrying zero per-player information. So the
     interval score is pinned from BOTH ends here: an ORACLE that knows the answer must be unbeatable,
     and BOTH degenerate strategies — zero width (maximally "sharp") and all-encompassing width
     (coverage ≈ 1) — must lose. A metric either degenerate can win cannot select an interval.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp
from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (
    _SHARED_BAND_POINT_SPREAD_TOL,
    audit_interval_quality,
)
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_interval_ablation import (
    interval_score,
)

_REPO = Path(__file__).resolve().parents[2]
_POOL = (_REPO / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
         / "nf1_4_rookie_training.parquet")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a synthetic drafted-rookie population with a KNOWN conditional spread
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _population(n: int = 900, seed: int = 7) -> pd.DataFrame:
    """A drafted-rookie population whose noise GROWS with the draft slot's implied level — i.e. the
    conditional spread genuinely depends on the player, which is precisely what a class-level band
    cannot express and a per-player band must recover. Zero-game busts are carried as a real 0, the
    NF1.4 population fix this inherits."""
    rng = np.random.default_rng(seed)
    rows = []
    for pos, lvl in (("QB", 250.0), ("RB", 190.0), ("WR", 200.0), ("TE", 120.0)):
        m = n // 4
        overall = rng.uniform(1, 255, m)
        truth = np.clip(lvl * (1.0 - overall / 270.0), 0, None)
        real = np.clip(truth + rng.normal(0, 1.0, m) * (0.55 * truth + 8.0), 0, None)
        real = np.where(rng.random(m) < 0.15, 0.0, real)       # the never-played share
        rows.append(pd.DataFrame({
            "gsis_id": [f"{pos}{i}" for i in range(m)],
            "player_name": [f"{pos} {i}" for i in range(m)],
            "position_group": pos, "nfl_position": pos,
            "draft_overall": overall, "draft_year": rng.integers(2016, 2025, m),
            "games": np.where(real > 0, 12.0, 0.0), "rookie_fp_ppr": real,
            "projected_nfl_z": rng.normal(0, 0.3, m),
            "projected_nfl_z_sd": rng.uniform(0.7, 1.1, m),
        }))
    out = pd.concat(rows, ignore_index=True)
    for c in sp._ROOKIE_RAW_STATS:
        out[c] = out["rookie_fp_ppr"] * 0.5
    # SHUFFLE: the frame is built in position BLOCKS, so an `iloc` slice would hand a test split a
    # position the training split barely contains — a position-disjoint fold, which is not the thing
    # any of these tests mean to measure (it silently drove one coverage assertion to 0.376).
    return out.sample(frac=1.0, random_state=seed).reset_index(drop=True)


@pytest.fixture(scope="module")
def population() -> pd.DataFrame:
    return _population()


@pytest.fixture(scope="module")
def pool() -> pd.DataFrame:
    """The real cached NF1.4 rookie pool where available; otherwise the synthetic population, so the
    fast gate never depends on an artifact that is gitignored."""
    if not _POOL.exists():
        return _population()
    p = pd.read_parquet(_POOL)
    p = p[pd.to_numeric(p["draft_overall"], errors="coerce").notna()].copy()
    for c in sp._ROOKIE_RAW_STATS:
        if c not in p.columns:
            p[c] = pd.to_numeric(p["rookie_fp_ppr"], errors="coerce") * 0.5
    return p


def _curves(frame: pd.DataFrame, **kw):
    """(point history, band history) → the three band tiers off one shared point curve."""
    band = frame.assign(games=lambda d: pd.to_numeric(d["games"] if "games" in d.columns
                                                      else d["rookie_games"], errors="coerce"))
    hist = band[band["games"] > 0].copy()
    return (sp.fit_rookie_slot_curves(hist),                                        # legacy cv
            sp.fit_rookie_slot_curves(hist, band_hist=band, per_player_band=False),  # NF1.4 tercile
            sp.fit_rookie_slot_curves(hist, band_hist=band, **kw))                   # NF1.7 per-player


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The POINT projection is untouched
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_per_player_band_does_NOT_move_the_point_projection(population):
    """⭐ THE REGRESSION GUARD FOR NF1.7'S CENTRAL PROMISE. The rookie point projection must be
    byte-identical across all three band tiers — NF1.4 proved the point is ~unbiased and its model
    bake-off returned a NULL, so an edit that let the band's fit reach the point curve would ship an
    unselected model with no gate behind it."""
    legacy, tercile, per_player = _curves(population)
    incoming = population.head(60)
    arms = [sp.project_rookies(incoming, c, 2026) for c in (legacy, tercile, per_player)]
    assert not arms[0].empty
    for col in ("proj_fp_ppr", "proj_games", *sp.RAW_STAT_COLS):
        if col not in arms[0].columns:
            continue
        base = arms[0][col].to_numpy(dtype=float)
        for other in arms[1:]:
            assert np.allclose(base, other[col].to_numpy(dtype=float), equal_nan=True), col


def test_rookie_point_projection_reproduces_the_SERVED_point_exactly(population):
    """The band is conditioned on `rookie_point_projection`, so if that ever drifts from what
    `project_rookies` actually emits, the band is centred on a number the board never shows — the
    class-level defect in a new disguise.

    ⚠️ THIS IS NOT HYPOTHETICAL: the first implementation re-derived the point as `slot curve × P1A
    nudge, clipped to the ceiling` and was wrong by up to 3.3 PPR, because the served point is that
    target MINUS the fumbles-lost term (`project_rookies` rescales the stat line to hit the target,
    then recomputes fumbles from the rescaled touches and re-scores). The cure was to DELEGATE.

    Scoped to ONE draft class, which is the invariant that actually holds and the only one that
    matters: the P1A residual nudge is a WITHIN-class regression, so `rookie_point_projection` groups
    by class while `project_rookies` fits over whatever frame it is handed. Production always hands it
    a single incoming class, so the two coincide exactly there — and over a MULTI-class frame they
    must NOT, because a cross-class nudge would be the wrong quantity."""
    curve, _, _ = _curves(population)
    yr = population["draft_year"].value_counts().idxmax()
    frame = population[population["draft_year"] == yr]
    got = sp.rookie_point_projection(frame, curve)
    served = sp.project_rookies(frame, curve, 2026)
    m = dict(zip(served["player_id"].astype(str),
                 pd.to_numeric(served["proj_fp_ppr"], errors="coerce")))
    expect = np.array([m.get(str(g), np.nan) for g in frame["gsis_id"].astype(str)])
    ok = np.isfinite(expect)
    assert ok.sum() > 50
    assert np.allclose(got[ok], expect[ok], atol=1e-9)


def test_a_band_history_without_gsis_id_still_fits(population):
    """A caller's band history need not carry ids (a unit-test fixture routinely does not), and the
    fit must not hard-require one: `rookie_point_projection` re-joins its OWN rows, so it assigns a
    synthetic key rather than trusting — or requiring — the caller's."""
    frame = population.drop(columns=["gsis_id"])
    curve, _, _ = _curves(frame)
    got = sp.rookie_point_projection(frame, curve)
    assert np.isfinite(got).sum() > 0.9 * len(frame)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The band is PER-PLAYER and COHERENT
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_band_is_per_player_not_class_level(pool):
    """The defect, inverted into an assertion. The class-level band quantises to ~3 intervals per
    position (a distinct-band fraction of ~0.18 on the real board); the per-player band must be
    essentially one interval per player."""
    frame = pool[pd.to_numeric(pool["draft_year"], errors="coerce") < 2026]
    incoming = pool[pd.to_numeric(pool["draft_year"], errors="coerce") == 2026]
    if incoming.empty:                      # synthetic fallback pool has no 2026 class
        frame, incoming = pool.iloc[:-80], pool.iloc[-80:]
    _, tercile, per_player = _curves(frame)

    def distinct_frac(curve):
        out = sp.project_rookies(incoming, curve, 2026)
        return len(set(zip(out["fp_ppr_p10"], out["fp_ppr_p90"]))) / len(out)

    assert distinct_frac(tercile) < 0.5, "the NF1.4 arm should be quantised — fixture drifted"
    assert distinct_frac(per_player) > 0.9


def test_the_band_brackets_its_own_point_and_is_non_negative(pool):
    """A displayed interval that excludes its own point estimate is incoherent, and a negative
    fantasy-season floor is not a thing. Enforced for EVERY form, not just the shipped one, so a
    future re-selection cannot land on a form that violates it."""
    frame = pool[pd.to_numeric(pool["draft_year"], errors="coerce") < 2026]
    incoming = pool[pd.to_numeric(pool["draft_year"], errors="coerce") == 2026]
    if incoming.empty:
        frame, incoming = pool.iloc[:-80], pool.iloc[-80:]
    for form in sp._ROOKIE_BAND_FORMS:
        _, _, curve = _curves(frame, band_form=form)
        out = sp.project_rookies(incoming, curve, 2026)
        assert (out["fp_ppr_p10"] >= 0).all(), form
        assert (out["fp_ppr_p10"] <= out["proj_fp_ppr"] + 1e-6).all(), form
        assert (out["fp_ppr_p90"] >= out["proj_fp_ppr"] - 1e-6).all(), form
        assert (out["fp_ppr_sd"] >= 0).all(), form


def test_the_band_width_tracks_the_players_own_projection(pool):
    """The band must carry per-player INFORMATION, not merely per-player NOISE: its width has to move
    with the player's own point projection. A class-level band is flat within a bucket by
    construction."""
    frame = pool[pd.to_numeric(pool["draft_year"], errors="coerce") < 2026]
    incoming = pool[pd.to_numeric(pool["draft_year"], errors="coerce") == 2026]
    if incoming.empty:
        frame, incoming = pool.iloc[:-80], pool.iloc[-80:]
    _, _, curve = _curves(frame)
    out = sp.project_rookies(incoming, curve, 2026)
    rho = (out["fp_ppr_p90"] - out["fp_ppr_p10"]).corr(out["proj_fp_ppr"], method="spearman")
    assert rho > 0.5, rho


def test_a_thin_band_history_degrades_to_the_class_level_band_not_to_a_fabrication(population):
    """A fit with too little history must fall BACK (to the NF1.4 tercile band, then to the legacy
    parameter width), never emit a per-player interval it cannot support."""
    tiny = population.head(12)
    band = tiny.assign(games=12.0)
    assert sp.fit_rookie_band_model(band, np.arange(len(band), dtype=float)) is None
    curve = sp.fit_rookie_slot_curves(band[band["games"] > 0], band_hist=band)
    assert curve.band_model is None
    out = sp.project_rookies(population.head(20), curve, 2026)
    assert set(out["uncertainty_type"]) <= {"calibrated", "parameter"}


def test_the_shipped_form_is_one_of_the_pre_registered_ones():
    """A shipped form outside the pre-registered set would be a config the bake-off never scored."""
    assert sp._ROOKIE_BAND_FORM in sp._ROOKIE_BAND_FORMS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⭐ SELECTION-METRIC HYGIENE — the interval score, pinned from BOTH ends
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _truth_band(rng, y_truth_sd, mu, n):
    z = 1.2815515594
    return np.clip(mu - z * y_truth_sd, 0, None), mu + z * y_truth_sd


def test_the_interval_score_cannot_be_won_by_a_ZERO_WIDTH_band():
    """⭐ THE ANCHOR THAT MAKES 'SELECT ON SHARPNESS' SAFE. A zero-width band is MAXIMALLY sharp, so
    a naive sharpness metric (mean width, or MAE on width) would crown it. Under the interval score it
    must LOSE to the correctly-specified band — that is what lets NF1.7 optimise sharpness without
    quietly buying it by under-covering."""
    rng = np.random.default_rng(3)
    mu = rng.uniform(20, 250, 4000)
    sd = 0.5 * mu + 10.0
    y = np.clip(mu + rng.normal(0, 1, 4000) * sd, 0, None)
    lo, hi = _truth_band(rng, sd, mu, 4000)
    assert interval_score(lo, hi, y).mean() < interval_score(mu, mu, y).mean()


def test_the_interval_score_cannot_be_won_by_an_ALL_ENCOMPASSING_band():
    """The mirror anchor: a band from 0 to the population maximum covers ~100% and says nothing. A
    coverage TARGET would love it. Under the interval score it must LOSE — which is the proof the
    selection is not a coverage exercise wearing a sharpness label."""
    rng = np.random.default_rng(4)
    mu = rng.uniform(20, 250, 4000)
    sd = 0.5 * mu + 10.0
    y = np.clip(mu + rng.normal(0, 1, 4000) * sd, 0, None)
    lo, hi = _truth_band(rng, sd, mu, 4000)
    wide_lo, wide_hi = np.zeros_like(mu), np.full_like(mu, y.max())
    assert np.mean((y >= wide_lo) & (y <= wide_hi)) > 0.99      # it really does over-cover
    assert interval_score(lo, hi, y).mean() < interval_score(wide_lo, wide_hi, y).mean()


def test_the_interval_score_prefers_a_PER_PLAYER_band_to_a_CLASS_LEVEL_one_at_equal_coverage():
    """⭐ THE MEASUREMENT THAT COVERAGE CANNOT MAKE, and the reason NF1.4 shipped the defect. Build a
    population whose conditional spread grows with the mean, then compare the correctly-specified
    per-player band against a CONSTANT band tuned to hit the SAME coverage. Coverage cannot tell them
    apart — the interval score must, decisively."""
    rng = np.random.default_rng(5)
    n = 8000
    mu = rng.uniform(10, 260, n)
    sd = 0.55 * mu + 8.0
    y = np.clip(mu + rng.normal(0, 1, n) * sd, 0, None)
    z = 1.2815515594
    p_lo, p_hi = np.clip(mu - z * sd, 0, None), mu + z * sd
    cov = float(np.mean((y >= p_lo) & (y <= p_hi)))
    # ONE constant band for everyone, set to the POOLED quantiles that reproduce the same coverage
    # by construction — the class-level band's logical limit.
    tail = (1.0 - cov) / 2.0
    c_lo = np.full(n, float(np.quantile(y, tail)))
    c_hi = np.full(n, float(np.quantile(y, 1.0 - tail)))
    assert abs(float(np.mean((y >= c_lo) & (y <= c_hi))) - cov) < 0.05, "coverage must be matched"
    assert interval_score(p_lo, p_hi, y).mean() < interval_score(c_lo, c_hi, y).mean()


def test_oracle_is_the_scoring_floor(population):
    """The CLAUDE.md floor pattern: a band fitted on the REALIZED outcomes it is scored against (it
    PEEKS) cannot be beaten by the same band fitted honestly. A candidate that beats its oracle is not
    a discovery — it is proof the metric is inverted.

    ⚠️ THE COMPARISON IS SAME-FAMILY **AND SAME-SAMPLE**, and two earlier cuts of this test show why
    neither qualifier is optional:
      * ONE peeking quantile-regression oracle for every family — the in-fold `knn_norm` legitimately
        BEAT it (215.5 vs 218.0). Not metric inversion: a peeking MISSPECIFIED model is beatable by an
        honest well-specified one. These conditional quantiles are not linear in log(point) (there is a
        15% point mass at zero), so the parametric oracle cannot represent them however hard it peeks.
      * per-family, but the oracle fitted on the 250-row test slice while candidates trained on 650 —
        the in-fold `knn_pos` beat its own oracle (214.9 vs 262.2), because a k-NN's CAPACITY depends
        on sample size: k=60 of 62 same-position rows is a constant band, k=60 of 650 is genuinely
        local. "Peeking can only help" holds at EQUAL resolution, not across sample sizes.
    So the orientation is tested the way that is well-posed at any sample size: fit the same family on
    the SAME rows, once against the TRUE outcomes and once against a PERMUTATION of them. Knowing the
    answer must score better than not knowing it. If a shuffled fit ever wins, the metric is inverted —
    which is the claim the oracle floor is really making."""
    frame = population.iloc[:-250]
    test = population.iloc[-250:]
    curve, _, _ = _curves(frame)
    pos = test["position_group"].astype(str).to_numpy()
    pred = sp.rookie_point_projection(test, curve)
    y = test["rookie_fp_ppr"].to_numpy(dtype=float)
    ok = np.isfinite(pred)
    pos, pred, y = pos[ok], pred[ok], y[ok]
    base = test[ok]
    shuffled = np.random.default_rng(19).permutation(y)

    def score(fit_frame, target):
        m = sp.fit_rookie_band_model(fit_frame.assign(rookie_fp_ppr=target), pred,
                                     form=form, k=40, qreg_alpha=0.01)
        if m is None:
            return None
        lo, hi = m.band_many(pos, pred, overall=base.get("draft_overall"),
                             resid_sd=base.get("projected_nfl_z_sd"))
        good = np.isfinite(lo) & np.isfinite(hi)
        if good.sum() < 50:
            return None
        return float(interval_score(lo[good], hi[good], y[good]).mean())

    checked = 0
    for form in sp._ROOKIE_BAND_FORMS:
        truth, noise = score(base, y), score(base, shuffled)
        if truth is None or noise is None:
            continue
        checked += 1
        assert truth < noise, (
            f"a {form} band fitted on SHUFFLED outcomes scored better than one fitted on the truth "
            f"({noise} < {truth}) — the interval score is inverted")
    assert checked >= 3, f"only {checked} families were actually checked"


def test_the_coverage_floor_is_held_on_a_known_population(population):
    """Coverage is a FLOOR, not a target — but a floor still has to be MET. The shipped form's
    realized coverage on a held-out slice of a population with a known spread must land at or above
    the nominal 80% (allowing sampling noise), or the sharpness win was bought dishonestly."""
    frame = population.iloc[:-250]
    test = population.iloc[-250:]
    _, _, curve = _curves(frame)
    out = sp.project_rookies(test, curve, 2026)
    real = dict(zip(test["gsis_id"].astype(str),
                    pd.to_numeric(test["rookie_fp_ppr"], errors="coerce")))
    y = np.array([real[str(p)] for p in out["player_id"]], dtype=float)
    cov = float(np.mean((y >= out["fp_ppr_p10"].to_numpy()) & (y <= out["fp_ppr_p90"].to_numpy())))
    assert cov >= 0.75, cov


def test_the_widener_is_widen_only(population):
    """`resid_sd_gain` is an HONEST-widening knob: it may only make a band wider on average, never
    sharpen one. A knob that could narrow a band would be a back door to buying sharpness."""
    frame = population.iloc[:-150]
    test = population.iloc[-150:]
    curve, _, _ = _curves(frame)
    pred = sp.rookie_point_projection(test, curve)
    train_pred = sp.rookie_point_projection(frame, curve)
    pos = test["position_group"].astype(str).to_numpy()
    widths = []
    for gain in (0.0, 0.2):
        m = sp.fit_rookie_band_model(frame, train_pred, form="qreg", qreg_alpha=0.01,
                                     resid_sd_gain=gain)
        lo, hi = m.band_many(pos, pred, overall=test.get("draft_overall"),
                             resid_sd=test.get("projected_nfl_z_sd"))
        widths.append(float(np.nanmean(hi - lo)))
    assert widths[1] >= widths[0]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The serving-path guards — the export audit and the league rescore
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _rec(name, point, lo, hi):
    return {"name": name, "fpPpr": point, "fpP10": lo, "fpP90": hi}


def test_the_audit_fires_on_a_class_level_band():
    """The exact 2026 shape: two rookie QBs sharing 26.5–277.0 against points of 268.3 and 58.1. The
    guard must call it out — this is NF1.7's acceptance signal, so it must be able to go RED."""
    recs = [_rec("Big QB", 268.3, 26.5, 277.0), _rec("Small QB", 58.1, 26.5, 277.0)]
    findings = audit_interval_quality(recs)
    assert any("CLASS-LEVEL" in f for f in findings)


def test_the_audit_does_NOT_fire_on_a_rounding_coincidence():
    """⚠️ THE FIX TO THE GUARD ITSELF. Its first cut fired on ANY band shared by two players, which
    made it permanently red for a non-defect: two deep-bench veterans whose p10 both floor at 0
    collide at the served 0.1 resolution. A guard that can never go green is a guard nobody reads."""
    recs = [_rec("Bench A", 21.0, 0.0, 43.5), _rec("Bench B", 22.4, 0.0, 43.5)]
    assert audit_interval_quality(recs) == []


def test_the_audit_threshold_separates_the_two_populations():
    """The tolerance is empirical, not chosen: on the real pre-NF1.7 board the class-level groups sat
    at a point-spread/width ratio of 0.68–0.84 and every veteran rounding coincidence at ≤0.196. The
    threshold must sit strictly inside that gap, or it is just a number someone liked."""
    assert 0.196 < _SHARED_BAND_POINT_SPREAD_TOL < 0.68


def test_the_audit_still_catches_an_incoherent_band():
    """The other half of the guard must not have been weakened by the shared-band rework."""
    findings = audit_interval_quality([_rec("Outside", 300.0, 10.0, 200.0)])
    assert any("OUTSIDE" in f for f in findings)
    findings = audit_interval_quality([_rec("Pinned", 195.0, 10.0, 200.0)])
    assert any("extreme" in f for f in findings)


def test_an_asymmetric_band_survives_the_league_rescore():
    """⭐ The league scorer used to rebuild the interval from a single `sd`, which forces it SYMMETRIC.
    That is fine for a veteran and wrong for a rookie, whose band is heavily right-skewed — it would
    hand the app back the very incoherence NF1.7 removed upstream, in a league format instead of the
    base one."""
    from quant_sports_intel_models.fantasy_engine.scoring import score_players
    from quant_sports_intel_models.football.nfl.fantasy.league_presets import (
        NFL_PROFILE,
        get_preset,
    )

    df = pd.DataFrame([{
        "player_id": "R1", "position": "RB", "proj_fp_ppr": 208.4, "fp_ppr_sd": 129.4,
        "fp_ppr_p10": 14.6, "fp_ppr_p90": 346.3,
        "proj_rush_att": 200.0, "proj_rush_yds": 900.0, "proj_rush_td": 6.0,
        "proj_targets": 60.0, "proj_rec": 45.0, "proj_rec_yds": 380.0, "proj_rec_td": 2.0,
        "proj_pass_att": 0.0, "proj_pass_cmp": 0.0, "proj_pass_yds": 0.0, "proj_pass_td": 0.0,
        "proj_pass_int": 0.0, "proj_fumbles_lost": 1.5, "proj_two_pt": np.nan,
    }])
    cfg = get_preset("full_ppr", 12)
    out = score_players(df, cfg, NFL_PROFILE)
    pts = float(out["league_points"].iloc[0])
    lo, hi = float(out["league_points_p10"].iloc[0]), float(out["league_points_p90"].iloc[0])
    assert lo <= pts <= hi
    # the upstream band is skewed DOWNWARD — the point sits ~58% of the way UP from p10, so the lower
    # arm is the long one. The rescored band must keep that shape rather than re-centring on the point
    # (a `±z·sd` rebuild would split the width evenly and slide the interval).
    up, down = hi - pts, pts - lo
    assert down > 1.3 * up, (lo, pts, hi)
    assert abs((lo / pts) - (14.6 / 208.4)) < 0.02
    assert abs((hi / pts) - (346.3 / 208.4)) < 0.02


def test_a_projection_without_published_bounds_still_gets_the_symmetric_fallback():
    """Back-compat: the CV path must still produce an interval for a frame carrying only `sd`."""
    from quant_sports_intel_models.fantasy_engine.scoring import score_players
    from quant_sports_intel_models.football.nfl.fantasy.league_presets import (
        NFL_PROFILE,
        get_preset,
    )

    df = pd.DataFrame([{
        "player_id": "V1", "position": "WR", "proj_fp_ppr": 200.0, "fp_ppr_sd": 40.0,
        "proj_targets": 120.0, "proj_rec": 80.0, "proj_rec_yds": 1000.0, "proj_rec_td": 6.0,
        "proj_rush_att": 0.0, "proj_rush_yds": 0.0, "proj_rush_td": 0.0, "proj_pass_att": 0.0,
        "proj_pass_cmp": 0.0, "proj_pass_yds": 0.0, "proj_pass_td": 0.0, "proj_pass_int": 0.0,
        "proj_fumbles_lost": 0.5, "proj_two_pt": np.nan,
    }])
    out = score_players(df, get_preset("full_ppr", 12), NFL_PROFILE)
    pts = float(out["league_points"].iloc[0])
    lo, hi = float(out["league_points_p10"].iloc[0]), float(out["league_points_p90"].iloc[0])
    assert 0 < lo < pts < hi
    assert abs((hi - pts) - (pts - lo)) < 0.3          # symmetric, as the CV path implies


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The plumbing that fails SILENTLY if removed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_rookie_band_history_carries_the_P1A_columns():
    """🚨 SOURCE-INSPECTION GUARD (the fast gate cannot open DuckDB). `load_rookie_training` must keep
    selecting `projected_nfl_z` and `projected_nfl_z_sd`, because losing them degrades the band with
    NO error: without `projected_nfl_z` the conditioning point loses its P1A nudge and stops matching
    the served point; without `projected_nfl_z_sd` the `z_sd` column of the shipped quantile
    regression is a constant zero at fit time, so its coefficient fits to ~0 and the driver is
    silently discarded while the live rows carry a real sd."""
    src = (_REPO / "quant_sports_intel_models/football/nfl/fantasy/run_season_projection.py").read_text()
    fn = src[src.index("def load_rookie_training"):src.index("def load_realized_season")]
    for col in ("projected_nfl_z", "projected_nfl_z_sd"):
        assert len(re.findall(col, fn)) >= 2, f"{col} dropped from the rookie band history"


def test_the_shipped_selection_matches_the_ablation_report():
    """The shipped constants must be the ones the bake-off report actually selected — a drifted
    default is an unselected model in production with a report that says otherwise."""
    rpt = (_REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
           / "nf1_7_rookie_intervals.md")
    if not rpt.exists():
        pytest.skip("ablation report not generated in this checkout")
    text = rpt.read_text()
    m = re.search(r"\*\*SHIPPED: `([^`]+)`\*\*", text)
    assert m, "the report does not name a shipped config"
    label = m.group(1)
    assert sp._ROOKIE_BAND_FORM in label, (label, sp._ROOKIE_BAND_FORM)
    assert f"sdgain {sp._ROOKIE_BAND_RESID_SD_GAIN:g}" in label, label
