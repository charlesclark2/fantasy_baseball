# NF-ROS1b — pre-registration amendment 3 (PM ruling R2, 2026-09-17): the RB-rookie C9 read

Amends `nf_ros1b_preregistration.md` after its §13 was written. It is committed **before the
RB-rookie reading exists**. It records the PM's decision rule so the read cannot become a post-hoc
negotiation.

## The read

**Population.** The certified position (RB), restricted to `rookie = True`, pooled over the six
decisive folds (2020–2025). It is the same frame, point and hurdle predictive as the decisive run,
regenerated from committed code.

**Statistic.** C9's statistic, unchanged: the randomized-PIT max-decile deviation on rows.

* Seed: `20260917 + 300` (the §7 diagnostic stream plus a fixed offset; never the gate's own
  per-position seed).
* The run also reports:
  * the RB-rookie 80% coverage;
  * row and player-season counts;
  * the RB-veteran complement, as context only.

## The decision rule (PM R2, declared before the number)

* **RB-rookie C9 ≤ 0.05** (the same bar, no invention) ⇒ RB rookies serve as registered, and the
  reading is recorded as *the stratum check passing*.
* **RB-rookie C9 > 0.05** ⇒ **STOP.** The number goes to the PM with two options framed:
  * (i) serve with a disclosed rookie-stratum note on the affected rows;
  * (ii) serve rookie rows as a stated absence.

  That residual choice is the PM's, made on the evidence, on this pre-declared trigger.

## Design quantity, computed BEFORE the reading (counts only; no PIT value was computed)

The stratum holds **1,464 rows across 122 RB-rookie player-seasons**. Under a perfectly calibrated
predictive, the chance that this statistic exceeds 0.05 (4,000 simulations, seed 20260917) is:

| assumption | P(> 0.05) |
|---|---|
| rows independent | **≈ 0.000** |
| fully clustered: one PIT value shared by a player-season's 12 k-rows | **≈ 0.51** |

The truth lies between the two. ROS totals at neighbouring k overlap heavily, so rows within a
player-season are strongly correlated. **At this sample size, a reading above 0.05 is therefore not,
by itself, evidence that the rookie band is miscalibrated.** The same false-reject class that NF-D22
measured for coverage floors applies here.

This does **not** change the rule. The PM declared it, and the bar is the registered C9 bar. The
design quantity is recorded so that a reading on either side is read with its resolution in view.
