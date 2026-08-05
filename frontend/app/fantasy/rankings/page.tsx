"use client"

// NF3 — NFL fantasy Rankings (browse), format-selectable.
//
// E9.56b: PUBLIC (`FantasyPublicGuard`). The SERVER decides per point what this caller sees — an
// entitled caller gets the real board; everyone else gets the same players with every model value
// removed, `locked: true` in its place, and the rows re-ordered onto market ADP. Bouncing a free
// user to /login here would defeat the freemium funnel: a locked point must render a "subscribe to
// unlock" CTA, and a redirect is exactly the "blank or absent" that rule rejects.

import { Nav } from "@/components/nav"
import { FantasyPublicGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { RankingsBoard } from "@/components/fantasy/rankings-board"

export default function FantasyRankingsPage() {
  const { accessToken, email } = useAuth()
  return (
    <FantasyPublicGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        {/* `authenticated` is now CONDITIONAL — a logged-out visitor needs a Login affordance, not
            signed-in chrome. Mirrors the NF3.2 player route. */}
        <Nav authenticated={!!accessToken} activeLink="fantasy-rankings" userEmail={email} />
        <RankingsBoard />
      </div>
    </FantasyPublicGuard>
  )
}
