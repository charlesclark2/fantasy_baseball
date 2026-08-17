"use client"

// NFL Mock Draft simulator (NF-C2.1) — practise a full draft against CPU opponents.
//
// ⛔ NOT PUBLIC. Same gate as the live Draft Optimizer it shares an engine with: `FantasyGuard`
// (subscriber + admin + the `fantasy_comp` allow-list). Its board data comes from the same
// server-side-gated `/fantasy/nfl/*` endpoints, which 403 a free caller — so marking this surface
// public would render a permanently broken page, not a free one (`test_freemium_tier.py` pins both
// halves).

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { MockDraft } from "@/components/fantasy/mock-draft"

export default function FantasyMockDraftPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-mock-draft" userEmail={email} />
        <MockDraft />
      </div>
    </FantasyGuard>
  )
}
