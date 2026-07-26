"use client"

// NFL Fantasy Draft Optimizer (NF-C2 / MVP-3). The FIRST launchable fantasy surface (E9.45):
// gated by FantasyGuard — accessible to `subscriber` + `admin` + the `fantasy_comp` allow-list
// (NOT beta_tester). Non-entitled users are bounced to /subscribe (the upsell). Board DATA is
// fetched through the server-side-gated /fantasy/nfl/* endpoints, not the old public JSON.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { DraftOptimizer } from "@/components/fantasy/draft-optimizer"

export default function FantasyDraftPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-draft" userEmail={email} />
        <DraftOptimizer />
      </div>
    </FantasyGuard>
  )
}
