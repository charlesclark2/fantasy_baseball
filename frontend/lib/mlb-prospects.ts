// E8.1 — MLB dynasty PROSPECT BOARD types + fetchers.
//
// Data comes from the SERVER-SIDE-GATED /fantasy/mlb/prospects/* endpoints (require_fantasy_access
// → 403), which read static JSON the operator publishes to s3://$CACHE_BUCKET/fantasy/mlb/<season>/.
// The current-season board is the PAID product, so the gate is at the DATA layer (E9.56 / NF-C6) —
// no gated value is ever shipped to an unentitled client and then hidden in the render.
//
// 🔒 HONEST FRAME (`best_alpha = 0`). Nothing on this surface claims to beat FanGraphs. Note that
// almost none of the framing copy lives in this file or the components: it arrives in the
// manifest's `framing` block, WRITTEN BY THE EXPORTER, so the wording travels with the model that
// earned it and cannot drift out of sync with what was actually measured (the NF3 convention).
//
// ⚠️ BUILD-TIME FRESHNESS. These blobs change only when the exporter re-publishes — a rebuilt
// board does NOT reach users until an operator re-runs `export_prospect_board_json.py --publish`.

import { apiFetch } from "@/lib/api"

/** The MLB prospect-board season every surface reads. */
export const PROSPECT_SEASON = 2026

/** One prospect. ⚠️ EVERY FIELD IS OPTIONAL EXCEPT the identity block: the exporter omits null keys,
 *  and a missing value is a REAL state on this board — "no minor-league PA yet" (complex/DSL/
 *  just-drafted), "not ranked by that source", "no grade published". Render `—`, never 0. */
export interface Prospect {
  rank: number
  name: string
  /** AL / NL of the parent org. ⭐ A REQUIRED filter, not a nicety: dynasty leagues are
   *  single-league, so scoping the whole board to one is the first thing a user does. */
  league: string
  /** "batter" | "pitcher" | "two_way" — drives the POSITION-DIFFERENTIATED framing (E7.8). */
  type: string
  org?: string
  pos?: string
  level?: string
  age?: number
  /** Age minus the median age of board prospects AT THAT LEVEL. Negative = young for the level. */
  ageVsLevel?: number
  eta?: number
  bats?: string
  throws?: string

  // ── the scouts ──
  fv?: number
  risk?: string
  fgOverallRank?: number
  fgOrgRank?: number
  fgDynastyRank?: number
  pipelineOverallRank?: number
  pipelineOrgRank?: number
  /** False = MLB Pipeline ranks him but FanGraphs' board does not carry him at all. His FanGraphs
   *  columns are then blank because there is NO FanGraphs row — never because he is "ungraded". */
  onFgBoard?: boolean
  consensusRank?: number
  consensusSources?: number
  consensusConfidence?: string
  consensusTier?: string

  // ── the three scores ──
  fvPctile?: number
  mleScore?: number
  ageScore?: number
  modelScore?: number
  blendScore?: number
  mleCoverage?: number
  /** How much HIGHER our score is than is usual for a player with THAT FV, in percentile points.
   *  A RESIDUAL fitted within player type — NOT modelScore − fvPctile. */
  disagreement?: number
  disagreementLabel?: string
  mleVsConsensus?: number
  mleVsConsensusLabel?: string
  speedFlag?: string
  inMajors?: string

  // ── our line: batters (E7.3) ──
  mleLevel?: string
  mlePa?: number
  mleK?: number
  mleKSd?: number
  mleBb?: number
  mleBbSd?: number
  mleIso?: number
  mleIsoSd?: number

  // ── our line: pitchers (E7.3p) ──
  mlePLevel?: string
  mlePTbf?: number
  mlePK?: number
  mlePKSd?: number
  mlePBb?: number
  mlePBbSd?: number
  mlePGb?: number
  mlePGbSd?: number

  // ── E7.13 comps ──
  compScore?: number
  /** How far the comp read moved him on the board (positive = UP), against `rankNoComps`. */
  compRankDelta?: number
  rankNoComps?: number
  compNames?: string
  compNames5?: string
  compNote?: string
  /** strong | fair | thin. THIN = read the band, not the median. */
  compQuality?: string
  compK?: number
  compBustRate?: number
  compPDebut?: number
  compFpMedian?: number
  compBandLo?: number
  compBandHi?: number
  compBandQuantiles?: string
  compNNever?: number
  compNFringe?: number
  compNRegular?: number
  compNImpact?: number

  note?: string
  mlbamId?: number
  fgMinorId?: string
}

export interface ProspectBoardPayload {
  season: number
  generated_at: string
  players: Prospect[]
}

/** The honest framing, authored by the EXPORTER (see `export_prospect_board_json.FRAMING`). */
export interface ProspectFraming {
  headline?: string
  claim?: string
  /** Keyed by player type — E7.8's verdict: lead with FV for arms, with our line for bats. */
  byPosition?: Record<string, string>
  /** Payload key → "strong" | "weak". Which of our metrics may be read with confidence (E7.3). */
  metricConfidence?: Record<string, string>
  metricNotes?: Record<string, string>
  /** Things deliberately ABSENT because they were measured and found null (wOBA), or structurally
   *  invisible to us (stolen bases). Rendered as prose — never quietly dropped. */
  absences?: string[]
  uncertainty?: string
  scoresAreWithinType?: string
  disagreement?: string
  comps?: string
  inMajors?: string
  /** Why a player can carry NO line from us — two genuinely different causes, keyed `complex`
   *  (the translation is not built for complex/DSL at all) and `thinSample` (he HAS a record, it is
   *  under the minimum-sample floor). Picking the right one matters: telling a user "no record"
   *  about a top-100 prospect he just watched play is how a surface loses its credibility. */
  noLine?: { complex?: string; thinSample?: string }
  /** The minimum PA/TBF at a level before we publish a translated line (E7.3's `min_minor_pa`). */
  minSample?: number
  /** The levels the translation actually covers. Any level outside this list is the `complex` case. */
  mleLevels?: string[]
}

export interface ProspectManifest {
  season: number
  generated_at: string
  as_of_date?: string | null
  source?: string
  players: number
  hasComps: boolean
  counts?: {
    byLeague?: Record<string, number>
    byType?: Record<string, number>
    disagreements?: number
  }
  filters?: {
    leagues?: string[]
    orgs?: string[]
    levels?: string[]
    positions?: string[]
    etas?: number[]
  }
  framing?: ProspectFraming
}

export function getProspectManifest(
  token: string | null,
  season: number = PROSPECT_SEASON,
): Promise<ProspectManifest> {
  return apiFetch(`/fantasy/mlb/prospects/manifest?season=${season}`, {}, token)
}

export function getProspectBoard(
  token: string | null,
  season: number = PROSPECT_SEASON,
): Promise<ProspectBoardPayload> {
  return apiFetch(`/fantasy/mlb/prospects/board?season=${season}`, {}, token)
}

// ── Display helpers ──────────────────────────────────────────────────────────────────────────

/** True for the rows that ride the batter side of the board (two-way players are scored as bats —
 *  `board_assembly`'s own rule, mirrored here so the UI never invents a third case). */
export const isBatter = (p: Prospect) => p.type === "batter" || p.type === "two_way"

/** A rate stored as a fraction (0.223) → "22.3%". Null-safe: a missing rate renders `—`. */
export const pct = (v: number | null | undefined, nd = 1) =>
  v == null ? "—" : `${(v * 100).toFixed(nd)}%`

/** ISO and other non-rate decimals: ".187"-style, the way a baseball reader expects them. */
export const dec3 = (v: number | null | undefined) =>
  v == null ? "—" : v.toFixed(3).replace(/^0\./, ".")

export const numOrDash = (v: number | null | undefined, nd = 1) =>
  v == null ? "—" : v.toFixed(nd)

/** ⭐ THE DISAGREEMENT LABELS ARE THE EXPORTER'S, not ours — the threshold behind them is a model
 *  constant (`DISAGREEMENT_THRESHOLD`), so re-deriving the label client-side from the number would
 *  put a second, drifting definition of "a disagreement" in the UI. */
export const isDisagreement = (p: Prospect) =>
  p.disagreementLabel === "WE'RE HIGHER" || p.disagreementLabel === "SCOUTS HIGHER"
