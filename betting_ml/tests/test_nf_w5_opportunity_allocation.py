"""NF-W5 guards — opportunity allocation on the JOINT gate.

Discipline carried from the NF-W family, applied here:
  · every RED-proof mutates the source IN-PROCESS and ASSERTS THE MUTATION LANDED before running
    the guard (E11.24 #682);
  · every guard that ITERATES over matches asserts NON-VACUITY (NF1.7 (a) / INC-38);
  · every clause of an AND-composed rule gets its OWN ISOLATING fixture, satisfying every other
    clause, so only the clause under test can flip the result (NF-D17);
  · source-inspection guards strip comments first so PROSE can neither satisfy nor trip them
    (INC-38);
  · ⭐ the scoring instrument carries a POSITIVE and a NEGATIVE control (MH2.1 (d)): a joint
    metric that cannot see a KNOWN dependence at study scale would make every ceiling reading
    INSTRUMENT_BLIND, not a finding.
"""
from __future__ import annotations

import json
import re
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_MODULE = Path(OA.__file__)
_RUNNER = _MODULE.parent / "run_nf_w5_opportunity_allocation.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w5_preregistration.md"


def _mutated(path: Path, old: str, new: str, name: str):
    """Load `path` with one deliberate break applied — asserting the break LANDED first."""
    src = path.read_text()
    assert old in src, f"RED-proof target not found in {path.name}: {old!r}"
    mutated = src.replace(old, new, 1)
    assert mutated != src, "the mutation did not change the source — the RED-proof would no-op"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(mutated, str(path), "exec"), mod.__dict__)  # noqa: S102 — test harness
    return mod


def _stripped_source(path: Path) -> str:
    """Comment-stripped source, so a prose mention can neither satisfy nor trip a check."""
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text().splitlines())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Field + pre-registration shape
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFieldAndPreregistration:
    def test_the_declared_field_is_the_sec05_minimum(self):
        assert len(OA.REAL_ARMS) == 4 and len(set(OA.REAL_ARMS)) == 4
        assert OA.FOILS == ("independence", "constant_rho")
        assert set(OA.eligible_labels()) == set(OA.REAL_ARMS) | set(OA.FOILS)

    def test_anchors_never_enter_the_eligible_field(self):
        anchors = OA.anchors()
        assert len(anchors) > 0                       # non-vacuity (NF1.7 (a))
        overlap = set(anchors) & set(OA.eligible_labels())
        assert not overlap, f"anchors leaked into the eligible field: {overlap} (MH2.1 (a))"

    def test_every_parametrized_form_has_an_oracle_and_independence_has_none(self):
        anchors = set(OA.anchors())
        for f in OA.PARAMETRIZED_FORMS:
            assert OA.oracle_of(f) in anchors
        assert OA.oracle_of("independence") not in anchors, (
            "independence has no parameters — a peeking version of it is itself, and listing "
            "one would be a vacuous anchor (NF1.7 (a))")

    def test_matched_n_controls_exist_for_every_real_arm(self):
        anchors = set(OA.anchors())
        missing = [a for a in OA.REAL_ARMS if OA.matched_n_of(a) not in anchors]
        assert not missing, f"arms without a matched-n capacity control (NF1.9 (f)): {missing}"

    def test_primary_metric_and_bands_are_the_preregistered_ones(self):
        assert OA.PRIMARY_METRIC == "team_total_crps"
        assert OA.CEILING_BANDS == (2.0, 5.0)
        assert OA.PRIMARY_METRIC in OA.ALL_METRICS
        assert set(OA.CO_METRICS) == {"energy_score", "variogram_score"}

    def test_the_two_fdr_families_are_singletons_and_disjoint(self):
        fams = OA.FDR_FAMILIES
        assert set(fams) == {"arm", "ceiling"}
        assert all(len(v) == 1 for v in fams.values())
        assert not set(fams["arm"]) & set(fams["ceiling"])

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        assert _PREREG.exists()
        text = _PREREG.read_text()
        needles = ("Sklar", "ceiling", "MARGINAL", "best_alpha = 0", "deploy-held",
                   "upward-biased", "team-total", "comonotonic", "leave-one-out",
                   "UNDEFINED by design")
        assert len(needles) > 0
        for needle in needles:
            assert needle in text, f"pre-registration must declare {needle!r}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The sample-CRPS reducer (exact identity + refusal of a non-finite ensemble)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestSampleCrps:
    def test_matches_brute_force_exactly(self):
        rng = np.random.default_rng(3)
        for _ in range(4):
            x = rng.normal(size=157)
            y = float(rng.normal())
            brute = float(np.mean(np.abs(x - y))
                          - 0.5 * np.mean(np.abs(x[:, None] - x[None, :])))
            assert abs(OA.crps_sample(x, y) - brute) < 1e-10

    def test_sharper_correct_beats_wrong_scale(self):
        rng = np.random.default_rng(4)
        y = rng.normal(size=400)
        good = np.mean([OA.crps_sample(rng.normal(size=256), yy) for yy in y])
        wide = np.mean([OA.crps_sample(3.0 * rng.normal(size=256), yy) for yy in y])
        assert good < wide

    def test_reducer_refuses_a_non_finite_ensemble(self):
        X = np.ones((16, 3))
        X[3, 1] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            OA.assert_finite_samples(X, "arm_x")

    def test_red_proof_the_refusal_is_load_bearing(self):
        mod = _mutated(_MODULE, "if bad:", "if False and bad:", "oa_mut_finite")
        mod.assert_finite_samples(np.full((4, 2), np.nan), "arm_x")  # no raise ⇒ clause binds


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Randomized PIT + inverse CDF (two reads of one grid object)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPitAndInverse:
    def test_continuous_pit_is_uniform_between_adjacent_levels(self):
        rng = np.random.default_rng(5)
        q = np.tile(np.linspace(0, 30, 39), (4000, 1))
        u = OA.randomized_pit(q, rng.uniform(0.5, 29.5, 4000), rng)
        assert 0.45 < u.mean() < 0.55
        assert (u > 0).all() and (u < 1).all()

    def test_atom_pit_spans_the_atom(self):
        rng = np.random.default_rng(6)
        q = np.tile(np.r_[np.zeros(20), np.linspace(0.5, 30, 19)], (3000, 1))
        u = OA.randomized_pit(q, np.zeros(3000), rng)
        # 20 zero quantiles ⇒ the atom spans [0, L[20]] = [0, 0.525]
        assert u.min() < 0.02 and 0.5 < u.max() <= 0.525 + 1e-9
        assert u.max() - u.min() > 0.4      # genuinely randomized, not a point

    def test_tails_map_to_the_clamped_bands(self):
        rng = np.random.default_rng(7)
        q = np.tile(np.linspace(10, 20, 39), (500, 1))
        below = OA.randomized_pit(q, np.full(500, 5.0), rng)
        above = OA.randomized_pit(q, np.full(500, 25.0), rng)
        assert below.max() <= 0.025 + 1e-9
        assert above.min() >= 0.975 - 1e-9

    def test_inverse_cdf_clamps_tails_identically(self):
        q = np.linspace(10, 20, 39)
        x = OA.x_from_uniforms(q, np.array([0.0, 0.01, 0.5, 0.99, 1.0]))
        assert x[0] == x[1] == q[0]
        assert x[-1] == x[-2] == q[-1]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The joint object: team-week grouping (row conservation fail-closed)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _test_frame(n_teams: int = 4, k: int = 5, gws: tuple[int, ...] = (1, 2)) -> pd.DataFrame:
    rows = []
    for gw in gws:
        for t in range(n_teams):
            for i in range(k):
                rows.append({"team": f"T{t}", "gw": gw,
                             "position": ["QB", "RB", "WR", "WR", "TE"][i % 5],
                             "fantasy_points": float(i)})
    return pd.DataFrame(rows)


class TestTeamWeeks:
    def test_groups_conserve_rows_and_count_exclusions(self):
        df = _test_frame()
        solo = pd.DataFrame([{"team": "T9", "gw": 1, "position": "QB", "fantasy_points": 3.0}])
        groups, excl = OA.build_team_weeks(pd.concat([df, solo], ignore_index=True))
        assert excl["n_rows_scored"] + excl["n_rows_excluded"] == excl["n_rows_total"]
        assert excl["n_groups_excluded"] == 1 and excl["n_rows_excluded"] == 1
        assert len(groups) == 8
        assert all(len(g["rows"]) >= OA.MIN_TEAM_K for g in groups)

    def test_red_proof_the_conservation_clause_fires_on_broken_accounting(self):
        mod = _mutated(_MODULE,
                       'excl["n_rows_excluded"] += int(len(rows))',
                       'excl["n_rows_excluded"] += 0',
                       "oa_mut_conserve")
        df = _test_frame()
        solo = pd.DataFrame([{"team": "T9", "gw": 1, "position": "QB", "fantasy_points": 3.0}])
        with pytest.raises(ValueError, match="lost rows"):
            mod.build_team_weeks(pd.concat([df, solo], ignore_index=True))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Constructions — marginal uniformity per construction (the Sklar property, per class)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_POSV = np.array(["QB", "RB", "RB", "WR", "WR", "TE"], dtype=object)


def _group(team: str = "T0", gw: int = 3) -> tuple[dict, dict, np.ndarray]:
    group = {"team": team, "gw": gw, "positions": _POSV}
    base = OA.group_base("fold", team, gw, len(_POSV))
    cm = np.array([18.0, 12.0, 6.0, 14.0, 9.0, 7.0])
    return group, base, cm


def _paircorr(r_same: float = -0.05, r_cross: float = 0.1) -> dict:
    out = {}
    for a in WP.POSITIONS:
        for b in WP.POSITIONS:
            out[OA.pair_key(a, b)] = {"r": r_same if a == b else r_cross,
                                      "n_pairs": 100, "n_groups": 50, "cluster_se": 0.02}
    return out


def _all_construction_cases() -> list[tuple[str, object]]:
    pf = _synthetic_pf(n_tw=24, rho=0.1, seed=11)
    return [
        ("independence", None),
        ("comonotonic", None),
        ("constant_rho", 0.12),
        ("gauss_pos_factor", {"QB": 0.3, "RB": 0.2, "WR": 0.25, "TE": 0.15}),
        ("gauss_pos_pairwise", _paircorr()),
        ("shuffled_teams", _paircorr(0.0, 0.0)),
        ("dirichlet_alloc", {"c": 32.0, "sv": 0.2}),
        ("empirical_role_resample", OA.fit_empirical_bank(pf)),
    ]


def _synthetic_pf(n_tw: int, rho: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(n_tw):
        zg = rng.standard_normal()
        z = np.sqrt(rho) * zg + np.sqrt(1 - rho) * rng.standard_normal(len(_POSV))
        u = np.clip(norm.cdf(z), 1e-6, 1 - 1e-6)
        for i, (p, ui) in enumerate(zip(_POSV, u)):
            rows.append({"team": f"T{t % 8}", "gw": t // 8 + 1, "position": p,
                         "u": float(ui), "z": float(norm.ppf(ui)), "champ_mean": 10.0 + i})
    return pd.DataFrame(rows)


class TestConstructionMarginals:
    @pytest.mark.parametrize("label,params", _all_construction_cases())
    def test_marginals_are_uniform_and_in_bounds(self, label, params):
        group, base, cm = _group()
        U = OA.sample_uniforms(label, params, group, base, cm)
        assert U.shape == (OA.N_SAMPLES, len(_POSV))
        assert U.min() >= 0.0 and U.max() <= 1.0
        assert np.all(np.abs(U.mean(axis=0) - 0.5) < 0.08), label
        assert np.all(np.abs(U.var(axis=0) - 1.0 / 12.0) < 0.02), label

    def test_case_list_is_exhaustive_over_the_field(self):
        cased = {lab.split("__")[-1] for lab, _ in _all_construction_cases()}
        declared = set(OA.FOILS) | set(OA.REAL_ARMS) | set(OA.BASE_ANCHORS)
        assert declared <= cased, f"constructions without a marginal guard: {declared - cased}"

    def test_comonotonic_is_maximal_dependence(self):
        group, base, cm = _group()
        U = OA.sample_uniforms("comonotonic", None, group, base, cm)
        assert np.allclose(U, U[:, [0]])

    def test_dirichlet_rank_transform_is_exactly_uniform(self):
        group, base, cm = _group()
        U = OA.sample_uniforms("dirichlet_alloc", {"c": 16.0, "sv": 0.1}, group, base, cm)
        for j in range(U.shape[1]):
            assert len(np.unique(U[:, j])) == OA.N_SAMPLES

    def test_unknown_label_raises(self):
        group, base, cm = _group()
        with pytest.raises(ValueError, match="unknown construction"):
            OA.sample_uniforms("mystery_arm", None, group, base, cm)

    def test_crn_base_is_deterministic_per_team_week(self):
        b1 = OA.group_base("2025H2", "KC", 210, 6)
        b2 = OA.group_base("2025H2", "KC", 210, 6)
        assert np.array_equal(b1["Z"], b2["Z"]) and np.array_equal(b1["zg"], b2["zg"])
        b3 = OA.group_base("2025H2", "KC", 211, 6)
        assert not np.array_equal(b1["Z"], b3["Z"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Dependence fitting (recovery, shuffle destruction, PSD projection)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDependenceFitting:
    def test_pair_correlations_recover_a_known_rho(self):
        # n_tw sized so every position's moment SE is well inside the tolerance — the QB cell
        # has no within-position pair on this roster, so it is the noisiest loading (measured:
        # at n_tw=400 a seed-level ~2-SE fluke breaches 0.12; at 1600 the SE is ~0.017).
        pf = _synthetic_pf(n_tw=1600, rho=0.15, seed=1)
        pc = OA.fit_pair_correlations(pf)
        assert len(pc) > 0                                  # non-vacuity
        assert abs(OA.fit_constant_rho(pc) - 0.15) < 0.03
        lam = OA.fit_factor_loadings(pc)
        for p in WP.POSITIONS:
            assert abs(lam[p] - np.sqrt(0.15)) < 0.12

    def test_unknown_position_rejects_the_fit(self):
        pf = _synthetic_pf(n_tw=8, rho=0.0, seed=2)
        pf.loc[0, "position"] = "FB"
        with pytest.raises(ValueError, match="unknown positions"):
            OA.fit_pair_correlations(pf)

    def test_shuffling_teams_destroys_dependence_but_keeps_marginals(self):
        pf = _synthetic_pf(n_tw=400, rho=0.2, seed=3)
        shuf = OA.shuffle_teams_within_week(pf)
        # a within-week shuffle retains a small collision residual (a pair can land back on one
        # team, P ≈ (K−1)/(N_week−1) ≈ 0.11 here ⇒ residual ≈ 0.02) — the property is that MOST
        # of the dependence is destroyed, not that the residual is exactly zero.
        r_orig = OA.fit_constant_rho(OA.fit_pair_correlations(pf))
        r_shuf = OA.fit_constant_rho(OA.fit_pair_correlations(shuf))
        assert r_orig > 0.15
        assert abs(r_shuf) < 0.3 * r_orig
        for gw in pf["gw"].unique():
            a = np.sort(pf.loc[pf["gw"] == gw, "u"].to_numpy())
            b = np.sort(shuf.loc[shuf["gw"] == gw, "u"].to_numpy())
            assert np.allclose(a, b), "the shuffle changed marginals — it must only relabel teams"

    def test_constant_rho_clips_negative_pooling_to_zero(self):
        pc = _paircorr(r_same=-0.3, r_cross=-0.3)
        assert OA.fit_constant_rho(pc) == 0.0

    def test_nearest_psd_repairs_a_non_psd_matrix(self):
        R = np.array([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]])
        assert np.linalg.eigvalsh(R).min() < 0          # genuinely non-PSD input
        A = OA.nearest_psd_corr(R)
        assert np.linalg.eigvalsh(A).min() > 0
        assert np.allclose(np.diag(A), 1.0)

    def test_matched_n_pit_cuts_at_week_boundaries(self):
        pf = _synthetic_pf(n_tw=64, rho=0.1, seed=4)
        cut = OA.matched_n_pit(pf, n_rows=60)
        assert len(cut) >= 60
        kept_gws = set(cut["gw"].unique())
        for g in kept_gws:
            assert (pf["gw"] == g).sum() == (cut["gw"] == g).sum(), (
                "a partial week in the matched-n slice breaks team-week integrity")

    def test_dirichlet_fit_is_deterministic_and_on_grid(self):
        pf = _synthetic_pf(n_tw=32, rho=0.1, seed=5)
        pc = OA.fit_pair_correlations(pf)
        a = OA.fit_dirichlet_params(pf, pc)
        b = OA.fit_dirichlet_params(pf, pc)
        assert a == b
        assert a["c"] in OA.DIRICHLET_C_GRID and a["sv"] in OA.DIRICHLET_SV_GRID

    def test_dirichlet_competition_is_negative_at_zero_volume(self):
        rng = np.random.default_rng(6)
        w = np.full(6, 1 / 6)
        u = OA._dirichlet_uniforms(w, 8.0, 0.0, rng.standard_normal(2048), rng)
        z = norm.ppf(np.clip(u, 1e-6, 1 - 1e-6))
        iu, ju = np.triu_indices(6, 1)
        assert float(np.mean(z[:, iu] * z[:, ju])) < -0.01, (
            "a pure Dirichlet allocation must be negatively dependent (shares sum to 1)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Role cells + empirical bank
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRoleCellsAndBank:
    def test_role_cells_rank_by_mean_and_cap(self):
        pos = np.array(["WR"] * 6 + ["QB"], dtype=object)
        means = np.array([1.0, 9.0, 5.0, 7.0, 3.0, 8.0, 20.0])
        cells = OA.role_cells(pos, means)
        assert cells[1] == "WR1" and cells[5] == "WR2" and cells[3] == "WR3"
        assert cells[0] is None                    # 6th WR is past the WR cap of 5
        assert cells[6] == "QB1"

    def test_bank_cells_are_rank_normalized_uniform(self):
        pf = _synthetic_pf(n_tw=40, rho=0.1, seed=7)
        bank = OA.fit_empirical_bank(pf)
        assert bank["n_donors"] == 40
        assert len(bank["bank"]) > 0               # non-vacuity
        for cell, arr in bank["bank"].items():
            vals = arr[np.isfinite(arr)]
            assert vals.min() > 0 and vals.max() < 1
            assert abs(vals.mean() - 0.5) < 0.01, cell

    def test_leave_one_out_falls_back_to_independence_when_self_is_the_only_donor(self):
        pf = _synthetic_pf(n_tw=1, rho=0.1, seed=8)
        bank = OA.fit_empirical_bank(pf)
        team, gw = bank["donors"][0]
        group = {"team": team, "gw": gw, "positions": _POSV}
        base = OA.group_base("f", team, gw, len(_POSV))
        cm = np.arange(6, dtype=float) + 5
        U = OA.sample_uniforms("empirical_role_resample", bank, group, base, cm)
        Uind = OA.sample_uniforms("independence", None, group, base, cm)
        assert np.allclose(U, Uind)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. ⭐ Instrument controls (MH2.1 (d)) — the metric must SEE dependence at study scale
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _control_scores(rho_true: float, rho_model: float, n_tw: int = 120,
                    seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Paired (independence, modeled-dependence) team-total CRPS on a synthetic league whose
    true copula is equicorrelated Gaussian rho_true, marginals N(10+i, 6) on the 39-level grid."""
    k = 12
    qgrid = np.array([(10.0 + i) + 6.0 * norm.ppf(WP.Q_LEVELS) for i in range(k)])
    pos = np.array((["QB", "RB", "RB", "WR", "WR", "WR", "TE", "TE"]
                    + ["RB", "WR", "QB", "TE"])[:k], dtype=object)
    ind, dep = [], []
    for t in range(n_tw):
        r = np.random.default_rng(seed * 100_000 + t)
        zg = r.standard_normal()
        z = np.sqrt(rho_true) * zg + np.sqrt(1 - rho_true) * r.standard_normal(k)
        y = 10.0 + np.arange(k) + 6.0 * z
        group = {"team": "X", "gw": t, "positions": pos}
        base = OA.group_base("ctl", "X", t, k)
        for label, par, acc in (("independence", None, ind),
                                ("constant_rho", rho_model, dep)):
            U = OA.sample_uniforms(label, par, group, base, np.arange(k) + 10.0)
            X = np.column_stack([OA.x_from_uniforms(qgrid[j], U[:, j]) for j in range(k)])
            acc.append(OA.score_group(X, y)["team_total_crps"])
    return np.asarray(ind), np.asarray(dep)


class TestInstrumentControls:
    def test_positive_control_the_metric_sees_a_known_dependence(self):
        ind, dep = _control_scores(rho_true=0.15, rho_model=0.15, n_tw=120, seed=1)
        d = ind - dep
        se = d.std(ddof=1) / np.sqrt(len(d))
        assert d.mean() > 3 * se, (
            f"INSTRUMENT_BLIND: team_total_crps cannot see rho=0.15 at n=120 "
            f"(delta {d.mean():.4f}, se {se:.4f}) — a null ceiling under this instrument "
            f"would be meaningless (MH2.1 (d))")

    def test_negative_control_no_false_dependence_win_under_independence(self):
        ind, dep = _control_scores(rho_true=0.0, rho_model=0.15, n_tw=120, seed=2)
        d = ind - dep
        se = d.std(ddof=1) / np.sqrt(len(d))
        assert d.mean() < 3 * se, (
            f"the instrument credits dependence that is not there (delta {d.mean():.4f}, "
            f"se {se:.4f})")

    def test_energy_and_variogram_also_prefer_the_true_copula(self):
        # VS is the highest-variance of the three scores — this control needs a stronger true
        # rho and more team-weeks than the primary-metric control to resolve (measured: at
        # n=80 / rho=0.2 the VS mean is inside its own noise).
        k = 6
        qgrid = np.array([(10.0 + i) + 6.0 * norm.ppf(WP.Q_LEVELS) for i in range(k)])
        es_d, vs_d = [], []
        for t in range(300):
            r = np.random.default_rng(9_000 + t)
            zg = r.standard_normal()
            z = np.sqrt(0.4) * zg + np.sqrt(0.6) * r.standard_normal(k)
            y = 10.0 + np.arange(k) + 6.0 * z
            group = {"team": "X", "gw": t, "positions": _POSV}
            base = OA.group_base("ctl2", "X", t, k)
            sc = {}
            for label, par in (("independence", None), ("constant_rho", 0.4)):
                U = OA.sample_uniforms(label, par, group, base, np.arange(k) + 10.0)
                X = np.column_stack([OA.x_from_uniforms(qgrid[j], U[:, j]) for j in range(k)])
                sc[label] = OA.score_group(X, y)
            es_d.append(sc["independence"]["energy_score"]
                        - sc["constant_rho"]["energy_score"])
            vs_d.append(sc["independence"]["variogram_score"]
                        - sc["constant_rho"]["variogram_score"])
        assert np.mean(es_d) > 0 and np.mean(vs_d) > 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The marginal-identity guard (the Sklar clause, fail-closed)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestMarginalIdentity:
    def test_within_tolerance_passes_and_returns_the_spread(self):
        s = OA.assert_marginal_identity({"a": 1.000, "b": 1.005, "c": 0.998}, "F")
        assert 0 < s < OA.MARGINAL_IDENTITY_TOL

    def test_a_leaked_marginal_fails_closed(self):
        with pytest.raises(ValueError, match="marginal-identity"):
            OA.assert_marginal_identity({"a": 1.0, "b": 1.2}, "F")

    def test_red_proof_the_tolerance_is_load_bearing(self):
        mod = _mutated(_MODULE, "if spread > tol:", "if spread > tol * 1e9:", "oa_mut_tol")
        mod.assert_marginal_identity({"a": 1.0, "b": 1.2}, "F")  # no raise ⇒ clause binds

    def test_variogram_matches_brute_force_on_a_small_case(self):
        rng = np.random.default_rng(11)
        X = rng.normal(size=(64, 4))
        y = rng.normal(size=4)
        p = OA.VARIOGRAM_P
        brute = 0.0
        for i in range(4):
            for j in range(i + 1, 4):
                brute += (abs(y[i] - y[j]) ** p
                          - np.mean(np.abs(X[:, i] - X[:, j]) ** p)) ** 2
        assert abs(OA.variogram_score(X, y) - brute) < 1e-10


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The gate — one ISOLATING fixture per clause (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"required": 6, "attainable": True, "passes": True},
        "pbo": 0.05, "dsr": 0.99,
        "anchors": {"comonotonic_loses": True, "winner_beats_shuffled": True,
                    "shuffled_lift_not_significant": True,
                    "oracle_floors_respected_at_matched_n": True},
        "coverage": {"blocking_shortfall": False},
    }


class TestArmGateClauses:
    def test_the_passing_fixture_ships(self):
        gate = OA.compose_gate_joint(_passing_sel(), fdr_pass=True)
        assert gate["ship"] and all(gate["checks"].values())

    @pytest.mark.parametrize("mutate,expect_check", [
        (lambda s: s.update(beats_foil=False), "beats_foil"),
        (lambda s: s["fold_clause"].update(passes=False), "fold_consistency"),
        (lambda s: s.update(pbo=0.5), "pbo_ok"),
        (lambda s: s.update(pbo=None), "pbo_ok"),
        (lambda s: s.update(dsr=0.5), "dsr_ok"),
        (lambda s: s.update(dsr=None), "dsr_ok"),
        (lambda s: s["anchors"].update(comonotonic_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(winner_beats_shuffled=False), "permutation_behaves"),
        (lambda s: s["anchors"].update(shuffled_lift_not_significant=False),
         "permutation_behaves"),
        (lambda s: s["anchors"].update(oracle_floors_respected_at_matched_n=False),
         "oracle_floors_respected"),
        (lambda s: s["coverage"].update(blocking_shortfall=True), "coverage_floor_ok"),
    ])
    def test_each_clause_flips_only_itself(self, mutate, expect_check):
        sel = _passing_sel()
        mutate(sel)
        gate = OA.compose_gate_joint(sel, fdr_pass=True)
        assert not gate["ship"]
        failing = [k for k, v in gate["checks"].items() if not v]
        assert failing == [expect_check], (
            f"the fixture must isolate {expect_check} — it flipped {failing} (NF-D17)")

    def test_fdr_clause_flips_only_fdr(self):
        gate = OA.compose_gate_joint(_passing_sel(), fdr_pass=False)
        failing = [k for k, v in gate["checks"].items() if not v]
        assert failing == ["fdr_ok"]

    def test_anchor_only_refusal_is_constraint_refused(self):
        sel = _passing_sel()
        sel["anchors"]["comonotonic_loses"] = False
        gate = OA.compose_gate_joint(sel, fdr_pass=True)
        hand = OA.hand_classify_refusal(gate["checks"])
        assert hand is not None and hand["state"] == "CONSTRAINT_REFUSED"
        assert hand["retest_trigger"] is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 11. ⭐ The NF-W8 decision rule — every band + the fail-closed edges (NF-D17 per clause)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ceiling(pct: float, lo: float = 0.01, passes: bool = True, fdr: bool = True) -> dict:
    return {"ci95": [lo, lo + 0.2], "fold_wins": 7,
            "fold_clause": {"required": 6, "attainable": True, "passes": passes},
            "fdr_binding": fdr, "ceiling_pct": pct}


class TestDecisionRule:
    def test_yes_at_and_above_five(self):
        assert OA.decide_nf_w8(_ceiling(5.0))["answer"] == "YES"
        assert OA.decide_nf_w8(_ceiling(8.7))["answer"] == "YES"

    def test_marginal_between_bands(self):
        assert OA.decide_nf_w8(_ceiling(2.0))["answer"] == "MARGINAL"
        assert OA.decide_nf_w8(_ceiling(4.9))["answer"] == "MARGINAL"

    def test_no_below_two(self):
        d = OA.decide_nf_w8(_ceiling(1.9))
        assert d["answer"] == "NO" and "simulator premise" in d["reason"]

    def test_ci_spanning_zero_is_no_even_at_large_pct(self):
        d = OA.decide_nf_w8(_ceiling(10.0, lo=-0.01))
        assert d["answer"] == "NO" and not d["stat_ok"]

    def test_fold_clause_failure_is_no_even_at_large_pct(self):
        assert OA.decide_nf_w8(_ceiling(10.0, passes=False))["answer"] == "NO"

    def test_fdr_failure_is_no_even_at_large_pct(self):
        assert OA.decide_nf_w8(_ceiling(10.0, fdr=False))["answer"] == "NO"

    def test_unevaluable_pct_fails_closed(self):
        c = _ceiling(3.0)
        c["ceiling_pct"] = None
        assert OA.decide_nf_w8(c)["answer"] == "NO"

    def test_missing_ci_fails_closed(self):
        c = _ceiling(3.0)
        c["ci95"] = [None, None]
        assert OA.decide_nf_w8(c)["answer"] == "NO"

    def test_red_proof_the_ci_clause_is_load_bearing(self):
        mod = _mutated(_MODULE, "and lo > 0", "and lo > -999", "oa_mut_ci")
        d = mod.decide_nf_w8(_ceiling(10.0, lo=-0.01))
        assert d["stat_ok"], "mutation landed but did not relax the clause — RED-proof no-op"

    def test_red_proof_the_bands_are_load_bearing(self):
        mod = _mutated(_MODULE, "CEILING_BANDS: tuple[float, float] = (2.0, 5.0)",
                       "CEILING_BANDS: tuple[float, float] = (0.1, 0.2)", "oa_mut_bands")
        assert mod.decide_nf_w8(_ceiling(1.9))["answer"] == "YES"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 12. The verdict layer is DERIVED, not stored (NF-W2e one level up)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fake_arm(beats: bool) -> dict:
    sel = _passing_sel()
    sel.update({
        "beats_foil": beats, "mean_delta": 0.01 if beats else -0.01,
        "ci95": [0.001, 0.02] if beats else [-0.02, 0.001],
        "fold_wins": 7 if beats else 2, "p_one_sided": 0.01 if beats else 0.6,
        "observed_sr": 1.2 if beats else -0.3, "var_trials_sr": 0.01,
    })
    sel["fold_clause"]["passes"] = beats
    return sel


def _fake_ceiling(pct: float, p: float = 0.01) -> dict:
    c = _ceiling(pct)
    c.update({"p_one_sided": p, "fdr_binding": None})
    return c


class TestVerdictLayerIsDerivedNotStored:
    def _out(self, pct: float = 6.0, arm_beats: bool = False) -> dict:
        return {"n_folds": 8, "arm": _fake_arm(arm_beats), "ceiling": _fake_ceiling(pct)}

    def test_decision_and_states_are_derived(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w5_opportunity_allocation as R,
        )
        derived = R.derive_verdict_layer(self._out(pct=6.0))
        assert derived["verdict"]["nf_w8_decision"] == "YES"
        assert derived["verdict"]["arm"] != "NULL"
        assert "arm" in derived["null_states"]

    def test_a_losing_arm_is_genuine_absence_with_no_trigger(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w5_opportunity_allocation as R,
        )
        derived = R.derive_verdict_layer(self._out(arm_beats=False))
        ns = derived["null_states"]["arm"]
        assert ns["state"] == "GENUINE_ABSENCE"
        assert ns.get("retest_trigger") is None

    def test_changing_the_stored_pct_changes_the_decision_on_rederivation(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w5_opportunity_allocation as R,
        )
        assert R.derive_verdict_layer(self._out(pct=6.0))["verdict"]["nf_w8_decision"] == "YES"
        assert R.derive_verdict_layer(self._out(pct=1.0))["verdict"]["nf_w8_decision"] == "NO"

    def test_re_deriving_is_idempotent(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w5_opportunity_allocation as R,
        )
        out = self._out()
        first = R.derive_verdict_layer(out)
        out.update(first)
        second = R.derive_verdict_layer(out)
        assert first["verdict"] == second["verdict"]

    def test_the_rewrite_path_shares_the_same_derivation(self):
        src = _stripped_source(_RUNNER)
        assert src.count("out.update(derive_verdict_layer(out))") == 2, (
            "the live run and --rewrite-report must share ONE derivation — a second "
            "implementation is a verdict that can disagree with itself")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 13. Runner wiring (source inspection, comment-stripped — INC-38)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRunnerWiring:
    def test_the_incumbent_pin_is_invoked_not_just_imported(self):
        src = _stripped_source(_RUNNER)
        assert "assert_incumbents_match_the_w2d_artifact()" in src, (
            "the W2d artifact pin must be CALLED — wired ≠ invoked (NF-C0e)")

    def test_the_incumbent_map_is_imported_never_retyped(self):
        src = _stripped_source(_RUNNER)
        assert "AV.INCUMBENT_OF_POSITION" in src
        # the tell of a re-typed map is a POSITION-keyed form literal ({'QB': 'inj_...'}); the
        # legitimate q_forms dict (form-keyed) must not trip this.
        assert not re.search(r"['\"](QB|RB|WR|TE)['\"]\s*:\s*['\"]inj_", src), (
            "a re-typed incumbent literal can drift from the certified artifact")

    def test_the_ceiling_is_logged_oracle_first_every_fold(self):
        src = _RUNNER.read_text()
        assert "peeking CEILING vs independence" in src.split("def select_joint_arm")[0], (
            "the ceiling must be logged inside the fold runner, before any arm selection")

    def test_no_pbp_no_fillna_zero_no_lake_io_in_the_pure_module(self):
        src = _stripped_source(_MODULE)
        for tok in ("pbp", "fillna(0)", "query_lake", "duckdb", "s3io", "read_parquet"):
            assert tok not in src, f"the pure module must not touch {tok!r}"

    def test_runner_has_no_pbp_and_no_fillna_zero(self):
        src = _stripped_source(_RUNNER)
        for tok in ("pbp", "fillna(0)"):
            assert tok not in src, f"{tok!r} is out of scope for NF-W5 (pre-registered)"

    def test_smoke_and_rewrite_report_paths_exist(self):
        src = _stripped_source(_RUNNER)
        for needle in ('"--smoke"', '"--rewrite-report"', "folds[-2:]"):
            assert needle in src

    def test_rewrite_report_needs_no_lake(self):
        src = _RUNNER.read_text()
        rewrite_block = src.split("if args.rewrite_report:")[1].split("t_start = time.time()")[0]
        assert "build_matrix_w2d" not in rewrite_block
        assert "write_report" in rewrite_block

    def test_stored_fold_results_carry_what_the_report_rereads(self):
        src = _RUNNER.read_text()
        for key in ("marginal_identity_spread", "exclusions", "ceiling_by_form",
                    "params_digest"):
            assert f'"{key}"' in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 14. Deploy-held (best_alpha = 0; promotes nothing, publishes nothing)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDeployHeld:
    _FORBIDDEN = ("write_serving_store", "write_api_cache", "deploy.sh", "boto3.client",
                  "put_object", "upload_file", "credence-prod", "s3.put", "registry.stage")

    def test_neither_file_touches_a_serving_surface(self):
        assert len(self._FORBIDDEN) > 0
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            hits = [tok for tok in self._FORBIDDEN if tok in src]
            assert not hits, f"{path.name} touches serving surfaces: {hits}"

    def test_red_proof_the_scan_would_catch_a_real_write(self):
        src = _stripped_source(_MODULE) + "\nboto3.client('s3').put_object()"
        hits = [tok for tok in self._FORBIDDEN if tok in src]
        assert hits, "the deploy-held scan cannot fire — it guards nothing"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 15. Score-group contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestScoreGroup:
    def test_carries_every_declared_metric_and_the_coverage_bit(self):
        rng = np.random.default_rng(12)
        sc = OA.score_group(rng.normal(size=(128, 5)), rng.normal(size=5))
        for m in OA.ALL_METRICS:
            assert m in sc and np.isfinite(sc[m])
        assert isinstance(sc["total_inside_80"], bool)
        assert sc["k"] == 5 and np.isfinite(sc["marginal_crps_sum"])

    def test_json_artifact_round_trip_preserves_the_decision_inputs(self):
        c = _fake_ceiling(3.3)
        again = json.loads(json.dumps(c))
        assert OA.decide_nf_w8(again)["answer"] == OA.decide_nf_w8(c)["answer"]
