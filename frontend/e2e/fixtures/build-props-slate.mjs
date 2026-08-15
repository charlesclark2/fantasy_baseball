// E5.10 — /props slate-navigation fixtures.
//
// Generates a synthetic 6-game slate for BOTH prop tabs (batter TB, pitcher K) — enough games to
// exercise game grouping/collapse, enough teams for the team filter chips, and a spread of line
// values (TB: 0.5/1.5/2.5 · K: 4.5/5.5/6.5) and book counts (1-5) for the line/books chips. Dates
// are set far in the future (2027) so every game is reliably "upcoming" relative to whenever the
// suite actually runs — the "next game to start" default-expand behaviour needs a stable ordering,
// not a boundary that depends on the wall clock at test time.
//
// Run: node e2e/fixtures/build-props-slate.mjs
//
// ⚠️ NOT derived from a real captured payload (unlike the ESPN/track-record fixtures) — there is no
// way to capture a full MLB slate deterministically, and the shapes here mirror
// `betting_ml/utils/tb_projection_serving.index_row` / `k_projection_serving.index_row` exactly
// (see `frontend/app/props/page.tsx`'s `BatterRow`/`ProjectionRow` types, which are typed against
// the same source).

import { writeFileSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), "api")

// [gamePk, teamA, teamB, isoDatetime] — teamA bats first in the generated order but both sides get
// full lineups. Times deliberately unsorted here so the generator (not authoring order) proves the
// slate-order sort.
const GAMES = [
  [900003, "LAD", "SFG", "2027-03-15T20:10:00Z"],
  [900001, "MIA", "PIT", "2027-03-15T17:10:00Z"],
  [900006, "CHC", "STL", "2027-03-16T01:20:00Z"],
  [900002, "NYY", "BOS", "2027-03-15T19:05:00Z"],
  [900005, "ATL", "NYM", "2027-03-15T22:40:00Z"],
  [900004, "HOU", "SEA", "2027-03-15T22:10:00Z"],
]

// One marquee, searchable name per game (batting leadoff for the home-listed team) — the rest of
// each lineup is a filler name. Distinctive enough for a partial-name search test ("ohtani" etc.)
// without needing every one of 108 rows to carry a real player's name.
const MARQUEE_BATTERS = {
  900001: "Shohei Ohtani",
  900002: "Aaron Judge",
  900003: "Mookie Betts",
  900004: "Yordan Alvarez",
  900005: "Ronald Acuna Jr.",
  900006: "Ian Happ",
}
const MARQUEE_PITCHERS = {
  900001: "Sandy Alcantara",
  900002: "Gerrit Cole",
  900003: "Yoshinobu Yamamoto",
  900004: "Framber Valdez",
  900005: "Spencer Strider",
  900006: "Justin Steele",
}

const TB_LINES = [0.5, 1.5, 2.5]
const K_LINES = [4.5, 5.5, 6.5]

// E5.10 — the sportsbook filter chips. A rotating deterministic subset of this pool (size ==
// book_count) is assigned per row, so "bovada" appears on a real subset of the slate rather than
// on everything (or nothing) — the fixture a book-availability filter needs to mean something.
const BOOK_POOL = ["bovada", "draftkings", "fanduel", "caesars", "betmgm"]

function round(n, d = 2) {
  const f = 10 ** d
  return Math.round(n * f) / f
}

function booksFor(seed, bookCount) {
  const start = seed % BOOK_POOL.length
  return Array.from({ length: bookCount }, (_, i) => BOOK_POOL[(start + i) % BOOK_POOL.length]).sort()
}

function batterRow({ batterId, name, team, opponent, gamePk, gameDatetime, slot, seed }) {
  const line = TB_LINES[seed % TB_LINES.length]
  const mean = round(0.6 + (seed % 7) * 0.18)
  const bookCount = 1 + (seed % 5)
  const pGe2 = round(0.12 + (seed % 5) * 0.05, 2)
  const modelPOver = round(0.35 + (seed % 6) * 0.05, 2)
  // Signed, spans both directions so "difference vs books" sort has a real order to prove.
  const diff = round((seed % 2 === 0 ? 1 : -1) * (0.02 + (seed % 5) * 0.015), 3)
  return {
    batter_id: batterId,
    full_name: name,
    team,
    opponent,
    game_pk: gamePk,
    game_date: gameDatetime.slice(0, 10),
    game_datetime: gameDatetime,
    batting_slot: slot,
    mean,
    median: round(mean - 0.1),
    p10: round(Math.max(0, mean - 1.3)),
    p90: round(mean + 1.6),
    p05: round(Math.max(0, mean - 1.8)),
    p95: round(mean + 2.3),
    p_ge_2: pGe2,
    primary_line: line,
    book_count: bookCount,
    books: booksFor(seed, bookCount),
    model_p_over: modelPOver,
    model_vs_book_p_over: diff,
    model_mean_minus_line: round(mean - line),
  }
}

function pitcherRow({ pitcherId, name, team, opponent, gamePk, gameDatetime, seed }) {
  const line = K_LINES[seed % K_LINES.length]
  const mean = round(4.2 + (seed % 5) * 0.5)
  // ⚠️ NOT `seed % 5` — every pitcher's seed lands exactly 9 or 19 past its game's start (9
  // batters, then the pitcher), so consecutive pitcher seeds differ by a multiple of 5 and
  // `seed % 5` is INVARIANT across all 12 pitchers (every one landed on bookCount=5, measured).
  // `pitcherId` increments by exactly 1 per pitcher row, so it actually varies.
  const bookCount = 1 + (pitcherId % 5)
  const modelPOver = round(0.4 + (seed % 4) * 0.05, 2)
  const diff = round((seed % 2 === 0 ? 1 : -1) * (0.01 + (seed % 4) * 0.02), 3)
  return {
    pitcher_id: pitcherId,
    full_name: name,
    team,
    opponent,
    game_pk: gamePk,
    game_date: gameDatetime.slice(0, 10),
    game_datetime: gameDatetime,
    last3_k: [4 + (seed % 3), 5 + (seed % 2), 6],
    mean,
    median: round(mean - 0.2),
    p10: round(Math.max(0, mean - 2)),
    p90: round(mean + 2.2),
    p05: round(Math.max(0, mean - 2.6)),
    p95: round(mean + 3),
    primary_line: line,
    book_count: bookCount,
    books: booksFor(seed, bookCount),
    model_p_over: modelPOver,
    model_vs_book_p_over: diff,
    model_mean_minus_line: round(mean - line),
  }
}

const batters = []
const pitchers = []
let batterId = 700001
let pitcherId = 800001
let seed = 0

for (const [gamePk, teamA, teamB, gameDatetime] of GAMES) {
  for (const [team, opponent] of [
    [teamA, teamB],
    [teamB, teamA],
  ]) {
    for (let slot = 1; slot <= 9; slot++) {
      const isLeadoff = slot === 1 && team === teamA
      const name = isLeadoff ? MARQUEE_BATTERS[gamePk] : `${team} Hitter ${slot}`
      batters.push(
        batterRow({ batterId: batterId++, name, team, opponent, gamePk, gameDatetime, slot, seed: seed++ }),
      )
    }
    const isProbable = team === teamA
    const name = isProbable ? MARQUEE_PITCHERS[gamePk] : `${team} Starter`
    pitchers.push(
      pitcherRow({ pitcherId: pitcherId++, name, team, opponent, gamePk, gameDatetime, seed: seed++ }),
    )
  }
}

const gameDate = "2027-03-15"
const DISCLAIMER =
  "Projections reflect our model; they are not betting advice and we make no profitability claim."

const tbIndex = {
  game_date: gameDate,
  count: batters.length,
  batters,
  disclaimer: DISCLAIMER,
  best_alpha: 0,
  is_bet_recommendation: false,
}
const kIndex = {
  game_date: gameDate,
  count: pitchers.length,
  pitchers,
  disclaimer: DISCLAIMER,
  best_alpha: 0,
  is_bet_recommendation: false,
}

writeFileSync(join(OUT_DIR, "props-tb-index-slate.json"), JSON.stringify(tbIndex, null, 2) + "\n")
writeFileSync(join(OUT_DIR, "props-k-index-slate.json"), JSON.stringify(kIndex, null, 2) + "\n")

console.log(`wrote ${batters.length} batter rows across ${GAMES.length} games (TB)`)
console.log(`wrote ${pitchers.length} pitcher rows across ${GAMES.length} games (K)`)
