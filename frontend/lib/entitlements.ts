// Per-SURFACE entitlement (E9.45). The app is multi-PRODUCT (betting + fantasy) and
// entitlement now differs BY SURFACE — a single paywall boolean is no longer enough:
//
//  • BETTING is GRANDFATHERED — open to every current access tier (admin / subscriber /
//    beta_tester). This mirrors the existing `has_access` rule; do NOT tighten it.
//  • FANTASY is a PAID feature: `subscriber` or `admin` or the `fantasy_comp` comp
//    allow-list ONLY. `beta_tester` is deliberately NOT granted fantasy (the divergence
//    from E9.8's paywall, where beta_tester bypasses) — no beta tier for fantasy.
//
// The `fantasy_comp` group is kept DISTINCT from `subscriber` on purpose: comps must not
// count toward E9.8's founding-100 $10→$20 flip, nor into paid analytics.
//
// The server enforces the same rule on the fantasy DATA endpoints (require_fantasy_access
// → 403) — this client helper only decides nav visibility / the locked-vs-open state.

import { apiErrorStatus } from "./api"

export type Surface = "betting" | "fantasy"

// Betting = the existing has_access group set (E9.8's ACCESS_GROUPS). Grandfathered.
const BETTING_GROUPS = ["admin", "subscriber", "beta_tester"] as const
// Fantasy = paid subscribers + admin + the comp allow-list. No beta tier.
const FANTASY_GROUPS = ["admin", "subscriber", "fantasy_comp"] as const

export function canAccess(surface: Surface, groups: string[]): boolean {
  const allowed = surface === "fantasy" ? FANTASY_GROUPS : BETTING_GROUPS
  return allowed.some((g) => groups.includes(g))
}

// True for an operator/comp on the fantasy allow-list (distinct from a paid subscriber).
export function isFantasyComp(groups: string[]): boolean {
  return groups.includes("fantasy_comp")
}

// ── NF-C0b: a NARROWER gate than the fantasy surface ─────────────────────────
// The manual league-settings editor ships to `admin` + `fantasy_comp` ONLY — a paying
// `subscriber` has fantasy but NOT the editor yet. Deliberately tighter than
// FANTASY_GROUPS: the settings saved there drive the board, VOR and the draft tool, so
// it goes to operator + comp accounts first (the staged shape MVP-3 used when the draft
// tool was admin-only).
//
// ⚠️ MIRROR OF THE SERVER RULE — `cognito.FANTASY_BETA_GROUPS` /
// `require_fantasy_beta_access`. This helper only hides nav/pages; the API is the actual
// gate (these are WRITE endpoints). Widen BOTH together or the two disagree.
const FANTASY_BETA_GROUPS = ["admin", "fantasy_comp"] as const

export function canAccessFantasyBeta(groups: string[]): boolean {
  return FANTASY_BETA_GROUPS.some((g) => groups.includes(g))
}

// ══ THE FREEMIUM BOUNDARY (2026-08-08, GROWTH-100) ═══════════════════════════════════════════════
//
// ⭐ MIRROR OF `app/backend/services/entitlement.py::Capability`. The server is the gate; this is
// what the UI branches on so a surface can say WHICH half it is in rather than re-deriving it from
// a group list. Both sides are pinned together by `test_freemium_tier.py` — a capability added on
// one side and not the other fails the build, because a UI that thinks a surface is free while the
// API 403s it renders a permanently broken page with no error anywhere.
//
// The split, in the terms the pricing page uses:
//   FREE  — the GENERIC board. Rankings + projections for the shipped presets, the 80% ranges,
//           market ADP, player pages, methodology. Anonymous included.
//   PAID  — PERSONALIZATION (your league's scoring/roster shape re-scoring the board, saved state)
//           and DECISION SUPPORT (the draft optimizer, the weekly tools).
//
// ⚠️ THIS IS NOT WHAT E9.56 DID. That story locked the CURRENT SEASON everywhere and served a
// per-point "subscribe to unlock" marker on the generic board. The freemium build retired that: the
// generic board's numbers are the acquisition wedge, so withholding them withheld the thing that
// earns the signup. The `locked` handling downstream (`LockChip`, `numOrLock`, `rowsAreLocked`) is
// KEPT as defensive rendering — a row that arrives without `pts` must render a chip, never `NaN` —
// but on the generic surfaces nothing sets it any more.

export type FantasyCapability = "generic_board" | "personalization" | "decision_support"

/** Free for everyone, including logged-out. One entry on purpose — widening it is a pricing
 *  decision, not a refactor. */
export const FREE_CAPABILITIES: readonly FantasyCapability[] = ["generic_board"] as const

/** Stated explicitly rather than as "everything else", so a NEW capability belongs to neither set
 *  until someone places it — and the guard test says so — instead of defaulting into one silently. */
export const PAID_CAPABILITIES: readonly FantasyCapability[] = [
  "personalization",
  "decision_support",
] as const

/**
 * Whether these Cognito groups may exercise `capability`.
 *
 * FAILS CLOSED on anything unplaced: an unrecognised capability is treated as PAID, matching the
 * server's `allows()`. A refused paid surface is visible and reversible; a leaked one is not.
 */
export function canUse(capability: FantasyCapability, groups: string[]): boolean {
  if ((FREE_CAPABILITIES as readonly string[]).includes(capability)) return true
  if (!(PAID_CAPABILITIES as readonly string[]).includes(capability)) return false
  return canAccess("fantasy", groups)
}

// ══ G100-C1 — ONE FREE PERSONALIZED LEAGUE ═══════════════════════════════════════════════════════
//
// ⭐ MIRROR OF `entitlement.FREE_PERSONALIZED_LEAGUE_QUOTA` / `personalized_league_quota` /
// `allows_personalization`. Pinned to the Python side by `test_g100_c1_free_league.py`, because a UI
// that thinks a surface is free while the API 403s it renders a permanently broken page with no
// error anywhere (and the reverse hides a feature the user is paying for).
//
// ⛔ `personalization` IS STILL A PAID CAPABILITY and `canUse("personalization", …)` still returns
// false for a free account. That is not a contradiction to fix — it is the distinction the whole
// tier rests on:
//
//   canUse("personalization", groups)   "is personalization in your tier?"   → what the PRICING says
//   personalizedLeagueQuota(groups)     "how many leagues may you keep?"     → what you may DO today
//
// A free account is `false` on the first and `1` on the second. Collapsing them by moving
// `personalization` into FREE_CAPABILITIES would be a pricing change wearing a refactor's clothes,
// and would silently free every other surface reading the same capability.
//
// ⚠️ SO: a component deciding whether to OFFER league setup must read `canConfigureLeague`, never
// `canUse("personalization", …)`. The freemium build's own lesson is that the gate is WHICH
// COMPONENT RENDERS — #681 gated one of three renderers and looked done — so the surfaces are
// enumerated in `docs/freemium_tier.md` and pinned by the e2e spec rather than left to memory.

/** How many personalized leagues a signed-in FREE account may keep. Mirrors the Python default. */
export const FREE_PERSONALIZED_LEAGUE_QUOTA = 1

/** The paid ceiling — mirrors `dynamo.MAX_LEAGUES_PER_USER`, which is what a subscriber's quota
 *  resolves to. Used only for copy ("you can save N leagues"); the server is the gate. */
export const MAX_LEAGUES_PER_USER = 25

/**
 * How many leagues these groups may keep.
 *
 * ⚠️ This answers "how many", not "may you" — it cannot see whether the caller is signed in, and a
 * league can only be stored against a Cognito `sub`. `canConfigureLeague` is the one that asks both.
 */
export function personalizedLeagueQuota(groups: string[]): number {
  return canAccess("fantasy", groups) ? MAX_LEAGUES_PER_USER : FREE_PERSONALIZED_LEAGUE_QUOTA
}

/**
 * Whether this caller may configure a personalized league at all.
 *
 * SIGNED IN + a quota above zero. Both halves matter and they fail differently: a logged-out visitor
 * needs SIGNUP (the server answers 401), a caller whose quota has been withdrawn needs a MEMBERSHIP
 * (403). Sending the first group to a paywall asks them to buy what they can have for free.
 */
export function canConfigureLeague(signedIn: boolean, groups: string[]): boolean {
  return signedIn && personalizedLeagueQuota(groups) > 0
}

/**
 * Whether this caller may save ANOTHER league given how many they already have.
 *
 * ⚠️ ADVISORY ONLY — `POST /fantasy/leagues` enforces the same rule and answers 409. This exists so
 * the UI can state the boundary at the control instead of letting someone fill in a form that is
 * going to be refused, which is the freemium build's "state the lock AT the control" pattern.
 */
export function canSaveAnotherLeague(savedCount: number, groups: string[]): boolean {
  return savedCount < personalizedLeagueQuota(groups)
}

/**
 * NF-DTB-1 — was THIS failed league save the free-league cap, rather than a fault?
 *
 * ⭐ WHY A SERVER REFUSAL STILL HAPPENS AT ALL, given `canSaveAnotherLeague` above disables the
 * control. That check is advisory and reads a CACHED list: `useSavedLeagues` has `staleTime: 60s`
 * and `retry: false`, and its `data` is `undefined` both while loading and ON ERROR — every one of
 * which makes `(leagues ?? []).length` read 0, i.e. "not at quota", and re-enables the button. So
 * the last line of defence is the server's 409, and what it hits on the way back out has to say
 * "limit", not "failure".
 *
 * ⚠️ SCOPED TO THE LEAGUE-SAVE CALL SITES ON PURPOSE. `POST /fantasy/leagues` raises exactly one
 * 409, and it is the quota — but that is a fact about THAT route, not about the number 409, so this
 * predicate is named for the route it interprets rather than living in `api.ts` as a generic
 * `isConflict`. A shared status→meaning table is where a status quietly acquires a wrong meaning.
 */
export function isLeagueQuotaRefusal(e: unknown): boolean {
  return apiErrorStatus(e) === 409
}
