import { expect, test } from "@playwright/test"

/**
 * NCAAF-P3.2 — @live: does the DEPLOYED API still send what this surface reads?
 *
 *   E2E_LIVE=1 npx playwright test --grep @live
 *
 * ⛔ EXCLUDED FROM THE HERMETIC GATE by the `@live` tag (`playwright.config.ts` `grepInvert`). It
 * reaches the real internet, so it is never part of CI.
 *
 * ══ WHY IT EXISTS ═════════════════════════════════════════════════════════════════════════════
 *
 * NF-C0: the API Lambda has NO CD. It ships only via a manual `infrastructure/lambda/deploy.sh`
 * while `frontend/` auto-deploys on merge to `main` — so the two halves of this feature deploy
 * INDEPENDENTLY and there is always a skew window in both directions. Every other clause in this
 * suite is "given the server sends X, the page renders Y", and a captured fixture is X frozen at
 * the moment of capture. Nothing else in the repo asks whether the SERVER still sends X.
 *
 * ⭐ IT ASSERTS THE FIELDS THE CLIENT READS, NOT THE WHOLE SCHEMA. `test_ncaaf_serving_contract.py`
 * owns the schema; duplicating it here would be a second copy free to drift (E9.61). What this
 * owns is the narrower, client-side question the backend suite cannot answer: of everything the
 * contract declares, which fields does THIS surface actually depend on, and are they still there
 * and still populated? A field the contract declares but the server never fills would pass every
 * backend guard and render an em-dash on every card.
 *
 * ⚠️ IT READS THE MANIFEST FOR ITS OWN GAME DAY rather than hardcoding one. The slate key IS the
 * kickoff day — there is no week parameter, because CFBD restarts `week` at 1 in the postseason —
 * so a hardcoded date is a test that expires. A season with nothing published is reported as a
 * SKIP with a reason, never as a pass: "we could not check" and "we checked and it is fine" are
 * different facts (NF1.7 (a)).
 */

const API = process.env.NCAAF_LIVE_API_URL ?? "https://api.credencesports.com"

/**
 * A CACHE-BUSTED URL, and it is load-bearing rather than tidy.
 *
 * ⭐ MEASURED 2026-09-05: every `/ncaaf/*` route answers
 * `cache-control: public, s-maxage=900, stale-while-revalidate=3600` (the G100-D1 public cache
 * rule — the single biggest lever on the cost of a Saturday, so it is not going away). A shared
 * cache therefore serves a response up to 15 minutes old, and up to an hour older while it
 * revalidates behind the scenes.
 *
 * ⛔ THAT MAKES A PLAIN READ UNABLE TO ANSWER THIS SPEC'S OWN QUESTION. "The deployed API no
 * longer sends X" and "the cache has not turned over since the deploy" produce a byte-identical
 * response, and on 2026-09-05 exactly that read as a failed deploy: a field was reported missing,
 * the deploy was blamed, and the Lambda turned out to be fine — the diagnosis needed a direct S3
 * read of the served blob to isolate. A check whose failure state is indistinguishable from its
 * healthy state has not verified anything (G100-D1's own lesson, arriving through the harness).
 *
 * ⚠️ A unique param per call, NOT a fixed one: a fixed `?cb=1` is itself cacheable and would go
 * stale the same way, one indirection later.
 */
const bust = (path: string) => {
  const sep = path.includes("?") ? "&" : "?"
  return `${API}${path}${sep}_cb=${Date.now()}-${Math.random().toString(36).slice(2)}`
}

test.describe("@live", () => {
  test("the deployed NCAAF API still serves what the games surface reads", async ({ request }) => {
    const manifestRes = await request.get(bust("/ncaaf/manifest"))
    // A 401 here means the API-Gateway authorizer is back in front of the route (NF3.2) — the
    // failure mode that is invisible in the FastAPI source, because the route is genuinely public
    // in code and refused before the Lambda is ever invoked.
    expect(
      manifestRes.status(),
      `GET /ncaaf/manifest → ${manifestRes.status()}. 401 = the API-Gateway authorizer is in ` +
        `front of this route again; 500 = the Lambda has not been deploy.sh'd.`,
    ).toBe(200)

    const manifest = await manifestRes.json()
    expect(manifest.sport).toBe("ncaaf")
    expect(typeof manifest.current_game_day).toBe("string")
    expect(Array.isArray(manifest.game_days)).toBe(true)
    // The honest-frame flags are MACHINE-READABLE for a reason: a surface branches on them rather
    // than trusting a rendered sentence, which is what makes the CLV null enforceable downstream.
    expect(manifest.framing.best_alpha).toBe(0)
    expect(manifest.framing.market_blind).toBe(true)
    expect(typeof manifest.framing.disclosure).toBe("string")
    expect(manifest.framing.disclosure.length).toBeGreaterThan(80)

    test.skip(
      manifest.game_days.length === 0,
      "the live season has no published game day — nothing to check, and that is not a pass",
    )

    const day = manifest.game_days[0].game_day
    const slateRes = await request.get(bust(`/ncaaf/games?game_day=${day}`))
    expect(slateRes.status(), `GET /ncaaf/games?game_day=${day}`).toBe(200)
    const slate = await slateRes.json()
    expect(slate.games.length).toBeGreaterThan(0)

    for (const g of slate.games) {
      const where = `game ${g.game_id}`
      // Identity — the card's header.
      expect(typeof g.game_id, where).toBe("number")
      expect(typeof g.game_day, where).toBe("string")
      // The headline. BOTH sides, because the client never re-derives one from the other.
      expect(g.win_probability, where).toHaveProperty("home")
      expect(g.win_probability, where).toHaveProperty("away")
      // The signature viz's inputs. `quantile_levels`/`quantiles` are PARALLEL ARRAYS and the
      // curve is only drawable if they stay the same length.
      for (const key of ["margin", "total"]) {
        const d = g[key]
        expect(Array.isArray(d.quantile_levels), `${where}.${key}`).toBe(true)
        expect(d.quantiles.length, `${where}.${key} parallel arrays`).toBe(d.quantile_levels.length)
        expect(d, `${where}.${key}`).toHaveProperty("interval_lo")
        expect(d, `${where}.${key}`).toHaveProperty("interval_lo_level")
      }
      // The market block is ALWAYS present, with a machine-readable status — a bare null would
      // leave the surface unable to say WHICH null it is.
      expect(["available", "unavailable"], where).toContain(g.market.status)
      if (g.market.status === "unavailable") {
        expect(typeof g.market.reason, `${where} market.reason`).toBe("string")
      }
      // ⛔ AND NOTHING THAT READS AS A PICK. The schema guard refuses such a FIELD NAME server-side;
      // this is the same question asked of the bytes actually on the wire.
      const flat = JSON.stringify(g).toLowerCase()
      for (const token of ["\"pick", "\"edge", "\"best_side", "\"value_side", "\"recommend"]) {
        expect(flat.includes(token), `${where} carries a ${token} field`).toBe(false)
      }
    }
  })

  test("the deployed NCAAF API still serves what the TEAM page reads", async ({ request }) => {
    // ⭐ ADDED AFTER THE 2026-09-05 DEPLOY (NCAAF-P3.3b follow-up), and it is the clause that would
    // have made that morning a one-liner. The team page gained two fields the client renders, and
    // this suite covered only the games surface — so "did the contract reach production?" had no
    // automated answer and was settled by hand, wrongly at first.
    //
    // ⚠️ THE FAILURE MODE IT WATCHES IS E9.41: `NcaafTeamStrength` declares these, and a Lambda
    // built before that declaration STRIPS them on serialize. The store is right the whole time and
    // the page renders a stated absence — no error anywhere, and nothing else in the repo asks.
    const res = await request.get(bust("/ncaaf/teams/68"))
    expect(
      res.status(),
      `GET /ncaaf/teams/68 → ${res.status()}. 401 = the API-Gateway authorizer is in front of this ` +
        `route again (NF3.2); 404 = nothing published for the clock-derived season.`,
    ).toBe(200)
    const team = await res.json()
    const s = team.strength

    // The stamp's two halves. Both KEYS must exist — their absence is the deploy-skew signature —
    // and each value must be an ISO instant or null, never a fabricated or malformed string.
    for (const key of ["ratings_as_of", "ratings_next_update"]) {
      expect(s, `strength.${key} is missing — the Lambda predates the P3.3b contract, so it is ` +
        `STRIPPING a field the store carries (E9.41). Re-run infrastructure/lambda/deploy.sh from ` +
        `a checkout at origin/main, then confirm GET /health reports that SHA.`).toHaveProperty(key)
      const v = s[key]
      if (v !== null) {
        expect(typeof v, `strength.${key}`).toBe("string")
        expect(Number.isNaN(Date.parse(v)), `strength.${key} = ${v} is not a parseable instant`)
          .toBe(false)
      }
    }
    // ⛔ `ratings_as_of` is asserted NON-NULL, `ratings_next_update` deliberately is NOT. Null there
    // is the MEASURED state (no schedule rewrites the ratings — the P1.2 re-fit is an operator
    // step), so requiring a value would make this clause fail on a correct payload; whereas a null
    // vintage means the box could not read the ratings artifact, which IS worth failing on.
    expect(s.ratings_as_of, "the served ratings carry no vintage — the box writer's lake read " +
      "failed, or the serving write has not run since the P3.3b deploy").not.toBeNull()
    // And it must not have quietly become the write clock: they are different instants by design,
    // and reading the wrong one would look completely normal (P3.3b).
    expect(String(s.ratings_as_of).slice(0, 10)).not.toBe(String(team.generated_at).slice(0, 10))
  })

  test("GET /health reports WHICH BUILD is answering", async ({ request }) => {
    // The affordance that turns "did deploy.sh take?" into one request. `/health` is deliberately
    // NOT in `_PUBLIC_CACHE_RULES`, so unlike every `/ncaaf/*` route it cannot be served stale.
    const res = await request.get(bust("/health"))
    expect(res.status(), "GET /health").toBe(200)
    const body = await res.json()
    expect(body.status).toBe("ok")
    expect(body, "no build marker — the deployed Lambda predates the P3.3b follow-up")
      .toHaveProperty("build")
    expect(body.build.packaged, "the deployed Lambda reports itself UNPACKAGED, which means it was " +
      "not built by deploy.sh — its `sha` cannot be trusted").toBe(true)
    expect(String(body.build.sha)).toMatch(/^[0-9a-f]{40}(\+dirty)?$/)
    expect(body.build.built_at, "a packaged build must carry its build instant").not.toBeNull()
  })
})
