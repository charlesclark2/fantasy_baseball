"use client"

// NCAAF-P3.2 — one matchup, in the order the P3 brand directive names: PROBABILITY first, then the
// distributional CURVES, then the market beside the model as transparency.
//
// ⛔ NOTHING RANKS OR RECOMMENDS. Cards are ordered by KICKOFF TIME and by nothing else. Sorting a
// board by "biggest disagreement", "most confident" or any function of the numbers would be a
// selection — a pick expressed as an ordering — and `best_alpha = 0` (VAL1: ATS 0.496 against the
// close, indistinguishable from a placebo). There is no badge, no star and no highlight.

import { Badge } from "@/components/ui/badge"
import {
  KICKED_OFF_LABEL,
  KICKED_OFF_NOTE,
  MARGIN_CURVE_HINT,
  MARGIN_CURVE_LABEL,
  PACE_INACTIVE_NOTE,
  PROVENANCE_LABEL,
  TEAM_PAGE_STUB_LABEL,
  TOTAL_CURVE_HINT,
  TOTAL_CURVE_LABEL,
} from "@/lib/ncaaf-copy"
import type { NcaafGamePrediction } from "@/lib/ncaaf"
import { DistributionCurve } from "./distribution-curve"
import { MarketComparison } from "./market-comparison"
import { WinProbability } from "./win-probability"

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

/** A team with no name served renders as a stated placeholder, ⛔ never as a blank or as its id:
 *  "TBD" is a fact about the payload; an empty span is a fact about our rendering. */
const TEAM_TBD = "Team TBD"
const teamName = (t: { team: string | null }) => t.team?.trim() || TEAM_TBD

/** Kickoff time in the READER's own timezone.
 *
 * ⚠️ The SERVING grain is the America/Los_Angeles game-day (INC-22) and that is what the day picker
 * selects — but the TIME shown on a card is local to whoever is reading it, which is the only time
 * that answers "when can I watch this". The two are deliberately different questions and the card
 * shows the timezone abbreviation so they cannot be confused. */
function kickoffLabel(commenceTime: string | null, startTimeTbd: boolean | null): string {
  if (startTimeTbd) return "Kickoff time TBD"
  if (!commenceTime) return "Kickoff time TBD"
  const d = new Date(commenceTime)
  if (Number.isNaN(d.getTime())) return "Kickoff time TBD"
  return d.toLocaleTimeString(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  })
}

/** Has the kickoff INSTANT passed?
 *
 * ⚠️ `now` is a parameter with a default rather than a bare `Date.now()` buried in the component,
 * and that is a testability decision with teeth: the whole point of this state is what the surface
 * does on the EVENING OF A SLATE, and a component that reads the wall clock directly can only be
 * tested on a day that happens to be one. The E2E drives it with `page.clock.setFixedTime`.
 *
 * ⛔ It answers ONE question — has the clock passed the kickoff — and never "is this game over".
 * The payload carries no game state and no score (see `lib/ncaaf-copy.ts`), so any stronger reading
 * would be invented. */
export function hasKickedOff(commenceTime: string | null, now: number = Date.now()): boolean {
  if (!commenceTime) return false
  const t = Date.parse(commenceTime)
  return Number.isFinite(t) && t <= now
}

export function NcaafGameCard({ game }: { game: NcaafGamePrediction }) {
  const home = teamName(game.home)
  const away = teamName(game.away)
  const market = game.market
  const marketHomeMargin =
    market.status === "available" && isNum(market.home_spread) ? -market.home_spread : null
  const marketTotal = market.status === "available" && isNum(market.total) ? market.total : null
  const prov = game.provenance
  const started = hasKickedOff(game.commence_time)

  return (
    <article
      data-testid="ncaaf-game-card"
      data-game-id={game.game_id}
      className="flex flex-col gap-4 rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] p-4"
    >
      <header className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-500">
          <span data-testid="ncaaf-kickoff">{kickoffLabel(game.commence_time, game.start_time_tbd)}</span>
          {started && (
            <Badge
              data-testid="ncaaf-kicked-off"
              variant="outline"
              className="border-amber-900/60 px-1.5 py-0 text-[10px] text-amber-300/90"
            >
              {KICKED_OFF_LABEL}
            </Badge>
          )}
          {game.is_neutral_site && (
            <Badge variant="outline" className="border-[#2a2a2a] px-1.5 py-0 text-[10px] text-gray-400">
              Neutral site
            </Badge>
          )}
          {game.is_conference_game && (
            <Badge variant="outline" className="border-[#2a2a2a] px-1.5 py-0 text-[10px] text-gray-400">
              Conference
            </Badge>
          )}
        </div>
        <h3 className="text-sm font-medium text-white">
          <span className="text-gray-300">{away}</span>
          <span className="px-1.5 text-gray-600">at</span>
          <span className="text-gray-300">{home}</span>
        </h3>
        {started && (
          <p data-testid="ncaaf-kicked-off-note" className="text-[11px] leading-snug text-amber-300/70">
            {KICKED_OFF_NOTE}
          </p>
        )}
        {/* P3.3 is not built. ⛔ A CTA pointing at a route that does not exist is precisely the
            defect this suite exists to catch, so the affordance is present, named and INERT —
            a disabled button rather than an anchor to a 404. */}
        <button
          type="button"
          disabled
          data-testid="ncaaf-team-page-stub"
          className="cursor-not-allowed text-[11px] text-gray-600 underline decoration-dotted underline-offset-2"
          title={TEAM_PAGE_STUB_LABEL}
        >
          {TEAM_PAGE_STUB_LABEL}
        </button>
      </header>

      <WinProbability winProbability={game.win_probability} homeTeam={home} awayTeam={away} />

      <div className="grid gap-4 sm:grid-cols-2">
        <DistributionCurve
          testId="ncaaf-curve-margin"
          distribution={game.margin}
          label={MARGIN_CURVE_LABEL}
          hint={MARGIN_CURVE_HINT}
          zeroReference
          marketValue={marketHomeMargin}
          marketLabel="market"
        />
        <DistributionCurve
          testId="ncaaf-curve-total"
          distribution={game.total}
          label={TOTAL_CURVE_LABEL}
          hint={TOTAL_CURVE_HINT}
          marketValue={marketTotal}
          marketLabel="market"
        />
      </div>

      <MarketComparison game={game} />

      <details data-testid="ncaaf-provenance" className="text-[11px] text-gray-500">
        <summary className="cursor-pointer select-none text-gray-500 hover:text-gray-400">
          {PROVENANCE_LABEL}
        </summary>
        <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          <dt className="text-gray-600">Model</dt>
          <dd className="tabular-nums">{prov.model_version ?? "—"}</dd>
          <dt className="text-gray-600">Form</dt>
          <dd className="tabular-nums">{prov.model_form ?? "—"}</dd>
          <dt className="text-gray-600">Simulations</dt>
          <dd className="tabular-nums">{prov.n_draws?.toLocaleString() ?? "—"}</dd>
          <dt className="text-gray-600">Team strength as of week</dt>
          <dd className="tabular-nums">{prov.strength_as_of_week ?? "—"}</dd>
          <dt className="text-gray-600">Taken at</dt>
          <dd className="tabular-nums">{prov.snapshot_ts ?? "—"}</dd>
        </dl>
        {prov.pace_term_active === false && (
          <p data-testid="ncaaf-pace-note" className="mt-1.5 leading-snug">
            {PACE_INACTIVE_NOTE}
          </p>
        )}
      </details>
    </article>
  )
}
