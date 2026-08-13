#!/usr/bin/env python3
"""G100-D0-R1 RED PROOF — break the source one defect at a time, require the NAMED test to fail.

    uv run python betting_ml/tests/g100_d0_r1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_g100_d0_r1_signup_authoritative.py` is refactored.

Same shape and the same reasons as `g100_c1_red_proof.py`: a green suite proves nothing on its
own, this repo has shipped a guard a COMMENT could satisfy (INC-38) and an `and`-composed clause
whose fixture a DIFFERENT clause already refused (NF-D17), and neither was found by reading the
test. Each case names ONE test and requires THAT test to go red; each case verifies its mutation
actually landed, because a patch that silently no-ops reports a perfectly good guard as vacuous —
a scarier and completely wrong finding (#682).

⭐ THE FIRST TWO CASES ARE THE STORY. Case 1 restores the pre-R1 rule (emit on intent) and case 2
restores its mirror (let intent override an authoritative server answer). They are the two
directions of the bug, and a suite that catches only one leaves the funnel wrong.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --`, which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

POST_SIGNIN = REPO / "frontend/lib/post-signin.ts"
TERMS = REPO / "frontend/lib/terms.ts"
GATE = REPO / "frontend/components/terms-gate.tsx"
DYNAMO = REPO / "app/backend/services/dynamo.py"
AUTH = REPO / "app/backend/routers/auth.py"

SUITE = "betting_ml/tests/test_g100_d0_r1_signup_authoritative.py"

# (label, file, find, replace, test_that_must_go_red)
CASES = [
    # ── the two directions of the bug ─────────────────────────────────────────────────────────
    (
        "restore the PRE-R1 rule: emit on the button, not on the server's answer",
        POST_SIGNIN,
        "  if (acceptance.known) {\n    if (acceptance.created) {",
        '  if (acceptance.known) {\n    if (intent === "signup") {',
        "test_a_new_account_at_the_signin_door_is_counted",
    ),
    (
        "let the client's intent override an authoritative created:false",
        POST_SIGNIN,
        "  if (acceptance.known) {",
        "  if (false) {",
        "test_a_returning_user_who_clicks_sign_up_is_not_counted",
    ),
    (
        "fall through from the known branch into the intent fallback",
        POST_SIGNIN,
        "    }\n    return\n  }",
        "    }\n  }",
        "test_a_returning_user_who_clicks_sign_up_is_not_counted",
    ),
    # ── the deploy skew (NF-C0 / E8.6) ────────────────────────────────────────────────────────
    (
        "read an ABSENT `created` as false, zeroing step 2 for the whole skew window",
        TERMS,
        'if (!res || typeof res.created !== "boolean") return { known: false }\n'
        "  return { known: true, created: res.created }",
        "return { known: true, created: Boolean(res && res.created) }",
        "test_an_absent_field_is_a_deploy_skew_not_a_negative_answer",
    ),
    (
        "stop labelling the skew-window event, making it indistinguishable from an authoritative one",
        POST_SIGNIN,
        'signal: "intent_fallback"',
        'signal: "server"',
        "test_the_skew_fallback_exists_and_is_labelled_on_the_wire",
    ),
    # ── the server signal ─────────────────────────────────────────────────────────────────────
    (
        "derive `created` from a SEPARATE read instead of the atomic write",
        DYNAMO,
        '        ReturnValues="ALL_OLD",\n    )\n',
        "    )\n    resp = {\"Attributes\": _users_table().get_item("
        'Key={"user_id": user_id}).get("Item", {})}\n',
        "test_the_answer_comes_from_the_write_itself_not_a_second_read",
    ),
    (
        "key on whether an ITEM existed rather than on the acceptance ATTRIBUTE",
        DYNAMO,
        'return (resp.get("Attributes") or {}).get("tos_accepted_at") is None',
        'return resp.get("Attributes") is None',
        "test_an_existing_profile_with_no_acceptance_still_reports_created",
    ),
    (
        "report every acceptance as a fresh signup",
        DYNAMO,
        'return (resp.get("Attributes") or {}).get("tos_accepted_at") is None',
        "return True",
        "test_an_account_that_already_accepted_reports_not_created",
    ),
    (
        "drop if_not_exists, so a re-acceptance moves the canonical timestamp",
        DYNAMO,
        'UpdateExpression="SET #ta = if_not_exists(#ta, :now), #tv = :ver",',
        'UpdateExpression="SET #ta = :now, #tv = :ver",',
        "test_the_write_still_never_overwrites_the_original_timestamp",
    ),
    # ── the router ────────────────────────────────────────────────────────────────────────────
    (
        "hardcode created:false rather than reporting what the store said",
        AUTH,
        "    return TermsAcceptanceResult(created=created)",
        "    return TermsAcceptanceResult(created=False)",
        "test_the_endpoint_reports_what_the_store_said",
    ),
    (
        "swallow the failed write again and report a cheerful created:false (the E9.58b defect)",
        AUTH,
        "        raise HTTPException(\n"
        '            status_code=503, detail="Could not record your acceptance. Please try again."\n'
        "        ) from exc",
        "        return TermsAcceptanceResult(created=False)",
        "test_the_endpoint_still_raises_rather_than_reporting_success_for_a_failed_write",
    ),
    # ── the surface that must stay silent ─────────────────────────────────────────────────────
    (
        "emit a signup from the TermsGate, reporting a years-old account as a new one",
        GATE,
        "      await acceptTerms(accessToken)",
        '      await acceptTerms(accessToken)\n      posthog.capture("user_signup_completed", {})',
        "test_the_terms_gate_deliberately_counts_nothing",
    ),
    # ── the anti-vacuity guard itself ─────────────────────────────────────────────────────────
    (
        "rename the decision function, so the source readers read whatever is nearby",
        POST_SIGNIN,
        "function reportSignupCompletion(",
        "function decideSignup(",
        "test_a_new_account_at_the_signin_door_is_counted",
    ),
]


def run_one(test_name: str) -> bool:
    """True if the named test PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}
    results = []
    try:
        for label, path, find, replace, test_name in CASES:
            original = backups[path]
            if find not in original:
                # ⭐ THE MUTATION DID NOT LAND — its own status, never "vacuous guard".
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            path.write_text(original.replace(find, replace, 1))
            try:
                passed = run_one(test_name)
            finally:
                path.write_text(original)
            results.append((label, test_name, "GREEN — VACUOUS" if passed else "RED"))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = sum(1 for _, _, s in results if s == "RED")
    for label, test_name, status in results:
        mark = "✅" if status == "RED" else "🚨"
        print(f"{mark} {label.ljust(width)}  →  {status}   ({test_name})")

    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
