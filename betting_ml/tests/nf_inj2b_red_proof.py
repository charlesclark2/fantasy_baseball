"""nf_inj2b_red_proof.py — prove every NF-INJ2b guard can actually FAIL (⛔ NOT a pytest module).

A guard that cannot go red is not a guard (NF1.7 (a); INC-38; NF-D17). This harness applies ONE
deliberate break to the source at a time, runs the clause that names it, and reports whether that
clause turned red. A clause that stays GREEN on its own break is VACUOUS and must be rewritten.

⚠️ FOUR WAYS A RED PROOF LIES, all recorded in this repo and all guarded against here:
  1. **THE MUTATION NEVER LANDS** (#682) — a quoting or match failure leaves the source unchanged and
     "the guard caught it" is indistinguishable from "the break never happened". ⇒ mutations are
     applied IN-PROCESS and the file is asserted to have CHANGED.
  2. **THE ANCHOR IS NOT UNIQUE** (E11.24) — a single-occurrence replace lands on the WRONG symbol
     and the run reports a FALSE VACUITY, the dangerous direction (it invites weakening a correct
     guard). ⇒ every anchor is asserted to occur EXACTLY ONCE.
  3. **THE MUTATION LANDS BUT DOES NOT MOVE THE ASSERTED PREDICATE** (#815) — e.g. a rename an
     `x in src` clause still matches. ⇒ each break names the token it removes, asserted GONE after.
  4. **THE PROOF LIVES IN NO WORKFLOW** (E9.64) — a mutation suite nobody runs decays silently. ⇒ it
     is a plain script the closeout runs, and its RED count is recorded in the story report.

⚠️ AND THIS FILE'S OWN WORST CASE: it mutates TRACKED source, so being killed mid-mutation would
leave the tree broken. Backups are restored AT START-UP as well as in `finally`, and it runs under
the PROJECT interpreter (a bare `python3` with no pytest would make a missing-pytest exit read as a
false RED — NF-INFRA1).

    uv run python betting_ml/tests/nf_inj2b_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FANTASY = ROOT / "quant_sports_intel_models/football/nfl/fantasy"
RO = FANTASY / "nf_inj2b_rate_ordering.py"
RUN = FANTASY / "run_nf_inj2b_rate_ordering.py"
N15 = FANTASY / "run_nf1_5.py"
M1 = FANTASY / "nf1_model.py"
TESTS = "betting_ml/tests/test_nf_inj2b_rate_ordering.py"


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    #: the substring that must be GONE after the mutation — defeats lie #3
    gone: str
    tests: tuple[str, ...]


BREAKS: tuple[Break, ...] = (
    Break("the stratified RATE rule re-multiplies by another row's games — coherence, the property "
          "the whole story turns on, silently lost",
          RO,
          "            target[order] = rate_desc * gsafe[order]",
          "            target[order] = rate_desc * gsafe[sub]",
          gone="target[order] = rate_desc * gsafe[order]",
          tests=("test_the_stratified_rate_rule_is_coherent_by_construction",)),

    Break("the stratified RATE rule permutes the season POINT multiset instead of the per-game RATE "
          "multiset — the incumbent's defect wearing this story's name",
          RO,
          "            rate_desc = np.sort(base[sub] / gsafe[sub])[::-1]",
          "            rate_desc = np.sort(base[sub])[::-1]",
          gone="rate_desc = np.sort(base[sub] / gsafe[sub])[::-1]",
          tests=("test_the_stratified_rate_rule_is_coherent_by_construction",)),

    Break("a shared arm stops DELEGATING to NF-INJ2's kernel and falls through to a different rule "
          "— two implementations of one assignment, free to drift (NF-C0e)",
          RO,
          '    "point_by_score": "incumbent",',
          '    "point_by_score": "stratified",',
          gone='"point_by_score": "incumbent",',
          tests=("test_delegation_is_byte_identical",
                 "test_nf_inj2_arm_names_still_route_through_the_new_owner")),

    Break("an unknown arm silently falls through to the incumbent instead of raising — the typo "
          "that would make the whole bake-off vacuous",
          RO,
          '        raise ValueError(f"unknown arm {arm!r} — the declared field is {ARMS}")',
          '        arm = INCUMBENT_ARM',
          gone='raise ValueError(f"unknown arm',
          tests=("test_an_unknown_arm_raises_rather_than_scoring_the_incumbent",)),

    Break("a MATCHED PAIR is allowed to move two factors at once, so it attributes nothing "
          "(NF-D15 g′ / NF-D17)",
          RO,
          "        if same_rule == same_score:",
          "        if False:",
          gone="if same_rule == same_score:",
          tests=("test_assert_coherent_refuses_a_pair_that_moves_two_factors",)),

    Break("the served arm may be flipped without CLEARED gates — a bare flag flip ships a result "
          "the record does not support (NF-D22)",
          RO,
          '        if GATE_STATUS != "CLEARED":',
          "        if False:",
          gone='if GATE_STATUS != "CLEARED":',
          tests=("test_a_non_incumbent_arm_cannot_be_served_without_cleared_gates",)),

    Break("clearing the gates is collapsed into deciding to ship — the conflation NF-D21 and "
          "NF-D22 were both burned by",
          RO,
          "        if not PM_DISPOSITION_RECORDED:",
          "        if False:",
          gone="if not PM_DISPOSITION_RECORDED:",
          tests=("test_a_non_incumbent_arm_cannot_be_served_without_a_pm_disposition",)),

    Break("BOTH registrations may name a non-incumbent served arm — one logical thing, two "
          "execution owners (INC-30 / INC-36 / INC-38)",
          RO,
          "    if SERVED_ARM is not None and _RP.SERVED_ARM != _RP.INCUMBENT_ARM:",
          "    if False:",
          gone="if SERVED_ARM is not None and _RP.SERVED_ARM != _RP.INCUMBENT_ARM:",
          tests=("test_assert_coherent_refuses_two_owners_of_the_served_arm",)),

    Break("a pre-registered DEGENERATE may be served — an arm that exists to LOSE reaching the wire",
          RO,
          "    if served in DEGENERATE_ARMS:",
          "    if False:",
          gone="if served in DEGENERATE_ARMS:",
          tests=("test_a_degenerate_can_never_be_served",)),

    Break("`nf1_model` reads NF-INJ2's SERVED_ARM directly again — a SECOND owner of the served-arm "
          "decision",
          M1,
          "    use_arm = _RO.resolve_served_arm() if arm is None else str(arm)",
          "    use_arm = _RO._RP.SERVED_ARM if arm is None else str(arm)",
          gone="use_arm = _RO.resolve_served_arm()",
          tests=("test_apply_learned_ordering_routes_through_the_single_owner",)),

    Break("the RATE target silently falls back to the POINTS target when the pool carries no "
          "realized games — scoring an arm under another arm's name",
          N15,
          '''        raise KeyError(
            "the training pool carries no `real_games`, so a per-game RATE target cannot be formed. "
            "Refusing rather than silently falling back to the POINTS target, which would score an "
            "arm under another arm's name and make the whole bake-off vacuous.")''',
          "        return y",
          gone="the training pool carries no `real_games`",
          tests=("test_the_rate_target_refuses_a_pool_with_no_realized_games",)),

    Break("the RATE target is not points-per-game at all",
          N15,
          "    return y / np.where(np.isfinite(g) & (g > _RATE_GAMES_FLOOR), g, _RATE_GAMES_FLOOR)",
          "    return y",
          gone="return y / np.where(np.isfinite(g)",
          tests=("test_the_rate_target_is_points_over_games",)),

    Break("an unknown `score_target` is accepted instead of raising",
          N15,
          '        raise ValueError(f"score_target must be one of {SCORE_TARGETS}, got {score_target!r}")',
          '        score_target = "points"',
          gone="raise ValueError(f\"score_target must be one of",
          tests=("test_an_unknown_score_target_raises",)),

    Break("the in-fold re-selection RANKS ITS CANDIDATES ON THE EVALUATION SEASON — a peek dressed "
          "as a selection (NCAAF-P2.1)",
          N15,
          "    inner_va = tr[ts == projection_season - 1]",
          "    inner_va = tr[ts == projection_season]",
          gone="inner_va = tr[ts == projection_season - 1]",
          tests=("test_the_in_fold_reselection_never_reads_the_evaluation_fold",)),

    Break("the in-fold re-selection FITS its candidates on the ranking season too — leakage across "
          "the inner split",
          N15,
          "    inner_tr = tr[ts <= projection_season - 2]",
          "    inner_tr = tr[ts <= projection_season - 1]",
          gone="inner_tr = tr[ts <= projection_season - 2]",
          tests=("test_the_in_fold_reselection_never_reads_the_evaluation_fold",)),

    Break("the shipped entrypoint fits its own learner again instead of delegating — two "
          "implementations of one fit, free to drift (NF-C0e)",
          N15,
          "    out, chosen = score_from_frames(feats, pool, selections, nf11, projection_season, score_target)",
          "    out, chosen = {}, {}\n    _ = [l.fit(pool, pool) for l in ()]",
          gone="out, chosen = score_from_frames(",
          tests=("test_score_from_frames_is_the_single_fit_implementation",)),

    Break("PBO is carried as a PER-ARM pass/fail — a FIELD-level statistic read as a verdict about "
          "an arm (PLAT-CVP1 defect 4(a); MLB-HV2-1 measured the cost)",
          RUN,
          '            "dsr": bool(dsr is not None and dsr >= M14.DSR_MIN),',
          '            "dsr": bool(dsr is not None and dsr >= M14.DSR_MIN),\n            "pbo": True,',
          gone='"dsr": bool(dsr is not None and dsr >= M14.DSR_MIN),\n        }',
          tests=("test_pbo_is_never_carried_as_a_per_arm_gate",)),

    Break("`classify_null` is no longer told how the PBO was applied, so a per-arm misapplication "
          "would be silently converted into a refusal verdict",
          RUN,
          '            pbo=defl["pbo"], pbo_application="field")',
          '            pbo=defl["pbo"])',
          gone='pbo_application="field")',
          tests=("test_classify_null_is_told_the_pbo_application_and_the_declared_field",)),

    Break("the positive control re-implements the gates instead of running the study's own — the "
          "NF-C0e 'reads a value back under the key the code wrote' class",
          RUN,
          "        inject=inject, run_gates=gate_table, effect=INJECTED_EFFECT, check_null_control=True)",
          "        inject=inject, run_gates=lambda p: {'x': {'y': True}}, effect=INJECTED_EFFECT,\n        check_null_control=True)",
          gone="run_gates=gate_table",
          tests=("test_the_positive_control_runs_the_studys_own_gate_function",)),

    Break("the control's two-sided (vacuity) leg is switched off, so 'the family certifies noise' "
          "could never be detected (NF1.7 (a))",
          RUN,
          "        inject=inject, run_gates=gate_table, effect=INJECTED_EFFECT, check_null_control=True)",
          "        inject=inject, run_gates=gate_table, effect=INJECTED_EFFECT,\n        check_null_control=False)",
          gone="check_null_control=True)",
          tests=("test_the_positive_control_runs_the_studys_own_gate_function",)),

    Break("`inject(0.0)` plants an effect, so the control's own vacuity leg becomes vacuous",
          RUN,
          "        if eff != 0.0:",
          "        if True:",
          gone="if eff != 0.0:",
          tests=("test_the_injection_null_leg_plants_nothing",)),

    Break("the injection also treats the REFERENCE arm, so the incumbent moves with the candidates "
          "and every lift is measured against a moving bar",
          RUN,
          "    treated = [a for a in B.ARMS\n               if a not in B.DEGENERATE_ARMS and a not in B.REFERENCE_ARMS]",
          "    treated = [a for a in B.ARMS if a not in B.DEGENERATE_ARMS]",
          gone="treated = [a for a in B.ARMS\n               if a not in B.DEGENERATE_ARMS and a not in B.REFERENCE_ARMS]",
          tests=("test_the_injection_treats_every_arm_except_the_degenerates_and_the_reference",)),

    Break("`V` keeps the REFERENCE arm's structural zero — the MH2.1 (a) inflation the "
          "pre-registration declares away",
          RUN,
          "    drop = set(B.DEGENERATE_ARMS) | set(B.REFERENCE_ARMS)",
          "    drop = set(B.DEGENERATE_ARMS)",
          gone="drop = set(B.DEGENERATE_ARMS) | set(B.REFERENCE_ARMS)",
          tests=("test_v_excludes_the_degenerates_and_the_reference_arm",)),

    Break("the joint criterion stops reporting which positions the mechanism could ACT on, so a "
          "pass earned only on INACTIVE cells reads as a pass (NF-D20)",
          RUN,
          '    act = {p: bool(v.get(B.SCORE_OF[arm] or "points", {}).get("can_act"))\n           for p, v in activity.items()} if B.SCORE_OF[arm] in ("rate", "rate_reselect") else {}',
          "    act = {}",
          gone='act = {p: bool(v.get(B.SCORE_OF[arm] or "points", {}).get("can_act"))',
          tests=("test_the_joint_criterion_does_not_pass_on_inactive_positions_alone",)),

    Break("an UNEVALUATED gate stops blocking a SHIP — an arm ships on a pre-registered gate that "
          "never ran (NF1.7 (a): a check that did not run is not a check that passed)",
          RUN,
          '    unevaluated = sorted(k for k in SHIP_REQUIRES_EVALUATED if und.get(k))',
          "    unevaluated = []",
          gone="sorted(k for k in SHIP_REQUIRES_EVALUATED if und.get(k))",
          tests=("test_an_uncomputable_gate_is_never_reported_as_a_deflation_refusal",)),

    Break("an INACTIVE own-form ceiling blocks a ship — 'the anchor pair could not act' converted "
          "into 'the arm failed' (NF-W6d)",
          RUN,
          '    SHIP_REQUIRES_EVALUATED = ("pbo_field_level", "dsr", "fold_consistency", "bh_fdr",\n                               "ordering_not_regressed")',
          '    SHIP_REQUIRES_EVALUATED = ("pbo_field_level", "dsr", "fold_consistency", "bh_fdr",\n                               "ordering_not_regressed", "own_form_ceiling")',
          gone='"ordering_not_regressed")\n    unevaluated',
          tests=("test_an_uncomputable_gate_is_never_reported_as_a_deflation_refusal",)),

    Break("the UNDEFINED branch is switched off, so an unevaluated gate falls through to the ship "
          "branches — an arm ships on a gate that never ran, and an uncomputable one reads as a "
          "REFUSAL carrying a remedy it does not have (NF1.7 (a) / MH2 / NF-D18)",
          RUN,
          "    elif unevaluated:",
          "    elif False:",
          gone="elif unevaluated:",
          tests=("test_an_uncomputable_gate_is_never_reported_as_a_deflation_refusal",)),

    Break("the 2026 table reads a give-back key the reducer never writes — the column silently "
          "renders an em-dash and the number vanishes (the NF-C0e wrong-key class, render side)",
          RUN,
          '"median ratio": _fmt(gb.get("median_point_ratio")),',
          '"median ratio": _fmt(gb.get("median_ratio")),',
          gone='gb.get("median_point_ratio")',
          tests=("test_the_2026_section_reads_the_giveback_keys_the_reducer_actually_writes",)),

    Break("an UNCOMPUTABLE gate renders as a plain False — UNDEFINED conflated with FAILED, the "
          "conflation the seven-state null taxonomy exists to prevent (MH2)",
          RUN,
          '        if und.get(key):\n            return "UNDEFINED (not computable at this n — ⛔ not a failure)"',
          "        if False:\n            return 'x'",
          gone='return "UNDEFINED (not computable at this n',
          tests=("test_an_uncomputable_gate_renders_as_UNDEFINED_not_as_a_failure",)),

    Break("the shipped fit target stops DEFAULTING to points, so every caller that never heard of "
          "NF-INJ2b silently changes what it serves (NF-C0 / E8.6)",
          N15,
          '                             score_target: str = "points") -> dict[str, float]:',
          '                             score_target: str = "rate") -> dict[str, float]:',
          gone='score_target: str = "points") -> dict[str, float]:',
          tests=("test_the_shipped_score_target_addition_is_strictly_additive",)),

    Break("a smoke run overwrites the DECISIVE artifact — a code-path proof promoted to a gate",
          RUN,
          '    suffix = "_smoke" if args.smoke else ""',
          '    suffix = ""',
          gone='suffix = "_smoke" if args.smoke else ""',
          tests=("test_the_runner_never_reruns_a_smoke_as_a_gate",)),
)


def _restore_stale_backups() -> None:
    for path in (RO, RUN, N15, M1):
        bak = path.with_suffix(path.suffix + ".redproof")
        if bak.exists():
            bak.replace(path)
            print(f"  ⚠️ restored a stale backup: {bak.name}")


def _run(node: str) -> bool:
    """True when the clause turned RED."""
    r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{node}", "-q",
                        "-p", "no:randomly", "--no-header", "-x"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode != 0


def main() -> int:
    _restore_stale_backups()
    results, vacuous = [], []
    for b in BREAKS:
        src = b.path.read_text()
        n_hits = src.count(b.old)
        if n_hits != 1:
            print(f"🚨 ANCHOR NOT UNIQUE ({n_hits} hit(s)) — {b.name[:90]}")
            vacuous.append((b.name, f"anchor not unique ({n_hits} hits)"))
            continue
        # ⭐ THE SAME RULE, ONE LEVEL IN — and it bit while this file was being written. A `gone`
        # token that ALSO occurs elsewhere in the file can never disappear, so the harness reports
        # "the mutation did not move the asserted predicate" for a mutation that landed perfectly.
        # That is a FALSE VACUITY, the dangerous direction: it reads as a real finding and invites
        # weakening a correct guard (E11.24's "the break landed on the WRONG symbol", one step over).
        n_gone = src.count(b.gone)
        if b.gone and n_gone != 1:
            print(f"🚨 `gone` TOKEN NOT UNIQUE ({n_gone} hit(s)) — {b.name[:80]}")
            vacuous.append((b.name, f"`gone` token not unique to the mutated site ({n_gone} hits)"))
            continue
        bak = b.path.with_suffix(b.path.suffix + ".redproof")
        bak.write_text(src)
        try:
            b.path.write_text(src.replace(b.old, b.new, 1))
            after = b.path.read_text()
            if after == src:
                print(f"🚨 MUTATION DID NOT LAND — {b.name[:90]}")
                vacuous.append((b.name, "mutation did not land"))
                continue
            if b.gone and b.gone in after:
                print(f"🚨 MUTATION LANDED BUT LEFT {b.gone[:40]!r} — {b.name[:70]}")
                vacuous.append((b.name, "mutation did not move the asserted predicate"))
                continue
            reds = [t for t in b.tests if _run(t)]
            greens = [t for t in b.tests if t not in reds]
            results.append((b.name, reds, greens))
            print(f"{'✅ RED' if reds else '🚨 VACUOUS':>12}  {b.name[:96]}")
            for t in greens:
                print(f"              …green on its own break: {t}")
            if not reds:
                vacuous.append((b.name, "no clause turned red"))
        finally:
            b.path.write_text(bak.read_text())
            bak.unlink()
    print(f"\n{len(results) - len([v for v in vacuous if v[1] == 'no clause turned red'])}"
          f"/{len(BREAKS)} breaks turned a guard RED")
    if vacuous:
        print("\n🚨 VACUOUS GUARDS — a guard that cannot fail is not a guard:")
        for n, why in vacuous:
            print(f"   · {n[:100]}  ({why})")
        return 1
    print("✅ every deliberate break turned its own clause red")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
