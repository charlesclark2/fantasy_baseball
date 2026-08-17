"use client"

// NFL Fantasy Auction Optimizer (NF-C5). Gated by `FantasyGuard` — the SAME entitlement as the live
// snake Draft Optimizer (`subscriber` + `admin` + the `fantasy_comp` allow-list, NOT beta_tester).
// It reads the same server-side-gated /fantasy/nfl/* board endpoints, so a public wrapper here
// would render a permanently broken page rather than a free one.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { AuctionOptimizer } from "@/components/fantasy/auction-optimizer"

export default function FantasyAuctionPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-auction" userEmail={email} />
        <AuctionOptimizer />
      </div>
    </FantasyGuard>
  )
}
