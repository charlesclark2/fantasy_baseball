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
  /** `paste` = ESPN: the USER makes the request in their own browser and gives us the response
   *  body. We never call ESPN, and we never hold a credential — see the ESPN block below. */
  auth: "public" | "oauth" | "paste"
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

/** What `resolve_target` came back with. A bare number is ambiguous between a Sleeper league id and
 *  a user id, so the server tells us which it turned out to be rather than making us guess. */
export type SleeperResolved =
  // `leagues` is present in BOTH branches by design — the API and this app deploy independently, so
  // a response-shape change has to be additive or the older side renders a blank screen on a 200.
  | { kind: "league"; season: string; league: PlatformLeagueSummary; leagues: PlatformLeagueSummary[] }
  | {
      kind?: "user"
      season: string
      user: { user_id: string; display_name: string }
      leagues: PlatformLeagueSummary[]
    }

/** Accepts a Sleeper **username, league ID, or user ID** — whichever the user actually has. The
 *  league ID is the common case: it is the long number in the league's own URL. */
export function sleeperLeagues(
  token: string | null,
  identifier: string,
  season: string,
): Promise<SleeperResolved> {
  return apiFetch(
    `/fantasy/import/sleeper/leagues`,
    { method: "POST", body: JSON.stringify({ username: identifier, season }) },
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

// ── ESPN — user-mediated paste ──────────────────────────────────────────────────────────────────
//
// ESPN publishes no delegated grant, and the only automated way into a private league is replaying
// a full-account session cookie, which we refuse. So the user opens the link in their OWN browser
// and pastes the response. `espn_s2` is an HTTP cookie and is never echoed into a response body,
// so what they paste structurally cannot contain their sign-in.

/** Build the settings link for the user to open THEMSELVES. Nothing fetches it. */
export function espnReadUrl(
  token: string | null,
  leagueId: string,
  season: string,
): Promise<{ url: string }> {
  return apiFetch(
    `/fantasy/import/espn/read-url`,
    { method: "POST", body: JSON.stringify({ league_id: leagueId, season }) },
    token,
  )
}

/** Parse a pasted ESPN settings response. The server refuses a paste containing credential
 *  material (a "Copy as cURL" carries the whole Cookie header) and never logs the body. */
export function espnPreview(
  token: string | null,
  payload: string,
  season: string,
): Promise<ImportPreview> {
  return apiFetch(
    `/fantasy/import/espn/preview`,
    { method: "POST", body: JSON.stringify({ payload, season }) },
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
