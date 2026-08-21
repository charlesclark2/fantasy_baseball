import { expect, test } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import {
  GRADE_CIRCULARITY_NOTE,
  SHARE_CARD_CAPTION,
  buildShareSummary,
  type DraftGrade,
} from "@/lib/mock-draft"
import { parseShareSummary, sharePageUrl, summaryToSearchParams } from "@/lib/mock-draft-share"

/**
 * NF-DS — the post-draft SHARE surfaces: the URL-encoded summary, the public share page, and the
 * branded image route.
 *
 * These are DELIBERATELY split from `fantasy-mock-draft.spec.ts`'s in-app modal test (which pays
 * for a full playthrough, the same way that file already keeps its one full draft to a single
 * test). Everything here needs no draft at all — the summary is a pure function, and both share
 * routes render from nothing but their own query string — so it stays out of the slow file.
 */

// ── the derivation, with no browser ─────────────────────────────────────────────────────────────

test.describe("buildShareSummary", () => {
  function fakeGrade(overrides: Partial<DraftGrade> = {}): DraftGrade {
    return {
      teams: [],
      me: { slot: 4, isMe: true, starterPoints: 1842, startersFilled: 9, starterSlots: 9, roster: [] },
      myRank: 4,
      nTeams: 12,
      roomMedian: 1784,
      positions: [
        { pos: "QB", mine: 320, roomMedian: 300 },
        { pos: "RB", mine: 610, roomMedian: 576 },
        { pos: "WR", mine: 590, roomMedian: 600 },
        // A position nobody has drafted (a quick mock's K/DST) — must never be crowned strongest.
        { pos: "K", mine: 0, roomMedian: 0 },
      ],
      steals: [
        {
          player: { id: "p1", name: "Bijan Robinson", pos: "RB" } as DraftGrade["steals"][number]["player"],
          overallPick: 20,
          adp: 8,
          vsMarket: 12,
        },
      ],
      reaches: [],
      ...overrides,
    }
  }

  test("reads the rank, points and median straight off the grade — no recomputation", () => {
    const s = buildShareSummary(fakeGrade(), "Full PPR")
    expect(s.rank).toBe(4)
    expect(s.nTeams).toBe(12)
    expect(s.starterPoints).toBe(1842)
    expect(s.roomMedian).toBe(1784)
    expect(s.leagueLabel).toBe("Full PPR")
  })

  test("the strongest position excludes a position nobody in the room has drafted", () => {
    const s = buildShareSummary(fakeGrade(), "Full PPR")
    // RB (+34) beats QB (+20); K (0 vs 0) is excluded outright, not scored as a "+0" tie.
    expect(s.bestPosition).toEqual({ pos: "RB", delta: 34 })
  })

  test("a room with no position anyone has started yet has no strongest position", () => {
    const s = buildShareSummary(
      fakeGrade({ positions: [{ pos: "K", mine: 0, roomMedian: 0 }] }),
      "Full PPR",
    )
    expect(s.bestPosition).toBeNull()
  })

  test("steals carry through, capped at 3, in the grade's own order", () => {
    const steals = Array.from({ length: 5 }, (_, i) => ({
      player: { id: `p${i}`, name: `Player ${i}`, pos: "WR" } as DraftGrade["steals"][number]["player"],
      overallPick: 10 + i,
      adp: 1,
      vsMarket: 20 - i,
    }))
    const s = buildShareSummary(fakeGrade({ steals }), "Full PPR")
    expect(s.steals).toHaveLength(3)
    expect(s.steals.map((x) => x.value)).toEqual([20, 19, 18])
  })
})

// ── URL round-trip, with no browser ─────────────────────────────────────────────────────────────

test.describe("the share URL encoding", () => {
  test("a full summary round-trips through the query string exactly", () => {
    const summary = buildShareSummary(
      {
        teams: [],
        me: { slot: 1, isMe: true, starterPoints: 1900, startersFilled: 9, starterSlots: 9, roster: [] },
        myRank: 1,
        nTeams: 10,
        roomMedian: 1700,
        positions: [{ pos: "RB", mine: 700, roomMedian: 600 }],
        steals: [
          {
            player: { id: "a", name: "Puka Nacua", pos: "WR" } as DraftGrade["steals"][number]["player"],
            overallPick: 30,
            adp: 42,
            vsMarket: 12,
          },
        ],
        reaches: [],
      },
      "Half PPR",
    )
    const roundTripped = parseShareSummary(summaryToSearchParams(summary))
    expect(roundTripped).toEqual(summary)
  })

  test("a summary with no strongest position and no steals round-trips too", () => {
    const summary = {
      rank: 6,
      nTeams: 8,
      starterPoints: 1200,
      roomMedian: 1250,
      leagueLabel: "Superflex",
      bestPosition: null,
      steals: [],
    }
    expect(parseShareSummary(summaryToSearchParams(summary))).toEqual(summary)
  })

  test("a missing query string decodes to null, never a throw", () => {
    expect(parseShareSummary(new URLSearchParams())).toBeNull()
  })

  test("a partial/mangled query string (a crawler dropping params) decodes to null", () => {
    const p = new URLSearchParams()
    p.set("r", "4")
    // no "n", "pts", "med" or "lg" — an incomplete link, not a well-formed one.
    expect(parseShareSummary(p)).toBeNull()
  })

  test("the copied link is fully-qualified, not relative", () => {
    const summary = buildShareSummary(
      {
        teams: [],
        me: { slot: 1, isMe: true, starterPoints: 1000, startersFilled: 9, starterSlots: 9, roster: [] },
        myRank: 2,
        nTeams: 12,
        roomMedian: 950,
        positions: [],
        steals: [],
        reaches: [],
      },
      "Full PPR",
    )
    expect(sharePageUrl(summary)).toMatch(/^https:\/\/www\.credencesports\.com\/fantasy\/mock-draft\/share\?/)
  })
})

// ── the public share page ───────────────────────────────────────────────────────────────────────

const SHARE_QUERY =
  "r=4&n=12&pts=1842&med=1784&lg=Full+PPR&bp=RB&bpd=34&stn0=Bijan+Robinson&stp0=RB&stv0=12"

test.describe("the public share page", () => {
  test("renders a well-formed share link with NO sign-in — the whole point of it being public", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    // Deliberately no `signIn` — the assertion IS that none is needed. A redirect to /login here
    // would be the FantasyGuard-on-a-public-route regression this page exists to avoid (PM
    // decision: the share artifact is public even though the tool itself is paid). `mockApi` is
    // still armed to keep the run hermetic (Nav/Providers may probe the API/PostHog on mount
    // regardless of auth state) — it answers requests, it does not gate the page.
    await mockApi(page)
    await page.goto(`/fantasy/mock-draft/share?${SHARE_QUERY}`)

    expect(page.url(), "a public share link redirected somewhere — it should never gate").toContain(
      "/fantasy/mock-draft/share",
    )
    await expect(page.getByRole("heading", { name: /4th of 12 in a Full PPR mock draft/ })).toBeVisible()

    const img = page.locator('img[src^="/fantasy/mock-draft/share/image"]')
    await expect(img).toBeVisible()
    await expect.poll(async () => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)

    await expect(page.getByText(SHARE_CARD_CAPTION)).toBeVisible()
    await expect(page.getByText(GRADE_CIRCULARITY_NOTE, { exact: false })).toBeVisible()

    // The acquisition loop this whole story exists for: a visitor with no account can get straight
    // to the tool from here.
    const cta = page.getByRole("link", { name: "Draft your own room" })
    await expect(cta).toHaveAttribute("href", "/fantasy/mock-draft")

    const bodyText = await page.evaluate(() => document.body.innerText)
    expect(forbiddenPhrasesIn(bodyText), "the public share page makes a claim the denylist forbids").toEqual(
      [],
    )

    expect(errors).toEqual([])
  })

  test("a malformed/missing link still renders a generic, non-broken page", async ({ page }) => {
    const errors = collectPageErrors(page)
    await mockApi(page)
    await page.goto("/fantasy/mock-draft/share")
    await expect(page.getByRole("heading", { name: "NFL Fantasy Mock Draft" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Draft your own room" })).toBeVisible()
    expect(errors).toEqual([])
  })

  test("the share page ships the OG/Twitter tags a link preview reads", async ({ page }) => {
    await mockApi(page)
    await page.goto(`/fantasy/mock-draft/share?${SHARE_QUERY}`)
    const ogImage = await page.locator('meta[property="og:image"]').getAttribute("content")
    expect(ogImage).toBe(
      `https://www.credencesports.com/fantasy/mock-draft/share/image?${SHARE_QUERY}`,
    )
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute(
      "content",
      "summary_large_image",
    )
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", /4th of 12/)
  })
})

// ── the image route ──────────────────────────────────────────────────────────────────────────────

test.describe("the share image route", () => {
  // ⚠️ NF-C4 — assert the RENDERED bytes, not that the route file imports `ImageResponse`. A
  // satori-invalid JSX tree throws at REQUEST time, never at build time (confirmed live: `next
  // build` succeeds regardless — see the story's own runtime verification), so only an actual
  // request proves the card renders.
  test("a fully-populated summary renders a real PNG at the OG size", async ({ request }) => {
    const res = await request.get(`/fantasy/mock-draft/share/image?${SHARE_QUERY}`)
    expect(res.ok()).toBeTruthy()
    expect(res.headers()["content-type"]).toBe("image/png")
    const body = await res.body()
    // A real rendered card is tens of KB; a blank/broken frame would be a few hundred bytes.
    expect(body.length).toBeGreaterThan(5_000)
  })

  test("a missing query string renders the generic fallback card, never an error", async ({ request }) => {
    const res = await request.get("/fantasy/mock-draft/share/image")
    expect(res.ok()).toBeTruthy()
    expect(res.headers()["content-type"]).toBe("image/png")
    expect((await res.body()).length).toBeGreaterThan(1_000)
  })

  test("a summary with no strongest position and no steals still renders (the chip row is optional)", async ({
    request,
  }) => {
    const res = await request.get(
      "/fantasy/mock-draft/share/image?r=8&n=12&pts=1500&med=1550&lg=Half+PPR",
    )
    expect(res.ok()).toBeTruthy()
    expect(res.headers()["content-type"]).toBe("image/png")
  })
})
