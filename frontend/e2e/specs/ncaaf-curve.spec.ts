import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import {
  buildDistributionCurve,
  curveArea,
  invNormalCdf,
  CURVE_RESOLUTION,
} from "@/lib/ncaaf-curve"

/**
 * NCAAF-P3.2 — the signature viz's ARITHMETIC, exercised directly.
 *
 * ⭐ WHY A NODE SPEC AND NOT A BROWSER ONE. `ncaaf-games.spec.ts` proves the curve REACHES the DOM
 * and that the band is the served interval — properties a reader has. It cannot prove the density
 * is a density: a `<path>` renders whether or not its `d` describes anything, and every wrong curve
 * this module could produce (a sign error, an overshooting spline, an inverted axis, a tail
 * extended from the wrong slope) draws a perfectly plausible squiggle. The one statement that
 * catches all of them at once is ∫f dx, and it is not a statement about the DOM.
 *
 * This file runs in Playwright's Node runner with no `page` at all — the repo already resolves
 * `@/lib/*` from a spec (`support/api-mock.ts` imports `@/lib/league-scoring`), so the module under
 * test is the SHIPPING one rather than a copy of it. That is the E9.61 point: a second
 * implementation would prove the two agree, not that either is right.
 *
 * ⛔ THE FIXTURES ARE THE REAL PAYLOAD. Every clause below runs over the CAPTURED production slate
 * as well as over constructed shapes, so "the arithmetic is right on data we invented" is never the
 * whole claim.
 */

const SLATE = JSON.parse(
  readFileSync(join(process.cwd(), "e2e", "fixtures", "api", "ncaaf-slate-2026-08-29.json"), "utf8"),
)

/** The drawing bounds the module extends to (0.002 … 0.998). The curve is TRUNCATED there, so the
 *  integral is that much less than 1 — and the exact shortfall is the assertion: a curve that
 *  integrated to 1.0 would mean the tails were being drawn somewhere they were not, and one that
 *  integrated to 0.8 would mean mass was being lost inside the body. */
const DRAWN_MASS = 0.996
const AREA_TOL = 0.004

test("the shipping curve integrates to the mass it draws — on every real game", () => {
  expect(SLATE.games.length).toBeGreaterThan(0)
  for (const g of SLATE.games) {
    for (const key of ["margin", "total"] as const) {
      const c = buildDistributionCurve(g[key])
      expect(c.source, `${g.game_id}.${key}`).toBe("quantiles")
      expect(curveArea(c.points), `${g.game_id}.${key} area`).toBeCloseTo(DRAWN_MASS, 2)
      expect(Math.abs(curveArea(c.points) - DRAWN_MASS)).toBeLessThan(AREA_TOL)
    }
  }
})

test("the curve is a density: strictly increasing in x, never negative, never NaN", () => {
  // A monotone quantile function is what keeps Q′ > 0, and Q′ > 0 is what keeps f finite and
  // positive. An ordinary cubic spline through a seven-knot ladder can OVERSHOOT and put Q′ < 0
  // somewhere in between, which draws a negative density on a curve whose whole job is to be an
  // honest picture — hence Fritsch–Carlson, and hence this clause.
  for (const g of SLATE.games) {
    for (const key of ["margin", "total"] as const) {
      const pts = buildDistributionCurve(g[key]).points
      expect(pts.length).toBe(CURVE_RESOLUTION)
      for (let i = 0; i < pts.length; i++) {
        expect(Number.isFinite(pts[i].x) && Number.isFinite(pts[i].density)).toBe(true)
        expect(pts[i].density).toBeGreaterThan(0)
        if (i > 0) expect(pts[i].x).toBeGreaterThan(pts[i - 1].x)
      }
    }
  }
})

test("the curve passes THROUGH the served quantiles", () => {
  // ⭐ THE CLAUSE THAT MAKES "drawn from the served params, not re-derived" TESTABLE. If the curve
  // is the served ladder's own quantile function, then integrating the density up to a served
  // quantile must recover that quantile's LEVEL. A curve that had quietly become a normal fitted to
  // μ/σ would pass every other clause here and fail this one on any non-Gaussian payload.
  for (const g of SLATE.games) {
    for (const key of ["margin", "total"] as const) {
      const dist = g[key]
      const pts = buildDistributionCurve(dist, 4001).points
      for (let k = 0; k < dist.quantile_levels.length; k++) {
        const q = dist.quantiles[k]
        let mass = 0
        for (let i = 1; i < pts.length && pts[i].x <= q; i++) {
          mass += ((pts[i].density + pts[i - 1].density) / 2) * (pts[i].x - pts[i - 1].x)
        }
        // + the untruncated lower tail the drawing window omits.
        expect(mass + 0.002).toBeCloseTo(dist.quantile_levels[k], 2)
      }
    }
  }
})

test("an exactly-Gaussian ladder comes back as the exact Gaussian density", () => {
  // The strongest available check that the z-space change of variable is right: for a Gaussian
  // predictive Q(z) = μ + σz is a straight line, so f = φ(z)/σ must come back out to machine
  // precision. A tail extended from `sigma` instead of from the ladder's own outer slope, an
  // off-by-one in the Hermite derivative, or a missing φ(z) factor all break this by orders of
  // magnitude while still drawing a bell.
  const mu = 7
  const sigma = 13
  const levels = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
  const c = buildDistributionCurve({
    mu,
    sigma,
    quantile_levels: levels,
    quantiles: levels.map((p) => mu + sigma * invNormalCdf(p)),
  })
  expect(c.source).toBe("quantiles")
  for (const p of c.points) {
    const z = (p.x - mu) / sigma
    const truth = Math.exp(-0.5 * z * z) / (sigma * Math.sqrt(2 * Math.PI))
    expect(Math.abs(p.density - truth) / truth).toBeLessThan(1e-9)
  }
})

test("a heavy tail is KEPT, not replaced by a normal one", () => {
  // ⭐ THE REASON THE TAILS ARE EXTENDED FROM THE LADDER'S OWN OUTER SLOPE RATHER THAN FROM σ. The
  // served form is whatever the registered artifact is (`student_t` is one of the declared forms,
  // and P2.5 measured a real right-skew on the college total). A tail rebuilt from σ would quietly
  // replace the served shape with a Gaussian one exactly where the shape matters most.
  //
  // The ladder below is deliberately WIDER in the tails than its own interquartile range implies:
  // a σ-extended tail would stop far short of where the ladder's outer slope carries it.
  const levels = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
  const heavy = [-40, -22, -6, 0, 6, 22, 40]
  const sigma = 8 // deliberately far too small for those tails
  const c = buildDistributionCurve({ mu: 0, sigma, quantile_levels: levels, quantiles: heavy })
  expect(c.source).toBe("quantiles")
  const lowest = Math.min(...c.points.map((p) => p.x))
  // A normal with σ=8 reaches about −23 at the 0.002 level; the ladder's own outer slope carries
  // it far further. The assertion is the SIGN of that difference, not a magnitude.
  expect(lowest).toBeLessThan(-23 - 10)
})

test("the band is the served interval and is never reconstructed from the parameters", () => {
  // A payload carrying an interval that is NOT μ ± 1.2816σ. If the module ever recomputed the band
  // it would silently disagree with the server here, which is exactly the case a Gaussian fixture
  // could never detect.
  const levels = [0.1, 0.5, 0.9]
  const c = buildDistributionCurve({
    mu: 0,
    sigma: 10,
    quantile_levels: levels,
    quantiles: [-11, 0, 11],
    interval_lo_level: 0.1,
    interval_hi_level: 0.9,
    interval_lo: -3.25,
    interval_hi: 41.75,
  })
  expect(c.band).toEqual({ lo: -3.25, hi: 41.75, loLevel: 0.1, hiLevel: 0.9 })
})

test("the median is the served 0.50 knot and is never the mean in disguise", () => {
  // The two are different numbers on a skewed predictive, and substituting one under the other's
  // label is the mislabelling class that cost INC-41 two unequal numbers under one word.
  const c = buildDistributionCurve({
    mu: 4,
    sigma: 10,
    quantile_levels: [0.1, 0.5, 0.9],
    quantiles: [-9, 1, 20],
  })
  expect(c.median).toBe(1)
  expect(c.mu).toBe(4)
  // No 0.50 knot ⇒ no median, and ⛔ NOT μ standing in for one.
  expect(buildDistributionCurve({ mu: 4, sigma: 10, quantile_levels: [0.1, 0.9], quantiles: [-9, 20] }).median)
    .toBeNull()
})

test("the fallbacks are named rather than silently substituted", () => {
  expect(buildDistributionCurve(null).source).toBe("unavailable")
  expect(buildDistributionCurve({}).source).toBe("unavailable")
  expect(buildDistributionCurve({ mu: 3, sigma: 0 }).source).toBe("unavailable")
  expect(buildDistributionCurve({ mu: 3, sigma: 16 }).source).toBe("parametric")
  // A non-monotone ladder is a payload we do not understand. It falls BACK rather than being
  // repaired: interpolating one anyway would draw a negative density.
  expect(
    buildDistributionCurve({
      mu: 1,
      sigma: 2,
      quantile_levels: [0.1, 0.5, 0.9],
      quantiles: [5, 3, 9],
    }).source,
  ).toBe("parametric")
  // Two knots cannot express curvature, so it is not treated as a shape.
  expect(
    buildDistributionCurve({ mu: 1, sigma: 2, quantile_levels: [0.1, 0.9], quantiles: [-1, 3] }).source,
  ).toBe("parametric")
})

test("the parametric fallback is itself a density", () => {
  const c = buildDistributionCurve({ mu: -4, sigma: 16.8 })
  expect(c.source).toBe("parametric")
  // ±3.5σ, so it draws slightly more mass than the quantile branch's 0.002/0.998 window.
  expect(curveArea(c.points)).toBeGreaterThan(0.99)
  expect(curveArea(c.points)).toBeLessThanOrEqual(1)
})
