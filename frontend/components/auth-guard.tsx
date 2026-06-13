"use client"

import React, { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (accessToken === null) router.push("/login")
  }, [accessToken])

  if (accessToken === null) return null
  return <>{children}</>
}
