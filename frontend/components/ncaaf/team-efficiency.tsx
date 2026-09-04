"use client"

// NCAAF-P3.3 — opponent-adjusted efficiency, and the trench/pace splits beside it.
//
// ⭐ ADJUSTED AND RAW ARE BOTH SHOWN, and that pairing is the substance rather than completeness.
// College football has 136 FBS teams playing ~12 games with almost no schedule overlap, so raw
// per-play numbers compare different questions: 0.25 PPA against the SEC's best defenses is a
// different achievement from 0.30 against the Sun Belt's worst. The adjusted figure is the one to
// read; showing the raw one beside it is what lets a reader see how much of a team's profile is
// its schedule.
//
// ⛔ NO RANKING. An ordering over 136 teams computed here would be a claim this page does not make,
// and a rank is the shape a reader most easily reads as a recommendation.
//
// ⚠️ TWO SERVED FLAGS CHANGE WHAT THE NUMBERS MEAN, and both are rendered rather than swallowed:
// `adjustment_applied` false means the adjusted value FELL BACK to the raw one (so the page would
// otherwise present a raw figure under an adjusted heading), and `has_reliable_adjustment` false
// means the opponents have barely played either, so the correction is mostly noise.

import {
  EFFICIENCY_ADJUSTED_COLUMN,
  EFFICIENCY_HINT,
  EFFICIENCY_LABEL,
  EFFICIENCY_NOT_ADJUSTED_NOTE,
  EFFICIENCY_RAW_COLUMN,
  EFFICIENCY_NET_LABEL,
  EFFICIENCY_ROW_DEF_PPA,
  EFFICIENCY_ROW_DEF_SUCCESS,
  EFFICIENCY_ROW_OFF_PPA,
  EFFICIENCY_ROW_OFF_SUCCESS,
  EFFICIENCY_ROW_POINTS_AGAINST,
  EFFICIENCY_ROW_POINTS_FOR,
  EFFICIENCY_SOS_LABEL,
  EFFICIENCY_UNRELIABLE_NOTE,
  PACE_LABEL,
  SPLITS_HINT,
  SPLITS_LABEL,
  SPLIT_DEF_LINE_YARDS,
  SPLIT_DEF_STUFF,
  SPLIT_EXPLOSIVE_DRIVE,
  SPLIT_EXPLOSIVENESS,
  SPLIT_FIELD_POSITION,
  SPLIT_OFF_LINE_YARDS,
  SPLIT_OFF_STUFF,
  SPLIT_PLAYS,
  SPLIT_POINTS_PER_DRIVE,
  SPLIT_POSSESSION,
  SPLIT_SCORING_OPPORTUNITY,
  SPLIT_THREE_AND_OUT,
  TRENCH_LABEL,
} from "@/lib/ncaaf-copy"
import {
  formatNumber,
  formatRate,
  formatSignedPoints,
  type NcaafTeamEfficiency,
  type NcaafTeamSplits,
} from "@/lib/ncaaf-team"
import { TeamBlockAbsence, TeamStat } from "./team-block"

/** One efficiency row: the quantity, its adjusted value, and its raw value beside it. */
function EfficiencyRow({
  testId,
  label,
  adjusted,
  raw,
}: {
  testId: string
  label: string
  adjusted: string | null
  raw: string | null
}) {
  return (
    <div
      data-testid={testId}
      // ⚠️ THREE COLUMNS, and the third is the RAW value rather than a difference. A signed
      // "adjusted minus raw" column would read as a verdict about the schedule; the two numbers
      // side by side let a reader draw that conclusion themselves, which is the whole posture of
      // this vertical (`market-comparison.tsx` refuses a difference column for the same reason).
      className="grid grid-cols-[1fr_auto_auto] items-baseline gap-x-3 border-b border-[#161616] py-1.5 last:border-b-0"
    >
      <span className="text-[11px] text-gray-500">{label}</span>
      <span
        data-testid={`${testId}-adjusted`}
        className="w-16 text-right text-xs tabular-nums text-gray-200"
      >
        {adjusted ?? "—"}
      </span>
      <span
        data-testid={`${testId}-raw`}
        className="w-16 text-right text-xs tabular-nums text-gray-500"
      >
        {raw ?? "—"}
      </span>
    </div>
  )
}

export function NcaafTeamEfficiencyBlock({ efficiency }: { efficiency: NcaafTeamEfficiency }) {
  if (efficiency.status !== "available") {
    return (
      <TeamBlockAbsence
        testId="ncaaf-team-efficiency"
        label={EFFICIENCY_LABEL}
        reason={efficiency.reason}
      />
    )
  }

  const e = efficiency
  return (
    <section
      data-testid="ncaaf-team-efficiency"
      data-block-status="available"
      className="space-y-3"
    >
      <header className="space-y-1">
        <h2 className="text-sm font-semibold text-white">{EFFICIENCY_LABEL}</h2>
        <p className="max-w-2xl text-[11px] leading-relaxed text-gray-500">{EFFICIENCY_HINT}</p>
        <p data-testid="ncaaf-efficiency-scope" className="text-[10px] text-gray-600">
          through week {e.as_of_week} · {e.games_played} game{e.games_played === 1 ? "" : "s"}
        </p>
      </header>

      {e.adjustment_applied === false && (
        <p
          data-testid="ncaaf-efficiency-not-adjusted"
          className="max-w-2xl rounded-md border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500"
        >
          {EFFICIENCY_NOT_ADJUSTED_NOTE}
        </p>
      )}
      {e.has_reliable_adjustment === false && (
        <p
          data-testid="ncaaf-efficiency-unreliable"
          className="max-w-2xl rounded-md border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500"
        >
          {EFFICIENCY_UNRELIABLE_NOTE}
        </p>
      )}

      <div className="rounded-lg border border-[#1e1e1e] px-3 py-2">
        <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 border-b border-[#242424] pb-1.5">
          <span />
          <span className="w-16 text-right text-[10px] uppercase tracking-wide text-gray-500">
            {EFFICIENCY_ADJUSTED_COLUMN}
          </span>
          <span className="w-16 text-right text-[10px] uppercase tracking-wide text-gray-600">
            {EFFICIENCY_RAW_COLUMN}
          </span>
        </div>
        <EfficiencyRow
          testId="ncaaf-efficiency-off-ppa"
          label={EFFICIENCY_ROW_OFF_PPA}
          adjusted={formatNumber(e.adj_off_ppa, 3)}
          raw={formatNumber(e.raw_off_ppa, 3)}
        />
        <EfficiencyRow
          testId="ncaaf-efficiency-def-ppa"
          label={EFFICIENCY_ROW_DEF_PPA}
          adjusted={formatNumber(e.adj_def_ppa, 3)}
          raw={formatNumber(e.raw_def_ppa, 3)}
        />
        <EfficiencyRow
          testId="ncaaf-efficiency-off-success"
          label={EFFICIENCY_ROW_OFF_SUCCESS}
          adjusted={formatRate(e.adj_off_success_rate)}
          raw={formatRate(e.raw_off_success_rate)}
        />
        <EfficiencyRow
          testId="ncaaf-efficiency-def-success"
          label={EFFICIENCY_ROW_DEF_SUCCESS}
          adjusted={formatRate(e.adj_def_success_rate)}
          raw={formatRate(e.raw_def_success_rate)}
        />
        <EfficiencyRow
          testId="ncaaf-efficiency-points-for"
          label={EFFICIENCY_ROW_POINTS_FOR}
          adjusted={formatNumber(e.adj_points_for_per_game, 1)}
          raw={formatNumber(e.raw_points_for_per_game, 1)}
        />
        <EfficiencyRow
          testId="ncaaf-efficiency-points-against"
          label={EFFICIENCY_ROW_POINTS_AGAINST}
          adjusted={formatNumber(e.adj_points_against_per_game, 1)}
          raw={formatNumber(e.raw_points_against_per_game, 1)}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <TeamStat
          testId="ncaaf-efficiency-net"
          label={EFFICIENCY_NET_LABEL}
          value={formatSignedPoints(e.adj_net_ppa, 3)}
        />
        <TeamStat
          testId="ncaaf-efficiency-sos"
          label={EFFICIENCY_SOS_LABEL}
          value={formatSignedPoints(e.sos_opponent_net_ppa, 3)}
          sub={
            e.opponents_counted === null
              ? null
              : `${e.opponents_counted} opponent${e.opponents_counted === 1 ? "" : "s"}`
          }
        />
      </div>
    </section>
  )
}

export function NcaafTeamSplitsBlock({ splits }: { splits: NcaafTeamSplits }) {
  if (splits.status !== "available") {
    return (
      <TeamBlockAbsence testId="ncaaf-team-splits" label={SPLITS_LABEL} reason={splits.reason} />
    )
  }

  const s = splits
  return (
    <section data-testid="ncaaf-team-splits" data-block-status="available" className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-sm font-semibold text-white">{SPLITS_LABEL}</h2>
        <p className="max-w-2xl text-[11px] leading-relaxed text-gray-500">{SPLITS_HINT}</p>
        <p data-testid="ncaaf-splits-scope" className="text-[10px] text-gray-600">
          through week {s.as_of_week} · {s.games_played} game{s.games_played === 1 ? "" : "s"}
        </p>
      </header>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
          {TRENCH_LABEL}
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <TeamStat
            testId="ncaaf-splits-off-line-yards"
            label={SPLIT_OFF_LINE_YARDS}
            value={formatNumber(s.off_line_yards)}
          />
          <TeamStat
            testId="ncaaf-splits-def-line-yards"
            label={SPLIT_DEF_LINE_YARDS}
            value={formatNumber(s.def_line_yards)}
          />
          <TeamStat
            testId="ncaaf-splits-off-stuff"
            label={SPLIT_OFF_STUFF}
            value={formatRate(s.off_stuff_rate)}
          />
          <TeamStat
            testId="ncaaf-splits-def-stuff"
            label={SPLIT_DEF_STUFF}
            value={formatRate(s.def_stuff_rate)}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
          {PACE_LABEL}
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <TeamStat
            testId="ncaaf-splits-plays"
            label={SPLIT_PLAYS}
            value={formatNumber(s.off_plays_per_game, 1)}
          />
          <TeamStat
            testId="ncaaf-splits-possession"
            label={SPLIT_POSSESSION}
            // ⚠️ Served in SECONDS; a raw 1997.5 beside "possession" reads as nothing at all, so it
            // is rendered as minutes — a UNIT change, never a value one.
            value={
              typeof s.possession_seconds_per_game === "number" &&
              Number.isFinite(s.possession_seconds_per_game)
                ? `${Math.floor(s.possession_seconds_per_game / 60)}m`
                : null
            }
          />
          <TeamStat
            testId="ncaaf-splits-points-per-drive"
            label={SPLIT_POINTS_PER_DRIVE}
            value={formatNumber(s.points_per_drive)}
            sub={s.drives === null ? null : `${s.drives} drives`}
          />
          <TeamStat
            testId="ncaaf-splits-three-and-out"
            label={SPLIT_THREE_AND_OUT}
            value={formatRate(s.three_and_out_rate)}
          />
          <TeamStat
            testId="ncaaf-splits-scoring-opportunity"
            label={SPLIT_SCORING_OPPORTUNITY}
            value={formatRate(s.scoring_opportunity_rate)}
          />
          <TeamStat
            testId="ncaaf-splits-explosive-drive"
            label={SPLIT_EXPLOSIVE_DRIVE}
            value={formatRate(s.explosive_drive_rate)}
          />
          <TeamStat
            testId="ncaaf-splits-field-position"
            label={SPLIT_FIELD_POSITION}
            value={formatNumber(s.avg_start_yards_to_goal, 1)}
          />
          <TeamStat
            testId="ncaaf-splits-explosiveness"
            label={SPLIT_EXPLOSIVENESS}
            value={formatNumber(s.off_explosiveness)}
          />
        </div>
      </div>
    </section>
  )
}
