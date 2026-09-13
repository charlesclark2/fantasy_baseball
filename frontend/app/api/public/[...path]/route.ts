// G100-D1 — the CDN read path for the ANONYMOUS fantasy board.
//
// WHY THIS ROUTE EXISTS. The rankings / projections / player surfaces are client components that
// call the API Lambda directly, so before this every anonymous page view was one API Gateway
// request and one Lambda invocation. Once the free board is un-gated to anonymous traffic that
// scales linearly with visitors — and with bots, which do not stop at one view.
//
// The key observation: the payload an anonymous caller receives is IDENTICAL for every anonymous
// caller. It is a pure function of the published S3 blob, with no per-user content at all. So it is
// cacheable exactly once for everybody. This handler fetches it and returns it with `s-maxage`,
// which Vercel's CDN honours — the first request in each window costs one function invocation and
// one Lambda call, and every subsequent view inside that window is served from the edge with NO
// function invocation and NO Lambda at all.
//
// ⭐ SINCE THE FREEMIUM BUILD (2026-08-08) THE BOARD READS ARE ENTITLEMENT-INDEPENDENT: the generic
// board is free, so an anonymous caller and a subscriber get the same bytes. That STRENGTHENS
// property 1 below rather than retiring it — the header must still never be forwarded, because the
// property that makes this cache safe is that the upstream cannot tell who is asking, and the way
// to keep that true is to never give it the means. Entitled callers still go straight to the API
// (see `lib/fantasy.ts` for why that split is kept even though both arms now agree).
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
  // The generic board surfaces — free for every caller since the freemium build, and identical
  // bytes for all of them, which is what makes them cacheable here at all.
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
  // E9.46 — the landing page's fantasy proof card. Same profile as `featured` above: no token,
  // identical payload for every caller, on the most-hit anonymous surface we have. Derived from the
  // published projections blob, so it moves only when the operator re-exports — hence the board
  // blobs' window rather than the featured pick's intraday one.
  // ⚠️ QUOTED KEY, because of the hyphen. `test_every_cdn_surface_is_also_mapped_in_the_e2e_harness`
  // parses these keys with a regex; it was extended to accept the quoted form in the same change,
  // or this entry would have been INVISIBLE to the guard rather than checked by it.
  "featured-player": {
    upstream: "/fantasy/nfl/featured-player",
    params: {},
    sMaxAge: 900,
    swr: 3600,
  },
  // ⭐ THE FREE BOARD ONLY, AND THE NARROW REGEXES ARE THE ENFORCEMENT — not decoration.
  //
  // Since the free tier narrowed to one preset (2026-08-08) the upstream `/fantasy/nfl/board`
  // answers 200 or 403 depending on who is asking, for every preset EXCEPT `full_ppr`/12. That
  // makes it the one upstream on this list whose response is not a pure function of the URL — and
  // this handler deliberately strips `Authorization` (property 1), so a paid board fetched through
  // here would be an anonymous request: a 403 written into a public CDN entry and served to
  // subscribers for the rest of the window. Pinning `config`/`size` to the free selection means the
  // edge CANNOT ask the upstream a question whose answer depends on the caller, which is a stronger
  // guarantee than remembering not to.
  //
  // ⇒ an entitled client fetches a paid board straight from the API (`apiFetch` in lib/fantasy.ts).
  // ⚠️ These two literals must move with `entitlement.FREE_BOARD_CONFIG` / `FREE_BOARD_SIZE`;
  // `test_freemium_tier.py::test_the_cdn_route_only_proxies_the_free_board` reads them from here
  // and compares, so a one-sided edit goes red rather than quietly opening or breaking the edge.
  board: {
    upstream: "/fantasy/nfl/board",
    params: { season: /^\d{4}$/, config: /^full_ppr$/, size: /^12$/ },
    sMaxAge: 900,
    swr: 3600,
  },
  // NF-C6-PH2 — the FREE weekly reads. Both upstreams are byte-identical for every caller (neither
  // handler takes a `Request`), so they are cacheable here for the same reason the season blobs
  // are, and they are rewritten once per weekly build rather than intraday.
  //
  // ⛔ `/fantasy/nfl/weekly/projections-full` IS DELIBERATELY ABSENT and must stay absent. It is
  // the PAID substrate: this handler strips `Authorization` (property 1), so fetching it here would
  // be an anonymous request whose 403 got written into a public CDN entry and served to subscribers
  // for the rest of the window. Pinned by
  // `test_nf_c6_ph2_weekly_contract.py::test_the_cdn_route_proxies_the_free_weekly_reads_and_never_the_paid_one`.
  //
  // ⚠️ `week` is OPTIONAL upstream — omitted, the API resolves it through the published pointer.
  // The regex still has to be here, because an unvalidated param is dropped rather than forwarded,
  // and a week that failed validation must fall through to the pointer rather than reach the
  // upstream as junk. Two digits: NFL REG weeks are 1–18.
  "weekly-manifest": {
    upstream: "/fantasy/nfl/weekly/manifest",
    params: { season: /^\d{4}$/, week: /^\d{1,2}$/ },
    sMaxAge: 900,
    swr: 3600,
  },
  "weekly-projections": {
    upstream: "/fantasy/nfl/weekly/projections",
    params: { season: /^\d{4}$/, week: /^\d{1,2}$/ },
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
