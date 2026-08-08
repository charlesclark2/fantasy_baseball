// G100-D1 — the CDN read path for the ANONYMOUS fantasy board.
//
// WHY THIS ROUTE EXISTS. The rankings / projections / player surfaces are client components that
// call the API Lambda directly, so before this every anonymous page view was one API Gateway
// request and one Lambda invocation. Once the free board is un-gated to anonymous traffic that
// scales linearly with visitors — and with bots, which do not stop at one view.
//
// The key observation: the LOCKED payload an anonymous caller receives is IDENTICAL for every
// anonymous caller. It is a pure function of the published S3 blob, with no per-user content at
// all. So it is cacheable exactly once for everybody. This handler fetches it and returns it with
// `s-maxage`, which Vercel's CDN honours — the first request in each window costs one function
// invocation and one Lambda call, and every subsequent view inside that window is served from the
// edge with NO function invocation and NO Lambda at all.
//
// Entitled callers do NOT come through here (see `lib/fantasy.ts` — the token-bearing path still
// goes straight to the API). That split is the whole design: one cacheable payload for the many,
// per-request Lambda for the few who pay.
//
// ───────────────────────────────────────────────────────────────────────────────────────────────
// THREE PROPERTIES THAT MAKE THIS SAFE
// ───────────────────────────────────────────────────────────────────────────────────────────────
//
// 1. ⭐ IT NEVER FORWARDS `Authorization`, UNCONDITIONALLY. This is the load-bearing one. If a
//    subscriber's token reached the upstream from here, the upstream would answer with the FULL
//    board and this handler would write that paid payload into a PUBLIC CDN entry keyed only on the
//    URL — served from then on to every anonymous visitor. That is a paid-data breach caused by a
//    proxy being helpful. The header is dropped rather than passed through, and a request that
//    arrives carrying one is still answered with the anonymous payload.
//
// 2. ⭐ IT IS AN ALLOWLIST, NOT A PROXY. A catch-all that forwarded any path would be an open
//    relay into our own API from a trusted origin, and would bypass the per-IP limiter's view of
//    the real client (every request would arrive from Vercel's egress). Only the three anonymous
//    board reads and the public track record are reachable, and their query parameters are
//    validated before they are used to build the upstream URL.
//
// 3. ⭐ IT NEVER CACHES A FAILURE OR AN EMPTY BODY (E9.26b). A wide lakehouse read that fails
//    inside the Lambda returns `[]` rather than raising, and a 404 is what a not-yet-published
//    export looks like. Pinning either into the CDN for the full window would turn a transient
//    blip into a blank board for everyone until it expired. Anything that is not a 200 with a
//    non-empty body is returned with `no-store`, so the next request retries.

import { NextRequest } from "next/server"

// The upstream API. Same env var the browser client uses, so there is one source of truth for
// where the backend lives.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

/**
 * Allowlisted upstream reads. The key is the path under `/api/public/`; the value is the
 * upstream path plus which query params may be forwarded and how each is validated.
 *
 * Adding an entry here makes a payload publicly CDN-cacheable — only ever add a read whose
 * anonymous response carries no per-caller content.
 */
const ROUTES: Record<
  string,
  { upstream: string; params: Record<string, RegExp>; sMaxAge: number; swr: number }
> = {
  // The 2026 board surfaces. Anonymous ⇒ the server returns the LOCKED payload (E9.56).
  // These blobs change only when the operator re-runs an exporter, never intraday.
  manifest: {
    upstream: "/fantasy/nfl/manifest",
    params: { season: /^\d{4}$/ },
    sMaxAge: 900,
    swr: 3600,
  },
  projections: {
    upstream: "/fantasy/nfl/projections",
    params: { season: /^\d{4}$/ },
    sMaxAge: 900,
    swr: 3600,
  },
  // The landing page's featured pick. It is fetched with NO token by every visitor (see
  // `components/home/pick-of-the-day.tsx`), so it is the single most-hit anonymous surface we
  // have — and therefore the biggest per-view saving on this list. Re-written intraday by each
  // re-score, hence a much shorter window than the board blobs.
  featured: {
    upstream: "/picks/featured",
    params: {},
    sMaxAge: 300,
    swr: 900,
  },
  board: {
    upstream: "/fantasy/nfl/board",
    // `config` mirrors the backend's `_CONFIG_RE`; `size` is the same 2..32 bound the API enforces.
    // Validating here as well means a junk value is rejected at the edge instead of minting a CDN
    // entry per junk value — an unvalidated param is a cache-key explosion, not just a bad request.
    params: { season: /^\d{4}$/, config: /^[a-z0-9_]{1,64}$/, size: /^(?:[2-9]|[12]\d|3[0-2])$/ },
    sMaxAge: 900,
    swr: 3600,
  },
}

/** Past seasons are immutable, so they get a much longer window than the live board. */
const TRACK_RECORD_S_MAXAGE = 3600
const TRACK_RECORD_SWR = 86400

function resolve(
  segments: string[],
): { upstream: string; params: Record<string, RegExp>; sMaxAge: number; swr: number } | null {
  if (segments.length === 1 && ROUTES[segments[0]]) return ROUTES[segments[0]]
  // The NF3.2 public receipts: `track-record/manifest` and `track-record/<season>`.
  if (segments.length === 2 && segments[0] === "track-record") {
    const leaf = segments[1]
    if (leaf === "manifest" || /^\d{4}$/.test(leaf)) {
      return {
        upstream: `/fantasy/nfl/track-record/${leaf}`,
        params: {},
        sMaxAge: TRACK_RECORD_S_MAXAGE,
        swr: TRACK_RECORD_SWR,
      }
    }
  }
  return null
}

function jsonError(status: number, detail: string) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  })
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params
  const route = resolve(path ?? [])
  if (!route) return jsonError(404, "Not found")

  if (!API_BASE) {
    // Misconfiguration, not a data problem — never cache it.
    return jsonError(503, "API is not configured")
  }

  // Build the upstream URL from VALIDATED params only. A param that fails its pattern is dropped
  // rather than forwarded, so the upstream sees either a good value or its own default.
  const url = new URL(API_BASE + route.upstream)
  for (const [name, pattern] of Object.entries(route.params)) {
    const value = request.nextUrl.searchParams.get(name)
    if (value !== null && pattern.test(value)) url.searchParams.set(name, value)
  }

  let upstream: Response
  try {
    upstream = await fetch(url.toString(), {
      // ⭐ NO `Authorization` HEADER IS CONSTRUCTED HERE, EVER — see property 1 above. We build a
      // fresh header set rather than spreading the incoming request's, so a token cannot reach the
      // upstream by being forwarded implicitly.
      headers: { Accept: "application/json" },
      // We do our own CDN caching via the response headers below; asking Next's data cache to also
      // hold it would add a second, separately-expiring copy with no benefit.
      cache: "no-store",
    })
  } catch {
    return jsonError(502, "Upstream unavailable")
  }

  if (!upstream.ok) {
    // Includes the 404 a not-yet-published export produces. Pass the status through so the client
    // renders its honest empty state, but never cache it.
    return jsonError(upstream.status, "Upstream returned an error")
  }

  const body = await upstream.text()
  // An empty body — or an empty array from a swallowed lakehouse failure (E9.26b) — is SUSPECT.
  // Serve it so the surface is not broken, but refuse to pin it in the CDN.
  const looksEmpty = body.trim() === "" || body.trim() === "[]" || body.trim() === "{}"
  const cacheControl = looksEmpty
    ? "no-store"
    : `public, s-maxage=${route.sMaxAge}, stale-while-revalidate=${route.swr}`

  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": cacheControl,
    },
  })
}
