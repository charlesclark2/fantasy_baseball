"use client"

import React, { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { getMfaStatus, getSessionAuthMethod, subscriberMfaRequired } from "@/lib/cognito"

// Subscriber MFA enforcement (E9.19) — the SINGLE in-app gate that gates E9.8 go-live.
// No-op in beta (NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA unset). When flipped on at Stripe
// launch: a `subscriber` who signed in with a password and hasn't enrolled TOTP is
// bounced to Settings to enroll. Google sessions are exempt (IdP MFA) — keyed off the
// session's auth METHOD, not a per-sub flag (post-E9.7 a linked user has both).
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, groups, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && accessToken === null) router.push("/login")
  }, [loading, accessToken])

  useEffect(() => {
    if (loading || accessToken === null) return
    if (!subscriberMfaRequired(groups)) return
    if (getSessionAuthMethod() === "google") return
    let cancelled = false
    getMfaStatus()
      .then((status) => {
        if (!cancelled && !status.federated && !status.enabled) {
          router.push("/settings?mfa=required")
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [loading, accessToken, groups, router])

  if (loading || accessToken === null) return null
  return <>{children}</>
}

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, isAdmin, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (loading) return
    if (accessToken === null) { router.push("/login"); return }
    if (!isAdmin) { router.push("/dashboard"); return }
  }, [loading, accessToken, isAdmin])

  if (loading || accessToken === null || !isAdmin) return null
  return <>{children}</>
}
