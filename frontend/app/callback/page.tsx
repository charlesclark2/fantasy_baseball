"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { completeGoogleSignIn, consumePostSignInRedirect, consumeSignInContext } from "@/lib/cognito"
import { useAuth } from "@/lib/auth-context"
import { completeSignIn } from "@/lib/post-signin"

function CallbackInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { onLoginSuccess } = useAuth()
  const [error, setError] = useState<string | null>(null)
  // React 19 StrictMode double-invokes effects in dev; the auth code is
  // single-use, so guard against a second exchange attempt.
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true

    const code = searchParams.get("code")
    const state = searchParams.get("state")
    const oauthError = searchParams.get("error_description") ?? searchParams.get("error")

    if (oauthError) {
      setError("Google sign-in was cancelled or failed. Please try again.")
      return
    }
    if (!code || !state) {
      setError("Missing sign-in details. Please try again.")
      return
    }

    completeGoogleSignIn(code, state)
      .then(({ accessToken, idToken }) => {
        onLoginSuccess(accessToken, idToken)

        // E9.58d — close the funnel this round-trip opened.
        // `user_signed_in` is byte-identical for a new signup and a returning user, so on its
        // own it cannot answer the only question worth asking here: of the people who clicked
        // Sign Up, how many came back with a session? The intent is carried across the redirect
        // by the surface that knows it (see consumeSignInContext).
        //
        // G100-C0 — the four post-sign-in obligations (both funnel captures, verify-email, and
        // the E9.58b ToS record) moved verbatim into `completeSignIn` so the new email-OTP door
        // performs the identical set rather than a hand-copied subset of it.
        const ctx = consumeSignInContext()
        completeSignIn({
          accessToken,
          method: "google",
          intent: ctx?.intent ?? "unknown",
          surface: ctx?.surface ?? "unknown",
        })
        // E9.58 — return the visitor to whatever they were trying to reach (e.g. /subscribe),
        // not unconditionally to /dashboard, which silently dropped their buying intent.
        router.replace(consumePostSignInRedirect() ?? "/dashboard")
      })
      .catch((err) => {
        setError(err?.message ?? "Google sign-in failed. Please try again.")
      })
  }, [searchParams, onLoginSuccess, router])

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        <Image
          src="/brand/logo-wordmark.svg"
          alt="Credence Sports"
          width={160}
          height={28}
          className="h-7 w-auto mx-auto mb-6"
          priority
        />
        {error ? (
          <>
            <Alert variant="destructive" className="mb-5 text-left">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
            <Button asChild className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]">
              <Link href="/login">Back to sign in</Link>
            </Button>
          </>
        ) : (
          <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            Signing you in…
          </div>
        )}
      </div>
    </div>
  )
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    }>
      <CallbackInner />
    </Suspense>
  )
}
