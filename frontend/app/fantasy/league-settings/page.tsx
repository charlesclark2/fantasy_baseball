"use client"

// NF-C0b — Manual league-settings editor. The customization FLOOR beneath platform import: when we
// cannot pull a league (private, long-tail platform, fragile ESPN endpoint), the user hand-enters it
// and every fantasy tool works the same.
//
// 🔒 Gated by FantasyBetaGuard — `admin` + `fantasy_comp` ONLY, narrower than the fantasy surface
// (a paying subscriber does not get the editor yet). The /fantasy/leagues endpoints enforce the same
// rule server-side; since these are WRITE endpoints, that is the real gate, not this.

import { Nav } from "@/components/nav"
import { FantasyBetaGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { LeagueSettingsEditor } from "@/components/fantasy/league-settings-editor"

export default function FantasyLeagueSettingsPage() {
  const { email } = useAuth()
  return (
    <FantasyBetaGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-league-settings" userEmail={email} />
        <LeagueSettingsEditor />
      </div>
    </FantasyBetaGuard>
  )
}
