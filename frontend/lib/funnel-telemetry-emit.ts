"use client"

import posthog from "posthog-js"
import {
  FUNNEL_EVENTS,
  readAcquisitionAttribution,
  readDeviceClass,
  readFreePaidStatus,
  type AcquisitionSurface,
} from "@/lib/funnel-telemetry"

/**
 * G100-D0 — the side of the funnel contract that talks to PostHog.
 *
 * Split from `funnel-telemetry.ts` for a measured reason, not for tidiness: a constant imported
 * from a `"use client"` module into a SERVER component arrives as `undefined`, which is how the
 * first cut shipped every home-page `landing_view` with no `surface` and no error anywhere. The
 * names and pure derivations therefore live in a boundary-free module; only this file imports
 * `posthog`, and only client components import this file.
 */

/**
 * Register first-touch attribution + the current device class as SUPER PROPERTIES.
 *
 * Called from every page (see `<FunnelTelemetry/>` in the root layout), not only from acquisition
 * surfaces, because a visitor can arrive anywhere — a shared `/subscribe` link, a deep link to a
 * player page — and attribution that only fires on pages we consider "the top of the funnel" would
 * record `direct` for exactly the traffic a campaign sent somewhere else.
 *
 * `register_once` for attribution (first touch wins forever, so a signup on visit three is still
 * credited to the campaign that brought them on visit one); plain `register` for device, which is a
 * property of the session in front of you and is allowed to change.
 */
export function registerFunnelSuperProperties(): void {
  if (typeof window === "undefined") return
  const attribution = readAcquisitionAttribution(
    window.location.href,
    document.referrer,
    window.location.host,
  )
  posthog.register_once(attribution)
  posthog.register({ device: readDeviceClass(window.innerWidth) })
}

/** Keep `free_paid_status` current on every event. See the `comped` note on `FreePaidStatus`. */
export function registerFreePaidStatus(signedIn: boolean, groups: string[]): void {
  posthog.register({ free_paid_status: readFreePaidStatus(signedIn, groups) })
}

/**
 * Top of the funnel.
 *
 * Carries only `surface` — the attribution dimensions arrive as super properties (see the module
 * header for why passing them here would be actively wrong).
 */
export function captureLandingView(surface: AcquisitionSurface): void {
  posthog.capture(FUNNEL_EVENTS.LANDING_VIEW, { surface })
}

/**
 * The visitor asked for a Checkout Session; a full-page redirect to Stripe follows.
 *
 * `send_instantly`, for the same reason E9.58c added it to the signup captures: what happens next
 * is `window.location.href = …`, and a batched event still sitting in the queue when the document
 * is torn down is simply lost. That loss is not random — it correlates with the FAST redirects,
 * so a batched capture here would under-count exactly the smoothest checkouts.
 */
export function captureCheckoutStarted(props: Record<string, unknown>): void {
  posthog.capture(FUNNEL_EVENTS.CHECKOUT_STARTED, props, { send_instantly: true })
}

/**
 * Payment landed AND access was granted.
 *
 * ⚠️ READ THE CAVEAT BEFORE TRUSTING THIS AS A REVENUE NUMBER. It fires on the post-checkout
 * screen once `/subscription/status` reports `has_access` — i.e. once the Stripe WEBHOOK has
 * actually granted the group, not merely when Stripe redirected. That makes it honest about what it
 * claims (nobody is counted as paid before they have access) but it is CLIENT-CONFIRMED, so a
 * visitor who closes the tab during the ~2-24s activation poll pays us and is never counted.
 *
 * ⇒ THE DASHBOARD STATES STRIPE AS THE SOURCE OF TRUTH FOR PAID COUNTS, exactly as it states
 * Cognito as the source of truth for new accounts. This event is the funnel's paid STEP — the thing
 * you can attribute back to a source and intersect with activation — and it is a FLOOR on paid, not
 * a count of it. A future story that wants a lossless number captures it server-side from the
 * Stripe webhook (`app/backend/routers/stripe.py`) keyed on the same email `identify()` uses.
 */
export function captureSubscriptionStarted(props: Record<string, unknown>): void {
  posthog.capture(FUNNEL_EVENTS.SUBSCRIPTION_STARTED, props)
}
