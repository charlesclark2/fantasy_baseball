"""NF-W8-0b RED proof — break the source, prove each guard goes RED.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w8_0b.py

A guard that cannot FAIL is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness applies
one deliberate defect at a time and asserts the named guard turns RED. The four disciplines this
repo has paid for are enforced, exactly as in NF-W8-0's harness:

- **the mutation must LAND** (E11.24 #682) — a no-op break reports a FALSE "the guard is
  vacuous", which reads as a real finding and invites weakening a correct guard;
- **the anchor must be UNIQUE** (#885) — a replace can otherwise land on the WRONG symbol;
- **the asserted token must be GONE** (#815) — a break that writes without moving the asserted
  predicate is a false GREEN;
- **a stalled leg reports HUNG**, never silently green.

⛔ Not a pytest module: it MUTATES tracked source and restores it in a `finally`.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_TP = Path(__file__).with_name("fp_tail_point.py")
_XP = Path(__file__).with_name("fp_cross_position.py")
_W80 = Path(__file__).with_name("run_nf_w8_0_cross_position.py")
_R0B = Path(__file__).with_name("run_nf_w8_0b_tail_point.py")
_TESTS = _ROOT / "betting_ml/tests/test_nf_w8_0b_tail_point.py"
_RECORD = Path(__file__).with_name("ablation_results") / "nf_w8_0b_tail_point.json"
_W80_TESTS = _ROOT / "betting_ml/tests/test_nf_w8_0_cross_position.py"
_TIMEOUT_S = 300


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    tests: tuple[str, ...]
    defect: str
    suite: Path = _TESTS


BREAKS: tuple[Break, ...] = (
    # ── §1 the transform's arithmetic ──────────────────────────────────────────────────────────
    Break("reweight_dropped_leaving_a_multiplicative_bias", _TP,
          "    return COVERED_MASS * XP.bank_point(b) + tc[\"hi\"] + tc[\"lo\"]",
          "    return XP.bank_point(b) + tc[\"hi\"] + tc[\"lo\"]",
          ("TestTailCompletedPointIsExactWhereItMustBe::"
           "test_degenerate_bank_returns_its_own_value_exactly",
           "TestTailCompletedPointIsExactWhereItMustBe::"
           "test_uniform_quantile_function_is_exact"),
          "⭐ the load-bearing 0.995 re-weight is dropped: every point gains +0.5% OF ITS OWN "
          "LEVEL, manufacturing exactly the cross-position differential family A measures"),
    Break("excess_term_dropped_from_the_tail_integral", _TP,
          "    k = float(np.log(s0 / s) + 1.0)                      # ln 2 + 1",
          "    k = float(np.log(s0 / s))                            # ln 2",
          ("TestTailCompletedPointIsExactWhereItMustBe::"
           "test_exponential_tail_is_recovered_and_beats_the_truncated_grid_mean",
           "TestTailCompletedPointIsExactWhereItMustBe::"
           "test_right_skewed_shapes_move_strictly_toward_the_truth"),
          "the mean-EXCESS term is dropped, so the tail contributes only its threshold mass — "
          "the completion under-extends and no longer recovers E[Y]"),
    Break("tail_scale_read_from_the_wrong_anchor_span", _TP,
          "    log_hi = float(np.log((1.0 - inner_hi) / (1.0 - ANCHOR_OUTER_HI)))",
          "    log_hi = 4.0 * float(np.log((1.0 - inner_hi) / (1.0 - ANCHOR_OUTER_HI)))",
          ("TestTailCompletedPointIsExactWhereItMustBe::"
           "test_exponential_tail_is_recovered_and_beats_the_truncated_grid_mean",),
          "β_hi is divided by the wrong log-span, so the exponential tail is mis-scaled and the "
          "Exp(1) oracle is no longer recovered"),
    Break("off_grid_anchor_silently_snapped", _TP,
          "    if idx >= N_LEVELS or abs(float(GRID_LEVELS[idx]) - level) > 1e-9:",
          "    if idx >= N_LEVELS or abs(float(GRID_LEVELS[idx]) - level) > 1e9:",
          ("TestTransformIsDeterministic::test_an_off_grid_anchor_is_refused_never_snapped",),
          "an anchor level not ON the grid is snapped to a neighbour — a different transform "
          "wearing this one's name"),
    Break("non_finite_bank_nan_meaned_instead_of_refused", _TP,
          "    if not np.isfinite(b).all():",
          "    if False:",
          ("TestTransformIsDeterministic::"
           "test_a_partly_absent_bank_is_refused_never_nan_meaned",),
          "a partly-absent bank is scored anyway — NF-W3: a different POPULATION, not a smaller "
          "one, and the leaderboard silently compares arms on different rows"),
    Break("transform_starts_fitting_on_outcomes", _TP,
          "def tail_scales(bank: np.ndarray, *, inner_hi: float = ANCHOR_INNER_HI) -> dict:",
          "def tail_scales(bank: np.ndarray, y=None, *, inner_hi: float = ANCHOR_INNER_HI) "
          "-> dict:  # MC.fit_tail_betas(bank, y)",
          ("TestTransformIsDeterministic::test_the_transform_signature_takes_no_outcomes",
           "TestTransformIsDeterministic::test_the_module_never_calls_a_tail_ESTIMATOR"),
          "⭐ the point becomes outcome-dependent — re-importing NF-W8-0 §12.3a's "
          "non-stationarity floor, the single thing this successor exists to step around",),

    # ── §2 the swap materiality floor ──────────────────────────────────────────────────────────
    Break("floor_becomes_a_result_chosen_summary", _TP,
          '    if statistic != SWAP_FLOOR_STATISTIC:',
          '    if False:',
          ("TestMaterialityFloor::test_an_unregistered_summary_statistic_is_refused",),
          "the floor's summary statistic can be swapped after a score — the E2.1-r inversion in "
          "its most literal form"),
    Break("unformable_floor_silently_becomes_zero", _TP,
          '        return {"floor_ppr": None, "statistic": statistic, "n_pairs": 0,',
          '        return {"floor_ppr": 0.0, "statistic": statistic, "n_pairs": 0,',
          ("TestMaterialityFloor::test_an_unformable_floor_is_none_never_zero",),
          "a floor that could not be FORMED becomes floor-0, silently restoring the "
          "predecessor's no-floor rule under this story's name (NF1.7 (a))"),
    Break("floor_ignored_by_the_activity_rule", _XP,
          '    material = True if floor_ppr is None else bool(abs(pooled) >= float(floor_ppr))',
          '    material = True',
          ("TestMaterialityFloor::test_a_precise_but_immaterial_shift_is_inactive",
           "TestMaterialityFloor::test_the_floor_reaches_the_clause_not_only_the_activity_helper"),
          "the floor is accepted and then ignored — a WIRED-but-never-INVOKED gate (NF-C0e), "
          "which reads as enforced and enforces nothing"),
    Break("floor_replaces_precision_instead_of_ANDing_it", _XP,
          '    out = {"active": bool(precise and material), "pooled_shift": round(pooled, 4),',
          '    out = {"active": bool(material), "pooled_shift": round(pooled, 4),',
          ("TestMaterialityFloor::test_a_material_but_IMPRECISE_shift_stays_inactive",
           "TestMaterialityFloor::test_the_floor_can_only_REMOVE_activity_never_add_it"),
          "the floor stops being an AND, so a large but IMPRECISELY estimated shift becomes "
          "active — a NEW way to refuse, not a materiality filter"),
    Break("floor_never_reaches_the_derive_layer", _W80,
          "        swap = XP.swap_clause(before, after, floor_ppr=swap_floor_ppr)",
          "        swap = XP.swap_clause(before, after)",
          ("TestDerive0bEndToEnd::"
           "test_the_materiality_floor_is_recorded_with_its_sensitivity_band",),
          "the floor is computed and reported but never plumbed into the CLAUSE — reported ≠ "
          "applied (the E11.24 'writing the caveat is not applying it' class)"),

    # ── §3 the predecessor's decided behaviour ─────────────────────────────────────────────────
    Break("predecessor_default_silently_gains_a_floor", _XP,
          "def swap_activity(shifts_by_fold: np.ndarray, *, se_mult: float = ACTIVITY_SE_MULT,\n"
          "                  floor_ppr: float | None = None) -> dict:",
          "def swap_activity(shifts_by_fold: np.ndarray, *, se_mult: float = ACTIVITY_SE_MULT,\n"
          "                  floor_ppr: float | None = 0.1955) -> dict:",
          ("TestPredecessorDefaultsUnchanged::test_swap_activity_default_is_the_no_floor_rule",),
          "⭐ the successor's rule leaks into the DECIDED predecessor's default — its recorded "
          "swap verification would silently change (E2.1-r)"),
    Break("predecessor_default_point_reader_changes", _W80,
          "    read = XP.bank_point if point_reader is None else point_reader",
          "    read = point_reader if point_reader is not None else (lambda b: "
          "XP.bank_point(b) * 0.995)",
          ("TestPredecessorDefaultsUnchanged::"
           "test_run_position_default_reader_is_the_truncated_grid_mean",),
          "the DECIDED story's registered ranking point moves under its own default — a "
          "successor silently rewriting a decided record's numbers"),
    Break("gridmean_disclosure_leaks_into_the_predecessor_schema", _W80,
          '    if point_reader is not None:                 # the incumbent read, kept BESIDE '
          'for disclosure',
          '    if True:                                     # leaked into every run',
          ("TestPredecessorDefaultsUnchanged::"
           "test_the_gridmean_columns_are_only_emitted_under_a_reader",),
          "the successor's disclosure columns appear in the predecessor's own rows schema"),

    # ── §4 the verdict + the ONE definition of cross_rankable ──────────────────────────────────
    Break("layer_repaired_gap_claims_the_deterministic_result", _TP,
          '        "cross_rankable": bool(state == V_CLOSES),',
          '        "cross_rankable": bool(state in (V_CLOSES, V_REMOVED)),',
          ("TestTailPointVerdict::test_a_layer_repaired_gap_is_NOT_the_deterministic_claim",),
          "⭐ a gap closed only by a FITTED layer is reported as this story's headline — which "
          "re-imports the non-stationarity floor the story exists to step around"),
    Break("undefined_harness_reads_as_cross_rankable", _TP,
          "    if base == XP.V_UNDEFINED or gap is None:",
          "    if False:",
          ("TestTailPointVerdict::"
           "test_an_unevaluable_harness_is_undefined_never_cross_rankable",),
          "a harness that DID NOT RUN is read as a verdict (NF1.7 (a))"),
    Break("null_stops_stating_its_own_MDE", _TP,
          '                  f"no pairwise contrast survives BH(q={XP.BH_Q}) at a max pairwise '
          'MDE of "\n                  f"{mde} PPR. ',
          '                  f"no pairwise contrast survives BH(q={XP.BH_Q}). ',
          ("TestTailPointVerdict::test_no_gap_closes_and_is_cross_rankable_with_no_layer",),
          "the null stops being 'no artifact larger than X PPR' and becomes 'no artifact' "
          "(MH2.6)"),
    Break("promote_blockers_stop_inheriting_the_predecessors", _TP,
          "PROMOTE_BLOCKERS: tuple[str, ...] = XP.PROMOTE_BLOCKERS + (",
          "PROMOTE_BLOCKERS: tuple[str, ...] = (",
          ("TestTailPointVerdict::test_promote_blockers_inherit_the_predecessors_in_full",),
          "the QB Option-B caveat and NF-W7c's calibrated-default disclosure quietly stop "
          "travelling with the input"),

    # ── §5 the derive layer + artifact hygiene ─────────────────────────────────────────────────
    Break("floor_read_diverges_from_the_recorded_family_a", _R0B,
          "    _assert_family_a_agrees(pre_a, out[\"family_a\"])",
          "    pass",
          ("TestDerive0bEndToEnd::"
           "test_the_family_a_agreement_check_is_actually_INVOKED_by_the_derivation",),
          "the floor may be formed off a DIFFERENT family A than the record reports — two "
          "readers of one field, two rule sets (E9.61)"),
    Break("unformable_floor_does_not_stop_the_run", _R0B,
          '        raise ValueError(f"the §6 materiality floor could not be formed: '
          '{floor[\'note\']}")',
          '        floor["floor_ppr"] = 0.0',
          ("TestDerive0bEndToEnd::"
           "test_an_unformable_floor_raises_rather_than_silently_dropping_the_rule",),
          "an unformable floor degrades to the predecessor's rule instead of refusing"),
    Break("path_proof_fallback_drops_to_the_predecessors_no_floor_rule", _R0B,
          '        floor = floor | {"floor_ppr": float("inf"), '
          '"unformable_on_a_path_proof": True,',
          '        floor = floor | {"floor_ppr": 0.0, "unformable_on_a_path_proof": True,',
          ("TestDerive0bEndToEnd::"
           "test_the_smoke_path_proof_makes_the_clause_UNEVALUABLE_not_the_predecessors_rule",),
          "⭐ the `--smoke` path proof's unformable-floor fallback degrades to floor-0 — which "
          "IS the predecessor's no-floor rule, wearing this story's name (NF1.7 (a))"),
    Break("verdict_reachable_guard_lets_a_decisive_run_take_the_path_proof_fallback", _R0B,
          "    verdict_reachable = (len(rows_by_fold) - 1) >= 4",
          "    verdict_reachable = False",
          ("TestDerive0bEndToEnd::"
           "test_an_unformable_floor_on_a_run_that_WOULD_reach_a_verdict_still_raises",),
          "a run that CAN decide silently takes the path-proof relaxation instead of refusing"),
    Break("published_trigger_loses_its_family_scoping", _R0B,
          '    if (out.get("classification") or {}).get("retest_trigger"):',
          '    if False:',
          ("TestDerive0bEndToEnd::"
           "test_a_rendered_retest_trigger_is_always_scoped_to_the_family_it_describes",),
          "⭐ the record publishes `+2 folds` with nothing saying it describes FAMILY B — a "
          "reader applies it to family A, whose null is arithmetically bounded (NF-D18)"),
    # ⚠️ ARTIFACT guards: these read the COMMITTED RECORD, so a SOURCE mutation cannot move them
    # (a first cut targeted the source and came back GREEN for exactly that reason). The record
    # is the thing under test, so the record is what the break must mutate.
    Break("record_bound_reverts_to_the_mean_of_fold_means", _RECORD,
          '"completion_delta_pooled": {\n    "QB": 0.045805,\n    "RB": 0.032641,\n'
          '    "WR": 0.051944,\n    "TE": 0.038152\n  },\n'
          '  "completion_delta_pooled_spread": 0.019303',
          '"completion_delta_pooled": {\n    "QB": 0.0462,\n    "RB": 0.0331,\n'
          '    "WR": 0.0498,\n    "TE": 0.0383\n  },\n'
          '  "completion_delta_pooled_spread": 0.0167',
          ("TestCommittedRecordConsistency::test_the_deterministic_bound_the_headline_rests_on",),
          "the record's headline bound reverts to a MEAN OF FOLD MEANS — the identity stops "
          "holding and the published bound (0.0167) is breached by RB|WR (0.0193) (NF1.8)"),
    Break("writer_shifts_the_band_with_the_point", _W80,
          '        w["point_vs_bank_offset"] = w["point_recal"] - w["point_raw"]',
          '        w["point_vs_bank_offset"] = (w["point_recal"] - w["point_raw"]); '
          'w["p50"] = w["p50"] + 0.25',
          ("TestDerive0bEndToEnd::"
           "test_the_written_input_carries_the_certified_quantiles_byte_identically",),
          "⭐ the NF-TR2 apply_to_band mistake: the CERTIFIED band moves with the point — this "
          "story changes only how a POINT is READ, so banks_untouched must catch it and demote"),
    Break("stored_scores_rounded_capping_every_reproduction_pin", _W80,
          '        "scores": {k: float(v) for k, v in scores.items()},',
          '        "scores": {k: round(float(v), 6) for k, v in scores.items()},',
          ("TestRegistrationAndArtifactHygiene::test_pin_scores_are_stored_at_full_precision",),
          "⛔ the NF-W8-0 smoke bug re-armed: rounding caps every pin at ~5e-7 against 1e-9, so "
          "the decisive run returns UNDEFINED at all four positions while reproducing perfectly"),
    Break("successor_forks_the_generator_code_path", _R0B,
          "    fold_results = [W80.run_fold(f, feat, smap, draws=draws, matrix_key=matrix_key,",
          "    def run_fold(*a, **k): ...\n"
          "    fold_results = [run_fold(f, feat, smap, draws=draws, matrix_key=matrix_key,",
          ("TestRegistrationAndArtifactHygiene::"
           "test_the_runner_drives_the_shared_harness_rather_than_forking_it",),
          "the successor forks the generator path — the reproduction pins can then drift and "
          "family A gains a second rule set (NF-W7d / E9.61)"),
    Break("successor_writes_the_decided_predecessors_paths", _R0B,
          '_ROWS_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0b_rows"',
          '_ROWS_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0_rows"',
          ("TestRegistrationAndArtifactHygiene::"
           "test_the_runner_refuses_to_write_the_predecessors_decided_paths",),
          "⭐ the NCAAF-P2.1 S1-serve lesson: a successor overwrites a DECIDED story's artifacts "
          "with no error and no test failure"),

    # ── §6 the predecessor's OWN suite must still hold (the decided record is untouched) ───────
    Break("inactive_everywhere_starts_counting_as_a_PASS", _XP,
          '        "passes": (None if n_active == 0 else bool(all(active_pass))),',
          '        "passes": (True if n_active == 0 else bool(all(active_pass))),',
          ("TestSwapClause::test_inactive_everywhere_is_not_a_pass",),
          "⭐ the floor makes INACTIVE_EVERYWHERE far more reachable, so the predecessor's "
          "semantics become load-bearing here: an inactive clause must neither pass nor refuse "
          "(NF-D20 — an inactive position is UNINFORMATIVE, never a pass). NF-W8-0's OWN suite "
          "is the tripwire, proving this story did not move the decided record.",
          _W80_TESTS),
)


def _run(tests: tuple[str, ...], suite: Path) -> tuple[str, str]:
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    for t in tests:
        args += [f"{suite}::{t}"]
    try:
        p = subprocess.run(args, cwd=_ROOT, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "HUNG", f"no verdict within {_TIMEOUT_S}s"
    tail = (p.stdout or p.stderr).strip().splitlines()
    return ("RED" if p.returncode != 0 else "GREEN"), (tail[-1] if tail else "")


def main() -> int:
    rows, failures = [], 0
    for b in BREAKS:
        original = b.path.read_text()
        occurrences = original.count(b.old)
        if occurrences != 1:
            rows.append((b.name, "ANCHOR", f"anchor occurs {occurrences}× — must be exactly 1"))
            failures += 1
            continue
        try:
            b.path.write_text(original.replace(b.old, b.new, 1))
            on_disk = b.path.read_text()
            if on_disk == original:
                rows.append((b.name, "NO-OP", "mutation did not LAND (E11.24 #682)"))
                failures += 1
                continue
            if b.old in on_disk:
                rows.append((b.name, "TOKEN", "asserted token still present (#815)"))
                failures += 1
                continue
            verdict, note = _run(b.tests, b.suite)
        finally:
            b.path.write_text(original)
        rows.append((b.name, verdict, note))
        if verdict != "RED":
            failures += 1

    w = max(len(r[0]) for r in rows)
    print(f"\nNF-W8-0b RED proof — {len(BREAKS)} deliberate defects\n")
    for name, verdict, note in rows:
        print(f"  {name.ljust(w)}  {verdict:<6}  {note}")
    print(f"\n{len(rows) - failures}/{len(rows)} RED\n")
    if failures:
        print("⛔ a guard that does not go RED on a deliberate defect is VACUOUS", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
