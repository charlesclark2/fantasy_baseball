// E9.56b — SEO posture for the PUBLIC (locked) Projections surface.
//
// 🚦 THIS IS AN OPERATOR DECISION, RECORDED DELIBERATELY (2026-08-05) rather than inherited from
// Next.js's default. The page is now crawlable, and what a crawler sees is the LOCKED view: every
// player's identity + market ADP, with our projections withheld behind lock chips.
//
// DECISION: INDEX IT. The freemium funnel's job is player-name search capture — someone googling
// "Bijan Robinson 2026 projection" should be able to land here, see that we have a number, and see
// the track-record evidence for why it is worth paying for. Two things make that defensible rather
// than thin-content spam: the page leads with the past-season receipts (a genuinely differentiated,
// genuinely free asset — 6 seasons of our projection vs ADP vs the realized outcome), and E9.56b
// truncates the ~632 undrafted rows that carried no market signal, so the indexed page is the ~226
// players anyone is actually searching for rather than a long empty tail.
//
// ⚠️ IF THE LOCKED VIEW EVER LOSES THE RECEIPTS FRAMING, REVISIT THIS. A page that is only market
// ADP plus lock icons is duplicative of freely available data and is exactly what search engines
// discount — at which point `robots: { index: false }` here, and letting `/fantasy/track-record`
// carry the funnel alone, is the better posture.
//
// A separate `layout.tsx` is required because `page.tsx` is a client component ("use client") and
// Next.js only honours `metadata` exported from a server component.

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "2026 NFL Fantasy Projections | Credence Sports",
  description:
    "Every projectable 2026 NFL fantasy player with an 80% range on his season total, measured against a six-season public track record versus preseason ADP.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/projections" },
  openGraph: {
    title: "2026 NFL Fantasy Projections | Credence Sports",
    description:
      "Projections with an honest range, and a six-season public record of how they have actually done against ADP.",
  },
}

export default function ProjectionsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
