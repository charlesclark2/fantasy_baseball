"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2 } from "lucide-react"
import posthog from "posthog-js"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { completeGoogleSignIn } from "@/lib/cognito"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"

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
        posthog.capture("user_signed_in", { method: "google" })
        // Parity with password login: verify the federated user's email server-side.
        apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
        router.replace("/dashboard")
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
