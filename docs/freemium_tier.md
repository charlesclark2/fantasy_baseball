# The freemium build — where the free/paid line falls, and why

**Date:** 2026-08-08 · **Branch:** `freemium-build` · **Context:** GROWTH-100 §1/§6/§14.
`best_alpha = 0`.

The one-line version: **free tells you what Credence thinks; a membership helps you decide.**

---

## 1. The boundary

The split is drawn by **capability**, not by season.

| Capability | Tier | What it is |
|---|---|---|
| `GENERIC_BOARD` | **FREE**, anonymous included | Overall + position rankings for the shipped league presets, the format-independent projections, the 80% ranges, market ADP, the player pages, Player Search, the methodology |
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

### A preset is not personalization

`/fantasy/nfl/board?config=full_ppr_3wr&size=12` is **free**. It selects one of the boards the
exporter published for everyone, so every caller asking for it gets the same bytes. A board scored
for *your* league is a different thing entirely — computed from a stored per-user config, behind
`require_fantasy_access` on `/fantasy/leagues` and `/fantasy/nfl/my-teams`. That distinction is the
whole free/paid line on this surface.

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

**The three generic endpoints are entitlement-independent.** Anonymous, free and paying callers get
byte-identical responses from `/fantasy/nfl/{manifest,projections,board}`.

That is not a nicety. It is what makes all three of these correct at once:

1. **G100-D1's CDN route** (`frontend/app/api/public/[...path]/route.ts`) may cache one copy for
   everybody.
2. **`cost_guardrails.cache_control_for`'s "same URL, two bodies" hazard cannot arise** on these
   paths.
3. **The frontend's `entitled`-keyed query cache can never strand a new subscriber** on a stale
   view.

⛔ Re-introducing any per-caller variation on those three routes invalidates all three **at once**,
and would need the CDN allowlist, the backend cache rules and the query keys revisited together.
`test_the_generic_board_is_byte_identical_for_every_caller` asserts literal byte equality across an
anonymous caller, a forged-token caller and a gateway-validated subscriber — equality rather than
"both payloads look right", because the failure this catches is an *extra field*, which every
"the free board has the numbers" assertion passes straight over.

The handlers take **no `Request` parameter at all**, which is the strongest available statement of
the same thing: a handler that cannot see the caller cannot branch on them. (The red-proof harness
had to apply a three-part patch to make one vary — that difficulty is the design working.)

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
rules) are unchanged — no new public surface was added to any of them, because Player Search and the
player pages read the *same three endpoints* that were already registered.

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
| The capability map, the quota seam, the frontend mirror | `betting_ml/tests/test_freemium_tier.py` | 48 pass |
| End to end through the real ASGI app (anonymous / forged token / gateway-validated subscriber) | same file, `test_*` above | byte-identical across all three |
| Rendered browser behaviour | `frontend/e2e/specs/freemium-board.spec.ts` | 13 pass |
| The whole frontend suite (no regression from the mock's default flip) | `npx playwright test` | 112 pass |
| Every guard is falsifiable | `uv run python betting_ml/tests/freemium_tier_red_proof.py` | **24/24 RED** |

The red-proof harness earned its keep immediately: **five clauses were vacuous on the first run.**
Two were weak assertions — one checked that a copy constant was still *imported* rather than
*rendered*, and one checked that the governed constants were *referenced* rather than that no inline
prose existed beside them — and both were rewritten. Three were insufficient breaks, one of which
was itself a finding: dropping the router-level `dependencies=[Depends(require_fantasy_access)]` left
`/fantasy/nfl/my-teams` correctly refusing, because that route carries the dependency on the function
as well. That is defence in depth working, and it is why the break now removes the entitlement at its
source.

### What is NOT proven here

- **The API Gateway authorizer.** A route that is public in code still returns 401 before the Lambda
  runs until its authorizer is set to `NONE` — per-route console config, outside this repo's IaC
  (NF3.2). See the handoff.
- **Anything about whether the numbers are right.** This is a tier and a render; the projection's own
  validation is NF1.x/NF-D*.
- **Live CDN behaviour.** The E2E mock answers before the route handler runs, by design — its
  contract is pinned in `test_g100_d1_cost_guardrails.py` and its payoff is edge behaviour no browser
  test can observe.
