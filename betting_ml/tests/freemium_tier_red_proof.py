#!/usr/bin/env python3
"""FREEMIUM BUILD RED PROOF — break the source one defect at a time, require the NAMED test to fail.

    uv run python betting_ml/tests/freemium_tier_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_freemium_tier.py` is refactored.

WHY IT EXISTS. Most of that suite is SOURCE INSPECTION — "this component renders that", "this module
does not import that". That is precisely the shape which reads as coverage while proving nothing,
and this repo has shipped it twice: a guard a COMMENT could satisfy (INC-38), and an `and`-composed
clause whose fixture was already refused by a different clause (NF-D17). Neither was found by
reading the test. Both were found by breaking the source and noticing the guard stayed green.

⭐ EACH CASE NAMES ONE TEST and asserts THAT test fails. A break that turns the whole file red
proves much less — it can mean the clause worked, or that the import broke.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --`, which would destroy uncommitted work in the files it patches (that harness ate an
in-progress `subscribe/page.tsx` at E9.59).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ENTITLEMENT = REPO / "app/backend/services/entitlement.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
TS_ENTITLEMENTS = REPO / "frontend/lib/entitlements.ts"
NAV = REPO / "frontend/lib/nav-model.ts"
FANTASY_TS = REPO / "frontend/lib/fantasy.ts"
QUERIES = REPO / "frontend/lib/fantasy-queries.ts"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
SCORING = REPO / "frontend/lib/league-scoring.ts"
DRAFT_PAGE = REPO / "frontend/app/fantasy/draft/page.tsx"
LEAGUE_BOARD_PAGE = REPO / "frontend/app/fantasy/league-board/page.tsx"

SUITE = "betting_ml/tests/test_freemium_tier.py"
E9_56_SUITE = "betting_ml/tests/test_e9_56_entitlement.py"
E9_45_SUITE = "betting_ml/tests/test_fantasy_entitlement.py"

# (label, file, patches, _unused, test_that_must_go_red, suite)
#   `patches` is a LIST of (find, replace) pairs applied in order. A list rather than one pair
#   because the honest break for the byte-identity clause needs three coordinated edits — and the
#   fact that it does is itself evidence the route cannot see its caller.
CASES = [
    # ── the un-gate itself ────────────────────────────────────────────────────────────────────
    ("re-wire E9.56's redaction into the projections route", ROUTER,
     "    return entitlement.open_projections_payload(data)",
     "    return entitlement.lock_projections_payload(data)",
     "test_an_anonymous_caller_gets_the_real_generic_board", SUITE),

    ("re-wire the redaction, seen from the RETIREMENT clause", ROUTER,
     "    return entitlement.open_projections_payload(data)",
     "    return entitlement.lock_projections_payload(data)",
     "test_the_locked_redaction_is_retired_from_every_live_route", E9_56_SUITE),

    # ⭐ THE SUBTLEST BREAK IN THE FILE, and the one that justifies asserting byte EQUALITY rather
    # than "both payloads look right". The board keeps every number, so every "the free board has
    # the numbers" clause stays green; only equality across callers sees the extra field. It needs a
    # TWO-PART patch (re-import `Request`, then take it and branch on it) — which is itself the
    # finding: the route currently cannot see the caller AT ALL, so there is no one-line way to make
    # it vary. That is the design doing its job.
    ("make the projections payload vary by caller", ROUTER,
     [("from fastapi import APIRouter, Depends, HTTPException, Query",
       "from fastapi import APIRouter, Depends, HTTPException, Query, Request"),
      ("def nfl_projections(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):",
       "def nfl_projections(request: Request, "
       "season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):"),
      ("    return entitlement.open_projections_payload(data)",
       "    _e = entitlement.resolve_entitlement(request)\n"
       "    return {**entitlement.open_projections_payload(data), 'vip': _e.fantasy}")],
     None,
     "test_the_generic_board_is_byte_identical_for_every_caller", SUITE),

    # The SAME break, seen from the signature clause one suite over. A `Request` parameter
    # reappearing is the first step of re-gating the free board, and it type-checks, builds and
    # passes every other test in that module — the handler simply regains the ability to tell
    # callers apart. Both clauses are wanted: this one fails on the CAPABILITY, the one above fails
    # on the OBSERVED payload, and a break could plausibly produce either without the other.
    ("re-give the projections handler a Request", ROUTER,
     [("def nfl_projections(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):",
       "def nfl_projections(request: 'Request', "
       "season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):")],
     None,
     "test_the_generic_board_handlers_take_no_caller", E9_45_SUITE),

    # ── the no-regression half: what must STAY paid ───────────────────────────────────────────
    # ⚠️ THE FIRST ATTEMPT DROPPED THE ROUTER-LEVEL `dependencies=` AND THE CLAUSE STAYED GREEN —
    # correctly, because `nfl_my_teams` ALSO carries `Depends(require_fantasy_access)` on the
    # function itself. That is defence in depth working, not a vacuous guard, and it is why the
    # break now removes the entitlement at its source instead.
    ("let the entitlement check pass everyone", REPO / "app/backend/services/cognito.py",
     [("def has_fantasy_access(", "def has_fantasy_access(_unused=None, *_a, **_k):\n"
                                  "    return True\n\n\ndef _retired_has_fantasy_access(")],
     None,
     "test_the_personalization_endpoints_still_403_a_non_entitled_caller", SUITE),

    # ── the capability map ────────────────────────────────────────────────────────────────────
    ("add a capability without placing it on either side", ENTITLEMENT,
     '    DECISION_SUPPORT = "decision_support"',
     '    DECISION_SUPPORT = "decision_support"\n\n    WEEKLY_TOOLS = "weekly_tools"',
     "test_every_capability_is_placed_on_exactly_one_side", SUITE),

    ("let an unrecognised capability default to ALLOWED", ENTITLEMENT,
     '        logger.warning("entitlement: unplaced capability %r treated as PAID", capability)\n'
     "        return False",
     '        logger.warning("entitlement: unplaced capability %r treated as PAID", capability)\n'
     "        return True",
     "test_an_unplaced_capability_fails_closed", SUITE),

    ("grant the paid half to anyone who is merely signed in", ENTITLEMENT,
     "    return bool(ent and ent.fantasy)",
     "    return bool(ent and not ent.is_anonymous)",
     "test_a_signed_in_caller_without_fantasy_is_treated_as_free_not_as_entitled", SUITE),

    # ── the G100-C1 seam ──────────────────────────────────────────────────────────────────────
    ("let the free personalization quota drift in as a default", ENTITLEMENT,
     'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "0"))',
     'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "1"))',
     "test_the_free_personalized_league_quota_is_zero_today", SUITE),

    # ── the frontend mirror ───────────────────────────────────────────────────────────────────
    ("quietly make the paid League Board public", LEAGUE_BOARD_PAGE,
     "<FantasyGuard>", "<FantasyPublicGuard>",
     "test_exactly_the_generic_board_pages_are_public", SUITE),

    ("quietly make the paid Draft Optimizer public", DRAFT_PAGE,
     "<FantasyGuard>", "<FantasyPublicGuard>",
     "test_personalization_and_decision_pages_stay_gated", SUITE),

    ("hide a free surface from the nav", NAV,
     '{ label: "Player Search", href: "/fantasy/players", key: "fantasy-players", public: true },',
     '{ label: "Player Search", href: "/fantasy/players", key: "fantasy-players" },',
     "test_the_nav_marks_exactly_the_public_surfaces_public", SUITE),

    ("let the frontend capability sets drift from the backend", TS_ENTITLEMENTS,
     '  "personalization",\n  "decision_support",',
     '  "personalization",',
     "test_the_frontend_capability_sets_mirror_the_backend", SUITE),

    ("put the entitlement gate back on the board hooks", QUERIES,
     "    queryKey: [\"nfl-fantasy-projections\", season, entitled],",
     "    queryKey: [\"nfl-fantasy-projections\", season, entitled],\n"
     "    enabled: canAccess(\"fantasy\", groups),",
     "test_the_three_board_hooks_never_gate_their_fetch_on_entitlement", SUITE),

    ("drop the entitlement discriminator from a dual-mode query key", QUERIES,
     '    queryKey: ["nfl-fantasy-board", season, configName, size, entitled],',
     '    queryKey: ["nfl-fantasy-board", season, configName, size],',
     "test_the_entitlement_is_still_part_of_every_dual_mode_query_key", SUITE),

    # ── the explicit boundary ─────────────────────────────────────────────────────────────────
    ("stop stating the boundary on the free rankings board", RANKINGS,
     "          <FreemiumBoundary entitled={entitled} />",
     "",
     "test_every_free_surface_states_the_boundary", SUITE),

    ("show the upsell to someone who already pays", SHARED,
     "  if (entitled) return null\n",
     "",
     "test_the_boundary_is_not_shown_to_someone_who_already_pays", SUITE),

    ("write the boundary copy inline instead of in the governed module", SHARED,
     "        {FREE_TIER_SUMMARY.title}",
     '        {"This board is free, and it is the whole board"}',
     "test_the_boundary_copy_lives_in_the_governed_copy_module", SUITE),

    ("turn the paid pitch into a performance promise", COPY,
     '  "The generic board is free. A membership re-scores it for your league and helps you decide."',
     '  "The generic board is free. A membership helps you win your league."',
     "test_the_boundary_copy_makes_no_forbidden_claim", SUITE),

    # ⚠️ THE FIRST ATTEMPT ONLY CHANGED THE `title` AND THE CLAUSE STAYED GREEN — correctly, because
    # the `detail` beneath it still named the draft tool. The clause reads the WHOLE entry, so the
    # break has to remove the decision-support half from the whole entry.
    ("describe only the personalization half of the paid tier", COPY,
     [('''    title: "The tools that turn a board into a pick",
    detail:
      "The draft optimizer, and the in-season calls — waivers, trades, start/sit — worked in your league's scoring rather than left as an exercise.",''',
       '''    title: "More of your own league",
    detail:
      "Save more than one league, and keep each one's settings between visits.",''')],
     None,
     "test_the_paid_summary_names_both_halves_of_the_boundary", SUITE),

    # ── the full-season rate stays a DISPLAY transform ────────────────────────────────────────
    ("let the full-season rate reach the scoring engine", SCORING,
     "export function buildBoard",
     "import { fullSeasonRate } from '@/lib/fantasy'\nexport function buildBoard",
     "test_the_full_season_rate_never_reaches_a_scoring_or_ordering_module", SUITE),

    ("drop the zero-games guard so a full-season rate can be Infinity", FANTASY_TS,
     "  if (games <= 0) return null",
     "  if (games < 0) return null",
     "test_the_full_season_rate_guards_a_zero_or_absent_games_figure", SUITE),

    ("drift the full-season constant to 16 games", FANTASY_TS,
     "export const FULL_SEASON_GAMES = 17",
     "export const FULL_SEASON_GAMES = 16",
     "test_the_full_season_rate_is_the_expected_arithmetic", SUITE),

    ("label the rate without disclaiming consensus calibration", COPY,
     "It is also our own arithmetic, not a figure reconciled against anyone else's published projections, and it stays conservative at running back.",
     "It is the cleanest way to compare two players.",
     "test_the_rate_label_does_not_imply_a_consensus_calibrated_number", SUITE),

    ("stop rendering the rate beside the expected total", RANKINGS,
     "                        <InfoTip label={FULL_SEASON_RATE_LABEL}>{GLOSSARY.fullSeasonRate}</InfoTip>",
     "                        <InfoTip label={\"Rate\"}>{GLOSSARY.fullSeasonRate}</InfoTip>",
     "test_the_rate_renders_beside_the_expected_total", SUITE),
]


def run_one(test_name: str, suite: str) -> bool:
    """True if the named test PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{suite}::{test_name}", "-q", "--no-header", "-p",
         "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}
    results = []
    try:
        for label, path, find, replace, test_name, suite in CASES:
            original = backups[path]
            # Accept both shapes: a single (find, replace) pair spelled inline, or a LIST of pairs.
            patches = find if isinstance(find, list) else [(find, replace)]
            if any(f not in original for f, _ in patches):
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            patched = original
            for f, r in patches:
                patched = patched.replace(f, r, 1)
            path.write_text(patched)
            try:
                passed = run_one(test_name, suite)
            finally:
                path.write_text(original)
            results.append((label, test_name, "GREEN — VACUOUS" if passed else "RED"))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = 0
    for label, test_name, status in results:
        mark = "✅" if status == "RED" else "🚨"
        print(f"{mark} {label.ljust(width)}  →  {status}   ({test_name})")
        red += status == "RED"

    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
