import { expect, test, type Locator, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { readFileSync } from "node:fs"
import { join } from "node:path"

// The fixture's `claim` block IS the shipping builder's output over the committed NF-D3/NF-D17
// artifacts (`betting_ml/tests/test_nf_tr1_claim_copy.py` pins it byte-for-byte). Reading the
// expectations from it — rather than from literals like "2019–2024" / "it is a wash" — is what
// lets a deliberate track-record refresh (NF-TR2b archived the 2025 ADP: 7 seasons, RB now
// "behind") re-pin this spec by regenerating ONE file instead of silently going red.
const CLAIM = JSON.parse(
  readFileSync(join(process.cwd(), "e2e", "fixtures", "api", "fantasy-nfl-track-record-manifest.json"), "utf8"),
).claim as {
  seasons: string
  byPosition: { position: string; deltaRho: number; verdict: "ahead" | "behind" | "even" }[]
}
const READS_AS = { ahead: "we ranked closer", behind: "they ranked closer", even: "too close to call" } as const
const RB = CLAIM.byPosition.find((r) => r.position === "RB")!

/**
 * NF-TR1 — COPY GOVERNANCE, at the render level.
 *
 * `betting_ml/tests/test_nf_tr1_claim_copy.py` proves the EXPORT produces honest copy. It cannot
 * prove the PAGE shows it: the two failures this file exists for are both invisible there —
 *
 *   1. ORDER. "Calibration appears before the benchmark comparison" is an acceptance criterion
 *      about what a visitor meets first. A build-time rule about sentence order inside `claim.lead`
 *      says nothing about where the component puts the blocks, and the Python guard can only read
 *      JSX source. This reads the rendered geometry.
 *   2. STATIC COMPONENT COPY. Headings, table labels, CTA text and empty states never pass through
 *      `build_claim`, so no export-side denylist has ever seen them — and they are exactly where a
 *      copy edit would put "beat ADP". The scan below runs over the whole rendered document.
 *
 * ⚠️ THE ENTIRE PAGE IS SCANNED, not just the claim block. A denylist applied only to the element
 * we already know is screened would be a restatement of the Python suite.
 */

/** Vertical position of an element's box — the honest form of "appears before" on a page. */
async function topOf(locator: Locator): Promise<number> {
  const box = await locator.first().boundingBox()
  expect(box, "element is not laid out, so its position cannot be compared").not.toBeNull()
  return box!.y
}

async function renderedText(page: Page): Promise<string> {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ")
}

/**
 * Navigate to the Track Record and wait until the CLAIM has actually rendered.
 *
 * ⚠️ WHY THIS IS A HELPER AND NOT A BARE `goto`. `renderedText` is a SNAPSHOT of `body.innerText`,
 * and the manifest arrives over an async fetch — so a whole-page text scan taken straight after
 * `goto` can capture the LOADING state, in which every disclosure is legitimately absent. That is
 * a race in the TEST, and it reports as a product defect ("required disclosure missing from the
 * page") which is the most expensive possible way to be wrong.
 *
 * It shipped exactly that way and CI caught it: "all six required disclosures render" passed on
 * this laptop every time — including 12 consecutive runs at `--workers=2` — and failed on both
 * attempts on a slower 2-worker runner. Measured afterwards with the manifest delayed 1200ms: the
 * bare-`goto` sequence reproduces the failure and this one does not.
 *
 * ⭐ IT DOES NOT WEAKEN ANY ASSERTION. A page that never renders the claim still FAILS here, on
 * the visibility wait, with a clearer message than a substring miss against the loading state —
 * and `nf-tr1: disclosure-dropped` in `e2e/red-proof.mjs` proves the disclosures test still goes
 * red when a disclosure is genuinely absent rather than merely late.
 */
async function gotoTrackRecord(page: Page) {
  await page.goto("/fantasy/track-record")
  await expect(page.getByText("The honest read")).toBeVisible()
  await expect(page.locator("table tbody tr").first()).toBeVisible()
}

test.describe("public Track Record — NF-TR1 claim governance", () => {
  test("calibration leads; the benchmark comparison comes after it", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)

    await gotoTrackRecord(page)
    await expect(page.getByText("What you get")).toBeVisible()

    const calibrationTop = await topOf(page.getByText("What you get"))
    const claimTop = await topOf(page.getByText("The honest read"))
    expect(
      calibrationTop,
      "the benchmark comparison renders above the calibration hook — that makes a gap whose own " +
        "interval includes zero the product's headline promise",
    ).toBeLessThan(claimTop)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the rendered page makes no forbidden market or edge claim", async ({ page }) => {
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    // Open the fine print too: a denied phrase hiding inside a collapsed <details> still ships.
    await page.getByText("How we measured this").click()

    const hits = forbiddenPhrasesIn(await renderedText(page))
    expect(hits, `the Track Record page renders forbidden claim language: ${hits.join(", ")}`)
      .toEqual([])

    expectApiFullyMocked(mock)
  })

  test("the plain lead keeps its hedges", async ({ page }) => {
    // ⭐ The failure mode NF-TR1 exists to prevent is a plainer lead that sounds punchier because
    // the hedges came off. Each is asserted separately so a red run names which one was dropped.
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    const lead = await page.locator("h2", { hasText: "The honest read" }).locator("..").innerText()
    expect(lead.toLowerCase(), "the lead no longer says the gap is small").toContain("gap is small")
    expect(lead.toLowerCase(), "the lead no longer says it varies by season").toContain("year to year")
    // The position clause is DERIVED from `delta_rho_by_pos`: a wash prints "basically even", a
    // position the crowd led prints "the crowd's order was slightly better than ours". Either is the
    // hedge; a lead that names NEITHER has dropped it (2026-08-15: RB slid −0.000 → −0.010 and the
    // wash clause correctly disappeared — the behind clause must take its place, not silence).
    expect(
      /basically even|crowd's order was slightly better than ours/.test(lead.toLowerCase()),
      "the lead no longer names a position with a direction word (even / behind)",
    ).toBe(true)
    expect(lead.toLowerCase(), "the lead dropped the could-be-luck hedge while the measured " +
      "interval still includes zero").toContain("could just be luck")

    // ⛔ …and it must not STOP there. Every hedge above stays; what changes is what the reader is
    // left holding. A block that ends on its own disclaimer reads as an apology, and this page's
    // job is to earn trust with the evidence attached. Asserted BESIDE the hedges, in the same
    // test, so the trade is visible: the trivially-wrong way to pass this line is to delete a
    // caveat, and the four assertions above forbid exactly that.
    expect(
      lead.trim().toLowerCase(),
      "the plain lead ends on a caveat instead of pointing at the evidence below it",
    ).toMatch(/detail is below[^.]*crowd was drafting them\.$/)

    expectApiFullyMocked(mock)
  })

  test("the position table is visible without expanding anything, and RB reads as measured", async ({
    page,
  }) => {
    // The disclosure that costs us something is the one most likely to end up behind an expander.
    // At NF-TR1 RB measured -0.000 and had to read "too close to call"; after the NF-TR2b refresh it
    // measures -0.010 and must read "they ranked closer". Either way the row must carry the
    // measured verdict's words and never be rounded UP to "we ranked closer".
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    const table = page.locator("table").filter({ hasText: "Gap vs. draft-day consensus" })
    await expect(table).toBeVisible()
    const rbRow = table.locator("tbody tr", { hasText: "RB" })
    await expect(rbRow).toContainText(READS_AS[RB.verdict])
    expect(RB.deltaRho <= 0 && RB.verdict === "ahead", "a non-positive RB gap rounded up to ahead").toBe(false)
    if (RB.verdict === "even") {
      // ⚠️ A wash must carry NO direction sign. The measured value is `-0.0`, and `-0.0 >= 0` is
      // true in JavaScript — so the natural formatter renders a wash as "+0.000", putting a plus in
      // front of the one row this story requires be legible as a wash.
      expect(
        (await rbRow.innerText()).replace(/RB/g, ""),
        "the level position renders a direction sign it has not earned",
      ).not.toMatch(/[+−-]\s*0/)
    }

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
  })

  test("the fine print names the benchmark, the metric, the sample and the interval", async ({
    page,
  }) => {
    // The precise layer was RELOCATED below a plain lead, never deleted — this is the assertion
    // that keeps "relocated" from quietly becoming "dropped".
    const mock = await mockApi(page)
    await gotoTrackRecord(page)
    await page.getByText("How we measured this").click()

    const text = await renderedText(page)
    expect(text, "the approved sentence is not on the page").toContain(
      "modestly outperformed the captured ADP benchmark",
    )
    expect(text, "the metric is not named").toContain("rank correlation")
    expect(text, "the seasons are not stated").toContain(CLAIM.seasons)
    expect(text, "the player count is not stated").toMatch(/about \d+ per season/)
    expect(text, "the interval is not shown").toContain("includes zero")

    expectApiFullyMocked(mock)
  })

  test("all six required disclosures render", async ({ page }) => {
    const mock = await mockApi(page)
    await gotoTrackRecord(page)
    const text = (await renderedText(page)).toLowerCase()

    // the level-position slot: "it is a wash" while a position measures level (NF-TR1); once none
    // does (NF-TR2b: RB -0.010 = behind) the page must SAY no position measured level
    const anyLevel = CLAIM.byPosition.some((r) => r.verdict === "even")
    for (const [name, marker] of [
      ["level-position statement", anyLevel ? "it is a wash" : "no position measured level"],
      ["ECR/ESPN/Sleeper reported separately", "reported separately"],
      ["ordering uses market consensus", "blends the market"],
      ["not a guarantee", "not a guarantee"],
      ["interval is visible", "range around the measured gap"],
      ["frozen-board method", "before that season kicked off"],
    ] as const) {
      expect(text, `required disclosure missing from the page: ${name}`).toContain(marker)
    }

    expectApiFullyMocked(mock)
  })

  test("an artifact published before NF-TR1 still leads with calibration", async ({ page }) => {
    // ⚠️ THE DEPLOY-SKEW RENDER, AND IT IS ASYMMETRIC. `frontend/` auto-deploys on merge; the
    // artifact only grows its `claim` block when the operator re-runs the exporter with
    // `--publish`. In that window the served manifest is a PRE-NF-TR1 one, whose `headline` is the
    // old un-hedged analyst sentence. The page must degrade by demoting that string to fine print,
    // never by promoting it into the lead — which is what an innocuous-looking
    // `claim?.lead ?? headline` fallback would do.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, {
      transform: (pathname, body) => {
        if (pathname !== "/fantasy/nfl/track-record/manifest") return body
        const { claim, ...rest } = body
        return { ...rest, headline: "So we finished ahead, by a narrow margin." }
      },
    })

    // ⛔ NOT `gotoTrackRecord` — this render deliberately has NO claim block, so that helper's
    // "The honest read" wait would time out. The waits below are its equivalent for this branch:
    // the static hook, and the season rows that prove the page really rendered rather than merely
    // being early. Do not "tidy" this into the helper.
    await page.goto("/fantasy/track-record")
    await expect(page.getByText("What you get")).toBeVisible()
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const calibrationTop = await topOf(page.getByText("What you get"))
    const finePrintTop = await topOf(page.getByText("How we measured this"))
    expect(calibrationTop).toBeLessThan(finePrintTop)

    // The legacy sentence must not be sitting in the open above the fine print.
    await expect(page.getByText("So we finished ahead")).toBeHidden()

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

/**
 * ⭐ THE OTHER HALF OF THE REFRAME — the MARKETING surface.
 *
 * The Track Record page is the destination a skeptical visitor opts into, and every hedge lives
 * there. The locked board is where a visitor ARRIVES, and it must sell the product: a board built
 * for their league, plus the decision support that is the paid half. It links to the record; it
 * does not recite it.
 *
 * ⚠️ Both halves need their own test and neither implies the other. A page can quote the stat
 * while still linking (the pre-NF-TR1 state), and a page can drop the quotation while ALSO losing
 * the link — which passes any "no forbidden claim" scan and leaves the evidence unreachable.
 */
test.describe("locked board — the track record is a trust LINK, not the pitch", () => {
  const STAT_FRAGMENTS = [
    "modestly outperformed",
    "could just be luck",
    "rank correlation",
    "0.517",
    "0.494",
    "+0.022",
  ]

  test("the upgrade banner sells the product and does not recite the measurement", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    // 🗄️ EXPLICITLY THE LOCKED MODE SINCE THE FREEMIUM BUILD. `UpgradeBanner` renders only when the
    // payload says `locked`, which no live caller now receives — so without naming the mode this
    // test navigated to a free board, found no banner, and failed on its own premise rather than
    // on a defect. The banner is retained (withdrawing the open board must stay a config decision,
    // not a rebuild), so its NF-TR1 copy contract is still worth holding.
    //
    // ⭐ THE SAME CONTRACT ON THE *LIVE* SURFACE IS HELD SEPARATELY, and this test cannot cover it:
    // the conversion surface a real visitor now meets is `FreemiumBoundary`, asserted in
    // `freemium-board.spec.ts`. Both are needed — this one would go on passing while the live
    // surface quietly grew a quotation of the statistic.
    const mock = await mockApi(page, { entitlement: "locked" })

    await page.goto("/fantasy/projections")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const text = await renderedText(page)
    for (const fragment of STAT_FRAGMENTS) {
      expect(
        text,
        `the locked board recites the track-record measurement (${fragment}) — that belongs on ` +
          "the page that can show its working, not on a conversion surface",
      ).not.toContain(fragment)
    }

    // What it says instead: the wedge, and the paid half stated as decision support.
    expect(text.toLowerCase(), "the banner does not state the free/paid division of labour")
      .toContain("helps you decide")
    expect(text.toLowerCase(), "the consensus reference is not framed as content")
      .toContain("furthest from where the crowd")

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the trust link reaches a Track Record page that actually renders", async ({ page }) => {
    // A link is only trust-building if it lands somewhere real — and this is the exact shape of
    // E9.56c's dead `/pricing` CTA, one surface over.
    const mock = await mockApi(page)
    await page.goto("/fantasy/projections")

    const link = page.getByRole("link", { name: "See the track record" }).first()
    await expect(link).toBeVisible()
    await link.click()

    await expect(page).toHaveURL(/\/fantasy\/track-record$/)
    await expect(page.getByText("What you get")).toBeVisible()
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    expectApiFullyMocked(mock)
  })

  test("the locked board makes no forbidden market or edge claim", async ({ page }) => {
    const mock = await mockApi(page)
    await page.goto("/fantasy/projections")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const hits = forbiddenPhrasesIn(await renderedText(page))
    expect(hits, `the locked board renders forbidden claim language: ${hits.join(", ")}`).toEqual([])

    expectApiFullyMocked(mock)
  })
})
