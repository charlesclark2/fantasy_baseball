# NF-LEAK1 — hardening the entitlement boundary against paid per-stat reconstruction

**Date:** 2026-08-14 · **Branch:** `nf-leak1` · **Predecessor:** `docs/nf_epic1_entitlement_audit.md` §9
`best_alpha = 0`. Nothing here changes a model, a projection or a bet.

---

## ⭐ The honest framing, first — this is not, and cannot be, zero

**Any server that scores an arbitrary user-supplied scoring config against the board leaks
information about the underlying stat line by construction.** Zero every weight but one and the
returned `pts` column *is* that stat, for every player. There is no version of "score the free
user's league on the server" that does not have this property, and this story does not claim to have
removed it.

What shipped is **price and attribution**:

> The paid stat line is no longer served to a free caller (that was NF-EPIC 1), and reconstructing it
> through the league scorer now costs **≥ 20 days of sustained, uninterrupted probing from one
> account**, every step of which is attributable to a Cognito `sub`. It was **22 seconds** before.

⛔ The copy, the code and this record must not drift into "closed", "impossible" or "zero leak".
`test_no_guard_here_claims_the_leak_is_closed` makes that a mechanical property of the source rather
than an intention, and the residual is named in §6 rather than omitted.

---

## 1. What the operator ratified, and what §9 actually said

NF-EPIC 1 §9 recorded this vector and chose to bound rather than close it, on the reasoning that it
"costs ~50 authenticated round trips to walk". The PM's ratified decision (option b) is that for a
paid product, *hard to scrape* is not *safe*.

§9's estimate was in the right order of magnitude and **wrong about what it implied**, which is why
Phase 0 was the load-bearing step of this story: the number was reasoned, never measured, and the
thing that matters is not the round-trip count but the wall-clock, which nobody had computed.

---

## 2. Phase 0 — the attack, measured

`scripts/nf_leak1_reconstruction_cost.py`, run against the **real** scorer
(`app/backend/services/league_scoring.py`) and the **real** published 858-player artifact — not a
fixture, which by construction can only restate the author's assumptions.

**Target set: 38 of the 53 keys in `STAT_FIELD` carry data in the current artifact → 32,604 paid
cells.** One board scores every player, so there is no per-position cost: all positions fall out of
the same pass.

| Attacker model | writes | reads | wall-clock @ 2 req/s | recovery |
|---|---|---|---|---|
| **A** · isolation — one config per stat, every other weight 0 | 38 | 38 | 38 s | **100.00 % exact** |
| **B** · differencing — realistic baseline, then baseline + δ | 39 | 39 | 39 s | ±0.1 |
| **C** · magnitude packing — several stats per config, decoded from one `pts` | **22** | **22** | **22 s** | 99.80 % exact |

⇒ **The cheapest path cost 44 round trips and 22 seconds.** The pre-existing per-IP limiter
(`cost_guardrails`, 2 req/s authenticated) is the only thing that was in the way, and at that rate it
is not an obstacle — it is a rounding error.

Two things the measurement established that reading could not:

- **Packing is real.** Model C was not in §9's threat model at all. It works because `pts` carries
  more precision than any single stat needs, so small-range stats (safety, blocked kicks, 2-pt
  conversions) can be stacked at separated magnitudes and peeled apart.
- **Model B survives any plausibility rule.** A realistic baseline plus δ on one stat is a perfectly
  ordinary league, and differencing two *admissible* configs isolates a stat as cleanly as a
  degenerate one. **This is why an expressiveness constraint alone cannot close the leak**, and why
  the budget — not the shape rules — had to be the primary lever.

---

## 3. Pre-registration

| | |
|---|---|
| **Gate** | one free account must need **≥ 14 days** of sustained probing to reconstruct the paid line |
| **Primary lever** | a durable **per-account budget on scoring changes** |
| **Secondary** | **write-time shape rules** (non-degeneracy + weight dynamic range) |
| **Tertiary** | **probe detection** — surcharge and log a config-permutation walk |
| **Constraint** | every real league must still save, and a real user's editing must be untouched |

---

## 4. The levers as shipped

### 4a. The meter is on the **write**, not the board read

Re-reading a board without changing the config returns the same numbers — zero new information. The
channel is opened by the **config change**, so that is what is metered. Metering reads would throttle
precisely what real users do (open the page, refresh, come back tomorrow) while barely inhibiting an
attacker who needs one read per write.

And only a change to the **scoring** counts. Renaming a league, editing the roster, linking a team,
re-importing to refresh a roster snapshot — none of them move `pts`, so none are charged.
`scoring_fingerprint` makes that mechanical; it also folds in `position_bonuses`, which reach `pts`
exactly like a per-stat weight and would otherwise have been a second, unmetered door.

### 4b. Budget — `BUDGET_BURST = 12`, `BUDGET_REFILL_PER_DAY = 1.0`

Durable, on the user item (`fantasy_scoring_ledger`), **keyed on the account**. Not per-league: a
free account may hold one league but may delete and recreate it without limit, so a per-league
counter hands back a full bucket on every recreate. Not the in-memory per-IP limiter either — that
one is per-Lambda-container by its own docstring and cannot count 32 changes spread over days.

**Tuned against the attacker's measured best *surviving* plan (32 changes), not the naive one (39).**
Tuning against 39 would have set a rate the attacker beats by a third, and nothing would have said so.

### 4c. Shape rules — `MIN_CORE_STATS = 2`, `MAX_WEIGHT_RATIO = 400`

- **Core-stat rule**: a config must pay for ≥2 of `pass_yds, pass_td, rush_yds, rush_td, rec_yds,
  rec_td`. Blocks model A outright; 2 is the smallest value under which *no single-term config at any
  stat* is admissible.
- **Dynamic-range cap**: the largest/smallest non-zero weight in one config may differ by ≤400×.
  Measured real leagues: presets **150**, widest imported league **300**.

⚠️ **These do not close the leak and are not sold as if they do.** They delete the two cheap paths and
force the attacker onto model B, which the budget prices.

### 4d. Probe detection — `PROBE_TOUCH_THRESHOLD = 10`, `PROBE_SURCHARGE = 2×`

A single-stat delta from an account that has already walked 10 distinct stats *one at a time* costs
double and is logged with its `sub` (`[METRIC] fantasy_scoring_probe`). ⚠️ **Evadable** — moving two
weights per step (advance one, revert the last) isolates a stat just as well and the delta test
misses it. The headline cost below is therefore stated on the **budget alone**.

---

## 5. Result — measured before and after

| | before | after |
|---|---|---|
| cheapest admissible path | packing, 1.73 stats/change | differencing, **1.23 stats/change** |
| model A (isolation) | admitted, 100 % exact | **refused at write time** |
| model C (packing) | admitted, 99.80 % exact | **refused at write time** |
| changes to cover all 38 stats | 22 | **32** |
| **wall-clock for a full reconstruction** | **22 seconds** | **20.0 days** (40.0 if the detector fires) |
| pre-registered gate (≥14 days) | — | **MET on the floor alone** |

**Legitimate use, checked on the same run:** all **12** real configs available to check — the 8
shipped presets and the 4 captured real imported leagues (two ESPN, one Yahoo) — still save. A free
user gets 12 scoring changes immediately and 7/week thereafter, against a real setup session of ~5.

### Two defects the harness caught that reading did not

1. **The first `MAX_WEIGHT_RATIO` was 10⁴ and made the attack *cheaper*** — packing improved from
   1.73 to 2.11 stats/config. `LeagueSave` already bounds `|w| ≤ 1000`, which for a config whose
   smallest weight is ~1 already implies a ratio ceiling of ~10³, so the "new guardrail" was a
   loosening. **A range rule is only a guardrail below the range the system already enforced** —
   measure a proposed limit against the status quo, never against zero. Pinned by
   `test_the_dynamic_range_cap_is_tighter_than_what_the_system_already_enforced`.
2. **`MIN_CORE_STATS` shipped as 4 on reasoning that measured false.** The argument was that forcing
   more big-range stats into the config would consume the window a packed place needs. It does not:
   the attacker differences against their own baseline and the core terms cancel exactly. Measured at
   1, 2, 3, 4 and 6, the surviving attack is **identical** (32 changes, 1.23 stats/change, 92.22 %
   exact) — so every threshold above 2 was pure false-refusal risk for zero protection, and one of
   them would have refused an existing test's league. **Ship the weakest rule the measurement
   supports.**

---

## 6. The residual — bounded, not closed

| Residual | Why it stands |
|---|---|
| **Fresh accounts.** Signup is free, instant and self-serve, so ~32 accounts buy the same reconstruction in one pass. | Bounded by the per-IP limiter and the email-OTP signup path, and every probe is attributable — but it is a **cost, not a wall**. This is NF-EPIC 1 §8's own point, inherited rather than solved. |
| **The detector is evadable.** Two weights per step defeats the delta test. | Deliberate: the budget floor (20 days) does not depend on it. |
| **The budget fails open.** An unreadable or undeliverable ledger lets a change through, logged as `[METRIC] fantasy_scoring_ledger_write_failed=1`. | The alternative turns a DynamoDB blip into "saving is broken" for a real user (E8.6). A *run* of that metric means the budget is not being enforced and is worth an operator look. |
| **A subscriber is exempt.** | They can `GET /fantasy/nfl/projections/full` and receive the whole stat line in one request. Metering them protects nothing and degrades what they paid for. |

⇒ The defensible sentence is **"the substrate is not served to a free caller, and reconstructing it
through the scorer is slow, shaped, surcharged and attributable"** — never "reconstruction is
impossible".

---

## 7. Guards

`betting_ml/tests/test_nf_leak1_scoring_probe_guard.py` — **35 tests**, two-sided: the attack is
priced out; real leagues and real editing are untouched; the failure modes (a refusal must not spend
a token, an unreadable ledger must not lock a user out, the read path must never run the write rules)
are pinned; and the record is forbidden from overclaiming.

`betting_ml/tests/nf_leak1_red_proof.py` — **32/32 breaks turn their named clause RED**, with every
named test verified PASSING on unmutated source first. The first three cases delete the enforcement
entirely (the pre-fix world), so the story cannot be decoration.

### The red proof was itself vacuous on its first run, and that is the transferable lesson

It reported **31/31 RED and not one case had executed.** `run_one` selected tests by the node id
`file::test_name`; every test here lives in a class, so pytest matched nothing, exited **4** ("no
tests ran"), and a non-zero exit was read as RED. A harness that certifies itself while measuring
nothing — the exact shape it exists to catch (E11.24 #682).

**Fix, and the rule for any future red proof:** select class-agnostically (`-k`), treat *no tests
ran* as its own status rather than as a failure, and **verify each named test PASSES on unmutated
source before trusting its later failure** — "it went red" is only evidence if it was green first.

Running it honestly then surfaced **7 genuinely vacuous guards** in the first cut of the suite,
each fixed by fixing the fixture:

| Vacuous guard | Why it could not fail |
|---|---|
| packed-probe refusal | the fixture was *also* degenerate, so the core rule refused it and deleting the ratio cap changed nothing — **NF-D17 verbatim** |
| refusal-does-not-charge | drained to exactly zero first, where `max(0.0, …)` makes "unchanged" and "decremented" the same number |
| ledger size bound | the fixture's edits were two-key deltas, which the counter ignores, so the bound was never approached |
| probe-walk surcharge ×2 | the "walk" replaced the previous stat each step — a two-key delta, i.e. the documented *evasion*, not a walk |
| first-few-tweaks not flagged | the baseline was a 9-term stub; the defect only reproduces at a real league's ~28 terms |
| failed ledger write | asserted on a throttling outcome a log line cannot change |
| the whole overclaim scan | flagged the module's own **prohibition** ("nothing here may claim the leak is closed") — a forbidden-phrase scan must exclude the lines that forbid it |

---

## 8. Deploy — this is not shipped by merging

⚠️ `app/backend/**` has **no CD**. The PR merging changes nothing in production; the API Lambda ships
only via `./infrastructure/lambda/deploy.sh` (NF-C0). Until that runs, the pre-fix cost stands.

Response shapes are **additive** (NF-C0): success payloads are untouched; the new outcomes are a
`400` on a config that could never be a league and a `429` with `Retry-After` on an exhausted budget,
both on endpoints that already return `4xx`. No frontend change ships with this, and no changelog
entry is warranted — no visible change to legitimate free editing.

**Post-merge operator steps** are in the handoff.
