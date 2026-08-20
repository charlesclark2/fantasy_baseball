// league-config.ts — NF-C0b: the SHARED league-settings contract, client side.
//
// This is a faithful TS mirror of `quant_sports_intel_models/fantasy_engine/league_config.py` +
// `settings.py` + the NFL policy in `football/nfl/fantasy/league_presets.py`, kept in lock-step with
// them exactly the way `draft-optimizer.ts` mirrors `fantasy_engine/draft.py`.
//
// ⚠️ THE CATALOG AND THE STAT-FIELD MAP BELOW ARE GUARD-TESTED against their Python originals by
// `betting_ml/tests/test_nf_c0b_league_settings.py` (fast gate). That test parses THIS FILE and fails
// on any drift in the term keys, their defaults, the FG fold table, or the stat→payload mapping. A
// hand-entered league and an imported one must produce the SAME object, so a second schema that
// quietly diverges is the one failure this story exists to prevent.

// ── the contract objects (JSON-identical to LeagueConfig.to_dict()) ───────────────────────────────
export interface ScoringRules {
  per_stat: Record<string, number>
  position_bonuses: Record<string, Record<string, number>>
}

export interface RosterSlotConfig {
  name: string
  count: number
  eligible: string[]
  bench: boolean
}

export interface LeagueConfig {
  format_version: string
  name: string
  sport: string
  n_teams: number
  ppr: string
  superflex: boolean
  description: string
  scoring: ScoringRules
  roster: RosterSlotConfig[]
  /** League rules captured for fidelity that the engine deliberately does NOT apply (median
   *  scoring, etc.). Nothing in scoring/VOR reads this — see the Python field's docstring. */
  captured_rules: Record<string, unknown>
  /** NF-C7b — how many of each position the user wants to finish the draft holding, for THIS
   *  league. `undefined`/absent means "never set" and inherits the account default;
   *  `{}` means "cleared for this league" and does not. `lib/depth-targets.ts` owns that rule. */
  depth_targets?: Record<string, number> | null
}

export const CONFIG_FORMAT_VERSION = "1.0"

// ── the editor catalog (mirror of league_presets.SCORING_CATALOG) ─────────────────────────────────
export interface StatTerm {
  key: string
  label: string
  group: string
  default: number
  help?: string
  /** Several keys one platform shows as a single control (a 7-tier points-allowed table over our
   *  nine buckets). Setting the group writes every member — an EXACT restatement, not a fold. */
  mergeGroup?: string
}

export const SCORING_CATALOG: StatTerm[] = [
  { key: "pass_yds", label: "Passing yards", group: "passing", default: 0.04, help: "Points per passing yard (0.04 = 1 per 25)." },
  { key: "pass_td", label: "Passing TD", group: "passing", default: 4 },
  { key: "pass_int", label: "Interception thrown", group: "passing", default: -2 },
  { key: "pass_cmp", label: "Completion", group: "passing", default: 0, help: "Some leagues add a per-completion bonus." },
  { key: "pass_att", label: "Pass attempt", group: "passing", default: 0 },
  { key: "pass_td_40p", label: "40+ yard passing TD bonus", group: "passing", default: 0, help: "Extra points for a touchdown pass of 40+ yards, on top of the passing-TD value." },

  { key: "rush_yds", label: "Rushing yards", group: "rushing", default: 0.1, help: "Points per rushing yard (0.1 = 1 per 10)." },
  { key: "rush_td", label: "Rushing TD", group: "rushing", default: 6 },
  { key: "rush_att", label: "Rush attempt", group: "rushing", default: 0 },
  { key: "rush_td_40p", label: "40+ yard rushing TD bonus", group: "rushing", default: 0, help: "Extra points for a rushing touchdown of 40+ yards, on top of the rushing-TD value." },

  { key: "rec", label: "Reception (PPR)", group: "receiving", default: 1, help: "1.0 full PPR, 0.5 half, 0 standard." },
  { key: "rec_yds", label: "Receiving yards", group: "receiving", default: 0.1 },
  { key: "rec_td", label: "Receiving TD", group: "receiving", default: 6 },
  { key: "targets", label: "Target", group: "receiving", default: 0 },
  { key: "rec_td_40p", label: "40+ yard receiving TD bonus", group: "receiving", default: 0, help: "Extra points for a receiving touchdown of 40+ yards, on top of the receiving-TD value." },

  { key: "two_pt", label: "2-point conversion", group: "misc", default: 2 },
  { key: "fumbles_lost", label: "Fumble lost", group: "misc", default: -2 },
  { key: "fumble_rec_td", label: "Fumble recovery TD", group: "misc", default: 6, help: "Offensive player recovering a fumble in the end zone." },
  { key: "st_player_td", label: "Return TD (player)", group: "misc", default: 6, help: "A kick/punt return TD credited to a skill player." },

  { key: "fg_made_0_19", label: "FG made 0-19", group: "kicking", default: 3 },
  { key: "fg_made_20_29", label: "FG made 20-29", group: "kicking", default: 3 },
  { key: "fg_made_30_39", label: "FG made 30-39", group: "kicking", default: 3 },
  { key: "fg_made_40_49", label: "FG made 40-49", group: "kicking", default: 4 },
  { key: "fg_made_50_59", label: "FG made 50-59", group: "kicking", default: 5 },
  { key: "fg_made_60p", label: "FG made 60+", group: "kicking", default: 5 },
  { key: "fg_missed", label: "FG missed", group: "kicking", default: 0, help: "Often -1; leave 0 if your league does not penalise." },
  { key: "pat_made", label: "PAT made", group: "kicking", default: 1 },
  { key: "pat_missed", label: "PAT missed", group: "kicking", default: 0 },

  { key: "def_td", label: "Defensive TD", group: "defense", default: 6 },
  { key: "st_td", label: "Special-teams TD (team)", group: "defense", default: 6 },
  { key: "def_sacks", label: "Sack", group: "defense", default: 1 },
  { key: "def_int", label: "Interception", group: "defense", default: 2 },
  { key: "def_fumble_rec", label: "Fumble recovered", group: "defense", default: 2 },
  { key: "def_forced_fumble", label: "Fumble forced", group: "defense", default: 0 },
  { key: "def_safety", label: "Safety", group: "defense", default: 2 },
  { key: "def_blocked_kick", label: "Blocked kick", group: "defense", default: 2 },

  { key: "dst_pa_g_0", label: "Points allowed 0", group: "dst_points_allowed", default: 5 },
  { key: "dst_pa_g_1_6", label: "Points allowed 1-6", group: "dst_points_allowed", default: 4 },
  { key: "dst_pa_g_7_13", label: "Points allowed 7-13", group: "dst_points_allowed", default: 3 },
  { key: "dst_pa_g_14_17", label: "Points allowed 14-17", group: "dst_points_allowed", default: 1, mergeGroup: "pa_14_20" },
  { key: "dst_pa_g_18_20", label: "Points allowed 18-20", group: "dst_points_allowed", default: 0, mergeGroup: "pa_14_20" },
  { key: "dst_pa_g_21_27", label: "Points allowed 21-27", group: "dst_points_allowed", default: 0 },
  { key: "dst_pa_g_28_34", label: "Points allowed 28-34", group: "dst_points_allowed", default: -1 },
  { key: "dst_pa_g_35_45", label: "Points allowed 35-45", group: "dst_points_allowed", default: -3, mergeGroup: "pa_35p" },
  { key: "dst_pa_g_46p", label: "Points allowed 46+", group: "dst_points_allowed", default: -5, mergeGroup: "pa_35p" },

  // NF-C0e — D/ST YARDS allowed. Defaults are 0 because a yards table is an opt-in a minority of
  // leagues set; seeding it non-zero would invent a rule for every league that does not have one.
  { key: "dst_ya_g_0_99", label: "Yards allowed under 100", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_100_199", label: "Yards allowed 100-199", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_200_299", label: "Yards allowed 200-299", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_300_349", label: "Yards allowed 300-349", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_350_399", label: "Yards allowed 350-399", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_400_449", label: "Yards allowed 400-449", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_450_499", label: "Yards allowed 450-499", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_500_549", label: "Yards allowed 500-549", group: "dst_yards_allowed", default: 0 },
  { key: "dst_ya_g_550p", label: "Yards allowed 550+", group: "dst_yards_allowed", default: 0 },
]

export const SCORING_GROUPS: { id: string; label: string }[] = [
  { id: "passing", label: "Passing" },
  { id: "rushing", label: "Rushing" },
  { id: "receiving", label: "Receiving" },
  { id: "misc", label: "Miscellaneous" },
  { id: "kicking", label: "Kicking (K)" },
  { id: "defense", label: "Team defense (D/ST)" },
  { id: "dst_points_allowed", label: "D/ST points allowed" },
  { id: "dst_yards_allowed", label: "D/ST yards allowed" },
]

/** Rules a real league has that do NOT move a per-player projection or replacement level. Stored in
 *  `captured_rules`, rendered as "captured, not applied" — never fed to the scorer. */
export const CAPTURED_RULE_CATALOG: { key: string; label: string; help: string }[] = [
  {
    key: "median_scoring",
    label: "Second matchup vs the league median",
    help:
      "A standings/schedule rule: each week you also play the league median. It changes WIN-LOSS " +
      "records, not what any player is projected to score, so it does not affect the board.",
  },
  {
    key: "fractional_scoring",
    label: "Fractional (decimal) scoring",
    help:
      "Recorded for fidelity. The board is computed in decimals regardless, so this changes nothing " +
      "about the ranking.",
  },
  {
    key: "playoff_weeks",
    label: "Playoff weeks",
    help:
      "Recorded for fidelity. Season-long projections are full-season totals, so the playoff " +
      "schedule does not enter the board.",
  },
]

// ── stat key → the projections-payload field that backs it ────────────────────────────────────────
// The TS analog of `NFL_PROFILE.stat_columns`. A key ABSENT from this map has no projection behind
// it, which is precisely what makes it CAPTURED rather than APPLIED — coverage is decided by this
// map plus the data actually present, never by a label someone wrote.
export const STAT_FIELD: Record<string, string> = {
  pass_att: "passAtt", pass_cmp: "passCmp", pass_yds: "passYds", pass_td: "passTd", pass_int: "passInt",
  rush_att: "rushAtt", rush_yds: "rushYds", rush_td: "rushTd",
  targets: "tgt", rec: "rec", rec_yds: "recYds", rec_td: "recTd",
  fumbles_lost: "fum", two_pt: "twoPt",
  fg_att: "fgAtt", fg_made: "fgMade",
  fg_made_0_39: "fg039", fg_made_40_49: "fg4049", fg_made_50_plus: "fg50", fg_missed: "fgMiss",
  pat_att: "patAtt", pat_made: "patMade",
  def_sacks: "sacks", def_int: "defInt", def_fumble_rec: "fumRec", def_td: "defTd", st_td: "stTd",
  def_safety: "safety", def_blocked_kick: "blocked", dst_points_allowed: "paTot",
  dst_pa_g_0: "paG0", dst_pa_g_1_6: "paG1_6", dst_pa_g_7_13: "paG7_13", dst_pa_g_14_17: "paG14_17",
  dst_pa_g_18_20: "paG18_20", dst_pa_g_21_27: "paG21_27", dst_pa_g_28_34: "paG28_34",
  dst_pa_g_35_45: "paG35_45", dst_pa_g_46p: "paG46p",
  // NF-C0e — graduated terms. Each cleared a held-out degenerate-baseline gate before earning a
  // field here; a term that failed it (pat_missed, fum, st_player_td, fumble_rec_td) is
  // deliberately ABSENT, which is what keeps it reported as captured rather than scored on noise.
  pass_td_40p: "passTd40p", rush_td_40p: "rushTd40p", rec_td_40p: "recTd40p",
  def_forced_fumble: "ff",
  dst_yards_allowed: "yaTot",
  dst_ya_g_0_99: "yaG0_99", dst_ya_g_100_199: "yaG100_199", dst_ya_g_200_299: "yaG200_299",
  dst_ya_g_300_349: "yaG300_349", dst_ya_g_350_399: "yaG350_399", dst_ya_g_400_449: "yaG400_449",
  dst_ya_g_450_499: "yaG450_499", dst_ya_g_500_549: "yaG500_549", dst_ya_g_550p: "yaG550p",
}

// ── FIELD GOALS: the league's six buckets fold onto the projection's three ────────────────────────
// Mirror of `league_presets.FG_DERIVED_BUCKETS`. The fold is EXACT whenever the fine values inside a
// projected bucket agree (the common case — most leagues pay the same for a 22- and a 35-yarder), so
// the shares below only ever enter the arithmetic for a league that genuinely prices them apart, and
// the resolver flags that case rather than pretending to a resolution we do not have.
export interface DerivedBucket {
  fineKey: string
  projectedKey: string
  share: number
}

export const FG_DERIVED_BUCKETS: DerivedBucket[] = [
  { fineKey: "fg_made_0_19", projectedKey: "fg_made_0_39", share: 0.02 },
  { fineKey: "fg_made_20_29", projectedKey: "fg_made_0_39", share: 0.3 },
  { fineKey: "fg_made_30_39", projectedKey: "fg_made_0_39", share: 0.68 },
  { fineKey: "fg_made_50_59", projectedKey: "fg_made_50_plus", share: 0.88 },
  { fineKey: "fg_made_60p", projectedKey: "fg_made_50_plus", share: 0.12 },
]

// ── coverage (mirror of fantasy_engine/settings.resolve_scoring) ──────────────────────────────────
export type Verdict = "applied" | "derived" | "captured"

export interface TermCoverage {
  key: string
  verdict: Verdict
  weight: number
  projectedKey?: string | null
  exact: boolean
  note: string
}

export interface CoverageReport {
  terms: TermCoverage[]
  capturedRules: string[]
  hasApproximation: boolean
}

const EPS = 1e-12

/**
 * Fold a league's scoring onto what the projection can express, and report what actually applies.
 *
 * `availableFields` — the payload fields that really carry a value. Supplying it is what keeps
 * coverage MECHANICAL: a stat mapped above but missing from the data downgrades to `captured`
 * instead of silently scoring zero behind an "applied" label.
 */
export function resolveScoring(
  scoring: ScoringRules,
  opts: { availableFields?: Set<string>; capturedRules?: string[] } = {},
): { resolved: ScoringRules; report: CoverageReport } {
  const { availableFields, capturedRules = [] } = opts
  const isProjected = (key: string): boolean => {
    const field = STAT_FIELD[key]
    if (!field) return false
    return availableFields ? availableFields.has(field) : true
  }

  const perStat = scoring.per_stat ?? {}
  const resolved: Record<string, number> = {}
  const terms: TermCoverage[] = []
  const handledFine = new Set<string>()

  // 1. fold the fine buckets the user actually set
  const byProjected = new Map<string, DerivedBucket[]>()
  for (const b of FG_DERIVED_BUCKETS) {
    const list = byProjected.get(b.projectedKey) ?? []
    list.push(b)
    byProjected.set(b.projectedKey, list)
  }
  for (const [projectedKey, buckets] of byProjected) {
    const present = buckets.filter((b) => b.fineKey in perStat)
    if (present.length === 0) continue
    if (!isProjected(projectedKey)) {
      for (const b of present) {
        handledFine.add(b.fineKey)
        terms.push({
          key: b.fineKey, verdict: "captured", weight: Number(perStat[b.fineKey]) || 0,
          exact: true, note: "no projection backs this scoring term",
        })
      }
      continue
    }
    const values = present.map((b) => Number(perStat[b.fineKey]) || 0)
    const exact = Math.max(...values) - Math.min(...values) <= 1e-9
    let folded: number
    if (exact) {
      folded = values[0]
    } else {
      const totalShare = present.reduce((s, b) => s + Math.max(0, b.share), 0)
      folded =
        totalShare > 0
          ? present.reduce((s, b) => s + (Number(perStat[b.fineKey]) || 0) * Math.max(0, b.share), 0) / totalShare
          : values.reduce((s, v) => s + v, 0) / values.length
    }
    resolved[projectedKey] = folded
    for (const b of present) {
      handledFine.add(b.fineKey)
      terms.push({
        key: b.fineKey, verdict: "derived", weight: Number(perStat[b.fineKey]) || 0,
        projectedKey, exact,
        note: exact
          ? ""
          : "the projection resolves this stat more coarsely, so buckets that score differently are combined by their attempt share",
      })
    }
  }

  // 2. everything else passes through, classified against the real data
  for (const [key, raw] of Object.entries(perStat)) {
    if (handledFine.has(key)) continue
    const weight = Number(raw) || 0
    if (key in resolved) {
      terms.push({
        key, verdict: "derived", weight, projectedKey: key, exact: true,
        note: "superseded by the per-bucket values set for this stat",
      })
      continue
    }
    resolved[key] = weight
    if (Math.abs(weight) <= EPS) continue // a zeroed term is a non-statement
    const applied = isProjected(key)
    terms.push({
      key, verdict: applied ? "applied" : "captured", weight, exact: true,
      note: applied ? "" : "no projection backs this scoring term",
    })
  }

  terms.sort((a, b) => (a.verdict === b.verdict ? a.key.localeCompare(b.key) : a.verdict.localeCompare(b.verdict)))
  return {
    resolved: { per_stat: resolved, position_bonuses: scoring.position_bonuses ?? {} },
    report: {
      terms,
      capturedRules,
      hasApproximation: terms.some((t) => t.verdict === "derived" && !t.exact),
    },
  }
}

// ── defaults for a fresh hand-entered league ──────────────────────────────────────────────────────
export function defaultScoring(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const t of SCORING_CATALOG) out[t.key] = t.default
  return out
}

/** The roster shape a fresh custom league starts from: 1QB/2RB/2WR/1TE/2FLEX/1K/1DEF + 5 BN + 3 IR.
 *  IR is a BENCH slot, so — correctly — it adds no starter demand and cannot move replacement level. */
export function defaultRoster(): RosterSlotConfig[] {
  return [
    { name: "QB", count: 1, eligible: ["QB"], bench: false },
    { name: "RB", count: 2, eligible: ["RB"], bench: false },
    { name: "WR", count: 2, eligible: ["WR"], bench: false },
    { name: "TE", count: 1, eligible: ["TE"], bench: false },
    { name: "FLEX", count: 2, eligible: ["RB", "WR", "TE"], bench: false },
    { name: "K", count: 1, eligible: ["K"], bench: false },
    { name: "DST", count: 1, eligible: ["DST"], bench: false },
    { name: "BN", count: 5, eligible: ["QB", "RB", "WR", "TE", "K", "DST"], bench: true },
    { name: "IR", count: 3, eligible: [], bench: true },
  ]
}

export function newCustomConfig(name = "My league", nTeams = 12): LeagueConfig {
  return {
    format_version: CONFIG_FORMAT_VERSION,
    name,
    sport: "nfl",
    n_teams: nTeams,
    ppr: "custom",
    superflex: false,
    description: "",
    scoring: { per_stat: defaultScoring(), position_bonuses: {} },
    roster: defaultRoster(),
    captured_rules: {},
  }
}

/**
 * "Start from a preset, then edit" — the MVP-2 custom path, made concrete.
 *
 * The ROSTER comes from the manifest, i.e. straight from the Python preset that produced the
 * shipped board, so the starting point is the real thing rather than a second definition of it.
 * Scoring starts at the catalog defaults with the per-reception weight taken from the preset's own
 * PPR label — which is exactly how the Python presets are built (`_scoring(rec_pts, te_premium)`
 * over one shared base), so the two agree by construction.
 */
export function presetToConfig(
  meta: { name: string; label?: string; ppr: string; superflex: boolean; description?: string; roster: RosterSlotConfig[] },
  nTeams: number,
): LeagueConfig {
  const perStat = defaultScoring()
  perStat.rec = meta.ppr === "ppr" ? 1 : meta.ppr === "half" ? 0.5 : 0
  // TE-premium is the one shipped preset that carries a per-position bonus rather than a different
  // base weight; it is named for it, which is the only signal the manifest exposes.
  const positionBonuses: Record<string, Record<string, number>> =
    meta.name === "te_premium" ? { TE: { rec: 0.5 } } : {}

  return {
    format_version: CONFIG_FORMAT_VERSION,
    name: meta.label ?? meta.name,
    sport: "nfl",
    n_teams: nTeams,
    ppr: meta.ppr,
    superflex: meta.superflex,
    description: meta.description ?? "",
    scoring: { per_stat: perStat, position_bonuses: positionBonuses },
    roster: meta.roster.map((s) => ({ ...s, eligible: [...s.eligible] })),
    captured_rules: {},
  }
}

export const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const

/** Client-side mirror of `LeagueConfig.validate()` — the same rules the API re-checks server-side. */
export function validateConfig(cfg: LeagueConfig): string[] {
  const errors: string[] = []
  if (!cfg.name.trim()) errors.push("League name is required.")
  if (!Number.isFinite(cfg.n_teams) || cfg.n_teams < 2 || cfg.n_teams > 32) {
    errors.push("Team count must be between 2 and 32.")
  }
  if (Object.keys(cfg.scoring.per_stat ?? {}).length === 0) {
    errors.push("A league must score at least one stat.")
  }
  for (const s of cfg.roster) {
    if (!s.name.trim()) errors.push("Every roster slot needs a name.")
    if (!Number.isFinite(s.count) || s.count < 0) errors.push(`Slot "${s.name}" has an invalid count.`)
    if (!s.bench && s.eligible.length === 0) {
      errors.push(`Starting slot "${s.name}" needs at least one eligible position.`)
    }
  }
  if (!cfg.roster.some((s) => !s.bench && s.count > 0)) {
    errors.push("A league needs at least one starting slot — there is nothing to rank against.")
  }
  return errors
}

/** True when the roster declares a QB-eligible multi-position slot (drives the superflex label). */
export function detectSuperflex(roster: RosterSlotConfig[]): boolean {
  return roster.some((s) => !s.bench && s.count > 0 && s.eligible.length > 1 && s.eligible.includes("QB"))
}

/**
 * The `ppr` label DERIVED from the actual per-reception weight.
 *
 * `ppr` is documented as a human-readable label so a config is self-describing without the engine —
 * the real weight always lives in `scoring.per_stat.rec`. That only holds if the label is kept in
 * step: editing a saved half-PPR league up to 1.0 per reception must not leave it still calling
 * itself "half", or the config contradicts its own scoring and an imported league and a hand-entered
 * one stop describing themselves the same way. Derived on save, exactly like `superflex`.
 */
export function derivePprLabel(scoring: ScoringRules): string {
  const rec = Number(scoring.per_stat?.rec ?? 0)
  if (!Number.isFinite(rec)) return "custom"
  if (Math.abs(rec) < 1e-9) return "standard"
  if (Math.abs(rec - 0.5) < 1e-9) return "half"
  if (Math.abs(rec - 1) < 1e-9) return "ppr"
  return "custom"
}
