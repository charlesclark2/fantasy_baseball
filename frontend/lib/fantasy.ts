// Fantasy data-fetch helpers (E9.45). The NFL draft boards used to load as static
// public JSON (/data/nfl-fantasy/...), which was publicly fetchable regardless of
// entitlement. They now come from the SERVER-SIDE-GATED backend endpoints
// (/fantasy/nfl/*, require_fantasy_access → 403) so the paid gate can't be bypassed
// by hitting the raw asset URL.

import { apiFetch } from "@/lib/api"
import type { Manifest, Player } from "@/lib/draft-optimizer"

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
