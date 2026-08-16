"use client"

// G100-C1 — My League. The ACTIVATION screen: a free account's one personalized board, led by the
// generic-vs-your-league delta.
//
// 🔒 Gated by `FantasyLeagueGuard` — signed in + a personalization quota above zero, which is every
// signed-in account (the free quota is 1). Deliberately NOT `FantasyGuard`: gating this on fantasy
// entitlement would 403 exactly the users the free tier exists for.
//
// ⛔ NOT `FantasyPublicGuard` either, and this is the line that matters. Everything on this page is
// computed from the caller's OWN saved league, so it is per-caller by construction — the opposite of
// the free board's byte-identity invariant. It must never join the CDN allowlist or the public cache
// rules; `/fantasy/nfl/my-teams` enforces the same gate server-side and answers `private, no-store`.

import { Suspense } from "react"
import { Nav } from "@/components/nav"
import { FantasyLeagueGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { MyLeague } from "@/components/fantasy/my-league"

export default function FantasyMyLeaguePage() {
  const { email } = useAuth()
  return (
    <FantasyLeagueGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-my-league" userEmail={email} />
        {/* G100-C2 — `MyLeague` reads `?league=` via `useSearchParams`, which Next.js requires to
            sit under a Suspense boundary at the page level. */}
        <Suspense
          fallback={
            <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-gray-500">Loading…</div>
          }
        >
          <MyLeague />
        </Suspense>
      </div>
    </FantasyLeagueGuard>
  )
}
