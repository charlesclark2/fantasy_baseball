// Shared react-query hooks for the NFL fantasy surfaces (NF3). Every surface — the draft
// optimizer and the three browse pages — reads the SAME gated endpoints, so the fetch/caching
// policy lives here once rather than being re-declared per surface.
//
// All three blobs are effectively static within a session (the boards are re-exported by an
// operator command, not intraday), hence `staleTime: Infinity`: switching format/tab never
// refetches a board already in cache.

"use client"

import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth-context"
import { canAccess, canAccessFantasyBeta } from "@/lib/entitlements"
import {
  createSavedLeague,
  deleteSavedLeague,
  getFantasyBoard,
  getFantasyManifest,
  getFantasyProjections,
  getMyTeams as getMyTeamsPayload,
  listSavedLeagues,
  updateSavedLeague,
} from "@/lib/fantasy"
import type { LeagueSaveInput, MyTeamsPayload, ProjectionPayload, SavedLeague } from "@/lib/fantasy"
import type { LeagueConfig } from "@/lib/league-config"
import { buildBoard, matchRosterToBoard } from "@/lib/league-scoring"
import type { BuiltBoard, RosterMatch } from "@/lib/league-scoring"
import type { Manifest, Player } from "@/lib/draft-optimizer"
import { freeSelection } from "@/lib/draft-optimizer"
import {
  PROSPECT_SEASON,
  getProspectBoard,
  getProspectManifest,
} from "@/lib/mlb-prospects"
import type { ProspectBoardPayload, ProspectManifest } from "@/lib/mlb-prospects"
import {
  ACTIVE_LEAGUE_STORAGE_KEY,
  assignDraftPick,
  deleteMlbLeague,
  getMlbLeague,
  listMlbLeagues,
  saveMlbLeague,
  undoDraftPick,
  updateMlbLeague,
  uploadTeamRoster,
} from "@/lib/mlb-league"
import type {
  DismissReason,
  LeagueDetail as MlbLeagueDetail,
  LeagueSummary as MlbLeagueSummary,
} from "@/lib/mlb-league"

/** The NFL fantasy season every surface reads. */
export const FANTASY_SEASON = 2026

// ── E9.56b: the `enabled: canAccess("fantasy", …)` gate is REMOVED from the three board hooks ────
//
// 🚨 READ THIS BEFORE PUTTING IT BACK. NF3.2 added that gate with sound reasoning FOR ITS TIME:
// "the hook itself must refuse to ever ISSUE the gated request for a non-entitled caller — never
// merely hide its result in the render." That was correct while these endpoints returned 403 to a
// non-entitled caller, so issuing the request could only ever produce an error.
//
// E9.56 changed what is on the other end. `/fantasy/nfl/{manifest,projections,board}` are now
// DUAL-MODE: an entitled caller gets the real numbers; everyone else gets the same rows with every
// model value REMOVED and `locked: true` in its place, re-ordered onto market ADP so the array index
// cannot reconstruct our ranking (proven in prod 2026-08-05 — 858/858 rows locked, 100%
// ADP-ascending, identical under a forged `subscriber` token). So this is no longer "the gated
// request" — it is the request whose RESPONSE is gated, server-side, per point.
//
// ⇒ keeping the gate here would mean a free user's fetch never fires, `data === undefined`, and the
// surface renders its "not available yet" EMPTY STATE — which reads as "we haven't published this",
// not "subscribe to unlock". That is the failure this story exists to fix, and it is SILENT: nothing
// errors, nothing logs, and it presents as a content problem rather than a gating one.
//
// ⚠️ HOOK REUSE — WHY THIS DOES NOT FIRE UNINTENDED ANONYMOUS FETCHES ELSEWHERE. These hooks are
// also consumed by STILL-GATED surfaces: `draft-optimizer`, `league-board`, `league-import`,
// `league-settings-editor`, `player-search`, and `player-page`'s EntitledPlayerView. None starts
// fetching for an anonymous caller, and the reason is structural rather than lucky: `FantasyGuard`
// returns `null` BEFORE rendering its children, so those components never MOUNT for a non-entitled
// user and their hooks therefore never run. `player-page` is the one that does not rely on a guard —
// it dispatches to `PublicPlayerView`, which genuinely never invokes these hooks at all (see its
// module docstring). It would be SAFE either way (the server returns locked-or-403), so this is a
// correctness/efficiency property, not a security one — but if `FantasyGuard` is ever changed to
// render children while redirecting, re-check that list.
//
// The server remains the actual gate. Nothing removed here hides anything the API would not send.
//
// 🚨🚨 THE ENTITLEMENT MUST BE IN THE QUERY KEY, AND THIS IS NOT OPTIONAL. These queries are
// `staleTime: Infinity`, and `queryClient.clear()` runs on SIGN-OUT ONLY — `onLoginSuccess` does NOT
// clear it (see `lib/auth-context.tsx`). So without the key discriminator: a logged-out visitor
// caches the LOCKED payload → they subscribe and log in → the cache is never invalidated → a PAYING
// SUBSCRIBER keeps seeing the locked view indefinitely. It presents as "the paywall is broken" and
// there is no error anywhere.
//
// This could not happen before E9.56b, because `enabled: false` meant nothing was ever cached in the
// un-entitled state — i.e. REMOVING the gate is what introduces it. Keying on entitlement makes
// login a natural cache-miss and refetch. (Clearing the cache on login would also work but changes
// auth behaviour for every surface; this stays scoped to the three hooks that are actually
// dual-mode.) Guarded by `public-surface.test.ts::the entitlement is part of every dual-mode key`.
export function useFantasyManifest(season: number = FANTASY_SEASON) {
  const { accessToken, groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  return useQuery<Manifest>({
    queryKey: ["nfl-fantasy-manifest", season, entitled],
    queryFn: () => getFantasyManifest(accessToken, season),
    staleTime: Infinity,
  })
}

export function useFantasyBoard(
  configName: string | null,
  size: number | null,
  season: number = FANTASY_SEASON,
) {
  const { accessToken, groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  return useQuery<Player[]>({
    // `entitled` in the key — see the block above; omitting it strands a new subscriber on the
    // cached locked board.
    queryKey: ["nfl-fantasy-board", season, configName, size, entitled],
    enabled: !!configName && !!size,
    queryFn: async () => {
      const rows = await getFantasyBoard(accessToken, season, configName as string, size as number)
      // dedupe by id (defensive — a duplicate player_id would collide React keys and corrupt rendering)
      const seen = new Set<string>()
      return rows.filter((p) => (seen.has(p.id) ? false : (seen.add(p.id), true)))
    },
    staleTime: Infinity,
  })
}

export function useFantasyProjections(season: number = FANTASY_SEASON) {
  const { accessToken, groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  return useQuery<ProjectionPayload>({
    // `entitled` in the key — see the block above; omitting it strands a new subscriber on the
    // cached locked projections.
    queryKey: ["nfl-fantasy-projections", season, entitled],
    queryFn: () => getFantasyProjections(accessToken, season),
    staleTime: Infinity,
    // The projections blob 404s until the operator's first NF3 export — surface that as an
    // honest empty state immediately instead of burning retries on a known-missing object.
    retry: false,
  })
}

// ── NF-C0b: saved (hand-entered or imported) leagues ─────────────────────────────────────────
// The customization floor. `useSavedLeagues` is the list; `useCustomBoard` is what makes the gate
// true — a saved league produces the SAME `Player[]` the pre-exported preset boards produce, so
// every downstream surface consumes it through one interface and cannot tell the two apart.

/**
 * The user's saved leagues.
 *
 * ⚠️ Only FIRES for a caller entitled to the editor (`admin` + `fantasy_comp` — NF-C0b ships
 * narrower than the fantasy surface). The board, rankings and draft surfaces all call this to offer
 * "Your leagues" beside the presets, and those pages are open to every SUBSCRIBER — so without the
 * `enabled` gate every subscriber page-load would fire a request that 403s by design. Skipping the
 * call leaves `data` undefined, which those surfaces already treat as "no saved leagues" and fall
 * back to the presets. Cosmetic only: `/fantasy/leagues` enforces the same rule server-side.
 */
export function useSavedLeagues() {
  const { accessToken, groups } = useAuth()
  const entitled = canAccessFantasyBeta(groups)
  return useQuery<SavedLeague[]>({
    queryKey: ["nfl-fantasy-leagues"],
    queryFn: () => listSavedLeagues(accessToken),
    enabled: entitled,
    staleTime: 60_000,
    retry: false,
  })
}

export function useSaveLeague() {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    // Accepts a config optionally stamped with NF-C0 import provenance, so the manual editor and
    // the import surface share ONE save path — the alternative (a second mutation for imports)
    // would be a second place for the save semantics to drift.
    mutationFn: ({ leagueId, config }: { leagueId: string | null; config: LeagueSaveInput }) =>
      leagueId
        ? updateSavedLeague(accessToken, leagueId, config)
        : createSavedLeague(accessToken, config),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["nfl-fantasy-leagues"] }),
  })
}

export function useDeleteLeague() {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (leagueId: string) => deleteSavedLeague(accessToken, leagueId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["nfl-fantasy-leagues"] }),
  })
}

/**
 * Score a saved league's board IN THE BROWSER off the format-independent projections payload.
 *
 * A hand-entered league is by definition not one of the pre-exported presets, so there is no
 * server-side board for it — and the API Lambda cannot build one (it bundles neither pandas/numpy
 * nor `quant_sports_intel_models`). Computing it client-side is the same choice MVP-3 already made
 * for the draft optimizer: pure and synchronous, so an edit re-ranks instantly.
 *
 * Returns `null` (not an error) until the projections payload is available, so callers fall back to
 * the preset path rather than rendering a wrong board.
 */
export function useCustomBoard(config: LeagueConfig | null): BuiltBoard | null {
  const { data: projections } = useFantasyProjections()
  return useMemo(() => {
    if (!config || !projections?.players?.length) return null
    return buildBoard(projections.players, config)
  }, [config, projections])
}

// ── NF-C6: My Teams (cross-league browse) ────────────────────────────────────────────────────────

/** One saved league, scored in the browser, joined against its linked roster (if any). */
export interface MyTeamEntry {
  league: SavedLeague
  /** `null` until the projections payload has loaded — callers should show a loading state, not an
   *  empty one, while this is null (mirrors `useCustomBoard`'s own null-until-ready contract). */
  board: BuiltBoard | null
  /** Empty when the league has no linked team yet (`imported_roster` is null/empty) — a hand-entered
   *  league, or an imported one the user has not picked a team for (see `source_team_key`). */
  roster: RosterMatch[]
}

/**
 * Every saved league this user has, each scored + joined to its linked roster.
 *
 * Reads `/fantasy/nfl/my-teams` (broader `require_fantasy_access` gate than `useSavedLeagues`'s
 * beta-only `/fantasy/leagues` — see that endpoint's docstring) for the configs + roster snapshots,
 * then scores each one CLIENT-SIDE with the SAME `buildBoard` every other fantasy surface uses — no
 * second scorer, per the NF1.5b/NF3.3 reuse rule (`fantasy_engine` cannot be imported into the API
 * Lambda; see `models/fantasy.py`).
 */
export function useMyTeams() {
  const { accessToken, groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  const { data: projections } = useFantasyProjections()
  const query = useQuery<MyTeamsPayload>({
    queryKey: ["nfl-fantasy-my-teams"],
    queryFn: () => getMyTeamsPayload(accessToken, FANTASY_SEASON),
    enabled: entitled,
    staleTime: 60_000,
    retry: false,
  })

  const teams = useMemo<MyTeamEntry[] | null>(() => {
    const leagues = query.data?.leagues
    if (!leagues) return null
    if (!projections?.players?.length) return null
    return leagues.map((league) => {
      const board = buildBoard(projections.players, league)
      const roster = league.imported_roster?.length
        ? matchRosterToBoard(league.imported_roster, board.players)
        : []
      return { league, board, roster }
    })
  }, [query.data, projections])

  return { ...query, teams }
}

/** A saved league is selected as `custom:<league_id>` in the same control as the shipped presets. */
export const CUSTOM_PREFIX = "custom:"
export const isCustomSelection = (configName: string | null | undefined): boolean =>
  !!configName && configName.startsWith(CUSTOM_PREFIX)
export const customLeagueId = (configName: string): string => configName.slice(CUSTOM_PREFIX.length)

/**
 * THE GATE, in one hook: resolve whatever is selected — a shipped preset or a hand-entered league —
 * to the SAME `Player[]`.
 *
 * A preset comes from its pre-exported board; a saved league is scored in the browser by the ported
 * engine. Callers get one array either way and never branch on provenance, which is what "the
 * fantasy tools read a manually-built config identically to an imported one" has to mean in code.
 */
export function useResolvedBoard(configName: string | null, size: number | null) {
  const custom = isCustomSelection(configName)
  const { data: leagues } = useSavedLeagues()
  const selectedLeague = useMemo(
    () =>
      custom && configName
        ? (leagues ?? []).find((l) => l.league_id === customLeagueId(configName)) ?? null
        : null,
    [custom, configName, leagues],
  )

  // Both hooks always run (hook rules); each is inert when the other path is active.
  const presetQuery = useFantasyBoard(custom ? null : configName, custom ? null : size)
  const customBoard = useCustomBoard(selectedLeague)

  if (custom) {
    return {
      board: customBoard?.players,
      // A selected-but-not-yet-loaded league is genuinely loading; a MISSING one is not.
      isLoading: !customBoard && selectedLeague !== null,
      isCustom: true as const,
      league: selectedLeague,
      coverage: customBoard?.coverage ?? null,
      error: null,
    }
  }
  return {
    board: presetQuery.data,
    isLoading: presetQuery.isLoading,
    isCustom: false as const,
    league: null,
    coverage: null,
    // ⚠️ SURFACED DELIBERATELY (freemium build). A paid preset now answers 403, and without this the
    // failure arrived as an empty array and rendered "No players match — try clearing the search
    // box": a refusal disguised as a search result, which is the worst of both readings. A caller
    // that can reach a paid board must be able to tell "refused" from "nothing here".
    error: presetQuery.error ?? null,
  }
}

// ── league-format selection ──────────────────────────────────────────────────────────────────
// Preferred defaults when a user has not chosen yet. Half-PPR at 12 teams is the most common
// home-league shape; both fall back to whatever the manifest actually shipped.
//
// ⚠️ THESE ARE THE *ENTITLED* DEFAULTS. Since the free tier narrowed to one preset (2026-08-08) an
// unentitled visitor is defaulted onto the manifest's own `freeBoard` instead — landing them on
// half-PPR would open the surface on a board the API answers 403 for, i.e. an empty page on first
// visit. See `entitledDefaults` below.
const DEFAULT_CONFIG = "half_ppr"
const DEFAULT_SIZE = 12
const FORMAT_STORAGE_KEY = "nfl-fantasy-format"

/** The (config, size) the browse surfaces are showing. Persisted so Rankings and the League Board
 *  stay on the same league when you move between them, and survive a reload. Always validated
 *  against the manifest — a stored preset that is no longer exported falls back to a real one. */
export function useFormatSelection(
  manifest: Manifest | undefined,
  /** NF-C0b — the user's saved leagues, so a stored `custom:<id>` selection is validated against
   *  leagues that still EXIST. A deleted league must fall back to a real preset rather than leave
   *  the surface pointing at nothing. */
  savedLeagues?: SavedLeague[],
  /** Freemium build — whether this caller may read the PAID presets. Defaults to `true` so every
   *  existing call site keeps its exact behaviour; the browse surfaces pass the real value.
   *
   *  ⚠️ Only ever RESTRICTS. When false, a stored paid selection is replaced by the free board and
   *  the default lands there — because the alternative is a first visit that renders nothing and
   *  reads as a broken page rather than as a paywall. The server is still the authority; this is
   *  about not steering someone into a 403. */
  entitled: boolean = true,
) {
  const [configName, setConfigName] = useState<string | null>(null)
  const [size, setSize] = useState<number | null>(null)

  useEffect(() => {
    if (!manifest || configName !== null) return
    let stored: { configName?: string; size?: number } = {}
    try {
      stored = JSON.parse(localStorage.getItem(FORMAT_STORAGE_KEY) ?? "{}")
    } catch {
      stored = {}
    }
    const names = manifest.configs.map((c) => c.name)
    const customIds = new Set((savedLeagues ?? []).map((l) => CUSTOM_PREFIX + l.league_id))
    const free = freeSelection(manifest)

    // Unentitled: the free board is the only one the API will answer, so it is both the default and
    // the only admissible stored value. A saved CUSTOM league is personalization and equally out of
    // reach, so it does not win here either. `free` null (a pre-deploy manifest that doesn't say)
    // falls through to the entitled path — the old behaviour, which is right for a backend that has
    // not narrowed yet.
    if (!entitled && free) {
      const storedIsFree = stored.configName === free.config && stored.size === free.size
      setConfigName(storedIsFree ? free.config : names.includes(free.config) ? free.config : names[0] ?? null)
      setSize(storedIsFree ? free.size : manifest.sizes.includes(free.size) ? free.size : manifest.sizes[0] ?? null)
      return
    }

    // A stored CUSTOM selection wins when that league still exists — a user who has entered their
    // own league should land back on it, not on a generic preset.
    if (stored.configName && customIds.has(stored.configName)) {
      setConfigName(stored.configName)
      setSize(stored.size ?? DEFAULT_SIZE)
      return
    }
    const pick = [stored.configName, DEFAULT_CONFIG].find((n) => n && names.includes(n))
    setConfigName(pick ?? names[0] ?? null)
    const sizePick = [stored.size, DEFAULT_SIZE].find((n) => n && manifest.sizes.includes(n))
    setSize(sizePick ?? manifest.sizes[0] ?? null)
  }, [manifest, configName, savedLeagues, entitled])

  const persist = (next: { configName?: string; size?: number }) => {
    if (next.configName !== undefined) setConfigName(next.configName)
    if (next.size !== undefined) setSize(next.size)
    try {
      localStorage.setItem(
        FORMAT_STORAGE_KEY,
        JSON.stringify({
          configName: next.configName ?? configName,
          size: next.size ?? size,
        }),
      )
    } catch {
      /* storage unavailable (private mode) — selection still works for this session */
    }
  }

  return {
    configName,
    size,
    setConfigName: (c: string) => persist({ configName: c }),
    setSize: (n: number) => persist({ size: n }),
  }
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// E8.1 — MLB dynasty PROSPECT BOARD
// ══════════════════════════════════════════════════════════════════════════════════════════════
// Same policy as the NFL hooks above and for the same reasons: the hook refuses to ISSUE the gated
// request for a caller who cannot have it (not merely hide its result), and `staleTime: Infinity`
// because the board is a build-time artifact — it changes when an operator re-publishes it, never
// within a session.
//
// 🔒 The `enabled` predicate here is `isAdmin`, NOT `canAccess("fantasy", …)`: this surface is
// ADMIN ONLY while it is in development (operator, 2026-08-02), matching `get_admin_user` on the
// routes. Using the fantasy predicate would have every subscriber firing a request that 403s.

/** The AL/NL scope a user drafts in. Persisted because a single-league dynasty owner picks it ONCE
 *  and every subsequent visit should already be scoped — re-choosing it every page load is the
 *  single most annoying thing this surface could do. */
const PROSPECT_LEAGUE_STORAGE_KEY = "mlb-prospect-league"

export function useProspectManifest(season: number = PROSPECT_SEASON) {
  const { accessToken, isAdmin } = useAuth()
  return useQuery<ProspectManifest>({
    queryKey: ["mlb-prospect-manifest", season],
    queryFn: () => getProspectManifest(accessToken, season),
    enabled: isAdmin,
    staleTime: Infinity,
  })
}

export function useProspectBoard(season: number = PROSPECT_SEASON) {
  const { accessToken, isAdmin } = useAuth()
  return useQuery<ProspectBoardPayload>({
    queryKey: ["mlb-prospect-board", season],
    queryFn: () => getProspectBoard(accessToken, season),
    enabled: isAdmin,
    staleTime: Infinity,
  })
}

/** The persisted AL/NL/both scope. Returns "ALL" until the stored value is read, so the first
 *  render is never a flash of the WRONG league (which would read as data changing under you). */
export function useProspectLeague(): [string, (v: string) => void] {
  const [league, setLeague] = useState<string>("ALL")
  useEffect(() => {
    try {
      const stored = localStorage.getItem(PROSPECT_LEAGUE_STORAGE_KEY)
      if (stored === "AL" || stored === "NL" || stored === "ALL") setLeague(stored)
    } catch {
      /* storage unavailable (private mode) — the session default is fine */
    }
  }, [])
  return [
    league,
    (v: string) => {
      setLeague(v)
      try {
        localStorage.setItem(PROSPECT_LEAGUE_STORAGE_KEY, v)
      } catch {
        /* storage unavailable — selection still works for this session */
      }
    },
  ]
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// E8.2 — the user's MLB dynasty league + the board availability overlay
// ══════════════════════════════════════════════════════════════════════════════════════════════
//
// 🔒 `enabled: isAdmin`, exactly like the prospect-board hooks above: this surface is admin-only
// dogfood until 2027 and the routes enforce `get_admin_user`, so gating on the wider fantasy
// predicate would have every subscriber firing a request that 403s.
//
// ⭐ CACHE POLICY IS THE OPPOSITE OF THE BOARD'S. The board is `staleTime: Infinity` because it
// only changes when an operator re-publishes. The overlay changes on every draft pick, so it is
// NOT cached across mounts — a board showing a prospect as available when he went three picks ago
// looks exactly like a correct board (NF-C0's live-draft lesson).

export function useMlbLeagues() {
  const { accessToken, isAdmin } = useAuth()
  return useQuery<{ leagues: MlbLeagueSummary[] }>({
    queryKey: ["mlb-leagues"],
    queryFn: () => listMlbLeagues(accessToken),
    enabled: isAdmin,
    staleTime: 60_000,
  })
}

/** One league's rosters + availability overlay. `leagueId` null → the query simply does not run,
 *  which is the "no league set up yet" state, not an error. */
export function useMlbLeague(leagueId: string | null) {
  const { accessToken, isAdmin } = useAuth()
  return useQuery<MlbLeagueDetail>({
    queryKey: ["mlb-league", leagueId],
    queryFn: () => getMlbLeague(accessToken, leagueId as string),
    enabled: isAdmin && !!leagueId,
    staleTime: 0,
  })
}

export function useSaveMlbLeague() {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { name: string; text: string; leagueScope: string; leagueId?: string }) =>
      saveMlbLeague(accessToken, input),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["mlb-leagues"] })
      qc.invalidateQueries({ queryKey: ["mlb-league", data.league?.league_id] })
    },
  })
}

export function useDeleteMlbLeague() {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (leagueId: string) => deleteMlbLeague(accessToken, leagueId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mlb-leagues"] })
      qc.invalidateQueries({ queryKey: ["mlb-league"] })
    },
  })
}

/** Record a manual name fix (`{key: rank}`) or a dismissal (`{key: "not_a_prospect"}` /
 *  `{key: "missing_from_board"}` — see `DismissReason`; the two are different statements). */
export function useResolveMlbRosterRow(leagueId: string | null) {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (overrides: Record<string, number | DismissReason | null>) =>
      updateMlbLeague(accessToken, leagueId as string, { overrides }),
    // The PATCH response IS the recomputed league, so seed the cache with it rather than
    // invalidating and re-fetching — during a review pass that round trip is the whole latency.
    onSuccess: (data) => qc.setQueryData(["mlb-league", leagueId], data),
  })
}

/** E8.6 — set (or clear, with `""`) which of the league's teams is the user's own, for the
 *  board's "my roster" highlight. */
export function useSetMyTeam(leagueId: string | null) {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (myTeam: string) =>
      updateMlbLeague(accessToken, leagueId as string, { my_team: myTeam }),
    onSuccess: (data) => qc.setQueryData(["mlb-league", leagueId], data),
  })
}

/** Replace one team's roster from a per-team export, leaving the other teams alone. */
export function useUploadTeamRoster(leagueId: string | null) {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ team, text }: { team: string; text: string }) =>
      uploadTeamRoster(accessToken, leagueId as string, team, text),
    onSuccess: (data) => qc.setQueryData(["mlb-league", leagueId], data),
  })
}

/** Live draft: mark a prospect taken, or undo. */
export function useDraftPick(leagueId: string | null) {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ rank, team }: { rank: number; team: string | null }) =>
      team
        ? assignDraftPick(accessToken, leagueId as string, rank, team)
        : undoDraftPick(accessToken, leagueId as string, rank),
    onSuccess: (data) => qc.setQueryData(["mlb-league", leagueId], data),
  })
}

/** The active league id, persisted so the board stays scoped between visits.
 *
 * ⚠️ Only the ID is stored. The league itself is always re-read from the server, so a deleted or
 * unreadable league degrades to "no overlay" — never to a stale overlay, which on this surface
 * would be indistinguishable from a correct one. */
export function useActiveMlbLeague(): [string | null, (v: string | null) => void] {
  const [leagueId, setLeagueId] = useState<string | null>(null)
  useEffect(() => {
    try {
      setLeagueId(localStorage.getItem(ACTIVE_LEAGUE_STORAGE_KEY))
    } catch {
      /* storage unavailable (private mode) — the session default is fine */
    }
  }, [])
  return [
    leagueId,
    (v: string | null) => {
      setLeagueId(v)
      try {
        if (v) localStorage.setItem(ACTIVE_LEAGUE_STORAGE_KEY, v)
        else localStorage.removeItem(ACTIVE_LEAGUE_STORAGE_KEY)
      } catch {
        /* storage unavailable — selection still works for this session */
      }
    },
  ]
}
