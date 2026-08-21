# NF-INJ1 §0.5 PRE-REGISTRATION — restoring (games, line) coherence to the served board

Written **before any arm is scored**. Diagnosis: `nf_inj1_diagnosis.md`. `best_alpha = 0`.

⛔ This document is the record. A change to it after a result is not a pre-registration (E2.1-r).
Anything overturned by the decisive run is left in place under a `SUPERSEDED` marker, verbatim
(NF-W7f).

---

## 1. The hypothesis

`nf1_model.apply_learned_level` rescales the twelve stat columns to the point level the NF1.5
ordering assigns, and leaves `proj_games` untouched. Because MVP-1's point is `per-game rate ×
expected games`, permuting the season-point multiset within a position **redistributes the
availability discount**. Measured: ρ(`proj_games`, `nf1_scale`) = −0.187 (p = 6.6e-07, n = 697),
significant at all four positions; 9 served rows are physically impossible at their own `g`.

**H1.** Permuting the per-game **RATE** multiset and re-multiplying by each player's **own**
`proj_games` restores coherence by construction **without** losing the ordering skill the NF1.5
bake-off validated.

**The question that decides it is not "is it more coherent" — it is coherent by construction.** It is
whether the *ordering* survives, and whether the served point level is not made worse.

⭐ **MEASURED TARGET (diagnosis §7.2, post-publish 2026-08-21).** On the 23-row injury-capped cohort
the ordering step hands back **+36.4%** of the availability discount in aggregate (median point ratio
1.292; 18 of 23 scaled up). `rate_permute` should remove that give-back **without** losing held-out
within-position ρ. The matched-vintage whole-board gradient to close is ρ(games, point ratio) =
**−0.213** (p = 1.4e-08, n = 697); a successful arm drives it to ~0 by construction, so ⛔ it is **not**
a discriminator between arms and must not be reported as one — it is a precondition.

---

## 2. Arms (declared forward; this IS the field for DSR)

| arm | what it does | role |
|---|---|---|
| `incumbent` | today's season-POINT multiset permutation | the thing to beat |
| `rate_permute` | permute the per-game RATE multiset; multiply by the row's own `proj_games` | **primary** |
| `stratified` | permute the point multiset **within availability strata** (`g` terciles) | keeps the point estimand, bounds the transfer |
| `feasibility_clamp` | incumbent, with `nf1_scale` bounded so the envelope cannot be breached | minimal/symptomatic |
| `mvp1_null` | no re-order at all | pre-registered **degenerate**, must LOSE |
| `random_order` | a within-position random permutation, seeded | pre-registered **degenerate**, must LOSE |

`declared_field_size = 6`, passed to `cv_power.classify_null(declared_field_size=6)`; read
`field_remedy_admissible`, not the prose (MH2.7). ⛔ **No post-hoc trim** (MH2.2). Per DSR-CONV the
two degenerates are declared **now** as degenerates — that convention is fixed here, before any
score, and the whole-field figure is reported beside the degenerate-excluded one either way.

**Matched foil (NF-D15 g′ — to attribute the win to the claimed channel, not merely to earn one):**
`rate_permute_games_frozen` — identical machinery, but re-multiplying by the position's MEAN games
instead of the player's own. If `rate_permute` beats the incumbent and this foil does not, the lift
is the **per-player availability** channel, which is the stated mechanism. If both win equally, the
mechanism claim is refuted and the win is a level effect.

---

## 3. Metric + gates

* **Primary:** CRPS on realized season PPR, walk-forward over base seasons (the `run_nf1_5`
  `walk_forward_pos` harness), per position.
* ⛔ **MAE never selects** — the target is skewed and the low-`g` cohort is exactly where the
  conditional median sits near the floor (NF-D11 / NF-D14). The all-zero degenerate is **scored every
  run** and its score READ, not reasoned about.
* **Ordering must not regress:** held-out within-position Spearman ρ vs the incumbent — this is what
  the original NF1.5 bake-off actually validated, so it is a constraint, not the selector.
* **Coherence (the constraint this exists to satisfy):** violating players against
  `projection_coherence.REALIZED_MAX_PER_GAME` must be **0**. ⚠️ Reported for **every** arm including
  the degenerates — a constraint a degenerate satisfies is fine (the metric then eliminates it); a
  *criterion* a degenerate wins is fatal (NF1.8). `rate_permute` satisfies it by construction, so it
  is explicitly **not** a discriminator and must not be presented as one.
* **Gates:** PBO < 0.2, DSR > 0 at the 6-arm field, BH-FDR across positions, and the fold-consistency
  clause via `h_harness.numeric_gate(n_folds=…)` (never the raw 0.60 rate — MH2 H8).
* **Anchors:** an oracle floor at **matched n and matched form** (NF1.7 (b) / NF1.9 (f)), one
  ceiling **per form** (NF-D16 g‴ — the forms nest: `feasibility_clamp` contains `incumbent`), and a
  permutation anchor **registered in advance as an expected TIE** for any level-only comparison
  (NF-D16), proven rather than presented as a passed test.

**If DSR fails:** compute the 2×2 (series × field) **as a labelled diagnostic** before naming a
remedy, and check the lockstep invariant — a shared-variance lever (more rows/folds/draws) is
**deterministically void** for `dsr_ok` (NF-W8-0d), so ⛔ publish no season/fold re-test trigger for
it. If the winner is `V`'s largest contributor, the field-trim reading is **inadmissible** (NF-W7h).

---

## 4. Level-adjacency — the gates this trips

`rate_permute` changes the served point distribution (the season-point multiset is no longer
preserved), so it is **level-adjacent** and must clear, before any publish:

1. **Whole-board cross-position placement read** — `run_nf_tr2b_placement_read` against the published
   artifact. ⚠️ The NF-W8-0 VOR "shield" is **additive-only**; this correction is not additive, so the
   shield does **not** excuse the read (NF-TR2b), and it does **not** hold at all under the two
   **superflex** configs, where QB is cross-pooled — and QB is the position this story moves most.
2. **Interval revalidation** — `run_interval_revalidation`; the NF1.9 per-player band is priced off
   the point and must follow it. Per-group coverage floors use **`power_floor()`**, derived from each
   group's n and the pre-registered false-reject target — ⛔ never a flat nominal point-floor
   (NF-D22).
3. **Rookie placement cap** — NF-D18/D20; and per NF-TR2b the build-time face-validity check ranks by
   PPR while the served boards rank by VOR **per config**, so the placement read must be run against
   the **published** artifact per config, not the build frame.

---

## 5. Explicitly out of scope (kept separable — NF-W7d)

* **The injury cap constants** `{RES: 4, PUP: 4, NFI: 4, SUS: 7}` at blend 0.7 (diagnosis §1.3, plan
  §5d). Bundling an availability-level change with a coherence change makes neither attributable.
* **The rookie `fp_target` ↔ slot-bucket-games decoupling** (§2.2 / §5c) — same class, different code
  path, its own registration.
* **The weekly game-report channel** (Q/D/O), deliberately unmapped since NF-D2 slice 5.

---

## 6. Pre-committed reading of the likely outcomes

* **`rate_permute` wins or ties on CRPS, holds ρ, and the matched foil loses** → SHIP, subject to §4.
* **`rate_permute` ties the incumbent on CRPS and holds ρ** → still ship it: coherence is a
  correctness constraint the incumbent *fails*, and a tie on the selecting metric is not a reason to
  keep serving an impossible stat line. This is written down **now** precisely so it cannot look like
  a post-hoc rescue.
* **`rate_permute` clearly LOSES on CRPS or ρ** → do not ship it. Fall back to `stratified` /
  `feasibility_clamp`, and if neither clears, record the null and keep the ALERT-tier guard — with
  the honest statement that the board serves a known-impossible line on ~9 rows and that the PM's
  `--strict-coherence` decision is then the live lever.
* **A null caused by the placement/interval constraint rather than the metric** → classify
  `CONSTRAINT_REFUSED`, ⛔ **not** `POWER_LIMITED`, and publish **no** "more seasons" trigger — no
  sampling error accumulates in a board rank (NF-D18).
