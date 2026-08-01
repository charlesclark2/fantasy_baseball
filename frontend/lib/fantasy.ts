// Fantasy data-fetch helpers (E9.45). The NFL draft boards used to load as static
// public JSON (/data/nfl-fantasy/...), which was publicly fetchable regardless of
// entitlement. They now come from the SERVER-SIDE-GATED backend endpoints
// (/fantasy/nfl/*, require_fantasy_access → 403) so the paid gate can't be bypassed
// by hitting the raw asset URL.

import { apiFetch } from "@/lib/api"
import type { Manifest, Player } from "@/lib/draft-optimizer"

// NF3 — the format-INDEPENDENT season projection: one row per projectable player, the raw
// season stat line plus an 80% PPR interval and the honest uncertainty metadata. This is what
// the browse Projections surface renders. The FORMAT-scored number is the league board's
// `pts`/`vor` (see `Player`), never `fpStd/fpHalf/fpPpr` — those are a one-format convenience.
export interface ProjectedPlayer {
  id: string
  name: string
  pos: string
  team: string | null
  bye: number | null
  rookie: boolean
  /** Overall draft slot for a rookie; null for veterans. */
  draftPick: number | null
  /** The model's own confidence tier: "high" | "medium" | "low". */
  conf: string | null
  /** Projected games played. */
  g: number | null
  fpStd: number | null
  fpHalf: number | null
  fpPpr: number | null
  fpSd: number | null
  fpP10: number | null
  fpP90: number | null
  /** How the 80% range was produced: "empirical" (veteran game-to-game variance) |
   *  "calibrated_per_player" (NF1.7 — a per-player rookie band, render as a REAL interval) |
   *  "calibrated" (the thin-history rookie fallback — a shared class-level band; keep this one, and
   *  ONLY this one, labelled "Class-level" — see UNCERTAINTY_LABEL/UNCERTAINTY_HELP). */
  uncType: string | null
  passAtt: number | null
  passCmp: number | null
  passYds: number | null
  passTd: number | null
  passInt: number | null
  rushAtt: number | null
  rushYds: number | null
  rushTd: number | null
  tgt: number | null
  rec: number | null
  recYds: number | null
  recTd: number | null
  fum: number | null
  twoPt: number | null
  /** Market average draft position (PPR, 12-team — see `adp_format`/`adp_teams` on the payload).
   *  A reference column; null means undrafted in that sample. */
  adp?: number | null

  // ── NF3.1: BIO — passed through from nflverse's identity table (`player_bio_map`), never
  // derived/projected. Optional: absent for a DST (a team, not a person), for the ~0.2-1% of
  // players the source has nothing for, and on any payload exported before NF3.1. ──────────────
  /** ISO date. Age is computed client-side from this (not baked in server-side) so it never goes
   *  stale between re-exports. */
  birthDate?: string | null
  heightIn?: number | null
  weightLb?: number | null
  college?: string | null
  /** Years of NFL experience as of the export's last bio refresh. */
  yearsExp?: number | null
  /** An official nfl.com headshot URL — render with a fallback (initials), not assumed to always
   *  resolve. */
  headshot?: string | null

  // ── NF1.6: KICKER + TEAM DEFENSE (DST) ────────────────────────────────────────────────────
  /** True for the positions whose projection must NOT be read as a confident rank (K/DST). Set on
   *  every row by the exporter (false for skill positions), so the UI never has to know which
   *  positions are soft. Optional — payloads exported before NF1.6 do not carry it. */
  lowPred?: boolean
  /** The honest caveat to render beside a `lowPred` row, supplied by the exporter so the wording
   *  lives with the model that earned it. */
  predNote?: string | null
  /** Kicker line. Field goals are split by DISTANCE because that is how they score (3/4/5) and
   *  because leg strength is the one kicker attribute that genuinely persists year to year. */
  fgAtt?: number | null
  fgMade?: number | null
  fg039?: number | null
  fg4049?: number | null
  fg50?: number | null
  fgMiss?: number | null
  patAtt?: number | null
  patMade?: number | null
  /** Team-defense line. `paPerG` (points allowed per game) is the number that communicates
   *  defensive quality; the nine points-allowed TIER buckets below are a scoring INPUT, never a
   *  display column. */
  sacks?: number | null
  defInt?: number | null
  fumRec?: number | null
  defTd?: number | null
  stTd?: number | null
  safety?: number | null
  blocked?: number | null
  paTot?: number | null
  paPerG?: number | null
  /** NF-C0b — the nine points-allowed TIER buckets, each the EXPECTED NUMBER OF GAMES the defense
   *  lands in that bucket. A per-game tier table therefore scores a season as
   *  `Σ_bucket tier_points × expected_games`, i.e. LINEAR in these columns — which is what lets a
   *  hand-entered D/ST scheme be applied EXACTLY rather than approximated. Never displayed.
   *  Optional: payloads exported before NF-C0b do not carry them, and a custom tier table then
   *  reports as captured-not-applied rather than silently scoring zero. */
  paG0?: number | null
  paG1_6?: number | null
  paG7_13?: number | null
  paG14_17?: number | null
  paG18_20?: number | null
  paG21_27?: number | null
  paG28_34?: number | null
  paG35_45?: number | null
  paG46p?: number | null
}

export interface ProjectionPayload {
  season: number
  generated_at: string
  source: string
  model_version: string | null
  base_season: number | null
  /** Which FFC ADP sample the `adp` column came from — this surface is format-independent, so its
   *  ADP reference is pinned rather than varying, and is labelled with these. */
  adp_format?: string | null
  adp_teams?: number | null
  players: ProjectedPlayer[]
}

export function getFantasyManifest(token: string | null, season: number): Promise<Manifest> {
  return apiFetch(`/fantasy/nfl/manifest?season=${season}`, {}, token)
}

export function getFantasyBoard(
  token: string | null,
  season: number,
  config: string,
  size: number,
): Promise<Player[]> {
  return apiFetch(
    `/fantasy/nfl/board?season=${season}&config=${encodeURIComponent(config)}&size=${size}`,
    {},
    token,
  )
}

export function getFantasyProjections(
  token: string | null,
  season: number,
): Promise<ProjectionPayload> {
  return apiFetch(`/fantasy/nfl/projections?season=${season}`, {}, token)
}

// ── NF-C0b: saved league settings ────────────────────────────────────────────────────────────────
// The manual customization FLOOR. A platform import (NF-C0) is the convenience path and will never
// reach every league (private leagues, long-tail platforms, a fragile ESPN endpoint), so a user can
// always type their settings in instead. Both paths write the SAME `fantasy_engine` LeagueConfig,
// which is why a hand-built league feeds the board / VOR / draft tools identically to an imported one.

import type { LeagueConfig } from "@/lib/league-config"

/** NF-C0 import provenance — where a league CAME FROM.
 *
 *  Deliberately NOT part of `LeagueConfig` (which mirrors the engine's `to_dict()` exactly): this
 *  is storage metadata in the same class as `created_at`, so an imported league and a typed-in one
 *  remain the identical config object once the envelope is dropped. A hand-entered league leaves
 *  these undefined. They exist for the one thing the config cannot express — going back to the
 *  platform for LIVE draft state, which is never persisted because a stale one looks correct. */
export interface LeagueProvenance {
  source_platform?: string | null
  source_league_id?: string | null
  imported_at?: string | null
}

/** What a save accepts: the shared config, optionally stamped with where it was imported from. */
export type LeagueSaveInput = LeagueConfig & LeagueProvenance

/** A stored league: the shared config object plus its server-assigned identity + timestamps. */
export interface SavedLeague extends LeagueConfig, LeagueProvenance {
  league_id: string
  user_id?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export function listSavedLeagues(token: string | null): Promise<SavedLeague[]> {
  return apiFetch(`/fantasy/leagues`, {}, token)
}

export function createSavedLeague(
  token: string | null,
  cfg: LeagueSaveInput,
): Promise<SavedLeague> {
  return apiFetch(`/fantasy/leagues`, { method: "POST", body: JSON.stringify(cfg) }, token)
}

export function updateSavedLeague(
  token: string | null,
  leagueId: string,
  cfg: LeagueSaveInput,
): Promise<SavedLeague> {
  return apiFetch(
    `/fantasy/leagues/${encodeURIComponent(leagueId)}`,
    { method: "PUT", body: JSON.stringify(cfg) },
    token,
  )
}

export function deleteSavedLeague(token: string | null, leagueId: string): Promise<void> {
  return apiFetch(
    `/fantasy/leagues/${encodeURIComponent(leagueId)}`,
    { method: "DELETE" },
    token,
  )
}
