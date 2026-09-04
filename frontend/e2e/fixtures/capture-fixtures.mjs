#!/usr/bin/env node
/**
 * E9.63 — capture the E2E API fixtures from the LIVE production API.
 *
 * ⛔ DO NOT HAND-WRITE A FIXTURE IN `api/`. That is the whole discipline this file exists to
 * enforce, and it is E9.56b's lesson stated as a rule: the bugs this suite guards (a locked board
 * rendering BLANK, `NaN` in a column, a CTA pointing at a route that does not exist) all live in
 * the gap between what we ASSUME the payload looks like and what the server actually sends. A
 * hand-written fixture encodes the assumption under test, so the suite would pass on exactly the
 * payload shape that never occurs in production.
 *
 * Every endpoint captured here is PUBLIC — no token, no entitlement. That is not a convenience;
 * it is the point. These are the bytes an anonymous visitor's browser receives, captured verbatim.
 *
 *   node e2e/fixtures/capture-fixtures.mjs            # refresh from prod
 *   node e2e/fixtures/capture-fixtures.mjs --check    # CI-safe: report drift, write nothing
 *
 * `--check` is deliberately NOT wired into the CI gate. A fixture is a SNAPSHOT of a payload the
 * operator re-exports on their own cadence; failing the build because the board was regenerated
 * would be a false red. Run it by hand when a payload shape changes.
 */

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs"
import { createHash } from "node:crypto"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(HERE, "api")

const API = process.env.E2E_CAPTURE_API_URL ?? "https://api.credencesports.com"

/** The season the frontend's `FANTASY_SEASON` points at — the LOCKED (paid) one. */
const LOCKED_SEASON = 2026
/** The newest season the public track record covers — real, unlocked model output. */
const TRACK_RECORD_SEASON = 2025
/** NCAAF-P3.2 — the LA kickoff day captured as the slate fixture: the 2026 opener.
 *
 *  ⚠️ A DATE, DELIBERATELY, AND IT WILL GO STALE. The NCAAF slate key IS the kickoff day (there is
 *  no week parameter — CFBD restarts `week` at 1 in the postseason, so a week would name two
 *  different sets of games), so a slate capture is necessarily pinned to one day and a re-capture
 *  in October needs this bumped to a published day. `/ncaaf/manifest`'s `game_days` lists them. */
const NCAAF_CAPTURED_GAME_DAY = "2026-08-29"

const TARGETS = [
  {
    file: "fantasy-nfl-projections-2026-locked.json",
    path: `/fantasy/nfl/projections?season=${LOCKED_SEASON}`,
    note: "Locked (anonymous) season projections. `locked: true`, every model value stripped, rows re-ordered onto market ADP.",
  },
  {
    file: "fantasy-nfl-manifest-2026-locked.json",
    path: `/fantasy/nfl/manifest?season=${LOCKED_SEASON}`,
    note: "Locked manifest — the board frame (configs + sizes) the CTA is rendered on.",
  },
  {
    file: "fantasy-nfl-board-full_ppr-12-2026-locked.json",
    path: `/fantasy/nfl/board?config=full_ppr&size=12&season=${LOCKED_SEASON}`,
    note: "Locked draft board. A bare ARRAY (never an envelope — see lock_board_payload). This is the payload that rendered BLANK in E9.56b.",
  },
  {
    file: "fantasy-nfl-track-record-manifest.json",
    path: "/fantasy/nfl/track-record/manifest",
    note: "Public track record manifest. Real numbers, no entitlement — the receipts surface.",
  },
  {
    file: `fantasy-nfl-track-record-${TRACK_RECORD_SEASON}.json`,
    path: `/fantasy/nfl/track-record/${TRACK_RECORD_SEASON}`,
    note: "Public past-season track record. REAL, UNLOCKED model output — the honest 'a real payload renders real numbers' fixture.",
  },
  {
    file: "picks-featured.json",
    path: "/picks/featured",
    note: "E9.46 — the home page's live model-vs-market element. PUBLIC (the pre-E9.46 home page fetched it server-side with no token). ⚠️ CHANGES DAILY: it is the current slate's widest model-vs-market gap, so a re-capture will always differ. The specs read the payload's own values rather than hardcoded numbers, so drift is not a failure — but a SHAPE change (a dropped field, a renamed side) is exactly what a re-capture is for.",
  },
  // ── NCAAF-P3.2 — the college-football game-predictions surface ────────────────────────────────
  //
  // ⭐ CAPTURED, NOT GENERATED. The four `/ncaaf/*` routes went live on 2026-08-24 (P3.1's deploy +
  // the API-Gateway `NONE` routes), so unlike E9.46's featured player these need no build script —
  // they are the verbatim bytes an anonymous visitor receives. NCAAF is FREE (E9.45), so there is
  // no token and no entitlement variant to capture.
  {
    file: "ncaaf-manifest.json",
    path: "/ncaaf/manifest",
    note: "NCAAF-P3.2 — the week selector's source. Kickoff DAYS, never a CFBD week (the season_order_week alias landmine). ⚠️ `current_game_day` is 'today in LA' and is DELIBERATELY not always a published day: before the opener it names a day with no slate, which is the surface's empty-week state and is captured here rather than invented.",
  },
  {
    file: `ncaaf-slate-${NCAAF_CAPTURED_GAME_DAY}.json`,
    path: `/ncaaf/games?game_day=${NCAAF_CAPTURED_GAME_DAY}`,
    // ⭐ NCAAF-P3.3 — FROZEN, and the freeze is the point rather than an omission.
    //
    // These bytes are the 2026-08-25 capture, when every game on the wire was
    // `market.status = "unavailable"`. NCAAF-ODDS-LIVE's ahead-of-kickoff feed has since landed,
    // so THE SAME URL now returns seven priced games (that is the `-mixed` target below). The
    // all-absent slate is therefore a shape prod no longer produces for this day — and it is the
    // ONLY fixture on which "every card states its absence" is a whole-slate assertion.
    //
    // Re-capturing it would overwrite that arm with the mixed one and silently delete a branch,
    // which is exactly the deletion the previous note asked the next session NOT to make. So it is
    // pinned: `--check` reports it FROZEN rather than DRIFT (a drift line here would be a red that
    // can only be "fixed" by destroying coverage), and its provenance entry is read off disk.
    frozen:
      "captured 2026-08-25, before NCAAF-ODDS-LIVE's feed reached this day. Prod now serves lines " +
      "on this URL (see ncaaf-slate-2026-08-29-mixed.json), so a re-capture would delete the " +
      "all-absent arm. Kept as the stated-absence fixture.",
    note: "NCAAF-P3.2 — one LA kickoff day's full slate, the payload the cards render from. ⚠️ EVERY GAME'S MARKET BLOCK IS `unavailable` — the real state of the wire WHEN THIS WAS TAKEN, not a gap in the capture: the only NCAAF odds capture scheduled for 2026 was the paid `/historical` catch-up, which by construction cannot reach a kickoff until it is PAST (P3.1 closeout §2), so the market-AVAILABLE shape had nothing to capture and is generated by `build-ncaaf-degraded.py` from the shipping builder. ⚠️ ON RE-CAPTURE: NCAAF-ODDS-LIVE added a live ahead-of-kickoff feed, so a fresh capture will eventually carry real lines. KEEP A GENUINELY ABSENT GAME and RE-ANCHOR the all-`unavailable` clauses (`test_ncaaf_p3_2_surface.py`, `ncaaf-games.spec.ts`) onto it rather than deleting them — a leakage refusal keeps the stated-absence branch live regardless.",
  },
  {
    file: `ncaaf-slate-${NCAAF_CAPTURED_GAME_DAY}-mixed.json`,
    path: `/ncaaf/games?game_day=${NCAAF_CAPTURED_GAME_DAY}`,
    note: "NCAAF-P3.3 — THE REALISTIC SATURDAY, and it replaces a GENERATED fixture with a captured one. The same URL as the frozen target above, taken 2026-09-01 once NCAAF-ODDS-LIVE's ahead-of-kickoff feed had landed: seven games carry a real `odds_api_live` line and one is genuinely without one. That mix is what a real in-season Saturday looks like, and it is why the synthetic `ncaaf-slate-2026-08-29-market.synthetic.json` was retired — a fixture built by feeding 2025 closes to the shipping builder can only ever confirm the shape we already assumed (E9.64b: a fixture derived from the transform cannot disconfirm it). ⚠️ THE ABSENT GAME IS A REFUSAL, not an uncaptured kickoff: `reason = market_snapshot_not_pre_kickoff`, i.e. the leakage guard declined a line it could not prove was taken before kickoff. KEEP IT on any re-capture — it is the only fixture in the tree that reaches that branch.",
  },
  // ── NCAAF-P3.3 — the team stats page ──────────────────────────────────────────────────────────
  //
  // ⭐ CAPTURED THE MORNING THE ROUTE WENT LIVE (2026-09-03) and RE-TAKEN 2026-09-04 by
  // NCAAF-P3.3b, once the standings write had landed — the re-capture the P3.3 closeout
  // asked for, and the way its self-announcing "the capture has acquired standings" clause
  // was RETIRED. ⛔ Retire such a clause BY RE-CAPTURING, never by weakening it into
  // something the new payload happens to satisfy. Originally taken once the box serving-write, the
  // Lambda deploy and the API-Gateway `NONE` route had all landed. Two teams, chosen because they
  // differ in the ways the page has to handle, not because they were convenient:
  //
  //   68   Boise State — a 2026 REALIGNMENT MOVER (Mountain West → Pac-12). Its whole schedule is
  //        still upcoming, so every scoring field is null and the record is 0-0 with nothing
  //        played: the state in which a component that defaulted a score to 0 would be visibly
  //        wrong, and the one a page opening in early September is mostly in.
  //   2449 North Dakota State — NEW TO FBS for 2026 (`is_new_to_fbs: true`) AND carrying a
  //        completed game, so the played/upcoming split is REALIZED on one payload rather than
  //        asserted from two.
  //
  // ⚠️ BOTH CARRY `efficiency` AND `splits` AS STATED ABSENCES (`no_row_for_this_team_and_season`)
  // — the P1.1 rollups hold no 2026 rows yet. That is the REAL state of the wire, not a capture
  // gap, and it is why `ncaaf-team-populated.synthetic.json` exists beside these: the available
  // branch of those two blocks has nothing to capture today, exactly as the market panel's
  // available branch had nothing to capture in P3.2.
  {
    file: "ncaaf-team-68.json",
    path: "/ncaaf/teams/68",
    note: "NCAAF-P3.3 — a 2026 conference mover with a wholly-upcoming schedule. ⚠️ ON RE-CAPTURE: keep a team whose `conference` differs from its prior season and whose `conference_source` is `scd2_dim` — the realignment clause reads this payload's own values, and a fixture whose conference never moved could not tell a point-in-time read from a `is_current` one.",
  },
  {
    file: "ncaaf-team-2449.json",
    path: "/ncaaf/teams/2449",
    note: "NCAAF-P3.3 — a first-year FBS program with one game played. ⚠️ ON RE-CAPTURE: keep BOTH a completed game and an upcoming one in the schedule. A fixture where every game is played (or none is) cannot tell a component that renders a result from one that renders whatever it is handed — the same argument the mixed market slate rests on.",
  },
  {
    file: "subscription-public-pricing.json",
    path: "/subscription/public-pricing",
    note: "Public price (E9.59). Read server-side from the Stripe Price object Checkout charges against — so this capture is the number a logged-out visitor actually sees. ✅ Captured from Stripe LIVE mode (E9.8-P2 flip, 2026-08-16): $10.00/mo founding, price_1Twvan…, 100 seats. ⚠️ `founding_slots_remaining` DRIFTS with every real conversion, so a re-capture will differ there — that is expected and no test asserts it; the PRICE contract ($10 / usd / monthly / recurring / founding) is what `test_e9_8_p2_lambda_env_helper.py::TestTheGoLivePriceContract` pins.",
  },
]

const sha = (s) => createHash("sha256").update(s).digest("hex").slice(0, 16)

const checkOnly = process.argv.includes("--check")

/**
 * `--only <substring>` — capture just the matching fixture(s).
 *
 * E9.8-P2 needs this: the Stripe TEST→LIVE flip changes exactly ONE payload
 * (`subscription-public-pricing.json`, whose amount comes from the live Stripe Price), and
 * forcing a full re-capture to refresh it would rewrite the 378 KB board blobs at the same
 * time. Those move on the operator's export cadence, not on the billing flip, so bundling
 * them buries a one-line price change in an unreviewable diff — and re-captures them at
 * whatever moment the flip happens to fall on rather than at a deliberate one.
 */
const onlyIdx = process.argv.indexOf("--only")
const only = onlyIdx !== -1 ? process.argv[onlyIdx + 1] : null
if (onlyIdx !== -1 && !only) {
  console.error("--only needs a substring, e.g. --only subscription-public-pricing")
  process.exit(2)
}
const targets = only ? TARGETS.filter((t) => t.file.includes(only)) : TARGETS
if (only && targets.length === 0) {
  console.error(`--only ${only}: matched no fixture. Known files:`)
  for (const t of TARGETS) console.error(`  ${t.file}`)
  process.exit(2)
}
if (only) console.log(`--only ${only}: capturing ${targets.length} of ${TARGETS.length} fixtures`)

mkdirSync(OUT_DIR, { recursive: true })

let drift = 0
const provenance = []

for (const t of targets) {
  const url = `${API}${t.path}`
  const out0 = join(OUT_DIR, t.file)

  // ⭐ A FROZEN TARGET IS READ OFF DISK, NEVER RE-FETCHED (NCAAF-P3.3).
  //
  // Some fixtures pin a payload shape prod NO LONGER PRODUCES — an all-absent NCAAF market slate,
  // now that a live odds feed exists. Re-capturing one overwrites the only fixture that reaches a
  // branch, so the branch dies quietly and the suite stays green. `--check` must not report it as
  // drift either: a red line whose only remedy is "delete the coverage" trains an operator to
  // refresh it. It still appears in CAPTURE.json, with its reason, so it cannot become a file
  // nobody can account for.
  if (t.frozen) {
    if (!existsSync(out0)) {
      console.error(`FAIL  frozen fixture is MISSING from disk: ${t.file}`)
      process.exitCode = 1
      continue
    }
    const body = readFileSync(out0, "utf8")
    console.log(`frozen ${t.file}  (${body.length} bytes) — ${t.frozen}`)
    provenance.push({
      file: t.file, url, bytes: body.length, sha256_16: sha(body),
      frozen: t.frozen, note: t.note,
    })
    continue
  }

  const res = await fetch(url)
  if (!res.ok) {
    console.error(`FAIL  ${res.status} ${url}`)
    process.exitCode = 1
    continue
  }
  // Re-serialize rather than storing the raw bytes: a stable 2-space form keeps the diff of a
  // re-capture readable instead of a single 267 KB line.
  const body = JSON.stringify(await res.json(), null, 2) + "\n"
  const prev = existsSync(out0) ? readFileSync(out0, "utf8") : null

  if (checkOnly) {
    const same = prev === body
    if (!same) drift++
    console.log(`${same ? "same" : "DRIFT"}  ${t.file}  (${body.length} bytes)`)
  } else {
    writeFileSync(out0, body)
    console.log(`wrote ${t.file}  ${body.length} bytes  sha256:${sha(body)}`)
  }
  provenance.push({ file: t.file, url, bytes: body.length, sha256_16: sha(body), note: t.note })
}

if (!checkOnly) {
  // ⚠️ A `--only` run must MERGE its provenance, never replace it. `provenance` holds just
  // the files captured THIS run, so writing it verbatim after a filtered run would delete the
  // records of every other fixture — the file would then claim those fixtures do not exist
  // while they sit right beside it on disk. Carry forward what this run did not touch, and
  // keep each entry's OWN capture time so a stale fixture cannot hide behind a fresh header.
  const capturedAt = new Date().toISOString()
  const capturedNow = new Set(provenance.map((p) => p.file))
  const previous = existsSync(join(OUT_DIR, "CAPTURE.json"))
    ? JSON.parse(readFileSync(join(OUT_DIR, "CAPTURE.json"), "utf8"))
    : { files: [] }
  const carried = (previous.files ?? [])
    .filter((p) => !capturedNow.has(p.file))
    .map((p) => ({ ...p, captured_at: p.captured_at ?? previous.captured_at }))
  // ⚠️ A FROZEN entry keeps its ORIGINAL `captured_at`. Stamping this run's instant on bytes
  // nobody fetched would be the NF-FRESH2 defect in miniature — a freshness field describing when
  // the script ran rather than when the payload was taken.
  const priorAt = new Map((previous.files ?? []).map((p) => [p.file, p.captured_at ?? previous.captured_at]))
  const files = [
    ...provenance.map((p) => ({
      ...p,
      captured_at: p.frozen ? (priorAt.get(p.file) ?? previous.captured_at ?? null) : capturedAt,
    })),
    ...carried,
  ].sort((a, b) => a.file.localeCompare(b.file))

  writeFileSync(
    join(OUT_DIR, "CAPTURE.json"),
    JSON.stringify(
      {
        captured_from: API,
        captured_at: capturedAt,
        how: only
          ? `node e2e/fixtures/capture-fixtures.mjs --only ${only}`
          : "node e2e/fixtures/capture-fixtures.mjs",
        anonymous: true,
        // Per-file `captured_at` — a single header date over files of different vintages
        // hides staleness (NF-FRESH2). Read the entry, not the header.
        files,
      },
      null,
      2,
    ) + "\n",
  )
  console.log(`wrote CAPTURE.json (${provenance.length} refreshed, ${carried.length} carried forward)`)
}

if (checkOnly && drift) {
  console.log(`\n${drift} fixture(s) differ from prod. Re-run without --check to refresh.`)
}
