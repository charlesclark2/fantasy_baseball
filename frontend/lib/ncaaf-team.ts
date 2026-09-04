"use client"

// NCAAF-P3.3 — the team stats page's read layer.
//
// ⚠️ THIS FILE MIRRORS A CONTRACT IT DOES NOT OWN, exactly as `lib/ncaaf.ts` does. Every type below
// is the TypeScript shadow of `app/backend/models/ncaaf.py`, which is the single source of truth
// for both ends of the pipe (the box writer builds against it; the router returns it). A field that
// exists here and not there is a field no server ever sends.
//
// 🔓 PUBLIC, SO NO TOKEN IS EVER PASSED. NCAAF is free (E9.45); `/ncaaf/teams/{id}` carries no
// `Depends` and reads no Bearer token. `apiFetch` is called with no token argument at all.
//
// ══ FOUR BLOCKS, FOUR AVAILABILITIES — AND THE PAGE MUST NOT COLLAPSE THEM ════════════════════
//
// The payload assembles from four independently-available sources, so a CORRECT page in early
// September has a strength rating, a full schedule, and two blocks that are structurally empty
// because the P1.1 rollups hold no rows for a season nobody has played yet. Each block carries its
// own `status` and a machine-readable `reason`, and the three causes mean different things:
//
//   no_games_played_yet             the rollup emitted this team's weeks and none has a game behind
//                                   it. The CORRECT state of week 1; nothing to do.
//   no_row_for_this_team_and_season the rollup was readable and holds nothing for this team and
//                                   season — on an in-progress season, it has not been rebuilt
//                                   that far. Measured on the wire 2026-09-03: this is what every
//                                   2026 team currently reports for efficiency and splits.
//   source_marts_unavailable        our mart build did not run. A DEFECT.
//
// A surface that rendered one blank for all three would make every recurrence re-investigate from
// scratch (NF-C6b / NF-K1), which is the whole reason the contract carries the reason at all.

import { useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import { invNormalCdf, type ServedDistribution } from "@/lib/ncaaf-curve"
import type { NcaafFraming, NcaafProvenance } from "@/lib/ncaaf"

// ══ the contract, mirrored ═══════════════════════════════════════════════════════════════════

/** ⛔ BINARY, like `market.status`. A third value would be rendered as ABSENT by every
 *  `=== "available"` test on this page — a silent wrong answer, not a missing feature, and
 *  invisible to `tsc` (a new union member type-checks fine at a `===` comparison). Staleness is
 *  expressed through each block's `as_of_week`, never through a new status. */
export type NcaafBlockStatus = "available" | "unavailable"

/** Who the team is AS OF the season being described.
 *
 * ⭐ `conference` IS POINT-IN-TIME AND THAT IS THE POINT. Eleven FBS programs changed conference
 * for 2026 — the Pac-12 rebuild took Boise State, Colorado State, Fresno State, San Diego State,
 * Utah State and Texas State; UTEP and Northern Illinois moved to the Mountain West; Louisiana Tech
 * to the Sun Belt — and Sacramento State and North Dakota State joined FBS outright. The server
 * resolves it through `dim_ncaaf_team`'s SCD-2 versions at this payload's own season, and says so
 * in `conference_source`. The page renders what it is given and never re-derives it. */
export interface NcaafTeamIdentity {
  team_id: number
  team: string | null
  season: number
  conference: string | null
  conference_division: string | null
  classification: string | null
  /** `"scd2_dim"` when resolved point-in-time; `"model_input"` when only the P1.2 row carried one. */
  conference_source: string | null
  /** ⚠️ `false` means the SCD-2 dim and the conference the posterior was POOLED under disagree —
   *  a finding about the model's inputs, not a display problem. Null when either side had none. */
  conference_matches_model_input: boolean | null
  abbreviation: string | null
  mascot: string | null
  venue_name: string | null
  venue_city: string | null
  venue_state: string | null
  /** True only for a first-year FBS program, whose pre-season covariates are absent BY
   *  CONSTRUCTION. Null when the server could not look — never fabricated as `false`. */
  is_new_to_fbs: boolean | null
}

/** One (team, week) row of the P1.2 posterior.
 *
 * 🚨 SIGN CONVENTION: `strength_offense` and `strength_defense` are BOTH higher-is-better —
 * defense is points PREVENTED. Net strength is their SUM; `strength_margin` is the number to read.
 * `offense − defense` returns approximately zero for every team in the league. */
export interface NcaafTeamStrengthWeek {
  as_of_week: number
  games_in_window: number | null
  has_sufficient_sample: boolean | null
  strength_margin: number | null
  /** ⚠️ NOT OPTIONAL DECORATION. At week 1 nothing has been played and the posterior IS the prior:
   *  the rating is real and the spread is wide (7.29 points on the live 2026 opener). A rating
   *  shown without it would publish a precision the model does not claim. */
  strength_margin_sd: number | null
  strength_conference_component: number | null
  strength_covariate_component: number | null
  strength_team_component: number | null
  strength_offense: number | null
  strength_offense_sd: number | null
  strength_defense: number | null
  strength_defense_sd: number | null
}

export interface NcaafTeamStrength {
  status: NcaafBlockStatus
  reason: string | null
  as_of_week: number | null
  current: NcaafTeamStrengthWeek | null
  weeks: NcaafTeamStrengthWeek[]
  league_base_points: number | null
  home_field_advantage: number | null
  residual_sigma: number | null
  model_version: string | null
  hyper_n_prior_seasons: number | null
}

export interface NcaafTeamEfficiency {
  status: NcaafBlockStatus
  reason: string | null
  as_of_week: number | null
  games_played: number | null
  adj_off_ppa: number | null
  adj_def_ppa: number | null
  adj_net_ppa: number | null
  adj_off_success_rate: number | null
  adj_def_success_rate: number | null
  adj_points_for_per_game: number | null
  adj_points_against_per_game: number | null
  raw_off_ppa: number | null
  raw_def_ppa: number | null
  raw_off_success_rate: number | null
  raw_def_success_rate: number | null
  raw_points_for_per_game: number | null
  raw_points_against_per_game: number | null
  sos_opponent_net_ppa: number | null
  opponents_counted: number | null
  /** False when no opponent rating existed and the adjusted value FELL BACK to the raw one. */
  adjustment_applied: boolean | null
  /** False in the first weeks, when opponents have 0–1 games and the adjustment is mostly noise. */
  has_reliable_adjustment: boolean | null
}

export interface NcaafTeamSplits {
  status: NcaafBlockStatus
  reason: string | null
  as_of_week: number | null
  games_played: number | null
  off_line_yards: number | null
  def_line_yards: number | null
  off_stuff_rate: number | null
  def_stuff_rate: number | null
  off_plays_per_game: number | null
  possession_seconds_per_game: number | null
  drives: number | null
  points_per_drive: number | null
  scoring_opportunity_rate: number | null
  three_and_out_rate: number | null
  explosive_drive_rate: number | null
  avg_start_yards_to_goal: number | null
  off_explosiveness: number | null
  def_explosiveness: number | null
}

/** One game on the season schedule — played or upcoming.
 *
 * ⛔ EVERY SCORING FIELD IS NULL ON AN UPCOMING GAME, never zero. `0-0` beside next Saturday's
 * opponent reads as a played scoreless game, which is a fabricated result. */
export interface NcaafTeamGame {
  game_id: number
  /** The America/Los_Angeles kickoff day, the same grain (and the same value) the game board uses.
   *  ⚠️ NOT the mart's own `game_date`, which is the UTC date and files a 02:00-UTC kickoff a day
   *  late for every US timezone (INC-22). */
  game_day: string | null
  commence_time: string | null
  season_type: string | null
  is_postseason: boolean | null
  is_home: boolean | null
  is_neutral_site: boolean | null
  is_conference_game: boolean | null
  /** False for a non-FBS opponent — real and common in September, and a reader needs it to read a
   *  result correctly. */
  is_fbs_matchup: boolean | null
  opponent_team_id: number | null
  opponent: string | null
  opponent_conference: string | null
  venue_name: string | null
  is_completed: boolean | null
  team_points: number | null
  opponent_points: number | null
  margin: number | null
  result: string | null
}

export interface NcaafTeamSchedule {
  status: NcaafBlockStatus
  reason: string | null
  n_games: number
  n_completed: number
  n_upcoming: number
  wins: number | null
  losses: number | null
  ties: number | null
  games: NcaafTeamGame[]
}

export interface NcaafTeamPage {
  sport: "ncaaf"
  season: number
  generated_at: string
  team: NcaafTeamIdentity
  strength: NcaafTeamStrength
  efficiency: NcaafTeamEfficiency
  splits: NcaafTeamSplits
  schedule: NcaafTeamSchedule
  provenance: NcaafProvenance
  framing: NcaafFraming
}

// ══ the read ═════════════════════════════════════════════════════════════════════════════════

export function getNcaafTeam(teamId: number | string): Promise<NcaafTeamPage> {
  return apiFetch(`/ncaaf/teams/${encodeURIComponent(String(teamId))}`)
}

/**
 * One FBS team's page.
 *
 * ⚠️ `retry: false`, for the same reason the slate query has it. A team we publish nothing for
 * answers **404**, and that is an ordinary answer on this surface (a team id that is not FBS, or a
 * season not yet written), not a fault. Retrying it three times turns the ordinary empty state into
 * three seconds of spinner before the same answer — and the page tells the two apart on `status`.
 */
export function useNcaafTeam(teamId: number | string | null) {
  return useQuery<NcaafTeamPage>({
    queryKey: ["ncaaf-team", String(teamId)],
    queryFn: () => getNcaafTeam(teamId as number | string),
    enabled: teamId !== null && teamId !== "",
    staleTime: 5 * 60_000,
    retry: false,
  })
}

// ══ display derivations — never of a model quantity ═══════════════════════════════════════════

/** The central interval level this page quotes, matching the game board's own 0.10/0.90 band. */
export const STRENGTH_BAND_LO_LEVEL = 0.1
export const STRENGTH_BAND_HI_LEVEL = 0.9

/**
 * The strength posterior as something `DistributionCurve` can draw.
 *
 * ⭐⭐ THIS IS THE ONE PLACE ON THIS PAGE THAT DERIVES A NUMBER, AND IT IS DELIBERATE — SO READ WHY
 * BEFORE COPYING THE PATTERN ANYWHERE ELSE.
 *
 * `lib/ncaaf-curve.ts` refuses to reconstruct a band from μ/σ (`bandOf`), and that rule is right:
 * on a GAME distribution the server sends a quantile ladder AND an interval computed from the
 * model's own simulated draw, so rebuilding it from two parameters would substitute a Normal
 * assumption for the shape the model actually produced — the mislabelling class this vertical keeps
 * paying for.
 *
 * The strength posterior is a DIFFERENT object. It is a partial-pooling mixed-effects posterior
 * whose served parameterisation IS `Normal(strength_margin, strength_margin_sd)` — there is no
 * ladder, no simulated draw, and no served interval, because there is no other shape to send. So
 * `margin ± z·sd` is not a substitution for a richer truth; it is the posterior's own definition
 * evaluated at a level. Nothing is being approximated away.
 *
 * ⚠️ IT IS STILL LABELLED. The curve reports `source: "parametric"` for this input and the page
 * renders a sentence saying the shape is the posterior's mean and spread — because a reader is
 * entitled to know which kind of picture they are looking at, and because the day this block does
 * gain a served interval, this function must be deleted rather than left to quietly disagree with
 * it. `invNormalCdf` is IMPORTED rather than re-written: one normal-quantile implementation on this
 * surface, not two (E9.61).
 */
export function strengthDistribution(
  week: NcaafTeamStrengthWeek | null | undefined,
): ServedDistribution | null {
  const mu = week?.strength_margin
  const sd = week?.strength_margin_sd
  if (typeof mu !== "number" || !Number.isFinite(mu)) return null
  if (typeof sd !== "number" || !Number.isFinite(sd) || sd <= 0) return null
  const z = invNormalCdf(STRENGTH_BAND_HI_LEVEL)
  return {
    mu,
    sigma: sd,
    quantile_levels: [],
    quantiles: [],
    interval_lo_level: STRENGTH_BAND_LO_LEVEL,
    interval_hi_level: STRENGTH_BAND_HI_LEVEL,
    interval_lo: mu - z * sd,
    interval_hi: mu + z * sd,
    interval_width: 2 * z * sd,
  }
}

/** A signed points figure, e.g. `+3.1` / `−1.5`.
 *
 * ⚠️ A TRUE MINUS SIGN (U+2212), not a hyphen — a hyphen beside a digit reads as a range separator
 * at small sizes, and this page shows a lot of signed numbers next to each other. */
export function formatSignedPoints(value: number | null | undefined, digits = 1): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null
  const rounded = Object.is(value, -0) ? 0 : value
  const body = Math.abs(rounded).toFixed(digits)
  return rounded < 0 ? `−${body}` : `+${body}`
}

/** A plain (unsigned) number, or null. Used where a sign would be meaningless (a rate, a count). */
export function formatNumber(value: number | null | undefined, digits = 2): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null
  return value.toFixed(digits)
}

/** A rate as a percentage, e.g. `41.9%`. */
export function formatRate(value: number | null | undefined, digits = 1): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null
  return `${(value * 100).toFixed(digits)}%`
}

/** `"9–4"`, or `null` when nothing has been played. ⛔ Never `"0–0"` for a season with no games —
 *  that reads as a played record, and the schedule block's own counts say which it is. */
export function formatRecord(schedule: NcaafTeamSchedule): string | null {
  const { wins, losses, ties, n_completed: played } = schedule
  if (!played || typeof wins !== "number" || typeof losses !== "number") return null
  const base = `${wins}–${losses}`
  return ties ? `${base}–${ties}` : base
}

/** Does this payload still describe what the page was written to describe? Re-exported from the
 *  game board's own owner so the two surfaces cannot drift on the posture check (E9.61). */
export { isMarketBlindProjection } from "@/lib/ncaaf"
