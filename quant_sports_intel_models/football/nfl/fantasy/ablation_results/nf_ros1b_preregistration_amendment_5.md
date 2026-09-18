# NF-ROS1b — amendment 5 (2026-09-18): the per-player spread the PM's disposition is made on

⛔ **GATES NOTHING. NO BAR MOVES. NO NUMBER IS RE-SCORED.** Amendment 3's statistic and decision
rule are untouched and have already fired: the RB-rookie C9 read returned **0.08101092896174864**
against the **0.05** bar ⇒ **`STOP_TO_PM`**. That decision is final for this story; nothing below
can reverse it, soften it, or produce a second reading of it. No in-story iteration past the
registered family.

**Why this exists.** The PM's 2026-09-18 ack said, of the stop-and-report branch: *"the burden then
sits on the disclosed-note-vs-absence choice, and I'll make it on the number plus the per-player
spread."* The number exists; the spread does not, because amendment 3 did not ask the read to emit
it. This amendment defines it **before it is computed**, so the descriptive evidence the PM's
residual choice rests on cannot be shaped by having seen it.

---

## 1. The reproduction requirement (this is the load-bearing part)

The spread is computed by **re-running the same entrypoint from committed code**, extended
additively. Because that re-run happens AFTER its own result is known, it must PROVE it changed
nothing:

* the spread is computed from the **same randomized-PIT draw** the read already made (`u` is reused,
  never re-drawn — a second draw would be a second reading of the gate);
* the runner compares the new `pit_max_decile_dev`, `coverage80` and `decision` against the prior
  artifact on disk and records `reproduction.identical` in both outputs;
* **if the decision number moves at all, the spread is void** and what gets reported to the PM is
  that discrepancy, not the spread.

## 2. What is computed (descriptive, all of it)

Rookie stratum only, same population as the read (RB, `rookie = True`, pooled over the six decisive
folds; 1,464 rows / 122 player-seasons):

1. **Per-player-season mean PIT** — each player-season's mean `u` over its rows, and the decile
   histogram of those 122 means. Under a calibrated predictive these concentrate toward 0.5 as rows
   accumulate; a rightward mass says the stratum's outcomes sit high in their own predictive.
2. **Concentration of the top-decile excess** — of the rows in the top PIT decile: how many distinct
   player-seasons they come from, the share contributed by the ten largest contributors, and the
   number of player-seasons with EVERY row in the top decile.
3. **The decile shares read under both dependence assumptions** — for each decile,
   `z = (share − 0.10) / sqrt(0.10 × 0.90 / n)` with `n` = rows (independence) and `n` =
   player-seasons (full within-player clustering). This is amendment 3's own framing extended from
   the maximum to the SHAPE: amendment 3 bounded how often a calibrated predictive produces a
   max-decile deviation this large; it said nothing about whether the deviation is flat-random or
   directional, and those two are different findings.
4. **The veteran complement**, same quantities, context only — it is the control that says whether a
   shape is a property of the rookie stratum or of the position.

## 3. What the spread is FOR, and what it is not

It discriminates between two pictures that produce the same 0.081:

* the excess is **carried by a few player-seasons** (a handful of rookie breakouts the band could
  not have anticipated) — the stratum is broadly right and a **disclosed note** fits;
* the excess is a **broad directional tilt** across most rookie player-seasons — the band is
  systematically wrong for the stratum, and a **stated absence** fits.

⛔ This amendment does NOT pre-commit which. The PM framed both options in R2 and holds the choice.
⛔ And no threshold is declared here for "few" versus "broad": inventing one after the stop fired
would be exactly the bar-after-the-answer inversion (E2.1-r) this story has been run to avoid. The
spread is reported as measured, and the PM reads it.

## 4. Scope of the consequence, stated plainly

Whichever option is taken, it changes only how the rookie rows of a certified position are SERVED.
It does not touch C1–C9, the certification, or RB's position-level numbers. Node 4's live dry run
(week 1, 2026) carried **13 synthetic-id rookie rows inside the 197 certified RB rows** — that is
the blast radius today, and it grows as rookies accumulate games.
