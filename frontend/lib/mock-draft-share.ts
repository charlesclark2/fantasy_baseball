// mock-draft-share.ts — URL encoding for the post-draft SHARE card (NF-DS).
//
// There is no backend persistence for a shared mock-draft result (the mock never leaves the
// browser — see mock-draft.tsx's own header comment on what the tool touches server-side). So the
// whole share artifact is encoded into the URL's query string: the share PAGE and the share IMAGE
// route both decode the same params back into a `ShareSummary` and render from that alone. Neither
// one re-fetches gated `/fantasy/nfl/*` data — which is what keeps both of them safely PUBLIC (PM
// decision: the share artifact is public even though the draft tool itself is paid) without ever
// touching the API-Gateway authorizer (NF3.2) at all: they are plain Next.js routes with no backend
// call, not a Lambda route that would need `--authorization-type NONE`.
//
// A malformed/missing query string decodes to `null`, never a throw — a share link a bot or a
// crawler mangles, or a bare visit to `/fantasy/mock-draft/share`, must render a generic branded
// fallback, not a 500.

import type { ShareSteal, ShareSummary } from "./mock-draft"

export const SHARE_PAGE_PATH = "/fantasy/mock-draft/share"
export const SHARE_IMAGE_PATH = "/fantasy/mock-draft/share/image"

// The image URL an `<meta property="og:image">` / a copied link's preview needs to be fully
// qualified regardless of `metadataBase` (which this app does not set). No env var carries the
// production origin today — every other OG image in the app is still a bare relative path — so this
// is hardcoded against the verified production domain (infrastructure/aws_resources.md) rather than
// inventing a config surface for one feature.
const SHARE_SITE_ORIGIN = "https://www.credencesports.com"

const MAX_STEALS = 3

export function summaryToSearchParams(s: ShareSummary): URLSearchParams {
  const p = new URLSearchParams()
  p.set("r", String(Math.round(s.rank)))
  p.set("n", String(Math.round(s.nTeams)))
  p.set("pts", String(Math.round(s.starterPoints)))
  p.set("med", String(Math.round(s.roomMedian)))
  p.set("lg", s.leagueLabel)
  if (s.bestPosition) {
    p.set("bp", s.bestPosition.pos)
    p.set("bpd", String(Math.round(s.bestPosition.delta)))
  }
  s.steals.slice(0, MAX_STEALS).forEach((st, i) => {
    p.set(`stn${i}`, st.name)
    p.set(`stp${i}`, st.pos)
    p.set(`stv${i}`, String(Math.round(st.value)))
  })
  return p
}

/** The inverse of {@link summaryToSearchParams}. Returns `null` if the query string does not carry
 *  the required fields — never throws, and never fabricates a value for a missing one. */
export function parseShareSummary(params: URLSearchParams): ShareSummary | null {
  const rank = Number(params.get("r"))
  const nTeams = Number(params.get("n"))
  const starterPoints = Number(params.get("pts"))
  const roomMedian = Number(params.get("med"))
  const leagueLabel = params.get("lg")
  if (
    !Number.isFinite(rank) ||
    !Number.isFinite(nTeams) ||
    !Number.isFinite(starterPoints) ||
    !Number.isFinite(roomMedian) ||
    !leagueLabel
  ) {
    return null
  }

  const bpPos = params.get("bp")
  const bpd = Number(params.get("bpd"))
  const bestPosition = bpPos && Number.isFinite(bpd) ? { pos: bpPos, delta: bpd } : null

  const steals: ShareSteal[] = []
  for (let i = 0; i < MAX_STEALS; i++) {
    const name = params.get(`stn${i}`)
    const pos = params.get(`stp${i}`)
    const value = Number(params.get(`stv${i}`))
    if (!name || !pos || !Number.isFinite(value)) continue
    steals.push({ name, pos, value })
  }

  return { rank, nTeams, starterPoints, roomMedian, leagueLabel, bestPosition, steals }
}

/** Path-only (no origin) — what the in-app modal's `<img>` preview should use. A relative URL
 *  resolves against whatever origin actually served the page (localhost, a Vercel preview, prod),
 *  where `SHARE_SITE_ORIGIN` would be wrong everywhere except prod. */
export function shareImagePath(summary: ShareSummary): string {
  return `${SHARE_IMAGE_PATH}?${summaryToSearchParams(summary).toString()}`
}

/** Path-only share-page link, for any in-app `<Link>`. */
export function sharePagePath(summary: ShareSummary): string {
  return `${SHARE_PAGE_PATH}?${summaryToSearchParams(summary).toString()}`
}

/** Fully-qualified share-page URL — what gets copied to the clipboard and passed to
 *  `navigator.share`, since a link handed to another person must not be relative. */
export function sharePageUrl(summary: ShareSummary): string {
  return `${SHARE_SITE_ORIGIN}${sharePagePath(summary)}`
}

/** Fully-qualified image URL — what `generateMetadata`'s `openGraph.images` needs, independent of
 *  `metadataBase` (unset at the root layout). */
export function shareImageUrl(summary: ShareSummary): string {
  return `${SHARE_SITE_ORIGIN}${shareImagePath(summary)}`
}

/** The image route with no query string — the generic branded placeholder the route renders for a
 *  malformed/missing link (its own `parseShareSummary(...) === null` branch). Used as the OG-image
 *  fallback so a mangled share link still previews something, never a broken image. */
export function genericShareImageUrl(): string {
  return `${SHARE_SITE_ORIGIN}${SHARE_IMAGE_PATH}`
}
