# NF-INJ2c node 3b — the capture-pinned dominance baseline

> ⛔ A BOARD MEASUREMENT, not a bake-off: no arm is scored against a realized outcome and no CV gate is computed here. The fold measures M1/M5/M6 belong to the decisive run.

Generated 2026-09-01T06:47:21.260981+00:00. PM re-scope ruling 3.

## 1. The capture (D3 — pinned against a CAPTURED artifact, never a re-pull)

| field | value |
|---|---|
| captured_at | 2026-09-01T06:25:40.433554+00:00 |
| served `generated_at` | 2026-09-01T06:04:18.984355+00:00 |
| sha256 | `817e3b5dbf469577...` |
| players | 871 |
| local MVP-1 `generated_at` | 2026-09-01T06:25:35.95858 |
| lag vs served | 0.35h (bar 48.0h) |

**Reproduction pin:** worst absolute difference **1.8163546006541402** over 797 rows against a tolerance of 0.05 ⇒ **False**.

> ⛔ **THE PIN DOES NOT HOLD, so this run is VOID — not a null** (margin rule §5 branch 3). A dominance claim against a board nobody is served is not a measurement.

## 2. The board-level dominance measures, against the SERVED incumbent

Bands are READ from `nf_inj2c_margin_construction_rule.md` (node 3a, committed BEFORE this ran); ⛔ none is defined here.

| arm | M2 attributable viol. | Δ vs inc | M2 | M3 worst × | M3 | M4 give-back (measure) | M4 signed | M4 | clamp hi/lo |
|---|---|---|---|---|---|---|---|---|---|
| `mvp1_null` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | 0.0 | IMPROVES | 0/0 |
| `incumbent` | 10 | +0 | TIES | 1.9318 | TIES | 88.34 | 88.34 | TIES | 14/21 |
| `stratified` | 7 | -3 | IMPROVES | 1.7973 | IMPROVES | 25.39 | 25.39 | IMPROVES | 6/14 |
| `feasibility_clamp` | 3 | -7 | IMPROVES | 1.0924 | IMPROVES | 87.93 | 87.93 | IMPROVES | 13/21 |
| `points_rate_permute` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | -11.23 | IMPROVES | 1/3 |
| `rate_refit` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | -4.81 | IMPROVES | 0/3 |
| `points_rate_stratified` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 0.0 | -0.57 | IMPROVES | 0/3 |
| `rate_refit_stratified` | 0 | -10 | IMPROVES | 1.0924 | IMPROVES | 5.49 | 5.49 | IMPROVES | 0/3 |

⭐ **M4 is `max(give_back_pct, 0)`** — declared in the margin rule §3(a) before this ran, because the defect NF-INJ1 named is injured players marked back UP; the SIGNED figure is reported beside it always.

⭐ **ATTRIBUTION BY CONTROL:** violations also produced by `mvp1_null` (the ordering step OFF) are subtracted — a defect present with the mechanism disabled is not caused by the mechanism

⚠️ M1 (CRPS), M5 (per-position ordering) and M6 (interval floors) are FOLD measures and are UNEVALUATED here — named rather than silently omitted, because a dominance table missing three of its six measures must not read as a complete one (NF1.7 (a)).

