"use client"

import { Suspense, useRef, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Eye, EyeOff, Loader2 } from "lucide-react"
import posthog from "posthog-js"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { getCognitoUser, AuthenticationDetails, startGoogleSignIn, isHostedUiConfigured } from "@/lib/cognito"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"
import { Nav } from "@/components/nav"
import type { CognitoUser } from "amazon-cognito-identity-js"

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.15-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
      <path fill="#FBBC05" d="M5.85 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.67-2.84Z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.67 2.84C6.71 7.31 9.14 5.38 12 5.38Z" />
    </svg>
  )
}

function LoginInner() {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const didReset     = searchParams.get("reset") === "success"

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // New-password-required step
  const [step, setStep] = useState<"login" | "new-password">("login")
  const [newPassword, setNewPassword] = useState("")
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const pendingUser = useRef<CognitoUser | null>(null)

  const { onLoginSuccess } = useAuth()

  const googleEnabled = isHostedUiConfigured()

  function handleGoogleSignIn() {
    setError(null)
    setIsLoading(true)
    posthog.capture("user_signin_started", { method: "google" })
    // Full-page redirect to the Cognito Hosted UI → Google. Control returns to
    // /callback, so no need to clear isLoading here.
    startGoogleSignIn().catch((err) => {
      setError(err?.message ?? "Could not start Google sign-in. Please try again.")
      setIsLoading(false)
    })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    const authDetails = new AuthenticationDetails({ Username: email, Password: password })
    const cognitoUser = getCognitoUser(email)

    cognitoUser.authenticateUser(authDetails, {
      onSuccess(session) {
        const accessToken = session.getAccessToken().getJwtToken()
        const idToken     = session.getIdToken().getJwtToken()
        onLoginSuccess(accessToken, idToken)
        posthog.capture("user_signed_in", { method: "password" })
        apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
        router.push("/dashboard")
      },
      onFailure(err) {
        setError(err.message ?? "Invalid email or password. Please try again.")
        setIsLoading(false)
      },
      newPasswordRequired() {
        pendingUser.current = cognitoUser
        setIsLoading(false)
        setStep("new-password")
      },
    })
  }

  function handleNewPassword(e: React.FormEvent) {
    e.preventDefault()
    if (!pendingUser.current) return
    setError(null)
    setIsLoading(true)

    pendingUser.current.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess(session) {
        const accessToken = session.getAccessToken().getJwtToken()
        const idToken     = session.getIdToken().getJwtToken()
        onLoginSuccess(accessToken, idToken)
        posthog.capture("user_set_initial_password")
        apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
        apiFetch("/auth/accept-terms", { method: "POST" }, accessToken).catch(() => {})
        router.push("/dashboard")
      },
      onFailure(err) {
        setError(err.message ?? "Could not set new password. Please try again.")
        setIsLoading(false)
      },
    })
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Nav */}
      <Nav />

      {/* Card */}
      <main className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-sm">
          {/* Wordmark + heading */}
          <div className="text-center mb-8">
            <Image
              src="/brand/logo-wordmark.svg"
              alt="Credence Sports"
              width={160}
              height={28}
              className="h-7 w-auto mx-auto mb-2"
              priority
            />
            {step === "login" ? (
              <>
                <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                  Welcome back
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Sign in to your account to view today&apos;s picks
                </p>
              </>
            ) : (
              <>
                <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                  Set your password
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose a permanent password for your account
                </p>
              </>
            )}
          </div>

          {/* Password-reset success banner */}
          {didReset && (
            <Alert className="mb-5 border-[#10b981]/40 bg-[#10b981]/10">
              <AlertDescription className="text-[#10b981]">
                Password reset successfully. Sign in with your new password below.
              </AlertDescription>
            </Alert>
          )}

          {/* Error alert */}
          {error && (
            <Alert variant="destructive" className="mb-5">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {step === "login" && googleEnabled && (
            <>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={handleGoogleSignIn}
                disabled={isLoading}
              >
                <GoogleIcon className="w-4 h-4 mr-2" />
                Continue with Google
              </Button>

              <div className="my-5 flex items-center gap-3">
                <Separator className="flex-1" />
                <span className="text-xs text-muted-foreground">or</span>
                <Separator className="flex-1" />
              </div>
            </>
          )}

          {step === "login" ? (
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isLoading}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign In"
                )}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleNewPassword} className="space-y-4" noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="new-password">New password</Label>
                <div className="relative">
                  <Input
                    id="new-password"
                    type={showNewPassword ? "text" : "password"}
                    placeholder="••••••••"
                    autoComplete="new-password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    disabled={isLoading}
                    className="pr-10"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword((v) => !v)}
                    aria-label={showNewPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    tabIndex={-1}
                  >
                    {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-start gap-2.5 pt-1">
                <input
                  id="agree-terms"
                  type="checkbox"
                  checked={agreedToTerms}
                  onChange={(e) => setAgreedToTerms(e.target.checked)}
                  disabled={isLoading}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border border-input accent-[#10b981] cursor-pointer"
                />
                <label htmlFor="agree-terms" className="text-xs text-muted-foreground leading-snug cursor-pointer">
                  I agree to the{" "}
                  <Link href="/terms" className="underline underline-offset-2 hover:text-foreground transition-colors">
                    Terms of Service
                  </Link>{" "}
                  and{" "}
                  <Link href="/privacy" className="underline underline-offset-2 hover:text-foreground transition-colors">
                    Privacy Policy
                  </Link>
                </label>
              </div>

              <Button
                type="submit"
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                disabled={isLoading || newPassword.length < 8 || !agreedToTerms}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Setting password...
                  </>
                ) : (
                  "Set Password & Sign In"
                )}
              </Button>
            </form>
          )}

          {step === "login" && (
            <>
              <p className="mt-4 text-center text-sm">
                <Link
                  href="/forgot-password"
                  className="text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
                >
                  Forgot your password?
                </Link>
              </p>

              <Separator className="my-6" />

              <Button variant="outline" className="w-full" asChild>
                <Link href="/request-access">Request Beta Access</Link>
              </Button>

              <p className="mt-4 text-center text-xs text-muted-foreground leading-relaxed">
                By signing in you agree to our{" "}
                <Link
                  href="/terms"
                  className="underline underline-offset-4 hover:text-foreground transition-colors"
                >
                  Terms of Service
                </Link>{" "}
                and{" "}
                <Link
                  href="/privacy"
                  className="underline underline-offset-4 hover:text-foreground transition-colors"
                >
                  Privacy Policy
                </Link>
                .
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    }>
      <LoginInner />
    </Suspense>
  )
}
