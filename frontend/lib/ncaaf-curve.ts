// NCAAF-P3.2 — the SIGNATURE VIZ's arithmetic: served interval params → a drawable density curve.
//
// ══ WHAT THIS IS ALLOWED TO DO, AND WHAT IT IS NOT ════════════════════════════════════════════
//
// The P3 brand directive says margin and total are shown as DISTRIBUTIONAL CURVES, never a point
// number, and the spec's clause is "curves draw from the served interval params — client-side
// density/band from the params, NO RE-DERIVATION of model quantities".
//
// That line is exact and this module holds it:
//
//   ✅ RENDERING a curve through numbers the server sent is presentation. Every x on the curve is
//      an interpolation between two SERVED quantiles, and the curve passes through each of them.
//   ⛔ COMPUTING a model quantity is not. Nothing here produces a probability, a mean, a σ, an
//      interval, or a comparison to a market line. The 80% band the card shades is read verbatim
//      off `interval_lo`/`interval_hi` — ⛔ never `mu ± 1.2816σ`, which would be a SECOND, drifting
//      copy of a number the payload already carries (the E9.61 two-renderers class), and would
//      silently disagree with the server the moment the served predictive stopped being Gaussian.
//
// ══ WHY THE QUANTILE LADDER IS THE PRIMARY SOURCE AND μ/σ IS THE FALLBACK ══════════════════════
//
// `NcaafDistribution` serves BOTH: `mu`/`sigma` parameterise the predictive, and a seven-level
// quantile ladder is the non-parametric read of the SAME joint draw. Drawing from μ/σ would mean
// drawing a NORMAL — and the served form is whatever the registered artifact is
// (`provenance.model_form` reads `gaussian` | `student_t` | `native` | `count` |
// `strength_posterior`; today it is `strength_posterior`, and P2.5 measured a real right-skew on
// the college total). A Gaussian drawn over a skewed or fat-tailed predictive would be a picture
// of a model we do not serve, and it would visibly disagree with the band shaded beside it.
//
// The ladder is form-agnostic by construction, so it is what the curve is built from. μ/σ is used
// for exactly one thing besides the fallback: nothing. (The tails are extended from the ladder's
// OWN outermost slope — see `_extendTails` — so a form with heavy tails keeps them.)
//
// ══ THE TRANSFORM, AND WHY IT IS DONE IN z-SPACE ══════════════════════════════════════════════
//
// A density is dp/dx. Interpolating the quantile function Q(p) directly in p and differentiating
// is badly behaved near the tails, where Q is nearly vertical. Substituting z = Φ⁻¹(p) fixes it:
//
//     f(x) = dp/dx = (dp/dz) / (dx/dz) = φ(z) / Q′(z)      where x = Q(z)
//
// and a Gaussian predictive is a STRAIGHT LINE in (z, Q) with slope σ — so the interpolation has
// nothing to bend and `φ(z)/σ` comes back out exactly. A departure from normality shows up as
// curvature, which is precisely the shape we want the reader to see.
//
// Q is interpolated with a MONOTONE cubic (Fritsch–Carlson). Monotone matters twice: a quantile
// function that is not monotone is not a quantile function, and `Q′ > 0` is what keeps the density
// finite. C¹ continuity matters too — Q′ is continuous across knots, so f = φ/Q′ has no jump at a
// served quantile, which a piecewise-linear Q would give it (seven visible steps in the density).
//
// ⛔ NO SMOOTHING PASS. A kernel/rolling smooth would move the curve off the served quantiles,
// which is the one property that makes it honest to draw at all.

/** Where a curve's shape came from — surfaced so a component can LABEL a fallback rather than
 *  present it as the same thing (and so a spec can tell the two apart). */
export type CurveSource = "quantiles" | "parametric" | "unavailable"

export interface CurvePoint {
  /** The outcome value (points of margin, or points of total). */
  x: number
  /** Probability density at `x`. Absolute magnitude is not meaningful to a reader; the SHAPE is. */
  density: number
}

/** The served central interval, carried verbatim. `loLevel`/`hiLevel` come from the payload too —
 *  the card names the band ("80%") from THESE, never from a constant, so a later ladder change is
 *  additive to the client rather than a silent re-interpretation (NF-C0). */
export interface CurveBand {
  lo: number
  hi: number
  loLevel: number
  hiLevel: number
}

export interface DistributionCurve {
  source: CurveSource
  points: CurvePoint[]
  /** Null when the payload served no interval — rendered as a stated absence, never as a guess. */
  band: CurveBand | null
  /** The served median (the ladder's 0.50 knot), or null. NOT a computed centre. */
  median: number | null
  mu: number | null
  sigma: number | null
}

/** How many points the curve is drawn with. Enough that the eye reads a smooth density at card
 *  width; small enough that eight cards' worth is not a payload of its own. */
export const CURVE_RESOLUTION = 96

/** How far into the tails the curve is drawn, as probability levels.
 *
 *  ⚠️ These are DRAWING BOUNDS, not a served interval and never presented as one. They exist
 *  because a density has to stop somewhere: the served ladder ends at 0.05/0.95, and a curve that
 *  stopped there would end mid-slope with two visible cliffs. Deliberately far outside the 0.10/
 *  0.90 band the card actually quotes, so the shaded region never touches the edge of the plot. */
const TAIL_LO_LEVEL = 0.002
const TAIL_HI_LEVEL = 0.998

/** The minimum served quantiles a shape can be interpolated from. Below this the ladder cannot
 *  express curvature and the parametric fallback is the honest render. */
const MIN_LADDER_KNOTS = 3

const SQRT_2PI = Math.sqrt(2 * Math.PI)

/** The standard normal density. */
export function normalPdf(z: number): number {
  return Math.exp(-0.5 * z * z) / SQRT_2PI
}

/**
 * Φ⁻¹ — the standard normal quantile function (Acklam's rational approximation, |ε| < 1.15e-9).
 *
 * Used ONLY as the change of variable described in the module header. It is not a model quantity:
 * `invNormalCdf` never touches a served value, only the served LEVELS (0.05, 0.10, …), which are
 * fixed constants of the ladder.
 */
export function invNormalCdf(p: number): number {
  if (!(p > 0 && p < 1)) return NaN
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
             1.38357751867269e2, -3.066479806614716e1, 2.506628277459239]
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
             6.680131188771972e1, -1.328068155288572e1]
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838,
             -2.549732539343734, 4.374664141464968, 2.938163982698783]
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416]
  const pLow = 0.02425
  const pHigh = 1 - pLow
  if (p < pLow) {
    const q = Math.sqrt(-2 * Math.log(p))
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  if (p > pHigh) {
    const q = Math.sqrt(-2 * Math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  const q = p - 0.5
  const r = q * q
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
    (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

/** The subset of `NcaafDistribution` this module reads. Structural rather than an import, so the
 *  arithmetic stays testable without dragging the query layer in. */
export interface ServedDistribution {
  mu?: number | null
  sigma?: number | null
  quantile_levels?: (number | null)[] | null
  quantiles?: (number | null)[] | null
  interval_lo_level?: number | null
  interval_hi_level?: number | null
  interval_lo?: number | null
  interval_hi?: number | null
  interval_width?: number | null
}

/** The served ladder, if it is usable as a quantile function. `null` means "fall back", never
 *  "repair it": a non-monotone ladder is a payload we do not understand, and interpolating one
 *  anyway would draw a negative density. */
function ladderOf(dist: ServedDistribution): { z: number[]; q: number[] } | null {
  const levels = (dist.quantile_levels ?? []).filter(isNum)
  const values = (dist.quantiles ?? []).filter(isNum)
  if (levels.length !== (dist.quantile_levels ?? []).length) return null
  if (values.length !== (dist.quantiles ?? []).length) return null
  if (levels.length !== values.length || levels.length < MIN_LADDER_KNOTS) return null
  for (let i = 0; i < levels.length; i++) {
    if (!(levels[i] > 0 && levels[i] < 1)) return null
    if (i > 0 && !(levels[i] > levels[i - 1])) return null
    if (i > 0 && !(values[i] > values[i - 1])) return null
  }
  return { z: levels.map(invNormalCdf), q: values }
}

/**
 * Add one knot beyond each end so the curve can be drawn into the tails.
 *
 * ⭐ THE SLOPE COMES FROM THE LADDER'S OWN OUTERMOST SEGMENT, not from `sigma`. For a Gaussian the
 * two are the same number; for anything heavier-tailed the outer segment is STEEPER, and using it
 * keeps the served shape's tail instead of quietly replacing it with a normal one. That is the
 * whole reason the ladder is the primary source (module header), so the tails must not undo it.
 */
function extendTails(z: number[], q: number[]): { z: number[]; q: number[] } {
  const zLo = invNormalCdf(TAIL_LO_LEVEL)
  const zHi = invNormalCdf(TAIL_HI_LEVEL)
  const n = z.length
  const slopeLo = (q[1] - q[0]) / (z[1] - z[0])
  const slopeHi = (q[n - 1] - q[n - 2]) / (z[n - 1] - z[n - 2])
  const out = { z: [...z], q: [...q] }
  if (zLo < z[0] && slopeLo > 0) {
    out.z.unshift(zLo)
    out.q.unshift(q[0] + slopeLo * (zLo - z[0]))
  }
  if (zHi > z[n - 1] && slopeHi > 0) {
    out.z.push(zHi)
    out.q.push(q[n - 1] + slopeHi * (zHi - z[n - 1]))
  }
  return out
}

/**
 * Fritsch–Carlson monotone tangents — the standard construction, and it is load-bearing rather
 * than a style choice: an ordinary cubic spline through a quantile ladder can OVERSHOOT between
 * knots, which puts `Q′ < 0` somewhere and produces a negative density on a curve whose whole job
 * is to be an honest picture of a distribution.
 */
function monotoneTangents(xs: number[], ys: number[]): number[] {
  const n = xs.length
  const delta: number[] = []
  for (let i = 0; i < n - 1; i++) delta.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]))
  const m: number[] = new Array(n)
  m[0] = delta[0]
  m[n - 1] = delta[n - 2]
  for (let i = 1; i < n - 1; i++) {
    m[i] = delta[i - 1] * delta[i] <= 0 ? 0 : (delta[i - 1] + delta[i]) / 2
  }
  for (let i = 0; i < n - 1; i++) {
    if (delta[i] === 0) {
      m[i] = 0
      m[i + 1] = 0
      continue
    }
    const a = m[i] / delta[i]
    const b = m[i + 1] / delta[i]
    const s = a * a + b * b
    if (s > 9) {
      const t = 3 / Math.sqrt(s)
      m[i] = t * a * delta[i]
      m[i + 1] = t * b * delta[i]
    }
  }
  return m
}

/** Hermite value AND derivative on the segment containing `x`. Both are needed at every sample:
 *  the value is where the point sits, the derivative is the density. */
function hermite(xs: number[], ys: number[], m: number[], x: number): { y: number; dy: number } {
  let i = 0
  while (i < xs.length - 2 && x > xs[i + 1]) i++
  const h = xs[i + 1] - xs[i]
  const t = (x - xs[i]) / h
  const t2 = t * t
  const t3 = t2 * t
  const h00 = 2 * t3 - 3 * t2 + 1
  const h10 = t3 - 2 * t2 + t
  const h01 = -2 * t3 + 3 * t2
  const h11 = t3 - t2
  const y = h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]
  const d00 = 6 * t2 - 6 * t
  const d10 = 3 * t2 - 4 * t + 1
  const d01 = -6 * t2 + 6 * t
  const d11 = 3 * t2 - 2 * t
  const dy = (d00 * ys[i] + d01 * ys[i + 1]) / h + d10 * m[i] + d11 * m[i + 1]
  return { y, dy }
}

/** The served band, verbatim, or null. ⛔ Never reconstructed from μ/σ — see the module header. */
function bandOf(dist: ServedDistribution): CurveBand | null {
  const { interval_lo: lo, interval_hi: hi, interval_lo_level: loL, interval_hi_level: hiL } = dist
  if (!isNum(lo) || !isNum(hi) || !isNum(loL) || !isNum(hiL)) return null
  if (!(hi > lo)) return null
  return { lo, hi, loLevel: loL, hiLevel: hiL }
}

/** The served median — the ladder's own 0.50 knot. `null` when the ladder does not carry one; ⛔
 *  `mu` is NOT substituted, because a mean and a median are different numbers on a skewed
 *  predictive and labelling one as the other is the mislabelling class the repo keeps hitting. */
function medianOf(dist: ServedDistribution): number | null {
  const levels = dist.quantile_levels ?? []
  const values = dist.quantiles ?? []
  for (let i = 0; i < levels.length; i++) {
    if (levels[i] === 0.5 && isNum(values[i])) return values[i] as number
  }
  return null
}

/**
 * The curve for one served distribution.
 *
 * Returns `source: "unavailable"` with NO points when the payload carries neither a usable ladder
 * nor μ/σ. That is a rendered state, not an error: the card says a curve cannot be drawn, which is
 * a different fact from a flat one and must not look like it (NF-C6b).
 */
export function buildDistributionCurve(
  dist: ServedDistribution | null | undefined,
  resolution: number = CURVE_RESOLUTION,
): DistributionCurve {
  const empty: DistributionCurve = {
    source: "unavailable", points: [], band: null, median: null, mu: null, sigma: null,
  }
  if (!dist) return empty

  const mu = isNum(dist.mu) ? dist.mu : null
  const sigma = isNum(dist.sigma) && dist.sigma > 0 ? dist.sigma : null
  const band = bandOf(dist)
  const median = medianOf(dist)

  const ladder = ladderOf(dist)
  if (ladder) {
    const { z, q } = extendTails(ladder.z, ladder.q)
    const m = monotoneTangents(z, q)
    const zMin = z[0]
    const zMax = z[z.length - 1]
    const points: CurvePoint[] = []
    for (let i = 0; i < resolution; i++) {
      const zi = zMin + ((zMax - zMin) * i) / (resolution - 1)
      const { y, dy } = hermite(z, q, m, zi)
      if (!(dy > 0) || !Number.isFinite(y)) continue
      points.push({ x: y, density: normalPdf(zi) / dy })
    }
    if (points.length >= MIN_LADDER_KNOTS) {
      return { source: "quantiles", points, band, median, mu, sigma }
    }
  }

  // The parametric fallback: μ/σ only. Reached when the ladder is absent, short, or not monotone.
  // Labelled `parametric` so a surface can say the shape is the served PARAMETERS' normal rather
  // than the served draw's own shape.
  if (mu !== null && sigma !== null) {
    const span = 3.5
    const points: CurvePoint[] = []
    for (let i = 0; i < resolution; i++) {
      const zi = -span + (2 * span * i) / (resolution - 1)
      points.push({ x: mu + sigma * zi, density: normalPdf(zi) / sigma })
    }
    return { source: "parametric", points, band, median, mu, sigma }
  }

  return { ...empty, band, median, mu, sigma }
}

/**
 * ∫ f dx by the trapezoid rule — for GUARDS, not for the render.
 *
 * A drawable density that does not integrate to ≈1 is not a density, and this is the one property
 * that catches a sign error, a bad tangent, or an inverted axis all at once. Exported so the guard
 * asserts the shipping curve rather than a re-implementation of it (the E9.61 lesson: a second
 * copy of the arithmetic proves the two copies agree, not that either is right).
 */
export function curveArea(points: CurvePoint[]): number {
  let area = 0
  for (let i = 1; i < points.length; i++) {
    area += ((points[i].density + points[i - 1].density) / 2) * (points[i].x - points[i - 1].x)
  }
  return area
}
