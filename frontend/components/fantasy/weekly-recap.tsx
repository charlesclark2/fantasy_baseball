"use client"

// NF-WK-RC1 Phase B — THE WEEKLY RECAP + STANDINGS, on the league view.
//
// ══ WHAT MAKES THIS SURFACE DIFFERENT FROM EVERY OTHER FANTASY SCREEN ═══════════════════════════
//
// It is FACTUAL. Every number here already happened, which is why it may carry claims a projection
// may not — and why the copy is past tense throughout and never tells a reader what they ought to
// have done (spec boundary (ii): no start/sit, no "should have started", no editorialised result).
//
// ══ THE ONE THING THIS FILE MUST NOT GET WRONG (PM ruling (i), 2026-09-16) ══════════════════════
//
//   the league's published total is the STANDINGS FACT;
//   our slot breakdown is the EXPLANATION.
//
// ⛔ THEY ARE NEVER PRESENTED AS TWO ESTIMATES OF ONE NUMBER. They carry different labels, sit in
// different visual weights, and each states what it is. The ruling's own words: "a number that's
// right sometimes is harder to trust than one that's openly derived differently". When the two
// differ, the gap is disclosed ADJACENT TO THE TOTAL (the MT1 ruling-③ adjacency rule — not a
// panel, not a footnote) and SPECIFICALLY, naming the league's own captured terms.
//
// ⚠️ AND THE DISCLOSURE REQUIRES A *MEASURED* GAP, not a capturing league. That distinction cost a
// live defect: the note is keyed on `itemisationGapNote`, which the server returns as NULL when the
// captured terms did not actually move anything that week. Rendering a caveat beside two identical
// numbers spends exactly the trust the caveat exists to protect (#1155), and the PM has since made
// that binding on every disclosure the program ships. ⛔ So this file must never synthesise its own
// version of that sentence from the coverage report — if the server says null, there is no note.
//
// ══ EVERY EMPTY STATE IS A DIFFERENT FACT, AND SAYS WHICH ═════════════════════════════════════
//
// "this league's platform cannot be read" (422), "this week has not been recorded yet" (404), "no
// week has finished yet", and "this team had no opponent" are four different things. Rendering them
// identically is why the same symptom gets investigated three times (NF-C6b), so each keeps its own
// sentence — and for the two the server answers, ITS sentence is preferred over ours, because the
// server knows which platform and which week.

import { useMemo, useState } from "react"
import { useWeeklyManifest } from "@/lib/nfl-weekly"
import { completedWeekFrom, usePowerRankings, useWeeklyRecap } from "@/lib/fantasy-queries"
import { apiErrorStatus } from "@/lib/api"
import { Picker } from "@/components/ui/picker"
import type { RecapSeat, RecapTeam, WeeklyRecapPayload } from "@/lib/fantasy"
import {
  POWER_RANKINGS_PA_LABEL,
  POWER_RANKINGS_PF_LABEL,
  POWER_RANKINGS_RECORD_LABEL,
  RECAP_CAPTURED_PREFIX,
  RECAP_COMPLETENESS_LABEL,
  RECAP_HEADING,
  RECAP_ITEMISED_TOTAL_DEFINITION,
  RECAP_ITEMISED_TOTAL_LABEL,
  RECAP_NOT_RECORDED_FALLBACK,
  RECAP_PARTIAL_NOTE,
  RECAP_PLATFORM_UNAVAILABLE_FALLBACK,
  RECAP_POINT_IN_TIME_NOTE,
  RECAP_RESULT_LOST,
  RECAP_RESULT_TIED,
  RECAP_RESULT_UNAVAILABLE,
  RECAP_RESULT_UNPAIRED,
  RECAP_RESULT_WON,
  RECAP_SOURCE_DETAIL,
  RECAP_SOURCE_LABEL,
  RECAP_STANDINGS_HEADING,
  RECAP_STANDINGS_TOTAL_DEFINITION,
  RECAP_STANDINGS_TOTAL_LABEL,
  powerRankingsWeeksNote,
} from "@/lib/fantasy-claim-copy"

function pts(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toFixed(2) : "—"
}

/** One started slot. ⭐ THE PLAYER'S NAME ALWAYS RENDERS (operator request 2026-09-17 — a player
 *  started while out reads as his name and a 0). The 0 arrives from the SERVER only as the league's
 *  own published figure, labelled as such; this component never turns a missing number into one.
 *  A remaining ABSENCE (we could not match a player the league did score, or the league published
 *  no per-slot score) keeps a blank score and states its reason under the name — a 0 there would be
 *  a wrong number that looks real. */
function SeatRow({ seat }: { seat: RecapSeat }) {
  const absent = !!seat.absence
  return (
    <tr className="border-t border-white/5">
      <td className="py-1.5 pr-3 text-xs font-medium text-gray-400 whitespace-nowrap">
        {seat.slot}
      </td>
      <td className="py-1.5 pr-3 text-sm text-gray-200">
        {seat.name ? (
          <>
            <span>{seat.name}</span>
            {(seat.position || seat.team) && (
              <span className="ml-1.5 text-xs text-gray-500">
                {[seat.position, seat.team].filter(Boolean).join(" · ")}
              </span>
            )}
          </>
        ) : (
          !absent && <span>—</span>
        )}
        {absent && (
          <span className={`${seat.name ? "block " : ""}text-xs text-gray-500 italic`}>
            {seat.absence?.detail}
          </span>
        )}
      </td>
      <td className="py-1.5 pr-3 text-right text-sm tabular-nums text-gray-100">
        {absent ? "—" : pts(seat.points)}
      </td>
      {/* ⛔ PER-SEAT PROVENANCE, PLAINLY — "not a footnote" (PM disposition D2 = (C)). The D/ST seat
          carries the LEAGUE'S OWN published figure, and a reader is entitled to know which of the
          numbers in front of them we computed and which we are citing. */}
      <td className="py-1.5 text-right whitespace-nowrap">
        {seat.source && (
          <span
            className="text-[10px] uppercase tracking-wide text-gray-500"
            title={seat.sourceNote || RECAP_SOURCE_DETAIL[seat.source] || undefined}
          >
            {RECAP_SOURCE_LABEL[seat.source] ?? seat.source}
          </span>
        )}
      </td>
    </tr>
  )
}

/** The result line. Stated, never narrated — no verbs of dominance (spec boundary (ii)). */
function ResultLine({ team, recap }: { team: RecapTeam; recap: WeeklyRecapPayload }) {
  const m = recap.matchups.find((x) => x.matchupId === team.matchupId)
  if (!m) return null
  if (m.unpaired) return <p className="text-xs text-gray-500">{RECAP_RESULT_UNPAIRED}</p>
  if (m.resultUnavailable) {
    return <p className="text-xs text-gray-500">{RECAP_RESULT_UNAVAILABLE}</p>
  }
  const opponent = m.teams.find((t) => t.teamKey !== team.teamKey)
  const verdict = m.tied
    ? RECAP_RESULT_TIED
    : m.winnerTeamKey === team.teamKey
      ? RECAP_RESULT_WON
      : RECAP_RESULT_LOST
  return (
    <p className="text-xs text-gray-400">
      <span className="font-medium text-gray-300">{verdict}</span>
      {opponent ? (
        <>
          {" "}
          {pts(team.standingsTotal)}–{pts(opponent.total)} against {opponent.teamName}
        </>
      ) : null}
    </p>
  )
}

function TeamCard({ team, recap }: { team: RecapTeam; recap: WeeklyRecapPayload }) {
  return (
    <div
      className="rounded-lg border border-white/10 bg-white/[0.02] p-3"
      data-testid={`recap-team-${team.teamKey}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-gray-100">{team.teamName}</h4>
          <ResultLine team={team} recap={recap} />
        </div>

        {/* ⭐ THE TWO TOTALS, SIDE BY SIDE AND LABELLED AS DIFFERENT FACTS. The league's figure
            carries the visual weight because it is the standings fact; ours sits beside it as the
            explanation, and says so. */}
        <div className="flex shrink-0 items-start gap-4 text-right">
          <div>
            <div
              className="text-[10px] uppercase tracking-wide text-gray-500"
              title={RECAP_STANDINGS_TOTAL_DEFINITION}
            >
              {RECAP_STANDINGS_TOTAL_LABEL}
            </div>
            <div className="text-lg font-semibold tabular-nums text-gray-100">
              {pts(team.standingsTotal)}
            </div>
          </div>
          <div>
            <div
              className="text-[10px] uppercase tracking-wide text-gray-500"
              title={RECAP_ITEMISED_TOTAL_DEFINITION}
            >
              {RECAP_ITEMISED_TOTAL_LABEL}
            </div>
            <div className="text-sm tabular-nums text-gray-400">{pts(team.itemisedTotal)}</div>
          </div>
        </div>
      </div>

      {/* ⛔ ADJACENT TO THE TOTAL — directly beneath it, inside the same card, never a page-level
          panel or a footnote (MT1 ruling ③). The sentence is the SERVER'S, which names the league's
          own captured terms; a generic "totals may differ" is explicitly forbidden, and so is
          synthesising a replacement here. Null ⇒ the itemisation matched, so nothing is drawn. */}
      {recap.itemisationGapNote && (
        <p className="mt-2 border-l-2 border-amber-500/40 pl-2 text-xs text-amber-200/80">
          {recap.itemisationGapNote}
        </p>
      )}

      <table className="mt-2 w-full">
        <tbody>
          {team.seats.map((s) => (
            <SeatRow key={`${s.slot}-${s.seat}`} seat={s} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Standings({ leagueId, throughWeek }: { leagueId: string; throughWeek: number }) {
  const { data, isLoading, error } = usePowerRankings(leagueId, throughWeek)
  if (isLoading) return <p className="text-xs text-gray-500">Loading standings…</p>
  // ⚠️ A FAILED STANDINGS READ IS NOT AN EMPTY STANDINGS TABLE. Rendering nothing would say "this
  // league has no standings", which is a claim, and a false one (NF1.7(a) on a surface).
  if (error || !data) {
    return (
      <p className="text-xs text-gray-500">
        {(error as Error)?.message || "We could not load standings for this league."}
      </p>
    )
  }
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-gray-500">
              <th className="py-1 pr-2 font-medium">#</th>
              <th className="py-1 pr-2 font-medium">Team</th>
              <th className="py-1 pr-2 text-right font-medium">{POWER_RANKINGS_RECORD_LABEL}</th>
              <th className="py-1 pr-2 text-right font-medium">{POWER_RANKINGS_PF_LABEL}</th>
              <th className="py-1 text-right font-medium">{POWER_RANKINGS_PA_LABEL}</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.teamKey} className="border-t border-white/5">
                <td className="py-1.5 pr-2 text-xs tabular-nums text-gray-500">{r.rank}</td>
                <td className="py-1.5 pr-2 text-sm text-gray-200">{r.teamName}</td>
                <td className="py-1.5 pr-2 text-right text-sm tabular-nums text-gray-300">
                  {r.wins}-{r.losses}
                  {r.ties ? `-${r.ties}` : ""}
                </td>
                <td className="py-1.5 pr-2 text-right text-sm tabular-nums text-gray-300">
                  {pts(r.pointsFor)}
                </td>
                <td className="py-1.5 text-right text-sm tabular-nums text-gray-400">
                  {pts(r.pointsAgainst)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* ⭐ THE RANK'S ARITHMETIC, SERVED AND SHOWN — the spec's "no opaque composite score". A
          reader must be able to reproduce this order by hand, and the weeks note says which weeks
          are in the totals, because a week we could not read is SKIPPED rather than zeroed. */}
      <p className="mt-2 text-xs text-gray-500">{data.rankingBasis}</p>
      <p className="mt-1 text-xs text-gray-500">{powerRankingsWeeksNote(data.weeksIncluded)}</p>
      <p className="mt-1 text-xs text-gray-500">{data.standingsNote}</p>
    </div>
  )
}

export function WeeklyRecapPanel({ leagueId }: { leagueId: string | null }) {
  const { data: weeklyManifest } = useWeeklyManifest()
  const completedWeek = completedWeekFrom(weeklyManifest?.week)
  const [week, setWeek] = useState<number | null>(null)
  const shown = week ?? completedWeek
  const { data: recap, isLoading, error } = useWeeklyRecap(leagueId, shown)

  const weekOptions = useMemo(
    () =>
      completedWeek
        ? Array.from({ length: completedWeek }, (_, i) => {
            const w = completedWeek - i
            return { value: String(w), label: `Week ${w}` }
          })
        : [],
    [completedWeek],
  )

  if (!leagueId) return null

  // ⚠️ A DISTINCT STATE, NOT AN ERROR: before the season's first week finishes there is genuinely
  // nothing to recap, and saying so is different from failing to load something.
  if (!completedWeek) {
    return (
      <section className="rounded-xl border border-white/10 bg-[#0f1115] p-4">
        <h2 className="text-sm font-semibold text-gray-200">{RECAP_HEADING}</h2>
        <p className="mt-2 text-xs text-gray-500">
          No week has finished yet this season, so there is nothing to recap.
        </p>
      </section>
    )
  }

  const status = apiErrorStatus(error)

  return (
    <section className="rounded-xl border border-white/10 bg-[#0f1115] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-gray-200">{RECAP_HEADING}</h2>
        {weekOptions.length > 1 && (
          <Picker
            ariaLabel="Week"
            value={String(shown)}
            options={weekOptions}
            onValueChange={(v) => setWeek(Number(v))}
            className="h-8 text-xs"
          />
        )}
      </div>

      {isLoading && <p className="mt-2 text-xs text-gray-500">Loading week {shown}…</p>}

      {/* ⛔ THE SERVER'S OWN SENTENCE WHEREVER IT HAS ONE. A 422 names the PLATFORM and says
          STANDINGS specifically (a platform we cannot fetch has NO standings rather than
          approximate ones — PM ruling (i), amendment 2); a 404 names the WEEK. Ours are fallbacks
          for a shape the server has not been given a sentence for yet. */}
      {!isLoading && error && (
        <p className="mt-2 text-xs text-gray-400">
          {(error as Error)?.message ||
            (status === 404 ? RECAP_NOT_RECORDED_FALLBACK : RECAP_PLATFORM_UNAVAILABLE_FALLBACK)}
        </p>
      )}

      {recap && (
        <>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
            <span className="font-medium text-gray-400">
              Week {recap.week} · {RECAP_COMPLETENESS_LABEL[recap.completeness] ?? recap.completeness}
            </span>
            {recap.capturedAt && (
              <span>
                {RECAP_CAPTURED_PREFIX} {new Date(recap.capturedAt).toLocaleString()}
              </span>
            )}
          </div>
          {/* ⚠️ A PARTIAL WEEK SAYS SO BEFORE ANY NUMBER IS READ. The server's completeness gate is
              a COUNT of games, not a clock, so this is a fact about the data rather than the time. */}
          {recap.completeness !== "final" && (
            <p className="mt-2 rounded border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-200/80">
              {recap.completenessNote || RECAP_PARTIAL_NOTE}
            </p>
          )}
          <p className="mt-2 text-xs text-gray-500">{recap.standingsNote}</p>
          <p className="mt-1 text-xs text-gray-500">{RECAP_POINT_IN_TIME_NOTE}</p>

          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {recap.teams.map((t) => (
              <TeamCard key={t.teamKey} team={t} recap={recap} />
            ))}
          </div>

          <h3 className="mt-5 text-sm font-semibold text-gray-200">{RECAP_STANDINGS_HEADING}</h3>
          <div className="mt-2">
            <Standings leagueId={leagueId} throughWeek={completedWeek} />
          </div>
        </>
      )}
    </section>
  )
}
