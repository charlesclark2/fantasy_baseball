import type { Page } from "@playwright/test"

/**
 * E9.60 — seed a SIGNED-IN Cognito session in the browser, so a spec can drive the authenticated
 * chrome (the signed-in nav, the account block, Sign Out).
 *
 * ══ WHY THIS HAD TO EXIST ══════════════════════════════════════════════════════════════════════
 *
 * Every spec before this one runs SIGNED OUT. `mockApi` intercepts the API, but the auth state is
 * not an API call — `lib/auth-context.tsx` asks `amazon-cognito-identity-js` for the current user,
 * which reads `window.localStorage` directly. So no amount of request mocking produces a signed-in
 * page, and the entire authenticated half of the nav was untestable: the E9.60 mobile-menu bug the
 * operator reported lives in the SIGNED-IN panel (Sign Out and Settings are only there).
 *
 * ⭐ WHAT IT DOES: writes the exact localStorage keys the SDK reads, with well-formed JWTs whose
 * `exp` is in the future so `getSession()` accepts them without attempting a refresh. The pool and
 * client ids come from `e2e/e2e.env`, which the E2E build inlines at compile time — so these keys
 * match what the shipped bundle looks for.
 *
 * ⛔ THE TOKENS ARE UNSIGNED AND THAT IS FINE HERE, but it bounds what a spec may claim. Nothing in
 * this harness verifies a signature: the SDK decodes the payload client-side and checks expiry, and
 * the API is mocked. So a spec using this proves RENDER behaviour for an authenticated user — it
 * proves nothing about authorization, which is enforced server-side and tested against the real
 * ASGI app in `test_freemium_tier.py` / `test_e9_56_entitlement.py`. Asserting authorization from
 * here would be the most convincing vacuous guard available (`api-mock.ts` records the same rule
 * for the league-quota refusal).
 */

/** Mirrors `e2e/e2e.env`'s `NEXT_PUBLIC_COGNITO_APP_CLIENT_ID`. ⚠️ If that value changes, this one
 *  must move with it — the SDK's storage keys are namespaced by client id, so a mismatch produces a
 *  silently signed-OUT page rather than an error. `positioning-alignment.spec.ts` asserts the
 *  signed-in chrome actually rendered, which is what turns that silent case into a failure. */
const CLIENT_ID = "e2etestappclientid000000"
const USERNAME = "e2e-user"

/** base64url of a JSON payload — the shape `amazon-cognito-identity-js` decodes. */
function jwt(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    Buffer.from(JSON.stringify(o))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "")
  // The signature segment is never verified client-side; it only has to be present.
  return `${b64({ alg: "RS256", typ: "JWT" })}.${b64(payload)}.e2e-not-a-real-signature`
}

export type SignedInOptions = {
  email?: string
  /** Cognito groups, e.g. `["subscriber"]`. Drives `canAccess` — an empty list is a signed-in
   *  visitor with NO entitlement, which is a real and distinct state worth being able to render. */
  groups?: string[]
}

/**
 * Must be called BEFORE `page.goto` — it installs an init script, so the session is present when
 * the app's first render reads it. Calling it after a navigation leaves the page signed out for
 * that render, which is exactly the kind of half-state that produces a confusing pass.
 */
export async function signIn(page: Page, options: SignedInOptions = {}): Promise<void> {
  const email = options.email ?? "e2e@credencesports.test"
  const groups = options.groups ?? ["subscriber"]
  // An hour out. Comfortably beyond any test run, and short enough that a leaked artifact is inert.
  const exp = Math.floor(Date.now() / 1000) + 3600

  const idToken = jwt({
    sub: USERNAME,
    email,
    "cognito:groups": groups,
    token_use: "id",
    aud: CLIENT_ID,
    exp,
    iat: Math.floor(Date.now() / 1000),
  })
  const accessToken = jwt({
    sub: USERNAME,
    username: USERNAME,
    token_use: "access",
    client_id: CLIENT_ID,
    exp,
    iat: Math.floor(Date.now() / 1000),
  })

  const prefix = `CognitoIdentityServiceProvider.${CLIENT_ID}`
  const entries: [string, string][] = [
    [`${prefix}.LastAuthUser`, USERNAME],
    [`${prefix}.${USERNAME}.idToken`, idToken],
    [`${prefix}.${USERNAME}.accessToken`, accessToken],
    [`${prefix}.${USERNAME}.refreshToken`, "e2e-refresh-token"],
    [`${prefix}.${USERNAME}.clockDrift`, "0"],
  ]

  await page.addInitScript((kv: [string, string][]) => {
    for (const [k, v] of kv) window.localStorage.setItem(k, v)
  }, entries)
}
