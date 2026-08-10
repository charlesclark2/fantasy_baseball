"use client"

import { useEffect, useRef } from "react"
import { useAuth } from "@/lib/auth-context"
import type { AcquisitionSurface } from "@/lib/funnel-telemetry"
import { captureLandingView } from "@/lib/funnel-telemetry-emit"

/**
 * G100-D0 — the funnel's FIRST step: a visitor reached an acquisition surface.
 *
 * Drop it on a page that a stranger can land on and get value from without an account. Renders
 * nothing.
 *
 * ══ WHY IT IS A COMPONENT AND NOT A PATHNAME REGEX ════════════════════════════════════════════
 *
 * `landing_view`'s population IS the denominator of visitor→signup, so what counts as an
 * acquisition surface is a product decision, not a routing detail. Putting it on the pages makes
 * that decision reviewable in a diff: adding a page to the top of the funnel is a visible line in
 * that page's file. A central regex over pathnames would make the same decision invisibly, and the
 * failure mode is silent in the direction that matters — a new public route quietly joining the
 * denominator depresses every rate below it with no code change anywhere near the funnel.
 *
 * ⛔ NOT ON `/subscribe` OR `/login`. Both are public, neither is acquisition: one is the
 * conversion surface and the other is a return path. Counting people who are already deep in the
 * funnel as fresh visitors is the cheapest way to manufacture a conversion problem that is not
 * there.
 *
 * ══ IT FIRES ON MOUNT, AND THE QUERY DEDUPES ══════════════════════════════════════════════════
 *
 * Deliberately unlike `custom_board_viewed`, which waits for the board to actually render. That
 * event is an ACTIVATION claim ("they saw their own board"), so a premature fire would be a false
 * claim. This one is an ARRIVAL claim, and someone who arrived at a page that then failed to load
 * did still arrive — that is a real visitor whose experience was bad, and hiding them would make a
 * broken page look like a traffic drop instead of a conversion drop.
 *
 * The once-per-mount ref stops React's dev-mode double-invoke and any re-render from multiplying a
 * single arrival. It is NOT a per-person dedupe and must not be mistaken for one: revisits are
 * expected and are collapsed by `count(DISTINCT person_id)` in the dashboard query, which is the
 * only layer that can see a person across sessions and devices.
 */
export function LandingView({ surface }: { surface: AcquisitionSurface }) {
  const fired = useRef(false)
  const { loading } = useAuth()

  useEffect(() => {
    // ⚠️ WAIT FOR THE SESSION TO RESOLVE. `landing_view` is the ONLY funnel event that can fire
    // before the auth provider has restored a session — every other step is downstream of one — and
    // `<FunnelTelemetry/>` cannot register `free_paid_status` until it knows whether there is a
    // session to describe. Firing on bare mount raced that: the E2E suite caught every
    // `landing_view` leaving with `free_paid_status: undefined`, which silently makes the top of
    // the funnel the one step that cannot be split by tier — so "do free accounts land here more
    // than subscribers?" would have been unanswerable, with nothing broken-looking anywhere.
    //
    // The restore is a local read (Cognito's own localStorage), not a network round trip, so this
    // costs one render and no meaningful arrivals.
    if (fired.current || loading) return
    fired.current = true
    captureLandingView(surface)
  }, [surface, loading])

  return null
}
