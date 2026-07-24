import {
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
  CognitoAccessToken,
  CognitoIdToken,
  CognitoRefreshToken,
  AuthenticationDetails,
} from "amazon-cognito-identity-js"

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

  return {
    accessToken: accessToken.getJwtToken(),
    idToken: idToken.getJwtToken(),
  }
}

export { AuthenticationDetails }
