# NF-W9-0 — PFF data-access feasibility spike

**Verdict: GO on the ENTITY-RESOLUTION half (measured), PENDING on the DATA-ACCESS half
(needs the operator's credential).** Research only; `best_alpha = 0`; nothing here touches a
serving path and nothing is published.

The two halves of "is this feasible?" have very different evidentiary status right now, and
collapsing them into one verdict would be dishonest:

| Half | Status | Why |
|---|---|---|
| Can we JOIN PFF to our ids? | ✅ **GO — measured on the live lake** | ≥99.59% opportunity-weighted NFL coverage, 99.60% NCAAF ceiling |
| Can we PULL PFF at all? | ⏳ **UNTESTED — operator-gated** | PFF is a paid login; I have no credential and did not attempt a bypass |
| Is nflverse's `pff_id` PFF's `player_id`? | ⚠️ **UNVERIFIED — the one real risk** | Nothing in our lake can settle it; `id_space_agreement` settles it on the first live pull |

---

## 1. Data access — what I built, and what only the operator can finish

PFF is a paid subscription behind auth (and, like FanGraphs, Cloudflare). I did **not** attempt
to bypass it. `client.py` is modelled on `scripts/utils/fangraphs_client.py`, the repo's
sanctioned authed-fetch pattern, and takes an **operator-supplied credential** over three
transports: `direct` (bearer token via curl_cffi/Chrome fingerprint), `flaresolverr` (cookie
replay through the existing FanGraphs solver), and `sample` (an operator-captured response read
off disk — the transport that made this developable and testable without a credential at all).

**Auth is verified by CAPABILITY, never reachability.** The probe's success condition is
"pulled N rows and matched them", not a 200. This matters more than it sounds: an expired PFF
session, a Cloudflare interstitial and a logged-out browser all return *cheerful HTML*, often
with HTTP 200. `_parse_response` therefore inspects the body shape and raises a *typed, named*
error — `PFFAuthError` ("re-capture the token") vs `PFFChallengeError` ("switch to
flaresolverr") vs `PFFClientError` — and **no failure path anywhere returns an empty list**, so
an outage can never be mistaken for a quiet day (the E5.10 `lakehouse_query`→`[]` class).

The probe runs `--strict` by default and **exits non-zero on a zero-row pull or a zero-match
join**. A spike whose entire question is "can we join this?" must never be able to answer
"yes, 0 rows".

## 2. Entity resolution — the crux, and it is the good news

### NFL: a deterministic tier-1 join, no fuzzy matching required

nflverse `weekly_rosters` already carries a `pff_id` vendor column, so PFF→`gsis_id` is a
**stable-vendor-id** join. The naive reading of that column is alarming and **wrong for the
decision at hand**, which is the whole point of the measurement:

| Denominator (live lake) | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| roster **rows** carrying a `pff_id` | 75.5% | 61.4% | 49.3% | **39.2%** | 75.3% |
| **same-season**, opportunity-weighted | 99.66% | 87.10% | 68.60% | **56.16%** | 99.97% |
| **player-level (cross-season)**, opportunity-weighted | **99.94%** | **99.59%** | **99.66%** | **99.89%** | **99.97%** |

Three findings, in the order they changed the design:

1. **The row rate is the wrong unit.** 2025 is 63.2% of *all* players and 99.97% of actual
   targets-and-carries — the sparseness lives entirely in the zero-opportunity tail. A story
   that needs the targets is entitled to the number about targets (the NF1.8 rule). Position
   coverage on the 2025 skill population: QB 96.2%, K 96.0%, RB 91.4%, WR 84.3%, TE 82.5%.
2. **2025 does not generalize, and reading only 2025 would have been a serious error.** The
   same-season join loses **44% of 2024 opportunity**. Since NF-W9-1/2/3 need multiple seasons
   for folds, a "2025 looks fine" conclusion would have shipped a historically broken join.
3. **`pff_id` is a PLAYER-level id that nflverse populates per roster-row.** Collapsing the map
   across *all* seasons recovers the gap almost entirely — 56.16% → **99.89%** for 2024. This
   is the design: `build_pff_crosswalk` is deliberately season-agnostic.

**⚠️ And the obvious implementation of that collapse is a wrong merge.** `max(pff_id)` is how
one naturally writes it, and it is wrong on live data: **pff_id 47327 is attached to BOTH Ryan
Izzo and Tyler Conklin**, and Conklin also carries 47124 — so `max()` hands Conklin an id that
is not uniquely his. Ambiguous ids are **dropped, not arbitrated** (2 of 4,841 players), because
a miss is visible and a wrong merge is not.

Rather than write a merge, the NFL leg **reuses the calibrated NF-W0b ladder** (`entity/
resolver.py`), which already enforces the properties that are easy to omit by hand: ambiguity
becomes an UNRESOLVED instead of a coin flip, a fuzzy rung cannot fire outside its block, and
the 0.95 threshold is one someone already calibrated against a blind vendor-id control rather
than tuned until the yield looked good. Running the real 2021–25 opportunity population through
the actual code path reproduces the SQL exactly (2024: 97.12% of rows, **99.89% of
opportunity**; 2025: 98.32% / **99.97%**).

### NCAAF: harder, and honest about being harder

There is **no shared player id** anywhere in college (NCAAF-P0.3 measured `CFBD nflAthleteId ∩
nflverse espn_id = 0 of 257`), so a PFF college player must be matched on name + school +
position. Measured ceiling on the live CFBD 2024 roster (22,843 rows, 22,837 athletes, 308
schools): **99.60%** on name+school+position, 98.94% on name+school — only 44 ambiguous keys.
Names are near-unique *inside a school*, so this is far less fragile than expected.

**The real NCAAF risk is the school key, not the name.** `nfl.entity.names.normalize_team` is an
NFL alias-code folder that merely upper-cases anything it does not recognise — it leaves
`Ole Miss` ≠ `Mississippi`, `San José State` ≠ `San Jose State`, `Miami (OH)` ≠ `Miami OH`. Since
the join is *blocked on the school*, that fails exactly the schools vendors disagree about (the
NF-W3 franchise-code class). `schools.py` adds a college key (accent/punctuation folding, a
positional `St`→`State` rule that leaves *Saint* Francis alone, and a small alias map). It is a
**new key for a new population**, deliberately *not* a widening of `normalize_team`, which is
shared with already-validated NFL legs.

An unmatched school is **named** (`unknown_school`), not silently dropped — a school we cannot
key takes its whole roster with it, so naming it converts a depressed match rate into a
one-line alias-map entry. Expect the alias map to grow on the first real pull (`App State` /
`Appalachian State` is a known pending case); that growth is the designed workflow.

### Games (both leagues)
Joined on `(season, week, home, away)` with the league-correct team key, trying the given
orientation then **swapped** — a feed that labels home/away the other way round would otherwise
produce a clean, total and utterly mysterious 0%.

> **A bug this found in my own code, worth recording.** After moving the NCAAF *player* join
> onto `school_key` I left `resolve_games` on the NFL folder. The probe then scored a **100%
> player match and a 0% game match** on real CFBD data — `Ohio St` vs `Ohio State`. Two
> renderers of one field running two rule sets (E9.61). Caught by *running* the probe, not by
> any test; now pinned by a regression test and RED-proven.

## 3. ⛔ RAW STATS ONLY — enforced in code

PFF's raw counting stats are data; its **projections, grades, rankings and mock drafts are a
competitor's model output**. Consuming them would launder someone else's model into ours and
make every downstream §0.5 verdict uninterpretable — a "win" could just be PFF's model showing
through. `guards.py` enforces this at two points, because the risk arrives two ways:

* **Endpoint refusal** — `/projections`, `/rankings`, `/mock-draft`, `/grades` raise
  `ForbiddenEndpointError`. Checked *before* the credential, so the refusal is unconditional
  rather than an accident of not being logged in.
* **Column strip** — the one that actually bites. A legitimate raw facet (`rushing/summary`)
  ships PFF's grades *inline* with the carries. Refusing the endpoint would throw away the raw
  stats we came for, so we keep the row, drop the graded columns, and **record what was
  dropped** — a silent strip is indistinguishable from "PFF sent no grades", and those are very
  different facts.

The match is **whole-token, not substring**: a raw `"grade"` scan also matches `downgrade`, and
`"rank"` matches `franchise`. (NF-W7 shipped exactly this bug — `'temp' ⊂ 'attempt'`.) So
`pass_grades_rate` is dropped while `yards_after_contact`, `franchise_id` and `downgrade`
survive, and both directions are tested.

## 4. Facet catalog — discovered, not declared

`discover_facets` probes each candidate `(unit, view)` against a **real game** and records what
answered, with the failures listed beside it. A hardcoded catalog would be a claim about PFF's
API written by us, and the repo has been bitten repeatedly by a declaration outrunning its
production (NF-C0e "wired ≠ invoked", NF-K1's declared-but-never-produced positions). Field
*names* are likewise discovered: `normalise_rows` records which candidate key hit (`adot` ←
`avg_depth_of_target`) and keeps every original column as `raw_*`, so the artifact says what PFF
actually sent rather than what we guessed.

Confirmed by the operator: `rushing/{summary,direction}`. Probed by symmetry: `receiving`,
`passing`, `blocking`, `coverage`, `defense`, `special_teams` × `summary`, `direction`, `depth`,
`concept`. **The real catalog is whatever the operator's run reports.**

## 5. Facet → signal map (what unblocks NF-W9-1/2/3)

| Story | Facets | Fields sought | Why PFF at all |
|---|---|---|---|
| **NF-W9-1** zero-atom opportunity | `receiving/summary`, `rushing/summary` | **routes**, snaps, targets, aDOT | The constraint measured across NF-W6d/W7c–f is that our per-stat zero atom is *marginal*: we cannot separate "inactive", "active but ran no routes" and "ran routes, no target". nflverse has targets and snap **counts** but **no routes run**, so all three collapse into one zero. **Routes is the field that splits them — the single most decision-relevant thing in this probe.** |
| **NF-W9-2** RB volume | `rushing/summary`, `rushing/direction`, `receiving/summary` | attempts, yards after contact, gap/direction | `rushing/direction` has no nflverse equivalent. |
| **NF-W9-3** college charting | `receiving/{summary,direction}`, `rushing/summary` | routes, aDOT, alignment | **CFBD has no charting layer at all.** If PFF's NCAA facets carry these it is net-new substrate for the college→NFL feeder; if they do not, **NF-W9-3 has no data and should not be carded.** |

## 6. The one thing that could still overturn the NFL verdict

Everything in §2 measures the coverage of **nflverse's `pff_id` column**. It does **not**
establish that nflverse's `pff_id` is the same id space as **PFF's own `player_id`** — and
nothing in our lake can. Assuming two same-named id columns are the same key is precisely the
NF-C0e wrong-key class, so it is instrumented rather than assumed: `id_space_agreement` runs on
the first live pull and returns `SAME_ID_SPACE` (≥80% overlap), `DISJOINT_ID_SPACE` (≤5%), or
`PARTIAL`. **Until it runs, the NFL numbers above are a CEILING, not a result.**

If it comes back disjoint, NFL is not dead — it falls back to the same name+team+position ladder
NCAAF uses, inside a season/week/team block. That is a materially worse but still workable
answer, and the probe will say so rather than silently scoring 0%.

## 7. Scope / limits

* A **spike**, not an ingest: a few weeks, a small local parquet, no Delta table, no schedule,
  no serving path, nothing published. `best_alpha = 0`.
* No PFF call has been made. Every number here is measured against **our own lake**; every PFF
  figure is pending the operator's run.
* CFBD roster ambiguity is measured for 2024 only; other seasons are assumed similar.
* 65 guards, **12/12 RED-proven** against deliberately broken source
  (`red_proof.py` — committed and runnable, because E9.64 found six red-proofs that had
  silently stopped working precisely because nothing ever ran them).
