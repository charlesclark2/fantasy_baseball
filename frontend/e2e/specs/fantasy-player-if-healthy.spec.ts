import { expect, test } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * NF-C · "if healthy" comparability + the served-stack methodology note, at the render level.
 *
 * `fullSeasonRate`/`MIN_GAMES_FOR_FULL_SEASON_RATE` and `ProjectionMethodologyNote` are all pure
 * functions — `test_freemium_tier.py` already pins their arithmetic and their source shape. Neither
 * proves what a real player row RENDERS, which is the property that matters:
 *
 *   · the full-season rate reaching the player page's free Full-PPR tile, as a real number.
 *   · the NF-C7 low-denominator trap — a player with a small but POSITIVE expected-games figure —
 *     actually being refused on the page, not merely in the helper. `g` between 0 and the floor is
 *     a payload state the committed fixtures never carry, so this is `transform`, the harness's
 *     sanctioned way to model a server state we cannot capture (see `api-mock.ts`'s own doc).
 *   · the methodology note degrading gracefully clause-by-clause against the REAL committed
 *     manifest fixture (which predates NF-TR2b — so the level-recalibration clause must be ABSENT),
 *     and appearing once the served stamp is present.
 */

test.describe("the full-season rate on the player page", () => {
  test("renders as a real number beside the free Full-PPR total", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)
    const { id, g, fpPpr } = FIXTURES.projectionsEntitled().players[0]
    expect(g, "fixture assumption: the first player has a normal games figure").toBeGreaterThan(2)

    await page.goto(`/fantasy/player/${id}`)
    await expect(page.getByTestId("format-tile-ppr")).toBeVisible()

    const tileText = await page.getByTestId("format-tile-ppr").innerText()
    expect(tileText).toContain("Full-season rate:")
    const rendered = tileText.match(/Full-season rate:\s*([\d,.]+)/)?.[1]
    expect(rendered, `no full-season-rate value in "${tileText}"`).toBeTruthy()

    // Pin the arithmetic against the SAME fixture values the page fetched — pts × 17 ÷ g.
    const expectedRate = ((fpPpr as number) * 17) / (g as number)
    expect(Number(rendered!.replace(/,/g, ""))).toBeCloseTo(expectedRate, 1)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("a player projected for too few games to trust a rate shows no such line — never ∞", async ({
    page,
  }) => {
    // ⭐ THE NF-C7 LOW-DENOMINATOR TRAP, one arithmetic step over: `pts * 17 / g` on a small but
    // POSITIVE `g` amplifies noise into a number that looks real and is not — worse than the
    // already-guarded `g === 0` case (`Infinity`, at least visibly absurd) because it is a
    // plausible-looking wrong number. `MIN_GAMES_FOR_FULL_SEASON_RATE` exists to refuse it.
    const errors = collectPageErrors(page)
    const { id, fpPpr } = FIXTURES.projectionsEntitled().players[0]
    const mock = await mockApi(page, {
      transform: (pathname, body) => {
        if (pathname !== "/fantasy/nfl/projections") return body
        const players = (body as any).players.map((p: any) => (p.id === id ? { ...p, g: 1.5 } : p))
        return { ...(body as any), players }
      },
    })

    await page.goto(`/fantasy/player/${id}`)
    await expect(page.getByTestId("format-tile-ppr")).toBeVisible()

    // The free total itself is untouched — only the rate derived from it is refused.
    await expect(page.getByTestId("format-tile-ppr-value")).toHaveText(new RegExp(String(fpPpr)))

    const tileText = await page.getByTestId("format-tile-ppr").innerText()
    expect(tileText, "a full-season rate rendered for a below-floor games figure").not.toContain(
      "Full-season rate:",
    )

    await expectNoNaN(page)
    expect(
      (await page.locator("body").innerText()).includes("∞"),
      "a low-denominator blow-up reached the rendered page",
    ).toBe(false)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the served-stack methodology note", () => {
  test("names MVP-1 and NF1.5 from the committed (pre-NF-TR2b) manifest, and omits the level clause it predates", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)
    const { id } = FIXTURES.projectionsEntitled().players[0]

    await page.goto(`/fantasy/player/${id}`)
    const note = page.getByTestId("projection-methodology-note")
    await expect(note, "the served-stack methodology note never rendered").toBeVisible()

    const text = await note.innerText()
    expect(text).toContain("How this projection is built")
    expect(text).toContain("MVP-1")
    expect(text).toContain("NF1.5")
    // ⭐ Honest degradation: the committed manifest fixture predates NF-TR2b (no
    // `veteran_level_policy` stamp), so the note must not claim a recalibration that this build's
    // own manifest does not carry — never a hard-coded model-version string.
    expect(
      text,
      "the note claims a veteran-level recalibration the committed manifest never stamped",
    ).not.toContain("nfl_fantasy_nf_tr2b_veteran_level_v1")

    expect(forbiddenPhrasesIn(text), `denied claim language in the methodology note: ${text}`).toEqual(
      [],
    )

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("names the live NF-TR2b veteran-level model once the manifest carries the stamp", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    const { id } = FIXTURES.projectionsEntitled().players[0]
    const mock = await mockApi(page, {
      transform: (pathname, body) => {
        if (pathname !== "/fantasy/nfl/manifest") return body
        return {
          ...(body as any),
          projections: {
            ...(body as any).projections,
            veteran_level_policy: {
              status: "recalibrated",
              form: "pos_const",
              source_model: "NF-TR2b",
              level_model_version: "nfl_fantasy_nf_tr2b_veteran_level_v1",
            },
          },
        }
      },
    })

    await page.goto(`/fantasy/player/${id}`)
    const note = page.getByTestId("projection-methodology-note")
    await expect(note).toBeVisible()

    const text = await note.innerText()
    expect(text).toContain("MVP-1")
    expect(text).toContain("NF1.5")
    expect(text).toContain("nfl_fantasy_nf_tr2b_veteran_level_v1")
    expect(text.toLowerCase()).toContain("live")

    expect(forbiddenPhrasesIn(text), `denied claim language in the methodology note: ${text}`).toEqual(
      [],
    )

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})
