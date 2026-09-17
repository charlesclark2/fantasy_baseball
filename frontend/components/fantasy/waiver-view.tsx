"use client"

// NF-WVR1 Phase B — THE WAIVER VIEW, per imported team on My Teams.
//
// ══ WHAT THIS SURFACE IS, AND THE THREE THINGS IT NEVER DOES ════════════════════════════════════
//
// It lists the players on NOBODY's roster in the league (the server subtracts every team's roster,
// re-read from the platform on each open where the platform allows it), grouped by position, beside
// where the caller's own roster is thin. The only numbers are REALIZED 2026 facts — points a player
// has already scored, in the league's own scoring, computed server-side by the one scorer.
//
//   ⛔ NO VALUE / PROJECTION COLUMN. NF-ROS1 closed as a certified NO; the preseason projection
//      cannot see 2026 and is never shown or substituted here (PM ruling 1).
//   ⛔ NO CROSS-POSITION ORDERING. Positions are separate tabs; players are ordered only within one,
//      and only by the stated basis the server returns (PM ruling 2).
//   ⛔ NO RECOMMENDATION LANGUAGE. No "add", "pickup", "target", no rank numbers — the copy lives in
//      `fantasy-claim-copy.ts` where the claim screen reads it.
//
// ⭐ A BLANK IS NOT A ZERO. A defence (no team-grain facts yet) and a player with no stat line both
// render "—" with their stated reason; the server never sends a 0 for either, and neither do we.
//
// ⭐ OPT-IN. Opening the panel re-reads the league's rosters from the platform, so it is fetched on
// open, never once per league on page load.
//
// 🔒 G100: this renderer checks `decision_support` itself, not only the page guard — the gate is
// which component renders (#681), and a future mount on an ungated page must not leak it.

import { useState } from "react"
import { useAuth } from "@/lib/auth-context"
import { canUse } from "@/lib/entitlements"
import { useWaiverPool } from "@/lib/fantasy-queries"
import type { WaiverGroup, WaiverNeedPosition, WaiverPlayer, WaiverPoolPayload } from "@/lib/fantasy"
import {
  WAIVER_CAPTURED_NOTE,
  WAIVER_CLOSE_LABEL,
  WAIVER_ERROR_FALLBACK,
  WAIVER_FACTS_ABSENCE_TEXT,
  WAIVER_GAMES_LABEL,
  WAIVER_HEADING,
  WAIVER_INTRO,
  WAIVER_LOADING,
  WAIVER_NEED_HEADING,
  WAIVER_NEED_LABEL,
  WAIVER_NEED_NOTE,
  WAIVER_OPEN_LABEL,
  WAIVER_PLAYER_ABSENCE_TEXT,
  WAIVER_POINTS_DEFINITION,
  WAIVER_POINTS_LABEL,
  WAIVER_REFUSAL_FALLBACK,
  WAIVER_REFUSAL_TEXT,
  WAIVER_SHOW_ALL,
  WAIVER_SHOW_FEWER,
  waiverCoverageNote,
  waiverExcludedNote,
  waiverFreshnessNote,
} from "@/lib/fantasy-claim-copy"

/** Rows shown per position before "Show all". A display cap, never a selection: the server sends
 *  the whole pool and the rest is one click away. */
export const WAIVER_ROWS_COLLAPSED = 15

const POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DST"]

function pts(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toFixed(1) : "—"
}

function PlayerRow({ p }: { p: WaiverPlayer }) {
  const fact = p.realized
  const absence = fact?.absence ?? null
  return (
    <tr className="border-t border-white/5 align-top" data-testid="waiver-player">
      <td className="min-w-0 py-1.5 pr-2">
        <div className="truncate text-gray-200">{p.name}</div>
        <div className="text-[11px] text-gray-500">
          {p.team ?? "FA"}
          {p.bye ? ` · bye ${p.bye}` : ""}
          {p.rookie ? " · rookie" : ""}
        </div>
        {absence && absence !== "team_grain_not_covered" && (
          <div className="text-[11px] italic text-gray-500" data-testid="waiver-player-absence">
            {WAIVER_PLAYER_ABSENCE_TEXT[absence]}
          </div>
        )}
      </td>
      <td className="py-1.5 pr-2 text-right tabular-nums text-gray-200" data-testid="waiver-points">
        {pts(fact?.points)}
      </td>
      <td className="py-1.5 text-right tabular-nums text-gray-400">
        {typeof fact?.games === "number" ? fact.games : "—"}
      </td>
    </tr>
  )
}

function GroupTable({ group, factsShown }: { group: WaiverGroup; factsShown: boolean }) {
  const [all, setAll] = useState(false)
  const rows = all ? group.players : group.players.slice(0, WAIVER_ROWS_COLLAPSED)
  const reason = group.facts_absence ?? null
  return (
    <div className="mt-2 min-w-0" data-testid={`waiver-group-${group.pos}`}>
      {reason === "team_grain_not_covered" && (
        <p className="mb-1 text-[11px] text-gray-500" data-testid="waiver-group-absence">
          {WAIVER_PLAYER_ABSENCE_TEXT.team_grain_not_covered}
        </p>
      )}
      <div className="min-w-0 overflow-x-auto">
        <table className="w-full table-fixed text-xs">
          <thead>
            <tr className="text-left text-[11px] text-gray-500">
              <th className="py-1 pr-2 font-normal">{group.available} available</th>
              <th className="w-24 py-1 pr-2 text-right font-normal" title={WAIVER_POINTS_DEFINITION}>
                {factsShown ? WAIVER_POINTS_LABEL : ""}
              </th>
              <th className="w-14 py-1 text-right font-normal">
                {factsShown ? WAIVER_GAMES_LABEL : ""}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <PlayerRow key={`${p.id ?? p.name}-${i}`} p={p} />
            ))}
          </tbody>
        </table>
      </div>
      {group.players.length > WAIVER_ROWS_COLLAPSED && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="mt-1 text-[11px] text-emerald-400 hover:underline"
        >
          {all ? WAIVER_SHOW_FEWER : `${WAIVER_SHOW_ALL} ${group.players.length}`}
        </button>
      )}
    </div>
  )
}

function needFor(data: WaiverPoolPayload, pos: string): WaiverNeedPosition | undefined {
  return data.need?.positions?.find((n) => n.pos === pos)
}

function NeedSummary({ data }: { data: WaiverPoolPayload }) {
  const positions = data.need?.positions ?? []
  const flex = data.need?.flex
  if (!positions.length) return null
  return (
    <div className="mt-3" data-testid="waiver-need">
      <div className="text-xs font-medium text-gray-300">{WAIVER_NEED_HEADING}</div>
      <p className="text-[11px] text-gray-500">{WAIVER_NEED_NOTE}</p>
      <ul className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
        {positions.map((n) => (
          <li
            key={n.pos}
            data-testid={`waiver-need-${n.pos}`}
            className={`rounded border px-1.5 py-0.5 ${
              n.need === "open_starter"
                ? "border-amber-500/40 text-amber-200"
                : n.need === "thin"
                  ? "border-white/15 text-gray-300"
                  : "border-white/10 text-gray-500"
            }`}
          >
            {n.pos}: {WAIVER_NEED_LABEL[n.need] ?? n.need} · {n.held} held / {n.starters_required}{" "}
            to start
          </li>
        ))}
        {flex && flex.slots > 0 && (
          <li
            data-testid="waiver-need-flex"
            className={`rounded border px-1.5 py-0.5 ${
              flex.short_by > 0 ? "border-amber-500/40 text-amber-200" : "border-white/10 text-gray-500"
            }`}
          >
            FLEX ({flex.eligible.join("/")}):{" "}
            {flex.short_by > 0
              ? `${flex.short_by} slot${flex.short_by === 1 ? "" : "s"} with no spare player to fill`
              : "filled by your spare players"}
          </li>
        )}
      </ul>
    </div>
  )
}

function PoolBody({ data }: { data: WaiverPoolPayload }) {
  const groups = [...(data.pool ?? [])].sort(
    (a, b) => POSITION_ORDER.indexOf(a.pos) - POSITION_ORDER.indexOf(b.pos),
  )
  const firstOpen = groups.find((g) => needFor(data, g.pos)?.need === "open_starter")?.pos
  const [pos, setPos] = useState<string | null>(null)
  const shownPos = pos ?? firstOpen ?? groups[0]?.pos ?? null
  const group = groups.find((g) => g.pos === shownPos)
  const realized = data.realized
  const factsShown = !!realized && realized.absence === null
  const excluded = waiverExcludedNote(realized?.excluded ?? [])

  return (
    <>
      <p className="mt-2 text-[11px] text-gray-500" data-testid="waiver-ordering-note">
        {data.ordering_note}
      </p>
      {factsShown && (
        <p className="mt-1 text-[11px] text-gray-500" data-testid="waiver-coverage">
          {waiverCoverageNote(realized!.weeks)}
          {excluded ? ` ${excluded}` : ""}
          {realized!.captured_terms.length ? ` ${WAIVER_CAPTURED_NOTE}` : ""}
        </p>
      )}
      {!factsShown && realized?.absence && (
        <p className="mt-1 text-[11px] text-gray-400" data-testid="waiver-facts-absence">
          {WAIVER_FACTS_ABSENCE_TEXT[realized.absence]}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Position">
        {groups.map((g) => {
          const need = needFor(data, g.pos)?.need
          const active = g.pos === shownPos
          return (
            <button
              key={g.pos}
              type="button"
              role="tab"
              aria-selected={active}
              data-testid={`waiver-tab-${g.pos}`}
              onClick={() => setPos(g.pos)}
              className={`rounded px-2 py-1 text-xs ${
                active ? "bg-emerald-500/20 text-emerald-200" : "bg-white/5 text-gray-400"
              }`}
            >
              {g.pos}
              {need === "open_starter" ? " · open slot" : ""}
            </button>
          )
        })}
      </div>
      {group && <GroupTable key={group.pos} group={group} factsShown={factsShown} />}
    </>
  )
}

export function WaiverView({ leagueId }: { leagueId: string }) {
  const { groups } = useAuth()
  const entitled = canUse("decision_support", groups)
  const [open, setOpen] = useState(false)
  const { data, isLoading, error } = useWaiverPool(leagueId, open && entitled)

  if (!entitled) return null

  return (
    <div className="mt-4 min-w-0 border-t border-white/10 pt-3" data-testid="waiver-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-200">{WAIVER_HEADING}</h3>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          data-testid="waiver-toggle"
          className="rounded border border-white/15 px-2 py-1 text-xs text-gray-300 hover:bg-white/5"
        >
          {open ? WAIVER_CLOSE_LABEL : WAIVER_OPEN_LABEL}
        </button>
      </div>
      {open && (
        <div className="min-w-0">
          <p className="mt-1 text-[11px] text-gray-500">{WAIVER_INTRO}</p>
          {isLoading && <p className="mt-2 text-xs text-gray-500">{WAIVER_LOADING}</p>}
          {!isLoading && error && (
            <p className="mt-2 text-xs text-gray-400" data-testid="waiver-error">
              {(error as Error)?.message || WAIVER_ERROR_FALLBACK}
            </p>
          )}
          {data && (
            <>
              <p className="mt-2 text-[11px] text-gray-500" data-testid="waiver-freshness">
                {waiverFreshnessNote(data.rosters)}
              </p>
              <NeedSummary data={data} />
              {data.pool === null ? (
                <div className="mt-3 space-y-1" data-testid="waiver-refusal">
                  {(data.refusals.length ? data.refusals : ["_"]).map((r) => (
                    <p key={r} className="text-xs text-gray-400">
                      {WAIVER_REFUSAL_TEXT[r] ?? WAIVER_REFUSAL_FALLBACK}
                    </p>
                  ))}
                </div>
              ) : (
                <PoolBody data={data} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
