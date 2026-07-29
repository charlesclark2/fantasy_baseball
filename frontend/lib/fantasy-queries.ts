// Shared react-query hooks for the NFL fantasy surfaces (NF3). Every surface — the draft
// optimizer and the three browse pages — reads the SAME gated endpoints, so the fetch/caching
// policy lives here once rather than being re-declared per surface.
//
// All three blobs are effectively static within a session (the boards are re-exported by an
// operator command, not intraday), hence `staleTime: Infinity`: switching format/tab never
// refetches a board already in cache.

"use client"

import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useAuth } from "@/lib/auth-context"
import { getFantasyBoard, getFantasyManifest, getFantasyProjections } from "@/lib/fantasy"
import type { ProjectionPayload } from "@/lib/fantasy"
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

// ── league-format selection ──────────────────────────────────────────────────────────────────
// Preferred defaults when a user has not chosen yet. Half-PPR at 12 teams is the most common
// home-league shape; both fall back to whatever the manifest actually shipped.
const DEFAULT_CONFIG = "half_ppr"
const DEFAULT_SIZE = 12
const FORMAT_STORAGE_KEY = "nfl-fantasy-format"

/** The (config, size) the browse surfaces are showing. Persisted so Rankings and the League Board
 *  stay on the same league when you move between them, and survive a reload. Always validated
 *  against the manifest — a stored preset that is no longer exported falls back to a real one. */
export function useFormatSelection(manifest: Manifest | undefined) {
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
    const pick = [stored.configName, DEFAULT_CONFIG].find((n) => n && names.includes(n))
    setConfigName(pick ?? names[0] ?? null)
    const sizePick = [stored.size, DEFAULT_SIZE].find((n) => n && manifest.sizes.includes(n))
    setSize(sizePick ?? manifest.sizes[0] ?? null)
  }, [manifest, configName])

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
