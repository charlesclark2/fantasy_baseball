// draft-optimizer.ts — the LIVE draft optimizer, a faithful TS port of the validated Python engine
// (quant_sports_intel_models/fantasy_engine/draft.py). Kept in lock-step with it: same need model,
// same VONA/tier-cliff signals, same additive (never multiplicative) scoring so VOR points stay
// comparable. Pure + synchronous → every pick recomputes instantly, no server round-trip.
//
//   score = vor + need_bonus            (need_bonus = 0 when the position's starter slots are full)
//   need_bonus = NEED_W[level] * positional_dropoff   (VONA — value lost at the position if you wait)
//
// ⭐ NF1.6: K and DST now carry a real (BASE) projection, so they ARE candidates. They need no
// special-casing to stay out of the early rounds — their VOR is genuinely tiny (the best 2026 kicker
// is +8 VOR against +150 for the top RB), so the same scoring that ranks everyone else already puts
// them where they belong: late, once the starter slots that matter are full. A row that is still
// genuinely unprojected (a gap-fill placeholder) has `vor == null` and is skipped below.
// The board JSON folds FB into RB, so positions here are QB/RB/WR/TE/K/DST.

export interface Player {
  id: string
  name: string
  pos: string
  team: string | null
  bye: number | null
  rookie: boolean
  g: number | null
  pts: number | null
  repl: number | null
  vor: number | null
  posRank: number
  ovrRank: number
  vorP10: number | null
  vorP90: number | null
  // NF3: the 80% interval on league POINTS. OPTIONAL because boards exported before NF3 do not
  // carry it — the browse surfaces render "—" rather than a wrong number until a re-export lands.
  ptsP10?: number | null
  ptsP90?: number | null
  // Market average draft position, matched to this board's scoring format + league size. A
  // REFERENCE column only — never an input to the optimizer's score. Null = undrafted in that
  // sample (a real signal), and absent entirely on boards exported before NF3.
  adp?: number | null
  // NF1.6: true for the positions whose projection must NOT be read as a confident rank (K/DST).
  // Declared on every row by the exporter (false for skill positions), so the UI never has to know
  // which positions are soft. OPTIONAL because boards exported before NF1.6 do not carry it.
  lowPred?: boolean
  /** The honest caveat to render beside a `lowPred` row. Supplied by the exporter so the wording
   *  lives with the model that earned it, not scattered across components. */
  predNote?: string | null
}

export interface RosterSlotDef {
  name: string
  count: number
  eligible: string[]
  bench: boolean
}

export interface LeagueConfigMeta {
  name: string
  label: string
  ppr: string
  superflex: boolean
  description: string
  roster: RosterSlotDef[]
  /** Which FFC ADP sample this board's `adp` came from ("ppr" | "half-ppr" | "standard" | "2qb").
   *  Surfaced so the UI can name the reference instead of implying it is the user's exact format. */
  adpFormat?: string | null
}

/** NF3.4 — the plain-language label + description for one FEATURE key, shared across every player's
 *  `contrib.drivers[].feature` — kept once here (the manifest's `featureLegend`) rather than repeated
 *  on every player record. */
export interface FeatureLegendEntry {
  label: string
  description: string
}

export interface Manifest {
  season: number
  generated_at: string
  source: string
  positions: string[]
  sizes: number[]
  configs: LeagueConfigMeta[]
  /** NF1.5b — which projection lineage EVERY blob in this export came from: `"nf1_5"` (the
   *  market-aware refined board, the served default since the NF1.5b re-land) or `"mvp1"` (the
   *  market-blind board). Optional: absent on an export made before NF1.5b. */
  projectionSource?: string | null
  projectionLabel?: string | null
  /** Provenance for the projections blob, mirrored into the manifest so a board-only surface can
   *  carry the model's own caveats without fetching `projections.json`. Null until that blob
   *  exports; absent entirely on a pre-NF3 manifest. */
  projections?: {
    players: number
    model_version?: string | null
    base_season?: number | null
    adp_format?: string | null
    adp_teams?: number | null
    /** NF1.5b — `{position -> market lean}` and the standing caveat sentence. See `MarketLeanNote`. */
    projection_source?: string | null
    projection_label?: string | null
    market_lean?: Record<string, string> | null
    market_lean_note?: string | null
  } | null
  /** NF3.4 — `{feature key -> label/description}` for every feature a player's `contrib.drivers` can
   *  reference. Optional: absent on a manifest exported before this shipped, or if the underlying
   *  artifact hadn't been (re-)built at export time. */
  featureLegend?: Record<string, FeatureLegendEntry> | null
  /** NF3.4 — provenance for the contributions data (which model, which season, when built) — kept
   *  separate from the per-player payload so the page can show/hide the panel without waiting on
   *  `projections.json`. */
  featureContributionsMeta?: {
    model_version: string
    generated_at: string
    base_season: number
    projection_season: number
    n_players: number
  } | null
}

const NEED_W_DEDICATED = 1.0
const NEED_W_FLEX = 0.4
const SURPLUS_BASE = 0.5
const SURPLUS_OVER = 0.35
const SURPLUS_CAP = 0.9
const BYE_PEN_FRAC = 0.08
const BYE_CLUSTER_CAP = 3

export interface RosterRequirements {
  dedicated: Record<string, number>
  flex: { eligible: Set<string>; count: number }[]
  bench: number
}

export function rosterRequirements(roster: RosterSlotDef[]): RosterRequirements {
  const dedicated: Record<string, number> = {}
  const flex: { eligible: Set<string>; count: number }[] = []
  let bench = 0
  for (const s of roster) {
    if (s.bench) {
      bench += s.count
      continue
    }
    if (s.eligible.length === 1) {
      dedicated[s.eligible[0]] = (dedicated[s.eligible[0]] ?? 0) + s.count
    } else if (s.eligible.length > 1) {
      flex.push({ eligible: new Set(s.eligible), count: s.count })
    }
  }
  return { dedicated, flex, bench }
}

export interface OpenSlots {
  dedicated: Record<string, number>
  flex: Set<string>[]
}

// need level: 2 = fills an open DEDICATED starter; 1 = fills only an open FLEX/superflex; 0 = none open
export function needLevel(open: OpenSlots, position: string): number {
  if ((open.dedicated[position] ?? 0) > 0) return 2
  if (open.flex.some((e) => e.has(position))) return 1
  return 0
}

// Greedily assign already-drafted positions to my starter slots (dedicated first, then most-restrictive
// flex) and return what's still open — mirrors the Python `open_starter_slots`.
export function openStarterSlots(myPositions: string[], req: RosterRequirements): OpenSlots {
  const openDed: Record<string, number> = { ...req.dedicated }
  const counts: Record<string, number> = {}
  for (const p of myPositions) counts[p] = (counts[p] ?? 0) + 1

  for (const pos of Object.keys(openDed)) {
    const take = Math.min(openDed[pos], counts[pos] ?? 0)
    openDed[pos] -= take
    counts[pos] = (counts[pos] ?? 0) - take
  }

  const flexSpots: Set<string>[] = []
  for (const f of req.flex) for (let i = 0; i < f.count; i++) flexSpots.push(f.eligible)
  flexSpots.sort((a, b) => a.size - b.size)

  const openFlex: Set<string>[] = []
  for (const elig of flexSpots) {
    let filler: string | null = null
    // prefer the scarcest surplus (fewest held) — same ordering intent as the Python
    const eligPositions = [...elig].sort((a, b) => (counts[a] ?? 0) - (counts[b] ?? 0))
    for (const pos of eligPositions) {
      if ((counts[pos] ?? 0) > 0) {
        filler = pos
        break
      }
    }
    if (filler) counts[filler] -= 1
    else openFlex.push(elig)
  }

  const dedicated: Record<string, number> = {}
  for (const [p, n] of Object.entries(openDed)) if (n > 0) dedicated[p] = n
  return { dedicated, flex: openFlex }
}

// Tier numbers (1 = best) for a DESCENDING points list: a new tier starts at an unusually-large gap
// (> mean + k*std of consecutive gaps). Sample-robust, no magic threshold.
export function assignTiers(pointsDesc: number[], k = 1.0): number[] {
  const n = pointsDesc.length
  if (n === 0) return []
  if (n === 1) return [1]
  const gaps: number[] = []
  for (let i = 0; i < n - 1; i++) gaps.push(Math.max(0, pointsDesc[i] - pointsDesc[i + 1]))
  const mean = gaps.reduce((a, b) => a + b, 0) / gaps.length
  const varc = gaps.reduce((a, b) => a + (b - mean) ** 2, 0) / gaps.length
  const std = Math.sqrt(varc)
  const thr = mean + k * std
  const tiers = [1]
  let t = 1
  for (const g of gaps) {
    if (g > thr && g > 1e-9) t += 1
    tiers.push(t)
  }
  return tiers
}

/** Tiers for one already-scoped slice of the board (e.g. one position's rows, or the whole board
 *  for an overall/VOR view), keyed by player id. Mirrors the Rankings board's tier computation
 *  (NF3): only above-replacement, genuinely-predictable rows are tiered — a tier break below
 *  replacement or inside a near-flat/noisy field (K/DST) is not a real signal. `metric` picks the
 *  ranking axis: VOR for a cross-position view, league points within a single position. */
export function positionTierMap(
  rows: Player[],
  metric: (p: Player) => number,
  lowPredictabilityPositions: readonly string[] = [],
): Map<string, number> {
  const m = new Map<string, number>()
  const draftable = rows.filter((p) => (p.vor ?? 0) > 0 && !lowPredictabilityPositions.includes(p.pos))
  if (draftable.length === 0) return m
  const sorted = draftable.slice().sort((a, b) => metric(b) - metric(a))
  const tiers = assignTiers(sorted.map(metric))
  sorted.forEach((p, i) => m.set(p.id, tiers[i] ?? 1))
  return m
}

export interface Recommendation {
  player: Player
  score: number
  needLevel: number
  needBonus: number
  positionalDropoff: number
  tier: number
  isLastInTier: boolean
  byeConflict: number
  rationale: string
}

const num = (v: number | null | undefined): number => (v == null || Number.isNaN(v) ? 0 : v)

export interface RecommendArgs {
  board: Player[]
  config: LeagueConfigMeta
  draftedIds: Set<string>
  myPlayerIds: string[]
  topN?: number
  tierK?: number
}

// Rank the still-available board players for MY next pick. Returns up to topN, sorted by score, each
// with a plain-language rationale. Deterministic + fast (a couple of passes over ≤~700 rows).
export function recommend(args: RecommendArgs): Recommendation[] {
  const { board, config, draftedIds, myPlayerIds, topN = 8, tierK = 1.0 } = args
  const req = rosterRequirements(config.roster)
  const mine = new Set(myPlayerIds)

  const myPositions: string[] = []
  const myByes = new Map<string, number>() // `${pos}|${bye}` → count I already hold
  const available: Player[] = []
  for (const p of board) {
    if (draftedIds.has(p.id)) {
      if (mine.has(p.id)) {
        myPositions.push(p.pos)
        if (p.bye != null) myByes.set(`${p.pos}|${p.bye}`, (myByes.get(`${p.pos}|${p.bye}`) ?? 0) + 1)
      }
      continue
    }
    if (p.vor == null) continue // genuinely unprojected (a gap-fill placeholder) — never recommended
    available.push(p)
  }
  const open = openStarterSlots(myPositions, req)

  const myCounts: Record<string, number> = {}
  for (const p of myPositions) myCounts[p] = (myCounts[p] ?? 0) + 1

  // per-position available lists (points-descending) → tiers + next-available VOR
  const byPos: Record<string, Player[]> = {}
  for (const p of available) (byPos[p.pos] ??= []).push(p)
  const tierOf: Record<string, number> = {}
  const nextVor: Record<string, number> = {}
  const idxInPos: Record<string, number> = {}
  for (const pos of Object.keys(byPos)) {
    const rows = byPos[pos].sort((a, b) => num(b.pts) - num(a.pts))
    const tiers = assignTiers(rows.map((r) => num(r.pts)), tierK)
    for (let i = 0; i < rows.length; i++) {
      tierOf[rows[i].id] = tiers[i]
      idxInPos[rows[i].id] = i
      nextVor[rows[i].id] =
        i + 1 < rows.length ? num(rows[i + 1].vor) : num(rows[i].repl) - num(rows[i].pts)
    }
  }

  const recs: Recommendation[] = []
  for (const p of available) {
    const vor = num(p.vor)
    const dropoff = Math.max(0, vor - (nextVor[p.id] ?? 0))
    const level = needLevel(open, p.pos)
    const needW = level === 2 ? NEED_W_DEDICATED : level === 1 ? NEED_W_FLEX : 0
    const needBonus = needW * dropoff

    const held = myCounts[p.pos] ?? 0
    const capacity =
      (req.dedicated[p.pos] ?? 0) + req.flex.reduce((a, f) => a + (f.eligible.has(p.pos) ? f.count : 0), 0)
    let surplusPen = 0
    if (level === 0 && vor > 0) {
      const frac = SURPLUS_BASE + (held >= capacity ? SURPLUS_OVER : 0)
      surplusPen = Math.min(SURPLUS_CAP, frac) * vor
    }
    // bye-week stacking: penalize by how many I already hold at this position on the same bye week
    const byeConflict = p.bye != null ? myByes.get(`${p.pos}|${p.bye}`) ?? 0 : 0
    const byePen = byeConflict > 0 && vor > 0 ? BYE_PEN_FRAC * Math.min(byeConflict, BYE_CLUSTER_CAP) * vor : 0
    const score = vor + needBonus - surplusPen - byePen

    const rows = byPos[p.pos]
    const i = idxInPos[p.id]
    const isLast = i === rows.length - 1 || tierOf[rows[i + 1].id] !== tierOf[p.id]

    recs.push({
      player: p,
      score: Math.round(score * 10) / 10,
      needLevel: level,
      needBonus: Math.round(needBonus * 10) / 10,
      positionalDropoff: Math.round(dropoff * 10) / 10,
      tier: tierOf[p.id] ?? 1,
      isLastInTier: isLast,
      byeConflict,
      rationale: rationale(p.pos, level, needBonus, dropoff, isLast, tierOf[p.id] ?? 1, surplusPen, p.bye, byeConflict),
    })
  }

  recs.sort((a, b) => b.score - a.score)
  return recs.slice(0, topN)
}

function rationale(
  pos: string,
  level: number,
  needBonus: number,
  dropoff: number,
  lastInTier: boolean,
  tier: number,
  surplusPen: number,
  bye: number | null,
  byeConflict: number
): string {
  const parts: string[] = []
  if (level === 2) parts.push(`Fills your open ${pos} starter`)
  else if (level === 1) parts.push(`Fills an open FLEX (${pos}-eligible)`)
  if (lastInTier && dropoff > 0) parts.push(`Last of Tier ${tier} — ${Math.round(dropoff)} VOR cliff to the next ${pos}`)
  else if (dropoff > 0 && needBonus > 0) parts.push(`+${Math.round(dropoff)} VOR over the next ${pos}`)
  if (surplusPen > 0) parts.push(`Depth pick — ${pos} starters already set`)
  if (byeConflict > 0 && bye != null) parts.push(`⚠ ${byeConflict} other ${pos} on bye ${bye}`)
  if (parts.length === 0) parts.push("Best value on the board (VOR)")
  return parts.join(" · ")
}

// ── snake-draft helpers ────────────────────────────────────────────────────────────────────────
export function overallPickFor(teamSlot: number, nTeams: number, round: number): number {
  if (round % 2 === 1) return (round - 1) * nTeams + teamSlot
  return (round - 1) * nTeams + (nTeams - teamSlot + 1)
}

export function myUpcomingPicks(teamSlot: number, nTeams: number, rounds: number): number[] {
  return Array.from({ length: rounds }, (_, r) => overallPickFor(teamSlot, nTeams, r + 1))
}

// How many OTHER picks happen before my next turn (0 = on the clock).
export function picksUntilNext(
  teamSlot: number,
  nTeams: number,
  currentOverallPick: number,
  rounds = 40
): number {
  for (const p of myUpcomingPicks(teamSlot, nTeams, rounds)) {
    if (p >= currentOverallPick) return p - currentOverallPick
  }
  return 0
}

// Which team is on the clock at a given 1-indexed overall pick, in a snake order.
export function slotOnClock(overallPick: number, nTeams: number): number {
  const round = Math.floor((overallPick - 1) / nTeams) + 1
  const posInRound = ((overallPick - 1) % nTeams) + 1
  return round % 2 === 1 ? posInRound : nTeams - posInRound + 1
}
