# Frontend E2E smoke suite (E9.63)

The frontend's only automated gates were `tsc`, `eslint` and `next build`. None of them renders a
page, so none of them can see a redirect, an empty state, a `NaN` column or a dead route. The whole
E9.56b→e cluster and all six E9.58 defects shipped past them, and every one was found by a human
opening a browser.

This suite is the automated form of the "verify in incognito" step every app story already lists
manually. E9.63 built it deliberately **minimal** — the launch-critical funnel, nothing else — and
the coverage phases add specs to *this* harness rather than rebuilding it: **E9.64 (Fantasy
interactivity) and E9.64b (the two real league-import paths) have landed**; E9.65 (MLB betting) is
still to come.

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
| `specs/locked-surfaces.spec.ts` 🗄️ | A logged-out visitor sees rows, lock chips on every withheld model value, a working Subscribe CTA, and no `NaN` | E9.56b (Rankings rendered blank for every free user), E9.56c (withheld values fell through to "—"; the CTA was a 404). 🗄️ **Runs under an explicit `entitlement: "locked"` mock mode since the freemium build — no live caller receives a locked payload any more.** It is kept because the components still carry their `locked` branches, so withdrawing the open board stays a config decision rather than a rebuild; ⛔ do not read it as a description of current behaviour |
| `specs/entitled-surfaces.spec.ts` | An unlocked payload renders real numbers, zero lock chips, and no upgrade ask | the other half of the same split — a page that renders chips unconditionally passes the file above and is broken for every subscriber |
| `specs/route-integrity.spec.ts` | **Every internal `href` in the rendered DOM resolves** | E9.56c — `/pricing` killed the entire buy path |
| `specs/signup-funnel.spec.ts` | Every signup entry point offers a working Google button; the nav carries a signup affordance on desktop **and mobile**; the click leaves for the configured Cognito host with correct PKCE params | E9.58 — the DNS-dead Hosted-UI host, and the logged-out mobile nav with no signup affordance (`hidden sm:flex`) |
| `specs/track-record-claim.spec.ts` | **The public Track Record leads with calibration, not with the ADP comparison**; the plain lead keeps all four of its hedges; the position table (where the running-back wash lives) renders without expanding anything; the fine print still names the benchmark, metric, sample and interval; **no forbidden claim language anywhere in the rendered document**; and a pre-NF-TR1 artifact degrades without promoting the old un-hedged sentence into the lead | NF-TR1 — pre-emptive. The claim is small (its own 90% interval includes zero, NF-D17) and the failure mode is a plainer rewrite that sounds punchier because a hedge came off. The Python suite screens what the *export* generates; only this file can see the *rendered* page, which also carries every static component string no export-side denylist has ever looked at |
| `specs/pricing.spec.ts` | A logged-out visitor sees the price; **the rendered price and currency FOLLOW the server**; a failed pricing read costs the price and not the funnel; the page's own CTA resolves; the payload carries no internal conversion count | E9.59 — until it, `/subscribe` could not show a price at all (the only pricing read required auth). The headline case is pre-emptive: a hardcoded price is invisible to every other gate |
| `specs/home-positioning.spec.ts` | A **first-class door to BOTH verticals** (scoped to the cards, not a link label another block supplies); the **fantasy proof renders a real served player** and comes **before** the MLB proof; personalisation is shown via one player scored three ways; the **rank gap never ships without its market-lean caveat**; the MLB badge says what was **measured** and never "HIGH CONVICTION"; the record is described as graded-daily **and** members-only; an empty read and a FAILED read say different things and **neither can blank the page**; **no forbidden claim anywhere in the rendered document**; the blog is out of the primary nav but still reachable | E9.46 — the pre-story page read as an MLB betting site ("Daily edge, quantified"). The 2026-08-08 revision also corrected three claims that were live: the featured game is the EARLIEST qualifying one and was described as the widest gap; "HIGH CONVICTION" was a hardcoded constant classifying nothing; and the MLB comparison is a de-vigged market consensus, not Bovada |
| `specs/freemium-board.spec.ts` | A **logged-out** visitor gets the free generic board (rows, real numbers, no redirect); lands on the **free preset** rather than the entitled default; sees every other preset **listed, marked and disabled** with the lock explained at the control; has a stored paid selection **re-checked**; meets a **paywall rather than an empty-search message** when a board is refused. On the other two surfaces that print the paid scorings: Season Projections offers **only the free reference scoring**, and a player page **locks standard + half-PPR while keeping full-PPR**, **withholds the raw stat line**, and does not call a preset the reader's **own league**. Plus: a free/paid boundary **below** the board naming **all three** paid halves, which **links** to the track record without quoting its number; the full-season rate **immediately beside** expected points with an em-dash for a zero / null / absent games figure; no denied claim anywhere in the rendered DOM; and the paid half (League Board, Draft Optimizer, My Teams) **still bounces** a stranger | The freemium build, the format split that narrowed it to one preset, and the two surfaces that split missed. The funnel-killing failure — a free visitor REDIRECTED before the board renders — is invisible to every Python assertion in the repo, because the API is perfectly happy and serves the free board to anyone; only a browser following the navigation can see it. Same for being *steered* onto a board the API refuses. ⭐ The stat-line case is the one the format lock depends on: the three totals differ only in how a reception scores, so `half = full − 0.5·rec` makes a visible reception count hand over both withheld numbers. The `Infinity` case is the other one nothing else catches: `pts × 17 ÷ 0` is a `number`, so it survives every `!= null` guard and prints "∞" in a points column |
| `specs/home-mobile.spec.ts` | The home page **never scrolls sideways** on a phone; the dense fantasy stat grids stay inside their card; **both explanatory popovers open on TAP**; both hero CTAs stay reachable and tappable | E9.46 — the home page is the highest-traffic surface and its two live cards are the densest layouts on it. A four-column rank grid and a three-column format row wrap, overflow or truncate on a phone in ways `tsc` and `next build` cannot see, and a hover-only popover is unreachable there (the E9.63/NF3 lesson) — both of ours carry the copy that stops a number being misread |

### E9.64 — the Fantasy interactivity specs

| File | What it guards | The defect it is written from |
|---|---|---|
| `specs/fantasy-entitlement-gates.spec.ts` | **Who can open what**, across anonymous / signed-in-free / subscriber. An anonymous visitor is offered no entitlement-gated fantasy surface **and** is refused one they navigate to directly, landing on sign-in with `?next=` intact; a free account opens the three league surfaces and is sent to the **upsell** (not to sign-in) for the three entitled ones; a subscriber opens all six and finds them in the nav | **G100-D0-R1 item 5.** Nothing guarded the league nav items against an anonymous visitor: the protection was incidental (`showSubNav` withholds the whole sport sub-nav), so a future story rendering the sport menu logged-out would remove it silently. See ⭐ below for why the anchor moved. Also E9.58 — every guard bounce used to be a bare `/login`, so a stranger who signed up landed on `/dashboard` with no trace of where they were going |
| `specs/fantasy-board-flows.spec.ts` | The free board **used**, not merely rendered: the position filter leaves only that position *according to the served payload*, search narrows and can be cleared, a no-match search **says so**, paging advances and keeps counting, Export CSV yields the whole filtered board, and a row opens the page for **that** player | Every pre-existing board assertion describes the OPENING state. `NaN` — E9.56b's whole class — appears on *interaction*; a filter keyed on the wrong field renders perfectly; a player cell bound to a shared id opens a real, correct-looking page about somebody else |
| `specs/fantasy-draft-optimizer.spec.ts` | Setup → start → draft → undo; a drafted player leaves the board and the snake clock advances; the Pts column sorts **and reverses**; the position tabs and search compose; a mid-draft **reload** keeps the picks | The largest component in the app, and before this nothing opened it. It is a state machine a user drives for two hours: a player who can be taken twice is discovered by the room rather than by us, and a lost draft at pick 40 is the session |
| `specs/fantasy-my-teams.spec.ts` | Each roster scored under **its own** league's format — pinned as arithmetic, not as a vibe — plus starters/bench separated, an unresolvable name counted rather than dropped, and the two states a real account is in (no leagues; a league with no team linked) | The failure is not a crash: it is scoring every roster on ONE board and relabelling the cards. It renders perfectly, has no `NaN`, throws nothing, and is wrong in a way the user cannot detect without doing the arithmetic themselves |
| `specs/fantasy-league-import.spec.ts` | The **review queue**: the league's settings are read back before saving, the rules we could **not** represent are shown verbatim, a coverage check that could not run **says so** (and does not block the save), and a save reports what it did | `free-league.spec.ts` stops at the league list. Step 2 is the only place a user can learn we did not understand their league — the component's own comment: *"an import that quietly loses a rule is the failure this whole surface guards."* The optimistic coverage render is the natural one to write, because the resolver reads an absent column set as "we have everything" |

### E9.64b — the two REAL import paths

| File | What it guards | The defect it is written from |
|---|---|---|
| `specs/fantasy-import-espn.spec.ts` | The **ESPN paste**, driven with **real bytes**: the settings link is the SERVER's (not one the page assembled), a real `?view=mSettings` response is pasted and the league is read back **from that payload's own values**, ⭐ the canonical yardage terms land in the **APPLIED** coverage card, ESPN's numbered rules are made **readable**, a cleanly-read league shows **no** "could not read" box, a drafted league brings its teams/rosters and **claims no live refresh**, the client's rewrite of the paste **does not corrupt it**, a refused paste says **why** and leaves the flow usable, and a save reports what it did | **NF-C0e** — `espn.py` mapped ESPN's yardage stat ids onto Sleeper's `pass_yd`/`rush_yd`/`rec_yd`, one character off the canonical keys, so **every ESPN league scored zero yardage from the day import shipped**. Nothing errored: an unrecognised key passes through verbatim and reports CAPTURED, a legitimate verdict for a rule we genuinely do not project. It survived 56 tests over one live-verified league. ⭐ Hence **two independently-sourced real payloads** (12-team full-PPR and 10-team half-PPR, disjoint rule families) carrying every settings assertion twice — a fixture derived from the first payload cannot disconfirm a wrong key-map |
| `specs/fantasy-import-yahoo.spec.ts` | The **Yahoo OAuth** flow, in all three platform states: the un-approved platform is **listed, marked coming soon, and offers no button to press**; the connect click leaves for **the authorize URL the server supplied**, verbatim including the signed `state`; the three `?yahoo=` return states say **different** things; a connected account lists → previews → reviews → saves; ⭐ Yahoo's `is_owner` **pre-selects the user's team and only theirs**; 🚩 Yahoo's **required attribution** renders; and disconnect **does not overstate** what it revoked | **E9.58**, whose worst defect was an OAuth host that was internally consistent in every file, type-checked, rendered a real button, fired a real click — and did not resolve. Plus the "a button that 500s" trade `list_platforms`' own docstring describes: `available` and `configured` are reported separately so an unapproved platform can say *"coming soon"* rather than being hidden (which a Yahoo user reads as "not supported") or offered (which sends them into a 503). The attribution is a **contractual** requirement living in a branch nothing had ever entered |

⭐ **The item-5 fix, and why the anchor had to move.** `free-league.spec.ts`'s "a logged-out visitor
is not offered the league surfaces" is honest about being over-determined, and `red-proof.mjs`
carries **two declared-GREEN cases** recording that `lockedVisibleItems` can be broken in either
direction without it noticing — an anonymous visitor never reaches that filter at all. Since E9.60
the list that actually renders for a stranger is **`SIGNED_OUT_NAV`** (`lib/positioning-copy.ts`),
which is *authored* and therefore falsifiable: `nav-offers-a-gated-league-surface` puts
`/fantasy/my-league` in it — precisely the future the finding described — and the spec goes **RED**.
The old cases are kept exactly as they are; they document a real property of the nav's shape.

`signup-funnel.spec.ts` is the only spec that also runs on a phone viewport, because one of the
defects it is written from was mobile-only and a desktop-only suite is structurally blind to it.
`fantasy-entitlement-gates.spec.ts` joins it for a **coverage** reason rather than a layout one:
`SIGNED_OUT_NAV` renders in two different subsets (the desktop bar draws only its `desktop`
entries; the phone menu draws the full list once opened), so a desktop-only run never sees the
majority of the authored list. Everything else in that file is a `router.push` and is skipped on
mobile rather than run twice.

## The Fantasy interactivity inventory (E9.64)

Recorded so **coverage gaps are visible** rather than inferred. "Controls" means things a user can
click or type into; entitlement columns are the states in which the surface is reachable.

| Surface | Route | Gate | Interactive controls | Covered by |
|---|---|---|---|---|
| Rankings | `/fantasy/rankings` | public | format + size picker, position tabs, search, paging, CSV export, own-league delta | `freemium-board` (picker lock, refusal), `fantasy-board-flows` (filter/search/paging/CSV/link), `generic-delta-column` |
| Season Projections | `/fantasy/projections` | public | reference-scoring picker, position tabs, search, paging | `freemium-board` (scoring lock), `fantasy-board-flows` (filter) |
| Player Search | `/fantasy/players` | public | search, position tabs, paging, result → player page | `fantasy-board-flows` |
| Player page | `/fantasy/player/[id]` | public | format tiles, definition popovers, history panel | `freemium-board` (locked totals, withheld stat line), `expected-points-label` (tap) |
| Track Record | `/fantasy/track-record` | public | season + position tables, popovers | `track-record-claim`, `expected-points-label` |
| My League | `/fantasy/my-league` | signed-in | position tabs, paging, delta highlights | `free-league` |
| Import League | `/fantasy/import` | signed-in | platform pick, identifier entry, league list, **review**, team pick, save; **ESPN**: league id → link → paste; **Yahoo**: connect → return → list → disconnect | `free-league` (quota boundary), `fantasy-league-import` (review + save, Sleeper), `fantasy-import-espn` (the whole paste path, ×2 real leagues), `fantasy-import-yahoo` (all three platform states) |
| League Settings | `/fantasy/league-settings` | signed-in | scoring + roster editor, New league, save | `funnel-telemetry` (create vs update), `free-league` (quota) |
| League Board | `/fantasy/league-board` | entitled | format picker, own-league delta column | `generic-delta-column` |
| Draft Optimizer | `/fantasy/draft` | entitled | setup pickers, start, draft / undo / reset, sort, position tabs, search, persistence | `fantasy-draft-optimizer` |
| My Teams | `/fantasy/my-teams` | entitled | browse (no controls) | `fantasy-my-teams` |
| Every gated surface | — | anon / free / subscriber | navigation + guard refusals | `fantasy-entitlement-gates` |

### Declared limitations — GREEN by design, not by coverage

Each of these is a case a spec **structurally cannot see**, recorded here so it is not mistaken for
coverage. This list is the honest half of the table above.

1. ✅ **CLOSED at E9.64b — Yahoo import is now driven, except for the consent screen itself.**
   Five of the flow's six steps are in our app and all five are covered
   (`fantasy-import-yahoo.spec.ts`). Only Yahoo's own consent page is unreachable, and faking the
   callback would exercise our own stub — so it stays out. ⚠️⚠️ **BUT THE YAHOO PAYLOAD IS NOT
   REAL, AND CANNOT BE YET.** Yahoo gates all Fantasy API access behind a developer-application
   review that has not cleared (`docs/nf_c0_yahoo_oauth_setup.md`: submitted 2026-08-01, still
   pending, SSM parameters unwritten), so there is no account anywhere that can produce a real
   response — the "≥2 independently-sourced real payloads" bar this suite meets for ESPN is
   **structurally unmeetable for Yahoo today and is NOT met**. What is real is the response SHAPE:
   the fixture is the output of the shipping `yahoo.import_league` adapter. ⏭️ **RE-GENERATE FROM A
   REAL LEAGUE THE DAY APPROVAL LANDS** (`uv run python frontend/e2e/fixtures/build-import-previews.py`)
   — that is the single open item on this path.
2. ✅ **CLOSED at E9.64b — ESPN paste import is driven with REAL bytes.** The blocker was thought to
   be "there is nothing to capture", but three verbatim `?view=mSettings` responses from real
   private leagues were already committed for the Python adapter suite
   (`betting_ml/tests/fixtures/espn_league_*`). `fantasy-import-espn.spec.ts` pastes those exact
   bytes and the previews are generated from them by the shipping parser, so no assumption about the
   payload is encoded anywhere. ⚠️ **The paste platform is ESPN**; E9.64's story prompt said "CBS
   paste" and no CBS integration exists — the catalog is corrected at `story_prompts.md`.
3. **Mark-as-drafted is not an NFL surface** (unchanged, and the catalog is now corrected too). It
   lives on the MLB prospect board (`/fantasy/mlb/prospects`), which is `restrict: "admin"` while in
   development. The three MLB fantasy surfaces are out of Phase 1 scope for that reason; they are
   asserted as *absent* for an anonymous visitor by `fantasy-entitlement-gates`, and nothing else.
4. ⚠️ **The review screen's DRAFT panel is unreachable for both import paths.** `espn.py` never
   constructs a `DraftState` (ESPN's import carries rosters off `teams`, never picks), and the Yahoo
   preview fixture is built with `include_draft=False` because a draft read is a third Yahoo
   resource and would be more synthetic surface with no assertion behind it. So `preview.draft` is
   `null` on all four committed previews and nothing renders that panel. This is recorded rather
   than worked around: see the red-proof section for the vacuous guard it produced when it was not.

5. ✅ **CLOSED at ESPN-PRUNER — `pruneEspnPayload`'s DENYLIST is now exercised against a real
   un-pruned capture** (`espn_league_raw_unpruned.json`, league 642070 / 2025, 834 KB, drafted).
   The client rewrites the user's paste before sending it, and **none of the three previously
   committed captures contained the fields it strips**
   (`stats` / `draftRanksByRankType` / `ownership` / `outlooks` / `ratings` /
   `notificationSettings`: measured, zero occurrences in all three), because they were already
   stripped before being committed. That is the NF-C0e shape — a fixture that is the transform's own
   OUTPUT cannot test the transform — so `fantasy-import-espn.spec.ts` asserts the pruner's
   *contract* rather than a size ratio, which would be a guard that cannot fail for the reason it
   names. What changed:
   - **`fantasy-import-espn-pruner.spec.ts` now holds the real assertions** — under the 4 MB cap,
     exactly the unread fields removed, the identity/roster/settings the parser reads preserved, and
     the silent `catch { return text }` path caught (the returned text MUST differ from the input).
     They are gated on two operator-supplied un-pruned captures and **SKIP, loudly, until those
     land**; a registry test that always runs prints `proven on real un-pruned bytes for N/2 sizes`
     into the run output, so a green run still tells you the claim is owed.
   - **A non-vacuity guard runs in the FAST GATE** — `test_espn_pruner_raw_capture.py` refuses a
     "raw" capture that is in fact pruned, which is the exact way this gap would silently reopen.
     It also pins the TypeScript's re-spelling of `MAX_PASTE_BYTES` to the server's real constant.
   - **Real-size paste behaviour is MEASURED, not assumed.** ⭐ 3,313,231 B pasted into the real
     React `<textarea>`, pruned, and POSTed in **533 ms** (the pure function: **7 ms**). The page
     does not hang. The largest payload ever put through that control before this was 207 KB.
     ⚠️ That probe uses a SYNTHETIC of the right SIZE, and size does not depend on the field names
     being right — so it is scoped to latency and to catching the walk BREAKING (a renamed key, a
     wrong path), never to whether our belief about ESPN's shape is CORRECT. That half is exactly
     what the operator captures are for.
   ⭐⭐ **THE FINDING THE CAPTURE PRODUCED, and it overturns the pruner's stated reason to exist.**
   The docstring claimed "3.3 MB un-pruned ⇒ 82% of the cap at 10 teams, ~99% at 12, REFUSED at 14".
   MEASURED on the real capture: **834 KB = 20.9% of the cap → 131 KB pruned**, a **6.4× reduction**
   (not 22×), with the 12- and 14-team scalings at **24.1%** and **28.1%** — *nothing measured comes
   near the cap*. So pruning is **not today load-bearing for import to work**; it is a 6.4× payload
   reduction, which is worth keeping on its own terms. 🔎 NOT SETTLED: the capture is a COMPLETED
   season with 5 `player.stats` splits per player and **zero** `outlooks`; an in-season response may
   be far larger, which is exactly where a missing 4× would live. An in-season capture would settle
   it. The suite REPORTS headroom rather than asserting a threshold, so a future capture that
   disagrees is a correction, not a red build.
   ⭐ **And the pruner is independently corroborated:** pruning the raw capture yields 131,311 B
   against the separately-committed pruned artifact's 130,112 B — same league, identical player
   keyset and roster counts. `test_espn_pruner_raw_capture.py` also now proves the real invariant
   (raw and pruned parse to the SAME league) rather than the idempotence PROXY that stood in for it.
   ⏭️ **Optional, not blocking:** a second independently-sourced capture, ideally IN-SEASON.
   - ⚠️ **THE SEASON MATTERS; THE LEAGUE SIZE DOES NOT.** The removable bulk lives in the **roster
     entries**, so an UNDRAFTED league returns its full team list with zero entries on every team
     and none of the removable fields — a faithful capture that is useless here. Measured on the
     first real attempt: a 2026 pre-draft 12-team league came back at **48 KB** with `"stats"`
     occurring **zero** times. A usable capture is **megabytes**. So a drafted 10-team league is
     worth far more than an undrafted 12-team one, and the shape-carrying registry entry declares
     `teams: null` to say so — pinning it to a size would reject a good capture for a reason
     unrelated to what it proves.
   - **Why one is enough for the SHAPE claim, and what it does not cover.** The denylist question is
     "do these fields exist where we think, in ESPN's output" — a claim about field names, not about
     league size, so one real capture settles it at every size. What one capture cannot disconfirm
     is that ESPN returns a materially different field set for a *larger* league; that is unverified
     and stated rather than assumed.
   - **The size legs are answered by SIZE-EXTENSION, not left pending.** Waiting on a drafted league
     of each size would leave those legs permanently "pending" — a limitation that reads as a
     considered decision and stops anyone re-checking it. Instead each size leg replicates whole
     teams out of whichever real capture exists: every byte is genuine ESPN output, so it carries
     the SIZE claim at that scale honestly and adds **zero** independent shape evidence. The
     registry test reports the two counts **separately** (`SHAPE proven on N independently-captured
     real payload(s); SIZE additionally covered at M size-extended league size(s)`) precisely so the
     second cannot be laundered into the first; a Python guard fails if every entry is ever flipped
     to size-extended; and if the base capture already IS a leg's size, the resolver labels it
     `captured` rather than extended (under-stating evidence is as dishonest as over-stating it).
   - **An undrafted capture and a pruned one are diagnosed apart.** Both present as "no bulk
     fields" and need opposite fixes (different *season* vs re-capture without the transform), so
     the roster check runs FIRST and names the real cause. An earlier cut reported the undrafted
     case as "it is a pruned artifact" — false, and it sends the reader at the wrong fix (INC-40:
     a suggested cause is diagnostic anchoring; it must be right or absent).
   - ⭐ **A genuinely real 14-team payload needs no credential.** A league whose owner has set it
     PUBLIC is readable unauthenticated from the same host (`docs/nf_c0_espn_access_probe.md` §1(b)
     — that path was rejected as a *product* path because it cannot reach private leagues, which is
     no objection to using it as a *fixture*). Drop a public 14-team league id into the read URL and
     the file slot takes it; a real capture always wins over extension.
   - **The "12-team ≈99% of cap / 14-team REFUSED" figures are now MEASURED and reported**, not
     inherited. They had been quoted in three places since NF-C0e and were themselves extrapolated
     from a single 10-team measurement. The cap test prints the real headroom; a capture that
     disagrees is a docstring to correct, not a test to fail.
6. **Rankings and Projections have no sortable columns.** Their order is the board's own rank, so
   there is no sort control to test — recorded so a future reader does not go looking for the test.
   The Draft Optimizer's Pts/VOR headers are the only user-driven sort in the product, and they are
   covered.
7. **A draft is never played to completion.** The "Draft complete" summary needs
   `slots × teams` picks (192 on the default preset); driving that is a slow test of arithmetic that
   is already unit-covered. Only the opening picks are driven.
8. **Live draft sync** (`/fantasy/import/live/…`) is not driven — it needs a draft actually running
   on the platform.
9. **No spec here proves authorization.** `session.ts` seeds unsigned tokens and the API is mocked,
   so every entitlement assertion is about what the client RENDERS. Who may read what is enforced
   server-side and asserted against the real ASGI app in `test_freemium_tier.py` /
   `test_g100_c1_free_league.py`. A browser test that appeared to check entitlement would be the
   most convincing vacuous guard in the repo.
10. **The subscriber side of the format picker** stays where `freemium-board.spec.ts` already puts
   it — server-side, for the reason recorded there.

### ⚠️ A whole-page text scan needs an explicit wait, and the laptop will not tell you

`(await page.locator("body").innerText())` is a SNAPSHOT. Take it straight after `goto` and it can
capture the loading state, in which the content you are asserting on is legitimately absent — so
the test reports a **product defect** ("required disclosure missing from the page") when what
actually happened is that the fetch had not landed. That is the most expensive way for a test to be
wrong, and NF-TR1 shipped it: the spec passed here every time, including **12 consecutive runs at
`--workers=2`**, and failed both attempts on the slower 2-worker CI runner.

Two rules, both cheap:

1. **Wait on the content the fetch produces before scanning** — `track-record-claim.spec.ts`'s
   `gotoTrackRecord` is the pattern. A page that never renders it still fails, on the visibility
   wait, with a better message.
2. **A wait added to silence a red test is how a test stops being able to fail.** Pair it with a
   red-proof case that removes the content for real (`disclosure-dropped`), so "slow" and "absent"
   stay distinguishable.

To reproduce a slow runner locally — which is the only instrument that actually finds this — copy
the spec, wrap `mockApi` so it registers a delaying `page.route(…, r => sleep then r.fallback())`
**after** the mock (routes are LIFO, so a later handler runs first), and run at `--workers=2`.
Measured: the pre-fix sequence fails at a 1200 ms manifest delay; the whole spec passes at 900 ms
on every call.

## Fixtures

`fixtures/api/` holds **verbatim captures of the live production API**, refreshed by
`capture-fixtures.mjs`. Every one is a public, anonymous GET — they are the bytes a real visitor's
browser receives.

⛔ **Do not hand-write a fixture.** That is the E9.56b lesson as a rule: the bugs this suite guards
all live in the gap between what we *assume* the payload looks like and what the server actually
sends, so a hand-written fixture encodes the assumption under test.

`subscription-public-pricing.json` (E9.59) was synthetic for one day — the route did not exist in
production until the operator added its API-Gateway `NONE` route, so there was nothing to capture.
It is a **real capture since 2026-08-07** and the synthetic file is deleted. Two notes on it:

- It is pinned to the backend model — `betting_ml/tests/test_e9_59_public_pricing.py` asserts its
  key set **equals** `PublicPricing.model_fields`. A capture is a snapshot and goes stale silently;
  that test is what turns "the API grew a field" into a red build instead of a suite passing
  against a shape that no longer occurs.
- ⚠️ It records the Stripe **TEST-mode** price. Re-capture at the E9.8-P2 live flip.

`fantasy-nfl-track-record-manifest.json` is a real capture **except for its `claim` block and its
`headline`**, which NF-TR1 added and which do not exist in production until the operator re-runs
the exporter with `--publish`. Same one-day shape the pricing fixture had. Nothing is authored:
`fixtures/build-track-record-claim.py` calls the SHIPPING `export_track_record_json.build_claim`
over the committed NF-D3 scorecard and NF-D17 population artifacts, and
`betting_ml/tests/test_nf_tr1_claim_copy.py::test_the_e2e_fixture_claim_is_the_shipping_builders_own_output`
asserts the fixture equals that output — so it cannot drift from the code it is testing. ⚠️ **Delete
that script and re-capture once the publish has landed.**

**E9.64 adds two COMPUTED payloads rather than fixture files**, both in `support/api-mock.ts` and
both following the same rule — derive everything that can be real, name what cannot:

- **`leagues: "linked"`** — two saved leagues with linked teams and real rosters. The three
  pre-existing modes all serve the captured league with `source_team_key: null` and a null roster
  (an honest state, and the only one they can make), so every roster table on My Teams was
  structurally unreachable. The pair is the real captured league differing in **exactly one scoring
  rule** — what a reception is worth — carrying the same players, which is what turns "each roster
  is scored under its own format" into arithmetic a spec can check (`0.5 × receptions`) rather than
  a difference it can only observe the sign of. Rostered players are read out of the real
  projections payload so they resolve through the app's own `name|pos` join.
- **the Sleeper `preview` response** — step 2 of the importer. Its `config` **is** the real captured
  league and its `teams` are real board players; only `warnings` / the captured scoring key are
  synthetic, and unavoidably so — a warning list has to be non-empty for "the rules we could not
  read are shown" to mean anything, and no anonymous caller can produce one. That does not weaken
  the assertion: the property under test is that whatever the server sends is rendered **verbatim**,
  so the wording being ours is precisely why the spec can check it word for word.
  ⚠️ A captured term is an ordinary `per_stat` rule with no projection behind it — *not*
  `captured_rules`, and *not* `unmapped_scoring_keys` (which only supplies display labels). Setting
  either of those instead renders the disclosure nowhere while looking entirely reasonable; the
  comment on `importPreviewFor` records it because it cost two wrong guesses.

**E9.64b adds five GENERATED fixtures for the two real import paths**, built by
`fixtures/build-import-previews.py` and pinned to the shipping adapters by
`betting_ml/tests/test_e9_64b_import_e2e_fixtures.py` (which fails the build if a fixture drifts
from what `espn.py` / `yahoo.py` produce today — a capture goes stale silently, and that test is
what turns "the adapter grew a field" into a red build instead of a suite passing against a shape
no caller receives). The two sides are **not** equally real, and the difference matters:

- `fantasy-import-espn-preview-{998005-2026,642070-2026,642070-2025}.json` — ⭐ **fully real.** The
  INPUTS are three verbatim `?view=mSettings` responses from real private leagues, already committed
  for the Python adapter suite; the OUTPUTS are what the shipping `espn.parse_settings_payload`
  makes of them. Nothing is authored. Two are **different leagues on different accounts** with
  disjoint scoring families — pinned as an assertion, because the moment they converge the second
  has stopped buying coverage, which is the whole NF-C0e lesson.
- `fantasy-import-yahoo-{preview,leagues}.json` — ⚠️ **the SHAPE is the shipping adapter's; the
  PAYLOAD is not real and cannot be** until Yahoo approves the developer application. See declared
  limitation 1.

⚠️ The ESPN specs paste the real captures **across the tree** (`betting_ml/tests/fixtures/`) rather
than from a copy in `e2e/fixtures/`, deliberately: a second copy would drift from the one the parser
is tested against, and the value of this path is that the browser pastes the same bytes the adapter
was proven on.

⚠️ **`fantasy-import-platforms.json` IS HAND-AUTHORED, NOT A CAPTURE — a pre-existing violation of
this section's own rule, found while writing E9.64b and recorded rather than quietly patched.**
`/fantasy/import/platforms` requires auth, so it is not in `capture-fixtures.mjs`'s `TARGETS`; it
was written by hand at G100-C1 (2026-08-08). Measured, it has already drifted from the server in two
ways: Yahoo carries no `attribution` / `attribution_url` (added to `list_platforms` on 2026-08-01,
i.e. **before** the file was written), and every `help` string differs from the one `PLATFORMS`
actually serves. `api-mock.ts` supplies the attribution so `fantasy-import-yahoo.spec.ts` asserts
Yahoo's contractual attribution against what the server sends rather than what the fixture guessed.
⏭️ The durable fix is to generate this file from the shipping `list_platforms` the way
`build-import-previews.py` generates the previews; it is left as a separate change because the
`help` strings would move and `free-league.spec.ts` reads this file too.

One fixture is still generated rather than captured —
`fantasy-nfl-projections-2026-entitled.synthetic.json`. There is no public unlocked form of the
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

`npm run e2e:red-proof` re-introduces real (and pre-emptive) defects one at a time,
rebuilds, and requires the named spec to fail. A green suite proves nothing on its own; a test that
*cannot* fail reads as coverage and stops anyone looking again.

### ⏰ It is SCHEDULED now (E9.64b), and that is the point

Until E9.64b **nothing ran this script.** It was a manual command whose only trigger was a session
remembering to type it — which is precisely how E9.64's first full run came to find **six**
pre-existing cases that had silently stopped proving anything. A falsifiability harness nobody runs
is decorative, which is the defect it exists to catch, one level up.

`.github/workflows/frontend_red_proof.yml` runs the whole board **weekly** (Mondays 07:00 UTC) plus
on demand via `workflow_dispatch`. It **gates nothing** — 108 sequential production builds take
~90 minutes, so it cannot sit on a PR, and `frontend_e2e.yml` remains the per-change gate. But it
**fails the job** on any drift, deliberately: a scheduled run that always exits 0 is the same
decorative thing one level up. The visible red (and GitHub's failed-scheduled-run notification) is
the signal.

`red-proof.mjs` carries the board's recorded shape in `RECORDED_BOARD` and compares every full run
against it. Two different things fail, needing different responses:

- **a case reporting `MISMATCH` / `STALE`** — a guard stopped proving what it claims. Repair the
  case (⛔ never delete it); the six E9.64 repairs below are the worked examples.
- **`BOARD DRIFT` with every case green** — a case was added or removed without updating
  `RECORDED_BOARD`. Update it, **in the same commit** that changed the case count; the two are meant
  to move together, which is what makes an unexpected drift informative.

⛔ **Never edit `RECORDED_BOARD` to match a drift you did not cause.** That converts the one
instrument in the repo that can distinguish coverage from the appearance of coverage into another
piece of decoration.

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

**E9.64 added 15 cases and every one of them is RED**, including all four negatives — the ones that
assert something is *absent*, which is where a vacuous guard hides:

```
RED  nav-offers-a-gated-league-surface        ⭐ the G100-D0-R1 item-5 fix (see above)
RED  league-surface-open-to-strangers         a per-caller surface losing its guard
RED  free-account-bounced-to-login-not-upsell the 401-vs-403 refusal inverted
RED  sign-in-bounce-drops-the-destination     E9.58 — a bare /login with no `?next=`
RED  position-filter-does-not-filter          a filter that repaints and narrows nothing
RED  empty-search-renders-a-blank-table       the silent-empty class, reached through a control
RED  paging-does-not-advance                  a Next button that repaints page one
RED  player-cell-links-to-one-shared-player   every row opening the same player's page
RED  drafted-player-stays-on-the-board        a player who can be drafted twice
RED  sort-direction-never-reverses            a header that sorts once and then is inert
RED  draft-does-not-survive-a-reload          two hours of tracked picks lost to a refresh
RED  every-roster-scored-on-one-board         ⭐ My Teams' cards relabelled, the scoring shared
RED  unresolvable-roster-row-dropped          data loss on the user's own roster
RED  import-warnings-suppressed               ⭐ an import that quietly loses a scoring rule
RED  coverage-claims-everything-applies       an unchecked coverage report shown as a clean one
```

**E9.64b added 11 more, one per load-bearing claim across the two import paths, and every one is
RED:**

```
RED  espn-league-named-as-sleeper              ⭐ LIVE until E9.64b — every ESPN import read back
                                                 as a SLEEPER league on the review screen
RED  espn-yardage-scored-as-captured           ⭐ NF-C0e, rendered: yardage moves out of APPLIED
RED  espn-read-url-built-locally               the settings link assembled client-side
RED  import-error-replaced-with-a-generic-string  the server's actionable message discarded
RED  could-not-read-box-always-rendered        telling every user we failed to read their league
RED  captured-rule-shown-as-its-espn-number    a disclosure the reader cannot act on
RED  yahoo-connect-offered-before-approval     a button that 503s on an unapproved platform
RED  yahoo-authorize-url-rebuilt-locally       the OAuth URL rebuilt, dropping the signed `state`
RED  yahoo-return-states-collapsed             one banner for connected, cancelled and failed
RED  yahoo-owner-team-not-preselected          discarding the one thing OAuth tells us
RED  yahoo-attribution-dropped                 🚩 a CONTRACTUAL requirement, invisible elsewhere
```

One of those eleven — `espn-league-named-as-sleeper` — is a **defect that was live in production**
and is fixed in the same story: found by opening the review screen on a non-Sleeper preview for the
first time.

⭐ **A TWELFTH CASE WAS WRITTEN AND THEN REMOVED, AND THAT IS THE MOST USEFUL THING IN THIS SECTION.**
`espn-claims-a-live-draft-refresh` broke the review screen's *"draft state is read live from
Sleeper each time"* copy, which for ESPN is both the wrong platform and a promise nothing can keep.
It came back **MISMATCH** — because `espn.py` never constructs a `DraftState` at all (ESPN's import
carries rosters, never picks), so `preview.draft` is `null` on every real capture and the panel is
unreachable for that platform *by construction*. The spec's assertion had been written behind an
`if (preview.draft?.pick_count > 0)` and was therefore **silently skipping**: a guard that cannot
fail, written in the story whose subject is guards that cannot fail. The red proof is the only
instrument that found it. The component fix is kept (the copy is correct, and honest if ESPN ever
gains draft parsing) but it is **latent, not a live user-visible defect**, and the spec now asserts
`preview.draft` is null so the day that changes, someone is told to assert it properly.

### ⭐ Six PRE-EXISTING cases had stopped proving anything — repaired (E9.64)

**Whole-board state: 107 cases, 101 RED and 6 declared NOT-OBSERVABLE, exit 0** (E9.64b; it was
95 / 89 / 6 at E9.64). No STALE, no MISMATCH, no non-deterministic case. That shape is recorded in
`RECORDED_BOARD` and checked on every full run, so a future run reporting anything else fails the
scheduled job — a regression in the harness even when the app suite is green.

The first full run on 2026-08-14 reported six cases whose verdict did not match their declaration.
None was introduced by E9.64; all six are **fixed here**, because a red-proof case that cannot fail
is exactly the defect this harness exists to catch, one level up. Each needed a *different* repair,
and the reasons are more useful than the fixes:

| case | was | why it had stopped proving anything |
|---|---|---|
| `home-blog-back-in-primary-nav` | STALE | anchor drifted **and the link is gated away from the visitor the spec drives** |
| `activation-fires-on-mount` | STALE | the guard grew a `loading` clause |
| `activation-fires-per-render` | STALE | same guard, same clause (declared GREEN either way) |
| `configured-league-reads-as-no-league` | MISMATCH | the break's data-flow assumption was retired by NF-EPIC 1 |
| `delta-sign-inverted` | MISMATCH | a correct re-anchor **orphaned** the only assertion that read it |
| `custom-selection-lost-to-the-load-race` | FLAKY | a race the harness left to chance |

Four of them carry a lesson worth more than the repair:

1. ⭐ **A STALE case can hide a case that would be VACUOUS once un-staled.**
   `home-blog-back-in-primary-nav` rewrote the hardcoded About `<Link>` in `nav.tsx` to point at
   `/blog`; it went stale on the indentation when E9.60 wrapped that link in `{showSubNav && (`.
   Re-pointing the whitespace would have produced a case that ran and proved **nothing** —
   `showSubNav` is `authenticated || isSignedIn`, and the spec drives an **anonymous** visitor, so
   that link does not render for them however its href is written. The list that actually renders
   their nav is `SIGNED_OUT_NAV`, which is where the break now goes. ⇒ **when you un-stale an
   anchor, re-derive whether the broken line is on the path the spec walks — do not just fix the
   string.** (Same lesson as E9.64's item-5 fix, one file over.)
2. ⭐ **A break is only as durable as the DATA-FLOW it assumes.**
   `configured-league-reads-as-no-league` swapped `!hasSavedLeague` for `!league`, which was a real
   defect while scoring happened in the browser: `useMyTeams` could not build a board without the
   projections blob, so `league` was null exactly when the read failed. NF-EPIC 1 moved scoring
   server-side, `league` now comes off `/fantasy/nfl/my-teams` — which this spec does not fail — and
   the substitution stopped changing anything. The assertion was fine; the *break* had died. ⇒
   **when a read moves, re-check every case whose break depends on that read failing.**
3. ⭐ **Re-anchoring a test onto a new quantity can silently ORPHAN the old one.**
   `delta-sign-inverted` inverts `ovrDelta`. E9.61 correctly re-anchored the movers test onto VOR
   when the highlights moved to ranking on value — and in doing so left the **overall** move unread
   by anything, even though the board's "vs our generic board" column still renders it
   (`GenericDeltaCell scale="overall"`). So the break flipped every arrow in that column and the
   suite stayed green. Fixing the case meant **writing the assertion it had been naming**: `the
   board column's overall move agrees with the two boards' own ranks`, derived the same way as the
   VOR check (generic rank off the board fixture, league rank off the served league board, chip off
   the DOM — neither input passing through `computeLeagueDelta`), and *exact* rather than tolerant,
   because ranks are integers. ⇒ **when a spec's anchor moves, check what the previous anchor was
   the only reader of.**
4. ⭐ **A red-proof case for a RACE must force the race.**
   `custom-selection-lost-to-the-load-race` gave **RED then MISMATCH on two consecutive runs of
   identical code** — the worst verdict a falsifiability harness can return, because a single green
   reads as proof. Both reads land within a few ms against a local server, so the broken build lost
   the race only sometimes. `MockOptions.delay` now holds `/fantasy/leagues` back 400 ms, which
   makes the manifest win every time. It cannot mask a regression: the deferral's whole job is to
   *wait* for that read, so a correct build passes at any delay. **Measured RED on three consecutive
   runs** after the change. ⛔ `delay` is for ORDERING two reads whose relative order is the property
   under test — not a latency knob, and never a substitute for an auto-retrying assertion.

⛔ Do not "fix" a future one of these by deleting the case. A STALE case needs its anchor re-pointed
*and* re-checked for reachability; a MISMATCH needs either a break that actually changes behaviour or
an assertion that can see the one it has.

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
