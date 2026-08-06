"use client"

// E9.58 — the public signup page. Before this route existed, every "get an account" affordance in
// the product was a `mailto:charlie@credencesports.com`, so the funnel E9.56b opened up read:
// stranger lands on an indexed locked projection → clicks Subscribe → "email Charlie and wait".
//
// Google OAuth (Hosted UI + PKCE) already worked end-to-end and was verified live by E9.57; it was
// simply only reachable from /login, a page a person with no account has no reason to open. This
// page is that flow given a front door — and it carries `?next=`, so a visitor who came here from
// /subscribe is returned to /subscribe with a session rather than dumped on /dashboard having lost
// the thing they were trying to buy.
//
// ⛔ There is deliberately NO email/password form here. See `lib/access.ts`: the Cognito pool has
// no email auto-verification, so a self-registered password account can never confirm itself.

import { Suspense, useEffect, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2 } from "lucide-react"
import posthog from "posthog-js"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { GoogleIcon } from "@/components/google-icon"
import { Nav } from "@/components/nav"
import { startGoogleSignIn, isHostedUiConfigured, sanitizeInternalPath } from "@/lib/cognito"
import { REQUEST_ACCESS_MAILTO } from "@/lib/access"
import { useAuth } from "@/lib/auth-context"

function SignupInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { accessToken, loading } = useAuth()

  const [isRedirecting, setIsRedirecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Never NULL-out an existing session's intent: someone already signed in who lands on /signup
  // (a stale bookmark, the nav on a cached page) wants where they were going, not a second account.
  const next = sanitizeInternalPath(searchParams.get("next"))

  useEffect(() => {
    if (!loading && accessToken) router.replace(next ?? "/dashboard")
  }, [loading, accessToken, next, router])

  const googleEnabled = isHostedUiConfigured()

  function handleGoogleSignUp() {
    setError(null)
    setIsRedirecting(true)
    // `send_instantly` — a full-page redirect to Cognito follows, and a batched event still in
    // the queue when the document is torn down is lost. (E9.58c)
    posthog.capture(
      "user_signup_started",
      { method: "google", surface: "signup", next: next ?? null },
      { send_instantly: true },
    )
    // Full-page redirect out to Cognito → Google; control returns to /callback, so there is no
    // success path here to clear isRedirecting on.
    startGoogleSignIn(next).catch((err) => {
      setError(err?.message ?? "Could not start Google sign-up. Please try again.")
      setIsRedirecting(false)
    })
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <Image
              src="/brand/logo-wordmark.svg"
              alt="Credence Sports"
              width={160}
              height={28}
              className="h-7 w-auto mx-auto mb-2"
              priority
            />
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              Create your account
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Free to create. Subscribe whenever you&apos;re ready.
            </p>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-5">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {googleEnabled ? (
            <>
              <Button
                type="button"
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                onClick={handleGoogleSignUp}
                disabled={isRedirecting}
              >
                {isRedirecting ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <GoogleIcon className="w-4 h-4 mr-2" />
                )}
                Continue with Google
              </Button>

              {/* Clickwrap. The acceptance itself is recorded server-side on the callback via the
                  existing POST /auth/accept-terms (reused, not re-invented — E9.58 scope item 4). */}
              <p className="mt-4 text-center text-xs text-muted-foreground leading-relaxed">
                By continuing you agree to our{" "}
                <Link href="/terms" className="underline underline-offset-4 hover:text-foreground transition-colors">
                  Terms
                </Link>{" "}
                and{" "}
                <Link href="/privacy" className="underline underline-offset-4 hover:text-foreground transition-colors">
                  Privacy Policy
                </Link>
                .
              </p>
            </>
          ) : (
            // Hosted UI unconfigured (NEXT_PUBLIC_COGNITO_HOSTED_UI_DOMAIN unset — a preview
            // deploy or a local shell). "Continue with Google" cannot work there, and a button
            // that silently does nothing is worse than the old mailto. Prod has it set.
            <>
              <Button variant="outline" className="w-full" asChild>
                <a href={REQUEST_ACCESS_MAILTO}>Request access by email</a>
              </Button>
              <p className="mt-4 text-center text-xs text-muted-foreground leading-relaxed">
                Sign-up with Google isn&apos;t available in this environment.
              </p>
            </>
          )}

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link
              href="/login"
              className="text-foreground underline underline-offset-4 hover:text-[#10b981] transition-colors"
            >
              Sign in
            </Link>
          </p>

          <p className="mt-6 border-t border-[#262626] pt-6 text-center text-xs text-muted-foreground leading-relaxed">
            Just looking? Every past season — and{" "}
            <Link href="/fantasy/track-record" className="text-[#10b981] hover:underline">
              how these projections actually did
            </Link>{" "}
            — is free, no account needed.
          </p>
        </div>
      </main>
    </div>
  )
}

export default function SignupPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background flex items-center justify-center">
          <span className="text-sm text-muted-foreground">Loading…</span>
        </div>
      }
    >
      <SignupInner />
    </Suspense>
  )
}
