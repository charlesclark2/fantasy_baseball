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

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "This Week's NFL Fantasy Projections | Credence Sports",
  description:
    "Our projected PPR points for every projected player this week, each with the 80% range around it and what is left of his season beside it.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/weekly" },
  openGraph: {
    title: "This Week's NFL Fantasy Projections | Credence Sports",
    description:
      "Weekly projections with an honest range on every number, conditioned on how players are actually being used.",
  },
}

export default function WeeklyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
