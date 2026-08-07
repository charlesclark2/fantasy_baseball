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

test.describe("public Track Record — NF-TR1 claim governance", () => {
  test("calibration leads; the benchmark comparison comes after it", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)

    await page.goto("/fantasy/track-record")
    await expect(page.getByText("What you get")).toBeVisible()
    await expect(page.getByText("The honest read")).toBeVisible()

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
    await page.goto("/fantasy/track-record")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

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
    await page.goto("/fantasy/track-record")

    const lead = await page.locator("h2", { hasText: "The honest read" }).locator("..").innerText()
    expect(lead.toLowerCase(), "the lead no longer says the gap is small").toContain("gap is small")
    expect(lead.toLowerCase(), "the lead no longer says it varies by season").toContain("year to year")
    expect(lead.toLowerCase(), "the lead no longer names a position where it is level")
      .toContain("basically even")
    expect(lead.toLowerCase(), "the lead dropped the could-be-luck hedge while the measured " +
      "interval still includes zero").toContain("could just be luck")

    expectApiFullyMocked(mock)
  })

  test("the position table is visible without expanding anything, and RB reads as a wash", async ({
    page,
  }) => {
    // The disclosure that costs us something is the one most likely to end up behind an expander.
    const mock = await mockApi(page)
    await page.goto("/fantasy/track-record")

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
    await page.goto("/fantasy/track-record")
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
    await page.goto("/fantasy/track-record")
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
