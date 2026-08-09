#!/usr/bin/env python3
"""G100-C1 RED PROOF — break the source one defect at a time, require the NAMED test to fail.

    uv run python betting_ml/tests/g100_c1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_g100_c1_free_league.py` is refactored.

WHY IT EXISTS. A green suite proves nothing on its own, and this repo has shipped the vacuous shape
more than once: a guard a COMMENT could satisfy (INC-38), and an `and`-composed clause whose fixture
was already refused by a DIFFERENT clause, so deleting the clause it named changed nothing (NF-D17).
Neither was found by reading the test. Both were found by breaking the source and noticing the guard
stayed green.

⭐ EACH CASE NAMES ONE TEST and asserts THAT test fails. A break that turns the whole file red proves
much less — it can mean the clause worked, or that the import broke.

⭐ AND EACH CASE VERIFIES ITS MUTATION LANDED (`ANCHOR-MISSING`). A harness whose patch silently
no-ops reports a perfectly good guard as vacuous, which reads as a finding and sends the next session
at a defect that does not exist.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --`, which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ENTITLEMENT = REPO / "app/backend/services/entitlement.py"
DEPENDENCIES = REPO / "app/backend/dependencies.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
DYNAMO = REPO / "app/backend/services/dynamo.py"
GUARDRAILS = REPO / "app/backend/services/cost_guardrails.py"

SUITE = "betting_ml/tests/test_g100_c1_free_league.py"
FREEMIUM = "betting_ml/tests/test_freemium_tier.py"

# (label, file, find, replace, test_that_must_go_red, suite)
CASES = [
    # ── the quota itself ──────────────────────────────────────────────────────────────────────
    (
        "revert the free quota to 0 (the pre-G100-C1 state)",
        ENTITLEMENT,
        'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "1"))',
        'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "0"))',
        "test_a_free_signed_in_account_gets_exactly_one_league",
        SUITE,
    ),
    (
        "the same revert, seen END TO END through the app",
        ENTITLEMENT,
        'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "1"))',
        'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "0"))',
        "test_a_free_account_can_save_and_read_its_one_league",
        SUITE,
    ),
    (
        "raise the free quota to 5 (a pricing change nobody reviewed)",
        ENTITLEMENT,
        'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "1"))',
        'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "5"))',
        "test_the_free_personalized_league_quota_is_one",
        FREEMIUM,
    ),
    # ⭐ THE MOST TEMPTING WRONG FIX. Moving PERSONALIZATION into FREE_CAPABILITIES opens every gate
    # in one line — and silently frees every OTHER surface reading that capability.
    (
        "reclassify PERSONALIZATION as a FREE capability",
        ENTITLEMENT,
        "FREE_CAPABILITIES: frozenset[Capability] = frozenset({Capability.GENERIC_BOARD})",
        "FREE_CAPABILITIES: frozenset[Capability] = frozenset("
        "{Capability.GENERIC_BOARD, Capability.PERSONALIZATION})",
        "test_personalization_is_still_a_paid_capability_after_the_free_grant",
        FREEMIUM,
    ),
    # ── the cap ───────────────────────────────────────────────────────────────────────────────
    (
        "let the router pass the STORAGE ceiling instead of the caller's quota",
        ROUTER,
        "            user_id, None, payload.model_dump(), max_leagues=quota",
        "            user_id, None, payload.model_dump()",
        "test_a_free_accounts_second_league_is_refused_by_the_api",
        SUITE,
    ),
    (
        "drop the create-time cap in the writer entirely",
        DYNAMO,
        "    if is_new and len(list_fantasy_leagues(user_id)) >= cap:",
        "    if False and is_new and len(list_fantasy_leagues(user_id)) >= cap:",
        "test_a_free_callers_second_league_is_refused_by_the_writer",
        SUITE,
    ),
    (
        "un-clamp the quota so an entitlement bug can overflow the item",
        DYNAMO,
        "    cap = min(cap, MAX_LEAGUES_PER_USER)",
        "    cap = cap",
        "test_the_quota_can_only_ever_tighten_the_storage_ceiling",
        SUITE,
    ),
    # ⭐ THE SYMMETRIC-LOOKING DEFECT: applying the cap to UPDATES as well as creates. It reads as
    # consistency and freezes a free user's one league at whatever they first typed.
    (
        "apply the cap to UPDATES as well as creates",
        DYNAMO,
        "    if is_new and len(list_fantasy_leagues(user_id)) >= cap:",
        "    if len(list_fantasy_leagues(user_id)) >= cap:",
        "test_a_caller_at_their_quota_can_still_EDIT_the_league_they_have",
        SUITE,
    ),
    # ── the serve-side cap (the lapsed subscriber) ────────────────────────────────────────────
    (
        "serve every stored league, ignoring the quota (the create-only-cap bug)",
        ROUTER,
        "    served = entitlement.leagues_within_quota(nfl_records, quota)",
        "    served = nfl_records",
        "test_the_management_list_is_not_capped_but_the_personalized_serve_is",
        SUITE,
    ),
    (
        "cap the MANAGEMENT list too, stranding a lapsed user above their quota",
        ROUTER,
        "    return _serialize_leagues(dynamo.list_fantasy_leagues(user_id))",
        "    return _serialize_leagues(dynamo.list_fantasy_leagues(user_id)[:1])",
        "test_the_management_list_is_not_capped_but_the_personalized_serve_is",
        SUITE,
    ),
    # ⚠️ Ordering: `updated_at` moves on every edit, so the kept league would change under a lapsed
    # user as soon as they opened a different one.
    (
        "order the serve cap by updated_at instead of created_at",
        ENTITLEMENT,
        '        raw = str(record.get("created_at") or "")',
        '        raw = str(record.get("updated_at") or "")',
        "test_the_serve_cap_keeps_the_oldest_league_deterministically",
        SUITE,
    ),
    (
        "sort a missing created_at FIRST, so one bad row wins the cap",
        ENTITLEMENT,
        '        return (not raw, raw, str(record.get("league_id") or ""))',
        '        return (bool(raw), raw, str(record.get("league_id") or ""))',
        "test_a_malformed_created_at_cannot_reorder_the_healthy_leagues",
        SUITE,
    ),
    # ── the gate ──────────────────────────────────────────────────────────────────────────────
    (
        "let an ANONYMOUS caller through the personalization gate",
        DEPENDENCIES,
        "def require_personalized_league_access(\n    request: Request, user_id: str = Depends(get_user_id)\n) -> str:",
        'def require_personalized_league_access(\n    request: Request, user_id: str = "anonymous"\n) -> str:',
        "test_an_anonymous_caller_is_told_to_sign_in_not_to_pay",
        SUITE,
    ),
    (
        "gate on fantasy ENTITLEMENT rather than on the quota (the pre-G100-C1 predicate)",
        DEPENDENCIES,
        "    if entitlement.allows_personalization(entitlement.resolve_entitlement(request)):",
        "    if entitlement.allows("
        "entitlement.Capability.PERSONALIZATION, entitlement.resolve_entitlement(request)):",
        "test_a_free_account_can_save_and_read_its_one_league",
        SUITE,
    ),
    (
        "drop the quota gate from the saved-league router",
        ROUTER,
        "    dependencies=[Depends(require_personalized_league_access)],\n)",
        ")",
        "test_every_saved_league_route_carries_the_quota_gate",
        SUITE,
    ),
    # ── the caches the personalized surface must stay out of ──────────────────────────────────
    (
        "add the personalized read to the PUBLIC cache rules",
        GUARDRAILS,
        '    ("/fantasy/nfl/manifest", 900, 3600),',
        '    ("/fantasy/nfl/my-teams", 900, 3600),\n    ("/fantasy/nfl/manifest", 900, 3600),',
        "test_a_personalized_path_is_never_shared_cacheable",
        SUITE,
    ),
    (
        "let an authorized response be shared-cacheable",
        GUARDRAILS,
        "    if has_authorization:\n        return PRIVATE_CACHE_CONTROL",
        "    if has_authorization:\n        return public_cache_control(path)",
        "test_a_personalized_response_is_private_no_store",
        SUITE,
    ),
    # ── the additive response shape (NF-C0 / E8.6 deploy skew) ────────────────────────────────
    (
        "drop the quota keys the client reads with `?? default`",
        ROUTER,
        '        "quota": quota,',
        "",
        "test_my_teams_keeps_every_key_the_deployed_client_already_reads",
        SUITE,
    ),
    (
        "wrap the management list in an envelope (the NF-C0 blank-screen break)",
        ROUTER,
        "    return _serialize_leagues(dynamo.list_fantasy_leagues(user_id))",
        '    return {"leagues": _serialize_leagues(dynamo.list_fantasy_leagues(user_id))}',
        "test_the_management_list_is_still_a_bare_array",
        SUITE,
    ),
    (
        "quote the STORAGE ceiling in the 409, telling a free user the wrong number",
        ROUTER,
        "                    f\"You can save {quota} league{'s' if quota != 1 else ''} on your current plan.\"",
        '                    f"You can save at most {dynamo.MAX_LEAGUES_PER_USER} leagues"',
        "test_a_free_accounts_second_league_is_refused_by_the_api",
        SUITE,
    ),
]


def run_one(test_name: str, suite: str) -> bool:
    """True if the named test PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{suite}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}
    results = []
    try:
        for label, path, find, replace, test_name, suite in CASES:
            original = backups[path]
            if find not in original:
                # ⭐ THE MUTATION DID NOT LAND. Reported as its own status rather than as a failing
                # guard: a quoting/anchor slip that silently no-ops would otherwise be indexed as
                # "this guard is vacuous", which is a scarier and completely wrong finding.
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            path.write_text(original.replace(find, replace, 1))
            try:
                passed = run_one(test_name, suite)
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
