"use client"

// NCAAF-P3.2 — the flagship college-football surface.
//
// ⭐ NCAAF IS FREE (E9.45 — fantasy is the paid hook). There is no guard, no token and no
// entitlement branch anywhere in this tree; the four `/ncaaf/*` routes read no Bearer token at all.
//
// ══ THE FOUR EMPTY STATES ARE FOUR DIFFERENT FACTS ════════════════════════════════════════════
//
// A surface whose "nothing here" renders identically for several causes makes every recurrence
// re-investigate from scratch (NF-C6b/NF-K1, which cost the same D/ST symptom two investigations).
// This page distinguishes them, and they are all reachable in the E2E harness:
//
//   * NOTHING PUBLISHED — the manifest lists no days at all. Pre-season, or nothing written yet.
//   * AN EMPTY DAY      — a day with no slate. The API answers **404**, which on this surface is
//                         the ORDINARY state of a Tuesday, not a fault. Hence `retry: false` on the
//                         slate query: retrying a normal answer three times buys nothing but a
//                         spinner.
//   * A FAILED READ     — anything that is not a 404. "We could not reach the model" is a problem
//                         on our side and says so.
//   * A GAME WITH GAPS  — handled inside the card (an absent curve, an absent probability, an
//                         absent market line), because a partial game must still render the parts
//                         it has rather than vanishing.
//
// ⛔ NO RANKING, NO SELECTION, NO PICK. Games are ordered by kickoff time. See `game-card.tsx`.

import { useCallback, useEffect, useMemo, useState } from "react"
import { apiErrorStatus } from "@/lib/api"
import {
  defaultGameDay,
  useNcaafManifest,
  useNcaafSlate,
  type NcaafGamePrediction,
} from "@/lib/ncaaf"
import {
  COLLAPSE_ALL_LABEL,
  EMPTY_DAY,
  EXPAND_ALL_LABEL,
  NOTHING_PUBLISHED,
  PAGE_STANDFIRST,
  PAGE_TITLE,
  READ_FAILED,
} from "@/lib/ncaaf-copy"
import { NcaafDayPicker } from "./day-picker"
import { NcaafGameCard } from "./game-card"

/** Kickoff order, and nothing else — see `game-card.tsx` for why an ordering is a claim.
 *  A game with no kickoff instant (`start_time_tbd`) sorts LAST rather than first, which is where
 *  a reader expects an unscheduled game; ties break on `game_id` so the order is stable across
 *  renders instead of depending on the payload's incidental array order. */
function byKickoff(a: NcaafGamePrediction, b: NcaafGamePrediction): number {
  const ta = a.commence_time ? Date.parse(a.commence_time) : Number.POSITIVE_INFINITY
  const tb = b.commence_time ? Date.parse(b.commence_time) : Number.POSITIVE_INFINITY
  const na = Number.isNaN(ta) ? Number.POSITIVE_INFINITY : ta
  const nb = Number.isNaN(tb) ? Number.POSITIVE_INFINITY : tb
  return na - nb || a.game_id - b.game_id
}

function Notice({ testId, tone = "muted", children }: {
  testId: string
  tone?: "muted" | "warn"
  children: React.ReactNode
}) {
  return (
    <p
      data-testid={testId}
      className={`rounded-lg border px-4 py-6 text-center text-sm ${
        tone === "warn"
          ? "border-amber-900/50 bg-amber-950/20 text-amber-200/80"
          : "border-[#1e1e1e] bg-[#0d0d0d] text-gray-400"
      }`}
    >
      {children}
    </p>
  )
}

function Skeleton({ testId }: { testId: string }) {
  return (
    <div data-testid={testId} className="space-y-3" aria-busy="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-44 animate-pulse rounded-xl border border-[#1e1e1e] bg-[#0d0d0d]" />
      ))}
    </div>
  )
}

/** Where the viewer's collapse preference lives.
 *
 * ⭐ `localStorage`, deliberately: this is a per-viewer convenience, it never leaves the browser,
 * and nothing downstream reads it. Every access is wrapped because the accessor ITSELF throws in a
 * private window or with site data blocked — and a page that cannot remember a preference must
 * still render, defaulting to EXPANDED (the P3 directive's answer, not a stored one).
 *
 * ⛔ It stores the DEFAULT only, never per-game state. A remembered set of collapsed game ids would
 * be stale the moment the slate changed, and would silently hide a card on a later week's board. */
const COLLAPSE_PREF_KEY = "ncaaf.games.defaultExpanded"

function readCollapsePref(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_PREF_KEY) !== "0"
  } catch {
    return true
  }
}

function writeCollapsePref(expanded: boolean): void {
  try {
    window.localStorage.setItem(COLLAPSE_PREF_KEY, expanded ? "1" : "0")
  } catch {
    // A viewer who cannot store a preference simply does not keep one.
  }
}

export function NcaafGamesPage() {
  const manifest = useNcaafManifest()
  // `null` means "we have not chosen yet" and the manifest's default applies; once the reader
  // picks a day, THEIR choice wins and is never silently replaced by a refetched default.
  const [chosen, setChosen] = useState<string | null>(null)
  const fallbackDay = useMemo(() => defaultGameDay(manifest.data), [manifest.data])
  const day = chosen ?? fallbackDay

  const slate = useNcaafSlate(day)
  const games = useMemo(() => [...(slate.data?.games ?? [])].sort(byKickoff), [slate.data])

  // ⚠️ SEEDED EXPANDED, THEN CORRECTED FROM STORAGE IN AN EFFECT — never read during render. This
  // tree is a client component but Next still renders it on the SERVER, where `localStorage` does
  // not exist; reading it in the initial state would either throw there or hand the client a first
  // paint different from the server's (a hydration mismatch). The directive's default is the safe
  // seed precisely because it is what a first-time viewer should see anyway.
  const [defaultExpanded, setDefaultExpanded] = useState(true)
  const [overrides, setOverrides] = useState<Record<number, boolean>>({})
  useEffect(() => setDefaultExpanded(readCollapsePref()), [])

  const isExpanded = useCallback(
    (gameId: number) => overrides[gameId] ?? defaultExpanded,
    [overrides, defaultExpanded],
  )
  const toggleOne = useCallback(
    (gameId: number, next: boolean) => setOverrides((o) => ({ ...o, [gameId]: next })),
    [],
  )
  // Expand/collapse-all moves the DEFAULT and clears every per-card override, so the control means
  // what it says: afterwards ALL cards are in the named state, not "all except the ones you touched".
  const toggleAll = useCallback((next: boolean) => {
    setDefaultExpanded(next)
    setOverrides({})
    writeCollapsePref(next)
  }, [])
  const anyExpanded = games.some((g) => isExpanded(g.game_id))

  // The disclosure is SERVED and rendered VERBATIM (see `lib/ncaaf-copy.ts` rule 3). Prefer the
  // slate's own copy of it so what a reader sees belongs to the payload in front of them; fall
  // back to the manifest's so the disclosure is present even before a slate loads.
  const disclosure = slate.data?.framing.disclosure ?? manifest.data?.framing.disclosure ?? null

  const slateStatus = apiErrorStatus(slate.error)
  const dayIsEmpty = slate.isError && slateStatus === 404
  const slateFailed = slate.isError && slateStatus !== 404

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold text-white sm:text-2xl">{PAGE_TITLE}</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-gray-400">{PAGE_STANDFIRST}</p>
        {disclosure && (
          <p
            data-testid="ncaaf-disclosure"
            className="max-w-2xl rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500"
          >
            {disclosure}
          </p>
        )}
      </header>

      <div className="mt-6 space-y-5">
        {manifest.isLoading && <Skeleton testId="ncaaf-manifest-loading" />}

        {manifest.isError && (
          <Notice testId="ncaaf-manifest-error" tone="warn">
            {READ_FAILED}
          </Notice>
        )}

        {manifest.data && manifest.data.game_days.length === 0 && (
          <Notice testId="ncaaf-nothing-published">{NOTHING_PUBLISHED}</Notice>
        )}

        {manifest.data && manifest.data.game_days.length > 0 && (
          <NcaafDayPicker
            days={manifest.data.game_days}
            selected={day}
            onSelect={setChosen}
          />
        )}

        {day && slate.isLoading && <Skeleton testId="ncaaf-slate-loading" />}

        {dayIsEmpty && <Notice testId="ncaaf-empty-day">{EMPTY_DAY}</Notice>}
        {slateFailed && (
          <Notice testId="ncaaf-slate-error" tone="warn">
            {READ_FAILED}
          </Notice>
        )}

        {/* A slate that loaded and holds nothing. Distinct from the 404 above on purpose: one is
            "this day is not published", the other is "this day is published and is empty", and a
            surface that rendered them identically would send the next investigation to the wrong
            place. */}
        {slate.data && games.length === 0 && (
          <Notice testId="ncaaf-empty-slate">{EMPTY_DAY}</Notice>
        )}

        {games.length > 0 && (
          <>
            <div className="flex justify-end">
              <button
                type="button"
                data-testid="ncaaf-toggle-all"
                onClick={() => toggleAll(!anyExpanded)}
                className="rounded-md border border-[#2a2a2a] px-2 py-1 text-[11px] text-gray-400 transition-colors hover:border-[#3a3a3a] hover:text-gray-200"
              >
                {anyExpanded ? COLLAPSE_ALL_LABEL : EXPAND_ALL_LABEL}
              </button>
            </div>
            <section data-testid="ncaaf-game-list" className="space-y-4">
              {games.map((g) => (
                <NcaafGameCard
                  key={g.game_id}
                  game={g}
                  expanded={isExpanded(g.game_id)}
                  onToggle={toggleOne}
                />
              ))}
            </section>
          </>
        )}
      </div>
    </main>
  )
}
