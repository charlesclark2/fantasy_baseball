import { expect, test, type Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { API_PREFIX, collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors, internalHrefs } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { SCHEDULE_PLAYED_HEADING } from "@/lib/ncaaf-copy"

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

test("no ranking renders without the range that makes it honest", async ({ page }) => {
  // ⭐⭐ RE-ANCHORED, NOT RETIRED, and the reason is worth keeping because the original guard was
  // RIGHT FOR THE WRONG REASON. It banned every ranking outright, on the ground that "a rank is
  // the shape a reader most easily converts into a pick". That reasoning does not survive contact
  // with the numbers: a rating in POINTS is far closer to a wagerable quantity than an ordinal is,
  // and the page publishes the rating.
  //
  // The real hazard is PRECISION, and it is measurable. On the live 2026 week-1 board (138 teams,
  // every sd ≈ 7.3) the MEDIAN team's 80% rank range spans 77 of 138 places and 130 of 138 span
  // more than 40 — Boise State is 42nd on the point estimate and 18th–97th on its own spread. So a
  // bare rank is the most over-precise thing this page could print, and a rank WITH its range is
  // the single most interpretable thing on it. The guard therefore moves from "no rank" to "no
  // rank without its range", which is the claim the surface can actually defend (MH2.7 —
  // re-anchor onto the new implementation, never weaken or delete).
  //
  // ⏳ And the hazard EXPIRES: the width is a function of a posterior sd that shrinks as games are
  // played, so this clause protects a September reader and costs a November one nothing.
  await open(page, 68, { ncaafTeam: "populated" })

  // NON-VACUITY: this fixture genuinely renders a ranking, so the assertions below have something
  // to bite on. Without it the loop would pass on a page that had stopped ranking entirely.
  const fbs = page.getByTestId("ncaaf-standing-fbs")
  await expect(fbs).toBeVisible()

  for (const testId of ["ncaaf-standing-fbs", "ncaaf-standing-conference"]) {
    const el = page.getByTestId(testId)
    if ((await el.count()) === 0) continue
    await expect(
      el.getByTestId(`${testId}-range`),
      `${testId} rendered a rank with no range`,
    ).toBeVisible()
    const range = ((await el.getByTestId(`${testId}-range`).innerText()) ?? "").trim()
    expect(range.length, `${testId}'s range is empty`).toBeGreaterThan(0)
  }

  // ⛔ The half of the original guard that STILL BINDS: an ordinal is admissible, the language of
  // a recommendation is not.
  const text = (await page.evaluate(() => document.body.innerText)).toLowerCase()
  for (const banned of ["should back", "best bet", "value pick", "our pick", "edge"]) {
    expect(text, `the page rendered "${banned}"`).not.toContain(banned)
  }
})

test("a rank whose range is missing renders nothing at all", async ({ page }) => {
  // ⭐ THE DEGRADE DIRECTION IS THE WHOLE POINT. Handed a rank with no bounds, the tempting
  // fallback is to show the rank — which is degrading toward the half that LOOKS most
  // authoritative and is least defensible. The surface shows neither, and says so.
  // ⚠️ `mockApi` FIRST so the rest of the page's calls are still served, THEN the override — a bare
  // `page.route` on one path leaves every other request unmocked and the page never renders at all,
  // which would have made this clause fail for a reason unrelated to what it tests.
  await mockApi(page, { ncaafTeam: "populated" })
  // ⚠️ SCOPED TO THE API PREFIX. `**/ncaaf/teams/**` also matches the PAGE's own navigation URL, so
  // an unscoped glob fulfils the DOCUMENT request with JSON and the browser renders the payload as
  // text — a failure that looks exactly like "the section did not render".
  await page.route(`**${API_PREFIX}/ncaaf/teams/**`, async (route) => {
    const blob = JSON.parse(JSON.stringify(TEAM_POPULATED))
    blob.strength.standing_fbs = { ...blob.strength.standing_fbs, rank_lo: null, rank_hi: null }
    blob.strength.standing_conference = null
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(blob) })
  })
  await page.goto(path(68))
  await expect(page.getByTestId("ncaaf-team-standing")).toBeVisible()
  await expect(page.getByTestId("ncaaf-standing-fbs")).toHaveCount(0)
  // ...and the absence is NAMED rather than left as a blank heading (NF-C6b).
  await expect(page.getByTestId("ncaaf-team-standing-absent")).toBeVisible()
  // ⛔ Non-vacuity from the other side: the rank itself must not have leaked out anywhere.
  const text = await page.evaluate(() => document.body.innerText)
  expect(text).not.toContain(`${TEAM_POPULATED.strength.standing_fbs.rank}th of`)
})

test("a ranking states its population and its confidence, both from the payload", async ({ page }) => {
  await open(page, 68, { ncaafTeam: "populated" })
  const fbs = TEAM_POPULATED.strength.standing_fbs
  const el = page.getByTestId("ncaaf-standing-fbs")
  // The count is the SERVED `n_ranked` — the population that had a posterior, not a constant and
  // not the size of FBS.
  await expect(el).toContainText(`of ${fbs.n_ranked}`)
  // ⛔ "80%" is DERIVED from the served levels, so a later ladder change cannot silently relabel a
  // range it did not recompute.
  const pct = Math.round((fbs.interval_hi_level - fbs.interval_lo_level) * 100)
  await expect(el.getByTestId("ncaaf-standing-fbs-range")).toContainText(`${pct}%`)
})

test("the pre-season note never contradicts the schedule below it", async ({ page }) => {
  // ⭐⭐ A CROSS-BLOCK CONSISTENCY CLAUSE, and it exists because the page DID contradict itself in
  // production. The note is keyed on `games_in_window === 0` — a fact about what THIS POSTERIOR has
  // absorbed — but its first wording claimed "No games have been played yet", a fact about the
  // SEASON. Those come apart BY DESIGN: the P1.2 strength fit rolls forward weekly (06:00 Monday),
  // so from the first Saturday until the next Monday every team that has played carries a week-1
  // rating. On 2026-09-04 that put the sentence directly above a "Played" section showing North
  // Dakota State 1-0 with a 33-7 win.
  //
  // ⚠️ NO BLOCK ON THIS PAGE IS SAFE TO WORD IN ISOLATION. Four independently-sourced blocks are
  // stacked on one screen, and a reader reads them as one statement — so a claim that is true of
  // its own block can still be false ON THE PAGE. That is not something a per-block guard can see,
  // which is why this one spans two.
  await mockApi(page, { ncaafTeam: "populated" })
  await page.route(`**${API_PREFIX}/ncaaf/teams/**`, async (route) => {
    // The exact live shape: a posterior that has absorbed nothing, over a schedule that has games.
    const blob = JSON.parse(JSON.stringify(TEAM_POPULATED))
    blob.strength.current.games_in_window = 0
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(blob) })
  })
  await page.goto(path(68))

  // NON-VACUITY: both halves must actually be on screen, or this asserts nothing.
  const note = page.getByTestId("ncaaf-strength-preseason-note")
  await expect(note).toBeVisible()
  expect(TEAM_POPULATED.schedule.n_completed, "the fixture must have a played game").toBeGreaterThan(0)
  await expect(page.getByTestId("ncaaf-team-schedule")).toContainText(SCHEDULE_PLAYED_HEADING)

  // ⛔ The note may say the RATING has taken nothing in. It may NOT say the season has not started.
  const text = (await note.innerText()).toLowerCase()
  for (const claim of ["no games have been played", "nobody has played", "the season has not"]) {
    expect(text, `the note claims "${claim}" while the schedule below shows a played game`)
      .not.toContain(claim)
  }
})

test("the page says what the rating MEANS, not only what its unit is", async ({ page }) => {
  // The operator's actual complaint: "I have no clue as an end user how to interpret these
  // numbers." Naming the unit was not enough — what makes the scale usable is that the DIFFERENCE
  // between two ratings is the expected margin, which is the sentence this clause pins.
  await open(page, 68)
  await expect(page.getByTestId("ncaaf-strength-meaning")).toContainText("gap between two teams")
})

test("a deployed payload with no standings renders the named absence, not a blank", async ({ page }) => {
  // ⭐ RE-ANCHORED BY NCAAF-P3.3b, AND THE SELF-ANNOUNCING CLAUSE DID ITS JOB. This used to read
  // the absence off the CAPTURE and assert it with "the capture has acquired standings — re-check
  // this clause". The 2026-09-04 re-capture acquired them (68 now serves rank 42 of 138, range
  // 18–97), so that assertion fired exactly as designed and was retired BY RE-CAPTURING — never by
  // weakening it into something the new payload happens to satisfy.
  //
  // ⛔ THE BRANCH STAYS COVERED, because the state it describes is still reachable: `frontend/`
  // auto-deploys on main while the API Lambda ships only via a manual `deploy.sh` (NF-C0), so a
  // client WILL meet a standings-less payload during that skew. The pre-standings server state is
  // now SYNTHESIZED rather than captured — which is what `transform` exists for — and the fixture's
  // own values are asserted to be present first, so this cannot silently become a test of nothing.
  expect(TEAM_68.strength.standing_fbs, "the capture must CARRY standings for the strip to mean anything").not.toBeNull()
  const { errors } = await open(page, 68, {
    transform: (pathname, body) =>
      pathname.startsWith("/ncaaf/teams")
        ? { ...body, strength: { ...body.strength, standing_fbs: null, standing_conference: null } }
        : body,
  })
  await expect(page.getByTestId("ncaaf-team-standing")).toBeVisible()
  await expect(page.getByTestId("ncaaf-team-standing-absent")).toBeVisible()
  expectNoPageErrors(errors)
})

test("the re-captured payload renders its real standing, with the range attached", async ({ page }) => {
  // The other side of the re-capture: the AVAILABLE branch is now reachable from production bytes
  // for the first time, so it is asserted against the capture's OWN values rather than a typed
  // expectation (the file-header rule). This is what retires the clause above by REPLACEMENT.
  await open(page, 68)
  await expect(page.getByTestId("ncaaf-standing-fbs")).toBeVisible()
  await expect(page.getByTestId("ncaaf-team-standing-absent")).toHaveCount(0)
  const fbs = page.getByTestId("ncaaf-standing-fbs")
  await expect(fbs).toContainText(String(TEAM_68.strength.standing_fbs.rank_lo))
  await expect(fbs).toContainText(String(TEAM_68.strength.standing_fbs.rank_hi))
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// NCAAF-P3.3b — WHEN these ratings last took in games
// ══════════════════════════════════════════════════════════════════════════════════════════════
//
// ⭐ WHAT THESE CLAUSES ARE FOR. P3.3 measured a reader misread that no number on the page is wrong
// about: the rating, band and both ranks move only when P1.2 is re-fit, so a Saturday win can sit
// beside a rating that predates it. The stamp is the missing fact, and BOTH its halves are read off
// the payload — so the two failure modes worth guarding are (a) a half that stops rendering and
// (b) a half that renders a date the payload never carried, which is far worse because it looks
// authoritative. Every clause below reads the FIXTURE'S OWN values; none types a date.

/** The date part of an ISO instant, computed the way the surface computes it. Kept here rather
 *  than importing the app's helper on purpose: a spec that called `isoDateOf` would be asserting
 *  the function against itself (the NF-C0e "a test that reads a value back under the key the code
 *  wrote" shape). Two independent derivations that must agree is the point. */
const isoDay = (v: string) => v.slice(0, 10)

test("the stamp states BOTH absences on a pre-deploy payload, and invents no date", async ({ page }) => {
  // ⭐ THE CAPTURES ARE THE PRE-DEPLOY SHAPE, AND THAT IS REAL PRODUCTION RIGHT NOW: they were taken
  // from the live API before the Phase-A field shipped, so neither stamp field exists on them. The
  // API Lambda deploys by hand while `frontend/` auto-deploys (NF-C0), so this is not a contrived
  // state — it is the state every reader is in until `deploy.sh` runs.
  expect(TEAM_68.strength.ratings_as_of ?? null, "the capture has acquired a vintage — re-anchor this clause onto a transform-stripped payload, do not weaken it").toBeNull()
  const { errors } = await open(page, 68)
  await expect(page.getByTestId("ncaaf-ratings-stamp")).toBeVisible()
  await expect(page.getByTestId("ncaaf-ratings-as-of-absent")).toBeVisible()
  await expect(page.getByTestId("ncaaf-ratings-next-update-absent")).toBeVisible()
  // ⛔ THE ANTI-FABRICATION HALF, and it is the one that matters. A stamp that fell back to "now",
  // or to `generated_at` (the HOURLY serving write — the very number that makes a five-week-old
  // rating look fresh), would render a plausible date over an unread artifact. Nothing
  // date-shaped may appear in the stamp when the payload carried no instant.
  const stamp = await page.getByTestId("ncaaf-ratings-stamp").innerText()
  expect(stamp, "the stamp printed a date the payload does not carry").not.toMatch(/\d{4}-\d{2}-\d{2}/)
  expect(stamp).not.toContain(isoDay(TEAM_68.generated_at))
  expectNoPageErrors(errors)
})

test("the stamp renders on BOTH the played and the unplayed capture", async ({ page }) => {
  // The played/unplayed contrast the fixture pair exists for: 2449 carries a completed game (and a
  // 1-0 record) while 68 is wholly upcoming. The stamp is a fact about OUR cadence, not about the
  // team, so it must render identically in both — a stamp that quietly disappeared on the state a
  // reader is most likely to misread would be worse than none.
  expect(TEAM_2449.schedule.n_completed).toBeGreaterThan(0)
  expect(TEAM_68.schedule.n_completed).toBe(0)
  for (const id of [68, 2449]) {
    await open(page, id)
    await expect(page.getByTestId("ncaaf-ratings-stamp")).toBeVisible()
    await expect(page.getByTestId("ncaaf-ratings-vintage-hint")).toBeVisible()
  }
})

test("a real vintage PRINTS, and it is the payload's own date", async ({ page }) => {
  // ⭐ THE PRESENT ARM, reached through the generated fixture — the shape prod cannot serve until
  // the Phase-A deploy lands, exactly as the efficiency/splits AVAILABLE branch is reached. The
  // expected text is derived from the fixture, so a re-capture moves it with the payload.
  const asOf = TEAM_POPULATED.strength.ratings_as_of
  expect(asOf, "the populated fixture must carry a vintage — rebuild it").toBeTruthy()
  const { errors } = await open(page, 68, { ncaafTeam: "populated" })
  await expect(page.getByTestId("ncaaf-ratings-as-of")).toContainText(isoDay(asOf))
  await expect(page.getByTestId("ncaaf-ratings-as-of-absent")).toHaveCount(0)
  // ⛔ AND IT IS NOT `generated_at`. The two are different instants by design (the artifact's Delta
  // commit vs this write's clock) and a stamp that read the wrong one would look completely normal.
  expect(isoDay(asOf)).not.toBe(isoDay(TEAM_POPULATED.generated_at))
  await expect(page.getByTestId("ncaaf-ratings-stamp")).not.toContainText(isoDay(TEAM_POPULATED.generated_at))
  expectNoPageErrors(errors)
})

test("production's real shape today — a vintage, and no scheduled next update", async ({ page }) => {
  // ⛔ THE ASYMMETRY IS THE MEASUREMENT, not a gap in the fixture. Nothing in `pipeline/` re-fits
  // P1.2 — it is an operator step, and the lake agrees (the ratings table last committed
  // 2026-08-18 while the roll-forward's own tables committed 2026-08-31, i.e. it fired and moved
  // nothing here). So the surface must say so rather than name a schedule that would not deliver.
  expect(TEAM_POPULATED.strength.ratings_next_update ?? null).toBeNull()
  await open(page, 68, { ncaafTeam: "populated" })
  await expect(page.getByTestId("ncaaf-ratings-next-update-absent")).toBeVisible()
  await expect(page.getByTestId("ncaaf-ratings-next-update")).toHaveCount(0)
})

test("a scheduled next update PRINTS its date rather than the absence", async ({ page }) => {
  // ⭐ THE FORWARD BRANCH, EXERCISED SO IT IS NOT DEAD CODE. `RATINGS_REFRESH_SCHEDULES` is empty
  // today, so no fixture can reach this arm — and a render branch nothing ever reaches is a
  // declaration that outran its production (NF-C0e). The day a re-fit is scheduled, the surface
  // must already be able to say so; this proves it can, without waiting for that decision.
  const next = "2099-01-04T14:00:00+00:00"
  const { errors } = await open(page, 68, {
    transform: (pathname, body) =>
      pathname.startsWith("/ncaaf/teams")
        ? { ...body, strength: { ...body.strength, ratings_next_update: next } }
        : body,
  })
  await expect(page.getByTestId("ncaaf-ratings-next-update")).toContainText(isoDay(next))
  await expect(page.getByTestId("ncaaf-ratings-next-update-absent")).toHaveCount(0)
  expectNoPageErrors(errors)
})

test("the stamp promises only a rewrite, never that the rating will move", async ({ page }) => {
  // ⛔ THE NO-OVERCLAIM CLAUSE. A re-fit over a bye week produces the same number, so a stamp that
  // said the ratings WILL change would be wrong through no fault of the data — and this page's
  // whole licence to publish is that it claims only what it has measured (best_alpha = 0).
  await open(page, 68, { ncaafTeam: "populated" })
  const text = (await page.getByTestId("ncaaf-ratings-vintage").innerText()).toLowerCase()
  expect(forbiddenPhrasesIn(text), "the stamp reached for a claim phrase").toEqual([])
  for (const claim of ["will change", "will move", "will update to", "improve", "expect the rating"]) {
    expect(text, `the stamp promises "${claim}" — a re-fit over a bye week moves nothing`)
      .not.toContain(claim)
  }
})
