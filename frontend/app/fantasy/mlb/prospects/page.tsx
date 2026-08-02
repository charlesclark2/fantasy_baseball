"use client"

// E8.1 — MLB dynasty Prospect Board (browse).
//
// 🔒 ADMIN ONLY while the surface is in development (operator, 2026-08-02) — `AdminGuard`, NOT
// `FantasyGuard`. FantasyGuard grants `subscriber` + `admin` + `fantasy_comp` (E9.45), which would
// put an unfinished surface in front of every paying subscriber. The server enforces the same rule
// (`get_admin_user` on /fantasy/mlb/prospects/*), so this is defence in depth, not the only gate —
// and the API is what actually keeps the data from an unentitled client (E9.56 / NF-C6).
//
// ⏭️ Opening this up later means changing FOUR things together: this guard, the sibling
// disagreements page, `restrict: "admin"` in nav-model.ts, and `get_admin_user` on the routes.

import { Nav } from "@/components/nav"
import { AdminGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { ProspectBoard } from "@/components/fantasy/prospect-board"

export default function MlbProspectBoardPage() {
  const { email } = useAuth()
  return (
    <AdminGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="mlb-prospects" userEmail={email} />
        <ProspectBoard view="board" />
      </div>
    </AdminGuard>
  )
}
