// E9.58 — the ONE way a visitor with no account gets one. It is now self-serve.
//
// This file was created by E9.56c to centralise a `mailto:` — the entire product's answer to "I
// want an account" was "email Charlie and wait", which dead-ended the funnel one step before
// conversion: E9.56b had just made every locked 2026 projection public, indexable, and topped with
// a Subscribe button that led to a request for an email.
//
// E9.57 then verified LIVE that Google OAuth self-serve signup already works end-to-end (a
// never-before-seen Gmail → account → Stripe checkout → `subscriber` group → gate opens). The
// entry point simply was not wired into the funnel: it existed only as one button on /login, a
// page a stranger with no account has no reason to open. So E9.58 is a wiring job, not a build.
//
// ⛔ NATIVE EMAIL/PASSWORD REGISTRATION IS A DELIBERATE DEAD END — DO NOT "FIX" IT.
// The Cognito pool has no email auto-verification (by design, per `infrastructure/aws_resources.md`):
// `sign_up` succeeds and creates an account that can NEVER confirm itself, because
// `resend_confirmation_code` returns "Auto verification not turned on" and no code is ever sent.
// The only two working onboarding paths are an admin-created invite and federated Google.
// Adding a password signup form without first turning on verification would manufacture
// permanently-unconfirmed accounts that also fail password reset — strictly worse than no signup.
export const SIGNUP_HREF = "/signup"

/** `/signup`, carrying where to return to after the OAuth round-trip (e.g. `/subscribe`). */
export function signupHref(next?: string): string {
  return next ? `${SIGNUP_HREF}?next=${encodeURIComponent(next)}` : SIGNUP_HREF
}

// Retained ONLY as the fallback for an environment where the Hosted UI is not configured
// (`NEXT_PUBLIC_COGNITO_HOSTED_UI_DOMAIN` unset — a preview deploy, a local dev shell). There,
// "Continue with Google" cannot work, and a mailto beats a button that silently does nothing.
// It is NOT the signup path any more; nothing should link to it when `isHostedUiConfigured()`.
export const REQUEST_ACCESS_MAILTO =
  "mailto:charlie@credencesports.com?subject=Beta%20Access%20Request"
