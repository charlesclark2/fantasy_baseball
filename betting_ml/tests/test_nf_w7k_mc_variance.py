"""NF-W7k guards — the Monte-Carlo variance gate that decides whether QB's `dsr_ok` refusal is
reachable by a lower-variance design.

⭐ WHAT THESE GUARDS DEFEND. The decision is a governance-adjacent DSR re-read, and its dangerous
failure is a FALSE STOP: a decomposition that reports zero Monte-Carlo error (a dead seed), or a
`het_var` silently clamped at zero (an infinite ceiling), or a projection that quietly deflates a
different object than NF-W7f scored, would each close the last remaining lever on arithmetic rather
than on evidence. Each of those is pinned here, and every clause is RED-proven on deliberately
broken source by `red_proof_nf_w7k.py`.

⚠️ ISOLATING FIXTURES (NF-D17). Several clauses live inside `and`-composed decision rules, so each
fixture is built to satisfy EVERY OTHER clause — only the clause under test can flip the result.
A fixture that trips two clauses proves neither.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_mc_variance as MV

_ROOT = Path(__file__).resolve().parents[2]
_FANTASY = _ROOT / "quant_sports_intel_models" / "football" / "nfl" / "fantasy"
_W7F = _FANTASY / "ablation_results" / "nf_w7f_qb_marginal.json"
_ARMS = ("zm_conditional", "zm_floor", "zm_climatology", "zm_over")
_WINNER, _FOIL = "zm_floor", "mixall_learned"


def _w7f_deltas() -> dict[str, np.ndarray]:
    """NF-W7f's OWN per-fold `(best_foil − arm)` series, read from the committed record."""
    rec = json.loads(_W7F.read_text())
    mat = {f["label"]: f["positions"]["QB"]["scores"] for f in rec["fold_results"]}
    folds = sorted(mat)
    return {a: np.asarray([mat[f][_FOIL] - mat[f][a] for f in folds], dtype=float) for a in _ARMS}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The registered identities (prereg §3.2, §3.3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRegisteredIdentities:
    def test_projection_at_the_observed_sds_reproduces_nf_w7f_exactly(self):
        """prereg §3.2 — the NO-OP identity. A projection that cannot return the UNprojected
        number is not measuring the same object (the NF-W7f `matched_foil_identity` shape)."""
        base = _w7f_deltas()
        obs = {a: float(v.std(ddof=1)) for a, v in base.items()}
        g = MV.project_gate(base, obs, _WINNER)
        assert g["dsr"] == 0.0, f"NF-W7f recorded DSR 0.0; the no-op projection returned {g['dsr']}"
        assert g["winner_sharpe"] == pytest.approx(1.013, abs=5e-4)
        assert g["sr0"] == pytest.approx(5.482, abs=5e-4)
        assert g["p_one_sided"] == pytest.approx(0.0121, abs=5e-5)

    def test_rescale_preserves_mean_and_every_standardized_shape_moment(self):
        """`deflated_sharpe` reads skew and kurtosis through its `denom`, so a projection that
        moved them would be deflating a differently-shaped series than the one under test."""
        from scipy.stats import kurtosis, skew

        d = np.array([0.4, -0.1, 0.9, 0.05, 0.2, -0.3, 1.4, 0.1])
        out = MV.rescale_to_sd(d, 0.05)
        assert out.mean() == pytest.approx(d.mean(), abs=1e-12)
        assert out.std(ddof=1) == pytest.approx(0.05, abs=1e-12)
        assert skew(out) == pytest.approx(skew(d), abs=1e-9)
        assert kurtosis(out, fisher=False) == pytest.approx(kurtosis(d, fisher=False), abs=1e-9)

    def test_the_winners_projected_sharpe_is_monotone_in_the_draw_count(self):
        """prereg §3.3 — removing Monte-Carlo error can only RAISE |SR|, so a non-monotone
        projection is a coding defect and must RAISE rather than be reported as a finding."""
        base = _w7f_deltas()
        dec = {a: {"mc_var": 0.4 * float(v.var(ddof=1)), "het_var": 0.6 * float(v.var(ddof=1))}
               for a, v in base.items()}
        rep = MV.ceiling_report(base, dec, _WINNER)
        srs = [r["winner_sharpe"] for r in rep["rungs"]]
        assert srs == sorted(srs), f"projected Sharpe is not monotone in draws: {srs}"

    def test_a_non_monotone_projection_raises_rather_than_reporting_a_finding(self):
        base = _w7f_deltas()
        # a NEGATIVE mc_var makes sd grow with k — the coding-defect signature the clause catches
        dec = {a: {"mc_var": -abs(float(v.var(ddof=1))), "het_var": float(v.var(ddof=1))}
               for a, v in base.items()}
        with pytest.raises(ValueError, match="monotone"):
            MV.ceiling_report(base, dec, _WINNER)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The decomposition itself — the FALSE-STOP surface
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDecompositionCannotManufactureAFalseStop:
    def test_het_var_is_returned_signed_and_never_clamped(self):
        """⭐ THE DANGEROUS DIRECTION. If `het_var` were silently clamped to 0 when the estimate
        goes negative, `projected_sd(k=inf)` would return 0, the ceiling Sharpe would be infinite,
        and the story would report a FUND it had not earned. The sign must survive."""
        # ⛔ THE FIXTURE MUST GUARANTEE A NEGATIVE ESTIMATE, or a clamp passes it vacuously — the
        # RED proof caught exactly that. Constructed, not sampled: every fold carries the SAME
        # seed MEAN (so `between_var` is exactly 0) with real within-fold spread, hence
        # `het_var = 0 − mc_var/S < 0` by arithmetic on every run.
        by_fold = {f"f{i}": [0.02 - 0.05, 0.02 + 0.05, 0.02 - 0.03, 0.02 + 0.03, 0.02]
                   for i in range(8)}
        d = MV.decompose(by_fold)
        assert d["between_var"] == pytest.approx(0.0, abs=1e-15)
        assert d["mc_var"] > 0.0, "the fixture must carry real within-fold spread"
        assert d["het_var"] < 0.0, (
            f"het_var is {d['het_var']} — a clamped estimate makes the ceiling sd 0, the ceiling "
            f"Sharpe infinite, and manufactures a FUND the evidence never earned")
        assert d["het_var_is_negative"] is True
        assert d["het_sd"] is None, "a negative heterogeneity variance has no real sd"
        # and the ceiling must NOT become infinitely reachable off a negative estimate
        assert MV.projected_sd(d["mc_var"], d["het_var"], float("inf")) == 0.0
        assert MV.projected_sd(d["mc_var"], d["het_var"], 1.0) > 0.0

    def test_mc_variance_is_the_within_fold_across_seed_spread(self):
        """The MC component must be the WITHIN-fold spread. Reading an across-fold quantity here
        would import season-to-season signal into the term the ceiling removes."""
        by_fold = {"a": [1.0, 1.0, 1.0], "b": [5.0, 5.0, 5.0], "c": [9.0, 9.0, 9.0]}
        d = MV.decompose(by_fold)
        assert d["mc_var"] == pytest.approx(0.0, abs=1e-15)
        assert d["between_var"] > 1.0, "the across-fold spread must survive in `between_var`"

    def test_a_decomposition_refuses_unbalanced_or_single_seed_input(self):
        with pytest.raises(ValueError, match="SAME number of seeds"):
            MV.decompose({"a": [1.0, 2.0], "b": [1.0]})
        with pytest.raises(ValueError, match="SAME number of seeds"):
            MV.decompose({"a": [1.0], "b": [2.0]})

    def test_a_decomposition_refuses_fewer_than_two_folds(self):
        with pytest.raises(ValueError, match="≥2 folds"):
            MV.decompose({"only": [1.0, 2.0, 3.0]})

    def test_the_seed_stride_cannot_alias_either_rng_stream(self):
        """⭐ A DEAD SEED IS THE FALSE-STOP. The assembly draws from `seed + row_block_start` and
        the availability Bernoulli from `seed + 1_000_000 + row_block_start`. If two seeds could
        land on the same stream the across-seed spread would read ZERO and the ceiling would look
        infinitely reachable — or, worse, `σ²_MC` would read 0 and the lever would be closed on a
        measurement that never happened."""
        from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX

        # every stream index a single seed can reach: `seed + offset + block_start`, where the
        # offset is 0 (the copula normals) or AVAIL_STREAM_OFFSET (the availability Bernoulli),
        # and block starts are multiples of ROW_BLOCK across the fold's rows
        from quant_sports_intel_models.football.nfl.fantasy import (
            fp_qb_marginal_calibration as QM,
        )

        max_rows = 4096                       # far above any real QB test block (~700 rows)
        blocks = {QM.ROW_BLOCK * i for i in range(max_rows // QM.ROW_BLOCK + 1)}
        offsets = {0, MX.AVAIL_STREAM_OFFSET}
        reachable = {o + b for o in offsets for b in blocks}
        span = max(reachable) - min(reachable)
        assert MV.SEED_STRIDE > span, (
            f"seed stride {MV.SEED_STRIDE} does not exceed the reachable stream span {span} — two "
            f"seeds could share a stream and report zero Monte-Carlo error")
        assert len(set(MV.SEEDS)) == MV.N_SEEDS == len(MV.SEEDS)
        assert MV.SEEDS[0] == MV.BASE_SEED, "the BASE seed must be NF-W7f's, or nothing pins"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The scaling law — the extrapolation the whole decision rests on
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestScalingLawIsMeasuredNotAssumed:
    def test_a_clean_one_over_d_law_lands_in_the_registered_band(self):
        s = MV.scaling_check(4.0e-6, 1000, 1.0e-6, 4000)
        assert s["evaluable"] and s["holds"] and s["ratio"] == pytest.approx(4.0)

    def test_a_law_the_data_does_not_obey_is_refused(self):
        assert not MV.scaling_check(1.05e-6, 1000, 1.0e-6, 4000)["holds"], "ratio 1.05 is flat"
        assert not MV.scaling_check(5.0e-5, 1000, 1.0e-6, 4000)["holds"], "ratio 50 is not 1/D"

    def test_a_zero_primary_variance_is_unevaluable_and_never_scored_as_holding(self):
        """NF1.7 (a) — a ratio that could not be computed is not a pass."""
        s = MV.scaling_check(1.0e-6, 1000, 0.0, 4000)
        assert s["evaluable"] is False and s["holds"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered decision rule (prereg §3) — isolating fixtures, one clause each
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ok_scaling() -> dict:
    return MV.scaling_check(4.0e-6, 1000, 1.0e-6, 4000)


def _rungs(dsrs: list[float]) -> list[dict]:
    # ⛔ the identity row carries the CURRENT draw count; if `decide` were to read it as a rung it
    # could "fund" a re-run at exactly the count that already failed. It is `kind`-tagged, and the
    # fixture reproduces that tagging so the clause is tested as it is actually called.
    out = [{"label": "observed (no-op identity)", "draws": 4000, "k": None,
            "kind": "identity", "dsr": 0.0},
           {"label": "4,000 (reconstructed)", "draws": 4000, "k": 1.0,
            "kind": "reconstruction", "dsr": 0.0}]
    out += [{"label": f"{d:,}", "draws": d, "k": d / 4000, "kind": "ladder", "dsr": v}
            for d, v in zip(MV.DRAW_LADDER, dsrs)]
    out += [{"label": "ceiling (∞ draws)", "draws": None, "k": float("inf"),
             "kind": "ceiling", "dsr": max(dsrs)}]
    return out


class TestTheDecisionRule:
    def test_a_ceiling_below_the_bar_closes_the_lever_and_publishes_no_retest_trigger(self):
        """⛔ NF-D18: the ceiling is what NO draw count can beat, so a draw/fold/season re-test
        trigger here would be the actively misleading direction."""
        d = MV.decide(_ok_scaling(), 0.31, {"evaluable": True, "lo": 0.05, "hi": 0.62},
                      _rungs([0.1, 0.2, 0.3]), 0.95)
        assert d["verdict"] == "MC_LEVER_EXHAUSTED"
        assert d["fund_phase_b"] is False and d["d2"] is None
        assert d["publishes_retest_trigger"] is False

    def test_the_decision_reads_the_UPPER_end_of_the_ceiling_ci(self):
        """The honest question is whether the lever COULD clear, so the gate refuses only when
        even the optimistic end fails. A point estimate below the bar with an upper end above it
        must FUND, not STOP."""
        d = MV.decide(_ok_scaling(), 0.42, {"evaluable": True, "lo": 0.10, "hi": 0.97},
                      _rungs([0.90, 0.96, 0.99]), 0.95)
        assert d["verdict"] == "FUND_HIGH_DRAW_RUN"

    def test_funding_picks_the_smallest_ladder_rung_that_clears(self):
        d = MV.decide(_ok_scaling(), 0.99, {"evaluable": True, "lo": 0.96, "hi": 0.999},
                      _rungs([0.80, 0.97, 0.99]), 0.95)
        assert d["fund_phase_b"] is True and d["d2"] == 64_000

    def test_d2_is_never_the_draw_count_that_already_failed(self):
        """⭐ ISOLATING FIXTURE (NF-D17). The identity and reconstruction rows carry the CURRENT
        draw count, so if `decide` read them as ladder rungs it could "fund" a re-run at exactly
        the 4,000 draws that already failed — a no-op dressed as a remedy. Here they are made to
        clear the bar (which only a ladder-only filter can ignore), while the ladder itself clears
        at its FIRST rung, so nothing but the filter can decide the answer."""
        rungs = _rungs([0.98, 0.99, 0.995])
        for r in rungs:
            if r["kind"] in ("identity", "reconstruction"):
                r["dsr"] = 0.97
        d = MV.decide(_ok_scaling(), 0.99, {"evaluable": True, "lo": 0.96, "hi": 0.999},
                      rungs, 0.95)
        assert d["fund_phase_b"] is True
        assert d["d2"] == 16_000, (
            f"D2 is {d['d2']} — funding the draw count that already failed is a no-op dressed as "
            f"a remedy")

    def test_funding_falls_back_to_the_registered_cap_when_no_rung_clears(self):
        d = MV.decide(_ok_scaling(), 0.99, {"evaluable": True, "lo": 0.96, "hi": 0.999},
                      _rungs([0.10, 0.20, 0.30]), 0.95)
        assert d["d2"] == MV.DRAW_LADDER[-1], "the cap is registered; the run cannot exceed it"

    def test_a_broken_scaling_law_withholds_a_verdict_rather_than_producing_one(self):
        """⭐ ISOLATING FIXTURE (NF-D17): the ceiling CI here is EMPHATICALLY passing (hi 0.999),
        so only the scaling clause can flip the result. G2 must WITHHOLD — not fall through to
        `MC_LEVER_EXHAUSTED`, which would close the lever on an invalid extrapolation."""
        bad = MV.scaling_check(1.02e-6, 1000, 1.0e-6, 4000)
        d = MV.decide(bad, 0.99, {"evaluable": True, "lo": 0.97, "hi": 0.999},
                      _rungs([0.99, 0.99, 0.99]), 0.95)
        assert d["verdict"] == "UNDEFINED_SCALING"
        assert d["fund_phase_b"] is False, "an invalid extrapolation must fund nothing"

    def test_an_unevaluable_ceiling_ci_withholds_a_verdict(self):
        """NF1.7 (a) — a CI that could not be computed is neither a pass nor a refusal. The
        scaling clause is passing here, so only the CI clause can flip it."""
        d = MV.decide(_ok_scaling(), None, {"evaluable": False, "reason": "too few resamples"},
                      _rungs([0.1, 0.2, 0.3]), 0.95)
        assert d["verdict"] == "UNDEFINED_CEILING_CI" and d["fund_phase_b"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The projection must cover the WHOLE field (or `SR0` mixes projected and unprojected trials)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestProjectionCoversTheDeclaredField:
    def test_a_partially_projected_field_is_refused(self):
        base = _w7f_deltas()
        partial = {a: float(v.std(ddof=1)) for a, v in base.items() if a != "zm_over"}
        with pytest.raises(ValueError, match="every arm in the field must be projected"):
            MV.project_gate(base, partial, _WINNER)

    def test_a_winner_outside_the_field_is_refused(self):
        base = _w7f_deltas()
        obs = {a: float(v.std(ddof=1)) for a, v in base.items()}
        with pytest.raises(KeyError, match="not among the scored arms"):
            MV.project_gate(base, obs, "an_arm_that_was_never_scored")

    def test_the_field_is_nf_w7fs_declared_four_arms_with_no_trim(self):
        """MH2.2 — the admissible remedy for a DSR failure is never a field you have already
        scored and then cut. This story re-measures the SAME declared field."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            fp_qb_marginal_calibration as QM,
        )
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w7k_mc_variance as W7K,
        )

        assert tuple(QM.REAL_ARMS) == _ARMS
        assert tuple(W7K.SCORED_LABELS) == tuple(QM.ELIGIBLE)
        assert set(QM.REAL_ARMS) <= set(W7K.SCORED_LABELS)


class TestRequiredMcShareSensitivity:
    """The sensitivity is arithmetic on NF-W7f's published series and appears in the record, so it
    is guarded like anything else that is published — but it is NOT the decision, and these
    clauses check exactly that it does not pretend to be."""

    def test_it_names_its_assumption(self):
        """A sensitivity computed under an assumption must SAY SO in its own payload — a reader
        who sees only the number cannot know it is not a measurement."""
        base = _w7f_deltas()
        r = MV.required_mc_share_for_ceiling(base, _WINNER, 0.95)
        assert "COMMON absolute Monte-Carlo sd" in r["assumption"]

    def test_zero_assumed_mc_reproduces_the_observed_gate(self):
        """The sweep's origin must be NF-W7f's own number, or the curve is anchored on nothing."""
        base = _w7f_deltas()
        r = MV.required_mc_share_for_ceiling(base, _WINNER, 0.95)
        first = r["curve"][0]
        assert first["mc_share_of_winner_var"] < 0.01
        assert first["dsr"] == 0.0, "at ~zero assumed Monte-Carlo error the gate must be W7f's"

    def test_the_bar_rises_with_the_sharpe_across_the_sweep(self):
        """⭐ The structural fact the pre-registration turns on: `SR0` is not a constant the winner
        climbs toward — the winner is one of the trials it is built from, so the bar climbs too."""
        base = _w7f_deltas()
        curve = MV.required_mc_share_for_ceiling(base, _WINNER, 0.95)["curve"]
        assert curve[-1]["sr0"] > curve[0]["sr0"], "the deflation benchmark must move with the field"
        assert curve[-1]["winner_sharpe"] > curve[0]["winner_sharpe"]

    def test_a_threshold_is_reported_as_absent_rather_than_invented_when_none_exists(self):
        """NF1.7 (a) — an unreachable bar must read as `threshold_exists: False`, never as a
        silently-clamped number a reader would take for a real requirement."""
        base = _w7f_deltas()
        r = MV.required_mc_share_for_ceiling(base, _WINNER, dsr_min=1.0001)
        assert r["threshold_exists"] is False
        assert r["required_mc_share_of_winner_var"] is None
        assert r["required_mc_sd"] is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# End-to-end over the verdict layer — the BASE seed IS NF-W7f's stored scores
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _synthetic_run(mc_sd: float, seed: int = 11) -> dict:
    """A full NF-W7k artifact whose BASE-seed scores are NF-W7f's STORED scores byte-for-byte, with
    the other seeds perturbed by Monte-Carlo noise of a known size.

    ⭐ This is what makes the end-to-end test real rather than a restatement: G0's reproduction pin
    is exercised against the genuine committed record, so a projection that silently deflated a
    re-derivation would fail here exactly as it would in production."""
    rec = json.loads(_W7F.read_text())
    mat = {f["label"]: f["positions"]["QB"]["scores"] for f in rec["fold_results"]}
    folds = sorted(mat)
    labels = list(_ARMS) + ["mixall_learned", "single_copula"]
    rng = np.random.default_rng(seed)
    scores: dict[str, dict] = {}
    for draws in (4000, 1000):
        scale = mc_sd * math.sqrt(4000 / draws)     # the 1/D law, injected exactly
        scores[str(draws)] = {}
        for f in folds:
            scores[str(draws)][f] = {}
            # ⭐ EVERY SEED IS EXCHANGEABLE, which is what the real run produces and what the
            # decomposition assumes. A first cut made the BASE seed noiseless and the others noisy
            # — i.e. it treated NF-W7f's published numbers as the latent TRUTH rather than as one
            # draw from it. That is not the object under study: NF-W7f's scores ARE a draw, and a
            # fixture that privileges them inflates `het_var` and can push the ceiling BELOW the
            # observed gate, which is the opposite of what removing noise does. So the latent
            # truth is BACKED OUT from the base seed's own perturbation, leaving the base-seed
            # scores exactly equal to the record (G0 still binds) with all five seeds i.i.d.
            noise = {(i, lab): rng.normal(0.0, scale) for i in range(len(MV.SEEDS))
                     for lab in labels}
            for i, s_ in enumerate(MV.SEEDS):
                exact = (draws == 4000 and i == 0)
                scores[str(draws)][f][str(s_)] = {
                    lab: (mat[f][lab] if exact
                          else mat[f][lab] - noise[(0, lab)] + noise[(i, lab)])
                    for lab in labels}
    return {"story": MV.STORY, "generated_at": "test", "position": "QB", "n_folds": len(folds),
            "base_seed": MV.BASE_SEED, "seeds": list(MV.SEEDS), "n_seeds": len(MV.SEEDS),
            "draws_primary": 4000, "draws_control": 1000, "scores": scores}


class TestEndToEndVerdictLayer:
    def test_the_reproduction_pin_passes_against_nf_w7fs_own_record(self, tmp_path):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7k_mc_variance as W7K

        out = W7K.derive_verdict_layer(_synthetic_run(mc_sd=2e-4))
        repro = out["verdict"]["checks"]["G0_reproduction_pin"]
        assert repro["evaluable"] and repro["reproduces"], repro
        assert repro["n_compared"] == 8 * 6, "all 8 folds × 6 labels must be compared"
        # and the report renders
        W7K.write_report(out, tmp_path / "r.md")
        text = (tmp_path / "r.md").read_text()
        assert out["verdict"]["story_verdict"] in text
        assert "DEPLOY-HELD" in text and "best_alpha" in text
        assert "no-op identity" in text, "the registered identity must be visible in the record"

    def test_a_drifted_base_seed_fails_the_reproduction_pin(self):
        """⭐ G0's whole job. If the base-seed re-score does not reproduce NF-W7f, the whole
        decomposition would describe a re-derivation rather than the object NF-W7f scored."""
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7k_mc_variance as W7K

        run = _synthetic_run(mc_sd=2e-4)
        f0 = sorted(run["scores"]["4000"])[0]
        run["scores"]["4000"][f0][str(MV.BASE_SEED)]["zm_floor"] += 1e-6
        # ⛔ a REAL run must REFUSE, not record-and-continue: publishing a decision derived from an
        # object the run just failed to authenticate is the decorative-guard failure.
        with pytest.raises(ValueError, match="G0 FAILED"):
            W7K.derive_verdict_layer(dict(run, smoke=False))
        # a path proof is exempt by construction (its draw counts are not NF-W7f's), and there the
        # failure must still be RECORDED rather than silently dropped
        repro = W7K.derive_verdict_layer(dict(run, smoke=True))["verdict"]["checks"][
            "G0_reproduction_pin"]
        assert repro["reproduces"] is False and repro["max_abs_gap"] >= 1e-7

    def test_a_dead_seed_is_caught_by_G1_rather_than_reported_as_zero_mc_error(self):
        """⭐ THE FALSE-STOP. A seed that never reaches the draws makes every score identical, so
        `σ²_MC` reads 0, the ceiling equals the observed gate, and the lever gets closed on a
        measurement that never happened. G1 must catch it."""
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7k_mc_variance as W7K

        run = _synthetic_run(mc_sd=2e-4)
        for lvl in run["scores"]:
            for f in run["scores"][lvl]:
                base = run["scores"][lvl][f][str(MV.BASE_SEED)]
                for s in run["scores"][lvl][f]:
                    run["scores"][lvl][f][s] = dict(base)
        with pytest.raises(ValueError, match="G1 FAILED"):
            W7K.derive_verdict_layer(dict(run, smoke=False))
        live = W7K.derive_verdict_layer(dict(run, smoke=True))["verdict"]["checks"][
            "G1_seed_is_live"]
        assert live["holds"] is False and live["zero_spread_cells"]

    def test_a_large_injected_mc_error_moves_the_ceiling_above_the_observed_gate(self):
        """A two-sided control: the instrument must RESPOND. With a large Monte-Carlo component
        the ceiling's Sharpe must exceed the observed one — an instrument that returned the same
        number either way could not distinguish a live lever from a dead one."""
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7k_mc_variance as W7K

        out = W7K.derive_verdict_layer(_synthetic_run(mc_sd=6e-3))
        rungs = out["verdict"]["ceiling"]["rungs"]
        by_kind = {r["kind"]: r for r in rungs}
        # ⛔ the comparison is RECONSTRUCTION → CEILING, never IDENTITY → ceiling. Both of the
        # former are built from the pooled decomposition, so they differ ONLY in `k`; the identity
        # row is the base-seed realization's own sd, which is a different estimate of the same
        # quantity and can be luckier or unluckier than typical. Comparing across the two would
        # test sampling luck rather than the instrument.
        assert (by_kind["ceiling"]["winner_sharpe"]
                > by_kind["reconstruction"]["winner_sharpe"] + 1e-6), (
            "removing a large injected Monte-Carlo component must RAISE the winner's Sharpe")
        assert out["verdict"]["decomposition_primary"]["zm_floor"]["mc_sd"] > 1e-3

    def test_removing_noise_raises_the_BAR_as_well_as_the_sharpe(self):
        """⭐ THE STRUCTURAL POINT the pre-registration turns on (§3.1). `SR0` is built from the
        DISPERSION of the four arms' Sharpes and the winner is one of those four trials, so
        shrinking Monte-Carlo error moves the Sharpe **and** the benchmark together. An instrument
        that held `SR0` fixed while raising the Sharpe would overstate the lever every time."""
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7k_mc_variance as W7K

        out = W7K.derive_verdict_layer(_synthetic_run(mc_sd=6e-3))
        by_kind = {r["kind"]: r for r in out["verdict"]["ceiling"]["rungs"]}
        assert by_kind["ceiling"]["sr0"] > by_kind["reconstruction"]["sr0"], (
            "the deflation benchmark must move with the field it is computed over")

    def test_the_verdict_layer_never_certifies_qb(self):
        """No path through this story sets a certification. `FUND` funds a MEASUREMENT."""
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7k_mc_variance as W7K

        for mc in (2e-4, 6e-3):
            out = W7K.derive_verdict_layer(_synthetic_run(mc_sd=mc))
            assert out["verdict"]["certified_for_nf_w8"] is False
            assert out["verdict"]["dsr_min"] == 0.95, "the bar is UNCHANGED (E2.1-r)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registration is the contract — it must exist and must have been fixed in advance
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPreregistrationIsTheContract:
    def test_the_registered_knobs_match_the_instrument(self):
        prereg = (_FANTASY / "ablation_results" / "nf_w7k_preregistration.md").read_text()
        assert "20260818" in prereg and "7_000_003" in prereg
        assert "4,000" in prereg and "1,000" in prereg
        for rung in MV.DRAW_LADDER:
            assert f"{rung:,}" in prereg, f"ladder rung {rung} is not registered"
        assert "[2.0, 8.0]" in prereg, "the scaling band must be registered forward"
        assert str(MV.N_SEEDS) in prereg

    def test_the_ceiling_binds_over_the_mc_share_proxy(self):
        """prereg §3.1 — registered FORWARD because the disagreement is foreseeable: the winner is
        one of the trials `SR0` is built from, so shrinking noise raises the Sharpe AND the bar."""
        prereg = (_FANTASY / "ablation_results" / "nf_w7k_preregistration.md").read_text()
        assert "G3` binds" in prereg or "G3 binds" in prereg
