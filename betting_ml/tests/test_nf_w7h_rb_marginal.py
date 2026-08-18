"""NF-W7h guards — the RB MARGINAL-layer zero-mass recalibration.

WHAT THESE DEFEND, AND WHY THEY ARE NOT NF-W7f's GUARDS AGAIN. The TRANSFORM is imported from
`fp_qb_marginal_calibration` BY IDENTITY, so its three measured identities are already guarded by
`test_nf_w7f_qb_marginal.py` and re-testing them here would be a second copy of a rule. What is NEW
at RB — and therefore what these guards concentrate on — is every place the QB story's SHAPE would
be wrong if copied:

  1. ⭐ **RB's calibration ALREADY CLEARS** (NF-W7e recorded 0.0242 against the 0.05 bar), so QB's
     verdict rule would return `CLEARS` for a mechanism that did nothing. The RB rule's five states
     — including `RB_CALIBRATION_DAMAGED`, which QB's rule cannot express — each get an ISOLATING
     fixture (NF-D17: a fixture that trips several conditions of an `and`-gate proves none of them),
     and one guard proves the vacuity directly by running QB's own rule on RB's pre-story numbers.
  2. ⭐ **The cap baseline must read RB's PER-POSITION block**, not the NF-W7e record's top-level
     `atom_cap`, which is QB's confirmation. Reading the top level would baseline RB against QB's
     0.2687 and MANUFACTURE a cap lift of ~0.28 out of nothing — a false `cap_was_lifted`, i.e. the
     mechanism-activity floor passing on a number from another position.
  3. ⭐ **The joint construction is `mix_played`, not `mixall_learned`**, because NF-W7e measured
     `mixall_learned` as BEATEN at RB. Pinning QB's choice would hand the story a foil already known
     to be beaten.
  4. ⭐ **The per-leg clause's MATERIALITY threshold** is decided forward and must come from a DESIGN
     quantity — so it is guarded two-sidedly, including the proof that it STILL REFUSES NF-W7f's own
     recorded QB result (a relaxation that rescued the case it was written after would be the
     E2.1-r inversion).
  5. a gate clause could be VACUOUS — the NF1.7 (a) / INC-38 / NF-D17 family this repo keeps
     re-learning.

⭐ EVERY GUARD BELOW IS RED-PROVEN against deliberately broken source by `_red_proof`, which asserts
its mutation LANDED on disk, that the mutated token is GONE, and that the anchor was UNIQUE in the
file — the three ways a RED proof has lied in this repo (#682 the mutation never landed; #815 it
landed but did not move the asserted predicate; the prediction_log case where it landed on the WRONG
symbol because two functions shared a tail).

Fast-gate safe: imports `betting_ml` / `quant_sports_intel_models` only, never `pipeline` (E11.23).
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_split_allrows as SA
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM
from quant_sports_intel_models.football.nfl.fantasy import fp_rb_marginal_calibration as RM
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7h_rb_marginal as R


def _repo_root() -> Path:
    """Walk up to the repo root, BOUNDED — a stalled walk reports HUNG rather than passing.

    ⛔ An unbounded `while not (p / marker).exists(): p = p.parent` silently terminates at `/` and
    then every path-based assertion below reads a file that is not there — which a `skip` or a
    truthy-guard would turn into a PASS. A walk that cannot find the root is a HARNESS failure and
    must say so (NF1.7 (a): a check that did not run is never a pass)."""
    p = Path(__file__).resolve()
    for _ in range(12):                      # bounded: the repo is nowhere near 12 deep from here
        if (p / "CLAUDE.md").exists() and (p / "quant_sports_intel_models").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    raise AssertionError(
        "HUNG: the repo-root walk exhausted its bound without finding CLAUDE.md + "
        "quant_sports_intel_models. The path-based guards below did NOT run — this is a harness "
        "failure, never a pass (NF1.7 (a)).")


_ROOT = _repo_root()
_FANTASY = _ROOT / "quant_sports_intel_models" / "football" / "nfl" / "fantasy"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The RED-proof harness — it must prove its own mutation before any verdict is trusted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _red_proof(path: Path, old: str, new: str, test_fn) -> None:
    """Apply a deliberate break to `path`, assert it LANDED, run `test_fn`, restore.

    Three assertions before the verdict is trusted, one per way a RED proof has lied here:
      · the anchor is UNIQUE in the file — otherwise `replace(old, new, 1)` can land on the WRONG
        symbol (two functions with byte-identical tails);
      · the mutation LANDED on disk (#682 — a break that silently no-ops reports a FALSE "the guard
        is vacuous", which reads as a finding and invites weakening a correct guard);
      · the mutated TOKEN IS GONE (#815 — a break that writes without moving the asserted predicate
        comes back green; an `x in src` assertion is blind to a suffix rename).

    ⭐ `test_fn` is expected to RAISE. It is caught as `BaseException`, not `Exception`, because
    pytest's `Failed` derives from `BaseException` — an `except Exception` here would let a
    `pytest.raises` clause's failure sail straight through and the RED proof would report SUCCESS on
    a break it never caught (NF-W6c)."""
    src = path.read_text()
    assert src.count(old) == 1, (
        f"the RED-proof anchor is not unique in {path.name} ({src.count(old)} occurrences) — "
        f"`replace(old, new, 1)` could land on the wrong symbol, so the proof would be about a "
        f"function other than the one under test")
    broken = src.replace(old, new, 1)
    assert broken != src, "the mutation did not change the source"
    path.write_text(broken)
    try:
        reread = path.read_text()
        assert reread == broken, "the mutation did not LAND on disk"
        assert old not in reread, (
            "the mutated token is still present after the break — the mutation wrote something "
            "but did not remove the thing the guard asserts on (#815)")
        import importlib
        for mod in (RM, R):
            importlib.reload(mod)
        caught = None
        try:
            test_fn()
        except BaseException as exc:            # noqa: BLE001 — pytest.Failed is a BaseException
            caught = exc
        assert caught is not None, (
            "THE GUARD IS VACUOUS: the deliberately broken source did NOT turn it red")
    finally:
        path.write_text(src)
        import importlib
        for mod in (RM, R):
            importlib.reload(mod)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ⭐ The RB verdict rule — five states, each with an ISOLATING fixture (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _verdict(**over):
    """A verdict call whose every condition is set to the PAYS branch, so a single overridden
    argument is the only thing that can move the state (NF-D17: isolate the clause)."""
    kw = dict(
        pit_by_arm={a: 0.02 for a in RM.REAL_ARMS},          # clears the 0.05 bar
        cap_mean=RM.PREDECESSOR_CAP_MEAN + RM.MIN_CAP_LIFT,  # exactly at the floor ⇒ lifted
        predecessor_cap_mean=RM.PREDECESSOR_CAP_MEAN,
        realized_atom=0.3359, installed_atom=0.33,
        clamp_binding_share=0.05, clamp_mean_move=0.001,
        binding_legs={"carries": 1.0}, pit_matched_foil=0.0242,
        beats_both_foils=True)
    kw.update(over)
    return RM.rb_marginal_verdict(**kw)


def test_the_rb_rule_reports_PAYS_only_when_the_cap_moved_the_pit_holds_and_both_foils_lose():
    assert _verdict()["state"] == RM.RB_PAYS


def test_the_rb_rule_reports_NO_SCORE_GAIN_when_the_cap_moved_but_the_foils_are_not_beaten():
    """The cap was REAL and was not RB's binding constraint — NF-W7e's GENUINE_ABSENCE stands.

    ISOLATING: the cap IS lifted and the PIT DOES clear, so neither the inactivity branch nor the
    damage branch can be what produced this state."""
    out = _verdict(beats_both_foils=False)
    assert out["state"] == RM.RB_NO_GAIN
    assert out["cap_was_lifted"] is True and out["best_pit"] <= out["bar"]


def test_the_rb_rule_reports_CALIBRATION_DAMAGED_when_the_pit_stops_clearing():
    """⭐ THE STATE QB's RULE CANNOT EXPRESS. RB's PIT already cleared, so a recalibration that
    pushes it past the bar has COST calibration rather than bought it — which is exactly what
    raising atoms on cells that already OVER-price their zero predicts (prereg §0.2).

    ISOLATING: the cap IS lifted and both foils ARE beaten, so only the PIT can move the state."""
    out = _verdict(pit_by_arm={a: 0.09 for a in RM.REAL_ARMS})
    assert out["state"] == RM.RB_DAMAGED
    assert out["cap_was_lifted"] is True and out["beats_both_foils"] is True
    assert "COST calibration" in out["reading"]


def test_the_rb_rule_reports_CAP_NOT_LIFTED_when_the_mechanism_could_not_act():
    """NF-D20 — count whether the mechanism could act before crediting OR condemning it.

    ISOLATING: the PIT clears and both foils are beaten, so a green everywhere-else field still
    reports INACTIVE purely because the knob did not turn."""
    out = _verdict(cap_mean=RM.PREDECESSOR_CAP_MEAN + RM.MIN_CAP_LIFT - 1e-6)
    assert out["state"] == RM.CAP_INACTIVE
    assert out["cap_was_lifted"] is False
    assert "UNTESTED, not refuted" in out["reading"]


def test_the_rb_rule_is_UNDEFINED_when_the_position_was_not_scored():
    assert _verdict(pit_by_arm={})["state"] == RM.CAP_UNDEFINED
    assert _verdict(cap_mean=float("nan"))["state"] == RM.CAP_UNDEFINED


def test_the_five_rb_states_are_distinct_and_enumerated():
    assert len(set(RM.RB_STATES)) == len(RM.RB_STATES) == 5
    for s in (RM.RB_PAYS, RM.RB_NO_GAIN, RM.RB_DAMAGED, RM.CAP_INACTIVE, RM.CAP_UNDEFINED):
        assert s in RM.RB_STATES


def test_QBs_rule_would_be_VACUOUS_on_RBs_own_pre_story_numbers():
    """⭐ THE REASON THE RB RULE EXISTS, PROVED RATHER THAN ASSERTED.

    NF-W7f's `marginal_cap_verdict` returns CLEARS when *the cap lifted AND some arm's PIT clears
    the bar*. Fed RB's RECORDED pre-story PIT (0.0242, which already clears) and a cap that moved by
    a hair MORE than the floor, QB's rule reports CLEARS — a verdict satisfied by a mechanism that
    bought nothing. The RB rule, on the identical numbers with the foils NOT beaten, reports
    `RB_CAP_LIFTED_NO_SCORE_GAIN`. If the two ever agree here, the RB rule has been flattened back
    into QB's and the vacuity is live again."""
    pit = {a: RM.PREDECESSOR_BEST_RB_PIT for a in RM.REAL_ARMS}
    qb_rule = QM.marginal_cap_verdict(
        pit_by_arm=pit, cap_mean=RM.PREDECESSOR_CAP_MEAN + RM.MIN_CAP_LIFT,
        predecessor_cap_mean=RM.PREDECESSOR_CAP_MEAN, realized_atom=0.3359,
        installed_atom=0.33, clamp_binding_share=0.05, binding_legs={"carries": 1.0},
        pit_matched_foil=RM.PREDECESSOR_BEST_RB_PIT, min_lift=RM.MIN_CAP_LIFT)
    assert qb_rule["state"] == QM.CAP_CLEARS, (
        "QB's rule no longer returns CLEARS on RB's already-clearing PIT — this guard's premise "
        "has moved and the vacuity argument must be re-derived")
    rb_rule = _verdict(pit_by_arm=pit, beats_both_foils=False)
    assert rb_rule["state"] == RM.RB_NO_GAIN
    assert rb_rule["state"] != qb_rule["state"], (
        "the RB rule agrees with QB's on RB's own already-clearing numbers — it has been flattened "
        "back into the rule the pre-registration §0.1 rejected as VACUOUS")


def test_the_rb_rule_reports_the_clamp_MAGNITUDE_beside_its_binding_share():
    """NF-W7f measured a binding SHARE byte-identical before and after (0.917 → 0.917) while the
    clamp's mean move on π̂ collapsed 112× — an activity COUNT is not a MAGNITUDE, and a headline
    quoting the share alone says *nothing changed* about a constraint that stopped mattering.

    ⛔ And it stays REPORTED: the STATE must not move with it."""
    out = _verdict()
    assert out["clamp_mean_upward_move"] == 0.001
    assert out["clamp_binding_share"] == 0.05
    assert _verdict(clamp_mean_move=None)["clamp_mean_upward_move"] is None
    assert _verdict(clamp_binding_share=0.99)["state"] == _verdict()["state"], \
        "the RB verdict STATE moved with the clamp share — it must read the cap lift, the PIT and "\
        "the foils only"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⭐ The mechanism-activity floor and its baseline
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_min_cap_lift_is_DERIVED_from_the_recorded_constants_not_typed():
    """§4: the floor is `realized all-zero rate − NF-W7e's recorded RB cap`. Deriving it in code
    (rather than typing 0.0341) is what makes it re-derivable when the baseline moves."""
    assert RM.MIN_CAP_LIFT == pytest.approx(
        RM.PREDECESSOR_REALIZED_ATOM - RM.PREDECESSOR_CAP_MEAN, abs=1e-9)
    assert RM.MIN_CAP_LIFT == pytest.approx(0.0341, abs=1e-9)
    src = inspect.getsource(RM)
    assert "MIN_CAP_LIFT = round(PREDECESSOR_REALIZED_ATOM - PREDECESSOR_CAP_MEAN" in src, \
        "the floor is a typed literal — it must be derived from the recorded design quantities"


def test_the_cap_baseline_reads_RBs_own_block_and_not_the_records_QB_confirmation():
    """⭐ THE HIGHEST-VALUE GUARD IN THIS FILE. NF-W7e's record carries a TOP-LEVEL `atom_cap` block
    that is QB's confirmation (cap 0.2687) and a PER-POSITION `selections.RB.atom_cap_detail`
    (cap 0.3018). Reading the top level here would baseline RB against QB's number and manufacture a
    cap lift of ~0.28 out of nothing — `cap_was_lifted` would pass on another position's figure and
    the whole mechanism-activity floor would be decorative."""
    base = R.cap_baseline()
    assert base["available"] is True, base
    assert base["position"] == "RB"
    assert base["source_path"] == "selections.RB.atom_cap_detail.cap_mean"
    assert base["atom_cap_mean"] == pytest.approx(RM.PREDECESSOR_CAP_MEAN, abs=1e-4)
    rec = json.loads((_ROOT / RM.CAP_BASELINE_RECORD_RELPATH).read_text())
    qb_top = float(rec["atom_cap"]["atom_cap_mean"])
    assert base["atom_cap_mean"] != pytest.approx(qb_top, abs=1e-4), (
        f"the baseline equals the record's TOP-LEVEL (QB) cap {qb_top} — it is reading QB's "
        f"confirmation, not RB's per-position block")
    # and the record still carries the numbers the pre-registration quoted (NF1.9-R)
    assert base["realized_all_zero_rate"] == pytest.approx(RM.PREDECESSOR_REALIZED_ATOM, abs=1e-4)
    assert base["installed_atom"] == pytest.approx(RM.PREDECESSOR_INSTALLED_ATOM, abs=1e-4)
    assert base["clamp_binding_share"] == pytest.approx(
        RM.PREDECESSOR_CLAMP_BINDING_SHARE, abs=1e-4)
    assert base["best_rb_pit"] == pytest.approx(RM.PREDECESSOR_BEST_RB_PIT, abs=1e-4)
    assert base["matches_preregistered_constants"] is True


def test_an_unavailable_baseline_is_unevaluable_and_can_never_satisfy_the_cap_lift():
    """NF1.7 (a): a check that did not run is never a pass."""
    out = RM.rb_marginal_verdict(
        pit_by_arm={a: 0.02 for a in RM.REAL_ARMS}, cap_mean=0.9,
        predecessor_cap_mean=float("nan"), realized_atom=0.34, installed_atom=0.33,
        clamp_binding_share=0.05, clamp_mean_move=0.0, binding_legs={},
        pit_matched_foil=0.0242, beats_both_foils=True)
    assert out["cap_was_lifted"] is False and out["state"] == RM.CAP_INACTIVE


def test_RBs_recorded_pit_already_clears_the_bar_which_is_the_storys_whole_premise():
    """If this ever goes red the pre-registration §0.1 is stale and the RB rule's rationale with
    it — the story would have become NF-W7f's after all."""
    assert RM.PREDECESSOR_BEST_RB_PIT < RM.PIT_MAX_DECILE_DEV, (
        RM.PREDECESSOR_BEST_RB_PIT, RM.PIT_MAX_DECILE_DEV)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⭐ The joint construction — `mix_played`, and justified by the RECORD
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_joint_construction_is_the_arm_the_record_says_is_RBs_best():
    """⛔ NOT a copy of NF-W7f's choice. NF-W7e recorded RB at `mix_played` 2.5173 <
    `mixall_learned` 2.5212 < `single_copula` 2.5290, so the matched foil must be `mix_played` —
    pinning `mixall_learned` would hand the story a foil already KNOWN to be beaten and make any
    win un-attributable to the recalibration.

    The ordering is read from the COMMITTED record, so if NF-W7e is ever regenerated with a
    different RB winner this guard goes red rather than silently leaving the wrong foil pinned."""
    assert RM.JOINT_CONSTRUCTION == "mix_played" == RM.MATCHED_FOIL
    assert RM.MATCHED_FOIL in RM.CONTEST_FOILS and RM.INCUMBENT_FOIL == "single_copula"
    rec = json.loads((_ROOT / RM.CAP_BASELINE_RECORD_RELPATH).read_text())
    crps = rec["selections"]["RB"]["mean_crps"]
    assert crps["mix_played"] < crps["mixall_learned"], (
        "NF-W7e no longer records `mix_played` as RB's better construction — the pinned joint "
        "construction must be re-derived, not inherited")
    assert crps[RM.MATCHED_FOIL] == min(crps["mix_played"], crps["mixall_learned"],
                                        crps["single_copula"]), \
        "the pinned construction is not RB's CRPS-best on record"


def test_the_arms_use_sigma_played_while_the_incumbent_keeps_sigma_all():
    """Both Σ estimators are needed at RB and each must reach the right construction: the real arms
    and the matched foil at Σ_played (the pinned construction), `single_copula` at Σ_all so it can
    still reproduce NF-W7c's `joint_rank` to 1e-9. Pinned by SOURCE inspection with comments
    stripped, so prose cannot satisfy the guard (INC-38)."""
    src = "\n".join(ln for ln in inspect.getsource(R.run_position).splitlines()
                    if not ln.lstrip().startswith("#"))
    assert "sig_played, sig_played_note = RM.sigma_played(raw_tr)" in src
    assert "sig_all, sig_all_note = FA.position_sigma(raw_tr)" in src
    assert 'banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all' in src, \
        "the incumbent is not built at Σ_all — it can no longer reproduce NF-W7c"
    assert "banks[RM.MATCHED_FOIL] = RM.assemble_mixture_bank(b_te, weights, pi=pi_served_used," \
           "\n                                                      corr=sig_played" in src, \
        "the matched foil is not built at Σ_played — it is no longer the pinned construction"
    assert "corr=sig_played, draws=draws)" in src


def test_the_predecessor_reproduction_target_is_the_record_that_actually_scored_RB():
    """`mix_played` IS NF-W7d's `mix_learned`, and NF-W7d scored RB — so the reproduction control
    is checked against a record that carries an RB row. A control pointed at a record with no RB
    block would report `reproduces: False` forever, or worse, be quietly skipped."""
    assert RM.PREDECESSOR_RECORD_ARMS == {"mix_played": "mix_learned"}
    rec = json.loads((_ROOT / RM.PREDECESSOR_RECORD_RELPATH).read_text())
    # ⭐ THE BUG THIS GUARD CAUGHT. The reproduction record is NF-W7d's; `PREDECESSOR` is NF-W7e
    # (the CAP-BASELINE record). `_record_scores` REFUSES a record whose `story` does not match and
    # returns None, and a None record makes the control report "DID NOT RUN" forever — a silently
    # never-running control, not a failure anyone would trace (NF1.7 (a)).
    assert RM.REPRODUCTION_RECORD_STORY != RM.PREDECESSOR, (
        "the two records this story reads have collapsed to one story string — the cap baseline "
        "(NF-W7e) and the reproduction target (NF-W7d) are different records")
    assert rec["story"] == RM.REPRODUCTION_RECORD_STORY and not rec.get("smoke")
    rb_rows = [fr for fr in rec["fold_results"]
               if "RB" in fr.get("positions", {})
               and "mix_learned" in fr["positions"]["RB"].get("scores", {})]
    assert len(rb_rows) >= 2, (
        f"the predecessor record carries {len(rb_rows)} RB folds with `mix_learned` — the "
        f"reproduction control cannot run (NF1.7 (a))")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. ⭐ The per-leg MATERIALITY clause — decided forward, guarded two-sidedly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pl(**over):
    kw = dict(relative_change=0.01, relative_claimed_effect=0.02,
              degraded_folds=8, n_folds=8)
    kw.update(over)
    return RM.per_leg_degradation_verdict(**kw)


def test_a_degradation_that_is_demonstrable_AND_material_REFUSES_the_story():
    out = _pl()                       # 0.01 ≥ 0.1 × 0.02 = 0.002, degraded on 8/8
    assert out["holds"] is False and out["state"] == "REFUSED"
    assert out["demonstrable"] is True and out["material"] is True


def test_a_degradation_that_is_not_DEMONSTRABLE_does_not_refuse():
    """ISOLATING: the degradation is MATERIAL (0.01 ≫ the 0.002 bar), so only the fold count can
    move the verdict — one fold's noise must not refuse a story."""
    out = _pl(degraded_folds=4)       # 4/8 is not a majority
    assert out["holds"] is True and out["state"] == "DEGRADED_BUT_NOT_DEMONSTRABLE"
    assert out["material"] is True and out["demonstrable"] is False


def test_a_degradation_that_is_not_MATERIAL_does_not_refuse():
    """ISOLATING: it is degraded on 8/8 folds, so only the magnitude can move the verdict — the
    'demonstrable ≠ material' rule (NF-W6), facing the refusal direction."""
    out = _pl(relative_change=0.0001)     # below 0.1 × 0.02
    assert out["holds"] is True and out["state"] == "DEGRADED_BUT_IMMATERIAL"
    assert out["demonstrable"] is True and out["material"] is False


def test_an_improvement_passes_and_is_labelled_as_such():
    out = _pl(relative_change=-0.02)
    assert out["holds"] is True and out["state"] == "IMPROVED" and out["material"] is False


def test_a_non_positive_claimed_effect_is_UNEVALUABLE_and_never_a_pass():
    """⛔ The registered edge (prereg §6.3): a non-positive claimed effect makes the materiality bar
    non-positive, so the clause cannot be evaluated — and an unevaluable clause is never a pass
    (NF1.7 (a)). It is not a loophole: the arm has already lost `beats_foil`."""
    for eff in (0.0, -0.01):
        out = _pl(relative_claimed_effect=eff)
        assert out["holds"] is False and out["state"] == "UNEVALUABLE", out
        assert "never a pass" in out["reason"]
    nan = _pl(relative_claimed_effect=float("nan"))
    assert nan["holds"] is False and nan["evaluated"] is False
    assert _pl(n_folds=0)["holds"] is False


def test_the_relaxed_clause_STILL_REFUSES_NF_W7fs_own_recorded_QB_result():
    """⭐ THE PROOF THAT THE RELAXATION RESCUES NOTHING (prereg §6.3). NF-W7f refused QB on a
    tolerance of 0.0 — any degradation at all. This story replaces that with a materiality
    threshold, and a threshold chosen to rescue the case it was written after would be the E2.1-r
    inversion in its most literal form. Fed NF-W7f's RECORDED numbers, the relaxed rule still
    REFUSES: 0.3866% observed against a 0.0712% bar, 5.4× above it."""
    rec = json.loads((_FANTASY / "ablation_results" / "nf_w7f_qb_marginal.json").read_text())
    sel = rec["selections"]["QB"]
    rel_change = float(sel["per_leg_detail"]["relative_change"])
    foil_mean = float(sel["mean_crps"][sel["best_foil"]])
    claimed = float(sel["mean_delta"]) / foil_mean
    by_fold = sel["per_fold_series"]["priced_leg_relative_change_by_fold"]
    out = RM.per_leg_degradation_verdict(
        relative_change=rel_change, relative_claimed_effect=claimed,
        degraded_folds=sum(1 for x in by_fold if x > 0), n_folds=len(by_fold))
    assert out["holds"] is False and out["state"] == "REFUSED", out
    assert out["materiality_bar"] < rel_change


def test_the_materiality_threshold_is_a_FRACTION_of_the_claimed_effect_not_a_level():
    """A DESIGN quantity: the bar scales with the arm's own claimed effect, so it can never be a
    number reverse-engineered from an observed degradation."""
    assert RM.PER_LEG_MATERIALITY_FRACTION == 0.1
    small = _pl(relative_claimed_effect=0.002)["materiality_bar"]
    big = _pl(relative_claimed_effect=0.2)["materiality_bar"]
    assert big == pytest.approx(100 * small), (small, big)


def test_the_gating_question_was_resolved_the_served_stat_line_is_not_these_cells():
    """⭐ prereg §6.1, re-checked against the RUNNING repo rather than a docstring. The board's
    exporter must reference none of the W6d substrate modules — if it ever does, the clause's whole
    justification (a per-leg change damages no served surface) is void and the relaxation must be
    re-argued before it can stand."""
    exporter = (_FANTASY / "export_draft_board_json.py").read_text()
    for token in ("stat_distribution_serving", "stat_distributions_d", "stat_distributions_c",
                  "fp_assembly", "fp_rb_marginal_calibration", "fp_qb_marginal_calibration"):
        assert token not in exporter, (
            f"`{token}` now reaches the board exporter — the served paid stat line may derive from "
            f"the W6d cells after all, so the per-leg materiality relaxation must be re-argued "
            f"(prereg §6.1)")
    # and the served stat line still comes from the SEASONAL point path
    assert "proj_rush_yds" in exporter and "proj_rec_yds" in exporter


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The declared field, the scope and the imports-by-identity
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_transform_is_imported_by_identity_never_re_implemented():
    """A second implementation would be the NF-C0e wrong-key class AND would break the matched-foil
    argument: `mix_played − zm_*` is 'the recalibration and nothing else' only if the splice is THE
    splice whose byte-identical no-op is measured per fold."""
    for name in ("resplice_zero_mass", "zero_targets", "positive_law_drift",
                 "zero_mass_hits_target", "matched_foil_identity", "leg_zero_mass",
                 "bucket_by_availability", "pool_availability_buckets", "atom_cap"):
        assert getattr(RM, name) is getattr(QM, name), f"{name} is not QM's object"
    assert RM.PI_BUCKET_EDGES is QM.PI_BUCKET_EDGES
    assert RM._SEED == QM._SEED and RM.AVAIL_STREAM_OFFSET == QM.AVAIL_STREAM_OFFSET


def test_the_story_gates_RB_only_and_says_so_on_the_record():
    assert RM.GATE_POSITIONS == ("RB",) and RM.POSITIONS == ("RB",) and RM.CAP_POSITION == "RB"
    blockers = " ".join(RM.PROMOTE_BLOCKERS)
    assert "RB ONLY" in blockers
    assert "CROSS-POSITION" in blockers, (
        "the record does not say that an RB certificate alone cannot unblock NF-W8's "
        "cross-position ranking (NF-W7c §4)")


def test_the_reference_foils_do_not_bind_beats_foil_and_stay_out_of_the_trial_field():
    """MH2.1 (a): a diagnostic anchor that joins the trial field sets the gate's own bar. `mix_off`
    was added by the §12 pre-score amendment and must be REFERENCE only — if it reached ELIGIBLE it
    would change what PBO and DSR deflate over, which is a field change, not a reported column."""
    assert "mix_off" in RM.REFERENCE_FOILS
    for f in RM.REFERENCE_FOILS:
        assert f not in RM.CONTEST_FOILS and f not in RM.ELIGIBLE
    assert set(RM.ELIGIBLE) == set(RM.REAL_ARMS) | set(RM.CONTEST_FOILS)
    assert RM.DECLARED_FIELD_SIZE == len(RM.REAL_ARMS) == 4


def test_the_split_channel_is_measured_at_a_FIXED_sigma_not_bundled_with_it():
    """⭐ The §12 amendment's whole point. At RB `single_copula − mix_played` differs in the SPLIT
    **and** the Σ population, so labelling it 'the split channel' would be a bundled contrast
    wearing a single channel's name (NF-W7d's bundled-null lesson, on the attribution side). The
    clean channel is `mix_off − mix_played`, and the bundled one must be NAMED as bundled."""
    src = "\n".join(ln for ln in inspect.getsource(R.select_position).splitlines()
                    if not ln.lstrip().startswith("#"))
    assert '"split_channel_at_fixed_sigma_played": _paired("mix_off", RM.MATCHED_FOIL)' in src
    assert '"split_at_fixed_sigma_played"' in src
    assert '"vs_incumbent_construction_BUNDLED"' in src, \
        "the bundled contrast is not named as bundled — a reader would read it as the split"


def test_every_declared_label_is_unique_and_the_watched_set_covers_the_degenerates():
    assert len(set(RM.ALL_LABELS)) == len(RM.ALL_LABELS)
    for d in RM.DEGENERATES:
        assert d in RM.WATCHED, f"{d}'s PIT is not printed every run (NF1.8)"
    assert "zm_permuted" in RM.ANCHORS and "zm_permuted" in RM.WATCHED
    for a in RM.REAL_ARMS:
        assert f"oracle__{a}" in RM.ANCHORS and f"matched_n__{a}" in RM.ANCHORS, \
            f"{a} has no per-FORM oracle at matched n (NF-D16 (g‴) / NF1.9 (f))"


def test_the_bar_the_floor_and_the_deflation_gates_are_inherited_by_reference():
    """⛔ E2.1-r: not one gate constant may be re-chosen by this story."""
    assert RM.PIT_MAX_DECILE_DEV is SA.PIT_MAX_DECILE_DEV
    assert RM.COVERAGE_FLOOR is SA.COVERAGE_FLOOR
    assert (RM.PBO_MAX, RM.DSR_MIN, RM.FDR_Q) == (SA.PBO_MAX, SA.DSR_MIN, SA.FDR_Q)
    assert RM.TARGET is FA.TARGET and RM.SELECTION_METRIC is FA.SELECTION_METRIC


def test_the_anchor_and_statistical_check_sets_partition_the_gate():
    assert not (set(RM.STATISTICAL_CHECKS) & set(RM.ANCHOR_CHECKS))
    for c in ("zero_mass_hits_target", "positive_law_preserved", "matched_foil_identity",
              "cap_was_lifted", "per_leg_calibration_not_degraded"):
        assert c in RM.ANCHOR_CHECKS


def test_the_preregistration_is_committed_and_names_the_field_and_the_amendment():
    doc = _FANTASY / "ablation_results" / "nf_w7h_preregistration.md"
    assert doc.exists(), f"the pre-registration is not committed at {doc}"
    text = doc.read_text()
    for label in (*RM.REAL_ARMS, *RM.CONTEST_FOILS, *RM.REFERENCE_FOILS):
        assert f"`{label}`" in text, f"{label} is declared in code but not in the committed prereg"
    assert str(RM.MIN_CAP_LIFT) in text, "the derived floor is not in the committed prereg"
    assert "RB ONLY" in text
    assert "PRE-SCORE AMENDMENT 1" in text, "the `mix_off` amendment is not recorded"
    assert RM.DECLARED_FIELD_SIZE_SOURCE.split(",")[0] in text.replace("\n", " ") or \
        "REAL_ARMS" in text


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Classification — the misleading-trigger directions (NF-D18)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _sel(**over):
    """A minimal selection block carrying exactly what `classify` reads."""
    sel = {"position": "RB", "n_folds_used": 8, "beats_foil": True, "observed_sr": 1.0,
           "var_trials_sr": 0.5, "fold_wins": 6, "p_one_sided": 0.01,
           "pit_flatness_winner_max_decile_dev": 0.03, "dsr": 0.9,
           "deltas_by_fold": [0.01, 0.02, -0.005, 0.03, 0.01, 0.02, 0.0, 0.015],
           "trial_srs": [1.0, 0.9, 0.2, -3.0],
           "coverage": {"blocking_shortfall": False, "winner_coverage_80": 0.89,
                        "n_rows": 8591, "binomial_se": 0.004}}
    sel.update(over)
    return sel


def _checks(**over):
    c = {k: True for k in (*RM.STATISTICAL_CHECKS, *RM.ANCHOR_CHECKS)}
    c.update(over)
    return c


def test_a_cap_that_did_not_lift_is_UNDEFINED_with_no_retest_trigger():
    """⭐ The mechanism-inactivity read comes FIRST: a knob that did not turn means the contest
    passed on nothing, so the thesis is UNTESTED, not refuted — and NO trigger is published,
    because the RAISE-ONLY splice cannot reach a cell that over-prices its zero at any fold count.

    ISOLATING: every other clause is green, so only `cap_was_lifted` can produce this state."""
    out = R.classify(_sel(), _checks(cap_was_lifted=False))
    assert out["state"] == "UNDEFINED"
    assert out["retest_trigger"] is None
    assert "UNTESTED, not refuted" in out["reason"]


def test_a_mixed_statistical_and_anchor_failure_publishes_no_data_trigger():
    """NF-D18, the direction that misleads: the anchor half BINDS, so no fold/season trigger is
    published — but the statistical shortfall is REPORTED, never hidden.

    ISOLATING: `cap_was_lifted` stays TRUE so this cannot be the inactivity branch, and both a
    statistical and an anchor check fail so it cannot be either single-cause branch."""
    out = R.classify(_sel(dsr=0.1), _checks(dsr_ok=False,
                                            per_leg_calibration_not_degraded=False))
    assert out["state"] == "CONSTRAINT_REFUSED"
    assert out["retest_trigger"] is None and out["binding_half"] == "anchor"
    assert "per_leg_calibration_not_degraded" in out["failing_anchor_checks"]
    assert "dsr_ok" in out["failing_statistical_checks"], "the shortfall was hidden"
    assert out["instrument_verdict"]["state"], "the instrument's raw reading was not kept"


def test_a_pure_anchor_failure_is_a_constraint_refusal_with_no_trigger():
    out = R.classify(_sel(), _checks(per_leg_calibration_not_degraded=False))
    assert out["state"] == "CONSTRAINT_REFUSED" and out["retest_trigger"] is None
    assert out["binding_half"] == "anchor"


def test_a_pit_only_failure_names_it_as_a_LOSS_because_RB_already_cleared():
    """At RB a PIT failure is not a shortfall — NF-W7e recorded the matched foil ALREADY clearing,
    so the recalibration COST calibration RB had. The record must say that rather than reading like
    QB's 'the bar was never reached'."""
    out = R.classify(_sel(pit_flatness_winner_max_decile_dev=0.09), _checks(pit_flat_ok=False))
    assert out["state"] == "CONSTRAINT_REFUSED"
    assert "ALREADY clearing" in out["reason"] and str(RM.PREDECESSOR_BEST_RB_PIT) in out["reason"]


def test_classify_passes_the_declared_field_size_and_reads_the_machine_flag():
    """MH2.7: `classify_null` must be told the DECLARED field so `field_remedy_admissible` is an
    auditable claim rather than a post-hoc field size, and the record must carry the SOURCE."""
    src = "\n".join(ln for ln in inspect.getsource(R.classify).splitlines()
                    if not ln.lstrip().startswith("#"))
    assert "declared_field_size=RM.DECLARED_FIELD_SIZE" in src
    out = R.classify(_sel(), _checks(per_leg_calibration_not_degraded=False))
    assert "field_remedy_admissible" in out
    assert out["declared_field_size_source"] == RM.DECLARED_FIELD_SIZE_SOURCE
    assert "preregistration" in RM.DECLARED_FIELD_SIZE_SOURCE


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. ⭐ The DSR 2×2 — measured before a remedy is named (prereg §9)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_dsr_diagnostic_runs_only_on_a_dsr_failure():
    assert "dsr_diagnostic" not in R.classify(
        _sel(), _checks(per_leg_calibration_not_degraded=False))
    assert "dsr_diagnostic" in R.classify(_sel(dsr=0.1), _checks(dsr_ok=False))


def test_the_dsr_diagnostic_names_VARIANCE_when_coherence_does_not_move_dsr():
    """⭐ NF-W7f's measured counterexample: dropping the far-out arm cut V 8.8× and DSR still
    reached only 0.174, because the binding quantity was per-fold NOISE. The diagnostic must name
    VARIANCE — and must NEVER prescribe a field trim (MH2.2)."""
    out = R.classify(_sel(dsr=0.05, observed_sr=0.2,
                          deltas_by_fold=[0.001, -0.02, 0.03, -0.01, 0.02, -0.015, 0.005, 0.0]),
                     _checks(dsr_ok=False))["dsr_diagnostic"]
    assert out["evaluated"] is True
    assert out["lever"] == "VARIANCE", out
    assert "LOWER-VARIANCE design" in out["reading"]
    assert "NOT more seasons" in out["reading"] and "NOT a field trim" in out["reading"]
    assert out["v_ratio_declared_over_coherent"] > 1.0, \
        "dropping the most extreme trial Sharpe did not reduce V — the decomposition is inert"


def test_the_dsr_diagnostic_calls_a_coherent_clearance_a_HYPOTHESIS_never_a_licence():
    """MH2.2: you get to PRE-REGISTER a family; you do NOT get to DISCOVER one. Even when a
    coherent sub-field WOULD clear, the admissible remedy is a fresh forward registration."""
    out = R.classify(_sel(dsr=0.1, observed_sr=6.0,
                          deltas_by_fold=[0.02] * 7 + [0.021],
                          trial_srs=[6.0, 5.9, 5.8, -40.0]),
                     _checks(dsr_ok=False))["dsr_diagnostic"]
    if out["lever"] == "MULTIPLICITY":
        assert "not a licence to trim it" in out["reading"]
        assert "FRESH, forward pre-registration" in out["reading"]
    assert out["declared_field_size"] == RM.DECLARED_FIELD_SIZE
    assert out["declared_field_size_source"] == RM.DECLARED_FIELD_SIZE_SOURCE


def test_the_dsr_diagnostic_is_UNEVALUABLE_rather_than_a_lever_when_it_cannot_run():
    """NF1.7 (a): a decomposition that could not be computed is never read as either lever."""
    out = R.classify(_sel(dsr=0.1, trial_srs=[1.0, 0.9]), _checks(dsr_ok=False))["dsr_diagnostic"]
    assert out["evaluated"] is False and "UNEVALUABLE" in out["reason"]
    assert "lever" not in out


def test_the_dsr_diagnostic_never_changes_the_gate():
    """It is a REPORTED row. A diagnostic that moved `ship` would be a gate added after the field
    was fixed (MH2 (a))."""
    gate_src = "\n".join(ln for ln in inspect.getsource(R.compose_gate).splitlines()
                         if not ln.lstrip().startswith("#"))
    assert "dsr_diagnostic" not in gate_src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The decomposition rule — FIXED absolute edges, never per-fold quantiles
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_availability_buckets_are_fixed_absolute_edges_not_quantiles():
    """⭐ NF-W7f's headline was REFUTED by its own decisive run because a π̂-QUARTILE bucketing on a
    bimodal covariate fabricated a monotone gradient. Fixed edges make 'bucket k' the same
    population on every fold, so the pool is exact."""
    assert RM.PI_BUCKET_EDGES == tuple(round(0.1 * k, 2) for k in range(11))
    # ⚠️ a RAW SUBSTRING scan false-fires on this story's own explanatory prose ("never per-fold
    # quantiles") — the NF-W7 banned-token lesson: match a CALL form, not a word, and strip
    # comments AND string literals so neither a comment nor a docstring can satisfy or trip it.
    import ast
    src = inspect.getsource(R._per_leg_table) + "\n" + inspect.getsource(R.select_position)
    calls = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            calls.add(f.attr if isinstance(f, ast.Attribute) else
                      f.id if isinstance(f, ast.Name) else "")
    for banned in ("quantile", "qcut", "percentile", "digitize"):
        assert banned not in calls, (
            f"a `{banned}(...)` CALL reached the decomposition — the buckets must be FIXED "
            f"absolute edges, and a per-fold quantile makes 'bucket k' a different population "
            f"on every fold")


def test_a_thin_bucket_is_unevaluable_and_can_never_supply_a_crossover():
    thin = {"sums": [1.0] * 10, "counts": [RM.MIN_BUCKET_ROWS - 1] * 10}
    out = RM.pool_availability_buckets([thin])
    assert out["state"] == "UNDEFINED" and all(m is None for m in out["mean_delta"])


def test_the_decomposition_pools_sums_and_counts_never_means_of_means():
    """NF1.8: a fold that returned per-bucket MEANS could only be pooled as a mean-of-means, which
    silently re-weights a thin fold equal to a fat one."""
    # a THIN fold (20 rows at 2.0) and a FAT one (30 rows at 0.0), both in bucket 0. The pooled
    # answer is Σsums/Σcounts = 40/50 = 0.8; a mean-of-means would report (2.0 + 0.0)/2 = 1.0.
    # Both folds together clear MIN_BUCKET_ROWS, so the bucket is evaluable rather than None.
    a = RM.bucket_by_availability(np.full(20, 2.0), np.full(20, 0.05))
    b = RM.bucket_by_availability(np.zeros(30), np.full(30, 0.05))
    pooled = RM.pool_availability_buckets([
        {"sums": a["sums"], "counts": a["counts"]},
        {"sums": b["sums"], "counts": b["counts"]}])
    assert pooled["counts"][0] == 50
    assert pooled["mean_delta"][0] == pytest.approx(0.8), (
        "the pool is not Σsums/Σcounts — a mean-of-means would report 1.0 and silently re-weight "
        "the thin fold equal to the fat one (NF1.8)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. ⭐ THE RED PROOFS — every clause above proven to go RED on deliberately broken source
# ══════════════════════════════════════════════════════════════════════════════════════════════
_MODULE = _FANTASY / "fp_rb_marginal_calibration.py"
_RUNNER = _FANTASY / "run_nf_w7h_rb_marginal.py"


def test_RED_the_damage_state_disappears_if_the_pit_branch_is_deleted():
    """Delete the branch that produces `RB_CALIBRATION_DAMAGED` and the state must become
    unreachable — the guard for QB's un-expressible state has to actually depend on it."""
    _red_proof(
        _MODULE,
        "    elif pit_by_arm[best_arm] > bar:\n        state = RB_DAMAGED\n",
        "",
        lambda: test_the_rb_rule_reports_CALIBRATION_DAMAGED_when_the_pit_stops_clearing())


def test_RED_the_cap_floor_becomes_decorative_if_the_lift_test_is_inverted():
    _red_proof(
        _MODULE,
        "and (cap_mean - predecessor_cap_mean) >= min_lift)",
        "and True)",
        lambda: test_the_rb_rule_reports_CAP_NOT_LIFTED_when_the_mechanism_could_not_act())


def test_RED_the_baseline_guard_fires_if_the_cap_is_read_from_the_records_QB_block():
    """⭐ The mutation that matters most: point the baseline at the record's top-level `atom_cap`
    (QB's confirmation) instead of RB's per-position block."""
    _red_proof(
        _RUNNER,
        '    sel = (rec.get("selections") or {}).get(RM.CAP_POSITION) or {}\n'
        '    cap = sel.get("atom_cap_detail") or {}\n',
        '    sel = (rec.get("selections") or {}).get(RM.CAP_POSITION) or {}\n'
        '    cap = {"cap_mean": (rec.get("atom_cap") or {}).get("atom_cap_mean")}\n',
        lambda: test_the_cap_baseline_reads_RBs_own_block_and_not_the_records_QB_confirmation())


def test_RED_the_materiality_clause_fires_if_the_bar_stops_scaling_with_the_effect():
    """Replace the design-derived bar with a fixed level and the 'still refuses QB' proof must
    break — a bar that does not scale with the claimed effect is exactly the reverse-engineered
    number the pre-registration forbids."""
    _red_proof(
        _MODULE,
        "    bar = materiality_fraction * eff\n",
        "    bar = 1.0\n",
        lambda: test_the_relaxed_clause_STILL_REFUSES_NF_W7fs_own_recorded_QB_result())


def test_RED_the_unevaluable_edge_fires_if_a_non_positive_effect_is_treated_as_a_pass():
    _red_proof(
        _MODULE,
        '    if eff <= 0.0:\n        return {"holds": False, "evaluated": False, '
        '"state": "UNEVALUABLE",',
        '    if eff <= 0.0:\n        return {"holds": True, "evaluated": True, '
        '"state": "UNEVALUABLE",',
        lambda: test_a_non_positive_claimed_effect_is_UNEVALUABLE_and_never_a_pass())


def test_RED_the_joint_construction_guard_fires_if_QBs_choice_is_copied():
    _red_proof(
        _MODULE,
        'JOINT_CONSTRUCTION = "mix_played"',
        'JOINT_CONSTRUCTION = "mixall_learned"',
        lambda: test_the_joint_construction_is_the_arm_the_record_says_is_RBs_best())


def test_RED_the_reference_foil_guard_fires_if_mix_off_reaches_the_trial_field():
    _red_proof(
        _MODULE,
        "ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *CONTEST_FOILS)",
        'ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *CONTEST_FOILS, "mix_off")',
        lambda: test_the_reference_foils_do_not_bind_beats_foil_and_stay_out_of_the_trial_field())


def test_RED_the_inactivity_branch_fires_if_a_dead_knob_publishes_a_data_trigger():
    _red_proof(
        _RUNNER,
        '        if not checks.get("cap_was_lifted", True):\n',
        '        if False:\n',
        lambda: test_a_cap_that_did_not_lift_is_UNDEFINED_with_no_retest_trigger())


def test_RED_the_dsr_variance_reading_fires_if_the_lever_is_hard_coded():
    _red_proof(
        _RUNNER,
        '        lever = "VARIANCE"',
        '        lever = "MULTIPLICITY"',
        lambda: test_the_dsr_diagnostic_names_VARIANCE_when_coherence_does_not_move_dsr())


def test_RED_the_split_channel_guard_fires_if_the_bundled_contrast_is_relabelled():
    _red_proof(
        _RUNNER,
        '"split_channel_at_fixed_sigma_played": _paired("mix_off", RM.MATCHED_FOIL)',
        '"split_channel_at_fixed_sigma_played": _paired("single_copula", RM.MATCHED_FOIL)',
        lambda: test_the_split_channel_is_measured_at_a_FIXED_sigma_not_bundled_with_it())


def test_RED_the_sigma_routing_guard_fires_if_the_incumbent_is_built_at_sigma_played():
    """If `single_copula` were built at Σ_played it could no longer reproduce NF-W7c's `joint_rank`
    — the reproduction control would fail for a reason no reader would trace to Σ."""
    _red_proof(
        _RUNNER,
        'banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all, draws=draws)',
        'banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_played, draws=draws)',
        lambda: test_the_arms_use_sigma_played_while_the_incumbent_keeps_sigma_all())


def test_RED_the_transform_identity_guard_fires_if_the_splice_is_re_implemented():
    _red_proof(
        _MODULE,
        "resplice_zero_mass = QM.resplice_zero_mass",
        "def resplice_zero_mass(banks, targets):\n"
        "    return QM.resplice_zero_mass(banks, targets)",
        lambda: test_the_transform_is_imported_by_identity_never_re_implemented())


def test_the_red_proof_harness_refuses_a_non_unique_anchor():
    """⭐ The harness's own guard (the prediction_log lesson): two functions with byte-identical
    tails make `replace(old, new, 1)` land on the WRONG symbol, and the run comes back green
    reporting a FALSE 'the guard is vacuous' — the dangerous direction, because it invites
    weakening a correct guard."""
    src = _MODULE.read_text()
    repeated = "REAL_ARMS"
    assert src.count(repeated) > 1, "the fixture token no longer repeats — pick another"
    with pytest.raises(AssertionError, match="not unique"):
        _red_proof(_MODULE, repeated, "XX", lambda: None)
    # and the file is UNTOUCHED: the refusal happens before anything is written
    assert _MODULE.read_text() == src, "a refused RED proof still mutated the file"


def test_the_red_proof_harness_catches_a_BaseException_from_a_pytest_raises_clause():
    """⭐ NF-W6c: `pytest.raises` failing raises `Failed`, which derives from `BaseException` — an
    `except Exception` here would let it sail through and the RED proof would report SUCCESS on a
    break it never caught. Proven by feeding the harness a `test_fn` that fails exactly that way."""
    def fails_via_pytest_raises() -> None:
        with pytest.raises(ValueError):
            pass                      # raises pytest.fail.Exception (a BaseException)

    # A restorable mutation whose token genuinely DISAPPEARS — appending a comment would leave the
    # old token a substring of the new text and the harness's own "#815" assertion would fire
    # first, so the exception-type claim would never be exercised (it did, on the first cut).
    # The point here is only the EXCEPTION TYPE the harness must catch.
    _red_proof(_MODULE, "PER_LEG_MATERIALITY_FRACTION = 0.1",
               "PER_LEG_MATERIALITY_FRACTION_RENAMED = 0.1", fails_via_pytest_raises)


def test_the_repo_root_walk_reports_HUNG_rather_than_passing():
    """A bounded walk that cannot find the root must RAISE. An unbounded one terminates at `/` and
    every path-based guard below silently reads a file that is not there (NF1.7 (a))."""
    src = inspect.getsource(_repo_root)
    assert "for _ in range(" in src, "the root walk is unbounded"
    assert "HUNG" in src and "raise AssertionError" in src
    assert _ROOT.is_dir() and (_ROOT / "CLAUDE.md").exists()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. ⭐ The REAL selection → gate → classify → report leg, exercised end to end
# ══════════════════════════════════════════════════════════════════════════════════════════════
# INC-39: a suite that monkeypatches the pipeline away asserts on strings a TEST AUTHOR wrote. The
# lake is not reachable here, but everything DOWNSTREAM of `run_position` is pure — so these drive
# the REAL `select_position`, `compose_gate`, `classify`, `derive_verdict_layer` and `write_report`
# over synthetic fold blocks. `write_report` had never executed before this section existed.
def _buckets(*, crossing: float = 0.5, rows: int = 70) -> dict:
    edges = RM.PI_BUCKET_EDGES
    sums, counts = [], []
    for k in range(len(edges) - 1):
        centre = 0.5 * (edges[k] + edges[k + 1])
        counts.append(rows)
        sums.append(round((crossing - centre) * rows, 6))
    return {"sums": sums, "counts": counts}


def _fold_block(*, scores: dict, per_leg_rel: float) -> dict:
    """A minimal-but-REAL `run_position` output for one (fold, RB)."""
    pit = {lab: {"max_decile_dev": 0.026, "decile_counts": [107] * 10,
                 "decile_freq": [0.1] * 10} for lab in RM.WATCHED}
    cov = {lab: {"coverage": 0.89, "n": 1073} for lab in RM.WATCHED}
    cov["assembled_comonotone"] = {"coverage": 0.94, "n": 1073}
    cov["assembled_indep"] = {"coverage": 0.74, "n": 1073}
    zm_labels = (*RM.REAL_ARMS, *RM.CONTEST_FOILS, "zm_cond_copula", "mix_off",
                 "assembled_indep", "assembled_comonotone")
    return {
        "scores": scores, "coverage": cov, "pit_flatness": pit,
        "n_train": 20000, "n_test": 1073, "atom_rate_train": 0.33, "atom_rate_test": 0.3359,
        "clamp": {a: {"mean_installed_atom": 0.33, "clamp_binding_share": 0.05,
                      "mean_upward_move": 0.001} for a in RM.REAL_ARMS},
        "clamp_served": {"clamp_binding_share": 0.4184, "mean_installed_atom": 0.2646,
                         "mean_upward_move": 0.07},
        "marginal_drift": {"max_probability_drift": 0.001},
        "targets": {a: {"mean": 0.6} for a in RM.REAL_ARMS},
        "resplice_edges": {a: {"share_target_clipped": 0.0} for a in RM.REAL_ARMS},
        "identities": {a: {
            "zero_mass_hits_target": {"max_abs_gap": 0.0, "holds": True},
            "positive_law": {"max_drift_over_bound": 0.5, "evaluated": True, "holds": True},
        } for a in RM.REAL_ARMS},
        "matched_foil_no_op": {"max_abs_draw_gap": 0.0, "holds": True},
        "per_leg_crps": {a: {
            "by_leg": {leg: {"served_crps": 1.0, "recalibrated_crps": 1.0 + per_leg_rel,
                             "delta": -per_leg_rel,
                             "delta_by_availability": _buckets(), "priced": True}
                       for leg in RM.LEGS},
            "priced_legs": list(RM.LEGS),
            "served_crps_sum_priced": float(RM.N_LEGS),
            "recalibrated_crps_sum_priced": float(RM.N_LEGS) * (1.0 + per_leg_rel),
            "relative_change": per_leg_rel,
            "priced_delta_by_availability": _buckets()} for a in RM.REAL_ARMS},
        "leg_zero_mass_table": {leg: {"predicted_zero_mass": 0.42, "realized_zero_rate": 0.36,
                                      "gap_realized_minus_predicted": -0.06} for leg in RM.LEGS},
        "leg_zero_mass_table_recalibrated": {
            leg: {"predicted_zero_mass": 0.42, "realized_zero_rate": 0.36,
                  "gap_realized_minus_predicted": -0.06} for leg in RM.LEGS},
        "binding_leg_share_served": {"carries": 1.0},
        "binding_leg_share_recalibrated": {"carries": 1.0},
        "atom_cap": {"cap_served": 0.3018, "cap_recalibrated": 0.36,
                     "installed_atom_recalibrated": 0.33, "installed_atom_served": 0.2646,
                     "clamp_binding_share_recalibrated": 0.05,
                     "clamp_binding_share_served": 0.4184,
                     "total_zero_mass_by_arm": {lab: 0.33 for lab in zm_labels}},
        "sigma_played_note": {}, "sigma_all_note": {},
    }


def _folds(*, winner_arm: str = "zm_conditional", per_leg_rel: float = -0.001,
           winner_crps: float = 2.50) -> list[dict]:
    base = {lab: 3.0 for lab in RM.ALL_LABELS}
    base.update({a: 2.9 for a in RM.REAL_ARMS})
    base[winner_arm] = winner_crps
    base[RM.MATCHED_FOIL] = 2.55                 # RB's CRPS-best construction on record
    base[RM.INCUMBENT_FOIL] = 2.60
    base["mix_off"] = 2.62
    for d in RM.DEGENERATES:
        base[d] = 6.0
    out = []
    for i in range(3):
        s = {k: v + 0.001 * i for k, v in base.items()}
        out.append({"label": f"f{i}", "n_test": 1073, "bank_cache": "test",
                    "positions": {"RB": _fold_block(scores=s, per_leg_rel=per_leg_rel)}})
    return out


def test_the_real_selection_and_report_legs_run_end_to_end(tmp_path):
    """⭐ The REAL legs, not monkeypatched ones (INC-39). `write_report` renders the RB verdict
    table, the per-leg materiality verdict, the availability decomposition and the premise table —
    none of which had ever executed before this test existed."""
    out = R.derive_verdict_layer({"fold_results": _folds(), "n_folds": 3,
                                  "generated_at": "2026-08-17T00:00:00+00:00", "smoke": False})
    sel = out["selections"]["RB"]
    assert sel["winner"] == "zm_conditional" and sel["best_foil"] == RM.MATCHED_FOIL
    assert sel["beats_foil"] is True
    # the per-leg clause ran its REAL materiality verdict and the arm IMPROVED the parts
    assert sel["per_leg_detail"]["verdict"]["state"] == "IMPROVED"
    assert sel["per_leg_detail"]["relative_claimed_effect"] > 0
    # the RB verdict rule ran and reports PAYS (cap lifted 0.3018 → 0.36 ≥ 0.0341; PIT clears;
    # both contest foils beaten)
    assert out["marginal_cap"]["state"] == RM.RB_PAYS, out["marginal_cap"]
    assert out["verdict"]["rb_verdict_state"] == RM.RB_PAYS
    assert out["verdict"]["joint_construction_held_fixed"] == "mix_played"
    # the clean split channel is present and named for the FIXED Σ
    assert "split_channel_at_fixed_sigma_played" in sel["channel_attribution"]
    assert "split_at_fixed_sigma_played" in sel["attribution"]
    assert "vs_incumbent_construction_BUNDLED" in sel["attribution"]
    # …and the report actually RENDERS
    p = tmp_path / "nf_w7h.md"
    R.write_report(out, p)
    text = p.read_text()
    for token in ("RB verdict", "RB IS NOT A RE-RUN OF NF-W7f", RM.RB_PAYS,
                  "clamp mean UPWARD MOVE", "materiality bar", "already cleared BEFORE this story",
                  "The premise, measured", "split_at_fixed_sigma_played", "RB ONLY"):
        assert token in text, f"the report never renders `{token}`"
    assert "mixall_learned" in text and "NOT NF-W7e" in text.replace("⛔ ", "")


def test_the_report_renders_the_DAMAGED_verdict_when_the_recalibration_costs_calibration(tmp_path):
    """The state QB's rule cannot express must survive all the way to the RENDERED record — a
    verdict nobody prints is not a verdict.

    ⚠️ This drives the whole leg, so several clauses fail at once and the classifier lands in its
    MIXED branch; the pit-ONLY wording is asserted by
    `test_a_pit_only_failure_names_it_as_a_LOSS_because_RB_already_cleared`, which isolates it
    (NF-D17 — a fixture that trips several clauses proves none of them individually). What this
    test owns is that the DAMAGED state is reached, reaches the gate, and RENDERS."""
    folds = _folds()
    for fr in folds:
        for lab in RM.REAL_ARMS:
            fr["positions"]["RB"]["pit_flatness"][lab]["max_decile_dev"] = 0.09
    out = R.derive_verdict_layer({"fold_results": folds, "n_folds": 3,
                                  "generated_at": "x", "smoke": False})
    assert out["marginal_cap"]["state"] == RM.RB_DAMAGED
    assert out["gates"]["RB"]["checks"]["pit_flat_ok"] is False
    assert out["gates"]["RB"]["ship"] is False
    n = out["null_states"]["RB"]
    # the anchor half BINDS, so no fold/season trigger is published (NF-D18)
    assert n["state"] == "CONSTRAINT_REFUSED" and n["retest_trigger"] is None
    assert n["binding_half"] == "anchor"
    assert "pit_flat_ok" in n["failing_statistical_checks"]
    p = tmp_path / "damaged.md"
    R.write_report(out, p)
    text = p.read_text()
    assert RM.RB_DAMAGED in text and "COST calibration" in text, \
        "the DAMAGED verdict never reaches the rendered record"


def test_a_winner_that_loses_the_foils_reports_NO_SCORE_GAIN_not_a_certificate():
    """RB's registered NO answer: the cap moved, calibration held, and the recalibration did not
    pay — NF-W7e's GENUINE_ABSENCE stands. It must NOT read as a certificate."""
    out = R.derive_verdict_layer({"fold_results": _folds(winner_crps=2.70), "n_folds": 3,
                                  "generated_at": "x", "smoke": False})
    assert out["marginal_cap"]["state"] == RM.RB_NO_GAIN
    assert out["verdict"]["story_verdict"] == "NULL"
    assert out["verdict"]["ship_positions"] == []
    assert out["gates"]["RB"]["checks"]["beats_foil"] is False


def test_the_per_leg_clause_reaches_the_gate_from_the_real_selection_leg():
    """⭐ WIRED ≠ INVOKED (NF-C0e). A materiality verdict computed but never read by `compose_gate`
    would leave the clause decorative. Driven through the REAL selection leg with a degradation
    that is both demonstrable and material."""
    out = R.derive_verdict_layer({"fold_results": _folds(per_leg_rel=0.05), "n_folds": 3,
                                  "generated_at": "x", "smoke": False})
    sel = out["selections"]["RB"]
    assert sel["per_leg_detail"]["verdict"]["state"] == "REFUSED"
    assert sel["per_leg_detail"]["degraded_folds"] == 3
    assert out["gates"]["RB"]["checks"]["per_leg_calibration_not_degraded"] is False
    assert out["gates"]["RB"]["ship"] is False
