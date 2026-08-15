#!/usr/bin/env python3
"""NF-LEAK1 RED PROOF — break the source one defect at a time, require the NAMED test to fail.

    uv run python betting_ml/tests/nf_leak1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A developer
tool, run by hand whenever `test_nf_leak1_scoring_probe_guard.py` is refactored.

WHY IT EXISTS. The story's own instruction is "⛔ no vacuous guards — the attack-simulation test must
actually fail on the pre-fix code", and this repo has shipped the vacuous shape more than once: a
guard a COMMENT could satisfy (INC-38), and an `and`-composed clause whose fixture was already
refused by a DIFFERENT clause so deleting the named clause changed nothing (NF-D17). Neither was
found by reading the test.

⭐ THE FIRST CASE IS THE PRE-FIX CODE ITSELF — the guard removed from both write paths. If the attack
simulation still passes with the enforcement deleted, the whole story is decoration.

⭐ EACH CASE NAMES ONE TEST and asserts THAT test fails; a break that reddens the whole file proves
much less (it can mean the clause worked, or that an import broke).

⭐ AND EACH CASE VERIFIES ITS MUTATION LANDED (`ANCHOR-MISSING`). A patch that silently no-ops
reports a perfectly good guard as vacuous, which reads as a finding and sends the next session after
a defect that does not exist (E11.24 #682).

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`,
which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

GUARD = REPO / "app/backend/services/scoring_probe_guard.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
DYNAMO = REPO / "app/backend/services/dynamo.py"

SUITE = "betting_ml/tests/test_nf_leak1_scoring_probe_guard.py"

# (label, file, find, replace, test_that_must_go_red)
CASES = [
    # ── the pre-fix world: no enforcement at all ───────────────────────────────────────────────
    (
        "PRE-FIX: remove the guard from the create path entirely",
        ROUTER,
        "    _enforce_scoring_probe_guard(user_id, ent, before=None, after=config)",
        "    pass",
        "test_an_isolating_probe_is_refused_by_the_api_not_by_the_editor",
    ),
    (
        "PRE-FIX: remove the guard from the EDIT path — the real attack surface",
        ROUTER,
        "    _enforce_scoring_probe_guard(\n"
        "        user_id, entitlement.resolve_entitlement(request), before=existing, after=config\n"
        "    )",
        "    pass",
        "test_the_real_attack_path_is_the_PUT_and_it_is_throttled_too",
    ),
    (
        "PRE-FIX: keep the shape rules but drop the budget (shape alone does NOT close it)",
        ROUTER,
        "    verdict = scoring_probe_guard.charge(\n"
        "        dynamo.get_fantasy_scoring_ledger(user_id), after, time.time()\n"
        "    )",
        "    verdict = scoring_probe_guard.BudgetVerdict(True, 0, {}, False, 1.0)",
        "test_a_free_account_that_burns_its_budget_is_throttled_with_a_retry_after",
    ),
    # ── the budget's own maths ─────────────────────────────────────────────────────────────────
    (
        "refill fast enough that the attack finishes inside the viable-path gate",
        GUARD,
        "BUDGET_REFILL_PER_DAY = 1.0",
        "BUDGET_REFILL_PER_DAY = 6.0",
        "test_the_measured_attack_plan_costs_more_than_the_pre_registered_gate",
    ),
    (
        "hand out a burst big enough to cover the whole walk",
        GUARD,
        "BUDGET_BURST = 12.0",
        "BUDGET_BURST = 60.0",
        "test_the_measured_attack_plan_costs_more_than_the_pre_registered_gate",
    ),
    (
        "shrink the burst below a real setup session",
        GUARD,
        "BUDGET_BURST = 12.0",
        "BUDGET_BURST = 3.0",
        "test_a_setup_session_of_a_handful_of_tweaks_is_never_throttled",
    ),
    (
        "never refill — the bucket becomes a lifetime cap on a season-long account",
        GUARD,
        "        float(state[\"tokens\"]) + elapsed * (BUDGET_REFILL_PER_DAY / SECONDS_PER_DAY),",
        "        float(state[\"tokens\"]),",
        "test_a_week_later_the_budget_has_refilled",
    ),
    (
        "charge for a REFUSED change, so retrying pushes the unlock further away",
        GUARD,
        "    if tokens < cost:\n        state[\"tokens\"] = tokens",
        "    if tokens < cost:\n        state[\"tokens\"] = max(0.0, tokens - cost)",
        "test_a_refused_change_does_not_spend_a_token",
    ),
    (
        "trust a stored token count, so a tampered ledger mints budget",
        GUARD,
        "        out[\"tokens\"] = min(BUDGET_BURST, max(0.0, float(ledger.get(\"tokens\", BUDGET_BURST))))",
        "        out[\"tokens\"] = float(ledger.get(\"tokens\", BUDGET_BURST))",
        "test_a_stored_ledger_cannot_grant_more_than_the_burst",
    ),
    (
        "fail CLOSED on an unreadable ledger, locking a real user out of their own league",
        GUARD,
        "    if not isinstance(ledger, dict):\n        return new_ledger(now)",
        "    if not isinstance(ledger, dict):\n        return {**new_ledger(now), \"tokens\": 0.0}",
        "test_an_unreadable_ledger_fails_open_rather_than_locking_the_user_out",
    ),
    (
        "let `touched` grow without bound on the shared 400 KB user item",
        GUARD,
        "        state[\"touched\"] = touched[-_MAX_TOUCHED:]",
        "        state[\"touched\"] = touched",
        "test_the_ledger_cannot_grow_without_bound_on_the_user_item",
    ),
    # ── the meter is on the SCORING, not on the save ───────────────────────────────────────────
    (
        "charge every save, so renaming a league burns a token",
        ROUTER,
        "    if not scoring_probe_guard.scoring_changed(before, after):\n        return",
        "    if False:\n        return",
        "test_editing_everything_EXCEPT_the_scoring_is_never_throttled",
    ),
    (
        "compare whole configs, so a roster edit reads as a scoring change",
        GUARD,
        "    return scoring_fingerprint(before) != scoring_fingerprint(after)",
        "    return (before or {}) != (after or {})",
        "test_an_edit_that_does_not_touch_the_scoring_is_never_charged",
    ),
    (
        "count captured (unscorable) terms as scoring, billing users for fidelity",
        GUARD,
        "        if key in STAT_FIELD:\n            out[str(key)] = _as_float(raw)",
        "        out[str(key)] = _as_float(raw)",
        "test_a_captured_only_term_is_not_a_scoring_change",
    ),
    (
        "ignore position_bonuses — the second door into the same room",
        GUARD,
        "    for pos, terms in (scoring.get(\"position_bonuses\") or {}).items():",
        "    for pos, terms in {}.items():",
        "test_position_bonuses_are_metered_like_per_stat_weights",
    ),
    # ── the shape rules ────────────────────────────────────────────────────────────────────────
    (
        "drop the core-stat rule, re-admitting the exact-recovery isolation probe",
        GUARD,
        "    if core < MIN_CORE_STATS:",
        "    if False:",
        "test_no_single_term_config_is_admissible_whichever_stat_it_names",
    ),
    (
        "set the core threshold to 1, which a probe isolating a CORE stat satisfies",
        GUARD,
        "MIN_CORE_STATS = 2",
        "MIN_CORE_STATS = 1",
        "test_no_single_term_config_is_admissible_whichever_stat_it_names",
    ),
    (
        "count TERMS instead of core families — the dataless-key padding bypass",
        GUARD,
        "    core = sum(\n        1 for stat in CORE_STATS\n"
        "        if any(k == stat or k.endswith(f\":{stat}\") for k in fingerprint)\n    )",
        "    core = len(fingerprint)",
        "test_a_probe_cannot_pad_a_degenerate_config_with_dataless_keys",
    ),
    (
        "drop the dynamic-range cap, restoring deep magnitude packing",
        GUARD,
        "        if smallest > 0 and largest / smallest > MAX_WEIGHT_RATIO:",
        "        if False:",
        "test_a_magnitude_packed_probe_is_refused",
    ),
    (
        "drop the caller's [METRIC] line, so a run of dropped charges is invisible",
        ROUTER,
        '            "[METRIC] fantasy_scoring_ledger_write_failed=1 user=%s'
        ' — this change went uncounted",',
        '            "ledger note for %s",',
        "test_a_failed_ledger_write_is_reported_rather_than_swallowed",
    ),
    (
        "'raise' the ratio cap to 10^4 — the LOOSENING this story shipped and measured",
        GUARD,
        "MAX_WEIGHT_RATIO = 400.0",
        "MAX_WEIGHT_RATIO = 10000.0",
        "test_the_dynamic_range_cap_is_tighter_than_what_the_system_already_enforced",
    ),
    (
        "tighten the ratio cap below the widest REAL league (a rule pointed at customers)",
        GUARD,
        "MAX_WEIGHT_RATIO = 400.0",
        "MAX_WEIGHT_RATIO = 100.0",
        "test_every_captured_real_imported_league_still_saves",
    ),
    (
        "require all six core families, refusing a preset-shaped league",
        GUARD,
        "MIN_CORE_STATS = 2",
        "MIN_CORE_STATS = 7",
        "test_every_shipped_preset_still_saves",
    ),
    # ── the probe detector ─────────────────────────────────────────────────────────────────────
    (
        "never flag a walk, so the surcharge is dead code",
        GUARD,
        "    return len(delta) == 1 and len(touched) >= PROBE_TOUCH_THRESHOLD",
        "    return False",
        "test_a_probe_walk_pays_the_surcharge_and_is_logged_against_the_account",
    ),
    (
        "arm the detector immediately, surcharging a real user's second tweak",
        GUARD,
        "PROBE_TOUCH_THRESHOLD = 10",
        "PROBE_TOUCH_THRESHOLD = 0",
        "test_the_first_few_single_stat_tweaks_are_not_treated_as_probing",
    ),
    (
        "count BULK writes as walk steps — the false positive the first cut shipped",
        GUARD,
        "    if len(delta) == 1:\n        touched = list(state[\"touched\"])\n"
        "        if delta[0] not in touched:\n            touched.append(delta[0])",
        "    if True:\n        touched = list(state[\"touched\"])\n"
        "        for _k in delta:\n"
        "            if _k not in touched:\n                touched.append(_k)",
        "test_the_first_few_single_stat_tweaks_are_not_treated_as_probing",
    ),
    # ── who is exempt, and the read path ───────────────────────────────────────────────────────
    (
        "meter subscribers too, degrading a product they already get in full",
        ROUTER,
        "    if getattr(ent, \"fantasy\", False):\n        return",
        "    if False:\n        return",
        "test_a_subscriber_is_never_throttled_on_the_same_traffic",
    ),
    (
        "run the write rules on the READ path (E9.49's retroactive-validator outage)",
        ROUTER,
        "    return _serialize_leagues(dynamo.list_fantasy_leagues(user_id))",
        "    records = dynamo.list_fantasy_leagues(user_id)\n"
        "    for r in records:\n"
        "        if scoring_probe_guard.shape_violations(r):\n"
        "            raise HTTPException(status_code=400, detail='bad league')\n"
        "    return _serialize_leagues(records)",
        "test_reading_a_league_is_never_gated_by_the_write_rules",
    ),
    (
        "charge a token for a config the shape rules were going to refuse anyway",
        ROUTER,
        "    problems = scoring_probe_guard.shape_violations(after)\n"
        "    if problems:\n        raise HTTPException(status_code=400, detail=\"; \".join(problems))",
        "    problems = scoring_probe_guard.shape_violations(after)",
        "test_an_isolating_probe_is_refused_by_the_api_not_by_the_editor",
    ),
    # ── the ledger's persistence ───────────────────────────────────────────────────────────────
    (
        "report a failed ledger write as a SUCCESS, hiding that the budget stopped counting",
        DYNAMO,
        "        return True\n    except Exception:\n"
        "        logger.warning(\"dynamo.put_fantasy_scoring_ledger failed for user=%s\", user_id)\n"
        "        return False",
        "        return True\n    except Exception:\n        return True",
        "test_a_failed_ledger_write_is_reported_rather_than_swallowed",
    ),
    # ── the honest framing ─────────────────────────────────────────────────────────────────────
    (
        "let the module claim the leak is closed",
        GUARD,
        "⭐ THE HONEST FRAMING, UP FRONT — THIS IS NOT AND CANNOT BE \"ZERO LEAK\"",
        "this leak is closed and the stat line is impossible to reconstruct",
        "test_no_guard_here_claims_the_leak_is_closed",
    ),
    (
        "delete the residual the module is required to name",
        GUARD,
        "⚠️ **THE RESIDUAL, STATED PLAINLY.**",
        "A note.",
        "test_the_residual_multi_account_path_is_recorded",
    ),
]


def run_one(test_name: str) -> str:
    """`"PASS"`, `"FAIL"`, or `"NOT-COLLECTED"` for the named test.

    🚨 THE BUG THIS SIGNATURE EXISTS TO PREVENT, FOUND IN THIS FILE'S FIRST CUT. It used to select
    with the node id `f"{SUITE}::{test_name}"` and return `returncode == 0`. Every test here lives
    inside a CLASS, so that node id matches nothing, pytest exits **4** ("no tests ran"), and a
    non-zero exit read as RED. All 31 cases reported RED and NOT ONE OF THEM HAD RUN — a harness
    that certified itself while measuring nothing, which is the precise shape it was written to
    catch (E11.24 #682: a RED proof must prove its own mutation landed AND that the test executed).

    So: select with `-k` (class-agnostic) and treat "no tests ran" as its OWN status. An
    un-collected test is never evidence, in either direction.
    """
    r = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-k", test_name, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    output = r.stdout + r.stderr
    if r.returncode == 4 or "no tests ran" in output:
        return "NOT-COLLECTED"
    return "PASS" if r.returncode == 0 else "FAIL"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}
    results = []

    # ⭐ BASELINE FIRST. A case whose test does not PASS on unmutated source proves nothing when it
    # later fails — "it went red" would just be "it was already red". Checked once per distinct
    # test rather than per case, since several cases name the same clause.
    baseline: dict[str, str] = {}
    for test_name in dict.fromkeys(c[4] for c in CASES):
        baseline[test_name] = run_one(test_name)
    broken = {t: s for t, s in baseline.items() if s != "PASS"}
    if broken:
        for test_name, status in broken.items():
            print(f"🚨 BASELINE {status}: {test_name} — no case naming it can be evidence")
        return 1

    try:
        for label, path, find, replace, test_name in CASES:
            original = backups[path]
            if find not in original:
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            path.write_text(original.replace(find, replace, 1))
            try:
                outcome = run_one(test_name)
            finally:
                path.write_text(original)
            results.append((label, test_name, {
                "PASS": "GREEN — VACUOUS",
                "FAIL": "RED",
                "NOT-COLLECTED": "NOT-COLLECTED",
            }[outcome]))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = sum(1 for _, _, s in results if s == "RED")
    for label, test_name, status in results:
        mark = "✅" if status == "RED" else "🚨"
        print(f"{mark} {label.ljust(width)}  →  {status}   ({test_name})")

    print(f"\n{red}/{len(results)} breaks turned their named clause RED "
          f"(all {len(baseline)} named tests verified PASSING on unmutated source first).")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard; "
              "a NOT-COLLECTED case measured nothing at all.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
