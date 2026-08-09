import { expect, test, type Page } from "@playwright/test"
import { captureAnalytics, collectPageErrors, mockApi } from "../support/api-mock"
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

/** Every spec here needs the same three things: a session, the API, and no third-party traffic. */
async function openMyLeague(
  page: Page,
  options: { leagues?: "none" | "one" | "overQuota"; groups?: string[] } = {},
) {
  await signIn(page, { groups: options.groups ?? SIGNED_IN_FREE.groups })
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, { entitlement: "free", leagues: options.leagues ?? "one" })
  const events = await captureAnalytics(page)
  await page.goto("/fantasy/my-league")
  return { errors, mock, events }
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
    // caught it as a TAUTOLOGY: the list MEMBERSHIP and the arrow both derive from `ovrDelta`, so
    // inverting the subtraction moves each player into the other list AND flips their arrow —
    // perfectly self-consistent, and the assertion passes on the exact defect it was written for.
    // (The NF-C0e "reading a value back under the key the code wrote" shape.)
    //
    // The card's OVERALL RANK PAIR ("#128 → #34") is the independent quantity: both numbers are
    // read straight off the two boards, so inverting the rank subtraction changes WHICH players
    // appear in each block but cannot change the numbers on their cards. A "riser" whose rank got
    // BIGGER is then a visible contradiction.
    //
    // ⚠️ Asserted per card, not on an aggregate. Rank is exact here — there is no averaging to do
    // and no player who can legitimately buck it: `ovrDelta > 0` means precisely
    // `genericOvrRank > leagueOvrRank`, so every single riser card must show a decrease.
    const rankMoves = async (block: typeof risers, label: string) => {
      const out: { from: number; to: number }[] = []
      for (const text of await block.locator('[data-testid="ovr-rank-move"]').allTextContents()) {
        const m = text.match(/#(\d+)\s*→\s*#(\d+)/)
        if (m) out.push({ from: Number(m[1]), to: Number(m[2]) })
      }
      expect(out.length, `no ${label} card rendered an overall-rank pair — the anchor is missing`)
        .toBeGreaterThan(0)
      return out
    }

    for (const { from, to } of await rankMoves(risers, "riser")) {
      expect(
        to,
        `a RISER moved from #${from} to #${to} — a worse rank. The rank delta's sign is inverted.`,
      ).toBeLessThan(from)
    }
    for (const { from, to } of await rankMoves(fallers, "faller")) {
      expect(
        to,
        `a FALLER moved from #${from} to #${to} — a better rank. The rank delta's sign is inverted.`,
      ).toBeGreaterThan(from)
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

  test("a signed-in free account can reach the league surfaces from the nav", async ({ page }) => {
    // The fantasy surface is LOCKED for a free account (no subscription), and before G100-C1 that
    // meant the whole menu collapsed to an "Unlock Fantasy" upsell. The three league items have to
    // survive that lock or the free tier ships with no way to reach it — a feature that exists and
    // cannot be found.
    await signIn(page, SIGNED_IN_FREE)
    await mockApi(page, { entitlement: "free", leagues: "one" })
    await page.goto("/fantasy/rankings")

    for (const href of ["/fantasy/my-league", "/fantasy/import", "/fantasy/league-settings"]) {
      expect(
        await page.locator(`a[href="${href}"]`).count(),
        `${href} is unreachable for a signed-in free account`,
      ).toBeGreaterThan(0)
    }
  })

  test("a logged-out visitor is not offered the league surfaces", async ({ page }) => {
    // The counterpart, and the reason `freeSignedIn` is not just `public: true`: a league is stored
    // against a Cognito `sub`, so these pages bounce an anonymous visitor to /login. A nav item
    // whose only behaviour is a redirect is a menu that lies about what it opens.
    await mockApi(page, { entitlement: "free" })
    await page.goto("/fantasy/rankings")

    for (const href of ["/fantasy/my-league", "/fantasy/import", "/fantasy/league-settings"]) {
      expect(
        await page.locator(`a[href="${href}"]`).count(),
        `${href} was offered to a logged-out visitor, who cannot use it`,
      ).toBe(0)
    }
  })
})
