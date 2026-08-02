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

export interface TrackRecordManifest {
  seasons: number[]
  /** Seasons whose rows carry a real `adp`/`adpRank` — Fantasy Football Calculator has no archive
   *  for some seasons (2025 confirmed: their live API returns `{"status":"Error"}`), so this can be
   *  a strict subset of `seasons`. A season NOT in this list still has real our/actual rows — only
   *  its ADP columns are null. Use this to render an honest "ADP unavailable" note instead of
   *  guessing from a blank column. */
  seasonsWithAdp: number[]
  generated_at: string
  /** The honest headline, built ENTIRELY from the NF-D3 scorecard's own numbers at export time —
   *  render this verbatim rather than writing new claim copy in a component. */
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
  /** Null when this season has no ADP benchmark at all — see `TrackRecordManifest.seasonsWithAdp`. */
  adp: number | null
  adpRank: number | null
  actualPoints: number | null
  actualRank: number
  /** Top-quartile disagreement with ADP within his position that season — the "fade" set the
   *  airtight independent claim is about. Always `false` for a season with no ADP benchmark (fade
   *  is an ADP-disagreement signal and cannot be computed without it — never a claim of "no fade"). */
  isFade: boolean
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
