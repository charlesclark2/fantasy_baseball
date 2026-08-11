"use client"

// G100-C0 — the email door, shared verbatim by /login and /signup.
//
// ONE component for both surfaces because they are the same three steps with different
// wording, and because the alternative — two copies — is how one of them ends up missing
// `completeSignIn` (the E9.58b ToS-evidence gap) or the funnel captures. What differs
// between the surfaces is passed in (`intent`, `surface`, headline copy); what must not
// differ is the flow, so the flow lives here.

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, Mail } from "lucide-react"
import posthog from "posthog-js"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { startEmailOtp, verifyEmailOtp } from "@/lib/email-otp"
import { completeSignIn } from "@/lib/post-signin"
import { useAuth } from "@/lib/auth-context"
import type { SignInIntent } from "@/lib/cognito"

type Step = "email" | "code" | "use-provider"

export type EmailOtpFormProps = {
  /** Which button the user pressed to get here. Drives the funnel pairing — an
   *  intent of "signup" is what emits `user_signup_completed` on success. */
  intent: SignInIntent
  /** Page this attempt started on ("login" / "signup"), recorded on every event. */
  surface: string
  /** Where to land after a successful sign-in (already sanitised by the caller). */
  dest: string
  /** Start the Google flow — offered when the address turns out to be a provider
   *  account, so the dead end has a working way out on the same screen. */
  onUseProvider?: () => void
}

export function EmailOtpForm({ intent, surface, dest, onUseProvider }: EmailOtpFormProps) {
  const router = useRouter()
  const { onLoginSuccess } = useAuth()

  const [step, setStep] = useState<Step>("email")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [session, setSession] = useState("")
  const [maskedEmail, setMaskedEmail] = useState("")
  const [provider, setProvider] = useState("Google")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function requestCode(e?: React.FormEvent) {
    e?.preventDefault()
    setError(null)
    setNotice(null)
    setIsLoading(true)

    // Pairs with `user_signup_completed` / `user_signed_in` from `completeSignIn`, and
    // carries the SAME `method` on both ends so the funnel can be read per door — which
    // is the entire question this story asks of G100-D0's instrumentation.
    //
    // No `send_instantly` here, unlike the Google buttons: nothing tears the document
    // down on this path (there is no redirect), so the ordinary batch delivers it.
    posthog.capture(intent === "signup" ? "user_signup_started" : "user_signin_started", {
      method: "email_otp",
      surface,
    })

    try {
      const result = await startEmailOtp(email.trim())
      if (result.next === "google") {
        setProvider(result.provider)
        setStep("use-provider")
        return
      }
      setSession(result.session)
      setMaskedEmail(result.maskedEmail)
      setCode("")
      setStep("code")
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "We couldn't send a code just now. Please try again.",
      )
    } finally {
      setIsLoading(false)
    }
  }

  async function submitCode(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)
    try {
      const { accessToken, idToken } = await verifyEmailOtp(email.trim(), code.trim(), session)
      onLoginSuccess(accessToken, idToken)
      completeSignIn({ accessToken, method: "email_otp", intent, surface })
      router.push(dest)
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "That code didn't work. Request a new one and try again.",
      )
      setIsLoading(false)
    }
    // No `finally` on the success path: the router push is in flight and clearing the
    // spinner here would flash an enabled form under the navigation.
  }

  async function resend() {
    setCode("")
    await requestCode()
    if (!error) setNotice("We've sent a new code.")
  }

  // ── This address belongs to a provider account ────────────────────────────────
  if (step === "use-provider") {
    return (
      <div className="space-y-4">
        <Alert>
          <AlertDescription>
            <span className="font-medium text-foreground">
              You already have an account with {provider}.
            </span>{" "}
            Continue with {provider} to sign in — it&apos;s the same account, with all your
            saved leagues and bets.
          </AlertDescription>
        </Alert>
        {onUseProvider && (
          <Button
            type="button"
            className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
            onClick={onUseProvider}
          >
            Continue with {provider}
          </Button>
        )}
        <button
          type="button"
          onClick={() => {
            setStep("email")
            setError(null)
          }}
          className="w-full text-center text-sm text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
        >
          Use a different email
        </button>
      </div>
    )
  }

  // ── Enter the code ────────────────────────────────────────────────────────────
  if (step === "code") {
    return (
      <form onSubmit={submitCode} className="space-y-4" noValidate>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {notice && !error && (
          <Alert className="border-[#10b981]/40 bg-[#10b981]/10">
            <AlertDescription className="text-[#10b981]">{notice}</AlertDescription>
          </Alert>
        )}

        <p className="text-sm text-muted-foreground">
          We sent a 6-digit code to{" "}
          <span className="text-foreground">{maskedEmail || "your email"}</span>. It expires
          in 15 minutes.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="otp-code">Sign-in code</Label>
          <Input
            id="otp-code"
            type="text"
            inputMode="numeric"
            // Lets iOS/Android offer the code straight from the notification — the single
            // biggest completion-rate lever on an OTP form.
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={6}
            placeholder="123456"
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            disabled={isLoading}
            className="text-center text-lg tracking-[0.4em] font-mono"
            autoFocus
          />
        </div>

        <Button
          type="submit"
          className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
          disabled={isLoading || code.length !== 6}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Verifying…
            </>
          ) : (
            "Verify & continue"
          )}
        </Button>

        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={resend}
            disabled={isLoading}
            className="text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors disabled:opacity-50"
          >
            Send a new code
          </button>
          <button
            type="button"
            onClick={() => {
              setStep("email")
              setError(null)
              setNotice(null)
            }}
            disabled={isLoading}
            className="text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors disabled:opacity-50"
          >
            Use a different email
          </button>
        </div>
      </form>
    )
  }

  // ── Enter the email ───────────────────────────────────────────────────────────
  return (
    <form onSubmit={requestCode} className="space-y-4" noValidate>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="otp-email">Email</Label>
        <Input
          id="otp-email"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={isLoading}
        />
      </div>

      <Button
        type="submit"
        variant="outline"
        className="w-full"
        disabled={isLoading || !email.includes("@")}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
        ) : (
          <Mail className="w-4 h-4 mr-2" />
        )}
        Email me a sign-in code
      </Button>

      <p className="text-center text-xs text-muted-foreground">
        No password needed — we&apos;ll send a one-time code.
      </p>
    </form>
  )
}
