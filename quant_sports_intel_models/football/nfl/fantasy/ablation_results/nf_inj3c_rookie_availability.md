# NF-INJ3c — Rookie-path availability routing

**Status:** code complete, verified against reality, **DEPLOY-HELD**. `best_alpha = 0`.
**Machine record:** `nf_inj3c_rookie_availability.json` (the four measured legs).
**Dated:** the 2026-08-30 53-man cutdown puts a wave of IR'd rookies on the board.

---

## 0. The gap, and what closed it

Both model-driven availability discounts — the formal RES/PUP/NFI/SUS status cap (NF-D2 slice 5)
and the NF-D11 return-from-absence prior — lived **inside `project_veterans`**. `project_rookies`
ran neither. A rookie placed on IR was therefore projected as though healthy by every path on the
board, on 81 of the 794 rows of the 2026 board.

Measured over the 2016–2025 builds (NF-INJ3 §1, reproduced here in leg 1): **50 of 60** flagged
rookies projected ABOVE the incumbent cap's own ceiling, against **0 of 496** veterans.

The fix is one shared step, `season_projection.apply_availability_chain`, that both projection
frames call — formal cap → NF-D11-where-applicable → reported-absence cap — with
`rescale_line_to_games` owning the 12-column line rescale that had been typed out four times. The
frames differ only in what they hand it, and each difference is a recorded ruling (§1, §2).

⛔ **Not a copy-paste of the caps into `project_rookies`.** One logical thing with many owners is
this repo's most-repeated defect class (INC-30 crontab, INC-36 deploy lock, INC-38 the per-caller
flag); a second copy would have closed the gap and re-opened it on the next edit to either copy.

---

## 1. AC-1 — the formal cap for rookies is the INCUMBENT CONSTANTS

`{RES/PUP/NFI: 4.0, SUS: 7.0}` at blend 0.7, applied through `injury_availability_games` **directly**
— ⛔ never through `injury_games_serving`, the NF-INJ3b policy router.

NF-INJ3b certified `hurdle_transfer` on the **veteran** population and **excluded rookies by
registration** (60 of them, `population.excluded.rookies`). Its covariates — `prior_games`,
`log1p_prior_fp`, `weeks_since_last_game`, `onset_carryover` — are prior-NFL-career quantities a
rookie does not have and cannot have. Serving it here would be an uncertified re-derivation on a
population it never scored: MH2.1's "serve the object that was VALIDATED", facing the population
axis rather than the object axis.

**If NF-INJ3b-M's certified artifact later ships for veterans, rookies REMAIN on constants** until a
registered read covers them. The boundary is written in `project_rookies` where the next editor will
meet it, and pinned in both directions by
`test_the_rookie_frame_routes_the_INCUMBENT_CONSTANTS_never_the_certified_veteran_hurdle`.

---

## 2. AC-2 — NF-D11 is `NOT-APPLICABLE-BY-CONSTRUCTION`

Ruled on **mechanism**, before any measurement, as the acceptance criterion asks.

The prior fires on `seasons_missed >= 1` — a player who missed an **entire prior NFL season** while
carrying production in Y−3..Y−2 — and its design matrix is
`(prior_games, log_prior_fp, seasons_missed, is_qb)`, three of whose four terms are prior-NFL-career
quantities. A rookie has no prior NFL season, so `seasons_missed` is not merely *missing* but
**undefined**, and the fit population (431 historical returners) contains no row like him.

⭐ **The FINDING transfers; the FEATURE does not.** NF-D11's finding is "a player whose availability
history is absent or stale must be DISCOUNTED, never carried forward at the healthy level." For a
tagged rookie, the formal cap in §1 is what expresses it. This is the recorded landmine the
acceptance criterion names, and it is why no rookie-shaped surrogate for `seasons_missed` was
invented.

Enforced at both ends: the rookie frame passes `absence_prior=None`, and the chain additionally
self-gates on `seasons_missed` so a future caller cannot re-open it by accident.

---

## 3. The measured evidence — against reality, not fixtures

`run_nf_inj3c_rookie_availability.py`, read-only over the real published boards, the real roster
feed and the real rookie classes. **All four legs pass.**

| leg | what it measures | result |
|---|---|---|
| 1. reproduction pin | NF-INJ3's recorded rookie-bypass measurement, recomputed | **50/60 rookies, 0/496 veterans** — reproduces exactly |
| 2. with-fix, same rows | the new formal step on those same published rookie rows | **60 flagged → 0 above ceiling**; **0 of 738** unflagged rows move; max games dropped **8.31** |
| 3. wiring, end to end | `project_rookies` with vs without the feed, 11 classes | **60/60 capped**, 0 above ceiling, 0 unflagged moved, every volume column scales **exactly** with games |
| 4. the live meter | `_warn_formal_tag_without_discount`, rookie half | **60 → 0** across the 10 informative seasons |

⚠️ **Leg 1's job is narrow and it did it.** A reproduction pin proves the with-fix leg is judged
against the same population; it does **not** prove the shared computation is correct — a pin can
faithfully reproduce a bug (NCAAF-CLV-repair). Here it earned its place immediately: the first cut
read the study's FOLD list (2019–2025) where the recorded measurement spans
`ERA_MIN_SEASON..max(fold)` = **2016–2025**, and measured 42/34 against a recorded 50/60. The window
is now derived from the study's own constants.

### 3.1 ⚠️⚠️ THE LIVE 2026 CLASS IS **INACTIVE**, and the packet must not read as though it were not

**Not one 2026 rookie carries a formal tag today** — the 53-man cutdown that creates that population
is 2026-08-30. Consequences a reader must have in front of them:

* the live meter reads **0 both with and without the fix**, so "meter = 0 on the live board" is
  **not** evidence the routing works — it is an inactive gate reported as a pass (NF-D20);
* a 2026-only verification leg **passes without testing anything**;
* the with-fix board therefore has **zero rookie rows moved today** (§4).

That is why every leg reports its **ACTIVE** season count beside its pass count and refuses a
verdict with none, and why the routing was exercised on the ten historical classes that actually
carry flagged rookies. **The fix ships ahead of its population, deliberately.**

### 3.2 The coherence clause, and the tolerance that was measured rather than chosen

"The line follows games" asserted on the fp **ratio** at `atol=1e-6` reported a coherence failure on
**9 of 10** real seasons. It was wrong. The volume columns scale to the last bit; `proj_fumbles_lost`
is recomputed from touches and **rounded to 2dp** on both sides at −2/fumble, so

`fp_after − s·fp_before = −2(ε_after − s·ε_before)`, each `|ε| ≤ 0.005` ⇒ **|Δfp| ≤ 0.02 points**,

derived, for any `s ∈ [0,1]`. Measured maximum across all active seasons: **0.0144**. The clause now
asserts exact scaling on the volume columns and reports the fp deviation against that derived bound.

---

## 4. Veteran byte-identity

This is a rookie story; a veteran row must not move by a single float.

* **Code-level:** `apply_availability_chain` is asserted **bit-for-bit** against a transcription of
  the three inline blocks `project_veterans` used to carry, on a frame exercising all three steps at
  once (a flagged row, a returner, an applied override **and a refused one**), with non-vacuity
  asserted first — `test_the_extraction_reproduces_the_old_three_blocks_BIT_FOR_BIT`.
* **Artifact-level:** the operator dry-run rebuild + diff (§6). ⭐ On today's board the expected diff
  is **empty** — no 2026 rookie is flagged (§3.1) — which makes this the cleanest possible
  byte-identity check and is exactly how it should be read: *the fix is inert on today's board and
  arms on 8/30.*

---

## 4.1 ⚠️ The fix is RETROACTIVE on any HISTORICAL board rebuild

`build_projection` now hands the rookie frame its roster status for **every** season it builds, the
backtest folds included. So a rebuild of a historical board moves the rookie rows leg 2 names:
**60 rows across 2016–2025** (6 in 2019, 11 in 2022, …; `leg2.per_season`). That is the fix working,
not a regression — but a future session that rebuilds 2022 and finds 11 rookie rows moved needs to
be able to tell those apart, so it is recorded here.

What this does and does not reach, checked rather than assumed:

* **Interval panels are unaffected.** `nf1_4_rookie_training.parquet` and `nf1_9_veteran_band_panel`
  are built from the warehouse (`load_rookie_training` / `build_veteran_band_panel_season`), not
  from the board parquet, so no interval fit reads a rebuilt board.
* **Veteran-only level fits are unaffected by construction** — the rows that move are rookies.
* **A WHOLE-BOARD read over rebuilt historical boards WOULD see them** (the placement read, and any
  study re-derived from `nfl_fantasy_season_projections_<year>.parquet`). Nothing is being re-fitted
  as part of this ship, so this is a note for whoever next re-runs one, not a blocker.

---

## 5. SECONDARY — the rookie `fp_target` ↔ slot-bucket-games decoupling: **DEFERRED, with the measurement**

Measured on the published 2026 `season_projection` output (`projection_coherence`, the module's own
`frame_coherence_summary`, not a re-implementation):

| population | in scope | violating players | violations |
|---|---|---|---|
| whole board | 777 | **1** | 1 |
| **rookies** | 80 | **1** | 1 |
| veterans | 697 | **0** | 0 |

The single row: **Fernando Mendoza (MEN516487), QB — `passAtt` 614.5 season over 12.38 expected
games = 49.64 per game against an all-time realized max of 45.44 (×1.09).** One row, one stat, 9%
over. It is produced **inside `project_rookies`** (the pre-NF1.5 parquet already carries it), which
confirms NF-INJ1 §2.2's attribution: `fp_target` comes from the slot curve and `proj_games` from the
slot-bucket historical mean, and nothing ties them.

⛔ **NOT ATTEMPTED, and the reason is a rule rather than the clock.** NF-INJ1's own pre-registration
§5 places this decoupling out of scope with *"same class, different code path, **its own
registration**"*, and records the principle directly above it: **"Bundling an availability-level
change with a coherence change makes neither attributable."** NF-INJ3c *is* the availability-level
change — it already moves rookie `proj_games` — so shipping the coherence repair inside it would
make the combined placement + interval read unattributable in exactly the way that sentence
forbids, and would repeat NF-W7e's non-additivity trap (two mechanisms on one quantity must be
registered jointly and the 2×2 measured, never fixed sequentially).

The surface harm meanwhile remains contained by NF-INJ1-C suppression.

**→ PM decision (`closeout.followUps`): register the rookie coherence repair as its own story.** Its
target is now sized precisely — 1 row, `passAtt` only, ×1.09 — which is small enough that the
question *which half is wrong* (cap the point, or raise the games the point implies) is the whole
story, and it interacts with the ratified rookie level machinery (NF-D16/D21 λ = 0.5, NF-D22's
power-derived floor).

---

## 6. Ship path — DEPLOY-HELD

No `--publish` was run and none may be run from this branch. See the session handoff for the
paste-ready operator commands.

⚠️⚠️ **DIFF A/B, NOT AGAINST THE PUBLISHED ARTIFACT.** The published 2026 board was built on
2026-08-21; `dev` has moved since. A rebuild-vs-**published** diff therefore carries every story
that merged in between and **cannot attribute anything to NF-INJ3c** — the operator would be reading
someone else's change and asking why this PR caused it. The attributable comparison is
**A/B on one `dev`**: rebuild at `dev` *without* this PR, rebuild at `dev` *with* it, diff those two.

⭐ Because no 2026 rookie is flagged today (§3.1), that A/B diff should be **exactly empty on every
column** — which is a far stronger veteran byte-identity proof than "only rookie rows moved", and it
is the correct expected result to hand the operator.

`--diff-published/--diff-rebuilt` on `run_nf_inj3c_rookie_availability.py` performs the comparison
either way (its names are positional roles, not a claim about provenance); PASS requires zero
veteran rows moved and identical row membership. It is verified two-sided: an empty diff on a file
against itself, a refusal on a 1e-9 veteran move, and a reported-but-not-refused rookie move.

⚠️ **COMPOSITION.** NF-INJ-NEWS-1 adoption and NF-INJ3b-M's cap change are also pending. **The first
publish carrying any two of these needs ONE final combined placement + interval read** — a per-story
read cannot attribute a board that moved for two reasons.
