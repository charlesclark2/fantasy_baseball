# NF-INJ2c node 3b — the capture-pinned dominance baseline

> ⛔ A BOARD MEASUREMENT, not a bake-off: no arm is scored against a realized outcome and no CV gate is computed here. The fold measures M1/M5/M6 belong to the decisive run.

Generated 2026-09-04T06:07:26.316035+00:00. PM re-scope ruling 3.

## 1. The capture (D3 — pinned against a CAPTURED artifact, never a re-pull)

| field | value |
|---|---|
| captured_at | 2026-09-04T06:04:16.905208+00:00 |
| served `generated_at` | 2026-09-04T06:03:38.723266+00:00 |
| sha256 | `89bbbd5b5d301863...` |
| players | 871 |
| local MVP-1 `generated_at` | 2026-09-04T06:06:10.62193 |
| lag vs served | 0.04h (bar 48.0h) |

**Reproduction pin:** worst absolute difference **0.05000000000000071** over 797 rows against a tolerance of 0.05 ⇒ **True**.

## 2. The board-level dominance measures, against the SERVED incumbent

Bands are READ from `nf_inj2c_margin_construction_rule.md` (node 3a, committed BEFORE this ran); ⛔ none is defined here.

| arm | M2 attributable viol. | Δ vs inc | M2 | M3 worst × | M3 | M4 give-back (measure) | M4 signed | M4 | clamp hi/lo |
|---|---|---|---|---|---|---|---|---|---|
| `mvp1_null` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | 0.0 | IMPROVES | 0/0 |
| `incumbent` | 10 | +0 | TIES | 1.9947 | TIES | 89.26 | 89.26 | TIES | 18/25 |
| `stratified` | 6 | -4 | IMPROVES | 1.7467 | IMPROVES | 30.02 | 30.02 | IMPROVES | 5/11 |
| `feasibility_clamp` | 4 | -6 | IMPROVES | 1.0924 | IMPROVES | 87.88 | 87.88 | IMPROVES | 16/25 |
| `points_rate_permute` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | -10.24 | IMPROVES | 1/6 |
| `rate_refit` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | -4.05 | IMPROVES | 0/5 |
| `points_rate_stratified` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 3.58 | 3.58 | IMPROVES | 0/5 |
| `rate_refit_stratified` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 7.63 | 7.63 | IMPROVES | 0/4 |

⭐ **M4 is `max(give_back_pct, 0)`** — declared in the margin rule §3(a) before this ran, because the defect NF-INJ1 named is injured players marked back UP; the SIGNED figure is reported beside it always.

⭐ **ATTRIBUTION BY CONTROL:** violations also produced by `mvp1_null` (the ordering step OFF) are subtracted — a defect present with the mechanism disabled is not caused by the mechanism

⚠️ M1 (CRPS), M5 (per-position ordering) and M6 (interval floors) are FOLD measures and are UNEVALUATED here — named rather than silently omitted, because a dominance table missing three of its six measures must not read as a complete one (NF1.7 (a)).

