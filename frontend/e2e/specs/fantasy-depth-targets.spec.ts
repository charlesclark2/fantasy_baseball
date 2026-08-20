// NF-C7 — the per-position DEPTH TARGET control, asserted on RENDERED OUTPUT.
//
// ⭐ WHY RENDERED, NOT SOURCE (NF-C4). A frontend guard that greps source, or walks a `className`
// string, tests that somebody TYPED something — not that the page shows it. Every clause here reads
// the DOM or a computed layout value.
//
// ⭐ AND WHY IT MATTERS ON *THIS* FEATURE. The control is shared by two near-duplicate setup screens
// (`draft-optimizer.tsx` and `mock-draft.tsx`) which have drifted before, and it persists through
// `localStorage` under a key both must agree on. A copy on one screen that read a different key
// would apply the user's preference on one surface and silently ignore it on the other — the E9.61
// "two renderers of one field are two rule sets" class, on a saved setting.
import fs from "node:fs"
import path from "node:path"
import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectNoPageErrors } from "../support/assertions"
import { signIn } from "../support/session"

const SURFACES = [
  { name: "the live draft optimizer", path: "/fantasy/draft", start: "Start draft" },
  { name: "the mock draft", path: "/fantasy/mock-draft", start: "Start mock draft" },
] as const

async function openSetup(page: Page, path: string) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", leagues: "none" })
  await page.goto(path)
  await expect(page.getByLabel("RB depth target")).toBeVisible()
  return errors
}

for (const surface of SURFACES) {
  test(`the depth-target control renders one box per position — ${surface.name}`, async ({ page }) => {
    const errors = await openSetup(page, surface.path)

    // The league preset the setup screen opens on starts QB/RB/WR/TE/K/DST, so all six are offered.
    for (const pos of ["QB", "RB", "WR", "TE", "K", "DST"]) {
      await expect(
        page.getByLabel(`${pos} depth target`),
        `${surface.name} does not offer a ${pos} depth target`,
      ).toBeVisible()
    }
    // ⭐ THE DEFAULT IS OFF, and it is asserted on the RENDERED value rather than on the constant:
    // shipping this "on" would apply an unmeasured ranking to every user who never touched it.
    await expect(page.getByLabel("QB depth target")).toHaveValue("0")
    await expect(page.getByLabel("RB depth target")).toHaveValue("0")

    // The starter requirement is rendered beside the box, because a bare "2" means nothing without
    // it. ⚠️ Asserted as TEXT: it lives in the label, not in the input's placeholder, which a
    // 0-valued NumericInput can never show.
    await expect(page.getByText("· starts 1").first()).toBeVisible()

    expectNoPageErrors(errors)
  })

  test(`a depth target survives a reload and reaches the other surface — ${surface.name}`, async ({
    page,
  }) => {
    const errors = await openSetup(page, surface.path)
    await page.getByLabel("QB depth target").fill("2")
    await page.getByLabel("QB depth target").blur()
    await expect(page.getByLabel("QB depth target")).toHaveValue("2")

    await page.reload()
    await expect(
      page.getByLabel("QB depth target"),
      "the depth target did not survive a reload — it is not being persisted",
    ).toHaveValue("2")

    // ⭐ THE CROSS-SURFACE CLAIM, which is the reason the control is one shared component. A second
    // copy with its own storage key would pass every clause above and fail only here.
    const other = SURFACES.find((s) => s.path !== surface.path)!
    await page.goto(other.path)
    await expect(
      page.getByLabel("QB depth target"),
      `a depth target set on ${surface.name} did not reach ${other.name} — the two surfaces are ` +
        "reading different storage keys",
    ).toHaveValue("2")

    expectNoPageErrors(errors)
  })
}

test("a depth target changes the reason shown beside a recommendation", async ({ page }) => {
  // ⚠️ ASSERTED ON THE RENDERED SENTENCE, not on an engine field. The first cut of this feature was
  // a weighted score bonus: it applied correctly, moved `score` by a fraction of a point and never
  // reached a panel. A clause reading an internal field would have called that a pass.
  //
  // ⭐ THE DRAFT IS SEEDED, NOT PLAYED. A depth target may only speak once every STARTING slot is
  // filled, which is ~9 rounds in — and clicking a hundred picks to get there timed the first cut
  // of this test out at 180s while proving nothing the seed cannot. The live tool restores an
  // in-progress draft from `localStorage`, so the state is planted and the panel is read on the
  // first render. Same component, same engine, one page load.
  const board = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "../fixtures/api/fantasy-nfl-board-full_ppr-12-2026-free.json"),
      "utf8",
    ),
  ) as { id: string; pos: string }[]
  const bestAt = (pos: string, n: number) => board.filter((p) => p.pos === pos).slice(0, n)
  // ⚠️ EVERY starting slot, KICKER AND DEFENCE INCLUDED. Leaving those two open left the panel full
  // of "fills your open K starter" — need-fillers, not bench — and a depth target is silent there
  // by design, so the test failed for the wrong reason. Its non-vacuity clause is what said so.
  const mine = [
    ...bestAt("QB", 1),
    ...bestAt("RB", 3),
    ...bestAt("WR", 2),
    ...bestAt("TE", 1),
    ...bestAt("K", 1),
    ...bestAt("DST", 1),
  ]
  const picks = mine.map((p) => ({ id: p.id, slot: 1 }))

  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", leagues: "none" })
  // ⚠️ The component defaults to `half_ppr` and size 12 with slot 1; the storage key is built from
  // exactly those, and the mock serves the same board for every config.
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key as string, value as string),
    [
      "nfl-draft-2026-half_ppr-12-slot1",
      JSON.stringify({ configName: "half_ppr", size: 12, mySlot: 1, picks }),
    ],
  )
  await page.goto("/fantasy/draft")

  await page.getByLabel("TE depth target").fill("4")
  await page.getByLabel("TE depth target").blur()
  await page.getByRole("button", { name: "Start draft" }).click()
  await expect(page.locator("table tbody tr").first()).toBeVisible()

  // ⭐ NON-VACUITY FIRST: the seeded state must actually be the bench phase, or "no sentence
  // appeared" would mean "the fixture never asked the question" rather than "the control is dead".
  const reasons = page.locator("div.truncate.text-xs")
  await expect(reasons.first()).toBeVisible()
  const texts = await reasons.allTextContents()
  expect(
    texts.some((t) => t.includes("Bench depth")),
    `the seeded roster is not in the depth phase, so this test cannot see a depth target: ${texts}`,
  ).toBe(true)

  expect(
    texts.some((t) => t.includes("You asked for 4 TEs")),
    "no recommendation explained itself with the user's TE depth target, so the control is " +
      `invisible to the person who set it: ${texts}`,
  ).toBe(true)

  expectNoPageErrors(errors)
})

test("the depth-target grid never widens the page on a phone", async ({ page }) => {
  // ⚠️ NF-C2.1: a CSS grid track's automatic minimum is its MIN-CONTENT width, so a new grid is the
  // classic way to give a page a horizontal scrollbar. Asserted on computed layout at a real phone
  // viewport, not by grepping for `min-w-0`.
  await page.setViewportSize({ width: 390, height: 844 })
  const errors = await openSetup(page, "/fantasy/draft")
  await expect(page.getByLabel("DST depth target")).toBeVisible()

  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(
    scrollWidth,
    `the setup screen scrolls sideways with the depth-target grid: scrollWidth ${scrollWidth} vs ` +
      `viewport ${clientWidth}. The grid ITEMS need min-w-0.`,
  ).toBeLessThanOrEqual(clientWidth + 1)

  expectNoPageErrors(errors)
})
