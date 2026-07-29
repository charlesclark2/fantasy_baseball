"use client"

// NF3 — NFL fantasy Season Projections (browse). Gated by FantasyGuard: `subscriber` + `admin` +
// the `fantasy_comp` allow-list (E9.45). Data comes from the server-side-gated /fantasy/nfl/*
// endpoints, so the client gate is defence in depth rather than the only gate.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { ProjectionsTable } from "@/components/fantasy/projections-table"

export default function FantasyProjectionsPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-projections" userEmail={email} />
        <ProjectionsTable />
      </div>
    </FantasyGuard>
  )
}
