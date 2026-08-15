"use client"

// NF-C6P2 — Post-Draft Roster Report. The monetization bridge for the post-draft window.
//
// 🔒 `FantasyLeagueGuard` — signed in with a personalization quota above zero, which is every
// signed-in account (the free quota is 1). Deliberately NOT `FantasyGuard`: this is the surface that
// SELLS the fantasy entitlement, so gating it on that entitlement would hide it from precisely the
// users it exists to convert. `/fantasy/nfl/league-board` enforces ownership and the quota
// server-side, so the client guard is defence in depth rather than the only gate.
//
// ⛔ NOT `FantasyPublicGuard`. Everything here is computed from the caller's own saved league, so it
// is per-caller by construction — the opposite of the free board's byte-identity invariant. It must
// never join the CDN allowlist or `cost_guardrails._PUBLIC_CACHE_RULES`; every request it makes
// carries `Authorization`, and `cache_control_for` answers `private, no-store` on any such request.

import { Nav } from "@/components/nav"
import { FantasyLeagueGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { RosterReport } from "@/components/fantasy/roster-report"

export default function FantasyRosterReportPage() {
  const { email } = useAuth()
  return (
    <FantasyLeagueGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-roster-report" userEmail={email} />
        <RosterReport />
      </div>
    </FantasyLeagueGuard>
  )
}
