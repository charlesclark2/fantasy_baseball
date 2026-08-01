"use client"

// NF-C0b — Manual league-settings editor. The customization FLOOR beneath platform import: when we
// cannot pull a league (private, long-tail platform, fragile ESPN endpoint), the user hand-enters it
// and every fantasy tool works the same. Gated by FantasyGuard (E9.45); the settings themselves are
// persisted through the server-side-gated /fantasy/leagues endpoints.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { LeagueSettingsEditor } from "@/components/fantasy/league-settings-editor"

export default function FantasyLeagueSettingsPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-league-settings" userEmail={email} />
        <LeagueSettingsEditor />
      </div>
    </FantasyGuard>
  )
}
