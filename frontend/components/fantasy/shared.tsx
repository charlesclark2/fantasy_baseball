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
import { Info } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Picker } from "@/components/ui/picker"
import type { LeagueConfigMeta, Manifest } from "@/lib/draft-optimizer"
import { marketLeaningPositions } from "@/lib/fantasy"
import type { ProjectedPlayer } from "@/lib/fantasy"
import { useTrackRecordManifest } from "@/lib/fantasy-track-record"

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
  // E9.56b — LEAD WITH THE RECEIPTS, not with the ask.
  //
  // The locked view is, by necessity, the MARKET's board with our numbers removed: E9.56's
  // anti-scrape rule re-orders locked rows onto ADP precisely so the array index cannot reconstruct
  // our ranking. So the page a free visitor lands on cannot argue for itself — on its own it reads
  // as an ADP clone with padlocks, which is a weak thing to ask money for.
  //
  // What CAN argue for it is already public and already measured: the NF3.2 track record (six
  // seasons of our projection vs that season's preseason ADP vs the realized outcome). Rendering
  // its headline VERBATIM keeps this honest — the claim is computed by
  // `export_track_record_json.build_headline` from the scorecard's own numbers, so it cannot drift
  // into marketing copy, and it respects the NF-D3 claim-scope rule at the top of this file (this
  // is a projection product; it never asserts a win rate or an edge).
  //
  // Degrades cleanly: the manifest is a public endpoint, but if it is slow or fails we simply show
  // the ask without the evidence rather than blocking the CTA.
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
            <span className="text-amber-200/60">
              {seasonCount > 0
                ? `Every past season stays free — including how these projections actually did across ${seasonCount} of them.`
                : "Past seasons stay free, including how these projections have actually done."}
            </span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a
            href="/fantasy/track-record"
            className="rounded-md border border-amber-500/40 px-3 py-1.5 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/10"
          >
            See the track record
          </a>
          <a
            href={resolveUpgradeHref(upgrade?.ctaHref)}
            className="rounded-md bg-amber-500 px-3 py-1.5 text-sm font-semibold text-black transition-colors hover:bg-amber-400"
          >
            Subscribe to unlock
          </a>
        </div>
      </div>

      {/* E9.56c — this is option (a)'s whole point ("lead with the track record"), so it cannot be
          the smallest, dimmest text in its own box. Nudged up from 12px/70% opacity. */}
      {receipts?.headline && (
        <p className="mt-2.5 border-t border-amber-500/20 pt-2.5 text-[13px] leading-relaxed text-amber-200/85">
          {receipts.headline}
        </p>
      )}
    </div>
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
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${style}`}>{label}</span>
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
export function InfoTip({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
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
          aria-label={typeof label === "string" ? `${label} — what this means` : "What this means"}
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
          className="inline-flex cursor-help items-center gap-1 underline decoration-dotted decoration-gray-600 underline-offset-4"
        >
          {label}
          <Info className="h-3 w-3 text-gray-600" aria-hidden />
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

/** NF3.4 — "what pushes {player}'s number up or down", the PER-PLAYER transparency panel.
 *
 *  🚨 HONEST LABELLING is the whole point of this component: every point value comes from our NF1
 *  research model's OWN separate prediction for this player (LightGBM TreeSHAP, exact — the
 *  contributions always sum to `contrib.totalPts`), which is NOT guaranteed to equal the served
 *  projection shown elsewhere on this page. The panel says so plainly rather than implying the two
 *  numbers are the same thing. Renders nothing for a rookie or K/DST (NF1 doesn't cover them) or if
 *  the manifest carries no legend yet (an older export) — see `ProjectedPlayer.contrib` / `Manifest.
 *  featureLegend`. */
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

/** Provenance strip — what the numbers were built from and when. */
export function ProvenanceLine({
  season,
  generatedAt,
  extra,
}: {
  season: number
  generatedAt?: string | null
  extra?: string | null
}) {
  const when = generatedAt ? new Date(generatedAt) : null
  return (
    <p className="text-[11px] text-gray-600">
      {season} season projections
      {extra ? ` · ${extra}` : ""}
      {when && !isNaN(when.getTime()) ? ` · built ${when.toLocaleDateString()}` : ""}
    </p>
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
}) {
  // useId (not a literal) so a page rendering two selectors cannot emit duplicate ids.
  const configSelectId = useId()
  const sizeSelectId = useId()
  if (!manifest) return null
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
              options: manifest.configs.map((c) => ({ value: c.name, label: c.label })),
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
            options={manifest.sizes.map((n) => ({ value: String(n), label: `${n} teams` }))}
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
 *  export would silently hand back 50 of 700 rows. */
export function downloadCsv(filename: string, headers: string[], rows: (string | number | null)[][]) {
  const esc = (v: string | number | null) => {
    if (v == null) return ""
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n")
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
