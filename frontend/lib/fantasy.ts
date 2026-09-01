// Fantasy data-fetch helpers (E9.45). The NFL draft boards used to load as static
// public JSON (/data/nfl-fantasy/...), which was publicly fetchable regardless of
// entitlement. They now come from the SERVER-SIDE-GATED backend endpoints
// (/fantasy/nfl/*, require_fantasy_access → 403) so the paid gate can't be bypassed
// by hitting the raw asset URL.

import { apiFetch, cdnFetch } from "@/lib/api"
import type { BigBoardDoc, SavedBigBoard } from "@/lib/big-board"
import type { FreshnessBlock, Manifest, Player } from "@/lib/draft-optimizer"

// NF3 — the format-INDEPENDENT season projection: one row per projectable player, the raw
// season stat line plus an 80% PPR interval and the honest uncertainty metadata. This is what
// the browse Projections surface renders. The FORMAT-scored number is the league board's
// `pts`/`vor` (see `Player`), never `fpStd/fpHalf/fpPpr` — those are a one-format convenience.
export interface ProjectedPlayer {
  id: string
  name: string
  pos: string
  team: string | null
  bye: number | null
  rookie: boolean
  /** Overall draft slot for a rookie; null for veterans. */
  draftPick: number | null
  /** The model's own confidence tier: "high" | "medium" | "low". */
  conf: string | null
  /** Projected games played. */
  g: number | null
  /** NF-C9 — the WEEKLY GAME-STATUS DESIGNATION ("Out" / "Doubtful" / "Questionable"), served for
   *  DISCLOSURE ONLY. Our projected-games figure does NOT price it in: the availability discount
   *  moves on a formal roster move (IR/PUP/NFI/suspension) and on nothing else, so this channel
   *  applies no discount at all — which is exactly why it has to be said out loud beside `g`.
   *
   *  ⚠️ ABSENT ≠ NULL, and both are real (`WeeklyDesignation` renders the difference): the key is
   *  ABSENT when there is nothing to disclose (no designation, or a roster move already priced, or
   *  no feed) and NULL when the feed carries a value the build could not interpret → "unknown".
   *  ⛔ Never an input to ordering, VOR or the optimizer. */
  gameStatus?: string | null
  /** NF-INJ-NEWS-1 — the reported-absence PROVENANCE stamp: this row's projected games was lowered
   *  BY HAND, after a published report of an expected absence that no formal roster move had yet
   *  reflected. An OPERATOR JUDGMENT with a citation, never a model output and never a forecast.
   *
   *  ⚠️ ABSENT on almost every row, and absent is the meaningful state: the key is set only where a
   *  judgment ACTUALLY moved the number (a row the disjointness rule refused, because the player
   *  has since been placed on IR, carries nothing here — the formal path priced him instead). So an
   *  un-overridden player is indistinguishable from before this mechanism existed (NF-FRESH2).
   *
   *  ⛔ Never an input to ordering, VOR or the optimizer — the CAP is already in `g`, and the whole
   *  effect of the judgment reaches the board through that number. This is the receipt, not the
   *  adjustment. */
  reportedAbsence?: { sourceUrl?: string | null; enteredAt?: string | null } | null
  fpStd: number | null
  fpHalf: number | null
  fpPpr: number | null
  fpSd: number | null
  fpP10: number | null
  fpP90: number | null
  /** How the 80% range was produced: "empirical" (veteran game-to-game variance) |
   *  "calibrated_per_player" (NF1.7 — a per-player rookie band, render as a REAL interval) |
   *  "calibrated" (the thin-history rookie fallback — a shared class-level band; keep this one, and
   *  ONLY this one, labelled "Class-level" — see UNCERTAINTY_LABEL/UNCERTAINTY_HELP). */
  uncType: string | null
  passAtt: number | null
  passCmp: number | null
  passYds: number | null
  passTd: number | null
  passInt: number | null
  rushAtt: number | null
  rushYds: number | null
  rushTd: number | null
  tgt: number | null
  rec: number | null
  recYds: number | null
  recTd: number | null
  fum: number | null
  twoPt: number | null
  /** Market average draft position (PPR, 12-team — see `adp_format`/`adp_teams` on the payload).
   *  A reference column; null means undrafted in that sample. */
  adp?: number | null

  /** NF1.5b — how MARKET-LEANING this row's ORDERING is: `"market-led"` / `"market-led-adaptive"` /
   *  `"market-blend"` / `"independent-lean"` / `"independent"`.
   *
   *  🚨 It is the honest caveat, not a decoration. The served board re-orders our own calibrated
   *  projections using market consensus (ADP/ECR) at the positions where that measurably helped — so
   *  at a market-led position the ranking is NOT an independent read on the market, and must never be
   *  presented as beating a market it is partly built from. Null on a market-blind payload and on
   *  rows with no market input (rookies, K/DST). */
  mktLean?: string | null

  // ── NF3.4: PER-PLAYER feature contributions — genuine per-player attribution (LightGBM TreeSHAP),
  // NOT a position-level description. Null for a rookie or K/DST (NF1 has no base-season feature row
  // to attribute for either). 🚨 `totalPts` is NF1's OWN separate research-model prediction for this
  // player — it is NOT guaranteed to equal `fpPpr` above (the served MVP-1 number); see
  // `nf1_model.player_feature_contributions`'s docstring. Feature labels/descriptions live in the
  // manifest's `featureLegend`, not repeated here. ──────────────────────────────────────────────
  contrib?: {
    /** The model's SHARED constant — its unconditional expected value, the SAME number for every
     *  player it scores. NOT player-specific; never describe this as "his" anything. */
    biasPts: number
    /** THIS player's own `mvp1_fp` contribution — genuinely player-specific (it scales with his own
     *  baseline heuristic projection), which is WHY two players at the same position show different
     *  `baselinePts` even though `biasPts` is identical for both. */
    ownPriorPts: number
    /** `biasPts + ownPriorPts` — NF1's starting point for him specifically, shown as "starting
     *  point", not as one of `drivers` (a driver a model can't act on isn't a useful lever to show a
     *  drafter). */
    baselinePts: number
    /** `baselinePts` + every driver's `pts` (not just the ones shown) — NF1's full own prediction. */
    totalPts: number
    /** Ranked by |pts| descending; a positive value pushes his number up, negative pushes it down. */
    drivers: { feature: string; pts: number }[]
  } | null

  // ── NF3.1: BIO — passed through from nflverse's identity table (`player_bio_map`), never
  // derived/projected. Optional: absent for a DST (a team, not a person), for the ~0.2-1% of
  // players the source has nothing for, and on any payload exported before NF3.1. ──────────────
  /** ISO date. Age is computed client-side from this (not baked in server-side) so it never goes
   *  stale between re-exports. */
  birthDate?: string | null
  heightIn?: number | null
  weightLb?: number | null
  college?: string | null
  /** Years of NFL experience as of the export's last bio refresh. */
  yearsExp?: number | null
  /** An official nfl.com headshot URL — render with a fallback (initials), not assumed to always
   *  resolve. */
  headshot?: string | null

  /** NF-INJ1-C — the counting-stat fields the SERVER withheld on this row, by name.
   *
   *  ⭐ ABSENT ON EVERY NORMAL ROW, and present ONLY on a row whose stat line is physically
   *  impossible at its own expected games (NF-INJ1's recorded per-game envelope: the maximum rate
   *  any real NFL player-season posted 2006-2025). ~10 rows of 868 on the live board, all QB.
   *
   *  ⚠️ IT EXISTS BECAUSE ABSENT ≠ WITHHELD. A withheld stat and a stat that was never served
   *  arrive as the SAME missing key, and rendering both as a bare em-dash is the E9.56c inversion —
   *  a value we are deliberately not showing, silently reading as "we have nothing for this
   *  player". Branch on this list, never on the key being missing.
   *
   *  ⛔ IT CARRIES NO MAGNITUDES, deliberately: `impliedPerGame × g` would reconstruct the withheld
   *  season total exactly. Field NAMES only, and nothing here may grow a number.
   *
   *  ⛔ NEVER an input to ordering, VOR, scoring or the optimizer — this is a DISPLAY marker on the
   *  paid `/projections-full` payload. Points and `g` are untouched. */
  statLineWithheld?: string[] | null

  /** E9.56 — set by the server when this caller is not entitled to the season's model output. The
   *  row keeps its public identity (name/pos/team/ADP) so a "subscribe to unlock" CTA has something
   *  to render; every projected value is ABSENT, not null-with-a-secret. Optional: an entitled
   *  response omits it entirely. */
  locked?: boolean

  // ── NF1.6: KICKER + TEAM DEFENSE (DST) ────────────────────────────────────────────────────
  /** True for the positions whose projection must NOT be read as a confident rank (K/DST). Set on
   *  every row by the exporter (false for skill positions), so the UI never has to know which
   *  positions are soft. Optional — payloads exported before NF1.6 do not carry it. */
  lowPred?: boolean
  /** The honest caveat to render beside a `lowPred` row, supplied by the exporter so the wording
   *  lives with the model that earned it. */
  predNote?: string | null
  /** Kicker line. Field goals are split by DISTANCE because that is how they score (3/4/5) and
   *  because leg strength is the one kicker attribute that genuinely persists year to year. */
  fgAtt?: number | null
  fgMade?: number | null
  fg039?: number | null
  fg4049?: number | null
  fg50?: number | null
  fgMiss?: number | null
  patAtt?: number | null
  patMade?: number | null
  /** Team-defense line. `paPerG` (points allowed per game) is the number that communicates
   *  defensive quality; the nine points-allowed TIER buckets below are a scoring INPUT, never a
   *  display column. */
  sacks?: number | null
  defInt?: number | null
  fumRec?: number | null
  defTd?: number | null
  stTd?: number | null
  safety?: number | null
  blocked?: number | null
  paTot?: number | null
  paPerG?: number | null
  /** NF-C0b — the nine points-allowed TIER buckets, each the EXPECTED NUMBER OF GAMES the defense
   *  lands in that bucket. A per-game tier table therefore scores a season as
   *  `Σ_bucket tier_points × expected_games`, i.e. LINEAR in these columns — which is what lets a
   *  hand-entered D/ST scheme be applied EXACTLY rather than approximated. Never displayed.
   *  Optional: payloads exported before NF-C0b do not carry them, and a custom tier table then
   *  reports as captured-not-applied rather than silently scoring zero. */
  paG0?: number | null
  paG1_6?: number | null
  paG7_13?: number | null
  paG14_17?: number | null
  paG18_20?: number | null
  paG21_27?: number | null
  paG28_34?: number | null
  paG35_45?: number | null
  paG46p?: number | null

  // ── NF3.3: PLAYER HISTORY — past-season actual finish + past ADP + a weekly injury-report log +
  // games-missed participation. Lands inside THIS gated payload (never the public track-record
  // blob), so it is gated AT THE DATA LAYER with no extra UI logic: `null`/absent for a player with
  // nothing (a rookie with no past season, or a DST — a team, not a person, never carries an injury
  // log) and for any payload exported before NF3.3. 🔒 HONEST: descriptive realized history, never a
  // forward-looking claim (best_alpha=0) — `gamesMissedBySeason` counts a game NOT played for ANY
  // reason (injury, healthy scratch, roster move), never asserted to be injury-caused; the weekly
  // `injuries` report is the only place a specific injury is named. */
  history?: PlayerHistory | null
}

/** NF3.3 — one past season's actual finish vs that season's ADP, reusing the SAME per-player join
 *  (`benchmark_scorecard.player_track_record_frame`) NF3.2's public track-record page is built from
 *  — never a parallel re-derivation. See `TrackRecordRow` in `lib/fantasy-track-record.ts` for the
 *  public sibling shape (deliberately similar field names; this one adds `gamesPlayed`). */
export interface PastSeasonRecord {
  season: number
  ourRank: number
  /** Market ADP for that season — null when neither FFC nor its MFL fallback had an archive. */
  adp: number | null
  adpRank: number | null
  /** "ffc" | "mfl" | null — which real-draft population backed `adp` (see NF3.2). */
  adpSource: string | null
  actualPoints: number
  actualRank: number
  gamesPlayed: number | null
  isFade: boolean
  fadeResult: "hit" | "miss" | "push" | null
}

/** NF3.3 — one weekly nflverse injury-report entry (game-report + practice-participation status).
 *  Distinct from the roster-status availability prior the projection itself uses — this is pure
 *  DISPLAY history, never a model input. */
export interface InjuryReportEntry {
  season: number
  week: number
  reportStatus: string | null
  reportPrimaryInjury: string | null
  practiceStatus: string | null
  dateModified: string | null
}

/** NF3.3 — a season's participation count: how many of his team's non-bye games he did NOT record a
 *  snap/box-score line for, for ANY reason. Never merged with `injuries` into one "games missed to
 *  injury" number — read the weekly report for causation where one exists. */
export interface GamesMissedRecord {
  season: number
  gamesOnRoster: number
  gamesMissed: number
}

export interface PlayerHistory {
  pastSeasons: PastSeasonRecord[]
  injuries: InjuryReportEntry[]
  gamesMissedBySeason: GamesMissedRecord[]
}

export interface ProjectionPayload {
  season: number
  generated_at: string
  source: string
  /** NF-FRESH2 — the per-input vintage. `generated_at` above is the BUILD clock; these are the
   *  DATA clocks, and they do not agree (NF-FRESH1 §1.2). Optional throughout: an absent key means
   *  the payload predates the stamps, a null value means we could not tell. */
  adp_as_of?: string | null
  ecr_as_of?: string | null
  freshness?: FreshnessBlock | null
  model_version: string | null
  base_season: number | null
  /** Which FFC ADP sample the `adp` column came from — this surface is format-independent, so its
   *  ADP reference is pinned rather than varying, and is labelled with these. */
  adp_format?: string | null
  adp_teams?: number | null
  /** NF1.5b — which projection lineage this payload IS: `"nf1_5"` (market-aware refined, the served
   *  default since the re-land) or `"mvp1"` (market-blind). Absent on a pre-NF1.5b export. */
  projection_source?: string | null
  projection_label?: string | null
  /** `{position -> market lean}` for the whole board — the per-position form of `mktLean`. */
  market_lean?: Record<string, string> | null
  /** The standing caveat, supplied BY THE EXPORT so the wording lives with the model that earned it
   *  and cannot drift out of sync with which positions actually use the market. */
  market_lean_note?: string | null
  players: ProjectedPlayer[]

  // ── E9.56: the server-side entitlement envelope ────────────────────────────────────────────
  // ALL OPTIONAL, and every consumer must tolerate their ABSENCE: the API Lambda ships only via a
  // manual `deploy.sh` while this frontend auto-deploys on merge, so there is always a window where
  // a NEW client is talking to the OLD backend (NF-C0, both directions). Absent ⇒ read as ENTITLED,
  // which is the shape the old backend has always returned to a caller it let through at all.
  /** True when the server withheld this season's model output from this caller. */
  locked?: boolean
  /** Stated explicitly rather than inferred from `!locked`, so a dropped field can never read as
   *  entitled (the E9.41 silently-dropped-Pydantic-field class). */
  entitled?: boolean
  lockedSeason?: number
  /** Exactly which field names the server removed — computed server-side from the real payload, so
   *  a newly-added projection field shows up as a locked point (and a CTA) automatically. */
  lockedFields?: string[]
  upgrade?: { reason: string; message: string; ctaHref: string }
}

/** True iff the server locked this payload/row. Absent marker ⇒ NOT locked (see above). */
export function isLocked(x: { locked?: boolean } | null | undefined): boolean {
  return x?.locked === true
}

/** True iff the server locked THIS SET of rows (any row carrying the marker locks the view). */
export function rowsAreLocked(rows: { locked?: boolean }[] | null | undefined): boolean {
  return !!rows?.some((r) => r.locked === true)
}

/** E9.56b — trim the undrafted tail from a LOCKED view, and report how many were hidden.
 *
 *  WHY. A locked row keeps only public identity + market ADP. Measured against the live payload
 *  (2026-08-05): of 858 rows, **226 have an ADP and 632 do not** — so ~74% of the free page would be
 *  players with a name, a lock icon and nothing else, sorted alphabetically at the bottom. That is
 *  not a conversion surface, it is dead weight, and it is the bulk of what a crawler would index.
 *
 *  The hidden count is RETURNED rather than swallowed so the UI can state it honestly ("N more
 *  players are included with a subscription") — which turns the truncation into a reason to
 *  subscribe rather than a silent omission. Never drop rows without saying so.
 *
 *  ⚠️ AN ENTITLED VIEW IS UNTOUCHED — an unlocked payload returns unchanged, tail and all. A
 *  subscriber has a real projection for every one of those players and must still see them.
 */
export function trimLockedTail<T extends { adp?: number | null; locked?: boolean }>(
  rows: T[],
): { rows: T[]; hiddenCount: number } {
  if (!rowsAreLocked(rows)) return { rows, hiddenCount: 0 }
  const kept = rows.filter((r) => typeof r.adp === "number" && Number.isFinite(r.adp))
  return { rows: kept, hiddenCount: rows.length - kept.length }
}

// ── The FULL-SEASON RATE — a pure DISPLAY transform over two already-served fields ───────────────
//
// `expected_pts × 17 ÷ expected_games`. Both inputs are in the payload the page already renders, so
// this is arithmetic, not a model output: no re-fit, no re-export, no new endpoint, and nothing to
// re-validate. See `FULL_SEASON_RATE_DEFINITION` in `fantasy-claim-copy.ts` for what it means and
// what it deliberately does not claim.
//
// ⛔⛔ DISPLAY ONLY. It must never reach VOR, the board ordering, tiering or the optimizer — ranking
// on a full-slate rate ranks players as if availability did not exist, systematically promoting
// exactly the players the projection discounts on purpose, and because it REORDERS the board it
// becomes a model decision subject to the whole-board placement gate rather than a UI change.
// `test_freemium_tier.py` asserts this helper is absent from every scoring/ordering module.

/** An NFL regular season. Named rather than inlined so the three surfaces that render this number
 *  cannot disagree about it, and so a schedule change is one edit. */
export const FULL_SEASON_GAMES = 17

/** NF-C-HEALTHY — below this many expected games, `pts * 17 / games` amplifies ordinary projection
 *  noise into a number that no longer describes anything real: the same shape as NF-C7's `pts / g`
 *  defect (a 1.9-game, 76.6-point Easton Stick line "rating" 40.3/game), one arithmetic step over —
 *  run that identical 1.9 through THIS formula and it prints ~686, not merely a doubled number.
 *  `fullSeasonRate` is deliberately a rate over the player's OWN expected games (dividing by the
 *  constant `FULL_SEASON_GAMES` instead, NF-C7's fix, would answer "how much does he help across
 *  the whole roster", a different question this metric does not ask) — so the guard here is a FLOOR
 *  below which the arithmetic refuses outright, not a different divisor. 2 is not a measured
 *  threshold; it is the smallest games figure at which a one-game swing (the resolution `g` is
 *  reported at) is not itself enough to double the result. */
export const MIN_GAMES_FOR_FULL_SEASON_RATE = 2

/**
 * The full-season rate, or `null` when it cannot be computed.
 *
 * ⚠️ RETURNS NULL RATHER THAN 0/Infinity/NaN, and every branch here is a real payload state rather
 * than defensive padding:
 *   • `games === 0` — a player projected to miss the whole season. Dividing gives `Infinity`, which
 *     renders as "∞" beside a points column, and in JS `Infinity` is a `number` that passes every
 *     `!= null` check a caller might guard with.
 *   • `games`/`pts` absent — K/DST and gap-filled rows do not always carry both; a missing field
 *     type-checks as its declared type at runtime (the E9.56b lesson) and `undefined * 17` is NaN.
 *   • a NEGATIVE `games` cannot occur today but would silently flip the sign, so it is refused too.
 *   • `0 < games < MIN_GAMES_FOR_FULL_SEASON_RATE` — technically finite and positive, but the
 *     low-denominator trap: a real number that is not a meaningful comparability figure (see the
 *     constant's own doc). Refused for the same reason `games === 0` is, not merely a smaller one.
 * Callers render `null` as an em-dash — never a blank cell, which reads as a rendering fault.
 */
export function fullSeasonRate(
  pts: number | null | undefined,
  games: number | null | undefined,
): number | null {
  if (typeof pts !== "number" || !Number.isFinite(pts)) return null
  if (typeof games !== "number" || !Number.isFinite(games)) return null
  if (games <= 0) return null
  if (games < MIN_GAMES_FOR_FULL_SEASON_RATE) return null
  return (pts * FULL_SEASON_GAMES) / games
}

// ══ NF-RATE1 — THE REALIZED-PACE CEILING ════════════════════════════════════════════════════════
//
// ⭐ THE RULE, IN ONE SENTENCE, BECAUSE THIS IS WHERE THE NEXT EDITOR MEETS IT:
//    we do not print a full-season rate no NFL player has ever achieved — a row whose implied
//    17-game pace exceeds the highest full-season pace any real player-season has posted at that
//    position is WITHHELD, exactly as a row below `MIN_GAMES_FOR_FULL_SEASON_RATE` already is.
//
// THE DEFECT (measured on the staged 2026 board, `board_full_ppr_12.json`, 868 rows — not
// hypothetical). `pts × 17 ÷ g` on a heavily availability-capped row prints a rate above every real
// player on the board: GEORGE KITTLE 580, ALEC PIERCE 545 and WILL LEVIS 633, against a #1 overall
// (Jahmyr Gibbs, 350.8 pts) at 414. `MIN_GAMES_FOR_FULL_SEASON_RATE` does not catch them — all three
// sit at 3.3–3.7 expected games, comfortably above the floor — because the floor guards the
// DENOMINATOR'S RESOLUTION and this is a defect in the RATIO.
//
// ⭐ AND IT IS NOT NEW, WHICH IS WHY THE RULE IS ANCHORED RATHER THAN LISTED. Levis renders 633 on
// every scoring preset including standard and predates NF-INJ3b's flip entirely; Kittle and Pierce
// were widened onto the list by it. A rule tuned to catch "the two new rows" would have been tuned
// to the incident and would have left the worst row on the board. (NF-INJ1 §3: NF1.5 hands a
// promoted player a different player's point level and rescales his stat line to reach it while
// `_RAW_SCALE_COLS` leaves `proj_games` where it was — so this column is the NF-INJ1 give-back
// re-expressed as a rate, on a surface NF-INJ1-C's stat-line suppression does not cover.)
//
// ⛔ A RENDER RULE, NOT A WITHHOLDING. `pts` and `g` are both still served on the row and still
// rendered beside this column (NF-INJ3b-SHIP ruling D3), so the quantity stays arithmetically
// reconstructible by any reader who wants it — the freemium arithmetic-derivability lesson. What
// stops is US printing it as though it were a comparability figure. Nothing here reaches VOR,
// ordering, tiering or the optimizer; see the `⛔⛔ DISPLAY ONLY` note above, which this inherits.
//
// ────────────────────────────────────────────────────────────────────────────────────────────────
// THE ENVELOPE IS DERIVED FROM REALIZED HISTORY, NOT CHOSEN — AND THE DERIVATION IS WHAT IS PINNED
// ────────────────────────────────────────────────────────────────────────────────────────────────
// Same anchor family, same source table and same twenty seasons as NF-INJ1's
// `projection_coherence.REALIZED_MAX_PER_GAME` (which bounds the per-game COUNTING line); this is
// its season-POINTS analog, because the quantity this column prints is points, not carries.
//
//     with s as (select season, player_id, max(position) pos,
//                       count_if(played_flag and not is_bye) g,
//                       sum(fantasy_points_std) std, sum(fantasy_points_ppr) ppr,
//                       sum(receptions) rec
//                from main_nfl_marts.fct_player_week
//                where week > 0 and player_id is not null and season between 2006 and 2025
//                group by 1, 2)
//     select pos, round(max((ppr + case when pos = 'TE' then 0.5 * rec else 0 end) / g) * 17, 1)
//     from s where g >= 1 and pos in ('QB','RB','WR','TE') group by 1
//
// over the same 11,190 player-seasons (QB 1,539 / RB 2,815 / TE 2,464 / WR 4,372).
//
// ⭐ IT IS A **MAX**, AND ACROSS THE MOST GENEROUS SCORING WE PUBLISH, both on purpose. A max makes
// a firing a statement about what has actually happened rather than about what is likely, so the
// rule cannot false-fire the way a percentile or a hand-picked "plausible" ceiling could; and
// taking the maximum over every published preset (`league_presets`: standard / half / full PPR /
// superflex / TE-premium — the TE bonus is the only one that exceeds full PPR, hence the `+0.5·rec`
// term on TE alone) means the same ceiling is safe on every board we serve. Both choices err
// toward PRINTING a rate, which is the direction to err in: the cost of a missed absurd row is one
// bad-looking cell, the cost of a false suppression is hiding a real number from a paying reader.
//
// Stability check, part of the derivation rather than a post-hoc defence: restricting the
// population to seasons with ≥4 games played moves QB 471.1 → 471.1, WR 435.2 → 435.2, TE
// 414.0 → 414.0 and RB 512.3 → 511.2 (0.2%) — i.e. the envelope is not an artifact of one-game
// cameos, so it does not depend on where the population floor is put.
//
// ⛔ E2.1-r: these numbers are a property of twenty seasons of realized football, fixed before any
// board row was scored. They must never be re-derived from, or widened to accommodate, a board that
// failed them. Measured firing population on the staged 2026 board: 34 cells across all 14 served
// configs (0.28%) — Levis on all 14, Kittle and Pierce on the 10 reception-scored ones. JAYDEN
// HIGGINS, the third row NF-INJ3b's follow-up named, renders 413 and is NOT suppressed: a WR has
// posted a 435-point pace, so 413 is inside what football has done, and the anchor says so rather
// than the incident list saying otherwise.
//
// ⚠️ SCOPE, STATED SO IT IS NOT MISREAD AS COVERAGE. Positions outside the envelope (K, DST) are
// OUT OF SCOPE, not passed — `row_violations`' own convention. There is no realized per-game
// counting analog for them here, they are projected at a near-full slate so the ratio defect cannot
// arise, and the rule therefore never fires on them. A genuinely custom league scored more
// generously than TE-premium (a 2-PPR house rule) could in principle push a real row above the
// ceiling; the served preset boards cannot.

/** The highest full-season pace (`points × 17 ÷ games played`) any real 2006–2025 player-season has
 *  posted at this position, under the most generous scoring we publish. Derived, never chosen — see
 *  the block above for the query, the population and the stability check. Positions absent from
 *  this map are OUT OF SCOPE for the rule, which is not the same as passing it. */
export const REALIZED_MAX_SEASON_PACE: Readonly<Record<string, number>> = {
  QB: 471.1,
  RB: 512.3,
  WR: 435.2,
  TE: 414.0,
}

/** What a surface should render for the full-season rate on one row.
 *
 *  THREE STATES, and collapsing any two of them loses a distinction a reader needs:
 *    • `rate`        — print the number.
 *    • `withheld`    — we have a number and it is above what football has done, so we refuse to
 *                      print it. A STATED absence with a disclosure behind it (Option-C), never a
 *                      blank and never the number.
 *    • `unavailable` — there is nothing to divide, or too little to divide by. Every branch
 *                      `fullSeasonRate` already returned `null` on, byte-for-byte, so the
 *                      pre-existing MIN_GAMES behaviour on all four surfaces is untouched. */
export type FullSeasonRateDisplay =
  | { kind: "rate"; value: number }
  | { kind: "withheld" }
  | { kind: "unavailable" }

/**
 * THE ONE OWNER of the full-season-rate render decision. All four render sites go through it —
 * the rankings board's column, the same board's CSV export, the projections table's column, and
 * the player page's two format tiles — because four inline copies of one rule is the
 * "one logical thing, many owners" defect (INC-30 / INC-36 / INC-38) on day one, and the CSV is
 * precisely the site a table-only fix silently misses.
 *
 * `pos` is read tolerantly (missing / unknown ⇒ out of scope ⇒ the rate prints as before), because
 * this crosses a payload boundary the frontend deploys independently of (NF-C0) and a row with no
 * position must degrade to the pre-story rendering rather than to a withheld cell.
 */
export function fullSeasonRateDisplay(
  pts: number | null | undefined,
  games: number | null | undefined,
  pos: string | null | undefined,
): FullSeasonRateDisplay {
  const rate = fullSeasonRate(pts, games)
  if (rate == null) return { kind: "unavailable" }
  const ceiling = REALIZED_MAX_SEASON_PACE[String(pos ?? "").toUpperCase()]
  if (typeof ceiling === "number" && rate > ceiling) return { kind: "withheld" }
  return { kind: "rate", value: rate }
}

/** The CSV cell for one row: the number, or `null` — which `downloadCsv` writes as an EMPTY cell.
 *
 *  ⭐ EMPTY, NOT A SENTINEL AND NOT THE NUMBER. A spreadsheet reader has no tooltip, so the only
 *  honest renderings are a value or nothing; a `withheld` string would break the column's type for
 *  every reader who sorts or averages it, and "0" or "-1" would be a wrong number rather than an
 *  absent one. The header note the export carries documents what an empty cell in this column
 *  means, so the withholding is STATED rather than inferable (NF-FRESH2's absent-vs-null rule).
 *  ⚠️ A withheld row and an unavailable row deliberately produce the SAME empty cell: both are "we
 *  are not publishing this number for this player", and a spreadsheet has nowhere to say which. */
export function fullSeasonRateCsv(
  pts: number | null | undefined,
  games: number | null | undefined,
  pos: string | null | undefined,
): number | null {
  const d = fullSeasonRateDisplay(pts, games, pos)
  return d.kind === "rate" ? d.value : null
}

// ══ NF-C8 — THE AVAILABILITY FLAG ═══════════════════════════════════════════════════════════════
//
// THE PROBLEM. The projection already multiplies the chance a player misses games through his point
// total, and `g` is served beside it — so the discount is PRESENT on every board and INVISIBLE on
// all of them. A drafter scanning the rankings meets a player two rounds lower than he expected and
// a number he cannot account for; the games column that explains it is four columns right, in the
// same weight and colour as every other figure on the row. The remedy is to make the discount
// legible AT A GLANCE on the rows where it is doing real work.
//
// THE BOUNDARY, STATED PRECISELY, BECAUSE THE DISHONEST VERSION IS ONE WORD AWAY. It is a fact
// about OUR PROJECTION — "we project this player for fewer than a full slate of games" — and it is
// NOT an injury forecast. We are not saying he is hurt, will get hurt, or will miss particular
// weeks. `g` is an EXPECTATION across everything that could happen to him (which is why it is
// fractional), and a surface that rendered it as "expected to miss N games" would be publishing a
// medical prediction we have never made and could not defend. See `AVAILABILITY_FLAG_DEFINITION`
// in `fantasy-claim-copy.ts`, which is where that boundary is written down and screened.
//
// AND IT IS A DISPLAY CLASSIFIER, FULL STOP. Like `fullSeasonRate` above, it must never reach VOR,
// the board ordering, tiering or the optimizer — a threshold that moved a player's RANK would be a
// model decision subject to the whole-board placement gate (NF-D18/NF-D20), not a UI change.

/** Below this many expected games, a row carries the availability flag.
 *
 *  ⚠️⚠️ THIS WAS 14 AND 14 WAS WRONG — the correction is recorded here rather than quietly applied,
 *  because the mistake is instructive and the temptation to re-make it is permanent.
 *
 *  The original derivation read "three games below a full `FULL_SEASON_GAMES` slate". The arithmetic
 *  was fine; the ANCHOR was not. **No skill player is projected anywhere near 17** — that is the
 *  schedule, and the only rows that reach it are team defences. Measured on the served 2026 board,
 *  the median DRAFTABLE skill player (top 180, the roster-fill depth of a 12-team league) sits at
 *  **14.4 expected games**, and the running-back median is **exactly 14.0**. So a 14-game threshold
 *  sat just below the median of the very population it was meant to mark as exceptional, and flagged
 *  **37.6% of draftable skill players** — 45.7% of running backs against 19.0% of tight ends, i.e.
 *  the flag was substantially reporting "this is a running back", which is a position norm and not
 *  information. A colour on two rows in five is a background, not a signal.
 *
 *  THE CORRECTED RULE, stated as a rule so the next reader can check it rather than trust it:
 *  measure the discount against the board's own typical draftable skill player, NOT against the
 *  schedule. "Limited" is roughly **two games below that typical player** — 14.4 − 2 ≈ 12.4, taken
 *  as 12.5 — which lands at 15.4% of draftable skill players and flattens the position spread
 *  (RB 25.7%, QB 18.8%, WR 11.1%, TE 4.8%).
 *
 *  ⛔ AND THE E2.1-r LINE, which this change walks right up to: re-deriving a threshold FROM A
 *  MEASURED PROPERTY OF THE POPULATION (its median) against a rule fixed in advance is legitimate;
 *  re-picking it so that a PARTICULAR PLAYER flags or stops flagging is the inversion, and it would
 *  be very easy here because the flag is visible and opinions about individual players are cheap.
 *  The roster this produces was sanity-checked AFTER the number was derived and the number was not
 *  moved as a result. Anyone changing it again owes the same order of operations. */
export const LIMITED_AVAILABILITY_GAMES = 12.5

/** The stronger tier — fewer than this many expected games. UNCHANGED at 10 by the same corrected
 *  rule: roughly four and a half games below the typical draftable skill player, which is a genuinely
 *  unusual projection rather than a soft one. It fires on 0.9% of the top 180 and 3.4% of the top 250
 *  — deliberately rare, because a second colour that is not rare is a second background.
 *
 *  Two tiers rather than one because "he misses a couple of games" and "we project him for well under
 *  half a season" are different facts for a drafter, and a single flag renders them identically. */
export const HEAVILY_LIMITED_AVAILABILITY_GAMES = 10

export type AvailabilityTier = "limited" | "heavily-limited"

/**
 * Which availability tier a row is in, or `null` when it carries no flag.
 *
 * EVERY `null` BRANCH HERE IS A REAL PAYLOAD STATE, and returning `null` for all of them is a
 * deliberate choice rather than defensive padding:
 *
 *   - `locked` — E9.56's redaction strips `g` from the row entirely, and `numOrLock` renders a
 *     "subscribe" chip in its place. A flag beside that chip would be worse than useless: it would
 *     DISCLOSE the withheld value's neighbourhood on exactly the rows the server withheld it from
 *     (NF-LEAK1), while claiming to describe a number the reader cannot see.
 *   - `g` absent or `null` — a K/DST row, a gap-filled row, or a payload from before `g` shipped.
 *     There is no honest flag for "we have no expected-games figure": unlike a freshness stamp
 *     (where NF-FRESH2's absent-vs-null distinction is load-bearing because "we looked and could
 *     not tell" is itself a fact worth rendering), an ABSENT projection supports no availability
 *     claim in either direction. Render nothing.
 *   - a NEGATIVE or non-finite `g` cannot occur today and would be flagged as "heavily limited" by
 *     a naive `<` chain — i.e. a corrupt field would produce a confident user-facing claim. Refused.
 *
 * `g === 0` is NOT refused. It is a real served state (the free-board fixture plants one), it is
 * genuinely below a full slate, and it is the single most important row to flag — the reader whose
 * projection is zero is the one owed an explanation. Note this is where the flag and
 * `fullSeasonRate` deliberately part company: that helper refuses below
 * `MIN_GAMES_FOR_FULL_SEASON_RATE` because DIVIDING by a tiny denominator amplifies noise into a
 * meaningless number, which is an arithmetic hazard this classifier does not have.
 */
export function availabilityTier(
  games: number | null | undefined,
  opts?: { locked?: boolean },
): AvailabilityTier | null {
  if (opts?.locked) return null
  if (typeof games !== "number" || !Number.isFinite(games)) return null
  if (games < 0) return null
  if (games < HEAVILY_LIMITED_AVAILABILITY_GAMES) return "heavily-limited"
  if (games < LIMITED_AVAILABILITY_GAMES) return "limited"
  return null
}

/** NF1.5b — the positions whose ordering INCORPORATES market consensus, from a `market_lean` map.
 *  Anything that is not explicitly independent counts, so a new lean label added upstream is treated
 *  as market-leaning (the conservative direction) rather than silently dropping the caveat. */
export function marketLeaningPositions(
  lean: Record<string, string> | null | undefined,
): string[] {
  if (!lean) return []
  return Object.entries(lean)
    .filter(([, v]) => typeof v === "string" && !v.startsWith("independent"))
    .map(([pos]) => pos)
    .sort()
}

// ── G100-D1: the anonymous read path goes through our own CDN, not the API Lambda ────────────────
//
// `/api/public/*` is a same-origin Next route handler that fetches the payload and returns it with
// `s-maxage` — Vercel serves every subsequent view from the edge with no function invocation and no
// Lambda call. See that route's module comment for the safety properties.
//
// ⚠️ WHY THE `token ? … : …` SPLIT SURVIVES THE FREEMIUM FLIP, WHEN ITS ORIGINAL REASON DID NOT.
// Pre-freemium the two arms returned DIFFERENT bodies (anonymous got E9.56's locked payload), so
// routing a subscriber through a shared cache would have been a paid-data breach. That is no longer
// true: these three reads are now entitlement-independent, so both arms fetch the same bytes and
// sending everyone through the CDN would be SAFE — and cheaper, since a signed-in free user is
// currently one Lambda invocation per view.
//
// It is deliberately NOT done here. Making the CDN the serving path for PAYING users is a serving
// change, not a UI un-gate, and it moves subscribers onto a cache whose staleness window (900s) was
// chosen for anonymous traffic. Carried as a follow-up rather than smuggled into this story.
//
// ⛔ THE INVARIANT THAT KEEPS BOTH ARMS CORRECT: whatever else changes, these three endpoints must
// stay entitlement-independent. If one ever varies by caller again, the CDN arm starts publishing
// one caller's payload to everybody — so that change would have to revisit the CDN allowlist, the
// backend cache rules and the query keys together. Pinned by `test_freemium_tier.py`.
export function getFantasyManifest(token: string | null, season: number): Promise<Manifest> {
  if (!token) return cdnFetch(`/api/public/manifest?season=${season}`)
  return apiFetch(`/fantasy/nfl/manifest?season=${season}`, {}, token)
}

export function getFantasyBoard(
  token: string | null,
  season: number,
  config: string,
  size: number,
): Promise<Player[]> {
  const qs = `season=${season}&config=${encodeURIComponent(config)}&size=${size}`
  if (!token) return cdnFetch(`/api/public/board?${qs}`)
  return apiFetch(`/fantasy/nfl/board?${qs}`, {}, token)
}

export function getFantasyProjections(
  token: string | null,
  season: number,
): Promise<ProjectionPayload> {
  if (!token) return cdnFetch(`/api/public/projections?season=${season}`)
  return apiFetch(`/fantasy/nfl/projections?season=${season}`, {}, token)
}

// ── NF-EPIC 1: the PAID half of the projection ───────────────────────────────────────────────────
//
// 🔒 The raw stat line and the two reference scorings (`fpStd`/`fpHalf`) left the public payload on
// 2026-08-10 (PM Option C). They were gated only by which component drew them, and a `curl`
// recovered all three; the stat line is the re-scorable substrate, so it is now served ONLY here,
// behind `require_fantasy_access`.
//
// ⚠️ ALWAYS TOKENED, NEVER THROUGH THE CDN ARM. Every other fetcher above falls back to
// `cdnFetch` when there is no token; this one must not, and the asymmetry is the point — the edge
// route strips `Authorization` by design, so a request for paid data through it would be an
// anonymous one, and a 403 (or worse, a paid body) would be pinned into a public cache entry.
export function getFullProjections(
  token: string,
  season: number,
): Promise<ProjectionPayload> {
  return apiFetch(`/fantasy/nfl/projections-full?season=${season}`, {}, token)
}

// ── NF-EPIC 1: a saved league's board, scored SERVER-SIDE ────────────────────────────────────────
//
// ⭐ THIS IS WHAT LETS A FREE ACCOUNT KEEP ITS ONE PERSONALIZED LEAGUE (G100-C1) NOW THAT THE STAT
// LINE IS PAID. The board used to be built in the browser by `buildBoard` off the raw stat line;
// with that substrate withheld, the same board is computed on the server and only the OUTPUT is
// sent. The caller receives a board they could not have derived.
//
// The server scorer mirrors `fantasy_engine` (the engine behind the shipped preset boards), so a
// custom league now agrees with a preset where the browser port previously differed by up to 0.05
// on an interval bound — see `app/backend/services/league_scoring.py`.
export interface LeagueBoardPayload {
  season: number
  league: SavedLeague
  board: {
    players: Player[]
    replacement: Record<string, number>
    started: Record<string, number>
    coverage: unknown
  }
  roster: RosterMatchRow[]
  /** NF-C6P3 — every stored team's roster joined to the SAME board, server-side (additive key: a
   *  league imported before this shipped has none, and the client reads it with `?? []`). */
  league_rosters?: LeagueTeamRoster[] | null
}

/** One team in the league, its roster already joined to this league's board. */
export interface LeagueTeamRoster {
  team_key: string
  team_name: string
  /** Resolved server-side from `source_team_key` — never by team NAME, because two managers in one
   *  league may well have picked the same one. */
  is_mine: boolean
  rows: RosterMatchRow[]
}

/** One roster slot joined to its scored board row. `board` is null on an honest miss (a spelling
 *  divergence, a DST rendered as a team abbreviation, an unresolved platform id). */
export interface RosterMatchRow {
  roster: ImportedPlayer
  board: Player | null
}

export function getLeagueBoard(
  token: string | null,
  leagueId: string,
  season: number,
): Promise<LeagueBoardPayload> {
  const qs = `league_id=${encodeURIComponent(leagueId)}&season=${season}`
  return apiFetch(`/fantasy/nfl/league-board?${qs}`, {}, token)
}

// ── NF-C0b: saved league settings ────────────────────────────────────────────────────────────────
// The manual customization FLOOR. A platform import (NF-C0) is the convenience path and will never
// reach every league (private leagues, long-tail platforms, a fragile ESPN endpoint), so a user can
// always type their settings in instead. Both paths write the SAME `fantasy_engine` LeagueConfig,
// which is why a hand-built league feeds the board / VOR / draft tools identically to an imported one.

import type { LeagueConfig } from "@/lib/league-config"
import type { ImportedPlayer } from "@/lib/fantasy-import"

/** NF-C0 import provenance — where a league CAME FROM.
 *
 *  Deliberately NOT part of `LeagueConfig` (which mirrors the engine's `to_dict()` exactly): this
 *  is storage metadata in the same class as `created_at`, so an imported league and a typed-in one
 *  remain the identical config object once the envelope is dropped. A hand-entered league leaves
 *  these undefined. They exist for the one thing the config cannot express — going back to the
 *  platform for LIVE draft state, which is never persisted because a stale one looks correct. */
export interface LeagueProvenance {
  source_platform?: string | null
  source_league_id?: string | null
  imported_at?: string | null
  // ── NF-C6: which previewed team is the user's own, and its roster AT IMPORT TIME ──────────────
  // A SNAPSHOT, not a live read: unlike draft state this works uniformly across all three
  // platforms, including ESPN, whose paste flow structurally can never be re-fetched by the server.
  // `roster_synced_at` keeps the age honest; re-importing (already an "update, not duplicate" save)
  // refreshes it. See the Python field docstrings in app/backend/models/fantasy.py.
  source_team_key?: string | null
  source_team_name?: string | null
  imported_roster?: ImportedPlayer[] | null
  roster_synced_at?: string | null
  // ── NF-C6P3: EVERY team's roster, not just the user's own ─────────────────────────────────────
  // We already fetched all of them at import (`ImportedLeague.teams[].players` — it is how the
  // "which team is yours?" screen works) and then discarded all but one. Keeping them is what turns
  // "outside the pool a league your size drafts" into a TRUE free-agent pool, and what makes a
  // comparison against the other managers possible at all. A snapshot, never re-fetched.
  // Slimmed to name/position/team server-side (`models/fantasy.LEAGUE_ROSTER_PLAYER_FIELDS`) and
  // bounded there too — `league_rosters_truncated` says when we stored fewer than we were given.
  league_rosters?: LeagueRosterEntry[] | null
  league_rosters_synced_at?: string | null
  league_rosters_truncated?: boolean | null
}

/** One team's stored roster, as the platform named the players. */
export interface LeagueRosterEntry {
  team_key: string
  team_name: string
  players: { name: string | null; position: string | null; team: string | null }[]
}

/** What a save accepts: the shared config, optionally stamped with where it was imported from. */
export type LeagueSaveInput = LeagueConfig & LeagueProvenance

/** A stored league: the shared config object plus its server-assigned identity + timestamps. */
export interface SavedLeague extends LeagueConfig, LeagueProvenance {
  league_id: string
  user_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  /** NF-C0-Yahoo-ENABLE — true once a disconnect, or the retention window closing, deleted roster
   *  data this league HAD held. Read with `?? false`: it is an additive key (NF-C0) and a league
   *  saved before it existed carries none.
   *
   *  ⭐ It exists so a deletion cannot render as "your league hasn't drafted yet". Those two states
   *  produce the identical payload — a linked team with an empty roster — and explaining ours as
   *  theirs is a confident wrong answer that sends the user to re-import for no reason. */
  roster_retention_purged?: boolean | null
}

export function listSavedLeagues(token: string | null): Promise<SavedLeague[]> {
  return apiFetch(`/fantasy/leagues`, {}, token)
}

// ── NF-C7b: ACCOUNT-level fantasy defaults ───────────────────────────────────────────────────────
export interface FantasyPreferences {
  depth_targets: Record<string, number>
}

export function getFantasyPreferences(token: string | null): Promise<FantasyPreferences> {
  return apiFetch(`/fantasy/preferences`, {}, token)
}

/** ⚠️ RESOLVES TO WHAT THE SERVER STORED, not to what was sent — and callers compare the two.
 *  These models set no `extra="forbid"`, so a backend that predates a field accepts it, ignores it
 *  and returns 200: the user watches their setting save and then vanish on reload with no error
 *  anywhere (E8.6). Echoing the stored value is what makes that visible instead of silent. */
export function saveFantasyPreferences(
  token: string | null,
  prefs: FantasyPreferences,
): Promise<FantasyPreferences> {
  return apiFetch(`/fantasy/preferences`, { method: "PUT", body: JSON.stringify(prefs) }, token)
}

export function createSavedLeague(
  token: string | null,
  cfg: LeagueSaveInput,
): Promise<SavedLeague> {
  return apiFetch(`/fantasy/leagues`, { method: "POST", body: JSON.stringify(cfg) }, token)
}

export function updateSavedLeague(
  token: string | null,
  leagueId: string,
  cfg: LeagueSaveInput,
): Promise<SavedLeague> {
  return apiFetch(
    `/fantasy/leagues/${encodeURIComponent(leagueId)}`,
    { method: "PUT", body: JSON.stringify(cfg) },
    token,
  )
}

export function deleteSavedLeague(token: string | null, leagueId: string): Promise<void> {
  return apiFetch(
    `/fantasy/leagues/${encodeURIComponent(leagueId)}`,
    { method: "DELETE" },
    token,
  )
}

// ── NF-C6: My Teams (cross-league browse) ────────────────────────────────────────────────────────
// `/fantasy/nfl/my-teams` reads at the BROADER `require_fantasy_access` gate (not the beta-only
// `/fantasy/leagues`) — see the endpoint's own docstring. It returns the same `SavedLeague` shape;
// this surface just reads it under a different entitlement and scores it client-side (`buildBoard`).

export interface MyTeamsPayload {
  season: number
  leagues: SavedLeague[]
  // ── G100-C1, ADDITIVE (NF-C0/E8.6) ──────────────────────────────────────────────────────────
  // OPTIONAL because the deployed API does not send them until `deploy.sh` runs, and the two halves
  // cross over in an order nobody controls. Every read below uses `?? default`, so during the skew
  // window the page behaves exactly as it does today rather than rendering `undefined`.
  /** How many personalized leagues this caller may keep (1 free, 25 subscriber). */
  quota?: number
  /** How many NFL leagues they have SAVED — may exceed `quota` for a lapsed subscriber. */
  saved_total?: number
  /** `saved_total − served`. Non-zero means leagues exist that we are not personalizing. */
  withheld_by_quota?: number
  // ── NF-EPIC 1, ADDITIVE ─────────────────────────────────────────────────────────────────────
  /** `{league_id: rosterRows}` — each league's linked roster joined to its OWN scored board,
   *  computed SERVER-SIDE now that the stat line the browser used to score with is paid.
   *
   *  ⚠️ ROSTER ROWS ONLY, never the full boards: at a subscriber's quota of 25 leagues, 25 boards
   *  is ~6 MB and straight through Lambda's proxy-response cap. The one board a page needs comes
   *  from `getLeagueBoard`, one league at a time.
   *
   *  OPTIONAL for the usual reason (NF-C0/E8.6): the deployed API does not send it until
   *  `deploy.sh` runs, so every read uses `?? default` and the skew window renders an honest empty
   *  state rather than `undefined`. */
  rosters?: Record<string, RosterMatchRow[]>
  // ── NF-K1, ADDITIVE ─────────────────────────────────────────────────────────────────────────
  /** Which PROJECTABLE positions the served board ACTUALLY carries, read off the board's own rows.
   *
   *  🔴 This is what lets an unmatched roster row explain itself. On 2026-08-16 the published board
   *  carried zero K and zero D/ST, so every rostered kicker and defence rendered "not matched" —
   *  wording that points a reader at the name join, which was fine and simply had nothing to match
   *  against. With this, "we have not published that position" is distinguishable from "we could
   *  not find this player".
   *
   *  ⚠️ THREE STATES, AND `undefined` IS NOT `[]`. `undefined` = an older deployed API that does not
   *  send the key (NF-C0 skew) OR a read the server could not make; `[]` = a board that genuinely
   *  published no projectable position. Only a non-empty array licenses the "not published" wording
   *  — on `undefined` the surface falls back to the plain, weaker sentence rather than asserting a
   *  cause it cannot support. */
  board_positions?: string[] | null
}

export function getMyTeams(token: string | null, season: number): Promise<MyTeamsPayload> {
  return apiFetch(`/fantasy/nfl/my-teams?season=${season}`, {}, token)
}

// ── NF-C4: the CUSTOM BIG BOARD ──────────────────────────────────────────────────────────────────
//
// A user's own ranking of one published (config, size) board. Reads at `require_fantasy_access` —
// the SAME gate as the draft and auction optimizers this surface sits beside — not the broader
// personalization quota: a big board is the paid decision-support half.
//
// ⛔ ALWAYS TOKENED, NEVER THROUGH `cdnFetch`. Every response here is per-caller by construction, so
// the CDN arm (which strips `Authorization` by design) would either 401 or, far worse, pin one
// user's board into a shared cache entry. The asymmetry with the board/manifest fetchers above is
// the point — see `getFullProjections` for the same rule on the paid projection.

export interface CustomBoardsPayload {
  boards: SavedBigBoard[]
  /** The storage ceiling, served so the surface never hardcodes a number the server owns. OPTIONAL
   *  for the usual reason (NF-C0/E8.6): `frontend/` deploys on merge and the API only on
   *  `deploy.sh`, so during the skew window this key is simply absent and the caller reads it with
   *  `?? null` and says nothing rather than quoting a guess. */
  max_boards?: number | null
}

export function listCustomBoards(token: string | null): Promise<CustomBoardsPayload> {
  return apiFetch(`/fantasy/nfl/custom-boards`, {}, token)
}

/** Upsert the caller's board for one (config, size). The server derives the storage key from those
 *  two fields, so there is no id to pass and no way for two saves of one board to diverge. */
export function saveCustomBoard(
  token: string | null,
  input: BigBoardDoc & { config: string; size: number },
): Promise<SavedBigBoard> {
  return apiFetch(
    `/fantasy/nfl/custom-boards`,
    { method: "PUT", body: JSON.stringify(input) },
    token,
  )
}

export function deleteCustomBoard(token: string | null, boardKey: string): Promise<void> {
  return apiFetch(
    `/fantasy/nfl/custom-boards/${encodeURIComponent(boardKey)}`,
    { method: "DELETE" },
    token,
  )
}
