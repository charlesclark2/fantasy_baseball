// SEO posture for the PUBLIC Player Search surface (freemium build, 2026-08-08).
//
// 🚦 OPERATOR DECISION, STATED RATHER THAN INHERITED — the same discipline the Rankings and
// Projections layouts beside this one record. DECISION: INDEX the search page, follow its links.
//
// ⭐ THE ROLE THIS PAGE PLAYS IS DIFFERENT FROM THE OTHER TWO, and it is why `follow` matters more
// than `index` here. Rankings and Projections are destinations a searcher lands on. This one is the
// only route to a player page that does not begin on a board — so its real SEO job is to be a
// crawlable INDEX of those pages, letting a crawler reach every player from one place rather than
// only through the paginated boards. A `noindex, nofollow` here would leave the player pages
// discoverable only via board pagination, which is exactly the shape crawlers traverse worst.
//
// The page itself is a search box over the free projections payload, so a crawler sees a thin page
// with a lot of outbound links. That is a legitimate index page, not thin content — but if search
// ever treats it as the latter, `index: false, follow: true` keeps the link-graph benefit while
// dropping the page itself, and is the first thing to try before removing it from the crawl.
//
// A separate `layout.tsx` is required because `page.tsx` is a client component ("use client") and
// Next.js only honours `metadata` exported from a server component.

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "NFL Fantasy Player Search | Credence Sports",
  description:
    "Look up any 2026 NFL fantasy player — projection, 80% range, rank and market ADP. Free, no account needed.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/players" },
  openGraph: {
    title: "NFL Fantasy Player Search | Credence Sports",
    description:
      "Search any player and see our 2026 projection with an honest range beside the market's ADP.",
  },
}

export default function PlayerSearchLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
