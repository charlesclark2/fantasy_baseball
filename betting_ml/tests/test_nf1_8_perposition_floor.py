"""NF1.8 — guards for the rookie 80% band's PER-POSITION coverage FLOOR.

WHAT THIS PROTECTS. NF1.7 selected the rookie band on a proper interval score with a POOLED coverage
floor. Pooled cleared 0.80, but coverage REDISTRIBUTED: QB 0.741, RB 0.777, TE 0.870, WR 0.826. Pooled
coverage is a POPULATION property that one position can pay for on another's behalf — the same class of
blind spot as NF1.4's "coverage cannot select an interval", one level up. NF1.8 re-selects under a
per-position floor, still selecting on the interval score.

The tests below pin the five things that would silently undo it:
  1. **The floor must be computed from POOLED ROWS.** A mean of per-class means silently DROPS a
     position that is thin in a class, so the floor would protect a different population than the one
     it names.
  2. **The floor must be a CONSTRAINT, not the selector.** `max_width` satisfies every per-position
     floor. If the floor ever becomes something to maximise, the degenerate wins — the E2.1-r
     inversion facing the other way.
  3. **The MONDRIAN (per-position) conformal layer must actually be per-position** — and must degrade
     LOUDLY (a recorded pooled fallback) when a group is too thin, never silently.
  4. **The four NF1.7 anchor-set guards must stay live** — a missing anchor RAISES, the oracle is a
     PERMUTATION, BOTH degenerates lose, the widener is monotone.
  5. **The POINT projection must not move** — across every band configuration, including the two new
     mechanisms. NF1.4 established the rookie point is ~unbiased; a band knob that shifts it would ship
     an unselected model.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_interval_ablation import interval_score
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_perposition_ablation import (
    _NF17_WINNER_LABEL,
    _NOMINAL,
    _POS_FLOOR_MIN_N,
    _TIER2_POSITIONS,
    deflate,
    floor_misses,
    floor_slack_rows,
    position_floors,
    position_power,
    require_anchors,
    score_rows,
)

_REPO = Path(__file__).resolve().parents[2]
_REPORT = (_REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
           / "nf1_8_rookie_perposition_floor.md")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _population(n: int = 720, seed: int = 11) -> pd.DataFrame:
    """A drafted-rookie population whose conditional spread grows with the slot-implied level, and in
    which QB is BOTH the thinnest position AND the one with the fattest right tail — the structure that
    makes a pooled floor hide a per-position miss (the real rookie-QB shape: ~10 a class, ~35% never
    take a snap)."""
    rng = np.random.default_rng(seed)
    rows = []
    for pos, lvl, share, zero_rate, tail in (("QB", 250.0, 0.12, 0.35, 1.05),
                                             ("RB", 190.0, 0.24, 0.15, 0.55),
                                             ("WR", 200.0, 0.40, 0.15, 0.55),
                                             ("TE", 120.0, 0.24, 0.18, 0.60)):
        m = max(60, int(n * share))
        overall = rng.uniform(1, 255, m)
        truth = np.clip(lvl * (1.0 - overall / 270.0), 0, None)
        real = np.clip(truth + rng.normal(0, 1.0, m) * (tail * truth + 8.0), 0, None)
        real = np.where(rng.random(m) < zero_rate, 0.0, real)
        rows.append(pd.DataFrame({
            "gsis_id": [f"{pos}{i}" for i in range(m)],
            "player_name": [f"{pos} {i}" for i in range(m)],
            "position_group": pos, "nfl_position": pos,
            "draft_overall": overall, "draft_year": rng.integers(2016, 2026, m),
            "games": np.where(real > 0, 12.0, 0.0), "rookie_fp_ppr": real,
            "projected_nfl_z": rng.normal(0, 0.3, m),
            "projected_nfl_z_sd": rng.uniform(0.7, 1.1, m),
        }))
    out = pd.concat(rows, ignore_index=True)
    for c in sp._ROOKIE_RAW_STATS:
        out[c] = out["rookie_fp_ppr"] * 0.5
    return out.sample(frac=1.0, random_state=seed).reset_index(drop=True)


@pytest.fixture(scope="module")
def population() -> pd.DataFrame:
    return _population()


@pytest.fixture(scope="module")
def fitted(population):
    """(train frame, test frame, point curve, served train point, served test point)."""
    frame, test = population.iloc[:-220], population.iloc[-220:]
    band = frame.assign(games=pd.to_numeric(frame["games"], errors="coerce"))
    curve = sp.fit_rookie_slot_curves(band[band["games"] > 0].copy())
    return (band, test, curve,
            sp.rookie_point_projection(band, curve), sp.rookie_point_projection(test, curve))


def _rows(pos, lo, hi, y, point, year=2025, fell=False) -> pd.DataFrame:
    n = len(np.atleast_1d(y))
    return pd.DataFrame({"year": year, "pos": pos, "lo": lo, "hi": hi, "y": y, "point": point,
                         "fell_back": np.full(n, bool(fell))})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The floor is computed from POOLED ROWS, not a mean of per-class means
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_per_position_coverage_is_pooled_over_rows_not_a_mean_of_class_means():
    """⚠️ THE CONVENTION IS LOAD-BEARING. NF1.7 averaged each metric over held-out CLASSES and required
    ≥3 rows for a position to enter a class's mean. A position thin in one class was therefore DROPPED
    from that class's contribution, so a floor computed that way is evaluated on a quietly different
    population than the one it claims to protect — and the direction of the error is unknowable.

    Here QB appears in two classes: 20 rows at 0.50 coverage, and 2 rows at 1.00. The pooled truth is
    12/22 = 0.545. NF1.7's convention would either drop the 2-row class (0.50) or weight it equally
    with the 20-row one (0.75). Only the pooled number is the coverage of the population the floor
    names."""
    big = _rows(["QB"] * 20, np.zeros(20), np.full(20, 100.0),
                np.r_[np.full(10, 50.0), np.full(10, 500.0)], np.full(20, 50.0), year=2024)
    tiny = _rows(["QB"] * 2, np.zeros(2), np.full(2, 100.0), np.full(2, 50.0),
                 np.full(2, 50.0), year=2025)
    got = score_rows(pd.concat([big, tiny], ignore_index=True))
    assert got["n_QB"] == 22
    assert got["cov_QB"] == pytest.approx(12 / 22, abs=1e-4), "coverage must be pooled over ROWS"
    # the two alternatives the pooled reading must NOT equal
    assert got["cov_QB"] != pytest.approx(0.50, abs=1e-3)     # thin class dropped
    assert got["cov_QB"] != pytest.approx(0.75, abs=1e-3)     # thin class weighted as a whole class


def test_an_arm_can_clear_the_POOLED_floor_while_failing_a_PER_POSITION_floor():
    """The exact NF1.7 shape, and the reason NF1.8 exists: pooled coverage is a property one position
    can pay for on another's behalf. 100 WR at 0.86 and 20 QB at 0.60 pool to 0.817 — above the floor —
    while QB is 20 points short."""
    def band(pos, n, cov):
        y = np.where(np.arange(n) < round(cov * n), 50.0, 500.0)
        return _rows([pos] * n, np.zeros(n), np.full(n, 100.0), y, np.full(n, 50.0))
    rec = score_rows(pd.concat([band("WR", 100, 0.86), band("QB", 20, 0.60)], ignore_index=True))
    assert rec["coverage_80"] >= _NOMINAL, "the POOLED floor is cleared"
    floors = {"WR": _NOMINAL, "QB": _NOMINAL}
    misses = floor_misses(rec, floors)
    assert any(m.startswith("QB") for m in misses), misses
    assert not any(m.startswith("pooled") for m in misses)


def test_a_position_too_thin_to_constrain_is_left_UNCONSTRAINED_rather_than_waved_through():
    """A floor on a dozen rows is noise. `position_floors` must simply not emit one — and the report
    must therefore say the position is unconstrained rather than quietly claiming it passed."""
    rec = {"n_QB": _POS_FLOOR_MIN_N - 1, "n_WR": _POS_FLOOR_MIN_N + 50,
           "cov_QB": 0.10, "cov_WR": 0.85}
    floors = position_floors(rec, ["QB", "WR"], tier=1)
    assert "QB" not in floors and floors["WR"] == _NOMINAL
    assert floor_misses(rec, floors) == [] or all("QB" not in m for m in floor_misses(rec, floors))


def test_the_tier2_fallback_relaxes_ONLY_the_thin_positions_and_ONLY_by_the_power_derived_amount():
    """Tier 2 must be derived from SAMPLE SIZE ALONE — a design quantity known before any result — or
    it is a floor reverse-engineered from the answer we wanted. And it must relax only the positions
    pre-registered as structurally thin; every other position keeps the hard nominal floor."""
    rec = {"n_QB": 81, "n_WR": 224, "cov_QB": 0.75, "cov_WR": 0.79}
    t1, t2 = (position_floors(rec, ["QB", "WR"], tier=t) for t in (1, 2))
    assert t1 == {"QB": _NOMINAL, "WR": _NOMINAL}
    assert "QB" in _TIER2_POSITIONS
    assert t2["WR"] == _NOMINAL, "a well-powered position is never relaxed"
    assert 0.70 < t2["QB"] < _NOMINAL, t2
    # exactly nominal − 1.645·SE(n): a function of n only, so it cannot chase the observed number
    assert t2["QB"] == pytest.approx(_NOMINAL - 1.6448536269514722 * np.sqrt(_NOMINAL * 0.2 / 81),
                                     abs=1e-4)


def test_floor_slack_reports_the_margin_in_ROOKIE_SEASONS():
    """⭐ A coverage decimal hides how few outcomes a per-position floor rests on. QB's 0.815 on 81 rows
    clears a 0.80 floor by ONE covered rookie-season; the report must be able to say that in rows,
    because 'QB now covers 0.815' reads like a stable property and is not one."""
    rec = {"cov_QB": 66 / 81, "n_QB": 81, "cov_WR": 0.90, "n_WR": 200}
    slack = floor_slack_rows(rec, {"QB": _NOMINAL, "WR": _NOMINAL})
    assert slack["QB"] == 1, slack          # 66 covered vs 64.8 needed
    assert slack["WR"] == 20, slack         # 180 covered vs 160 needed
    below = floor_slack_rows({"cov_QB": 0.74, "n_QB": 81}, {"QB": _NOMINAL})
    assert below["QB"] < 0, "a miss must read as NEGATIVE slack, not clamp to zero"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⭐ The floor is a CONSTRAINT, never the selector
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_max_width_degenerate_SATISFIES_every_per_position_floor_and_still_LOSES():
    """⭐ THE PROOF THE PER-POSITION FLOOR DID NOT TURN THIS INTO A COVERAGE EXERCISE. An
    all-encompassing band clears any coverage floor at every position and is useless. That is FINE for
    a constraint — the interval score then eliminates it. It would be fatal for a TARGET. This test is
    what stops a future session from 'improving' the gate by maximising per-position coverage, or from
    tightening the floor above nominal 'for safety' (every notch above nominal moves the eligible set
    toward this degenerate)."""
    rng = np.random.default_rng(21)
    n = 1200
    pos = rng.choice(["QB", "RB", "WR", "TE"], n)
    mu = rng.uniform(10, 260, n)
    sd = 0.55 * mu + 8.0
    y = np.clip(mu + rng.normal(0, 1, n) * sd, 0, None)
    z = 1.2815515594
    honest = _rows(pos, np.clip(mu - z * sd, 0, None), mu + z * sd, y, mu)
    degen = _rows(pos, np.zeros(n), np.full(n, y.max()), y, mu)
    h, d = score_rows(honest), score_rows(degen)
    floors = {p: _NOMINAL for p in ("QB", "RB", "WR", "TE")}
    assert floor_misses(d, floors) == [], "max_width must SATISFY every per-position floor"
    assert d["interval_score"] > h["interval_score"], "…and must still LOSE on the primary metric"


def test_the_zero_width_degenerate_fails_the_floor_AND_loses():
    """The other side: maximally sharp, so a naive sharpness metric would crown it. It must lose on the
    metric AND be excluded by the floor — both guards firing, so neither is load-bearing alone."""
    rng = np.random.default_rng(22)
    n = 800
    pos = rng.choice(["QB", "WR"], n)
    mu = rng.uniform(10, 260, n)
    sd = 0.55 * mu + 8.0
    y = np.clip(mu + rng.normal(0, 1, n) * sd, 0, None)
    z = 1.2815515594
    h = score_rows(_rows(pos, np.clip(mu - z * sd, 0, None), mu + z * sd, y, mu))
    d = score_rows(_rows(pos, mu, mu, y, mu))
    floors = {"QB": _NOMINAL, "WR": _NOMINAL}
    assert floor_misses(d, floors), "zero_width must fail the floor"
    assert d["interval_score"] > h["interval_score"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The MONDRIAN (per-position) conformal layer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_mondrian_conformal_layer_is_actually_PER_POSITION(fitted):
    """The mechanism NF1.8 added must condition on the position, or it is the pooled foil with a
    different name. Two things are asserted: the fitted adjustments differ ACROSS positions, and the
    pooled variant applies ONE number to everybody."""
    band, test, _, train_pred, test_pred = fitted
    m = sp.fit_rookie_band_model(band, train_pred, form="qreg_sqrt", qreg_alpha=0.01,
                                 cqr_mode="pos", cqr_scale="add")
    groups = {k: v for k, v in m.conformal.items() if k != sp._CQR_POOL_KEY}
    assert len(groups) >= 3, m.conformal
    assert len({round(v, 6) for v in groups.values()}) > 1, (
        "every position received the SAME adjustment — the layer is not per-position", groups)
    pooled = sp.fit_rookie_band_model(band, train_pred, form="qreg_sqrt", qreg_alpha=0.01,
                                      cqr_mode="pool", cqr_scale="add")
    pos = test["position_group"].astype(str).str.upper().to_numpy()
    kw = dict(overall=test.get("draft_overall"), resid_sd=test.get("projected_nfl_z_sd"))
    lo_m, hi_m = m.band_many(pos, test_pred, **kw)
    lo_p, hi_p = pooled.band_many(pos, test_pred, **kw)
    # the widths must differ between the two modes for at least one position
    assert not np.allclose(np.nan_to_num(hi_m - lo_m), np.nan_to_num(hi_p - lo_p)), (
        "the pooled and per-position calibrations produced identical bands — the foil is not a foil")


def test_the_conformal_adjustment_is_a_per_GROUP_SCALAR_so_it_cannot_narrow_a_chosen_player(fitted):
    """⭐ WHY THE CONFORMAL LAYER IS NOT A BACK DOOR AROUND THE WIDEN-ONLY RULE. CQR's adjustment may be
    NEGATIVE when the base band over-covers on calibration — that is the method working, not a cheat —
    but it is a SINGLE SCALAR PER GROUP, so it moves every member of a position together and cannot buy
    sharpness by narrowing the players who most need width. Asserted structurally: within a position,
    every band's UPPER bound moves by the same amount.

    ⚠️ THIS TEST'S FIRST CUT WAS VACUOUS, AND THE WAY IT FAILED IS THE STORY'S OWN LESSON-1 IN
    MINIATURE. It compared the change in WIDTH on rows with `lo > 0` — but on a drafted-rookie
    population the q10 is floored at 0 for essentially everybody (15–35% never play), so the filter
    selected ZERO rows and the assertion ran on nothing. A deliberate per-player mutation of the
    adjustment passed it. The fixes: measure the HI side (never floored), and ASSERT THE CHECK WAS NOT
    VACUOUS — at least one group carrying a genuinely non-zero adjustment must have been examined. A
    check that can only be satisfied by running on nothing is not a check."""
    band, test, _, train_pred, test_pred = fitted
    pos = test["position_group"].astype(str).str.upper().to_numpy()
    kw = dict(overall=test.get("draft_overall"), resid_sd=test.get("projected_nfl_z_sd"))
    base = sp.fit_rookie_band_model(band, train_pred, form="qreg_sqrt", qreg_alpha=0.01)
    conf = sp.fit_rookie_band_model(band, train_pred, form="qreg_sqrt", qreg_alpha=0.01,
                                    cqr_mode="pos", cqr_scale="add")
    lo0, hi0 = base.band_many(pos, test_pred, **kw)
    lo1, hi1 = conf.band_many(pos, test_pred, **kw)
    checked_nonzero = 0
    for p in np.unique(pos):
        adj = float(conf.conformal.get(p, conf.conformal.get(sp._CQR_POOL_KEY, 0.0)))
        # the UPPER bound: `hi = max(hi, point)` only binds when the fit put hi BELOW the point, which
        # a q90 essentially never does — unlike `lo`, which is floored at 0 for most rookies.
        sel = (pos == p) & np.isfinite(hi1) & np.isfinite(hi0) & (hi1 > test_pred + 1e-6)
        if sel.sum() < 5:
            continue
        d = (hi1 - hi0)[sel]
        assert np.ptp(d) < 1e-6, (
            f"{p}: the upper bound moved by a DIFFERENT amount per player (spread {np.ptp(d):.4g}) — "
            "the conformal adjustment is not a per-group scalar")
        assert d[0] == pytest.approx(adj, abs=1e-6), (p, d[0], adj)
        checked_nonzero += int(abs(adj) > 1e-9)
        # …and the LOWER bound moves by the same scalar wherever the 0 floor does not bind
        free = sel & (lo1 > 1e-6) & (lo0 > 1e-6)
        if free.sum() >= 5:
            assert np.ptp((lo0 - lo1)[free]) < 1e-6, f"{p}: lower bound is not a group scalar"
    assert checked_nonzero >= 1, (
        "no group with a NON-ZERO conformal adjustment was examined — the assertions above ran on "
        "rows the layer never touched, so this test would pass on a broken implementation "
        f"(fitted adjustments: {conf.conformal})")


def test_BOTH_bounds_move_by_the_group_scalar_and_nothing_else():
    """The companion to the test above, and the reason it exists: on a real drafted-rookie population
    the q10 is floored at 0 for nearly everybody, so the LOWER bound's behaviour is unobservable there
    — a deliberate per-player tilt of `lo` passed the population-based test. So the invariant is pinned
    on a CONSTRUCTED model where neither the 0 floor nor the bracket-the-point clip can bind: a wide
    band well above zero, one group with a positive adjustment and one with a negative one.

    Both directions matter. A NEGATIVE adjustment (the base band over-covering on calibration) is
    legitimate CQR, and it must sharpen the WHOLE group by the same amount — never selected members."""
    m = sp.RookieBandModel(form="qreg", cqr_mode="pos", cqr_scale="add",
                           qreg_positions=("QB", "WR"),
                           qreg_lo={"log_pred": 0.0, "log_overall": 0.0, "z_sd": 0.0,
                                    "pos_WR": 0.0, "intercept": 400.0},
                           qreg_hi={"log_pred": 0.0, "log_overall": 0.0, "z_sd": 0.0,
                                    "pos_WR": 0.0, "intercept": 900.0},
                           conformal={"QB": 25.0, "WR": -10.0, sp._CQR_POOL_KEY: 5.0})
    pos = np.array(["QB"] * 6 + ["WR"] * 6 + ["TE"] * 6, dtype=object)
    pred = np.linspace(500.0, 800.0, 18)                # inside [400, 900] ⇒ no clip binds
    plain = sp.RookieBandModel(form="qreg", qreg_positions=m.qreg_positions,
                               qreg_lo=dict(m.qreg_lo), qreg_hi=dict(m.qreg_hi))
    lo0, hi0 = plain.band_many(pos, pred)
    lo1, hi1 = m.band_many(pos, pred)
    assert np.allclose(lo0, 400.0) and np.allclose(hi0, 900.0), (lo0, hi0)
    for p, want in (("QB", 25.0), ("WR", -10.0), ("TE", 5.0)):   # TE unseen ⇒ the pooled fallback
        s = pos == p
        assert np.allclose(hi1[s] - hi0[s], want), (p, hi1[s] - hi0[s])
        assert np.allclose(lo0[s] - lo1[s], want), (p, lo0[s] - lo1[s])
        assert np.ptp(hi1[s]) == 0.0 and np.ptp(lo1[s]) == 0.0, f"{p}: not a group scalar"
    # `pool` mode must apply ONE number to everybody, ignoring the per-group entries it also stores
    pooled = sp.RookieBandModel(form="qreg", cqr_mode="pool", cqr_scale="add",
                                qreg_positions=m.qreg_positions, qreg_lo=dict(m.qreg_lo),
                                qreg_hi=dict(m.qreg_hi), conformal=dict(m.conformal))
    _, hi_p = pooled.band_many(pos, pred)
    assert np.allclose(hi_p - hi0, 5.0), hi_p - hi0
    # `width` scaling is a per-group MULTIPLIER on the width, so it too cannot reorder widths
    wide = sp.RookieBandModel(form="qreg", cqr_mode="pos", cqr_scale="width",
                              qreg_positions=m.qreg_positions, qreg_lo=dict(m.qreg_lo),
                              qreg_hi=dict(m.qreg_hi), conformal={"QB": 0.5, sp._CQR_POOL_KEY: 0.0})
    lo_w, hi_w = wide.band_many(pos, pred)
    qb = pos == "QB"
    assert np.allclose((hi_w - lo_w)[qb], 500.0 * 2.0), (hi_w - lo_w)[qb]   # w·(1 + 2·0.5)
    assert np.allclose((hi_w - lo_w)[~qb], 500.0)


def test_a_calibration_group_too_thin_for_its_own_quantile_falls_back_to_POOLED_and_is_RECORDED():
    """⚠️ THE NF1.7 LESSON-1 SHAPE, one layer down: a group that quietly borrows the pooled quantile
    would be a per-position claim the fit never made. The fallback is legitimate — a 4-row quantile is
    noise — but it must be RECORDED so a reader can tell which positions actually carry their own
    calibration."""
    pop = _population(seed=31)
    thin = pd.concat([pop[pop.position_group != "TE"],
                      pop[pop.position_group == "TE"].head(6)], ignore_index=True)
    band = thin.assign(games=pd.to_numeric(thin["games"], errors="coerce"))
    curve = sp.fit_rookie_slot_curves(band[band["games"] > 0].copy())
    m = sp.fit_rookie_band_model(band, sp.rookie_point_projection(band, curve), form="qreg",
                                 qreg_alpha=0.01, cqr_mode="pos", cqr_scale="add")
    assert "TE" in m.cqr_pooled_groups, (m.cqr_pooled_groups, m.cqr_n_calib)
    assert "TE" not in m.conformal, "a thin group must NOT carry its own quantile"
    assert sp._CQR_POOL_KEY in m.conformal, "…but the pooled fallback must exist to fall back TO"
    assert m.cqr_n_calib.get("TE", 0) < sp._ROOKIE_BAND_CQR_MIN_CALIB


def test_the_conformal_level_is_the_FINITE_SAMPLE_split_conformal_quantile(fitted):
    """The (1−α) level must be ⌈(1−α)(n+1)⌉/n, not a plain empirical quantile: that correction is the
    whole reason split conformal carries a finite-sample coverage guarantee at the group's own n. Read
    off the source, because the level is computed inside the fit and never returned.

    ⚠️ NF1.9 factored the level into the SHARED `_conformity_quantile` kernel (the rookie and veteran
    band models must not carry two copies of it — a plain `np.quantile(v, 1−α)` in either would silently
    drop the guarantee). So this now checks BOTH halves: the kernel computes the finite-sample level, and
    the rookie fit DELEGATES to it rather than rolling its own."""
    src = Path(sp.__file__).read_text()
    kern = src[src.index("def _conformity_quantile"):src.index("def _interval_score")]
    assert "np.ceil((1.0 - alpha) * (nn + 1.0)) / nn" in kern, (
        "the conformal level is not the finite-sample split-conformal quantile")
    fn = src[src.index("def _fit_conformal_into"):src.index("def fit_rookie_band_model")]
    assert "_conformity_quantile(vals, alpha)" in fn, (
        "the rookie conformal fit must DELEGATE to the shared finite-sample kernel, not re-implement it")
    assert "np.quantile" not in fn, "a raw np.quantile here would bypass the finite-sample correction"
    assert "alpha = 1.0 - (m.hi_q - m.lo_q)" in src, "α must be derived from the band's own quantiles"
    # and the numeric behaviour is unchanged by the refactor: the level must exceed the plain quantile
    vals = list(range(100))
    assert sp._conformity_quantile(vals, 0.20) >= float(np.quantile(vals, 0.80))


def test_unknown_conformal_settings_raise_rather_than_silently_doing_nothing():
    """A typo'd `cqr_mode` that silently emitted an un-conformalized band would ship an arm the bake-off
    never scored, with a label claiming otherwise."""
    pop = _population(seed=41).head(200)
    band = pop.assign(games=pd.to_numeric(pop["games"], errors="coerce"))
    with pytest.raises(ValueError):
        sp.fit_rookie_band_model(band, np.full(len(band), 80.0), form="qreg", cqr_mode="per_position")
    with pytest.raises(ValueError):
        sp.fit_rookie_band_model(band, np.full(len(band), 80.0), form="qreg", cqr_scale="multiply")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The four NF1.7 anchor-set guards, carried
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_missing_anchor_RAISES_rather_than_passing_vacuously():
    """⭐ ANCHOR GUARD 1. `best >= anchor` on an ABSENT anchor is not evaluated at all — the check passes
    on nothing. NF1.7's first harness shipped exactly that (both oracles silently returned None because
    the production fitter refuses a per-position fit under 40 rows). Every required anchor must be
    present or the run dies."""
    full = {k: 200.0 for k in
            ("oracle_knn", "oracle_qreg", "zero_width", "max_width", "const_width",
             "permuted_own", "permuted_knn_norm")}
    require_anchors(full)                                     # complete → no raise
    for drop in list(full):
        with pytest.raises(SystemExit, match=drop):
            require_anchors({k: v for k, v in full.items() if k != drop})


def test_the_permutation_oracle_LOSES_to_the_same_arm_fitted_on_the_truth(fitted):
    """⭐ ANCHOR GUARD 2. The oracle is a PERMUTATION, not a peeking fit: family, hyper-parameters and
    sample size are held exactly equal and only the information content moves, which makes the
    comparison well-posed at ANY n. (NF1.7 learned this twice — a cross-family peeking oracle was
    legitimately beaten by an honest well-specified arm, and a peeking k-NN fitted on ~80 test rows was
    beaten because a k-NN's capacity depends on n.) Run over EVERY pre-registered form, including
    NF1.8's two new mechanisms: if a shuffled fit ever wins, the metric is inverted."""
    band, test, _, train_pred, test_pred = fitted
    pos = test["position_group"].astype(str).str.upper().to_numpy()
    y = pd.to_numeric(test["rookie_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    shuffled = band.assign(rookie_fp_ppr=np.random.default_rng(7).permutation(
        pd.to_numeric(band["rookie_fp_ppr"], errors="coerce").to_numpy(dtype=float)))
    kw = dict(overall=test.get("draft_overall"), resid_sd=test.get("projected_nfl_z_sd"))

    def score(frame, **fit_kw):
        m = sp.fit_rookie_band_model(frame, train_pred, k=40, qreg_alpha=0.01, **fit_kw)
        if m is None:
            return None
        lo, hi = m.band_many(pos, test_pred, **kw)
        ok = np.isfinite(lo) & np.isfinite(hi)
        return float(interval_score(lo[ok], hi[ok], y[ok]).mean()) if ok.sum() > 50 else None

    checked = 0
    variants = [{"form": f} for f in sp._ROOKIE_BAND_FORMS] + [
        {"form": "qreg_sqrt", "qreg_per_pos": True},
        {"form": "qreg_sqrt", "cqr_mode": "pos", "cqr_scale": "add"},
        {"form": "qreg_sqrt", "cqr_mode": "pos", "cqr_scale": "width"},
        {"form": "qreg", "cqr_mode": "pool", "cqr_scale": "add"},
    ]
    for v in variants:
        truth, noise = score(band, **v), score(shuffled, **v)
        if truth is None or noise is None:
            continue
        checked += 1
        assert truth < noise, (
            f"{v}: a band fitted on SHUFFLED outcomes scored better than one fitted on the truth "
            f"({noise:.2f} < {truth:.2f}) — the interval score is inverted")
    assert checked >= 6, f"only {checked} variants were actually checked"


def test_the_widener_is_still_widen_only_on_the_new_forms(fitted):
    """⭐ ANCHOR GUARD 4. `resid_sd_gain` clamps its z to max(z, 0) so it can only WIDEN — a two-sided
    version sharpened half the field off a parameter-uncertainty z and cost NF1.7 coverage 0.808 →
    0.773. Re-asserted on the NF1.8 forms, and on the source, because the clamp is one `np.clip` away
    from silently disappearing."""
    band, test, _, train_pred, test_pred = fitted
    pos = test["position_group"].astype(str).str.upper().to_numpy()
    kw = dict(overall=test.get("draft_overall"), resid_sd=test.get("projected_nfl_z_sd"))
    for fit_kw in ({"form": "qreg_sqrt", "cqr_mode": "pos"}, {"form": "qreg_sqrt"}):
        widths = []
        for gain in (0.0, 0.2):
            m = sp.fit_rookie_band_model(band, train_pred, qreg_alpha=0.01, resid_sd_gain=gain,
                                         **fit_kw)
            lo, hi = m.band_many(pos, test_pred, **kw)
            widths.append(float(np.nanmean(hi - lo)))
        assert widths[1] >= widths[0], fit_kw
    src = Path(sp.__file__).read_text()
    assert "np.clip(zsd, 0.0, 2.0)" in src, "the widen-only clamp was removed"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The POINT projection does not move — across every band configuration
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_point_projection_is_IDENTICAL_across_every_band_configuration(population):
    """NF1.8's hard constraint. The band knobs may only move `fp_ppr_p10`/`fp_ppr_p90`; if any of them
    shifts `proj_fp_ppr` (or a projected stat), the story has silently changed the rookie LEVEL, which
    NF1.4's bake-off returned a NULL on and neither NF1.7 nor NF1.8 re-attacked. Byte-identical, not
    approximately."""
    frame, test = population.iloc[:-200], population.iloc[-200:]
    band = frame.assign(games=pd.to_numeric(frame["games"], errors="coerce"))
    hist = band[band["games"] > 0].copy()
    configs = [
        {"per_player_band": False},                                        # NF1.4 incumbent
        {"band_form": "qreg", "band_qreg_alpha": 0.01},                    # NF1.7 shipped
        {},                                                               # NF1.8 production defaults
        {"band_form": "qreg_sqrt", "band_cqr_mode": "pos", "band_cqr_scale": "width"},
        {"band_form": "qreg_sqrt", "band_qreg_per_pos": True},
        {"band_form": "knn_norm", "band_k": 80, "band_resid_sd_gain": 0.2},
    ]
    ref = None
    cols = ["proj_fp_ppr", "proj_fp_std", "proj_fp_half", "proj_games",
            "proj_pass_yds", "proj_rush_yds", "proj_rec_yds"]
    bands_seen = set()
    for kw in configs:
        out = sp.project_rookies(test, sp.fit_rookie_slot_curves(hist, band_hist=band, **kw), 2026)
        got = out.set_index("player_id")[cols].sort_index()
        if ref is None:
            ref = got
        else:
            pd.testing.assert_frame_equal(got, ref, check_exact=True, obj=str(kw))
        b = out.set_index("player_id")[["fp_ppr_p10", "fp_ppr_p90"]].sort_index()
        bands_seen.add(tuple(b.to_numpy().ravel().tolist()))
    assert len(bands_seen) >= 4, "the band configurations produced the same band — nothing was tested"


def test_the_shipped_form_and_conformal_mode_are_pre_registered():
    """A shipped setting outside the pre-registered sets would be a config the bake-off never scored."""
    assert sp._ROOKIE_BAND_FORM in sp._ROOKIE_BAND_FORMS
    assert sp._ROOKIE_BAND_CQR_MODE in sp._ROOKIE_BAND_CQR_MODES
    assert sp._ROOKIE_BAND_CQR_SCALE in sp._ROOKIE_BAND_CQR_SCALES


def test_the_shipped_constants_match_the_NF1_8_ablation_report():
    """The drift guard: shipped constants must be the ones the bake-off report actually selected. A
    drifted default is an unselected model in production with a report that says otherwise. The label
    format is `<form>[+cqr[<mode>,<scale>]] · sdgain <gain>`."""
    if not _REPORT.exists():
        pytest.skip("NF1.8 ablation report not generated in this checkout")
    text = _REPORT.read_text()
    m = re.search(r"\*\*SHIPPED: `([^`]+)`\*\*", text)
    assert m, "the report does not name a shipped config"
    label = m.group(1)
    assert label.startswith(sp._ROOKIE_BAND_FORM), (label, sp._ROOKIE_BAND_FORM)
    assert f"sdgain {sp._ROOKIE_BAND_RESID_SD_GAIN:g}" in label, label
    if sp._ROOKIE_BAND_CQR_MODE:
        assert f"cqr[{sp._ROOKIE_BAND_CQR_MODE},{sp._ROOKIE_BAND_CQR_SCALE}]" in label, label
    else:
        assert "cqr[" not in label, label
    assert ("_perpos" in label) == bool(sp._ROOKIE_BAND_QREG_PER_POS), label


def test_the_NF17_reference_arm_is_PINNED_not_derived_from_the_production_constants():
    """🚨 A SELF-REFERENCE THAT WOULD ZERO EVERY COMPARISON. NF1.8 reports its cost against NF1.7's
    winner. If that reference were rebuilt from `season_projection`'s constants — the very constants
    NF1.8 changes — the harness would silently compare NF1.8 against ITSELF and every 'vs NF1.7' number
    in the report would read 0.00."""
    src = (_REPO / "quant_sports_intel_models/football/nfl/fantasy"
           / "run_rookie_perposition_ablation.py").read_text()
    assert '_NF17_WINNER_LABEL = "qreg α0.01 · sdgain 0"' in src
    assert "_NF17_WINNER_LABEL" in src.split("def main")[1], "main must use the pinned label"
    assert not re.search(r'f"qreg α\{SP\._ROOKIE_BAND_QREG_ALPHA', src), (
        "the NF1.7 reference is being rebuilt from the production constants")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The deflation must not be read as PBO alone
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_deflation_reports_the_flip_distribution_and_the_degradation_beside_PBO():
    """⭐ WHY PBO ALONE IS UNREADABLE ON THIS FIELD. Build a matrix of near-clones (a genuine tie) and
    confirm the reported statistics distinguish it from a real spread: PBO is high because the argmin
    flips, but Bailey's performance degradation is ~0 and the contender spread is ~0, and the flip
    distribution names the arms. A future session must not condemn a tie as overfitting on PBO alone —
    nor bless a real overfit, which the second half of this test pins."""
    idx = list(range(2019, 2027))
    rng = np.random.default_rng(3)
    tie = pd.DataFrame({f"clone{i}": 180.0 + rng.normal(0, 0.4, len(idx)) for i in range(6)},
                       index=idx)
    got = deflate(tie)
    assert got["pbo"] is not None and got["os_gap_pct"] is not None
    assert got["os_gap_pct"] < 1.0, got            # picking any clone costs ~nothing
    assert got["contender_spread_pct"] < 2.0, got
    assert got["flips"] and sum(f["IS-half wins"] for f in got["flips"]) > 0
    # a REAL separation: one arm genuinely better every class ⇒ no flips, no degradation
    real = tie.copy()
    real["winner"] = 150.0
    sep = deflate(real)
    assert sep["pbo"] == 0.0, sep
    assert len(sep["flips"]) == 1 and sep["flips"][0]["config"] == "winner"


def test_the_power_table_reports_BOTH_standard_errors_and_the_exact_false_reject_rate():
    """⚠️ POWER REPORTED, NOT ASSUMED. A per-position floor at nominal is a hypothesis test with one
    position's sample size behind it. The binomial SE is the idealised error the Tier-2 floor is derived
    from; the CLASS-CLUSTERED SE is the honest one (rookie-seasons inside a draft class are not
    independent draws). And the exact `P(reject | truly nominal)` must be reported, because it is ≈ 0.5
    at EVERY n — sample size buys the ability to detect a smaller true shortfall, NOT a lower
    false-reject rate, and a reader who assumes otherwise will over-trust the floor."""
    rec = {"n_QB": 81, "cov_QB": 0.739, "covsd_QB": 0.031,
           "n_WR": 224, "cov_WR": 0.826, "covsd_WR": 0.043}
    rows = position_power(rec, ["QB", "WR"])
    assert len(rows) == 2
    for r in rows:
        assert r["binomial SE"] > 0 and r["class-clustered SE"] is not None
        assert 0.35 < r["P(reject | truly nominal)"] < 0.65, r
    qb = next(r for r in rows if r["position"] == "QB")
    assert qb["z vs nominal"] < 0
    assert qb["significantly below nominal?"] == "NO", (
        "0.739 on 81 rows is NOT significantly below nominal — the report must say so")
    assert qb["binomial SE"] > next(r for r in rows if r["position"] == "WR")["binomial SE"]


def test_the_report_states_the_floor_is_a_constraint_and_names_the_degenerate():
    """The report is the artifact a future session reads before touching the gate. Two claims must be
    IN it, not just in the code: that `max_width` satisfies every per-position floor and still loses,
    and that coverage is never a target."""
    if not _REPORT.exists():
        pytest.skip("NF1.8 ablation report not generated in this checkout")
    text = _REPORT.read_text()
    assert "max_width" in text and "satisfies every per-position floor" in text
    assert "never a target" in text
    assert _NF17_WINNER_LABEL in text, "the report must name the NF1.7 arm it is compared against"
