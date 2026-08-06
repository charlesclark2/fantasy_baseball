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
import { getCognitoUser, AuthenticationDetails, startGoogleSignIn, isHostedUiConfigured, setSessionAuthMethod, sanitizeInternalPath } from "@/lib/cognito"
import { useAuth } from "@/lib/auth-context"
import { signupHref } from "@/lib/access"
import { apiFetch } from "@/lib/api"
import { Nav } from "@/components/nav"
import { GoogleIcon } from "@/components/google-icon"
import type { CognitoUser } from "amazon-cognito-identity-js"

function LoginInner() {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const didReset     = searchParams.get("reset") === "success"

  // E9.58 — honour `?next=` symmetrically with /signup. A visitor who reached the paywall, clicked
  // through to /subscribe and then chose "I already have an account" was landed on /dashboard,
  // silently losing what they were trying to buy. Sanitised: this value comes from a query string,
  // so anything that could leave the origin would be an open redirect on the auth path.
  const next = sanitizeInternalPath(searchParams.get("next"))
  const dest = next ?? "/dashboard"

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // New-password-required step
  const [step, setStep] = useState<"login" | "new-password" | "mfa">("login")
  const [newPassword, setNewPassword] = useState("")
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const pendingUser = useRef<CognitoUser | null>(null)

  // TOTP MFA challenge step (SOFTWARE_TOKEN_MFA)
  const [mfaCode, setMfaCode] = useState("")

  const { onLoginSuccess } = useAuth()

  const googleEnabled = isHostedUiConfigured()

  function handleGoogleSignIn() {
    setError(null)
    setIsLoading(true)
    // `send_instantly` — same redirect-teardown loss as the signup surfaces (E9.58c).
    posthog.capture(
      "user_signin_started",
      { method: "google", surface: "login" },
      { send_instantly: true },
    )
    // Full-page redirect to the Cognito Hosted UI → Google. Control returns to
    // /callback, so no need to clear isLoading here.
    startGoogleSignIn(next, { intent: "signin", surface: "login" }).catch((err) => {
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
        setSessionAuthMethod("password")
        onLoginSuccess(accessToken, idToken)
        posthog.capture("user_signed_in", { method: "password" })
        apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
        router.push(dest)
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
      // TOTP MFA (E9.19) — only the password/InitiateAuth path issues this challenge;
      // Google Hosted-UI logins are MFA'd by Google and never reach here.
      totpRequired() {
        pendingUser.current = cognitoUser
        setMfaCode("")
        setIsLoading(false)
        setStep("mfa")
      },
    })
  }

  function handleMfaCode(e: React.FormEvent) {
    e.preventDefault()
    if (!pendingUser.current) return
    setError(null)
    setIsLoading(true)

    pendingUser.current.sendMFACode(
      mfaCode.trim(),
      {
        onSuccess(session) {
          const accessToken = session.getAccessToken().getJwtToken()
          const idToken     = session.getIdToken().getJwtToken()
          setSessionAuthMethod("password")
          onLoginSuccess(accessToken, idToken)
          posthog.capture("user_signed_in", { method: "password", mfa: true })
          apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
          router.push(dest)
        },
        onFailure(err) {
          setError(
            /CodeMismatch|invalid|not match/i.test(err.message ?? "")
              ? "That code didn't match. Check your authenticator app and try again."
              : /expired/i.test(err.message ?? "")
              ? "That code expired. Enter the current code from your authenticator app."
              : err.message ?? "Could not verify the code. Please try again.",
          )
          setIsLoading(false)
        },
      },
      "SOFTWARE_TOKEN_MFA",
    )
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
        setSessionAuthMethod("password")
        onLoginSuccess(accessToken, idToken)
        posthog.capture("user_set_initial_password")
        apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
        apiFetch("/auth/accept-terms", { method: "POST" }, accessToken).catch(() => {})
        router.push(dest)
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
                {/* E9.56c — was "Sign in to your account to view today's picks". That was written
                    when MLB picks were the whole product; a visitor now arrives here from an NFL
                    fantasy paywall as often as from the dashboard, and being told the site is about
                    "today's picks" reads as though they followed the wrong link. */}
                <p className="mt-1 text-sm text-muted-foreground">
                  Sign in to your account
                </p>
              </>
            ) : step === "mfa" ? (
              <>
                <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                  Two-factor verification
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Enter the 6-digit code from your authenticator app
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
          ) : step === "mfa" ? (
            <form onSubmit={handleMfaCode} className="space-y-4" noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="mfa-code">Authentication code</Label>
                <Input
                  id="mfa-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="123456"
                  required
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  disabled={isLoading}
                  className="text-center text-lg tracking-[0.4em] font-mono"
                  autoFocus
                />
              </div>

              <Button
                type="submit"
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                disabled={isLoading || mfaCode.length !== 6}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  "Verify & Sign In"
                )}
              </Button>

              <button
                type="button"
                onClick={() => { setStep("login"); setError(null); setMfaCode(""); setPassword("") }}
                disabled={isLoading}
                className="w-full text-center text-sm text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors disabled:opacity-50"
              >
                Back to sign in
              </button>
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

              {/* E9.56c pointed this at a `mailto:` (it had been `/request-access`, a route that
                  never existed — a 404 behind the one "I have no account" button on the page).
                  E9.58 makes it a real destination: signup is self-serve via Google. */}
              <Button variant="outline" className="w-full" asChild>
                <Link href={signupHref(next ?? undefined)}>Create an account</Link>
              </Button>

              {/* E9.56b/c — the way OUT for a visitor who hit this page from a locked 2026
                  projection, has no account, and would otherwise be stuck at a sign-in wall with
                  nothing to do. Past seasons and the track record are genuinely free and need no
                  account, so say so here rather than letting the login page be a dead end. */}
              <p className="mt-4 text-center text-xs text-muted-foreground leading-relaxed">
                No account yet? Every past season is free to browse — see the{" "}
                <Link
                  href="/fantasy/track-record"
                  className="underline underline-offset-4 hover:text-foreground transition-colors"
                >
                  fantasy track record
                </Link>{" "}
                without signing in.
              </p>

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
