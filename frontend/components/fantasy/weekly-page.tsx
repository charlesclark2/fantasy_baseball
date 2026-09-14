"use client"

// NF-WK-FE1 — the WEEKLY projections surface: the first thing users see of the in-season model.
//
// ⭐ PUBLIC. The two reads this page depends on (`weekly/manifest`, `weekly/projections`) are FREE
// and BYTE-IDENTICAL for every caller — neither handler takes a `Request`, so neither can branch on
// who is asking. The only entitled thing on the page is the STAT-LINE panel, and it is gated by
// WHICH COMPONENT PRINTS rather than by what the page holds (the G100 lesson: #681 gated one of
// three renderers and looked complete).
//
// ══ THE FOUR EMPTY STATES ARE FOUR DIFFERENT FACTS ══════════════════════════════════════════════
//
// A surface whose "nothing here" renders identically for several causes makes every recurrence
// re-investigate from scratch (NF-C6b/NF-K1 cost the same D/ST symptom two investigations). All
// four are reachable in the E2E harness:
//
//   * AWAITING PUBLISH — the week has not been built. The API answers **404**, which on this
//                        surface is the ORDINARY state between builds, not a fault. Measured on the
//                        live API 2026-09-13: both free routes 404 with
//                        `{"detail":"Weekly projection not found"}`. Hence `retry: false` — three
//                        retries of a normal answer buy a spinner in front of the same empty state.
//   * A FAILED READ    — anything that is not a 404. "We could not reach the model" is a problem on
//                        our side and says so.
//   * AN ABSENT PLAYER — never a row. He is counted in the manifest's `absences`, by machine-
//                        readable reason, and the panel names the reason.
//   * A BYE            — a ROW, with a stated zero. ⛔ NOT an empty state at all, and conflating it
//                        with one is the specific error this page must not make: a bye is a
//                        DETERMINISTIC zero knowable at schedule release.
//
// ⛔ NO PICK, NO EDGE, NO START/SIT. `best_alpha = 0`. The table is ordered by our projected points
// — which is what its column header says — and that is an ordering, not advice.
//
// ⛔ NO SCORING ARITHMETIC ANYWHERE IN THIS TREE, and in particular the stat line is NEVER SUMMED.
// See `WEEKLY_STAT_LINE_NOTE`: the points head and the component head are independent models, so a
// total derived from the line is a SECOND number that does not equal the first and that no reader
// could reconcile. There is no fourth scorer here and no derived total.

import { useMemo, useState } from "react"
import Link from "next/link"
import { apiErrorStatus } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { canUse } from "@/lib/entitlements"
import {
  WEEKLY_SEASON,
  WEEKLY_PROJECTED_POSITIONS,
  WEEKLY_STAT_FIELDS,
  WEEKLY_STATS_BY_POSITION,
  byWeeklyPoints,
  hasStatLine,
  useWeeklyManifest,
  useWeeklyProjections,
  useWeeklyProjectionsFull,
  type NflWeeklyManifest,
  type NflWeeklyPlayer,
  type WeeklyPosition,
} from "@/lib/nfl-weekly"
import {
  WEEKLY_ABSENCE_HEADING,
  WEEKLY_ABSENCE_LABEL,
  WEEKLY_AWAITING_PUBLISH_DETAIL,
  WEEKLY_AWAITING_PUBLISH_TITLE,
  WEEKLY_BYE_DEFINITION,
  WEEKLY_BYE_LABEL,
  WEEKLY_HIST_DEFINITION,
  WEEKLY_HIST_LABEL,
  WEEKLY_PAGE_STANDFIRST,
  WEEKLY_PAGE_TITLE,
  WEEKLY_POINTS_DEFINITION,
  WEEKLY_POINTS_LABEL,
  WEEKLY_PPR_NATIVE_DETAIL,
  WEEKLY_PPR_NATIVE_TITLE,
  WEEKLY_RANGE_DEFINITION,
  WEEKLY_RANGE_LABEL,
  WEEKLY_READ_FAILED,
  WEEKLY_ROS_DEFINITION,
  WEEKLY_ROS_LABEL,
  WEEKLY_STAT_LINE_ABSENT,
  WEEKLY_STAT_LINE_HEADING,
  WEEKLY_STAT_LINE_LOCK_DETAIL,
  WEEKLY_STAT_LINE_LOCK_TITLE,
  WEEKLY_STAT_LINE_NOTE,
} from "@/lib/fantasy-claim-copy"
import {
  EmptyBlock,
  FreemiumBoundary,
  InfoTip,
  IntervalBar,
  LoadingBlock,
  PosBadge,
  PositionTabs,
  SUBSCRIBE_HREF,
  SurfaceHeader,
  num,
} from "@/components/fantasy/shared"

/** One decimal, and an em-dash for a declared null. ⚠️ A null `ros*` is the season's final week —
 *  a DECLARED state, not a missing value — so it renders as an explicit absence rather than as a
 *  zero, which would be a different (and false) claim. */
const fmt = (v: number | null | undefined) => (v == null ? "—" : num(v, 1))

/**
 * An input vintage, in the reader's own locale.
 *
 * ⭐ THE WHOLE POINT OF SHOWING PER-INPUT VINTAGES IS THAT STALENESS IS LEGIBLE AT A GLANCE
 * (NF-FRESH2: one build date rendered over inputs of several vintages HIDES staleness). A raw
 * `2026-09-16T09:02:11+00:00` is visible but not legible — a reader cannot tell at a glance that it
 * is three days old, and printing it beside a locale-formatted build time makes the line read as
 * two different kinds of fact. Same formatting for every timestamp on the line, or the comparison
 * the line exists to support has to be done in the reader's head.
 *
 * ⚠️ FAILS TOWARD THE RAW STRING RATHER THAN TOWARD "unknown". An unparseable vintage is still
 * INFORMATION — it is what the builder stamped — and replacing it with a friendly word would
 * discard the only evidence of whatever went wrong upstream. A genuinely absent one is `null` on
 * the wire and says "unknown", which is a different fact and reads as one.
 */
function vintage(iso: string | null | undefined): string {
  if (!iso) return "unknown"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

/** The shared domain every row's band is drawn on, so two bars are comparable at a glance.
 *
 * ⚠️ COMPUTED OVER THE ROWS ACTUALLY SHOWN, not over a constant. A fixed domain would squash a
 * quiet week's bars into invisibility and a fixed MAX would clip a big one. Guarded against a
 * degenerate span (every row identical, or a single row) because `IntervalBar` divides by it. */
function bandDomain(rows: NflWeeklyPlayer[]): { min: number; max: number } {
  if (!rows.length) return { min: 0, max: 1 }
  const lo = Math.min(...rows.map((r) => r.fpP10))
  const hi = Math.max(...rows.map((r) => r.fpP90))
  return hi > lo ? { min: lo, max: hi } : { min: lo, max: lo + 1 }
}

/** The week a row belongs to, said once, in the reader's own terms. */
function WeekHeading({ manifest }: { manifest: NflWeeklyManifest }) {
  return (
    <span data-testid="weekly-week-label" className="text-sm font-medium text-gray-300">
      {manifest.season} · Week {manifest.week}
    </span>
  )
}

/**
 * The opponent cell. ⚠️ A BYE HAS NO OPPONENT AND NO HOME FLAG — both are null on the wire — so it
 * renders the bye label rather than an em-dash: "not playing" is a fact we know, and an em-dash
 * would say "we do not know", which is the merged-empty-state error one cell down.
 */
function OpponentCell({ p }: { p: NflWeeklyPlayer }) {
  if (p.status === "bye") {
    return (
      <span data-testid="weekly-bye-chip" className="rounded bg-[#3f2d1a] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
        {WEEKLY_BYE_LABEL}
      </span>
    )
  }
  if (!p.opp) return <span className="text-gray-600">—</span>
  return (
    <span className="text-gray-300">
      {p.home === false ? "@ " : p.home === true ? "vs " : ""}
      {p.opp}
    </span>
  )
}

/**
 * ⭐⭐ THE PAID PANEL, AND THE GATE IS THIS COMPONENT'S OWN DECISION.
 *
 * It reads `canUse("decision_support", groups)` itself rather than inferring permission from
 * whether paid data happens to be in hand. That distinction is the whole G100 lesson: a component
 * that draws whatever it holds is one stale cache away from printing paid substrate, and "the fetch
 * did not fire" is not a gate. The server (and, measured 2026-09-13, the API Gateway before it —
 * the paid route answers 401 to an anonymous caller) is the real one; this decides what PRINTS.
 *
 * ⛔ IT NEVER SUMS. There is no total here and no derived points figure anywhere in this tree.
 */
function StatLinePanel({ player, paid, loading }: {
  player: NflWeeklyPlayer
  paid: NflWeeklyPlayer | null
  /** ⚠️ THE PAID READ IS A SEPARATE QUERY, so "it has not arrived yet" is a FOURTH state here and
   *  it must not borrow the third one's sentence. Without this an entitled reader who opens a row
   *  before `/weekly/projections-full` resolves is told "no projected stat line was produced for
   *  this player" — which is not a slow render, it is a FALSE CLAIM about the model, shown for as
   *  long as the fetch takes. The whole page is built on the rule that an empty state meaning
   *  several things costs an investigation every time it recurs; a state that means something
   *  untrue is worse than one that is merely ambiguous. */
  loading: boolean
}) {
  const { groups } = useAuth()
  const entitled = canUse("decision_support", groups)

  if (!entitled) {
    return (
      <div data-testid="weekly-stat-line-locked" className="rounded-md border border-[#262626] bg-[#101010] p-3">
        <p className="text-[12px] font-semibold text-gray-300">{WEEKLY_STAT_LINE_LOCK_TITLE}</p>
        <p className="mt-1 text-[11px] leading-relaxed text-gray-500">{WEEKLY_STAT_LINE_LOCK_DETAIL}</p>
        <a
          href={SUBSCRIBE_HREF}
          className="mt-2 inline-block rounded border border-[#2a2a2a] px-2 py-1 text-[11px] text-gray-300 transition-colors hover:border-[#3a3a3a] hover:text-gray-100"
        >
          See membership options
        </a>
      </div>
    )
  }

  // Still in flight — say so rather than asserting an absence that has not been established.
  if (loading && !hasStatLine(paid)) {
    return (
      <p data-testid="weekly-stat-line-loading" className="rounded-md border border-[#262626] bg-[#101010] p-3 text-[11px] text-gray-500" aria-busy="true">
        Loading the projected stat line…
      </p>
    )
  }

  // ⚠️ A THIRD STATE, and it is neither the lock nor a failure: the component head is an INDEPENDENT
  // model, so it can legitimately have produced nothing for a player the points head projected.
  // Rendering zeros here would fabricate a line; rendering the lock would lie about why it is
  // missing.
  if (!hasStatLine(paid)) {
    return (
      <p data-testid="weekly-stat-line-absent" className="rounded-md border border-[#262626] bg-[#101010] p-3 text-[11px] leading-relaxed text-gray-500">
        {WEEKLY_STAT_LINE_ABSENT}
      </p>
    )
  }

  const shown = WEEKLY_STAT_FIELDS.filter(
    ({ key }) => WEEKLY_STATS_BY_POSITION[player.pos].includes(key) && paid![key] != null,
  )
  return (
    <div data-testid="weekly-stat-line" className="rounded-md border border-[#262626] bg-[#101010] p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">
        {WEEKLY_STAT_LINE_HEADING}
      </p>
      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
        {shown.map(({ key, label }) => (
          <div key={String(key)} data-testid={`weekly-stat-${String(key)}`}>
            <dt className="text-[10px] uppercase tracking-wide text-gray-600">{label}</dt>
            <dd className="text-[13px] tabular-nums text-gray-200">{num(paid![key] as number, 1)}</dd>
          </div>
        ))}
      </dl>
      {/* ⭐ THE DISCLOSURE RIDES WITH THE NUMBERS, unconditionally and un-collapsed. A caveat behind
          a click did not render (NF-C6P3), and this one is the difference between supporting detail
          and a second, contradictory total. */}
      <p data-testid="weekly-stat-line-note" className="mt-3 border-t border-[#1f1f1f] pt-2 text-[11px] leading-relaxed text-gray-500">
        {WEEKLY_STAT_LINE_NOTE}
      </p>
    </div>
  )
}

/** One player's row, plus the expandable paid detail beneath it. */
function PlayerRow({
  p,
  paid,
  paidLoading,
  domain,
  open,
  onToggle,
}: {
  p: NflWeeklyPlayer
  paid: NflWeeklyPlayer | null
  paidLoading: boolean
  domain: { min: number; max: number }
  open: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr data-testid="weekly-row" data-player-id={p.id} className="border-t border-[#1a1a1a] hover:bg-[#101010]">
        <td className="px-3 py-2">
          <div className="flex items-center gap-2">
            <PosBadge pos={p.pos} />
            <Link
              href={`/fantasy/player/${p.id}`}
              className="font-medium text-gray-200 hover:text-emerald-400"
            >
              {p.name}
            </Link>
          </div>
        </td>
        <td className="px-3 py-2 text-gray-400">{p.team}</td>
        <td className="px-3 py-2"><OpponentCell p={p} /></td>
        {/* ⭐ THE BAND RENDERS WITH THE POINT, EVERYWHERE THE POINT RENDERS. A weekly point without
            its interval overstates precision, and this is the surface where that matters most. */}
        <td className="px-3 py-2 text-right" data-testid="weekly-points">
          <div className="font-semibold tabular-nums text-gray-100">{fmt(p.fpPpr)}</div>
          <div className="text-[11px] tabular-nums text-gray-500" data-testid="weekly-band">
            {fmt(p.fpP10)}–{fmt(p.fpP90)}
          </div>
        </td>
        <td className="w-28 px-3 py-2">
          <IntervalBar p10={p.fpP10} point={p.fpPpr} p90={p.fpP90} min={domain.min} max={domain.max} />
        </td>
        <td className="px-3 py-2 text-right" data-testid="weekly-ros">
          <div className="tabular-nums text-gray-300">{fmt(p.rosPpr)}</div>
          <div className="text-[11px] tabular-nums text-gray-500" data-testid="weekly-ros-band">
            {p.rosP10 == null || p.rosP90 == null ? "—" : `${fmt(p.rosP10)}–${fmt(p.rosP90)}`}
          </div>
        </td>
        <td className="px-3 py-2 text-right tabular-nums text-gray-400" data-testid="weekly-ros-weeks">
          {p.rosWeeks}
        </td>
        <td className="px-3 py-2 text-right tabular-nums text-gray-400" data-testid="weekly-hist-weeks">
          {p.histWeeks}
        </td>
        <td className="px-3 py-2 text-right">
          <button
            type="button"
            data-testid="weekly-detail-toggle"
            aria-expanded={open}
            onClick={onToggle}
            className="rounded border border-[#2a2a2a] px-2 py-0.5 text-[11px] text-gray-400 transition-colors hover:border-[#3a3a3a] hover:text-gray-200"
          >
            {open ? "Hide" : "Detail"}
          </button>
        </td>
      </tr>
      {open && (
        <tr data-testid="weekly-detail" data-player-id={p.id} className="border-t border-[#141414] bg-[#0c0c0c]">
          <td colSpan={9} className="px-3 py-3">
            <StatLinePanel player={p} paid={paid} loading={paidLoading} />
          </td>
        </tr>
      )}
    </>
  )
}

/** The manifest's absence COUNTS, each with the served `detail` rendered verbatim beside a short
 *  human label. ⭐ Three causes, three rows — never one merged "some players are missing". */
function AbsencePanel({ manifest }: { manifest: NflWeeklyManifest }) {
  const rows = manifest.absences.filter((a) => a.n > 0)
  if (!rows.length) return null
  return (
    <section data-testid="weekly-absences" className="mt-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="text-[13px] font-semibold text-gray-300">{WEEKLY_ABSENCE_HEADING}</h2>
      <dl className="mt-3 space-y-3">
        {rows.map((a) => (
          <div key={a.reason} data-testid={`weekly-absence-${a.reason}`}>
            <dt className="text-[12px] font-medium text-gray-300">
              {WEEKLY_ABSENCE_LABEL[a.reason] ?? a.reason}
              <span className="ml-2 tabular-nums text-gray-500">{a.n}</span>
            </dt>
            {/* SERVED PROSE, VERBATIM. A paraphrase here would be claim copy no screening had ever
                looked at, and the reason strings are the writer's own. */}
            <dd className="mt-0.5 text-[11px] leading-relaxed text-gray-500">{a.detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

export function WeeklyProjectionsPage() {
  const { accessToken, groups } = useAuth()
  const entitled = canUse("decision_support", groups)
  const manifest = useWeeklyManifest()
  const projections = useWeeklyProjections()
  const full = useWeeklyProjectionsFull()

  const [pos, setPos] = useState<string>("All")
  const [open, setOpen] = useState<string | null>(null)

  const rows = useMemo(() => {
    const all = [...(projections.data?.players ?? [])].sort(byWeeklyPoints)
    return pos === "All" ? all : all.filter((p) => p.pos === pos)
  }, [projections.data, pos])

  const domain = useMemo(() => bandDomain(rows), [rows])

  /** The paid rows, by id. ⚠️ Built from the ENTITLED payload only — the free payload has no paid
   *  fields to index, and a lookup that silently fell back to it would make the panel render free
   *  data under a paid heading. */
  const paidById = useMemo(() => {
    const m = new Map<string, NflWeeklyPlayer>()
    for (const p of full.data?.players ?? []) m.set(p.id, p)
    return m
  }, [full.data])

  // ⚠️ THE TWO READS FAIL FOR THE SAME REASONS, so the state is decided on either of them: a week
  // that is not published 404s BOTH. Reading only one would let a half-published week render a
  // table with no provenance, or provenance with no table.
  const status = apiErrorStatus(projections.error) ?? apiErrorStatus(manifest.error)
  const awaiting = (projections.isError || manifest.isError) && status === 404
  const failed = (projections.isError || manifest.isError) && status !== 404
  const loading = projections.isLoading || manifest.isLoading

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <SurfaceHeader title={WEEKLY_PAGE_TITLE} blurb={WEEKLY_PAGE_STANDFIRST}>
        {manifest.data && (
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <WeekHeading manifest={manifest.data} />
          </div>
        )}
      </SurfaceHeader>

      {/* ⭐ THE PPR-NATIVE PANEL, ABOVE THE TABLE. It answers "why is there no format picker"
          BEFORE a reader goes looking for one — and it says the other formats do not exist yet
          rather than that they are withheld, which is the true and the honest framing. */}
      <section data-testid="weekly-ppr-native" className="mb-5 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
        <h2 className="text-[13px] font-semibold text-gray-300">{WEEKLY_PPR_NATIVE_TITLE}</h2>
        <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-gray-400">
          {WEEKLY_PPR_NATIVE_DETAIL}
        </p>
      </section>

      {loading && <LoadingBlock label="Loading this week's projections…" />}

      {awaiting && (
        <div data-testid="weekly-awaiting-publish">
          <EmptyBlock title={WEEKLY_AWAITING_PUBLISH_TITLE} detail={WEEKLY_AWAITING_PUBLISH_DETAIL} />
        </div>
      )}

      {failed && (
        <p
          data-testid="weekly-read-failed"
          className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-6 text-center text-sm text-amber-200/80"
        >
          {WEEKLY_READ_FAILED}
        </p>
      )}

      {/* A week that LOADED and holds nothing. Distinct from the 404 on purpose: one is "this week
          is not published", the other is "this week is published and is empty", and a surface that
          rendered them identically would send the next investigation to the wrong place. */}
      {projections.data && rows.length === 0 && (
        <div data-testid="weekly-empty-week">
          <EmptyBlock
            title="No players to show"
            detail={
              pos === "All"
                ? "This week is published but carries no players. That is unexpected — if it persists, it is a problem on our side."
                : `We publish no ${pos} rows for this week.`
            }
          />
        </div>
      )}

      {projections.data && rows.length > 0 && (
        <>
          <div className="mb-3">
            <PositionTabs
              value={pos}
              onChange={(p) => { setPos(p); setOpen(null) }}
              positions={[...WEEKLY_PROJECTED_POSITIONS]}
            />
          </div>

          {/* ⚠️ `overflow-x-auto` ON ITS OWN CONTAINER, and `min-w-0` on the wrapper: a table wide
              enough to need sideways scrolling must scroll INSIDE its own box rather than giving the
              whole page a horizontal scrollbar (the NF-C2.1 grid lesson — a `1fr` track's automatic
              minimum is its min-content width).

              ⭐⭐ `relative` IS LOAD-BEARING AND IT FIXES A MEASURED BUG, not a hypothetical one.
              An `overflow-x-auto` box clips its IN-FLOW children, but a `position: absolute`
              descendant is laid out against its nearest POSITIONED ancestor — and with none, that
              is the INITIAL containing block, i.e. the document. It therefore escapes the scroll
              container completely. This table has exactly such a descendant: Tailwind's `sr-only`
              (the accessible name on the last column's header) is `position: absolute`, and with
              every ancestor `static` it was laid out at x=864 in DOCUMENT coordinates — inflating
              `document.documentElement.scrollWidth` to 866 in a 412px viewport while the container
              itself measured a perfectly correct 378/860.

              ⚠️ THE TELL THAT IT IS REAL RATHER THAN A MEASUREMENT QUIRK: the shipped season tables
              use the identical pattern with WIDER tables (980px and 954px) and measure 412 — a
              narrower table leaking is backwards for any overflow explanation, which is what
              pointed at the escaping absolute child. Bisected to `<thead>`, then to that one cell,
              then to the span itself (rect x=864, width 1px).

              ⛔ THE FIX IS CONTAINMENT, NOT DELETION. That span is the only accessible name the
              detail column's header has; removing it would trade a layout bug for an a11y
              regression. `relative` scopes it — and every future absolute descendant of this
              table — back inside the box. Caught only because this surface is in the `mobile`
              project: at 1280px the table fits and the span sits inside the viewport, so the
              defect is structurally invisible to a desktop run, to `tsc` and to `next build`. */}
          <div className="relative min-w-0 overflow-x-auto rounded-lg border border-[#262626]">
            <table className="w-full min-w-[860px] text-left text-xs">
              <thead className="bg-[#0f0f0f] text-[11px] uppercase tracking-wide text-gray-500">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Player</th>
                  <th scope="col" className="px-3 py-2 font-medium">Team</th>
                  <th scope="col" className="px-3 py-2 font-medium">Opp</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    <InfoTip label={WEEKLY_POINTS_LABEL}>{WEEKLY_POINTS_DEFINITION}</InfoTip>
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    <InfoTip label={WEEKLY_RANGE_LABEL}>{WEEKLY_RANGE_DEFINITION}</InfoTip>
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    <InfoTip label={WEEKLY_ROS_LABEL}>{WEEKLY_ROS_DEFINITION}</InfoTip>
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Weeks left</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    <InfoTip label={WEEKLY_HIST_LABEL}>{WEEKLY_HIST_DEFINITION}</InfoTip>
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    <span className="sr-only">Projected stat line</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <PlayerRow
                    key={p.id}
                    p={p}
                    paid={paidById.get(p.id) ?? null}
                    paidLoading={full.isLoading}
                    domain={domain}
                    open={open === p.id}
                    onToggle={() => setOpen(open === p.id ? null : p.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* The bye explainer, rendered whenever a bye is on the page. It exists because a zero in
              a points column is the single most misreadable cell here: it is a CERTAINTY, not a
              missing projection, and the row's own ROS number beside it is unaffected. */}
          {rows.some((p) => p.status === "bye") && (
            <p data-testid="weekly-bye-note" className="mt-3 text-[11px] leading-relaxed text-gray-500">
              <span className="font-semibold text-gray-400">{WEEKLY_BYE_LABEL}:</span>{" "}
              {WEEKLY_BYE_DEFINITION}
            </p>
          )}

          {/* ⭐ THE SERVED FRAMING NOTES, RENDERED VERBATIM. `interval_note` carries the measured
              coverage floors and `ros_interval_note` carries the independence approximation behind
              the rest-of-season band — both are the payload's own prose, and both belong to the
              numbers directly above them. Rendering our own paraphrase would be writing claim copy
              no screening had looked at, and would drift from the measurement on the next re-score. */}
          {manifest.data && (
            <div className="mt-4 space-y-2">
              <p data-testid="weekly-interval-note" className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500">
                {manifest.data.framing.interval_note}
              </p>
              <p data-testid="weekly-ros-interval-note" className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500">
                {manifest.data.framing.ros_interval_note}
              </p>
            </div>
          )}
        </>
      )}

      {manifest.data && <AbsencePanel manifest={manifest.data} />}

      {/* Provenance: WHEN each input was read, per input. One build date rendered over inputs of
          several vintages hides staleness (NF-FRESH2), and these are free on both sides for exactly
          that reason — withholding them from a free caller would leave the defect in place for half
          the audience. */}
      {manifest.data && (
        <p data-testid="weekly-provenance" className="mt-6 text-[11px] text-gray-600">
          Week {manifest.data.week} built {vintage(manifest.data.generated_at)} · rosters{" "}
          {vintage(manifest.data.input_vintage.rosters_as_of)} · schedule{" "}
          {vintage(manifest.data.input_vintage.schedule_as_of)} · stats{" "}
          {vintage(manifest.data.input_vintage.stats_as_of)} · trained through{" "}
          {manifest.data.input_vintage.train_through_season ?? "—"} week{" "}
          {manifest.data.input_vintage.train_through_week ?? "—"} ·{" "}
          {manifest.data.lineage.served_version}
        </p>
      )}

      <FreemiumBoundary entitled={entitled && !!accessToken} surface="weekly" />
    </main>
  )
}
