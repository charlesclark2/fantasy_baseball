# NF-INJ4b — the designation → duration model under a MATCHED-RESOLUTION oracle anchor

**Verdict: `SHIP_CANDIDATE (DEPLOY-HELD)`.** `best_alpha = 0`. **DEPLOY-HELD** — the served Questionable / Doubtful / Out availability discount is EXACTLY ZERO until the gated ship path and explicit operator approval.

---

## ⛔ 0. Read this before any number below

**This study buys a PROPERLY-REGISTERED RECORD of an ALREADY-MEASURED result. It is not new evidence and it is not fresh confirmation.**

NF-INJ4 measured this mechanism and published it. The field, the folds, the seed and the substrate here are NF-INJ4's — the fold machinery is IMPORTED from its runner verbatim, and the substrate was vintage-checked against its committed census before this registration was written. So **every number below was already known, and only the gate flips.**

The reproduction pin is the proof of that claim: **34 of 34 published figures reproduce** at the artifact's own resolution. ⛔ What that certifies is the PIPELINE — that "only the gate flips" is a measurement. It certifies NOTHING about the mechanism: reproducing a known number is not evidence for the hypothesis that produced it.

⭐ **The one genuinely NEW result is the positive control's verdict** (§4), because the control drives the study's own gate function and this registration changes that function.

⛔ NF-INJ4's registration, verdict and record stand UNEDITED. This supersedes ONE clause going forward and never re-reads its refusal (E2.1-r).

---

## 1. The gates, in the registered order

| gate | class | result |
|---|---|---|
| `beats_incumbent` | metric | ✅ PASS |
| `beats_foil` | metric | ✅ PASS |
| `fold_consistency` | metric | ✅ PASS |
| `bh_ok` | metric | ✅ PASS |
| `anchor_pair_informative` | invariant | ✅ PASS |
| `oracle_floor_matched_resolution` | invariant | ✅ PASS |
| `beats_permutation` | metric | ✅ PASS |
| `dsr_ok` | deflation | ✅ PASS |
| `degenerates_lose` | invariant | ✅ PASS |

**Winner: `desig_x_practice`** — pooled CRPS 0.4987 against the matched status-blind foil's 0.6394 and the served incumbent's 0.7994.

Lift over the foil **+0.1408 CRPS** on **10 of 10 folds**, one-sided p = 0 against the binding single-hypothesis cutoff 0.05 (the conservative arm-corrected 0.00714 is cleared too). PBO 0 over the eligible set and 0 over the declared field; DSR-CONV 0.9999.

---

## 2. ⭐ The anchor, at MATCHED RESOLUTION — the one clause this story changes

The registered clause NF-INJ4 refused on read *"no arm beats its own-form oracle"*. That oracle is fitted on a **131-row test fold** against arms trained on **1178 rows** — a **9.0× ratio fixed by the CV design** — so it measured the ORACLE'S SAMPLE SIZE, not any property of an arm.

NF1.9 (f): a peeking oracle is a floor **only at matched `n`**. Both readings of that one measured pair are registered here as SEPARATE named clauses, because registering one does not give you the other.

| arm | arm CRPS | oracle | matched-n control | oracle − control | state |
|---|---|---|---|---|---|
| `desig_empirical` | 0.5172 | 0.6068 | 0.6406 | -0.033725 | ACTIVE |
| `desig_x_posgroup` | 0.5201 | 0.6036 | 0.6383 | -0.034606 | ACTIVE |
| `desig_x_practice` | 0.4987 | 0.6015 | 0.6420 | -0.040560 | ACTIVE |
| `fixed_penalty` | 0.6335 | 0.6335 | 0.6335 | +0.000000 | INACTIVE |
| `status_blind_foil` | 0.6394 | 0.6255 | 0.6402 | -0.014705 | ACTIVE |
| `always_zero` | 0.7994 | 0.7994 | 0.7994 | +0.000000 | INACTIVE |
| `always_max` | 8.2657 | 8.2657 | 8.2657 | +0.000000 | INACTIVE |

**A — `anchor_pair_informative` (NF-W6d inactive-pair): ✅ PASS.** 4/7 evaluable pairs are ACTIVE; the active shippable arms are `desig_empirical`, `desig_x_posgroup`, `desig_x_practice`. An INACTIVE pair had nothing to act on and is UNINFORMATIVE — neither a refusal nor a pass.

**B — `oracle_floor_matched_resolution` (NF1.9 (f) capacity): ✅ PASS.** The floor holds on 7/7 evaluable pairs — but ⚠️ it is VACUOUS on the 3 INACTIVE ones (`always_max`, `always_zero`, `fixed_penalty`), so the number that carries information is **4/4 active pairs** (NF-D20: count what the mechanism could ACT on before crediting "the constraint held N of M").

⭐ **The tie tolerance is measurably not load-bearing.** Every ACTIVE pair sits orders of magnitude clear of the ±1e-06 band (smallest active margin 0.014705, i.e. ~14,705× the tolerance), and every INACTIVE pair is an EXACT tie. An activity classification is not a magnitude (NF-W7f), so the margins are published rather than the labels alone.

⛔ **The retired naive clause is still reported.** It reads FALSE on `desig_empirical`, `desig_x_posgroup`, `desig_x_practice` — exactly as NF-INJ4 measured. In THIS design an arm beating its own peek can only be CAPACITY, never leakage: the arms are fitted strictly on training rows disjoint **by player**, so leakage is excluded by the FOLD CONSTRUCTION rather than by the anchor. ⚠️ That does not generalise — in a design where an arm could see its own test rows, the naive clause is the thing that catches it.

⭐ **The anchor construction is self-checked, not assumed:** the matched-n control is fitted on 131 rows against a peek of 131 — matched on every fold: **True**. A control that silently fitted at FULL resolution would make both clauses vacuous while still returning a number.

---

## 3. The forward invariance declaration, and the ladder that could have refuted it

Both anchor clauses were declared **injection-invariant FORWARD** — the declaration NF-INJ4 said belonged to its successor. `degenerates_lose`, `anchor_pair_informative`, `oracle_floor_matched_resolution`.

| effect (games) | `beats_incumbent` | `beats_foil` | `fold_consistency` | `bh_ok` | `anchor_pair_informative` | `oracle_floor_matched_resolution` | `beats_permutation` | `dsr_ok` | `degenerates_lose` |
|---|---|---|---|---|---|---|---|---|---|
| 0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 0.5 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 1.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 4.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

⭐ NO declared-invariant clause MOVED with the planted effect, up to 4x the registered size — CONSISTENT with the forward declaration. ⚠️ It is not PROOF: a clause that PASSES at every rung has nowhere to move upward, so this ladder can only REFUTE the declaration, never confirm it. Reported as consistency, never as a passed check (NF1.7 (a)).

---

## 4. ⭐ The positive control — the one genuinely NEW result, and it is not what was expected

The PLAT-CVP2 injected-effect positive control returned **`VACUOUS`** (partition `gate_classes`, verified `True`). ⛔ **That badge STANDS exactly as the instrument returned it** (E2.1-r). At the registered 1-game effect all three shippable arms clear every gate with an EMPTY blocking set — but the badge is decided by the null-control leg, on which the same three arms also survive.

⭐ **The claim behind the badge was MEASURED, not argued** — NF-INJ4's own handling of a badge it disagreed with is the precedent. Running the SAME gate table on payloads where the mechanism is genuinely ABSENT (designations shuffled, every marginal preserved):

| shuffle seed | survivors | failing gates |
|---|---|---|
| 11 | **none** | `beats_foil`, `beats_permutation`, `bh_ok`, `dsr_ok`, `fold_consistency` |
| 22 | **none** | `beats_foil`, `beats_permutation`, `bh_ok`, `dsr_ok`, `fold_consistency` |
| 33 | **none** | `beats_foil`, `beats_permutation`, `bh_ok`, `dsr_ok`, `fold_consistency` |
| 44 | **none** | `beats_foil`, `beats_permutation`, `bh_ok`, `dsr_ok`, `fold_consistency` |
| 55 | **none** | `beats_foil`, `beats_permutation`, `bh_ok`, `dsr_ok`, `fold_consistency` |

⭐ ZERO arms survive on a genuinely mechanism-ABSENT payload, on every shuffle, with the metric and deflation gates failing each time. **The gate family does NOT certify noise.** ⇒ the `VACUOUS` badge is an artifact of the null leg's PAYLOAD SPECIFICATION, not a property of these gates — see `null_control_leg_specification`.

⭐ **The instrument finding, stated generally rather than as this study's excuse.** With `inject(0.0)` defined as the IDENTITY the null payload IS the real data, so **a study that SHIPS cannot avoid `VACUOUS`** — its winner clears every gate on the real data, which makes it a survivor on the null payload. That direction is EXACT. ⚠️ The converse is not, and the distinction is stated because an over-stated instrument finding is what propagates: `VACUOUS` says only that SOME arm cleared every gate on the real data — a statement about the study's own RESULT, never about the gate family's SENSITIVITY, which is what the leg is read as measuring. Either way, for a caller defining `inject(0) = identity` the leg carries no information about the gate family.

⭐ **And NF-INJ4's clean null leg was clean for the WRONG REASON**, which is why this could not have been seen before now: it recorded `null_control_survivors: []`, but its `oracle_respected` clause was FALSE on the real payload, so it blocked every arm on the identity payload too. The defective anchor was MASKING the mis-specification. ⛔ NF-INJ4's verdict and record stand unedited; this is drawn from its own published figures.

⚠️ **This is a DEFECT IN THIS REGISTRATION and is reported as one.** The pre-registration predicted the control's PBO leg would be inert and said NOTHING about the null leg, whose identity-at-zero specification it inherited verbatim and did not examine. ⛔ The remedy — a MECHANISM-ABSENT null payload rather than an UN-INJECTED one — is a FORWARD decision for the PM, not something adopted here after seeing the badge.

---

## 5. What the record must NOT say

- ⛔ Not *"the mechanism is confirmed"* — the evidence is NF-INJ4's, and this run reproduces it by construction.
- ⛔ Not *"replicated"* — same field, same folds, same seed, same rows. A reproduction pin is a pipeline check.
- ✅ What it does say: the mechanism's evidence is now held under a registration whose anchor clause measures an ARM PROPERTY instead of a FOLD SIZE, so the refusal that blocked it no longer stands in the way.
