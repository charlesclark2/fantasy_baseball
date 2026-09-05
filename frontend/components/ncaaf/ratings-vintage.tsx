"use client"

// NCAAF-P3.3b — WHEN the ratings on this page last took in games, and when they next will.
//
// ══ WHY THIS EXISTS ═══════════════════════════════════════════════════════════════════════════
//
// P3.3 measured the gap and #1081 fixed half of it. The rating, its band and both ranks move only
// when the P1.2 posterior is re-fit, so between fits a team can win by 26 while all four sit
// unchanged beside that win in its own schedule. Every number on the block is then correct and the
// PAGE is still misleading — because a reader reads a rating printed today as a rating computed
// today, and the footer's "built <date>" (the hourly serving write) actively encourages that.
//
// ══ WHY IT IS A COMPONENT AND NOT A SENTENCE ══════════════════════════════════════════════════
//
// ⭐ BOTH HALVES ARE DATA. A hand-written cadence line is right on the day it is written and free
// to be wrong forever after: a bye week, a cancelled opener, a cadence change — or, as it turned
// out here, a premise that was never true (#1081's own commit message states the P1.2 fit "rolls
// forward weekly"; it does not, and P3.3b measured that three independent ways). Everything below
// is read off the payload; there is no date literal in this file and a guard keeps it that way.
//
// ⛔ AND IT PROMISES NOTHING. "next update" names when the ratings are next REWRITTEN, never that
// the rewrite will MOVE them — a re-fit over a bye week produces the same number, and a stamp that
// had promised movement would be wrong through no fault of the data.
//
// 🔗 ONE OWNER, DELIBERATELY, THOUGH ONLY ONE SURFACE USES IT TODAY. `strength_margin` is rendered
// on the team page and nowhere else (measured: the game cards and futures board carry the field in
// their types and print neither). The moment a second surface prints a rating it imports THIS
// component rather than re-wording the fact — which is the whole reason it is not inlined into
// `team-strength.tsx`.

import {
  RATINGS_AS_OF_PREFIX,
  RATINGS_AS_OF_UNAVAILABLE,
  RATINGS_NEXT_UPDATE_PREFIX,
  RATINGS_NEXT_UPDATE_UNSCHEDULED,
  RATINGS_VINTAGE_HINT,
} from "@/lib/ncaaf-copy"
import { ratingsStamp, type RatingsVintageFields } from "@/lib/ncaaf-team"

export function NcaafRatingsVintage({
  strength,
}: {
  strength: RatingsVintageFields | null | undefined
}) {
  const stamp = ratingsStamp(strength)

  return (
    <div data-testid="ncaaf-ratings-vintage" className="space-y-1">
      <p
        data-testid="ncaaf-ratings-stamp"
        // ⭐ THE RAW VALUES ARE ON THE NODE so a guard can assert the rendered text came from the
        // payload rather than re-deriving the expectation itself — the NF-C4 rule (assert rendered
        // output) without letting the assertion restate the component's own arithmetic.
        data-ratings-as-of={stamp.asOf ?? ""}
        data-ratings-next-update={stamp.nextUpdate ?? ""}
        className="text-[11px] text-gray-500"
      >
        {stamp.asOf ? (
          <span data-testid="ncaaf-ratings-as-of" className="tabular-nums">
            {RATINGS_AS_OF_PREFIX} {stamp.asOf}
          </span>
        ) : (
          // ⛔ "We could not read when" — NOT the same fact as "there is no next one", and not a
          // silent gap. Rendering the two absences identically is what makes every recurrence
          // re-investigate from scratch (NF-C6b/NF-K1).
          <span data-testid="ncaaf-ratings-as-of-absent">{RATINGS_AS_OF_UNAVAILABLE}</span>
        )}
        <span aria-hidden="true"> · </span>
        {stamp.nextUpdate ? (
          <span data-testid="ncaaf-ratings-next-update" className="tabular-nums">
            {RATINGS_NEXT_UPDATE_PREFIX} {stamp.nextUpdate}
          </span>
        ) : (
          <span data-testid="ncaaf-ratings-next-update-absent">
            {RATINGS_NEXT_UPDATE_UNSCHEDULED}
          </span>
        )}
      </p>
      {/* Rendered ALWAYS, on the `STANDING_HINT` argument: a reader who meets a fresh stamp needs
          to know it is the same measurement as a stale one, or the staleness reads as a fault the
          one time they happen to see it. */}
      <p
        data-testid="ncaaf-ratings-vintage-hint"
        className="max-w-2xl text-[11px] leading-relaxed text-gray-500"
      >
        {RATINGS_VINTAGE_HINT}
      </p>
    </div>
  )
}
