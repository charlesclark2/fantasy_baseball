"use client"

import { createContext, useContext, useState } from "react"
import { queryClient } from "@/lib/query-client"

type AuthCtx = {
  accessToken: string | null
  email: string | null
  onLoginSuccess: (at: string, it: string) => void
  signOut: () => void
}

export const AuthContext = createContext<AuthCtx>({
  accessToken: null,
  email: null,
  onLoginSuccess: () => {},
  signOut: () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)

  function onLoginSuccess(at: string, it: string) {
    const payload = JSON.parse(
      atob(it.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
    )
    setAccessToken(at)
    setEmail((payload.email as string) ?? null)
  }

  function signOut() {
    queryClient.clear()
    setAccessToken(null)
    setEmail(null)
  }

  return (
    <AuthContext.Provider value={{ accessToken, email, onLoginSuccess, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
