# The freemium build — where the free/paid line falls, and why

**Date:** 2026-08-08 · **Branch:** `freemium-build` · **Context:** GROWTH-100 §1/§6/§14.
`best_alpha = 0`.

The one-line version: **free tells you what Credence thinks; a membership helps you decide.**

---

## 1. The boundary

The split is drawn by **capability**, not by season.

| Capability | Tier | What it is |
|---|---|---|
| `GENERIC_BOARD` | **FREE**, anonymous included | Overall + position rankings scored for **one** league preset (full-PPR, 12 teams), the format-independent projections, the 80% ranges, market ADP, the player pages, Player Search, the methodology |
| `PERSONALIZATION` | PAID | A board re-scored for the caller's **own** saved league — their scoring, roster shape and size; VOR against that roster; saved state |
| `DECISION_SUPPORT` | PAID | The draft optimizer, and the weekly tools as they land |

One map, one place: `app/backend/services/entitlement.py::Capability` / `FREE_CAPABILITIES` /
`PAID_CAPABILITIES`, mirrored in `frontend/lib/entitlements.ts` and pinned in both directions by
`betting_ml/tests/test_freemium_tier.py`.

**Written as capabilities rather than as a list of route paths on purpose.** A path list has to be
re-derived every time a surface is added or renamed, and getting it wrong fails silently in the
dangerous direction: a new personalized endpoint nobody remembered to add is free by default.
Naming the capability forces the question "which half is this?" at the point a route is written.

Both sets are also spelled **longhand** rather than derived from each other. `PAID = all − FREE`
makes a forgotten capability silently paid; the reverse spelling makes it silently free. Neither
default is acceptable, so a new capability belongs to neither set until someone places it — and
`test_every_capability_is_placed_on_exactly_one_side` says so.

### One preset is free, thirteen are the membership

`Capability.GENERIC_BOARD` says a caller may read the generic board. **Which one** is a second
question, answered by two constants:

```python
FREE_BOARD_CONFIG = "full_ppr"
FREE_BOARD_SIZE = 12
```

`/fantasy/nfl/board?config=full_ppr&size=12` is free for everyone. The exporter publishes 7 scoring
presets × 2 league sizes; the other 13 boards answer **403** to an unentitled caller.

**Why that preset, and it is a data fact before it is a pricing one.** The ADP column we show beside
our number is an FFC **12-team PPR** sample (`nfl/fantasy/benchmarks/adp_benchmark`). At any other
preset our points and the market's ADP describe *different leagues*, so the one comparison the free
board exists to support is only honest here. Moving the free selection means moving that sample too.

**Both coordinates matter.** League size sets the replacement level, so `full_ppr`/10 is a different
set of numbers rather than a relabelling — a gate written against the scoring format alone would
leave the size control offering a combination the API refuses. That is the failure an implementation
naturally produces, so it has its own clause and its own red-proof case on both sides.

A **403, not a redacted 200.** E9.56's lock existed to draw a per-cell CTA on a board the visitor had
asked for; here the client keeps them on the free board and states the boundary at the control, so a
lock payload would be an elaborate description of a page nobody is looking at. It also keeps the
answer unambiguous for the CDN.

### A preset is still not personalization

A board scored for *your* league is a different thing again — computed from a stored per-user
config, behind `require_fantasy_access` on `/fantasy/leagues` and `/fantasy/nfl/my-teams`. Selecting
`half_ppr` from a menu is a **preset**; VOR against your actual starting requirements is
**personalization**. The paid tier now contains both, and they are sold as separate lines because
they are separate things: one is "the format you actually play", the other is "your league".

### The G100-C1 seam

G100-C1 will grant a free account **one** personalized league. This story does not build that; it
leaves a boundary the grant is expressible in:

```python
FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "0"))
```

A **count**, not a `free_personalization: bool` — a boolean cannot express "one league but not
five", so G100-C1 would have had to *replace* the predicate, and replacing an entitlement predicate
is exactly when a surface quietly falls out of its gate. Nothing reads it to grant access today, and
the default of 0 is pinned so raising it is a reviewed edit rather than a drift.

---

## 2. ⭐ The invariant three other systems rest on

**Every FREE response is entitlement-independent.** Anonymous, free and paying callers get
byte-identical responses from `/fantasy/nfl/manifest`, `/fantasy/nfl/projections`, and the free board
URL `/fantasy/nfl/board?config=full_ppr&size=12`.

That is not a nicety. It is what makes all three of these correct at once:

1. **G100-D1's CDN route** (`frontend/app/api/public/[...path]/route.ts`) may cache one copy for
   everybody.
2. **`cost_guardrails.cache_control_for`'s "same URL, two bodies" hazard cannot arise** on these
   paths.
3. **The frontend's `entitled`-keyed query cache can never strand a new subscriber** on a stale
   view.

⛔ Re-introducing per-caller variation on a **free** URL invalidates all three **at once**, and
would need the CDN allowlist, the backend cache rules and the query keys revisited together.
`test_the_free_generic_board_is_byte_identical_for_every_caller` asserts literal byte equality across
an anonymous caller, a forged-token caller and a gateway-validated subscriber — equality rather than
"both payloads look right", because the failure this catches is an *extra field*, which every
"the free board has the numbers" assertion passes straight over.

`nfl_manifest` and `nfl_projections` take **no `Request` parameter at all**, which is the strongest
available statement of the same thing: a handler that cannot see the caller cannot branch on them.

### ⚠️ The paid board URLs are the deliberate exception

`nfl_board` **does** read its caller — one preset is free and thirteen are not — so a paid board URL
answers 200 or 403 depending on who asks. Three consequences, each held by a clause:

1. **The CDN cannot reach one.** The public route strips `Authorization` unconditionally, so any
   board it fetched would be fetched anonymously; left proxyable, a subscriber's request for
   `half_ppr` would write a **403 into a public CDN entry** and serve it to every subscriber for the
   window. So its `config`/`size` patterns are pinned to the free selection — the edge cannot ask a
   caller-dependent question rather than being trusted not to.
2. **`cache_control_for` is path-keyed and cannot see `config`**, so one rule covers both. It is
   safe for two *separate* pre-existing reasons — an authorized request is `private`, and a non-200
   is `no-store` — and losing either is a breach rather than a caching regression, so both are
   asserted directly.
3. **The client is steered, not merely refused.** An unentitled visitor is defaulted onto the free
   board and a stored paid selection is re-checked against it, so the 403 is a backstop rather than
   something a normal visit meets.

---

## 3. What was retired, and what it means for the code that stayed

E9.56 locked the current season **everywhere**: a non-entitled caller received each row with its
public identity and market ADP, every model value removed, `locked: true` in its place, and the
array re-sorted onto ADP so the index could not reconstruct our ranking.

That machinery still exists in `entitlement.py` and is still unit-tested, and **no live route calls
it**. Read it as the mechanism for withdrawing the open board if that decision is ever taken, not as
a description of what users receive.

Two things make "retired" a fact rather than a comment:

- `test_e9_56_entitlement.py::test_the_locked_redaction_is_retired_from_every_live_route` asserts on
  the **router source**, so re-wiring the lock fails immediately rather than only once some payload
  happens to be exercised.
- `e2e/specs/locked-surfaces.spec.ts` still runs, under an explicit `entitlement: "locked"` mock
  mode. The components keep their `locked` branches — a row arriving without `pts` must render a
  chip, never `NaN` — so withdrawing the board would be a config decision, not a rebuild.

The **response envelope survives the flip** rather than being deleted. The deployed frontend branches
on `locked`/`entitled`, the API Lambda ships only via a manual `deploy.sh`, and the two halves cross
over in an order nobody controls. Every caller now gets `locked: false, entitled: true`, which the
already-deployed client renders as the full board with no change at all. Dropping the keys would be
the NF-C0 break in its original form.

### `LOCKED_SEASON` still exists and no longer means "paid"

It now means *"the season with no graded outcomes yet"* — a season that has not been played has
nothing to grade a projection against. That is why `export_track_record_json` refuses to emit it and
why `fantasy_public._LOCKED_SEASON` bounds the public receipts route. Both are statements about data
existing, not about entitlement.

---

## 4. The boundary in the UX

`FreemiumBoundary` (`components/fantasy/shared.tsx`) renders on Rankings, Projections and each
player page, **below** the complete board.

Position is the argument. A visitor has to see that nothing is withheld before "this is the generic
one" means anything; at the top it reads as a paywall on a page that has none.

It is **not** an `UpgradeBanner`. That component sits above a board whose numbers are withheld and
says "subscribe to unlock" — a lock, with lock iconography to match. Nothing is withheld here, and
telling a visitor the complete board in front of them is partial is both false and a weaker pitch
than the truth.

Every string comes from `fantasy-claim-copy.ts`, including the section heading and the button label.
Those two are chrome rather than claims and they live there anyway, because the guard cannot
distinguish a heading from a promise — and an exception list for "just a heading" is how the first
claim gets typed into a component.

### The format lock is stated AT the control

The boundary block explains the tier; the **pickers** are where a visitor meets it. Every preset is
listed, the paid ones disabled and suffixed `· Members`, with `FORMAT_LOCK_EXPLANATION` underneath.

**Listed-but-disabled is the deliberate choice**, and the alternative is tempting enough to have its
own red-proof case: removing the paid presets satisfies "an unentitled caller cannot select one"
completely, and makes the free board look like the only board we publish — untrue, and the reverse
of what an upgrade prompt is for.

**And a refusal must not read as a failed search.** A 403 arriving as zero rows previously rendered
*"No players match — try clearing the search box"*: a paywall described as a typo, reachable through
a stale stored selection or the NF-C0 skew window, i.e. exactly when a wrong message costs most.
The board's error is surfaced now and has its own branch.

### ⚠️ Copy that describes an entitlement goes stale silently

`FREE_TIER_SUMMARY` read *"scored for the common league presets"* — accurate while all 14 boards were
free, false the moment this landed, and **invisible either way**, because nothing renders differently
when a sentence stops being true.

It now names no format at all. That is a correctness constraint rather than a style preference: the
block also renders on **Projections**, which is format-*independent*, so any sentence about full-PPR
at twelve teams would be false on one of the two pages showing it. The format scope lives on the
controls it constrains (`FORMAT_LOCK_EXPLANATION`) and in the paid summary, both asserted separately.

---

## 5. The full-season rate

`expected_pts × 17 ÷ expected_games`, rendered immediately beside the expected total on the
rankings, the projections and the player page.

Our headline number is availability-weighted: the chance a player misses games is already multiplied
through it. That is the honest number and it stays the headline — but it answers only one of the two
questions a drafter has. The other, *"what is he worth in the weeks he plays?"*, is what makes two
players comparable when their injury risk differs.

**No model run.** Both inputs are already in the served payload; dividing one by the other is
arithmetic on numbers the page already shows.

⛔ **It must never feed VOR, the board ordering, tiering or the optimizer.** Ranking on a full-slate
rate ranks players as if availability did not exist — it systematically promotes exactly the players
the projection discounts on purpose — and because it *reorders the board* it stops being a UI change
and becomes a model decision subject to the whole-board placement gate (the NF-D18/NF-D20
`CONSTRAINT_REFUSED` class), which carries its own pre-registration.
`test_the_full_season_rate_never_reaches_a_scoring_or_ordering_module` holds that line.

**The null guard is the part that would have shipped broken.** `games === 0` yields `Infinity` —
which is a `number` in JS, so it survives every `!= null` check a caller might write and prints "∞"
beside a points column; an absent `g` yields `NaN`. Neither is visible to `tsc`, because a missing
field type-checks as its declared type at runtime. `fullSeasonRate` returns `null` for zero, absent,
non-finite and negative inputs, and callers render that as an em-dash. The e2e fixture builder
deliberately plants three degenerate rows (`g: 0`, `g: null`, `g` absent) and the spec asserts all
three render a dash — a fixture where every row is healthy cannot see this, and it is exactly the
fixture anyone would write by hand.

**What the label may not claim.** It is our own projection divided by our own expected games — not
reconciled against anyone else's published "if he plays every week" figure, and still conservative at
running back, where the residual miscalibration `EXPECTED_POINTS_NOTE` refuses to bury has not gone
anywhere. `FULL_SEASON_RATE_DEFINITION` says both, and a guard holds each clause.

---

## 6. Cost

Nothing here adds per-view compute to a free path. The three generic reads are single S3
`GetObject`s of pre-built blobs, and G100-D1's CDN serves the anonymous path from the edge.

The three registries a new public surface must join (CDN allowlist, degrade floor, public cache
rules) gained no new *surface* — Player Search and the player pages read the same three endpoints
already registered. The CDN allowlist's `board` entry was **narrowed**, not widened: its `config`
and `size` patterns now match only the free selection, so the edge can reach exactly one board.

**The paid presets cost nothing extra either.** They are the same pre-built S3 blobs, served to
entitled callers straight from the Lambda as they always were — one `GetObject`, no compute — and an
unentitled request is refused before the read happens.

**One follow-up, deliberately not taken here.** Now that the generic reads are entitlement-
independent, routing signed-in callers through the CDN too would be *safe* and would remove one
Lambda invocation per view for every logged-in free user. It is a serving change rather than a UI
un-gate, and it moves paying users onto a cache whose 900 s staleness window was chosen for
anonymous traffic — so it is carried as a follow-up rather than smuggled in. The `token ? … : …`
split in `lib/fantasy.ts` is where it would land.

---

## 7. Verification

| Layer | Instrument | Result |
|---|---|---|
| The capability map, the free preset, the quota seam, the frontend mirror | `betting_ml/tests/test_freemium_tier.py` | 72 pass |
| End to end through the real ASGI app (anonymous / forged token / signed-in non-subscriber / gateway-validated subscriber) | same file | free URLs byte-identical across all four; paid presets 403/200 |
| Rendered browser behaviour | `frontend/e2e/specs/freemium-board.spec.ts` | 20 pass |
| The whole frontend suite | `npx playwright test` | 119 pass |
| Every Python guard is falsifiable | `uv run python betting_ml/tests/freemium_tier_red_proof.py` | **45/45 RED** |
| Every new e2e clause is falsifiable | `frontend/e2e/red-proof.mjs` (12 freemium cases) | **12/12 RED** |

The red-proof harness earned its keep twice. On the freemium build's first run **five clauses were
vacuous**; on the format-split's first run, **three more**.

Of the eight, four were weak assertions and all four had the same shape — *asserting a NAME rather
than the thing the name refers to*. One checked a copy constant was still **imported** rather than
**rendered**; one checked the governed constants were **referenced** rather than that no inline prose
sat beside them; one checked an identifier `storedIsFree` **existed** rather than that it held the
comparison it is named for (replacing the whole expression with `= true` left the name in place and
the guard green). A name is the last thing an edit removes, which is exactly why grepping for one
proves so little.

The other four were insufficient **breaks**, and three of those were findings rather than gaps —
each stayed green because a *different* layer was correctly still refusing: dropping the
router-level `dependencies=[Depends(require_fantasy_access)]` left `/fantasy/nfl/my-teams` refusing
(the route carries the dependency on the function too); forcing a token "verified" left the groups
coming from a separate verified decode; reading groups via `dependencies._groups_from_request` hit
E9.56's hardening, which falls back to a verified decode whenever the authorizer context is absent.
Defence in depth working, three times. The fourth was an anchor collision: `allows_board` ends with
the identical `return bool(ent and ent.fantasy)` as `allows` and is defined first, so a
first-occurrence patch broke the wrong function.

### What is NOT proven here

- **The API Gateway authorizer.** A route that is public in code still returns 401 before the Lambda
  runs until its authorizer is set to `NONE` — per-route console config, outside this repo's IaC
  (NF3.2). See the handoff.
- **Anything about whether the numbers are right.** This is a tier and a render; the projection's own
  validation is NF1.x/NF-D*.
- **Live CDN behaviour.** The E2E mock answers before the route handler runs, by design — its
  contract is pinned in `test_g100_d1_cost_guardrails.py` and its payoff is edge behaviour no browser
  test can observe.
