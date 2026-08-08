// Fantasy data-fetch helpers (E9.45). The NFL draft boards used to load as static
// public JSON (/data/nfl-fantasy/...), which was publicly fetchable regardless of
// entitlement. They now come from the SERVER-SIDE-GATED backend endpoints
// (/fantasy/nfl/*, require_fantasy_access → 403) so the paid gate can't be bypassed
// by hitting the raw asset URL.

import { apiFetch, cdnFetch } from "@/lib/api"
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

  /** NF1.5b — how MARKET-LEANING this row's ORDERING is: `"market-led"` / `"market-led-adaptive"` /
   *  `"market-blend"` / `"independent-lean"` / `"independent"`.
   *
   *  🚨 It is the honest caveat, not a decoration. The served board re-orders our own calibrated
   *  projections using market consensus (ADP/ECR) at the positions where that measurably helped — so
   *  at a market-led position the ranking is NOT an independent read on the market, and must never be
   *  presented as beating a market it is partly built from. Null on a market-blind payload and on
   *  rows with no market input (rookies, K/DST). */
  mktLean?: string | null

  // ── NF3.4: PER-PLAYER feature contributions — genuine per-player attribution (LightGBM TreeSHAP),
  // NOT a position-level description. Null for a rookie or K/DST (NF1 has no base-season feature row
  // to attribute for either). 🚨 `totalPts` is NF1's OWN separate research-model prediction for this
  // player — it is NOT guaranteed to equal `fpPpr` above (the served MVP-1 number); see
  // `nf1_model.player_feature_contributions`'s docstring. Feature labels/descriptions live in the
  // manifest's `featureLegend`, not repeated here. ──────────────────────────────────────────────
  contrib?: {
    /** The model's SHARED constant — its unconditional expected value, the SAME number for every
     *  player it scores. NOT player-specific; never describe this as "his" anything. */
    biasPts: number
    /** THIS player's own `mvp1_fp` contribution — genuinely player-specific (it scales with his own
     *  baseline heuristic projection), which is WHY two players at the same position show different
     *  `baselinePts` even though `biasPts` is identical for both. */
    ownPriorPts: number
    /** `biasPts + ownPriorPts` — NF1's starting point for him specifically, shown as "starting
     *  point", not as one of `drivers` (a driver a model can't act on isn't a useful lever to show a
     *  drafter). */
    baselinePts: number
    /** `baselinePts` + every driver's `pts` (not just the ones shown) — NF1's full own prediction. */
    totalPts: number
    /** Ranked by |pts| descending; a positive value pushes his number up, negative pushes it down. */
    drivers: { feature: string; pts: number }[]
  } | null

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

  /** E9.56 — set by the server when this caller is not entitled to the season's model output. The
   *  row keeps its public identity (name/pos/team/ADP) so a "subscribe to unlock" CTA has something
   *  to render; every projected value is ABSENT, not null-with-a-secret. Optional: an entitled
   *  response omits it entirely. */
  locked?: boolean

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

  // ── NF3.3: PLAYER HISTORY — past-season actual finish + past ADP + a weekly injury-report log +
  // games-missed participation. Lands inside THIS gated payload (never the public track-record
  // blob), so it is gated AT THE DATA LAYER with no extra UI logic: `null`/absent for a player with
  // nothing (a rookie with no past season, or a DST — a team, not a person, never carries an injury
  // log) and for any payload exported before NF3.3. 🔒 HONEST: descriptive realized history, never a
  // forward-looking claim (best_alpha=0) — `gamesMissedBySeason` counts a game NOT played for ANY
  // reason (injury, healthy scratch, roster move), never asserted to be injury-caused; the weekly
  // `injuries` report is the only place a specific injury is named. */
  history?: PlayerHistory | null
}

/** NF3.3 — one past season's actual finish vs that season's ADP, reusing the SAME per-player join
 *  (`benchmark_scorecard.player_track_record_frame`) NF3.2's public track-record page is built from
 *  — never a parallel re-derivation. See `TrackRecordRow` in `lib/fantasy-track-record.ts` for the
 *  public sibling shape (deliberately similar field names; this one adds `gamesPlayed`). */
export interface PastSeasonRecord {
  season: number
  ourRank: number
  /** Market ADP for that season — null when neither FFC nor its MFL fallback had an archive. */
  adp: number | null
  adpRank: number | null
  /** "ffc" | "mfl" | null — which real-draft population backed `adp` (see NF3.2). */
  adpSource: string | null
  actualPoints: number
  actualRank: number
  gamesPlayed: number | null
  isFade: boolean
  fadeResult: "hit" | "miss" | "push" | null
}

/** NF3.3 — one weekly nflverse injury-report entry (game-report + practice-participation status).
 *  Distinct from the roster-status availability prior the projection itself uses — this is pure
 *  DISPLAY history, never a model input. */
export interface InjuryReportEntry {
  season: number
  week: number
  reportStatus: string | null
  reportPrimaryInjury: string | null
  practiceStatus: string | null
  dateModified: string | null
}

/** NF3.3 — a season's participation count: how many of his team's non-bye games he did NOT record a
 *  snap/box-score line for, for ANY reason. Never merged with `injuries` into one "games missed to
 *  injury" number — read the weekly report for causation where one exists. */
export interface GamesMissedRecord {
  season: number
  gamesOnRoster: number
  gamesMissed: number
}

export interface PlayerHistory {
  pastSeasons: PastSeasonRecord[]
  injuries: InjuryReportEntry[]
  gamesMissedBySeason: GamesMissedRecord[]
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
  /** NF1.5b — which projection lineage this payload IS: `"nf1_5"` (market-aware refined, the served
   *  default since the re-land) or `"mvp1"` (market-blind). Absent on a pre-NF1.5b export. */
  projection_source?: string | null
  projection_label?: string | null
  /** `{position -> market lean}` for the whole board — the per-position form of `mktLean`. */
  market_lean?: Record<string, string> | null
  /** The standing caveat, supplied BY THE EXPORT so the wording lives with the model that earned it
   *  and cannot drift out of sync with which positions actually use the market. */
  market_lean_note?: string | null
  players: ProjectedPlayer[]

  // ── E9.56: the server-side entitlement envelope ────────────────────────────────────────────
  // ALL OPTIONAL, and every consumer must tolerate their ABSENCE: the API Lambda ships only via a
  // manual `deploy.sh` while this frontend auto-deploys on merge, so there is always a window where
  // a NEW client is talking to the OLD backend (NF-C0, both directions). Absent ⇒ read as ENTITLED,
  // which is the shape the old backend has always returned to a caller it let through at all.
  /** True when the server withheld this season's model output from this caller. */
  locked?: boolean
  /** Stated explicitly rather than inferred from `!locked`, so a dropped field can never read as
   *  entitled (the E9.41 silently-dropped-Pydantic-field class). */
  entitled?: boolean
  lockedSeason?: number
  /** Exactly which field names the server removed — computed server-side from the real payload, so
   *  a newly-added projection field shows up as a locked point (and a CTA) automatically. */
  lockedFields?: string[]
  upgrade?: { reason: string; message: string; ctaHref: string }
}

/** True iff the server locked this payload/row. Absent marker ⇒ NOT locked (see above). */
export function isLocked(x: { locked?: boolean } | null | undefined): boolean {
  return x?.locked === true
}

/** True iff the server locked THIS SET of rows (any row carrying the marker locks the view). */
export function rowsAreLocked(rows: { locked?: boolean }[] | null | undefined): boolean {
  return !!rows?.some((r) => r.locked === true)
}

/** E9.56b — trim the undrafted tail from a LOCKED view, and report how many were hidden.
 *
 *  WHY. A locked row keeps only public identity + market ADP. Measured against the live payload
 *  (2026-08-05): of 858 rows, **226 have an ADP and 632 do not** — so ~74% of the free page would be
 *  players with a name, a lock icon and nothing else, sorted alphabetically at the bottom. That is
 *  not a conversion surface, it is dead weight, and it is the bulk of what a crawler would index.
 *
 *  The hidden count is RETURNED rather than swallowed so the UI can state it honestly ("N more
 *  players are included with a subscription") — which turns the truncation into a reason to
 *  subscribe rather than a silent omission. Never drop rows without saying so.
 *
 *  ⚠️ AN ENTITLED VIEW IS UNTOUCHED — an unlocked payload returns unchanged, tail and all. A
 *  subscriber has a real projection for every one of those players and must still see them.
 */
export function trimLockedTail<T extends { adp?: number | null; locked?: boolean }>(
  rows: T[],
): { rows: T[]; hiddenCount: number } {
  if (!rowsAreLocked(rows)) return { rows, hiddenCount: 0 }
  const kept = rows.filter((r) => typeof r.adp === "number" && Number.isFinite(r.adp))
  return { rows: kept, hiddenCount: rows.length - kept.length }
}

/** NF1.5b — the positions whose ordering INCORPORATES market consensus, from a `market_lean` map.
 *  Anything that is not explicitly independent counts, so a new lean label added upstream is treated
 *  as market-leaning (the conservative direction) rather than silently dropping the caveat. */
export function marketLeaningPositions(
  lean: Record<string, string> | null | undefined,
): string[] {
  if (!lean) return []
  return Object.entries(lean)
    .filter(([, v]) => typeof v === "string" && !v.startsWith("independent"))
    .map(([pos]) => pos)
    .sort()
}

// ── G100-D1: the anonymous read path goes through our own CDN, not the API Lambda ────────────────
//
// An anonymous caller always receives the same LOCKED payload (E9.56), so it is cacheable once for
// everybody. `/api/public/*` is a same-origin Next route handler that fetches it and
// returns it with `s-maxage` — Vercel serves every subsequent view from the edge with no function
// invocation and no Lambda call. See that route's module comment for the safety properties.
//
// A TOKEN-BEARING caller keeps going straight to the API, unchanged: their payload is
// entitlement-dependent and must never be shared-cached. The `token ? … : …` split below IS that
// boundary, so keep the two arms symmetric in shape — the callers cannot tell them apart, and the
// response bodies are byte-identical (the route handler passes the upstream body through verbatim).
export function getFantasyManifest(token: string | null, season: number): Promise<Manifest> {
  if (!token) return cdnFetch(`/api/public/manifest?season=${season}`)
  return apiFetch(`/fantasy/nfl/manifest?season=${season}`, {}, token)
}

export function getFantasyBoard(
  token: string | null,
  season: number,
  config: string,
  size: number,
): Promise<Player[]> {
  const qs = `season=${season}&config=${encodeURIComponent(config)}&size=${size}`
  if (!token) return cdnFetch(`/api/public/board?${qs}`)
  return apiFetch(`/fantasy/nfl/board?${qs}`, {}, token)
}

export function getFantasyProjections(
  token: string | null,
  season: number,
): Promise<ProjectionPayload> {
  if (!token) return cdnFetch(`/api/public/projections?season=${season}`)
  return apiFetch(`/fantasy/nfl/projections?season=${season}`, {}, token)
}

// ── NF-C0b: saved league settings ────────────────────────────────────────────────────────────────
// The manual customization FLOOR. A platform import (NF-C0) is the convenience path and will never
// reach every league (private leagues, long-tail platforms, a fragile ESPN endpoint), so a user can
// always type their settings in instead. Both paths write the SAME `fantasy_engine` LeagueConfig,
// which is why a hand-built league feeds the board / VOR / draft tools identically to an imported one.

import type { LeagueConfig } from "@/lib/league-config"
import type { ImportedPlayer } from "@/lib/fantasy-import"

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
  // ── NF-C6: which previewed team is the user's own, and its roster AT IMPORT TIME ──────────────
  // A SNAPSHOT, not a live read: unlike draft state this works uniformly across all three
  // platforms, including ESPN, whose paste flow structurally can never be re-fetched by the server.
  // `roster_synced_at` keeps the age honest; re-importing (already an "update, not duplicate" save)
  // refreshes it. See the Python field docstrings in app/backend/models/fantasy.py.
  source_team_key?: string | null
  source_team_name?: string | null
  imported_roster?: ImportedPlayer[] | null
  roster_synced_at?: string | null
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

// ── NF-C6: My Teams (cross-league browse) ────────────────────────────────────────────────────────
// `/fantasy/nfl/my-teams` reads at the BROADER `require_fantasy_access` gate (not the beta-only
// `/fantasy/leagues`) — see the endpoint's own docstring. It returns the same `SavedLeague` shape;
// this surface just reads it under a different entitlement and scores it client-side (`buildBoard`).

export interface MyTeamsPayload {
  season: number
  leagues: SavedLeague[]
}

export function getMyTeams(token: string | null, season: number): Promise<MyTeamsPayload> {
  return apiFetch(`/fantasy/nfl/my-teams?season=${season}`, {}, token)
}
