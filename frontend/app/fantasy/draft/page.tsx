"use client"

// NFL Fantasy Draft Optimizer (NF-C2 / MVP-3). Admin-only to start (gated by AdminGuard) — the live
// draft tool the operator uses for the 8/22 draft; widened to subscribers later.

import { Nav } from "@/components/nav"
import { AdminGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { DraftOptimizer } from "@/components/fantasy/draft-optimizer"

export default function FantasyDraftPage() {
  const { email } = useAuth()
  return (
    <AdminGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-draft" userEmail={email} />
        <DraftOptimizer />
      </div>
    </AdminGuard>
  )
}
