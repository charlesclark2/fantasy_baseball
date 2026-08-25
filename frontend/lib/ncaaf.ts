"use client"

// NCAAF-P3.2 — the college-football read layer.
//
// ⚠️ THIS FILE MIRRORS A CONTRACT IT DOES NOT OWN. Every type below is the TypeScript shadow of
// `app/backend/models/ncaaf.py`, which P3.1 owns and which is the SINGLE source of truth for both
// ends of the pipe (the box writer builds against it; the router returns it). A field that exists
// here and not there is a field no server ever sends.
//
// ⛔ FRONTEND-ONLY STORY. If this surface needs a field the contract does not declare, that is a
// FLAG for P3.1/P3.3 — not an edit to the backend, and not a value derived here to stand in for
// one. Every such gap this session found is recorded in the spec's `closeout.followUps`.
//
// 📣 WHY THERE IS NO PICK, NO EDGE AND NO DELTA HERE. P1.4's CLV leg came back a clean null
// (VAL1: ATS 0.496 = placebo; the pooled CLV null stands), so `best_alpha = 0` and no stake rides
// on any of these numbers. The payload carries machine-readable honest-frame flags for exactly
// this reason — a surface can BRANCH on `market_blind` / `projection_only` rather than trusting a
// sentence someone wrote — and `assert_no_edge_claim_in_schema` REFUSES to declare a field whose
// NAME reads as a pick. Nothing in this module computes a model-minus-market difference; see
// `NcaafMarketLine`'s own docstring for why that column deliberately does not exist.
//
// 🔓 PUBLIC, SO NO TOKEN IS EVER PASSED. NCAAF is free (E9.45) and the four routes carry no
// `Depends` and read no Bearer token. `apiFetch` is called with no token argument at all — an
// absence that is the point, exactly as `cdnFetch`'s signature is (a call that cannot take a token
// cannot leak one into a shared read).

import { useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"

// ══ the contract, mirrored ═══════════════════════════════════════════════════════════════════

/** The honest-frame flags stamped on every NCAAF blob. `disclosure` is SERVED PROSE and is
 *  rendered VERBATIM — a component that paraphrased it would be writing claim copy no screening
 *  had ever looked at (the NF-TR1 discipline). */
export interface NcaafFraming {
  framing: "market_blind_projection"
  best_alpha: number
  market_blind: boolean
  projection_only: boolean
  disclosure: string
}

export interface NcaafProvenance {
  model_version: string | null
  model_form: string | null
  model_learner: string | null
  model_contract: string | null
  mean_artifact_version: string | null
  /** The P1.2 strength vintage the prediction read — a week index ON THE INPUT, never a key. */
  strength_as_of_week: number | null
  /** Whether the certified pace term ACTED. `false` at week 1 is CORRECT by construction, not a
   *  defect: week-1 team-weeks are null and a null contributes exactly 0.0 to a mean-imputed
   *  ridge. Rendered as a stated fact so "no pace" is said rather than silent. */
  pace_term_active: boolean | null
  n_draws: number | null
  snapshot_ts: string | null
  snapshot_kind: string | null
}

export interface NcaafTeamSide {
  team_id: number | null
  team: string | null
  conference: string | null
  strength_margin: number | null
  strength_margin_sd: number | null
}

/** Both sides are SERVED. ⛔ Never re-derive `away` as `1 - home`: two renderers of one number is
 *  how they drift (E9.61), and the server already did it. */
export interface NcaafWinProbability {
  home: number | null
  away: number | null
}

export interface NcaafDistribution {
  mu: number | null
  sigma: number | null
  quantile_levels: number[]
  quantiles: number[]
  interval_lo_level: number | null
  interval_hi_level: number | null
  interval_lo: number | null
  interval_hi: number | null
  interval_width: number | null
}

/** ⚠️ `status`/`reason` exist because a null market line has SEVERAL causes that must not render
 *  identically (NF-C6b). Today EVERY upcoming game is `unavailable` — the only NCAAF odds capture
 *  scheduled for 2026 is the paid `/historical` catch-up, which by construction cannot reach a
 *  kickoff until it is PAST (P3.1 closeout item 2) — so the absent branch is the one users meet. */
export interface NcaafMarketLine {
  status: "available" | "unavailable"
  reason: string | null
  source: string | null
  snapshot_ts: string | null
  /** Negative = the home team is favoured by that many points, the book's own convention. */
  home_spread: number | null
  total: number | null
  home_moneyline_american: number | null
  /** ⚠️ Includes the book's margin — it is a PRICE, not the book's belief. Labelled as such
   *  wherever it is shown beside our probability, or the comparison reads as a bigger disagreement
   *  than it is. */
  home_moneyline_implied_probability: number | null
}

export interface NcaafGamePrediction {
  game_id: number
  season: number
  /** The America/Los_Angeles kickoff day — the serving grain (INC-22). */
  game_day: string
  commence_time: string | null
  start_time_tbd: boolean | null
  season_type: string | null
  /** ⚠️ CFBD's raw week, a DISPLAY LABEL ONLY: it restarts at 1 in the postseason, so it is not an
   *  ordering and nothing may key or group on it (the `season_order_week` alias landmine). */
  cfbd_week: number | null
  is_neutral_site: boolean | null
  is_conference_game: boolean | null
  home: NcaafTeamSide
  away: NcaafTeamSide
  win_probability: NcaafWinProbability
  /** The HOME margin (home points − away points). */
  margin: NcaafDistribution
  total: NcaafDistribution
  market: NcaafMarketLine
  provenance: NcaafProvenance
  framing: NcaafFraming
}

export interface NcaafSlate {
  sport: "ncaaf"
  game_day: string
  season: number
  generated_at: string
  n_games: number
  games: NcaafGamePrediction[]
  framing: NcaafFraming
}

export interface NcaafGameDayRef {
  game_day: string
  n_games: number
}

/** What the day selector reads. ⛔ There is no week endpoint and there will not be one — see
 *  `cfbd_week` above. */
export interface NcaafManifest {
  sport: "ncaaf"
  season: number
  generated_at: string
  /** "Today" in LA terms at write time. ⚠️ NOT guaranteed to be in `game_days`: before the opener
   *  (and on any weekday) today has no slate at all, which is the surface's empty state. */
  current_game_day: string
  game_days: NcaafGameDayRef[]
  n_games_total: number
  futures_available: boolean
  provenance: NcaafProvenance
  framing: NcaafFraming
}

// ══ the reads ════════════════════════════════════════════════════════════════════════════════

export function getNcaafManifest(): Promise<NcaafManifest> {
  return apiFetch("/ncaaf/manifest")
}

export function getNcaafSlate(gameDay: string): Promise<NcaafSlate> {
  return apiFetch(`/ncaaf/games?game_day=${encodeURIComponent(gameDay)}`)
}

export function useNcaafManifest() {
  return useQuery<NcaafManifest>({
    queryKey: ["ncaaf-manifest"],
    queryFn: getNcaafManifest,
    staleTime: 5 * 60_000,
    retry: false,
  })
}

/**
 * One LA kickoff day's slate.
 *
 * ⚠️ `retry: false` IS DELIBERATE AND LOAD-BEARING. A day with nothing published answers **404**,
 * which is a normal, expected state on this surface (a Tuesday; a day past the last published
 * slate), not a fault — retrying it three times would turn the ordinary empty state into three
 * seconds of spinner before the same answer. The surface tells the two apart on `status`: a 404 is
 * "nothing is published for this day", anything else is "we could not reach the model", and they
 * render differently because they are different facts.
 */
export function useNcaafSlate(gameDay: string | null) {
  return useQuery<NcaafSlate>({
    queryKey: ["ncaaf-slate", gameDay],
    queryFn: () => getNcaafSlate(gameDay as string),
    enabled: !!gameDay,
    staleTime: 5 * 60_000,
    retry: false,
  })
}

// ══ small, shared derivations of DISPLAY state (never of model quantities) ════════════════════

/**
 * Which day the surface should open on.
 *
 * ⭐ NOT SIMPLY `current_game_day`. That field is "today in LA at write time" and is frequently a
 * day with NO slate — before the opener it is a weekday, and in season it is any non-game day. The
 * measured 2026-08-24 manifest is exactly that case: `current_game_day` is 2026-08-24 and the only
 * published day is 2026-08-29. Opening on a 404 would make a working surface look broken on most
 * days of the week.
 *
 * So: today if today has a slate, otherwise the NEXT published day, otherwise the LAST published
 * one (in the off-season there is no "next"). Null when nothing is published at all.
 */
export function defaultGameDay(manifest: NcaafManifest | undefined): string | null {
  if (!manifest) return null
  const days = manifest.game_days.map((d) => d.game_day).sort()
  if (days.length === 0) return null
  const today = manifest.current_game_day
  if (days.includes(today)) return today
  return days.find((d) => d > today) ?? days[days.length - 1]
}

/** True when this game's day has already begun relative to the manifest's "today". Used only to
 *  LABEL a day (upcoming vs past); nothing on this surface changes its numbers because of it. */
export function isPastGameDay(gameDay: string, manifest: NcaafManifest | undefined): boolean {
  return !!manifest && gameDay < manifest.current_game_day
}
