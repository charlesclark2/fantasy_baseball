"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import type { CognitoUserSession } from "amazon-cognito-identity-js"
import posthog from "posthog-js"
import { queryClient } from "@/lib/query-client"
import { getCurrentCognitoUser } from "@/lib/cognito"
import { registerTokenRefresher } from "@/lib/api"

type AuthCtx = {
  accessToken: string | null
  email: string | null
  groups: string[]
  isAdmin: boolean
  loading: boolean
  onLoginSuccess: (at: string, it: string) => void
  signOut: () => void
}

export const AuthContext = createContext<AuthCtx>({
  accessToken: null,
  email: null,
  groups: [],
  isAdmin: false,
  loading: true,
  onLoginSuccess: () => {},
  signOut: () => {},
})

function decodeJwt(jwt: string): Record<string, unknown> | null {
  try {
    return JSON.parse(atob(jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))
  } catch {
    return null
  }
}

function decodeIdToken(idToken: string): { email: string | null; groups: string[] } {
  const payload = decodeJwt(idToken)
  if (!payload) return { email: null, groups: [] }
  return {
    email: (payload.email as string) ?? null,
    groups: (payload["cognito:groups"] as string[]) ?? [],
  }
}

// Renew this many ms before the access token's `exp` so calls never race expiry.
const PROACTIVE_REFRESH_LEAD_MS = 60_000

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [groups, setGroups] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const isAdmin = groups.includes("admin")

  // Scheduled proactive-refresh timer + de-dupe guard so concurrent renewals
  // (e.g. several queries 401-ing at once) share a single in-flight refresh.
  const proactiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const renewInFlightRef = useRef<Promise<string | null> | null>(null)
  // Holds the latest forceRenew so the scheduled timer always calls the current one.
  const forceRenewRef = useRef<() => Promise<string | null>>(() => Promise.resolve(null))

  const applySession = useCallback((at: string, it: string) => {
    const { email: userEmail, groups: userGroups } = decodeIdToken(it)
    setAccessToken(at)
    setEmail(userEmail)
    setGroups(userGroups)

    // (Re)schedule a proactive force-refresh a minute before this access token expires.
    if (proactiveTimerRef.current) clearTimeout(proactiveTimerRef.current)
    const payload = decodeJwt(at)
    const exp = payload && typeof payload.exp === "number" ? payload.exp : null
    if (exp) {
      const delay = Math.max(exp * 1000 - Date.now() - PROACTIVE_REFRESH_LEAD_MS, 5_000)
      proactiveTimerRef.current = setTimeout(() => {
        void forceRenewRef.current()
      }, delay)
    }
  }, [])

  const clearAuth = useCallback(() => {
    if (proactiveTimerRef.current) {
      clearTimeout(proactiveTimerRef.current)
      proactiveTimerRef.current = null
    }
    setAccessToken(null)
    setEmail(null)
    setGroups([])
  }, [])

  // Renew via getSession — amazon-cognito-identity-js transparently uses the
  // refresh token when the cached access/id tokens are expired. Returns the
  // (possibly unchanged, still-valid) access token, or null if the refresh
  // token itself is expired/invalid.
  const renewSession = useCallback((): Promise<string | null> => {
    if (renewInFlightRef.current) return renewInFlightRef.current
    const p = new Promise<string | null>((resolve) => {
      const user = getCurrentCognitoUser()
      if (!user) {
        clearAuth()
        resolve(null)
        return
      }
      user.getSession((err: Error | null, session: CognitoUserSession | null) => {
        if (!err && session?.isValid()) {
          const at = session.getAccessToken().getJwtToken()
          const it = session.getIdToken().getJwtToken()
          applySession(at, it)
          resolve(at)
        } else {
          // Refresh token expired/invalid → force re-authentication.
          clearAuth()
          resolve(null)
        }
      })
    }).finally(() => {
      renewInFlightRef.current = null
    })
    renewInFlightRef.current = p
    return p
  }, [applySession, clearAuth])

  // Force a brand-new token pair even while the current one is still valid.
  // Used by the proactive timer so an always-visible tab never 401s at all.
  const forceRenew = useCallback((): Promise<string | null> => {
    if (renewInFlightRef.current) return renewInFlightRef.current
    const p = new Promise<string | null>((resolve) => {
      const user = getCurrentCognitoUser()
      if (!user) {
        clearAuth()
        resolve(null)
        return
      }
      user.getSession((err: Error | null, session: CognitoUserSession | null) => {
        if (err || !session) {
          // Proactive path: the current token is likely still valid; don't force a
          // logout on a transient failure. The reactive 401 handler is the safety net.
          resolve(null)
          return
        }
        user.refreshSession(session.getRefreshToken(), (rErr, newSession: CognitoUserSession | null) => {
          if (rErr || !newSession?.isValid()) {
            resolve(null)
            return
          }
          const at = newSession.getAccessToken().getJwtToken()
          const it = newSession.getIdToken().getJwtToken()
          applySession(at, it)
          resolve(at)
        })
      })
    }).finally(() => {
      renewInFlightRef.current = null
    })
    renewInFlightRef.current = p
    return p
  }, [applySession, clearAuth])

  forceRenewRef.current = forceRenew

  // Mount: read the existing session, wire the reactive refresher (used by
  // apiFetch on a 401), and re-check on tab focus / visibility change.
  useEffect(() => {
    renewSession().finally(() => setLoading(false))
    registerTokenRefresher(() => renewSession())

    const onFocus = () => {
      if (document.visibilityState !== "hidden") void renewSession()
    }
    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onFocus)

    return () => {
      registerTokenRefresher(null)
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onFocus)
      if (proactiveTimerRef.current) clearTimeout(proactiveTimerRef.current)
    }
  }, [renewSession])

  const onLoginSuccess = useCallback((at: string, it: string) => {
    applySession(at, it)
    const { email: userEmail } = decodeIdToken(it)
    if (userEmail) {
      posthog.identify(userEmail, { email: userEmail })
    }
  }, [applySession])

  const signOut = useCallback(() => {
    const user = getCurrentCognitoUser()
    user?.signOut()
    posthog.reset()
    queryClient.clear()
    clearAuth()
  }, [clearAuth])

  return (
    <AuthContext.Provider value={{ accessToken, email, groups, isAdmin, loading, onLoginSuccess, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
