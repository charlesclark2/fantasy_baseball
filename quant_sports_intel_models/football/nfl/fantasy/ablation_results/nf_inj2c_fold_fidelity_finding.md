# NF-INJ2c node 3c — the +1 fold, on DATA-FIDELITY grounds: **2018 IS NOT ADMITTED**

**Committed before the pre-registration.** PM re-scope ruling 4: *"THE +1 FOLD is registered forward
on the data-fidelity ruling already given (2018 admitted only if data-honest; state the finding
either way). DSR at 8 folds is then a real gate, not a formality — 0.9325 at 7 does not guarantee
0.95 at 8."*

**The finding, stated either way as ordered: 2018 is NOT data-honest, and admitting it would move the
DSR gate the WRONG WAY.** Three measured legs, each independent of the others.

> ⚠️ The third leg is a diagnostic computed ON THE ARM, and it comes out ADVERSE to the arm. That is
> stated up front because a fold ruling that happened to favour the arm would deserve more suspicion
> than one that does not.

---

## Leg 1 — at the registered configuration the fold does not exist

`capture_fold` and `build_season_projection` derive a fold's training pool as
`base_seasons = [b for b in range(base_from, projection_season − 1) if b + 1 < projection_season]`,
at the SHIPPED default `base_from = 2017` — the same value `run_nf1_5.py` builds the served board
with, so the bake-off's folds are the serving path's own.

| fold | `base_seasons` at `base_from=2017` | pool |
|---|---|---|
| 2013 – 2018 | `[]` | **EMPTY — the ordering learner has nothing to fit on** |
| 2019 | `[2017]` | ok |
| 2025 | `[2017 … 2023]` | ok |

A 2018 fold at the registered configuration is **structurally empty**, not merely thin.

## Leg 2 — it has already been RUN at that configuration, and the mechanism is inactive there

NF-INJ2's disclosed wide-window sensitivity ran folds 2013–2025 **at the same `base_from`**
(`run(con, schema, SENSITIVITY_FOLDS, selections, base_from=args.base_from, …)`), so 2018 is on the
record rather than hypothetical. Its draftable-tier learner edge, against 2019's:

| fold | QB | RB | WR | TE | pooled |
|---|---|---|---|---|---|
| **2018** | 0.0622 | **0.000** | **0.000** | **0.000** | 0.0155 |
| 2019 | 0.2713 | 0.2356 | 0.1869 | 0.1131 | 0.2018 |

The mechanism is inactive at three of four positions — which is exactly what leg 1 predicts. An
INACTIVE fold is UNINFORMATIVE, ⛔ never a pass (NF-D20), and NF-INJ2's own record already said so of
that window: *"the ordering mechanism could act on only 10/13 of those folds."*

## Leg 3 — so the 8th fold DILUTES the statistic the +1 fold was meant to help

`stratified`'s registered per-fold lift series and NF-INJ2's recorded 2018 value:

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| *0.0761* | 0.3286 | 0.0696 | 0.4391 | 0.5976 | 0.4959 | 0.4055 | 0.7803 |

| | mean | sd | winner's per-fold Sharpe |
|---|---|---|---|
| 7 registered folds | 0.4452 | 0.2215 | **2.0101** |
| + a 2018 fold | 0.3991 | 0.2431 | **1.6418** |
| | | | **−0.3682** |

⇒ the 8th fold LOWERS the winner's Sharpe, and `SR` is the numerator of the very gate the fold was
prescribed for. **The "+1 fold" is not a power lever here; it is a dilution.**

⚠️ **Precision of leg 3, stated rather than glossed:** the 0.0761 comes from NF-INJ2's run, not
NF-INJ2b's, and the two vintages do not agree to the digit on shared folds (2019: NF-INJ2 0.3120 vs
NF-INJ2b 0.3286). So 1.6418 is INDICATIVE, not the number an 8-fold run would print. The DIRECTION is
robust: 0.0761 against a 0.4452 mean is a 5.9× gap, and no plausible vintage difference closes it.

## The alternative route, and why it is not one

The only way to give 2018 a real pool is to lower `base_from`. That re-bases **every registered
fold** (2019 `[2017]` → `[2016, 2017]`; 2025 seven base seasons → eight), so the result is **eight
different folds, not the seven plus one**: its DSR would not be comparable to 0.9325, NF-INJ2b's
whole evidence base would need re-deriving, and — the point that decides it — the fold window's
authority comes from being **INHERITED from NF1.5's own `score_from = 2019`** precisely so it
"cannot have been tuned to this result". Re-cutting it after a gate missed is what that inheritance
exists to prevent (E2.1-r).

## Consequence, which is the PM's to rule on

**The +1 fold is NOT REACHABLE.** The registration runs at **7 folds**. The remaining candidate 8th
fold is **2026**, available only once the 2026 season is realized — a genuinely CALENDAR-bound
trigger, ⛔ not a design one, and therefore not something this story can buy.

At 7 folds over NF-INJ2b's declared 10-arm field, DSR measured **0.9325 against 0.95**. Ruling 4's
premise — that an 8-fold run would make DSR "a real gate, not a formality" — is measured false in
the direction that matters: there is no 8-fold option, and the 7-fold figure is the one the
registration will face. **This is surfaced BEFORE the decisive run rather than discovered by it.**

⛔ This document takes no decision on it. Which field NF-INJ2c declares is a PRE-REGISTRATION act
belonging to the registration's author, and a field chosen by which one clears is the exact
selection bias DSR exists to deflate (MH2.2). The options and their constraints are put to the PM
in the session handoff; ⛔ no per-candidate-family DSR has been computed, and none will be before the
family is declared (the NF-INJ3b-M rule).
