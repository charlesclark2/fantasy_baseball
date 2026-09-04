import { expect, test, type Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors, internalHrefs } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NCAAF-P3.3 — THE TEAM STATS PAGE, AT THE RENDER LEVEL.
 *
 * ⭐ WHY EVERY ASSERTION HERE IS ON RENDERED OUTPUT. NF-C4 measured eight frontend defects that were
 * all green in CI because the suite asserted on SOURCE — a guard that greps a component, or walks a
 * className, tests that somebody TYPED a string. Nothing below reads this repo's source: each clause
 * reads the DOM the browser produced, and every number it checks is read from the FIXTURE'S OWN
 * VALUES rather than typed here, so a re-capture moves the expectation with the payload instead of
 * turning the suite red for the wrong reason.
 *
 * WHAT THIS SURFACE IS, AND THE FOUR THINGS THAT COULD GO WRONG SILENTLY:
 *
 *   1. THE RATING COULD APPEAR WITHOUT ITS BAND. That is the page's whole licence to publish:
 *      `best_alpha = 0`, and at week 1 the posterior IS the prior (measured on the live board:
 *      +3.09 with a spread of 7.29, a range from about −6 to +12). A bare "+3.1" would claim a
 *      precision the model does not have, and it would look completely normal.
 *
 *   2. TWO DIFFERENT ABSENCES COULD RENDER AS ONE. On a September Saturday a CORRECT page has two
 *      empty blocks; if "nobody has played yet" reads the same as "our mart build failed", every
 *      recurrence re-investigates from scratch (NF-C6b / NF-K1).
 *
 *   3. AN UPCOMING GAME COULD RENDER AS A PLAYED ONE. A `0-0` beside next Saturday's opponent is a
 *      fabricated result, and it is the ordinary state of most of this page in September.
 *
 *   4. THE CONFERENCE COULD BE THE WRONG SEASON'S. Eleven FBS programs moved for 2026, and a
 *      "current" read would file a mover under the league it ends up in rather than the one it
 *      plays in. The fixture is a REAL mover for exactly this reason.
 *
 * ⚠️ THE CAPTURED FIXTURES ARE THE DEFAULT because they are production. Both carry `efficiency` and
 * `splits` as stated absences — the P1.1 rollups hold no 2026 rows yet — so the AVAILABLE branch of
 * those blocks is reached only through the GENERATED `ncaaf-team-populated.synthetic.json`. On the
 * first re-capture after those rollups materialize, retire the generated fixture and re-anchor onto
 * the capture; keep the ABSENT arm alive on whichever fixture still has it.
 */

const FIXTURE_DIR = join(process.cwd(), "e2e", "fixtures", "api")
const readFixture = (name: string) => JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8"))

/** 68 — Boise State. A 2026 REALIGNMENT MOVER (Mountain West → Pac-12), wholly-upcoming schedule. */
const TEAM_68 = readFixture("ncaaf-team-68.json")
/** 2449 — North Dakota State. NEW TO FBS, and it has a completed game. */
const TEAM_2449 = readFixture("ncaaf-team-2449.json")
/** All four blocks available. Generated — see the file header. */
const TEAM_POPULATED = readFixture("ncaaf-team-populated.synthetic.json")

const path = (id: number | string) => `/ncaaf/teams/${id}`

async function open(page: Page, id: number | string, options: MockOptions = {}) {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, options)
  await page.goto(path(id))
  return { mock, errors }
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 1. The page renders from the API, for a real team
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a captured team renders its identity from the payload", async ({ page }) => {
  const { mock, errors } = await open(page, 68)
  await expect(page.getByTestId("ncaaf-team-header")).toHaveAttribute(
    "data-team-id",
    String(TEAM_68.team.team_id),
  )
  await expect(page.getByTestId("ncaaf-team-name")).toHaveText(TEAM_68.team.team)
  await expect(page.getByTestId("ncaaf-team-season")).toContainText(String(TEAM_68.season))
  expectNoPageErrors(errors)
  await expectNoNaN(page)
  expectApiFullyMocked(mock)
})

test("the page asks for the team in the URL, not a fixed one", async ({ page }) => {
  // ⭐ THE HARNESS'S OWN NON-VACUITY. Every clause below reads a fixture; if the page requested a
  // constant id, or the mock answered every id with one payload, all of them would pass while the
  // browser sat on the wrong team. Two ids, two different payloads, asserted to differ.
  await open(page, 2449)
  await expect(page.getByTestId("ncaaf-team-name")).toHaveText(TEAM_2449.team.team)
  expect(TEAM_2449.team.team).not.toEqual(TEAM_68.team.team)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 2. The band travels with the rating — the page's licence to publish
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the strength rating never appears without its band", async ({ page }) => {
  // ⭐⭐ THE LOAD-BEARING CLAUSE. `best_alpha = 0` and at week 1 the posterior IS the prior, so a
  // bare point rating would publish a precision the model does not claim — and it would look
  // entirely normal on the page. Both elements, always, in the same block.
  await open(page, 68)
  const rating = page.getByTestId("ncaaf-strength-rating")
  await expect(rating).toBeVisible()
  await expect(rating).toHaveAttribute(
    "data-strength-margin",
    String(TEAM_68.strength.current.strength_margin),
  )
  const band = page.getByTestId("ncaaf-strength-band")
  await expect(band).toBeVisible()

  // The band is the SERVED spread evaluated at the page's own level, not a number typed here:
  // recompute it from the fixture and demand the rendered text carries both ends.
  const mu = TEAM_68.strength.current.strength_margin
  const sd = TEAM_68.strength.current.strength_margin_sd
  expect(sd).toBeGreaterThan(0)
  const z = 1.2815515655446004 // the 0.90 normal quantile — the level `lib/ncaaf-team.ts` quotes
  const lo = mu - z * sd
  const hi = mu + z * sd
  const signed = (v: number) => `${v < 0 ? "−" : "+"}${Math.abs(v).toFixed(1)}`
  await expect(band).toContainText(signed(lo))
  await expect(band).toContainText(signed(hi))

  // ⚠️ AND THE BAND IS WIDE, which is the fact the sentence beside it explains. Asserting the WIDTH
  // is what stops a future change from rendering a band so narrow it implies certainty the model
  // does not have — a band is not honest merely by existing.
  expect(hi - lo).toBeGreaterThan(Math.abs(mu))
})

test("a week-one rating says why its range is wide, rather than leaving it unexplained", async ({ page }) => {
  await open(page, 68)
  expect(TEAM_68.strength.current.games_in_window).toBe(0)
  const note = page.getByTestId("ncaaf-strength-preseason-note")
  await expect(note).toBeVisible()
  // ⛔ It explains, it does not apologise or withdraw: the rating is still on the page.
  await expect(page.getByTestId("ncaaf-strength-rating")).toBeVisible()
})

test("the strength curve is drawn from the served parameters, and it is a real shape", async ({ page }) => {
  // A `<path>` renders whether or not its `d` came from the payload, and an empty or degenerate one
  // looks like a quiet section rather than a bug. So read the drawn geometry.
  await open(page, 68)
  const curve = page.getByTestId("ncaaf-strength-curve")
  await expect(curve).toBeVisible()
  const d = await curve.locator("path[data-testid$='-path']").first().getAttribute("d")
  expect(d, "the strength curve drew no path").toBeTruthy()
  expect((d ?? "").split("L").length, "the curve is a straight line, not a distribution").toBeGreaterThan(10)
})

test("the curve does not borrow the game board's degradation warning", async ({ page }) => {
  // ⭐⭐ THE POINT OF THIS CLAUSE IS THAT ONE RENDERING MEANT TWO DIFFERENT FACTS (NF-C6b).
  //
  // `DistributionCurve` shows an AMBER note when its source is parametric, because on a game card
  // that IS a degradation: the simulator publishes a quantile ladder and we did not get it. The
  // strength posterior's served form is a mean and a spread — there are no simulated quantiles to
  // be missing — so the identical note announced a defect that does not exist, in a warning colour,
  // and its noun ("this game's") is wrong on a page that is not about a game. It shipped, and the
  // operator read it as a broken chart on the first page they opened.
  //
  // ⚠️ NON-VACUITY FIRST, and it is load-bearing here: this curve IS parametric, so the branch
  // under test genuinely executes. Without that assertion the two below would pass on a curve that
  // never reached the code path at all (NF1.7 (a)).
  await open(page, 68)
  const curve = page.getByTestId("ncaaf-strength-curve")
  await expect(curve).toHaveAttribute("data-curve-source", "parametric")

  await expect(
    page.getByTestId("ncaaf-strength-curve-parametric-note"),
    "the team page is rendering the game card's parametric warning",
  ).toHaveCount(0)
  // ⛔ And not merely under a different testid: the game surface's wording must not be on this
  // page by ANY route. Matched on the distinctive noun rather than the whole sentence, so a reword
  // of the game copy does not silently retire this guard.
  await expect(page.locator("body")).not.toContainText("this game's simulated quantiles")

  // ⭐ THE PROVENANCE IS STILL STATED — suppressing the warning is only admissible because the
  // hint says the same true thing in this surface's own words. A clause that checked only the
  // absence would be satisfied by a page that had quietly stopped explaining the curve at all.
  await expect(page.getByTestId("ncaaf-strength-curve-hint")).toContainText("mean and spread")
})

test("the zero rule on a rating axis is named for a rating, not for a game", async ({ page }) => {
  // "even" is what zero means on a game MARGIN — a tied game — and it is the shared component's
  // default. Zero on a rating axis is an AVERAGE FBS TEAM. The rule is drawn precisely to give the
  // reader the comparison that makes the number mean something, so carrying the game surface's
  // noun across answers the wrong question in the one place the page is trying to orient them.
  await open(page, 68)
  const svg = page.getByTestId("ncaaf-strength-curve").locator("svg")
  await expect(svg).toContainText("average FBS team")
  await expect(svg, "the rating axis is labelled with the game board's word").not.toContainText(
    /\beven\b/,
  )
})

test("the week-by-week trend appears only when there is more than one week to draw", async ({ page }) => {
  // ⭐ TWO-SIDED, and the negative half is the ordinary September state. One point is not a trend,
  // and a component that drew one anyway would render a picture of nothing that looks like data.
  await open(page, 68)
  expect(TEAM_68.strength.weeks.length).toBe(1)
  await expect(page.getByTestId("ncaaf-strength-trend")).toHaveCount(0)

  await open(page, 68, { ncaafTeam: "populated" })
  expect(TEAM_POPULATED.strength.weeks.length).toBeGreaterThan(1)
  const trend = page.getByTestId("ncaaf-strength-trend")
  await expect(trend).toBeVisible()
  // The BAND is plotted, not only the line — that is what makes "the model got more confident"
  // visible at all, and a line-only chart would look almost identical while saying much less.
  await expect(trend.getByTestId("ncaaf-strength-trend-band")).toBeAttached()
  await expect(trend.getByTestId("ncaaf-strength-trend-line")).toBeAttached()
  // The week labels are the SERVED `as_of_week`, never a 1..n index.
  const weeks = TEAM_POPULATED.strength.weeks
  await expect(trend.getByTestId("ncaaf-strength-trend-first")).toContainText(String(weeks[0].as_of_week))
  await expect(trend.getByTestId("ncaaf-strength-trend-last")).toContainText(
    String(weeks[weeks.length - 1].as_of_week),
  )
})

test("the rating's three parts are shown, and they add up to it", async ({ page }) => {
  // ⭐ THE DECOMPOSITION SUMS TO THE RATING EXACTLY — a property of the model, and what makes the
  // number auditable rather than a black box. Asserting the ARITHMETIC (not just that three boxes
  // rendered) is what would catch a part wired to the wrong field.
  await open(page, 68)
  const c = TEAM_68.strength.current
  const sum =
    c.strength_conference_component + c.strength_covariate_component + c.strength_team_component
  expect(sum).toBeCloseTo(c.strength_margin, 6)
  for (const key of ["conference", "covariates", "team"]) {
    await expect(page.getByTestId(`ncaaf-strength-part-${key}`)).toBeVisible()
  }
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 3. Realignment — the AC this story is graded on
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a 2026 conference mover renders the season's conference, resolved from the dim", async ({ page }) => {
  // ⭐ THE NAMED TEST CASE. Boise State moved Mountain West → Pac-12 for 2026; a type-1 "current"
  // read, or a value carried along from a prior-season source, would say the other one. The fixture
  // is a REAL mover captured from production, so this is a statement about the shipped payload.
  await open(page, 68)
  const conf = page.getByTestId("ncaaf-team-conference")
  await expect(conf).toHaveText(TEAM_68.team.conference)
  await expect(conf).toHaveAttribute("data-conference-source", TEAM_68.team.conference_source)
  // The capture's own claim about itself, so a re-capture that lost the property fails HERE with a
  // message that says which half moved.
  expect(TEAM_68.team.conference_source).toBe("scd2_dim")
  // ...and the season is rendered beside it, so "Pac-12" is unambiguous about which year it names.
  await expect(page.getByTestId("ncaaf-team-season")).toContainText(String(TEAM_68.team.season))
})

test("a first-year FBS program is named as one, and told why its rating is thin", async ({ page }) => {
  await open(page, 2449)
  expect(TEAM_2449.team.is_new_to_fbs).toBe(true)
  await expect(page.getByTestId("ncaaf-team-new-to-fbs")).toBeVisible()
  await expect(page.getByTestId("ncaaf-team-new-to-fbs-note")).toBeVisible()
  // ⭐ THE TWO-SIDED HALF. A chip rendered unconditionally would pass the clause above and say
  // nothing; the established team must NOT carry it.
  await open(page, 68)
  expect(TEAM_68.team.is_new_to_fbs).toBe(false)
  await expect(page.getByTestId("ncaaf-team-new-to-fbs")).toHaveCount(0)
  await expect(page.getByTestId("ncaaf-team-new-to-fbs-note")).toHaveCount(0)
})

test("a conference disagreement with the model's own input is surfaced, not swallowed", async ({ page }) => {
  // The served flag is a finding about OUR INPUTS — the posterior was pooled toward a league this
  // team does not play in. It cannot be produced by any captured payload today (all agree), so the
  // branch is driven through a transform; without this it would be untestable and pass on nothing.
  await open(page, 68, {
    transform: (pathname, body) =>
      pathname.startsWith("/ncaaf/teams/")
        ? { ...body, team: { ...(body as any).team, conference_matches_model_input: false } }
        : body,
  })
  await expect(page.getByTestId("ncaaf-team-conference-mismatch")).toBeVisible()
  // Two-sided: the captured payload agrees, so the notice must be absent there.
  await open(page, 68)
  expect(TEAM_68.team.conference_matches_model_input).toBe(true)
  await expect(page.getByTestId("ncaaf-team-conference-mismatch")).toHaveCount(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 4. The absences stay apart — the page's central honesty claim
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("an empty block states its own reason, in words", async ({ page }) => {
  await open(page, 68)
  for (const block of ["efficiency", "splits"] as const) {
    const el = page.getByTestId(`ncaaf-team-${block}`)
    await expect(el).toHaveAttribute("data-block-status", "unavailable")
    await expect(el).toHaveAttribute("data-block-reason", TEAM_68[block].reason)
    // ⛔ Never a blank. Something is always SAID about why.
    await expect(page.getByTestId(`ncaaf-team-${block}-absent-reason`)).not.toHaveText("")
  }
})

test("the three causes of an empty block read differently from one another", async ({ page }) => {
  // ⭐⭐ THE CLAUSE THE WHOLE CONTRACT EXISTS FOR. "Nobody has played yet" is the CORRECT state of
  // week 1 and needs no action; "the rollup holds nothing for this season" is a different fact; "we
  // could not read the tables" is a DEFECT. A surface handed one blank for all three makes every
  // recurrence re-investigate from scratch.
  const texts: string[] = []
  for (const reason of [
    "no_games_played_yet",
    "no_row_for_this_team_and_season",
    "source_marts_unavailable",
  ]) {
    await open(page, 68, {
      transform: (pathname, body) =>
        pathname.startsWith("/ncaaf/teams/")
          ? { ...body, efficiency: { ...(body as any).efficiency, status: "unavailable", reason } }
          : body,
    })
    texts.push(await page.getByTestId("ncaaf-team-efficiency-absent-reason").innerText())
  }
  expect(new Set(texts).size, `the three causes rendered as ${new Set(texts).size} sentence(s)`).toBe(3)
  // The defect case must READ like our problem, not like an ordinary early-season state.
  expect(texts[2].toLowerCase()).toContain("our side")
})

test("a reason we have no sentence for still says something", async ({ page }) => {
  // ⛔ A NEW `reason` RENDERING AS A BLANK is the exact failure the field exists to prevent, and it
  // is the one that arrives silently — a later story adds a reason and this page goes quiet.
  await open(page, 68, {
    transform: (pathname, body) =>
      pathname.startsWith("/ncaaf/teams/")
        ? {
            ...body,
            efficiency: {
              ...(body as any).efficiency,
              status: "unavailable",
              reason: "a_reason_invented_after_this_page_shipped",
            },
          }
        : body,
  })
  await expect(page.getByTestId("ncaaf-team-efficiency-absent-reason")).not.toHaveText("")
})

test("the page renders its available blocks even when two are empty", async ({ page }) => {
  // ⚠️ THE PARTIAL PAGE IS THE ORDINARY PAGE. Measured on the wire: every 2026 team serves a
  // rating and a schedule with efficiency and splits absent. A page that hid itself until all four
  // blocks were present would be blank for the whole of September.
  await open(page, 68)
  await expect(page.getByTestId("ncaaf-team-strength")).toHaveAttribute("data-block-status", "available")
  await expect(page.getByTestId("ncaaf-team-schedule")).toHaveAttribute("data-block-status", "available")
  await expect(page.getByTestId("ncaaf-team-efficiency")).toHaveAttribute("data-block-status", "unavailable")
})

test("a fully populated team renders all four blocks with real numbers", async ({ page }) => {
  const { errors } = await open(page, 68, { ncaafTeam: "populated" })
  for (const block of ["strength", "efficiency", "splits", "schedule"] as const) {
    await expect(page.getByTestId(`ncaaf-team-${block}`)).toHaveAttribute(
      "data-block-status",
      "available",
    )
  }
  // The adjusted AND raw columns are both populated — the pairing is the substance of this block,
  // and a build that rendered one under both headings would look complete.
  const e = TEAM_POPULATED.efficiency
  await expect(page.getByTestId("ncaaf-efficiency-off-ppa-adjusted")).toHaveText(
    e.adj_off_ppa.toFixed(3),
  )
  await expect(page.getByTestId("ncaaf-efficiency-off-ppa-raw")).toHaveText(e.raw_off_ppa.toFixed(3))
  expect(e.adj_off_ppa).not.toEqual(e.raw_off_ppa)
  await expect(page.getByTestId("ncaaf-splits-off-line-yards")).toHaveAttribute("data-has-value", "true")
  expectNoPageErrors(errors)
  await expectNoNaN(page)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 5. Schedule and results — realized vs upcoming
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("an upcoming game shows no score at all, and a played one shows its result", async ({ page }) => {
  // ⛔ NOT "shows a dash" — the ELEMENT IS ABSENT on an upcoming row. A `0-0` beside next Saturday's
  // opponent reads as a played scoreless game, which is a fabricated result.
  await open(page, 68, { ncaafTeam: "populated" })
  const played = TEAM_POPULATED.schedule.games.filter((g: any) => g.result !== null)
  const upcoming = TEAM_POPULATED.schedule.games.filter((g: any) => g.result === null)
  expect(played.length, "the fixture lost its played arm").toBeGreaterThan(0)
  expect(upcoming.length, "the fixture lost its upcoming arm").toBeGreaterThan(0)

  for (const g of played) {
    const row = page.locator(`[data-testid="ncaaf-schedule-row"][data-game-id="${g.game_id}"]`)
    await expect(row).toHaveAttribute("data-played", "true")
    const score = row.getByTestId("ncaaf-schedule-score")
    await expect(score).toContainText(`${g.team_points}`)
    await expect(score).toContainText(`${g.opponent_points}`)
    await expect(score).toContainText(g.result)
  }
  for (const g of upcoming) {
    const row = page.locator(`[data-testid="ncaaf-schedule-row"][data-game-id="${g.game_id}"]`)
    await expect(row).toHaveAttribute("data-played", "false")
    await expect(row.getByTestId("ncaaf-schedule-score")).toHaveCount(0)
  }
})

test("played and upcoming games are in separate, headed groups", async ({ page }) => {
  await open(page, 68, { ncaafTeam: "populated" })
  await expect(page.getByTestId("ncaaf-schedule-played")).toBeVisible()
  await expect(page.getByTestId("ncaaf-schedule-upcoming")).toBeVisible()
  const s = TEAM_POPULATED.schedule
  await expect(page.getByTestId("ncaaf-schedule-played").locator('[data-testid="ncaaf-schedule-row"]'))
    .toHaveCount(s.n_completed)
  await expect(page.getByTestId("ncaaf-schedule-upcoming").locator('[data-testid="ncaaf-schedule-row"]'))
    .toHaveCount(s.n_upcoming)
})

test("the record counts only games that were played", async ({ page }) => {
  // ⭐ "3-0 through three games" and "3-0 with nine still to play" are different statements. A team
  // with a full schedule and nothing played must show NO record at all — ⛔ never "0–0", which
  // reads as a played record.
  await open(page, 68)
  expect(TEAM_68.schedule.n_completed).toBe(0)
  expect(TEAM_68.schedule.n_games).toBeGreaterThan(0)
  await expect(page.getByTestId("ncaaf-team-record")).toHaveCount(0)

  await open(page, 2449)
  expect(TEAM_2449.schedule.n_completed).toBeGreaterThan(0)
  await expect(page.getByTestId("ncaaf-team-record")).toHaveText(
    `${TEAM_2449.schedule.wins}–${TEAM_2449.schedule.losses}`,
  )
})

test("the schedule shows the SERVED kickoff day, not the UTC date", async ({ page }) => {
  // ⭐⭐ THE INC-22 CLAUSE, AND THE FIXTURE IS BUILT TO DISCRIMINATE. A 02:00-UTC kickoff is the
  // PRIOR evening in every US timezone; the mart's own `game_date` column is `start_date::date` and
  // would name the next day. The served `game_day` is the America/Los_Angeles day — the same value
  // the game board uses — and this asserts the page renders THAT and does not re-derive a day from
  // the instant in the reader's own timezone.
  await open(page, 68, { ncaafTeam: "populated" })
  const crossing = TEAM_POPULATED.schedule.games.find(
    (g: any) => g.commence_time && g.game_day && g.commence_time.slice(0, 10) !== g.game_day,
  )
  expect(crossing, "the fixture no longer contains a day-crossing kickoff").toBeTruthy()
  const row = page.locator(`[data-testid="ncaaf-schedule-row"][data-game-id="${crossing.game_id}"]`)
  const shown = await row.getByTestId("ncaaf-schedule-day").innerText()
  // The rendered day must be the SERVED one. Both are formatted the same way, so compare the day
  // number: the UTC date is one day later and would print a different one.
  expect(shown).toContain(String(Number(crossing.game_day.slice(8, 10))))
  expect(shown).not.toContain(String(Number(crossing.commence_time.slice(8, 10))))
})

test("a non-FBS opponent is labelled as one", async ({ page }) => {
  // Real and common in September, and a reader needs it to read a result correctly — a 42-10 win
  // over an FCS opponent is a different fact from one over a conference rival.
  await open(page, 68, { ncaafTeam: "populated" })
  const nonFbs = TEAM_POPULATED.schedule.games.find((g: any) => g.is_fbs_matchup === false)
  expect(nonFbs, "the fixture lost its non-FBS game").toBeTruthy()
  const row = page.locator(`[data-testid="ncaaf-schedule-row"][data-game-id="${nonFbs.game_id}"]`)
  await expect(row.getByTestId("ncaaf-schedule-tags")).toContainText("non-FBS")
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 6. The empty states, the links, and the copy
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a team with nothing published reads differently from a failed read", async ({ page }) => {
  // ⭐ TWO DIFFERENT FACTS (NF-C6b). A 404 is an ORDINARY answer here — a non-FBS id, a season not
  // yet written — and a 500 is our problem. A harness that could only produce one could only ever
  // test half of this.
  await open(page, 999999, { ncaafTeam: "missing" })
  const missing = await page.getByTestId("ncaaf-team-not-found").innerText()
  await expect(page.getByTestId("ncaaf-team-error")).toHaveCount(0)

  await open(page, 68, { ncaafTeam: "failed" })
  const failed = await page.getByTestId("ncaaf-team-error").innerText()
  await expect(page.getByTestId("ncaaf-team-not-found")).toHaveCount(0)

  expect(missing).not.toEqual(failed)
  expect(failed.toLowerCase()).toContain("our side")
})

test("the game board links to a team page that exists", async ({ page }) => {
  // ⭐ RE-ANCHORED FROM P3.2's "no link points at a route that does not exist". Through P3.2 the
  // affordance was a DISABLED BUTTON because the route did not exist; it exists now, so the clause
  // becomes the stronger one: the links are real, they carry the SERVED team ids, and following one
  // lands on that team's page rather than a 404.
  const errors = collectPageErrors(page)
  await mockApi(page)
  await page.goto("/ncaaf/games")
  const links = page.getByTestId("ncaaf-team-page-links").first()
  await expect(links.getByTestId("ncaaf-team-page-link-home")).toBeVisible()

  const hrefs = await internalHrefs(page)
  const teamHrefs = hrefs.filter((h) => h.startsWith("/ncaaf/teams/"))
  expect(teamHrefs.length, "the board offers no team links at all").toBeGreaterThan(0)
  // ⛔ NO `/ncaaf/teams/null` — a null id would build a link that is a 404 in disguise.
  for (const h of teamHrefs) {
    expect(h).toMatch(/^\/ncaaf\/teams\/\d+$/)
  }

  await page.getByTestId("ncaaf-team-page-link-home").first().click()
  await expect(page).toHaveURL(/\/ncaaf\/teams\/\d+$/)
  await expect(page.getByTestId("ncaaf-team-header")).toBeVisible()
  expectNoPageErrors(errors)
})

test("every internal link on the team page points at a route that exists", async ({ page }) => {
  // ⭐ THE LINK IS FETCHED, NOT MATCHED AGAINST A LIST I TYPED. The first cut of this clause was an
  // allowlist regex of path prefixes, and it went red on `/changelog` — a real route the footer has
  // rendered all along. That is the shape of guard this repo keeps paying for: it does not test
  // whether the link works, it tests whether the author remembered a route, so it fails on correct
  // code and passes on a broken link to any prefix that happens to be listed.
  //
  // Asking the server is the assertion the clause's own name makes. A route this app does not serve
  // answers 404; a client-side route answers 200 (E9.56c is what this exists to catch — a CTA
  // pointing at a 404).
  await open(page, 68, { ncaafTeam: "populated" })
  const hrefs = [...new Set(await internalHrefs(page))]
  expect(hrefs.length, "the page rendered no internal links at all").toBeGreaterThan(0)
  for (const h of hrefs) {
    const res = await page.request.get(new URL(h, page.url()).toString())
    expect(res.status(), `${h} is not a route this app serves`).toBeLessThan(400)
  }
})

test("every rendered word passes the claim denylist", async ({ page, browserName }) => {
  // Over the WHOLE RENDERED PAGE rather than over the copy module, because a component's inline
  // heading is exactly where a stronger sentence would appear and no module-level screen can see
  // it. Run in every data mode so a claim hiding in an empty-state branch is caught too.
  for (const mode of ["captured", "populated", "missing", "failed"] as const) {
    const context = await page.context().browser()!.newContext()
    const p = await context.newPage()
    await mockApi(p, { ncaafTeam: mode })
    await p.goto(path(68))
    const text = await p.evaluate(() => document.body.innerText)
    expect(forbiddenPhrasesIn(text), `mode=${mode} browser=${browserName}`).toEqual([])
    await context.close()
  }
})

test("the SERVED disclosure is rendered verbatim", async ({ page }) => {
  // Rule 3 of `lib/ncaaf-copy.ts`: the disclosure belongs to the payload, and a paraphrase here
  // would be claim copy no screening had ever looked at.
  await open(page, 68)
  await expect(page.getByTestId("ncaaf-team-disclosure")).toHaveText(TEAM_68.framing.disclosure)
})

test("a payload whose framing flags change makes the page stop asserting the posture", async ({ page }) => {
  // ⭐ THE FLAGS BEING RESPECTED RATHER THAN MERELY PRESENT. Every claim-bearing sentence here is
  // warranted by `market_blind && projection_only && best_alpha === 0` and by nothing else.
  // ⚠️ IT CANNOT FIRE TODAY — the write path refuses a non-zero `best_alpha` outright. That is the
  // point: the guarantee lives in a writer this client cannot see, across a deploy boundary it
  // cannot control (the API Lambda has no CD — NF-C0), so the client asserts it for itself.
  await open(page, 68)
  await expect(page.getByTestId("ncaaf-team-disclosure")).toHaveAttribute(
    "data-posture",
    "market_blind_projection",
  )
  await open(page, 68, {
    transform: (pathname, body) =>
      pathname.startsWith("/ncaaf/teams/")
        ? { ...body, framing: { ...(body as any).framing, market_blind: false, best_alpha: 0.02 } }
        : body,
  })
  await expect(page.getByTestId("ncaaf-team-disclosure")).toHaveAttribute("data-posture", "changed")
})

test("nothing on the page ranks this team against another", async ({ page }) => {
  // ⛔ A RANK IS THE SHAPE A READER MOST EASILY CONVERTS INTO A PICK, and `best_alpha = 0`. There is
  // no "Nth in the country", no percentile and no ordering anywhere on this surface.
  await open(page, 68, { ncaafTeam: "populated" })
  const text = (await page.evaluate(() => document.body.innerText)).toLowerCase()
  for (const banned of ["rank", "ranked", "percentile", "nationally", "out of 136"]) {
    expect(text, `the page rendered "${banned}"`).not.toContain(banned)
  }
})
