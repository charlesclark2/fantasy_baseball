import { expect, test, type Page } from "@playwright/test"
import {
  E2E_ESPN_PASTE_REFUSED,
  E2E_ESPN_READ_URL,
  ESPN_REAL_PASTES,
  FIXTURES,
  collectPageErrors,
  espnPasteText,
  mockApi,
  type ApiMock,
  type EspnPaste,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.64b — LEAGUE IMPORT, PATH 1 OF 2: the ESPN PASTE.
 *
 * ══ WHY THIS PATH, AND WHY THE PAYLOADS ARE THE STORY ═════════════════════════════════════════
 *
 * ESPN is the biggest platform by some distance (~48% of leagues) and it is the one import path a
 * user has to WORK for — copy a link, open it signed in, select all, paste back. Until now nothing
 * drove it: E9.64 recorded it as a declared limitation because "a hand-authored settings blob would
 * encode our assumption about the very payload shape under test". That was the right call and it is
 * no longer necessary — the repo already holds THREE verbatim `?view=mSettings` captures from real
 * private leagues, committed for the Python adapter suite, and this spec pastes those exact bytes.
 *
 * ⭐⭐ THE DEFECT THIS FILE IS WRITTEN FROM IS NF-C0e, AND IT IS THE REASON FOR ≥2 PAYLOADS.
 * `espn.py` mapped ESPN's yardage stat ids onto `pass_yd` / `rush_yd` / `rec_yd` — SLEEPER's keys,
 * one character off the canonical `pass_yds` — so EVERY ESPN league scored ZERO for passing, rushing
 * and receiving yardage from the day import shipped. Nothing errored: an unrecognised key passes
 * through verbatim and reports CAPTURED, which is a legitimate verdict for a rule we genuinely do
 * not project. It survived 56 tests over one live-verified league, and was found only when a second
 * real account was tried. So:
 *
 *   · every settings assertion below runs TWICE, against two DIFFERENT leagues on DIFFERENT
 *     accounts (12-team full-PPR and 10-team half-PPR), and reads each payload's OWN values;
 *   · the coverage assertion is scoped to the APPLIED card by test id, because under the outage the
 *     very same key still rendered — in the CAPTURED card, under "saved with your league, but NOT
 *     applied". A page-wide text scan cannot tell those apart, and would have passed throughout.
 *
 * ⚠️ Import is a WRITE path, so the real gate is the server. Nothing here proves authorization; the
 * hard red line (a paste carrying credential material is refused, and never logged) is asserted
 * against the real adapter in `test_nf_c0_platform_import.py`. What this file proves is the half no
 * Python assertion can reach: that a real user pasting real bytes ends up looking at their own
 * league, correctly described.
 */

const REVIEW = /Review what we read/

/** Sign in, mock, and get to the ESPN panel with a link built. Returns the harness record so a spec
 *  can assert on what actually left the browser. */
async function openEspnPanel(page: Page): Promise<{ errors: string[]; mock: ApiMock }> {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: [] })
  // `leagues: "none"` — a fresh free account, so the G100-C1 quota never enters the picture. The
  // quota boundary is `free-league.spec.ts`'s subject and is deliberately not re-tested here.
  const mock = await mockApi(page, { entitlement: "free", leagues: "none" })
  await page.goto("/fantasy/import")

  // ⚠️ Anchored regex, not `exact`. A platform card's accessible name is its label PLUS its help
  // paragraph ("ESPN You make the request in your own browser and paste the response back."), so an
  // exact match on the label alone finds nothing.
  await page.getByRole("button", { name: /^ESPN/ }).click()
  await page.getByPlaceholder("Paste your ESPN league ID").fill("998005")
  await page.getByRole("button", { name: /Get my link/ }).click()
  await expect(
    page.getByRole("link", { name: /Open my league settings/ }),
    "asking for the link produced no link to open",
  ).toBeVisible()
  return { errors, mock }
}

/**
 * Paste a real ESPN response and read the league.
 *
 * ⚠️ NOT `fill()`. A real drafted response is ~200 KB, and Playwright's `fill` on a value that size
 * against a React-controlled `<textarea>` exceeded a 60 s timeout — measured, on the two specs that
 * use the drafted capture. Setting the value through the NATIVE setter and dispatching one `input`
 * event is both fast and a closer model of the interaction under test: a clipboard paste IS a single
 * input event, whereas `fill` is a whole typing protocol. The event is what React's `onChange`
 * listens to, so the component sees exactly what a real paste gives it.
 */
async function pasteAndRead(page: Page, paste: EspnPaste) {
  const box = page.getByPlaceholder(/Paste the text here/)
  await expect(box).toBeVisible()
  await box.evaluate((el, text) => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value",
    )!.set!
    setter.call(el, text)
    el.dispatchEvent(new Event("input", { bubbles: true }))
  }, espnPasteText(paste))
  await page.getByRole("button", { name: /Read my league/ }).click()
}

test.describe("the ESPN paste flow, driven end to end", () => {
  test("the link the user opens is the SERVER's, not one the page assembled", async ({ page }) => {
    // ⭐ `POST /espn/read-url` exists so the server owns this string — it format-checks the league id
    // and builds ESPN's path. A component that constructed the URL locally would render something
    // entirely plausible, would keep working here forever, and would break silently the day ESPN's
    // path changed. This is the E9.58 shape (an OAuth host that was internally consistent everywhere
    // and simply did not exist), which is why it is asserted rather than assumed.
    const { errors } = await openEspnPanel(page)

    const link = page.getByRole("link", { name: /Open my league settings/ })
    await expect(link).toHaveAttribute("href", E2E_ESPN_READ_URL)
    // It must open away from the app: the user has to be signed in to ESPN in their OWN browser for
    // the response to contain their league at all.
    await expect(link).toHaveAttribute("target", "_blank")

    expectNoPageErrors(errors)
  })

  // ⭐ THE SAME ASSERTIONS, TWICE, ON TWO INDEPENDENTLY-SOURCED REAL LEAGUES. See the header.
  for (const [label, paste] of [
    ["a 12-team full-PPR league", ESPN_REAL_PASTES.pprTwelve],
    ["a 10-team half-PPR league", ESPN_REAL_PASTES.halfTen],
  ] as const) {
    test(`${label} is read back correctly from its own real payload`, async ({ page }) => {
      const { errors } = await openEspnPanel(page)
      await pasteAndRead(page, paste)

      await expect(
        page.getByRole("heading", { name: REVIEW }),
        "pasting a real ESPN settings response never reached the review screen",
      ).toBeVisible()

      // Everything below is read from the payload the harness served, never hardcoded — the point is
      // that the screen echoes the SERVER's reading of the league, which is the only thing the user
      // can check it against.
      const preview = previewFor(paste)
      const review = page.locator("section").filter({ hasText: REVIEW }).first()

      await expect(review).toContainText(`${preview.config.n_teams}-team`)
      await expect(review).toContainText(preview.config.ppr.replace(/_/g, " "))

      // ⭐⭐ THE PLATFORM'S OWN NAME. This screen used to name the platform with a TWO-WAY test on a
      // THREE-WAY field (`platform === "yahoo" ? "Yahoo" : "Sleeper"`), so every ESPN import — the
      // paste flow, on the largest platform — read back "Sleeper" on the one screen whose entire job
      // is to let the user check what we understood. Both branches are strings, so `tsc` was happy,
      // and no assertion had ever opened this screen on a non-Sleeper preview.
      await expect(review, "the review screen does not name ESPN as the platform").toContainText("ESPN")
      await expect(
        review,
        "the review screen calls this ESPN league a Sleeper league",
      ).not.toContainText("Sleeper")

      // The starting lineup, which is what makes "12-team full PPR" concrete. A roster shape read
      // wrongly is the difference between a useful board and a wrong one.
      for (const slot of preview.config.roster.filter((s: any) => !s.bench)) {
        await expect(
          review.getByText(`${slot.count}× ${slot.name}`),
          `the ${slot.name} slot was not read back on the review screen`,
        ).toBeVisible()
      }

      await expectNoNaN(page)
      expectNoPageErrors(errors)
    })

    test(`${label}'s scoring is APPLIED, not silently captured (NF-C0e)`, async ({ page }) => {
      // ⭐⭐ THE ASSERTION THIS FILE EXISTS FOR — the rendered form of the outage. Under NF-C0e these
      // three terms existed, carried the right weights, and appeared on this very screen; they were
      // simply in the CAPTURED column, which reads "Saved with your league, but NOT applied — we do
      // not project this stat." A user reading that would conclude we cannot project passing yards.
      const { errors } = await openEspnPanel(page)
      await pasteAndRead(page, paste)
      await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

      const applied = page.getByTestId("coverage-applied")
      const captured = page.getByTestId("coverage-captured")
      await expect(applied, "the coverage panel never rendered an applied column").toBeVisible()

      for (const key of ["pass_yds", "rush_yds", "rec_yds", "rec"]) {
        await expect(
          applied.getByText(key, { exact: true }),
          `${key} is not reported as APPLIED — this is the NF-C0e signature: an ESPN league scoring ` +
            "zero yardage behind a panel that says so",
        ).toBeVisible()
        await expect(
          captured.getByText(key, { exact: true }),
          `${key} is reported as CAPTURED, i.e. stored and scored as nothing`,
        ).toHaveCount(0)
      }

      expectNoPageErrors(errors)
    })
  }

  test("⭐ the two payloads disagree, and the screen follows the payload rather than a default", async ({
    page,
  }) => {
    // The discriminating half of "≥2 real payloads". Asserting each league renders its own numbers
    // is necessary but not sufficient — a screen that hardcoded 12-team full-PPR would pass the
    // first case above. This one reads BOTH in the same browser and requires them to differ.
    const { errors } = await openEspnPanel(page)

    await pasteAndRead(page, ESPN_REAL_PASTES.pprTwelve)
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()
    const first = await page.locator("section").filter({ hasText: REVIEW }).first().innerText()

    await pasteAndRead(page, ESPN_REAL_PASTES.halfTen)
    // Wait for the value the SECOND payload alone produces before scanning: a snapshot taken while
    // the first is still on screen is the whole-page-text trap this suite's README documents.
    await expect(page.getByText("10-team", { exact: false })).toBeVisible()
    const second = await page.locator("section").filter({ hasText: REVIEW }).first().innerText()

    expect(
      first,
      "both ESPN leagues rendered identically — the screen is not reading the payload",
    ).not.toEqual(second)
    expect(first).toContain("12-team")
    expect(second).toContain("10-team")

    expectNoPageErrors(errors)
  })

  test("a league we read CLEANLY shows no 'could not read' box", async ({ page }) => {
    // ⭐ THE NEGATIVE HALF OF THE DISCLOSURE CONTRACT, and it needs its own payload to be reachable
    // at all. `import-warnings-suppressed` proves a warning IS shown; nothing proved the header is
    // absent when there is nothing to report — and a component that rendered it unconditionally
    // would pass that test while telling most users we failed to read their league. The 10-team
    // capture is the one real payload that parses with zero warnings.
    const { errors } = await openEspnPanel(page)
    await pasteAndRead(page, ESPN_REAL_PASTES.halfTen)
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

    await expect(
      page.getByText(/What we could not read exactly/),
      "a league that parsed with no warnings still shows the 'we could not read this' header",
    ).toHaveCount(0)
    // And the settings really are there, so this is not passing on an unrendered screen.
    await expect(page.getByTestId("coverage-applied")).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("a rule we could not represent is shown verbatim, and its ESPN number is made readable", async ({
    page,
  }) => {
    const { errors } = await openEspnPanel(page)
    await pasteAndRead(page, ESPN_REAL_PASTES.pprTwelve)
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

    const preview = previewFor(ESPN_REAL_PASTES.pprTwelve)
    expect(preview.warnings.length, "this payload no longer warns; the case is unreachable").toBeGreaterThan(0)

    await expect(page.getByText(/What we could not read exactly/)).toBeVisible()
    for (const warning of preview.warnings) {
      await expect(
        page.getByText(warning, { exact: false }),
        "the server said it could not represent a rule and the review screen did not pass it on",
      ).toBeVisible()
    }

    // ⭐ ESPN NUMBERS ITS SCORING RULES, so a captured term is `15` or `129@dst` unless the server
    // sends a label. A row rendering the bare number is technically honest and completely useless —
    // the user cannot tell which of their settings we dropped, which defeats the point of the
    // disclosure. The label is server-supplied and additive, so this also pins that the client
    // actually reads `unmapped_labels` rather than falling through to the raw key.
    const [key, label] = Object.entries(preview.unmapped_labels ?? {})[0] as [string, string]
    expect(key, "no labelled captured key in this payload").toBeTruthy()
    await expect(
      // `.first()` because ESPN legitimately reuses ONE label across several rule ids — this league
      // scores 15 and 16 as separate "Long passing touchdown bonus" rules at different thresholds.
      // That is a property of the payload, not an ambiguity to resolve: what is under test is that
      // the LABEL reaches the row at all.
      page.getByTestId("coverage-captured").getByText(label, { exact: false }).first(),
      `the captured rule ${key} renders as its ESPN number instead of "${label}"`,
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("a drafted league brings its teams and rosters, and claims no live refresh", async ({
    page,
  }) => {
    const { errors } = await openEspnPanel(page)
    await pasteAndRead(page, ESPN_REAL_PASTES.draftedTen)
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

    const preview = previewFor(ESPN_REAL_PASTES.draftedTen)
    expect(preview.teams.length).toBeGreaterThan(1)
    await expect(page.getByText(`Teams · ${preview.teams.length}`)).toBeVisible()

    // ⭐ ESPN's response does not say which team is the caller's, so the screen must ASK rather than
    // guess — that choice is what lets My Teams score a roster at all (NF-C6). A platform that
    // silently picked one would link the wrong roster and look exactly like a working import.
    await expect(page.getByText(/This platform does not tell us which team is yours/)).toBeVisible()
    const mine = page.getByRole("button", { name: "Mine?" })
    await expect(mine.first()).toBeVisible()
    await mine.first().click()
    await expect(
      page.getByRole("button", { name: "✓ Mine" }),
      "picking a team did not mark it as the user's own",
    ).toBeVisible()

    // Open a roster and require it to hold real players.
    // ⚠️ Anchored and word-bounded: this league's teams are "Team 1" … "Team 13", so an unanchored
    // `Team 1` matches five of them. A `.first()` here would silently pick whichever row Playwright
    // saw first and then assert a correct-looking roster about a different team.
    const teamName = preview.teams[0].name
    await page
      .getByRole("button", { name: new RegExp(`^${teamName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s`) })
      .click()
    await expect(
      page.getByText(preview.teams[0].players[0].name, { exact: false }).first(),
      "a drafted roster expanded to no players",
    ).toBeVisible()

    // ⚠️⚠️ THE DRAFT PANEL IS NOT ASSERTED HERE, AND THE REASON IS A FINDING RATHER THAN AN
    // OMISSION. `espn.py` never constructs a `DraftState` at all — ESPN's import carries ROSTERS
    // (off `teams`), never picks — so `preview.draft` is `null` on all three real captures and the
    // whole panel is unreachable for this platform by construction. A first cut of this test
    // guarded the assertion behind `if (preview.draft?.pick_count > 0)`, which made it silently
    // skip: a guard that cannot fail, in the file whose subject is guards that cannot fail. The red
    // proof caught it (`espn-claims-a-live-draft-refresh` came back MISMATCH), which is the
    // clearest argument for the harness in this whole story. See `e2e/README.md`'s declared
    // limitations. ⛔ Do not restore an `if`-wrapped assertion here; if ESPN ever gains draft
    // parsing, assert it unconditionally.
    expect(
      preview.draft,
      "an ESPN preview now carries a draft — the panel is reachable, so assert it unconditionally " +
        "and add back a red-proof case for the live-refresh copy",
    ).toBeNull()

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the client's rewrite of the paste does not corrupt it", async ({ page }) => {
    // ⭐ THE CLIENT MUTATES THE USER'S DATA ON THE WAY OUT, and it has to. `pruneEspnPayload` drops
    // per-player blocks the import never reads; without it a real drafted response is ~3.3 MB, a
    // 12-team league lands at ~99% of the server's 4 MB cap, and a 14-team league is REFUSED
    // outright — i.e. the most common league sizes could not import at all. But it JSON round-trips
    // the user's entire payload and RETURNS THE ORIGINAL on anything unexpected, so a bug in it
    // degrades silently: from the DOM a corrupted paste looks exactly like a working one, right up
    // until the server cannot parse it.
    //
    // ⚠️⚠️ WHAT THIS DOES **NOT** PROVE, SAID PLAINLY: the DENYLIST is not exercised. None of the
    // three committed captures contains `stats` / `draftRanksByRankType` / `ownership` / `outlooks`
    // / `ratings` / `notificationSettings` — measured, zero occurrences in all three — because they
    // were already stripped before being committed. So on this fixture the pruner has nothing to
    // remove, and the ~37% it does shrink the payload by is WHITESPACE. Asserting a size ratio here
    // would be a guard that cannot fail for the reason it names. `pruneEspnPayload` has no other
    // coverage anywhere in the repo (there is no TS unit runner), which is recorded in
    // `e2e/README.md` as an open gap rather than dressed up as coverage here.
    //
    // What IS asserted is the pruner's CONTRACT, spelled out independently of its source: the posted
    // payload equals the pasted one minus exactly the unread fields. That is true whether or not a
    // capture carries them, and it goes red the day the round trip starts losing something.
    const { mock, errors } = await openEspnPanel(page)
    const pasted = JSON.parse(espnPasteText(ESPN_REAL_PASTES.draftedTen))
    await pasteAndRead(page, ESPN_REAL_PASTES.draftedTen)
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

    expect(mock.espnPastes, "no ESPN paste reached the API").toHaveLength(1)
    const [sent] = mock.espnPastes
    expect(JSON.parse(sent.posted)).toEqual(withoutUnreadFields(pasted))
    // And the rewrite did not lose the league's identity: the server resolved THIS league.
    expect(sent.leagueId).toBe(ESPN_REAL_PASTES.draftedTen.leagueId)

    expectNoPageErrors(errors)
  })

  test("a paste the server refuses says WHY, at the control, and leaves the flow usable", async ({
    page,
  }) => {
    // ⭐ E8.6's lesson on the other create path: a refused action that reports nothing is
    // indistinguishable from one that silently did not happen. `errorText`'s contract is that the
    // SERVER's own message wins — substituting a generic string keyed off the status code would
    // throw away the only sentence that says what to DO — so the detail is asserted verbatim.
    const { errors } = await openEspnPanel(page)

    await page.getByPlaceholder(/Paste the text here/).fill('{"not":"an espn league"}')
    await page.getByRole("button", { name: /Read my league/ }).click()

    await expect(
      page.getByText(E2E_ESPN_PASTE_REFUSED, { exact: false }),
      "a refused paste produced no visible reason — the button reads as dead",
    ).toBeVisible()
    // It must not have pretended to succeed.
    await expect(page.getByRole("heading", { name: REVIEW })).toHaveCount(0)

    // ⭐ AND THE FLOW MUST STILL WORK AFTERWARDS. A one-shot error state that wedges the panel turns
    // a typo into a dead end, which on this surface means a user who mis-copied once can never
    // import at all.
    await pasteAndRead(page, ESPN_REAL_PASTES.halfTen)
    await expect(
      page.getByRole("heading", { name: REVIEW }),
      "the paste box never recovered from a refused paste",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("saving an ESPN import reports what it did", async ({ page }) => {
    const { errors } = await openEspnPanel(page)
    await pasteAndRead(page, ESPN_REAL_PASTES.halfTen)
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

    await page.getByRole("button", { name: /Save this league/ }).click()

    await expect(
      page.getByText(/League saved/),
      "the save produced no confirmation — the user cannot tell it happened",
    ).toBeVisible()
    await expect(
      page.getByText(/No team linked yet/),
      "a league saved without a team claimed the roster was linked",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })
})

/** The exact preview the harness served for this paste, read Node-side.
 *
 *  ⚠️ Every assertion above reads its expected values from HERE rather than from a literal. These
 *  fixtures are regenerated from the shipping adapters (`build-import-previews.py`, pinned by
 *  `test_e9_64b_import_e2e_fixtures.py`), so a hardcoded "12-team" or a hardcoded warning string
 *  would be a second, driftable spelling of a real league — and would start describing the wrong
 *  one the moment a capture was refreshed. Same discipline as `home-positioning.spec.ts`. */
function previewFor(paste: EspnPaste): any {
  return FIXTURES.importEspnPreview(paste.leagueId, paste.seasonId)
}

/**
 * The pruner's CONTRACT, stated here rather than imported.
 *
 * ⛔ DELIBERATELY A SECOND SPELLING of `ESPN_UNREAD_PLAYER_FIELDS`. Importing the constant the code
 * prunes with would make this a restatement of the implementation — the exact shape NF-C0e shipped
 * (a test that read a value back under the key the code wrote can never catch a wrong key). If the
 * two lists ever disagree, that disagreement IS the finding.
 */
function withoutUnreadFields(doc: any): any {
  const copy = JSON.parse(JSON.stringify(doc))
  for (const m of copy.members ?? []) delete m?.notificationSettings
  for (const t of copy.teams ?? []) {
    for (const e of t?.roster?.entries ?? []) {
      const pool = e?.playerPoolEntry
      if (!pool) continue
      delete pool.ratings
      for (const f of ["stats", "draftRanksByRankType", "ownership", "outlooks"]) {
        delete pool.player?.[f]
      }
    }
  }
  return copy
}
