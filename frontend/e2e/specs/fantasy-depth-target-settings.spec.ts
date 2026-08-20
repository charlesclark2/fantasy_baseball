// NF-C7b — depth targets are a SAVED setting with two homes, asserted on RENDERED output.
//
// ⭐ WHY RENDERED, NOT SOURCE (NF-C4). A frontend guard that greps source tests that somebody TYPED
// something. Every clause here reads the DOM.
//
// ⭐ WHAT THIS DEFENDS. NF-C7 kept a depth target in `localStorage` keyed by season + scoring-format
// name, so two different leagues on one format shared a setting, nothing synced, and the Chrome
// extension could not read it at all. The setting now lives on the league record (per league) and on
// the account (a default for every league without one). The precedence between them is stated ONCE
// in `betting_ml/tests/fixtures/nf_c7b_depth_target_precedence.json` and pinned on both sides; what
// THIS file defends is the half a fixture cannot see — that the user can TELL which one is in force
// and can get back to inheriting.
import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectNoPageErrors } from "../support/assertions"
import { signIn } from "../support/session"

const SURFACES = [
  { name: "the live draft optimizer", path: "/fantasy/draft" },
  { name: "the mock draft", path: "/fantasy/mock-draft" },
] as const

async function open(page: Page, path: string, opts: Parameters<typeof mockApi>[1]) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, opts)
  await page.goto(path)
  return errors
}

for (const surface of SURFACES) {
  test(`an account default is APPLIED and NAMED, not silently in force — ${surface.name}`, async ({
    page,
  }) => {
    const errors = await open(page, surface.path, {
      entitlement: "entitled",
      leagues: "none",
      fantasyPrefs: "accountTargets",
    })

    // ⭐ THE POINT OF THE CLAUSE. An account default of {QB: 2} and a league value of {QB: 2} rank
    // identically, so a user who wants to change it cannot tell which screen to open. The applied
    // values AND their origin are rendered.
    await expect(page.getByText(/from your account default/i)).toBeVisible()
    await expect(page.getByText(/2 QB/)).toBeVisible()
    await expect(page.getByText(/3 TE/)).toBeVisible()

    // ...and the ad-hoc boxes are NOT offered, because editing them here would write a local value
    // that the account default outranks — a control that silently does nothing.
    await expect(page.getByLabel("QB depth target")).toHaveCount(0)

    expectNoPageErrors(errors)
  })

  test(`with no account default the ad-hoc control is offered — ${surface.name}`, async ({ page }) => {
    // ⚠️ THE TWO-SIDED HALF. Without this, the clause above passes on a screen that NEVER renders
    // the boxes — "the control is hidden" and "the control does not exist" would be identical.
    const errors = await open(page, surface.path, {
      entitlement: "entitled",
      leagues: "none",
      fantasyPrefs: "none",
    })
    await expect(page.getByLabel("QB depth target")).toBeVisible()
    await expect(page.getByText(/from your account default/i)).toHaveCount(0)
    expectNoPageErrors(errors)
  })
}

test("the account default is editable on /settings and reports what the server stored", async ({
  page,
}) => {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", fantasyPrefs: "none" })
  await page.goto("/settings")

  const rb = page.getByLabel("RB depth target")
  await expect(rb).toBeVisible()
  await expect(rb).toHaveValue("0") // ⭐ the default is OFF, asserted on the rendered value

  await rb.fill("6")
  await rb.blur()
  const save = page.getByRole("button", { name: /save defaults/i })
  await expect(save).toBeEnabled()
  await save.click()

  // ⭐ "✓ Saved" is rendered only after the response is compared against what was SENT. A backend
  // that predates this field accepts the request, ignores the key and returns 200 — the user sees a
  // save and watches it vanish on reload (E8.6). The comparison is what makes that visible.
  await expect(page.getByText("✓ Saved")).toBeVisible()

  // ⚠️ NO `expectNoPageErrors` HERE, AND THE REASON IS RECORDED RATHER THAN THE ASSERTION QUIETLY
  // DROPPED. `/settings` throws React #418 (a hydration text mismatch) on load, and it does so
  // WITHOUT this section — measured by removing `<FantasyDefaultsSettings />` and re-running: the
  // error is identical. It is a real pre-existing defect on that page, not this story's, and
  // fixing it means auditing every auth-dependent branch on a 1000-line page. Asserting here would
  // make an unrelated page's bug fail this feature's guard; deleting the clause without saying so
  // would hide a defect somebody found. It is written up in the PR instead.
  //
  // The two draft surfaces DO assert `expectNoPageErrors`, so this story's own components are still
  // covered — /settings is the only surface exempted, and only for a cause proven to predate it.
  void errors
})

test("a league can be given its own targets and put back to inheriting", async ({ page }) => {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", leagues: "one", fantasyPrefs: "accountTargets" })
  await page.goto("/fantasy/league-settings")

  // Inheriting is the starting state for a league saved before this field existed, and it NAMES the
  // value it is inheriting — an unnamed "using your default" is an invisible setting.
  await expect(page.getByText(/using your account default/i)).toBeVisible()
  await expect(page.getByText(/2 QB, 3 TE/)).toBeVisible()
  await expect(page.getByLabel("QB depth target")).toHaveCount(0)

  await page.getByRole("button", { name: /set for this league/i }).click()
  await expect(page.getByLabel("QB depth target")).toBeVisible()

  // ⭐ THE ONE-WAY-DOOR GUARD. Once the control is touched the league is explicit and stops
  // inheriting; clearing every box then reads as "off", not "inherit". Without a way back a user who
  // tried the control once could never return to their default — so the way back is asserted, not
  // assumed.
  await page.getByRole("button", { name: /use my account default instead/i }).click()
  await expect(page.getByText(/using your account default/i)).toBeVisible()
  await expect(page.getByLabel("QB depth target")).toHaveCount(0)

  expectNoPageErrors(errors)
})

test("the depth-target grid never widens the page on a phone", async ({ page }) => {
  // NF-C2.1 — a grid track's automatic minimum is its min-content width, so a long label can widen
  // the track and give the whole page a horizontal scrollbar. Asserted as a COMPUTED value.
  await page.setViewportSize({ width: 390, height: 844 })
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", fantasyPrefs: "none" })
  await page.goto("/settings")
  await expect(page.getByLabel("RB depth target")).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow, "the settings page scrolls sideways at 390px").toBeLessThanOrEqual(1)
})
