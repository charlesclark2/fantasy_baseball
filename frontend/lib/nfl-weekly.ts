"use client"

// NF-WK-FE1 — the WEEKLY read layer: the first client of NF-C6-PH2's contract.
//
// ⚠️ THIS FILE MIRRORS A CONTRACT IT DOES NOT OWN. Every type below is the TypeScript shadow of
// `app/backend/models/nfl_weekly.py`, which NF-C6-PH2 owns and which is the SINGLE source of truth
// for both ends of the pipe (the box builder validates against it; the router returns it). A field
// that exists here and not there is a field no server ever sends.
//
// ⛔ FRONTEND-ONLY STORY. If this surface needs a field the contract does not declare, that is a
// FLAG for a backend story — not an edit to `nfl_weekly.py`, and not a value derived here to stand
// in for one. Every such gap this session found is in the spec's `closeout.followUps`.
//
// 📣 NO EDGE, NO PICK, NO DELTA — `best_alpha = 0`, stamped on the manifest's own framing block and
// walked by `assert_best_alpha_is_zero` before the artifact may be written. Nothing in this module
// computes a model-minus-market difference, and there is no market here to difference against.
//
// ⛔⛔ AND NO SCORING ARITHMETIC. The weekly point is PPR-NATIVE — the champion's own output, not a
// re-scoring of a stat line — so there is nothing here for a browser scorer to do. The repo already
// carries THREE implementations of the season scoring policy (`fantasy_engine`, the browser TS
// port, the Lambda scorer) under a merge-gating parity test; a fourth, weekly one is exactly the
// tax NF-EPIC 1 warns about, and it would also be WRONG: re-scoring an arbitrary league needs the
// per-stat line and a scorer, which is the DEFERRED gate-3 story. Everything below is display.

import { useQuery } from "@tanstack/react-query"
import { apiFetch, cdnFetch } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { canAccess } from "@/lib/entitlements"

/** The season the weekly surface reads. Mirrors `_DEFAULT_SEASON` on the router; the API defaults
 *  to the same value, so this is only ever sent to make the request self-describing. */
export const WEEKLY_SEASON = 2026

// ══ the contract, mirrored ═══════════════════════════════════════════════════════════════════

/** The positions NF-W1's champion covers. Everything else is an honest ABSENCE, never a fabricated
 *  row — mirrors `nfl_weekly.PROJECTED_POSITIONS`. */
export const WEEKLY_PROJECTED_POSITIONS = ["QB", "RB", "WR", "TE"] as const
export type WeeklyPosition = (typeof WEEKLY_PROJECTED_POSITIONS)[number]

/**
 * ⭐ EXACTLY TWO STATUSES, AND THERE IS DELIBERATELY NO THIRD.
 *
 * `"bye"` is a DETERMINISTIC zero knowable at schedule release, not a missing projection — the
 * contract emits the identity 0 at every level for it. A player we do NOT project is ABSENT from
 * `players` entirely and counted in the manifest's `absences` instead, so "missing" can never
 * arrive as a status value. A surface that invented a third state here would be re-introducing the
 * merged empty state the absence counts exist to prevent (NF-C6b/NF-K1).
 */
export type WeeklyStatus = "projected" | "bye"

export interface NflWeeklyPlayer {
  id: string
  name: string
  pos: WeeklyPosition
  team: string
  /** null on a bye. */
  opp: string | null
  /** null on a bye. */
  home: boolean | null
  status: WeeklyStatus
  /** Our number. PPR-native — the champion's own output. */
  fpPpr: number
  /** The honest 80% band. `interval_lo_level`/`interval_hi_level` on the manifest name its levels
   *  rather than leaving the client to assume them (the NCAAF-P3.3 lesson: a later ladder change is
   *  then additive on the client instead of silently relabelling a range it did not recompute). */
  fpP10: number
  fpP90: number
  /** Rest-of-season, summed over the remaining weeks on the frozen-form basis.
   *
   *  ⚠️ NULL IS A DECLARED STATE, NOT AN OMISSION — in the season's final week there is no remaining
   *  horizon to sum, which is a different fact from a ROS of zero. Nothing on the wire is serialized
   *  with `exclude_none`, so the field is always present and the null is always legible. */
  rosPpr: number | null
  rosP10: number | null
  rosP90: number | null
  /** Remaining weeks summed, byes included as identity zeros. */
  rosWeeks: number
  /** How many prior modeled weeks stand behind this row's lagged features. FREE, and served
   *  precisely because a week-1 rookie is projected from position and a rookie flag alone — a
   *  reader deserves to see the evidence base rather than infer it. */
  histWeeks: number

  // ── PAID (present only on `/weekly/projections-full`) ──
  /** The 39-level predictive quantile vector. The free band is 2 of its levels — strictly less,
   *  never a reconstruction. */
  q?: number[] | null
  passAtt?: number | null
  passYds?: number | null
  passTd?: number | null
  passInt?: number | null
  rushAtt?: number | null
  rushYds?: number | null
  rushTd?: number | null
  tgt?: number | null
  rec?: number | null
  recYds?: number | null
  recTd?: number | null
}

export interface NflWeeklyPayload {
  season: number
  week: number
  generated_at: string
  scoring_system_id: "ppr"
  players: NflWeeklyPlayer[]
}

/** A COUNT of players not projected, by machine-readable reason. `detail` is SERVED PROSE and is
 *  rendered VERBATIM — a component that paraphrased it would be writing claim copy no screening had
 *  ever looked at (the NF-TR1 discipline, and the same rule NCAAF's `disclosure` follows). */
export interface NflWeeklyAbsence {
  reason: string
  n: number
  detail: string
}

export interface NflWeeklyInputVintage {
  rosters_as_of: string | null
  schedule_as_of: string | null
  stats_as_of: string | null
  snaps_as_of: string | null
  train_through_season: number | null
  train_through_week: number | null
}

export interface NflWeeklyLineage {
  model_family: string
  target: string
  served_version: string
  base_model_version: string
  point_model_version: string
  interval_model_version: string
  /** ⭐ The component head is the champion's ADVISORY raw line and is NOT independently gated.
   *  Stamped on the wire so the claim cannot drift into "certified" by omission — which is why the
   *  stat-substrate panel reads this value rather than asserting the status in its own copy. */
  component_head_status: "advisory_ungated"
  scoring_contract_version: string | null
}

/** The posture, on the wire. Both notes are SERVED PROSE, rendered verbatim. */
export interface NflWeeklyFraming {
  best_alpha: number
  interval_note: string
  ros_interval_note: string
}

export interface NflWeeklyManifest {
  season: number
  week: number
  season_type: "REG"
  scoring_system_id: "ppr"
  generated_at: string
  /** The kickoff instant the projection is AS OF — the target week's first game. */
  projection_day: string
  interval_lo_level: number
  interval_hi_level: number
  ros_basis: "frozen_form"
  ros_sigma_lo_level: number
  ros_sigma_hi_level: number
  positions: string[]
  n_players: number
  n_by_position: Record<string, number>
  n_bye: number
  n_rookies: number
  absences: NflWeeklyAbsence[]
  pit_weeks_checked: number
  pit_records_checked: number
  pit_rows_dropped: number
  input_vintage: NflWeeklyInputVintage
  lineage: NflWeeklyLineage
  framing: NflWeeklyFraming
}

// ══ the reads ════════════════════════════════════════════════════════════════════════════════
//
// ⭐ THE `token ? apiFetch : cdnFetch` SPLIT, AND WHY THE FREE HALF NEEDS NO ENTITLEMENT IN ITS KEY.
//
// The two free handlers take NO `Request` parameter and read no entitlement at all — a handler that
// cannot see its caller cannot branch on them — so `/weekly/manifest` and `/weekly/projections` are
// BYTE-IDENTICAL for every caller by construction rather than by policy. Three things rest on that
// (the contract's own header spells them out): the CDN entry is legal, `cache_control_for`'s "same
// URL, two bodies" hazard cannot arise, and a query cache cannot strand a new subscriber on a stale
// view.
//
// ⚠️ THAT LAST ONE IS WHY THERE IS NO `entitled` DISCRIMINATOR IN THE FREE QUERY KEYS BELOW, and
// its ABSENCE is deliberate rather than an oversight. The three SEASON board hooks carry one
// because their endpoints were dual-mode: a logged-out visitor cached the locked payload, then
// subscribed, and — with `staleTime: Infinity` and `queryClient.clear()` running on sign-out only —
// kept seeing the locked view indefinitely. These endpoints cannot produce two bodies, so the same
// key across the login boundary is a cache HIT on bytes that are already correct. Copying the
// discriminator would be cargo-cult: it would cost a refetch on every login and would suggest, to
// the next reader, a caller-dependence that must not exist.
//
// ⛔ SO IF EITHER FREE ROUTE EVER VARIES BY CALLER, THIS IS ONE OF FOUR PLACES THAT MOVE TOGETHER:
// the CDN allowlist, the backend cache rules, the route's own signature, and these keys. Pinned
// server-side by `test_nf_c6_ph2_weekly_contract.py::test_the_free_weekly_url_is_byte_identical_for_every_caller`.

function weeklyQuery(season: number, week: number | null): string {
  const qs = new URLSearchParams({ season: String(season) })
  if (week != null) qs.set("week", String(week))
  return qs.toString()
}

export function getWeeklyManifest(
  token: string | null,
  season: number,
  week: number | null = null,
): Promise<NflWeeklyManifest> {
  const qs = weeklyQuery(season, week)
  if (!token) return cdnFetch(`/api/public/weekly-manifest?${qs}`)
  return apiFetch(`/fantasy/nfl/weekly/manifest?${qs}`, {}, token)
}

export function getWeeklyProjections(
  token: string | null,
  season: number,
  week: number | null = null,
): Promise<NflWeeklyPayload> {
  const qs = weeklyQuery(season, week)
  if (!token) return cdnFetch(`/api/public/weekly-projections?${qs}`)
  return apiFetch(`/fantasy/nfl/weekly/projections?${qs}`, {}, token)
}

/**
 * 🔒 THE PAID HALF — the 39-level predictive vector and the per-stat component line.
 *
 * ⚠️ ALWAYS TOKENED, NEVER THROUGH THE CDN ARM, and the asymmetry with the two fetchers above is
 * the point rather than an inconsistency. The edge route strips `Authorization` by design, so a
 * request for paid data through it would arrive at the upstream ANONYMOUS — and its 403 (or, far
 * worse, a paid body) would be pinned into a public cache entry and served to every visitor for the
 * rest of the window. `/fantasy/nfl/weekly/projections-full` is deliberately absent from the CDN
 * allowlist and must stay absent.
 *
 * Measured 2026-09-13: anonymous, this route answers **401 at the API Gateway** (`{"message":
 * "Unauthorized"}` — the gateway's shape, not FastAPI's `{"detail": …}`), i.e. the paid half is
 * refused before the Lambda is even invoked. The client gate below is therefore a second line, not
 * the line.
 */
export function getWeeklyProjectionsFull(
  token: string,
  season: number,
  week: number | null = null,
): Promise<NflWeeklyPayload> {
  return apiFetch(`/fantasy/nfl/weekly/projections-full?${weeklyQuery(season, week)}`, {}, token)
}

// ══ the hooks ════════════════════════════════════════════════════════════════════════════════
//
// ⚠️ `retry: false` ON ALL THREE, AND IT IS LOAD-BEARING RATHER THAN A PREFERENCE. A week with
// nothing published answers **404** — measured on the live API 2026-09-13, both free routes, with
// the gateway authorizer already flipped to NONE — and that is the ORDINARY state of this surface
// until the first weekly build lands, not a fault. Retrying a normal answer three times buys
// nothing but a spinner in front of an empty state the page is perfectly able to explain. The
// surface tells the two apart on `status`: a 404 is "nothing is published for this week", anything
// else is "we could not reach the model", and they render differently because they are different
// facts.

export function useWeeklyManifest(season: number = WEEKLY_SEASON, week: number | null = null) {
  const { accessToken } = useAuth()
  return useQuery<NflWeeklyManifest>({
    queryKey: ["nfl-weekly-manifest", season, week],
    queryFn: () => getWeeklyManifest(accessToken, season, week),
    staleTime: 5 * 60_000,
    retry: false,
  })
}

export function useWeeklyProjections(season: number = WEEKLY_SEASON, week: number | null = null) {
  const { accessToken } = useAuth()
  return useQuery<NflWeeklyPayload>({
    queryKey: ["nfl-weekly-projections", season, week],
    queryFn: () => getWeeklyProjections(accessToken, season, week),
    staleTime: 5 * 60_000,
    retry: false,
  })
}

/**
 * The paid detail.
 *
 * ⚠️ `enabled` IS THE ENTITLEMENT, deliberately — the same rule `useFullProjections` follows. An
 * unentitled caller must not fire a request that 401s by design on every page load; the server (and
 * here the gateway before it) is the real gate, this only avoids the noise.
 *
 * ⛔ AND `enabled` IS NOT THE RENDER GATE. The G100 lesson is that the gate is WHICH COMPONENT
 * PRINTS — #681 gated one of three renderers and looked complete — so the paid panel decides for
 * itself whether it may draw, off the same predicate, rather than inferring permission from the
 * presence of data. A hook that merely fails to fetch leaves a component free to render whatever it
 * already holds.
 */
export function useWeeklyProjectionsFull(
  season: number = WEEKLY_SEASON,
  week: number | null = null,
) {
  const { accessToken, groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  return useQuery<NflWeeklyPayload>({
    queryKey: ["nfl-weekly-projections-full", season, week],
    queryFn: () => getWeeklyProjectionsFull(accessToken as string, season, week),
    enabled: !!accessToken && entitled,
    staleTime: 5 * 60_000,
    retry: false,
  })
}

// ══ small, shared derivations of DISPLAY state (never of model quantities) ════════════════════

/**
 * The paid per-stat component fields, in the order a stat line is read.
 *
 * ⚠️ A DISPLAY ORDER, NOT A DERIVED SET. The authoritative paid set is
 * `nfl_weekly.PAID_WEEKLY_PLAYER_FIELDS`, DERIVED server-side from the scorer's own `STAT_FIELD`
 * map precisely so a new scorable component is withheld automatically rather than shipping public
 * by default. This list only decides what a panel DRAWS and in what order; it is pinned against the
 * contract by `test_nf_wk_fe1_weekly_page.py`, so a component added on the server and not here is a
 * failing test rather than a silently unrendered column.
 *
 * ⛔ NOTHING SUMS THESE. See `WEEKLY_STAT_LINE_NOTE` in `fantasy-claim-copy.ts`.
 */
export const WEEKLY_STAT_FIELDS: readonly { key: keyof NflWeeklyPlayer; label: string }[] = [
  { key: "passAtt", label: "Pass att" },
  { key: "passYds", label: "Pass yds" },
  { key: "passTd", label: "Pass TD" },
  { key: "passInt", label: "INT" },
  { key: "rushAtt", label: "Rush att" },
  { key: "rushYds", label: "Rush yds" },
  { key: "rushTd", label: "Rush TD" },
  { key: "tgt", label: "Targets" },
  { key: "rec", label: "Rec" },
  { key: "recYds", label: "Rec yds" },
  { key: "recTd", label: "Rec TD" },
] as const

/** Which stat fields are worth showing for a position — display only, and a FILTER on what the
 *  payload already carries rather than a claim about what exists. A row whose passing line is all
 *  zeros is not wrong, it is just noise on a receiver's card. */
export const WEEKLY_STATS_BY_POSITION: Record<WeeklyPosition, readonly (keyof NflWeeklyPlayer)[]> = {
  QB: ["passAtt", "passYds", "passTd", "passInt", "rushAtt", "rushYds", "rushTd"],
  RB: ["rushAtt", "rushYds", "rushTd", "tgt", "rec", "recYds", "recTd"],
  WR: ["tgt", "rec", "recYds", "recTd", "rushAtt", "rushYds", "rushTd"],
  TE: ["tgt", "rec", "recYds", "recTd"],
}

/**
 * Descending by our weekly point, ties broken on id so the order is STABLE across renders instead
 * of depending on the payload's incidental array order.
 *
 * ⭐ AN ORDERING IS A CLAIM, and this one's claim is exactly "our projected points, highest first"
 * — which is what the column header says. It is NOT a ranking of who to start: that is a decision
 * this page does not make (`best_alpha = 0`), and a bye sorts to the bottom on its own zero rather
 * than being specially demoted, because the zero IS the honest answer for that player this week.
 */
export function byWeeklyPoints(a: NflWeeklyPlayer, b: NflWeeklyPlayer): number {
  return b.fpPpr - a.fpPpr || a.id.localeCompare(b.id)
}

/** The 80% band's width, as the page shows it. Display arithmetic on two served numbers — not a
 *  model quantity, and never presented as one. */
export function bandWidth(p: Pick<NflWeeklyPlayer, "fpP10" | "fpP90">): number {
  return p.fpP90 - p.fpP10
}

/** `true` when this row's paid detail actually arrived. Used to decide whether the stat panel has
 *  anything to draw — SEPARATELY from whether the caller is entitled to see it, because "you may
 *  not see this" and "there is nothing here for this player" are different facts and the
 *  independent component head genuinely produces the second (a row can carry a points distribution
 *  and no advisory line at all). */
export function hasStatLine(p: NflWeeklyPlayer | undefined | null): boolean {
  if (!p) return false
  return WEEKLY_STAT_FIELDS.some(({ key }) => p[key] != null)
}
