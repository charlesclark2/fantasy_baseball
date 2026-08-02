"use client"

// NF3.2 — the fantasy football past-season track record ("receipts"). Deliberately PUBLIC: no
// FantasyGuard here, unlike every other /fantasy/* route. See track-record-page.tsx's module
// docstring for why that is safe (the data it fetches can never be the current/locked season).

import { Nav } from "@/components/nav"
import { useAuth } from "@/lib/auth-context"
import { FantasyTrackRecordPage } from "@/components/fantasy/track-record-page"

export default function FantasyTrackRecordRoute() {
  const { accessToken, email } = useAuth()
  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Nav authenticated={!!accessToken} activeLink="fantasy-track-record" userEmail={email} />
      <FantasyTrackRecordPage />
    </div>
  )
}
