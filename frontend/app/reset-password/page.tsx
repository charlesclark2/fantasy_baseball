"use client"

import { Suspense, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Eye, EyeOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { getCognitoUser } from "@/lib/cognito"
import { Nav } from "@/components/nav"

function ResetPasswordInner() {
  const router       = useRouter()
  const searchParams = useSearchParams()

  const [email, setEmail]               = useState(searchParams.get("email") ?? "")
  const [code, setCode]                 = useState("")
  const [newPassword, setNewPassword]   = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading]       = useState(false)
  const [error, setError]               = useState<string | null>(null)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.")
      return
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }

    setIsLoading(true)
    const user = getCognitoUser(email.trim().toLowerCase())

    user.confirmPassword(code.trim(), newPassword, {
      onSuccess() {
        router.push("/login?reset=success")
      },
      onFailure(err) {
        setIsLoading(false)
        const msg = err.message ?? ""
        if (msg.includes("ExpiredCodeException") || msg.includes("expired")) {
          setError("That code has expired. Request a new one from the forgot-password page.")
        } else if (msg.includes("CodeMismatchException") || msg.includes("mismatch")) {
          setError("Incorrect code. Double-check the code in your email and try again.")
        } else if (msg.includes("InvalidPasswordException") || msg.includes("password")) {
          setError("Password doesn't meet requirements: min 8 characters, must include a number.")
        } else {
          setError(msg || "Something went wrong. Please try again.")
        }
      },
    })
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 flex items-center justify-center px-4">
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
              Set new password
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Enter the code from your email and choose a new password.
            </p>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-5">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

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
                onChange={e => setEmail(e.target.value)}
                disabled={isLoading}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="code">Reset code</Label>
              <Input
                id="code"
                type="text"
                inputMode="numeric"
                placeholder="123456"
                autoComplete="one-time-code"
                required
                value={code}
                onChange={e => setCode(e.target.value)}
                disabled={isLoading}
                autoFocus={!!email}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="new-password">New password</Label>
              <div className="relative">
                <Input
                  id="new-password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  required
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  disabled={isLoading}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm-password">Confirm new password</Label>
              <Input
                id="confirm-password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                disabled={isLoading}
              />
            </div>

            <Button
              type="submit"
              className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
              disabled={isLoading || !email || !code || !newPassword || !confirmPassword}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Resetting password...
                </>
              ) : (
                "Reset Password"
              )}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm">
            <Link
              href="/forgot-password"
              className="text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
            >
              Request a new code
            </Link>
            {" · "}
            <Link
              href="/login"
              className="text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
            >
              Back to sign in
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    }>
      <ResetPasswordInner />
    </Suspense>
  )
}
