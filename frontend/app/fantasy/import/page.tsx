"use client"

// NF-C0 — Platform league import. The CONVENIENCE path over NF-C0b's manual editor: pull the user's
// real league (settings, rosters, live draft state) straight from Sleeper or Yahoo.
//
// 🔒 G100-C1 — gated by `FantasyLeagueGuard`: signed in + a personalization quota above zero, which
// is every signed-in account (the free quota is 1). It was `FantasyBetaGuard` (`admin` +
// `fantasy_comp` only); import is one of the two ways a free account configures its one league, so
// keeping it on a group list would have left the free tier with only the manual editor.
// `/fantasy/import/*` enforces the same rule server-side; since importing WRITES a league config,
// that is the real gate and this is cosmetic. The COUNT is enforced where a league is SAVED.
//
// ⚠️ Suspense boundary is REQUIRED, not stylistic: the Yahoo OAuth callback returns the browser here
// with a `?yahoo=…` flag, so the component reads `useSearchParams`, and Next's App Router refuses to
// statically render a page that does so outside Suspense.

import { Suspense } from "react"
import { Nav } from "@/components/nav"
import { FantasyLeagueGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { LeagueImport } from "@/components/fantasy/league-import"
import { LoadingBlock } from "@/components/fantasy/shared"

export default function FantasyImportPage() {
  const { email } = useAuth()
  return (
    <FantasyLeagueGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-import" userEmail={email} />
        <Suspense fallback={<LoadingBlock label="Loading import…" />}>
          <LeagueImport />
        </Suspense>
      </div>
    </FantasyLeagueGuard>
  )
}
