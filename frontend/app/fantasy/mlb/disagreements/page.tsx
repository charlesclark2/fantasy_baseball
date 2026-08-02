"use client"

// E8.1 — MLB prospect DISAGREEMENT view: the prospects our translated minor-league line ranks
// differently than the scouts' grade does. The differentiated read, and the MLB analog of the NFL
// fade view. Same gate and same data as the full board (one component, `view="disagreements"`).

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { ProspectBoard } from "@/components/fantasy/prospect-board"

export default function MlbProspectDisagreementsPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="mlb-disagreements" userEmail={email} />
        <ProspectBoard view="disagreements" />
      </div>
    </FantasyGuard>
  )
}
