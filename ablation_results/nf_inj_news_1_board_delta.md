# NF-INJ-NEWS-1 — pre-publish measurement (2026-08-23)

> **AMENDED 2026-08-23 by PM rulings 1, 2b and 3.** The rule that will serve is the
> REMAINING-SEASON RATE, not the ceiling this report was first written against. The
> ORIGINAL measurement is retained below UNCHANGED — it is the evidence the ruling was
> made on, and rewriting it would leave the ruling resting on numbers nobody can see.
> Read §0 first for what actually serves.

**This certifies nothing.** The reported-absence cap is an **operator judgment with a source
attached**, never a fitted model. It has not been backtested, no claim of improvement attaches to
it, and `best_alpha = 0`. This report exists so the operator can approve — or decline — the first
publish with the board delta in hand, which is the only responsible gate a judgment mechanism has.

**Status: DEPLOY-HELD.** Nothing is published. The curated file ships EMPTY.

---

## §0 — WHAT WILL ACTUALLY SERVE (PM ruling 1, and it supersedes §1 below)

    proj_games_new = min( proj_games_current, (17 − n_reported) × proj_games_current / 17 )
    effect         = n_reported × proj_games_current / 17

`proj_games` is a season-long availability RATE — the product already treats it as one
(`fullSeasonRate` is points × 17/expected_games; this is that construct in reverse). A reported
absence removes n games from the schedulable season, and the rate applies to the 17−n that remain.
The effect is strictly smaller than subtracting n outright, so a report is never double-counted in
full against durability the model has already priced; and unlike the ceiling it always engages.

Re-scored on the same real board (794 rows, built 08-21):

| player | pos | rookie | proj_games | n | new_games | effect | qualifies (ruling 3) |
|---|---|---|---|---|---|---|---|
| Jordyn Tyson | WR | ✅ | 13.61 | 5 | **9.608** | **−4.003** | **YES** |
| Alvin Kamara | RB | | 11.49 | 2 | **10.139** | **−1.352** | **YES** |
| Kyle Monangai | RB | | 11.89 | 1 | 11.193 | −0.700 | no — n<2 |
| Jeremiyah Love | RB | ✅ | 16.00 | 1 | 15.059 | −0.941 | no — n<2 |
| Emeka Egbuka | WR | | 15.30 | 1 | 14.398 | −0.900 | no — n<2 |
| Sam LaPorta | TE | | 13.83 | 1 | 13.016 | −0.814 | no — n<2 |

**No inert tier remains.** Every applied row moves, and every applied row logs its effect size.

### PM ruling 3 — what qualifies, and what it removes

A row qualifies only when (i) the source explicitly reports missing **regular-season** time — a
named count of games/weeks or a dated return, never day-to-day / week-to-week / camp-only language
— and (ii) `n ≥ 2`. Clause (ii) is enforced in the loader; clause (i) is the curator's obligation,
carried in the curated file's header (no scan can read a source and decide what it means, and a
keyword check over source prose would reject an honest citation that quotes a coach).

**Four of the six originally-proposed rows fall out, on BOTH halves** — their sources are
"week-to-week", "day-to-day", "I don't know", and a preseason-only report. That the two filters
agree is a reasonable sign the policy is aimed at something real rather than at a number.
**Two rows qualify: Tyson (5) and Kamara (2).**

### PM ruling 2b — disjointness now turns on the APPLIED DISCOUNT

An override is ignored when a formal discount **was applied**, not when a formal tag merely exists.
The old form had a reachable worst case: a rookie placed on IR gets **zero** from the formal path
(it runs only inside `project_veterans`) and was **also** un-overridable because a tag existed —
undiscounted *and* un-overridable, with the 53-man cutdown putting a wave of exactly those rows on
the board.

Every row carrying a formal tag with no discount behind it is now named in the build log by
`_warn_formal_tag_without_discount`, **board-wide and on every build**. That line is the live
detector for the NF-INJ3c population, and it counts rookies explicitly — the rookie half of the
frame carries no `proj_status` natively, so the build attaches it *for detection only* (no discount;
the rookie-path fix is NF-INJ3c's story). Without that attach the detector would have been
structurally blind to precisely the population it exists for.

---

## §1 — THE ORIGINAL MEASUREMENT (retained verbatim; the evidence PM ruling 1 was made on)

⚠️ **SUPERSEDED BY §0.** Everything below describes the CEILING rule, which no longer serves.
It is kept because the ruling was made on these numbers and a record that quietly rewrote
itself would leave the decision resting on evidence nobody can check.

### The headline, as reported to the operator

**Measured against the real 2026 board (794 rows, built 2026-08-21), the cap as the spec defines it
is INERT for 5 of the 6 proposed candidates.**

The spec's rule is `min(current_expected_games, 17 − expected_games_missed)`. That was implemented
exactly. But the model does not start every player at 17 games — its base expected-games estimate
blends depth-chart role with prior durability and lands most starters between 11 and 16. So a
ceiling built as *17 minus a short absence* sits **above** what the player is already projected for,
and the `min` does nothing:

| player | pos | rookie | proj_games | absence | ceiling `17−n` | effect |
|---|---|---|---|---|---|---|
| Jordyn Tyson | WR | ✅ | 13.61 | 5 | 12 | **−1.61 games** |
| Alvin Kamara | RB | | 11.49 | 2 | 15 | **inert** |
| Kyle Monangai | RB | | 11.89 | 1 | 16 | **inert** |
| Jeremiyah Love | RB | ✅ | 16.00 | 1 | 16 | **inert** |
| Emeka Egbuka | WR | | 15.30 | 1 | 16 | **inert** |
| Sam LaPorta | TE | | 13.83 | 1 | 16 | **inert** |

Even the one that bites moves less than a reader would expect: "misses 5 of 17" reads as a ~29% cut,
and the row actually moves 12%, because 3.4 games of absence were already priced.

**The two readings, and why this is not the session's call.** A ceiling of `17 − n` says *"he will
play no more than 12 games this year"*. A subtractive rule (`current − n`) says *"whatever you
thought, he misses 5 more"*. The spec is explicit and binding, so it was implemented as written and
is **flagged here, not edited**. But the operator should know that under the specified rule a
one-or-two-game report is a no-op by construction, and that the mechanism only really engages for
absences long enough to push below the model's own durability estimate — roughly 4+ games at a
starter's projection, more for a player already discounted.

⭐ Note the mechanism handles this honestly either way: an inert cap is reported as `INERT` in the
build log rather than passing as a working discount, so this is visible on every build and not
something anyone has to remember.

---

## ⭐⭐ A DEFECT THE MEASUREMENT FOUND, NOW FIXED

**The canonical first row is a ROOKIE, and the availability path is the VETERAN path.**

Jordyn Tyson is a 2026 rookie (`is_rookie=True`, `source='rookie'`, board id `TYS405541`), as is
Jeremiyah Love. Every existing availability discount — the RES/PUP/NFI/SUS status cap, the NF-D11
return prior — lives inside `project_veterans`; `project_rookies` has its own games path and calls
none of them. **81 of the 794 rows on the 2026 board are rookies**, and they are precisely the
population with no roster history for the model to discount them by.

Wired only into the veteran path, this story would have shipped a mechanism that *declares* it moves
the Tyson class and structurally *cannot*. Fixed: `project_rookies` now applies the same cap at the
same position in its ordering (availability → level recalibration → band).

**It was invisible to all 44 guards**, because a synthetic frame does not know which production
function built it. It surfaced by resolving the seed candidates against the real published board —
the NF-C0e wired-vs-invoked class, which only the artifact ever shows. Now pinned by two clauses and
RED-proven.

A second, smaller defect fell out of the same fix: each population is handed the whole override list
and reports on all of it, so a rookie's row read `UNMATCHED_ON_BOARD` to the veteran half and vice
versa. Logged raw, **every** override would have emitted a spurious `[ALERT] NOT applied` beside its
own `APPLY` line — the alert-on-every-healthy-row pattern that gets a monitor muted. The two halves
are now reconciled: unmatched only when neither population matched, and a real refusal (a formal
tag) outranks "not in this half".

---

## What is measured, and what is not

| | status |
|---|---|
| candidate resolution by name against the real board | ✅ **6/6 resolved, 0 ambiguous** |
| formal-designation check (the disjointness precondition) | ✅ **all 6 `proj_status = None`** on the live Sleeper feed |
| per-row cap effect on the served board | ✅ **measured** (table above) |
| whole-board placement read (`run_nf_tr2b_placement_read`) | ⏭️ **operator step** — needs a built board |
| interval revalidation (`run_interval_revalidation`) | ⏭️ **operator step** — see the invariance note |
| NF1.5 give-back on this cohort | ⏭️ **operator step** — needs both builds |

**Why the last three are operator steps and not session omissions.** All of them need
`sports.duckdb` and the artifact/panel caches, which are gitignored and therefore **absent from any
worktree** (NF-INFRA1) — and two full board builds is a long run. The runner that does the whole A/B
end-to-end is committed as
`quant_sports_intel_models/football/nfl/fantasy/run_nf_inj_news_1_measure.py`; the command is in the
session handoff. Its name-resolution half was run here against the real board — that is where the
table above and the rookie defect came from.

### ⛔ Do not inherit NF-INJ1's +36.4% give-back

NF1.5 re-orders each position by handing every player a different player's projected-point level and
rescaling his stat line to match, through `nf1_model._RAW_SCALE_COLS` — which contains the twelve
stat columns and **not** `proj_games`. So a capped player promoted within the multiset has his line
multiplied while his games stay cut, and part of the cap is handed back. NF-INJ1 measured that at
**+36.4%** for the served arm.

That figure is **not transferable to this cohort** and must not be assumed proportional. It was
measured on the *formally*-capped population; this is a different population (untagged players, a
different position mix, different places in their positions' point multisets, and — now — two rows
that are rookies, which NF1.5's veteran re-ordering does not touch at all). The runner computes it
for this cohort on this build via the existing `injury_giveback` instrument.

### Why the interval revalidation cannot be affected

`run_interval_revalidation` validates the interval bands on **historical walk-forward panels**, and
`load_overrides` gates on the file's declared season, so a 2026 judgment can never reach a
historical fold. The build path enforces the same thing structurally: `build_veteran_panel_season`
calls `build_veteran_projection` without the override arguments at all, and a guard pins that.
Running it is therefore a **regression check that the gate held**, not a measurement of the
overrides — worth stating rather than leaving a reader to infer that it was skipped.

---

## The seed list

Six candidates proposed across two tiers, six declined, two excluded on principle, in
`data/reported_absence_overrides.proposed.yaml`. Nothing reads that file; the operator moves the
rows they accept into `reported_absence_overrides.yaml`.

⏳ **The list has a shelf life of about a week.** The 2026 cutdown to 53 is **2026-08-30**, and this
population exists precisely because IR placements have not happened yet — several of these players
are described in reporting as IR candidates once teams cut down. When that happens the formal path
takes over and the override is ignored automatically, named in the build log. Every `review_by` is
set to the cutdown for that reason.

📌 `ablation_results/nf_c8_injury_designation_gap.md` places Tyson in **Arizona**. The live Sleeper
feed and every beat report say **New Orleans**. Nothing depends on it — recorded because a false
premise in a doc is what the next reader builds on.
