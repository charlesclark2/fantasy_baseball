import { expect, test, type Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, mockTeamLogos } from "../support/api-mock"
import { expectNoPageErrors } from "../support/assertions"
import { signIn } from "../support/signed-in"

/**
 * NCAAF-P3.9 — MAKING THE LIVE SURFACE FINDABLE, AND PUTTING A FACE ON THE CARDS.
 *
 * ══ WHY THIS IS A SPEC AND NOT A SOURCE GUARD ══════════════════════════════════════════════════
 *
 * NF-C4's lesson, applied verbatim: a guard that greps `nav.tsx` for `/ncaaf/games` proves someone
 * TYPED the string. It cannot see that the link is inside a branch that never renders for the
 * visitor who needs it — which is precisely the defect shape this story exists to fix, because the
 * page has been LIVE and unreachable since P3.2 with the route working perfectly the whole time.
 * Every clause below reads the DOM the browser produced, at the viewport and in the auth state a
 * real reader meets.
 *
 * ══ THE FOUR MENUS ═════════════════════════════════════════════════════════════════════════════
 *
 * `Nav` renders FOUR structurally different menus — signed-out bar, signed-out phone panel,
 * signed-in sub-nav, signed-in phone panel — and `/ncaaf/games` is free and unguarded, so the
 * DEFAULT reader of the page sees the signed-OUT pair. A door added only to the sport model would
 * have left the surface exactly as unfindable as it was, so the clauses drive both auth states.
 * They locate the entry by `data-nav-item="ncaaf-games"`, never by its text: with four menus in one
 * component a text locator would silently be asserting about whichever one happened to match.
 */

const SLATE = JSON.parse(
  readFileSync(join(process.cwd(), "e2e", "fixtures", "api", "ncaaf-slate-2026-08-29.json"), "utf8"),
)

const PATH = "/ncaaf/games"

/** Every entry the nav drew for NCAAF, at whatever viewport/auth state the page is currently in.
 *  ⚠️ Scoped to `[data-primary-nav]`: `SiteFooter` wraps its columns in `<nav>`, the collision this
 *  repo has now hit four separate times — and the silent half is the one that matters, since a
 *  footer link would satisfy a loose locator while the nav entry was missing. */
const navEntry = (page: Page) =>
  page.locator('[data-primary-nav] [data-nav-item="ncaaf-games"]:visible')

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 1. NAV — the entry renders, navigates, and says you are here
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a signed-out visitor can reach the NCAAF board from the nav on any page", async ({ page }) => {
  const errors = collectPageErrors(page)
  await mockApi(page)
  await mockTeamLogos(page)

  // ⭐ FROM A PAGE THAT IS NOT THE BOARD. "The nav on /ncaaf/games links to /ncaaf/games" is a
  // tautology; the requirement is that a stranger who has never heard of the surface can find it.
  await page.goto("/about")
  const entry = navEntry(page)
  await expect(entry, "no NCAAF door in the signed-out desktop nav").toHaveCount(1)
  await expect(entry).toHaveText(/NCAAF/i)

  // NAVIGATES — a real click, not an href assertion. `test_e9_56c_cta_routes.py` already proves the
  // href resolves to a route that exists; what only a browser can say is that clicking it arrives.
  await entry.click()
  await page.waitForURL(/\/ncaaf\/games$/)
  await expect(page.getByTestId("ncaaf-game-card").first()).toBeVisible()

  // HIGHLIGHTS. `activeLink="ncaaf-games"` has been passed by the page since P3.2 with nothing
  // reading it; this is the half that makes it mean something.
  await expect(
    navEntry(page),
    "the NCAAF door does not mark itself current while standing on the NCAAF board",
  ).toHaveAttribute("data-nav-active", "true")

  expectNoPageErrors(errors)
})

test("the highlight is a CURRENT-PAGE signal, not a class the entry always carries", async ({
  page,
}) => {
  // ⭐ THE OTHER HALF, and without it "highlights" is satisfied by an entry that is permanently
  // highlighted — which is not a highlight, it is a colour. The one-sided-fix shape the red-proof
  // harness records for the kicked-off badge, on the nav.
  await mockApi(page)
  await page.goto("/about")
  await expect(navEntry(page)).toHaveAttribute("data-nav-active", "false")
})

test("a signed-in visitor gets the NCAAF door too, in the sport-first sub-nav", async ({ page }) => {
  // The signed-in nav is built from an entirely different model (`SPORTS` in `nav-model.ts`), so a
  // door added to the signed-out list alone would vanish the moment a subscriber logs in — the
  // reverse of the defect being fixed, and just as invisible.
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page)
  await mockTeamLogos(page)
  await page.goto(PATH)

  const entry = navEntry(page)
  await expect(entry, "no NCAAF door in the signed-in nav").toHaveCount(1)
  await expect(entry).toHaveAttribute("data-nav-active", "true")
  await expect(entry).toHaveText(/NCAAF/i)
})

test("a bare /ncaaf lands on the board rather than a 404", async ({ page }) => {
  await mockApi(page)
  await mockTeamLogos(page)
  // The URL a reader types, and the one a nav label reading "NCAAF" implies. It 404'd until this
  // story; a redirect is a routing fact, and dev-server routing is not the routing that ships,
  // which is why this suite runs a production build (E9.56c's `/pricing` lesson).
  const response = await page.goto("/ncaaf")
  expect(response?.status(), "/ncaaf did not resolve").toBeLessThan(400)
  await expect(page).toHaveURL(/\/ncaaf\/games$/)
  await expect(page.getByTestId("ncaaf-game-card").first()).toBeVisible()
})

test("the footer offers NCAAF as a live link instead of 'Coming this season'", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  const footer = page.locator("footer")
  const ncaaf = footer.getByRole("link", { name: /NCAAF/i })
  await expect(ncaaf, "the footer still has no NCAAF link").toHaveCount(1)
  await expect(ncaaf).toHaveAttribute("href", "/ncaaf/games")

  // ⭐ AND THE STALE CLAIM IS GONE, which is the half a presence-only assertion cannot see: the
  // footer renders on every page, so "Coming this season" over a live product was the product
  // telling every visitor the opposite of the truth. The heading itself must SURVIVE (NFL betting
  // is genuinely unbuilt) — asserting the whole section away would be the fix overshooting.
  const products = footer.locator('nav[aria-label="Products"]')
  await expect(products).toContainText(/coming this season/i)
  const comingText = await products.innerText()
  const afterHeading = comingText.slice(comingText.toLowerCase().indexOf("coming this season"))
  expect(afterHeading, "NCAAF is still listed under 'Coming this season'").not.toMatch(/NCAAF/i)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 2. LOGOS — decorative, and provably so
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("each card header carries both teams' marks, built from the payload's own ids", async ({
  page,
}) => {
  const errors = collectPageErrors(page)
  await mockApi(page)
  await mockTeamLogos(page)
  await page.goto(PATH)

  const game = SLATE.games[0]
  const header = page
    .locator(`[data-testid="ncaaf-game-card"][data-game-id="${game.game_id}"]`)
    .getByTestId("ncaaf-card-header")

  const logos = header.getByTestId("ncaaf-team-logo")
  await expect(logos).toHaveCount(2)

  // ⭐ THE PAYLOAD'S OWN IDS, never a literal. `team_id` IS the ESPN id — that is the entire reason
  // this rider is frontend-only — so the assertion is that the served id is what reaches the URL.
  // A hardcoded id here would pass just as well against a component that ignored the payload.
  await expect(logos.nth(0)).toHaveAttribute(
    "src",
    `https://a.espncdn.com/i/teamlogos/ncaa/500/${game.away.team_id}.png`,
  )
  await expect(logos.nth(1)).toHaveAttribute(
    "src",
    `https://a.espncdn.com/i/teamlogos/ncaa/500/${game.home.team_id}.png`,
  )

  // ⚠️ `naturalWidth`, NOT `toBeVisible()`. An `<img>` with width/height attributes has a box
  // whether or not a single byte arrived, so `toBeVisible()` passes on a broken image — which is
  // exactly how `static.www.nfl.com` stayed missing from the CSP allowlist unnoticed (E9.46). This
  // asks whether the browser DECODED something.
  for (const i of [0, 1]) {
    const decoded = await logos.nth(i).evaluate((el) => (el as HTMLImageElement).naturalWidth)
    expect(decoded, `logo ${i} rendered a box but decoded nothing`).toBeGreaterThan(0)
  }

  expectNoPageErrors(errors)
})

test("a logo that cannot load renders a stated fallback, never initials", async ({ page }) => {
  const errors = collectPageErrors(page)
  await mockApi(page)
  await mockTeamLogos(page, { broken: true }) // a dead CDN / a CSP refusal / a 404 — same signal
  await page.goto(PATH)

  const game = SLATE.games[0]
  const header = page
    .locator(`[data-testid="ncaaf-game-card"][data-game-id="${game.game_id}"]`)
    .getByTestId("ncaaf-card-header")

  await expect(header.getByTestId("ncaaf-team-logo-fallback")).toHaveCount(2)
  await expect(header.getByTestId("ncaaf-team-logo")).toHaveCount(0)

  // ⭐⭐ E9.46, BOUND BY THIS STORY'S SPEC: the fallback must not read as DATA. Two-letter initials
  // beside a college team ("NC", "TC") are indistinguishable from a real team abbreviation, so a
  // reader would meet a rendering failure believing it was something we published about the team.
  // The clause therefore asserts what must NOT be there, which is the only form that can catch it.
  const fallbackText = (await header.getByTestId("ncaaf-team-logo-fallback").first().innerText()).trim()
  const away: string = game.away.team
  const initials = away.split(/\s+/).map((w: string) => w[0]).join("").slice(0, 2)
  expect(
    fallbackText.toUpperCase(),
    "the fallback renders the team's initials — a failed image wearing the costume of data",
  ).not.toBe(initials.toUpperCase())
  expect(fallbackText.toUpperCase()).not.toContain(away.slice(0, 2).toUpperCase())

  // The team NAME is still there — the mark is decorative, so losing the image must lose nothing.
  await expect(header).toContainText(away)
  expectNoPageErrors(errors)
})

test("a team served with no id gets the fallback without ever requesting an image", async ({
  page,
}) => {
  // The third state, and the one no CDN behaviour can produce: `team_id: null` in the payload. It
  // must not build `…/ncaa/500/null.png` and wait for a 404 to discover what it already knew.
  //
  // ⚠️ THE CDN IS ANSWERED, NOT ABORTED, and the first cut of this clause got it wrong in a way
  // worth recording. Aborting made the OTHER team's logo fail too, so the card carried TWO
  // fallbacks — and the clause passed only while the second `onError` had not yet fired, i.e. it
  // was green for a reason unrelated to what it asserts. Serving the image makes the two teams
  // DIFFER: the null-id side falls back, the served-id side renders, and only the payload can
  // explain the difference.
  const requested: string[] = []
  await mockApi(page, {
    transform: (pathname, body) => {
      if (pathname !== "/ncaaf/games") return body
      const games = body.games.map((g: any, i: number) =>
        i === 0 ? { ...g, away: { ...g.away, team_id: null } } : g,
      )
      return { ...body, games }
    },
  })
  await mockTeamLogos(page)
  await page.route("https://a.espncdn.com/**", async (route) => {
    requested.push(route.request().url())
    await route.fallback() // hand on to `mockTeamLogos`, which answers it
  })
  await page.goto(PATH)

  const header = page.getByTestId("ncaaf-card-header").first()
  await expect(header.getByTestId("ncaaf-team-logo")).toHaveCount(1)
  await expect(header.getByTestId("ncaaf-team-logo-fallback")).toHaveCount(1)
  expect(
    requested.filter((u) => u.includes("null") || u.includes("undefined")),
    "a null team id was turned into a logo URL",
  ).toEqual([])
})
