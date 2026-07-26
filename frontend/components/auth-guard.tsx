"use client"

import React, { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { canAccess } from "@/lib/entitlements"
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

// Fantasy surface gate (E9.45). A signed-in caller without fantasy entitlement
// (subscriber / admin / fantasy_comp) is bounced to /subscribe — the upsell. A
// beta_tester is deliberately NOT entitled here (they keep full betting access).
// This is the client half of a defense-in-depth pair: the fantasy DATA endpoints
// enforce the same rule server-side (403), so hiding the page is not the only gate.
export function FantasyGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, groups, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (loading) return
    if (accessToken === null) { router.push("/login"); return }
    if (!canAccess("fantasy", groups)) { router.push("/subscribe"); return }
  }, [loading, accessToken, groups, router])

  if (loading || accessToken === null || !canAccess("fantasy", groups)) return null
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
