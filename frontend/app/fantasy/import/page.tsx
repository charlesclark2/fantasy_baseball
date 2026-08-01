"use client"

// NF-C0 — Platform league import. The CONVENIENCE path over NF-C0b's manual editor: pull the user's
// real league (settings, rosters, live draft state) straight from Sleeper or Yahoo.
//
// 🔒 Gated by FantasyBetaGuard — `admin` + `fantasy_comp` ONLY, matching the manual editor rather
// than the wider fantasy surface. `/fantasy/import/*` enforces the same rule server-side; since
// importing WRITES a league config, that is the real gate and this is cosmetic.
//
// ⚠️ Suspense boundary is REQUIRED, not stylistic: the Yahoo OAuth callback returns the browser here
// with a `?yahoo=…` flag, so the component reads `useSearchParams`, and Next's App Router refuses to
// statically render a page that does so outside Suspense.

import { Suspense } from "react"
import { Nav } from "@/components/nav"
import { FantasyBetaGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { LeagueImport } from "@/components/fantasy/league-import"
import { LoadingBlock } from "@/components/fantasy/shared"

export default function FantasyImportPage() {
  const { email } = useAuth()
  return (
    <FantasyBetaGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-import" userEmail={email} />
        <Suspense fallback={<LoadingBlock label="Loading import…" />}>
          <LeagueImport />
        </Suspense>
      </div>
    </FantasyBetaGuard>
  )
}
