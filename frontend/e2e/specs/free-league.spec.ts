import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, captureAnalytics, collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * G100-C1 — ONE FREE PERSONALIZED LEAGUE, and the activation screen it exists for.
 *
 * ══ WHAT THIS FILE IS FOR ══════════════════════════════════════════════════════════════════════
 *
 * The free tier's payoff is a screen: a board re-scored for the caller's own league, led by what
 * CHANGED versus the free one. Three things about that are only observable in a browser, and each
 * has been a real defect class in this repo:
 *
 *   1. The delta RENDERS, with a sign that means what the column says. A rank scale is inverted
 *      (smaller is better), so `league − generic` is the intuitive spelling and the wrong one —
 *      and a sign error produces a page that looks completely normal.
 *   2. The activation event actually LEAVES THE PAGE, under the name G100-D0's dashboard reads.
 *      Asserting that `posthog.capture` was called proves nothing if PostHog was never armed, which
 *      is the state this suite was in until G100-C1 set a token in `e2e.env`.
 *   3. The empty and over-quota states are STATED, not blank. "You have no league yet" and "we are
 *      only personalizing one of your three" are different facts, and a page that renders nothing
 *      for either is the silent-empty class (E9.56b) on the surface the funnel converts on.
 *
 * ⛔ WHAT IT DOES NOT PROVE. Entitlement. The API is mocked here, and `signIn` seeds a session into
 * localStorage without any server involvement — deliberately, because a browser test that appeared
 * to check authorization would be the most convincing vacuous guard in the repo. Who may read and
 * write what is asserted against the real ASGI app in
 * `betting_ml/tests/test_g100_c1_free_league.py`, including the server-enforced cap of one.
 */

const SIGNED_IN_FREE = { groups: [] as string[] }

/**
 * The three `freeSignedIn` nav items (`lib/nav-model.ts`) — offered to a signed-in free account,
 * withheld from a logged-out visitor.
 *
 * ONE list, read by both halves of that contract, because they are two statements about the same
 * membership: an item added to the menu but not to the negative test would be asserted reachable
 * and never asserted withheld. Same reason the app keeps one ordering function rather than two.
 */
const LEAGUE_NAV_HREFS = ["/fantasy/my-league", "/fantasy/import", "/fantasy/league-settings"] as const

/** Every spec here needs the same three things: a session, the API, and no third-party traffic. */
async function openMyLeague(
  page: Page,
  options: {
    leagues?: "none" | "one" | "overQuota"
    groups?: string[]
    /** Rewrite a payload before it is served — how the pool tests below change the league's ROSTER
     *  without a second fixture, so the arithmetic is exercised on more than one shape. */
    transform?: (pathname: string, body: any) => any
  } = {},
) {
  await signIn(page, { groups: options.groups ?? SIGNED_IN_FREE.groups })
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, {
    entitlement: "free",
    leagues: options.leagues ?? "one",
    transform: options.transform,
  })
  const events = await captureAnalytics(page)
  await page.goto("/fantasy/my-league")
  return { errors, mock, events }
}

/** Replace the saved league's roster/size — the two inputs to the draft pool. */
function withLeague(patch: Record<string, unknown>) {
  return (pathname: string, body: any) => {
    if (pathname === "/fantasy/nfl/my-teams" && body?.leagues?.[0]) {
      body.leagues[0] = { ...body.leagues[0], ...patch }
    }
    return body
  }
}

test.describe("the free personalized league", () => {
  test("a signed-in free account sees its own board and the delta that explains it", async ({
    page,
  }) => {
    const { errors, mock } = await openMyLeague(page)

    // The board renders — i.e. the free tier's personalization actually reached the page. This is
    // the assertion that would have failed had `useSavedLeagues`/`useMyTeams` kept their
    // entitlement gates, which is exactly how a free user's own league would have gone invisible.
    await expect(page.getByTestId("my-league-board")).toBeVisible()
    await expect(page.locator('[data-testid="my-league-board"] tbody tr').first()).toBeVisible()

    // The AHA block, with its honest definition beside it.
    const delta = page.getByTestId("league-delta")
    await expect(delta).toBeVisible()
    await expect(delta).toContainText("What changed because it's your league")
    // ⭐ The load-bearing sentence. Without it a movement column reads as a claim about the MARKET,
    // which is what every other fantasy product means by one — and would be an `best_alpha = 0`
    // violation on the highest-traffic conversion surface we have.
    await expect(delta).toContainText("two of our own boards")

    // The mechanism, not just the assertion — this is what makes the screen explanatory.
    await expect(page.getByTestId("replacement-shift")).toBeVisible()

    await expectApiFullyMocked(mock)
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the movement is real, and its sign points the way the column says", async ({ page }) => {
    await openMyLeague(page)
    await expect(page.getByTestId("league-delta")).toBeVisible()

    const risers = page.locator('[data-testid="risers"] [data-testid="mover-card"]')
    const fallers = page.locator('[data-testid="fallers"] [data-testid="mover-card"]')
    expect(await risers.count(), "no risers — the delta computed nothing").toBeGreaterThan(0)
    expect(await fallers.count(), "no fallers — the delta computed nothing").toBeGreaterThan(0)

    // ⭐⭐ THE ANCHOR MUST BE A QUANTITY THE DELTA'S SIGN DOES NOT PRODUCE.
    //
    // The first cut asserted that every card in `risers` carried a "▲", and the red-proof harness
    // caught it as a TAUTOLOGY: the list MEMBERSHIP and the arrow both derive from the same delta,
    // so inverting the subtraction moves each player into the other list AND flips their chip —
    // perfectly self-consistent, and the assertion passes on the exact defect it was written for.
    // (The NF-C0e "reading a value back under the key the code wrote" shape.)
    //
    // ⚠️ E9.61 RETIRED THE PREVIOUS ANCHOR, and the reason is worth keeping. It asserted that every
    // riser's OVERALL RANK improved, which was exact while the list was SELECTED on rank movement
    // (`ovrDelta > 0` means precisely `genericOvrRank > leagueOvrRank`). The highlights now rank on
    // VOR DELTA, and value and board position can legitimately disagree — a player can be worth
    // more above replacement in this league and still sit lower overall, because the players around
    // him gained more. Keeping that assertion would have failed on correct behaviour, which is the
    // worse half of a stale test: it does not merely stop catching the bug, it argues against the
    // fix. (Measured on this fixture: all five top risers slip in overall rank.)
    //
    // THE REPLACEMENT RE-DERIVES THE CHIP FROM THE SERVED PAYLOADS. The generic side is read out of
    // the board FIXTURE and the league side off the rendered board table — neither passes through
    // `computeLeagueDelta`, so inverting its subtraction flips the chip's sign while both inputs
    // stay put, and the comparison goes red. That is the property the old rank anchor had and a
    // "risers all show positive" check does not.
    const genericVor = new Map(
      (FIXTURES.boardFree() as { name: string; vor: number | null }[]).map((p) => [p.name, p.vor]),
    )

    /** The chip on the first card of a block, with the player it belongs to. */
    const topCard = async (block: typeof risers) => {
      const card = block.first()
      const name = (await card.getByRole("link").first().innerText()).trim()
      const chip = await card.getByTestId("value-chip").innerText()
      return { name, value: Number(chip.replace(/[^0-9.+-]/g, "")) }
    }

    // Show every row so the mover's own board row is findable, then read HIS league VOR off it.
    // ⚠️ A Radix `Picker`, not a native <select> — `selectOption` silently does nothing here.
    await page.getByLabel("Rows per page").first().click()
    await page.getByRole("option", { name: "All", exact: true }).click()

    for (const [block, label, sign] of [
      [risers, "riser", 1],
      [fallers, "faller", -1],
    ] as const) {
      const { name, value } = await topCard(block)
      expect(Number.isFinite(value), `the top ${label} card rendered no value chip`).toBe(true)
      expect(Math.sign(value), `a ${label}'s value chip has the wrong sign`).toBe(sign)

      const generic = genericVor.get(name)
      expect(generic, `${name} is not on the generic board fixture — anchor missing`).not.toBe(
        undefined,
      )
      const row = page.locator('[data-testid="my-league-board"] tbody tr', { hasText: name }).first()
      await expect(row, `${name} has no row on his own league board`).toBeVisible()
      // columns: # | Player | Pos | Team | Bye | pts | VOR | vs generic
      const leagueVor = Number((await row.locator("td").nth(6).innerText()).replace(/,/g, ""))

      // ⚠️ TOLERANT ON MAGNITUDE, EXACT ON DIRECTION. Both figures are rendered to one decimal, so
      // the difference carries two roundings; the SIGN is what an inverted subtraction breaks, and
      // it is asserted without tolerance.
      const expected = leagueVor - (generic as number)
      expect(
        Math.sign(expected),
        `${name} is listed as a ${label} but his own board says the opposite: league VOR ` +
          `${leagueVor} vs generic ${generic}. The delta's subtraction is inverted.`,
      ).toBe(sign)
      expect(
        Math.abs(expected - value),
        `${name}'s chip (${value}) does not match his own boards (${expected})`,
      ).toBeLessThan(0.5)
    }

    // The summary counts something, and the count is bounded by what was compared — a delta that
    // silently compared nothing would render "0 of 0" and pass a mere "the block is visible" check.
    const summary = await page.getByTestId("delta-summary").textContent()
    const [moved, compared] = (summary ?? "").match(/\d+/g)?.map(Number) ?? []
    expect(compared, "nothing was compared against the free board").toBeGreaterThan(100)
    expect(moved, "no player moved in a superflex, half-PPR, TE-premium league").toBeGreaterThan(0)
    expect(moved).toBeLessThanOrEqual(compared)
  })

  test("the activation event reaches the wire, once, under the name the funnel reads", async ({
    page,
  }) => {
    const { events } = await openMyLeague(page)
    await expect(page.getByTestId("my-league-board")).toBeVisible()

    // posthog batches on a timer, so give the queue a beat to flush.
    await expect
      .poll(() => events.filter((e) => e.event === "custom_board_viewed").length, {
        message: "`custom_board_viewed` never reached the ingest endpoint",
        timeout: 10_000,
      })
      .toBeGreaterThan(0)

    const captured = events.filter((e) => e.event === "custom_board_viewed")
    // ⚠️ EXACTLY ONE. This component re-renders on every position-tab click and on each query
    // settling; a capture outside the once-per-mount ref would multiply a single activation by
    // however much the user browsed, inflating the DENOMINATOR paid conversion is measured against.
    // An inflated activation rate reads as a CONVERSION problem and sends the next story at the
    // wrong thing.
    expect(captured.length, "the activation event fired more than once for one view").toBe(1)

    // …and it stays one while the user BROWSES. A position-tab click re-renders the component,
    // which is the cheapest way to reproduce the "counted per render" defect. Today two layers
    // prevent it (the once-per-mount ref, and an effect dependency list that a tab click does not
    // disturb), so no single-line break can falsify this — see the `activation-fires-per-render`
    // case in `e2e/red-proof.mjs`, which is declared GREEN for exactly that reason. Exercising it
    // here is what catches a future edit that makes those dependencies unstable.
    await page.getByRole("button", { name: "RB", exact: true }).click()
    await page.waitForTimeout(2_000)
    expect(
      events.filter((e) => e.event === "custom_board_viewed").length,
      "browsing the board counted a second activation",
    ).toBe(1)

    // G100-D0's required dimensions, carried on the event the dashboard keys off.
    const props = captured[0].properties
    expect(props.league_platform).toBe("sleeper")
    expect(props.league_size).toBe(10)
    // The delta's size travels with it: "saw their board" and "saw their board CHANGE something"
    // are different funnel facts.
    expect(typeof props.players_moved).toBe("number")
  })

  test("no league yet: the screen says so and offers both ways in", async ({ page }) => {
    const { errors } = await openMyLeague(page, { leagues: "none" })

    const empty = page.getByTestId("my-league-empty")
    await expect(empty).toBeVisible()
    // BOTH routes. The manual editor is the GUARANTEE underneath the importer rather than a
    // fallback for when it fails, and a free user whose platform we cannot reach must not be left
    // looking at an import button that will never work for them.
    await expect(page.getByRole("link", { name: /import my league/i })).toBeVisible()
    await expect(page.getByRole("link", { name: /enter it by hand/i })).toBeVisible()

    // The delta block must be ABSENT rather than empty — there is nothing to compare yet, and a
    // headline reading "0 of 0 players move" would be a true sentence that reads as a broken page.
    await expect(page.getByTestId("league-delta")).toHaveCount(0)
    expectNoPageErrors(errors)
  })

  test("a configured league is never described as 'no league' when scoring fails", async ({
    page,
  }) => {
    // ⭐ THREE FACTS, NOT TWO. The page cannot show a scored board until the board read lands, so
    // "my league is here but unscored" is a state of its own. Keying the empty state on it would
    // tell someone who configured a league last week to go and set one up — every time the read is
    // slow, 404s before the first export, or fails. That is the silent-empty class (E9.56b) landing
    // on the one screen this whole story exists for.
    //
    // ⚠️ NF-EPIC 1 RE-ANCHORED WHICH READ IS FAILED, NOT WHAT THIS TEST ASSERTS. Scoring used to
    // happen in the browser off the PROJECTIONS blob, so failing that read was the deterministic
    // form of "the board cannot be built". Scoring moved to the server when the raw stat line
    // became paid, so the board now arrives from `/fantasy/nfl/league-board` and failing
    // projections no longer prevents it — the page would render fine and this spec would assert
    // against a state it can no longer produce. Failing the read the board ACTUALLY depends on
    // keeps the property intact; the property itself is unchanged.
    await signIn(page, SIGNED_IN_FREE)
    const errors = collectPageErrors(page)
    await mockApi(page, {
      entitlement: "free",
      leagues: "one",
      fail: ["/fantasy/nfl/league-board"],
    })
    await page.goto("/fantasy/my-league")

    // ⚠️ THE POSITIVE ASSERTION RUNS FIRST, AND THE ORDER IS LOAD-BEARING. `toHaveCount(0)` passes
    // the instant it is evaluated if the element has not rendered YET, so putting it first makes it
    // a race against the page settling rather than a statement about the settled page — it passed
    // against the deliberately-broken source until this was reordered (caught by the red proof).
    // Waiting for the error message is what proves the page has finished.
    await expect(page.getByText(/couldn't score your league/i)).toBeVisible()
    await expect(page.getByText(/your league settings are safe/i)).toBeVisible()
    // …and the "set up your league" prompt is NOT also on screen.
    await expect(page.getByTestId("my-league-empty")).toHaveCount(0)
    expectNoPageErrors(errors)
  })

  test("the activation event does NOT fire on an empty state", async ({ page }) => {
    // ⭐ THE OTHER HALF OF THE ACTIVATION CONTRACT, and the one an implementation naturally gets
    // wrong by firing on mount. A visitor who arrived, saw "set up your league" and left has not
    // activated; counting them inflates the funnel's denominator with its own drop-off.
    const { events } = await openMyLeague(page, { leagues: "none" })
    await expect(page.getByTestId("my-league-empty")).toBeVisible()
    // Give the batcher the same window the positive case gets, so this is a real absence rather
    // than a race that happens to read empty.
    await page.waitForTimeout(3_000)
    expect(
      events.filter((e) => e.event === "custom_board_viewed"),
      "activation was counted for a visitor who has no league",
    ).toHaveLength(0)
  })

  test("a lapsed subscriber is told nothing was deleted", async ({ page }) => {
    // Three saved, one personalized. The dangerous rendering is SILENCE: two of their leagues stop
    // appearing and the page offers no account of why, which reads as data loss on a surface the
    // user typed their own settings into.
    const { errors } = await openMyLeague(page, { leagues: "overQuota" })

    await expect(page.getByTestId("my-league-board")).toBeVisible()
    const note = page.getByTestId("quota-withheld-note")
    await expect(note).toBeVisible()
    await expect(note).toContainText("Nothing has been deleted")
    expectNoPageErrors(errors)
  })

  test("the board still renders when the manifest has not named a free board yet", async ({
    page,
  }) => {
    // ⚠️ THE DEPLOY-SKEW WINDOW (NF-C0). `frontend/` ships on merge and the API Lambda only on a
    // manual `deploy.sh`, so there is always an interval where the client is new and the manifest
    // has no `freeBoard` key. `freeSelection` returns null there — deliberately, rather than
    // guessing `full_ppr`/12 locally, which would state the paywall in two places and render a
    // confident comparison against a board we were not told is the free one.
    //
    // The page must degrade to "your board, no delta" rather than to a blank screen or a wrong
    // one. This is the assertion that a `?? "full_ppr"` shortcut would quietly break.
    await signIn(page, SIGNED_IN_FREE)
    const errors = collectPageErrors(page)
    await mockApi(page, {
      entitlement: "free",
      leagues: "one",
      transform: (path, body) => {
        if (path !== "/fantasy/nfl/manifest") return body
        const { freeBoard: _dropped, ...rest } = body
        return rest
      },
    })
    await page.goto("/fantasy/my-league")

    await expect(page.getByTestId("my-league-board")).toBeVisible()
    await expect(page.locator('[data-testid="my-league-board"] tbody tr').first()).toBeVisible()
    // No baseline ⇒ no comparison. Absent, not an empty block reading "0 of 0 players move".
    await expect(page.getByTestId("league-delta")).toHaveCount(0)
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("a signed-in free account can reach the league surfaces from the nav", async ({ page }) => {
    // The fantasy surface is LOCKED for a free account (no subscription), and before G100-C1 that
    // meant the whole menu collapsed to an "Unlock Fantasy" upsell. The three league items have to
    // survive that lock or the free tier ships with no way to reach it — a feature that exists and
    // cannot be found.
    await signIn(page, SIGNED_IN_FREE)
    await mockApi(page, { entitlement: "free", leagues: "one" })
    await page.goto("/fantasy/rankings")

    for (const href of LEAGUE_NAV_HREFS) {
      // ⏳ AUTO-RETRYING, and it has to be. `page.goto` resolves on `load`; the nav gates these
      // items on `isSignedIn = !!accessToken`, which `AuthContext` restores in an EFFECT that runs
      // after that. A single-shot `await locator.count()` therefore reads whatever happened to be
      // painted at one instant — it wins on a fast machine and loses on a loaded CI runner, which
      // is exactly what it did (2026-08-13: one commit, two runs minutes apart, one red one green,
      // with only a markdown file changed between them).
      await expect(
        page.locator(`a[href="${href}"]`),
        `${href} is unreachable for a signed-in free account`,
      ).not.toHaveCount(0)
    }
  })

  test("a logged-out visitor is not offered the league surfaces", async ({ page }) => {
    // The counterpart, and the reason `freeSignedIn` is not just `public: true`: a league is stored
    // against a Cognito `sub`, so these pages bounce an anonymous visitor to /login. A nav item
    // whose only behaviour is a redirect is a menu that lies about what it opens.
    await mockApi(page, { entitlement: "free" })
    await page.goto("/fantasy/rankings")

    // ⚠️⚠️ READ THIS BEFORE TRUSTING THE ASSERTIONS BELOW — THEY ARE WEAKER THAN THEY LOOK, AND
    // THE COMMENT THEY USED TO CARRY NAMED THE WRONG MECHANISM.
    //
    // The requirement is real and is met. But it is NOT met by `freeSignedIn && isSignedIn`, which
    // is what a reader naturally assumes from the sibling test. It is met one level up, by
    // `showSubNav = authenticated || isSignedIn` (`components/nav.tsx:93`), which withholds the
    // ENTIRE sport sub-nav from an anonymous visitor. MEASURED: a logged-out nav renders one
    // unlabelled button and the links `/`, `/fantasy/rankings`, `/fantasy/track-record`, `/about`,
    // `/login`, `/signup`; a signed-in one renders `NFL`/`MLB` dropdowns and all 20+ surface items.
    //
    // ⇒ THIS SPEC IS OVER-DETERMINED. `lockedVisibleItems` can be broken in EITHER direction —
    // items dropped, or `freeSignedIn` promoted to public — and these assertions stay green,
    // because the menu that would carry them is not in the DOM at all. Both breaks are registered
    // in `e2e/red-proof.mjs` as DECLARED-GREEN cases so that fact is recorded rather than
    // rediscovered; if either ever flips to RED, the nav's structure moved and this note is stale.
    //
    // The anchor below therefore claims only what it can: the logged-out nav MOUNTED. That is the
    // one failure this spec can genuinely catch (a blank or crashed page silently satisfying three
    // `toHaveCount(0)`s), and it is worth catching — it is the shape the repo has been bitten by
    // repeatedly, where a test reads as coverage so nobody looks again.
    await expect(
      page.locator('nav a[href="/signup"]'),
      "the logged-out nav never mounted — the absences below would be vacuous",
    ).not.toHaveCount(0)

    for (const href of LEAGUE_NAV_HREFS) {
      await expect(
        page.locator(`a[href="${href}"]`),
        `${href} was offered to a logged-out visitor, who cannot use it`,
      ).toHaveCount(0)
    }
  })
})

// ══════════════════════════════════════════════════════════════════════════════════════════════════
// G100-C1 FOLLOW-UP — the three defects the first real league surfaced (operator, 2026-08-08)
// ══════════════════════════════════════════════════════════════════════════════════════════════════
//
// Every one of these was invisible to the suite above and visible in the first ten seconds of using
// the page, which is worth recording: the original spec proved the delta was CORRECT and never asked
// whether it was USEFUL, whether the table below it was navigable, or whether the second create path
// enforced the same limit as the first.

test.describe("the draftable pool bounds the highlights", () => {
  test("the pool states its own arithmetic, and counts bench spots", async ({ page }) => {
    const { errors } = await openMyLeague(page)
    await expect(page.getByTestId("league-delta")).toBeVisible()

    // 10 teams × 16 drafted spots (QB1 RB2 WR2 TE2 SF1 K1 DST1 + 6 bench). Bench IS drafted, and
    // that is the point of the number: a last-round bench pick is exactly the "does my scoring make
    // him worth a pick?" call this screen should be able to speak to.
    await expect(page.getByTestId("delta-pool-note")).toContainText("10 teams × 16")
    await expect(page.getByTestId("delta-pool-note")).toContainText("the top 160")
    expectNoPageErrors(errors)
  })

  test("IR and taxi spots are not draft picks, so they do not widen the pool", async ({ page }) => {
    // ⚠️ ISOLATING: the ONLY change from the test above is three IR spots and two taxi spots. If the
    // exclusion is dropped the pool becomes 10 × 21 = 210 and both assertions move together, so this
    // case can only fail for the reason it names. The default fixture has no reserve slots at all —
    // which is exactly why an inclusion bug would have shipped invisibly.
    const { errors } = await openMyLeague(page, {
      transform: withLeague({
        roster: [
          { name: "QB", count: 1, eligible: ["QB"], bench: false },
          { name: "RB", count: 2, eligible: ["RB"], bench: false },
          { name: "WR", count: 2, eligible: ["WR"], bench: false },
          { name: "TE", count: 2, eligible: ["TE"], bench: false },
          { name: "SUPERFLEX", count: 1, eligible: ["QB", "RB", "WR", "TE"], bench: false },
          { name: "K", count: 1, eligible: ["K"], bench: false },
          { name: "DST", count: 1, eligible: ["DST"], bench: false },
          { name: "BENCH", count: 6, eligible: [], bench: true },
          { name: "IR", count: 3, eligible: [], bench: true },
          { name: "TAXI", count: 2, eligible: [], bench: true },
        ],
      }),
    })
    await expect(page.getByTestId("delta-pool-note")).toContainText("10 teams × 16")
    await expect(page.getByTestId("delta-pool-note")).toContainText("the top 160")
    expectNoPageErrors(errors)
  })

  test("shrinking the pool shrinks the highlights — the filter actually gates them", async ({
    page,
  }) => {
    // ⭐ THE DIFFERENTIAL, and the only assertion here that proves the pool REACHES the highlight
    // lists rather than merely being computed and rendered. A 4-team league with one starter and no
    // bench drafts four players; five risers and five fallers cannot come out of four players.
    //
    // Stated as a comparison rather than an absolute count because the absolute is a property of
    // the fixture's numbers, while "a smaller pool yields no more highlights" is a property of the
    // CODE — the distinction the repo keeps relearning about assertions that inherit their
    // artifact's incidentals.
    const wide = await openMyLeague(page)
    await expect(page.getByTestId("league-delta")).toBeVisible()
    const wideCards = await page.getByTestId("mover-card").count()
    expect(wideCards, "the default league produced no highlights to compare against").toBeGreaterThan(0)
    expectNoPageErrors(wide.errors)

    const narrow = await openMyLeague(page, {
      transform: withLeague({
        n_teams: 4,
        roster: [{ name: "QB", count: 1, eligible: ["QB"], bench: false }],
      }),
    })
    await expect(page.getByTestId("delta-pool-note")).toContainText("the top 4")
    expect(
      await page.getByTestId("mover-card").count(),
      "a 4-player draft pool still produced as many highlights as a 160-player one",
    ).toBeLessThan(wideCards)
    expectNoPageErrors(narrow.errors)
  })

  test("no kicker or defense can lead the list", async ({ page }) => {
    // ⭐ THE SECOND DISQUALIFICATION, and the one the pool filter did NOT fix: K and D/ST sit
    // comfortably inside any real draft pool, and on the first real league four of the top five
    // movers were defenses. ~32 of each project within a narrow band, so any difference in a
    // league's K/DST scoring reorders the whole position at once — and the band sits deep enough in
    // the overall list that a one-tier shuffle is worth dozens of places, every one of them noise.
    //
    // ⚠️ ASSERTED ON THE RENDERED POSITION, not on the delta's own `lowPred` field. Reading back the
    // value the filter wrote would be the "test restates the code" shape (NF-C0e): it would pass
    // just as well if the flag were computed correctly and then never consulted. The badge is what
    // the reader sees.
    const { errors } = await openMyLeague(page)
    await expect(page.getByTestId("league-delta")).toBeVisible()

    const cards = page.getByTestId("mover-card")
    expect(await cards.count(), "no highlights rendered — the assertion below is vacuous")
      .toBeGreaterThan(0)

    for (const text of await cards.allInnerTexts()) {
      const pos = text.match(/\b(QB|RB|WR|TE|K|DST)\b/)?.[1]
      expect(pos, `a highlight card carried no position at all: ${text}`).toBeTruthy()
      expect(
        ["K", "DST"].includes(pos as string),
        `a ${pos} led the movers — its rank is not a signal, and the section below cannot explain it`,
      ).toBe(false)
    }
    expectNoPageErrors(errors)
  })

  test("…but they keep their place on the board", async ({ page }) => {
    // The other side of the clause, and the reason it is a HIGHLIGHT filter rather than a data one.
    // Dropping K/DST from the board would delete two roster slots the user has to fill — the NF1.6
    // defect that put them on the board in the first place.
    const { errors } = await openMyLeague(page)
    await expect(page.getByTestId("my-league-board")).toBeVisible()
    await page.getByRole("button", { name: "DST", exact: true }).click()
    const rows = page.locator('[data-testid="my-league-board"] tbody tr')
    expect(await rows.count(), "the board dropped D/ST entirely").toBeGreaterThan(0)
    expectNoPageErrors(errors)
  })

  test("the board below still carries every player, and their moves", async ({ page }) => {
    // The pool bounds the HIGHLIGHTS, never the data. Filtering the board itself would blank the
    // "vs free board" column for most rows — hiding a real number rather than declining to lead
    // with it.
    const { errors } = await openMyLeague(page)
    await expect(page.getByTestId("my-league-board")).toBeVisible()
    const total = Number(
      (await page.getByText(/\d+–\d+ of [\d,]+/).first().textContent())
        ?.split("of")[1]
        ?.replace(/[^\d]/g, "") ?? 0,
    )
    expect(total, "the board was truncated to the draft pool").toBeGreaterThan(160)
    expectNoPageErrors(errors)
  })
})

test.describe("the board is paged", () => {
  test("a page holds one page of rows, and the numbering continues across pages", async ({
    page,
  }) => {
    const { errors } = await openMyLeague(page)
    await expect(page.getByTestId("my-league-board")).toBeVisible()

    const rows = page.locator('[data-testid="my-league-board"] tbody tr')
    await expect(rows).toHaveCount(50)
    await expect(rows.first().locator("td").first()).toHaveText("1")

    await page.getByRole("button", { name: "Next" }).first().click()
    // ⚠️ THE ASSERTION THAT MATTERS. A bare `i + 1` renders "1" at the top of every page, and the
    // row number silently stops meaning rank and starts meaning position-on-screen. It looks
    // completely normal.
    await expect(rows.first().locator("td").first()).toHaveText("51")
    expectNoPageErrors(errors)
  })

  test("changing position while deep in the pages never shows an empty table", async ({ page }) => {
    // The classic paging bug: the filter shrinks the row count and the page index is left pointing
    // past the end, so the table renders EMPTY — which reads as "you have no TEs" rather than "you
    // are on page 9 of 2".
    const { errors } = await openMyLeague(page)
    await expect(page.getByTestId("my-league-board")).toBeVisible()

    await page.getByRole("button", { name: "»" }).first().click()
    await page.getByRole("button", { name: "TE", exact: true }).click()

    const rows = page.locator('[data-testid="my-league-board"] tbody tr')
    expect(await rows.count(), "the table was empty after filtering from a late page").toBeGreaterThan(0)
    expectNoPageErrors(errors)
  })
})

test.describe("the one-league quota is enforced on BOTH create paths", () => {
  /** Open a surface as a signed-in free account with `n` leagues already saved. */
  async function open(page: Page, path: string, leagues: "none" | "one") {
    await signIn(page, { groups: [] })
    const errors = collectPageErrors(page)
    await mockApi(page, { entitlement: "free", leagues })
    await page.goto(path)
    return { errors }
  }

  test("import: a SECOND league cannot be chosen, and the way out is offered", async ({ page }) => {
    // ⭐ THE DEFECT. The manual editor refused a second league from the first cut; the IMPORTER did
    // not, so a free account at its quota could pick a platform, type a username, wait on a preview
    // and press Save before meeting a 409. The tier is enforced by WHICH COMPONENT RENDERS — this
    // is the freemium build's own lesson (#681 gated one of three renderers) recurring on the two
    // create paths.
    const { errors } = await open(page, "/fantasy/import", "one")

    await page.getByPlaceholder("Paste your Sleeper league ID").fill("e2e-tester")
    await page.getByRole("button", { name: "Import", exact: true }).click()

    await expect(page.getByTestId("league-quota-notice")).toBeVisible()
    // Two rows, and they must behave DIFFERENTLY — one saved (re-import = update, allowed), one new.
    await expect(page.getByTestId("import-league-locked")).toHaveCount(1)
    await expect(page.getByTestId("import-league-locked")).toBeDisabled()
    await expect(page.getByTestId("import-league-option")).toHaveCount(1)
    await expect(page.getByTestId("import-league-option")).toBeEnabled()
    expectNoPageErrors(errors)
  })

  test("import: with no league saved, nothing is locked", async ({ page }) => {
    // The other side of the same clause. Without this, "lock everything always" passes the test
    // above — and the free tier's one league would be unreachable.
    const { errors } = await open(page, "/fantasy/import", "none")

    await page.getByPlaceholder("Paste your Sleeper league ID").fill("e2e-tester")
    await page.getByRole("button", { name: "Import", exact: true }).click()

    await expect(page.getByTestId("import-league-option")).toHaveCount(2)
    await expect(page.getByTestId("league-quota-notice")).toHaveCount(0)
    expectNoPageErrors(errors)
  })

  test("the refusal always carries a way to lift it", async ({ page }) => {
    // ⭐ A limit with no way past it is a dead end, and the way past it is the conversion this whole
    // funnel exists for. The CTA lives INSIDE `LeagueQuotaNotice` precisely so a third create path
    // cannot ship the refusal without the offer.
    const { errors } = await open(page, "/fantasy/league-settings", "one")
    // The editor opens on the league you already have (returning users land on their own settings),
    // so the refusal is met the moment you ask for a SECOND one — which is the honest trigger, and
    // the reason `atQuota` is keyed on `leagueId === null` rather than on the saved count alone.
    await page.getByRole("button", { name: "New league" }).click()
    await expect(page.getByTestId("league-quota-notice")).toBeVisible()
    const cta = page.getByTestId("league-quota-upgrade")
    await expect(cta).toBeVisible()
    await expect(cta).toHaveAttribute("href", "/subscribe")
    expectNoPageErrors(errors)
  })
})
