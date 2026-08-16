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
  {
    file: "subscription-public-pricing.json",
    path: "/subscription/public-pricing",
    note: "Public price (E9.59). Read server-side from the Stripe Price object Checkout charges against — so this capture is the number a logged-out visitor actually sees. ⚠️ Stripe TEST mode until E9.8-P2; the amount will change at the live flip and this fixture should be re-captured then.",
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
  const res = await fetch(url)
  if (!res.ok) {
    console.error(`FAIL  ${res.status} ${url}`)
    process.exitCode = 1
    continue
  }
  // Re-serialize rather than storing the raw bytes: a stable 2-space form keeps the diff of a
  // re-capture readable instead of a single 267 KB line.
  const body = JSON.stringify(await res.json(), null, 2) + "\n"
  const out = join(OUT_DIR, t.file)
  const prev = existsSync(out) ? readFileSync(out, "utf8") : null

  if (checkOnly) {
    const same = prev === body
    if (!same) drift++
    console.log(`${same ? "same" : "DRIFT"}  ${t.file}  (${body.length} bytes)`)
  } else {
    writeFileSync(out, body)
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
  const files = [
    ...provenance.map((p) => ({ ...p, captured_at: capturedAt })),
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
