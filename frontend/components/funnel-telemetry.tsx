"use client"

import { useEffect, useRef } from "react"
import { usePathname } from "next/navigation"
import posthog from "posthog-js"
import { useAuth } from "@/lib/auth-context"
import { registerFreePaidStatus, registerFunnelSuperProperties } from "@/lib/funnel-telemetry-emit"

/**
 * G100-D0 — the site-wide half of the funnel instrumentation. Renders nothing.
 *
 * Mounted once in `Providers`, so it runs on EVERY route. Three jobs, and each one exists because
 * the alternative loses data in a way that is invisible afterwards:
 *
 *  1. ATTRIBUTION ON EVERY PAGE, NOT ONLY ON "THE TOP OF THE FUNNEL". A campaign link can point
 *     anywhere — a player page, `/subscribe`, a shared board — and `register_once` only ever fires
 *     for the FIRST page of a visitor's first visit. Registering it only on the pages we happen to
 *     class as acquisition surfaces would silently record `direct` for precisely the traffic a
 *     campaign paid to send somewhere else.
 *
 *  2. IDENTITY STITCHING ON SESSION RESTORE, not only on an explicit login. `auth-context`
 *     identifies at `onLoginSuccess`, which covers the signup round-trip — the case D0 needs most,
 *     since it is what joins a visitor's ANONYMOUS `landing_view` to the account they then create.
 *     It does not cover a RETURNING visitor, whose session is restored from Cognito on mount with
 *     no login event at all. PostHog persists the identified id, so that visitor is usually still
 *     stitched — right up until they clear storage or open the product on a second device, at which
 *     point every event they produce lands on a fresh anonymous person and the funnel counts one
 *     human as two. Re-identifying on restore costs one call and closes it.
 *
 *  3. `free_paid_status` AS A SUPER PROPERTY, so every event carries it and any step of the funnel
 *     can be split by it — including the events fired by people who are not signed in, which is the
 *     majority of the top of the funnel.
 *
 * ⛔ IT DOES NOT FIRE `landing_view`. That is per-surface and belongs to the surfaces (see
 * `<LandingView/>`) — a single global emitter here would have to decide what counts as an
 * acquisition surface from a pathname, which puts the definition of the funnel's first step in a
 * regex instead of at the pages it describes.
 */
export function FunnelTelemetry() {
  const { accessToken, email, groups, loading } = useAuth()
  const identifiedRef = useRef<string | null>(null)
  const pathname = usePathname()

  // Attribution + device. `register_once` makes the repeat calls on later navigations no-ops for
  // the attribution half, which is exactly the first-touch semantics we want; device is re-read so
  // a rotated tablet or a resized window reports what the visitor is actually looking at now.
  useEffect(() => {
    registerFunnelSuperProperties()
  }, [pathname])

  useEffect(() => {
    // ⚠️ WAIT FOR `loading`. The provider starts every page with `accessToken: null` while it
    // restores the Cognito session, so registering on the first render would stamp `anonymous` onto
    // any event a signed-in visitor's page fires during that window — including a `landing_view`.
    if (loading) return

    registerFreePaidStatus(!!accessToken, groups)

    if (email && identifiedRef.current !== email) {
      identifiedRef.current = email
      // Same distinct_id as `auth-context` uses, deliberately: two identifiers for one human is the
      // stitching bug this call exists to prevent.
      posthog.identify(email, { email })
    }
    if (!email) identifiedRef.current = null
  }, [loading, accessToken, email, groups])

  return null
}
