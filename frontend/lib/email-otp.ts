// G100-C0 — client for the passwordless email sign-in routes.
//
// Both legs go through our API rather than talking to Cognito from the browser. See
// `app/backend/routers/email_otp.py` for why (browser-direct CUSTOM_AUTH would let any
// caller make Cognito email a code to any address we hold a user for). The upshot here
// is pleasant: this file has no Cognito SDK in it at all, just two POSTs and the shared
// hydration step that puts the returned tokens exactly where every other session lives.

import { apiFetch } from "@/lib/api"
import { hydrateSessionFromTokens } from "@/lib/cognito"

/** What `/start` decided this address should do. */
export type OtpStartResult =
  /** A code is on its way. Carry `session` to `verifyEmailOtp` unchanged. */
  | { next: "otp"; maskedEmail: string; session: string }
  /** This address already signs in with a provider — show that button instead. Sending
   *  a code would either strand them at an empty inbox or split their account in two.
   *  See `app/backend/services/identity.py`. */
  | { next: "google"; maskedEmail: string; provider: string }

export async function startEmailOtp(email: string): Promise<OtpStartResult> {
  const res = await apiFetch("/auth/email-otp/start", {
    method: "POST",
    body: JSON.stringify({ email }),
  })

  // ⚠️ Read `next` defensively and treat anything unrecognised as the OTP path only when
  // a session actually came back. The API Lambda has no CD (it ships via deploy.sh while
  // this file auto-deploys on merge), so a skew window is guaranteed; the failure that
  // must not happen is showing a code field for a response that carried no session, which
  // presents as a code that is never accepted rather than as an error (NF-C0).
  if (res?.next === "google") {
    return {
      next: "google",
      maskedEmail: res?.masked_email ?? "",
      provider: res?.provider ?? "Google",
    }
  }
  if (!res?.session) {
    throw new Error("We couldn't start sign-in just now. Please try again.")
  }
  return { next: "otp", maskedEmail: res?.masked_email ?? "", session: res.session }
}

/**
 * Answer the challenge and install the session.
 *
 * On success the tokens are hydrated into the SAME `amazon-cognito-identity-js`
 * localStorage layout a Google sign-in uses, stamped `email_otp`, so silent refresh, the
 * proactive renewal timer, the 401 retry and sign-out all work with no OTP-specific code
 * anywhere downstream.
 */
export async function verifyEmailOtp(
  email: string,
  code: string,
  session: string,
): Promise<{ accessToken: string; idToken: string }> {
  const res = await apiFetch("/auth/email-otp/verify", {
    method: "POST",
    body: JSON.stringify({ email, code, session }),
  })
  if (!res?.access_token || !res?.id_token) {
    throw new Error("That code didn't work. Request a new one and try again.")
  }
  return hydrateSessionFromTokens(
    {
      id_token: res.id_token,
      access_token: res.access_token,
      refresh_token: res.refresh_token ?? "",
    },
    "email_otp",
  )
}
