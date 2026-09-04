"use client"

// NCAAF-P3.3 — the strength block, which LEADS the team page.
//
// ⭐⭐ THE BAND IS THE HONESTY, AND IT IS NOT AN ADORNMENT ON THE NUMBER — IT IS HALF THE NUMBER.
//
// At week 1 nothing has been played and the posterior IS the prior: measured on the live 2026
// board, Boise State reads +3.09 with a spread of 7.29, which is a range from about −6 to +12. A
// surface that printed "+3.1" and stopped would be publishing a precision the model does not claim,
// on a vertical whose entire licence to publish rests on `best_alpha = 0` — the rating is context
// for reading a game, never a recommendation about one. So the band is rendered at the same visual
// weight as the rating, immediately beside it, and there is no view of this page in which the
// number appears without it.
//
// ⛔ THE CURVE IS REUSED, NOT FORKED. `DistributionCurve` already owns the drawing, the band
// shading and the "which shape is this" labelling; a second renderer here would be two rule sets
// for one picture (E9.61). What this file supplies is the ADAPTER — see `strengthDistribution` in
// `lib/ncaaf-team.ts` for why turning a posterior's (mean, spread) into a drawable band is
// legitimate HERE and would not be on a game distribution.

import { DistributionCurve } from "./distribution-curve"
import {
  STRENGTH_BAND_PREFIX,
  STRENGTH_DEFENSE_LABEL,
  STRENGTH_OFFENSE_LABEL,
  STRENGTH_CURVE_NOTE,
  STRENGTH_LABEL,
  STRENGTH_PARTS_LABEL,
  STRENGTH_PART_CONFERENCE,
  STRENGTH_PART_COVARIATES,
  STRENGTH_PART_TEAM,
  STRENGTH_PRESEASON_NOTE,
  STRENGTH_SIDES_HINT,
  STRENGTH_SIDES_LABEL,
  STRENGTH_TREND_HINT,
  STRENGTH_TREND_LABEL,
  STRENGTH_MEANING_HINT,
  STRENGTH_UNIT_HINT,
  STRENGTH_ZERO_LABEL,
  STANDING_HINT,
  STANDING_LABEL,
  STANDING_RANGE_PREFIX,
  STANDING_UNAVAILABLE,
} from "@/lib/ncaaf-copy"
import {
  formatSignedPoints,
  standingText,
  strengthDistribution,
  type NcaafTeamStanding,
  type NcaafTeamStrength,
  type NcaafTeamStrengthWeek,
} from "@/lib/ncaaf-team"
import { TeamBlockAbsence } from "./team-block"

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

/** The additive decomposition, as `(label, value)` pairs.
 *
 * ⭐ THE THREE PARTS SUM TO THE RATING EXACTLY — that is a property of the model, and it is what
 * makes the rating auditable instead of a black box. They are shown in the order they compound:
 * the conference you play in, what your roster suggests, then what this season's games have added.
 */
function decomposition(week: NcaafTeamStrengthWeek) {
  return [
    { key: "conference", label: STRENGTH_PART_CONFERENCE, value: week.strength_conference_component },
    { key: "covariates", label: STRENGTH_PART_COVARIATES, value: week.strength_covariate_component },
    { key: "team", label: STRENGTH_PART_TEAM, value: week.strength_team_component },
  ]
}

/**
 * The week-by-week series, drawn as a band with a line through it.
 *
 * ⭐ THE NARROWING IS THE SUBJECT. A reader who sees only the current rating cannot tell a number
 * the model has held all season from one that has just moved, and cannot see that the model started
 * unsure. Plotting the BAND rather than the line alone is what makes "it is more confident now"
 * visible — and a component that plotted only the ratings would look almost identical while saying
 * something much weaker.
 *
 * Inline SVG with a `viewBox`, for the reason `distribution-curve.tsx` records: a measured chart
 * renders nothing at zero width and is structurally unassertable in a harness where layout has not
 * settled, whereas an explicit `<path d>` puts the drawn geometry in the DOM where a spec can read
 * it (NF-C4 — assert rendered output, never source).
 */
function StrengthTrend({ weeks }: { weeks: NcaafTeamStrengthWeek[] }) {
  const usable = weeks.filter(
    (w) => isNum(w.strength_margin) && isNum(w.strength_margin_sd) && w.strength_margin_sd > 0,
  )
  // ⛔ ONE POINT IS NOT A TREND. Rendering a single-week "series" would be a picture of nothing,
  // and in early September that is the ordinary state — so the block is simply omitted, and the
  // current rating above it already says everything one week can say.
  if (usable.length < 2) return null

  const VB_W = 320
  const VB_H = 64
  const PAD_X = 4
  const PAD_Y = 6

  const los = usable.map((w) => (w.strength_margin as number) - 1.2816 * (w.strength_margin_sd as number))
  const his = usable.map((w) => (w.strength_margin as number) + 1.2816 * (w.strength_margin_sd as number))
  const yMin = Math.min(...los)
  const yMax = Math.max(...his)
  const span = yMax - yMin || 1

  const x = (i: number) => PAD_X + ((VB_W - 2 * PAD_X) * i) / (usable.length - 1)
  const y = (v: number) => PAD_Y + (VB_H - 2 * PAD_Y) * (1 - (v - yMin) / span)

  const line = usable.map((w, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(w.strength_margin as number).toFixed(2)}`).join(" ")
  const bandPath =
    usable.map((_, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(his[i]).toFixed(2)}`).join(" ") +
    " " +
    usable
      .map((_, i) => {
        const j = usable.length - 1 - i
        return `L${x(j).toFixed(2)},${y(los[j]).toFixed(2)}`
      })
      .join(" ") +
    " Z"

  const first = usable[0]
  const last = usable[usable.length - 1]

  return (
    <section data-testid="ncaaf-strength-trend" className="space-y-1.5">
      <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {STRENGTH_TREND_LABEL}
      </h3>
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        role="img"
        aria-label={STRENGTH_TREND_HINT}
        preserveAspectRatio="none"
        className="h-16 w-full"
      >
        <path data-testid="ncaaf-strength-trend-band" d={bandPath} fill="rgba(16, 185, 129, 0.16)" />
        <path
          data-testid="ncaaf-strength-trend-line"
          d={line}
          fill="none"
          stroke="#10b981"
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="flex justify-between text-[10px] text-gray-600">
        {/* ⛔ The week labels are the SERVED `as_of_week`, never an index — a series that skipped a
            week would otherwise be relabelled into a contiguous one it is not. */}
        <span data-testid="ncaaf-strength-trend-first">Week {first.as_of_week}</span>
        <span>{STRENGTH_TREND_HINT}</span>
        <span data-testid="ncaaf-strength-trend-last">Week {last.as_of_week}</span>
      </div>
    </section>
  )
}

/**
 * One placement — "42nd of 138 in FBS", and the range that keeps it honest.
 *
 * ⛔⛔ THE RANGE RENDERS OR THE RANK DOES NOT. `standingText` returns null when a payload carries a
 * rank without its bounds, and this component honours that by rendering nothing at all. Degrading
 * to the bare rank would be degrading toward the half that LOOKS most authoritative and is least
 * defensible: on the live 2026 week-1 board the median team's 80% rank range spans 77 of 138
 * places, so "42nd" alone is close to noise presented as a fact.
 */
function Standing({ standing, testId }: { standing: NcaafTeamStanding | null; testId: string }) {
  const text = standingText(standing)
  if (!text || !text.range) return null
  return (
    <div
      data-testid={testId}
      data-standing-rank={standing?.rank ?? ""}
      className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-md border border-[#1e1e1e] px-2.5 py-1.5"
    >
      <span className="text-sm tabular-nums text-gray-200">{text.placement}</span>
      <span data-testid={`${testId}-range`} className="text-[11px] tabular-nums text-gray-500">
        {STANDING_RANGE_PREFIX} {text.range}
        {text.confidence ? ` (${text.confidence})` : ""}
      </span>
    </div>
  )
}

export function NcaafTeamStrengthBlock({ strength }: { strength: NcaafTeamStrength }) {
  if (strength.status !== "available" || !strength.current) {
    return (
      <TeamBlockAbsence
        testId="ncaaf-team-strength"
        label={STRENGTH_LABEL}
        reason={strength.reason}
      />
    )
  }

  const week = strength.current
  const rating = formatSignedPoints(week.strength_margin)
  const dist = strengthDistribution(week)
  const lo = formatSignedPoints(dist?.interval_lo ?? null)
  const hi = formatSignedPoints(dist?.interval_hi ?? null)
  // ⭐ THE PRE-SEASON SENTENCE IS KEYED ON THE SERVED GAME COUNT, not on the week number. A week
  // index is a calendar fact; "no games are behind this number" is the fact that actually explains
  // the width, and it stays true for a team on a bye or one whose opener was cancelled.
  const preseason = week.games_in_window === 0
  // ⚠️ FILTERED ON THE DATA, not on rendered nodes. `standingText` is the ONE place that decides
  // whether a standing is publishable (it returns null for a rank with no range), so the section's
  // "is there anything to show" question and the component's "should I render" question go through
  // the same function and cannot disagree — the E9.61 two-renderers shape, avoided rather than
  // fixed later. An empty list falls to the NAMED absence below, never to a blank heading.
  const standings = (
    [
      ["fbs", strength.standing_fbs],
      ["conference", strength.standing_conference],
    ] as const
  ).filter(([, standing]) => standingText(standing)?.range)

  return (
    <section data-testid="ncaaf-team-strength" data-block-status="available" className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-sm font-semibold text-white">{STRENGTH_LABEL}</h2>
        <p className="max-w-2xl text-[11px] leading-relaxed text-gray-500">{STRENGTH_UNIT_HINT}</p>
      </header>

      {/* ⭐ THE RATING AND ITS BAND, TOGETHER. Not a headline number with a footnote — the range is
          on the same line, in the same block, and there is no rendering path that omits it. */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span
          data-testid="ncaaf-strength-rating"
          data-strength-margin={week.strength_margin ?? ""}
          className="text-3xl font-semibold tabular-nums text-emerald-400"
        >
          {rating ?? "—"}
        </span>
        {lo && hi && (
          <span data-testid="ncaaf-strength-band" className="text-sm tabular-nums text-gray-400">
            <span className="text-gray-500">{STRENGTH_BAND_PREFIX}: </span>
            {lo} to {hi}
          </span>
        )}
        <span data-testid="ncaaf-strength-week" className="text-[11px] text-gray-600">
          through week {strength.as_of_week} · {week.games_in_window ?? 0} game
          {week.games_in_window === 1 ? "" : "s"}
        </span>
      </div>

      {/* ⭐ WHAT THE NUMBER MEANS, before where it places. A reader who cannot convert the rating
          into a judgement cannot use the rank either — the placement is only legible once the
          scale is. */}
      <p data-testid="ncaaf-strength-meaning" className="max-w-2xl text-[11px] leading-relaxed text-gray-500">
        {STRENGTH_MEANING_HINT}
      </p>

      <section data-testid="ncaaf-team-standing" className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
          {STANDING_LABEL}
        </h3>
        {standings.length > 0 ? (
          <>
            <div className="flex flex-wrap gap-2">
              {standings.map(([scope, standing]) => (
                <Standing key={scope} standing={standing} testId={`ncaaf-standing-${scope}`} />
              ))}
            </div>
            <p className="max-w-2xl text-[11px] leading-relaxed text-gray-500">{STANDING_HINT}</p>
          </>
        ) : (
          // ⛔ Named, not blank. An absent ranking and a ranking we chose not to show read the
          // same to a reader unless one of them says so (NF-C6b).
          <p data-testid="ncaaf-team-standing-absent" className="text-[11px] text-gray-500">
            {STANDING_UNAVAILABLE}
          </p>
        )}
      </section>

      {preseason && (
        <p
          data-testid="ncaaf-strength-preseason-note"
          className="max-w-2xl rounded-md border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500"
        >
          {STRENGTH_PRESEASON_NOTE}
        </p>
      )}

      {/* ⚠️ THE WIDTH CONSTRAINT IS PART OF THE DRAWING, NOT DECORATION. `DistributionCurve` uses
          `preserveAspectRatio="none"`, so it stretches to whatever box it is handed — at this
          page's full `max-w-4xl` the 320×96 viewBox was rendered ~896×96 and the bell came out
          flattened into something a reader reads as a broken chart. The pair below keeps the drawn
          box near the 320:96 ≈ 3.3:1 it was designed at, at both widths. */}
      <div className="max-w-xl">
        <DistributionCurve
          testId="ncaaf-strength-curve"
          distribution={dist}
          label={STRENGTH_LABEL}
          hint={STRENGTH_CURVE_NOTE}
          zeroReference
          zeroLabel={STRENGTH_ZERO_LABEL}
          heightClass="h-28 sm:h-40"
          // ⭐ SUPPRESSED, AND ONLY BECAUSE THE HINT ABOVE ALREADY SAYS IT. `STRENGTH_CURVE_NOTE`
          // states this curve's provenance in the words this surface needs. The default note is a
          // DEGRADATION warning written for a game card ("this game's simulated quantiles were not
          // published") — on a posterior whose served form IS a mean and a spread there are no
          // simulated quantiles to be missing, so it announced a defect that does not exist, in
          // amber, under a page about a team and not a game.
          parametricNote={null}
        />
      </div>

      <StrengthTrend weeks={strength.weeks} />

      <section data-testid="ncaaf-strength-parts" className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
          {STRENGTH_PARTS_LABEL}
        </h3>
        <dl className="grid grid-cols-1 gap-1 sm:grid-cols-3">
          {decomposition(week).map((part) => (
            <div
              key={part.key}
              data-testid={`ncaaf-strength-part-${part.key}`}
              className="flex items-baseline justify-between gap-2 rounded-md border border-[#1e1e1e] px-2 py-1.5"
            >
              <dt className="text-[11px] text-gray-500">{part.label}</dt>
              <dd className="text-xs tabular-nums text-gray-300">
                {formatSignedPoints(part.value) ?? "—"}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section data-testid="ncaaf-strength-sides" className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
          {STRENGTH_SIDES_LABEL}
        </h3>
        {/* 🚨 Both halves are HIGHER-IS-BETTER — defense counts points PREVENTED — so they ADD to
            the rating. `offense − defense` returns ~0 for every team, which is exactly the mistake
            this sentence exists to prevent, and it is rendered rather than left in a comment. */}
        <p className="text-[11px] leading-relaxed text-gray-500">{STRENGTH_SIDES_HINT}</p>
        <dl className="grid grid-cols-2 gap-1">
          <div
            data-testid="ncaaf-strength-offense"
            className="flex items-baseline justify-between gap-2 rounded-md border border-[#1e1e1e] px-2 py-1.5"
          >
            <dt className="text-[11px] text-gray-500">{STRENGTH_OFFENSE_LABEL}</dt>
            <dd className="text-xs tabular-nums text-gray-300">
              {formatSignedPoints(week.strength_offense) ?? "—"}
            </dd>
          </div>
          <div
            data-testid="ncaaf-strength-defense"
            className="flex items-baseline justify-between gap-2 rounded-md border border-[#1e1e1e] px-2 py-1.5"
          >
            <dt className="text-[11px] text-gray-500">{STRENGTH_DEFENSE_LABEL}</dt>
            <dd className="text-xs tabular-nums text-gray-300">
              {formatSignedPoints(week.strength_defense) ?? "—"}
            </dd>
          </div>
        </dl>
      </section>
    </section>
  )
}
