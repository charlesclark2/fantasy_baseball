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
import { canAccessFantasyBeta } from "@/lib/entitlements"
import {
  createSavedLeague,
  deleteSavedLeague,
  getFantasyBoard,
  getFantasyManifest,
  getFantasyProjections,
  listSavedLeagues,
  updateSavedLeague,
} from "@/lib/fantasy"
import type { ProjectionPayload, SavedLeague } from "@/lib/fantasy"
import type { LeagueConfig } from "@/lib/league-config"
import { buildBoard } from "@/lib/league-scoring"
import type { BuiltBoard } from "@/lib/league-scoring"
import type { Manifest, Player } from "@/lib/draft-optimizer"

/** The NFL fantasy season every surface reads. */
export const FANTASY_SEASON = 2026

export function useFantasyManifest(season: number = FANTASY_SEASON) {
  const { accessToken } = useAuth()
  return useQuery<Manifest>({
    queryKey: ["nfl-fantasy-manifest", season],
    queryFn: () => getFantasyManifest(accessToken, season),
    staleTime: Infinity,
  })
}

export function useFantasyBoard(
  configName: string | null,
  size: number | null,
  season: number = FANTASY_SEASON,
) {
  const { accessToken } = useAuth()
  return useQuery<Player[]>({
    queryKey: ["nfl-fantasy-board", season, configName, size],
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
  const { accessToken } = useAuth()
  return useQuery<ProjectionPayload>({
    queryKey: ["nfl-fantasy-projections", season],
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
    mutationFn: ({ leagueId, config }: { leagueId: string | null; config: LeagueConfig }) =>
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
    }
  }
  return {
    board: presetQuery.data,
    isLoading: presetQuery.isLoading,
    isCustom: false as const,
    league: null,
    coverage: null,
  }
}

// ── league-format selection ──────────────────────────────────────────────────────────────────
// Preferred defaults when a user has not chosen yet. Half-PPR at 12 teams is the most common
// home-league shape; both fall back to whatever the manifest actually shipped.
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
  }, [manifest, configName, savedLeagues])

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
