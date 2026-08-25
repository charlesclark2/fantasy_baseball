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

test.describe("@live", () => {
  test("the deployed NCAAF API still serves what the games surface reads", async ({ request }) => {
    const manifestRes = await request.get(`${API}/ncaaf/manifest`)
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
    const slateRes = await request.get(`${API}/ncaaf/games?game_day=${day}`)
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
})
