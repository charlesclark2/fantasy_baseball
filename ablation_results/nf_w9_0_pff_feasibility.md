# NF-W9-0 — PFF data-access feasibility spike

> ## ✅ RESOLVED — GO. The answer is `&export=true`, and `routes` is confirmed.
>
> **VERDICT: GO. NF-W9-1/2/3 are unblocked, on the current subscription, with no browser
> automation and no manual downloads.**
>
> The full field set is one query parameter away. The identical endpoint, identical params, plus
> `&export=true`, returns a 44-column **CSV** instead of the 19-field JSON:
>
> ```
> https://premium.pff.com/api/v1/facet/passing/summary?league=nfl&season=2025&week=1,…,18&export=true
> ```
>
> It carries every field the JSON reports as `restricted` — `avg_depth_of_target`,
> `aimed_passes`, `dropbacks`, `passing_snaps`, `epa`, `pressure_to_sack_rate`, and the grades.
> Validated against a real operator export: 44 columns parse, `player_id` is preserved (so the
> 100% NFL entity resolution is unchanged), blanks stay `None` rather than becoming fabricated
> zeros, and the raw-stats guard strips exactly the 4 `grades_*` columns.
>
> **And `week=` takes a LIST**, so a whole season is ONE request: ~1 call per (league, season,
> facet) — or one per week for weekly grain — against the 2,176 per-game calls first sized, and
> against the manual CSV downloads this story set out to replace. No Selenium, no browser
> automation, no bulk download.
>
> Implemented as `client.get_export()` / `facets.fetch_facet_export()`.
>
> ### ✅ `routes` CONFIRMED (2026-08-19) — NF-W9-1 has its substrate
>
> The receiving export carries **47 columns**, including every opportunity field: `routes`,
> `route_rate`, `pass_plays`, `avg_depth_of_target`, `slot_rate`/`slot_snaps`,
> `wide_rate`/`wide_snaps`, `inline_rate`/`inline_snaps`, `yprr`, `yards_after_catch`,
> `avoided_tackles`, `contested_targets`.
>
> **And it does the job NF-W9-1 needs.** Measured on the real export, `pass_plays` + `routes` +
> `targets` decompose the zero atom that NF-W6d/W7c–f identified as marginal:
>
> | player | pass plays | routes | route % | targets | tgt/route |
> |---|---|---|---|---|---|
> | Ja'Marr Chase (WR) | 669 | 632 | 94.5% | 182 | 0.288 |
> | Jake Matthews (T) | 610 | **1** | **0.2%** | 1 | — |
> | Julius Chestnut (HB) | 22 | 19 | 86.4% | 2 | 0.105 |
> | Andre Baccellia (WR) | 72 | 71 | 98.6% | 4 | 0.056 |
>
> A tackle on the field for 610 pass plays who ran **one** route, and a back who ran 19 routes
> and drew 2 targets, are **both a bare zero in nflverse** — which has snaps and targets but no
> routes. They are different events. Route participation spans 0.2%→98.6% and, among actual
> route-runners, targets-per-route spans 0.056→0.288 (a 5× spread). So this factorises
> P(target) into **P(on field) × P(runs a route | on field) × P(targeted | route)**, the first
> two of which nflverse cannot express at all.
>
> `rushing/summary` likewise confirms NF-W9-2's list: `yards_after_contact`, `yco_attempt`,
> `gap_attempts`, `zone_attempts`, `breakaway_attempts`, `designed_yards`, `elusive_rating`.
>
> ---
>
> ### The earlier retraction, kept for the record
>
> **The "the subscription tier withholds every field" verdict below is RETRACTED.** It was wrong.
>
> The operator's `passing_summary.csv`, exported from the PFF UI on the same account, contains
> **all 28 of the 28 fields** the per-game JSON listed as `restricted` — `avg_depth_of_target`,
> `aimed_passes`, `dropbacks`, `passing_snaps`, `epa`, `btt_rate`, and every `grades_*` column.
> The account HAS the data.
>
> `restricted` is therefore **not an account entitlement**. It is a per-response field set: the
> `/api/v1/facet/*` JSON API serves a REDUCED set, and the CSV export serves the full one.
> Measured across three query shapes, the reduction is universal and identical:
>
> | Path | `routes` / `adot` / grades |
> |---|---|
> | NFL per-game JSON (`?game_id=`) | ✗ |
> | NFL season-aggregate JSON (`?league=&season=&week=`) | ✗ (adds only 4 metadata fields) |
> | NCAA season-aggregate JSON | ✗ |
> | **NFL CSV export (UI)** | ✅ all 28 |
>
> **The tell I should have caught and didn't:** the `restricted` list contained `grades_offense`
> and `grades_pass`. PFF's entire consumer product *is* the grades — a premium subscription that
> withholds them is not a plausible reading, and I had the evidence to falsify my own conclusion
> at the moment I formed it. I treated a field named `restricted` as self-explanatory instead of
> testing what it meant. Everything measured below is accurate; the INFERENCE drawn from it was
> not, and it was the load-bearing one.
>
> **Corrected status:**
> * §2 (entity resolution) — **unaffected and still a GO.** NFL 100%/100%, NCAAF 97.1%/100%,
>   `SAME_ID_SPACE` confirmed. That work stands entirely.
> * §3 (auth mechanics) — **unaffected.** Clerk, 60s JWT, handshake, 431, DataDome all hold.
> * §1 + §6 (entitlement + "do not card NF-W9-1/2/3") — **RETRACTED.** The stories are not
>   blocked by a paywall.
> * **OPEN:** which path serves the full field set. The export request has not yet been captured
>   (the first attempt caught Clerk's `/touch` heartbeat, which fires every ~50s regardless of
>   what is clicked). Until it is, the automated ingest has no target — an ENGINEERING task,
>   likely small, not a purchase decision.
>
> Read §1 and §6 below as the superseded record of how the wrong call was reached, not as
> guidance.


**Verdict: the join is a GO; the DATA is a NO-GO on the current subscription tier.**

Both halves are now **measured against the live PFF API** (2026-08-18, operator credential).
They point opposite ways, and that split is the deliverable:

| Question | Answer | Evidence |
|---|---|---|
| Can we authenticate and pull? | ✅ **YES** | 32 NFL + 116 NCAAF games, 6,279 facet rows pulled live |
| Can we join PFF to our ids? | ✅ **YES, essentially perfectly** | NFL **100%** players / **100%** games; NCAAF **97.1%** / **100%** |
| Is nflverse's `pff_id` PFF's `player_id`? | ✅ **CONFIRMED — same id space** | 99.72% of live PFF ids found in our map |
| **Do we get the fields NF-W9-1/2/3 need?** | ✅ **YES — via `&export=true`** | receiving export = 47 cols incl. `routes`, `route_rate`, `pass_plays`, `adot`, `slot/wide/inline` splits, `yprr` |

⇒ **The blocker is not engineering and not entity resolution. It is ENTITLEMENT**, which makes
this a subscription/PM decision rather than a build task. Research only; `best_alpha = 0`.

---

## 1. ⛔ The finding that decides the story: the tier withholds every field we came for

Each facet returns, beside its data, a `restricted` array — **PFF telling us which fields this
subscription withholds**. On the operator's account (Clerk JWT: `tier: annual`,
`permissions: {premium: [full]}`) that array contains, verbatim:

```
routes  route_rate  avg_depth_of_target  slot_rate  slot_snaps  wide_rate  inline_rate
yprr  pass_plays  run_plays  yards_after_contact  yco_attempt  gap_attempts
zone_attempts  breakaway_attempts  designed_yards  elusive_rating
```

That is **the entire NF-W9-1/2/3 shopping list**. The available and restricted sets are
disjoint (checked), so `restricted` really does mean withheld. What *is* returned:

| Facet | Available | Restricted |
|---|---|---|
| `receiving/summary` | 15 | 31 |
| `rushing/summary` | 17 | 29 |
| `rushing/direction` | 10 | 11 |
| `receiving/depth` | 6 | **499** |
| `passing/depth` | 6 | **548** |

The available columns are plain box score — `targets`, `receptions`, `yards`, `touchdowns`,
`attempts`, `first_downs`, `longest`, `fumbles` — **all of which nflverse already gives us for
free**. `rushing/direction` is the sharpest illustration: it returns the direction *labels* and
`long`, while every count (`attempts`, `yards`, `yards_after_contact`, `ypa`, `touchdowns`) is
restricted, so the gap/direction split NF-W9-2 wants is exactly the part withheld.

**NCAAF is the same** — `routes` and `avg_depth_of_target` are restricted there too.

### What this means per story

| Story | Needs | Status |
|---|---|---|
| **NF-W9-1** zero-atom opportunity | `routes` | ⛔ **BLOCKED.** Routes is the field that splits "inactive" / "played, ran no routes" / "ran routes, no target" — the marginal-zero-atom constraint measured across NF-W6d/W7c–f. Without it there is no story. |
| **NF-W9-2** RB volume | `yards_after_contact`, `gap_attempts`, `zone_attempts`, `breakaway_*` | ⛔ **BLOCKED.** Every field restricted. |
| **NF-W9-3** college charting | `routes`, `adot` at NCAA | ⛔ **BLOCKED.** CFBD has no charting layer, so there is no fallback — **do not card it.** |

The fields demonstrably **exist** (PFF names them). This is a paywall, not an API limit — so
the live question is *"is the higher tier worth buying?"*, and this probe is exactly the
instrument to re-run against a upgraded credential: **nothing else needs to change.**

## 2. ✅ Entity resolution — measured, and better than the first pass predicted

### NFL — 100%, entirely deterministic

| | NFL 2024 wk1–2 |
|---|---|
| games / facet rows | 32 / 1,245 |
| **player match** | **100.00%** — 1,243 by `stable_vendor_id`, 2 by name |
| **game match** | **100.00%** (32/32) |
| id-space overlap | **0.9972** → `SAME_ID_SPACE` |

**The one open risk from the first pass is closed.** Everything measurable from our lake alone
could only bound nflverse's `pff_id` *column*; whether it was the *same id space* as PFF's own
`player_id` needed a live call. It is: 99.72% of PFF ids seen appear in our map, and PFF's
`player_id` for Aaron Rodgers is `2241` — byte-identical to nflverse's `pff_id`. The NFL join
needs **no fuzzy matching at all**.

The lake measurements that shaped the design still stand and still matter for a historical pull:

| Denominator (live lake) | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| roster **rows** with a `pff_id` | 75.5% | 61.4% | 49.3% | **39.2%** | 75.3% |
| **same-season**, opportunity-weighted | 99.66% | 87.10% | 68.60% | **56.16%** | 99.97% |
| **player-level (cross-season)** | **99.94%** | **99.59%** | **99.66%** | **99.89%** | **99.97%** |

Three findings, in the order they changed the design: the **row rate is the wrong unit** (the
sparseness is entirely the zero-opportunity tail); **2025 does not generalize** (a same-season
join loses 44% of 2024 opportunity, and NF-W9-1/2/3 need multiple seasons for folds); and
`pff_id` is **player-level but populated per roster-row**, so the map is collapsed across all
seasons. ⚠️ The obvious collapse is a **wrong merge** — `max(pff_id)` mis-keys Tyler Conklin,
because pff_id 47327 is attached to *both* him and Ryan Izzo. Ambiguous ids are dropped, not
arbitrated (2 of 4,841).

### NCAAF — 97.1%, and the residual is enumerated

| | NCAAF 2025 wk11 |
|---|---|
| games / facet rows | 116 / 5,034 |
| **player match** | **97.10%** (1,735 exact name+school+pos, 3,153 name+school) |
| **game match** | **100.00%** (116/116) |
| unmatched | 146 — **36** unknown-school, **110** known-school-player-absent |

There is no shared college id (NCAAF-P0.3: `CFBD nflAthleteId ∩ nflverse espn_id = 0 of 257`),
so this is a name join blocked on the school, and the **school key is the join**. The first
live run scored **92.1% players / 88.8% games**; reading the reported unmatched schools against
CFBD and adding 13 verified aliases took it to **97.1% / 100%**. That is the designed workflow,
not a patch: an unmatched school is *named*, checked, and keyed.

⛔ **The tempting general rule is wrong and the data says so.** PFF appends "State" where CFBD
does not (`Grambling State`→`Grambling`, `McNeese State`→`McNeese`), but stripping "State"
wholesale would merge **Ohio / Ohio State, Michigan / Michigan State, Florida / Florida State**
— all real, distinct, both present in CFBD. So the alias is added only where CFBD has the base
and *not* the "State" form. Also pinned: PFF ships the typo **"UT Rio Grand Valley"**; a typo is
a fact about the feed, so it is aliased rather than met by loosening the fuzzy threshold.

The 110 known-school misses are CFBD roster gaps (a school is present, that player is not); the
36 unknown-school rows are D-II/D-III programmes CFBD's roster endpoint does not cover at all
(John Carroll, Ohio Wesleyan). Both are **CFBD coverage facts, not key bugs** — which is
precisely the distinction `unknown_school` exists to make.

## 3. How PFF auth actually works — and why the first attempt failed

**PFF uses Clerk. There is no bearer token to copy** (which is what the operator observed): the
`__session` cookie *is* the JWT, minted with a **60-second lifetime**. A cookie captured from
DevTools is therefore always expired by the time it is pasted.

An expired session does **not** return 401. `premium.pff.com` answers **307** to
`clerk.pff.com/v1/client/handshake?…&__clerk_hs_reason=se`; the handshake mints a fresh session
from the long-lived `__refresh_*` cookie and redirects back. ⇒ **a stateless `Cookie:` header
per request cannot authenticate** — it never carries the handshake cookie back, so it loops
until curl aborts with "maximum redirects followed", which looks like a network fault and is
really an auth flow. The cure is a **cookie-persisting session that follows redirects**.

Two more live failures, both now named by the client rather than left to be puzzled over:

* **HTTP 431, empty body.** Seeding the session jar *and* setting an explicit `Cookie:` header
  sends PFF's ~7 KB jar twice. The empty body surfaces as "unparseable JSON" and looks nothing
  like the header-size problem it is.
* **HTTP 404 with the body `"Internal server error"`** — which is neither. It is the normal
  answer for a facet PFF does not publish, so it is now non-retryable (it was tripling our
  request count against a paid API) and distinguished from a genuine fetch failure.

`premium.pff.com` is behind **DataDome** (not Cloudflare; `clerk.pff.com` is Cloudflare) — the
challenge detector matches both.

## 4. Facet catalog — discovered, and the guess was wrong

Probed live against NFL 2024 wk1 game 25907:

| Available | Not published (404) |
|---|---|
| `rushing/summary`, `rushing/direction`, `receiving/{summary,depth,concept}`, `passing/{summary,depth,concept}`, `defense/summary` | `blocking/*`, `coverage/*`, `special_teams/*`, `receiving/direction`, `passing/direction` |

Discovery earned its keep immediately: the symmetric guess included `receiving/direction`
(404) and **omitted** `receiving/depth` and `receiving/concept`, both real. A hardcoded catalog
would have been a claim about PFF's API written by us.

**PFF's facet rows carry no team name — only `franchise_id`.** The team is only knowable by
joining back to the game, and the label key is league-specific: NFL `abbreviation` ("SF")
matches nflverse codes, NCAA `city` ("Notre Dame") matches CFBD school names (NCAA
`abbreviation` is "NOTRED", which matches nothing of ours). Without that map the NCAAF school
block is empty and the join scores a clean 0% — which is exactly what the first live NCAAF run
did, and the strict guard caught it rather than reporting 5,034 rows as a success.

## 5. ⛔ Raw stats only — enforced in code

PFF's raw counting stats are data; its projections, grades, rankings and mock drafts are a
**competitor's model output**, and consuming them would launder someone else's model into ours.
Enforced at two points: **endpoint refusal** (checked *before* the credential, so it is
unconditional) and a **column strip** for grades that ship inline with raw facets — the strip
**reports what it dropped**, since a silent strip is indistinguishable from "PFF sent no
grades". Live, it stripped `grades_offense`, `grades_pass_route`, `grades_hands_fumble`, … from
every facet. Matching is **whole-token, not substring**, so `downgrade` and `franchise_id`
survive (the NF-W7 `'temp' ⊂ 'attempt'` trap).

## 6. Recommendation ⚠️ SUPERSEDED — see the correction at the top

~~1. **Do not card NF-W9-1/2/3 against the current subscription.**~~ **RETRACTED.** The account
   has the fields; the CSV export carries all 28. The stories are not paywalled.
~~2. **The decision is a purchase, not a build.**~~ **RETRACTED — it is the opposite.** It is a
   build: find the path that serves the full field set.

**Corrected next steps:**

1. **Capture the CSV export request.** The full data is demonstrably reachable on this account;
   we simply have not identified the endpoint. Easiest route is the browser's own download
   history (`chrome://downloads` records each file's source URL) rather than DevTools, where
   Clerk's `/touch` heartbeat dominates the log. If clicking Download produces no request to
   `premium.pff.com` at all, the CSV is built client-side — which would mean the page receives
   the full data from a call we have not yet seen (plausibly a Phoenix LiveView WebSocket; the
   `_premium_key` cookie is a Phoenix signed session, and LiveView traffic never appears under
   the XHR filter).
2. **Then re-point the crawler at that path.** The client, resolution, guards and match rates
   all stand unchanged — only the fetch URL moves.
3. **Prefer the season-aggregate query shape regardless.** `week=` accepts a list, so one call
   covers a season and one call per week gives weekly grain — ~17 requests per season per facet
   instead of the 2,176 per-game calls originally sized.
3. **The entity-resolution work is banked either way.** NFL 100% / NCAAF 97.1% is reusable for
   any future PFF-shaped feed, and the id-space confirmation retires a standing unknown.
4. Meanwhile the routes-shaped gap in NF-W9-1 stays open. Worth a separate look at whether any
   **non-PFF** source carries routes run (nflverse `pbp_participation` gives personnel/snap
   participation, which is a weaker but free proxy) before paying for a tier.

## 7. Scope / limits

* A **spike**: 32 NFL + 116 NCAAF games, a small local parquet, no Delta table, no schedule, no
  serving path, nothing published. `best_alpha = 0`.
* The entitlement finding is about **this account's tier**. It is what PFF reports, not an
  inference — but a different tier would report a different `restricted` list.
* NFL match rates are from 2024 wk1–2 and NCAAF from 2025 wk11; the multi-season lake coverage
  table is what bounds a historical pull.
* CFBD roster ambiguity measured for 2024/2025 only.
* 82 guards, **19/19 RED-proven** against deliberately broken source (`red_proof.py`, committed
  and runnable). Three of those guards were themselves found vacuous by the RED proof and
  fixed — two tested a helper while the defect lived at the call site.
