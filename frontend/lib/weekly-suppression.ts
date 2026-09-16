// NF-INC-0916 node 0 — THE WEEKLY SURFACE WITHHOLDS ITS MODEL NUMBERS.
//
// ══ WHY ══════════════════════════════════════════════════════════════════════════════════════════
//
// The weekly model's two training feeds (`stats_player_week`, `snap_counts`) have no scheduled
// ingest, so the 2026 week-1 training rows carried no stat line and `attach_labels` filled them
// with zeros under the retained-zero convention. The model therefore fitted a whole week of
// fabricated zeros, which inflates the hurdle's ZERO ATOM: the conditional-on-playing ceilings are
// roughly right and the floor is not. Population-matched against realized scoring, the served
// point runs at roughly a third of reality, and at quarterback at roughly a fifth.
//
// The manifest proves it without re-deriving anything: `input_vintage.stats_as_of` records the
// 2025 season's final week beside a `train_through` of 2026 week 1.
//
// `best_alpha = 0` — nothing is staked on this number, and that is exactly why it comes down. A
// figure we have measured at a fraction of reality does not stay on a public surface unlabelled.
//
// ══ WHAT IS WITHHELD, AND WHAT IS NOT ════════════════════════════════════════════════════════════
//
// WITHHELD — everything the defective fit produced: the weekly point, its 80% band, the band's
// bar, the rest-of-season point and band, and the paid per-stat line (it is the same substrate,
// produced by the component head of the same fit).
//
// KEPT — every fact about the week that the model did not produce: who is on a game-day roster,
// his opponent, whether he is on a bye, how many weeks of his own form exist, how many weeks are
// left, the absence counts and their served reasons, and the provenance line — which carries the
// very `stats_as_of` / `train_through` pair that names this defect, and so is more useful now than
// it has ever been.
//
// ⚠️ THE ORDERING IS WITHHELD TOO, AND THAT IS A JUDGMENT RATHER THAN A MECHANICAL CONSEQUENCE.
// The table is ordered by name within position while the numbers are down, NOT by the model's
// point. Within-position ordering probably survives the defect largely intact — but "probably
// largely" is a hedged claim, and publishing a hedged claim in the same breath as withholding the
// firm one it is derived from is not a posture this surface can defend. A ranked list with the
// numbers stripped reads as a ranking, because it is one. Reversing this is one line
// (`weeklyRowOrder`) and it is recorded as a follow-up for the operator, who may prefer the
// ordering kept.
//
// ══ THE REVERSAL ═════════════════════════════════════════════════════════════════════════════════
//
// ⭐ FLIP `WEEKLY_NUMBERS_WITHHELD` TO `false`. Nothing else moves: every call site reads it, and
// the un-withheld branch of `weeklyRowView` returns the payload's own values verbatim, which is
// precisely the behaviour this page had before. There is no second implementation to keep in step.
//
// ⛔ DELIBERATELY NOT AN ENVIRONMENT VARIABLE. A Vercel env change does not change git, so a plain
// Redeploy re-diffs the same commit, `vercel.json`'s `ignoreCommand` skips the build, and the new
// value silently never takes effect (`docs/vercel_build_skipping.md`). A constant in this file
// ships through the ordinary `frontend/` path that auto-deploys, which is the one mechanism here
// that cannot fail quietly.

import type { NflWeeklyPlayer } from "@/lib/nfl-weekly"

/**
 * ⭐⭐ THE ONE LINE THE REVERSAL FLIPS.
 *
 * `true` while NF-INC-0916's retrain is outstanding. The operator flips it to `false` after
 * reading node 3's measured before/after table — un-suppression is that decision's outcome, not
 * an automatic consequence of a republish, which is why nothing here reads the manifest.
 */
export const WEEKLY_NUMBERS_WITHHELD = true

/**
 * The day the withholding began, rendered in the notice.
 *
 * A dated statement is falsifiable — a reader can tell a notice that went up this morning from one
 * that has been sitting there a month. An undated "we are working on it" is the euphemism this
 * notice exists not to be.
 */
export const WEEKLY_WITHHELD_SINCE = "2026-09-16"

/** What one number cell shows. THREE states, and collapsing any two of them is the specific error
 *  this surface is built not to make (NF-C6b/NF-K1: a "nothing here" that means several things
 *  costs an investigation every time it recurs).
 *
 *  - `value`   — the model's own number.
 *  - `absent`  — a DECLARED null. The season's final week has no remaining horizon to sum, so its
 *                rest-of-season figure is genuinely not a number. Renders as an em-dash.
 *  - `withheld`— we have a number and are not showing it. A different fact from both of the above,
 *                and it must not borrow either one's rendering. */
export type WeeklyCell =
  | { kind: "value"; n: number }
  | { kind: "absent" }
  | { kind: "withheld" }

/** What a row may draw. Consumed by `weekly-page.tsx`; there is no parallel copy of this logic. */
export interface WeeklyRowView {
  point: WeeklyCell
  p10: WeeklyCell
  p90: WeeklyCell
  ros: WeeklyCell
  rosP10: WeeklyCell
  rosP90: WeeklyCell
  /** Whether the interval bar may be drawn. It is a rendering of p10/point/p90 and so is withheld
   *  with them — a bar without its numbers would still publish the shape of the distribution. */
  band: boolean
  /** Whether the paid per-stat panel may be drawn. Same fit, same defect. */
  statLine: boolean
}

const cell = (n: number | null | undefined): WeeklyCell =>
  n == null ? { kind: "absent" } : { kind: "value", n }

const WITHHELD: WeeklyCell = { kind: "withheld" }

/**
 * The row, as the page may render it.
 *
 * ⭐ ONE OWNER. The page calls this and renders what it returns; it does not decide again. That is
 * what makes the rendered assertions in `weekly-projections.spec.ts` (which exercise the shipping,
 * withheld branch) and the pure assertions on this function (which exercise BOTH branches) compose
 * into coverage of the reversal — rather than each proving something about a different decision.
 *
 * ⚠️ `withheld` IS A PARAMETER, not a read of the constant, and that is the whole point: a function
 * whose branch is baked in can only ever be tested one way, which is how a reversal ships broken.
 */
export function weeklyRowView(p: NflWeeklyPlayer, withheld: boolean): WeeklyRowView {
  if (withheld) {
    return {
      point: WITHHELD,
      p10: WITHHELD,
      p90: WITHHELD,
      ros: WITHHELD,
      rosP10: WITHHELD,
      rosP90: WITHHELD,
      band: false,
      statLine: false,
    }
  }
  return {
    point: cell(p.fpPpr),
    p10: cell(p.fpP10),
    p90: cell(p.fpP90),
    ros: cell(p.rosPpr),
    rosP10: cell(p.rosP10),
    rosP90: cell(p.rosP90),
    band: true,
    statLine: true,
  }
}

/**
 * The table's order.
 *
 * While the numbers are withheld this is position, then name — carrying no model quantity at all.
 * Restored to `byWeeklyPoints` by the same flag, so the reversal does not have to remember it.
 *
 * ⚠️ Ties break on `id` in BOTH branches so the order is stable across renders rather than
 * depending on the payload's incidental array order.
 */
export function weeklyRowOrder(
  withheld: boolean,
  byPoints: (a: NflWeeklyPlayer, b: NflWeeklyPlayer) => number,
): (a: NflWeeklyPlayer, b: NflWeeklyPlayer) => number {
  if (!withheld) return byPoints
  return (a, b) =>
    a.pos.localeCompare(b.pos) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
}
