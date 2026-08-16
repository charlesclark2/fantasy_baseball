"""Guards for MH2.6 — the served-window calibration audit.

The verdict this study reports is a NULL ("within noise"). A null is only worth anything if the
machine that produced it could have said something else, so the load-bearing guards here are
NON-VACUITY guards: they feed the audit a KNOWN defect and require it to stop saying WITHIN_NOISE.
A verdict machine with one reachable verdict is the NF1.7 (a) vacuous-check class wearing a study's
clothes.

Fast gate: imports only `betting_ml` (never `pipeline`, per E11.23), does no IO, and mutates no
global state at import.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts import mh2_6_calibration_audit as M

SRC = Path(M.__file__).read_text()

# Above the vacuity floor (so the machine CAN fire) but small enough for the fast gate.
GUARD_REPS = M.min_null_reps() + 260


def _strip_comments(src: str) -> str:
    """INC-38: a source-inspection guard that prose can satisfy is not a guard."""
    return "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))


def _frame(n=300, *, sigma_scale=1.0, mu_shift=0.0, p_shift=0.0, seed=7,
           tier="post_lineup", stamp="v6", dates=None) -> pd.DataFrame:
    """A served frame whose outcomes are drawn from the served predictive, optionally CORRUPTED.

    `sigma_scale`/`mu_shift`/`p_shift` corrupt the TRUTH, not the prediction — i.e. the served
    μ/σ/p̂ stay as they are and reality departs from them, which is exactly the defect an audit
    must catch.
    """
    rng = np.random.default_rng(seed)
    if dates is None:
        dates = pd.date_range("2026-06-24", periods=50).date
    mu = rng.normal(9.0, 0.6, n)
    sg = np.clip(rng.normal(4.3, 0.25, n), 3.2, 6.5)
    p = np.clip(rng.normal(0.52, 0.035, n), 0.02, 0.98)
    return pd.DataFrame({
        "game_pk": np.arange(n), "game_date": rng.choice(dates, n), "tier": tier,
        "model_version": "v6", "totals_model_version": stamp,
        "mu": mu, "sigma": sg, "p_home": p, "data_source": "feature_store",
        "y_total": np.round(rng.normal(mu + mu_shift, sg * sigma_scale)),
        "y_home_win": rng.binomial(1, np.clip(p + p_shift, 1e-6, 1 - 1e-6)).astype(float),
    })


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ NON-VACUITY — the audit must be able to return something OTHER than WITHIN_NOISE
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
class TestTheAuditCanFail:
    def test_a_clean_frame_is_called_within_noise(self):
        """The negative control. Without it, 'it detects defects' could just mean 'it fires on
        everything', which is as useless as a check that never fires."""
        r = M.run(frame=_frame(), reps=GUARD_REPS, with_power=False)
        assert r["verdict"]["verdict"] == "WITHIN_NOISE"
        assert r["verdict"]["phase_2_fires"] is False

    @pytest.mark.parametrize("kw,expect_key", [
        ({"sigma_scale": 1.35}, "totals"),   # reality far more dispersed than the served σ
        ({"sigma_scale": 0.70}, "totals"),   # ...and the mirror, so the test is two-sided
        ({"mu_shift": 1.50}, "totals"),      # a level defect
    ])
    def test_a_corrupted_frame_is_NOT_called_within_noise(self, kw, expect_key):
        r = M.run(frame=_frame(**kw), reps=GUARD_REPS, with_power=False)
        v = r["verdict"]
        assert v["verdict"] != "WITHIN_NOISE", (
            f"a known {kw} defect was reported as within noise — the audit cannot fail")
        assert v["outside_null_recent"][expect_key], "nothing was flagged outside the null"

    def test_a_h2h_defect_is_detected(self):
        r = M.run(frame=_frame(n=600, p_shift=0.12), reps=GUARD_REPS, with_power=False)
        assert r["verdict"]["verdict"] != "WITHIN_NOISE"
        assert r["verdict"]["outside_null_recent"]["h2h"]

    def test_an_empty_population_raises_rather_than_reporting_a_verdict(self):
        """NF1.7 (a): a verdict computed over nothing is not a pass."""
        with pytest.raises(RuntimeError, match="ZERO rows"):
            M.run(frame=_frame().iloc[0:0], reps=GUARD_REPS, with_power=False)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MH2.1 METHOD LOCK — the stratifier is validated first, or nothing is read off it
# ══════════════════════════════════════════════════════════════════════════════════════════════

class TestTheStratifierLock:
    def test_the_validation_is_imported_from_mh2_5_not_reimplemented(self):
        """One implementation of the lock. A second copy is a second thing to drift."""
        body = _strip_comments(SRC)
        assert re.search(r"from betting_ml\.scripts\.mh2_5_sigma_recalibration import",
                         body), "MH2.6 must import MH2.5's stratifier bar, not restate it"
        for name in ("realized_dispersion_table", "rms_var_z", "metric_noise_floor"):
            assert f"def {name}" not in body, f"{name} is re-implemented locally — drift risk"
        # ...and the bar itself is MH2.5's, not a locally softened copy.
        assert "STRATIFIER_MIN_RHO =" not in body and "STRATIFIER_MIN_ENDPOINT_SE =" not in body

    def test_a_failing_partition_is_reported_as_disqualified_and_refuses_the_read(self):
        """A partition whose bins do not separate realized dispersion must be REFUSED, not read.
        Fixture: a stratifier with NO relationship to the residual spread."""
        rng = np.random.default_rng(0)
        strat = rng.uniform(3.5, 5.5, 400)
        resid = rng.normal(0, 4.3, 400)          # dispersion independent of the stratifier
        s = M.realized_dispersion_table(strat, resid, 5)
        assert s["valid"] is False
        table = M._strat_table(s)
        assert "DISQUALIFIED" in table
        assert "No `Var(z)` may be read off this partition" in table

    def test_a_genuine_partition_validates(self):
        """The two-sided half: the bar must also PASS on a partition that really does separate
        dispersion, or 'DISQUALIFIED' would just mean 'the bar is unreachable'."""
        rng = np.random.default_rng(0)
        strat = rng.uniform(3.0, 6.0, 800)
        resid = rng.normal(0, strat)             # dispersion IS the stratifier
        s = M.realized_dispersion_table(strat, resid, 5)
        assert s["valid"] is True
        assert "✅ VALIDATED" in M._strat_table(s)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE PRE-REGISTERED LOCKS
# ══════════════════════════════════════════════════════════════════════════════════════════════

class TestPreRegisteredLocks:
    def test_strata_count_is_derived_from_n_alone(self):
        """LOCK 3 — a design quantity known before any result (NF1.8). It may depend on n and on
        nothing else."""
        assert M.n_strata(60) == M.STRATA_MIN        # floor holds at small n
        assert M.n_strata(300) == 5
        assert M.n_strata(600) == 10
        assert M.n_strata(10_000) == M.STRATA_MAX    # and is capped
        assert all(M.n_strata(a) <= M.n_strata(b) for a, b in [(100, 200), (200, 400)])

    @pytest.mark.slow
    def test_the_rolled_back_mh2_1_rows_leave_the_totals_leg_and_stay_in_the_h2h_leg(self):
        """The 2026-08-02 rows were priced for TOTALS by the rolled-back challenger; their
        home_win side is still v6. Isolating fixture: the only thing separating the two legs is
        the stamp, so nothing else can produce the difference."""
        clean = _frame(n=200, seed=1)
        stamped = _frame(n=60, seed=2, stamp=M.ROLLED_BACK_TOTALS_STAMP)
        stamped["game_pk"] += 10_000
        r = M.run(frame=pd.concat([clean, stamped], ignore_index=True), reps=GUARD_REPS, with_power=False)
        t = r["tiers"]["post_lineup"]
        assert t["n_dropped_rolled_back"] == 60
        assert t["n_totals_rows"] == 200
        assert t["h2h"]["FULL"]["obs"]["n"] == 260, "the h2h leg must KEEP those rows"

    def test_the_pull_serves_the_row_the_app_showed(self):
        """Latest row per (game_pk, tier), live only. Checked on comment-stripped SQL so a
        docstring cannot satisfy it (INC-38)."""
        sql = _strip_comments(M._PULL_SQL)
        assert "ROW_NUMBER() OVER" in sql and "ORDER BY inserted_at DESC" in sql
        assert "PARTITION BY game_pk, prediction_type" in sql
        # ⭐ the `= 1` is the whole point: without it the window function ranks the rows and then
        # keeps ALL of them, so a game's superseded morning/earlier runs re-enter the population.
        assert re.search(r"\)\s*=\s*1", sql), "QUALIFY must keep rank 1 ONLY"
        assert "COALESCE(is_backfill, FALSE) = FALSE" in sql
        assert "game_type = 'R'" in sql and "home_final_score IS NOT NULL" in sql

    def test_the_study_is_snowflake_free(self):
        """Keyed on real IMPORT/CALL forms, not on the word — the module docstring says
        'SNOWFLAKE-FREE', and a substring scan that its own honest label trips is the E9.64
        over-eager-guard class."""
        body = _strip_comments(SRC)
        for form in ("import snowflake", "from snowflake", "get_snowflake_connection",
                     "snowflake.connector", "run_snowflake_query"):
            assert form not in body, f"MH2.6 must not reach Snowflake — found `{form}`"

    def test_best_alpha_is_zero(self):
        assert M.BEST_ALPHA == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE DECISION RULE — each clause proven independently RED-provable (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _decide_fixture(*, outside: bool, moved: bool) -> dict:
    """A minimal result whose ONLY varying inputs are the two clauses under test, so each clause
    can be isolated — a fixture that trips several clauses at once proves none of them.

    `bias` is used because it is in the declared verdict family unconditionally; the p-value is set
    far from the BH boundary so this fixture tests the DECISION RULE, not the correction.
    """
    nn = {"bias": {"evaluable": True, "outside_null": outside,
                   "p_two_sided": 0.0005 if outside else 0.60}}
    drift = {"bias": {"excludes_zero": moved, "p_two_sided": 0.0005 if moved else 0.60}}
    win = {"obs": {"n": 100, "p_sd": 0.03}, "null": nn}
    return {"tiers": {M.PRIMARY_TIER: {
        "totals": {"FULL": win, "RECENT": win, "EARLIER": win, "TRIGGER": win},
        "h2h": {"FULL": {"obs": {"n": 100, "p_sd": 0.03}, "null": {}},
                "RECENT": {"obs": {"n": 100, "p_sd": 0.03}, "null": {}},
                "EARLIER": {"obs": {}, "null": {}}, "TRIGGER": {"obs": {}, "null": {}}},
        "totals_drift": drift, "h2h_drift": {},
    }}}


class TestTheDecisionRule:
    @pytest.mark.parametrize("outside,moved,expect,fires", [
        (True, True, "DRIFT", True),
        (True, False, "STANDING_MISCALIBRATION", False),
        (False, True, "WITHIN_NOISE_WITH_MOVEMENT", False),
        (False, False, "WITHIN_NOISE", False),
    ])
    def test_drift_needs_BOTH_clauses(self, outside, moved, expect, fires):
        """Either clause alone is not drift: outside-the-null without movement is a STANDING
        property of the champion; movement without either window being miscalibrated is two
        windows that are both fine."""
        v = M._decide(_decide_fixture(outside=outside, moved=moved))
        assert v["verdict"] == expect
        assert v["phase_2_fires"] is fires


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE STATISTICS
# ══════════════════════════════════════════════════════════════════════════════════════════════

class TestTheMultiplicityCorrection:
    """LOCK 5b. The first cut of this audit flagged a perfectly calibrated synthetic model 9 times
    in 20 because ~15 statistics were each tested at α=0.05 with no correction. These guards keep
    that from coming back."""

    def test_the_verdict_family_is_small_and_declared(self):
        body = _strip_comments(SRC)
        assert "VERDICT_STATS_TOTALS" in body and "VERDICT_STATS_H2H" in body
        assert len(M.VERDICT_STATS_TOTALS) + len(M.VERDICT_STATS_H2H) <= 8, (
            "the verdict family has grown — every added statistic costs family-wise error")

    def test_bh_is_stricter_than_uncorrected_alpha_and_still_rejects_a_real_signal(self):
        """Two-sided: a correction that rejects nothing is as useless as no correction.

        The failure this guards is ONE statistic scraping under a bare α=0.05 while the rest of the
        family is plainly null — the shape that produced the 9-in-20 false-positive rate.
        """
        lone = {"s0": 0.04, **{f"s{i}": 0.85 for i in range(1, 6)}}
        assert M.bh_reject(lone) == set(), (
            "one borderline p among five nulls must NOT be rejected — a bare α=0.05 would take it")
        real = {"s0": 0.0001, **{f"s{i}": 0.9 for i in range(1, 6)}}
        assert "s0" in M.bh_reject(real), "BH must still reject a genuinely tiny p-value"
        # ...and a family that is null all the way through stays empty.
        assert M.bh_reject({f"s{i}": 0.5 for i in range(6)}) == set()

    def test_a_disqualified_stratifier_removes_var_z_from_the_verdict_family(self):
        """⭐ The MH2.1 method lock, as a decision-rule clause: a partition that fails validation
        is REFUSED, not read with a caveat — so it must leave the family entirely."""
        def _t(valid):
            return {"totals": {"RECENT": {"stratifiers": {M.PRIMARY_STRATIFIER: {"valid": valid}}}}}
        fam_ok, note_ok = M._verdict_family(_t(True), "RECENT")
        fam_bad, note_bad = M._verdict_family(_t(False), "RECENT")
        assert "rms_var_z_sigma" in fam_ok and note_ok is None
        assert "rms_var_z_sigma" not in fam_bad
        assert note_bad and "DROPPED" in note_bad, "the removal must be stated, not silent"

    def test_the_correction_is_applied_AT_THE_DECISION_SITE_not_merely_available(self):
        """⭐ The RED proof caught this gap: `bh_reject` had its own unit test, so replacing the
        CALL in `_decide` with a bare `p < ALPHA` left the suite green — the clause was tested at
        the function while the defect lived at the call site (the NCAAF-P2.1 / E9.64 class).

        Deterministic fixture: ONE family member scrapes under a bare α=0.05 while the rest are
        plainly null — the exact shape that produced the 9-in-20 false-positive rate. It does not
        survive BH, so any verdict other than WITHIN_NOISE means the correction is not wired in.

        ⚠️ Deliberately NOT "every member at 0.045": BH is an FDR procedure and a family that is
        uniformly borderline IS collectively significant, so such a fixture would assert the
        opposite of BH's actual behaviour (a mistake this test was written wrong once already).
        """
        r = _decide_fixture(outside=False, moved=False)
        t = r["tiers"][M.PRIMARY_TIER]
        fam_t = [k for k in M.VERDICT_STATS_TOTALS if k != "rms_var_z_sigma"]
        for win in ("FULL", "RECENT"):
            t["totals"][win]["null"] = {
                k: {"evaluable": True, "outside_null": True,
                    "p_two_sided": 0.045 if i == 0 else 0.85}
                for i, k in enumerate(fam_t)}
            t["h2h"][win]["null"] = {
                k: {"evaluable": True, "outside_null": True, "p_two_sided": 0.85}
                for k in M.VERDICT_STATS_H2H}
        assert M._decide(r)["verdict"] == "WITHIN_NOISE", (
            "a lone p=0.045 among nulls must NOT clear BH at q=0.05 — a bare α=0.05 would take "
            "it, so the correction is not wired into the decision")

    def test_the_drift_clause_is_corrected_too(self):
        """The other half: an uncorrected drift clause over the same family re-introduces exactly
        the family-wise error the null clause's correction removes."""
        r = _decide_fixture(outside=True, moved=False)
        t = r["tiers"][M.PRIMARY_TIER]
        fam_t = [k for k in M.VERDICT_STATS_TOTALS if k != "rms_var_z_sigma"]
        t["totals_drift"] = {k: {"excludes_zero": True,
                                 "p_two_sided": 0.045 if i == 0 else 0.85}
                             for i, k in enumerate(fam_t)}
        assert M._decide(r)["drift_excludes_zero"]["totals"] == [], (
            "a lone borderline drift p-value must not clear BH either")

    @pytest.mark.slow
    def test_a_rep_count_too_small_for_the_correction_to_bind_is_REFUSED(self):
        """⭐ Below the vacuity floor no statistic can ever clear BH, so the audit would return
        WITHIN_NOISE for every input — including a catastrophically broken model. A study whose
        headline is a null must refuse to run in a configuration that could not have contradicted
        it (NF1.7 (a))."""
        floor = M.min_null_reps()
        m = len(M.VERDICT_STATS_TOTALS) + len(M.VERDICT_STATS_H2H)
        # the floor is exactly the boundary: at it the smallest achievable p REACHES BH's
        # strictest threshold; one rep below, it cannot — so the machine could never fire.
        assert 2.0 / (floor + 1) <= M.FDR_Q / m
        assert 2.0 / floor > M.FDR_Q / m
        with pytest.raises(RuntimeError, match="vacuity floor"):
            M.run(frame=_frame(), reps=floor - 1)
        # ...and the PRODUCTION default is comfortably above it, or the real verdict was vacuous.
        # Read from source, not from `M.N_NULL` — run() mutates that global, so a prior test in
        # the same process could make this assertion pass for the wrong reason.
        m = re.search(r"^N_NULL = (\d+)", _strip_comments(SRC), re.M)
        assert m and int(m.group(1)) > floor

    def test_a_monte_carlo_p_value_can_never_be_exactly_zero(self):
        """⭐ A p of exactly 0 survives ANY multiplicity correction, so the naive estimator made
        BH decorative for the most extreme (i.e. most consequential) statistic in every window."""
        draws = np.linspace(0.0, 1.0, 200)
        assert M.mc_pvalue(draws, 99.0) > 0.0
        assert M.mc_pvalue(draws, -99.0) > 0.0
        assert M.mc_pvalue(draws, 99.0) == pytest.approx(2.0 / 201.0)
        assert M.mc_pvalue(draws, 0.5) > 0.5      # dead centre is not evidence of anything

    def test_a_verdict_stat_outside_the_family_cannot_drive_the_verdict(self):
        """Isolating fixture: the ONLY flagged statistic is one deliberately left out of the
        declared family, so nothing else can explain a WITHIN_NOISE verdict."""
        r = _decide_fixture(outside=False, moved=False)
        t = r["tiers"][M.PRIMARY_TIER]
        assert "crps" not in M.VERDICT_STATS_TOTALS
        for win in ("FULL", "RECENT"):
            t["totals"][win]["null"]["crps"] = {"evaluable": True, "outside_null": True,
                                                "p_two_sided": 1e-9}
        t["totals_drift"]["crps"] = {"excludes_zero": True}
        assert M._decide(r)["verdict"] == "WITHIN_NOISE"


class TestStatistics:
    def test_randomized_pit_is_uniform_under_a_correct_predictive_and_not_under_a_wrong_one(self):
        """Two-sided: a PIT that is 'uniform' on everything measures nothing."""
        from scipy.stats import kstest
        rng = np.random.default_rng(3)
        n = 20_000
        mu = rng.normal(9.0, 0.6, n)
        sg = np.full(n, 4.3)
        y_ok = np.round(rng.normal(mu, sg))
        assert kstest(M.randomized_pit(y_ok, mu, sg, rng), "uniform").pvalue > 0.01
        y_bad = np.round(rng.normal(mu, sg * 1.4))
        assert kstest(M.randomized_pit(y_bad, mu, sg, rng), "uniform").pvalue < 1e-6

    def test_crps_is_minimised_at_the_true_sigma(self):
        """A proper score, so a mis-scaled σ must cost — otherwise it cannot rank σ models."""
        rng = np.random.default_rng(4)
        mu = np.zeros(40_000)
        y = rng.normal(0, 3.0, 40_000)
        at = {s: float(np.mean(M.crps_normal(y, mu, np.full_like(y, s))))
              for s in (2.0, 2.5, 3.0, 3.5, 4.5)}
        assert min(at, key=at.get) == 3.0

    def test_the_randomized_pit_coverage_is_the_honest_one_at_any_sigma(self):
        """E2.1-r: inclusive integer bounds inflate a correctly-specified COUNT model's coverage,
        which is how a coverage TARGET can reward under-dispersion.

        Two-sided, because the size of that inflation depends on σ and the study must not claim it
        where it does not bite: at the served totals σ (≈4.3 runs) the integer grid is fine
        relative to the interval and the naive read is barely biased, whereas at a small σ it is
        badly biased. The randomized-PIT read is correct in BOTH regimes — which is why it, and
        not the naive one, is what the audit reports.
        """
        rng = np.random.default_rng(5)
        n = 60_000
        mu = rng.normal(9.0, 0.6, n)

        served = M.totals_stats(np.round(rng.normal(mu, 4.3)), mu, np.full(n, 4.3), rng)
        assert abs(served["cov80"] - 0.80) < 0.01
        assert served["cov80_integer_inclusive"] > served["cov80"], (
            "the inclusive-integer read must sit ABOVE the honest one — that is the E2.1-r trap")

        tight = M.totals_stats(np.round(rng.normal(mu, 0.8)), mu, np.full(n, 0.8), rng)
        assert abs(tight["cov80"] - 0.80) < 0.01, "the randomized PIT stays honest at small σ"
        assert tight["cov80_integer_inclusive"] - 0.80 > 0.05, (
            "at small σ the inflation must be LARGE — a correctly specified model scoring ~0.9 "
            "against a 0.80 target is exactly how the trap rewards under-dispersion")
        assert (tight["cov80_integer_inclusive"] - 0.80) > (served["cov80_integer_inclusive"] - 0.80), (
            "and the inflation must GROW as σ shrinks relative to the integer grid")

    def test_rms_var_z_is_anchored_on_the_analytic_truth_not_the_incumbent(self):
        """MH2.1 (b): an incumbent-relative metric inverts whenever the incumbent is the defective
        one. A perfectly specified z must score ~0 in absolute terms."""
        rng = np.random.default_rng(6)
        z = rng.normal(0, 1, 6000)
        lab = M._bin_labels(rng.uniform(size=6000), 5)
        rms, rows = M.rms_var_z(z, lab)
        assert rms < 4 * M.metric_noise_floor([r["n"] for r in rows])
        rms_bad, _ = M.rms_var_z(z * 1.5, lab)
        assert rms_bad > rms

    def test_murphy_decomposition_reconstructs_the_brier_score(self):
        rng = np.random.default_rng(8)
        p = np.clip(rng.normal(0.52, 0.08, 4000), 0.02, 0.98)
        y = rng.binomial(1, p).astype(float)
        s = M.h2h_stats(y, p)
        assert s["brier"] == pytest.approx(
            s["reliability"] - s["resolution"] + s["uncertainty"], abs=2e-3)


class TestTheReport:
    @pytest.mark.slow
    def test_a_null_verdict_is_reported_together_with_its_MDE(self):
        """NF1.8 / MH2: 'no defect found' means 'no defect larger than the MDE'. A null without a
        power statement is a shrug, not a measurement."""
        r = M.run(frame=_frame(), reps=GUARD_REPS, power_reps=60)
        assert r["verdict"]["verdict"] == "WITHIN_NOISE"
        pw = r["tiers"]["post_lineup"]["power"]["RECENT"]["sigma_scale"]
        assert pw["evaluable"] is True and pw["curve"], "the MDE curve must actually be computed"
        assert max(pw["curve"].values()) >= M.TARGET_POWER, (
            "the power curve never reaches the target — the MDE would be unreportable")
