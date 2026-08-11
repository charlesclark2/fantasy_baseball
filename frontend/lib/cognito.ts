import {
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
  CognitoAccessToken,
  CognitoIdToken,
  CognitoRefreshToken,
  AuthenticationDetails,
} from "amazon-cognito-identity-js"
import type { IMfaSettings } from "amazon-cognito-identity-js"

let _pool: CognitoUserPool | null = null

function getPool(): CognitoUserPool {
  if (!_pool) {
    _pool = new CognitoUserPool({
      UserPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID!,
      ClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID!,
      Storage: typeof window !== "undefined" ? window.localStorage : undefined,
    })
  }
  return _pool
}

export function getCognitoUser(email: string) {
  return new CognitoUser({ Username: email, Pool: getPool() })
}

export function getCurrentCognitoUser() {
  return getPool().getCurrentUser()
}

// Force-mint a brand-new token pair from the refresh token, even if the cached
// access token is still valid. Used after a Stripe conversion (E9.8) so the freshly
// added `subscriber` Cognito group lands in the id/access token immediately, rather
// than waiting for the next scheduled refresh. Resolves null if there's no session.
export function forceRefreshTokens(): Promise<{ accessToken: string; idToken: string } | null> {
  return new Promise((resolve) => {
    const user = getCurrentCognitoUser()
    if (!user) {
      resolve(null)
      return
    }
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session) {
        resolve(null)
        return
      }
      user.refreshSession(session.getRefreshToken(), (rErr, newSession: CognitoUserSession | null) => {
        if (rErr || !newSession?.isValid()) {
          resolve(null)
          return
        }
        resolve({
          accessToken: newSession.getAccessToken().getJwtToken(),
          idToken: newSession.getIdToken().getJwtToken(),
        })
      })
    })
  })
}

// ── Hosted-UI / federated (Google) sign-in (E9.7) ────────────────────────────
// Google OAuth runs through Cognito's Hosted UI (authorization-code + PKCE). The
// app client is a PUBLIC client (no secret — the SDK can't hold one), so the code
// exchange needs only the client id + PKCE verifier. The GOOGLE client secret
// lives in Cognito's federated-IdP config server-side, never in this repo.

const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID!

// Cognito Hosted-UI domain host, without a scheme. The live value is
// "us-east-1gg9zmbwqt.auth.us-east-1.amazoncognito.com" — the USER POOL ID lowercased with
// the underscore removed, because the pool has no custom domain.
// ⚠️ This comment used to offer two plausible, brand-shaped hosts as examples. Both were
// inventions, neither resolved, and one of them reached Vercel and took the only signup path
// in production down with a browser DNS error (2026-08-06). Never write a guessed host here —
// `aws cognito-idp describe-user-pool --user-pool-id <pool>` is the only source of truth, and
// a guard pins this value to the two other files that name it.
function hostedUiDomain(): string {
  const raw = process.env.NEXT_PUBLIC_COGNITO_HOSTED_UI_DOMAIN ?? ""
  return raw.replace(/^https?:\/\//, "").replace(/\/+$/, "")
}

export function isHostedUiConfigured(): boolean {
  return hostedUiDomain().length > 0
}

// Must match a Cognito app-client callback URL exactly (localhost for dev,
// https://credencesports.com/callback for prod).
function redirectUri(): string {
  return `${window.location.origin}/callback`
}

// Stored in localStorage (NOT sessionStorage): the PKCE verifier + CSRF state
// must survive the cross-origin OAuth redirect round-trip (login → Cognito →
// Google → Cognito → /callback). sessionStorage is unreliable across a cross-site
// top-level navigation in several browsers; localStorage always survives. Both
// keys are single-use and cleared as soon as the callback consumes them.
const PKCE_VERIFIER_KEY = "cognito_pkce_verifier"
const OAUTH_STATE_KEY = "cognito_oauth_state"

// E9.58 — where to land AFTER the round-trip. The Cognito app client's callback URL is a
// fixed allowlist entry (`<origin>/callback`), so the destination cannot ride in redirect_uri;
// it is stashed beside the PKCE verifier for the same reason (localStorage survives the
// cross-origin navigation, sessionStorage does not reliably).
// This is what makes the funnel close: a stranger who clicks Subscribe on a locked projection
// signs up and comes back to /subscribe, rather than being dropped on /dashboard having
// silently lost the thing they were trying to buy.
const POST_SIGNIN_REDIRECT_KEY = "cognito_post_signin_redirect"

// E9.58d — what the user was TRYING to do, carried across the same round-trip as the redirect.
//
// Without this the funnel has a start and no finish: `user_signup_started` fires on the CTA, and
// what comes back is `user_signed_in`, which is byte-identical for a brand-new signup and a
// returning user. So the one number worth having off this funnel — how many people who clicked
// Sign Up actually made it back with a session — was not computable.
//
// The surface is the only thing that knows the difference (a "Sign Up" button vs a "Sign In"
// button), and the surface is on the far side of a cross-origin redirect from the callback,
// which is why this has to be stashed rather than inferred.
const SIGNIN_CONTEXT_KEY = "cognito_signin_context"

export type SignInIntent = "signup" | "signin"
export type SignInContext = { intent: SignInIntent; surface: string }

// Only a same-origin ABSOLUTE PATH is ever accepted. This value is read from a query string
// (`/signup?next=…`), i.e. it is attacker-controlled: anything that could leave the origin is an
// open redirect on the auth callback, which is the worst place in the app to have one.
// Rejects "//evil.com" (protocol-relative), "https://…", "javascript:…", and any non-"/" start.
export function sanitizeInternalPath(raw: string | null | undefined): string | null {
  if (!raw) return null
  if (!raw.startsWith("/")) return null
  // Protocol-relative ("/" + "/" + host) leaves the origin entirely. Written as an index check
  // rather than a two-slash string literal on purpose: the repo's source-inspection guards strip
  // `//` line comments before asserting, and a literal double slash inside a string is eaten by
  // that stripper — so the clause would be invisible to the very test that pins it.
  if (raw[1] === "/") return null
  // A backslash is normalised to "/" by some browsers, so "/\evil.com" can escape the origin.
  if (raw.includes("\\")) return null
  return raw
}

function base64UrlEncode(bytes: Uint8Array): string {
  let str = ""
  for (const b of bytes) str += String.fromCharCode(b)
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

function randomToken(byteLength: number): string {
  const bytes = new Uint8Array(byteLength)
  window.crypto.getRandomValues(bytes)
  return base64UrlEncode(bytes)
}

async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await window.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  )
  return base64UrlEncode(new Uint8Array(digest))
}

// Kick off "Continue with Google": mint a PKCE verifier + CSRF state (stashed in
// localStorage so it survives the cross-origin redirect round-trip), then redirect
// the browser to the Cognito Hosted-UI authorize endpoint forced to the Google IdP.
// `next` is where to send the user once the callback completes (default /dashboard).
// `context` records whether this was a signup or a sign-in, and from which page, so the
// callback can close the funnel it opened (E9.58d).
export async function startGoogleSignIn(
  next?: string | null,
  context?: SignInContext,
): Promise<void> {
  const verifier = randomToken(64)
  const state = randomToken(16)
  const challenge = await pkceChallenge(verifier)

  window.localStorage.setItem(PKCE_VERIFIER_KEY, verifier)
  window.localStorage.setItem(OAUTH_STATE_KEY, state)

  const dest = sanitizeInternalPath(next)
  if (dest) window.localStorage.setItem(POST_SIGNIN_REDIRECT_KEY, dest)
  else window.localStorage.removeItem(POST_SIGNIN_REDIRECT_KEY)

  // Always write or clear, never leave a previous attempt's context to be picked up by the next
  // sign-in — a stale "signup" would report a conversion that did not happen.
  if (context) window.localStorage.setItem(SIGNIN_CONTEXT_KEY, JSON.stringify(context))
  else window.localStorage.removeItem(SIGNIN_CONTEXT_KEY)

  const params = new URLSearchParams({
    identity_provider: "Google",
    client_id: CLIENT_ID,
    response_type: "code",
    scope: "openid email",
    redirect_uri: redirectUri(),
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  })
  window.location.href = `https://${hostedUiDomain()}/oauth2/authorize?${params.toString()}`
}

// Read-and-clear the stashed destination. Single-use: a stale entry must never hijack a later,
// unrelated sign-in. Re-sanitised on the way out — the value has been through localStorage, where
// anything on the page could have written to it.
export function consumePostSignInRedirect(): string | null {
  const raw = window.localStorage.getItem(POST_SIGNIN_REDIRECT_KEY)
  window.localStorage.removeItem(POST_SIGNIN_REDIRECT_KEY)
  return sanitizeInternalPath(raw)
}

// Read-and-clear the sign-in context. Single-use for the same reason the redirect is: a stale
// entry from an ABANDONED attempt must not attach itself to an unrelated later sign-in and
// report a conversion that never happened. Returns null when absent or unparseable — the
// callback then reports the intent as unknown rather than guessing "signup", so a bug here can
// only ever UNDER-count conversions, never inflate them.
export function consumeSignInContext(): SignInContext | null {
  const raw = window.localStorage.getItem(SIGNIN_CONTEXT_KEY)
  window.localStorage.removeItem(SIGNIN_CONTEXT_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as SignInContext
    if (parsed?.intent !== "signup" && parsed?.intent !== "signin") return null
    return { intent: parsed.intent, surface: String(parsed.surface ?? "unknown") }
  } catch {
    return null
  }
}

export type OAuthTokens = {
  id_token: string
  access_token: string
  refresh_token: string
}

// Exchange the authorization code (returned to /callback) for tokens.
// Validates the CSRF state and consumes the one-time PKCE verifier.
export async function completeGoogleSignIn(
  code: string,
  state: string,
): Promise<{ accessToken: string; idToken: string }> {
  const savedState = window.localStorage.getItem(OAUTH_STATE_KEY)
  const verifier = window.localStorage.getItem(PKCE_VERIFIER_KEY)
  window.localStorage.removeItem(OAUTH_STATE_KEY)
  window.localStorage.removeItem(PKCE_VERIFIER_KEY)

  if (!savedState || savedState !== state) {
    throw new Error("Sign-in could not be verified. Please try again.")
  }
  if (!verifier) {
    throw new Error("Sign-in session expired. Please try again.")
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: CLIENT_ID,
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  })

  const res = await fetch(`https://${hostedUiDomain()}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  })
  if (!res.ok) {
    // Cognito returns { error, error_description } on a bad token exchange.
    const detail = await res.text().catch(() => "")
    console.error("oauth2/token exchange failed", res.status, detail)
    throw new Error("Google sign-in failed. Please try again.")
  }
  const tokens = (await res.json()) as OAuthTokens
  return hydrateSessionFromTokens(tokens)
}

// Persist a token trio into the amazon-cognito-identity-js localStorage layout via
// setSignInUserSession(), so getCurrentCognitoUser() + getSession()/refreshSession()
// (the AuthContext silent-refresh machinery) work for a federated user exactly as
// they do for a password user.
//
// G100-C0 — EXPORTED and given an explicit `method`, because email-OTP tokens arrive
// the same way Google's do: minted by Cognito, handed to us over HTTPS, with no
// CognitoUser object to attach them to. Sharing this one function is what makes the
// OTP session indistinguishable from every other session everywhere downstream —
// silent refresh, the proactive renewal timer, the 401 retry, and sign-out. A second
// hand-rolled hydration would be a second thing to keep in step with the SDK's
// storage layout, and the first one to rot.
export function hydrateSessionFromTokens(
  tokens: OAuthTokens,
  method: AuthMethod = "google",
): {
  accessToken: string
  idToken: string
} {
  const idToken = new CognitoIdToken({ IdToken: tokens.id_token })
  const accessToken = new CognitoAccessToken({ AccessToken: tokens.access_token })
  const refreshToken = new CognitoRefreshToken({ RefreshToken: tokens.refresh_token })
  const session = new CognitoUserSession({
    IdToken: idToken,
    AccessToken: accessToken,
    RefreshToken: refreshToken,
  })

  const payload = idToken.decodePayload() as Record<string, unknown>
  const username = (payload["cognito:username"] as string) ?? (payload.sub as string)
  const user = new CognitoUser({ Username: username, Pool: getPool() })
  user.setSignInUserSession(session) // writes tokens to localStorage (cacheTokens)

  // Mark how this session authenticated so MFA (E9.19) can skip the TOTP path when it
  // does not apply — Google already MFA'd the user, and an emailed one-time code is
  // itself the possession factor. The Cognito software-token challenge belongs to the
  // password `InitiateAuth` path and only that path.
  setSessionAuthMethod(method)

  return {
    accessToken: accessToken.getJwtToken(),
    idToken: idToken.getJwtToken(),
  }
}

// ── TOTP MFA (E9.19) ─────────────────────────────────────────────────────────
// Software-token (authenticator-app) MFA for username/password accounts. Federated
// (Google/E9.7) users inherit MFA from their IdP — the enrollment UI is hidden for
// them (detected via the id token's `identities` claim) so we never double-prompt.
// Cognito drives the whole flow: AssociateSoftwareToken → VerifySoftwareToken →
// SetUserMFAPreference (enroll); RespondToAuthChallenge (login); no SES/SNS/backend.

const MFA_ISSUER = "Credence Sports"

// Resolve the current signed-in user with a hydrated, valid session so the
// authenticated AssociateSoftwareToken / VerifySoftwareToken / SetUserMFAPreference
// branches — which read signInUserSession.getAccessToken() — work. Rejects if the
// user isn't signed in or the session can't be refreshed.
function withValidUser(): Promise<CognitoUser> {
  return new Promise((resolve, reject) => {
    const user = getCurrentCognitoUser()
    if (!user) {
      reject(new Error("You're not signed in. Please sign in again."))
      return
    }
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session?.isValid()) {
        reject(new Error("Your session has expired. Please sign in again."))
        return
      }
      resolve(user)
    })
  })
}

// How the CURRENT session authenticated. This is the load-bearing MFA signal — NOT
// the id token's `identities` claim. Post-E9.7 account-linking, ONE Cognito sub can
// carry BOTH a password credential and a linked Google identity, so `identities` is
// present even on that user's password logins — keying off it would wrongly hide TOTP
// on the password path (and mis-scope enforcement). The auth METHOD of this session is
// the truth: a Google Hosted-UI login is already MFA'd by Google (no TOTP), a password
// InitiateAuth login is the one TOTP protects. We stamp it at each sign-in entry point.
const AUTH_METHOD_KEY = "credence_auth_method"
export type AuthMethod = "password" | "google" | "email_otp"

// G100-C0 — the methods that never involve a password, and therefore never involve TOTP.
//
// ⭐ THIS IS A PREDICATE, NOT A LIST OF `=== "google"` COMPARISONS SCATTERED AROUND. E9.19's
// actual property is "a session that did not authenticate with a password is not prompted for
// the factor that protects passwords" — it was written as `=== "google"` only because Google
// was the sole passwordless method at the time. Adding a second one by bolting `|| === "otp"`
// onto each call site is how one of them gets missed, and the miss is invisible: an OTP user
// who has no password would be sent to enroll TOTP, and the only way back out
// (`reauthenticatePassword`) asks for a password they have never had. Naming the property once
// makes "did we cover every site?" a question with an answer.
const PASSWORDLESS_METHODS: readonly AuthMethod[] = ["google", "email_otp"]

export function sessionUsesPasswordlessAuth(): boolean {
  return PASSWORDLESS_METHODS.includes(getSessionAuthMethod())
}

export function setSessionAuthMethod(method: AuthMethod): void {
  try {
    window.localStorage.setItem(AUTH_METHOD_KEY, method)
  } catch {
    /* localStorage unavailable (private mode) — enrollment UI falls back to password */
  }
}

// Absent marker (pre-E9.19 sessions) ⇒ treat as "password": the safe default for the
// beta's username/password majority, and self-corrects on the user's next sign-in.
// An UNRECOGNISED value falls to "password" for the same reason — the strict direction,
// since over-prompting for TOTP is an annoyance and under-prompting is a bypass.
export function getSessionAuthMethod(): AuthMethod {
  try {
    const raw = window.localStorage.getItem(AUTH_METHOD_KEY)
    if (raw === "google") return "google"
    if (raw === "email_otp") return "email_otp"
    return "password"
  } catch {
    return "password"
  }
}

export function clearSessionAuthMethod(): void {
  try {
    window.localStorage.removeItem(AUTH_METHOD_KEY)
  } catch {
    /* nothing to clear */
  }
}

export type MfaStatus = {
  // TOTP is active on this (native) account.
  enabled: boolean
  // True ⇒ this session authenticated without a password (Google, or a G100-C0 emailed
  // one-time code), so the TOTP path does not apply. The name predates the second case
  // and is kept because the Settings UI already reads it; what it MEANS is "TOTP is not
  // applicable to this session", which is exactly what both cases are.
  federated: boolean
}

// Full MFA state for the Settings security surface: whether TOTP is active plus whether
// this session is federated (Google). A Google session inherits IdP MFA and never hits
// the password TOTP path, so we short-circuit before calling GetUserData.
export function getMfaStatus(): Promise<MfaStatus> {
  return new Promise((resolve, reject) => {
    if (sessionUsesPasswordlessAuth()) {
      resolve({ enabled: false, federated: true })
      return
    }
    const user = getCurrentCognitoUser()
    if (!user) {
      reject(new Error("You're not signed in. Please sign in again."))
      return
    }
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session?.isValid()) {
        reject(new Error("Your session has expired. Please sign in again."))
        return
      }
      // bypassCache: read the authoritative MFA setting from Cognito, not the stale
      // cached user-data blob (which would miss an enroll/disable done this session).
      user.getUserData(
        (dErr, data) => {
          if (dErr || !data) {
            // An unreadable status shouldn't hard-fail the page — treat as not enrolled.
            resolve({ enabled: false, federated: false })
            return
          }
          const enabled = (data.UserMFASettingList ?? []).includes("SOFTWARE_TOKEN_MFA")
          resolve({ enabled, federated: false })
        },
        { bypassCache: true },
      )
    })
  })
}

export type TotpEnrollment = {
  // Base32 secret for manual ("enter a setup key") entry in an authenticator app.
  secretCode: string
  // otpauth:// URI to encode as a QR code.
  otpauthUrl: string
}

// Step 1 of enrollment — AssociateSoftwareToken. Returns the shared secret + an
// otpauth URI (issuer "Credence Sports", account = the user's email) for the QR.
export function beginTotpEnrollment(email: string): Promise<TotpEnrollment> {
  return withValidUser().then(
    (user) =>
      new Promise<TotpEnrollment>((resolve, reject) => {
        user.associateSoftwareToken({
          associateSecretCode(secretCode: string) {
            const label = encodeURIComponent(`${MFA_ISSUER}:${email}`)
            const params = new URLSearchParams({
              secret: secretCode,
              issuer: MFA_ISSUER,
            })
            resolve({
              secretCode,
              otpauthUrl: `otpauth://totp/${label}?${params.toString()}`,
            })
          },
          onFailure(err) {
            reject(err)
          },
        })
      }),
  )
}

// Step 2 of enrollment — VerifySoftwareToken(code) then SetUserMFAPreference to make
// TOTP the preferred + enabled factor. The authenticated verify/preference calls key
// off the access token (not a client-side Session), so a freshly-resolved user works.
export function confirmTotpEnrollment(code: string): Promise<void> {
  return withValidUser().then(
    (user) =>
      new Promise<void>((resolve, reject) => {
        user.verifySoftwareToken(code, "Authenticator app", {
          onSuccess() {
            const totp: IMfaSettings = { PreferredMfa: true, Enabled: true }
            user.setUserMfaPreference(null, totp, (err) => {
              if (err) {
                reject(err)
                return
              }
              resolve()
            })
          },
          onFailure(err) {
            reject(err)
          },
        })
      }),
  )
}

// Turn TOTP off — SetUserMFAPreference(disabled). Guard the caller with a re-auth
// (reauthenticatePassword) so a walk-up session can't silently drop MFA.
export function disableTotpMfa(): Promise<void> {
  return withValidUser().then(
    (user) =>
      new Promise<void>((resolve, reject) => {
        const totp: IMfaSettings = { PreferredMfa: false, Enabled: false }
        user.setUserMfaPreference(null, totp, (err) => {
          if (err) {
            reject(err)
            return
          }
          resolve()
        })
      }),
  )
}

// Re-auth gate for a sensitive change (disable MFA). Verifies the password WITHOUT
// disturbing the live session: on a correct password Cognito issues the TOTP
// challenge (the account has MFA on), and REACHING that challenge already proves the
// password — we resolve there and never complete it (so no cached-token churn, no
// second authenticator prompt). A wrong password fails via onFailure.
export function reauthenticatePassword(email: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const authDetails = new AuthenticationDetails({ Username: email, Password: password })
    const user = getCognitoUser(email)
    user.authenticateUser(authDetails, {
      onSuccess() {
        resolve()
      },
      onFailure(err) {
        reject(err)
      },
      // Password was correct → MFA challenge issued → re-auth satisfied.
      totpRequired() {
        resolve()
      },
      mfaRequired() {
        resolve()
      },
    })
  })
}

// ── Subscriber MFA enforcement (E9.19 → gates E9.8) ──────────────────────────
// The SINGLE in-app enforcement gate. Optional-but-encouraged in beta; flip
// NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA=1 at Stripe launch to require TOTP for every
// paying (`subscriber`) account. Federated users are exempt (they inherit IdP MFA).
export function isSubscriberMfaEnforced(): boolean {
  return process.env.NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA === "1"
}

// Whether `groups` should be forced to enroll MFA before using the app. Returns false
// unless enforcement is on AND the user is a subscriber. Federated-vs-enrolled is
// resolved by the caller against getMfaStatus() (an async Cognito read).
export function subscriberMfaRequired(groups: string[]): boolean {
  return isSubscriberMfaEnforced() && groups.includes("subscriber")
}

export { AuthenticationDetails }
