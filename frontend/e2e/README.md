# Frontend E2E smoke suite (E9.63)

The frontend's only automated gates were `tsc`, `eslint` and `next build`. None of them renders a
page, so none of them can see a redirect, an empty state, a `NaN` column or a dead route. The whole
E9.56b→e cluster and all six E9.58 defects shipped past them, and every one was found by a human
opening a browser.

This suite is the automated form of the "verify in incognito" step every app story already lists
manually. It is deliberately **minimal** — the launch-critical funnel, nothing else. E9.64 (Fantasy)
and E9.65 (MLB betting) add specs to *this* harness; they do not rebuild it.

## Running it

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium   # first time only

npm run test:e2e          # build + run everything (the gate)
npm run test:e2e:run      # run against the existing build (fast iteration)
npm run e2e:red-proof     # break the app on purpose; assert the suite fails
npm run test:e2e:live     # the one non-hermetic check (see @live below)
npm run e2e:capture       # refresh the fixtures from the live API
```

`npm run test:e2e` produces a production build in `.next` using `e2e/e2e.env` — it **overwrites a
dev build**. Run `npm run build` (or just `npm run dev`) afterwards if that matters.

To run against something already serving — a Vercel preview, a hand-started `next start`:

```bash
E2E_BASE_URL=https://<preview>.vercel.app npx playwright test
```

⚠️ The API mock only fires for calls to `NEXT_PUBLIC_API_URL` as *that build* was compiled with, so
against a real deployment the fantasy specs talk to the real API. Useful as a live smoke; not the
hermetic gate.

## What is in here

| File | What it guards | The defect it is written from |
|---|---|---|
| `specs/locked-surfaces.spec.ts` | A logged-out visitor sees rows, lock chips on every withheld model value, a working Subscribe CTA, and no `NaN` | E9.56b (Rankings rendered blank for every free user), E9.56c (withheld values fell through to "—"; the CTA was a 404) |
| `specs/entitled-surfaces.spec.ts` | An unlocked payload renders real numbers, zero lock chips, and no upgrade ask | the other half of the same split — a page that renders chips unconditionally passes the file above and is broken for every subscriber |
| `specs/route-integrity.spec.ts` | **Every internal `href` in the rendered DOM resolves** | E9.56c — `/pricing` killed the entire buy path |
| `specs/signup-funnel.spec.ts` | Every signup entry point offers a working Google button; the nav carries a signup affordance on desktop **and mobile**; the click leaves for the configured Cognito host with correct PKCE params | E9.58 — the DNS-dead Hosted-UI host, and the logged-out mobile nav with no signup affordance (`hidden sm:flex`) |
| `specs/pricing.spec.ts` | A logged-out visitor sees the price; **the rendered price and currency FOLLOW the server**; a failed pricing read costs the price and not the funnel; the page's own CTA resolves; the payload carries no internal conversion count | E9.59 — until it, `/subscribe` could not show a price at all (the only pricing read required auth). The headline case is pre-emptive: a hardcoded price is invisible to every other gate |

`signup-funnel.spec.ts` is the only spec that also runs on a phone viewport, because one of the
defects it is written from was mobile-only and a desktop-only suite is structurally blind to it.

## Fixtures

`fixtures/api/` holds **verbatim captures of the live production API**, refreshed by
`capture-fixtures.mjs`. Every one is a public, anonymous GET — they are the bytes a real visitor's
browser receives.

⛔ **Do not hand-write a fixture.** That is the E9.56b lesson as a rule: the bugs this suite guards
all live in the gap between what we *assume* the payload looks like and what the server actually
sends, so a hand-written fixture encodes the assumption under test.

Two fixtures are not captures, and each says so in its own `__provenance__` / header.

`subscription-public-pricing.synthetic.json` (E9.59) is synthetic because
`GET /subscription/public-pricing` **does not exist in production yet** — it ships with E9.59 and
needs an operator API-Gateway route before it will answer anonymously, so there is nothing to
capture. The rule it would otherwise break ("a hand-written fixture encodes the assumption under
test") is closed from the other side instead: `betting_ml/tests/test_e9_59_public_pricing.py`
asserts the fixture's key set equals `PublicPricing.model_fields` **exactly**, so a backend shape
change fails the Python gate rather than drifting quietly away from this file. Its amount is
`1234` ($12.34) rather than the real $10/$20 on purpose — a realistic value would let a page that
hardcodes its price still render something plausible. **Replace it with a real capture once the
route is live** (add it to `capture-fixtures.mjs`; it is deliberately not listed there yet, because
a target that 404s makes `npm run e2e:capture` exit non-zero for no useful reason).

The other is `fantasy-nfl-projections-2026-entitled.synthetic.json`. There is no public unlocked form of the
current season to capture (every past season's `projections.json` 404s), and the entitled payload
*is* the paid product, which does not belong in the repo. `build-entitled-fixture.mjs` derives it
from the real locked capture, filling exactly the fields the server's own computed `lockedFields`
declares it stripped: **the envelope, the roster, the row order and the field set are real; the
numeric values are synthetic.** Its header states this at length. The genuinely-real
"unlocked payload renders real numbers" leg is carried in parallel by the track-record fixtures,
which are real, unlocked model output.

## The boundary — what a green run does NOT mean

This is a **smoke suite driving the real rendered funnel**, not a mock of Cognito, Stripe or
PostHog internals. Green here does **not** mean the paid path is verified. Specifically:

- **Who the server sends the locked payload to** is decided server-side by `_may_see_values`. This
  suite asserts the *render contract on either side* of that decision, never the decision itself.
- **Whether the Cognito Hosted-UI host actually exists** is not knowable from a hermetic run — and
  that was E9.58's worst defect. Every file was internally consistent, `tsc` was happy, the button
  rendered and the click fired; the host simply did not resolve. The suite asserts the app sends
  the user to *the host it was configured with*; whether that host is the right one is the `@live`
  check, and ultimately an operator check.
- **A real Google → Cognito → Stripe → `subscriber` round trip** is not exercised. It needs live
  credentials and a real card. It stays an operator incognito walkthrough.
- **Anything only reachable behind a login** is out of scope. The suite drives the logged-out
  funnel; there is no seeded subscriber session (tokens are held in memory by
  `amazon-cognito-identity-js`, so there is nothing to seed from the browser side).

### `@live`

One test reaches the real internet: it asks whether the production Cognito Hosted-UI host answers
at all. It is excluded from the default run and from CI. Run it with `npm run test:e2e:live`; it
needs the real host in `PROD_COGNITO_HOSTED_UI_DOMAIN` or in `frontend/.env.local`, and **skips
loudly** if neither has it — a check that could not run is never scored as a pass.

Verified two-sided 2026-08-06: it **passes** against the real host
(`us-east-1gg9zmbwqt.auth.us-east-1.amazoncognito.com`, so prod's signup host is healthy today) and
**fails** — `getaddrinfo ENOTFOUND` — against `credence-auth.auth.us-east-1.amazoncognito.com`, one
of the plausible-looking invented hosts that actually shipped. That is the E9.58 outage reproduced
and caught; it is also why the value must never be guessed from the brand name (the real prefix is
the pool id lowercased with the underscore removed).

## Red proof

`npm run e2e:red-proof` re-introduces seven real, previously-shipped defects one at a time,
rebuilds, and requires the named spec to fail. A green suite proves nothing on its own; a test that
*cannot* fail reads as coverage and stops anyone looking again.

Result as of 2026-08-06:

```
RED            blank-locked-board                     E9.56b — Rankings blank for every free user
NOT-OBSERVABLE nan-in-columns                         (declared — see below)
RED            withheld-renders-as-absent             E9.56c — a withheld value rendered as "—"
RED            dead-cta-route                         E9.56c — the CTA pointed at /pricing
RED            server-supplied-cta-trusted-verbatim   E9.56c — the API's ctaHref rendered verbatim
RED            no-signup-affordance                   E9.58 — logged-out nav had no way to sign up
RED            google-entry-missing                   E9.58 — a signup page with no Google button
```

The red proof also **found two real weaknesses in this suite** while it was being written, which is
the argument for keeping it:

1. The lock-chip assertion was originally a page-wide count (`chips > 10`). Breaking `numOrLock` so
   every withheld number renders "—" left the other chip sites intact, comfortably over the
   threshold, suite green. It is now asserted **per row, on one named model-output column** — a
   count cannot tell "every withheld value is marked" from "some of them are".
2. The Google-redirect test compared the URL's host against `process.env.… ?? url.host`, which
   passes for every possible value. `NEXT_PUBLIC_*` is inlined at build time and is not visible to
   the Playwright process, so it now reads `e2e/e2e.env` — the same file the build sourced.

### `nan-in-columns` is declared GREEN, and that is a finding

Both shipped NaN defects were **comparators** (`-Infinity - -Infinity`, `undefined - undefined`
when sorting a locked board). E9.56b's own commit message records why they were invisible:
*"Array.sort treats a NaN comparator as 0, so it happens to leave the server's order intact."*
Nothing wrong ever reaches the DOM, so **no rendered-text scan can see them** — they are a
unit-level concern and already guarded there.

The render-level form of the class is a missing null-guard in the shared `num()` formatter.
Measured with that guard removed, across all four page × payload combinations (projections locked,
rankings locked, projections entitled, track record): **zero rendered NaN**. On a locked board
`numOrLock` short-circuits to a lock chip before `num` is ever reached with a null, and every real
payload's numeric fields are non-null (checked: all seven track-record seasons carry no nulls in
the three columns they format).

So `expectNoNaN` is kept — it costs nothing and is a live tripwire for a *future* render-level NaN
— but it is **not presented as proven**. The red-proof script asserts this case stays green; if it
ever flips to red the class has become observable, and that note (and this section) are stale.

## Notes for whoever extends this (E9.64 / E9.65)

- **The API base must be same-origin.** `next.config.mjs` ships a CSP whose `connect-src` allows
  only `'self'` and the real API host. The first cut of this harness pointed
  `NEXT_PUBLIC_API_URL` at `http://api.e2e.invalid` so an un-intercepted call could not reach
  production — and the browser refused the fetch *before* Playwright's route handler fired, so
  every fantasy surface silently rendered its "not published yet" empty state while the harness
  reported it had mocked the API. `/__e2e-api` is same-origin (CSP-clean), collides with no route,
  and still cannot resolve anywhere but the local server.
- **Assert `expectApiFullyMocked`.** Every conclusion here is "given the server sent X, the page
  renders Y". A page that never got X is evidence of nothing, and an unmocked call presents as a
  passing test on an empty page.
- **Answer 204 on an intercepted top-level navigation, do not `abort()`.** An abort leaves the tab
  on `about:blank`, whose origin is `null` and whose `localStorage` access throws `SecurityError`.
- **Add a red-proof case with every new guard**, and prefer breaking a defect that actually
  shipped.
