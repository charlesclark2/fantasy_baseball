"use client"

import { Suspense, useRef, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Eye, EyeOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { getCognitoUser, AuthenticationDetails } from "@/lib/cognito"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"
import { Nav } from "@/components/nav"
import type { CognitoUser } from "amazon-cognito-identity-js"

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
  const pendingUser = useRef<CognitoUser | null>(null)

  const { onLoginSuccess } = useAuth()

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
        apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
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

              <Button
                type="submit"
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                disabled={isLoading || newPassword.length < 8}
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
