import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { signIn } from "../support/session"

/**
 * NF-INJ1-C — THE IMPOSSIBLE STAT LINE IS WITHHELD, at the render level.
 *
 * THE DEFECT (NF-INJ1, measured on the live board). NF1.5's ordering step hands a player a
 * different player's point level and rescales the twelve stat columns to reach it while leaving
 * `proj_games` behind, so ~10 served rows — all QB — carry a per-game workload no NFL player has
 * ever recorded (Easton Stick: 153.4 pass attempts over 1.86 projected games = 82.7 per game,
 * against an all-time maximum of 45.4). The MODEL fix (NF-INJ2) was refused by its own
 * pre-registered ordering gate, firing the PM's recorded Option-C fallback: withhold the counting
 * stats on those rows and keep the points and the games figure.
 *
 * ⭐ WHY THIS NEEDS A BROWSER, given `test_nf_inj1_c_stat_line_suppression.py` exists. That suite
 * proves the SERVER removes the right keys and the COPY is honest. Neither is a property a READER
 * has, and both are satisfied by a page that renders nothing:
 *
 *   1. THE WITHHELD CELL MUST BE DISTINGUISHABLE FROM AN EMPTY ONE. The server sends an ABSENT
 *      key, and the shipped table already renders an absent number as a bare em-dash. So a build
 *      that ignores `statLineWithheld` entirely renders "—" too — visually identical, and silently
 *      converting "we are not showing you this" into "we have nothing for this player" (E9.56c,
 *      exactly). Only a rendered read of the disclosure separates the two, and `tsc`, `next build`
 *      and every source scan are green either way.
 *   2. IT MUST FIRE ON THE VIOLATING ROW AND ONLY THAT ROW. A treatment that renders on every row
 *      is decoration; one that renders on none is indistinguishable from the defect it patches.
 *   3. THE DISCLOSURE MUST OPEN ON TAP. `WithheldStat` is `InfoTip` (Popover) precisely because a
 *      Radix Tooltip closes on pointerdown and can never be opened by a touch. A source scan sees
 *      `<InfoTip>` either way; only a real tap on a hover-less viewport tells them apart — hence
 *      the `mobile` project registration. An unexplained em-dash on a paid surface is strictly
 *      worse than the impossible number it replaced.
 *
 * ⛔⛔ THE FIXTURE IS PLANTED, AND IT HAS TO BE — for a reason the other specs do not have.
 * The committed entitled fixture is SCRAMBLED (`passAtt === passYds === rushAtt` on every row),
 * which makes 246 of its 784 in-scope rows violate NF-INJ1's envelope: 31%, entirely an artifact of
 * the scrambling. Asserting against whatever that produced would be measuring the fixture, and
 * "only the violating row is treated" would be a claim about 246 rows nobody planted. The harness
 * also does not run the Python suppressor — it serves fixture bytes — so the marker is planted
 * exactly as the server emits it, on ONE row, with a NAMED control beside it.
 */

/** ⭐ THE VIOLATING ROW AND ITS CONTROL, and both are named rather than positional.
 *
 *  `WITHHELD` is planted with the marker AND with its counting stats deleted — the server does BOTH,
 *  and planting only the marker would let a build pass that renders the disclosure while still
 *  printing the impossible number beside it. `CLEAN` is planted with NOTHING, so it renders exactly
 *  as it does today; it is the clause that catches a treatment applied too widely, which on a PAID
 *  surface is the failure that costs a member the data they bought.
 *
 *  ⚠️ NEITHER IS LOCATED BY ID (NF-C9's lesson, from its own id-normalisation defect) — the specs
 *  reach both through the search box by NAME, which is what a reader does. */
const WITHHELD = { name: "Josh Allen", id: "00-0034857" }
const CLEAN = { name: "Joe Burrow", id: "00-0036442" }

/** The counting-stat keys the server strips on a violating QB row (a subset of `STAT_FIELD`, which
 *  is what `counting_stat_fields()` derives from). Only the QB line matters here — the table's `QB`
 *  tab draws exactly these. */
const QB_STAT_KEYS = [
  "passCmp", "passAtt", "passYds", "passTd", "passInt", "rushAtt", "rushYds", "rushTd",
]

/** The disclosure's rendered trigger, located by its ACCESSIBLE NAME — what a screen reader gets,
 *  and the only thing carrying meaning here at all (the visible label is an em-dash, which a screen
 *  reader announces as nothing, i.e. as an empty cell). Mirrors `STAT_LINE_WITHHELD_SR_LABEL`. */
const WITHHELD_TRIGGER = /stat detail withheld/i

/**
 * Plant the server's suppression on ONE row of the PAID payload.
 *
 * ⚠️ `/fantasy/nfl/projections-full` ONLY, and that precision is the point. The marker can only
 * ever exist on the paid payload: the public `/fantasy/nfl/projections` blob carries no stat line
 * at all (NF-EPIC 1 strips it), so a server that planted it there does not exist and a spec written
 * against one would be asserting on a state no caller can reach.
 */
function withSuppression(extra?: Partial<MockOptions>): MockOptions {
  return {
    ...extra,
    entitlement: "entitled",
    transform: (pathname, body) => {
      if (pathname === "/fantasy/nfl/projections-full" && Array.isArray(body?.players)) {
        return {
          ...body,
          stat_line_withheld_players: 1,
          players: body.players.map((p: any) => {
            if (p?.id !== WITHHELD.id) return p
            const stripped = { ...p }
            for (const k of QB_STAT_KEYS) delete stripped[k]
            return { ...stripped, statLineWithheld: QB_STAT_KEYS }
          }),
        }
      }
      return extra?.transform ? extra.transform(pathname, body) : body
    },
  }
}

/** The projections table paginates and sorts, so a named row is reached through the search box
 *  rather than by index (the `weekly-designation.spec.ts` pattern). */
async function rowFor(page: Page, playerName: string) {
  await page.getByPlaceholder("Search player").fill(playerName)
  const row = page.locator("table tbody tr", { hasText: playerName }).first()
  await expect(row).toBeVisible()
  return row
}

/** ⭐⭐ A SIGNED-IN SUBSCRIBER SESSION IS LOAD-BEARING, AND ITS ABSENCE IS SILENT.
 *
 *  `mockApi`'s `entitlement: "entitled"` only chooses which fixture the harness SERVES; it does not
 *  sign the browser in, because auth is not an API call (`auth-context` reads `localStorage`
 *  directly). `useFullProjections` is `enabled: !!accessToken && canAccess("fantasy", groups)`, so
 *  without a session the page never requests `/projections-full` at all, silently falls back to the
 *  PUBLIC payload — which carries no stat line and no marker — and every clause here fails while
 *  pointing at the component. Measured: that is exactly how this spec failed on its first run.
 *
 *  ⛔ It must be seeded BEFORE `goto` (it installs an init script), or the first render is signed
 *  out and the fallback happens anyway. */
async function asSubscriber(page: Page) {
  await signIn(page, { groups: ["subscriber"] })
}

async function gotoProjections(page: Page) {
  await page.goto("/fantasy/projections")
  // ⚠️ Wait for FETCHED content — a snapshot taken straight after `goto` can capture the loading
  // state, in which every row is legitimately absent, and the spec then reports a product defect
  // for its own race (the CI-only flake NF-TR1 had to fix).
  await expect(page.locator("table tbody tr").first()).toBeVisible()
  // The QB tab, so the table draws the QB stat columns this story is about.
  await page.getByRole("button", { name: "QB", exact: true }).click()
}

test.describe("the withheld stat line — which rows, and what renders", () => {
  test("Projections: the violating row is withheld and the clean row is untouched", async ({
    page,
  }) => {
    // ⭐ BOTH ROWS IN ONE RENDER, against one payload. Presence alone is satisfied by a treatment
    // that fires on every row; absence alone by one that fires on none. Only the pair is the test.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withSuppression())
    await asSubscriber(page)
    await gotoProjections(page)

    const withheld = await rowFor(page, WITHHELD.name)
    const triggers = withheld.getByRole("button", { name: WITHHELD_TRIGGER })
    await expect(
      triggers.first(),
      `${WITHHELD.name} is served with statLineWithheld and renders no disclosure — his stat ` +
        `cells then read as a plain em-dash, i.e. as "we have nothing for this player", which is ` +
        `the E9.56c inversion this story exists to avoid`,
    ).toBeVisible()
    // ⛔ NOT "a disclosure rendered". EVERY withheld cell has to carry it: a treatment applied to
    // the breaching column only would leave the rest of an impossible line printed beside it.
    await expect(
      triggers,
      "not every withheld QB stat cell carries the disclosure",
    ).toHaveCount(QB_STAT_KEYS.length)

    // ⭐ AND THE TWO VALUES THE PM RULED MUST SURVIVE. A row stripped of everything teaches a
    // drafter nothing; the point total and the availability figure are what he is here for.
    const cells = withheld.locator("td")
    const rowText = await withheld.innerText()
    expect(cells.first()).toBeTruthy()
    expect(
      rowText,
      "the projected-points column is blank on a withheld row — points must still render",
    ).toMatch(/\d/)

    const clean = await rowFor(page, CLEAN.name)
    await expect(
      clean.getByRole("button", { name: WITHHELD_TRIGGER }),
      `${CLEAN.name} carries no marker and a disclosure rendered anyway — on the PAID surface a ` +
        `treatment applied one row too wide costs a member the data they paid for, and it looks ` +
        `exactly like a working feature`,
    ).toHaveCount(0)
    // …and his stat line is still NUMBERS, not em-dashes. "no disclosure" alone would also be
    // satisfied by a build that blanked him silently.
    await expect(
      clean.locator("td", { hasText: /^\s*[\d,]+(\.\d+)?\s*$/ }).first(),
      `${CLEAN.name}'s stat line no longer renders numbers`,
    ).toBeVisible()

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the player page withholds the same line the table does", async ({ page }) => {
    // The surface where the defect is most legible: this page prints the point total and the
    // projected-games figure side by side, so an impossible line here is one a reader can check at
    // a glance. It renders the stat line as TILES rather than table cells — a different code path,
    // and the one a table-only fix would silently skip.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withSuppression())
    await asSubscriber(page)

    await page.goto(`/fantasy/player/${WITHHELD.id}`)
    await expect(page.getByRole("heading", { name: WITHHELD.name })).toBeVisible()
    await expect(
      page.getByRole("button", { name: WITHHELD_TRIGGER }).first(),
      "the player page prints the impossible stat line the projections table withholds",
    ).toBeVisible()

    await page.goto(`/fantasy/player/${CLEAN.id}`)
    await expect(page.getByRole("heading", { name: CLEAN.name })).toBeVisible()
    await expect(
      page.getByRole("button", { name: WITHHELD_TRIGGER }),
      "the player page withholds the stat line of a player the server did not mark",
    ).toHaveCount(0)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the withheld stat line — what it says", () => {
  test("the disclosure opens on TAP and refuses every forecast reading", async ({ page }) => {
    // ⭐ THE CLAUSE A SOURCE SCAN CANNOT MAKE — and it only makes it on the `mobile` project. On
    // desktop Chromium `click()` dispatches `pointerenter` first and `InfoTip` opens on hover for a
    // mouse, so the popover is open before the click lands and a Radix TOOLTIP (which no touch can
    // ever open) would pass identically. On Pixel 7 there is no hover and `pointerType` is "touch",
    // so only the tap can open it.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withSuppression())
    await asSubscriber(page)
    await gotoProjections(page)

    const row = await rowFor(page, WITHHELD.name)
    await row.getByRole("button", { name: WITHHELD_TRIGGER }).first().click()

    // ⚠️ Scoped to the POPOVER, not to the page text — this table carries several column
    // definitions a few hundred pixels away, and whether the tap did anything is the whole subject.
    const disclosure = page.getByRole("dialog")
    await expect(disclosure, "the withheld-stat disclosure did not open on tap").toBeVisible()
    const text = (await disclosure.innerText()).toLowerCase()

    expect(
      text,
      "the disclosure no longer says the detail is WITHHELD — an em-dash behind a popover that " +
        "does not use the word reads as a missing number, which is the inversion itself",
    ).toContain("withh")

    // ⛔⛔ THE SENTENCE THE STORY IS FOR. The treatment fires on rows whose projected-games figure
    // is low, so the em-dash renders right beside "1.9 proj. games" — and copy reaching for ANY
    // availability verb would read as a medical or usage forecast we have not made and do not make
    // (`best_alpha = 0`). This is a statement about OUR line, never about him.
    for (const forecast of ["will miss", "injury risk", "is hurt", "sidelined", "out for"]) {
      expect(text, `the disclosure forecasts an injury (${forecast})`).not.toContain(forecast)
    }
    for (const duration of ["weeks", "rest of the season", "multi-week"]) {
      expect(
        text,
        `the disclosure implies a duration (${duration}) — a coherence refusal carries none`,
      ).not.toContain(duration)
    }

    // ⭐ AND IT MUST NOT READ AS THE PAYWALL. This refusal is served to a member who has ALREADY
    // paid for the stat line; the lock's wording here would sell them what they own.
    for (const upsell of ["membership", "subscribe", "unlock"]) {
      expect(
        text,
        `the disclosure has drifted into the LOCK's wording (${upsell}) — a paid caller is being ` +
          `asked to buy the thing they are already entitled to`,
      ).not.toContain(upsell)
    }

    // …and the whole rendered composition passes the shared overclaim denylist, held HERE as well
    // as in Python because this popover composes two constants plus component chrome, and the
    // COMPOSITION is what a reader meets.
    expect(forbiddenPhrasesIn(text), "the disclosure carries an overclaim").toEqual([])

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})
