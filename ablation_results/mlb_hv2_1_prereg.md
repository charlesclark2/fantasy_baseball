# MLB-HV2-1 — Node 2: PRE-REGISTRATION

**Story:** MLB-HV2-1 — Bovada H2H market-bias backtest (model-independent).
**Spec:** `plan_specs/mlb/mlb-hv2-1.yaml`. **Date:** 2026-08-24.
**Code twin:** `betting_ml/scripts/mlb_hv2_1_market_bias.py` — the constants below
are frozen *in that module*, and `test_prereg_document_matches_the_registered_family`
pins this document to it so neither can drift from the other.

> **⛔ COMMITTED BEFORE ANY SCORING.** At the time of this commit no ROI, hit rate,
> arm result, gate value or verdict has been computed. The only thing looked at is
> the COVERAGE audit in `mlb_hv2_1_data_audit.md`, which the Plan graph places
> before this node precisely so the population can be registered against measured
> coverage rather than assumed coverage.
>
> `best_alpha = 0`. Nothing here ships, no bet flag flips. A surviving segment is a
> **CANDIDATE** for an operator-gated forward paper-trade accrual; a classified
> null **CLOSES** the market-bias direction.

---

## 1. Question

Does Bovada's recreational H2H pricing carry a persistent, pre-registrable
**segment bias** — the public overweighting favorites, home teams, or marquee
clubs — that a **flat-stake rule** would have exploited historically?

**No model anywhere in the loop.** E13.8 capped model-side headroom at
~0.002–0.005 Brier; this is the orthogonal question that reframe licensed.

## 2. Population (the explicitly re-registered smaller window)

| | |
|---|---|
| Book / market | `bookmaker_key='bovada'`, `market_key='h2h'`, `sport_key='baseball_mlb'` |
| Games | completed MLB **regular season** (`game_type='R'`, final score present) |
| **First pitch** | scheduled first pitch in **UTC hours 03–23** (i.e. before 00:00 UTC) |
| **Seasons** | **2020, 2021, 2022, 2024, 2025, 2026** — every season whose early-stratum coverage is **≥ 0.50** |
| Excluded | **2023** (early-stratum coverage 0.070) — reported as an unfolded diagnostic |
| Price | the LAST two-sided Bovada H2H quote with `bookmaker_last_update < commence_time` |
| Expected n | **8,828 games** (measured at node 1) |

**Why the restriction, stated in advance.** Node 1 measured that the odds store
covers 0.93–0.96 of games with first pitch before 00:00 UTC and only 0.098–0.119
of games after it — the historical backfill captured **zero** post-00:00-UTC
games in five of six seasons (the INC-22 UTC-date class). Restricting turns the
sample from an unknown-selection mixture into a **near-census (0.897–0.999 per
season) of a cleanly named population**. This is the spec's own instruction —
*"re-register the smaller window explicitly instead"* — executed before scoring.

**The 0.50 season-coverage threshold is not load-bearing:** the partition is
identical for **any** threshold in **[0.08, 0.89]**.

**Price choice.** `ingestion_ts` is the 2026-04-23 backfill time for 2020–2025
and cannot serve as the pre-game bound (it rejects 100 % of the historical era).
`bookmaker_last_update` is the book's own last-moved stamp, is strictly
pre-first-pitch on every historical row, and bounds the price as pre-game — which
is the only property leakage requires. Both sides are read from the **same**
snapshot (E9.52), never max()'d across snapshots.

## 3. The registered arm family — CLOSED, 8 arms

Every arm is a **directional** hypothesis ("bet the side the public does *not*
like") and is therefore a **one-sided** test. Flat **1-unit** stake on every
qualifying game. A pick'em (identical decimal odds) has no favorite and is
excluded from any arm referencing favorite/dog status.

| # | `arm_id` | family | bets on | eligible when |
|---|---|---|---|---|
| 1 | `dog_vs_heavy_fav` | A · favorite–longshot | the **dog** | favorite price ≤ −200 |
| 2 | `dog_vs_mod_fav` | A · favorite–longshot | the **dog** | −200 < favorite price ≤ −140 |
| 3 | `dog_vs_slight_fav` | A · favorite–longshot | the **dog** | −140 < favorite price ≤ −100 |
| 4 | `road_all` | B · home bias | the **road** team | every game |
| 5 | `road_dog` | B · home bias | the **road** team | home is the favorite |
| 6 | `road_fav` | B · home bias | the **road** team | road is the favorite |
| 7 | `fade_marquee` | C · marquee bias | the **non-marquee** side | exactly one side is marquee |
| 8 | `fade_marquee_fav` | C · marquee bias | the **non-marquee** side | exactly one side is marquee **and** it is the favorite |

`declared_field_size = 8` and **`n_trials = 8`** for every deflation gate.
Arms 4 = 5 ∪ 6 and families A/B/C overlap; they are **correlated trials, honestly
counted at full multiplicity** — no arm is dropped for redundancy.

**Marquee list, declared in advance on an EXTERNAL basis** (top US media markets
+ heaviest national-broadcast presence): **ATL, BOS, CHC, LAD, NYM, NYY**. It is
a judgment call and is recorded as one. Node 1 measured that West-Coast clubs
appear disproportionately as **road** teams (LAD 97 home / 234 away), which is
why **no marquee × home/away interaction arm is registered**.

**`day/night` was CONSIDERED and DECLINED**: it carries no directional
public-bias hypothesis, so registering it would spend multiplicity on a fishing
axis rather than a mechanism.

**⛔ Direction rule.** A registered arm whose ROI is significantly **negative** is
recorded as a **finding** and is **never promoted**. Flipping a registered
direction after seeing the sign is the E2.1-r inversion, and re-reading the
mirror after a gate fails is the post-hoc re-read the spec forbids.

## 4. Metric

- **PRIMARY (and the only gated metric): ROI per unit staked** = mean flat-stake
  PnL, where a win pays `decimal_odds − 1` and a loss pays `−1`.
  ⭐ **ROI uses the actual American price and the actual result, so it does not
  depend on the de-vig method at all** — the overround choice cannot manufacture
  the headline.
- **REPORTED, non-gating:** hit rate with a Wilson 95 % CI; the **calibration
  gap** = realized hit rate − mean no-vig implied probability; a **season-block**
  bootstrap 95 % CI on ROI (whole seasons resampled, not bets); per-season ROI.

**No-vig conversion — registered method: proportional / multiplicative.**
`p_i = (1/d_i) / Σ_j (1/d_j)`, applied uniformly. **Shin (1993)** is registered
as a **declared sensitivity for the calibration diagnostic only** and gates
nothing — proportional de-vig is known to under-correct the longshot side, so it
is deliberately kept off the primary.

## 5. Gates — all must pass for an arm to be a CANDIDATE

| gate | rule |
|---|---|
| **G1 ROI** | pooled ROI > 0 |
| **G2 fold consistency** | ROI > 0 in ≥ **5 of 6** season folds (`cv_power.fold_consistency_clause(6, α=0.20)`; attained false-fire 0.109) |
| **G3 BH-FDR** | one-sided p (mean PnL > 0) survives Benjamini–Hochberg at **α = 0.05** across **all 8** registered arms |
| **G4 PBO** | CSCV **PBO < 0.20** over a (season-month × 8-arm) bucket-ROI matrix |
| **G5 DSR** | `deflated_sharpe(per-bet PnL, n_trials=8, trial_sharpes=the 8 arms' per-bet Sharpes) ≥ 0.95` |

**PBO and DSR are registered on DIFFERENT return series** (MH2 / NCAAF-P2.1: one
series silently taxes the other). PBO gets many **season-month** buckets because
CSCV needs partitions; DSR gets the **per-bet** PnL series because it needs
low-noise observations. A bucket in which an arm places no bet scores **0.0** —
the correct return of a flat-stake rule that did not fire, not a missing value.

**`V` (cross-trial dispersion) is measured over the 8 REGISTERED arms only.**
⭐ MH2.1 (a): a diagnostic anchor is never a trial — letting the outcome-seeing
oracle into `V` would have the anchor that polices the metric setting the gate's
own bar.

## 6. Anchors — two-sided, and none of them is a trial

| anchor | must |
|---|---|
| `anchor_oracle_winner` — bets the actual winner | **beat every registered arm.** An arm that beats it is a metric inversion, not a finding (NF-D11 / E2.1-r) |
| `anchor_coin_flip` — seeded pseudo-random side | **lose** (it measures the vig a rule pays for showing up) |
| `anchor_all_home` — bets home every game | **lose** — the exact mirror of `road_all`, scored so the home/road result cannot be read as an artifact of which side was registered |
| `anchor_all_fav` — bets the favorite every game | **lose** — the mirror of family A |

## 7. Harness controls — BOTH directions required (MH2.6 vacuity floor)

A gate family that cannot **fire** returns a null for free; one that cannot
**fail** certifies noise. Both are pre-registered as required:

- **NEGATIVE control** — permute the outcomes, keep every price and segment:
  **no arm may survive**.
- **POSITIVE control** — inject a known 6-percentage-point dog bias:
  **a `dog_vs_*` arm must survive**.

## 8. Model independence (a checkable property)

The study module's **transitive import closure**, measured by importing it in a
**subprocess** and inspecting `sys.modules`, must contain **no** learner library
(`sklearn`, `lightgbm`, `xgboost`, `ngboost`, `torch`, `statsmodels`), **no**
Credence model or serving module (`betting_ml.models`, `pipeline`,
`predict_today`, `write_serving_store`), and **no** model registry. An in-process
check would be vacuous — pytest has already imported half the scientific stack.

## 9. Reproduction

The extracted frame is committed as `betting_ml/tests/fixtures/mlb_hv2_1_input.csv.gz`.
Everything after `extract()` is pure, so the committed artifact is re-derivable
offline and is pinned to **1e-9**.

## 10. Valid outcomes

- **A surviving segment** → recorded as a **CANDIDATE** for a forward
  paper-trade accrual. Nothing ships; no bet flag flips; the operator decides.
- **A classified null** → the **market-bias direction CLOSES** and the epic's
  remaining EV re-ranks. Classified with `cv_power.classify_null`, passing
  `declared_field_size = 8`.

Either way the verdict is stated loudly in the decisive record.
