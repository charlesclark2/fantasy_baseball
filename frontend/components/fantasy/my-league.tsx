"use client"

// G100-C1 — MY LEAGUE. The activation screen: the one place that answers, visibly,
// "what changed because this is MY league?"
//
// ══ WHY A DEDICATED SCREEN AND NOT A COLUMN ON THE BOARDS (operator, 2026-08-08) ════════════════
//
// A "vs generic" column on Rankings / League Board is genuinely useful for a returning user and is
// carded as a fast-follow. It is the wrong shape for ACTIVATION. Someone who has just finished
// configuring a league is holding one question, and a column answers it as a footnote on a page
// about something else. Three consequences shaped this file:
//
//   1. The DELTA IS THE HEADLINE. Risers/fallers and the replacement-level shift render ABOVE the
//      board, not beside it. The board is the payoff you scroll to.
//   2. `custom_board_viewed` — the third clause of the activation definition — has ONE fire point,
//      here. Scattered across two browse surfaces, "when did this user activate?" stops having an
//      answer, and G100-D0's funnel is measured off that denominator.
//   3. It is the SMALLEST gating surface. Personalization is a PAID capability granted to free
//      accounts one league at a time, so every additional renderer of it is another place to gate
//      consistently — the freemium build shipped exactly that bug (#681 gated one of three
//      renderers and looked done).
//
// ══ COST ═══════════════════════════════════════════════════════════════════════════════════════
//
// No new per-view compute. The generic board and the projections are the SAME pre-built S3 blobs
// every browse surface already reads (and the CDN already serves the anonymous copies of); the
// league board is scored in the browser by `buildBoard`, the same scorer NF-C0e uses; the only
// added request is one DynamoDB point read (`/fantasy/nfl/my-teams`).
//
// ⚠️ This page is PER-CALLER and must stay off the CDN allowlist and the public cache rules. It is
// safe structurally rather than by memory: every request it makes carries `Authorization`, and
// `cost_guardrails.cache_control_for` answers `private, no-store` on any such request.

import { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import posthog from "posthog-js"
import {
  useFantasyBoard,
  useFantasyManifest,
  useMyTeams,
} from "@/lib/fantasy-queries"
import { freeSelection } from "@/lib/draft-optimizer"
import type { Player } from "@/lib/draft-optimizer"
import {
  HIGHLIGHT_COUNT,
  MEANINGFUL_MOVE,
  computeLeagueDelta,
  computePositionShifts,
} from "@/lib/league-delta"
import type { PlayerDelta } from "@/lib/league-delta"
import {
  EXPECTED_POINTS_LABEL,
  LEAGUE_DELTA_DEFINITION,
  LEAGUE_DELTA_MECHANISM,
  LEAGUE_DELTA_UNCERTAINTY,
  LEAGUE_VOR_DEFINITION,
  LEAGUE_WITHHELD_BY_QUOTA_DETAIL,
  MY_LEAGUE_BLURB,
  MY_LEAGUE_EMPTY_DETAIL,
  MY_LEAGUE_EMPTY_TITLE,
  MY_LEAGUE_HEADING,
} from "@/lib/fantasy-claim-copy"
import {
  ALL_POSITIONS,
  EmptyBlock,
  GLOSSARY,
  InfoTip,
  LoadingBlock,
  PosBadge,
  PositionTabs,
  ProvenanceLine,
  RookieBadge,
  SKILL_POSITIONS,
  SurfaceHeader,
  UncertaintyNote,
  int,
  num,
  teamLabel,
} from "@/components/fantasy/shared"

/** Signed, with an explicit zero — "0" reads as "did not move", which is the honest reading. */
function signed(n: number | null | undefined, nd = 0): string {
  if (n == null) return "—"
  const v = nd === 0 ? Math.round(n) : Number(n.toFixed(nd))
  if (v > 0) return `+${nd === 0 ? v : v.toFixed(nd)}`
  return `${nd === 0 ? v : v.toFixed(nd)}`
}

function MoveChip({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="text-gray-600">—</span>
  if (delta === 0) return <span className="text-gray-600">no change</span>
  const up = delta > 0
  return (
    <span
      className={up ? "font-medium text-[#10b981]" : "font-medium text-[#ef4444]"}
      data-testid="move-chip"
    >
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  )
}

/** One riser/faller card. Leads with the POSITION rank move ("TE7 → TE3") because that is the form
 *  a drafter reasons in; the overall move is the supporting number. */
function MoverCard({ d }: { d: PlayerDelta }) {
  return (
    <li className="rounded border border-[#1f1f1f] bg-[#0a0a0a] p-3" data-testid="mover-card">
      <div className="flex items-start justify-between gap-2">
        <Link
          href={`/fantasy/player/${d.id}`}
          className="truncate font-medium text-gray-200 hover:text-[#10b981] hover:underline"
        >
          {d.name}
        </Link>
        <MoveChip delta={d.ovrDelta} />
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-gray-500">
        <PosBadge pos={d.pos} />
        <span>
          {d.pos}
          {d.genericPosRank ?? "—"} → {d.pos}
          {d.leaguePosRank}
        </span>
      </div>
      {/* ⭐ THE OVERALL RANKS THEMSELVES, not just the size of the move. Two reasons, and the
          second is why it is written this way round:
          (a) "#128 → #34" is concrete in a way "+94 overall" is not — it says where he actually
              sits on the board the reader is about to scroll;
          (b) these two numbers come from the BOARDS, whereas the arrow above comes from `ovrDelta`.
              That makes them the independent quantity a test can anchor on: inverting the rank
              subtraction swaps which players appear here but cannot change these ranks, so a sign
              error becomes visible as a "riser" whose number got bigger. The first version of the
              spec asserted on the arrow and was a tautology (see `free-league.spec.ts`). */}
      <div className="mt-1 text-[11px] text-gray-600" data-testid="ovr-rank-move">
        #{d.genericOvrRank ?? "—"} → #{d.leagueOvrRank}
        {d.vorDelta != null && <> · {signed(d.vorDelta, 1)} value</>}
      </div>
    </li>
  )
}

export function MyLeague() {
  const { data: manifest } = useFantasyManifest()
  const { teams, isLoading: teamsLoading, data: payload } = useMyTeams()
  const [pos, setPos] = useState("All")

  // The FREE preset is the comparison baseline — read from the manifest rather than hardcoded, so
  // the paywall is stated in ONE place (`entitlement.FREE_BOARD_CONFIG`). `freeSelection` returns
  // null during the deploy-skew window, and the delta is simply withheld rather than computed
  // against a guessed default (which would be a wrong number rendered confidently).
  const free = freeSelection(manifest)
  const { data: genericBoard, isLoading: genericLoading } = useFantasyBoard(
    free?.config ?? null,
    free?.size ?? null,
  )

  // ⚠️ ONE league — this surface is deliberately singular. `/fantasy/nfl/my-teams` already caps its
  // response at the caller's quota, so for a free account this array holds at most one entry; taking
  // `[0]` here is reading what the server served, not a second cap. My Teams remains the surface for
  // a member browsing several.
  const entry = teams?.[0] ?? null
  const league = entry?.league ?? null
  const leagueBoard = entry?.board?.players ?? null

  const delta = useMemo(
    () => computeLeagueDelta(genericBoard, leagueBoard),
    [genericBoard, leagueBoard],
  )
  const shifts = useMemo(
    () => computePositionShifts(genericBoard, leagueBoard, SKILL_POSITIONS),
    [genericBoard, leagueBoard],
  )

  const ranked = useMemo(
    () =>
      (leagueBoard ?? []).filter(
        (p: Player) =>
          p.pts != null && p.vor != null && (ALL_POSITIONS as readonly string[]).includes(p.pos),
      ),
    [leagueBoard],
  )

  const rows = useMemo(() => {
    const byId = new Map((delta?.players ?? []).map((d) => [d.id, d]))
    const filtered = pos === "All" ? ranked : ranked.filter((r) => r.pos === pos)
    return filtered
      .slice()
      .sort((a, b) => (b.vor ?? 0) - (a.vor ?? 0))
      .map((p) => ({ player: p, d: byId.get(p.id) ?? null }))
  }, [ranked, pos, delta])

  // ── THE ACTIVATION EVENT ──────────────────────────────────────────────────────────────────────
  //
  // `custom_board_viewed` is the third clause of G100-C1's activation definition
  // (`account_created AND league_config_completed AND custom_board_viewed`) and one of G100-D0's
  // required events, so the NAME is a contract with the funnel dashboard — ⛔ do not rename it.
  //
  // ⭐ IT FIRES ON THE BOARD ACTUALLY RENDERING, not on the route mounting. Those differ by every
  // failure this page can have: no league saved, projections not published, the delta still
  // loading. Firing on mount would count a visitor who saw an empty state as activated, which
  // inflates the exact denominator paid conversion is measured against — and an inflated activation
  // rate reads as a CONVERSION problem, sending the next story to fix the wrong thing.
  //
  // The ref makes it once-per-mount: this component re-renders on every position-tab click, and a
  // per-render capture would multiply one activation by however much the user browsed.
  const fired = useRef(false)
  useEffect(() => {
    if (fired.current || !league || ranked.length === 0) return
    fired.current = true
    posthog.capture("custom_board_viewed", {
      league_platform: league.source_platform ?? "manual",
      league_format: league.ppr ?? null,
      league_size: league.n_teams ?? null,
      // The delta is what makes the view an ACTIVATION rather than a page load; carrying its size
      // lets the funnel tell "saw their board" from "saw their board CHANGE something".
      players_moved: delta?.meaningfulMoves ?? null,
      players_compared: delta?.compared ?? null,
    })
  }, [league, ranked.length, delta])

  const loading = teamsLoading || genericLoading || (!!league && !leagueBoard)
  const withheld = payload?.withheld_by_quota ?? 0

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title={league ? league.name : "My League"}
        blurb={MY_LEAGUE_BLURB}
      >
        <div className="mt-2">
          <ProvenanceLine
            season={manifest?.season ?? 2026}
            generatedAt={manifest?.generated_at}
            extra={
              league
                ? `${league.n_teams}-team${
                    league.source_platform ? ` · imported from ${league.source_platform}` : ""
                  }`
                : null
            }
          />
        </div>
      </SurfaceHeader>

      {/* ── no league yet ─────────────────────────────────────────────────────────────────────── */}
      {!teamsLoading && !league && (
        <div data-testid="my-league-empty">
          <EmptyBlock title={MY_LEAGUE_EMPTY_TITLE} detail={MY_LEAGUE_EMPTY_DETAIL} />
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              href="/fantasy/import"
              className="rounded bg-[#10b981] px-4 py-2 text-sm font-medium text-black hover:bg-[#0ea371]"
            >
              Import my league
            </Link>
            <Link
              href="/fantasy/league-settings"
              className="rounded border border-[#262626] px-4 py-2 text-sm font-medium text-gray-200 hover:border-[#10b981] hover:text-[#10b981]"
            >
              Enter it by hand
            </Link>
          </div>
        </div>
      )}

      {loading && <LoadingBlock label="Scoring your league…" />}

      {league && !loading && (
        <>
          {withheld > 0 && (
            <p
              className="mb-5 rounded-lg border border-[#262626] bg-[#0f0f0f] p-3 text-xs leading-relaxed text-gray-400"
              data-testid="quota-withheld-note"
            >
              {LEAGUE_WITHHELD_BY_QUOTA_DETAIL}
            </p>
          )}

          {/* ── THE AHA ───────────────────────────────────────────────────────────────────────── */}
          {delta && (
            <section
              className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4"
              data-testid="league-delta"
            >
              <h2 className="text-sm font-semibold text-gray-200">{MY_LEAGUE_HEADING}</h2>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-gray-500">
                {LEAGUE_DELTA_DEFINITION}
              </p>

              <p className="mt-3 text-sm text-gray-300" data-testid="delta-summary">
                <span className="font-semibold text-gray-100">{delta.meaningfulMoves}</span> of{" "}
                {delta.compared} players move at least {MEANINGFUL_MOVE} places in your scoring.
              </p>

              {delta.risers.length + delta.fallers.length === 0 ? (
                // ⚠️ A REAL AND CORRECT OUTCOME, not an error: a league configured close to
                // full-PPR/12 genuinely produces almost no movement. Saying so plainly is more
                // honest — and more trust-building — than manufacturing a highlight out of noise.
                <p className="mt-3 text-xs text-gray-500" data-testid="delta-no-movement">
                  Your settings are close enough to the free board that almost nothing moves. That
                  is a real answer: the generic rankings already describe your league well.
                </p>
              ) : (
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[#10b981]">
                      Worth more in your league
                    </h3>
                    <ul className="mt-2 space-y-2" data-testid="risers">
                      {delta.risers.map((d) => (
                        <MoverCard key={d.id} d={d} />
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[#ef4444]">
                      Worth less in your league
                    </h3>
                    <ul className="mt-2 space-y-2" data-testid="fallers">
                      {delta.fallers.map((d) => (
                        <MoverCard key={d.id} d={d} />
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              <p className="mt-4 text-[11px] leading-relaxed text-gray-600">
                {LEAGUE_DELTA_MECHANISM}
              </p>
            </section>
          )}

          {/* ── WHY: the replacement-level shift ──────────────────────────────────────────────── */}
          {shifts.length > 0 && (
            <section
              className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4"
              data-testid="replacement-shift"
            >
              <h2 className="text-sm font-semibold text-gray-200">
                Why those players moved
              </h2>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-gray-500">
                Replacement level is the points of the first player at a position who does not start
                anywhere in the league. Your roster shape and league size move it, and every player
                at that position moves with it.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {shifts.map((s) => (
                  <div
                    key={s.pos}
                    className="rounded border border-[#1f1f1f] bg-[#0a0a0a] p-3"
                    data-testid={`shift-${s.pos}`}
                  >
                    <PosBadge pos={s.pos} />
                    <div className="mt-2 text-lg font-semibold text-gray-100">
                      {num(s.leagueReplacement)}
                    </div>
                    <div className="text-[11px] text-gray-500">replacement pts</div>
                    <div className="mt-2 border-t border-[#1f1f1f] pt-2 text-[11px]">
                      <span
                        className={
                          s.replacementDelta == null
                            ? "text-gray-600"
                            : s.replacementDelta > 0
                              ? "text-[#ef4444]"
                              : "text-[#10b981]"
                        }
                      >
                        {signed(s.replacementDelta, 1)}
                      </span>{" "}
                      <span className="text-gray-600">vs the free board</span>
                    </div>
                    {s.leagueStartable != null && (
                      <div className="mt-1 text-[11px] text-gray-600">
                        {s.leagueStartable} startable
                        {s.genericStartable != null && (
                          <span> (was {s.genericStartable})</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── the board ─────────────────────────────────────────────────────────────────────── */}
          <div className="mb-4">
            <PositionTabs value={pos} onChange={setPos} />
          </div>

          <div className="overflow-x-auto rounded-lg border border-[#262626]">
            <table className="w-full min-w-[720px] text-left text-xs" data-testid="my-league-board">
              <thead className="bg-[#0f0f0f] text-gray-500">
                <tr>
                  <th className="px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Player</th>
                  <th className="px-3 py-2 font-medium">Pos</th>
                  <th className="px-3 py-2 font-medium">Team</th>
                  <th className="px-3 py-2 text-right font-medium">Bye</th>
                  <th className="px-3 py-2 text-right font-medium">
                    <InfoTip label={EXPECTED_POINTS_LABEL}>{GLOSSARY.expectedPoints}</InfoTip>
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    <InfoTip label="VOR">{LEAGUE_VOR_DEFINITION}</InfoTip>
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    {/* The delta's definition rides ON the column, because this is the cell most
                        likely to be read as a claim about the market. */}
                    <InfoTip label="vs free board">{LEAGUE_DELTA_DEFINITION}</InfoTip>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a]">
                {rows.map(({ player: p, d }, i) => (
                  <tr key={p.id} className="hover:bg-[#0f0f0f]">
                    <td className="px-3 py-2 text-gray-600">{i + 1}</td>
                    <td className="px-3 py-2">
                      <Link
                        href={`/fantasy/player/${p.id}`}
                        className="flex items-center gap-1.5 font-medium text-gray-200 hover:text-[#10b981] hover:underline"
                      >
                        <span>{p.name}</span>
                        {p.rookie && <RookieBadge />}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      <PosBadge pos={p.pos} />
                    </td>
                    <td className="px-3 py-2 text-gray-400">{teamLabel(p)}</td>
                    <td className="px-3 py-2 text-right text-gray-500">{p.bye ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-gray-300">{num(p.pts)}</td>
                    <td className="px-3 py-2 text-right font-semibold text-gray-100">
                      {num(p.vor)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {/* A player absent from the free board has an UNDEFINED move, not a zero —
                          e.g. a superflex league ranking a QB the free roster shape leaves out.
                          Rendering 0 there would assert he did not move. */}
                      {d?.onlyInLeague ? (
                        <span className="text-gray-600" title="Not ranked on the free board">
                          new
                        </span>
                      ) : (
                        <MoveChip delta={d?.ovrDelta ?? null} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-6">
            <UncertaintyNote>
              <p className="mt-2">{LEAGUE_DELTA_UNCERTAINTY}</p>
              <p className="mt-2">
                <span className="font-semibold text-gray-300">About value over replacement.</span>{" "}
                {LEAGUE_VOR_DEFINITION}
              </p>
            </UncertaintyNote>
          </div>

          <p className="mt-4 text-[11px] text-gray-600">
            Changed your settings?{" "}
            <Link href="/fantasy/league-settings" className="text-gray-400 hover:text-[#10b981]">
              Edit this league
            </Link>{" "}
            and the board re-scores immediately.
          </p>
        </>
      )}

      {/* An entitlement-independent footnote: HIGHLIGHT_COUNT is referenced so the constant and the
          rendered lists cannot drift apart silently. */}
      {league && !loading && delta && delta.risers.length > 0 && (
        <p className="mt-2 text-[11px] text-gray-700">
          Showing the {HIGHLIGHT_COUNT} largest moves in each direction; the full board is above.
        </p>
      )}
    </div>
  )
}
