"use client"

// NCAAF-P3.3 — the team-page route. NCAAF is FREE (E9.45), so there is no `AuthGuard` and no
// `SubscriptionGate` here, deliberately and by the same pattern `/ncaaf/games` uses: the absence of
// a guard IS the entitlement decision, stated in one place.
//
// ⚠️ BEING PUBLIC IN THE APP IS NOT SUFFICIENT ON THE API SIDE. `/ncaaf/teams/{team_id}` needed its
// own API-Gateway route with `--authorization-type NONE` (NF3.2) — measured 401 until it was
// created on 2026-09-03. Nothing in this file can cause or cure that; it is recorded here because
// the symptom (a page that loads and reports "we could not reach the model") points at the client.
//
// ⭐ `activeLink` IS THE GAMES DOOR ON PURPOSE. The nav has one NCAAF entry, and a team page is a
// place inside that section rather than a sibling of it — leaving the highlight off entirely would
// make the whole sport look unselected while a reader stands inside it.

import { use } from "react"
import { Nav } from "@/components/nav"
import { useAuth } from "@/lib/auth-context"
import { NcaafTeamPageView } from "@/components/ncaaf/team-page"

export default function NcaafTeamRoute({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = use(params)
  const { accessToken, email } = useAuth()
  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Nav authenticated={!!accessToken} activeLink="ncaaf-games" userEmail={email} />
      <NcaafTeamPageView teamId={teamId} />
    </div>
  )
}
