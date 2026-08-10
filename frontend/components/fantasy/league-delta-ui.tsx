"use client"

// E9.61 — THE "vs our generic board" DELTA, RENDERED. One module, three renderers.
//
// ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════════════════════════
//
// G100-C1 put the generic-vs-your-league delta on My League, and its module docstring records the
// argument for keeping it there: someone who has just configured a league is holding one question,
// and a column answers it as a footnote. That argument is about ACTIVATION and it still stands.
//
// It says nothing about the RETURNING user, who is the case E9.61 is for. Rankings and the League
// Board are where the habit lives, and a member browsing them wants the same quantity in the place
// they are already looking. So the delta now has two shapes — a headline on My League, a column on
// the browse boards — and this module is what stops those from becoming two different NUMBERS.
//
// Concretely, it owns three things that were about to be re-implemented per surface:
//   1. the LABEL (`GENERIC_DELTA_LABEL`) — see that constant for why a bare "Δ" is unsafe here;
//   2. the CHIP, so a riser is green with the same arrow on all three;
//   3. the SCALE choice, which is the part most likely to be got wrong (see `deltaOnScale`).
//
// ══ 🔒 GATING — THE CONSTRAINT THAT MATTERS ════════════════════════════════════════════════════
//
// This renders PERSONALIZATION, and Rankings is a PUBLIC route (`FantasyPublicGuard`). So the
// gating question is not "is the page gated" — it is not — but "can this component ever render for
// a caller who has no league of their own". It cannot, and the reason is structural rather than a
// check anyone has to remember:
//
//   • every caller of `<GenericDeltaBand>` / `<GenericDeltaCell>` passes a delta computed from
//     `useResolvedBoard(...).isCustom`, which is true only for a `custom:<league_id>` selection;
//   • `useFormatSelection` only admits a `custom:` value whose id is in the caller's `savedLeagues`;
//   • `useSavedLeagues` is `enabled: !!accessToken` — an anonymous visitor never has one.
//
// ⇒ anonymous ⇒ no saved leagues ⇒ no custom selection ⇒ no delta. And because the personalized
// board itself is scored IN THE BROWSER (`useCustomBoard`, off the free projections blob), adding
// this column introduces NO new endpoint and nothing new to gate server-side.
//
// ⛔ NOTHING HERE MAY JOIN THE CDN ALLOWLIST OR `_PUBLIC_CACHE_RULES`. The two reads behind it are
// already correctly classified and must stay that way: `/fantasy/nfl/board` (the free preset — the
// same bytes for everyone, cacheable) and `/fantasy/leagues` (per-caller, carries `Authorization`,
// so `cache_control_for` answers `private, no-store`). A personalized board is per-caller by
// construction; a shared cache entry for one would be the paid-data breach `cache_control_for`
// exists to prevent. Pinned by `test_e9_61_generic_delta.py`.

import Link from "next/link"
import {
  GENERIC_DELTA_BAND_DETAIL,
  GENERIC_DELTA_LABEL,
  LEAGUE_DELTA_DEFINITION,
} from "@/lib/fantasy-claim-copy"
import { MEANINGFUL_MOVE } from "@/lib/league-delta"
import type { LeagueDelta, PlayerDelta } from "@/lib/league-delta"

/** Which rank scale a surface is displaying, and therefore which delta it may show beside it.
 *
 *  ⚠️ THE TWO-SCALES TRAP, which this product has already paid for once. Rankings' ADP column needs
 *  `adpPositionRanks` for exactly this reason: on a position tab the visible rank is 1..n WITHIN the
 *  position, so putting an OVERALL move next to it silently compares two different scales and the
 *  number is simply wrong — while looking entirely normal. A board filtered to TE shows "TE4", and
 *  the move beside it has to be the move in TE. */
export type RankScale = "overall" | "position"

/** The move to render for `d` on `scale`, or null when it is undefined (see `onlyInLeague`). */
export function deltaOnScale(d: PlayerDelta | null | undefined, scale: RankScale): number | null {
  if (!d) return null
  return scale === "position" ? d.posDelta : d.ovrDelta
}

/**
 * The move chip. POSITIVE = moved UP the board, which is the sign convention `PlayerDelta.ovrDelta`
 * fixes once (rank is an inverted scale — see its docstring).
 *
 * An explicit "no change" rather than "0": a zero here means "we compared him and he did not move",
 * which is a different statement from the em-dash below it ("there was nothing to compare").
 */
export function MoveChip({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="text-gray-600">—</span>
  if (delta === 0) return <span className="text-gray-600">no change</span>
  const up = delta > 0
  return (
    <span
      className={up ? "font-medium text-[#10b981]" : "font-medium text-[#ef4444]"}
      data-testid="move-chip"
    >
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  )
}

/**
 * One board cell. Kept as a component rather than inlined per surface so the THREE states stay
 * distinguishable everywhere:
 *
 *   • "new"  — on your board, absent from the generic one (a superflex league ranking a QB the free
 *              roster shape leaves out). The move is UNDEFINED, and rendering 0 would assert that
 *              he did not move.
 *   • "—"    — not comparable at all.
 *   • a chip — a real move.
 */
export function GenericDeltaCell({
  d,
  scale,
}: {
  d: PlayerDelta | null | undefined
  scale: RankScale
}) {
  if (d?.onlyInLeague) {
    return (
      <span className="text-gray-600" title="Not ranked on our generic board">
        new
      </span>
    )
  }
  return <MoveChip delta={deltaOnScale(d, scale)} />
}

/**
 * The summary band above a personalized browse board.
 *
 * ⭐ DELIBERATELY NOT A SECOND ACTIVATION SCREEN. My League owns the risers/fallers and the
 * replacement-level explanation, and duplicating them here would both bury the board this page is
 * for and split `custom_board_viewed` — the activation event whose single fire point is what makes
 * "when did this user activate?" answerable at all (see `my-league.tsx`). So this states the count,
 * states what the column is NOT, and links to the screen that explains WHY.
 */
export function GenericDeltaBand({
  delta,
  leagueName,
}: {
  delta: LeagueDelta
  leagueName?: string | null
}) {
  return (
    <div
      className="mb-4 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4"
      data-testid="generic-delta-band"
    >
      <h2 className="text-sm font-semibold text-gray-200">
        {leagueName ? `${leagueName} vs our generic board` : "Your league vs our generic board"}
      </h2>
      {/* The denominator names its own population, for the reason `my-league` spells out: "N of 131"
          with no scope reads as a fraction of every player alive. */}
      <p className="mt-2 text-sm text-gray-300" data-testid="generic-delta-summary">
        <span className="font-semibold text-gray-100">{delta.meaningfulMoves}</span> of{" "}
        {delta.compared}{" "}
        {delta.poolSize != null
          ? "draftable QBs, RBs, WRs and TEs"
          : "ranked QBs, RBs, WRs and TEs"}{" "}
        move at least {MEANINGFUL_MOVE} places in your scoring.
      </p>
      <p className="mt-2 max-w-3xl text-xs leading-relaxed text-gray-500">
        {GENERIC_DELTA_BAND_DETAIL}
      </p>
      <p className="mt-2 text-[11px] leading-relaxed text-gray-600">{LEAGUE_DELTA_DEFINITION}</p>
      <p className="mt-2 text-[11px] text-gray-600">
        <Link href="/fantasy/my-league" className="text-gray-400 hover:text-[#10b981]">
          See what moved and why
        </Link>{" "}
        on My League.
      </p>
    </div>
  )
}

/** The column header, shared so the label and its definition can never drift apart. Rendered by the
 *  caller inside its own `<th>` so each table keeps its own alignment/width classes. */
export { GENERIC_DELTA_LABEL }
