// league-scoring.ts — NF-C0b: score a projection under ANY league config, in the browser.
//
// A faithful TS port of `fantasy_engine/scoring.py` + `fantasy_engine/vor.py`, in the same lock-step
// spirit as `draft-optimizer.ts` (which already ports `fantasy_engine/draft.py`).
//
// ⭐ WHY THIS EXISTS. The shipped boards are pre-computed by the Python engine, one per (preset,
// size), and served as static JSON. A hand-entered league is not a preset, so there is no board to
// pre-compute — and the API Lambda cannot score one (it bundles neither pandas/numpy nor
// `quant_sports_intel_models`, and its zip already sits near the size cap). Scoring client-side off
// the format-INDEPENDENT projections payload is therefore the natural home, and it is the same
// choice MVP-3 already made for the draft optimizer: pure, synchronous, instant on every edit.
//
// The output is the SAME `Player` shape the pre-exported boards use, which is what makes the story's
// gate true in the strong sense: the board / VOR / draft components consume a hand-built league
// through the identical interface they consume an imported or preset one — they cannot tell which.

import type { LeagueConfig, ScoringRules } from "@/lib/league-config"
import { POSITIONS, STAT_FIELD, resolveScoring } from "@/lib/league-config"
import type { UnmatchedCause } from "@/lib/fantasy-claim-copy"
import type { Player } from "@/lib/draft-optimizer"
import type { ProjectedPlayer } from "@/lib/fantasy"
import type { ImportedPlayer } from "@/lib/fantasy-import"

// 80% two-sided normal quantile — matches the projection's interval convention (scoring.py `_Z80`).
const Z80 = 1.2815515594

// Raw positions → the ranked ones (mirror of NFL_PROFILE.position_aliases). The exporter already
// folds these, so this is a defensive second pass for any payload that predates it.
const POSITION_ALIASES: Record<string, string> = {
  FB: "RB",
  DEF: "DST", "D/ST": "DST", DEFENSE: "DST", D: "DST",
  PK: "K", KICKER: "K",
}

export function normalizePosition(pos: string): string {
  return POSITION_ALIASES[pos] ?? pos
}

function num(rec: Record<string, unknown>, field: string | undefined): number {
  if (!field) return 0
  const v = rec[field]
  return typeof v === "number" && Number.isFinite(v) ? v : 0
}

/** The payload fields that carry at least one real value — the input to MECHANICAL coverage. */
export function availableFields(players: ProjectedPlayer[]): Set<string> {
  const out = new Set<string>()
  for (const p of players) {
    for (const [k, v] of Object.entries(p as unknown as Record<string, unknown>)) {
      if (typeof v === "number" && Number.isFinite(v)) out.add(k)
    }
  }
  return out
}

interface ScoredRow {
  player: ProjectedPlayer
  pos: string
  pts: number
  p10: number | null
  p90: number | null
}

/** Score one projection row under already-RESOLVED scoring rules (scoring.py `score_players`). */
function scoreRow(p: ProjectedPlayer, pos: string, scoring: ScoringRules): ScoredRow {
  const rec = p as unknown as Record<string, unknown>

  let pts = 0
  for (const [statKey, weight] of Object.entries(scoring.per_stat)) {
    if (!weight) continue
    pts += weight * num(rec, STAT_FIELD[statKey])
  }
  // per-position bonuses (TE-premium PPR and friends) — added only for that position
  const bonus = scoring.position_bonuses?.[pos]
  if (bonus) {
    for (const [statKey, weight] of Object.entries(bonus)) {
      if (!weight) continue
      pts += weight * num(rec, STAT_FIELD[statKey])
    }
  }

  // ── uncertainty passthrough, per NF1.7 ──────────────────────────────────────────────────────────
  // Carry EACH SIDE of the projection's own band through by the ratio the point moved, so an
  // ASYMMETRIC interval survives the rescore. Rebuilding from a single sd would force the band
  // symmetric — right for a veteran, wrong for a rookie (whose p10 is near zero while his p90 is a
  // real season) and wrong for K/DST (both floor at 0). The CV path is only the fallback.
  const basePts = p.fpPpr ?? 0
  const baseSd = p.fpSd ?? 0
  let p10: number | null = null
  let p90: number | null = null
  if (basePts > 1e-9) {
    const cv = baseSd / basePts
    const sd = Math.abs(cv * pts)
    p10 = Math.max(0, pts - Z80 * sd)
    p90 = pts + Z80 * sd

    const bLo = p.fpP10
    const bHi = p.fpP90
    if (bLo != null && bHi != null && bHi >= bLo && (bHi > 0 || bLo > 0)) {
      const k = pts / basePts
      p10 = Math.max(0, bLo * k)
      p90 = bHi * k
    }
    // coherence: a displayed interval must contain its own point estimate (NF1.7)
    p10 = Math.max(0, Math.min(p10, pts))
    p90 = Math.max(p90, pts)
  }
  return { player: p, pos, pts, p10, p90 }
}

/**
 * Replacement level per position (vor.py `compute_replacement_levels`).
 *
 * THE SUBTLE PART is the flex allocation: demand = dedicated starters PLUS that position's share of
 * the flex/superflex pool, and the pool is filled by the best remaining players ACROSS eligible
 * positions. Spots are filled most-restrictive-first so a QB-eligible SUPERFLEX never poaches a
 * player a strict FLEX still needed. Under superflex the QB-eligible spots pull the best remaining
 * QBs into starting lineups, QB replacement drops deep, and QB VOR jumps — the face-validity proof
 * the scarcity math is right.
 */
export function replacementLevels(
  rows: ScoredRow[],
  cfg: LeagueConfig,
): { replacement: Record<string, number>; started: Record<string, number> } {
  const ranked: Record<string, number[]> = {}
  for (const r of rows) {
    ;(ranked[r.pos] ??= []).push(r.pts)
  }
  for (const pos of Object.keys(ranked)) ranked[pos].sort((a, b) => b - a)

  const started: Record<string, number> = {}
  for (const pos of Object.keys(ranked)) started[pos] = 0

  const starters = cfg.roster.filter((s) => !s.bench && s.count > 0)
  for (const s of starters) {
    if (s.eligible.length === 1) {
      const pos = s.eligible[0]
      started[pos] = (started[pos] ?? 0) + cfg.n_teams * s.count
    }
  }

  const spots: string[][] = []
  for (const s of starters) {
    if (s.eligible.length > 1) {
      for (let i = 0; i < cfg.n_teams * s.count; i++) spots.push(s.eligible)
    }
  }
  spots.sort((a, b) => a.length - b.length) // most-restrictive first
  for (const eligible of spots) {
    let bestPos: string | null = null
    let bestPts = -Infinity
    for (const pos of eligible) {
      const arr = ranked[pos]
      const idx = started[pos] ?? 0
      if (arr && idx < arr.length && arr[idx] > bestPts) {
        bestPts = arr[idx]
        bestPos = pos
      }
    }
    if (bestPos) started[bestPos] = (started[bestPos] ?? 0) + 1
  }

  const replacement: Record<string, number> = {}
  for (const [pos, arr] of Object.entries(ranked)) {
    const idx = started[pos] ?? 0
    let v: number
    if (arr.length === 0) v = 0
    else if (idx < arr.length) v = arr[idx] // first non-starter = the free replacement
    else v = arr[arr.length - 1] // thinner than demand ⇒ weakest rostered
    replacement[pos] = Math.max(0, v)
  }
  return { replacement, started }
}

export interface BuiltBoard {
  players: Player[]
  replacement: Record<string, number>
  started: Record<string, number>
  /** Coverage of the config against the data actually present — rendered as applied/derived/captured. */
  coverage: ReturnType<typeof resolveScoring>["report"]
}

/**
 * A projection payload + a league config → the ranked cross-position board (vor.py `build_board`).
 *
 * `positions` limits the board to the positions the league actually starts, so a league with no
 * kicker slot does not get a kicker board.
 */
export function buildBoard(projected: ProjectedPlayer[], cfg: LeagueConfig): BuiltBoard {
  const fields = availableFields(projected)
  const { resolved, report } = resolveScoring(cfg.scoring, {
    availableFields: fields,
    capturedRules: Object.keys(cfg.captured_rules ?? {}),
  })

  // only rank positions the league can actually start or bench
  const rosterable = new Set<string>()
  for (const s of cfg.roster) {
    if (s.count <= 0) continue
    for (const p of s.eligible) rosterable.add(p)
  }

  const rows: ScoredRow[] = []
  for (const p of projected) {
    const pos = normalizePosition(p.pos)
    if (rosterable.size > 0 && !rosterable.has(pos)) continue
    rows.push(scoreRow(p, pos, resolved))
  }

  const { replacement, started } = replacementLevels(rows, cfg)

  // positional rank by POINTS within position (ties broken by original order, like pandas "first")
  const posCounters: Record<string, number> = {}
  const byPos: Record<string, ScoredRow[]> = {}
  for (const r of rows) (byPos[r.pos] ??= []).push(r)
  const posRankOf = new Map<ScoredRow, number>()
  for (const [pos, list] of Object.entries(byPos)) {
    const sorted = [...list].sort((a, b) => b.pts - a.pts)
    posCounters[pos] = 0
    for (const r of sorted) posRankOf.set(r, ++posCounters[pos])
  }

  const players: Player[] = rows
    .map((r) => {
      const repl = replacement[r.pos] ?? 0
      return {
        id: r.player.id,
        name: r.player.name,
        pos: r.pos,
        team: r.player.team,
        bye: r.player.bye,
        rookie: r.player.rookie,
        g: r.player.g,
        pts: round1(r.pts),
        repl: round1(repl),
        vor: round1(r.pts - repl),
        posRank: posRankOf.get(r) ?? 0,
        ovrRank: 0, // assigned after the VOR sort below
        // the interval shifts by the FIXED replacement level → an honest interval on VOR
        vorP10: r.p10 == null ? null : round1(r.p10 - repl),
        vorP90: r.p90 == null ? null : round1(r.p90 - repl),
        ptsP10: r.p10 == null ? null : round1(r.p10),
        ptsP90: r.p90 == null ? null : round1(r.p90),
        adp: r.player.adp ?? null,
        lowPred: r.player.lowPred,
        predNote: r.player.predNote,
      } satisfies Player
    })
    .sort((a, b) => (b.vor ?? 0) - (a.vor ?? 0))

  players.forEach((p, i) => {
    p.ovrRank = i + 1
  })

  return { players, replacement, started, coverage: report }
}

function round1(v: number): number {
  return Math.round(v * 10) / 10
}

// ── NF-C6: match an IMPORTED roster (platform names) onto a scored board (our player ids) ────────
//
// `ImportedPlayer.player_key` is the PLATFORM's own id and is deliberately NOT joinable to our
// projection ids (`canonical.ImportedPlayer`'s own docstring) — Sleeper's id and ours are unrelated
// namespaces. Name + position is the only join key common to both sides, so this normalizes each
// the same way (ASCII-fold, drop generational suffixes/punctuation, collapse whitespace) and matches
// on that pair. A miss is a REAL, expected outcome (a name spelling divergence, a DST rendered as a
// team abbreviation instead of a name, or a Sleeper id the NF-C0c name cache never resolved to a
// name at all) — it is surfaced, never hidden, matching NF-C0c's own "matched N of M" convention.
function normalizePlayerName(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "") // strip diacritics (combining marks left by NFKD)
    .toLowerCase()
    .replace(/\b(jr|sr|ii|iii|iv|v)\b\.?/g, "")
    .replace(/[^a-z ]/g, "")
    .replace(/\s+/g, " ")
    .trim()
}

// ══ NF-C6P3 — THE D/ST JOIN. A team defence is not a person, and the name join never matched one ══
//
// The board publishes a unit as "DET D/ST"; every platform publishes it under its NICKNAME (ESPN
// "Lions D/ST", Sleeper "Detroit Lions", Yahoo "Detroit"). Normalized, that is `det dst` against
// `lions dst` — no match, for any team, on any platform. The miss is a legitimate `board: null`, so
// nothing errors: the D/ST STARTING SLOT simply sits empty and contributes ZERO to the headline
// total. A confidently wrong number that renders perfectly.
//
// So a DST row keys on its FRANCHISE: the row's own `team` field, else a nickname in the name, else
// an abbreviation token in the name (which is how our own board renders it). Unresolvable ⇒ the old
// name key and an honest miss; there is deliberately NO fuzzy fallback, because matching the WRONG
// defence would credit a user with points they never drafted.
//
// ⚠️ MIRRORS `app/backend/services/league_scoring.py` EXACTLY — that module is what the live server
// joins with, this one is what the E2E harness scores through, and
// `betting_ml/tests/test_nf_c6p3_league_rosters.py` pins the two maps against each other and against
// the research tree's franchise table. A nickname added here and not there is a failing test.

/** Franchise nickname → the abbreviation our board publishes, keyed on what `normalizePlayerName`
 *  PRODUCES. ⚠️ "49ers" folds to "ers" (digits are dropped), so that is the key — it looks like a
 *  typo and is not. Historical nicknames are included: an older league still names them that way. */
export const NFL_TEAM_BY_NICKNAME: Record<string, string> = {
  cardinals: "ARI", falcons: "ATL", ravens: "BAL", bills: "BUF",
  panthers: "CAR", bears: "CHI", bengals: "CIN", browns: "CLE",
  cowboys: "DAL", broncos: "DEN", lions: "DET", packers: "GB",
  texans: "HOU", colts: "IND", jaguars: "JAX", jags: "JAX",
  chiefs: "KC", chargers: "LAC", rams: "LAR", raiders: "LV",
  dolphins: "MIA", vikings: "MIN", patriots: "NE", saints: "NO",
  giants: "NYG", jets: "NYJ", eagles: "PHI", steelers: "PIT",
  seahawks: "SEA", ers: "SF", niners: "SF", buccaneers: "TB",
  bucs: "TB", titans: "TEN", commanders: "WAS", redskins: "WAS",
  // ⚠️ THE ONLY TWO-WORD ENTRY — Washington played as the "Football Team" for 2020–21, so
  // `dstTeam` checks adjacent token PAIRS too. "team" alone cannot be a key: a defence rendered
  // "Team 3 D/ST" would then resolve to Washington.
  "football team": "WAS",
}

/** A platform's team abbreviation → ours. DIVERGENCES only; relocations dominate. */
export const NFL_TEAM_ABBREV_ALIASES: Record<string, string> = {
  OAK: "LV", LVR: "LV",
  SD: "LAC", SDG: "LAC",
  STL: "LAR", LA: "LAR", RAM: "LAR",
  WSH: "WAS", WFT: "WAS",
  JAC: "JAX",
  GNB: "GB", KAN: "KC", NWE: "NE", NOR: "NO", SFO: "SF", TAM: "TB",
  ARZ: "ARI", BLT: "BAL", CLV: "CLE", HST: "HOU",
}

const NFL_TEAM_ABBREVIATIONS = new Set(Object.values(NFL_TEAM_BY_NICKNAME))

/** A platform's team abbreviation as OUR board spells it, or `""` when unresolvable.
 *  ⚠️ `""` rather than the input: a key built from an unknown abbreviation can only ever match
 *  itself, which is a silent no-match dressed up as a resolution. */
export function normalizeTeamAbbrev(team: string | null | undefined): string {
  const t = String(team ?? "").trim().toUpperCase()
  if (!t) return ""
  const aliased = NFL_TEAM_ABBREV_ALIASES[t] ?? t
  return NFL_TEAM_ABBREVIATIONS.has(aliased) ? aliased : ""
}

/** The franchise a D/ST row belongs to, or `""` when it cannot be resolved honestly. */
export function dstTeam(name: string, team: string | null | undefined): string {
  const resolved = normalizeTeamAbbrev(team)
  if (resolved) return resolved
  // Adjacent PAIRS before single tokens: the map has one two-word nickname whose second word must
  // never be a key on its own.
  const tokens = normalizePlayerName(name).split(" ")
  for (let i = 0; i < tokens.length - 1; i++) {
    const hit = NFL_TEAM_BY_NICKNAME[`${tokens[i]} ${tokens[i + 1]}`]
    if (hit) return hit
  }
  for (const token of tokens) {
    const hit = NFL_TEAM_BY_NICKNAME[token]
    if (hit) return hit
  }
  // Our own board's rendering ("DET D/ST"): read off the RAW name, since normalization lowercases.
  for (const token of String(name ?? "").replace(/\//g, " ").split(/\s+/)) {
    const hit = normalizeTeamAbbrev(token)
    if (hit) return hit
  }
  return ""
}

/** The key both sides of the join reduce to. Everyone but a team defence keys on `name|pos`
 *  exactly as before — this is not a rewrite of a join that works for 95% of a roster. */
function joinKey(name: string, pos: string | null | undefined, team: string | null | undefined): string {
  const position = normalizePosition(pos ?? "")
  if (position === "DST") {
    const resolved = dstTeam(name, team)
    if (resolved) return `DST|${resolved}`
  }
  return `${normalizePlayerName(name)}|${position}`
}

export interface RosterMatch {
  roster: ImportedPlayer
  /** The scored board row for this roster player, or `null` when no match was found in the current
   *  projection universe (an honest miss — see the module note above). */
  board: Player | null
}

/**
 * 🔴 NF-K1 — WHY this roster row has no board row, in a form a surface can render.
 *
 * `RosterMatch.board === null` has three genuinely different causes and the surface rendered all
 * three as "not matched" — see `fantasy-claim-copy`'s NF-K1 block for what that cost. This is the
 * one place that decides which one applies, so the table cell, its tooltip and the card footnote
 * cannot drift apart (the E9.61 "two renderers of one field are two rule sets" lesson).
 *
 * @param position    the roster row's position, as the platform reported it
 * @param published   the PROJECTABLE positions the served board actually carries
 *                    (`MyTeamsPayload.board_positions`). `null`/`undefined` = we do not know.
 *
 * ⚠️ THE `unknown` FALLBACK IS LOAD-BEARING, not a default-case formality. During the deploy skew
 * an older API sends no `board_positions`; with an empty array standing in for that, EVERY
 * unmatched row would claim "we have not published this position" — a confident, wrong,
 * product-wide cause. Not knowing is reported as not knowing.
 */
export function classifyUnmatched(
  position: string | null | undefined,
  published: readonly string[] | null | undefined,
): UnmatchedCause {
  const pos = normalizePosition(position ?? "")
  // A position we never project is decidable WITHOUT the server's help — `POSITIONS` is the
  // client's mirror of the exporter's `PROJECTABLE`. An IDP or punter slot is answerable even on a
  // skewed deploy, so it is settled before the unknown check.
  if (!pos || !(POSITIONS as readonly string[]).includes(pos)) return "not-projected"
  if (!published) return "unknown"
  return published.includes(pos) ? "unresolved" : "not-published"
}

/** Join one imported roster onto an already-`buildBoard`'d array. */
export function matchRosterToBoard(roster: ImportedPlayer[], board: Player[]): RosterMatch[] {
  const byKey = new Map<string, Player>()
  for (const p of board) {
    const key = joinKey(p.name, p.pos, p.team)
    if (!byKey.has(key)) byKey.set(key, p) // first (highest-VOR, since board is VOR-sorted) wins
  }
  return roster.map((r) => {
    if (!r.name) return { roster: r, board: null }
    const key = joinKey(r.name, r.position ?? "", r.team)
    return { roster: r, board: byKey.get(key) ?? null }
  })
}
