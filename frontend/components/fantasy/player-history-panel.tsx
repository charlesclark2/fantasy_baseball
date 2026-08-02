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
import type { PlayerHistory } from "@/lib/fantasy"

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

export function PlayerHistoryPanel({ history }: { history: PlayerHistory | null | undefined }) {
  if (!history) return null
  const { pastSeasons, injuries, gamesMissedBySeason } = history
  if (pastSeasons.length === 0 && injuries.length === 0 && gamesMissedBySeason.length === 0) return null

  const missedBySeason = new Map(gamesMissedBySeason.map((g) => [g.season, g]))
  const sortedSeasons = [...pastSeasons].sort((a, b) => b.season - a.season)
  const sortedInjuries = [...injuries].sort((a, b) => (b.season - a.season) || (b.week - a.week))

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
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
            Past seasons
          </h3>
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
