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
DEPENDENCIES = REPO / "app/backend/dependencies.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
TS_ENTITLEMENTS = REPO / "frontend/lib/entitlements.ts"
NAV = REPO / "frontend/lib/nav-model.ts"
FANTASY_TS = REPO / "frontend/lib/fantasy.ts"
QUERIES = REPO / "frontend/lib/fantasy-queries.ts"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
PROJECTIONS = REPO / "frontend/components/fantasy/projections-table.tsx"
PLAYER_PAGE = REPO / "frontend/components/fantasy/player-page.tsx"
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
    # the numbers" clause stays green; only equality across callers sees the extra field.
    #
    # 🗄️ It USED to need a three-part patch, because the module imported no `Request` at all and the
    # route could not see its caller by construction. `nfl_board` now takes one (one preset is free,
    # thirteen are not), so the import is present and the break is two edits. The two
    # format-independent routes still take no caller, which is what the clause one case down pins.
    ("make the projections payload vary by caller", ROUTER,
     [("def nfl_projections(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):",
       "def nfl_projections(request: Request, "
       "season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):"),
      ("    return entitlement.open_projections_payload(data)",
       "    _e = entitlement.resolve_entitlement(request)\n"
       "    return {**entitlement.open_projections_payload(data), 'vip': _e.fantasy}")],
     None,
     "test_the_free_generic_board_is_byte_identical_for_every_caller", SUITE),

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

    # ...and the same signature clause pointing the OTHER way. `nfl_board` MUST see its caller now,
    # so "no handler takes a Request" must not be satisfiable by deleting the one that needs one.
    ("take the caller away from the board handler", ROUTER,
     [("def nfl_board(\n    request: Request,", "def nfl_board(")],
     None,
     "test_the_board_handler_does_take_a_caller", E9_45_SUITE),

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

    # ⚠️ THE ANCHOR CARRIES THE PRECEDING LINE ON PURPOSE. `allows_board` (added when the tier
    # narrowed) ends with the IDENTICAL `return bool(ent and ent.fantasy)` and is defined FIRST, so
    # the bare line patched the wrong function and this case reported GREEN — VACUOUS. A
    # first-occurrence replace is only as precise as its anchor is unique.
    ("grant the paid half to anyone who is merely signed in", ENTITLEMENT,
     "        return False\n    return bool(ent and ent.fantasy)",
     "        return False\n    return bool(ent and not ent.is_anonymous)",
     "test_a_signed_in_caller_without_fantasy_is_treated_as_free_not_as_entitled", SUITE),

    # ── the G100-C1 seam, now FLIPPED ON ──────────────────────────────────────────────────────
    # 🗄️ This case used to break the quota by raising it 0 → 1, which was the drift the seam
    # existed to prevent. G100-C1 (2026-08-08) made that raise the SHIPPED value, so the same case
    # now points the other way: the number is pinned in BOTH directions, and either a revert or a
    # further raise is a pricing change that has to be seen.
    ("drift the free personalization quota away from one", ENTITLEMENT,
     'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "1"))',
     'FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "3"))',
     "test_the_free_personalized_league_quota_is_one", SUITE),

    # ⭐ AND THE CAPABILITY ITSELF — the one-line "fix" that opens every gate at once. A free
    # account holds a QUOTA against a PAID capability; moving the capability into FREE_CAPABILITIES
    # would silently free every other surface that reads it.
    ("reclassify PERSONALIZATION as free rather than granting a quota", ENTITLEMENT,
     "FREE_CAPABILITIES: frozenset[Capability] = frozenset({Capability.GENERIC_BOARD})",
     "FREE_CAPABILITIES: frozenset[Capability] = frozenset("
     "{Capability.GENERIC_BOARD, Capability.PERSONALIZATION})",
     "test_personalization_is_still_a_paid_capability_after_the_free_grant", SUITE),

    # ⭐ THE NO-REGRESSION HALF, after G100-C1 moved it. "personalization is reachable" no longer
    # discriminates on its own — it passes against a server with no gate at all. Withdrawing the
    # quota is what proves the gate READS it.
    ("wave every caller through the personalization gate", DEPENDENCIES,
     "    if entitlement.allows_personalization(entitlement.resolve_entitlement(request)):",
     "    if True:",
     "test_personalization_is_still_refused_when_the_free_quota_is_withdrawn", SUITE),

    # ── ONE preset is free (2026-08-08) ───────────────────────────────────────────────────────
    # The whole gate is one predicate and one call site, so it has exactly two ways to fail open:
    # the predicate says yes to everything, or the route stops asking. Both are here, plus the two
    # SHAPES of paid board (a different format, and the free format at a different size) — a gate
    # written against the format alone passes the first and fails the second.
    ("call every preset the free one", ENTITLEMENT,
     [('        return str(config) == FREE_BOARD_CONFIG and int(size) == FREE_BOARD_SIZE',
       '        return True')],
     None,
     "test_only_the_one_preset_is_free", SUITE),

    ("gate on the FORMAT and forget the league SIZE", ENTITLEMENT,
     [('        return str(config) == FREE_BOARD_CONFIG and int(size) == FREE_BOARD_SIZE',
       '        return str(config) == FREE_BOARD_CONFIG')],
     None,
     "test_only_the_one_preset_is_free", SUITE),

    # ⭐ The same size-blindness seen END TO END rather than as a predicate. The unit clause above
    # could be satisfied by a correct predicate nobody calls; this one fails only if a real request
    # for `full_ppr`/10 is actually refused.
    ("gate on the FORMAT only, seen through the API", ENTITLEMENT,
     [('        return str(config) == FREE_BOARD_CONFIG and int(size) == FREE_BOARD_SIZE',
       '        return str(config) == FREE_BOARD_CONFIG')],
     None,
     "test_an_anonymous_caller_is_refused_a_paid_preset", SUITE),

    ("stop asking who is requesting the board", ROUTER,
     [("    if not entitlement.allows_board(config, size, entitlement.resolve_entitlement(request)):",
       "    if False:")],
     None,
     "test_an_anonymous_caller_is_refused_a_paid_preset", SUITE),

    # The OPPOSITE failure, and the one a nervous fix produces: refusing everyone. Every "anonymous
    # is refused" clause above stays green while subscribers lose the thing they pay for.
    ("refuse the paid presets to subscribers too", ENTITLEMENT,
     [("    if is_free_board(config, size):\n        return True\n"
       "    return bool(ent and ent.fantasy)",
       "    if is_free_board(config, size):\n        return True\n    return False")],
     None,
     "test_a_subscriber_gets_a_paid_preset", SUITE),

    # ⚠️ TWO INSUFFICIENT BREAKS BEFORE THIS ONE, and both were the same lesson as the
    # `require_fantasy_access` case above: the guard stayed GREEN because a DIFFERENT layer was
    # still refusing. (a) Forcing `verified` truthy left the GROUPS coming from
    # `jwt_verify.verified_groups`, which still returned nothing for an unsigned token. (b) Reading
    # them via `dependencies._groups_from_request` failed too — E9.56 hardened that helper to fall
    # back to a VERIFIED decode whenever the authorizer context is absent, which is exactly the
    # public-route case. Both are defence in depth working.
    #
    # ⇒ the break has to remove the signature check at its SOURCE. `_unverified_claims` is the
    # pre-verification decode the module already has, so this is the shape a real regression takes:
    # someone reaches for the convenient decode and skips the verify.
    ("skip the signature check and trust the token's own claims", REPO / "app/backend/services/jwt_verify.py",
     [("def verify_cognito_token(token: str | None) -> dict | None:",
       "def verify_cognito_token(token: str | None) -> dict | None:\n"
       "    import base64 as _b64, json as _json\n"
       "    try:\n"
       "        _p = str(token).split()[-1].split('.')[1]\n"
       "        return _json.loads(_b64.urlsafe_b64decode(_p + '=' * (-len(_p) % 4)))\n"
       "    except Exception:\n"
       "        return None\n")],
     None,
     "test_a_forged_token_does_not_unlock_a_paid_preset", SUITE),

    # A junk config must be rejected on SYNTAX before entitlement is consulted, or the status code
    # tells an attacker whether their token is entitled on a request that was never valid anyway.
    ("check entitlement before validating the config name", ROUTER,
     [("    if not _CONFIG_RE.match(config):\n"
       '        raise HTTPException(status_code=422, detail="Invalid config name")',
       "    pass")],
     None,
     "test_a_junk_config_reads_the_same_to_everyone", SUITE),

    # ── the manifest is how the client learns where the line is ───────────────────────────────
    ("stop telling the client which preset is free", ENTITLEMENT,
     [('    out["freeBoard"] = {"config": FREE_BOARD_CONFIG, "size": FREE_BOARD_SIZE}', "    pass")],
     None,
     "test_the_manifest_marks_exactly_the_free_preset", SUITE),

    ("mark every preset free in the manifest", ENTITLEMENT,
     [('{**c, "free": c.get("name") == FREE_BOARD_CONFIG} if isinstance(c, dict) else c',
       '{**c, "free": True} if isinstance(c, dict) else c')],
     None,
     "test_the_manifest_marks_exactly_the_free_preset", SUITE),

    # ⚠️ The NF-C0 shape break: marking the presets by REBUILDING each config instead of spreading
    # it drops every other key (`label`, `description`, `roster`, `adpFormat`) — a 200 whose format
    # picker renders blank rows. The clause above cannot see it; it only reads `name` and `free`.
    ("rebuild each config instead of extending it", ENTITLEMENT,
     [('{**c, "free": c.get("name") == FREE_BOARD_CONFIG} if isinstance(c, dict) else c',
       '{"name": c.get("name"), "free": c.get("name") == FREE_BOARD_CONFIG} '
       "if isinstance(c, dict) else c")],
     None,
     "test_the_manifest_marking_is_purely_additive", SUITE),

    # ── the edge must not be able to ask a caller-dependent question ──────────────────────────
    ("let the CDN route proxy any preset", REPO / "frontend/app/api/public/[...path]/route.ts",
     [("params: { season: /^\\d{4}$/, config: /^full_ppr$/, size: /^12$/ },",
       "params: { season: /^\\d{4}$/, config: /^[a-z0-9_]{1,64}$/, "
       "size: /^(?:[2-9]|[12]\\d|3[0-2])$/ },")],
     None,
     "test_the_cdn_route_can_only_ask_for_the_free_board", SUITE),

    # ── the picker, and the two ways it goes wrong ────────────────────────────────────────────
    ("leave the paid presets selectable", SHARED,
     [("                  disabled: locked,\n                }\n              }),",
       "                  disabled: false,\n                }\n              }),")],
     None,
     "test_the_picker_disables_every_paid_preset_for_an_unentitled_caller", SUITE),

    ("lock the format but leave the paid league SIZE selectable", SHARED,
     [("              const locked = lockFormats && n !== free!.size",
       "              const locked = false && n !== free!.size")],
     None,
     "test_the_picker_disables_every_paid_preset_for_an_unentitled_caller", SUITE),

    # ⭐ The tempting "fix" that satisfies the two clauses above completely: remove the paid presets
    # rather than disable them. The visitor can no longer select one — and can no longer SEE that
    # they exist, which is the opposite of what an upgrade prompt is for.
    ("hide the paid presets instead of disabling them", SHARED,
     [("              options: manifest.configs.map((c) => {",
       "              options: manifest.configs.filter((c) => isFreeConfig(c)).map((c) => {")],
     None,
     "test_a_locked_preset_is_listed_rather_than_removed", SUITE),

    ("default an unentitled visitor onto a paid preset", QUERIES,
     [("    if (!entitled && free) {", "    if (false && free) {")],
     None,
     "test_an_unentitled_visitor_is_defaulted_onto_a_board_they_can_read", SUITE),

    # ⚠️ THE BREAK HAD TO CHANGE WITH THE CLAUSE, and the reason is worth keeping: the first version
    # patched a `storedIsFree` ternary whose two arms were IDENTICAL, so the break was a genuine
    # no-op and reported GREEN — VACUOUS. That was a defect in the SOURCE, not in the harness: dead
    # code cannot be broken. The branch now ignores `stored` outright, and the honest regression is
    # putting it back.
    ("honour a stored paid selection for an unentitled caller", QUERIES,
     [("      setConfigName(names.includes(free.config) ? free.config : names[0] ?? null)",
       "      setConfigName(stored.configName ?? free.config)")],
     None,
     "test_an_unentitled_visitor_is_defaulted_onto_a_board_they_can_read", SUITE),

    ("report a refused board as an empty search", RANKINGS,
     [("          {!boardLoading && boardError && (", "          {false && boardError && (")],
     None,
     "test_a_refused_board_does_not_render_as_an_empty_search", SUITE),

    # ── the paid formats must not be readable, or derivable, on a free surface ────────────────
    # Three leaks, all client-side: the API serves `fpStd`/`fpHalf` to everyone by design, so the
    # gate is entirely which component prints them. The third is arithmetic rather than a column.
    ("offer every reference scoring on the projections page", PROJECTIONS,
     [("                  const lockedOption = !entitled && s !== FREE_SCORING",
       "                  const lockedOption = false")],
     None,
     "test_the_projections_page_offers_only_the_free_reference_scoring", SUITE),

    # ⭐ THE SUBTLE ONE. The picker still LOOKS locked — the options are disabled, the note renders,
    # every "is it locked" assertion stays green — but the table reads the raw state, so anything
    # that sets it (a future URL param, a restored preference, a test) reaches the paid numbers.
    ("read the picker state directly instead of the derived scoring", PROJECTIONS,
     [("  const effScoring: Scoring = entitled ? scoring : FREE_SCORING",
       "  const effScoring: Scoring = scoring")],
     None,
     "test_the_projections_page_reads_the_derived_scoring_not_the_raw_state", SUITE),

    ("print the standard total on a free player page", PLAYER_PAGE,
     [("value={entitled ? num(proj.fpStd) : <LockChip title={STAT_LINE_LOCK_TITLE} />}",
       "value={num(proj.fpStd)}")],
     None,
     "test_the_player_page_locks_the_two_paid_reference_totals", SUITE),

    ("print the half-PPR total on a free player page", PLAYER_PAGE,
     [("value={entitled ? num(proj.fpHalf) : <LockChip title={STAT_LINE_LOCK_TITLE} />}",
       "value={num(proj.fpHalf)}")],
     None,
     "test_the_player_page_locks_the_two_paid_reference_totals", SUITE),

    # ⭐⭐ THE CASE THE WHOLE SECTION TURNS ON. With the stat line back, the two locked totals are
    # exact mental arithmetic (`half = full − 0.5·rec`), so every "the total is locked" clause above
    # stays green while the withheld numbers are one subtraction away on the same screen.
    ("show the raw stat line beside the locked totals", PLAYER_PAGE,
     [('              {entitled ? (\n                <div className="grid grid-cols-3',
       '              {true ? (\n                <div className="grid grid-cols-3')],
     None,
     "test_the_player_page_gates_the_raw_stat_line", SUITE),

    ("tell a free visitor a preset is their own league", PLAYER_PAGE,
     [("                    : config?.label ?? \"Board scoring\"",
       "                    : config ? `${config.label} (your league)` : \"Your league\"")],
     None,
     "test_the_free_player_page_makes_no_claim_about_the_readers_league", SUITE),

    ("claim the stat-line lock stops scraping", COPY,
     [('  "Targets, receptions, yards and touchdowns',
       '  "Stops scraping. Targets, receptions, yards and touchdowns')],
     None,
     "test_the_stat_line_lock_does_not_claim_to_stop_scraping", SUITE),

    # ── copy that describes an entitlement goes stale silently ────────────────────────────────
    ("let the free-tier copy claim a format it no longer covers", COPY,
     [('"Every player we project, every ranking, every 80% range and the market ADP beside it '
       "— no account, no trial, and no number quietly withheld. It is the same board for everyone, "
       'which is exactly what makes it free.",',
       '"Every player we project, scored for every PPR preset we publish.",')],
     None,
     "test_the_free_tier_summary_names_no_league_format", SUITE),

    ("stop naming the format half in the paid summary", COPY,
     [('    title: "Every scoring format, at your league\'s size",',
       '    title: "More of the board",')],
     None,
     "test_the_paid_summary_names_both_halves_of_the_boundary", SUITE),

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

    # ⚠️ RE-ANCHORED. This case originally patched `FREEMIUM_BOUNDARY_LINE`, which was then deleted
    # for having no caller — and the harness reported ANCHOR-MISSING rather than passing, which is
    # the behaviour that makes a stale case visible instead of silently unproven (the shape that
    # quietly staled `unhedged-plain-lead` in the e2e harness). Now anchored on copy the boundary
    # actually RENDERS, so the case cannot go stale without the surface changing.
    ("turn the paid pitch into a performance promise", COPY,
     '    title: "Your league, not a preset",',
     '    title: "Win your league, not a preset",',
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
