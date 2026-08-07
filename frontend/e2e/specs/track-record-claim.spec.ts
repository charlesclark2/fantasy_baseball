import { expect, test, type Locator, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

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
    expect(lead.toLowerCase(), "the lead no longer names a position where it is level")
      .toContain("basically even")
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

  test("the position table is visible without expanding anything, and RB reads as a wash", async ({
    page,
  }) => {
    // The disclosure that costs us something is the one most likely to end up behind an expander.
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    const table = page.locator("table").filter({ hasText: "Gap vs. draft-day consensus" })
    await expect(table).toBeVisible()
    const rbRow = table.locator("tbody tr", { hasText: "RB" })
    await expect(rbRow).toContainText("too close to call")
    // ⚠️ And it must carry NO direction sign. The measured value is `-0.0`, and `-0.0 >= 0` is
    // true in JavaScript — so the natural formatter renders a wash as "+0.000", putting a plus in
    // front of the one row this story requires be legible as a wash.
    expect(
      (await rbRow.innerText()).replace(/RB/g, ""),
      "the level position renders a direction sign it has not earned",
    ).not.toMatch(/[+−-]\s*0/)

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
    expect(text, "the seasons are not stated").toContain("2019–2024")
    expect(text, "the player count is not stated").toMatch(/about \d+ per season/)
    expect(text, "the interval is not shown").toContain("includes zero")

    expectApiFullyMocked(mock)
  })

  test("all six required disclosures render", async ({ page }) => {
    const mock = await mockApi(page)
    await gotoTrackRecord(page)
    const text = (await renderedText(page)).toLowerCase()

    for (const [name, marker] of [
      ["RB is a wash", "it is a wash"],
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
    const mock = await mockApi(page)

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
