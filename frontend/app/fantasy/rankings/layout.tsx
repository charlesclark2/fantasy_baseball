// SEO posture for the PUBLIC Rankings surface.
//
// 🚦 OPERATOR DECISION, 2026-08-05, re-affirmed 2026-08-08: INDEX IT. Same reasoning as the
// Projections layout beside this one — see that file's header, including why the freemium build
// retired the thin-content condition that used to qualify this decision.
//
// A separate `layout.tsx` is required because `page.tsx` is a client component ("use client") and
// Next.js only honours `metadata` exported from a server component.

import type { Metadata } from "next"

export const metadata: Metadata = {
  // ⚠️ The description promises the FREE thing, not the paid one. It used to say "re-scored for
  // your league's format and roster" — which is now the PERSONALIZATION half, behind the paywall.
  // A meta description that pitches the paid feature on the free page is the ordinary way a
  // freemium funnel earns a bounce.
  title: "2026 NFL Fantasy Rankings | Credence Sports",
  description:
    "Free 2026 NFL fantasy rankings for the common league formats — every player, an 80% range on each projection, and market ADP beside it.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/rankings" },
  openGraph: {
    title: "2026 NFL Fantasy Rankings | Credence Sports",
    description:
      "Free rankings with an honest range on every number, and a public record of how they have done against ADP.",
  },
}

export default function RankingsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
