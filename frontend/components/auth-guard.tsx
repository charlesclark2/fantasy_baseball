"use client"

import React, { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && accessToken === null) router.push("/login")
  }, [loading, accessToken])

  if (loading || accessToken === null) return null
  return <>{children}</>
}
