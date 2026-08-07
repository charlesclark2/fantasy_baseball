#!/usr/bin/env node
/**
 * E9.63 — RED PROOF: break the app on purpose, one defect at a time, and require the suite to FAIL.
 *
 *   npm run e2e:red-proof            # all cases
 *   npm run e2e:red-proof -- blank   # one case, by id substring
 *
 * ══ WHY THIS EXISTS AS A SCRIPT, NOT A ONE-OFF ══════════════════════════════════════════════════
 *
 * A green suite proves nothing on its own. A test that CANNOT fail is worse than no test: it reads
 * as coverage, so nobody looks again. This repo has been bitten by that specific shape more than
 * once (a source-inspection guard a COMMENT could satisfy; a guard on an `and`-composed rule whose
 * fixture was already refused by a different clause, so deleting the clause it named changed
 * nothing). Both were caught only by deliberately breaking the source and noticing the guard stayed
 * green.
 *
 * So each case below re-introduces a REAL, SHIPPED defect — every one of these was live in
 * production — and asserts the named spec goes red. Re-run it whenever the specs are refactored;
 * a case that stops failing means the assertion it names has quietly become decorative.
 *
 * The working tree is restored after every case, including on a crash (see `restoreAll`).
 */

import { execFileSync, spawnSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..")

const CASES = [
  {
    id: "blank-locked-board",
    shipped: "E9.56b — Rankings rendered BLANK for every logged-out visitor",
    detail:
      "`p.pts != null` drops all 858 rows of a locked board, because a locked row carries no `pts`.",
    file: "components/fantasy/rankings-board.tsx",
    from: "(p) => (boardLocked || p.pts != null) &&",
    to: "(p) => p.pts != null &&",
    grep: "locked Rankings",
  },
  {
    id: "nan-in-columns",
    shipped: "E9.56b — the two NaN-class defects",
    // ⭐ DECLARED GREEN. This is a FINDING, not a gap, and pinning it here is what keeps it one.
    //
    // Both shipped NaN defects were COMPARATORS (`-Infinity - -Infinity`, `undefined - undefined`
    // when sorting a locked board). E9.56b's own commit message records why they were invisible:
    // "Array.sort treats a NaN comparator as 0, so it *happens* to leave the server's order
    // intact". Nothing wrong ever reaches the DOM, so no rendered-text scan can see them — they
    // are a unit-level concern and E9.56b already guards them there.
    //
    // The render-level form of the class is a missing null-guard in the shared `num()` formatter,
    // which is what is broken below. MEASURED with that guard removed, across all four
    // page × payload combinations (projections locked / rankings locked / projections entitled /
    // track record): ZERO rendered NaN. On a locked board `numOrLock` short-circuits to a lock
    // chip before `num` is ever reached with a null, and every real payload's numeric fields are
    // non-null (checked: all seven track-record seasons carry no nulls in the three columns they
    // format).
    //
    // ⇒ `expectNoNaN` is a live tripwire for a FUTURE render-level NaN and costs nothing, but it
    // has no reachable trigger today and is NOT presented as proven. If this case ever flips to
    // RED, the class has become observable — update this note and the README rather than deleting
    // the case.
    expect: "GREEN",
    detail: "the shipped form is comparator-only; the render form has no reachable trigger today",
    file: "components/fantasy/shared.tsx",
    from: "  v == null ? \"—\" : v.toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })",
    to: "  Number(v).toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })",
    grep: "renders NaN|no NaN",
  },
  {
    id: "withheld-renders-as-absent",
    shipped: "E9.56c — a withheld value fell through to an em-dash",
    detail:
      "A locked cell rendering '—' says 'we have nothing for this player' instead of 'subscribe to see it'.",
    file: "components/fantasy/shared.tsx",
    from: "): React.ReactNode => (v == null && locked ? <LockChip /> : num(v, nd))",
    to: "): React.ReactNode => num(v, nd)",
    grep: "carries a lock chip",
  },
  {
    id: "dead-cta-route",
    shipped: "E9.56c — the primary CTA pointed at `/pricing`, a route that never existed",
    detail:
      "Killed the entire buy path. Invisible to tsc (a URL is a string) and to next build (it was a plain <a href>).",
    file: "components/fantasy/shared.tsx",
    from: 'export const SUBSCRIBE_HREF = "/subscribe"',
    to: 'export const SUBSCRIBE_HREF = "/pricing-does-not-exist"',
    grep: "route integrity|CTA",
  },
  {
    id: "server-supplied-cta-trusted-verbatim",
    shipped: "E9.56c — the API's `upgrade.ctaHref` was rendered verbatim",
    detail:
      "A server-controlled link target is a server-controlled outage; the API Lambda ships on its own cadence.",
    file: "components/fantasy/shared.tsx",
    from: "  return href && KNOWN_CTA_ROUTES.has(href) ? href : SUBSCRIBE_HREF",
    to: "  return href ?? SUBSCRIBE_HREF",
    grep: "not trusted verbatim",
  },
  {
    id: "no-signup-affordance",
    shipped: "E9.58 — the logged-out nav offered no way to create an account",
    detail:
      "The pre-E9.58 state, and the mobile-only variant of it (`hidden sm:flex`) that a desktop-only suite cannot see.",
    file: "components/nav.tsx",
    from: "<Link href={SIGNUP_HREF}>Sign Up</Link>",
    to: "<span>Sign Up</span>",
    grep: "signup affordance",
  },
  {
    id: "google-entry-missing",
    shipped: "E9.58 — a signup entry point with no working Google button",
    detail: "The DNS-dead-host outage presented to the user as exactly this: no way through.",
    file: "app/subscribe/page.tsx",
    from: "  const googleEnabled = isHostedUiConfigured()",
    to: "  const googleEnabled = false",
    grep: "offers a working Google entry",
  },
]

const selected = process.argv[2]
  ? CASES.filter((c) => c.id.includes(process.argv[2]))
  : CASES
if (!selected.length) {
  console.error(`no case matching "${process.argv[2]}". ids: ${CASES.map((c) => c.id).join(", ")}`)
  process.exit(2)
}

function restoreAll() {
  for (const c of CASES) {
    try {
      execFileSync("git", ["checkout", "--", c.file], { cwd: FRONTEND })
    } catch {
      /* nothing to restore */
    }
  }
}
process.on("exit", restoreAll)
process.on("SIGINT", () => process.exit(130))

const run = (cmd, args) =>
  spawnSync(cmd, args, { cwd: FRONTEND, stdio: "pipe", encoding: "utf8", shell: false })

const results = []

for (const c of selected) {
  const path = join(FRONTEND, c.file)
  const original = readFileSync(path, "utf8")
  if (!original.includes(c.from)) {
    console.log(`SKIP  ${c.id} — anchor not found in ${c.file} (the source moved; update the case)`)
    results.push({ id: c.id, verdict: "STALE" })
    continue
  }

  process.stdout.write(`\n▶ ${c.id}\n  breaking: ${c.shipped}\n  building… `)
  writeFileSync(path, original.replace(c.from, c.to))

  const build = run("npm", ["run", "e2e:build"])
  if (build.status !== 0) {
    // A break that does not compile proves nothing about the E2E suite — `tsc`/the build caught it,
    // which is a different (and welcome) gate. Say so rather than counting it as a pass, and PRINT
    // the tail: a transient build failure and a genuinely-uncompilable break look identical from
    // the exit code alone, and mislabelling one as the other is how a missed case hides.
    console.log("BUILD FAILED — either the build caught this defect, or the build itself flaked:")
    console.log(
      [build.stdout, build.stderr].join("\n").trim().split("\n").slice(-15).join("\n"),
    )
    writeFileSync(path, original)
    results.push({ id: c.id, verdict: "BUILD-CAUGHT" })
    continue
  }

  process.stdout.write("running… ")
  const test = run("npx", ["playwright", "test", "--reporter=line", "--grep", c.grep])
  writeFileSync(path, original)

  const red = test.status !== 0
  const wanted = c.expect ?? "RED"
  const observed = red ? "RED" : "GREEN"
  const ok = observed === wanted

  if (wanted === "GREEN") {
    // A case DECLARED green asserts the opposite property: this defect is genuinely not
    // DOM-observable, and saying so is a finding. If it ever goes red, the boundary moved and the
    // note on the case is now wrong — which is a failure worth surfacing, not a quiet upgrade.
    console.log(
      ok
        ? "GREEN ✅ (declared not-observable — see the case note)"
        : "RED ❌ (declared not-observable, but the suite caught it — the note is now stale)",
    )
  } else {
    console.log(ok ? "RED ✅ (the suite caught it)" : "GREEN ❌ (THE SUITE MISSED IT)")
    if (!ok) console.log(test.stdout.split("\n").slice(-12).join("\n"))
  }
  results.push({ id: c.id, verdict: ok ? (wanted === "GREEN" ? "NOT-OBSERVABLE" : "RED") : "MISMATCH" })
}

// Rebuild clean so the tree is left in a runnable state.
process.stdout.write("\nrestoring clean build… ")
console.log(run("npm", ["run", "e2e:build"]).status === 0 ? "ok" : "FAILED")

console.log("\n── red-proof summary ─────────────────────────────")
for (const r of results) console.log(`  ${r.verdict.padEnd(12)} ${r.id}`)
const bad = results.filter((r) => r.verdict !== "RED" && r.verdict !== "NOT-OBSERVABLE")
if (bad.length) {
  console.log(
    `\n${bad.length} case(s) did not match their declared expectation. The suite is not proving what it claims.`,
  )
  process.exitCode = 1
}
