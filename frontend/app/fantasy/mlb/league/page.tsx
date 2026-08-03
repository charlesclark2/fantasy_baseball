"use client"

// E8.2 — MLB dynasty league setup (roster import + availability).
//
// 🔒 ADMIN ONLY, matching the E8.1 board this overlays — `AdminGuard`, NOT `FantasyGuard`.
// FantasyGuard grants subscriber + admin + fantasy_comp (E9.45), which would put an unfinished
// surface in front of every paying subscriber. The server enforces the same rule (`get_admin_user`
// on /fantasy/mlb/leagues*), so this is defence in depth, not the only gate.
//
// ⏭️ Opening this up later means changing the same FOUR things E8.1 lists: this guard, the board
// guards, `restrict: "admin"` in nav-model.ts, and `get_admin_user` on the routes.

import { Nav } from "@/components/nav"
import { AdminGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { MlbLeagueSetup } from "@/components/fantasy/mlb-league-setup"

export default function MlbLeaguePage() {
  const { email } = useAuth()
  return (
    <AdminGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="mlb-league" userEmail={email} />
        <MlbLeagueSetup />
      </div>
    </AdminGuard>
  )
}
