"use client"

// NF-C4 — the Custom Big Board. Gated by `FantasyGuard`, the SAME entitlement as the live snake
// Draft Optimizer and the Auction Optimizer it sits beside (`subscriber` + `admin` + the
// `fantasy_comp` allow-list, NOT beta_tester).
//
// ⛔ NEVER `FantasyPublicGuard`. It reads the same 403-ing gated board endpoints AND its own
// per-user `/fantasy/nfl/custom-boards`, so a public wrapper here would render a permanently broken
// page rather than a free one — and would advertise a saved-board surface to a caller with no
// entitlement to store one. Membership of the gated set is pinned both ways by
// `betting_ml/tests/test_freemium_tier.py`.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { BigBoard } from "@/components/fantasy/big-board"

export default function FantasyBigBoardPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a] print:min-h-0 print:bg-white">
        {/* ⚠️ THE NAV DOES NOT BELONG ON PAPER. `window.print()` prints the PAGE, so without this
            the printed cheat sheet opens with a logo, a sign-out link and a row of section tabs —
            reported on the live surface. Hidden HERE rather than inside `Nav`, because every other
            page's print behaviour is not this story's to decide. */}
        <div className="print:hidden">
          <Nav authenticated activeLink="fantasy-big-board" userEmail={email} />
        </div>
        <BigBoard />
      </div>
    </FantasyGuard>
  )
}
