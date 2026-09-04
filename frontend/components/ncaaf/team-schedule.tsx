"use client"

// NCAAF-P3.3 — the season's schedule and results.
//
// ⭐⭐ THE PLAYED/UPCOMING SPLIT IS THE WHOLE COMPONENT, not a detail of it. In September this page
// is mostly a list of games that have not happened, and the single most misleading thing it could
// do is render those identically to games that have. So they are in SEPARATE, HEADED groups, an
// upcoming row shows no score at all (⛔ never `0-0`, which reads as a played scoreless game), and
// the record above counts only what has been played.
//
// ⛔ NO PROJECTION HERE. What the model expects of an upcoming game lives on the game board; this
// page is what the team has done. Each row links there rather than duplicating it — which is also
// what keeps a single owner for the projection render (E9.61).
//
// 🕐 THE DAY SHOWN IS THE SERVED `game_day`, the America/Los_Angeles kickoff day — the same value
// and the same grain the game board uses. ⚠️ It is NOT the mart's `game_date`, which is the UTC
// date and files a 02:00-UTC kickoff a day late for every US timezone (INC-22); the server does
// that conversion so the two surfaces cannot disagree about when a game is.

import Link from "next/link"
import {
  SCHEDULE_CONFERENCE_TAG,
  SCHEDULE_GAME_LINK_LABEL,
  SCHEDULE_HINT,
  SCHEDULE_LABEL,
  SCHEDULE_NEUTRAL_TAG,
  SCHEDULE_NON_FBS_TAG,
  SCHEDULE_PLAYED_HEADING,
  SCHEDULE_UPCOMING_HEADING,
} from "@/lib/ncaaf-copy"
import type { NcaafTeamGame, NcaafTeamSchedule } from "@/lib/ncaaf-team"
import { TeamBlockAbsence } from "./team-block"
import { NcaafTeamLogo } from "./team-logo"

/** `2026-08-29` → `Sat 29 Aug`. ⚠️ Parsed as a plain calendar date with NO timezone applied: the
 *  served `game_day` is ALREADY the LA day, so running it through a local-time `Date` would shift
 *  it a second time for a reader east of UTC and undo the conversion the server did. */
function formatGameDay(day: string | null): string | null {
  if (!day) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day)
  if (!m) return null
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  })
}

function ScheduleRow({ game }: { game: NcaafTeamGame }) {
  const played = game.result !== null
  const tags = [
    game.is_fbs_matchup === false ? SCHEDULE_NON_FBS_TAG : null,
    game.is_neutral_site ? SCHEDULE_NEUTRAL_TAG : null,
    game.is_conference_game ? SCHEDULE_CONFERENCE_TAG : null,
  ].filter((t): t is string => t !== null)

  return (
    <li
      data-testid="ncaaf-schedule-row"
      data-game-id={game.game_id}
      data-played={played}
      data-result={game.result ?? ""}
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[#161616] py-2 last:border-b-0"
    >
      <span data-testid="ncaaf-schedule-day" className="w-24 shrink-0 text-[11px] tabular-nums text-gray-500">
        {formatGameDay(game.game_day) ?? "TBD"}
      </span>

      {/* ⚠️ The home/away marker is a WORD, not a colour or a position: a reader scanning a column
          of rows cannot infer "at" from alignment, and the distinction changes how every result
          reads. */}
      <span data-testid="ncaaf-schedule-venue" className="w-6 shrink-0 text-[11px] text-gray-600">
        {game.is_neutral_site ? "vs" : game.is_home ? "vs" : "at"}
      </span>

      <span className="flex min-w-0 items-center gap-1.5">
        <NcaafTeamLogo teamId={game.opponent_team_id} teamName={game.opponent ?? "opponent"} />
        <span data-testid="ncaaf-schedule-opponent" className="truncate text-xs text-gray-200">
          {game.opponent ?? "—"}
        </span>
      </span>

      {tags.length > 0 && (
        <span data-testid="ncaaf-schedule-tags" className="flex gap-1">
          {tags.map((t) => (
            <span
              key={t}
              className="rounded border border-[#2a2a2a] px-1 py-px text-[9px] uppercase tracking-wide text-gray-600"
            >
              {t}
            </span>
          ))}
        </span>
      )}

      <span className="ml-auto flex items-center gap-3">
        {/* ⛔ AN UPCOMING GAME RENDERS NOTHING HERE. Not a dash in a score slot, not a zero — the
            absence of the element is what distinguishes it, and a spec can read that. */}
        {played && (
          <span
            data-testid="ncaaf-schedule-score"
            className={`text-xs tabular-nums ${
              game.result === "W" ? "text-emerald-400" : game.result === "L" ? "text-red-400" : "text-gray-300"
            }`}
          >
            {game.result} {game.team_points}–{game.opponent_points}
          </span>
        )}
        <Link
          data-testid="ncaaf-schedule-game-link"
          href={`/ncaaf/games?game_day=${encodeURIComponent(game.game_day ?? "")}`}
          className="text-[10px] text-gray-600 underline decoration-dotted underline-offset-2 transition-colors hover:text-gray-400"
        >
          {SCHEDULE_GAME_LINK_LABEL}
        </Link>
      </span>
    </li>
  )
}

export function NcaafTeamScheduleBlock({ schedule }: { schedule: NcaafTeamSchedule }) {
  if (schedule.status !== "available" || schedule.games.length === 0) {
    return (
      <TeamBlockAbsence
        testId="ncaaf-team-schedule"
        label={SCHEDULE_LABEL}
        reason={schedule.reason}
      />
    )
  }

  // ⭐ THE SPLIT IS ON THE SERVED `result`, not on a date comparison against the reader's clock.
  // A client-side "is it in the past" would disagree with the server about a game in progress, and
  // would make the page's answer depend on which timezone the reader is in.
  const played = schedule.games.filter((g) => g.result !== null)
  const upcoming = schedule.games.filter((g) => g.result === null)

  return (
    <section data-testid="ncaaf-team-schedule" data-block-status="available" className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-sm font-semibold text-white">{SCHEDULE_LABEL}</h2>
        <p className="max-w-2xl text-[11px] leading-relaxed text-gray-500">{SCHEDULE_HINT}</p>
      </header>

      {played.length > 0 && (
        <section data-testid="ncaaf-schedule-played">
          <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
            {SCHEDULE_PLAYED_HEADING} ({played.length})
          </h3>
          <ul className="mt-1">
            {played.map((g) => (
              <ScheduleRow key={g.game_id} game={g} />
            ))}
          </ul>
        </section>
      )}

      {upcoming.length > 0 && (
        <section data-testid="ncaaf-schedule-upcoming">
          <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
            {SCHEDULE_UPCOMING_HEADING} ({upcoming.length})
          </h3>
          <ul className="mt-1">
            {upcoming.map((g) => (
              <ScheduleRow key={g.game_id} game={g} />
            ))}
          </ul>
        </section>
      )}
    </section>
  )
}
