"use client"

// E8.1 — MLB dynasty Prospect Board (browse). Gated by FantasyGuard: `subscriber` + `admin` + the
// `fantasy_comp` allow-list (E9.45). The data comes from the server-side-gated
// /fantasy/mlb/prospects/* endpoints, so this client gate is defence in depth rather than the only
// gate — the current-season board is the paid product and is never shipped to an unentitled client
// (E9.56 / NF-C6).

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { ProspectBoard } from "@/components/fantasy/prospect-board"

export default function MlbProspectBoardPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="mlb-prospects" userEmail={email} />
        <ProspectBoard view="board" />
      </div>
    </FantasyGuard>
  )
}
