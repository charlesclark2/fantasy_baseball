export class AuthError extends Error {}

/**
 * Global token refresher, registered by AuthProvider (see lib/auth-context.tsx).
 * Returns a freshly-renewed Cognito access token, or null if the refresh itself
 * failed (refresh token expired/invalid → the user must re-authenticate).
 *
 * This lets apiFetch recover a long-lived tab whose access token has silently
 * expired: on a 401 it renews the session once and retries the failed call,
 * instead of hard-breaking the section (E9.44 / the E9.26b finding).
 */
type TokenRefresher = () => Promise<string | null>
let _refresher: TokenRefresher | null = null

export function registerTokenRefresher(fn: TokenRefresher | null) {
  _refresher = fn
}

/**
 * Extract the API's OWN explanation of a failure, falling back to the bare status.
 *
 * ⚠️ WHY THIS EXISTS. `apiFetch` used to throw `API error ${status}` and DISCARD the response body,
 * so a router that had gone to the trouble of returning a precise, user-ready `detail`
 * ("Sleeper has no user called 'X' — check the spelling, or paste your league ID instead") had that
 * message thrown away at the boundary and replaced with a number. Every caller was then forced to
 * guess a generic message from the status code, which is how a plain typo came to read as an
 * unexplained failure. Same class as E9.41's dropped Pydantic field: the information was correct
 * and complete at the source and got lost one layer out.
 *
 * FastAPI's `detail` is a STRING for our own `HTTPException`s, but a LIST of objects for automatic
 * request-validation errors — dumping that at a user would be worse than the status code, so only a
 * string is surfaced. The status is always appended so the message stays diagnosable in a bug report.
 */
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const detail = body?.detail
    if (typeof detail === "string" && detail.trim()) return detail
  } catch {
    // no body, or not JSON — fall through to the status-only message
  }
  return `API error ${res.status}`
}

/**
 * G100-D1 — the ANONYMOUS read path: fetch a same-origin `/api/public/*` route handler instead of
 * the API Lambda.
 *
 * Those handlers return the payload with `s-maxage`, so Vercel's CDN serves every view inside the
 * window from the edge with NO function invocation and NO Lambda call. Use it for any read whose
 * response carries no per-caller content — a token-bearing read must keep using `apiFetch`, because
 * an entitlement-dependent payload must never reach a shared cache.
 *
 * Deliberately takes no token parameter: the absence of one is the point, and a signature that
 * cannot accept a token cannot accidentally forward it.
 */
export async function cdnFetch(path: string): Promise<any> {
  // Relative URL ⇒ same origin ⇒ our CDN. Deliberately NOT prefixed with `NEXT_PUBLIC_API_URL`.
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(await errorMessage(res))
  if (res.status === 204 || res.headers.get('content-length') === '0') return null
  return res.json()
}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
  token?: string | null,
  // Internal: set on the single post-refresh retry so we never loop.
  _isRetry = false
): Promise<any> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? ''
  const res = await fetch(`${base}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (res.status === 401) {
    // Attempt exactly one silent token refresh, then retry the call. Only if the
    // refresh itself fails (or yields no newer token) do we surface AuthError,
    // which the AuthGuard turns into a redirect to /login.
    if (!_isRetry && _refresher) {
      const fresh = await _refresher()
      if (fresh && fresh !== token) {
        return apiFetch(path, options, fresh, true)
      }
    }
    throw new AuthError('Unauthorized')
  }
  if (!res.ok) throw new Error(await errorMessage(res))
  if (res.status === 204 || res.headers.get('content-length') === '0') return null
  return res.json()
}
