"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Eye, EyeOff, Loader2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"

// ---------------------------------------------------------------------------
// Nav — matches landing page style, replaces CTA buttons with Back link
// ---------------------------------------------------------------------------
function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link
          href="/"
          className="flex items-center gap-0 text-lg font-bold tracking-tight"
        >
          <span className="text-[#10b981]">Credence</span>
          <span className="text-white"> Sports</span>
        </Link>

        <Button
          variant="ghost"
          size="sm"
          asChild
          className="text-gray-400 hover:text-white hover:bg-[#141414]"
        >
          <Link href="/">Back to home</Link>
        </Button>
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Login card
// ---------------------------------------------------------------------------
function LoginCard() {
  const router = useRouter()

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    // Stub auth — replace with Cognito Hosted UI in A0.4
    await new Promise((resolve) => setTimeout(resolve, 1500))

    // Simulate: any non-empty email + password succeeds
    if (email.trim() && password) {
      router.push("/dashboard")
    } else {
      setPassword("")
      setError("Invalid email or password. Please try again.")
    }

    setLoading(false)
  }

  return (
    <div className="w-full max-w-md rounded-xl border border-[#262626] bg-[#141414] shadow-2xl shadow-black/60 p-8">
      {/* Card wordmark */}
      <div className="mb-6 text-center">
        <span className="text-base font-bold">
          <span className="text-[#10b981]">Credence</span>
          <span className="text-white"> Sports</span>
        </span>
      </div>

      <h1 className="text-2xl font-bold tracking-tight text-white">
        Welcome back
      </h1>
      <p className="mt-1 text-sm text-gray-500">
        Sign in to your account to see every pick.
      </p>

      <form onSubmit={handleSubmit} noValidate className="mt-6 flex flex-col gap-4">
        {/* Email */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email" className="text-sm text-gray-300">
            Email
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            required
            className="border-[#262626] bg-[#0a0a0a] text-white placeholder:text-gray-600 focus-visible:ring-[#10b981]/40 focus-visible:border-[#10b981]/60"
          />
        </div>

        {/* Password */}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password" className="text-sm text-gray-300">
            Password
          </Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
              className="border-[#262626] bg-[#0a0a0a] text-white placeholder:text-gray-600 focus-visible:ring-[#10b981]/40 focus-visible:border-[#10b981]/60 pr-10"
            />
            <button
              type="button"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((v) => !v)}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-gray-500 hover:text-gray-300 transition-colors"
              tabIndex={-1}
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>

        {/* Inline error */}
        {error && (
          <Alert variant="destructive" className="border-red-900/50 bg-red-950/40">
            <AlertDescription className="text-sm text-red-400">
              {error}
            </AlertDescription>
          </Alert>
        )}

        {/* Sign in button */}
        <Button
          type="submit"
          disabled={loading}
          className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] disabled:opacity-60"
        >
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Signing in...
            </>
          ) : (
            "Sign In"
          )}
        </Button>

        {/* Forgot password */}
        <div className="flex justify-end">
          <Link
            href="/forgot-password"
            className="text-xs text-gray-500 hover:text-gray-300 underline-offset-4 hover:underline transition-colors"
          >
            Forgot password?
          </Link>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <Separator className="flex-1 bg-[#262626]" />
          <span className="text-xs text-gray-600">or</span>
          <Separator className="flex-1 bg-[#262626]" />
        </div>

        {/* Beta access */}
        <Button
          type="button"
          variant="outline"
          asChild
          className="w-full border-[#262626] bg-transparent text-gray-300 hover:bg-[#1a1a1a] hover:text-white"
        >
          <a href="mailto:hello@credencesports.com">Request Beta Access</a>
        </Button>
      </form>

      {/* Disclaimer */}
      <p className="mt-6 text-[11px] leading-relaxed text-gray-600">
        Picks are informational only and do not constitute financial advice. You
        are solely responsible for any wagers placed.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Navbar />
      <main className="flex min-h-[calc(100vh-65px)] items-center justify-center px-4 py-12">
        <LoginCard />
      </main>
    </div>
  )
}
