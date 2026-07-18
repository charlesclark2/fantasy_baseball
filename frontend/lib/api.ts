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
  if (!res.ok) throw new Error(`API error ${res.status}`)
  if (res.status === 204 || res.headers.get('content-length') === '0') return null
  return res.json()
}
