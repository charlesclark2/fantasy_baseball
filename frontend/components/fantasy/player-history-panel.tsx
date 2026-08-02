"use client"

// NF3.3 — the player-page HISTORY panel: past-season actual finish + past ADP, an injury-report
// timeline, and games-missed participation. Reads `proj.history`, which lands inside the GATED
// `/fantasy/nfl/projections` payload (see `export_player_history_json.py`) — so this panel is gated
// AT THE DATA LAYER: `EntitledPlayerView` is the only caller, and `PublicPlayerView` never fetches
// this payload at all (it has its own, separately-sourced "Past-season track record" table built
// from the PUBLIC track-record endpoints — see `player-page.tsx`'s `PublicPlayerView`). Nothing here
// hardcodes an entitlement check; the gate is "does this player object have a `history` key."
//
// 🔒 HONEST (best_alpha=0): every number here is REALIZED history, never a forward-looking claim.
// `gamesMissed` counts a game not played for ANY reason (injury, healthy scratch, roster move) — it
// is never asserted to be injury-caused; the weekly report below is the only place a specific injury
// is named, and only when nflverse's feed actually reported one.

import { FadeBadge, FadeLegend, GLOSSARY, InfoTip, num, int } from "@/components/fantasy/shared"
import type { PastSeasonRecord, PlayerHistory } from "@/lib/fantasy"

/** Weekly report status -> badge color. Unrecognized/null status (a practice-only entry with no
 *  game-report designation) falls to the neutral style rather than being hidden — an entry the
 *  feed carries is real information even without a report_status. */
function statusStyle(status: string | null): string {
  const s = (status ?? "").toLowerCase()
  if (s === "out") return "border-rose-500/40 bg-rose-500/10 text-rose-400"
  if (s === "doubtful") return "border-amber-500/40 bg-amber-500/10 text-amber-500"
  if (s === "questionable") return "border-amber-400/30 bg-amber-400/10 text-amber-300"
  return "border-[#333] bg-[#1a1a1a] text-gray-400"
}

function StatusBadge({ status }: { status: string | null }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${statusStyle(status)}`}>
      {status ?? "Practice report"}
    </span>
  )
}

/** A season's points PER GAME — pure display arithmetic on numbers the payload already carries
 *  (`actualPoints` / `gamesPlayed`), so this needs no export/backend change. Null when
 *  `gamesPlayed` is missing or 0 (an export from before NF3.3, or — in principle — a scored season
 *  with no games, which `player_track_record_frame`'s own >=6-games filter should already exclude,
 *  but this stays defensive rather than dividing by zero). */
function ptsPerGame(r: PastSeasonRecord): number | null {
  if (r.gamesPlayed == null || r.gamesPlayed <= 0) return null
  return r.actualPoints / r.gamesPlayed
}

const MIN_SEASONS_FOR_CONSISTENCY = 3

type ConsistencyLabel = "Steady" | "Somewhat variable" | "Boom-or-bust"

/** How much this player's points-PER-GAME have swung season to season — see GLOSSARY.consistency
 *  for the full plain-language explanation shown to the user. Deliberately a RATE (points per game
 *  he actually played), never a season total: a season cut short by injury would otherwise read as
 *  a "down year" for scoring level when his per-game output may have been unchanged — that
 *  confound (availability, not performance) is exactly what the Games/missed column beside this
 *  already covers, so this metric stays about performance alone. Requires >= 3 qualifying seasons
 *  (gamesPlayed > 0) — a read on 1-2 seasons is not a meaningful statement about consistency, so
 *  this returns null (renders nothing) rather than a shaky badge. Coefficient of variation
 *  (sample stddev / mean) is the standard scale-free way to compare variability across players
 *  whose average output differs wildly (a QB and a kicker are not on the same points scale). */
function seasonConsistency(pastSeasons: PastSeasonRecord[]): { label: ConsistencyLabel; nSeasons: number } | null {
  const rates = pastSeasons.map(ptsPerGame).filter((r): r is number => r != null && r > 0)
  if (rates.length < MIN_SEASONS_FOR_CONSISTENCY) return null
  const mean = rates.reduce((a, b) => a + b, 0) / rates.length
  const variance = rates.reduce((sum, r) => sum + (r - mean) ** 2, 0) / (rates.length - 1)
  const cv = Math.sqrt(variance) / mean
  const label: ConsistencyLabel = cv < 0.2 ? "Steady" : cv < 0.4 ? "Somewhat variable" : "Boom-or-bust"
  return { label, nSeasons: rates.length }
}

const CONSISTENCY_STYLE: Record<ConsistencyLabel, string> = {
  Steady: "border-[#10b981]/40 bg-[#10b981]/10 text-[#10b981]",
  "Somewhat variable": "border-amber-500/40 bg-amber-500/10 text-amber-500",
  "Boom-or-bust": "border-rose-500/40 bg-rose-500/10 text-rose-400",
}

function ConsistencyBadge({ result }: { result: { label: ConsistencyLabel; nSeasons: number } }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-gray-500">
      <InfoTip label="Year-to-year consistency">{GLOSSARY.consistency}</InfoTip>
      <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${CONSISTENCY_STYLE[result.label]}`}>
        {result.label}
      </span>
      <span className="text-gray-600">({result.nSeasons} seasons)</span>
    </span>
  )
}

export function PlayerHistoryPanel({ history }: { history: PlayerHistory | null | undefined }) {
  if (!history) return null
  const { pastSeasons, injuries, gamesMissedBySeason } = history
  if (pastSeasons.length === 0 && injuries.length === 0 && gamesMissedBySeason.length === 0) return null

  const missedBySeason = new Map(gamesMissedBySeason.map((g) => [g.season, g]))
  const sortedSeasons = [...pastSeasons].sort((a, b) => b.season - a.season)
  const sortedInjuries = [...injuries].sort((a, b) => (b.season - a.season) || (b.week - a.week))
  const consistency = seasonConsistency(pastSeasons)

  return (
    <section className="mb-6">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
        Player history
      </h2>
      <p className="mb-3 text-[11px] leading-relaxed text-gray-500">
        Descriptive history only — past-season finishes, past draft position, and reported injuries.
        None of this is a forward-looking claim about this season.
      </p>

      {/* Past-season actual vs ADP */}
      {sortedSeasons.length > 0 && (
        <div className="mb-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
              Past seasons
            </h3>
            {consistency && <ConsistencyBadge result={consistency} />}
          </div>
          {sortedSeasons.some((r) => r.isFade) && (
            <div className="mb-2">
              <FadeLegend />
            </div>
          )}
          <div className="overflow-x-auto rounded-lg border border-[#262626] bg-[#0f0f0f]">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#262626] text-[10px] uppercase tracking-wider text-gray-500">
                  <th className="px-3 py-2">Season</th>
                  <th className="px-3 py-2 text-right">Our rank</th>
                  <th className="px-3 py-2 text-right">
                    <InfoTip label="ADP rank">{GLOSSARY.adp}</InfoTip>
                  </th>
                  <th className="px-3 py-2 text-right">Actual rank</th>
                  <th className="px-3 py-2 text-right">Actual pts</th>
                  <th className="px-3 py-2 text-right">Pts/G</th>
                  <th className="px-3 py-2 text-right">Games</th>
                  <th className="px-3 py-2">
                    <InfoTip label="Fade">{GLOSSARY.fade}</InfoTip>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedSeasons.map((r) => {
                  const missed = missedBySeason.get(r.season)
                  return (
                    <tr key={r.season} className="border-b border-[#1a1a1a] last:border-0">
                      <td className="px-3 py-2 text-gray-200">{r.season}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">{r.ourRank}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">
                        {int(r.adpRank)}
                        {r.adpSource && <span className="ml-1 text-[10px] text-gray-600">({r.adpSource})</span>}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">{r.actualRank}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-400">{num(r.actualPoints)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-400">{num(ptsPerGame(r))}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-500">
                        {r.gamesPlayed ?? "—"}
                        {missed != null && (
                          <span className="ml-1 text-[10px] text-gray-600">
                            ({missed.gamesMissed} missed)
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <FadeBadge isFade={r.isFade} fadeResult={r.fadeResult} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Injury-report timeline */}
      {sortedInjuries.length > 0 && (
        <div>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
            Injury report log
          </h3>
          <p className="mb-2 text-[11px] leading-relaxed text-gray-600">
            Every weekly game-report / practice-participation entry on file, most recent first.
            Reflects what was reported that week — not a diagnosis and not a prediction.
          </p>
          <ul className="max-h-72 space-y-1.5 overflow-y-auto rounded-lg border border-[#262626] bg-[#0f0f0f] p-3">
            {sortedInjuries.map((r, i) => (
              <li
                key={`${r.season}-${r.week}-${i}`}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-[#1a1a1a] pb-1.5 text-xs last:border-0 last:pb-0"
              >
                <span className="w-20 flex-shrink-0 text-gray-500">
                  {r.season} wk {r.week}
                </span>
                <StatusBadge status={r.reportStatus} />
                {r.reportPrimaryInjury && <span className="text-gray-400">{r.reportPrimaryInjury}</span>}
                {r.practiceStatus && (
                  <span className="text-[10px] text-gray-600">· {r.practiceStatus}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
