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

// Cognito domain host (e.g. "auth.credencesports.com" or
// "credence-prod.auth.us-east-1.amazoncognito.com"). Stored without a scheme.
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
export async function startGoogleSignIn(): Promise<void> {
  const verifier = randomToken(64)
  const state = randomToken(16)
  const challenge = await pkceChallenge(verifier)

  window.localStorage.setItem(PKCE_VERIFIER_KEY, verifier)
  window.localStorage.setItem(OAUTH_STATE_KEY, state)

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

type OAuthTokens = {
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

// Persist the Hosted-UI tokens into the amazon-cognito-identity-js localStorage
// layout via setSignInUserSession(), so getCurrentCognitoUser() +
// getSession()/refreshSession() (the AuthContext silent-refresh machinery) work
// for a federated user exactly as they do for a password user.
function hydrateSessionFromTokens(tokens: OAuthTokens): {
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

  // Mark this session as federated so MFA (E9.19) skips the TOTP path — Google
  // already MFA'd the user; the Cognito software-token challenge never applies here.
  setSessionAuthMethod("google")

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
export type AuthMethod = "password" | "google"

export function setSessionAuthMethod(method: AuthMethod): void {
  try {
    window.localStorage.setItem(AUTH_METHOD_KEY, method)
  } catch {
    /* localStorage unavailable (private mode) — enrollment UI falls back to password */
  }
}

// Absent marker (pre-E9.19 sessions) ⇒ treat as "password": the safe default for the
// beta's username/password majority, and self-corrects on the user's next sign-in.
export function getSessionAuthMethod(): AuthMethod {
  try {
    return window.localStorage.getItem(AUTH_METHOD_KEY) === "google" ? "google" : "password"
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
  // True ⇒ this session signed in via Google (MFA inherited from the IdP); TOTP N/A.
  federated: boolean
}

// Full MFA state for the Settings security surface: whether TOTP is active plus whether
// this session is federated (Google). A Google session inherits IdP MFA and never hits
// the password TOTP path, so we short-circuit before calling GetUserData.
export function getMfaStatus(): Promise<MfaStatus> {
  return new Promise((resolve, reject) => {
    if (getSessionAuthMethod() === "google") {
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
