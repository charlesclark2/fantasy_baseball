# NF-C-LDA-1 — the live-draft recommendation overlay (ESPN)

Builds the product NF-C-LDA-0 proved feasible: our pick recommendation, on the user's actual ESPN
draft board, from the read the spike decoded.

`best_alpha = 0`. Paid-gated, server-side. Ships behind **NF-EPIC 11's explicit GO** — see §7.

---

## 0. What shipped

| | |
|---|---|
| Extension | `extension/` — MV3, loaded unpacked; overlay + break detection + entitlement handoff |
| API | `POST /fantasy/nfl/draft-assistant` (paid gate: `require_fantasy_access`) |
| Service | `app/backend/services/draft_assistant.py` — resolve, then rank |
| Engine | `fantasy_engine/draft.py`, **restored to lock-step** with the shipping TS optimizer |
| Fix | `platform_import.espn._player_position` — the two-way-player (`Travis Hunter`) defect |
| Guards | 5 new suites, **35 RED-proven clauses**, two of them behavioural (real JS) |

---

## 1. ⭐ The premise was false when we measured it: there were TWO rankers

The epic's architecture rule is **ONE ranker** — the extension sends normalized state and our API
runs the *same* optimizer the web app runs. Checking that premise found it was already untrue.

`quant_sports_intel_models/fantasy_engine/draft.py` was **two shipped fixes behind**
`frontend/lib/draft-optimizer.ts`, plus a rounding difference:

| | |
|---|---|
| NF-D19 | tier **sizing** — merge undersized groups, split oversized ones, both scaled to `n` |
| NF-C2.1 | the **flex-seat re-basing** (`flexSeatRepl` / `seatValue` / `flexPoolDropoff`) |
| — | `Math.round(x*10)/10` (half **away from zero**) vs Python `round(x, 1)` (half-to-**even**) |

**Measured on a real 2026 `full_ppr`/12 board:** in one mid-draft state only **5 of 8** recommended
slots agreed — the Python engine surfaced a TE the TS engine did not rank at all. `score` sat
**0.05** apart on 10 of 41 sampled states while every other quantity agreed to `1e-14`, and the sort
reads that rounded value.

Nothing would have surfaced any of it. Both engines run, both return plausible recommendations, no
error anywhere — the E9.61 "two renderers of one field are two rule sets" class, aimed at the number
the product advises with. The live-draft overlay is what turns it into *"the extension recommends a
different player from the website"*.

**Python was moved onto the TS engine, never the reverse** — it is the engine users already draft
with and both its extra fixes were measured on live boards. Result: **540 recommendations across 38
draft states, field-for-field identical, zero tolerance.**

### 1.1 How the parity is kept

* `frontend/scripts/gen-optimizer-parity-fixture.mjs` regenerates the expectation **from the
  shipping engine** — real output, never hand-written (NF-C0e).
* `betting_ml/tests/test_nf_c_lda_1_optimizer_parity.py` replays it through Python and demands the
  same bytes, plus a separate clause on the *ordering* alone so a reader can tell "the sentence
  changed" from "we now recommend a different player".
* **Node is NOT on the CI path**; the committed fixture is. A test that shelled out to node would go
  green-by-skip on a runner without it — the NF1.7(a) vacuous-guard class.

### 1.2 The guard's own anti-vacuity clause earned its keep immediately

Every entry in a top-8 panel is its position's leader, so **all eight are tier 1 by construction**
— the NF-D19 tier-sizing mechanism, one of the two drifts the guard exists to catch, was untested by
the first fixture. Two deep top-N states were added.

### 1.3 A hazard matched deliberately, not endorsed

The TS engine **sorts on the rounded score**, which can collapse two candidates 0.04 apart into a
tie broken by list position (the `_vor_raw` defect `league_scoring.build_board` records). Python now
does the same, because diverging would reintroduce exactly what lock-step prevents. Changing it is a
decision for the ranker, taken in **both** engines at once — never a quiet fix on one side.

---

## 2. Resolution — and the defect the spike named

The endpoint resolves ESPN's pool onto our board through the **shipped** join
(`league_scoring._join_key`, DST franchise resolution included). Measured on the committed
172-player real-league fixture: **170/172 = 98.8% resolved, join-failure rate 0.0%** — both misses
absent from the board entirely (NF-K1 cause 3).

⚠️ **The ladder stops at the name rung on purpose.** Tier 1 (ESPN id → gsis) needs a lakehouse read,
and a wide DuckDB read in this Lambda is both slow and a documented silent-empty hazard
(E9.26b / E5.10) — on a live draft clock that is the wrong trade. It is also **unnecessary**: the
name rung alone reaches the full 98.8%; tier 1 adds cross-validation, not coverage. The report says
`tier1: "not_attempted"` — a NAMED state, never a `0` that would read as "the id rung resolved
nothing" (NF1.7(a)).

### 2.1 `Travis Hunter` — fixed, with a measured blast radius

A two-way player's `eligibleSlots` span both sides of the ball, so the derived set is not a
singleton and the old code returned the **alphabetically** first member. His real 2025 row
(`defaultPositionId` 3 = WR; slots `[3,4,5,23,7,20,21,12,14,15]` ⇒ `{WR, CB, DB, DP}`) derived as
**CB** and dropped out of the join — exactly 1 of 1,027 draftable rows, and a premium pick.

The fix adds `defaultPositionId` as a **tie-break among positions `eligibleSlots` already
established**. That keeps the NF-C0 §4c trap structurally out of reach — for an ordinary player the
set is a singleton and the table is never consulted, so Kittle stays TE and Mahomes stays QB.

**Blast radius, measured over 7 seasons of the real ESPN pool (45,541 rows with a derivable
position): 3 rows change.** 2019 Tremon Smith CB→RB, 2020 Cordarrelle Patterson RB→WR, 2025 Travis
Hunter CB→WR. The 19,383 single-position rows are untouched *by construction*; no IDP row moves.

⚠️ The obvious alternative — fixing the ordering to be by slot id — was measured first and
**rejected**: it changes **4,936** rows, almost all IDP. It happens to fix Hunter (slot 4 < slot 12)
but only because offensive slot ids are numerically lower, which is an accident rather than a rule.

### 2.2 Name ambiguity: implemented, and honestly labelled

Rule (b) — *ambiguity is an UNRESOLVED, not a coin flip* — is enforced: two pool rows claiming one
board row resolve for **neither**. It is **defensive, not urgent**, and the record says so: the
spike measured 10 such collisions against ESPN's ~11,600-row *whole universe* and **ZERO** against
the 1,027-row real *draftable* pool this endpoint receives. A larger population **overstated** the
risk. The rule stays because it costs nothing and its failure mode is silent; `collisions` in the
report is what would say the situation had changed.

---

## 3. Break detection — the story's headline property

> "We can't read your draft" must never look like "nothing has happened yet."

A draft assistant fails inside a once-a-year two-hour window, and its characteristic failure is a
read that quietly stops advancing while the overlay keeps rendering the recommendation that was true
four picks ago. Those two states are otherwise **pixel-identical**, and the wrong one is confidently
wrong advice on a decision the user cannot take back.

* The panel always names **which pick it is reasoning about**. Compared against ESPN's own counter,
  a freeze is visible in one glance — nothing derivable from the recommendation itself can do that.
* The verdict is `OK` / `DEGRADED` / `BLOCKED`, **derived from what was observed**, and every
  degraded state names itself: pre-draft lobby, stalled stream (with the elapsed seconds *and* the
  pick it is stuck at), disconnected socket, "we can't tell which team is yours".
* A **BLOCKED** read shows **no recommendations at all**. A stale "best available" list is worse
  than none — it is wrong in exactly the way the user cannot check.
* A failed API call **clears** the previous advice rather than leaving it on screen looking current,
  and prints the named reason (`signed_out`, `not_subscribed`, `network`, …) in its place.

Proven behaviourally by `extension/tools/state_red_proof.mjs`, which drives the real
`draft-state.js` through every one of those states and asserts each gets a *distinguishable*
verdict — with a RED proof that deleting the staleness check makes a stalled read report healthy
again.

---

## 4. Compliance

### 4.1 Toward ESPN — the context split

The spike could state its rule as "this extension issues no requests at all". The overlay must ask
our API for a recommendation, so the rule is kept where it bites — by **separating contexts**, not
by relaxing the token list. The ESPN-context scripts (`main-world-probe`, `content`, `draft-state`,
`overlay`) may originate **nothing**; `background.js` has no ESPN page context and no ESPN host
permission, and reaches `api.credencesports.com` alone.

`test_nf_c_lda_0_extension_red_line.py` was **re-anchored, not weakened** (E9.60), and now pins the
*exhaustiveness of the classification itself*: a new file in `extension/src/` that belongs to
neither context fails the build, so it cannot silently fall out of both suites (INC-38 — a
per-caller rule fails exactly where its registry is incomplete).

### 4.2 Away from the browser — the wire

`extension/src/wire.js` **rebuilds** the outbound body from an allowlist. Nothing is forwarded,
spread or cloned. `wire_red_proof.mjs` drives it with a state polluted by every credential-shaped
thing a live capture has actually carried — `espn_s2`, a SWID, the socket's short-integer
`draftSecurity` token, raw bodies, request headers, PII — and asserts none survives, then replaces
the rebuild with a passthrough and asserts the leak clause fires.

The server states the same contract independently: `DraftAssistantRequest` is `extra="forbid"`, and
the `espn_settings` path runs through the shipped `parse_settings_payload`, which applies
`assert_no_credentials` **before** parsing.

### 4.3 The session token

The extension reads the user's **own Credence** session from **our own** origin's `localStorage` and
hands it to the background worker, which keeps it in `chrome.storage.session` (in-memory, cleared on
browser close). The handoff is `sender.origin`-checked — that field is set by Chrome, not by the
page.

⛔ **This is not the §3(c) loophole.** §3(c) refuses a *third party's* long-lived, unscoped,
non-revocable session credential obtained with no consent screen. This is our own session, on our
own origin, from a user who installed our extension, revocable by signing out, used for exactly one
thing: authenticating them to us. Conflating the two would argue that no extension may ever
authenticate its own user.

---

## 5. A defect the guards had already missed

`recordCall`'s off-allowlist branch wrote `entry.bodyNotRead` **above** the `var entry = …` line.
`var` hoists the name but not the assignment, so `entry` was `undefined`, the write threw a
TypeError, and the function's own outer `try/catch` swallowed it.

The security property held — the body was never read, because the throw aborted everything — but the
documented one did not: *"everything off the list still records URL + count"* was false, and
off-allowlist calls were recorded **nowhere**.
`test_an_off_allowlist_body_is_recorded_as_REFUSED_not_as_unreadable` passed the whole time, because
it asserts the string `bodyNotRead` appears in the **source**.

That is why the two load-bearing new guards run the **real JavaScript** (NF-C4: assert rendered
output, not source). Fixed, and the comment now records why.

---

## 6. Operator steps

1. **`./infrastructure/lambda/deploy.sh`** — the API Lambda has **no CD** (NF-C0); merging the PR
   ships the frontend changelog and nothing else. The endpoint does not exist in prod until this
   runs. `deploy.sh` gained a step 3c copying `fantasy_engine/{__init__,league_config,draft}.py`.
2. ⭐ **NO API Gateway change is needed, and that corrects the story's own assumption.** NF3.2's rule
   is that a route is reachable *anonymously* only once its authorizer is set to `NONE` — the
   catch-all `ANY /{proxy+}` carries the Cognito JWT authorizer and an explicit route *exempts* a
   path from it. This route **requires** a token, so it wants the catch-all's authorizer. Adding
   `--authorization-type NONE` would **strip** a layer of defence rather than add one. ⛔ Do not
   create a route for it.
3. **NF-EPIC 11 GO** — confirm before any user-facing release (§7).
4. **Live pass** — load the extension unpacked against a real ESPN mock draft. CI mocks all IO and
   cannot see a browser, so the read path is UNVERIFIED against a live room until this is done. Take
   it while `inProgress=true` **and** a `fantasydraft.espn.com` socket is open; a mock league is
   deleted when the draft ends, so it must work in one pass.

### 6.1 Not verified, and stated plainly

* The overlay has **never run against a live ESPN draft room** — every JS path is proven by the two
  node harnesses over real captured shapes, which is not the same thing.
* **CORS**: MV3 background fetches to a host in `host_permissions` are not subject to page CORS, so
  no change to `main.py`'s `allow_origins` should be needed. If a live pass shows otherwise, the fix
  is to add the extension origin there — noted rather than pre-emptively applied, because an
  unnecessary CORS origin is a permanent widening bought on a guess.
* A **second operator capture** (auction format / a different league size / a different account) is
  still worth having before hardening further. Prior work on this surface was corrected twice by a
  second real account, and the pattern is documented:
  [[feedback-a-vendor-id-can-be-dense-yet-absent-for-the-cohort-that-matters]].

---

## 7. ⚠️ The compliance gate

This ships to users only after **NF-EPIC 11's explicit GO**. The spike delivered the memo; the GO is
the operator's to confirm. Everything here is merge-safe without it — the extension is loaded
unpacked by hand and is not published anywhere, and the API route is inert until `deploy.sh` runs.

The standing policy question the spike deliberately left open is **unchanged and still open**:
whether the extension may ever issue its *own* authenticated ESPN call. This story did not decide
it, did not need it, and is built so that answering "no" costs nothing. ⛔ It is a deliberate
decision with the operator, never a refactor.

---

## 8. What the first live draft found (2026-08-19)

The overlay ran a full 15-round ESPN mock end to end — the runtime gate the CI suites structurally
cannot reach. The **read** held (856 of 1,027 players matched, the pick counter tracked ESPN's own,
no stale-advice window), and the **ranking** was wrong twice. Both defects were in
`fantasy_engine/draft.py` *and* `frontend/lib/draft-optimizer.ts`, i.e. they had been shipping on the
website the whole time; the parity harness had faithfully kept the two engines identical, defects
included. **Parity proves agreement, never correctness** — that is why the fixes carry their own
guard file (`test_nf_c_lda_1_roster_constraints.py`) rather than relying on the parity fixture.

### 8.1 An IR spot is not a pick

K/DST are deliberately `deferred` — sunk below every real candidate — and lifted back by the reserve
constraint the moment `picks_remaining <= open_starter_count`. That composition is what makes
absolute deferral safe, so the constraint is load-bearing, not a nicety.

`translate_roster` maps ESPN slot 21 (**IR**) to bench depth, and the pick count summed *every* slot:

```
ESPN's own roster limit in that draft room: 15
  IR counted (as shipped)  roster=17   13 picks made → 4 left, 2 mandatory open → must_fill = False
  IR counted (as shipped)  roster=17   15 picks made → 2 left, 2 mandatory open → must_fill = True
  IR excluded (fixed)      roster=15   13 picks made → 2 left, 2 mandatory open → must_fill = True
```

It first turned true with the roster **already full** — never in time. The user reached his final two
picks with D/ST and K empty and was shown a backup QB and five tight ends.

⭐ **Blast radius is wider than the imports.** `defaultRoster()` ships **3 IR spots**, so every custom
league made in the app had the constraint firing three picks late too. Its docstring — "IR is a BENCH
slot, so — correctly — it adds no starter demand and cannot move replacement level" — is true of
*replacement* and silently false of the *pick count*. That is exactly the distinction
`RESERVE_SLOT_NAMES` now draws.

⚠️ The error direction is deliberate: an unrecognised slot stays **draftable**. Over-counting delays
a constraint that is inert while there is slack; under-counting fires it early and forces K/DST on a
user with picks to spare, which the constraint explicitly must not do.

### 8.2 A filled flex seat is not capacity

Bench depth is discounted because it fills no open slot, and the discount hardened on
`held >= capacity`, where `capacity` summed **every flex seat the position was eligible for** —
including one already filled by somebody else:

```
roster QB1 RB3 WR2 TE1, flex already filled by an RB
  QB: hold 1, capacity 1 → 85% penalty → a bench QB keeps 15% of its VOR
  RB: hold 3, capacity 3 → 85% penalty → a bench RB keeps 15%
  TE: hold 1, capacity 2 → 50% penalty → a bench TE keeps 50%   ← the seat is NOT available
```

A backup TE kept **3.3×** the credit of a bench back no lineup could bench him for.

⭐ The fix is a **removal, not a re-tune**: `level == 0` already means "no open slot takes this
position", so the "I still have room" case cannot arise where the penalty applies. The light branch
was reachable *only* through the miscount. Measured on the depth phase of that draft's state, the
top-25 went from 12 WR / 8 RB / 4 TE / 1 QB to 10 RB / 8 WR / 5 QB / 2 TE, ordered strictly by VOR
(Gibbs 193 now leads Chase 110; the two TEs fall to ranks 17 and 21).

### 8.3 One rule, five owners

The reserve constraint had **three** implementations (Python engine, TS engine, mock-draft CPU) and
all three carried the defect — the repo's recurring one-logical-rule-many-owners shape (INC-30,
INC-36, INC-38). The registry is now pinned, and its exhaustiveness sweep earned its keep on the
first run by finding a **fourth and fifth**: `auction-optimizer.ts::rosterSpotsOf` and
`league_config.roster_spots()`, which answer the same question for the auction reserve and answer it
the same wrong way.

⚠️ **The auction is deliberately NOT fixed here.** An IR spot cannot be bought at auction either, so
the reserve is over-stated by `n_teams × IR × min_bid` — measured on the default 12-team/$200 roster,
$216 against $180, understating every player's dollar surplus by **1.62%**. Correcting it re-prices
every published auction value and needs `build_auction_vectors.py` re-run and the artifacts
republished. It is recorded in `_KNOWN_DEFERRED`, with a clause that fails if the deferral outlives
the defect, and carded as a follow-on rather than smuggled in as a ride-along.

### 8.4 Not fixed, and why

* **Injury status.** The board carries a projected-games figure, but for the rookie the operator
  flagged it reads **13.6** — a generic availability prior — inside an 18.5–330.9 interval, i.e. "no
  idea", not "he is hurt". The NF-W2 injury line (SHIP ×4) is a *weekly, in-season* designation feed;
  a preseason board needs a return-timeline input we do not ingest. Carded.
* **Strategy toggles** (skip a backup QB/TE). Most of the observed symptom was §8.2, so the right
  order is to fix the mechanics first and re-judge whether the preference is still wanted. Carded.
* **Capturing finished drafts.** A new persistence surface, not a patch: today the extension sends
  state and stores nothing, and storing it crosses the line the red lines were drawn around. Carded.
