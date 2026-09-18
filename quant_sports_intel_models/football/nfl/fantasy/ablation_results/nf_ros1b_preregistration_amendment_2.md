# NF-ROS1b — pre-registration amendment 2 (PM ruling 2026-09-17): a POST-SMOKE COMPANION DIAGNOSTIC

Amends `nf_ros1b_preregistration.md` §7. It is committed **after the 2-fold smoke** (a code-path
proof, never a gate) and **before the decisive run**. The PM approved it with the constraints below,
which are binding.

## Why

**The registered prediction.** §7 predicted that under the hurdle, the top tercile's q05 = 0 share
"falls toward the realized zero share."

**Why that prediction was misconceived.** A q05 = 0 share is **not a calibration reading**. A
correct predictive puts q05 at 0 exactly when P(zero) ≥ 0.05. If everyone sits at 6%, the share is
100% beside a 6% zero rate. The smoke showed it: the hurdle's share rose at QB (0.196 → 0.488) while
its lowest PIT decile nearly halved (0.227 → 0.112).

**What the misconception implies for the parent.** It is inherited from the parent's §13.1
reading. NF-ROS1's headline share figure ("29.9% vs 5.2%") was not, by itself, evidence of
miscalibration. Its PIT and lowest-decile readings were.

## What is added

**`POST-SMOKE COMPANION DIAGNOSTIC — top-tercile atom calibration`.**

* **Scope:** per position, for the winner under the hurdle, on the same top tercile of the point that
  §7's mechanism check uses (tercile edges cut per position on the pooled decisive-run points).
* **What it reports:** the **mean predicted P(zero) (π)** against the **realized `y ≤ 0` share**, and
  their difference.

## Constraints (binding)

1. It is labelled **POST-SMOKE COMPANION DIAGNOSTIC** here and in every output that carries it.
2. It **gates nothing**, enters no clause C1–C9, joins neither V nor PBO nor DSR, and takes no part in
   any verdict or null-classification logic.
3. The registered §7 reading **stays exactly as written**. It is reported as a **failed prediction**,
   with the explanation above attached. It is not re-labelled, removed or replaced.
4. The family, its parameters and every bar are unchanged.
