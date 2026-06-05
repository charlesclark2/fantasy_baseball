"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Eye, EyeOff, ChevronLeft, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription } from "@/components/ui/alert"

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    // TODO: replace with real auth call
    await new Promise((resolve) => setTimeout(resolve, 1200))

    // Stub: treat any login as success for now
    if (email && password) {
      router.push("/dashboard")
    } else {
      setError("Invalid email or password. Please try again.")
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Nav */}
      <header className="h-14 flex items-center px-6 border-b border-border">
        <Link
          href="/"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Back to home
        </Link>
        <span className="mx-auto font-semibold tracking-tight text-foreground">
          Credence Sports
        </span>
        {/* spacer to balance the back link */}
        <span className="w-24" aria-hidden />
      </header>

      {/* Card */}
      <main className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-sm">
          {/* Wordmark + heading */}
          <div className="text-center mb-8">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">
              Credence Sports
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              Welcome back
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Sign in to your account to view today&apos;s picks
            </p>
          </div>

          {/* Error alert */}
          {error && (
            <Alert variant="destructive" className="mb-5">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Form */}
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
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
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

          {/* Forgot password */}
          <p className="mt-4 text-center text-sm">
            <Link
              href="/forgot-password"
              className="text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
            >
              Forgot your password?
            </Link>
          </p>

          <Separator className="my-6" />

          {/* Request access */}
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
        </div>
      </main>
    </div>
  )
}
