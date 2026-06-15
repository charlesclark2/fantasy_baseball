"use client"

import { createContext, useContext, useEffect, useState } from "react"
import type { CognitoUserSession } from "amazon-cognito-identity-js"
import posthog from "posthog-js"
import { queryClient } from "@/lib/query-client"
import { getCurrentCognitoUser } from "@/lib/cognito"

const _ADMIN_EMAILS: ReadonlySet<string> = new Set(
  (process.env.NEXT_PUBLIC_ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)
)

type AuthCtx = {
  accessToken: string | null
  email: string | null
  isAdmin: boolean
  loading: boolean
  onLoginSuccess: (at: string, it: string) => void
  signOut: () => void
}

export const AuthContext = createContext<AuthCtx>({
  accessToken: null,
  email: null,
  isAdmin: false,
  loading: true,
  onLoginSuccess: () => {},
  signOut: () => {},
})

function decodeEmail(idToken: string): string | null {
  try {
    const payload = JSON.parse(
      atob(idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
    )
    return (payload.email as string) ?? null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const isAdmin = email !== null && _ADMIN_EMAILS.has(email.toLowerCase())

  useEffect(() => {
    const user = getCurrentCognitoUser()
    if (!user) {
      setLoading(false)
      return
    }
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (!err && session?.isValid()) {
        const at = session.getAccessToken().getJwtToken()
        const it = session.getIdToken().getJwtToken()
        setAccessToken(at)
        setEmail(decodeEmail(it))
      }
      setLoading(false)
    })
  }, [])

  function onLoginSuccess(at: string, it: string) {
    const userEmail = decodeEmail(it)
    setAccessToken(at)
    setEmail(userEmail)
    if (userEmail) {
      posthog.identify(userEmail, { email: userEmail })
    }
  }

  function signOut() {
    const user = getCurrentCognitoUser()
    user?.signOut()
    posthog.reset()
    queryClient.clear()
    setAccessToken(null)
    setEmail(null)
  }

  return (
    <AuthContext.Provider value={{ accessToken, email, isAdmin, loading, onLoginSuccess, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
