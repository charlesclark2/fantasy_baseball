// The branded, downloadable PNG for a mock-draft share (NF-DS). Pure function of its own query
// string — parsed with the SAME `parseShareSummary` the share page uses, so the pixels and the page
// text can never drift onto two different readings of the same link. No data fetch, no auth: this
// is what keeps the route safely public without an API-Gateway route at all (see the header comment
// in lib/mock-draft-share.ts).
//
// `runtime = "edge"` is what next/og's ImageResponse is built for — no filesystem/DuckDB/Snowflake
// access happens here, so the edge runtime's restrictions cost nothing.
//
// ⚠️ satori (what ImageResponse renders through) supports a CONSTRAINED CSS subset — flexbox only,
// inline `style` objects, no Tailwind classes, and any element with more than one child must
// declare `display: flex` itself. Every node below is written to that constraint deliberately.

import { ImageResponse } from "next/og"
import { parseShareSummary } from "@/lib/mock-draft-share"
import { SHARE_CARD_CAPTION, ordinal, type ShareSummary } from "@/lib/mock-draft"

export const runtime = "edge"

const WIDTH = 1200
const HEIGHT = 630
const GREEN = "#10b981"
const BG = "#0a0a0a"
const BORDER = "#262626"
const GRAY = "#9ca3af"
const DIM = "#6b7280"

function signed(n: number): string {
  return n >= 0 ? `+${n}` : String(n)
}

function card(summary: ShareSummary | null) {
  if (!summary) {
    // A malformed/absent link — never a broken image, a generic branded placeholder instead.
    return (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: BG,
        }}
      >
        <div style={{ display: "flex", fontSize: 56, fontWeight: 700, color: GREEN }}>CREDENCE</div>
        <div style={{ display: "flex", marginTop: 16, fontSize: 28, color: GRAY }}>
          NFL Fantasy Mock Draft
        </div>
      </div>
    )
  }

  const { rank, nTeams, starterPoints, roomMedian, leagueLabel, bestPosition, steals } = summary
  const vsMedian = starterPoints - roomMedian

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: BG,
        padding: "56px 64px",
      }}
    >
      {/* Wordmark */}
      <div style={{ display: "flex", fontSize: 30, fontWeight: 700, color: GREEN, letterSpacing: -1 }}>
        CREDENCE
      </div>

      {/* Rank */}
      <div style={{ display: "flex", flexDirection: "column", marginTop: 28 }}>
        <div style={{ display: "flex", fontSize: 88, fontWeight: 800, color: "#ffffff", lineHeight: 1 }}>
          {ordinal(rank)} of {nTeams}
        </div>
        <div style={{ display: "flex", marginTop: 10, fontSize: 26, color: GRAY }}>
          {leagueLabel} Mock Draft
        </div>
      </div>

      {/* Points */}
      <div style={{ display: "flex", marginTop: 24, fontSize: 30, color: "#ffffff" }}>
        {starterPoints.toLocaleString()} projected pts
        <span style={{ display: "flex", marginLeft: 12, color: vsMedian >= 0 ? GREEN : "#f59e0b" }}>
          {signed(vsMedian)} vs room median
        </span>
      </div>

      {/* Chips */}
      {(bestPosition || steals.length > 0) && (
        <div style={{ display: "flex", flexDirection: "row", flexWrap: "wrap", marginTop: 28, gap: 12 }}>
          {bestPosition && (
            <div
              style={{
                display: "flex",
                border: `1px solid ${GREEN}55`,
                backgroundColor: `${GREEN}1a`,
                color: GREEN,
                borderRadius: 8,
                padding: "10px 16px",
                fontSize: 22,
              }}
            >
              Strongest: {bestPosition.pos} ({signed(bestPosition.delta)})
            </div>
          )}
          {steals[0] && (
            <div
              style={{
                display: "flex",
                border: `1px solid ${BORDER}`,
                backgroundColor: "#141414",
                color: "#ffffff",
                borderRadius: 8,
                padding: "10px 16px",
                fontSize: 22,
              }}
            >
              Best value: {steals[0].name} ({steals[0].pos}) {signed(steals[0].value)}
            </div>
          )}
        </div>
      )}

      {/* Caption + domain, pinned to the bottom */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          marginTop: "auto",
          borderTop: `1px solid ${BORDER}`,
          paddingTop: 20,
        }}
      >
        <div style={{ display: "flex", fontSize: 18, color: DIM }}>{SHARE_CARD_CAPTION}</div>
        <div style={{ display: "flex", marginTop: 6, fontSize: 16, color: DIM }}>credencesports.com</div>
      </div>
    </div>
  )
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const summary = parseShareSummary(searchParams)
  return new ImageResponse(card(summary), { width: WIDTH, height: HEIGHT })
}
