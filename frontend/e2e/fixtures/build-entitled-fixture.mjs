#!/usr/bin/env node
/**
 * E9.63 — build the ENTITLED projections fixture from the REAL locked capture.
 *
 *   node e2e/fixtures/build-entitled-fixture.mjs
 *
 * ══ WHY THIS IS GENERATED RATHER THAN CAPTURED, AND WHAT THAT COSTS ══════════════════════════
 *
 * Every other fixture in `api/` is a verbatim prod capture (see `capture-fixtures.mjs`). This one
 * cannot be, for two independent reasons:
 *
 *   1. There is NO public unlocked form of the 2026 projections. `_may_see_values` opens a payload
 *      only for a past season or an entitled caller, and no past season's `projections.json` exists
 *      in the store (every `season < 2026` 404s — verified 2026-08-06). So an anonymous capture of
 *      the entitled shape is not obtainable at all.
 *   2. The entitled payload IS the paid product — 858 players' worth of the thing the subscription
 *      buys. Committing it to the repo to test a render is the wrong trade at any size.
 *
 * ══ SO WHAT IS REAL HERE, AND WHAT IS NOT ═══════════════════════════════════════════════════
 *
 *   REAL (carried straight from the prod capture):
 *     · the whole envelope — season, generated_at, source, adp_format, model_version, market_lean…
 *     · every player's public identity — id, name, pos, team, bye, rookie, draftPick, adp, college…
 *     · the row COUNT and the row ORDER
 *     · ⭐ THE FIELD SET ITSELF. The keys this script adds are exactly `lockedFields` from the prod
 *       payload — which the server COMPUTES from the stored artifact
 *       (`locked_field_names(players, _PUBLIC_PROJECTION_FIELDS)`), it is not a static list. So
 *       "which fields does an entitled row carry that a locked row does not" is answered by the
 *       server, not by me. That is the assumption a hand-written fixture would have encoded, and
 *       it is the one that is NOT encoded here.
 *
 *   SYNTHETIC (deterministic, seeded off the player id):
 *     · the numeric VALUES of those fields.
 *
 * ⇒ This fixture can prove: an unlocked payload renders REAL NUMBERS, ZERO lock chips, and no
 *   `NaN` — the entitled half of the E9.56b split. It CANNOT prove anything about whether the
 *   numbers are right, or about WHO the server decides to send them to. Both of those are out of
 *   scope for a frontend smoke suite and are stated as such in `e2e/README.md`.
 *
 * The genuinely-real "unlocked payload renders real numbers" leg is carried in parallel by the
 * public track-record fixtures, which ARE verbatim prod captures of real, unlocked model output.
 */

import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const API_DIR = join(HERE, "api")
const SRC = join(API_DIR, "fantasy-nfl-projections-2026-locked.json")
const OUT = join(API_DIR, "fantasy-nfl-projections-2026-entitled.synthetic.json")

const locked = JSON.parse(readFileSync(SRC, "utf8"))
const lockedFields = locked.lockedFields ?? []
if (!lockedFields.length) {
  throw new Error(
    "The locked capture carries no `lockedFields`. Re-capture from prod before building this.",
  )
}

/** Deterministic 0..1 from a string — so a re-run produces a byte-identical fixture. */
function unit(seed) {
  let h = 2166136261
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 100000) / 100000
}

// Type-correct fillers for the non-numeric locked fields. Numbers are the default; these are the
// fields whose TYPE the render branches on (a string where a number is expected renders `NaN`,
// which is precisely what this suite exists to catch — so the fixture must be type-honest).
const CONF_TIERS = ["high", "medium", "low"]
const nonNumeric = (field, u) => {
  switch (field) {
    case "conf":
      return CONF_TIERS[Math.floor(u * CONF_TIERS.length)]
    case "uncType":
      return "empirical"
    case "mktLean":
      return "market-led"
    case "lowPred":
      return false
    case "predNote":
      return null
    case "contrib":
      return null
    default:
      return undefined
  }
}

const players = locked.players.map((p) => {
  const row = { ...p }
  delete row.locked // an entitled row carries NO lock marker at all

  const u = unit(String(p.id))
  // A plausible fantasy-point spine, so the table sorts and the interval bar has a real domain.
  const ppr = Math.round((40 + u * 300) * 10) / 10

  for (const f of lockedFields) {
    const nn = nonNumeric(f, u)
    if (nn !== undefined) {
      row[f] = nn
      continue
    }
    row[f] = Math.round(u * 200 * 10) / 10
  }
  // Pin the fields the table's ordering, interval and range columns actually read, so the render
  // is a realistic one rather than 858 identical rows.
  row.fpPpr = ppr
  row.fpHalf = Math.round(ppr * 0.9 * 10) / 10
  row.fpStd = Math.round(ppr * 0.8 * 10) / 10
  row.fpP10 = Math.round(ppr * 0.6 * 10) / 10
  row.fpP90 = Math.round(ppr * 1.4 * 10) / 10
  row.g = 14 + Math.floor(u * 4)
  return row
})

const out = {
  ...locked,
  players,
  locked: false,
  entitled: true,
  // The entitled envelope carries neither of these — `entitlement_envelope(locked=False)` sets
  // only `locked`/`entitled`/`lockedSeason`.
  lockedFields: undefined,
  upgrade: undefined,
  _fixture_note:
    "GENERATED by e2e/fixtures/build-entitled-fixture.mjs from the real prod locked capture. " +
    "Envelope, roster, row order and FIELD SET are real; the numeric VALUES are synthetic. " +
    "Read that file's header before trusting this for anything beyond render-shape.",
}
delete out.lockedFields
delete out.upgrade

writeFileSync(OUT, JSON.stringify(out, null, 2) + "\n")
console.log(
  `wrote ${OUT.split("/").pop()} — ${players.length} players, ${lockedFields.length} server-declared fields unlocked per row`,
)

// ══════════════════════════════════════════════════════════════════════════════════════════════
// FREEMIUM BUILD — the BOARD and MANIFEST in their FULL (un-redacted) form
// ══════════════════════════════════════════════════════════════════════════════════════════════
//
// WHY THESE ARE NEEDED NOW AND WERE NOT BEFORE. Pre-freemium an anonymous visitor received the
// LOCKED board, so the locked capture was the only anonymous shape the suite had to render. The
// generic board is now free, so the shape EVERY caller sees — including the crawler and the
// logged-out visitor the funnel is built for — is the full one, and there is no capture of it for
// the same two reasons the projections fixture is generated (no public unlocked artifact exists,
// and committing the paid product to test a render is the wrong trade).
//
// Same honesty boundary as above: the ENVELOPE, the roster, the row COUNT and the row ORDER are
// real; the numeric VALUES are synthetic and seeded off the player id, so a re-run is byte-stable.
//
// ⭐ THREE ROWS ARE DELIBERATELY DEGENERATE, and they are the point of generating this rather than
// hand-writing it. The `g` (expected games) column feeds the full-season-rate transform, whose
// whole risk is a divide-by-zero rendering as `Infinity` — a `number` in JS, so it passes every
// `!= null` guard a caller might write and prints "∞" beside a points column. A fixture where
// every row has a healthy `g` cannot see that, and it is exactly the fixture anyone would write by
// hand. So the board carries one row with `g: 0`, one with `g: null`, and one with the key ABSENT
// (a missing field type-checks as its declared type at runtime — the E9.56b lesson), and
// `freemium-board.spec.ts` asserts all three render an em-dash.

const BOARD_SRC = join(API_DIR, "fantasy-nfl-board-full_ppr-12-2026-locked.json")
const BOARD_OUT = join(API_DIR, "fantasy-nfl-board-full_ppr-12-2026-free.json")

const lockedBoard = JSON.parse(readFileSync(BOARD_SRC, "utf8"))
if (!Array.isArray(lockedBoard)) throw new Error("the board capture is not a bare list")

/** The degenerate `g` values, by row index. See the block above. */
const DEGENERATE_GAMES = { 3: 0, 4: null, 5: "absent" }

const freeBoard = lockedBoard.map((p, i) => {
  const row = { ...p }
  delete row.locked

  const u = unit(String(p.id))
  const pts = Math.round((40 + u * 300) * 10) / 10
  row.pts = pts
  row.ptsP10 = Math.round(pts * 0.6 * 10) / 10
  row.ptsP90 = Math.round(pts * 1.4 * 10) / 10
  row.vor = Math.round((pts - 90) * 10) / 10
  row.repl = 90
  row.conf = CONF_TIERS[Math.floor(u * CONF_TIERS.length)]
  row.uncType = "empirical"
  row.lowPred = false
  row.predNote = null
  row.mktLean = "market-led"

  const degenerate = DEGENERATE_GAMES[i]
  if (degenerate === "absent") delete row.g
  else if (degenerate !== undefined) row.g = degenerate
  else row.g = 14 + Math.floor(u * 4)
  return row
})

// Ranks follow the generated points, so the board is internally consistent — a table sorted by
// `ovrRank` and one sorted by `pts` must not disagree, or the render is testing an impossible state.
const byPts = [...freeBoard].sort((a, b) => (b.pts ?? 0) - (a.pts ?? 0))
byPts.forEach((row, i) => {
  row.ovrRank = i + 1
})
const posSeen = {}
byPts.forEach((row) => {
  posSeen[row.pos] = (posSeen[row.pos] ?? 0) + 1
  row.posRank = posSeen[row.pos]
})

writeFileSync(BOARD_OUT, JSON.stringify(freeBoard, null, 2) + "\n")
console.log(
  `wrote ${BOARD_OUT.split("/").pop()} — ${freeBoard.length} rows, ` +
    `${Object.keys(DEGENERATE_GAMES).length} degenerate expected-games rows`,
)

// The manifest needs no synthetic VALUES at all — the locked form already drops only the feature
// legend/attribution metadata. So this is the real capture with the envelope flipped, which is
// exactly what the server now returns.
const MANIFEST_SRC = join(API_DIR, "fantasy-nfl-manifest-2026-locked.json")
const MANIFEST_OUT = join(API_DIR, "fantasy-nfl-manifest-2026-free.json")

// ⭐ ...PLUS THE FREE-BOARD MARKINGS the server stamps in `entitlement.open_manifest_payload`. These
// are the only ADDED fields in this whole file, and they have to be here: the picker's lock state is
// driven entirely by them, so a fixture without them would render a fully-open picker and every
// format-lock assertion would pass on the pre-freemium behaviour. Mirrors FREE_BOARD_CONFIG/SIZE.
const FREE_CONFIG = "full_ppr"
const FREE_SIZE = 12

const freeManifest = { ...JSON.parse(readFileSync(MANIFEST_SRC, "utf8")) }
freeManifest.locked = false
freeManifest.entitled = true
delete freeManifest.lockedFields
delete freeManifest.upgrade
freeManifest.configs = (freeManifest.configs ?? []).map((c) => ({
  ...c,
  free: c.name === FREE_CONFIG,
}))
freeManifest.freeBoard = { config: FREE_CONFIG, size: FREE_SIZE }
freeManifest._fixture_note =
  "GENERATED by e2e/fixtures/build-entitled-fixture.mjs — the real prod manifest capture with the " +
  "entitlement envelope flipped to the freemium build's open form, plus the per-config `free` " +
  "markings and `freeBoard` the server stamps. No synthetic model values."

const nFree = freeManifest.configs.filter((c) => c.free).length
if (nFree !== 1) {
  throw new Error(
    `expected exactly one free preset in the manifest, marked ${nFree} — the capture no longer ` +
      `contains ${FREE_CONFIG}, so the fixture would not exercise the format lock`,
  )
}

writeFileSync(MANIFEST_OUT, JSON.stringify(freeManifest, null, 2) + "\n")
console.log(
  `wrote ${MANIFEST_OUT.split("/").pop()} — envelope opened, ` +
    `${freeManifest.configs.length} presets with ${FREE_CONFIG} marked free`,
)
