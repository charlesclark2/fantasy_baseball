"use client"

import { useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { getCognitoUser } from "@/lib/cognito"
import { Nav } from "@/components/nav"

type Step = "request" | "sent"

export default function ForgotPasswordPage() {
  const [email, setEmail]   = useState("")
  const [step, setStep]     = useState<Step>("request")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    const user = getCognitoUser(email.trim().toLowerCase())

    user.forgotPassword({
      onSuccess() {
        setIsLoading(false)
        setStep("sent")
      },
      inputVerificationCode() {
        setIsLoading(false)
        setStep("sent")
      },
      onFailure(err) {
        setIsLoading(false)
        const msg = err.message ?? ""
        if (msg.includes("no registered/verified email") || msg.includes("email_verified")) {
          setError(
            "Your account email hasn't been verified yet. Contact the admin to verify your account before resetting your password.",
          )
        } else if (msg.includes("UserNotFoundException") || msg.includes("user does not exist")) {
          setError("No account found for that email address.")
        } else if (msg.includes("LimitExceededException")) {
          setError("Too many attempts. Please wait a few minutes and try again.")
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
              Reset your password
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {step === "request"
                ? "Enter your email and we'll send you a reset code."
                : "Check your email for a reset code."}
            </p>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-5">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {step === "request" ? (
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
                  autoFocus
                />
              </div>

              <Button
                type="submit"
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                disabled={isLoading || !email}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Sending code...
                  </>
                ) : (
                  "Send Reset Code"
                )}
              </Button>
            </form>
          ) : (
            <div className="space-y-4">
              <Alert className="border-[#10b981]/40 bg-[#10b981]/10">
                <AlertDescription className="text-[#10b981]">
                  A reset code was sent to <strong>{email}</strong>. Check your inbox
                  (and spam folder) and use the code below.
                </AlertDescription>
              </Alert>

              <Button
                className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
                asChild
              >
                <Link href={`/reset-password?email=${encodeURIComponent(email)}`}>
                  Enter reset code
                </Link>
              </Button>

              <p className="text-center text-sm text-muted-foreground">
                Didn&apos;t get an email?{" "}
                <button
                  type="button"
                  onClick={() => setStep("request")}
                  className="underline underline-offset-4 hover:text-foreground transition-colors"
                >
                  Try again
                </button>
              </p>
            </div>
          )}

          <p className="mt-6 text-center text-sm">
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
