"use client"

import { createContext, useContext, useEffect, useState } from "react"
import type { CognitoUserSession } from "amazon-cognito-identity-js"
import posthog from "posthog-js"
import { queryClient } from "@/lib/query-client"
import { getCurrentCognitoUser } from "@/lib/cognito"

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

function decodeIdToken(idToken: string): { email: string | null; groups: string[] } {
  try {
    const payload = JSON.parse(
      atob(idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
    )
    return {
      email: (payload.email as string) ?? null,
      groups: (payload["cognito:groups"] as string[]) ?? [],
    }
  } catch {
    return { email: null, groups: [] }
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [groups, setGroups] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const isAdmin = groups.includes("admin")

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
        const { email: userEmail, groups: userGroups } = decodeIdToken(it)
        setAccessToken(at)
        setEmail(userEmail)
        setGroups(userGroups)
      }
      setLoading(false)
    })
  }, [])

  function onLoginSuccess(at: string, it: string) {
    const { email: userEmail, groups: userGroups } = decodeIdToken(it)
    setAccessToken(at)
    setEmail(userEmail)
    setGroups(userGroups)
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
    setGroups([])
  }

  return (
    <AuthContext.Provider value={{ accessToken, email, groups, isAdmin, loading, onLoginSuccess, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
