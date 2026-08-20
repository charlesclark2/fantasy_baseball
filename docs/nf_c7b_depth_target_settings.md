# NF-C7b — depth targets are a saved setting, and the extension can read them

**Status: SHIPPED.** NF-C7 gave the draft optimizer a per-position depth target and stored it in the
browser. This gives it two real homes and closes a gap NF-C7 shipped.

## The gap

NF-C7 wired `depth_targets` into `recommend()` and into both web surfaces. **The Chrome extension
path never passed one.** `POST /nfl/draft-assistant` → `recommend_for_state(...)` forwarded
`board, config, pool, drafted, mine, top_n` and nothing else, so for extension users the feature was
simply absent — no error, no fallback, no signal.

The parameter existed. Fifteen guards passed. That is the NF-C0e **wired ≠ invoked** class, and it
survived because every NF-C7 guard exercised the surface that worked. The first test in
`test_nf_c7b_depth_target_settings.py` is the one that would have caught it, and it asserts the
**answer differs** rather than that the parameter is accepted — deleting the wiring turns it red.

## What else was wrong with browser storage

The key was `nfl-depth-targets-${season}-${configName}` — season plus scoring-format *name*:

- two different leagues on the same format **silently shared one setting**;
- nothing followed the user to another device;
- the extension could not read it at all (above).

## What shipped

| level | edited on | applies to |
|---|---|---|
| **Account default** | `/settings` → Fantasy Defaults | every league with no explicit value |
| **Per-league** | `/fantasy/league-settings` | that league, on all three surfaces + the extension |
| **Ad-hoc** | the draft optimizer / mock draft setup | this browser, for a **preset**-format draft only |

Precedence: **league → account → local → none**, stated once per side and pinned by a shared
fixture.

⭐ **The extension gets this without sending anything.** `_draft_league_config` was already
resolving the caller's saved league to build the board, so the targets ride in on data already
fetched. That is what keeps the change free of the E8.6 deploy-skew hazard: a *new request field*
would have opened a window in which an un-deployed backend accepts it, ignores it and returns 200,
and the user watches a setting vanish on reload. No new field is sent, so there is no such window.

## Three decisions worth knowing about

**`None` and `{}` are different on a league, and that is the whole reason the resolver is a
function.** `None` means "never set here" and inherits; `{}` means "the user cleared this league"
and does not. Written the obvious way — `league or account` — an empty map is falsy, so clearing one
league's targets would silently restore the account default and the user could never turn the
feature off for that league. It would present as "my setting won't save" (the E8.6 silent-save
class). The shared fixture's third case pins it.

**A league value replaces the account default whole; it is not merged per position.** A merge would
make "this league wants 6 RBs" quietly inherit an account-level `TE: 3` the user never asked for
here, and no single screen would show the effective set. Whole replacement means one screen always
shows the truth.

**Inheriting is a state you can get back to.** The moment the per-league control is touched the
league becomes explicit; without an explicit way back that is a one-way door, and clearing every box
would read as "off" rather than "inherit". Both states are named on screen and both are reachable.

## One rule, two languages

Precedence has to hold in the browser and in the API Lambda. This repo has paid for one rule with
two implementations twice — E9.61's player name (upper-cased by two different passes, where a grep
of the wrong file cleared the right one) and NF-C7's own sibling, where the two draft **engines** had
silently drifted two fixes apart and recommended different players on a real board.

So the rule lives in **`betting_ml/tests/fixtures/nf_c7b_depth_target_precedence.json`** and neither
side restates it. Python asserts against it directly; TypeScript cannot be imported from pytest, so
`frontend/scripts/gen-depth-target-precedence-fixture.mjs` runs the shipped resolver over the same
cases and records its answers, which the same test also checks. The generator is deliberately **not**
on the CI path — the committed output is — so an unavailable `node` cannot silently turn the guard
green.

Building it surfaced a real divergence: the TypeScript sanitizer **clamped** an over-large count
while the Python one **dropped** it, and TypeScript did not filter unknown positions at all. Both now
drop. Unreachable from the UI either way (`NumericInput` refuses the keystroke) — which is precisely
why it had to be pinned rather than argued about.

## The load-bearing guarantee is unchanged

**A depth target can never produce an illegal roster.** A target reorders inside the level-0 cohort
and touches nothing else: `need_level` is unchanged so `must_fill` cannot see it, and the K/DST
deferral is a higher sort key. NF-C7 proved this against a target typed on the screen the user was
looking at; NF-C7b re-asserts it against one arriving from **storage**, which is a different path to
the same code and had never been tested.

## 🔴 Shipped broken, then fixed: nested `Decimal` on the read path

An account default saved fine and then **vanished** — within ~60 seconds (react-query's
`staleTime`) or on any sign-out. Reported from production; not caught by the suite.

`get_fantasy_prefs` used `_from_dynamo`, which converts `Decimal` only at the **top level** of the
map it is handed. These counts live **two levels down** (`fantasy_prefs.depth_targets.RB`), so they
came back as `Decimal` — and `sanitize_depth_targets` tests `isinstance(v, (int, float))`, which
`Decimal` is **neither**. Every count was silently dropped on READ while the WRITE landed correctly.
Fix: `_deep_from_dynamo`, the converter `list_fantasy_leagues` was already using.

⭐ **Why 18 passing tests could not see it.** Every storage test constructed a Python dict and fed it
to a Pydantic model, and **Pydantic coerces `Decimal` to `int`** — so they passed either way. They
exercised the MODEL; the defect lived in the STORE. The asymmetry was visible the whole time and
nothing looked at it: the per-league path worked (it goes through `_deep_from_dynamo`) while only the
account default broke, which is exactly the shape a store-level test would have surfaced on the
first run.

The lesson generalises past this field: **a nested numeric map read from DynamoDB needs the deep
converter, and a test that never crosses the storage boundary cannot tell you that.**
`portfolio` above escapes it only because its numbers happen to be one level deep — it is one nested
key away from the same bug.

## ⚠️ Found but not fixed

**`/settings` throws React #418 (a hydration text mismatch) on load, and it predates this story.**
Measured: removing `<FantasyDefaultsSettings />` and re-running reproduces the identical error. Its
cause is the same shape as one this story *did* hit and fix in its own component — a `useQuery`
gated on `enabled: !!accessToken` reports `isLoading: false` during SSR (disabled) and `true` on the
client's first render (fetching), so any branch on it renders different text on the two passes.
`/settings` has ~1000 lines of auth-dependent rendering and no E2E coverage at all, so finding
*which* branch is a scoped piece of work rather than a line change.

The E2E for the account-default surface therefore does **not** assert `expectNoPageErrors`, and says
so at the call site rather than dropping the clause quietly. The two draft surfaces do assert it, so
this story's own components remain covered.

## Guards

`betting_ml/tests/test_nf_c7b_depth_target_settings.py` (21), RED-proven by
`betting_ml/tests/nf_c7b_red_proof.py` — **15 deliberate breaks, all caught**, including one that
mutates the TypeScript resolver and regenerates its fixture (a break in TS that is not regenerated
lands in a file the Python guard never opens and reports a false green — E11.24 #815).

`frontend/e2e/specs/fantasy-depth-target-settings.spec.ts` (7) asserts rendered output (NF-C4),
including the two-sided case: with no account default the ad-hoc control **is** offered, without
which "the control is hidden" and "the control does not exist" would be the same passing test.

`best_alpha = 0`; nothing here claims an edge or a result.
