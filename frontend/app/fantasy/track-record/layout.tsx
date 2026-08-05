// E9.56b — SEO metadata for the PAST-SEASON TRACK RECORD (NF3.2's "receipts").
//
// This page was already public and already indexable (nothing excluded it), but it carried no
// metadata of its own, so it inherited the root "Credence Sports" title and description. That is a
// weak posture for what is, by some distance, the strongest SEO surface the fantasy product has:
// six seasons of our projection against that season's preseason ADP against the realized outcome,
// with the honest headline computed from the scorecard's own numbers.
//
// The operator's 2026-08-05 decision to INDEX the locked Projections/Rankings pages rested on the
// receipts being what makes those pages worth landing on — so leaving the receipts themselves
// generically titled would have undercut the decision it was justified by.
//
// ⚠️ CLAIM SCOPE (NF-D3): this is a PROJECTION product. The copy below describes a measured
// ordering correlation against ADP and nothing more — no win rate, no edge, no profit claim. Keep
// any future edit inside that boundary; the page's own headline is generated from the model's
// numbers precisely so marketing copy cannot drift away from what was measured.

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "NFL Fantasy Projection Track Record, 2019–2025 | Credence Sports",
  description:
    "Six seasons of our preseason NFL fantasy projections, shown against that season's ADP and the outcome that actually happened. Free, per player, every season.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/fantasy/track-record" },
  openGraph: {
    title: "NFL Fantasy Projection Track Record, 2019–2025",
    description:
      "Our projection vs preseason ADP vs what actually happened — six seasons, per player, free.",
  },
}

export default function TrackRecordLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
