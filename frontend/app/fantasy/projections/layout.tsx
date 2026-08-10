// SEO posture for the PUBLIC Projections surface.
//
// 🚦 AN OPERATOR DECISION, RECORDED DELIBERATELY (2026-08-05, re-affirmed 2026-08-08) rather than
// inherited from Next.js's default. DECISION: INDEX IT.
//
// ⭐ THE FREEMIUM BUILD MADE THIS DECISION STRICTLY EASIER, and the reasoning is worth keeping
// because it inverts the old caveat. E9.56b indexed a LOCKED page — identity + market ADP with our
// numbers behind lock chips — and the note here warned that if it ever lost its receipts framing it
// would be thin content duplicating freely available ADP, at which point `index: false` was the
// better posture. That risk is GONE: the crawler now sees the real projections, the real ranges and
// the real ranks, which is genuinely differentiated content that exists nowhere else. The
// thin-content condition that would have reversed this decision can no longer arise.
//
// The funnel's job is unchanged — player-name search capture. Someone googling "Bijan Robinson 2026
// projection" lands here, gets a real answer, and meets the membership case below it.
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
