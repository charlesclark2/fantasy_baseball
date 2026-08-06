"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { Check, Loader2 } from "lucide-react"
import { Nav } from "@/components/nav"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useAuth } from "@/lib/auth-context"
import { signupHref } from "@/lib/access"
import { startGoogleSignIn, isHostedUiConfigured } from "@/lib/cognito"
import { GoogleIcon } from "@/components/google-icon"
import {
  getSubscriptionPricing,
  getSubscriptionStatus,
  openBillingPortal,
  startCheckout,
} from "@/lib/subscription"

// E9.56c — the NFL line was missing entirely. Every locked 2026 projection and ranking now sends
// free visitors here, so the single largest inbound cohort was landing on a list of five MLB
// betting features with no mention of the fantasy product they had just been paywalled out of.
const PERKS = [
  "Full 2026 NFL fantasy projections, rankings & draft tools",
  "Daily model picks across every MLB slate",
  "Full EV tracker + line-movement history",
  "Pitcher strikeout projections & prop edges",
  "Team & player research surfaces",
  "Model-vs-market performance scorecards",
]

function PerkList() {
  return (
    <ul className="mt-6 space-y-2">
      {PERKS.map((perk) => (
        <li key={perk} className="flex items-start gap-2 text-sm text-gray-300">
          <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
          {perk}
        </li>
      ))}
    </ul>
  )
}

function fmtUsd(cents: number): string {
  const dollars = cents / 100
  return Number.isInteger(dollars) ? `$${dollars}` : `$${dollars.toFixed(2)}`
}

export default function SubscribePage() {
  const { accessToken, email, loading } = useAuth()
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const signedIn = !!accessToken

  const status = useQuery({
    queryKey: ["subscription-status"],
    queryFn: () => getSubscriptionStatus(accessToken),
    enabled: signedIn,
  })

  const pricing = useQuery({
    queryKey: ["subscription-pricing"],
    queryFn: () => getSubscriptionPricing(accessToken),
    enabled: signedIn,
  })

  // E9.58 — signup, in place, on the page every padlock points at. Returning to `/subscribe`
  // (rather than the callback's default /dashboard) is the whole point: this visitor arrived
  // holding a buying intent, and dropping them on a dashboard discards it.
  const googleEnabled = isHostedUiConfigured()

  function handleGoogleSignUp() {
    setError(null)
    setBusy(true)
    startGoogleSignIn("/subscribe").catch(() => {
      setError("Could not start Google sign-up. Please try again.")
      setBusy(false)
    })
  }

  async function handleSubscribe() {
    setError(null)
    setBusy(true)
    try {
      await startCheckout(accessToken) // full-page redirect to Stripe Checkout
    } catch {
      setError("Could not start checkout. Please try again in a moment.")
      setBusy(false)
    }
  }

  async function handleManage() {
    setError(null)
    setBusy(true)
    try {
      await openBillingPortal(accessToken)
    } catch {
      setError("Could not open the billing portal. Please try again.")
      setBusy(false)
    }
  }

  const hasAccess = status.data?.has_access
  const tier = status.data?.tier

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <Nav authenticated={signedIn} userEmail={email} />

      <main className="mx-auto max-w-2xl px-4 py-16">
        <div className="text-center">
          <h1 className="text-3xl font-bold sm:text-4xl">Credence Sports Membership</h1>
          <p className="mt-3 text-gray-400">
            Bayesian sports analytics. Daily edge, quantified.
          </p>
        </div>

        {error && (
          <Alert variant="destructive" className="mt-8">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* 🚨 E9.56c — THE DEAD END. This block used to be one line, "Sign in to start your
            membership.", and a single Sign In button.
            E9.56b made every locked 2026 projection link here, so the dominant visitor is now
            someone who has never heard of us, has no account, and cannot get one from this page:
            "sign in" presumes an account they do not have, and the only real sign-up path (the
            mailto below) appeared nowhere. It also showed them nothing about what they would be
            buying — the perks list was rendered only INSIDE the signed-in checkout branch, i.e.
            only to people who had already committed enough to have an account.
            ⚠️ The price genuinely cannot be shown here yet: `/subscription/pricing` requires auth,
            so a logged-out fetch 401s. Making it public is a backend + API-Gateway-route change
            (see the E9.56c handoff) — deliberately not smuggled into a frontend fix. */}
        {!loading && !signedIn && (
          <div className="mt-10 rounded-xl border border-[#262626] bg-[#0f0f0f] p-8">
            <h2 className="text-lg font-semibold">What a membership includes</h2>
            <PerkList />

            <div className="mt-8 space-y-3">
              {googleEnabled ? (
                <Button
                  onClick={handleGoogleSignUp}
                  disabled={busy}
                  className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                >
                  {busy ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <GoogleIcon className="mr-2 h-4 w-4" />
                  )}
                  Continue with Google
                </Button>
              ) : (
                <Button
                  asChild
                  className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                >
                  <Link href={signupHref("/subscribe")}>Create an account</Link>
                </Button>
              )}
              <Button
                asChild
                variant="outline"
                className="w-full border-[#262626] text-gray-200 hover:bg-[#141414]"
              >
                <Link href="/login?next=%2Fsubscribe">I already have an account</Link>
              </Button>
            </div>

            {/* E9.58 — this used to explain that there was no "create account" button
                ("Credence is invite-only while we finish building"). There is one now, and the
                honest-holding-pattern copy would read as a contradiction beside it. */}
            <p className="mt-4 text-center text-xs text-gray-500">
              Free to create an account. By continuing you agree to our{" "}
              <Link href="/terms" className="underline underline-offset-4 hover:text-gray-300">
                Terms
              </Link>{" "}
              and{" "}
              <Link href="/privacy" className="underline underline-offset-4 hover:text-gray-300">
                Privacy Policy
              </Link>
              .
            </p>

            <p className="mt-5 border-t border-[#262626] pt-5 text-center text-xs text-gray-500">
              Just looking? Every past season — and{" "}
              <Link
                href="/fantasy/track-record"
                className="text-[#10b981] hover:underline"
              >
                how these projections actually did
              </Link>{" "}
              — is free, no account needed.
            </p>
          </div>
        )}

        {/* Already has access — beta testers & existing subscribers never see checkout */}
        {signedIn && hasAccess && (
          <div className="mt-10 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-8 text-center">
            <Check className="mx-auto h-10 w-10 text-emerald-400" />
            <h2 className="mt-4 text-xl font-semibold">
              {tier === "beta_tester"
                ? "You're a beta member — full access, on the house."
                : "Your membership is active."}
            </h2>
            <p className="mt-2 text-sm text-gray-400">
              {tier === "beta_tester"
                ? "No payment needed. Thanks for helping us build."
                : "Thanks for being a member."}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Button asChild className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]">
                <Link href="/dashboard">Go to Dashboard</Link>
              </Button>
              {status.data?.has_billing && (
                <Button
                  variant="outline"
                  onClick={handleManage}
                  disabled={busy}
                  className="border-[#262626] text-gray-200 hover:bg-[#141414]"
                >
                  {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Manage billing
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Checkout offer — free / churned users */}
        {signedIn && status.isSuccess && !hasAccess && (
          <div className="mt-10 rounded-xl border border-[#262626] bg-[#0f0f0f] p-8">
            {pricing.data?.founding_available && (
              <div className="mb-4 inline-block rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-400">
                Founding member rate — locked in for life
              </div>
            )}
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-bold">
                {pricing.data ? fmtUsd(pricing.data.unit_amount) : "—"}
              </span>
              <span className="text-gray-400">/ month</span>
            </div>
            {pricing.data?.founding_available && (
              <p className="mt-2 text-sm text-amber-400/80">
                First {pricing.data.founding_cap} members lock in this rate permanently.
              </p>
            )}

            <PerkList />

            <Button
              onClick={handleSubscribe}
              disabled={busy || !pricing.data}
              className="mt-8 w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
            >
              {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Subscribe
            </Button>
            <p className="mt-3 text-center text-xs text-gray-500">
              Secure checkout by Stripe · monthly · cancel anytime
            </p>
          </div>
        )}

        {(loading || (signedIn && (status.isLoading || pricing.isLoading))) && (
          <div className="mt-10 flex justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-gray-500" />
          </div>
        )}
      </main>
    </div>
  )
}
