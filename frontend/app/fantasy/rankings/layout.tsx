// E9.56b — SEO posture for the PUBLIC (locked) Rankings surface.
//
// 🚦 OPERATOR DECISION, 2026-08-05: INDEX IT. Same reasoning as the Projections layout beside this
// one — see that file's header for the full rationale and for the condition under which this should
// be revisited (if the locked view ever stops leading with the past-season receipts, a page that is
// only market ADP plus lock icons is thin-content and `index: false` becomes the better call).
//
// A separate `layout.tsx` is required because `page.tsx` is a client component ("use client") and
// Next.js only honours `metadata` exported from a server component.

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "2026 NFL Fantasy Rankings | Credence Sports",
  description:
    "2026 NFL fantasy rankings re-scored for your league's format and roster, with a six-season public track record against preseason ADP.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/rankings" },
  openGraph: {
    title: "2026 NFL Fantasy Rankings | Credence Sports",
    description:
      "Rankings for your league's exact format, and a six-season public record of how they have done against ADP.",
  },
}

export default function RankingsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
