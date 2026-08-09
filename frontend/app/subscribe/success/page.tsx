"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Check, Loader2 } from "lucide-react"
import { Nav } from "@/components/nav"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"
import { forceRefreshTokens } from "@/lib/cognito"
import { getSubscriptionStatus } from "@/lib/subscription"
import { captureSubscriptionStarted } from "@/lib/funnel-telemetry-emit"

// Post-checkout landing. Stripe redirects here after a successful payment; the
// subscriber group is granted asynchronously by the webhook, so we poll the
// authoritative /subscription/status until access lands, then force-refresh the
// Cognito tokens so the new `subscriber` group is in the JWT before entering the app.
function SuccessInner() {
  const { accessToken, email, onLoginSuccess } = useAuth()
  const [ready, setReady] = useState(false)
  const [timedOut, setTimedOut] = useState(false)
  const cancelled = useRef(false)
  /** G100-D0 — one `subscription_started` per mount. See the capture site below. */
  const fired = useRef(false)

  useEffect(() => {
    cancelled.current = false
    let attempts = 0
    const MAX_ATTEMPTS = 12 // ~24s at 2s intervals

    async function poll() {
      if (cancelled.current) return
      attempts += 1
      try {
        const status = await getSubscriptionStatus(accessToken)
        if (status.has_access) {
          // ── G100-D0: the funnel's PAID step ────────────────────────────────────────────────
          //
          // ⭐ HERE, NOT ON PAGE LOAD. Landing on this route only means Stripe redirected; access
          // is granted asynchronously by the webhook, and this poll is the first moment anyone can
          // honestly say the person is a subscriber. Firing on mount would count a payment that
          // later failed to provision — and would fire again on every refresh of this URL, which a
          // confused user does exactly when provisioning is slow.
          //
          // ⚠️ It is inside the `has_access` branch and therefore INSIDE the `cancelled` guard's
          // blast radius by design: a tab closed mid-poll produces no event. See
          // `captureSubscriptionStarted` — this is a FLOOR on paid conversions, and the dashboard
          // names Stripe as the source of truth for the count.
          //
          // `fired` makes it once-per-mount: React 19 StrictMode double-invokes this effect in dev.
          if (!fired.current) {
            fired.current = true
            captureSubscriptionStarted({ attempts })
          }
          // Refresh tokens so the paywall gate (which reads JWT groups) lets us in.
          const tokens = await forceRefreshTokens()
          if (tokens) onLoginSuccess(tokens.accessToken, tokens.idToken)
          if (!cancelled.current) setReady(true)
          return
        }
      } catch {
        /* transient — keep polling */
      }
      if (attempts >= MAX_ATTEMPTS) {
        if (!cancelled.current) setTimedOut(true)
        return
      }
      setTimeout(poll, 2000)
    }

    if (accessToken) poll()
    return () => {
      cancelled.current = true
    }
  }, [accessToken, onLoginSuccess])

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <Nav authenticated={!!accessToken} userEmail={email} />
      <main className="mx-auto max-w-lg px-4 py-20 text-center">
        {ready ? (
          <>
            <Check className="mx-auto h-14 w-14 text-emerald-400" />
            <h1 className="mt-6 text-2xl font-bold">You&apos;re in. Welcome to Credence.</h1>
            <p className="mt-3 text-gray-400">
              Your membership is active. Head to the dashboard to see today&apos;s edge.
            </p>
            <Button
              asChild
              className="mt-8 bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
            >
              <Link href="/dashboard">Go to Dashboard</Link>
            </Button>
          </>
        ) : timedOut ? (
          <>
            <h1 className="text-2xl font-bold">Payment received — finishing setup</h1>
            <p className="mt-3 text-gray-400">
              Your payment went through. It can take a moment to activate. If access
              isn&apos;t live shortly, refresh this page or sign out and back in.
            </p>
            <Button
              asChild
              variant="outline"
              className="mt-8 border-[#262626] text-gray-200 hover:bg-[#141414]"
            >
              <Link href="/dashboard">Continue</Link>
            </Button>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-emerald-400" />
            <h1 className="mt-6 text-2xl font-bold">Confirming your membership…</h1>
            <p className="mt-3 text-gray-400">Just a moment while we activate your access.</p>
          </>
        )}
      </main>
    </div>
  )
}

export default function SubscribeSuccessPage() {
  return (
    <Suspense fallback={null}>
      <SuccessInner />
    </Suspense>
  )
}
