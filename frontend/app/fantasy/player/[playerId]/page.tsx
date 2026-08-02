"use client"

// NF3.1 — NFL fantasy per-player drill-down.
//
// NF3.2 season-scoped entitlement: this route is now PUBLIC (no FantasyGuard) — a visitor with no
// fantasy entitlement sees the player's identity + past-season track record (public data), with the
// current-season projection rendered as a locked upsell instead of fetched. An entitled caller sees
// exactly what this page has always shown. See `FantasyPlayerPage`'s module docstring.

import { Nav } from "@/components/nav"
import { useAuth } from "@/lib/auth-context"
import { FantasyPlayerPage } from "@/components/fantasy/player-page"

export default function FantasyPlayerRoute() {
  const { accessToken, email } = useAuth()
  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Nav authenticated={!!accessToken} userEmail={email} />
      <FantasyPlayerPage />
    </div>
  )
}
