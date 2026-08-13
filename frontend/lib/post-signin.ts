// G100-C0 — the work that must happen after ANY successful sign-in, in ONE place.
//
// WHY THIS IS A SHARED MODULE AND NOT COPIED INTO THE SECOND FLOW. Until now there was
// exactly one self-serve door (Google), so its four post-sign-in obligations lived inline
// in `app/callback/page.tsx` and nothing could drift. Adding email OTP means a second
// door, and a second inline copy is a second thing that has to remember all four:
//
//   1. `posthog.capture("user_signed_in")`   — the funnel's arrival event
//   2. `user_signup_completed` when this sign-in CREATED the account — the numerator of
//      G100-D0's R1. ⭐ G100-D0-R1 moved that condition from the client's stashed intent
//      to the server's answer; `reportSignupCompletion` below is where and why.
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
import { acceptTermsWithRetry, type TermsAcceptance } from "@/lib/terms"
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

  apiFetch("/auth/verify-email", { method: "POST" }, accessToken).catch(() => {})

  // ⭐ G100-D0-R1 — THE SIGNUP EVENT NOW RIDES ON THE ACCEPTANCE WRITE'S ANSWER, NOT ON THE
  // BUTTON. See `reportSignupCompletion`. The write was already happening on this exact line;
  // all that changed is that its result is read instead of discarded.
  //
  // ⚠️ THE CAPTURE IS NOW ASYNC, AND THAT IS SAFE HERE FOR ONE SPECIFIC REASON: every caller
  // follows this with a CLIENT-SIDE navigation (`router.replace` / `router.push`), which does
  // not tear the document down, so posthog-js's batcher survives to flush it. A caller that
  // ended in `window.location.href = …` would need `send_instantly`, the way the pre-redirect
  // start events already do.
  acceptTermsWithRetry(accessToken)
    .then((acceptance) => reportSignupCompletion(acceptance, { method, intent, surface }))
    // Both attempts failed ⇒ no signal at all ⇒ no event. Deliberately an UNDER-count: the
    // account still exists, `TermsGate` will collect the acceptance on the next authed render,
    // and this funnel step is documented as a floor.
    .catch(() => {})
}

/**
 * Emit `user_signup_completed` iff this sign-in actually created an account.
 *
 * ══ WHY THIS IS NOT KEYED ON THE BUTTON ANY MORE (G100-D0-R1) ═══════════════════════════════
 *
 * E9.58d keyed the event on `intent`, stashed by the surface that owned the button. That is the
 * only thing a CLIENT can know — and it is wrong in BOTH directions, because Google federation
 * auto-provisions an account at either door:
 *
 *   · a first-time visitor who clicks SIGN IN gets a brand-new account and emitted nothing, so
 *     R1's ordered funnel discarded them entirely — neither a signup nor a drop-off. Not a
 *     hypothetical: all 16 auth events in production's first 48h used the /login door.
 *   · a RETURNING user who clicks SIGN UP emitted a signup that never happened.
 *
 * The server already knows, and knows atomically: `/auth/accept-terms` writes with
 * `if_not_exists` and now reports whether THIS call was the first. Both directions are fixed by
 * the same signal, and fixing only one of them would leave the funnel wrong.
 *
 * ══ THE DEPLOY-SKEW FALLBACK IS NOT REDUNDANT ══════════════════════════════════════════════
 *
 * `known: false` means an old Lambda answered (frontend auto-deploys on merge to main; the API
 * ships only via `deploy.sh`). Falling back to the pre-R1 intent rule there keeps the window at
 * the OLD, already-understood behaviour instead of a flat zero — and a flat zero on step 2 of a
 * conversion funnel is read as a conversion collapse, which is the most expensive way this can
 * fail. ⛔ The fallback must never run when the server DID answer: `created: false` is
 * authoritative, and honouring the intent there would restore the false positive.
 */
function reportSignupCompletion(
  acceptance: TermsAcceptance,
  props: { method: SignInMethod; intent: SignInIntent | "unknown"; surface: string },
): void {
  const { method, intent, surface } = props

  if (acceptance.known) {
    if (acceptance.created) {
      // `signal` distinguishes the authoritative event from a skew-window one IN THE EVENT
      // ITSELF, so a funnel read during a deploy window is diagnosable rather than merely
      // suspicious. `intent` rides along so the two doors stay separable now that the event no
      // longer depends on which one was used — which is the whole finding this fixes.
      posthog.capture("user_signup_completed", { method, surface, intent, signal: "server" })
    }
    return
  }

  if (intent === "signup") {
    posthog.capture("user_signup_completed", { method, surface, intent, signal: "intent_fallback" })
  }
}
