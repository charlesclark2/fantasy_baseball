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
  /** "empirical" (veteran game-to-game variance) | "calibrated" (rookie band). */
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
