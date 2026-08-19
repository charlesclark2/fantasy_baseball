# NF-W7j — the COMPONENT-CLAUSE decision + the served-cell audit

Generated 2026-08-18T07:45:41.528414+00:00 · position **QB** · 8 folds · re-derived from NF-W7f's STORED fold results at ZERO refit

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · research-only. ⛔ This story re-scores ONE clause; NF-W7f's scores are untouched and reproduce byte-identically (prereg §3).

> ⛔ **The component-clause decision cannot certify QB on its own** — `dsr_ok` is a second, independent refusal and is OUT OF SCOPE here (prereg §0.1). The most this decision can do is reduce a two-clause refusal to a one-clause refusal.

## Verdict: **`QB_REFUSED`** · certified for NF-W8: **NO**

- full gate green: **False**
- failing clauses: `['dsr_ok']`
  - anchor: `none` · statistical: `['dsr_ok']`
- null state: **`DSR_UNREACHABLE`**
  - `nf_w7j_component_clause|QB`: the winner's per-fold Sharpe 1.013 sits at or BELOW the 4-arm field's deflated benchmark SR0 5.482, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
  - re-test trigger: `field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)`
  - `field_remedy_admissible`: `None` — **field size is NO LEVER AT ALL here** (`max_field_size < 2`) — there is nothing for admissibility to be ABOUT. ⛔ A bare `None` must NOT be read as "unset" or "unknown": it is the instrument's strongest field reading, and it agrees with NF-W7f's measured 3-arm diagnostic (V falls 8.8×, DSR reaches only 0.174 against a 0.95 bar)
  - ⭐ read as a MACHINE FLAG, never the prose (MH2.7). The reason text still says "the remedy is a SMALLER field"; the flag says it is not.
  - field-shrink flag: `SUSPECT — NOT ADVICE`

## §1 The served-cell audit — does the served paid stat line derive from the W6d cells?

**PASS** — the NF-W6d per-stat cells NF-W7f's recalibration degrades reach NO serving surface — not the published board, not the entitled stat line, not the scorer

> This is the question NF-W7f §12.5b(3) left explicitly unresolved. It is answered by MEASUREMENT over the serving plane — a transitive import-closure walk AND a by-path artifact scan — ⛔ not by a grep over one file (INC-27) and not by argument.

| serving-plane entry point | modules in closure | import hits | artifact-path hits |
|---|---|---|---|
| `quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json` | 18 | **none** | **none** |
| `quant_sports_intel_models.football.nfl.fantasy.season_projection` | 15 | **none** | **none** |
| `app.backend.main` | 65 | **none** | **none** |
| `app.backend.routers.fantasy` | 11 | **none** | **none** |
| `quant_sports_intel_models.fantasy_engine.scoring` | 2 | **none** | **none** |

⭐ **Two LEGS, not one** (INC-27: grep for the PATH, not only the import). An import closure is blind to a consumer that reads the W6d artifact BY FILENAME with no import edge, so every source file that can run on this plane is ALSO scanned for `['nf_w6d_served_stat_distributions', 'nf_w6c_served_stat_distributions', 'weekly_stat_distribution']`. That leg carries its own positive control — the W6d serve builder, which must contain the token (2 hits) or the scan is vacuous.

⭐ **The audit is two-sided** — a walker that resolves nothing returns an empty hit set for every seed, so a PASS would be indistinguishable from a broken audit (NF1.7 (a)). These KNOWN consumers must come back non-empty or the audit RAISES:

| positive control | hits |
|---|---|
| `quant_sports_intel_models.football.nfl.fantasy.run_nf_w7f_qb_marginal` | 10 |
| `quant_sports_intel_models.football.nfl.fantasy.fp_assembly` | 6 |

⚠️ **Scope + expiry.** True of the **SERVING plane only** — the NF-W6/W7 research line consumes the cells and NF-W8 intends to. The audit re-runs on EVERY invocation and the decided clause **fails closed** to the raw 0.0 tolerance if it stops passing, so a future story that wires the cells into a served surface re-arms the hard gate automatically (prereg §1.3).

## §2 The component clause — BOTH readings (NF-D20: the raw clause is never re-labelled)

| reading | rule | measured | refuses? |
|---|---|---|---|
| **RAW** (NF-W7f, pre-registered) | any degradation, tolerance `0.0` | +0.3866% | **YES** |
| **DECIDED** (NF-W7j, prereg §2) | audit ∧ demonstrable ∧ material | see below | **no** |

### The four conditions

| # | condition | value |
|---|---|---|
| A | `served_cell_audit_passes` | **True** |
| B | `demonstrable` | **False** |
| C | `material_primary_relative` | **True** |
| D | `claimed_effect_well_defined` | **True** |

- **B — DEMONSTRABLE**: p(one-sided) = **0.1611** vs α = 0.05; degraded on **5/8** folds; mean **+0.3748%**, CI95 [-0.4575%, +1.2070%]
  - instrument: `nf1_1_model.onesided_paired_pvalue (the harness's own, by identity)`
  - per-fold: `[-1.249, -0.351, 0.739, 1.81, 0.317, 1.418, -0.287, 0.601]` %
- **C — MATERIAL** (primary unit: relative (dimensionless): a 10-leg SUM and a 1-number total share no absolute scale, so the dimensionless form is the comparable one)
  - the arm's claimed effect, relative: **0.7124%** ⇒ materiality band = 0.1 × that = **0.0712%**
  - component change **+0.3866%** = **5.4269× the band**
  - ⭐ CI95 **in band units**: [-6.4216, 16.9438] ⇒ band state **`UNDECIDED_MAGNITUDE`**
  - ⛔ `UNDECIDED_MAGNITUDE` is a BAND decision, **not** `POWER_LIMITED` (NF-W7i)
  - sensitivity, ABSOLUTE unit: +0.13909 CRPS vs a band of 0.00184 ⇒ material = **True**; units agree: **True**

## §3 Reproduction pin — the decision is measured against the object NF-W7f scored

| pinned quantity | NF-W7f | reproduced |
|---|---|---|
| `per_leg_relative_change` | 0.003866 | ✅ |
| `per_leg_relative_change_winner_by_fold_mean` | 0.003748 | ✅ |
| `per_leg_tolerance` | 0.0 | ✅ |
| `mean_delta` | 0.0184 | ✅ |
| `ci95_lo` | 0.0032 | ✅ |
| `ci95_hi` | 0.0336 | ✅ |
| `matched_foil_mean_crps` | 2.5829 | ✅ |
| failing clauses | `['dsr_ok', 'per_leg_calibration_not_degraded']` | ✅ |
| gate clause count | 22 | ✅ |

## ⭐ What this leaves — QB's blocker set, before and after

| | NF-W7f | NF-W7j |
|---|---|---|
| clauses refusing the ship | **2** (`per_leg_calibration_not_degraded`, `dsr_ok`) | **1** (`dsr_ok`) |
| null state | `CONSTRAINT_REFUSED`, `binding_half: anchor` | `DSR_UNREACHABLE` |
| re-test trigger | `None` (an anchor half is not rescuable by data — NF-D18) | field size is no lever; the only lever is a LOWER-VARIANCE DESIGN |
| certified for NF-W8 | NO | NO |

⭐ **The deliverable is the CHANGE OF KIND, not a ship.** NF-W7f's refusal mixed an undecided governance question with a statistical one, so its null could name no remedy at all. With the governance half decided, the refusal is purely statistical, `classify_null` runs (the call NF-W7f's mixed-refusal path bypassed), and the blocker is now named with a mechanism and a registered lever.

⛔ **The lever is NOT more data and NOT a smaller field.** NF-W7f measured both: field coherence cuts `V` 8.8× and still reaches DSR 0.174, and `n` enters only through `√(n−1)`, so it scales a positive gap but cannot create one. The candidate lever is MONTE-CARLO error in the per-fold deltas at 4,000 draws (per-fold mean 0.0184, sd ≈ 0.0182, two negative folds) — ⛔ which must be registered FORWARD as its own story, is NOT a claim that it would clear, and is out of scope here.

## Promote blockers

- NF-W7j decides ONE clause and audits ONE condition; it re-scores nothing and refits nothing — NF-W7f's scores stand byte-identical
- the component-clause decision CANNOT certify QB on its own: `dsr_ok` is a second, independent refusal, out of scope here (prereg §0.1)
- the served-cell audit licenses the relaxation for the SERVING plane only — the NF-W6/W7 research line consumes the cells and NF-W8 intends to (prereg §1.3)
- NF-W7f's and NF-W7c's promote blockers are inherited in full, including NF-W7c §4's rule that a per-position-certified distribution may not feed a CROSS-POSITION ranking

## ⭐ Flagged for a 2nd reader (governance — prereg §5)

1. **The clause decision itself.** A pre-registered gate is replaced by a materiality gate. Protections: the licensing audit is mechanical and fails closed, the raw clause stays scored and printed, the rule SHAPE is NF-W7c's (named by NF-W7f §12.5b(3) before this story existed), and the decision cannot buy a ship. ⛔ The disclosure in prereg §0.2 stands: NF-W7f had already PUBLISHED the shape of the refusing quantity, so this decision is not made blind.
2. **The certification bar for NF-W8 consumption.** This story holds QB to the FULL gate — the bar NF-W7h pre-registered for RB and the one WR (NF-W7e, DSR 0.9852) and TE (NF-W7c, DSR 0.9822) actually cleared. A three-part *PIT + component + beats incumbent* reading omits `dsr_ok`; adopting it after seeing `dsr_ok` fail would be the E2.1-r inversion and would certify QB on a bar the other three positions were never held to. If a distinct, lower CONSUMPTION bar is intended, it is a PM decision to register FORWARD in NF-W8.
