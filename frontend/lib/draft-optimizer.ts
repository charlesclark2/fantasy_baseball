// draft-optimizer.ts — the LIVE draft optimizer, a faithful TS port of the validated Python engine
// (quant_sports_intel_models/fantasy_engine/draft.py). Kept in lock-step with it: same need model,
// same VONA/tier-cliff signals, same additive (never multiplicative) scoring so VOR points stay
// comparable. Pure + synchronous → every pick recomputes instantly, no server round-trip.
//
//   score = vor + need_bonus            (need_bonus = 0 when the position's starter slots are full)
//   need_bonus = NEED_W[level] * urgency              (VONA — value lost at the slot if you wait)
//
// where `urgency` is measured over the pool that can actually fill the OPEN SLOT: within the
// position for a DEDICATED starter, across the whole FLEX-eligible pool for a flex slot. See
// `flexPoolDropoff` below — a within-position gap is the wrong denominator for a flex seat.
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
  /** E9.56 — the server withheld this season's model output from this caller. The row keeps its
   *  public identity (name/pos/team/bye/ADP) and carries NO `pts`/`vor`/`posRank`/`ovrRank`, so a
   *  "subscribe to unlock" chip renders in each value cell. Optional: absent on an entitled
   *  response, which is byte-identical to what this surface has always received. */
  locked?: boolean
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
  /** Freemium build (2026-08-08) — whether this preset is the FREE one. Server-stamped in
   *  `entitlement.open_manifest_payload`, identically for every caller, so the paywall is stated in
   *  one place instead of being re-derived from a hardcoded format name in the client.
   *
   *  ⚠️ OPTIONAL, and `undefined` must be read as NOT free (see `isFreeConfig`): this key is absent
   *  from any manifest served by a Lambda that predates the deploy, and during that skew window the
   *  safe reading is the restrictive one — a locked control on a board the user can in fact see is
   *  a cosmetic bug, while an open control on one they cannot is a 403 with no explanation. */
  free?: boolean
}

/** NF3.4 — the plain-language label + description for one FEATURE key, shared across every player's
 *  `contrib.drivers[].feature` — kept once here (the manifest's `featureLegend`) rather than repeated
 *  on every player record. */
export interface FeatureLegendEntry {
  label: string
  description: string
}

/** NF-FRESH2 — one market source's own as-of stamp, read from the snapshot the build consumed.
 *  ⚠️ `asOf` is the vintage of the DATA, never the build. A build date is true of the projection
 *  and can be false of the ADP column beside it — which is exactly the defect these exist to fix. */
export interface MarketAsOf {
  source: string
  /** ISO date. For ADP this is FFC's `end_date` — the LAST day of the rolling draft window the
   *  average covers, i.e. the newest real information in the number. */
  as_of: string
  window_start?: string | null
  window_end?: string | null
  drafts?: number | null
  scoring?: string | null
  format?: string | null
  teams?: number | null
  /** FantasyPros' own bare "7/26" label, year-less by their choice — kept for reconciliation
   *  against their page, never for sorting or rendering. */
  label?: string | null
  experts?: number | null
}

/** NF-FRESH2 — the full per-input provenance block. Every field is optional and every value may be
 *  null, and the two mean DIFFERENT things (NF-C0 skew + NF1.7(a)):
 *    • the key is ABSENT  → this payload predates the stamps; claim nothing, render nothing.
 *    • the value is NULL  → we looked and could not tell; render "unknown", never "fresh". */
export interface FreshnessBlock {
  adp?: MarketAsOf | null
  ecr?: MarketAsOf | null
  adp_by_sample?: Record<string, MarketAsOf | null> | null
  input_vintage?: {
    depth_chart_as_of?: string | null
    sleeper_status_as_of?: string | null
  } | null
  projection_built_at?: string | null
  /** Whether THIS build was allowed to re-fetch the market. False on a `--no-market-refresh`
   *  reproduction run, and on any historical season (the E5.9 backfill boundary). */
  market_refresh?: boolean | null
}

export interface Manifest {
  season: number
  generated_at: string
  source: string
  /** NF-FRESH2 — the two dates a surface renders beside the ADP column. See `FreshnessBlock` for
   *  what an absent key vs a null value each mean. */
  adp_as_of?: string | null
  ecr_as_of?: string | null
  freshness?: FreshnessBlock | null
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
  // ── E9.56: the server-side entitlement envelope ────────────────────────────────────────────
  // The board endpoint returns a bare ARRAY (no room for an envelope without the NF-C0 shape
  // break), so the PAGE-level lock state travels on the manifest — which every board surface
  // already loads. All optional: absent ⇒ entitled, the shape the pre-E9.56 backend always sent.
  /** True when the server withheld this season's model output from this caller. */
  locked?: boolean
  /** Stated explicitly so a dropped field can never read as entitled (E9.41). */
  entitled?: boolean
  lockedSeason?: number
  upgrade?: { reason: string; message: string; ctaHref: string }
  /** NF3.4 — `{feature key -> label/description}` for every feature a player's `contrib.drivers` can
   *  reference. Optional: absent on a manifest exported before this shipped, or if the underlying
   *  artifact hadn't been (re-)built at export time. Also absent on a LOCKED manifest — it exists
   *  only to label the entitled attribution panel (E9.56 payload minimization). */
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
  /** Freemium build — which single (config, size) preset board is free, server-stamped identically
   *  for every caller. The client uses it to DEFAULT an unentitled visitor onto a board they can
   *  actually read, and to lock the size control. Absent on a pre-deploy manifest ⇒ treat nothing
   *  as free-by-name and fall back to `free` on each config (see `freeSelection`). */
  freeBoard?: { config: string; size: number } | null
}

/** The free (config, size) preset, or null if this manifest doesn't say.
 *
 * ⚠️ Read through this rather than reaching for `manifest.freeBoard` directly: during the deploy
 * skew window (frontend ships on merge, the API only on `deploy.sh` — NF-C0) the key is absent, and
 * the honest answer is "unknown", not a guessed default. Callers decide what to do with null; what
 * they must NOT do is invent `full_ppr`/12 locally, because then the paywall is stated in two
 * places and only one of them is deployed.
 */
export function freeSelection(manifest: Manifest | undefined | null) {
  const fb = manifest?.freeBoard
  if (!fb || typeof fb.config !== "string" || typeof fb.size !== "number") return null
  return { config: fb.config, size: fb.size }
}

/** Whether a preset NAME is the free one. `undefined` ⇒ false — see the note on `free`. */
export function isFreeConfig(config: LeagueConfigMeta | undefined | null): boolean {
  return config?.free === true
}

const NEED_W_DEDICATED = 1.0
/** Exported for `scripts/measure-flex-urgency.mjs`, which reconstructs the pre-flex-pool ordering
 *  from a `Recommendation` to count how often the rule below changes the top pick. */
export const NEED_W_FLEX = 0.4
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
//
// ⭐ NF-D19: a real gap can still cliff off a tier of exactly one player (T1=Bijan, T2=Chase, ...),
// which reads as broken rather than as a signal — a "tier" of one is not a group. The first cut of
// this fix enforced a flat minimum size (3) — but a flat floor only merges the tiny groups; it does
// nothing about the mirror problem, a long flat stretch (no gap ever clears the threshold) collapsing
// into ONE undifferentiated tier that can swallow most of a position (full-PPR WR: nearly the whole
// position landed in just two tiers). So both bounds are enforced, and both SCALE WITH THE POOL SIZE
// (`n`) rather than being a fixed count — a ~20-player TE pool and an ~84-player Overall board should
// not use the same absolute floor/ceiling:
//   minSize = max(2, round(n * MIN_TIER_FRAC))     — a tier below this merges into its neighbor
//   maxSize = max(minSize + 1, round(n * MAX_TIER_FRAC)) — a tier above this is split further
// MIN_TIER_FRAC/MAX_TIER_FRAC (4%/15%) target roughly 7-25 tiers regardless of n. An oversized group
// is split at its OWN largest internal gaps (recursively, largest first) rather than sliced evenly by
// count — the split points still come from the data, they just use a per-group relative threshold
// instead of the whole-pool mean+k·std one. A split is skipped if it would leave either side under
// `minSize` (the min is the harder constraint; an oversized-but-otherwise-unsplittable tail is left
// as is rather than manufacturing a below-floor sliver).
const MIN_TIER_FRAC = 0.04
const MAX_TIER_FRAC = 0.15

export function assignTiers(pointsDesc: number[], k = 1.0): number[] {
  const n = pointsDesc.length
  if (n === 0) return []
  if (n === 1) return [1]
  const minSize = Math.max(2, Math.round(n * MIN_TIER_FRAC))
  const maxSize = Math.max(minSize + 1, Math.round(n * MAX_TIER_FRAC))

  const gaps: number[] = []
  for (let i = 0; i < n - 1; i++) gaps.push(Math.max(0, pointsDesc[i] - pointsDesc[i + 1]))
  const mean = gaps.reduce((a, b) => a + b, 0) / gaps.length
  const varc = gaps.reduce((a, b) => a + (b - mean) ** 2, 0) / gaps.length
  const std = Math.sqrt(varc)
  const thr = mean + k * std

  // Raw gap-based groups — each a contiguous run of indices into `pointsDesc`.
  const groups: number[][] = [[0]]
  for (let i = 0; i < gaps.length; i++) {
    if (gaps[i] > thr && gaps[i] > 1e-9) groups.push([i + 1])
    else groups[groups.length - 1].push(i + 1)
  }

  // Pass 1 — fold any undersized group into its neighbor.
  const merged: number[][] = []
  for (const g of groups) {
    if (merged.length > 0 && merged[merged.length - 1].length < minSize) {
      merged[merged.length - 1].push(...g)
    } else {
      merged.push(g)
    }
  }
  if (merged.length > 1 && merged[merged.length - 1].length < minSize) {
    const last = merged.pop() as number[]
    merged[merged.length - 1].push(...last)
  }

  // Pass 2 — split any oversized group at its largest internal gap(s), recursively, until every
  // piece is at or under `maxSize` or no further split can respect `minSize` on both sides.
  const splitOversized = (g: number[]): number[][] => {
    if (g.length <= maxSize) return [g]
    let bestPos = -1
    let bestGap = -Infinity
    for (let pos = minSize; pos <= g.length - minSize; pos++) {
      const gapVal = gaps[g[pos - 1]] // the gap between g[pos-1] and g[pos] — a contiguous run
      if (gapVal > bestGap) {
        bestGap = gapVal
        bestPos = pos
      }
    }
    if (bestPos === -1) return [g] // can't split without leaving a sliver under minSize
    return [...splitOversized(g.slice(0, bestPos)), ...splitOversized(g.slice(bestPos))]
  }
  const final = merged.flatMap(splitOversized)

  const tiers = new Array<number>(n)
  final.forEach((g, t) => g.forEach((idx) => (tiers[idx] = t + 1)))
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
  /** The base the score is built on: plain VOR, except for a FLEX-only candidate, where it is
   *  points over the FLEX SEAT's replacement (see the note in `recommend`). Exposed so the exact
   *  pre-flex-seat ordering stays reconstructible from a `Recommendation` alone — that is what
   *  `scripts/measure-flex-urgency.mjs` counts flips with, instead of keeping a forked copy of the
   *  engine that could drift away from the one being measured. */
  seatValue: number
  positionalDropoff: number
  tier: number
  isLastInTier: boolean
  byeConflict: number
  /** The reserve constraint is binding and this player fills one of the open starter slots — i.e.
   *  every remaining pick is now spoken for, so passing on all of these strands a slot empty. False
   *  for every candidate whenever there is slack. */
  mustFill: boolean
  /** A low-predictability position (K/DST — the exporter's own `lowPred`), held back until the
   *  roster actually requires it. See the note on the sort. */
  deferred: boolean
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
// ── the BEST-AVAILABLE board ordering ────────────────────────────────────────────────────────────

export type BoardSortCol = "ovrRank" | "pts" | "vor"

export interface SortAvailableOpts {
  sortCol: BoardSortCol
  sortDir: "asc" | "desc"
  /** Whether low-predictability rows (K/DST) are held below every real candidate.
   *
   *  ⚠️ MUST be false when the user has explicitly filtered to K or D/ST — they asked for those
   *  rows, and burying them inside their own filtered view would be perverse. Everywhere else (the
   *  mixed "ALL" view) it must be true; see the note below. */
  deferLowPred: boolean
}

/**
 * Order the "Available players" board — the cheat sheet a user reads when they DON'T take the
 * recommendation.
 *
 * ⭐ THIS EXISTS AS A SHARED FUNCTION BECAUSE THE RULE HAS TO HOLD ON BOTH SURFACES. `recommend`
 * defers K/DST (their VOR is not comparable across positions — the whole above-replacement range is
 * 8.1 at K and 10.4 at D/ST against a median 80% interval of 118.7 / 87.3 on a single player). But
 * the board was sorted INLINE in the component by raw `ovrRank`/`pts`/`vor`, so the same D/ST that
 * had just been pushed out of the recommendations reappeared at the top of best-available — reported
 * live 2026-08-13 with PIT D/ST at #56, level with WRs on VOR 6. Fixing one surface and not the
 * other leaves the user exactly one click from the advice we decided not to give.
 *
 * ⚠️ WHY THE OLD INLINE SORT LOOKED FINE. Its comment read "null pts/vor (K/DST) always sort to the
 * bottom regardless of direction" — TRUE when MVP-3 shipped K/DST as null-VOR placeholders, and
 * silently false from NF1.6 on, when they gained real numbers and started interleaving. The same
 * stale pre-NF1.6 assumption that produced the recommendation bug, in a second place.
 */
export function sortAvailable(rows: Player[], opts: SortAvailableOpts): Player[] {
  const { sortCol, sortDir, deferLowPred } = opts
  const sign = sortDir === "asc" ? 1 : -1
  const val = (p: Player) => (sortCol === "ovrRank" ? p.ovrRank : sortCol === "pts" ? p.pts : p.vor)
  return [...rows].sort((a, b) => {
    // The deferral outranks the chosen column, so it holds under EVERY sort the header offers —
    // including an explicit VOR-descending click, which is precisely the ordering that surfaced the
    // D/ST in the first place.
    if (deferLowPred && (a.lowPred === true) !== (b.lowPred === true)) return a.lowPred === true ? 1 : -1
    const av = val(a),
      bv = val(b)
    // A genuinely unprojected gap-fill row (null pts/vor) still sinks regardless of direction.
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return (av - bv) * sign
  })
}

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

  // ── THE RESERVE CONSTRAINT: a mandatory starter slot may never be left unfilled ────────────────
  //
  // An empty starter slot scores ZERO on Sunday, so once my remaining picks are all needed to fill
  // my open starter slots, bench depth is not a trade-off any more — it is strictly dominated, and
  // every remaining pick MUST fill a slot. Without this the optimizer walks a user into an illegal
  // roster: measured on the live 2026 full_ppr/12 board, with every above-replacement RB gone and
  // both RB slots open, the best available RB ranked #86 of 834 and a surplus-penalized BACKUP QB
  // (vor 25.2, kept 10% of its value by `SURPLUS_CAP`) out-scored it. The draft ended 7/9.
  //
  // ⭐ EXACT, NOT A HEURISTIC — it binds if and only if taking a non-filler PROVABLY strands a slot,
  // so it cannot distort normal drafting. With slack it is inert; with none it is total. Deliberately
  // NO safety margin: any reserve > 0 would start overriding real value judgements on a guess, and
  // "grab a filler a round early" is a preference, while "do not end the draft with an empty starter
  // slot" is a correctness property. That is the only one enforced here.
  //
  // Everything it needs is DERIVED (roster size from the config, picks made from `myPlayerIds`), so
  // `recommend`'s signature is unchanged — no caller has to be taught to pass draft state, which is
  // exactly how a constraint like this ends up enforced on some surfaces and not others.
  //
  // ⚠️ It RANKS, never FILTERS. If no filler exists at all (a position exhausted), the caller still
  // gets its best available options rather than an empty list.
  const totalSlots = config.roster.reduce((a, s) => a + s.count, 0)
  const picksRemaining = totalSlots - myPlayerIds.length
  const openStarterCount =
    Object.values(open.dedicated).reduce((a, n) => a + n, 0) + open.flex.length
  const mustFillNow = openStarterCount > 0 && picksRemaining <= openStarterCount

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

  // ⭐⭐ FLEX URGENCY IS MEASURED OVER THE FLEX POOL, NOT WITHIN THE POSITION (operator, 2026-08-17,
  // off a real mock draft: "it seemed to really be pushing for TEs to fill my FLEX spot, which seems
  // unrealistic unless they're projected to outscore RBs and WRs").
  //
  // VONA asks "what do I lose at this SLOT if I wait?" — so the right denominator is whatever can
  // still fill the slot next time. For a DEDICATED starter that is the next player at the same
  // position, which is what `nextVor` measures. For a FLEX seat it is the next FLEX-ELIGIBLE player
  // at ANY of its positions, and using the within-position gap there is a units error with a
  // systematic direction: TE is the thinnest position on the board, so its cliffs are structurally
  // the steepest, and the best available TE collected `0.4 x (a steep TE cliff)` for a seat a WR two
  // VOR behind him would have filled almost as well.
  //
  // ⚠️⚠️ MEASURED, AND THE MEASUREMENT SAYS THIS HALF DOES NOTHING. `scripts/measure-flex-urgency.mjs`
  // over 200 drafts x 15 rounds of the served 2026 full_ppr/12 board: reverting this rule on its own
  // changes the #1 recommendation on 0 of 3,000 decision points. The flex bonus is capped by
  // `NEED_W_FLEX` at ~5 VOR and the gaps it competes against are far wider, so it was never the
  // mechanism behind the reported TE-for-FLEX push — the base re-basing below is. This is kept
  // because it is the correct denominator for a flex seat and it is free, NOT because it fixed
  // anything, and saying so is the point: a plausible mechanism that measured inert is a finding,
  // and quietly banking it as the fix would have left the real one in place.
  //
  // ⛔ NOT a TE penalty, and not a weight change. `NEED_W_FLEX` is untouched; only the quantity it
  // multiplies moves onto the pool the slot actually draws from. And the DEDICATED TE slot is
  // unaffected: `needLevel` returns 2 there, so taking the best TE before the TE cliff is still the
  // full-weight advice.
  //
  // ⚠️ The bonus is still awarded only to the best available player at each position (`idxInPos === 0`
  // — the K/DST inversion fix above), which this rule does not weaken: within a position the pts and
  // VOR orders are identical (`vor = pts - repl`, one `repl` per position), so a position's leader is
  // the only member that can ever top the pool.
  // ⭐⭐⭐ AND THE VALUE ITSELF IS RE-BASED ON THE SEAT, BECAUSE VOR IS NOT A FAIR FLEX COMPARATOR.
  //
  // This is the bigger half, and it is the one the measurement actually implicates. VOR is
  // points-over-REPLACEMENT-AT-HIS-OWN-POSITION, which is exactly right for a DEDICATED slot — you
  // must start a TE, so a TE's worth is against other TEs. It is the wrong unit for a FLEX seat,
  // because the seat does not care which position walks into it: it collects POINTS.
  //
  // Measured on the served 2026 full_ppr/12 board, replacement is RB 150.1 / WR 148.3 / TE 130.4.
  // That gap is structural, not noise: the twelve flex seats in a 12-team league are allocated to
  // whichever position has the best next man, TE13 (130.4) never wins one, so TE replacement stays
  // at TE12 while RB/WR replacement is pushed ~19 points deeper. Which means plain VOR hands every
  // TE a ~19.7-point head start in a flex comparison he does not deliver in the lineup: Trey
  // McBride (239.0 pts, VOR 108.7) outranks a WR projected for 257 points, and the WR is the one who
  // scores more in the seat. That is precisely the operator's report — TEs pushed into FLEX in the
  // middle rounds without projecting to outscore the RBs and WRs beside them.
  //
  // So a candidate whose ONLY open seat is a flex is scored against THE SEAT'S replacement: the best
  // freely-available player who could fill it, i.e. `max(repl)` over the seat's eligible positions —
  // a startable RB, not a startable TE. `pts - seatRepl` is then a common yardstick across the pool,
  // and comparing two flex candidates becomes comparing projected points, which is the operator's
  // own criterion.
  //
  // ⛔ NOT a change to VOR, and not a TE penalty. The published board, the rankings, every dedicated
  // slot and every bench pick are untouched — `seatValue` returns plain VOR for level 0 and level 2,
  // so this can only ever act on the one question it is about. A TE still wins a FLEX seat whenever
  // he out-projects the flex pool, and the DEDICATED TE slot still gets the full-weight "take the
  // best TE before the cliff" advice.
  //
  // MEASURED (`scripts/measure-flex-urgency.mjs`, 200 drafts x 15 rounds on the served board, run
  // BOTH ways because my own picks change which states the draft reaches):
  //
  //   driving with the new rule   181 of 3,000 decision points flip (6.0%)
  //   driving with the old rule   102 of 3,000 decision points flip (3.4%)
  //   the displaced pick          a TE at a FLEX seat in 181 of 181 and 102 of 102
  //   the round it happens in     3-7, and nowhere else
  //
  // Every flip carries a margin above 0.5 VOR, so none is an artifact of reading rounded fields
  // back. A change whose entire measured effect is the reported symptom, in the rounds it was
  // reported in, and nothing else.
  const replOf: Record<string, number> = {}
  for (const p of board) if (p.repl != null && !(p.pos in replOf)) replOf[p.pos] = p.repl
  /** The replacement level of the best FLEX seat this position can still fill — `null` when it has
   *  no open flex seat, which is every level-0 and level-2 candidate. `min` over the open seats
   *  because the player gets to pick his best one; `max` within a seat because he can be displaced
   *  by any eligible replacement-level player. */
  const flexSeatRepl: Record<string, number> = {}
  for (const pos of Object.keys(byPos)) {
    if (needLevel(open, pos) !== 1) continue
    let best = Infinity
    for (const slot of open.flex) {
      if (!slot.has(pos)) continue
      let seat = -Infinity
      for (const e of slot) if (replOf[e] != null) seat = Math.max(seat, replOf[e])
      if (Number.isFinite(seat)) best = Math.min(best, seat)
    }
    if (Number.isFinite(best)) flexSeatRepl[pos] = best
  }
  /** What this player is worth in the seat he would actually occupy. Plain VOR everywhere except a
   *  flex-only candidate, where the baseline moves onto the seat (see the note above). */
  const seatValue = (p: Player): number =>
    flexSeatRepl[p.pos] != null ? num(p.pts) - flexSeatRepl[p.pos] : num(p.vor)

  const flexPoolDropoff: Record<string, number> = {}
  for (const pos of Object.keys(byPos)) {
    if (needLevel(open, pos) !== 1) continue
    const mine = byPos[pos]
    if (!mine.length) continue
    // The pool is every position accepted by an open flex slot THIS position could also fill — so a
    // superflex seat pulls QBs in, and a plain FLEX seat does not.
    const pool = new Set<string>()
    for (const slot of open.flex) if (slot.has(pos)) slot.forEach((e) => pool.add(e))
    // Best value still available for this seat AFTER passing on `mine[0]`: the next man at his own
    // position, or the leader at any other position the seat accepts. In `seatValue` units, so the
    // cross-position comparison is on one yardstick.
    let next = mine.length > 1 ? seatValue(mine[1]) : -Infinity
    for (const other of pool) {
      if (other === pos) continue
      const rows = byPos[other]
      if (rows?.length) next = Math.max(next, seatValue(rows[0]))
    }
    // Nothing else can fill the seat (the pool is down to one man) — fall back to the dedicated
    // measure, whose own last-player fallback is `repl - pts`.
    if (next === -Infinity) next = nextVor[mine[0].id] ?? 0
    flexPoolDropoff[pos] = Math.max(0, seatValue(mine[0]) - next)
  }

  const recs: Recommendation[] = []
  for (const p of available) {
    const vor = num(p.vor)
    const dropoff = Math.max(0, vor - (nextVor[p.id] ?? 0))
    const level = needLevel(open, p.pos)
    const needW = level === 2 ? NEED_W_DEDICATED : level === 1 ? NEED_W_FLEX : 0
    // ⭐ THE SCARCITY BONUS BELONGS TO THE POSITION, SO ONLY ITS BEST AVAILABLE PLAYER EARNS IT.
    // Awarding each player his OWN `dropoff` inverts a position, because `dropoff` is a pure GAP —
    // `max(0, vor - nextVor)` — that says nothing about what the candidate is worth. Whoever happens
    // to sit on the near side of a cliff collects the whole cliff, however bad he is.
    //
    // Measured on the live 2026 full_ppr/12 board (2026-08-12): the kicker pool cliffs 29.1 VOR
    // between the projected starters (~119 pts) and the deep backups (~90 pts). Andre Szmyt sat on
    // that edge at vor -10.8 and scored -10.8 + 29.1 = 18.3, beating Jake Bates — the BEST kicker on
    // the board, vor +8.1 — who scored 8.1 + 1.5 = 9.6. That put K31 at #66 overall and drafted him
    // in ROUND 6 of a 12-team snake.
    //
    // ⚠️ WHY IT SURVIVED TO HERE: MVP-3 shipped K/DST as null-VOR placeholders, which `recommend`
    // skips outright, so no sub-replacement tail was ever a candidate. NF1.6 gave K/DST a real BASE
    // projection and made the whole 42-deep kicker pool live — including the ~30 rows below
    // replacement the gap term was never designed for. The guard suite still fixtures K/DST as
    // null-VOR only (`test_null_vor_rows_never_recommended`), i.e. it tests the pre-NF1.6 world.
    //
    // ⛔ THE OBVIOUS PATCH — `vor > 0 ? needW * dropoff : 0` — IS WRONG TWICE, and both were caught
    // by measurement rather than by eye. (1) It does not remove the inversion, it MOVES it: with the
    // cliff one row higher the K just above it still outranks the best K (fixture: vor 3.9 beats vor
    // 8.2). (2) It BREAKS need-filling, which is a real requirement — late in a draft every player
    // left at a needed position is below replacement, and the roster still has to be filled;
    // `test_mock_snake_draft_replay` fails with "team 8 never drafted a TE".
    //
    // VONA answers "should I address this position NOW?", not "which player at it should I take?" —
    // that second question is always answered by VOR alone. So the urgency is computed once per
    // position, at the player you would actually draft (`idxInPos === 0`, the top of the same
    // pts-descending order used for tiers). Ordering within a position is then VOR-monotone BY
    // CONSTRUCTION — a worse player can no longer outrank a better one — while the best available at
    // a needed position keeps the full bonus even when he is below replacement, so a thin position
    // still gets filled.
    //
    // ⭐ `urgency` is the gap over the pool that can fill the OPEN SLOT (see `flexPoolDropoff`):
    // within-position for a dedicated starter, across the flex pool for a flex seat. `dropoff` stays
    // the within-position number because the tier-cliff line below is a genuine statement about the
    // position and is true regardless of which seat is open.
    const urgency = level === 1 ? flexPoolDropoff[p.pos] ?? dropoff : dropoff
    const needBonus = idxInPos[p.id] === 0 ? needW * urgency : 0

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
    // ⭐ `seatValue`, not `vor` — see the note above. Identical to `vor` for every candidate except a
    // flex-only one. (`surplusPen` is level-0-only and `byePen` scales a held-position stack, so both
    // stay on `vor`: they are statements about the roster, not about the open seat.)
    const base = seatValue(p)
    const score = base + needBonus - surplusPen - byePen

    const rows = byPos[p.pos]
    const i = idxInPos[p.id]
    const isLast = i === rows.length - 1 || tierOf[rows[i + 1].id] !== tierOf[p.id]

    // True only while the reserve constraint binds AND this player fills an open starter slot.
    // Everyone is `false` when there is slack, so the sort below is a no-op in the normal case.
    const mustFill = mustFillNow && level > 0
    // ⭐ K/DST ARE HELD BACK UNTIL THE ROSTER REQUIRES THEM. Read from the exporter's own `lowPred`
    // rather than a position list here — the flag's contract is that a consumer "never has to know
    // which positions are soft", and a hardcoded ["K","DST"] would silently miss a future one.
    const deferred = p.lowPred === true

    recs.push({
      player: p,
      score: Math.round(score * 10) / 10,
      needLevel: level,
      needBonus: Math.round(needBonus * 10) / 10,
      seatValue: Math.round(base * 10) / 10,
      positionalDropoff: Math.round(dropoff * 10) / 10,
      tier: tierOf[p.id] ?? 1,
      isLastInTier: isLast,
      byeConflict,
      mustFill,
      deferred,
      rationale: rationale(p.pos, level, needBonus, dropoff, urgency, base - vor, vor, isLast, tierOf[p.id] ?? 1, surplusPen, p.bye, byeConflict, mustFill, picksRemaining, openStarterCount),
    })
  }

  // ── the ordering, in three keys ────────────────────────────────────────────────────────────────
  //
  // 1. `mustFill` — a required filler outranks everything (the reserve constraint).
  // 2. `deferred` — a LOW-PREDICTABILITY position (K/DST) sits below every real candidate.
  // 3. `score`.
  //
  // ⭐ WHY (2) EXISTS. Recommending a D/ST in an early round destroys trust in every other
  // recommendation on the page, and it was happening: measured on the live 2026 full_ppr/12 board,
  // ROUND 6's six-slot panel came back FIVE-SIXTHS K/DST with DEN D/ST ranked #1 at score 12.2.
  //
  // It is not a scoring bug — it is VOR being read as comparable across positions where it is not.
  // The whole above-replacement VOR range is 8.1 at K and 10.4 at D/ST, against a MEDIAN 80%
  // interval of 118.7 and 87.3 points on a single player: a signal-to-noise of 0.07 and 0.12, versus
  // 0.55-0.61 at RB/WR/TE. Buying DST1 over DST12 is a ~10-point edge drawn from a distribution ~9x
  // wider than the edge, so it is not a distinction this projection can support — which is exactly
  // what the exporter states by stamping `lowPred` on those rows (and what `predNote` tells the user
  // in words: "use these as streaming TIERS, not precise ranks").
  //
  // ⛔ NOT A SCORE PENALTY, deliberately. A fudge factor large enough to sink K/DST would be a
  // number reverse-engineered from the answer, and it would corrupt `score` — which the UI shows and
  // the rationale explains. Deferral leaves every number honest and changes only the ORDER.
  //
  // ⚠️ THE TWO RULES COMPOSE, AND THE COMPOSITION IS WHAT MAKES ABSOLUTE DEFERRAL SAFE. Deferral has
  // no end-of-draft failure mode, because whenever K/DST are the only things a roster can still
  // accept, the bench is full ⇒ `picksRemaining == openStarterCount` ⇒ the reserve constraint is
  // NECESSARILY binding ⇒ `mustFill` lifts them straight back to the top. That is structural, not
  // luck. So: never early, always by the end — the operator's rule (2026-08-12) in two keys.
  recs.sort((a, b) => {
    if (a.mustFill !== b.mustFill) return a.mustFill ? -1 : 1
    if (a.deferred !== b.deferred) return a.deferred ? 1 : -1
    return b.score - a.score
  })
  return recs.slice(0, topN)
}

function rationale(
  pos: string,
  level: number,
  needBonus: number,
  dropoff: number,
  /** The gap the bonus was ACTUALLY computed from — see `urgency` at the call site. Equal to
   *  `dropoff` for a dedicated starter; the flex-pool gap for a flex seat. Passed separately so the
   *  sentence can never quote a number the score did not use. */
  urgency: number,
  /** `seatValue - vor` — how much the FLEX seat's own replacement re-bases this candidate. Always 0
   *  outside a flex-only candidate; negative for a position whose replacement sits below the seat's
   *  (TE, on every board measured so far). Stated in the sentence whenever it moves the score,
   *  because the panel shows `score` and an unexplained gap between it and the player's published
   *  VOR is exactly the kind of number a user is right not to trust. */
  seatAdj: number,
  vor: number,
  lastInTier: boolean,
  tier: number,
  surplusPen: number,
  bye: number | null,
  byeConflict: number,
  mustFill = false,
  picksRemaining = 0,
  openStarterCount = 0
): string {
  const parts: string[] = []
  // Leads the sentence when it applies: this is no longer a value judgement the user can weigh, so
  // saying WHY the tool stopped offering better-scoring bench players is the honest thing to show.
  if (mustFill) {
    const picks = `${picksRemaining} pick${picksRemaining === 1 ? "" : "s"} left`
    const slots = `${openStarterCount} starter slot${openStarterCount === 1 ? "" : "s"} still open`
    parts.push(`⚠ Must fill a starter — ${picks}, ${slots}`)
  }
  if (level === 2) parts.push(`Fills your open ${pos} starter`)
  else if (level === 1) parts.push(`Fills an open FLEX (${pos}-eligible)`)
  // The re-basing, whenever it is big enough to matter to the score on screen. ⚠️ SHORT ON PURPOSE:
  // it names the two numbers, and the WHY belongs in the panel's tooltip rather than repeated on
  // every row — the first cut spelled the whole mechanism out here, which both buried the rest of
  // the sentence and (with `truncate`) blew the page's width out. Numbers on the row, rule in the
  // tooltip.
  if (level === 1 && seatAdj < -0.5)
    parts.push(`Scored for the FLEX seat: ${Math.round(vor + seatAdj)}, not his ${Math.round(vor)} VOR`)
  if (lastInTier && dropoff > 0) parts.push(`Last of Tier ${tier} — ${Math.round(dropoff)} VOR cliff to the next ${pos}`)
  // ⚠️ QUOTES `urgency`, NOT `dropoff` — for a FLEX seat the bonus is the gap over the flex POOL, and
  // naming the (larger) within-position gap beside it would explain the score with a number the
  // score did not use. The wording names the pool too, so the two cases are not confusable.
  else if (urgency > 0 && needBonus > 0)
    parts.push(
      level === 1
        ? `+${Math.round(urgency)} VOR over the next FLEX-eligible player`
        : `+${Math.round(urgency)} VOR over the next ${pos}`,
    )
  if (surplusPen > 0) parts.push(`Depth pick — ${pos} starters already set`)
  if (byeConflict > 0 && bye != null) parts.push(`⚠ ${byeConflict} other ${pos} on bye ${bye}`)
  if (parts.length === 0) parts.push("Best value on the board (VOR)")
  return parts.join(" · ")
}

// ── roster assignment ──────────────────────────────────────────────────────────────────────────
//
// ⭐ THIS LIVES BESIDE `recommend` RATHER THAN IN A COMPONENT BECAUSE IT NOW HAS THREE CALLERS, AND
// they must agree. It was local to `draft-optimizer.tsx` while the live tool was the only surface
// that filled a roster. NF-C2.1 added two more readings of the same question — "which of a team's
// slots are still open?" (the mock-draft CPU's legality check) and "what do this team's starters
// project?" (the post-draft grade) — and a second implementation of slot assignment would let the
// CPU believe a roster is full while the panel shows it open, or grade a team on a lineup the tool
// would never have set. Same shape as `sortAvailable`: one rule, one function (E9.61).

export interface FilledSlot {
  slotName: string
  eligible: string[]
  player: Player | null
  bench: boolean
}

/** Greedily fit `myPlayers` into `roster`: best-VOR-first into dedicated slots, then the most
 *  restrictive flex, then the bench. Returns EVERY slot, filled or empty, in display order. */
export function assignRoster(myPlayers: Player[], roster: RosterSlotDef[]): FilledSlot[] {
  const pool = [...myPlayers].sort((a, b) => (b.vor ?? 0) - (a.vor ?? 0))
  const used = new Set<string>()
  const out: FilledSlot[] = []
  // expand slots: dedicated (1 eligible) first, then flex (by eligibility size), then bench
  const starters = roster.filter((s) => !s.bench)
  const dedicated = starters.filter((s) => s.eligible.length === 1)
  const flex = starters.filter((s) => s.eligible.length > 1).sort((a, b) => a.eligible.length - b.eligible.length)
  const take = (eligible: string[]): Player | null => {
    for (const p of pool) {
      if (!used.has(p.id) && eligible.includes(p.pos)) {
        used.add(p.id)
        return p
      }
    }
    return null
  }
  for (const grp of [dedicated, flex]) {
    for (const s of grp) {
      for (let i = 0; i < s.count; i++) {
        out.push({ slotName: s.name, eligible: s.eligible, player: take(s.eligible), bench: false })
      }
    }
  }
  // leftovers → bench rows (bench accepts whatever the config's bench slots accept — for the roster
  // fit-check; defaults to the skill positions).
  const benchSlots = roster.filter((s) => s.bench)
  const bench = benchSlots.reduce((a, s) => a + s.count, 0)
  const benchEligible = benchSlots.length
    ? Array.from(new Set(benchSlots.flatMap((s) => s.eligible)))
    : ["QB", "RB", "WR", "TE"]
  const leftover = pool.filter((p) => !used.has(p.id))
  for (let i = 0; i < Math.max(bench, leftover.length); i++) {
    out.push({ slotName: "BN", eligible: benchEligible, player: leftover[i] ?? null, bench: true })
  }
  return out
}

/** Positions a team's STILL-OPEN slots can accept (starters, flex and bench alike). Empty once the
 *  roster is full, which is how a caller tells "no legal pick exists" from "anything goes". */
export function openEligibility(myPlayers: Player[], roster: RosterSlotDef[]): Set<string> {
  const s = new Set<string>()
  for (const fs of assignRoster(myPlayers, roster)) if (!fs.player) fs.eligible.forEach((e) => s.add(e))
  return s
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
