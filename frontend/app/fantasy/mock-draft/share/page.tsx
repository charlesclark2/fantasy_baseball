// The PUBLIC share landing page for a mock-draft result (NF-DS). Deliberately outside `FantasyGuard`
// — PM decision: the share artifact is public and branded even though the mock-draft tool itself is
// paid. Nothing here fetches gated data; the whole render is a pure function of its own query
// string (see the header comment in lib/mock-draft-share.ts), which is what makes that safe.

import type { Metadata } from "next"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { GRADE_CIRCULARITY_NOTE, SHARE_CARD_CAPTION, ordinal } from "@/lib/mock-draft"
import { genericShareImageUrl, parseShareSummary, shareImagePath, shareImageUrl } from "@/lib/mock-draft-share"

type SearchParams = Promise<Record<string, string | string[] | undefined>>

function toURLSearchParams(sp: Record<string, string | string[] | undefined>): URLSearchParams {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(sp)) {
    if (typeof v === "string") p.set(k, v)
  }
  return p
}

export async function generateMetadata({
  searchParams,
}: {
  searchParams: SearchParams
}): Promise<Metadata> {
  const summary = parseShareSummary(toURLSearchParams(await searchParams))
  const title = summary
    ? `${ordinal(summary.rank)} of ${summary.nTeams} — Mock Draft Grade | Credence Sports`
    : "NFL Fantasy Mock Draft | Credence Sports"
  const description = summary
    ? `${summary.starterPoints.toLocaleString()} projected starter points, ${ordinal(summary.rank)} of ${summary.nTeams} in a ${summary.leagueLabel} mock draft. Free to try.`
    : "Practice a full fantasy football draft against CPU opponents and see how the room grades out — free."
  const images = [summary ? shareImageUrl(summary) : genericShareImageUrl()]
  return {
    title,
    description,
    // Ephemeral, per-share content — not worth indexing on its own, but the CTA link below should
    // still pass link equity to the actual product page (mirrors the Player Search layout's
    // index/follow split).
    robots: { index: false, follow: true },
    openGraph: { title, description, images },
    twitter: { card: "summary_large_image", title, description, images },
  }
}

export default async function MockDraftSharePage({ searchParams }: { searchParams: SearchParams }) {
  const summary = parseShareSummary(toURLSearchParams(await searchParams))

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Nav />
      <main className="mx-auto max-w-2xl px-4 py-12">
        {summary ? (
          <>
            <h1 className="text-xl font-semibold text-white">
              {ordinal(summary.rank)} of {summary.nTeams} in a {summary.leagueLabel} mock draft
            </h1>
            <img
              src={shareImagePath(summary)}
              alt={`Mock draft grade — ${ordinal(summary.rank)} of ${summary.nTeams}, ${summary.starterPoints.toLocaleString()} projected points`}
              width={1200}
              height={630}
              className="mt-4 w-full rounded-lg border border-[#262626]"
            />
            {/* Rendered as real text, not just baked into the image's pixels — so the caption
                survives an image load failure and is legible to a screen reader. */}
            <p className="mt-2 text-xs text-gray-500">{SHARE_CARD_CAPTION}</p>
          </>
        ) : (
          <>
            <h1 className="text-xl font-semibold text-white">NFL Fantasy Mock Draft</h1>
            <p className="mt-2 text-sm text-gray-400">
              This share link is missing or malformed, but the mock draft simulator is free to try.
            </p>
          </>
        )}

        {/* ⚠️ NOT OPTIONAL, AND NOT BEHIND A CLICK — same discipline as GradeCard's own
            GRADE_CIRCULARITY_NOTE render. A visitor who never touched the tool is reading a rank a
            stranger got, so the caveat matters here at least as much as it does in-app. */}
        <p className="mt-4 rounded-md border border-[#262626] bg-[#141414] px-3 py-2.5 text-xs leading-relaxed text-gray-400">
          {GRADE_CIRCULARITY_NOTE}
        </p>

        <div className="mt-6">
          <Link
            href="/fantasy/mock-draft"
            className="inline-flex items-center rounded-md bg-[#10b981] px-4 py-2 text-sm font-semibold text-[#0a0a0a] hover:bg-[#059669]"
          >
            Draft your own room
          </Link>
        </div>
      </main>
    </div>
  )
}
