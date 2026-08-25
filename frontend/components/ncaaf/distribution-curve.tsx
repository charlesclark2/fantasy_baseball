"use client"

// NCAAF-P3.2 — the signature viz: one served distribution, drawn.
//
// ⭐ HAND-ROLLED INLINE SVG RATHER THAN RECHARTS, and the reason is a testing one before it is an
// aesthetic one. `ResponsiveContainer` measures its parent at runtime and renders NOTHING at zero
// width — so a chart is structurally unassertable in any harness where layout has not settled, and
// the acceptance criterion here is E2E on RENDERED OUTPUT (NF-C4: a guard that reads source, or a
// className, tests that somebody TYPED a string). A `viewBox`'d `<svg>` with an explicit `<path d>`
// renders identically at every width, needs no measurement, and puts the actual drawn geometry in
// the DOM where a spec can read it. It is also ~2 KB against recharts' bundle on a page whose
// whole job is to draw eight of these.
//
// ⛔ IT COMPUTES NO MODEL QUANTITY. The shape comes from `buildDistributionCurve` (see that
// module's header for the exact line between rendering and re-deriving); the shaded band is the
// SERVED interval, verbatim; the band's own name ("80%") is computed from the SERVED levels rather
// than from a constant, so a later ladder change is additive to this component instead of silently
// mislabelling the shading.

import { buildDistributionCurve, type ServedDistribution } from "@/lib/ncaaf-curve"
import { CURVE_PARAMETRIC_NOTE, CURVE_UNAVAILABLE } from "@/lib/ncaaf-copy"

/** The drawing box. Arbitrary units — the SVG scales to its container via `viewBox`. */
const VB_W = 320
const VB_H = 96
/** Room at the top so the peak is not clipped, and at the bottom for the axis ticks. */
const PAD_TOP = 8
const PAD_BOTTOM = 16

const ACCENT = "#10b981"
const BAND = "rgba(16, 185, 129, 0.18)"
const AXIS = "#3f3f46"
const MUTED = "#71717a"
const MARKET = "#f59e0b"

const fmt1 = (n: number) => (Object.is(n, -0) ? 0 : n).toFixed(1)

/** "80%" from the SERVED levels. ⛔ Never a literal — the payload decides which interval it sent. */
export function bandLabel(loLevel: number, hiLevel: number): string {
  return `${Math.round((hiLevel - loLevel) * 100)}%`
}

export interface DistributionCurveProps {
  distribution: ServedDistribution | null | undefined
  /** Section heading, e.g. "Margin". */
  label: string
  /** One sentence saying what the axis means, from `lib/ncaaf-copy`. */
  hint: string
  /** A vertical reference the reader already understands — 0 for a margin (the win/loss boundary).
   *  ⛔ NOT a model quantity and never labelled as one. */
  zeroReference?: boolean
  /** The market's number for this quantity, drawn as a second vertical rule for comparison ONLY.
   *  Null when no line has been captured — the commonest case today (P3.1 closeout item 2). */
  marketValue?: number | null
  marketLabel?: string
  /** ⭐ This axis is honest as a BAND but not as an ORDERING on this payload — see
   *  `TOTAL_CURVE_HINT_NO_PACE`. It marks the curve for a spec and gives the hint a little more
   *  weight than a neutral caption; it does NOT withdraw or restyle the curve itself, because the
   *  range is exactly as trustworthy as it ever was. */
  undifferentiated?: boolean
  /** Distinguishes the two curves on a card for a screen reader and for a spec. */
  testId: string
}

export function DistributionCurve({
  distribution,
  label,
  hint,
  zeroReference = false,
  marketValue = null,
  marketLabel,
  undifferentiated = false,
  testId,
}: DistributionCurveProps) {
  const curve = buildDistributionCurve(distribution)

  if (curve.source === "unavailable" || curve.points.length < 2) {
    return (
      <div data-testid={testId} data-curve-source="unavailable" className="space-y-1">
        <div className="text-[10px] uppercase tracking-widest text-gray-500">{label}</div>
        <p className="text-xs text-gray-500">{CURVE_UNAVAILABLE}</p>
      </div>
    )
  }

  const xs = curve.points.map((p) => p.x)
  // The drawn window has to CONTAIN every reference we are about to draw, or a rule silently
  // renders off-canvas and the reader sees a comparison that is not there.
  const refs = [
    ...(zeroReference ? [0] : []),
    ...(marketValue != null && Number.isFinite(marketValue) ? [marketValue] : []),
  ]
  const xMin = Math.min(...xs, ...refs)
  const xMax = Math.max(...xs, ...refs)
  const span = xMax - xMin || 1
  const peak = Math.max(...curve.points.map((p) => p.density)) || 1

  const sx = (x: number) => ((x - xMin) / span) * VB_W
  const sy = (d: number) => VB_H - PAD_BOTTOM - (d / peak) * (VB_H - PAD_TOP - PAD_BOTTOM)

  const line = curve.points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(2)},${sy(p.density).toFixed(2)}`)
    .join(" ")
  const baseline = VB_H - PAD_BOTTOM
  const area = `${line} L${sx(xs[xs.length - 1]).toFixed(2)},${baseline} L${sx(xs[0]).toFixed(2)},${baseline} Z`

  // The band is SHADED between the served bounds, clipped to the drawn window. A band that ran off
  // the edge would read as "the range continues past the picture", which is the opposite of the
  // honest reading — the band is the MIDDLE of the range and the tails are what continue.
  const band = curve.band
  const bandLo = band ? Math.max(band.lo, xMin) : null
  const bandHi = band ? Math.min(band.hi, xMax) : null
  const bandName = band ? bandLabel(band.loLevel, band.hiLevel) : null

  return (
    <div
      data-testid={testId}
      data-curve-source={curve.source}
      data-curve-points={curve.points.length}
      data-undifferentiated={undifferentiated ? "true" : "false"}
      className="space-y-1"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">{label}</span>
        {band && (
          <span
            data-testid={`${testId}-band`}
            className="text-[11px] tabular-nums text-gray-300"
          >
            <span className="text-gray-500">{bandName} of outcomes</span>{" "}
            {fmt1(band.lo)} to {fmt1(band.hi)}
          </span>
        )}
      </div>

      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
        className="h-24 w-full"
        role="img"
        aria-label={`${label}: ${hint}${
          band ? ` ${bandName} of simulated outcomes fall between ${fmt1(band.lo)} and ${fmt1(band.hi)}.` : ""
        }`}
      >
        {band && bandLo != null && bandHi != null && bandHi > bandLo && (
          <rect
            data-testid={`${testId}-band-shade`}
            x={sx(bandLo)}
            y={PAD_TOP}
            width={sx(bandHi) - sx(bandLo)}
            height={baseline - PAD_TOP}
            fill={BAND}
          />
        )}
        <path d={area} fill="rgba(16,185,129,0.10)" />
        <path data-testid={`${testId}-path`} d={line} fill="none" stroke={ACCENT} strokeWidth={1.75} />
        <line x1={0} y1={baseline} x2={VB_W} y2={baseline} stroke={AXIS} strokeWidth={1} />

        {zeroReference && 0 >= xMin && 0 <= xMax && (
          <>
            <line
              data-testid={`${testId}-zero`}
              x1={sx(0)}
              y1={PAD_TOP}
              x2={sx(0)}
              y2={baseline}
              stroke={MUTED}
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <text x={sx(0) + 3} y={PAD_TOP + 8} fill={MUTED} fontSize={9}>
              even
            </text>
          </>
        )}

        {marketValue != null && Number.isFinite(marketValue) && (
          <>
            <line
              data-testid={`${testId}-market`}
              x1={sx(marketValue)}
              y1={PAD_TOP}
              x2={sx(marketValue)}
              y2={baseline}
              stroke={MARKET}
              strokeWidth={1.25}
              strokeDasharray="4 3"
            />
            <text
              x={Math.min(sx(marketValue) + 3, VB_W - 44)}
              y={VB_H - 4}
              fill={MARKET}
              fontSize={9}
            >
              {marketLabel ?? "market"}
            </text>
          </>
        )}

        {/* Axis ends, so the horizontal scale is readable without a full axis. */}
        <text x={0} y={VB_H - 4} fill={MUTED} fontSize={9}>
          {fmt1(xMin)}
        </text>
        <text x={VB_W} y={VB_H - 4} fill={MUTED} fontSize={9} textAnchor="end">
          {fmt1(xMax)}
        </text>
      </svg>

      <p
        data-testid={`${testId}-hint`}
        className={`text-[11px] leading-snug ${undifferentiated ? "text-amber-300/70" : "text-gray-500"}`}
      >
        {hint}
      </p>
      {curve.source === "parametric" && (
        <p data-testid={`${testId}-parametric-note`} className="text-[11px] leading-snug text-amber-500/80">
          {CURVE_PARAMETRIC_NOTE}
        </p>
      )}
    </div>
  )
}
