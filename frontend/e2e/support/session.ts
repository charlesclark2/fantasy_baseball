import type { Page } from "@playwright/test"
import { buildEnv } from "./env"

/**
 * G100-C1 — put the browser in a SIGNED-IN state, without a network round trip.
 *
 * ══ WHY THIS IS NEEDED AT ALL ══════════════════════════════════════════════════════════════════
 *
 * Every spec before this one exercised a PUBLIC surface, so the suite had never had to authenticate.
 * The free tier's personalized league cannot be tested that way: a league is stored against a
 * Cognito `sub`, `FantasyLeagueGuard` bounces an anonymous visitor to /login, and `useSavedLeagues`
 * is `enabled: !!accessToken` — so without a session the activation screen never even fetches, and
 * a spec asserting "the delta rendered" would be asserting against a redirect.
 *
 * ══ HOW IT WORKS, AND WHY IT IS NOT A SECURITY SHORTCUT ════════════════════════════════════════
 *
 * `amazon-cognito-identity-js` reads its session straight out of `window.localStorage` under a
 * documented key layout, and `CognitoUserSession.isValid()` checks only the JWT's `exp` claim —
 * signature verification is a SERVER concern, which is precisely the repo's standing position
 * (`services/jwt_verify.py`: a client-side token is attacker-controlled, so the API verifies it).
 * Seeding those keys therefore produces exactly the state a real login produces, in the only place
 * the client ever looks.
 *
 * ⛔ IT PROVES NOTHING ABOUT AUTHORIZATION, and must never be read as if it did. The API is mocked
 * here, so this exercises RENDER behaviour for a signed-in caller and nothing else. Who may read
 * what is asserted server-side, against the real ASGI app, in
 * `betting_ml/tests/test_g100_c1_free_league.py` — including that a forged token buys no
 * entitlement. Keeping the two in different suites is deliberate: a browser test that appeared to
 * check entitlement would be the most convincing vacuous guard in the repo.
 *
 * ⚠️ `addInitScript`, NOT a post-load `evaluate`. The auth context reads the session during its
 * first effect; seeding after navigation would race it, and the flake would look like a guard bug.
 */

const HOUR = 3600

function segment(obj: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(obj))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "")
}

/** A structurally-real, unsigned JWT. `exp` is what `isValid()` reads. */
function token(claims: Record<string, unknown>, nowSeconds: number): string {
  return [
    segment({ alg: "RS256", typ: "JWT", kid: "e2e" }),
    segment({ ...claims, iat: nowSeconds, exp: nowSeconds + HOUR }),
    "e2e-not-a-real-signature",
  ].join(".")
}

export interface SessionOptions {
  email?: string
  /** Cognito groups. `[]` — the DEFAULT — is a signed-in FREE account, which is G100-C1's subject.
   *  Pass `["subscriber"]` for an entitled caller. */
  groups?: string[]
  sub?: string
}

/**
 * Seed a Cognito session into `localStorage` before the page's first script runs.
 *
 * Call BEFORE `page.goto`.
 */
export async function signIn(page: Page, options: SessionOptions = {}): Promise<void> {
  const email = options.email ?? "free-user@example.com"
  const groups = options.groups ?? []
  const sub = options.sub ?? "e2e-free-user-1"
  // ⚠️ Read from the file the app was COMPILED with, never hardcoded: `NEXT_PUBLIC_*` values are
  // inlined at build time, so a literal here would silently stop matching the moment e2e.env moved
  // and the session would land under a key nothing reads (`buildEnv` throws rather than returning
  // undefined, for exactly that reason).
  const clientId = buildEnv("NEXT_PUBLIC_COGNITO_APP_CLIENT_ID")
  const now = Math.floor(Date.now() / 1000)

  const accessToken = token(
    { sub, token_use: "access", username: email, "cognito:groups": groups, client_id: clientId },
    now,
  )
  const idToken = token(
    { sub, token_use: "id", email, email_verified: true, "cognito:groups": groups, aud: clientId },
    now,
  )

  const prefix = `CognitoIdentityServiceProvider.${clientId}`
  await page.addInitScript(
    ([p, user, at, it]) => {
      const ls = window.localStorage
      ls.setItem(`${p}.LastAuthUser`, user)
      ls.setItem(`${p}.${user}.accessToken`, at)
      ls.setItem(`${p}.${user}.idToken`, it)
      // A refresh token must be PRESENT — `getSession` reaches for it — but is never exercised: the
      // access token above is unexpired, so no refresh round trip is attempted (and there would be
      // no Cognito endpoint to answer one).
      ls.setItem(`${p}.${user}.refreshToken`, "e2e-refresh-token")
      ls.setItem(`${p}.${user}.clockDrift`, "0")
    },
    [prefix, email, accessToken, idToken] as const,
  )
}

/**
 * G100-D0-R1 — the token trio a Cognito `/oauth2/token` exchange hands back.
 *
 * ⭐ WHY THIS IS NOT A SECOND JWT BUILDER. `signup-attribution.spec.ts` drives the REAL
 * `/callback` page, which calls `completeGoogleSignIn` → `hydrateSessionFromTokens`; that decodes
 * the id token's payload for the username and writes the trio into the SDK's storage layout. So
 * the tokens have to be structurally real in exactly the way `signIn` above already needs them to
 * be. Sharing the builder is what stops the two drifting into disagreement about a claim shape.
 *
 * ⛔ Unsigned, and that proves nothing about authorization — see the header. Signature
 * verification is a SERVER concern and is asserted against the real ASGI app.
 */
export function fakeOAuthTokens(options: SessionOptions = {}): {
  id_token: string
  access_token: string
  refresh_token: string
} {
  const email = options.email ?? "new-user@example.com"
  const groups = options.groups ?? []
  const sub = options.sub ?? "e2e-callback-user-1"
  const clientId = buildEnv("NEXT_PUBLIC_COGNITO_APP_CLIENT_ID")
  const now = Math.floor(Date.now() / 1000)
  return {
    id_token: token(
      { sub, token_use: "id", email, email_verified: true, "cognito:groups": groups, aud: clientId },
      now,
    ),
    access_token: token(
      { sub, token_use: "access", username: email, "cognito:groups": groups, client_id: clientId },
      now,
    ),
    refresh_token: "e2e-refresh-token",
  }
}
