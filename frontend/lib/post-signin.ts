// G100-C0 — the work that must happen after ANY successful sign-in, in ONE place.
//
// WHY THIS IS A SHARED MODULE AND NOT COPIED INTO THE SECOND FLOW. Until now there was
// exactly one self-serve door (Google), so its four post-sign-in obligations lived inline
// in `app/callback/page.tsx` and nothing could drift. Adding email OTP means a second
// door, and a second inline copy is a second thing that has to remember all four:
//
//   1. `posthog.capture("user_signed_in")`   — the funnel's arrival event
//   2. `user_signup_completed` when the intent was signup — the ONLY thing that pairs
//      1:1 with `user_signup_started`, and therefore the only thing that makes the
//      G100-D0 conversion rate computable at all
//   3. `POST /auth/verify-email`             — flips Cognito's `email_verified`
//   4. `acceptTermsWithRetry`                — E9.58b: since signup went public this is
//      the ONLY evidence a given account agreed to anything. It is EVIDENCE, not
//      telemetry, and a door that quietly skips it manufactures accounts with no
//      acceptance on file and nothing anywhere saying so.
//
// (3) and (4) are the dangerous ones to miss, because missing them is completely silent:
// the user signs in, the app works, and the gap only surfaces the day someone asks which
// terms an account accepted. A missed capture in (1)/(2) is merely a hole in the funnel
// this sprint exists to measure. So the second door calls this function rather than
// re-deriving the list — and `test_g100_c0_post_signin.spec` asserts that every sign-in
// surface routes through here, so a THIRD door cannot ship without them either.

import posthog from "posthog-js"
import { apiFetch } from "@/lib/api"
import { acceptTermsWithRetry } from "@/lib/terms"
import type { SignInIntent } from "@/lib/cognito"

export type SignInMethod = "google" | "email_otp" | "password"

export type CompleteSignInArgs = {
  accessToken: string
  /** Which door. Recorded on every event so the funnel breaks down per method — the
   *  whole reason G100-C0 exists is to find out whether the second door converts. */
  method: SignInMethod
  /** What the user was TRYING to do. "unknown" is honest and deliberate: guessing
   *  "signup" would report conversions that never happened, so an unknown intent can
   *  only ever UNDER-count. */
  intent: SignInIntent | "unknown"
  /** Which page the attempt started on (login / signup / subscribe / …). */
  surface: string
}

/**
 * Fire the four post-sign-in obligations. Never throws — a telemetry or Dynamo blip must
 * not strand a user who now holds a perfectly valid session on an error screen.
 *
 * ⚠️ (4) NOT THROWING HERE IS NOT THE SAME AS (4) BEING OPTIONAL. `acceptTermsWithRetry`
 * already retries once; if both attempts fail the user is stopped on the next authed
 * render by `TermsGate`, which cannot be dismissed until the write lands. That is the
 * guarantee — this call is the first attempt, not the safety net.
 */
export function completeSignIn({
  accessToken,
  method,
  intent,
  surface,
}: CompleteSignInArgs): void {
  posthog.capture("user_signed_in", { method, intent, surface })

  if (intent === "signup") {
    // ⚠️ SCOPE, carried verbatim from the Google flow so the two doors' events mean the
    // SAME thing and can be summed: this is "someone who clicked a SIGN-UP button now
    // has a session" — NOT "a new account was created". A returning user who clicked
    // Sign Up counts here. That is the right denominator for a funnel question and the
    // wrong one for counting accounts; for accounts, Cognito's creation dates are the
    // source of truth, not this event.
    posthog.capture("user_signup_completed", { method, surface })
  }

  apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})
  acceptTermsWithRetry(accessToken).catch(() => {})
}
