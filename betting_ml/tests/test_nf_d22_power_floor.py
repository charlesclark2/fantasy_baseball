"""NF-D22 — guards for the power-derived coverage floor.

⚠️ WHAT THESE GUARDS ARE ACTUALLY DEFENDING, because it is not "the floor computes the right number".
The number is easy; what is hard is that NF-D22 sits one step from the repo's most-repeated failure —
**a floor that moves until something clears it** (E2.1-r) — and its downstream consequence happens to
be a previously-refused publish clearing. So the clauses below are, in order of how much they matter:

  1. ⛔ THE FLOOR CANNOT SEE A RESULT. `power_floor` takes no coverage argument and must never gain
     one; the floor for a given `n` is identical no matter what any band did.
  2. ⛔ THE LEVEL IS NF1.8's OWN PRE-REGISTERED ONE, pinned by arithmetic rather than by a docstring
     sentence that can drift.
  3. ⛔ THE MEASURED 0.7905 THAT REFUSED NF-D21 APPEARS NOWHERE IN THE DERIVATION.
  4. ⭐ THE VALIDATION IS TWO-SIDED. A one-sided guard is vacuous here in the most literal way: "a
     correct band passes" is satisfied perfectly by a floor of 0.0.
  5. ⛔ THE §0.5 SELECTION FLOOR IS UNTOUCHED — relaxing bake-off eligibility would re-decide
     recorded searches post hoc.

⭐ EVERY CLAUSE HAS ITS OWN ISOLATING FIXTURE AND IS RED-PROVEN (`nf_d22_red_proof.py`). The NF-D17
lesson is the reason: a guard on an `and`-composed rule stays GREEN when you delete the clause it
names, because another clause is already refusing the fixture — so a test per clause, with a fixture
that satisfies every OTHER clause, is the only shape that proves anything.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import binom, norm

from betting_ml.governance import gates as G
from betting_ml.utils import coverage_power_floor as CPF
from quant_sports_intel_models.football.nfl.fantasy import run_interval_revalidation as RV
from quant_sports_intel_models.football.nfl.fantasy import run_nf_d22_power_floor as D22
from quant_sports_intel_models.football.nfl.fantasy import (
    run_rookie_perposition_ablation as NF18,
)

NOMINAL = 0.80
#: A ladder spanning the whole range this program uses, plus awkward sizes where the Binomial's
#: discreteness is worst. Design quantities — nothing here was chosen by looking at a result.
NS = (30, 31, 37, 50, 64, 81, 100, 125, 148, 200, 313, 400, 1000, 3000, 6000)


def _code_only(src: str) -> str:
    """The module's EXECUTABLE text — docstrings and comments removed.

    A source-inspection guard that matches prose can be satisfied by deleting the very sentence that
    documents the discipline (INC-38's "prose cannot satisfy a guard", facing the other way). Both
    strippers are needed and the ORDER matters: comments are dropped by re-unparsing the AST, which
    also lets docstrings be identified structurally rather than by regex."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The floor is a DESIGN quantity — it cannot see a result
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_floor_function_has_no_coverage_argument_and_must_never_gain_one():
    """⛔ THE LOAD-BEARING GUARD. The whole defence against "this floor was reverse-engineered from
    the number that failed" is that the derivation is structurally incapable of reading one."""
    for fn in (CPF.power_floor, CPF.required_covered_rows, CPF.normal_approx_floor):
        params = set(inspect.signature(fn).parameters)
        assert params <= {"n", "nominal", "target"}, (
            f"{fn.__name__} may only depend on design quantities; it grew {params}")
        assert not ({"coverage", "cov", "observed", "rec", "band", "result"} & params)


def test_the_floor_is_identical_regardless_of_what_any_band_measured():
    """The behavioural twin of the signature check: same n ⇒ same floor, always. If a future edit
    routed an observation in through a default, a keyword, or module state, this moves."""
    base = {n: CPF.power_floor(n, nominal=NOMINAL) for n in NS}
    # score wildly different bands through the surface that DOES take coverage …
    for cov in (0.0, 0.5, 0.7905, 0.99, 1.0):
        for n in NS:
            block = CPF.group_floor(n, nominal=NOMINAL, coverage=cov)
            assert block["floor"] == pytest.approx(base[n], abs=5e-5), (
                "the floor moved with the observed coverage — it is no longer a design quantity")


def test_the_derivation_never_mentions_the_measurement_that_refused_nf_d21():
    """⛔ E2.1-r, as a mechanical check rather than a promise.

    0.7905 is the rookie-RB coverage that refused NF-D21. It may appear in a CONSEQUENCE section of a
    report; it may not appear anywhere in the instrument that derives the floor."""
    src = Path(CPF.__file__).read_text()
    assert "0.7905" not in src, (
        "the floor's derivation names the measurement it is accused of being fitted to — remove it, "
        "do not rephrase around it. A CONSEQUENCE section of a report may cite it; the instrument "
        "that derives the floor may not.")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The level is NF1.8's own, pinned by arithmetic
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_target_is_nf1_8s_own_pre_registered_level():
    """⭐ NF-D22 changes the level's SCOPE and FORM, never the level.

    NF1.8's Tier-2 fallback is `nominal − _TIER2_Z·SE(n)` with `_TIER2_Z = Φ⁻¹(0.95)`, i.e. a
    one-sided 95% test ⇒ a 0.05 false-reject target, recorded long before any result now read against
    it. Pinned here so the provenance paragraph cannot drift away from the constant."""
    implied = 1.0 - float(norm.cdf(NF18._TIER2_Z))
    assert CPF.FALSE_REJECT_TARGET == pytest.approx(implied, abs=1e-9)
    assert "NF1.8" in CPF.TARGET_PROVENANCE


def test_the_target_is_not_reachable_as_a_tuning_knob_from_a_verdict_path():
    """A target outside a sane one-sided range is refused outright rather than quietly honoured."""
    for bad in (0.0, 0.5, 0.9, -0.1, 1.0):
        with pytest.raises(ValueError):
            CPF.required_covered_rows(148, nominal=NOMINAL, target=bad)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The contract, EXACTLY — half A of the two-sided validation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_truly_nominal_band_clears_the_new_floor_at_the_pre_registered_rate():
    """Half A. Exact Binomial at every reference size — no simulation, so no lucky seed.

    ⚠️ This clause ALONE is vacuous (a floor of 0.0 satisfies it perfectly); it is only meaningful
    beside `test_a_materially_short_band_still_fails`."""
    for n in NS:
        floor = CPF.power_floor(n, nominal=NOMINAL)
        rate = CPF.false_reject_rate(n, nominal=NOMINAL, floor=floor)
        assert rate <= CPF.FALSE_REJECT_TARGET + 1e-12, (
            f"n={n}: the floor rejects a truly-nominal band {rate:.4f} of the time, above its own "
            f"advertised {CPF.FALSE_REJECT_TARGET}")


def test_the_incumbent_hard_floor_really_is_the_coin_flip_this_story_claims():
    """The indictment, MEASURED. If this ever stopped holding, NF-D22's whole motivation would be
    false and a future reader needs to find that out here rather than in prose."""
    rates = [CPF.false_reject_rate(n, nominal=NOMINAL, floor=NOMINAL) for n in NS]
    assert min(rates) > 0.30 and max(rates) < 0.60
    # …and it does NOT improve with n — the part that is easy to get wrong (NF1.8 §3)
    assert abs(rates[-1] - rates[0]) < 0.20


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Half B — a genuinely-short band still FAILS
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_materially_short_band_still_fails_the_new_floor():
    """⭐ Half B, and the clause that stops NF-D22 being a floor-REMOVAL wearing a floor's badge.

    ⚠️ THE FIRST VERSION OF THIS TEST WAS SELF-REFERENTIAL AND THE RED PROOF CAUGHT IT. It asserted
    that a band AT the floor's own `detectable_shortfall` is rejected at the detection power — but
    `detectable_shortfall` RECOMPUTES the floor, so dropping the floor drops the resolution with it
    and the clause stayed GREEN while the floor was gutted (`nf_d22_red_proof.py`, break "the floor
    is dropped to a level a broken band survives"). A guard whose reference point moves with the
    thing it guards has examined nothing (the NF1.7 (a) / NF-D17 class).

    ⭐ THE FIX IS AN ABSOLUTE, DESIGN-DERIVED CEILING ON THE RESOLUTION. Asymptotically the smallest
    detectable shortfall is `(z_target + z_power)·σ/√n`, and `σ = √(p(1−p)) ≤ 0.5` for ANY coverage,
    so `(nominal − detectable_shortfall)·√n` is bounded by `(z_target + z_power)/2` — a number that
    falls out of the two pre-registered design constants and NOTHING measured. A generous 25%
    allowance is added for the Binomial's discreteness at small n (the observed envelope is
    1.04–1.26 against a bound of 1.55, so it is not a bar fitted to the answer)."""
    z_t = float(norm.ppf(1.0 - CPF.FALSE_REJECT_TARGET))
    z_p = float(norm.ppf(CPF.DETECTION_POWER))
    ceiling = (z_t + z_p) * 0.5 * 1.25          # σ ≤ 0.5 for any p, + a discreteness allowance
    for n in NS:
        floor = CPF.power_floor(n, nominal=NOMINAL)
        res = CPF.detectable_shortfall(n, nominal=NOMINAL)
        assert res is not None and res < NOMINAL, f"n={n}: the floor resolves nothing at all"
        # the floor really does reject a band at its stated resolution …
        rejected = 1.0 - CPF.pass_probability(n, true_coverage=res, floor=floor)
        assert rejected >= CPF.DETECTION_POWER - 1e-9
        # … and that resolution is not allowed to wander away from nominal, which is what a dropped
        #   floor would do and what the self-referential version could not see
        assert (NOMINAL - res) * np.sqrt(n) <= ceiling, (
            f"n={n}: the floor only resolves a shortfall down to {res:.4f}; a floor honouring its "
            f"own target cannot be that blunt — has the floor been dropped?")


def test_a_catastrophically_short_band_is_refused_almost_always():
    """The blunt end of half B — a band covering half its nominal rate must not survive at any n."""
    for n in NS:
        floor = CPF.power_floor(n, nominal=NOMINAL)
        assert CPF.pass_probability(n, true_coverage=NOMINAL / 2, floor=floor) < 0.01


def test_the_two_sided_validation_reports_BOTH_halves_and_fails_if_either_is_missing():
    """The runner's §2 must carry both verdict keys; a report with only half A has proven nothing."""
    v = D22.two_sided_validation()
    assert v["rows"] and v["verdicts"]
    for row in v["verdicts"]:
        assert {"nominal_band_clears", "short_band_still_fails"} <= set(row)
    assert v["pass"] is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The floor may never be TIGHTENED, and it self-attenuates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_floor_is_never_above_nominal():
    """⛔ NF1.8 §1: every notch above nominal moves the eligible set toward `max_width`. The clamp is
    written and guarded even though it is mathematically slack, because "tighten it a little for
    safety" is a real and recurring temptation."""
    for n in NS:
        for nominal in (0.50, 0.80, 0.90, 0.95):
            assert CPF.power_floor(n, nominal=nominal) <= nominal + 1e-12


def test_the_floor_self_attenuates_so_no_thin_group_boundary_was_ever_needed():
    """⭐ The reason there is no thin-group LIST: the correction shrinks as √(1/n) on its own, so a
    fat group's floor converges to nominal without anyone deciding where to stop applying it. A
    boundary would have been a degree of freedom someone chose.

    ⚠️ THE CLAIM IS AN ENVELOPE, NOT POINTWISE MONOTONICITY, and asserting the latter was the first
    (wrong) instinct — it FAILS, because the requirement is an integer count and discreteness makes
    the floor locally jagged (n = 31 → 0.6774 but n = 37 → 0.6757). Writing the guard the natural way
    would have made the module's docstring say something the arithmetic does not support."""
    floors = [CPF.power_floor(n, nominal=NOMINAL) for n in sorted(NS)]
    assert floors[0] < floors[-1] < NOMINAL
    assert NOMINAL - floors[-1] < 0.01, "at 6000 rows the floor should sit within 1pp of nominal"
    env = [(NOMINAL - f) * np.sqrt(n) for n, f in zip(sorted(NS), floors)]
    assert max(env) / min(env) < 1.5, (
        f"(nominal − floor)·√n should sit in a narrow band across three orders of magnitude; got "
        f"{min(env):.3f}–{max(env):.3f}")


def test_every_group_size_this_program_has_is_thin_so_uniform_and_thin_only_are_one_set():
    """`is_thin` is a DIAGNOSTIC and gates nothing — and this is why: under the pre-registered target
    it never discriminates, so "uniformly to all thin groups" and "uniformly to every constrained
    group" describe the same set."""
    assert all(CPF.is_thin(n, nominal=NOMINAL) for n in NS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The §0.5 SELECTION floor is untouched
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_bakeoff_selection_floor_is_still_the_hard_nominal_one():
    """⛔ NF-D22 governs the GATE, not bake-off ELIGIBILITY. Inside a §0.5 search a FIELD of arms
    exists and the METRIC does the selecting; relaxing eligibility there would admit arms into
    searches that are already RECORDED — i.e. re-decide them post hoc."""
    rec = {"n_QB": 81, "cov_QB": 0.80, "n_RB": 148, "cov_RB": 0.79}
    assert NF18.position_floors(rec, ["QB", "RB"], tier=1) == {"QB": 0.80, "RB": 0.80}
    assert "coverage_power_floor" not in Path(NF18.__file__).read_text(), (
        "the selection module must not import the GATE floor")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Multiplicity is REPORTED, never acted on
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_groups_floor_does_not_depend_on_how_many_other_groups_are_in_the_family():
    """⛔ NF-D22 deliberately does NOT split the target across the family. A Bonferroni correction
    would LOOSEN every individual floor — the one adjustment a reader should most distrust from a
    story whose downstream consequence is a previously-refused publish clearing."""
    alone = CPF.floor_table({"A": 148}, nominal=NOMINAL)["floors"]["A"]
    crowded = CPF.floor_table({"A": 148, **{f"G{i}": 500 for i in range(12)}},
                              nominal=NOMINAL)["floors"]["A"]
    assert alone == crowded


def test_the_family_false_reject_rate_is_reported_beside_the_per_group_target():
    """It must be visible — the honest caveat — without ever becoming the thing that binds."""
    fam = CPF.family_false_reject_rate([148, 81, 200, 300], nominal=NOMINAL)
    assert fam["per_group_target"] == CPF.FALSE_REJECT_TARGET
    assert fam["family_false_reject_rate"] > CPF.FALSE_REJECT_TARGET
    # and the previous rule was far worse on the same reading — the comparison that makes it honest
    assert fam["family_false_reject_rate"] < fam["family_false_reject_rate_at_nominal_floor"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The substantive backstop
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_pooled_floor_is_the_stricter_tier_and_that_is_measured_not_asserted():
    """The objection to a self-attenuating per-group floor is that a band could rest near every thin
    group's own low floor. It cannot — the pooled check runs the identical rule over a larger n."""
    out = CPF.pooled_backstop_check(600, [148, 81, 200, 171], nominal=NOMINAL)
    assert out["verdict"] == "BACKSTOP_HOLDS"
    assert out["pooled_floor"] > out["tightest_group_floor"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The gate + the standing re-validation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _rec(cov_rb: float, n_rb: int = 148) -> dict:
    """A scored-arm record whose ONLY variable is rookie-RB coverage — every other group is
    comfortably clear, so a verdict change can only come from the clause under test (NF-D17)."""
    return {"n": 600, "coverage_80": 0.83, "interval_score": 100.0,
            "n_QB": 81, "cov_QB": 0.86, "n_RB": n_rb, "cov_RB": cov_rb,
            "n_TE": 140, "cov_TE": 0.88, "n_WR": 231, "cov_WR": 0.87}


def test_the_revalidation_block_carries_BOTH_readings_so_a_floor_change_is_auditable():
    """A floor change visible only in a changelog is a floor change nobody can audit later."""
    b = RV._floor_block(_rec(0.7905), ["QB", "RB", "TE", "WR"],
                        {"min_n": 30, "tier2_positions": ("QB",), "nominal": 0.80})
    assert b["floors"]["RB"] < 0.80 and b["floors_at_nominal"]["RB"] == 0.80
    assert b["slack_rows"]["RB"] > 0 > b["slack_rows_at_nominal"]["RB"]
    assert b["floor_rule"] == CPF.FLOOR_RULE


def test_the_gate_floor_admits_a_thin_group_the_previous_rule_refused_by_two_rows():
    """The consequence, isolated: at n=148 a 0.7905 band is 2 covered rows short of the hard floor and
    7 rows clear of the calibrated one."""
    b = RV._floor_block(_rec(0.7905), ["QB", "RB", "TE", "WR"],
                        {"min_n": 30, "tier2_positions": ("QB",), "nominal": 0.80})
    assert b["pass"] is True and not b["misses"]
    assert b["misses_at_nominal_floor"], "the previous rule must still be shown refusing it"


def test_a_genuinely_short_thin_group_is_STILL_refused_by_the_gate():
    """⭐ The two-sided half at the GATE, not just in the instrument. Same fixture, same n, a band
    that is really broken — it must still fail, or NF-D22 removed a floor rather than fixing one."""
    b = RV._floor_block(_rec(0.65), ["QB", "RB", "TE", "WR"],
                        {"min_n": 30, "tier2_positions": ("QB",), "nominal": 0.80})
    assert b["pass"] is False
    assert any(m.startswith("RB ") for m in b["misses"])


def test_a_group_whose_coverage_could_not_be_read_is_not_scored_as_met():
    """NF1.7 (a): a check with no subject has examined nothing, and scoring that green is how a floor
    becomes decoration."""
    rec = _rec(0.86)
    rec["cov_RB"] = None
    b = RV._floor_block(rec, ["QB", "RB", "TE", "WR"],
                        {"min_n": 30, "tier2_positions": ("QB",), "nominal": 0.80})
    assert b["pass"] is False
    assert any("unavailable" in m for m in b["misses"])


def test_a_group_below_the_pre_registered_minimum_stays_unconstrained():
    """`min_n` is a separate pre-registered design quantity owned by each population's own story.
    NF-D22 must not quietly move it — that would be a floor change wearing a different hat."""
    rec = _rec(0.86)
    rec["n_RB"] = 12
    b = RV._floor_block(rec, ["QB", "RB", "TE", "WR"],
                        {"min_n": 30, "tier2_positions": ("QB",), "nominal": 0.80})
    assert "RB" in b["unconstrained"] and "RB" not in b["floors"]


def test_the_gate_surfaces_the_floor_rule_but_stays_ADDITIVE_for_older_reports():
    """NF-C0: an older report that predates the `floor_rule` key was correct when written, so
    refusing it would fail closed on the record rather than on a defect."""
    ok = G.interval_floors({"pass": True, "rookies": {"misses": [], "floor_rule": CPF.FLOOR_RULE}})
    assert ok.passed and ok.data["floor_rule"] == CPF.FLOOR_RULE
    legacy = G.interval_floors({"pass": True})
    assert legacy.passed and legacy.data["floor_rule"] == "unstated"
    bad = G.interval_floors({"pass": False, "rookies": {"misses": ["RB 0.60<0.743"]}})
    assert not bad.passed and "tol" not in inspect.signature(G.interval_floors).parameters


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The runner's own disciplines
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_runner_writes_only_its_own_paths_and_never_a_decided_storys():
    """⛔ NCAAF-P2.1 S1-serve: a fixed-output-path write clobbered a decided story's audit trail and
    nothing failed. NF-D21's record must keep saying it was refused under the rule then in force."""
    src = Path(D22.__file__).read_text()
    written = set(re.findall(r"_OUT_(?:JSON|MD)\s*=\s*_REPORT_DIR\s*/\s*\"([^\"]+)\"", src))
    assert written == {"nf_d22_power_floor.json", "nf_d22_power_floor.md"}
    # ⚠️ SCAN CODE, NOT PROSE. The module's docstring names NF-D21's artifacts precisely in order to
    #    say it must not write them — a raw substring scan would fire on the sentence that documents
    #    the discipline, i.e. the cheapest way to pass would be deleting the warning (the negation-
    #    blind-scan class). Strip docstrings and comments via AST first.
    assert "nf_g0_d21_governance_publish" not in _code_only(src), (
        "the runner references a DECIDED story's artifact paths in executable code")


def test_the_runner_does_not_flip_a_serving_switch():
    """⛔ THIS RUNNER PUBLISHES NOTHING — it reports and stops. A publish needs a NEW PM disposition,
    recorded in `rookie_publish_policy` by a human.

    ⭐ RE-ANCHORED 2026-08-20. The original form ALSO asserted the live state was still
    `False` / `CONSTRAINT_REFUSED`, which conflated two different claims: "this runner does not flip
    the switch" (a property of THIS story, permanent) and "the switch is currently off" (a fact about
    a DIFFERENT story, which changed the moment NF-D21-PUBLISH landed). Pinning the second inside
    NF-D22's suite made a legitimate downstream decision look like an NF-D22 regression. The
    permanent claim is kept and made stricter; the live-state claim moves to the story that owns it
    (`test_nf_d21_rookie_publish.py`), and what is asserted here instead is that the two are
    INDEPENDENT — the flip moved by a route that does not run through this module."""
    src = Path(D22.__file__).read_text()
    assignments = [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.Assign)
                   for t in n.targets
                   if isinstance(t, ast.Attribute) and t.attr in
                   ("SERVING_ENABLED", "DISPOSITION", "SHRINK_LAMBDA",
                    "DISPOSITION_IS_NOT_PENDING", "PUBLISHABLE_DISPOSITIONS")]
    assert not assignments, "the runner mutates the rookie publish policy"
    # ⚠️ non-vacuity: the AST scan above proves nothing if it never looked at real assignments.
    assert any(isinstance(n, ast.Assign) for n in ast.walk(ast.parse(src))), (
        "the AST scan found no assignments at all — it is not reading the runner's source")
    # …and no other mutation route either (setattr / __dict__ / importlib.reload on the policy).
    low = _code_only(src)
    assert "setattr(" not in low and "__dict__" not in low, (
        "the runner reaches the rookie policy by a route the AST scan cannot see")


def test_the_serving_flip_is_owned_by_nf_d21_not_by_this_story():
    """⭐ THE SEPARATION IS THE POINT OF NF-D22's WHOLE FRAMING: the floor is derived from design
    quantities, and NF-D16 clearing under it is a CONSEQUENCE, never the motivation. So this suite
    asserts the SEPARATION (the flip is decided elsewhere, under its own recorded disposition) and
    deliberately does NOT assert which way it currently points — an NF-D22 test that went red when a
    PM re-decided NF-D21 would be claiming ownership of a decision it must not own."""
    from quant_sports_intel_models.football.nfl.fantasy import rookie_publish_policy as RP
    RP.assert_coherent()
    assert RP.SERVING_ENABLED is (RP.DISPOSITION in RP.PUBLISHABLE_DISPOSITIONS) or \
        not RP.SERVING_ENABLED, "serving must agree with the recorded disposition"
    assert RP.DECISION_STORY == "NF-D21", "the flip's owning story"
    assert RP.DISPOSITION_REVIEWED_BY.strip(), "a disposition with no named reviewer is unowned"


def test_section_3_is_not_computed_unless_the_two_sided_validation_passes():
    """⭐ THE ORDER IS THE ARGUMENT. If a consequence could be read before the floor has proven
    itself, the story would be exactly the inversion it exists to avoid."""
    src = inspect.getsource(D22.main)
    i_two = src.index('if not two_sided["pass"]')
    i_sweep = src.index("sweep = floor_sweep(")
    assert i_two < i_sweep, "§3 must be gated behind §2's verdict"
    assert "return 1" in src[i_two:i_sweep]


def test_the_design_table_is_computable_with_no_artifact_at_all():
    """§1's entire claim: every floor could have been published before any band was scored."""
    d = D22.design_table()
    assert d["rows"] and d["self_attenuates"] and d["all_reference_sizes_thin"]
    assert d["new_false_reject_max"] <= CPF.FALSE_REJECT_TARGET + 1e-12
    lo, hi = d["incumbent_false_reject_range"]
    assert lo > 0.30 and hi < 0.60


def test_the_floor_matches_an_independent_reimplementation_of_its_own_contract():
    """⭐ Re-derived from the CONTRACT ("the largest requirement whose false-reject rate honours the
    target"), not from this module's search, so a subtle off-by-one in the walk would show."""
    for n in NS:
        k = CPF.required_covered_rows(n, nominal=NOMINAL)
        admissible = [j for j in range(0, n + 1)
                      if float(binom.cdf(j - 1, n, NOMINAL)) <= CPF.FALSE_REJECT_TARGET]
        assert k == max(admissible)
        assert np.isclose(CPF.power_floor(n, nominal=NOMINAL), k / n, atol=5e-5)
