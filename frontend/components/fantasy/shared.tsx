"use client"

// Shared presentation pieces for the NFL fantasy surfaces (NF3). Position colours, the format
// selector, and the honest-uncertainty primitives live here so all four surfaces (Projections,
// Rankings, League Board, Draft Optimizer) read as one product.
//
// 🚨 CLAIM SCOPE (NF-D3): these surfaces are a PROJECTION product. They never claim to beat a
// consensus, an ADP, or any competitor — the honest framing is uncertainty made visible (an 80%
// range on every number) plus transparency about how the number is built. Copy here is the one
// place that framing is written down; keep new copy inside it.

import { useId, useState } from "react"
import Link from "next/link"
import { Info, Lock } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Picker } from "@/components/ui/picker"
import type { FreshnessBlock, LeagueConfigMeta, Manifest, VeteranLevelPolicy } from "@/lib/draft-optimizer"
import { freeSelection, isFreeConfig } from "@/lib/draft-optimizer"
import { availabilityTier, fullSeasonRateDisplay, marketLeaningPositions } from "@/lib/fantasy"
import type { AvailabilityTier, ProjectedPlayer } from "@/lib/fantasy"
import { useTrackRecordManifest } from "@/lib/fantasy-track-record"
import {
  AVAILABILITY_DATA_AS_OF_PREFIX,
  AVAILABILITY_DATA_AS_OF_UNKNOWN,
  AVAILABILITY_FLAG_DEFINITION,
  AVAILABILITY_FLAG_LABEL,
  AVAILABILITY_FLAG_SUMMARY,
  DECISION_SUPPORT_LINE,
  DISAGREEMENT_HOOK,
  EXPECTED_POINTS_DEFINITION,
  FORMAT_LOCK_EXPLANATION,
  FORMAT_LOCK_SUFFIX,
  FREE_TIER_SUMMARY,
  FULL_SEASON_RATE_DEFINITION,
  FULL_SEASON_RATE_LABEL,
  FULL_SEASON_RATE_WITHHELD_DETAIL,
  FULL_SEASON_RATE_WITHHELD_LABEL,
  FULL_SEASON_RATE_WITHHELD_SR_LABEL,
  MEMBERSHIP_CTA_LABEL,
  PAID_TIER_HEADING,
  PAID_TIER_SUMMARY,
  PROJECTED_GAMES_DEFINITION,
  PROJECTED_GAMES_LABEL,
  STAT_LINE_WITHHELD_DETAIL,
  STAT_LINE_WITHHELD_LABEL,
  STAT_LINE_WITHHELD_SR_LABEL,
  TRACK_RECORD_TRUST_LINK,
  WEEKLY_DESIGNATION_CODE,
  WEEKLY_DESIGNATION_LABEL,
  WEEKLY_DESIGNATION_NOT_A_DIAGNOSIS,
  WEEKLY_DESIGNATION_NOT_MODELLED,
  WEEKLY_DESIGNATION_SUMMARY,
  WEEKLY_DESIGNATION_UNKNOWN,
  REPORTED_ABSENCE_LABEL,
  REPORTED_ABSENCE_SUMMARY,
  REPORTED_ABSENCE_MANUAL,
  REPORTED_ABSENCE_NOT_A_FORECAST,
  REPORTED_ABSENCE_ENTERED_PREFIX,
  REPORTED_ABSENCE_SOURCE_LABEL,
  REPORTED_ABSENCE_METHOD_DISCLOSURE,
  WEEKLY_DESIGNATION_UNKNOWN_SUMMARY,
} from "@/lib/fantasy-claim-copy"

export const POS_COLORS: Record<string, string> = {
  QB: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  RB: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  WR: "text-sky-400 bg-sky-500/10 border-sky-500/30",
  TE: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  K: "text-violet-400 bg-violet-500/10 border-violet-500/30",
  DST: "text-teal-400 bg-teal-500/10 border-teal-500/30",
}

export const SKILL_POSITIONS = ["QB", "RB", "WR", "TE"] as const

/** Every position the board ranks. ⭐ NF1.6 added K + DST: before it they carried no projection and
 *  were filtered out of every ranked surface, so those roster slots rendered empty. They now carry a
 *  real (deliberately BASE) projection with points, VOR and an 80% range, so they belong in the
 *  ranked lists. Use this — not SKILL_POSITIONS — anywhere the question is "what can be ranked".
 *  SKILL_POSITIONS remains correct for the genuinely skill-only reads (bye-week stacking, flex). */
export const ALL_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const

/** Positions whose projection must NOT be presented as a confident rank. K and D/ST are the least
 *  predictable fantasy positions (held-out rank correlation ~0.32 for DST, ~0.23 among startable
 *  kickers).
 *
 *  ⚠️ This is carried as PROSE in each surface's notes, deliberately NOT as a per-row badge. A badge
 *  reading "Tier" beside every kicker was read as a RATING — on a board that already has a real tier
 *  column, "Jake Bates · Tier" parses as "tier-one asset", i.e. the exact opposite of the caveat it
 *  was meant to carry. A caveat that can be misread as a promotion is worse than no caveat. The rows
 *  still carry `lowPred`/`predNote` from the export (the source of truth) for any future surface
 *  that finds an unambiguous way to show it. */
export const LOW_PREDICTABILITY_POSITIONS: readonly string[] = ["K", "DST"]

/** One column of a position's raw projected stat line (NF3 Projections table + NF3.1 player page —
 *  the single source of truth for "which raw stats does this position's projection carry"). */
export interface StatCol {
  key: keyof ProjectedPlayer
  label: string
  nd?: number
}

/** Per-position stat lines. "All" stays condensed (a shared stat set across positions would be
 *  mostly empty cells); pick a position to see that position's full projected line. */
export const STAT_COLS: Record<string, StatCol[]> = {
  QB: [
    { key: "passCmp", label: "Cmp", nd: 0 },
    { key: "passAtt", label: "Att", nd: 0 },
    { key: "passYds", label: "Pass Yds", nd: 0 },
    { key: "passTd", label: "Pass TD" },
    { key: "passInt", label: "INT" },
    { key: "rushAtt", label: "Rush", nd: 0 },
    { key: "rushYds", label: "Rush Yds", nd: 0 },
    { key: "rushTd", label: "Rush TD" },
  ],
  RB: [
    { key: "rushAtt", label: "Att", nd: 0 },
    { key: "rushYds", label: "Rush Yds", nd: 0 },
    { key: "rushTd", label: "Rush TD" },
    { key: "tgt", label: "Tgt", nd: 0 },
    { key: "rec", label: "Rec", nd: 0 },
    { key: "recYds", label: "Rec Yds", nd: 0 },
    { key: "recTd", label: "Rec TD" },
  ],
  WR: [
    { key: "tgt", label: "Tgt", nd: 0 },
    { key: "rec", label: "Rec", nd: 0 },
    { key: "recYds", label: "Rec Yds", nd: 0 },
    { key: "recTd", label: "Rec TD" },
    { key: "rushAtt", label: "Rush", nd: 0 },
    { key: "rushYds", label: "Rush Yds", nd: 0 },
  ],
}
STAT_COLS.TE = STAT_COLS.WR
// NF1.6 — the K/DST lines. Field goals are split by DISTANCE because that is how they score (3/4/5)
// and because leg strength is the one kicker attribute that genuinely persists. For a defence,
// points allowed PER GAME is the number that communicates quality — the nine points-allowed tier
// buckets behind it are a scoring input, not something a drafter reads.
STAT_COLS.K = [
  { key: "fgAtt", label: "FGA", nd: 0 },
  { key: "fgMade", label: "FG" },
  { key: "fg039", label: "0-39" },
  { key: "fg4049", label: "40-49" },
  { key: "fg50", label: "50+" },
  { key: "patMade", label: "XP" },
]
STAT_COLS.DST = [
  { key: "paPerG", label: "Pts Allowed/G" },
  { key: "sacks", label: "Sacks" },
  { key: "defInt", label: "INT" },
  { key: "fumRec", label: "Fum Rec" },
  { key: "defTd", label: "Def TD" },
  { key: "stTd", label: "ST TD" },
]

/** A player's team for display: real abbreviation, or an honest label for the unteamed. A rookie's
 *  NFL team is not always resolved upstream, so an unteamed rookie shows "Rk", never a wrong "FA". */
export const teamLabel = (p: { team: string | null; rookie: boolean }) =>
  p.team ?? (p.rookie ? "Rk" : "FA")

export const num = (v: number | null | undefined, nd = 1) =>
  v == null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })

export const int = (v: number | null | undefined) => (v == null ? "—" : Math.round(v).toLocaleString())

// ── E9.56: locked (paid) values ──────────────────────────────────────────────────────────────────
// The server never sends a gated season's numbers to a non-entitled caller — it sends the row with
// its public identity plus `locked: true` and NO value fields. So "locked" and "genuinely has no
// value" arrive as the SAME absent field, and only the row's marker can tell them apart. That
// distinction is the whole product decision: a locked point must read "subscribe to unlock", while
// a real null must keep reading "—" (an honest absence we already communicate carefully — K/DST
// `lowPred`, missing bio, no ADP). Getting it backwards either sells a value that doesn't exist or
// silently hides one the user could buy.

// 🚨 E9.56c — THE SUBSCRIBE ROUTE IS `/subscribe`. IT HAS NEVER BEEN `/pricing`.
//
// E9.56/E9.56b shipped every locked CTA pointing at `/pricing` — the LockChip on every withheld
// cell (hundreds per page), both "Subscribe to unlock" buttons, and the two footer links. That
// route DOES NOT EXIST in `frontend/app/`, so the entire conversion path off the locked view was a
// 404, verified live. Nothing caught it: `next build` only resolves `<Link>` targets it can see
// statically, these are plain `<a href>`, and there is no route-existence check anywhere in CI.
// A dead CTA is invisible to every test that does not actually follow the link.
//
// ⇒ Route strings are now a CONSTANT here rather than a literal at each call site, and
// `test_e9_56c_cta_routes.py` asserts a real `frontend/app/<route>/page.tsx` exists for it. A future
// rename of the route directory then goes RED instead of silently 404ing in production.
export const SUBSCRIBE_HREF = "/subscribe"

/** Routes the server's `upgrade.ctaHref` is allowed to send us to.
 *
 *  NF-C0's deploy-skew rule, applied to a LINK TARGET rather than a payload key: the API Lambda
 *  ships only via a manual `deploy.sh`, so a frontend deployed today can be talking to a backend
 *  that still sends the old `/pricing`. Trusting that value verbatim is what put a 404 behind the
 *  primary CTA in the first place. An unrecognized target falls back to the route we KNOW exists,
 *  so the skew window degrades to "slightly wrong copy" instead of "dead button". */
const KNOWN_CTA_ROUTES = new Set([SUBSCRIBE_HREF])
export function resolveUpgradeHref(href?: string | null): string {
  return href && KNOWN_CTA_ROUTES.has(href) ? href : SUBSCRIBE_HREF
}

/** The lock chip that stands in for a withheld value. Deliberately small and inline — it replaces a
 *  single table cell, so it must not change row height or column width. */
export function LockChip({ title }: { title?: string }) {
  return (
    <a
      href={SUBSCRIBE_HREF}
      title={title ?? "Subscribe to unlock this projection"}
      className="inline-flex items-center gap-0.5 rounded px-1 text-[10px] font-medium text-amber-400/90 hover:text-amber-300 hover:bg-amber-400/10 transition-colors"
      aria-label="Locked — subscribe to unlock"
    >
      <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
        <rect x="4" y="11" width="16" height="9" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
      </svg>
    </a>
  )
}

/** `num`, but a LOCKED row renders the chip instead of an em-dash.
 *  `locked` is read from the row's own marker, so an entitled payload (no marker) is untouched. */
export const numOrLock = (
  v: number | null | undefined,
  locked: boolean | undefined,
  nd = 1,
): React.ReactNode => (v == null && locked ? <LockChip /> : num(v, nd))

/** NF-INJ1-C — is THIS stat withheld on THIS row?
 *
 *  ⛔ NOT `value == null`. A missing key means one of two entirely different things and only the
 *  row's own marker separates them: the server withheld it (an impossible per-game rate we refuse
 *  to print), or the player genuinely has no such stat. Reading absence as withholding would put
 *  this disclosure on every K's passing line; reading withholding as absence is the E9.56c
 *  inversion the lock helpers above exist to prevent.
 *
 *  Tolerant of a non-array value on purpose: this key crosses an API boundary the frontend deploys
 *  independently of (NF-C0), so a malformed marker must degrade to "not withheld" — the pre-story
 *  rendering — rather than throw inside a table cell. */
export const isStatWithheld = (
  withheld: string[] | null | undefined,
  key: string,
): boolean => Array.isArray(withheld) && withheld.includes(key)

/** The em-dash that stands in for a withheld stat, with the disclosure behind it.
 *
 *  ⭐ A POPOVER (`InfoTip`), NOT A `title=`. A `title` tooltip is unreachable on a phone — no hover,
 *  no long-press affordance — and this renders on a dense table a phone already scrolls sideways.
 *  A refusal a reader cannot ask about is indistinguishable from a missing number, which is the one
 *  thing this must never look like (NF-C9 made the same call for the same reason).
 *
 *  `bare` because the column header directly above already carries the stat's name and its own ⓘ;
 *  the dotted underline and second glyph would cost width on every row to repeat it. The trigger
 *  stays a real focusable button with an accessible name, so keyboard and screen-reader access are
 *  untouched — chrome goes, function does not. */
export function WithheldStat() {
  return (
    <InfoTip
      bare
      srLabel={STAT_LINE_WITHHELD_SR_LABEL}
      label={
        <span data-testid="withheld-stat" className="cursor-help text-gray-500 underline decoration-dotted decoration-gray-700 underline-offset-4">
          —
        </span>
      }
    >
      <p className="font-medium text-gray-300">{STAT_LINE_WITHHELD_LABEL}</p>
      <p className="mt-1.5">{STAT_LINE_WITHHELD_DETAIL}</p>
    </InfoTip>
  )
}

// ── NF-RATE1 — the full-season rate's THREE render states, in one place ──────────────────────────
//
// ⚠️ ADJACENT TO `WithheldStat` ABOVE, DELIBERATELY NOT SHARED WITH IT. That one suppresses SERVED
// COUNTING STATS the server marked; this one suppresses a DERIVED DISPLAY LINE the client computes,
// off a rule the client owns (`fullSeasonRateDisplay`). Same Option-C pattern, different predicate,
// different inputs, different failure modes — folding them together would make one component answer
// to two stories and give a future edit to either one a blast radius it should not have.
//
// The rule itself lives in `lib/fantasy.ts` and is NOT restated here; these components render the
// three states it returns and nothing else.

/** The em-dash standing in for a rate we refuse to print, with the disclosure behind it.
 *
 *  ⭐ A POPOVER (`InfoTip`), NOT a `title=` — unreachable on a phone, and a refusal a reader cannot
 *  ask about is indistinguishable from a missing number, which is the one thing this must never
 *  look like. Same call, same reason, as `WithheldStat` and NF-C9. */
export function WithheldFullSeasonRate() {
  return (
    <InfoTip
      bare
      srLabel={FULL_SEASON_RATE_WITHHELD_SR_LABEL}
      label={
        <span data-testid="withheld-full-season-rate" className="cursor-help text-gray-500 underline decoration-dotted decoration-gray-700 underline-offset-4">
          —
        </span>
      }
    >
      <p className="font-medium text-gray-300">{FULL_SEASON_RATE_WITHHELD_LABEL}</p>
      <p className="mt-1.5">{FULL_SEASON_RATE_WITHHELD_DETAIL}</p>
    </InfoTip>
  )
}

/** The whole TABLE CELL for the full-season rate — the rankings board's column and the projections
 *  table's column render this and nothing else, so the two cannot disagree about any of the three
 *  states (the #681 "two renderers of one field are two rule sets" lesson).
 *
 *  ⚠️ `unavailable` renders `num(null)` — the plain em-dash, with no disclosure and no dotted
 *  underline. That is the PRE-EXISTING rendering of the `MIN_GAMES_FOR_FULL_SEASON_RATE` floor and
 *  of an absent games figure, and it is left byte-identical on purpose: this story adds a state, it
 *  does not restyle the one that was already there. The two are visually distinguishable precisely
 *  because only one of them is something a reader can ask about. */
export function FullSeasonRateCell({
  pts,
  games,
  pos,
}: {
  pts: number | null | undefined
  games: number | null | undefined
  pos: string | null | undefined
}) {
  const d = fullSeasonRateDisplay(pts, games, pos)
  if (d.kind === "withheld") return <WithheldFullSeasonRate />
  return <>{num(d.kind === "rate" ? d.value : null)}</>
}

/** The same three states as a TILE SUB-LINE, for the player page's format tiles.
 *
 *  Returns `false` (not an em-dash) for `unavailable`, because `combineSub` DROPS a false entry and
 *  the pre-story behaviour there was for the line to be simply absent — a tile sub-line is a list of
 *  present facts, not a fixed grid of cells, so an em-dash of its own would read as a new kind of
 *  emptiness rather than as the same one. `withheld` DOES render, because "we have this number and
 *  are not printing it" is a fact, and an omitted line cannot say it. */
export function FullSeasonRateSubLine({
  pts,
  games,
  pos,
}: {
  pts: number | null | undefined
  games: number | null | undefined
  pos: string | null | undefined
}): React.ReactNode | false {
  const d = fullSeasonRateDisplay(pts, games, pos)
  if (d.kind === "unavailable") return false
  if (d.kind === "rate") return `${FULL_SEASON_RATE_LABEL}: ${num(d.value)}`
  return (
    <InfoTip
      bare
      srLabel={FULL_SEASON_RATE_WITHHELD_SR_LABEL}
      label={
        <span data-testid="withheld-full-season-rate-subline" className="cursor-help underline decoration-dotted decoration-gray-700 underline-offset-4">
          {FULL_SEASON_RATE_LABEL}: —
        </span>
      }
    >
      <p className="font-medium text-gray-300">{FULL_SEASON_RATE_WITHHELD_LABEL}</p>
      <p className="mt-1.5">{FULL_SEASON_RATE_WITHHELD_DETAIL}</p>
    </InfoTip>
  )
}

export const intOrLock = (
  v: number | null | undefined,
  locked: boolean | undefined,
): React.ReactNode => (v == null && locked ? <LockChip /> : int(v))

/** The page-level "this season is paid" banner, rendered above a locked surface.
 *
 *  Takes its copy from the server's `upgrade` envelope so the reason and the CTA target live with
 *  the gate that produced them; the defaults exist only for the deploy-skew window where a NEW
 *  frontend is talking to an OLD backend that sends no envelope at all. */
export function UpgradeBanner({
  season,
  upgrade,
}: {
  season?: number | null
  upgrade?: { reason?: string; message?: string; ctaHref?: string } | null
}) {
  // E9.56b — LEAD WITH SOMETHING, not with the ask.
  //
  // The locked view is, by necessity, the MARKET's board with our numbers removed: E9.56's
  // anti-scrape rule re-orders locked rows onto ADP precisely so the array index cannot reconstruct
  // our ranking. So the page a free visitor lands on cannot argue for itself — on its own it reads
  // as an ADP clone with padlocks, which is a weak thing to ask money for.
  //
  // ⭐⭐ NF-TR1 REVERSED WHAT IT LEADS WITH (operator 2026-08-07, GROWTH-100). E9.56b answered that
  // by rendering the track-record headline verbatim, i.e. by making a MEASURED STATISTIC the
  // pitch. That is the wrong instrument on this surface, for a reason that has nothing to do with
  // honesty and everything to do with what a banner can carry: the measurement is a +0.022 gap
  // whose own 90% interval INCLUDES ZERO (NF-D17), so stated truthfully it must arrive wrapped in
  // four hedges and CLOSE on "it could just be luck". A conversion surface that ends on its own
  // disclaimer persuades nobody — and it informs nobody either, because the caveats only mean
  // something beside the table, the position split and the interval that explain them.
  //
  // So the division of labour is now explicit, and it is the whole point:
  //   · THIS BANNER sells the PRODUCT — a board built for the reader's own league scoring, and the
  //     decision support that is the paid half. Consensus appears only as CONTENT (`DISAGREEMENT_
  //     HOOK`: where we differ from the crowd and why), never as a boast.
  //   · THE TRACK RECORD PAGE carries every hedge, where a reader who opted in meets them with the
  //     evidence attached and they build trust instead of repelling.
  //   · The connection between them is a LINK, not a quotation.
  //
  // ⛔ DO NOT RENDER `receipts.headline`, `claim.lead` OR `claim.precise` HERE. That is not style —
  // `test_nf_tr1_claim_copy.py::test_the_marketing_banner_does_not_quote_the_track_record_stat`
  // fails the build on it, and the Playwright suite checks the rendered DOM as well.
  //
  // The manifest is still read, for ONE thing: how many seasons the record covers. That is a
  // description of the LINK's destination ("across 6 past seasons"), not a performance figure —
  // it says how much there is to read, not how well we did. Degrades cleanly: if the public
  // endpoint is slow or fails, the link loses its season count and nothing else.
  const { data: receipts } = useTrackRecordManifest()
  const seasonCount = receipts?.seasons?.length ?? 0

  return (
    <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/[0.07] px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <rect x="4" y="11" width="16" height="9" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 8 0v4" />
          </svg>
          <p className="text-sm text-amber-200/90">
            {upgrade?.message ?? `Subscribe to unlock the ${season ?? ""} projections.`}{" "}
            <span className="text-amber-200/60">{DECISION_SUPPORT_LINE}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a
            href={TRACK_RECORD_TRUST_LINK.href}
            className="rounded-md border border-amber-500/40 px-3 py-1.5 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/10"
          >
            {TRACK_RECORD_TRUST_LINK.label}
          </a>
          <a
            href={resolveUpgradeHref(upgrade?.ctaHref)}
            className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-semibold text-black transition-colors hover:bg-amber-400"
          >
            Subscribe to unlock
          </a>
        </div>
      </div>

      {/* The second line is a REASON TO CLICK, not a summary of the finding — the moment a
          marketing surface summarises the measurement it has quoted the stat, hedges and all.
          `DISAGREEMENT_HOOK` is true whichever side of the gap we are on, which is exactly what
          makes it usable here and a superiority claim not.

          It closes on the invitation, never on a caveat (AC 5). The season count is the size of
          what there is to read; if the public manifest has not resolved, the sentence simply
          stands without it. */}
      <p className="mt-2.5 border-t border-amber-500/20 pt-2.5 text-[13px] leading-relaxed text-amber-200/85">
        {DISAGREEMENT_HOOK}{" "}
        <a
          href={TRACK_RECORD_TRUST_LINK.href}
          className="font-medium text-amber-200 underline underline-offset-4 hover:text-amber-100"
        >
          {seasonCount > 0
            ? `Free, across ${seasonCount} past seasons`
            : "Free, across every past season"}
        </a>
        .
      </p>
    </div>
  )
}

/**
 * ⭐ THE FREEMIUM BOUNDARY — the explicit free/paid line, rendered BESIDE a fully-visible free board.
 *
 * THE PRODUCT ARGUMENT THIS EXISTS TO MAKE (GROWTH-100 §1). The paid aha is "what changed because
 * it is MY league" — and a visitor cannot want that until they have seen the generic board AND
 * understood that it is generic. Left implicit, a complete-looking free board reads as the whole
 * product and there is nothing to buy; stated, the same board becomes the argument for the upgrade.
 * So this block is the conversion surface, and the board above it is the proof.
 *
 * ⚠️ IT IS NOT AN `UpgradeBanner`, AND THE DIFFERENCE IS THE WHOLE STORY. `UpgradeBanner` sits above
 * a board whose numbers are WITHHELD and says "subscribe to unlock" — it is a lock, and its
 * defaults, its `upgrade` envelope and its amber lock iconography all say so. Nothing is withheld on
 * this page any more. Rendering the lock here would tell a visitor the complete board in front of
 * them is partial, which is both false and a weaker pitch than the truth.
 *
 * ⛔ NEVER RENDER THIS FOR AN ENTITLED CALLER. A subscriber already has both halves; an upsell for
 * something they pay for reads as a bug in our billing. Callers pass `entitled` rather than reading
 * auth here, so this component stays pure and the guard test can drive it directly.
 *
 * ⛔ NO PERFORMANCE PROMISE, and no quotation of the track-record statistic — the marketing/trust
 * split NF-TR1 encodes. The copy is a division of LABOUR ("we do more of the work"), never an
 * outcome claim, and the record is a LINK. Every string comes from `fantasy-claim-copy.ts` so the
 * denylist screening covers it; `test_freemium_tier.py` fails the build on a literal written here.
 */
export function FreemiumBoundary({ entitled }: { entitled: boolean }) {
  if (entitled) return null
  return (
    <section
      data-testid="freemium-boundary"
      aria-labelledby="freemium-boundary-heading"
      className="mt-8 rounded-lg border border-[#262626] bg-[#0f0f0f] p-5"
    >
      <h2 id="freemium-boundary-heading" className="text-sm font-semibold text-gray-200">
        {FREE_TIER_SUMMARY.title}
      </h2>
      <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-gray-400">
        {FREE_TIER_SUMMARY.detail}
      </p>

      <div className="mt-5 border-t border-[#1f1f1f] pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[#10b981]">
          {PAID_TIER_HEADING}
        </p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {PAID_TIER_SUMMARY.map((item) => (
            <div key={item.title}>
              <p className="text-[13px] font-semibold text-gray-200">{item.title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-gray-400">{item.detail}</p>
            </div>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2.5">
          <a
            href={SUBSCRIBE_HREF}
            className="rounded-md bg-[#10b981] px-3.5 py-2 text-sm font-semibold text-black transition-colors hover:bg-[#34d399]"
          >
            {MEMBERSHIP_CTA_LABEL}
          </a>
          {/* The trust LINK, never the statistic (NF-TR1). A skeptical reader is one click from the
              whole measurement, hedges and all, on the page built to carry them. */}
          <a
            href={TRACK_RECORD_TRUST_LINK.href}
            className="rounded-md border border-[#262626] px-3.5 py-2 text-sm font-medium text-gray-300 transition-colors hover:border-[#3a3a3a] hover:text-gray-100"
          >
            {TRACK_RECORD_TRUST_LINK.label}
          </a>
        </div>
      </div>
    </section>
  )
}

export function PosBadge({ pos }: { pos: string }) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
        POS_COLORS[pos] ?? "text-gray-400 bg-gray-500/10 border-gray-500/30"
      }`}
    >
      {pos}
    </span>
  )
}

const CONF_STYLE: Record<string, string> = {
  high: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  low: "text-gray-400 bg-gray-500/10 border-gray-500/30",
}

/** The model's own confidence tier — driven by how much history backs the player's per-game line. */
export function ConfidenceBadge({ conf }: { conf: string | null }) {
  if (!conf) return <span className="text-gray-600">—</span>
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize ${
        CONF_STYLE[conf] ?? CONF_STYLE.low
      }`}
    >
      {conf}
    </span>
  )
}

/** NF3.2 — a fade, graded. `isFade` alone only says "we disagreed with the market"; it says nothing
 *  about whether that disagreement paid off. `fadeResult` answers that: "hit" (our rank landed
 *  closer to how the season actually finished than ADP's did), "miss" (ADP was the better call), or
 *  "push" (a dead-even tie) — see `_fade_result` in `benchmark_scorecard.py` for the exact
 *  definition. Colour follows the existing hit/miss convention on these boards (emerald = good,
 *  rose = bad) rather than a single undifferentiated green "fade" chip, so "the full picture, wins
 *  and losses both" (the Track Record page's own blurb) is true of this column too. Renders nothing
 *  for a non-fade row — same as before. */
export function FadeBadge({
  isFade,
  fadeResult,
}: {
  isFade: boolean
  fadeResult: "hit" | "miss" | "push" | null | undefined
}) {
  if (!isFade) return null
  // ⚠️ Explicit `== null` (covers BOTH `null` and `undefined`), never a `=== "hit" ? : === "miss" ? :
  // else "push"` fallthrough — an export that predates this field, or one read before republishing,
  // omits the key entirely, which is `undefined` in JS, not `"push"`. A fallthrough silently painted
  // every ungraded fade amber as a fake tie (2026-08-02 mobile report: "everything is showing up as
  // push"). An ungraded row gets the original plain "fade" chip instead.
  if (fadeResult == null) {
    return (
      <span className="rounded border border-[#10b981]/40 bg-[#10b981]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#10b981]">
        fade
      </span>
    )
  }
  const style =
    fadeResult === "hit"
      ? "border-[#10b981]/40 bg-[#10b981]/10 text-[#10b981]"
      : fadeResult === "miss"
        ? "border-rose-500/40 bg-rose-500/10 text-rose-400"
        : "border-amber-500/40 bg-amber-500/10 text-amber-500"
  const label = fadeResult === "hit" ? "fade · hit" : fadeResult === "miss" ? "fade · miss" : "fade · push"
  // ⚠️ `whitespace-nowrap` is load-bearing, not cosmetic. This is a two-word label inside a bordered
  // chip in the LAST column of a table that grew a column (the projected-games column), and a
  // browser will happily break it at the "·" — which draws the border around a two-line chip whose
  // second line is the grade, i.e. exactly the part that carries the meaning. The table already
  // sits in an `overflow-x-auto`, so refusing the break costs a little horizontal scroll on a
  // narrow viewport rather than a mangled badge, which is the right trade for a chip this small.
  return (
    <span
      className={`inline-block whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] font-semibold ${style}`}
    >
      {label}
    </span>
  )
}

/** The hit/miss/push definitions, spelled out in-line rather than left to the "Fade" column's
 *  tooltip alone — the user report that prompted this: "even I'm confused by it" applied to the
 *  bare word "Fade"; a bare colour-coded chip has the same problem one level down. Shared so the
 *  Track Record page (scatter + table) and a player's own track-record table say the identical
 *  thing rather than two slightly different explanations drifting apart. */
export function FadeLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] leading-relaxed text-gray-500">
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2 w-2 flex-shrink-0 rounded-full bg-[#10b981]" />
        <span>
          <span className="font-semibold text-[#10b981]">Hit</span> — our rank landed closer to how the
          season actually finished than ADP&apos;s did.
        </span>
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2 w-2 flex-shrink-0 rounded-full bg-rose-500" />
        <span>
          <span className="font-semibold text-rose-400">Miss</span> — ADP&apos;s rank was the better
          call.
        </span>
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2 w-2 flex-shrink-0 rounded-full bg-amber-500" />
        <span>
          <span className="font-semibold text-amber-500">Push</span> — a dead-even tie.
        </span>
      </span>
    </div>
  )
}

export function RookieBadge() {
  return (
    <span className="inline-block rounded border border-indigo-500/30 bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-300">
      R
    </span>
  )
}

/** How a row's interval was produced — the honest caveat, not a decoration.
 *
 *  ⚠️ `calibrated` (rookies) is deliberately labelled "Class-level", NOT "Calibrated". The rookie
 *  band is quantised to a handful of buckets PER POSITION rather than fitted per player: every
 *  rookie QB in a bucket carries the identical 26.5–277.0 band even though their point projections
 *  span 25 to 268. So it is a band for rookies at that draft tier, not a statement about THIS
 *  player, and the point projection can sit anywhere inside it. Calling that "calibrated" would
 *  imply a per-player interval we do not have. Model-side fix is routed to NF1.4. */
export const UNCERTAINTY_LABEL: Record<string, string> = {
  empirical: "Player",
  // NF1.7: the rookie band is now PER-PLAYER, so it is labelled — and rendered — as a real interval.
  // `calibrated` (the class-level tercile bucket) remains a live fallback for a rookie the per-player
  // fit has too little draft history to speak to, and keeps its honest "Class-level" demotion.
  calibrated_per_player: "Player",
  calibrated: "Class-level",
}
export const UNCERTAINTY_HELP: Record<string, string> = {
  empirical:
    "Player-specific — the range comes from this player's own game-to-game scoring variance across the seasons he has actually played.",
  calibrated_per_player:
    "Player-specific — a rookie has no NFL history, so this range is fitted from what drafted rookies with HIS projection, draft slot and position actually went on to score (busts included, counted as zero). It is roughly twice as wide as a veteran's, which is honest: there is genuinely less to go on.",
  calibrated:
    "Class-level, NOT player-specific — the range for rookies at his draft tier, shared by every rookie in that tier. It is deliberately wide, and his point projection can sit anywhere inside it. Treat it as 'rookies are unpredictable', not as a forecast interval for him.",
}

/** A column header (or any label) with an explainer on hover/focus. These boards use several terms
 *  of art — VOR, replacement, ADP — that are unreadable at a glance to anyone who has not met them,
 *  so the definition travels with the column rather than living in a paragraph below the table. */
export function InfoTip({
  label,
  srLabel,
  bare,
  children,
}: {
  label: React.ReactNode
  /** The accessible name, when `label` is a NODE rather than a string.
   *
   *  ⚠️ NF-C8. The fallback below ("What this means") is fine for an icon-only tip and useless the
   *  moment the label carries meaning that only renders VISUALLY — the availability chip is a
   *  coloured number, so a screen reader met a button called "What this means" sitting next to a
   *  bare figure, i.e. exactly the unexplained number the tip exists to explain. Optional, so every
   *  existing caller is unchanged. */
  srLabel?: string
  /** Render the trigger WITHOUT the dotted underline and the ⓘ glyph.
   *
   *  ⚠️ NF-C8, and it is a scoped exception rather than a style knob. The underline+icon is what
   *  says "there is a definition behind this" for a plain text label, and removing it from one is
   *  removing the only affordance it has. It is redundant ONLY where a labelled, defined column
   *  header sits directly above the cell — the reader has already met the ⓘ once per column, and
   *  repeating it on every row of a dense table that already scrolls sideways on a phone costs
   *  width on every row to say the same thing again. The trigger stays a real focusable `<button>`
   *  with its accessible name, so keyboard and screen-reader access are untouched; what goes is
   *  chrome, not function. ⛔ Do not pass this where the label is the only thing on screen. */
  bare?: boolean
  children: React.ReactNode
}) {
  // Built on POPOVER, not Tooltip, and that is deliberate: Radix's Tooltip closes on pointerdown by
  // design, so a tap can never open it — on a phone (no hover) the definition would be unreachable,
  // and these definitions are what make the boards readable. Popover is click/tap-driven (Radix
  // toggles the controlled `open` state on click on its own), and the hover handlers below ADD the
  // usual tooltip feel on a mouse on top of that. `button` keeps it keyboard-focusable.
  //
  // 🐛 the hover handlers must be POINTER events gated to `pointerType === "mouse"`, not plain
  // `onMouseEnter`/`onMouseLeave` (2026-08-02 mobile bug): a touch tap fires a real `click` (which
  // Radix uses to open it) immediately followed by a browser-synthesized `mouseleave` on the same
  // element (touch simulates a brief hover-then-leave on many mobile browsers) — a plain
  // `onMouseLeave` closed it again in the same frame, so the definition "popped up and immediately
  // went away" on a phone. Pointer events reliably carry `pointerType`, so gating on `=== "mouse"`
  // makes a touch tap invisible to these handlers entirely; Radix's own click-to-toggle is then the
  // ONLY thing driving touch, exactly like the tap-to-open guarantee this component already promises.
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={
            typeof label === "string"
              ? `${label} — what this means`
              : srLabel
                ? `${srLabel} — what this means`
                : "What this means"
          }
          onPointerEnter={(e) => {
            if (e.pointerType === "mouse") setOpen(true)
          }}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") setOpen(false)
          }}
          // Browsers' default stylesheet resets `text-transform: none` on <button> — it is otherwise
          // an INHERITED property, so a plain <th> in an `uppercase` header row picks that up for
          // free but this button doesn't, and silently renders "Fade" instead of "FADE" next to
          // "POS"/"ADP" siblings that never went through a button. `inherit` restores the normal CSS
          // inheritance so this reads correctly both inside an uppercase header AND inline mid-sentence
          // (e.g. the Confidence badge on the player page), which is exactly what "inherit" should do.
          style={{ textTransform: "inherit" }}
          className={
            bare
              ? "inline-flex cursor-help items-center"
              : "inline-flex cursor-help items-center gap-1 underline decoration-dotted decoration-gray-600 underline-offset-4"
          }
        >
          {label}
          {!bare && <Info className="h-3 w-3 text-gray-600" aria-hidden />}
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        // don't steal focus on hover-open, or the pointer leaving would fight the focus ring
        onOpenAutoFocus={(e) => e.preventDefault()}
        className="max-w-xs border-[#262626] bg-[#0f0f0f] p-3 text-xs font-normal leading-relaxed text-gray-300"
      >
        {children}
      </PopoverContent>
    </Popover>
  )
}

/** Definitions shared by the boards — one wording, so a term never means two things across surfaces. */
export const GLOSSARY = {
  // ⭐ RE-EXPORTED, NOT RE-TYPED. These two are claim-bearing — they describe what our published
  // number IS — so their canonical text lives in `lib/fantasy-claim-copy.ts`, where the
  // `_CLAIM_DENYLIST` screen and the no-measured-figure rule (`test_nf_tr1_claim_copy.py`) already
  // run over every string literal. Pasting the prose here instead would put the single most
  // load-bearing disclosure on the boards outside every copy governance check there is.
  expectedPoints: EXPECTED_POINTS_DEFINITION,
  projectedGames: PROJECTED_GAMES_DEFINITION,
  fullSeasonRate: FULL_SEASON_RATE_DEFINITION,
  vor: "Value over replacement. A player's projected points minus the points of the best player at his position who does NOT start anywhere in your league. It is what makes positions comparable: an elite quarterback scores more raw points than an elite running back, but if every team can start a good quarterback anyway, those points buy you less.",
  replacement:
    "The points of the first player at this position who does not crack a starting lineup anywhere in the league — the level you could get for free off waivers. It moves with your format: more teams, or a superflex spot, pushes it deeper.",
  nextAtPos:
    "How much value you give up by passing on this player and taking the next one at his position instead. A big number means a cliff — the tier ends here. A small number means you can comfortably wait.",
  adp: "Average draft position across thousands of real public drafts (Fantasy Football Calculator), matched to your scoring format and league size. It is a picture of what other drafters are doing — a reference point, not a target and not a competitor we claim to beat.",
  adpDelta:
    "Where our board differs from the room. A positive number means the public typically drafts him LATER than we rank him; a negative number means they take him EARLIER. On the overall board that is ADP minus our overall rank. On a position tab it compares like with like — our rank at the position against the room's rank at that position, derived from ADP — because ADP is an overall pick number and subtracting it from a positional rank would compare two different scales. Big gaps are where our projection and the consensus genuinely disagree; read them alongside the 80% range, which tells you how sure the model is.",
  confidence:
    "How much played history sits behind the projection — high is 10 or more games in the season we project from, medium is 5 to 9, low is fewer than 5. Every rookie is low by definition, having never played an NFL game. It describes how much EVIDENCE there is, which is not the same as how good the player is: a low-confidence projection can still be a high one.",
  tier: "A grouping of players of similar value, split where there is an unusually large drop to the next player (bigger than the typical gap on this board). Tiers are the practical draft question — inside a tier you can take whoever you prefer, but letting a tier run out before you pick costs you real value. Kickers and defences are left untiered: their whole field fits inside a few points, so a tier break there would be splitting noise rather than value.",
  replacementPlayer:
    "The specific player sitting at this position's replacement level — roughly the calibre you should still be able to get for free, or very late. He is the yardstick every player at the position is measured against.",
  overallRank:
    "Our model's own rank across every position, for your league's format and roster shape — where WE would take this player if the draft started right now. It is not the market's rank (that's ADP, shown separately) and not a promise of where he'll actually be drafted.",
  fade: "A player where our rank and that season's ADP genuinely disagreed — his gap between the two, within his position, was in the top quarter of gaps that season. This runs BOTH ways: it flags a player we had much higher on our board than the room did, or much lower — not just one direction. These are our highest-conviction calls against the market, which is where an honest track record is most informative: anyone can look good agreeing with consensus. Each one is also graded: hit (green) means our rank ended up closer to how the season actually finished than ADP's did; miss (red) means ADP's rank was the better call; push (gray) means it was a dead-even tie. A fade is a high-conviction call, not a guaranteed win — the misses are shown here too.",
  consistency:
    "How much this player's points PER GAME have swung from one season to the next — not how spiky he is week to week within a season, which is a different question this doesn't answer. Steady means his per-game rate has stayed in a fairly tight band across seasons; Boom-or-bust means it has swung widely — a monster season followed by a quiet one, or the reverse. Based on games he actually played, so a season lost to injury doesn't get counted as a bad rate — that's what the Games/missed column already covers. Needs at least 3 qualifying seasons to say anything meaningful; shown as a plain label, not a raw statistic, and it describes the past — it is not a projection of what he'll do next.",
} as const

// ══ NF-C8 — THE AVAILABILITY FLAG ══════════════════════════════════════════════════════════════
//
// Rendered IN THE PROJECTED-GAMES CELL, replacing the plain grey figure rather than adding a
// column. That placement is the point: the number that explains the discount becomes the thing that
// announces it, so a drafter scanning the board sees WHERE to look and WHY in one glance, and the
// board gains a colour instead of a column (this table already scrolls sideways on a phone, and a
// new column would be paid for on every row including the ~95% that carry no flag).
//
// ⛔ Every claim-bearing string here comes from `fantasy-claim-copy.ts`. None of it is typed inline
// — the injury-forecast boundary is one careless verb wide (see that module's NF-C8 block), and a
// sentence written in a component is a sentence no denylist has ever read.

const AVAILABILITY_STYLE: Record<AvailabilityTier, string> = {
  // Amber and rose, matching this file's existing attention palette (`CONF_STYLE`'s medium, and
  // `FadeBadge`'s miss) rather than inventing a third. ⚠️ Colour is never the ONLY carrier: the
  // chip is also a real `<button>` with an accessible name and a tappable definition, so a
  // colour-blind or screen-reader user gets the same disclosure (WCAG 1.4.1).
  limited: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  "heavily-limited": "border-rose-500/40 bg-rose-500/10 text-rose-400",
}

/** The freshness line inside the flag's definition, or `null` when the payload says nothing.
 *
 *  ⚠️ THE THREE STATES ARE NOT TWO (NF-FRESH2, and NF1.7 (a) for the third):
 *    • no `freshness`, or no `input_vintage`, or the KEY ABSENT → `null`, render nothing. A payload
 *      that predates the stamp must not be described, and during an NF-C0 deploy-skew window that
 *      is every payload.
 *    • the key present with a NULL value → "unknown". The exporter looked and could not resolve it;
 *      dropping that silently would let a missing stamp read as covered.
 *    • an unparseable string → also "unknown", via `shortStamp`, for the same reason.
 */
export function availabilityAsOfLine(freshness?: FreshnessBlock | null): string | null {
  const vintage = freshness?.input_vintage
  if (!vintage || !("sleeper_status_as_of" in vintage)) return null
  const stamp = shortStamp(vintage.sleeper_status_as_of)
  return `${AVAILABILITY_DATA_AS_OF_PREFIX} ${stamp ?? AVAILABILITY_DATA_AS_OF_UNKNOWN}`
}

/**
 * The projected-games figure, flagged when the row's availability discount is material.
 *
 * ⭐ ONE COMPONENT FOR ALL THREE SURFACES (rankings, projections, player page) rather than three
 * conditionals. The tiering rule, the palette, the wording and the accessible name are then a
 * single edit — the E9.61 "two renderers of one field are two rule sets" lesson, applied before it
 * becomes true rather than after.
 *
 * ⚠️ RENDERS THE PLAIN FIGURE WHEN THERE IS NO FLAG, and that is what makes it safe to use as a
 * drop-in for the bare `numOrLock(p.g, p.locked)` it replaces: an unflagged row is byte-identical
 * to what shipped before, a locked row still gets its lock chip, and an absent `g` still gets its
 * em-dash. `availabilityTier` refuses locked and absent rows, so neither can reach the chip branch.
 */
export function AvailabilityFlag({
  games,
  locked,
  freshness,
  underDefinedHeader,
}: {
  games: number | null | undefined
  locked?: boolean
  /** From `manifest.freshness` (boards) or `projections.freshness` (the projections table and the
   *  player page). Omit and the flag simply carries no as-of line. */
  freshness?: FreshnessBlock | null
  /** ⭐ THE TABLES PASS THIS; THE PLAYER PAGE DOES NOT, and the asymmetry is the whole point.
   *
   *  On Rankings and Projections the projected-games COLUMN HEADER is itself an `InfoTip` carrying
   *  `PROJECTED_GAMES_LABEL` and its definition, directly above every cell — so the per-row ⓘ says
   *  a second time what the header already said, once per row, in a table that already scrolls
   *  sideways on a phone. The coloured chip is its own affordance there. The player page has no such
   *  header, so the flag keeps the glyph and remains discoverable. (Operator call, 2026-08-22.) */
  underDefinedHeader?: boolean
}) {
  const tier = availabilityTier(games, { locked })
  if (tier == null) return <>{numOrLock(games, locked)}</>

  const value = num(games)
  const asOf = availabilityAsOfLine(freshness)
  return (
    <InfoTip
      bare={underDefinedHeader}
      srLabel={`${value} projected games — ${AVAILABILITY_FLAG_LABEL.toLowerCase()}`}
      label={
        // `whitespace-nowrap` for the same reason `FadeBadge` carries it: this chip lives in a
        // right-aligned cell of a table that already scrolls, and a break would draw the border
        // around a two-line figure.
        <span
          className={`inline-block whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-semibold tabular-nums ${AVAILABILITY_STYLE[tier]}`}
        >
          {value}
        </span>
      }
    >
      <p className="font-semibold text-gray-200">
        {AVAILABILITY_FLAG_SUMMARY.replace("{games}", value)}
      </p>
      <p className="mt-2">{AVAILABILITY_FLAG_DEFINITION}</p>
      <p className="mt-2">
        <span className="font-medium text-gray-400">{PROJECTED_GAMES_LABEL}</span> —{" "}
        {GLOSSARY.projectedGames}
      </p>
      {asOf && <p className="mt-2 text-gray-500">{asOf}</p>}
    </InfoTip>
  )
}

// ══ NF-C9 — THE WEEKLY GAME-STATUS DESIGNATION ═════════════════════════════════════════════════
//
// Rendered BESIDE the projected-games figure, which is the only placement that makes the sentence
// land: the whole disclosure is "this designation is NOT in that number", so it has to sit next to
// the number it is not in. It is a SEPARATE component from `AvailabilityFlag` on purpose —
//
//   ⭐ THEY ARE INDEPENDENT FACTS, AND COUPLING THEM WOULD MISS THE MOTIVATING CASE. The flag fires
//     on OUR projection (a materially low `g`); this fires on a THIRD PARTY'S filing. A player can
//     carry either without the other, and the row that prompted NF-C8's finding is exactly that
//     shape — Jordyn Tyson sat at 13.6 projected games, ABOVE `LIMITED_AVAILABILITY_GAMES`, so a
//     disclosure hung off the flag would never have rendered for the player it was written for.
//   ⭐ IT KEEPS NF-C8's SUITE HONEST. Folding a second concern into `AvailabilityFlag` would make
//     that story's clauses fail for reasons unrelated to anything it defends (the NF-D17 rule about
//     adding a new story's requirement to an older story's guard).
//
// ⛔ NEUTRAL, AND THE COLOUR IS ITSELF A CLAIM. Amber and rose on the availability flag mean "our
// projection moved". This chip means the opposite — "a club filed this and our number did not
// move" — so painting it in the attention palette would say, in the only language a scanning reader
// actually reads, that we priced it. Slate is the honest colour here, and it is not a styling
// preference. Colour is never the sole carrier either: the chip is a real `<button>` whose
// accessible name spells the designation out in full (WCAG 1.4.1).

const DESIGNATION_CHIP =
  "inline-block whitespace-nowrap rounded border border-slate-500/40 bg-slate-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300"

/**
 * The un-modelled weekly designation, or nothing at all.
 *
 * ⚠️ THREE STATES, MATCHING WHAT THE EXPORTER CAN ACTUALLY ESTABLISH (NF-FRESH2's absent-vs-null
 * rule; `export_draft_board_json.weekly_designation_map` is the other half of this contract):
 *
 *   • `status` ABSENT (`undefined`) → render NOTHING. Either the feed had nothing to disclose about
 *     him — no designation, or a roster move the projection ALREADY prices — or the build could not
 *     read the feed at all. In every one of those cases this channel has no true sentence to say,
 *     and a board-wide "unknown" during a routine ingest gap would put a scary word on every row
 *     (the hazard `AVAILABILITY_DATA_AS_OF_PREFIX`'s doc names). The board-level statement already
 *     exists: the injury vintage under the availability flag.
 *   • `status` NULL → render "unknown". The feed said something the build could not interpret.
 *     Dropping it silently would let an unreadable value read as a clean bill of health, which is
 *     the one direction that is never safe (NF1.7 (a)).
 *   • `status` a STRING → render it. A designation this client does not know renders VERBATIM
 *     rather than as "unknown" — a newer exporter serving a new label to an older client is an
 *     NF-C0 deploy-skew window, and the honest rendering there is the word the server sent.
 *
 * ⛔ It never invents "Active"/"Healthy" for a player with no designation. Silence is the correct
 * rendering of "we were told nothing", and a fabricated clean status is the one output here that
 * would be worse than the gap this story exists to close.
 */
export function WeeklyDesignation({
  status,
  freshness,
}: {
  /** The served `gameStatus`. `undefined` (absent) and `null` are DIFFERENT — see above. */
  status?: string | null
  /** From `manifest.freshness` / `projections.freshness`. Supplies the same injury-feed vintage the
   *  availability flag names, because it is the same feed and the same snapshot — Sleeper carries no
   *  per-designation timestamp, so a per-row date would be a precision the source does not have. */
  freshness?: FreshnessBlock | null
}) {
  if (status === undefined) return null

  const known = status == null ? null : status
  const label = known ?? WEEKLY_DESIGNATION_UNKNOWN
  const glyph = known == null ? WEEKLY_DESIGNATION_UNKNOWN : (WEEKLY_DESIGNATION_CODE[known] ?? known)
  const asOf = availabilityAsOfLine(freshness)

  return (
    <InfoTip
      // `bare` because the bordered chip IS the affordance — the same argument `AvailabilityFlag`
      // makes for its own chip, and it holds on every surface here rather than only where a defined
      // column header sits above (this chip is never a bare run of text).
      bare
      srLabel={`${WEEKLY_DESIGNATION_LABEL.toLowerCase()}: ${label}`}
      label={<span className={DESIGNATION_CHIP}>{glyph}</span>}
    >
      <p className="font-semibold text-gray-200">
        {known == null
          ? WEEKLY_DESIGNATION_UNKNOWN_SUMMARY
          : WEEKLY_DESIGNATION_SUMMARY.replace("{status}", known)}
      </p>
      {/* ⭐⭐ THE LINE THE STORY IS FOR. It renders on BOTH branches — an unrecognised value is
          exactly as un-modelled as a recognised one, and a reader who meets "unknown" with no
          disclaimer would have no way to tell. */}
      <p className="mt-2">{WEEKLY_DESIGNATION_NOT_MODELLED}</p>
      <p className="mt-2">{WEEKLY_DESIGNATION_NOT_A_DIAGNOSIS}</p>
      {asOf && <p className="mt-2 text-gray-500">{asOf}</p>}
    </InfoTip>
  )
}


// NF-INJ-NEWS-1 — a chip VISUALLY DISTINCT from both siblings, because it means something different.
// The availability flag is amber/rose (a warning about a number), the weekly designation is slate (a
// neutral fact from the feed); this is indigo and reads as a small hand-marked annotation, which is
// exactly what it is. ⛔ Not amber: this chip is NOT a severity signal — the severity, if any, is
// already carried by the games number itself through `AvailabilityFlag`.
const REPORTED_ABSENCE_CHIP =
  "inline-block whitespace-nowrap rounded border border-indigo-400/40 bg-indigo-400/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-300"

/** NF-INJ-NEWS-1 — the reported-absence provenance stamp: "a person on our side lowered this number
 *  by hand, here is what they read".
 *
 *  ⭐ RENDERS NOTHING WITHOUT A SOURCE URL, and that is a correctness rule rather than a styling
 *  choice. The whole claim this chip makes is "there is something to check"; a chip with no link
 *  would assert a manual adjustment while withholding the only thing that distinguishes it from a
 *  guess. The exporter already omits the key entirely on an un-stamped row (absent ≠ null,
 *  NF-FRESH2), so the normal path here is `undefined` and nothing renders.
 *
 *  ⛔ IT SAYS WHAT WE DID, NEVER WHAT WILL HAPPEN. No return date, no body part, no diagnosis —
 *  see the copy block in `fantasy-claim-copy.ts`. */
export function ReportedAbsence({
  reported,
}: {
  /** The served `reportedAbsence`. ABSENT for almost every player — the key is set only on a row an
   *  operator judgment actually moved, so an un-overridden player is unchanged from before this
   *  mechanism existed. */
  reported?: { sourceUrl?: string | null; enteredAt?: string | null } | null
}) {
  const url = reported?.sourceUrl
  if (!url) return null
  const entered = shortStamp(reported?.enteredAt)

  return (
    <InfoTip
      bare
      srLabel={REPORTED_ABSENCE_LABEL.toLowerCase()}
      label={<span className={REPORTED_ABSENCE_CHIP}>{REPORTED_ABSENCE_LABEL}</span>}
    >
      <p className="font-semibold text-gray-200">{REPORTED_ABSENCE_SUMMARY}</p>
      {/* ⭐ BOTH honesty lines render UNCONDITIONALLY. A caveat that appears only in some states is
          a caveat a reader learns to ignore, and these two are what keep a hand adjustment from
          reading as a model output or as a medical opinion. */}
      <p className="mt-2">{REPORTED_ABSENCE_MANUAL}</p>
      <p className="mt-2">{REPORTED_ABSENCE_NOT_A_FORECAST}</p>
      <p className="mt-2">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="text-indigo-300 underline underline-offset-2 hover:text-indigo-200"
        >
          {REPORTED_ABSENCE_SOURCE_LABEL}
        </a>
      </p>
      {entered && (
        <p className="mt-2 text-gray-500">{`${REPORTED_ABSENCE_ENTERED_PREFIX} ${entered}`}</p>
      )}
    </InfoTip>
  )
}


/** The ADP-delta column header. Plain English on purpose — "Δ" reads as statistical notation and
 *  tells a drafter nothing about what the number means. */
export const ADP_DELTA_LABEL = "vs ADP"

/** A p10–p90 band drawn on a shared domain, with the projection marked. The visual carries the
 *  uncertainty that a single number hides — the point is deliberately a small tick, not a bar. */
export function IntervalBar({
  p10,
  point,
  p90,
  min,
  max,
  classLevel = false,
}: {
  p10: number | null | undefined
  point: number | null | undefined
  p90: number | null | undefined
  min: number
  max: number
  /** True when the band is a shared class-level range rather than a per-player one — drawn muted
   *  so it never reads as this player's own distribution. */
  classLevel?: boolean
}) {
  const span = max - min
  if (span <= 0 || p10 == null || p90 == null) return <div className="h-1.5" />
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / span) * 100))
  const left = pct(p10)
  const right = pct(p90)
  return (
    <div className="relative h-1.5 w-full rounded-full bg-[#1a1a1a]">
      <div
        className={`absolute h-1.5 rounded-full ${classLevel ? "bg-gray-600/30" : "bg-emerald-500/30"}`}
        style={{ left: `${left}%`, width: `${Math.max(right - left, 0.5)}%` }}
      />
      {point != null && (
        <div
          className={`absolute top-[-2px] h-[10px] w-[2px] rounded-sm ${
            classLevel ? "bg-gray-500" : "bg-emerald-400"
          }`}
          style={{ left: `${pct(point)}%` }}
        />
      )}
    </div>
  )
}

/** The numeric 80% range, with class-level bands visibly demoted and self-explaining on hover. */
export function RangeCell({
  p10,
  p90,
  classLevel = false,
}: {
  p10: number | null | undefined
  p90: number | null | undefined
  classLevel?: boolean
}) {
  if (p10 == null || p90 == null) return <span className="text-[11px] text-gray-600">—</span>
  return (
    <div className={`text-[11px] ${classLevel ? "text-gray-600" : "text-gray-400"}`}>
      {int(p10)}–{int(p90)}
      {classLevel && (
        <span className="ml-1 cursor-help text-[9px] uppercase tracking-wide text-gray-700" title={UNCERTAINTY_HELP.calibrated}>
          class
        </span>
      )}
    </div>
  )
}

/** The standing honest-uncertainty explainer every browse surface carries. */
export function UncertaintyNote({ children }: { children?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4 text-xs leading-relaxed text-gray-400">
      <p>
        <span className="font-semibold text-gray-300">Every number here is a range, not a call.</span>{" "}
        The projection is the middle of a distribution; the 80% range is where the model puts roughly
        eight of ten seasons for that player. A wide range is the model telling you it does not know —
        read the range before the point.
      </p>
      {children}
      <p className="mt-2">
        This is a projection and transparency tool for your own draft decisions. It is a current model
        and modelling is ongoing; we make no claim that it beats any particular ranking, and nothing
        here is betting advice.
      </p>
    </div>
  )
}

/** NF1.5b — the MARKET-LEAN caveat: which positions' ordering incorporates market consensus.
 *
 *  🚨 THIS IS THE HONEST FRAME FOR THE SERVED BOARD, and it is deliberately rendered from the
 *  PAYLOAD rather than hard-coded. The board we serve re-orders our own calibrated projections using
 *  market consensus (ADP/ECR) at the positions where doing so measurably helped on the backtest. So
 *  the ordering DID beat consensus ADP overall — a real, measured result — but at a market-leaning
 *  position it is NOT an independent read on the market, and it must never be presented as beating a
 *  market it is partly built from. Which positions those are is a MODEL decision that can change on
 *  the next re-selection, so the copy takes them from `market_lean` and the sentence itself from
 *  `market_lean_note`: the wording travels with the model that earned it and cannot drift.
 *
 *  Renders nothing for a market-BLIND payload (no `market_lean`) — there is nothing to caveat. */
export function MarketLeanNote({
  lean,
  note,
}: {
  lean?: Record<string, string> | null
  note?: string | null
}) {
  const positions = marketLeaningPositions(lean)
  if (!note || positions.length === 0) return null
  return (
    <p className="mt-2">
      <span className="font-semibold text-gray-300">
        Where the ranking uses the market: {positions.join(", ")}.
      </span>{" "}
      {note}
    </p>
  )
}

/** NF-INJ-NEWS-1 — the board-level disclosure of the manual-override mechanism.
 *
 *  ⭐ WHY A BOARD-LEVEL NOTE EXISTS AT ALL, given every affected row already carries a chip: a
 *  mechanism that announces itself only on the rows it touched is VISIBLE, not DISCLOSED. A reader
 *  scrolling a board has no way to learn that some of these numbers are hand-adjusted unless they
 *  happen to hover the right player — and "some of our numbers were set by a person" is exactly the
 *  kind of thing a reader is entitled to know before they trust any of them.
 *
 *  ⚠️ IT RENDERS ONLY WHEN THE COUNT IS ABOVE ZERO, and that is honesty rather than tidiness: the
 *  copy says a small number of players carry a hand-lowered projection, and on a board where none
 *  do that sentence is simply false. An export that predates the mechanism has no count at all and
 *  likewise renders nothing (absent ≠ 0 — NF-FRESH2). */
export function ReportedAbsenceNote({ count }: { count?: number | null }) {
  if (typeof count !== "number" || count <= 0) return null
  return (
    <p className="mt-2">
      <span className="font-semibold text-gray-300">
        {REPORTED_ABSENCE_LABEL}: {count} {count === 1 ? "player" : "players"}.
      </span>{" "}
      {REPORTED_ABSENCE_METHOD_DISCLOSURE}
    </p>
  )
}

/** NF-C-HEALTHY — "how this projection is built", the SERVED-STACK companion to the NF3.4 panel
 *  below. It describes what actually produced the projection shown elsewhere on this page: a
 *  per-position baseline (MVP-1), refined within each position using market consensus at the
 *  positions where that measurably helped (NF1.5, when this export is running the market-aware
 *  lineage), and a season-long rate recalibration against realized outcomes (NF-TR2b's veteran
 *  level policy, when it is live). Every clause is sourced from the manifest's OWN stamp columns —
 *  never hard-coded — so a rollback or a pre-recalibration export renders honestly instead of
 *  claiming a stage that isn't actually in this build. The MVP-1 baseline clause is always true and
 *  always rendered; the market-aware and level-recalibration clauses degrade gracefully — a
 *  pre-NF1.5b or pre-NF-TR2 export just omits the clause it predates rather than claiming it. The
 *  caller gates rendering on the manifest having loaded at all (see `player-page.tsx`). */
export function ProjectionMethodologyNote({
  projectionSource,
  projectionLabel,
  veteranLevelPolicy,
}: {
  projectionSource?: string | null
  projectionLabel?: string | null
  veteranLevelPolicy?: VeteranLevelPolicy | null
}) {
  const marketAware = projectionSource === "nf1_5"
  const levelOn = veteranLevelPolicy?.status === "recalibrated"
  const stages = ["a per-position baseline level and range (our MVP-1 model)"]
  if (marketAware) {
    stages.push(
      `refined within each position using market consensus, at the positions where doing so measurably helped on the backtest (${projectionLabel ?? "NF1.5"})`,
    )
  }
  if (levelOn) {
    stages.push(
      `each position's season-long rate recalibrated against realized outcomes (${veteranLevelPolicy?.level_model_version ?? "our veteran level model"}, live)`,
    )
  }
  return (
    <p
      data-testid="projection-methodology-note"
      className="mb-4 text-[11px] leading-relaxed text-gray-600"
    >
      <span className="font-semibold text-gray-400">How this projection is built: </span>
      {stages.join(", then ")}. This is the model that produced the number above — the panel below,
      when shown, is a second, separate model's independent read on the same player.
    </p>
  )
}

/** NF3.4 — "what pushes {player}'s number up or down", the PER-PLAYER transparency panel.
 *
 *  🚨 HONEST LABELLING is the whole point of this component: every point value comes from our NF1
 *  research model's OWN separate prediction for this player (LightGBM TreeSHAP, exact — the
 *  contributions always sum to `contrib.totalPts`), which is NOT guaranteed to equal the served
 *  projection shown elsewhere on this page (see `ProjectionMethodologyNote` for what actually
 *  built that one). The panel says so plainly rather than implying the two numbers are the same
 *  thing. Renders nothing for a rookie or K/DST (NF1 doesn't cover them) or if the manifest carries
 *  no legend yet (an older export) — see `ProjectedPlayer.contrib` / `Manifest.featureLegend`. */
export function PlayerContributionsPanel({
  playerName,
  contrib,
  legend,
}: {
  playerName: string
  contrib: import("@/lib/fantasy").ProjectedPlayer["contrib"]
  legend: Record<string, { label: string; description: string }> | null | undefined
}) {
  if (!contrib || !legend || contrib.drivers.length === 0) return null
  const maxAbs = Math.max(...contrib.drivers.map((d) => Math.abs(d.pts)), 0.1)
  return (
    <section className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
        <InfoTip label={`What pushes ${playerName}'s number up or down`}>
          These points come from our separate research model (NF1) — it re-weights the same
          underlying signals your projection above is built from, but LEARNS how much each one
          matters instead of using a fixed formula. Its own total for {playerName} is{" "}
          {contrib.totalPts.toFixed(1)} points, which is <strong>not necessarily the same number</strong>{" "}
          as the projection shown above (that one comes from our served model, not this research
          one) — think of this as &ldquo;what our research model sees in him specifically,&rdquo; a second,
          independent read, not a receipt for the number above it.
        </InfoTip>
      </h2>
      <p className="mb-3 text-[11px] leading-relaxed text-gray-600">
        Player-specific. Across every player our research model scores, its average is{" "}
        {contrib.biasPts.toFixed(1)} points — that part is the same for everyone.{" "}
        {playerName}&apos;s own baseline projection already puts HIM at {contrib.baselinePts.toFixed(1)}{" "}
        before any signal below is applied (a different starting point than another player at his
        position would have, because his own baseline differs) — these signals move it further still,
        based on what specifically stands out about him.
      </p>
      <div className="space-y-3">
        {contrib.drivers.map((d) => {
          const entry = legend[d.feature]
          const positive = d.pts >= 0
          return (
            <div key={d.feature}>
              {/* label + value share the top line but never fight for space with the bar — a label
                  wraps onto a second line rather than being cut off (the whole point of this panel
                  is that the label is legible; a truncated one defeats it, esp. on a narrow phone) */}
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs leading-snug text-gray-300">
                  {entry ? (
                    <InfoTip label={entry.label}>{entry.description}</InfoTip>
                  ) : (
                    d.feature
                  )}
                </span>
                <span
                  className={`flex-shrink-0 text-right text-[11px] tabular-nums ${
                    positive ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {positive ? "+" : ""}
                  {d.pts.toFixed(1)}
                </span>
              </div>
              <div className="relative mt-1 h-1.5 w-full rounded-full bg-[#1a1a1a]">
                <div
                  className={`absolute top-0 h-1.5 rounded-full ${positive ? "bg-emerald-500/60" : "bg-rose-500/60"}`}
                  style={{
                    left: positive ? "50%" : `${50 - (Math.abs(d.pts) / maxAbs) * 50}%`,
                    width: `${Math.max((Math.abs(d.pts) / maxAbs) * 50, 2)}%`,
                  }}
                />
                <div className="absolute left-1/2 top-0 h-1.5 w-px bg-gray-700" />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

/** A short date for a provenance stamp, or null when the string is absent/unparseable.
 *  ⚠️ An ISO DATE (`2026-08-14`, what the market stamps are) parses as UTC MIDNIGHT, so rendering
 *  it with the local calendar shows the previous day west of Greenwich. Dates are formatted in UTC;
 *  full timestamps (the lake vintages, which carry a real time) keep local rendering. */
function shortStamp(value?: string | null): string | null {
  if (!value) return null
  const d = new Date(value)
  if (isNaN(d.getTime())) return null
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value)
  return d.toLocaleDateString(undefined, {
    month: "numeric",
    day: "numeric",
    ...(dateOnly ? { timeZone: "UTC" } : {}),
  })
}

/** NF-FRESH2 — the per-input vintage items for the provenance strip.
 *
 *  ⭐ WHY THIS EXISTS. Before it, every fantasy surface rendered ONE `built <date>` over a row
 *  whose inputs had three different vintages: on 2026-08-10 the board said "built 8/10" beside an
 *  ADP column whose draft window ended 7/25 and a depth-chart view from 8/03. A reader reasonably
 *  takes one date as covering the whole row, so the strip was dishonest by omission — the staleness
 *  was real and only inferable by an audit. A staleness figure must be VISIBLE.
 *
 *  ⭐ ABSENT ≠ NULL, and the distinction is load-bearing in BOTH directions:
 *    • key ABSENT (an older payload, or an older backend under NF-C0 deploy skew) → emit nothing.
 *      Inventing "unknown" for a payload that never carried the field would put a scary word on
 *      every surface during a routine deploy window.
 *    • value NULL (the exporter looked and could not tell) → emit "unknown". Silently dropping it
 *      would let a missing stamp read as covered by the build date — the exact defect (NF1.7(a):
 *      an unevaluable check is never scored healthy).
 */
function freshnessItems(freshness?: FreshnessBlock | null): string[] {
  if (!freshness) return []
  const items: string[] = []
  if ("adp" in freshness) items.push(`ADP ${shortStamp(freshness.adp?.as_of) ?? "unknown"}`)
  if ("ecr" in freshness)
    items.push(`expert ranks ${shortStamp(freshness.ecr?.as_of) ?? "unknown"}`)
  const vintage = freshness.input_vintage
  if (vintage && "depth_chart_as_of" in vintage)
    items.push(`depth charts ${shortStamp(vintage.depth_chart_as_of) ?? "unknown"}`)
  return items
}

/** Provenance strip — what the numbers were built from and when.
 *
 *  Two lines by design: the BUILD clock on top, the DATA clocks below. Folding them into one line
 *  is what let a build date be read as covering inputs it does not describe. */
export function ProvenanceLine({
  season,
  generatedAt,
  extra,
  freshness,
}: {
  season: number
  generatedAt?: string | null
  extra?: string | null
  /** NF-FRESH2 — from `manifest.freshness` or `projections.freshness`. Omit and the input line
   *  simply does not render (every caller upgraded independently; nothing regresses meanwhile). */
  freshness?: FreshnessBlock | null
}) {
  const when = generatedAt ? new Date(generatedAt) : null
  const inputs = freshnessItems(freshness)
  return (
    <div className="text-[11px] text-gray-600">
      <p>
        {season} season projections
        {extra ? ` · ${extra}` : ""}
        {when && !isNaN(when.getTime()) ? ` · built ${when.toLocaleDateString()}` : ""}
      </p>
      {inputs.length > 0 && (
        <p className="mt-0.5">
          Market and role inputs as of: {inputs.join(" · ")}
        </p>
      )}
    </div>
  )
}

export function SurfaceHeader({
  title,
  blurb,
  children,
}: {
  title: string
  blurb: string
  children?: React.ReactNode
}) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      <p className="mt-1 max-w-3xl text-sm text-gray-400">{blurb}</p>
      {children}
    </div>
  )
}

// ⚠️ `text-base` on MOBILE is deliberate and load-bearing, not a sizing preference.
// iOS Safari AUTO-ZOOMS the page when a form control smaller than 16px receives focus. The zoom
// re-lays-out the viewport underneath the native picker, so the picker opens anchored to
// pre-zoom coordinates and lands somewhere unrelated to the control — the "dropdown pops up in a
// weird spot" report. 16px (text-base) is exactly the threshold that suppresses the zoom; the
// control drops back to text-sm from `sm:` up, where no zoom behaviour exists.
const selectClass =
  "rounded border border-[#262626] bg-[#0f0f0f] px-2.5 py-1.5 text-base sm:text-sm text-gray-200 focus:border-[#10b981] focus:outline-none"

/** League format + size picker. Manifest-driven: whatever (config, size) combos were exported are
 *  exactly what is offered, so a preset that has not been built never renders as a dead option. */
export function FormatSelector({
  manifest,
  configName,
  size,
  onConfig,
  onSize,
  savedLeagues,
  entitled = true,
}: {
  manifest: Manifest | undefined
  configName: string | null
  size: number | null
  onConfig: (c: string) => void
  onSize: (n: number) => void
  /** NF-C0b — the user's own hand-entered (or imported) leagues, offered alongside the shipped
   *  presets. Selecting one switches the surface to that league's exact settings; because a saved
   *  league carries its OWN team count, the size control is not applicable and is hidden. */
  savedLeagues?: { league_id: string; name: string; n_teams: number }[]
  /** Freemium build — whether the caller may open the PAID presets. When false the paid options are
   *  still LISTED, disabled and suffixed, rather than removed.
   *
   *  ⭐ LISTED-BUT-DISABLED IS THE DELIBERATE CHOICE. Removing them would make the free board look
   *  like the only board we publish, which is both untrue and the opposite of what an upgrade
   *  prompt is for; showing them tells the visitor exactly what the membership is. Defaults to true
   *  so a call site that has not been updated keeps its current behaviour. */
  entitled?: boolean
}) {
  // useId (not a literal) so a page rendering two selectors cannot emit duplicate ids.
  const configSelectId = useId()
  const sizeSelectId = useId()
  if (!manifest) return null
  const free = freeSelection(manifest)
  // A locked control only makes sense once the manifest has actually named a free board. On a
  // pre-deploy manifest (`free` null) nothing is marked, which reproduces the old fully-open
  // picker — the honest rendering of "this backend has not narrowed the tier".
  const lockFormats = !entitled && !!free
  const isCustom = !!configName?.startsWith("custom:")
  const config: LeagueConfigMeta | undefined = manifest.configs.find((c) => c.name === configName)
  const league = isCustom
    ? savedLeagues?.find((l) => `custom:${l.league_id}` === configName)
    : undefined
  return (
    <div className="flex flex-wrap items-end gap-3">
      {/* ⚠️ Controls are SIBLINGS of their <label>, never children — nesting an interactive control
          inside a <label> makes a tap activate it twice on iOS. These are `Picker` (Radix) rather
          than a raw <select>: the native popup was anchoring to the top-left of the page on iOS
          regardless of font-size or label nesting. See components/ui/picker.tsx. */}
      <div className="flex flex-col gap-1">
        <label htmlFor={configSelectId} className="text-[11px] uppercase tracking-wider text-gray-500">
          Scoring format
        </label>
        <Picker
          id={configSelectId}
          className={selectClass}
          value={configName}
          onValueChange={onConfig}
          ariaLabel="Scoring format"
          groups={[
            {
              label: "Your leagues",
              options: (savedLeagues ?? []).map((l) => ({
                value: `custom:${l.league_id}`,
                label: `${l.name} (${l.n_teams}-team)`,
              })),
            },
            {
              label: "Standard formats",
              options: manifest.configs.map((c) => {
                const locked = lockFormats && !isFreeConfig(c)
                return {
                  value: c.name,
                  label: locked ? `${c.label} · ${FORMAT_LOCK_SUFFIX}` : c.label,
                  disabled: locked,
                }
              }),
            },
          ]}
        />
      </div>
      {!isCustom && (
        <div className="flex flex-col gap-1">
          <label htmlFor={sizeSelectId} className="text-[11px] uppercase tracking-wider text-gray-500">
            League size
          </label>
          <Picker
            id={sizeSelectId}
            className={selectClass}
            value={size == null ? null : String(size)}
            onValueChange={(v) => onSize(Number(v))}
            ariaLabel="League size"
            options={manifest.sizes.map((n) => {
              // ⚠️ The SIZE is locked too, and separately: `full_ppr` at ten teams is a paid board.
              // A picker that locked only the format would offer a combination the API 403s.
              const locked = lockFormats && n !== free!.size
              return {
                value: String(n),
                label: locked ? `${n} teams · ${FORMAT_LOCK_SUFFIX}` : `${n} teams`,
                disabled: locked,
              }
            })}
          />
        </div>
      )}
      {config && !isCustom && (
        <p className="max-w-md pb-1.5 text-[11px] leading-relaxed text-gray-500">
          {config.description}
        </p>
      )}
      {isCustom && (
        <p className="max-w-md pb-1.5 text-[11px] leading-relaxed text-gray-500">
          Your saved settings for <span className="text-gray-400">{league?.name ?? "this league"}</span>
          {league ? ` (${league.n_teams} teams)` : ""} — scored from exactly what you entered.{" "}
          <a href="/fantasy/league-settings" className="text-sky-400 hover:underline">
            Edit
          </a>
        </p>
      )}
      {lockFormats && (
        <p
          data-testid="format-lock-note"
          className="w-full text-[11px] leading-relaxed text-gray-500"
        >
          {FORMAT_LOCK_EXPLANATION}
        </p>
      )}
    </div>
  )
}

/** Position filter chips. */
export function PositionTabs({
  value,
  onChange,
  positions = [...ALL_POSITIONS],
  allLabel = "All",
}: {
  value: string
  onChange: (p: string) => void
  positions?: string[]
  allLabel?: string
}) {
  const opts = [allLabel, ...positions]
  return (
    <div className="flex flex-wrap gap-1.5">
      {opts.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`rounded border px-2.5 py-1 text-xs font-medium transition-colors ${
            value === p
              ? "border-[#10b981]/50 bg-[#10b981]/10 text-[#10b981]"
              : "border-[#262626] bg-[#0f0f0f] text-gray-400 hover:text-gray-200"
          }`}
        >
          {p}
        </button>
      ))}
    </div>
  )
}

/** ADP delta, signed and coloured. Emerald = we rank him higher than the room drafts him. The colour
 *  is a "we differ here" cue, NOT a value/edge claim — the tooltip on the column says so. */
/** The room's ordering WITHIN a position, derived by ranking that position's rows on ADP.
 *
 *  ⚠️ Needed because ADP is an OVERALL pick number while a position tab ranks 1..n within the
 *  position, and subtracting one from the other compares two different scales. It read as a huge
 *  disagreement that was pure units: the top kicker showed "+131" (K#1 vs pick 131.9) and Josh Allen
 *  "+26" (QB#1 vs pick 26.6) — on rows where our board and the room actually AGREE exactly. The
 *  bigger the position's typical draft slot, the bigger the fake delta, which is why kickers and
 *  defences made it obvious. Ranking ADP within the position puts both sides on the same scale, so
 *  a real disagreement (we say K2, the room says K7) is what survives. */
export function adpPositionRanks<T extends { id: string; adp?: number | null }>(
  rows: T[],
): Map<string, number> {
  const m = new Map<string, number>()
  rows
    .filter((r) => r.adp != null)
    .slice()
    .sort((a, b) => (a.adp as number) - (b.adp as number))
    .forEach((r, i) => m.set(r.id, i + 1))
  return m
}

export function AdpDelta({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="text-gray-600">—</span>
  const rounded = Math.round(delta)
  if (rounded === 0) return <span className="text-gray-500">0</span>
  return (
    <span className={rounded > 0 ? "text-emerald-400" : "text-rose-400"}>
      {rounded > 0 ? `+${rounded}` : rounded}
    </span>
  )
}

// ══ G100-C1 — THE ONE-LEAGUE BOUNDARY, STATED AT THE CONTROL ═════════════════════════════════════
//
// ⭐ WHY THIS IS A SHARED COMPONENT AND NOT A BLOCK OF JSX IN EACH EDITOR. There are TWO ways to
// create a league — the manual editor and platform import — and the first cut gated only the editor.
// So a free account at its quota was refused by the form and waved through by the importer, right up
// to a 409 it met after choosing a platform, typing a username, waiting on a preview and pressing
// Save. That is the freemium build's own lesson recurring (#681 gated one of three renderers and
// looked done): the tier is enforced by WHICH COMPONENT RENDERS, so the boundary has to be one
// component that every create path shows.
//
// ⭐ THE UPGRADE CTA IS BUILT IN, DELIBERATELY. A limit with no way past it is a dead end, and the
// way past it is the conversion this whole funnel exists for. Making it part of the notice means a
// third create path cannot ship the refusal without the offer — the failure mode a per-call-site
// `<Link>` invites.
export function LeagueQuotaNotice({
  title,
  detail,
  action,
  testId = "league-quota-notice",
}: {
  title: string
  detail: string
  /** An escape hatch that does NOT cost money — "edit the league you have", "re-import this one".
   *  Rendered before the upgrade so the free path is offered first. */
  action?: React.ReactNode
  testId?: string
}) {
  return (
    <div
      className="rounded border border-[#262626] bg-[#0f0f0f] p-3 text-xs leading-relaxed"
      data-testid={testId}
    >
      <p className="font-medium text-gray-200">{title}</p>
      <p className="mt-1 text-gray-500">{detail}</p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {action}
        <Link
          href={SUBSCRIBE_HREF}
          className="inline-flex items-center gap-1.5 rounded border border-[#10b981]/40 bg-[#10b981]/10 px-2.5 py-1 font-semibold text-[#10b981] transition-colors hover:bg-[#10b981]/20"
          data-testid="league-quota-upgrade"
        >
          <Lock className="h-3 w-3" /> Become a member for more leagues
        </Link>
      </div>
    </div>
  )
}

export const PAGE_SIZES = [25, 50, 100] as const
export const ALL_ROWS = -1

/** Page-size picker + pager. `total` is the filtered row count, so the caller can page a view that
 *  is already sorted/filtered without this component knowing anything about the data. */
export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (p: number) => void
  onPageSize: (n: number) => void
}) {
  const pageSizeId = useId()
  const showingAll = pageSize === ALL_ROWS
  const pages = showingAll ? 1 : Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : showingAll ? 1 : page * pageSize + 1
  const to = showingAll ? total : Math.min(total, (page + 1) * pageSize)
  const btn =
    "rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-xs text-gray-400 transition-colors hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-40"
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
      <div className="flex items-center gap-1.5">
        <label htmlFor={pageSizeId}>Show</label>
        <Picker
          id={pageSizeId}
          value={String(pageSize)}
          onValueChange={(v) => {
            onPageSize(Number(v))
            onPage(0)
          }}
          ariaLabel="Rows per page"
          className="h-auto rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-base sm:text-xs text-gray-200 focus:border-[#10b981]"
          options={[
            ...PAGE_SIZES.map((n) => ({ value: String(n), label: String(n) })),
            { value: String(ALL_ROWS), label: "All" },
          ]}
        />
      </div>
      <span>
        {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
      </span>
      {!showingAll && pages > 1 && (
        <div className="flex items-center gap-1.5">
          <button className={btn} onClick={() => onPage(0)} disabled={page === 0}>
            «
          </button>
          <button className={btn} onClick={() => onPage(page - 1)} disabled={page === 0}>
            Prev
          </button>
          <span className="px-1">
            Page {page + 1} of {pages}
          </span>
          <button className={btn} onClick={() => onPage(page + 1)} disabled={page >= pages - 1}>
            Next
          </button>
          <button className={btn} onClick={() => onPage(pages - 1)} disabled={page >= pages - 1}>
            »
          </button>
        </div>
      )}
    </div>
  )
}

/** Download rows as CSV. Exports the WHOLE filtered set, not just the visible page — a paginated
 *  export would silently hand back 50 of 700 rows.
 *
 *  NF-CSV1 — `note`, when given, is appended as ONE ROW AFTER THE DATA: its text in the first cell
 *  and the remaining cells empty, so the row keeps the header's arity. That placement is the whole
 *  design and it is owned HERE rather than at the call site, because every part of it is a property
 *  of the FILE rather than of any one export: the header stays row 1 so a header-first parser is
 *  untouched, the note trails the data so a reader who slices rows by index is untouched, and the
 *  arity holds so column tooling is untouched. ⛔ Falsy ⇒ NO ROW AT ALL, never an empty one — an
 *  export with nothing to disclose must be byte-identical to what it was before the note existed. */
export function downloadCsv(
  filename: string,
  headers: string[],
  rows: (string | number | null)[][],
  note?: string | null,
) {
  const esc = (v: string | number | null) => {
    if (v == null) return ""
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))]
  if (note) {
    lines.push([note, ...Array(Math.max(headers.length - 1, 0)).fill(null)].map(esc).join(","))
  }
  const csv = lines.join("\n")
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }))
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-8 text-center text-sm text-gray-500">
      {label}
    </div>
  )
}

/** The honest empty/failed state — says what is missing rather than showing a blank table. */
export function EmptyBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-8 text-center">
      <p className="text-sm font-medium text-gray-300">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-gray-500">{detail}</p>
    </div>
  )
}
