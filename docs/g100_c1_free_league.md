# G100-C1 — one free personalized league, and the activation gate

**Date:** 2026-08-08 · **Branch:** `g100-c1` · **Context:** GROWTH-100 §C1 (P0, sequence 5).
`best_alpha = 0`.

The one-line version: **a free account now gets one league of its own, and a screen that shows what
changed because of it.**

---

## 1. ⭐ The renderer inventory — the first deliverable

The freemium build's own lesson is that a tier is enforced by **which component renders**, not by
which endpoint answers: #681 gated one of three surfaces that print the paid scorings and looked
complete. So before anything was built, every surface that shows personalized-vs-generic was
enumerated against the running code.

| Surface | Renders personalization by | Gate after G100-C1 |
|---|---|---|
| **`/fantasy/my-league`** ⭐ NEW | The whole page — the delta, then the league board | `FantasyLeagueGuard`; `/nfl/my-teams` quota-gated |
| `/fantasy/league-settings` | Editing the config the board is scored from | `FantasyLeagueGuard` (was `FantasyBetaGuard`) |
| `/fantasy/import` | Producing that config from a platform | `FantasyLeagueGuard` (was `FantasyBetaGuard`) |
| `/fantasy/rankings` | `FormatSelector`'s "Your leagues" group + `useResolvedBoard` | unchanged — free surface, the group is empty without a league |
| `/fantasy/league-board` | Same selector, same resolver | unchanged (`FantasyGuard`) |
| `/fantasy/draft` | Same selector; the optimizer itself is `DECISION_SUPPORT` | unchanged (`FantasyGuard`) — **paid, by product decision** |
| `/fantasy/my-teams` | Every saved league, scored | unchanged (`FantasyGuard`) — **multiple leagues is the paid line** |
| `/fantasy/player/[id]` | The `(your league)` tile, when a league is selected | unchanged — already correct for a free reader |

Two entries carry the whole free/paid line and are worth stating plainly, because both are
`Capability.PERSONALIZATION` surfaces that stay **paid**:

- **My Teams** is *several* leagues at once. G100-E0 puts "multiple leagues" on the paid side, so a
  free account gets My League (one) and not My Teams (many).
- **The draft optimizer** is paid for a product reason rather than a data one — its inputs are free.
  It is the "helps you decide" half.

⚠️ The three browse surfaces (`rankings`, `league-board`, `draft`) reach saved leagues through
`useSavedLeagues` → `FormatSelector`. That hook's `enabled` predicate moved from *entitlement* to
*identity*, so a free account's league appears in "Your leagues" there too. That is correct and
deliberate: a league the user configured should be selectable wherever formats are, and the board it
produces is the same one My League shows.

---

## 2. What actually changed

**One number.** `FREE_PERSONALIZED_LEAGUE_QUOTA` 0 → 1. The freemium build left it as a real, read
count precisely so this story would not have to replace a predicate — and it worked: no gate was
rewritten, and `Capability.PERSONALIZATION` is still PAID. See `docs/freemium_tier.md` §1 for the
three-predicate table that keeps "is it in your tier?" and "how many may you keep?" apart.

**The gate is the quota.** `require_personalized_league_access` asks `quota > 0`, resolving identity
first — so an anonymous caller gets **401 ("sign in")**, not 403 ("pay"). A league is stored against
a Cognito `sub`; sending that visitor to a paywall asks them to buy something free.

**The cap is enforced twice**, because one check cannot see both cases:

- `POST /fantasy/leagues` → 409 on the second league, quoting the **caller's** quota.
- `GET /fantasy/nfl/my-teams` → serves at most `quota`, which is the only place a **lapsed
  subscriber** is visible. They make no further create call, so a create-only cap would keep serving
  them five personalized boards forever — the paid tier, retained by having once paid for it.

`/fantasy/leagues` stays **uncapped**: those are the user's own configs, and capping the management
list would strand them above a quota they could never get back under.

---

## 3. ⭐ The activation screen

`/fantasy/my-league` leads with the delta and puts the board underneath it. A "vs generic" column on
the existing boards is genuinely useful for a returning user and is **carded as a fast-follow**; it
is the wrong shape for activation, for three reasons that each shaped the file:

1. Someone who has just configured a league is holding one question. A column answers it as a
   footnote on a page about something else.
2. `custom_board_viewed` gets **one fire point**. Scattered across two browse surfaces, "when did
   this user activate?" stops having an answer — and that event is the funnel's denominator.
3. It is the **smallest gating surface**. Every extra renderer of a paid capability is another place
   to gate consistently.

**The delta is surfaced, not asserted.** Risers and fallers, then the per-position replacement-level
shift that *explains* them: "your league starts two tight ends, so TE replacement level sits 31
points lower" is arithmetic on settings the user typed in, not an insight we are claiming.

⛔ **And it says nothing about the market.** A movement column means "versus ADP" everywhere else in
this category, so a reader imports that meaning unless the page refuses it explicitly —
`LEAGUE_DELTA_DEFINITION` renders beside the block and on the column itself. The comparison is
between **two of our own boards**. `best_alpha = 0`.

---

## 4. Telemetry

The activation definition is `account_created AND league_config_completed AND custom_board_viewed`.
Event names are a contract with G100-D0's dashboard and are drawn from its vocabulary:

| Event | Fires | Why there |
|---|---|---|
| `user_signup_completed` | (pre-existing) | `account_created` |
| `league_config_completed` | on a **create**, from both the manual editor and import | activation is about *having* a league, not which door it came through — a funnel counting only imports would read the manual floor's users as never activating |
| `league_import_started` / `..._completed` | on choosing a league / on saving it | G100-D0's platform-specific pair; the gap between them **is** the import funnel |
| `custom_board_viewed` | when the personalized board **renders** | ⭐ not on mount — see below |

⭐ **`custom_board_viewed` fires on the board rendering, once per mount.** Firing on mount would
count a visitor who saw an empty state as activated, inflating the exact denominator paid conversion
is measured against — and an inflated activation rate reads as a *conversion* problem, sending the
next story at the wrong thing. Both halves are asserted (it fires; it does **not** fire on the empty
state).

---

## 5. ⚠️ A harness finding worth keeping

**posthog-js drops every capture under Playwright, silently.** Its bot filter has two clauses that
both catch an automated browser — `navigator.webdriver`, and `HeadlessChrome` in
`navigator.userAgentData.brands` — and **both** must be defeated; clearing either alone changes
nothing. The SDK still initialises, POSTs `/flags/` and loads its remote config, so the ingest log is
simply empty, which is indistinguishable from "the app never called `capture()`".

⇒ **every analytics assertion in this suite was vacuous before this story**, including — especially —
any assertion that an event did *not* fire. Both clauses are now defeated in `captureAnalytics`, and
two other plausible causes were measured and ruled out so nobody re-chases them (the shipped CSP
already permits the same-origin `/ingest` path; allowing `blob:` workers changed nothing).

Also fixed: **the per-IP rate limiter is process-global and stateful**, so one suite's requests
deplete the bucket and the next file starts receiving 429s — surfacing as payload-shape assertion
failures rather than as throttling. Adding this story's suite ahead of the freemium one turned 17 of
its tests red. Both fixtures reset it now.

---

## 6. Verification

| Layer | Instrument | Result |
|---|---|---|
| The quota, the cap, the gate, the caches — end to end through the real ASGI app | `betting_ml/tests/test_g100_c1_free_league.py` | **31 pass** |
| Every Python guard is falsifiable | `uv run python betting_ml/tests/g100_c1_red_proof.py` | **20/20 RED** |
| The freemium boundary, re-pointed at the widened gate | `betting_ml/tests/test_freemium_tier.py` | **114 pass** (with `test_g100_c1_free_league.py`) |
| …and still falsifiable | `betting_ml/tests/freemium_tier_red_proof.py` | **54/54 RED** |
| Rendered browser behaviour | `frontend/e2e/specs/free-league.spec.ts` | **8 pass** |
| The whole frontend suite | `npx playwright test` | **131 pass** (was 123) |
| Every new e2e clause is falsifiable | `frontend/e2e/red-proof.mjs` (8 G100-C1 cases) | **6 RED, 2 declared not-observable** |
| Python fast gate / slow gate | `pytest -m "not slow"` / `-m "slow and not research"` | **6590 pass** / **26 pass** |

**The red-proof harness earned its keep twice.**

- The delta's sign test was a **tautology**: list membership and the arrow both derive from
  `ovrDelta`, so inverting the subtraction swapped both consistently and the test passed on the
  exact defect it existed to catch. Fixed by rendering the overall ranks themselves (`#128 → #34`)
  and asserting on those — board-derived, so the sign cannot produce them. It is also the more
  concrete thing to show a drafter.
- A quota-ordering fixture used timestamps whose `created_at` and `updated_at` sorted **identically**,
  so deleting the clause it named changed nothing (the NF-D17 shape).

**Two cases are declared GREEN, and that is a finding rather than a gap** — both are defence in
depth, where no single-line break is observable:

- once-per-mount is delivered by the `fired` ref **and** by an effect dependency list a tab click
  does not disturb;
- the logged-out nav protection is delivered by `freeSignedIn`'s `isSignedIn` half **and** by
  `showSubNav`, which hides the whole surface menu pre-login.

### What is NOT proven here

- **The API Gateway authorizer.** These routes are authenticated, so they inherit the default
  Cognito authorizer and need **no** gateway change (NF3.2 in reverse — adding an
  `--authorization-type NONE` route would un-gate the saved-league surface). A test reads the route
  inventory to keep that a checked claim rather than a comment.
- **The live `deploy.sh`.** The quota, the gate and the cap are all **backend** — merging to `main`
  does not ship them.
- **That the activation event reaches the real PostHog project.** The e2e proves it leaves the page
  under the right name with the right dimensions; the dashboard end is an operator check.
