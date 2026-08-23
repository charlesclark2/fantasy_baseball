# NF-INJ-NEWS-1 — pre-publish measurement (2026-08-23)

**This certifies nothing.** The reported-absence cap is an **operator judgment with a source
attached**, never a fitted model. It has not been backtested, no claim of improvement attaches to
it, and `best_alpha = 0`. This report exists so the operator can approve — or decline — the first
publish with the board delta in hand, which is the only responsible gate a judgment mechanism has.

**Status: DEPLOY-HELD.** Nothing is published. The curated file ships EMPTY.

---

## ⚠️ THE HEADLINE, AND IT IS A DECISION FOR THE OPERATOR

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
