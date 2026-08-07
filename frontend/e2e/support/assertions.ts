import { expect, type Page } from "@playwright/test"
import type { ApiMock } from "./api-mock"

/** The lock chip's own accessible name — the one thing every withheld value renders. */
export const LOCK_CHIP = '[aria-label="Locked — subscribe to unlock"]'

/**
 * `NaN` reached the Rankings/Projections columns in E9.56b because a locked row's model values are
 * ABSENT and the arithmetic on them silently produced `NaN` rather than throwing. Nothing in
 * `tsc` can see it (`number | undefined` arithmetic is legal TypeScript) and nothing in
 * `next build` renders a page, so a rendered-text scan is the only instrument that catches it.
 *
 * Word-bounded, so a player or team whose name merely contains the letters cannot false-positive.
 */
export async function expectNoNaN(page: Page) {
  const text = await page.evaluate(() => document.body.innerText)
  const hits = text.split("\n").filter((l) => /\bNaN\b/.test(l))
  expect(hits, `rendered text contains NaN:\n${hits.slice(0, 10).join("\n")}`).toEqual([])
}

/**
 * Every rendered row must carry a lock chip in the named MODEL-OUTPUT column.
 *
 * ⚠️ WHY PER-COLUMN AND NOT A COUNT. The first cut asserted `chips > 10` page-wide, and the red
 * proof killed it: breaking `numOrLock` so every withheld number renders an em-dash instead of a
 * chip left the OTHER chip sites (the range/confidence/basis cells, which branch on `p.locked`
 * directly) intact — comfortably over the threshold, suite green, defect shipped. A page-wide
 * count cannot tell "every withheld value is marked" from "some of them are".
 *
 * Pinned to one column that is unambiguously model output, so the assertion is 1-per-row and a
 * single cell falling through to "we have nothing for this player" fails it.
 */
export async function expectLockChipInEveryRow(page: Page, columnHeader: string) {
  const headers = await page
    .locator("table thead th")
    .evaluateAll((els) => els.map((e) => (e.textContent ?? "").trim()))
  const index = headers.findIndex((h) => h.toLowerCase() === columnHeader.toLowerCase())
  expect(index, `no "${columnHeader}" column — headers: ${headers.join(" | ")}`).toBeGreaterThan(-1)

  const withChip = await page
    .locator("table tbody tr")
    .evaluateAll(
      (rows, i) =>
        rows.filter((r) => r.children[i]?.querySelector('[aria-label="Locked — subscribe to unlock"]'))
          .length,
      index,
    )
  const total = await page.locator("table tbody tr").count()
  expect(total).toBeGreaterThan(0)
  expect(
    withChip,
    `${total - withChip} of ${total} rows render "${columnHeader}" without a lock chip`,
  ).toBe(total)
}

/**
 * The suite's own tripwire. Every conclusion below is "given the server sent X, the page renders
 * Y" — so a page that never GOT X is not evidence of anything. An un-mocked call is a harness
 * defect that would otherwise present as a passing test on an empty page, which is the exact
 * silent-empty shape E9.56b shipped.
 */
export function expectApiFullyMocked(mock: ApiMock) {
  expect(mock.unmatched, "the page requested an API path this harness has no fixture for").toEqual(
    [],
  )
  expect(mock.requested.length, "the page made no API calls at all").toBeGreaterThan(0)
}

/** A surface that threw during render can still look plausible; fail on an uncaught error. */
export function expectNoPageErrors(errors: string[]) {
  expect(errors, `uncaught page error(s):\n${errors.join("\n")}`).toEqual([])
}

/** Internal, navigable hrefs on the current page — `<Link>` and plain `<a href>` alike.
 *
 *  ⭐ Plain `<a href>` is the whole point. `next build` resolves a `<Link>`'s target and will
 *  complain about a broken one; it does NOT look inside an `<a href>` string, and the E9.56c
 *  `/pricing` CTA that killed the buy path was exactly that — including the one the SERVER
 *  supplies via `upgrade.ctaHref`, which no build step could ever see. */
export async function internalHrefs(page: Page): Promise<string[]> {
  const raw = await page
    .locator("a[href]")
    .evaluateAll((els) => els.map((e) => (e as HTMLAnchorElement).getAttribute("href") ?? ""))
  const out = new Set<string>()
  for (const href of raw) {
    if (!href.startsWith("/")) continue // external, mailto:, tel:, or a bare #fragment
    const path = href.split("#")[0]
    if (path) out.add(path)
  }
  return [...out].sort()
}
