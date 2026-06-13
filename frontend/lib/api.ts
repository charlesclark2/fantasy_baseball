export class AuthError extends Error {}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
  token?: string | null
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
  if (res.status === 401) throw new AuthError('Unauthorized')
  if (!res.ok) throw new Error(`API error ${res.status}`)
  if (res.status === 204 || res.headers.get('content-length') === '0') return null
  return res.json()
}
