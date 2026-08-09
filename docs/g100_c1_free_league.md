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
| Rendered browser behaviour | `frontend/e2e/specs/free-league.spec.ts` | **10 pass** |
| The whole frontend suite | `npx playwright test` | **133 pass** (was 123) |
| Every new e2e clause is falsifiable | `frontend/e2e/red-proof.mjs` (10 G100-C1 cases) | **8 RED, 2 declared not-observable** |
| Python fast gate / slow gate | `pytest -m "not slow"` / `-m "slow and not research"` | **6590 pass** / **26 pass** |

**The red-proof harness earned its keep three times, and a fourth defect came out of re-reading the
component rather than the tests.**

- The delta's sign test was a **tautology**: list membership and the arrow both derive from
  `ovrDelta`, so inverting the subtraction swapped both consistently and the test passed on the
  exact defect it existed to catch. Fixed by rendering the overall ranks themselves (`#128 → #34`)
  and asserting on those — board-derived, so the sign cannot produce them. It is also the more
  concrete thing to show a drafter. ⚠️ Two intermediate attempts failed for a reason worth
  recording: aggregate position-rank and aggregate VOR movement are both unusable here, because the
  two e2e board fixtures are **independently synthesised** (values seeded per player id by different
  formulas), so any cross-board statistic over them is noise.
- A quota-ordering fixture used timestamps whose `created_at` and `updated_at` sorted **identically**,
  so deleting the clause it named changed nothing (the NF-D17 shape).
- A negative assertion **raced**: `toHaveCount(0)` passes the instant it is evaluated if the element
  has not rendered *yet*, so leading with it tested the page mid-load rather than the settled page.
  Ordering the positive wait first is what makes it a statement about the outcome.
- ⭐ And the defect the harness could not have found, because no test existed to break:
  `useMyTeams` collapses "not loaded yet" and "could not load" into a single `teams: null`, so
  keying the empty state on the scored board told a user who had **configured a league last week**
  to go and set one up — whenever the projections read was slow, 404'd before the first export, or
  failed. Three states now, not two, and the first cut of the loading condition **contained its own
  clause** so the page hung instead.

**Two cases are declared GREEN, and that is a finding rather than a gap** — both are defence in
depth, where no single-line break is observable:

- once-per-mount is delivered by the `fired` ref **and** by an effect dependency list a tab click
  does not disturb;
- the logged-out nav protection is delivered by `freeSignedIn`'s `isSignedIn` half **and** by
  `showSubNav`, which hides the whole surface menu pre-login.

---

## 7. ⭐ What the first real league found (2026-08-08, post-merge)

The story shipped, the operator configured an actual league on an actual free account, and three
defects were visible inside a minute. None was caught by anything above, and the reason they were
not is worth more than the fixes: **§6 proved the delta was CORRECT and never asked whether the
screen was USABLE.** Correctness was heavily instrumented — a sign convention, an anchor that cannot
be produced by the sign, a red proof for the tautology. Nobody asserted that the players named were
players you would draft, that the table under them could be navigated, or that the *other* create
path enforced the same limit as the first.

### 7.1 The highlights were waiver-wire churn — and it was structural

Every riser and faller on the first real league was a player nobody would draft. This was not a
threshold that needed tuning. **Rank density grows down the board:** around pick 30 a few points of
projection separates adjacent players; around rank 400 the same few points spans dozens of them. So
the largest *rank* moves live in the deep tail **by construction**, and a highlight list sorted by
rank movement is a list of churn — arithmetically perfect, and useless on the one screen the funnel
converts on.

The fix is a **population**, not a different sort. `draftablePoolSize` = `n_teams ×` drafted roster
spots, bench included (bench spots are drafted; a last-round pick is exactly the "does my scoring
make him worth it?" call this screen should answer) and **IR/taxi excluded** (filled after the
draft). A player is eligible to be a headline if he is inside that pool on **either** measure:

- **market ADP** — the authority on who actually gets drafted. ⛔ Used to bound *our* list, never to
  claim anything against it; nothing on the surface presents this as an ADP comparison.
- **this league's board** — required, not a nicety. ADP is sampled in one format, so a superflex QB,
  a rookie with no sample, and every row of a pre-ADP board all carry `adp == null`. Judging by the
  market alone would delete exactly the players whose value this league *creates* — the most
  interesting highlights on the page.

⚠️ **The pool bounds what LEADS, never what is shown.** `players` stays the full comparison so the
board's "vs free board" column is populated for every row; filtering it would hide a real number
rather than decline to headline it.

⚠️ **The pool is a league property, which is the point.** 160 in a 10-team/16-spot league, 240 in a
12-team/20-spot one. A hardcoded "top 200" would be a different, wrong answer for most leagues and
would stop scaling the moment someone imports a 14-team dynasty.

### 7.2 The board was one unbroken run of several hundred rows

Paged with the shared `Pagination` (Track Record's). Two failure modes that look normal and are not:
the row number **continues across pages** (a bare `i + 1` reprints "1" at the top of every page, and
the column silently stops meaning rank), and the page index is **clamped during render** so a
position filter that shrinks the row count can never show an empty table — which would read as "you
have no TEs" rather than "you are on page 9 of 2".

### 7.3 The importer ignored the quota the editor enforced

**The freemium build's own lesson, recurring on the two create paths.** #681 gated one of three
renderers that print the paid scorings and looked complete; here the manual editor refused a second
league from day one and **platform import did not** — so a free account at its quota could choose a
platform, type a username, wait for us to read the league, and press Save before meeting a 409. The
tier is enforced by **which component renders**, and there were two.

Now refused at the **league list**, before any work. ⚠️ **The rule is "a different league", not "any
import"**: re-importing the league you already have is an *update*, costs no quota (`PUT` is not
capped server-side either), and is how a returning user refreshes a roster mid-season. Blocking it
would break the re-sync everyone needs in order to enforce a limit nobody exceeded — which is why
the e2e fixture carries **both** a saved and an unsaved league, and why `the-quota-locks-the-league-
you-already-have` is a red-proof case in its own right.

The refusal and the **upgrade CTA** are one component (`LeagueQuotaNotice`), so a third create path
cannot ship the limit without the way past it. A limit with no route past it is a dead end, and that
route is the conversion the funnel exists for.

### 7.4 Two defects found while fixing the three

- **The activation event raced its own delta.** It fired when the league board's rows existed, but
  `players_moved`/`players_compared` come from a comparison against the **generic** board, which
  lands independently — so whenever the generic board settled second the event still arrived, the
  funnel still counted the activation, and only the dimension saying whether anything *changed* was
  quietly null. Indistinguishable from "a league where nothing moved". It now waits for `loading` to
  clear, which is also the more faithful reading of "viewed their custom board".
- **Both summary numbers are now pool-scoped**, so `players_compared` changed meaning.
  `draft_pool_size` is emitted beside them rather than left to be inferred. Event *names* are still
  G100-D0's contract and unchanged.

### 7.5 Verification

| Layer | Instrument | Result |
|---|---|---|
| The pool arithmetic, the pager, both create paths | `frontend/e2e/specs/free-league.spec.ts` (+9) | **19 pass** |
| Whole frontend suite | `npx playwright test` | **142 pass** (was 133) |
| Every new clause is falsifiable | `frontend/e2e/red-proof.mjs` (+7 cases) | **6 RED, 1 declared not-observable** |
| Backend untouched, boundary still holds | `test_g100_c1_free_league.py` + `test_freemium_tier.py` + `test_e9_56c_cta_routes.py` | **127 pass** |

⭐ **The declared-GREEN case is the honest one.** "A filter change never empties the table" is
delivered by **two** independent mechanisms — the tab handler resets the page, and the render clamps
the index — so breaking either alone leaves the other holding and no single-line defect is
observable. That is the NF-D17 `and`-composed-clause trap facing the other way: the redundancy is
deliberate and wanted, but it has the same consequence for provability, so it is stated rather than
left as a case that quietly always passes. Measured both ways round, not reasoned about.

### What is NOT proven here

- **The API Gateway authorizer.** These routes are authenticated, so they inherit the default
  Cognito authorizer and need **no** gateway change (NF3.2 in reverse — adding an
  `--authorization-type NONE` route would un-gate the saved-league surface). A test reads the route
  inventory to keep that a checked claim rather than a comment.
- **The live `deploy.sh`.** The quota, the gate and the cap are all **backend** — merging to `main`
  does not ship them.
- **That the activation event reaches the real PostHog project.** The e2e proves it leaves the page
  under the right name with the right dimensions; the dashboard end is an operator check.
