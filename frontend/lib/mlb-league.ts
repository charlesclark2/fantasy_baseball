// E8.2 — a user's MLB dynasty league: roster upload, and the availability overlay it puts on the
// E8.1 prospect board.
//
// 🚪 UPLOAD ONLY, BY DECISION. E8.2a found no compliant way to read a CBS league (dead API,
// login-walled pages, a blanket robots.txt, no OAuth program), so the one-click import was OMITTED
// rather than deferred. Nothing here asks for a platform password, and nothing here calls CBS.
//
// 🔒 ADMIN ONLY, matching the board it overlays (`get_admin_user` on every route). These endpoints
// WRITE a user's own league data, so the server-side gate is the real one.
//
// ⭐ WHY THE OVERLAY IS A SEPARATE FETCH FROM THE BOARD. The board blob is static and cached for
// the session (`staleTime: Infinity`); the overlay changes every time a pick is made. Folding
// availability into the board payload would either make the board uncacheable or make availability
// stale — and a board showing a player as available when he went three picks ago is worse than no
// board at all (NF-C0's live-draft lesson).

import { apiFetch } from "@/lib/api"

/** How confidently a roster name was resolved to a board row. Ordered best → worst. */
export type MatchConfidence =
  | "exact" // initial + full surname, unique inside the league's AL/NL scope
  | "manual" // the user pinned it by hand
  | "draft" // marked drafted during a live draft
  | "variant" // matched on a name-rendering variant (`H Yu Lee` → `Hao-Yu Lee`) — confirm it
  | "ambiguous" // two or more board prospects share the name; NEVER guessed
  | "position_conflict" // a same-name prospect the roster SLOT contradicts (a batter slot vs a
  //                       pitching prospect). Usually a genuine different player.
  | "contested" // a second roster entry resolving to a board row another entry already claimed
  | "missing_from_board" // the admin says this IS a prospect we don't carry — see coverage_gaps
  | "unresolved" // no board row at all — usually an established major-leaguer

/** How a review row is dismissed. These are DIFFERENT STATEMENTS and collapsing them is what threw
 *  away the signal: "not a prospect" is Salvador Perez; "missing from board" is a prospect somebody
 *  is spending a dynasty roster spot on that we do not carry. */
export type DismissReason = "not_a_prospect" | "missing_from_board"

/** A player who looks like a prospect we should be tracking but is not on the board. */
export interface CoverageGap {
  key: string
  name: string
  team: string
  slot: string
  status: string | null
  org: string | null
  positions: string | null
  /** "confirmed" = the admin said so · "suggested" = an unplaceable minors-slot stash. */
  source: "confirmed" | "suggested"
}

export interface RosterEntry {
  team: string
  slot: string
  name: string
  /** "minors" | "injured" | "reserve" | null (active). A minors stash is still ROSTERED. */
  status: string | null
}

/** Who holds a given board row, keyed by the board's `rank`. */
export interface RosteredBy {
  team: string
  slot: string
  status: string | null
  confidence: MatchConfidence
  source: "roster" | "draft"
}

export interface ReviewRow {
  key: string
  name: string
  team: string
  slot: string
  status: string | null
  confidence: MatchConfidence
  candidates: {
    rank: number
    name: string
    org?: string
    pos?: string
    level?: string
    eta?: number
    mlbamId?: number
  }[]
}

export interface LeagueSummary {
  league_id: string
  name: string
  league_scope: string
  season: number
  team_count: number
  player_count: number
  updated_at?: string
  created_at?: string
}

/** What every league read returns. `rostered` is the whole product: board rank → who holds him. */
export interface LeagueOverlay {
  league_scope: string
  season: number
  teams: string[]
  counts: Record<string, number>
  rostered: Record<string, RosteredBy>
  picks: Record<string, string>
  review: ReviewRow[]
  coverage_gaps: CoverageGap[]
  /** Written server-side so the honest framing travels with the computation (the NF3 convention). */
  framing: string
}

export interface LeaguePreview extends LeagueOverlay {
  upload_format: "cbs_grid" | "long"
  warnings: string[]
  entries: RosterEntry[]
}

export interface LeagueDetail extends LeagueOverlay {
  league: LeagueSummary
  entries: RosterEntry[]
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
})

export function previewLeagueUpload(
  token: string | null,
  text: string,
  leagueScope: string,
): Promise<LeaguePreview> {
  return apiFetch("/fantasy/mlb/league/preview", json({ text, league_scope: leagueScope }), token)
}

export function listMlbLeagues(token: string | null): Promise<{ leagues: LeagueSummary[] }> {
  return apiFetch("/fantasy/mlb/leagues", {}, token)
}

export function getMlbLeague(token: string | null, leagueId: string): Promise<LeagueDetail> {
  return apiFetch(`/fantasy/mlb/leagues/${encodeURIComponent(leagueId)}`, {}, token)
}

export function saveMlbLeague(
  token: string | null,
  input: { name: string; text: string; leagueScope: string; leagueId?: string },
): Promise<LeaguePreview & { league: LeagueSummary }> {
  return apiFetch(
    "/fantasy/mlb/leagues",
    json({
      name: input.name,
      text: input.text,
      league_scope: input.leagueScope,
      league_id: input.leagueId ?? null,
    }),
    token,
  )
}

export function updateMlbLeague(
  token: string | null,
  leagueId: string,
  patch: {
    name?: string
    league_scope?: string
    overrides?: Record<string, number | DismissReason | null>
  },
): Promise<LeagueDetail> {
  return apiFetch(
    `/fantasy/mlb/leagues/${encodeURIComponent(leagueId)}`,
    { method: "PATCH", body: JSON.stringify(patch) },
    token,
  )
}

export function deleteMlbLeague(token: string | null, leagueId: string): Promise<void> {
  return apiFetch(
    `/fantasy/mlb/leagues/${encodeURIComponent(leagueId)}`,
    { method: "DELETE" },
    token,
  )
}

/** Replace ONE team's roster from a per-team export (CBS's "roster overview").
 *
 * ⚠️ The team NAME is required: that export does not contain it, and filing 33 players under ""
 * would make a whole roster belong to nobody — every one of them reading as available. */
export function uploadTeamRoster(
  token: string | null,
  leagueId: string,
  team: string,
  text: string,
): Promise<LeagueDetail & { imported: number; replaced: number }> {
  return apiFetch(
    `/fantasy/mlb/leagues/${encodeURIComponent(leagueId)}/teams`,
    { method: "PUT", body: JSON.stringify({ team, text }) },
    token,
  )
}

/** Live draft: mark a board prospect as just taken. */
export function assignDraftPick(
  token: string | null,
  leagueId: string,
  boardRank: number,
  team: string,
): Promise<LeagueDetail> {
  return apiFetch(
    `/fantasy/mlb/leagues/${encodeURIComponent(leagueId)}/picks/${boardRank}`,
    { method: "PUT", body: JSON.stringify({ team }) },
    token,
  )
}

export function undoDraftPick(
  token: string | null,
  leagueId: string,
  boardRank: number,
): Promise<LeagueDetail> {
  return apiFetch(
    `/fantasy/mlb/leagues/${encodeURIComponent(leagueId)}/picks/${boardRank}`,
    { method: "DELETE" },
    token,
  )
}

// ── display helpers ──────────────────────────────────────────────────────────────────────────

export const STATUS_LABEL: Record<string, string> = {
  minors: "minors",
  injured: "IL",
  reserve: "reserve",
}

/** The one-line honest summary of a match run.
 *
 * ⚠️ It deliberately does NOT lead with "103 of 442 matched (23%)". That number is arithmetically
 * right and rhetorically wrong: most of a fantasy roster is established major-leaguers who are not
 * prospects, so a low ratio is the EXPECTED shape, not a failure. Leading with it would train the
 * user to distrust a working import. What actually needs attention is the review queue. */
export function matchSummary(counts: Record<string, number>): string {
  const resolved = (counts.exact ?? 0) + (counts.variant ?? 0) + (counts.manual ?? 0)
  const parts = [
    `${counts.rostered_board_rows ?? 0} of the ${counts.board_rows_in_scope ?? 0} prospects in ` +
      `your league's scope are already rostered`,
    `${resolved} roster ${resolved === 1 ? "name" : "names"} matched the board`,
  ]
  const needs =
    (counts.ambiguous ?? 0) + (counts.contested ?? 0) + (counts.minors_unresolved ?? 0)
  if (needs > 0) parts.push(`${needs} need${needs === 1 ? "s" : ""} a look`)
  return parts.join(" · ")
}

/** The coverage report as a CSV an operator can hand straight to the board build. */
export function coverageGapsCsv(gaps: CoverageGap[]): string {
  const rows = [
    ["name", "position", "mlb_team", "roster_status", "fantasy_team", "confidence"],
    ...gaps.map((g) => [
      g.name,
      g.positions ?? g.slot ?? "",
      g.org ?? "",
      g.status ?? "active",
      g.team,
      g.source,
    ]),
  ]
  return rows
    .map((r) => r.map((c) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(","))
    .join("\n")
}

/** The persisted "which league am I drafting in" selection, shared by the setup page and the
 *  board. One id in localStorage — the league itself always comes from the server, so a stale or
 *  deleted id degrades to "no league" rather than to a wrong overlay. */
export const ACTIVE_LEAGUE_STORAGE_KEY = "mlb-active-league"
