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
   *  fall back to MFL — the headline's claim and the fallback are deliberately independent. */
  headline: string
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
