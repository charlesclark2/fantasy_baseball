#!/usr/bin/env python3
"""NF-C4 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_c4_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run whenever `test_nf_c4_custom_big_board.py` is refactored.

WHY IT EXISTS HERE SPECIFICALLY. Much of that suite is SOURCE INSPECTION — "the budget is checked
before the write", "the base order is still the shared function", "the printed sheet carries none of
our numbers" — which is exactly the shape that reads as coverage while proving nothing. This repo has
shipped a source guard a COMMENT could satisfy (INC-38), an `and`-composed clause whose fixture a
DIFFERENT clause already refused (NF-D17), and a red-proof break that landed on the wrong symbol
because two functions shared a tail (E11.24). All three were found by breaking the source, never by
a green suite.

⚠️ EACH BREAK MUST BE PROVEN TO LAND, AND ITS ANCHOR MUST BE UNIQUE. A mutation that silently fails
to apply makes "the guard caught it" and "nothing happened" indistinguishable, and the false-vacuity
report is the DANGEROUS direction — it reads as a real finding and invites weakening a correct guard
(E11.24 #682, #815, and the byte-identical-tails case). So: a missing anchor is a FAILURE, an anchor
that appears more than once is a FAILURE, and a no-op replacement is an assertion error.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately not `git checkout --`:
that destroys uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODELS = REPO / "app/backend/models/fantasy.py"
DYNAMO = REPO / "app/backend/services/dynamo.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
DEPS = REPO / "app/backend/dependencies.py"
TS_LIB = REPO / "frontend/lib/big-board.ts"
TS_API = REPO / "frontend/lib/fantasy.ts"
COMPONENT = REPO / "frontend/components/fantasy/big-board.tsx"
SUITE = "betting_ml/tests/test_nf_c4_custom_big_board.py"

#: `(label, file, anchor, replacement, the ONE test that must go red)`.
#:
#: ⚠️ ONE CLAUSE PER CASE, and the named test must be the one whose SUBJECT the break removes. A
#: break that trips three clauses proves nothing about any of them — the first refusal hides the
#: rest (NF-D17 §7).
CASES = [
    # ── the gate ───────────────────────────────────────────────────────────────────────────────
    ("move the save route onto the public board router", ROUTER,
     '@router.put("/nfl/custom-boards")',
     '@board_router.put("/nfl/custom-boards")',
     "test_the_board_routes_are_on_the_fantasy_gated_router"),

    # ⭐ THE BEHAVIOURAL HALF OF THE SAME RULE, and a DIFFERENT break on purpose: the case above
    # removes the route from the gated ROUTER (a source fact this suite reads); this one leaves every
    # decorator exactly as written and removes the enforcement.
    #
    # ⚠️⚠️ TWO EARLIER ATTEMPTS WERE INERT, AND WHY IS A FINDING RATHER THAN A NUISANCE: this gate is
    # enforced TWICE, INDEPENDENTLY. `router` declares `Depends(require_fantasy_access)` at the ROUTER
    # level, and each handler ALSO takes it as a parameter (which is how it obtains `user_id`). So
    # neither "drop the router-level dependency" nor "drop the per-function one" changes the answer —
    # the surviving enforcer still refuses. That is a real defence-in-depth property of this surface,
    # and it means the only break that can prove this clause non-vacuous removes the gate ITSELF.
    #
    # ⛔ IT IS ALSO WHY THE SOURCE CLAUSE ABOVE IS NOT REDUNDANT WITH THIS ONE. A route quietly moved
    # onto a public router sails past both enforcers, and no behavioural test written against the
    # gated path would notice.
    ("make the fantasy gate grant everyone", DEPS,
     "    if cognito.has_fantasy_access(_groups_from_request(request)):\n        return user_id",
     "    return user_id",
     "test_a_caller_without_fantasy_entitlement_is_refused"),

    ("let a saved board be fetched through the anonymous CDN arm", TS_API,
     "export function listCustomBoards(token: string | null): Promise<CustomBoardsPayload> {\n"
     "  return apiFetch(`/fantasy/nfl/custom-boards`, {}, token)",
     "export function listCustomBoards(token: string | null): Promise<CustomBoardsPayload> {\n"
     "  if (!token) return cdnFetch(`/api/public/custom-boards`)\n"
     "  return apiFetch(`/fantasy/nfl/custom-boards`, {}, token)",
     "test_the_client_never_fetches_a_saved_board_through_the_cdn_arm"),

    # ── the shared item budget ─────────────────────────────────────────────────────────────────
    #
    # ⭐ THE DEFECT THIS STORY EXISTS NOT TO SHIP, in its most natural form: giving big boards their
    # own claim instead of sharing the leagues'. It looks tidy, every existing test stays green, and
    # 260 + 260 KB is past a 400 KB item.
    ("give big boards a budget of their own instead of the shared one", DYNAMO,
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key) + sum(\n"
     "        _estimated_bytes(league) for league in list_fantasy_leagues(user_id)\n"
     "    )",
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key)",
     "test_the_budget_is_joint_across_leagues_and_boards"),

    ("stop counting the stored boards when a league is written", DYNAMO,
     "    others += _big_boards_bytes(user_id)",
     "    others += 0",
     "test_a_league_write_now_sees_the_stored_boards_too"),

    # ⭐ "CHECKED BEFORE THE WRITE" AS A BREAK, NOT AS A SOURCE-ORDER ASSERTION. The first cut of
    # this pair asserted the two statements' relative INDEX in the file and stayed green under
    # `if False:` — the lines had not moved, so the guard could not see that the refusal had stopped
    # refusing. The property is observable instead: after a refusal, no write was issued at all.
    ("issue the write before the item budget is consulted", DYNAMO,
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key) + sum(\n"
     "        _estimated_bytes(league) for league in list_fantasy_leagues(user_id)\n"
     "    )",
     "    _users_table().update_item(\n"
     "        Key={\"user_id\": user_id},\n"
     "        UpdateExpression=\"SET #bb.#k = :doc\",\n"
     "        ExpressionAttributeNames={\"#bb\": _BIG_BOARDS_ATTR, \"#k\": board_key},\n"
     "        ExpressionAttributeValues={\":doc\": _to_ddb(record)},\n"
     "    )\n"
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key) + sum(\n"
     "        _estimated_bytes(league) for league in list_fantasy_leagues(user_id)\n"
     "    )",
     "test_an_oversized_board_is_refused_whole_and_never_truncated"),

    # ⭐ THE TEMPTING WRONG FIX: shorten the board so the save "succeeds". It produces a cheat sheet
    # that still looks complete and is quietly missing its tail — a plausible wrong answer read at
    # the pick, which is exactly the class NF-C6P3 chose whole-entity truncation to avoid.
    ("truncate an oversized board instead of refusing it", DYNAMO,
     '        raise ValueError("board_too_large")',
     '        record["order"] = record.get("order", [])[:50]',
     "test_an_oversized_board_is_refused_whole_and_never_truncated"),

    # ⭐ THE OTHER TEMPTING WRONG FIX: pay for this write with someone else's data.
    ("evict another stored board to make room", DYNAMO,
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key) + sum(",
     "    for _k in [k for k in _big_boards_raw(user_id) if k != board_key][:1]:\n"
     "        delete_fantasy_big_board(user_id, _k)\n"
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key) + sum(",
     "test_a_refused_save_evicts_nothing_that_was_already_stored"),

    ("count a board's own old bytes against its replacement", DYNAMO,
     "    footprint = _big_boards_bytes(user_id, skip_key=board_key) + sum(",
     "    footprint = _big_boards_bytes(user_id) + sum(",
     "test_replacing_a_board_does_not_count_its_own_old_bytes_twice"),

    ("apply the per-user board cap to edits as well as creates", DYNAMO,
     "    if existing is None and len(stored) >= MAX_BIG_BOARDS_PER_USER:",
     "    if len(stored) >= MAX_BIG_BOARDS_PER_USER:",
     "test_the_per_user_board_cap_refuses_a_new_key_but_never_an_edit"),

    # ⚠️ THE FIRST ATTEMPT — making the malformed branch RAISE — was INERT, because the per-row
    # `try/except` that this clause exists to protect catches it and skips the row anyway. The real
    # defect is the shape E9.49 actually shipped: a list comprehension with no per-row recovery, so
    # one bad record raises out of the function and blanks the whole collection.
    ("build the collection as one comprehension with no per-row recovery", DYNAMO,
     "    out: list[dict] = []\n"
     "    for board_key, doc in _big_boards_raw(user_id).items():\n"
     "        try:",
     "    out: list[dict] = [\n"
     "        {**_deep_from_dynamo(doc), \"board_key\": board_key}\n"
     "        for board_key, doc in _big_boards_raw(user_id).items()\n"
     "    ]\n"
     "    for board_key, doc in []:\n"
     "        try:",
     "test_one_malformed_stored_board_does_not_blank_the_collection"),

    # ── the payload contract ───────────────────────────────────────────────────────────────────
    #
    # 🚨 E9.49 IN ITS EXACT SHIPPED SHAPE — the RESPONSE model subclassing the REQUEST model, which
    # is how a write-time rule became retroactive over stored history and blanked a whole bet log.
    ("make the response model inherit the request model's rules", MODELS,
     "class BigBoard(_BigBoardFields):",
     "class BigBoard(BigBoardSave):",
     "test_the_response_model_carries_no_save_time_validators"),

    ("store a duplicate player id", MODELS,
     "        if not pid or len(pid) > MAX_PLAYER_ID_LEN or pid in seen:",
     "        if not pid or len(pid) > MAX_PLAYER_ID_LEN:",
     "test_a_duplicate_player_id_is_dropped_rather_than_stored"),

    ("persist an unrecognised tag", MODELS,
     "            if not pid or len(pid) > MAX_PLAYER_ID_LEN or tag not in BIG_BOARD_TAGS:",
     "            if not pid:",
     "test_an_unrecognised_tag_is_dropped_rather_than_persisted"),

    # ⚠️ THE BOUND FACING THE OTHER WAY. A cap set BELOW a real board would silently shorten a
    # legitimate whole-board ranking, which is the same partial-entity defect the refusal avoids.
    ("set the order bound below a real published board", MODELS,
     "MAX_BIG_BOARD_ORDER = 1000",
     "MAX_BIG_BOARD_ORDER = 300",
     "test_the_order_and_tag_bounds_hold_above_any_real_board"),

    # ⚠️ ITS OWN FIXTURE: the charset is left correct and only the LENGTH bound moves, so the
    # no-regression clause (a `custom:<uuid>` selection must still be accepted) is untouched.
    ("refuse a saved league's own board selection", MODELS,
     'if not v or len(v) > 60 or not re.fullmatch(r"[A-Za-z0-9_:-]+", v):',
     'if not v or len(v) > 60 or not re.fullmatch(r"[a-z0-9_]+", v):',
     "test_every_real_board_selection_is_accepted"),

    ("let the caller choose the stored attribute name", ROUTER,
     '@router.put("/nfl/custom-boards")',
     '@router.put("/nfl/custom-boards/{board_key}")',
     "test_the_storage_key_is_derived_by_the_server_not_supplied_by_the_caller"),

    ("restate the storage ceiling in the model layer", MODELS,
     "BIG_BOARD_TAGS = (\"target\", \"avoid\")",
     "MAX_BIG_BOARDS_PER_USER = 12\nBIG_BOARD_TAGS = (\"target\", \"avoid\")",
     "test_the_ceiling_has_exactly_one_owner"),

    ("replace the refusal's explanation with a status code", ROUTER,
     '                    "This board is too large to save alongside your other saved data. "\n'
     '                    "Nothing was changed — delete a custom board you no longer need and try again."',
     '                    "413"',
     "test_a_board_too_large_to_store_answers_413_with_a_readable_sentence"),

    # ── the surface ────────────────────────────────────────────────────────────────────────────
    # ⭐ E9.46 ON THE USER'S OWN DATA. Falling through on a failed read is the natural way to write
    # the loader and it states, confidently, that their saved board does not exist.
    ("report a failed read of the saved boards as an empty account", COMPONENT,
     "    if (savedError) {\n      setSaveState({ kind: \"unreadable\" })\n      return\n    }",
     "    if (false) {\n      setSaveState({ kind: \"unreadable\" })\n      return\n    }",
     "test_an_unreadable_saved_board_list_is_not_reported_as_an_empty_one"),

    ("swallow the server's explanation behind a generic message", COMPONENT,
     'message: e instanceof Error && e.message ? e.message : "Could not save this board.",',
     'message: "Could not save this board.",',
     "test_a_failed_save_renders_the_servers_own_sentence"),

    # ⚠️ THE CLAUSE THIS BREAK EXPOSED. Its first cut looked for `"saving"` ANYWHERE in the file and
    # stayed green with this render branch deleted, because the string still appeared in the
    # `SaveState` type union — a guard satisfied by a type declaration for a thing the user never
    # sees. The clause now reads the status line's own rendered text.
    ("drop the saving state from the status line", COMPONENT,
     '          {saveState.kind === "saving" && <span className="text-gray-400">Saving…</span>}\n',
     "",
     "test_the_save_surface_renders_all_four_states"),

    ("stop rendering the unsaved-changes warning", COMPONENT,
     '            <span className="text-amber-400">Unsaved changes.</span>',
     "            <span />",
     "test_the_save_surface_renders_all_four_states"),

    # ⭐ E9.61's two-renderers defect in the form that would hurt most here: the optimizer
    # recommends one order and the sheet printed from it shows another.
    ("give the big board its own base ordering", TS_LIB,
     'return sortAvailable(board, { sortCol: "ovrRank", sortDir: "asc", deferLowPred: true })',
     "return [...board].sort((a, b) => a.ovrRank - b.ovrRank)",
     "test_the_ordering_starts_from_the_shared_function_not_a_local_sort"),

    ("persist our own projection alongside the user's order", MODELS,
     "    tags: dict[str, str] = Field(default_factory=dict)",
     "    tags: dict[str, str] = Field(default_factory=dict)\n    pts: dict[str, float] = Field(default_factory=dict)",
     "test_the_board_stores_no_model_output"),

    # ⚠️ THIS BREAK IS RUNTIME-INERT AND THE CLAUSE IT PROVES IS A TRIPWIRE, NOT A BEHAVIOUR. Removing
    # BOTH tokens is what a careless tidy-up looks like; removing `overflow-x-auto` alone is the
    # half that a browser can see, and it is proved in `frontend/e2e/red-proof.mjs` against the
    # phone-width page-overflow assertion. Measured: with only `min-w-0` gone, the E2E stays green,
    # because this container's parent is a block. Saying so here is what keeps the source clause
    # honest about what it is defending.
    ("hardcode today's row count as the whole-board depth", COMPONENT,
     "                  label: d === ALL_ROWS ? \"Whole board\" : `Top ${d}`,",
     "                  label: d === 858 ? \"Whole board\" : `Top ${d}`,",
     "test_the_board_depth_control_states_no_row_count_of_its_own"),

    ("drop the scroll container's overflow and its min-width tripwire", COMPONENT,
     'className="min-w-0 overflow-x-auto rounded-lg border border-[#262626] bg-[#0f0f0f]"',
     'className="rounded-lg border border-[#262626] bg-[#0f0f0f]"',
     "test_the_layout_cannot_scroll_the_whole_page_sideways"),

    ("print our projection on the draft-day cheat sheet", COMPONENT,
     '                    <span className="truncate">{r.player.name}</span>',
     '                    <span className="truncate">{r.player.name} {r.player.pts}</span>',
     "test_the_cheat_sheet_prints_the_users_decisions_not_our_numbers"),

    # ⛔ `best_alpha = 0`. The divergence column describes a difference; a surface that graded it
    # would be claiming the exact advantage the program has repeatedly measured and failed to find.
    # ⚠️ TWO CASES, BECAUSE THE CAVEAT IS MADE TWICE AND THEY ARE DIFFERENT PROMISES. The first cut
    # ran ONE break against a whole-file search and stayed green: the standing note was gutted and
    # the column tooltip still carried the phrase, so the guard was satisfied by whichever of the
    # two survived. Each surface is now scoped and broken on its own (NF-D17 §7).
    ("drop the standing note's statement that a difference is not a verdict", COMPONENT,
     "we have no way to\n      know which of us is right about any one player",
     "we know where the value is",
     "test_the_surface_makes_no_claim_about_who_is_right"),

    ("let the divergence column present itself as a score", COMPONENT,
     "It is a description of the difference, not a\n                      score of it",
     "It is how much better your read is",
     "test_the_divergence_column_explains_itself_without_grading_the_difference"),
]

FILES = {MODELS, DYNAMO, ROUTER, DEPS, TS_LIB, TS_API, COMPONENT}


def run(test_name: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-500:]


def main() -> int:
    backups = {p: p.read_text() for p in FILES}
    failures: list[str] = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for label, path, old, new, test in CASES:
            src = backups[path]
            # ⚠️ A MISSING ANCHOR IS A FAILURE, NOT A SKIP, and so is an AMBIGUOUS one: a two-match
            # anchor patched with `replace(..., 1)` lands on whichever comes first, which may not be
            # the symbol under test (E11.24, two functions with byte-identical tails).
            hits = src.count(old)
            if hits != 1:
                failures.append(f"{label}: ANCHOR APPEARS {hits}x in {path.name} (want exactly 1)")
                print(f"⚠️  ANCHOR {'MISSING' if hits == 0 else 'AMBIGUOUS'}  {label}  ({path.name})")
                continue
            patched = src.replace(old, new, 1)
            assert patched != src, f"{label}: the replacement is a no-op"
            path.write_text(patched)
            code, out = run(test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {label}  ->  {test}")
            if code == 0:
                failures.append(f"{label} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        print("\nrestored all files")

    if failures:
        print(f"\n❌ {len(failures)} VACUOUS CLAUSE(S):\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(CASES)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
