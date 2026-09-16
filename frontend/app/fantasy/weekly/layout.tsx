// SEO posture for the PUBLIC weekly surface.
//
// DECISION: INDEX IT — the same reasoning the Projections layout records, and it applies more
// strongly here. The crawler sees real weekly projections with real ranges, which exists nowhere
// else; the search intent ("<player> week <n> projection") is one of the highest-volume queries in
// fantasy football and it recurs every week of the season rather than once a summer.
//
// ⛔ NO `alternates.canonical` POINTING AT A WEEK. The route serves whatever week the published
// pointer names and takes no week in its path, so there is exactly one URL and it is this one.
// A canonical naming a week would go stale the moment the next build landed.
//
// A separate `layout.tsx` is required because `page.tsx` is a client component ("use client") and
// Next.js only honours `metadata` exported from a server component.

//
// ⚠️ NF-INC-0916 — THE DESCRIPTION IS FLAG-DRIVEN, because a page description is a CLAIM about what
// the page contains and the ordinary one is currently false. While the weekly numbers are withheld,
// a search result promising "projected PPR points … with the 80% range around it" would be us
// making, in the one place a reader meets before he arrives, exactly the assertion the page itself
// declines to make. The flag is the same single constant the page reads, so the reversal stays one
// line rather than growing a second thing to remember.
//
// ⭐ STILL INDEXED. The page remains truthful and useful — the rosters, opponents, byes, evidence
// base and absence counts are all unaffected — and de-indexing it would also lose the standing it
// has earned for the week it comes back. What changes is what we promise, not whether we are here.
//
// ⛔ `weekly-suppression.ts` carries NO `"use client"` directive, which is why its constant can be
// read from this SERVER component at all: a constant imported from a `"use client"` module resolves
// to a client REFERENCE in a server component and arrives `undefined`, with `tsc` and `next build`
// both silent (the G100-D0 landmine).

import type { Metadata } from "next"
import { WEEKLY_NUMBERS_WITHHELD } from "@/lib/weekly-suppression"

const TITLE = "This Week's NFL Fantasy Projections | Credence Sports"

const DESCRIPTION = WEEKLY_NUMBERS_WITHHELD
  ? "Our weekly projected points are withheld while we correct a fault in the data the model trains on. The week's rosters, opponents, byes and who we are not projecting are all still here."
  : "Our projected PPR points for every projected player this week, each with the 80% range around it and what is left of his season beside it."

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/weekly" },
  openGraph: {
    title: TITLE,
    description: WEEKLY_NUMBERS_WITHHELD
      ? DESCRIPTION
      : "Weekly projections with an honest range on every number, conditioned on how players are actually being used.",
  },
}

export default function WeeklyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
