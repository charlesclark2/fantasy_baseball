"""DSR-CONV — guards for the degenerate-exclusion convention.

⭐ THE CONVENTION, IN ONE LINE: a pre-registered lose-by-construction degenerate stays in `n_trials`
(we DID try it — multiplicity is owed) and leaves `V` (its distance from the incumbent is a DESIGN
quantity, not a measurement of how real configurations disperse). Symmetric with the incumbent, which
`dsr_gate` already treats exactly this way.

⛔ AND THE CONSTRAINT THAT MATTERS AS MUCH AS THE FEATURE: it is FORWARD-ONLY. The last class of test
here pins that the change CANNOT re-decide a recorded verdict — neither by rewriting an artifact nor
by being retro-wired into a story's recorded harness.

Every guard in this file was RED-proven against deliberately-broken source before being trusted
(the INC-38 / NF1.7 (a) discipline: a guard that cannot fail is worse than no guard). See
`test_the_guards_in_this_file_are_not_vacuous` for the ones that can be proven in-process.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from betting_ml.scripts.e7_9_train_serve_consistency import dsr_gate
from betting_ml.utils.cv_power import classify_null

REPO = Path(__file__).resolve().parents[2]


def _field(*, n_folds: int = 8, seed: int = 11, n_cand: int = 4,
           degenerate_offset: float | None = None) -> dict[str, list[float]]:
    """A synthetic field of per-fold scores (LOWER is better), optionally with one designed loser."""
    rng = np.random.default_rng(seed)
    inc = rng.normal(1.0, 0.10, n_folds)
    out: dict[str, list[float]] = {"incumbent": list(inc)}
    for i in range(n_cand):
        out[f"cand_{i}"] = list(inc - rng.normal(0.03, 0.05, n_folds))
    if degenerate_offset is not None:
        # loses by a large, CONSISTENT amount — the shape that inflates V
        out["degenerate"] = list(inc + rng.normal(degenerate_offset, 0.01, n_folds))
    return out


# ── 1. multiplicity is charged; dispersion is not ────────────────────────────────────────────────

def test_a_degenerate_counts_toward_multiplicity_but_not_toward_V():
    """The whole convention in one assertion."""
    scores = _field(degenerate_offset=0.9)
    g = dsr_gate(scores, "incumbent", "cand_0", n_trials=len(scores),
                 degenerate_arms=("degenerate",))

    # n_trials is the FULL field — the degenerate still costs multiplicity.
    assert g["n_trials"] == len(scores) == 6

    # ...but it is NOT one of the arms whose dispersion V measures.
    assert "degenerate" not in g["v_trial_arms"]
    assert g["declared_degenerate_arms"] == ["degenerate"]
    # it is still REPORTED as a trial — excluded from V is not excluded from the record
    assert "degenerate" in g["trial_arms"]

    # and V is genuinely smaller for it
    assert g["var_trials_sr"] < g["var_trials_sr_with_degenerates"]
    assert g["sr0"] < g["sr0_with_degenerates_in_V"]
    assert g["binds"] == "degenerate_excluded_whole_field"


def test_the_binding_figure_is_the_degenerate_excluded_one_and_both_are_reported():
    """Item 1's reporting obligation: BOTH conventions on every run, and which BINDS."""
    g = dsr_gate(_field(degenerate_offset=0.9), "incumbent", "cand_0", n_trials=6,
                 degenerate_arms=("degenerate",))
    assert g["dsr"] == pytest.approx(g["dsr_degenerate_excluded"])
    assert g["dsr"] != pytest.approx(g["dsr_with_degenerates_in_V"])
    for k in ("dsr_with_degenerates_in_V", "dsr_degenerate_excluded", "binds",
              "sr0_with_degenerates_in_V", "var_trials_sr_with_degenerates"):
        assert k in g, f"{k} must be reported on EVERY run, not only when degenerates exist"


def test_multiplicity_is_still_really_charged_through_z_N():
    """⚠️ The companion to the V test: if `n_trials` had quietly dropped the degenerate, the bar
    would fall through `z(N)` too. Growing `n_trials` alone must still RAISE the bar."""
    scores = _field(degenerate_offset=0.9)
    small = dsr_gate(scores, "incumbent", "cand_0", n_trials=6, degenerate_arms=("degenerate",))
    big = dsr_gate(scores, "incumbent", "cand_0", n_trials=30, degenerate_arms=("degenerate",))
    assert big["sr0"] > small["sr0"]
    assert big["dsr"] < small["dsr"]


# ── 2. the incumbent path is byte-unchanged ──────────────────────────────────────────────────────

_PRE_EXISTING_KEYS = ("convention", "n_obs", "n_trials", "dsr", "observed_sr", "sr0",
                      "var_trials_sr", "available", "skill_mean", "skill_sd", "trial_arms",
                      "trial_sharpes", "dsr_asymptotic_V", "sr0_asymptotic_V",
                      "degenerate_trial_arms")


@pytest.mark.parametrize("n_folds,n_cand", [(8, 4), (3, 4), (5, 1), (11, 6)])
def test_with_no_degenerates_declared_every_pre_existing_key_is_byte_unchanged(n_folds, n_cand):
    """An un-updated caller cannot silently change its own verdicts.

    Both calls go through the NEW code; the reference is the value the OLD code produced, which is
    `deflated_sharpe` over ALL non-incumbent arms — reconstructed here independently rather than
    read back out of the function under test (a test that reads a value back under the key the code
    wrote cannot catch a wrong key — NF-C0e).
    """
    from betting_ml.utils.overfitting import deflated_sharpe

    scores = _field(n_folds=n_folds, n_cand=n_cand)
    g = dsr_gate(scores, "incumbent", "cand_0", n_trials=len(scores))
    if not g["available"]:
        pytest.skip("degenerate series at this size — covered by the UNDEFINED guard")

    inc = np.asarray(scores["incumbent"], float)
    lead = inc - np.asarray(scores["cand_0"], float)
    trial = [a for a in scores if a != "incumbent"]

    def _sr(s):
        s = np.asarray(s, float)
        s = s[np.isfinite(s)]
        if len(s) < 3:
            return 0.0
        sd = float(np.std(s, ddof=1))
        return float(np.mean(s) / sd) if sd > 0 else 0.0

    sharpes = [_sr(inc - np.asarray(scores[a], float)) for a in trial]
    ref = deflated_sharpe(lead, n_trials=len(scores), trial_sharpes=sharpes)

    assert g["dsr"] == pytest.approx(float(ref.dsr))
    assert g["sr0"] == pytest.approx(float(ref.sr0))
    assert g["observed_sr"] == pytest.approx(float(ref.observed_sr))
    assert g["trial_arms"] == trial, "the incumbent, and ONLY the incumbent, leaves V by default"
    assert "incumbent" not in g["v_trial_arms"]


def test_the_two_conventions_coincide_when_nothing_is_declared():
    g = dsr_gate(_field(), "incumbent", "cand_0", n_trials=5)
    assert g["binds"] == "whole_field_no_degenerates_declared"
    assert g["dsr"] == pytest.approx(g["dsr_with_degenerates_in_V"])
    assert g["dsr_degenerate_excluded"] == pytest.approx(g["dsr_with_degenerates_in_V"])
    assert g["declared_degenerate_arms"] == []


# ── 3. the V channel is the ONLY channel ─────────────────────────────────────────────────────────

def test_adding_a_degenerate_moves_the_whole_field_DSR_but_not_the_excluded_one():
    """⭐ The isolation test. `n_trials` is held FIXED across the two calls so the ONLY thing that
    varies is whether a designed loser is present in the field — i.e. the V channel alone.

    (Holding `n_trials` fixed is what makes this an isolation test rather than a confound; the
    multiplicity channel is proven separately, above.)
    """
    without = _field()
    with_deg = _field(degenerate_offset=0.9)
    assert set(with_deg) - set(without) == {"degenerate"}, "the fields must differ ONLY by the arm"

    n = 6  # held fixed on purpose
    a = dsr_gate(without, "incumbent", "cand_0", n_trials=n)
    b = dsr_gate(with_deg, "incumbent", "cand_0", n_trials=n, degenerate_arms=("degenerate",))

    # the whole-field figure MOVES — that is the defect being fixed
    assert b["dsr_with_degenerates_in_V"] != pytest.approx(a["dsr_with_degenerates_in_V"], abs=1e-9)
    assert b["var_trials_sr_with_degenerates"] > a["var_trials_sr_with_degenerates"]

    # the degenerate-excluded figure does NOT
    assert b["dsr_degenerate_excluded"] == pytest.approx(a["dsr_degenerate_excluded"])
    assert b["var_trials_sr"] == pytest.approx(a["var_trials_sr"])
    assert b["sr0"] == pytest.approx(a["sr0"])


# ── 4. the honest-degradation paths ──────────────────────────────────────────────────────────────

def test_an_unestimable_excluded_V_is_UNDEFINED_not_silently_the_asymptotic_fallback():
    """Dropping the degenerates can leave <2 arms. `deflated_sharpe` would silently fall back to
    `V = 1/n_obs` — a DIFFERENT convention. It must be refused and SAID, and the whole-field figure
    must bind (the conservative direction)."""
    scores = _field(n_cand=2, degenerate_offset=0.9)          # 2 candidates + 1 degenerate
    g = dsr_gate(scores, "incumbent", "cand_0", n_trials=len(scores),
                 degenerate_arms=("cand_1", "degenerate"))    # leaves ONE non-degenerate arm
    assert g["binds"] == "whole_field_with_degenerates"
    assert g["dsr_degenerate_excluded"] is None
    assert g["dsr"] == pytest.approx(g["dsr_with_degenerates_in_V"])
    assert "UNDEFINED" in (g["degenerate_exclusion_note"] or "")
    # ⛔ and it must NOT have quietly become the asymptotic figure
    assert g["dsr"] != pytest.approx(g["dsr_asymptotic_V"]) or g["n_obs"] < 3


@pytest.mark.parametrize("ineffective", ["typo_never_scored", "incumbent"])
def test_a_declared_degenerate_that_did_not_become_an_exclusion_is_recorded(ineffective):
    """NF1.7 (a): a check that did not run is not a check that passed.

    Two ways a declaration can silently do nothing — a typo'd/unscored name, and the INCUMBENT
    (already out of `V`, so declaring it is a no-op). Both must surface.
    """
    g = dsr_gate(_field(degenerate_offset=0.9), "incumbent", "cand_0", n_trials=6,
                 degenerate_arms=("degenerate", ineffective))
    assert g["declared_degenerate_arms_not_applied"] == [ineffective]
    assert g["declared_degenerate_arms"] == ["degenerate"]


# ── 5. classify_null no longer inherits an inflated V silently ───────────────────────────────────

@pytest.mark.parametrize("prov,must_contain", [
    (False, "DO NOT QUOTE THIS REMEDY BARE"),
    (None, "provenance of `V` was NOT stated"),
])
def test_classify_null_hedges_a_field_size_remedy_computed_off_an_unclean_V(prov, must_contain):
    v = classify_null(metric="m", n_folds=8, n_arms=9, beats_foil=True,
                      observed_sr=0.35, var_trials_sr=8.33,
                      degenerates_excluded_from_v=prov)
    assert must_contain in v.reason
    assert must_contain in (v.retest_trigger or "")


def test_classify_null_speaks_plainly_when_V_is_declared_clean():
    v = classify_null(metric="m", n_folds=8, n_arms=9, beats_foil=True,
                      observed_sr=0.35, var_trials_sr=8.33,
                      degenerates_excluded_from_v=True)
    assert "DO NOT QUOTE" not in (v.retest_trigger or "")
    assert "NOT stated" not in (v.retest_trigger or "")
    assert "DSR-CONV-correct" in v.reason


def test_classify_null_records_the_inflation_rather_than_asserting_it():
    v = classify_null(metric="m", n_folds=8, n_arms=9, beats_foil=True,
                      observed_sr=0.35, var_trials_sr=0.0262,
                      degenerates_excluded_from_v=True, var_trials_sr_with_degenerates=8.3314)
    assert v.detail["v_inflation_factor_from_degenerates"] == pytest.approx(317.99, abs=0.1)


# ── 6. ⛔ FORWARD-ONLY — the change cannot re-decide a recorded verdict ───────────────────────────

MH25_MD = REPO / ("quant_sports_intel_models/baseball/edge_program/ablation_results/"
                  "mh2_5_sigma_recalibration.md")
NFB3_MD = REPO / ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                  "nf_b3_joint_level_band.md")


def test_the_recorded_MH2_5_and_NF_B3_verdicts_are_untouched():
    """The nulls STAND. This pins the recorded verdict strings themselves — if a future change
    rewrites either artifact, this fails."""
    mh = MH25_MD.read_text()
    assert "INCUMBENT_STANDS" in mh
    assert "DSR_UNREACHABLE" in mh
    nb = NFB3_MD.read_text()
    assert "POWER_LIMITED" in nb
    assert "0.8773" in nb, "NF-B3's recorded whole-field DSR must remain on the record verbatim"


# ⚠️ WHICH recorded harness routes through `dsr_gate` is a MEASURED fact, not an assumption — and
# getting it wrong makes the forward-only guard below vacuous. `run_nf_b3_joint.py` does NOT call
# `dsr_gate` at all (its only textual hit is the dict key "folds_needed_for_dsr_gate"); it reaches
# DSR through the shared `deflated_sharpe` primitive, as most fantasy legs do. So the two harnesses
# need DIFFERENT invariants, and each must be proven NON-VACUOUSLY.
_RECORDED_HARNESSES = {
    "betting_ml/scripts/mh2_5_sigma_recalibration.py": True,                                # calls
    "quant_sports_intel_models/football/nfl/fantasy/run_nf_b3_joint.py": False,             # doesn't
}


def _code_of(rel: str) -> str:
    """Source with `#` comments stripped — a source guard that PROSE can satisfy is vacuous
    (INC-38), and a comment merely MENTIONING the parameter must not trip these."""
    return "\n".join(ln.split("#")[0] for ln in (REPO / rel).read_text().splitlines())


@pytest.mark.parametrize("rel,calls_dsr_gate", sorted(_RECORDED_HARNESSES.items()))
def test_dsr_conv_is_not_retro_wired_into_a_recorded_harness(rel, calls_dsr_gate):
    """⭐ THE STRONGEST FORM OF 'CANNOT RE-DECIDE': re-running either recorded harness must
    reproduce its recorded number, so neither may have picked up the new convention."""
    code = _code_of(rel)
    sites = list(re.finditer(r"dsr_gate\s*\(", code))

    if calls_dsr_gate:
        # ⚠️ The anti-vacuity assertion. Without it, a harness that stopped calling `dsr_gate`
        # (or a renamed function) would make the loop below iterate ZERO times and PASS on nothing.
        assert sites, (f"{rel} is registered as a dsr_gate caller but has no call site — the "
                       f"forward-only check below would pass vacuously")
        for m in sites:
            tail = code[m.end():m.end() + 400]
            assert "degenerate_arms" not in tail, (
                f"{rel} calls dsr_gate with degenerate_arms — DSR-CONV is FORWARD-ONLY and must "
                f"never be retro-applied to a recorded story's harness (its null STANDS)")
    else:
        # This harness reaches DSR through `deflated_sharpe` directly. Its forward-only guarantee is
        # therefore that it does not use the new parameter AND that the shared primitive is
        # unchanged (pinned separately, below).
        assert not sites, (f"{rel} now calls dsr_gate — update _RECORDED_HARNESSES and re-check "
                           f"that its recorded verdict is still reproducible")
        assert "degenerate_arms" not in code, (
            f"{rel} references degenerate_arms — DSR-CONV must not reach a recorded harness")


def test_the_shared_deflated_sharpe_primitive_has_no_degenerate_concept():
    """⭐ THE REAL REASON EVERY NON-`dsr_gate` LEG IS SAFE, asserted rather than assumed.

    Most §0.5 legs — including every fantasy leg except via its own harness — call
    `deflated_sharpe` directly. DSR-CONV lives ONE LAYER UP, in `dsr_gate`, so the primitive is
    untouched and those legs are byte-identical. If a future change pushed the convention DOWN into
    `deflated_sharpe`, it would silently alter every recorded leg at once — this is the tripwire.
    """
    import inspect

    from betting_ml.utils import overfitting

    params = inspect.signature(overfitting.deflated_sharpe).parameters
    assert "degenerate_arms" not in params and "degenerates" not in params, (
        "deflated_sharpe grew a degenerate concept — DSR-CONV must stay in `dsr_gate`, or it "
        "silently re-scores every leg that calls the primitive directly")


def test_even_the_recorded_degenerate_excluded_figures_do_not_cross_the_gate():
    """A belt-and-braces factual check: both records ALREADY carry a non-binding
    degenerate-excluded figure, and both sit BELOW 0.95. So this convention could not be read as a
    back-door rescue of either even by someone who ignored the forward-only rule.

    ⛔ This is NOT a re-scoring and NOT a re-verdict — it reads numbers already printed on the
    records and asserts they still fail the unchanged bar.
    """
    assert 0.6047 < 0.95, "MH2.5 §6's recorded V-excluding-designed-losers DSR"
    assert 0.938 < 0.95, "NF-B3's recorded contender-set DSR"
    mh = MH25_MD.read_text()
    assert "0.6047" in mh
    assert "0.938" in NFB3_MD.read_text()


def test_the_dsr_bar_itself_is_unchanged():
    """(b) was explicitly NOT adopted: the 0.95 whole-field bar stands."""
    from betting_ml.utils.overfitting import DSR_CONFIDENCE
    assert DSR_CONFIDENCE == 0.95
    src = (REPO / "betting_ml/scripts/dsr_conv_characterization.py").read_text()
    assert "DSR_GATE = 0.95" in src


# ── 7. the guards are not vacuous ────────────────────────────────────────────────────────────────

def test_the_guards_in_this_file_are_not_vacuous():
    """⭐ The RED-proof that can run in-process: the isolation test's premise must actually hold,
    and the degenerate must genuinely be extreme enough to move V. If `_field`'s degenerate stopped
    being a designed loser, the §3 guard would pass for the WRONG reason (both figures unchanged
    because nothing moved), so that possibility is refuted here explicitly.
    """
    g = dsr_gate(_field(degenerate_offset=0.9), "incumbent", "cand_0", n_trials=6,
                 degenerate_arms=("degenerate",))
    infl = g["var_trials_sr_with_degenerates"] / g["var_trials_sr"]
    assert infl > 5.0, (
        f"the fixture's degenerate only inflates V by {infl:.2f}× — too mild for the isolation "
        f"guard to be meaningful; a passing §3 would not prove anything")
    # and the leader must be a real arm, not the incumbent (whose series is identically zero)
    assert g["available"] and g["skill_sd"] > 0


def test_the_characterization_memo_is_result_blind():
    """⛔ The memo must not frame itself as a re-verdict on any recorded story."""
    memo = REPO / ("quant_sports_intel_models/baseball/edge_program/ablation_results/"
                   "dsr_conv_characterization.md")
    text = memo.read_text()
    assert "NOT A RE-VERDICT" in text
    for forbidden in ("MH2.5", "NF-B3", "MH2.2", "would now pass", "would have passed"):
        assert forbidden not in text, (
            f"the characterization names `{forbidden}` — it is a property study of the estimator "
            f"on synthetic fields and must not be readable as a re-scoring of a recorded story")
