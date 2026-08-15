#!/usr/bin/env python3
"""NF-C6P3 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_c6p3_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run whenever `test_nf_c6p3_league_rosters.py` is refactored.

WHY IT EXISTS HERE SPECIFICALLY. Half of that suite is SOURCE INSPECTION — "the writer still checks
the budget", "the pool still excludes rostered players" — which is precisely the shape that reads as
coverage while proving nothing. This repo has been bitten by a source guard a COMMENT could satisfy
(INC-38), by an `and`-composed clause whose fixture a different clause already refused (NF-D17), and
by a clause that passed because a committed artifact's incidental ROW ORDER made broken code return
the right answer (NF-TR1). Every one was found by breaking the source, never by a green suite.

⭐ AND ITS SIBLING ALREADY EARNED ITS KEEP IN THIS STORY. The browser half
(`frontend/e2e/red-proof.mjs`, case `free-agent-pool-ignores-the-rosters`) caught the free-agent
clause passing with the rostered filter DELETED OUTRIGHT — the mocked rivals held a mid-board slice,
so the waiver section's three picks came from the untouched top of the board either way. The fixture,
not the assertion, was doing the work.

⚠️ EACH BREAK MUST BE PROVEN TO LAND. A mutation that silently fails to apply makes "the guard went
red" and "nothing happened" indistinguishable, and the latter reports as a scarier finding than it
is (E11.24 #682). The anchor is checked against the file's real text before the run, and a missing
anchor is a FAILURE, never a skip.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately not `git checkout --`:
that destroys uncommitted work in the files it patches (it ate an in-progress page at E9.59).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCORING = REPO / "app/backend/services/league_scoring.py"
MODELS = REPO / "app/backend/models/fantasy.py"
DYNAMO = REPO / "app/backend/services/dynamo.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
TS_SCORING = REPO / "frontend/lib/league-scoring.ts"
TS_REPORT = REPO / "frontend/lib/roster-report.ts"
TS_COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
TS_IMPORT = REPO / "frontend/components/fantasy/league-import.tsx"
SUITE = "betting_ml/tests/test_nf_c6p3_league_rosters.py"

#: `(label, file, anchor, replacement, the ONE test that must go red)`.
#:
#: ⚠️ ONE CLAUSE PER CASE, and the named test must be the one whose SUBJECT the break removes. A
#: break that trips three clauses proves nothing about any of them — the first refusal hides the
#: rest (NF-D17 §7).
CASES = [
    # ── the D/ST join ──────────────────────────────────────────────────────────────────────────
    ("revert the team-defence branch entirely", SCORING,
     '    if position == "DST":',
     "    if False:",
     "test_every_captured_team_defence_now_joins_to_its_board_row"),

    ("stop reading the row's own team field", SCORING,
     "    resolved = normalize_team(team)\n    if resolved:\n        return resolved",
     "    pass",
     "test_every_platform_rendering_of_a_defence_resolves"),

    ("stop resolving a nickname out of the name", SCORING,
     "    for token in tokens:\n        hit = NFL_TEAM_BY_NICKNAME.get(token)\n        if hit:\n            return hit",
     "    pass",
     "test_the_defence_join_works_without_the_team_field"),

    ("stop resolving an abbreviation out of the board's own naming", SCORING,
     '    for token in str(name or "").replace("/", " ").split():\n        hit = normalize_team(token)\n        if hit:\n            return hit',
     "    pass",
     "test_the_defence_join_works_when_the_board_carries_no_team"),

    # ⚠️ Its OWN fixture: everything else about the join is left intact, so only the "answer `\"\"`
    # rather than the input" rule can decide the result.
    ("let an unknown abbreviation resolve to itself", SCORING,
     '    return t if t in NFL_TEAM_ABBREVIATIONS else ""',
     "    return t",
     "test_an_unknown_abbreviation_does_not_resolve_to_itself"),

    # ⚠️ THE BREAK IS A FALLBACK GUESS, NOT A KEY CHANGE. The first cut of this case made the key
    # unconditional (`DST|{dst_team(...)}`), which for an unresolvable row is `DST|` — a key nothing
    # matches, so the row was still an honest miss and the clause stayed green. The defect the clause
    # actually defends is GUESSING a franchise, so the break has to guess one.
    ("guess a franchise for a defence we cannot place", SCORING,
     "    for token in str(name or \"\").replace(\"/\", \" \").split():\n"
     "        hit = normalize_team(token)\n"
     "        if hit:\n"
     "            return hit\n"
     '    return ""',
     "    for token in str(name or \"\").replace(\"/\", \" \").split():\n"
     "        hit = normalize_team(token)\n"
     "        if hit:\n"
     "            return hit\n"
     '    return "SEA"',
     "test_an_unresolvable_defence_is_an_honest_miss_not_a_guess"),

    ("drop the two-word nickname the franchise table needs", SCORING,
     '    "football team": "WAS",',
     "",
     "test_the_nickname_map_covers_every_franchise_the_research_tree_knows"),

    ("drift the TypeScript nickname map away from the Python one", TS_SCORING,
     '  cowboys: "DAL", broncos: "DEN", lions: "DET", packers: "GB",',
     '  cowboys: "DAL", broncos: "DEN", packers: "GB",',
     "test_the_nickname_map_is_identical_in_python_and_typescript"),

    ("drift the TypeScript alias map away from the Python one", TS_SCORING,
     '  JAC: "JAX",',
     "",
     "test_the_abbreviation_alias_map_is_identical_in_python_and_typescript"),

    ("point a nickname at a spelling the board does not publish", SCORING,
     '    "seahawks": "SEA",',
     '    "seahawks": "SEATTLE",',
     "test_every_board_abbreviation_is_a_target_of_the_nickname_map"),

    # ⭐ THE REGRESSION SIDE. The team-defence branch must leave the 95% of a roster that already
    # joined alone; this makes it swallow every position and requires that to be caught.
    ("let the defence branch capture every position", SCORING,
     '    if position == "DST":',
     "    if True:",
     "test_the_defence_branch_leaves_every_other_position_alone"),

    # ── the stored field ───────────────────────────────────────────────────────────────────────
    ("store the platform's whole player row instead of the join fields", MODELS,
     'LEAGUE_ROSTER_PLAYER_FIELDS = ("name", "position", "team")',
     'LEAGUE_ROSTER_PLAYER_FIELDS = ("name", "position", "team", "player_key", "starter")',
     "test_the_stored_player_row_is_slimmed_to_the_join_fields"),

    # ⚠️ Truncating by PLAYERS rather than by whole teams is the plausible-looking wrong fix — it
    # keeps every team and produces a team total that is quietly too low.
    ("truncate inside a team rather than dropping it whole", MODELS,
     "        if players_kept + len(players) > MAX_LEAGUE_ROSTER_PLAYERS:\n"
     "            # This team does not fit WHOLE, so it does not go in at all. Continuing rather than\n"
     "            # breaking lets a later, smaller team still land — the cap is on total players, not on\n"
     "            # position in the list.\n"
     "            truncated = True\n"
     "            continue",
     "        if players_kept + len(players) > MAX_LEAGUE_ROSTER_PLAYERS:\n"
     "            players = players[: max(0, MAX_LEAGUE_ROSTER_PLAYERS - players_kept)]\n"
     "            truncated = True",
     "test_a_league_over_the_player_cap_truncates_by_whole_teams"),

    ("drop the team cap", MODELS,
     "        if len(kept) >= MAX_LEAGUE_ROSTER_TEAMS:\n            truncated = True\n            continue",
     "        pass",
     "test_a_league_over_the_team_cap_truncates"),

    ("overwrite a client's truncation claim with our own", MODELS,
     "        self.league_rosters_truncated = bool(self.league_rosters_truncated or truncated)",
     "        self.league_rosters_truncated = bool(truncated)",
     "test_a_client_declared_truncation_is_never_overwritten"),

    ("raise on a malformed roster entry instead of skipping it", MODELS,
     "        if not isinstance(entry, dict):\n            truncated = True\n            continue",
     "        if not isinstance(entry, dict):\n            raise ValueError('bad entry')",
     "test_a_malformed_roster_entry_costs_only_itself"),

    # 🚨 E9.49 — the write-time rule migrating onto the shared base, where it would run on READS.
    # 🚨 E9.49 IN ITS EXACT SHIPPED SHAPE — the RESPONSE model subclassing the REQUEST model, which
    # is how a write-time rule became retroactive over stored history and blanked a whole bet log.
    # ⚠️ The first cut of this case merely ADDED an unused subclass, which moved no rule at all and
    # left the clause green: a break that changes nothing is indistinguishable from a vacuous guard.
    ("make the response model inherit the request model's rules", MODELS,
     "class League(_LeagueFields):",
     "class League(LeagueSave):",
     "test_the_response_model_carries_no_write_rule"),

    ("stop calling the item-budget check", DYNAMO,
     '    if record.get("league_rosters") and not _fits_fantasy_budget(user_id, league_id, record):',
     '    if record.get("league_rosters") and False:',
     "test_the_writer_carries_a_total_item_budget"),

    ("drop the rosters for size without recording that it happened", DYNAMO,
     '        record["league_rosters_truncated"] = True',
     "        pass",
     "test_the_budget_drops_only_the_rosters_and_only_from_the_incoming_league"),

    ("fail the whole save when the item budget is reached", DYNAMO,
     '        record["league_rosters"] = None',
     '        raise ValueError("too_big")',
     "test_the_budget_drops_only_the_rosters_and_only_from_the_incoming_league"),

    # ── the served join, and what the surfaces say ─────────────────────────────────────────────
    ("give the league-roster join its own board", ROUTER,
     '                "rows": league_scoring.match_roster_to_board(\n'
     '                    entry.get("players") or [], board_players\n'
     "                ),",
     '                "rows": league_scoring.build_board(entry.get("players") or [], {}, {}),',
     "test_the_league_board_serves_the_rosters_joined_by_the_shared_function"),

    ("drop a response key the deployed client reads", ROUTER,
     '        "roster": league_scoring.match_roster_to_board(\n'
     '            record.get("imported_roster") or [], board["players"]\n'
     "        ),",
     "",
     "test_the_league_board_response_key_is_additive"),

    ("stop excluding rostered players from the pool", TS_REPORT,
     "    if (rosteredIds) return !rosteredIds.has(p.id)",
     "    if (rosteredIds) return true",
     "test_the_free_agent_pool_excludes_players_on_another_roster"),

    ("treat partial roster coverage as a complete league", TS_REPORT,
     "    rosteredIds: complete ? ids : null,",
     "    rosteredIds: ids,",
     "test_a_partial_league_does_not_produce_a_free_agent_pool"),

    ("delete the partial-coverage sentence", TS_COPY,
     "export const REPORT_FREE_AGENT_PARTIAL_NOTE =",
     "const _REPORT_FREE_AGENT_PARTIAL_NOTE =",
     "test_the_waiver_copy_states_which_definition_it_is_using"),

    # ⚠️ ITS OWN FIXTURE. The rest of the sentence is untouched, so only the snapshot hedge can flip
    # this — and the hedge is what makes a true sentence true.
    ("trim the snapshot hedge off the free-agent sentence", TS_COPY,
     " It is the roster picture from when you imported the league; we do not re-read it, so anyone "
     "claimed since then will still be listed.",
     "",
     "test_the_free_agent_copy_keeps_its_snapshot_hedge"),

    # ⭐ THE DEPLOY-SKEW CLAUSE (E8.6). Echoing our own payload is the natural, wrong way to write
    # this: an un-deployed Lambda accepts `league_rosters`, ignores it, and answers 200 — so the
    # screen would confirm "all 10 rosters stored" over a server that stored none.
    ("confirm what we SENT instead of what the server stored", TS_IMPORT,
     "setStoredRosterTeams((res as { league_rosters?: unknown[] | null }).league_rosters?.length ?? 0)",
     "setStoredRosterTeams(leagueRosters.length)",
     "test_the_import_confirms_what_the_server_actually_stored"),
]

FILES = {SCORING, MODELS, DYNAMO, ROUTER, TS_SCORING, TS_REPORT, TS_COPY, TS_IMPORT}


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
            # ⚠️ A MISSING ANCHOR IS A FAILURE, NOT A SKIP. A mutation that never lands makes "the
            # guard caught it" and "nothing happened" indistinguishable (E11.24 #682).
            if old not in src:
                failures.append(f"{label}: PATCH ANCHOR NOT FOUND in {path.name}")
                print(f"⚠️  ANCHOR MISSING  {label}  ({path.name})")
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
