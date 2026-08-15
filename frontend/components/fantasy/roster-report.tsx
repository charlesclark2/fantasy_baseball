"use client"

// NF-C6P2 — THE POST-DRAFT ROSTER REPORT. The monetization bridge for the post-draft window: a user
// finishes their draft, imports the result, reads an honest account of what they built, and meets
// the season-upgrade prompt at the one moment it is genuinely useful to them.
//
// ══ WHERE EVERY NUMBER COMES FROM ═══════════════════════════════════════════════════════════════
//
// ONE request: `/fantasy/nfl/league-board` (via `useLeagueBoard`), which returns this league's
// server-scored board plus the caller's roster already joined to it. `lib/roster-report.ts` then
// SUMS and RANKS those served values — it scores nothing and fetches nothing. Two reasons, and both
// are constraints rather than preferences:
//
//   ⛔ NO WIDE READ. `lakehouse_query` inside the API Lambda fails SILENTLY and returns `[]`
//      (E9.26b), so a panel built on one renders empty with no error anywhere. The league board is
//      the narrowest served artifact that answers every output on this page.
//   ⛔ NO FOURTH SCORER. `fantasy_engine` (authority) / `lib/league-scoring.ts` / the Lambda's
//      `league_scoring.py` are already three implementations of one policy, pinned together by
//      `test_nf_epic1_parity.py`. Re-deriving points here would inherit that whole tax; and it
//      could not work anyway, since the raw stat line is paid and never reaches this browser.
//
// ══ WHAT THIS PAGE MAY AND MAY NOT SAY ══════════════════════════════════════════════════════════
//
// The reader is primed for a verdict — "did I win my draft?" — and we have measured nothing that
// answers it. So: no grade, no projected finish, no ranking against the other eleven managers (we
// do not hold their rosters), no win probability. Every claim is arithmetic on our own projections
// against our own replacement levels, and every string is in `fantasy-claim-copy.ts` so the
// denylist screening in `test_nf_tr1_claim_copy.py` runs over it. `best_alpha = 0`.
//
// ══ GATE ════════════════════════════════════════════════════════════════════════════════════════
//
// `FantasyLeagueGuard` — signed in with a personalization quota above zero, i.e. every signed-in
// account (the free quota is 1). Deliberately NOT `FantasyGuard`: gating the conversion surface on
// the entitlement it is trying to sell would hide it from exactly the users it exists for. The
// server enforces ownership AND the quota on `/fantasy/nfl/league-board` regardless.
//
// ⚠️ PER-CALLER BY CONSTRUCTION — every request carries `Authorization` and
// `cost_guardrails.cache_control_for` answers `private, no-store`. It must never join the CDN
// allowlist or `_PUBLIC_CACHE_RULES`.

import { useMemo, useState } from "react"
import Link from "next/link"
import { useMyTeams, useLeagueBoard } from "@/lib/fantasy-queries"
import {
  buildRosterReport,
  perGameRate,
  type ByeWeek,
  type PositionStrength,
  type ReportPlayer,
  type RosterReport,
  type WaiverIdea,
} from "@/lib/roster-report"
import {
  REPORT_BENCH_NOTE,
  REPORT_BYE_NOTE,
  REPORT_EMPTY,
  REPORT_FIRST_WEEK_NOTE,
  REPORT_FRAGILITY_NOTE,
  REPORT_LEAGUE_BASELINE_NOTE,
  REPORT_POSITION_DEFINITION,
  REPORT_TRADE_NOTE,
  REPORT_UPGRADE_CTA,
  REPORT_UPGRADE_DETAIL,
  REPORT_UPGRADE_HEADING,
  REPORT_WAIVER_NOTE,
  ROSTER_REPORT_BLURB,
  ROSTER_REPORT_HEADING,
  ROSTER_REPORT_RANGE_NOTE,
  EXPECTED_POINTS_LABEL,
} from "@/lib/fantasy-claim-copy"
import {
  EmptyBlock,
  GLOSSARY,
  InfoTip,
  LoadingBlock,
  PosBadge,
  RangeCell,
  SUBSCRIBE_HREF,
  SurfaceHeader,
  num,
  int,
} from "@/components/fantasy/shared"
import { Picker } from "@/components/ui/picker"
import { useAuth } from "@/lib/auth-context"
import { canAccess } from "@/lib/entitlements"

function Section({
  title,
  note,
  children,
  testId,
}: {
  title: string
  note?: string
  children: React.ReactNode
  testId: string
}) {
  return (
    <section className="mt-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-5" data-testid={testId}>
      <h2 className="text-sm font-semibold text-gray-200">{title}</h2>
      {note && <p className="mt-1.5 max-w-3xl text-[12px] leading-relaxed text-gray-500">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

// ══ THE TABS ═════════════════════════════════════════════════════════════════════════════════════
//
// Operator, 2026-08-15, on the shipped single-column build: "the organization of this page isn't the
// easiest because you have to do so much scrolling" — eight stacked sections is roughly four screens
// on a laptop, and the sections a drafter actually acts on (byes, the wire) were the furthest down.
// Every leading competitor tabs this surface.
//
// ⭐ TWO THINGS DELIBERATELY STAY OUTSIDE THE TABS, and both are load-bearing:
//
//   1. THE TEAM PROJECTION, because it is the answer to the question the page is opened with, and a
//      headline you have to select a tab to see is not a headline. It also carries the uncertainty
//      disclosure and the unmatched-roster note — neither may end up on a tab a reader never opens,
//      since a caveat behind a click is a caveat that did not render.
//   2. THE UPGRADE PROMPT, because burying the conversion moment behind a tab is exactly how this
//      surface would stop doing the job it exists for.
//
// The four groupings are by the QUESTION each answers, not by data type: what have I got (Positions)
// · who starts (Lineup) · can I cover a gap (Depth & byes) · what do I do next (Next moves).
const TABS = [
  { id: "positions", label: "Positions" },
  { id: "lineup", label: "Lineup" },
  { id: "depth", label: "Depth & byes" },
  { id: "moves", label: "Next moves" },
] as const

type TabId = (typeof TABS)[number]["id"]

/** ⚠️ Real tab semantics, not styled buttons: `tablist`/`tab`/`tabpanel` with `aria-selected` is what
 *  makes the grouping legible to a screen reader, and it is what the E2E locates by role. */
function Tabs({ value, onChange }: { value: TabId; onChange: (t: TabId) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Roster report sections"
      className="mt-6 flex flex-wrap gap-1.5 border-b border-[#262626] pb-3"
      data-testid="report-tabs"
    >
      {TABS.map((t) => (
        <button
          key={t.id}
          role="tab"
          id={`report-tab-${t.id}`}
          aria-selected={value === t.id}
          aria-controls={`report-panel-${t.id}`}
          onClick={() => onChange(t.id)}
          className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
            value === t.id
              ? "border-[#10b981]/50 bg-[#10b981]/10 text-[#10b981]"
              : "border-[#262626] bg-[#0f0f0f] text-gray-400 hover:text-gray-200"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function Panel({ id, active, children }: { id: TabId; active: TabId; children: React.ReactNode }) {
  if (id !== active) return null
  return (
    <div role="tabpanel" id={`report-panel-${id}`} aria-labelledby={`report-tab-${id}`}>
      {children}
    </div>
  )
}

/** A signed figure with an explicit zero — "0" reads as "did not move", the honest reading. */
function signed(v: number | null | undefined, nd = 1): string {
  if (v == null || !Number.isFinite(v)) return "—"
  const r = Number(v.toFixed(nd))
  return r > 0 ? `+${r.toFixed(nd)}` : r.toFixed(nd)
}

export function RosterReport() {
  const { groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  const { teams, isLoading: teamsLoading, isError: teamsError } = useMyTeams()

  // The league to report on. A free account has exactly one; a subscriber picks. Defaulting to the
  // first served league keeps the common case zero-click, which matters on a surface someone opens
  // once, straight out of a draft.
  const [selected, setSelected] = useState<string | null>(null)
  const leagueId = selected ?? teams?.[0]?.league.league_id ?? null

  const { data, isLoading: boardLoading, isError: boardError } = useLeagueBoard(leagueId)
  const report = useMemo(() => buildRosterReport(data), [data])

  if (teamsError) {
    return (
      <Shell>
        <EmptyBlock
          title="Could not load your leagues"
          detail="Something went wrong reading your saved leagues. Try reloading the page."
        />
      </Shell>
    )
  }
  if (teamsLoading || teams === null) {
    return (
      <Shell>
        <LoadingBlock label="Loading your leagues…" />
      </Shell>
    )
  }
  if (teams.length === 0) {
    return (
      <Shell>
        <Empty reason="no-league" />
      </Shell>
    )
  }

  return (
    <Shell>
      {teams.length > 1 && (
        <div className="mb-4 max-w-sm">
          <div className="text-[11px] uppercase tracking-wider text-gray-500">League</div>
          {/* ⚠️ `Picker`, NOT a raw <select> — on iOS the native popup opens detached from the
              control it belongs to, on every surface that uses one (see `components/ui/picker.tsx`).
              `test_mobile_form_control_guard.py` enforces this repo-wide, and it caught exactly this
              control. Consequence for the E2E: `selectOption` silently does nothing on a Radix
              trigger, so the spec clicks the trigger and then the option. */}
          <Picker
            id="report-league"
            className="mt-1 w-full"
            ariaLabel="League"
            value={leagueId}
            onValueChange={setSelected}
            options={teams.map((t) => ({
              value: t.league.league_id,
              label: t.league.name,
            }))}
          />
        </div>
      )}

      {/* ⚠️ A FAILED READ IS NOT AN EMPTY ROSTER, and the two must not share a message. The board IS
          the response here (unlike `/nfl/my-teams`, which degrades to "no roster linked"), so a
          read failure has to surface as a real fault the page reports. */}
      {boardError && <Empty reason="no-board" />}
      {!boardError && boardLoading && <LoadingBlock label="Building your report…" />}
      {!boardError && !boardLoading && !report.ready && <Empty reason={report.reason} />}
      {!boardError && report.ready && <Report report={report} entitled={entitled} />}
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <SurfaceHeader title={ROSTER_REPORT_HEADING} blurb={ROSTER_REPORT_BLURB} />
      {children}
    </div>
  )
}

/** ⚠️ FIVE DISTINCT FACTS, FIVE DISTINCT MESSAGES. NF-C6 already shipped the bug where "you never
 *  picked a team" and "your league has not drafted" shared a message and told a user to do something
 *  they had already done. `REPORT_EMPTY` keys on the reason for exactly that reason. */
function Empty({ reason }: { reason: keyof typeof REPORT_EMPTY }) {
  const copy = REPORT_EMPTY[reason]
  return (
    <div data-testid={`report-empty-${reason}`}>
      <EmptyBlock title={copy.title} detail={copy.detail} />
    </div>
  )
}

function Report({ report, entitled }: { report: RosterReport; entitled: boolean }) {
  const [tab, setTab] = useState<TabId>("positions")
  const { projection, coverage, positions, bench, byes, fragility, waivers, trades } = report
  const ranked = positions
    .filter((p) => p.edge != null && p.starters > 0)
    .sort((a, b) => (b.edge as number) - (a.edge as number))

  return (
    <div data-testid="roster-report">
      {/* ── The headline ─────────────────────────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-5" data-testid="team-projection">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500">
              <InfoTip label={`Starting lineup · ${EXPECTED_POINTS_LABEL}`}>
                {GLOSSARY.expectedPoints}
              </InfoTip>
            </div>
            <div className="font-mono text-3xl font-bold text-white" data-testid="team-total">
              {num(projection.total, 1)}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500">80% range</div>
            <div className="font-mono text-lg text-gray-300" data-testid="team-range">
              <RangeCell p10={projection.p10} p90={projection.p90} />
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500">Starters</div>
            <div className="font-mono text-lg text-gray-300">
              {int(projection.starters)}
              {projection.unfilled > 0 && (
                <span className="ml-2 text-xs font-normal text-[#f59e0b]">
                  {projection.unfilled} slot{projection.unfilled === 1 ? "" : "s"} unfilled
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ⭐ THE UNCERTAINTY DISCLOSURE, rendered WITH the number and not behind a disclosure. The
            band is an assumption with a known direction of error (independence under-disperses a
            correlated sum — NF-W7b measured it), so the comonotone bound is printed beside it
            rather than the independent one being presented as "the" range. */}
        <p className="mt-4 max-w-3xl text-[12px] leading-relaxed text-gray-500">
          {ROSTER_REPORT_RANGE_NOTE}
        </p>
        {projection.correlatedP10 != null && projection.correlatedP90 != null && (
          <p className="mt-1 font-mono text-[12px] text-gray-500" data-testid="team-range-correlated">
            If every season moved in step: {num(projection.correlatedP10, 1)} – {num(projection.correlatedP90, 1)}
          </p>
        )}

        {coverage.unmatched.length > 0 && (
          // An absence is reported, never imputed. Scoring an unresolved row as zero would understate
          // the team; dropping it silently would overstate the coverage.
          <p className="mt-3 text-[12px] text-[#f59e0b]" data-testid="report-unmatched">
            {coverage.matched} of {coverage.rosterRows} rostered players matched a projection.
            Not counted above: {coverage.unmatched.join(", ")}.
          </p>
        )}
      </section>

      <Tabs value={tab} onChange={setTab} />

      {/* ── Positions ────────────────────────────────────────────────────────────────────────── */}
      <Panel id="positions" active={tab}>
      <Section
        testId="position-strengths"
        title="Where you are strong, and where you are thin"
        note={`${REPORT_POSITION_DEFINITION} ${REPORT_LEAGUE_BASELINE_NOTE}`}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-[12px]">
            <thead>
              <tr className="text-gray-500">
                <th className="py-1 pr-3 font-medium">Position</th>
                <th className="py-1 pr-3 font-medium">Starters</th>
                <th className="py-1 pr-3 text-right font-medium">Their points</th>
                <th className="py-1 pr-3 text-right font-medium">Value over replacement</th>
                <th className="py-1 pr-3 text-right font-medium">vs an average team</th>
                <th className="py-1 pr-3 text-right font-medium">Depth</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((p) => (
                <PositionRow key={p.pos} p={p} />
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      </Panel>

      <Panel id="lineup" active={tab}>
      {/* ── The starting lineup ──────────────────────────────────────────────────────────────
          ⭐ ONE TABLE, AND IT IS THE ONE THE HEADLINE SUMS. The report has two legitimate lineups —
          the SEASON one (ordered by season points, which is what `team-total` above adds up) and the
          WEEK-1 one (ordered by points per game played, with week-1 byes removed). Rendering both as
          tables would put two different "best nine"s on one page and leave the headline agreeing
          with neither in the reader's eyes. So the table IS the season lineup, its total is
          verifiable by adding the column up, and the week-1 view is reported as the DIFFERENCE —
          which is the only part of it that is news. */}
      <Section testId="starting-lineup" title="Your starting lineup" note={REPORT_FIRST_WEEK_NOTE}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-[12px]">
            <thead>
              <tr className="text-gray-500">
                <th className="py-1 pr-3 font-medium">Slot</th>
                <th className="py-1 pr-3 font-medium">Player</th>
                <th className="py-1 pr-3 font-medium">Pos</th>
                <th className="py-1 pr-3 text-right font-medium">Per game</th>
                <th className="py-1 pr-3 text-right font-medium">Season</th>
              </tr>
            </thead>
            <tbody>
              {report.lineup.slots.map((s, i) => (
                <tr key={`${s.name}-${i}`} className="border-t border-white/5" data-testid="lineup-row">
                  <td className="py-1 pr-3 text-gray-400">{s.name}</td>
                  <td className="py-1 pr-3 text-gray-200">
                    {s.player ? s.player.name : <span className="text-[#f59e0b]">nobody eligible</span>}
                  </td>
                  <td className="py-1 pr-3">
                    {s.player ? <PosBadge pos={s.player.pos} /> : <span className="text-gray-600">—</span>}
                  </td>
                  <td className="py-1 pr-3 text-right font-mono text-gray-300">
                    {s.player ? num(perGameRate(s.player), 1) : "—"}
                  </td>
                  <td className="py-1 pr-3 text-right font-mono text-gray-400" data-testid="lineup-season-pts">
                    {s.player ? num(s.player.pts, 1) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <FirstWeekDifference report={report} />
      </Section>

      </Panel>

      <Panel id="depth" active={tab}>
      {/* ── Bench ───────────────────────────────────────────────────────────────────────────── */}
      <Section testId="bench-quality" title="Your bench" note={REPORT_BENCH_NOTE}>
        <p className="text-[13px] text-gray-300" data-testid="bench-summary">
          {int(bench.count)} player{bench.count === 1 ? "" : "s"} on the bench,{" "}
          {int(bench.aboveReplacement)} of them worth more than a freely-available replacement, and{" "}
          {int(bench.startable.length)} good enough to be starting somewhere in this league.
        </p>
        {bench.startable.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {bench.startable.map((p) => (
              <li
                key={p.key}
                className="rounded border border-[#1f1f1f] bg-[#0a0a0a] px-2 py-1 text-[12px] text-gray-300"
              >
                {p.name} <span className="text-gray-500">{p.pos}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* ── Bye weeks ───────────────────────────────────────────────────────────────────────── */}
      <Section testId="bye-conflicts" title="Bye weeks" note={REPORT_BYE_NOTE}>
        {byes.length === 0 ? (
          <p className="text-[13px] text-gray-400">
            No bye weeks are known for your roster yet — the season schedule has not reached our board.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-[12px]">
              <thead>
                <tr className="text-gray-500">
                  <th className="py-1 pr-3 font-medium">Week</th>
                  <th className="py-1 pr-3 font-medium">Idle</th>
                  <th className="py-1 pr-3 text-right font-medium">Points per game lost</th>
                  <th className="py-1 pr-3 text-right font-medium">Unfillable slots</th>
                </tr>
              </thead>
              <tbody>
                {byes.map((b) => (
                  <ByeRow key={b.week} b={b} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* ── Fragility ───────────────────────────────────────────────────────────────────────── */}
      <Section testId="fragility" title="Where your projection is concentrated" note={REPORT_FRAGILITY_NOTE}>
        <ul className="space-y-1.5 text-[13px] text-gray-300">
          {fragility.topTwoShare != null && (
            <li data-testid="fragility-concentration">
              Your top two starters carry {num(fragility.topTwoShare * 100, 0)}% of the starting
              lineup&rsquo;s projection.
            </li>
          )}
          {fragility.expectedGamesMissed != null && (
            <li data-testid="fragility-availability">
              Across your starters the model expects {num(fragility.expectedGamesMissed, 1)} missed
              games in total, spread over {int(fragility.atRisk.length)} player
              {fragility.atRisk.length === 1 ? "" : "s"}.
            </li>
          )}
          {fragility.worstCover && (
            <li data-testid="fragility-cover">
              Your thinnest slot is {fragility.worstCover.slot}: if {fragility.worstCover.player.name}{" "}
              is unavailable, the best body on your bench is{" "}
              {fragility.worstCover.replacement
                ? `${fragility.worstCover.replacement.name}, ${num(fragility.worstCover.drop, 1)} points per game lower`
                : `nobody eligible — you would lose the whole slot (${num(fragility.worstCover.drop, 1)} points per game)`}
              .
            </li>
          )}
        </ul>
      </Section>

      </Panel>

      <Panel id="moves" active={tab}>
      {/* ── Waivers ─────────────────────────────────────────────────────────────────────────── */}
      <Section testId="waiver-ideas" title="Worth a look on the wire" note={REPORT_WAIVER_NOTE}>
        {waivers.length === 0 ? (
          <p className="text-[13px] text-gray-400">
            Nothing outside the drafted pool stands out against what you already hold.
          </p>
        ) : (
          <ul className="space-y-2">
            {waivers.map((w) => (
              <WaiverRow key={w.player.id} w={w} />
            ))}
          </ul>
        )}
        {report.poolSize != null && (
          <p className="mt-3 text-[11px] text-gray-600">
            &ldquo;Outside the drafted pool&rdquo; means beyond board rank {int(report.poolSize)} —{" "}
            {int(report.league.n_teams)} teams times the drafted slots in your roster.
          </p>
        )}
      </Section>

      {/* ── Trades ──────────────────────────────────────────────────────────────────────────── */}
      <Section testId="trade-ideas" title="The trade your roster shape suggests" note={REPORT_TRADE_NOTE}>
        {trades.length === 0 ? (
          <p className="text-[13px] text-gray-400">
            Your bench holds nobody who would be starting elsewhere in this league, so there is no
            surplus to trade from.
          </p>
        ) : (
          <ul className="space-y-2 text-[13px] text-gray-300">
            {trades.map((t) => (
              <li key={`${t.from}-${t.to}`} data-testid="trade-idea">
                You hold {int(t.surplus.length)} startable {t.from}
                {t.surplus.length === 1 ? "" : "s"} on the bench (
                {t.surplus.map((p) => p.name).join(", ")}) and your thinnest starters are at {t.to}.
              </li>
            ))}
          </ul>
        )}
      </Section>

      </Panel>

      {/* ── The conversion moment ───────────────────────────────────────────────────────────── */}
      <UpgradePrompt entitled={entitled} />
    </div>
  )
}

/**
 * Week 1 as a DIFFERENCE from the season lineup, not as a second table.
 *
 * The two lineups are built on different currencies — season points, and points per game played
 * with week-1 byes removed — so they can legitimately pick different players. Naming only who
 * changes keeps the season table's total addable and makes the week-1 view a statement rather than
 * a duplicate. When they agree, saying so is the useful answer.
 */
function FirstWeekDifference({ report }: { report: RosterReport }) {
  const changes = report.firstWeek.slots
    .map((s, i) => ({ slot: s.name, week1: s.player, season: report.lineup.slots[i]?.player ?? null }))
    .filter((c) => (c.week1?.key ?? null) !== (c.season?.key ?? null))
  if (changes.length === 0) {
    return (
      <p className="mt-3 text-[12px] text-gray-500" data-testid="first-week-same">
        Your week 1 lineup is the same nine — nobody is on a bye and the per-game order agrees with
        the season order.
      </p>
    )
  }
  return (
    <p className="mt-3 text-[12px] text-gray-500" data-testid="first-week-diff">
      In week 1, ranked by points per game played and with that week&rsquo;s byes removed,{" "}
      {changes
        .map(
          (c) =>
            `${c.week1?.name ?? "nobody"} takes the ${c.slot} slot instead of ${c.season?.name ?? "an empty spot"}`,
        )
        .join("; ")}
      .
    </p>
  )
}

function PositionRow({ p }: { p: PositionStrength }) {
  const edge = p.edge
  const tone = edge == null ? "text-gray-500" : edge > 0 ? "text-[#10b981]" : "text-[#ef4444]"
  return (
    <tr className="border-t border-white/5" data-testid={`position-row-${p.pos}`}>
      <td className="py-1 pr-3">
        <PosBadge pos={p.pos} />
      </td>
      <td className="py-1 pr-3 text-gray-400">{int(p.starters)}</td>
      <td className="py-1 pr-3 text-right font-mono text-gray-300">{num(p.startersPts, 1)}</td>
      <td className="py-1 pr-3 text-right font-mono text-gray-300">{num(p.startersVor, 1)}</td>
      <td className={`py-1 pr-3 text-right font-mono ${tone}`} data-testid={`position-edge-${p.pos}`}>
        {signed(edge, 1)}
      </td>
      <td className="py-1 pr-3 text-right text-gray-400">{int(p.depth)}</td>
    </tr>
  )
}

function ByeRow({ b }: { b: ByeWeek }) {
  return (
    <tr className="border-t border-white/5" data-testid={`bye-week-${b.week}`}>
      <td className="py-1 pr-3 text-gray-300">{b.week}</td>
      <td className="py-1 pr-3 text-gray-400">
        {b.out.map((p: ReportPlayer) => p.name).join(", ")}
      </td>
      <td className="py-1 pr-3 text-right font-mono text-gray-300" data-testid={`bye-cost-${b.week}`}>
        {b.cost == null ? "—" : num(b.cost, 1)}
      </td>
      <td className="py-1 pr-3 text-right text-gray-400">
        {b.unfilled > 0 ? <span className="text-[#f59e0b]">{b.unfilled}</span> : 0}
      </td>
    </tr>
  )
}

function WaiverRow({ w }: { w: WaiverIdea }) {
  const why =
    w.kind === "bye-cover"
      ? `cover for your week ${w.becauseWeek} bye`
      : w.kind === "thinnest-position"
        ? `depth at ${w.becausePos}, your thinnest starting spot`
        : "the widest upside in his 80% range"
  return (
    <li className="rounded border border-[#1f1f1f] bg-[#0a0a0a] p-3" data-testid="waiver-idea">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium text-gray-200">
          {w.player.name} <span className="ml-1 text-[12px] text-gray-500">{w.player.pos}</span>
        </span>
        <span className="font-mono text-[12px] text-gray-400">
          {num(w.player.pts, 1)} · <RangeCell p10={w.player.ptsP10} p90={w.player.ptsP90} />
        </span>
      </div>
      <p className="mt-1 text-[12px] text-gray-500">{why}</p>
    </li>
  )
}

/**
 * ⭐ THE CONVERSION MOMENT — and the reason it is a component with an `entitled` prop rather than a
 * block of JSX. A subscriber must never be sold what they already pay for: showing them an upgrade
 * prompt reads as a bug in our billing, which is the freemium build's own lesson.
 *
 * ⛔ IT SELLS ONGOING ANALYSIS, NOT AN OUTCOME. Every string is in `fantasy-claim-copy.ts` and is
 * screened by the claim denylist; nothing here promises a result, and nothing implies the free
 * report is withholding an edge (`best_alpha = 0`).
 */
function UpgradePrompt({ entitled }: { entitled: boolean }) {
  if (entitled) return null
  return (
    <section
      className="mt-8 rounded-lg border border-[#10b981]/30 bg-[#0f1a16] p-5"
      data-testid="season-upgrade-prompt"
    >
      <h2 className="text-sm font-semibold text-gray-100">{REPORT_UPGRADE_HEADING}</h2>
      <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-gray-400">
        {REPORT_UPGRADE_DETAIL}
      </p>
      <Link
        href={SUBSCRIBE_HREF}
        className="mt-4 inline-block rounded-md bg-[#10b981] px-3.5 py-2 text-sm font-semibold text-black transition-colors hover:bg-[#34d399]"
      >
        {REPORT_UPGRADE_CTA}
      </Link>
    </section>
  )
}
