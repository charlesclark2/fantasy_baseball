"use client"

// NF-C0b — Manual league-settings editor. The customization FLOOR beneath platform import: when we
// cannot pull a league (private, long-tail platform, fragile ESPN endpoint), the user hand-enters it
// and every fantasy tool works the same.
//
// 🔒 G100-C1 — gated by `FantasyLeagueGuard`: signed in + a personalization quota above zero, which
// is every signed-in account (the free quota is 1). It was `FantasyBetaGuard` (`admin` +
// `fantasy_comp` only, so not even a paying subscriber had the editor); the free tier's one league
// has to be configurable, and a paid account can never have less than a free one. The
// /fantasy/leagues endpoints enforce the same rule server-side, and the COUNT on `POST` — since
// these are WRITE endpoints, that is the real gate, not this.

import { Nav } from "@/components/nav"
import { FantasyLeagueGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { LeagueSettingsEditor } from "@/components/fantasy/league-settings-editor"

export default function FantasyLeagueSettingsPage() {
  const { email } = useAuth()
  return (
    <FantasyLeagueGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-league-settings" userEmail={email} />
        <LeagueSettingsEditor />
      </div>
    </FantasyLeagueGuard>
  )
}
