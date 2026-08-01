// NF-C0 — platform league import client.
//
// Import is the CONVENIENCE layer over NF-C0b's manual editor. Both produce the SAME
// `LeagueConfig`, so an imported league is saved through the SAME `/fantasy/leagues` endpoints the
// editor uses — there is no second save path and no second settings schema to keep in sync.
//
// 🚨 No password ever reaches this client. Sleeper needs no credential at all; Yahoo sends the user
// to Yahoo's own consent screen and the grant lives server-side, encrypted.

import { apiFetch } from "@/lib/api"
import type { LeagueConfig } from "@/lib/league-config"

export interface ImportPlatform {
  id: string
  label: string
  auth: "public" | "oauth"
  /** We built an adapter for it. */
  available: boolean
  /** It is usable RIGHT NOW — false for an OAuth platform whose app registration is still pending.
   *  Kept separate from `available` so the UI can say "coming, pending registration" rather than
   *  hiding the option or offering a button that fails. */
  configured: boolean
  connected: boolean
  help: string
  attribution?: string
  attribution_url?: string
}

export interface PlatformLeagueSummary {
  league_id: string
  name: string
  season: string
  total_rosters: number
  status: string
  sport: string
}

export interface ImportedPlayer {
  player_key: string
  name: string
  position: string | null
  team: string | null
  starter: boolean
}

export interface ImportedTeam {
  team_key: string
  name: string
  owner: string | null
  is_owner: boolean
  players: ImportedPlayer[]
}

export interface DraftPick {
  pick_no: number
  round: number
  team_key: string | null
  player: ImportedPlayer | null
}

export interface DraftStatePayload {
  status: string | null
  type: string | null
  rounds: number | null
  start_time: string | null
  picks: DraftPick[]
  pick_count: number
  supported: boolean
  note: string
}

export interface ImportPreview {
  platform: string
  source_league_id: string
  season: string | null
  config: LeagueConfig
  teams: ImportedTeam[]
  draft: DraftStatePayload | null
  /** Things the platform said that we could NOT represent faithfully, in plain language. Rendered
   *  verbatim — an import that quietly loses a rule is the failure this whole surface guards. */
  warnings: string[]
  /** Scoring terms carried through under the platform's own key because we do not project them.
   *  They are STORED (so the league stays a faithful record) and contribute nothing to the board;
   *  the coverage panel reports them as "captured". */
  unmapped_scoring_keys: string[]
}

export function listImportPlatforms(token: string | null): Promise<ImportPlatform[]> {
  return apiFetch(`/fantasy/import/platforms`, {}, token)
}

export function sleeperLeagues(
  token: string | null,
  username: string,
  season: string,
): Promise<{ user: { user_id: string; display_name: string }; season: string; leagues: PlatformLeagueSummary[] }> {
  return apiFetch(
    `/fantasy/import/sleeper/leagues`,
    { method: "POST", body: JSON.stringify({ username, season }) },
    token,
  )
}

export function sleeperPreview(token: string | null, leagueId: string): Promise<ImportPreview> {
  return apiFetch(
    `/fantasy/import/sleeper/preview`,
    { method: "POST", body: JSON.stringify({ league_id: leagueId }) },
    token,
  )
}

export function yahooAuthorizeUrl(token: string | null): Promise<{ authorize_url: string }> {
  return apiFetch(`/fantasy/import/yahoo/authorize`, {}, token)
}

export function yahooLeagues(token: string | null): Promise<{ leagues: PlatformLeagueSummary[] }> {
  return apiFetch(`/fantasy/import/yahoo/leagues`, {}, token)
}

export function yahooPreview(token: string | null, leagueId: string): Promise<ImportPreview> {
  return apiFetch(
    `/fantasy/import/yahoo/preview`,
    { method: "POST", body: JSON.stringify({ league_id: leagueId }) },
    token,
  )
}

export function yahooDisconnect(token: string | null): Promise<void> {
  return apiFetch(`/fantasy/import/yahoo/connection`, { method: "DELETE" }, token)
}

/** LIVE roster/draft state for an ALREADY-SAVED imported league. Never cached into the stored
 *  config: a stale "who's drafted" board is worse than none, because it looks correct. */
export function liveLeagueState(
  token: string | null,
  leagueId: string,
): Promise<{ platform: string; source_league_id: string; draft: DraftStatePayload }> {
  return apiFetch(`/fantasy/import/live/${encodeURIComponent(leagueId)}`, {}, token)
}
