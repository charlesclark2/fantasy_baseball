"use client"

// NF3.2 — the fantasy football past-season TRACK RECORD ("receipts"): our projection vs that
// season's preseason ADP vs the realized outcome, 2019–2025. Deliberately kept SEPARATE from
// `lib/fantasy.ts` (whose header comment documents its payloads as server-gated) so the public/paid
// split is visible at the FILE level, not only in runtime logic: nothing in this file ever needs an
// access token, and nothing it fetches is ever the current/locked season's projection — that
// guarantee lives in the export writer (`export_track_record_json.py`'s `LOCKED_SEASON` refusal) and
// the backend route (`fantasy_public.py`), not here; this file just calls the public endpoints.

import { useQueries, useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"

export type AdpSource = "ffc" | "mfl"

/** NF-TR1 — one position's measured gap against the captured ADP benchmark.
 *
 *  `verdict` is DERIVED at export time, never re-derived here: a component that decided "ahead" vs
 *  "even" from `deltaRho` would be a second, drifting copy of the threshold, and the whole point of
 *  the disclosure is that "running back is a wash" is a reading of the data rather than an
 *  assertion about it. Render the word the export computed. */
export interface TrackRecordPositionRow {
  position: string
  deltaRho: number
  verdict: "ahead" | "behind" | "even"
}

/** A context benchmark (ECR / ESPN / Sleeper) — reported SEPARATELY from the headline ADP claim and
 *  required by NF-TR1 to be visible. We currently trail all three, and that is the point of showing
 *  them: a page that reported only the comparison that flatters us would be selecting its evidence. */
export interface TrackRecordOtherBenchmark {
  key: string
  label: string
  deltaRho: number
  usRho: number
  benchmarkRho: number
  nSeasons: number
  verdict: "ahead" | "behind" | "even"
}

/** NF-TR1's TWO-LAYER claim, built by `export_track_record_json.build_claim` from the NF-D3
 *  scorecard + the NF-D17 population artifact.
 *
 *  ⛔ RENDER THESE STRINGS VERBATIM. Every one is screened against the export's `_CLAIM_DENYLIST`
 *  at build time and again by `betting_ml/tests/test_nf_tr1_claim_copy.py`; a component that
 *  rewrites, truncates mid-sentence, or conditionally drops one of them re-opens exactly the hole
 *  the screening closes — the hedges are load-bearing, not decoration (NF-D17 measured the shipped
 *  gap's own 90% interval as [-0.006, +0.051], which includes zero).
 *
 *  ⚠️ OPTIONAL ON THE MANIFEST, ON PURPOSE. An artifact published before NF-TR1 carries no `claim`,
 *  and the frontend ships ahead of the export (see `LEGACY_CLAIM_NOTE`). Treat its absence as a
 *  degraded render, never as a reason to promote the legacy `headline` into the lead. */
export interface TrackRecordClaim {
  /** Plain, everyday English. Calibration first, the benchmark comparison second and hedged. */
  lead: string
  /** The operator-approved analyst sentence, plus the numbers backing it. */
  precise: string
  benchmark: string
  benchmarkShort: string
  metric: string
  /** Display span, e.g. "2019–2024". */
  seasons: string
  nSeasons: number
  playersPerSeason: number
  playersPerSeasonMin: number
  playersPerSeasonMax: number
  usRho: number
  benchmarkRho: number
  deltaRho: number
  ciLow: number
  ciHigh: number
  /** Percent, e.g. 90. */
  ciLevel: number
  ciIncludesZero: boolean
  byPosition: TrackRecordPositionRow[]
  otherBenchmarks: TrackRecordOtherBenchmark[]
  /** The six required disclosures, already in plain words. Render all of them. */
  disclosures: string[]
  /** The frozen-board method, explained. */
  method: string
  /** The served two-stack architecture (calibrated level + market-consensus ordering). */
  architecture: string
}

export interface TrackRecordManifest {
  seasons: number[]
  /** Which ADP source backs each season, keyed by season as a STRING (JSON object keys) — "ffc"
   *  (the primary/established source, Fantasy Football Calculator) or "mfl" (MyFantasyLeague, used
   *  ONLY as a fallback when FFC has no archive for that season at all — 2025 confirmed: FFC's live
   *  API returns `{"status":"Error"}` across every teams/format combination). A season absent from
   *  this map has no ADP from either source (still has real our/actual rows — only its ADP columns
   *  are null). Use this to render an honest per-season source note instead of guessing from a
   *  blank column or presenting a fallback season as identical to a primary-source one. */
  adpSourceBySeason: Record<string, AdpSource>
  generated_at: string
  /** The honest headline, built ENTIRELY from the NF-D3 scorecard's own numbers at export time —
   *  render this verbatim rather than writing new claim copy in a component. Scoped to FFC's own
   *  archive span (the scorecard's "adp" aggregate) even in a season where the per-player rows below
   *  fall back to MFL — the headline's claim and the fallback are deliberately independent.
   *
   *  ⭐ NF-TR1: this IS `claim.lead` — the plain-English consumer lead. The field kept its name so
   *  the surfaces already quoting it (the locked-surface upgrade banner, the player page) inherited
   *  the plainer, better-hedged wording with no client change. The analyst sentence it used to carry
   *  moved to `claim.precise`; it was relocated, not deleted. */
  headline: string
  /** NF-TR1's two-layer claim. OPTIONAL: absent on any artifact published before NF-TR1. */
  claim?: TrackRecordClaim
  lockedSeason: number
  scorecardGeneratedAt: string
}

export interface TrackRecordRow {
  season: number
  playerId: string
  playerName: string
  position: string
  ourPoints: number | null
  ourRank: number
  /** Null when NEITHER ADP source has this season at all — see `TrackRecordManifest.adpSourceBySeason`. */
  adp: number | null
  adpRank: number | null
  actualPoints: number | null
  actualRank: number
  /** Top-quartile disagreement with ADP within his position that season — the "fade" set the
   *  airtight independent claim is about. Always `false` for a season with no ADP benchmark (fade
   *  is an ADP-disagreement signal and cannot be computed without it — never a claim of "no fade"). */
  isFade: boolean
  /** Whether the fade was RIGHT: "hit" (our rank landed closer to the actual finish than ADP's did),
   *  "miss" (ADP was the better call), or "push" (an exact tie). Always `null` when `isFade` is
   *  false — there is nothing to grade on a row we didn't flag as a real disagreement. See
   *  `_fade_result` in `benchmark_scorecard.py` for the exact definition. */
  fadeResult: "hit" | "miss" | "push" | null
  /** "ffc" | "mfl" | null — same meaning as `TrackRecordManifest.adpSourceBySeason`, carried on the
   *  row itself so a consumer never needs the manifest just to label one row. */
  adpSource: AdpSource | null
}

export function getTrackRecordManifest(): Promise<TrackRecordManifest> {
  return apiFetch(`/fantasy/nfl/track-record/manifest`)
}

export function getTrackRecordSeason(season: number): Promise<TrackRecordRow[]> {
  return apiFetch(`/fantasy/nfl/track-record/${season}`)
}

export function useTrackRecordManifest() {
  return useQuery<TrackRecordManifest>({
    queryKey: ["nfl-fantasy-track-record-manifest"],
    queryFn: getTrackRecordManifest,
    staleTime: Infinity,
    retry: false,
  })
}

export function useTrackRecordSeason(season: number | null) {
  return useQuery<TrackRecordRow[]>({
    queryKey: ["nfl-fantasy-track-record-season", season],
    queryFn: () => getTrackRecordSeason(season as number),
    enabled: season != null,
    staleTime: Infinity,
    retry: false,
  })
}

/** Every published season's rows, fetched in parallel — the player page uses this to find one
 *  player's full history without knowing in advance which seasons he appears in, without hand-rolling
 *  a variable-length list of hooks (react-query's `useQueries` is the sanctioned way to do that). */
export function useAllTrackRecordSeasons(seasons: number[]) {
  const results = useQueries({
    queries: seasons.map((s) => ({
      queryKey: ["nfl-fantasy-track-record-season", s],
      queryFn: () => getTrackRecordSeason(s),
      staleTime: Infinity,
      retry: false,
    })),
  })
  const isLoading = seasons.length > 0 && results.some((r) => r.isLoading)
  const rows: TrackRecordRow[] = results.flatMap((r) => r.data ?? [])
  return { rows, isLoading }
}
