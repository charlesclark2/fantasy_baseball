/**
 * G100-D0 — THE FUNNEL EVENT CONTRACT.
 *
 * ══ WHY THIS FILE HAS NO `"use client"` AND NO POSTHOG IMPORT ═════════════════════════════════
 *
 * It had both in the first cut, and that shipped a silent defect the E2E suite caught on the wire:
 *
 *   ⚠️ A CONSTANT IMPORTED FROM A `"use client"` MODULE INTO A **SERVER** COMPONENT ARRIVES AS
 *   `undefined`. The home page is a server component; it imported `ACQUISITION_SURFACES.HOME` from
 *   here and passed it as a prop; Next.js resolved the module to a client REFERENCE rather than to
 *   its values, so the prop serialised to nothing and every `landing_view` from the highest-traffic
 *   page in the product shipped with **no `surface`**. `tsc` was perfectly happy — the types are
 *   real — `next build` was happy, the event still fired, and the only symptom was one missing
 *   property on a chart nobody had built yet.
 *
 * So the contract (names, surfaces, pure derivations) lives here, importable from anywhere on
 * either side of the boundary, and everything that touches `posthog` lives in
 * `funnel-telemetry-emit.ts`. The split is not tidiness — it is what makes "a server component may
 * name an acquisition surface" a structural property instead of a thing to remember.
 *
 * ══ WHAT THIS FILE IS ═════════════════════════════════════════════════════════════════════════
 *
 * One place that names the six events the founder dashboard reads, and one place that derives the
 * dimensions they are broken down by. The names are a CONTRACT with `docs/g100_d0_funnel.md` and
 * with the HogQL in `scripts/provision_posthog_funnel_dashboard.py`; renaming one here without
 * renaming it there produces a chart that silently reads zero, which is worse than no chart —
 * a zero looks like a conversion collapse rather than a broken query.
 * `betting_ml/tests/test_g100_d0_funnel_telemetry.py` pins the two sides together.
 *
 * ⛔ FOUR OF THE SIX WERE ALREADY LIVE BEFORE THIS STORY (E9.58 + G100-C1) and are re-declared
 * here as constants rather than re-emitted: `user_signup_started`, `user_signup_completed`,
 * `league_config_completed`, `custom_board_viewed`. Their call sites are unchanged. Declaring them
 * is the point — the dashboard's spine has to be one list, not two half-lists.
 *
 * ══ THE THREE THINGS THAT MAKE THESE NUMBERS EASY TO MISREAD ══════════════════════════════════
 *
 * All three were found by G100-C1's live testing, and each one, gotten wrong, makes the activation
 * rate read like a CONVERSION problem and sends the next story at the wrong thing:
 *
 *   1. COUNT DISTINCT PERSONS, NEVER EVENTS. `custom_board_viewed` fires once per page MOUNT (by
 *      design, and tested) — one user produced three in an hour. Every metric on the dashboard
 *      therefore dedupes on `person_id`. ⭐ THAT IS WHY THIS FILE DOES NOT TRY TO DEDUPE ON THE
 *      CLIENT: a browser cannot see a person across devices or a cleared session, so a client-side
 *      "only once" is a weaker version of a guarantee the query already provides exactly. The
 *      once-per-mount refs that DO exist (my-league.tsx) are there to stop one view being counted
 *      many times, which is a different problem.
 *   2. `user_signup_completed` MEANS "THIS SIGN-IN CREATED THE ACCOUNT" (G100-D0-R1). It used to
 *      mean "clicked Sign Up and came back with a session", which was wrong in both directions
 *      because Google federation auto-provisions at EITHER door: a first-timer entering through
 *      /login emitted nothing at all (and an ordered funnel then discarded them), while a
 *      returning user who clicked Sign Up emitted a signup that never happened. It is now keyed
 *      on the server's `created` answer from `/auth/accept-terms`, so the door does not matter.
 *      ⚠️ STILL NOT AN ACCOUNT COUNT: it is a first-ToS-acceptance proxy, it is a floor across a
 *      backend deploy skew, and COGNITO creation dates remain the truth. Stated on the dashboard.
 *   3. `league_config_completed` fires ONLY on a CREATE (both doors — manual editor and import —
 *      separated by `method`). A re-import that refreshes a roster deliberately does not re-count.
 *
 * ══ ATTRIBUTION IS FIRST-TOUCH, AND IT IS A SUPER PROPERTY ════════════════════════════════════
 *
 * `acquisition_source` / `campaign` / `referrer` are registered ONCE per browser
 * (`posthog.register_once`) and then ride on EVERY subsequent event, including the ones fired days
 * later on the other side of a signup. That is what makes "activation rate by acquisition source"
 * answerable at all: the activation event happens on a surface that has no idea where the visitor
 * originally came from.
 *
 * ⭐ AND IT IS WHY `captureLandingView` DOES NOT PASS THEM ITSELF. PostHog merges super properties
 * into every event, but an explicitly-passed property OVERRIDES the super property of the same
 * name — so passing this-touch values on `landing_view` while every downstream event carried
 * first-touch values would make one step of the funnel break down differently from the other five,
 * on the same property name. One set of names, one semantics: first touch, everywhere.
 */

// ══════════════════════════════════════════════════════════════════════════════════════════════
// The events
// ══════════════════════════════════════════════════════════════════════════════════════════════

export const FUNNEL_EVENTS = {
  /** A visitor reached an acquisition surface. Fired per view; deduped to a person in the query. */
  LANDING_VIEW: "landing_view",
  /** Clicked a Sign-Up affordance (E9.58). The step BEFORE the OAuth round-trip. */
  SIGNUP_STARTED: "user_signup_started",
  /** This sign-in CREATED the account, whichever door it came through (E9.58, re-keyed to the
   *  server's answer by G100-D0-R1). Carries `signal` — "server", or "intent_fallback" during a
   *  backend deploy skew. */
  SIGNUP_COMPLETED: "user_signup_completed",
  /** Saved a league for the first time — manual editor or import (G100-C1). CREATE only. */
  LEAGUE_CONFIG_COMPLETED: "league_config_completed",
  /** ⭐ ACTIVATION. Their own re-scored board actually rendered (G100-C1). */
  CUSTOM_BOARD_VIEWED: "custom_board_viewed",
  /** Asked the backend for a Stripe Checkout Session — i.e. left for the card form. */
  CHECKOUT_STARTED: "checkout_started",
  /** Payment landed AND the webhook granted access. See the caveat on `captureSubscriptionStarted`. */
  SUBSCRIPTION_STARTED: "subscription_started",
} as const

/**
 * The spine, in order. The dashboard's three rates are computed from adjacent-ish members of this
 * list, so the ORDER is part of the contract and is asserted against the dashboard spec.
 *
 * Activation is the conjunction G100-C1 defined — `account_created AND league_config_completed AND
 * custom_board_viewed` — and `custom_board_viewed` is its terminal clause: it is unreachable
 * without a configured league, and a signed-out visitor cannot produce one. So the funnel treats
 * `custom_board_viewed` as the activation marker and carries `league_config_completed` as the step
 * before it rather than as a second thing to intersect. ⚠️ That is an equivalence that holds
 * because of how the app is built, not by definition — if a future story ever renders a
 * personalised board without a saved league, this stops being true and the dashboard needs the
 * explicit intersection instead.
 */
export const FUNNEL_SPINE = [
  FUNNEL_EVENTS.LANDING_VIEW,
  FUNNEL_EVENTS.SIGNUP_COMPLETED,
  FUNNEL_EVENTS.LEAGUE_CONFIG_COMPLETED,
  FUNNEL_EVENTS.CUSTOM_BOARD_VIEWED,
  FUNNEL_EVENTS.CHECKOUT_STARTED,
  FUNNEL_EVENTS.SUBSCRIPTION_STARTED,
] as const

/**
 * Surfaces that count as an ACQUISITION surface — the pages a stranger can land on and get value
 * from without an account. Deliberately NOT every public route: `/subscribe` is a conversion
 * surface, `/login` is a return path, and counting either as a "visitor" would put people who are
 * already deep in the funnel into the top of it and depress every rate below.
 */
export const ACQUISITION_SURFACES = {
  HOME: "home",
  FANTASY_RANKINGS: "fantasy_rankings",
  FANTASY_PROJECTIONS: "fantasy_projections",
  FANTASY_PLAYER: "fantasy_player",
} as const

export type AcquisitionSurface =
  (typeof ACQUISITION_SURFACES)[keyof typeof ACQUISITION_SURFACES]

// ══════════════════════════════════════════════════════════════════════════════════════════════
// The dimensions — pure derivations, so the E2E suite can drive them from a real URL
// ══════════════════════════════════════════════════════════════════════════════════════════════

export type AcquisitionAttribution = {
  acquisition_source: string
  campaign: string | null
  referrer: string | null
}

export type DeviceClass = "mobile" | "tablet" | "desktop"

/**
 * `anonymous` → `free` → `paid`, plus `comped`.
 *
 * ⭐ `comped` EXISTS SO THE OPERATOR DOES NOT COUNT THEMSELVES AS A CONVERSION. `admin`,
 * `beta_tester` and `fantasy_comp` all have full access and have paid nothing; folding them into
 * `paid` would put the founder's own account, and every beta tester, in the numerator of the metric
 * the whole sprint is judged on. At launch scale that is not a rounding error — it is most of the
 * numerator.
 */
export type FreePaidStatus = "anonymous" | "free" | "paid" | "comped"

/** Groups that mean "is actually paying us". Only one. */
const PAYING_GROUPS = ["subscriber"] as const
/** Groups that mean "has access, pays nothing". */
const COMPED_GROUPS = ["admin", "beta_tester", "fantasy_comp"] as const

/**
 * First-touch attribution from a URL + the document referrer.
 *
 * Precedence: an explicit `utm_source` beats an inferred referrer host, and a visit with neither is
 * `direct`. ⚠️ An INTERNAL referrer is dropped rather than recorded: a click from our own home page
 * to the rankings page would otherwise register `credencesports.com` as the acquisition source of
 * everyone who browses, which is the single easiest way to make an attribution breakdown useless.
 *
 * Pure, and takes its inputs explicitly, so `funnel-telemetry.spec.ts` can drive it from a real
 * navigation and read the result off the wire rather than asserting about a mock.
 */
export function readAcquisitionAttribution(
  url: string,
  referrer: string,
  selfHost: string,
): AcquisitionAttribution {
  let params: URLSearchParams
  try {
    params = new URL(url).searchParams
  } catch {
    params = new URLSearchParams()
  }

  const utmSource = params.get("utm_source")?.trim() || null
  const campaign = params.get("utm_campaign")?.trim() || null

  let referrerHost: string | null = null
  try {
    const host = referrer ? new URL(referrer).host : ""
    // Our own host is not a referrer; nor is an empty one.
    if (host && host !== selfHost) referrerHost = host
  } catch {
    referrerHost = null
  }

  return {
    acquisition_source: utmSource ?? referrerHost ?? "direct",
    campaign,
    referrer: referrerHost,
  }
}

/**
 * Device class from the VIEWPORT, not the user-agent string.
 *
 * A UA string is spoofable, deprecated in pieces, and — as G100-C1's harness discovered the hard
 * way — not even the thing posthog-js itself reads for its bot check. The viewport is what actually
 * determines which layout the visitor saw, which is the question a funnel breakdown is asking
 * ("does the phone experience convert worse?"). Boundaries match Tailwind's `sm`/`lg`, so the
 * buckets line up with the breakpoints the pages are actually built against.
 */
export function readDeviceClass(viewportWidth: number): DeviceClass {
  if (viewportWidth < 640) return "mobile"
  if (viewportWidth < 1024) return "tablet"
  return "desktop"
}

export function readFreePaidStatus(signedIn: boolean, groups: string[]): FreePaidStatus {
  if (!signedIn) return "anonymous"
  if (PAYING_GROUPS.some((g) => groups.includes(g))) return "paid"
  if (COMPED_GROUPS.some((g) => groups.includes(g))) return "comped"
  return "free"
}
