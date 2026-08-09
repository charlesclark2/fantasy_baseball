# NF-W2 — the availability channel: current-week injury-report state (§0.5 bake-off)

**Generated:** 2026-08-09T02:28:43+00:00 · **gated folds:** 12 half-season blocks (2019H1…2024H2; family ACTIVE on all) · **shadow folds:** 2025H1, 2025H2 (2025 — family structurally unmeasured, never gated) · **modeled rows:** 84553 · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. The incumbent NF-W1 champion (`base_hurdle`) is simultaneously the MATCHED FOIL (NF-D10): each arm is the identical bundle plus the `injury_report` family, so the paired delta IS the attribution.

**PIT gate (per-game as-of instants; injury source records carry `date_modified`):** 532 game-groups / 98611 records (14058 injury) checked; 0 rows in 0 groups dropped fail-closed.

## Per-position verdicts (gated folds)

### QB — **NULL (POWER_LIMITED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.0737 |
| oracle_avail__inj  |      2.0737 |
| inj_both           |      2.4868 |
| inj_zero_leg       |      2.4884 |
| inj_override       |      2.5101 |
| inj_permuted       |      2.5827 |
| base_hurdle        |      2.5924 |
| pos_marginal       |      4.8170 |
| nihilist_zero      |      6.7135 |

- winner `inj_both` vs incumbent `base_hurdle`: mean lift +0.1055 CRPS, fold wins 11/12 (clause requires 8) · PBO 0.0357 · DSR 0.9987 · p 0.0 · FDR pass True
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.1055, 'fold_wins': 11}, 'inj_zero_leg': {'mean': 0.104, 'fold_wins': 11}, 'inj_override': {'mean': 0.0822, 'fold_wins': 12}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_mean': 0.0096, 'permuted_lift_p_one_sided': 0.0327, 'winner_vs_permuted_mean': 0.0959} · coverage(80) {'winner_coverage_80': 0.8172, 'n_rows': 8111, 'binomial_se': 0.0044, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.2763, 'base_hurdle': 3.4029, 'nihilist_zero': 6.7135}

### RB — **NULL (POWER_LIMITED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1855 |
| oracle_avail__base |      2.1888 |
| inj_both           |      2.4813 |
| inj_zero_leg       |      2.4856 |
| inj_override       |      2.5129 |
| inj_permuted       |      2.6131 |
| base_hurdle        |      2.6211 |
| pos_marginal       |      3.8360 |
| nihilist_zero      |      5.5872 |

- winner `inj_both` vs incumbent `base_hurdle`: mean lift +0.1398 CRPS, fold wins 12/12 (clause requires 8) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.1398, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.1355, 'fold_wins': 12}, 'inj_override': {'mean': 0.1082, 'fold_wins': 12}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_mean': 0.008, 'permuted_lift_p_one_sided': 0.0089, 'winner_vs_permuted_mean': 0.1318} · coverage(80) {'winner_coverage_80': 0.8297, 'n_rows': 13102, 'binomial_se': 0.0035, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.3348, 'base_hurdle': 3.5176, 'nihilist_zero': 5.5872}

### WR — **NULL (POWER_LIMITED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1969 |
| oracle_avail__base |      2.1972 |
| inj_both           |      2.6727 |
| inj_zero_leg       |      2.6732 |
| inj_override       |      2.7067 |
| inj_permuted       |      2.8007 |
| base_hurdle        |      2.8041 |
| pos_marginal       |      3.8876 |
| nihilist_zero      |      5.8070 |

- winner `inj_both` vs incumbent `base_hurdle`: mean lift +0.1315 CRPS, fold wins 12/12 (clause requires 8) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.1315, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.1309, 'fold_wins': 12}, 'inj_override': {'mean': 0.0974, 'fold_wins': 12}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_mean': 0.0034, 'permuted_lift_p_one_sided': 0.0361, 'winner_vs_permuted_mean': 0.1281} · coverage(80) {'winner_coverage_80': 0.8351, 'n_rows': 18873, 'binomial_se': 0.0029, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.6139, 'base_hurdle': 3.7895, 'nihilist_zero': 5.807}

### TE — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      1.3629 |
| oracle_avail__inj  |      1.3639 |
| inj_zero_leg       |      1.7964 |
| inj_both           |      1.7968 |
| inj_override       |      1.8119 |
| inj_permuted       |      1.8565 |
| base_hurdle        |      1.8578 |
| pos_marginal       |      2.5840 |
| nihilist_zero      |      3.5336 |

- winner `inj_zero_leg` vs incumbent `base_hurdle`: mean lift +0.0614 CRPS, fold wins 12/12 (clause requires 8) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.0611, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.0614, 'fold_wins': 12}, 'inj_override': {'mean': 0.0459, 'fold_wins': 12}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_mean': 0.0013, 'permuted_lift_p_one_sided': 0.1922, 'winner_vs_permuted_mean': 0.0602} · coverage(80) {'winner_coverage_80': 0.8797, 'n_rows': 11006, 'binomial_se': 0.0038, 'blocking_shortfall': False}
- MAE (report-only): {'inj_zero_leg': 2.4211, 'base_hurdle': 2.4953, 'nihilist_zero': 3.5336}

## Per-fold family activity (the NF-D20 discipline)

| fold   |   n_test |   listed_share |   out_doubtful_share |   observed_share | override                                                          |
|:-------|---------:|---------------:|---------------------:|-----------------:|:------------------------------------------------------------------|
| 2019H1 |     4291 |         0.1906 |               0.0506 |                1 | {'p_emp': 0.999, 'n_train_cell': 953, 'n_test_overridden': 217}   |
| 2019H2 |     3833 |         0.1962 |               0.042  |                1 | {'p_emp': 0.9983, 'n_train_cell': 1168, 'n_test_overridden': 161} |
| 2020H1 |     4367 |         0.1802 |               0.036  |                1 | {'p_emp': 0.9985, 'n_train_cell': 1338, 'n_test_overridden': 157} |
| 2020H2 |     4038 |         0.2117 |               0.0332 |                1 | {'p_emp': 0.998, 'n_train_cell': 1483, 'n_test_overridden': 134}  |
| 2021H1 |     4337 |         0.1729 |               0.0327 |                1 | {'p_emp': 0.9981, 'n_train_cell': 1617, 'n_test_overridden': 142} |
| 2021H2 |     4362 |         0.1992 |               0.0353 |                1 | {'p_emp': 0.9983, 'n_train_cell': 1764, 'n_test_overridden': 154} |
| 2022H1 |     4387 |         0.1798 |               0.0429 |                1 | {'p_emp': 0.9984, 'n_train_cell': 1928, 'n_test_overridden': 188} |
| 2022H2 |     4299 |         0.1849 |               0.0354 |                1 | {'p_emp': 0.9986, 'n_train_cell': 2099, 'n_test_overridden': 152} |
| 2023H1 |     4264 |         0.1524 |               0.0237 |                1 | {'p_emp': 0.9987, 'n_train_cell': 2264, 'n_test_overridden': 101} |
| 2023H2 |     4337 |         0.2156 |               0.0399 |                1 | {'p_emp': 0.9987, 'n_train_cell': 2367, 'n_test_overridden': 173} |
| 2024H1 |     4365 |         0.1805 |               0.0323 |                1 | {'p_emp': 0.9984, 'n_train_cell': 2526, 'n_test_overridden': 141} |
| 2024H2 |     4212 |         0.194  |               0.0332 |                1 | {'p_emp': 0.9985, 'n_train_cell': 2676, 'n_test_overridden': 140} |

## Shadow 2025 (mechanism cannot act — registered expectation: near-tie)

```json
{
  "QB": {
    "inj_both": {
      "mean_delta_vs_base": -0.0306,
      "max_abs_delta": 0.0392
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0318,
      "max_abs_delta": 0.0381
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "RB": {
    "inj_both": {
      "mean_delta_vs_base": -0.0227,
      "max_abs_delta": 0.0319
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0265,
      "max_abs_delta": 0.0376
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "WR": {
    "inj_both": {
      "mean_delta_vs_base": -0.0329,
      "max_abs_delta": 0.0579
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0369,
      "max_abs_delta": 0.0638
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "TE": {
    "inj_both": {
      "mean_delta_vs_base": -0.0113,
      "max_abs_delta": 0.0148
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0079,
      "max_abs_delta": 0.0137
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "activity": [
    {
      "fold": "2025H1",
      "n_test": 4308,
      "listed_share": null,
      "out_doubtful_share": 0.0,
      "observed_share": 0.0
    },
    {
      "fold": "2025H2",
      "n_test": 4380,
      "listed_share": null,
      "out_doubtful_share": 0.0,
      "observed_share": 0.0
    }
  ]
}
```

## Gate detail

```json
{
  "QB": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": false,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": false
  },
  "RB": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": false,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": false
  },
  "WR": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": false,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": false
  },
  "TE": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": true,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": true
  }
}
```

## Null-state classification (failing positions)

```json
{
  "QB": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w2_injury_crps_QB`: insufficient recorded statistics to certify the null as powered. Absent a detectability figure the honest default is POWER-LIMITED \u2014 a null is trustworthy only when something was computed to make it so.",
    "retest_trigger": null
  },
  "RB": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w2_injury_crps_RB`: insufficient recorded statistics to certify the null as powered. Absent a detectability figure the honest default is POWER-LIMITED \u2014 a null is trustworthy only when something was computed to make it so.",
    "retest_trigger": null
  },
  "WR": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w2_injury_crps_WR`: insufficient recorded statistics to certify the null as powered. Absent a detectability figure the honest default is POWER-LIMITED \u2014 a null is trustworthy only when something was computed to make it so.",
    "retest_trigger": null
  }
}
```

## Reading the result (hand-written; the JSON above is the machine record)

**Verdict: TE SHIPS (`inj_zero_leg`); QB/RB/WR are a recorded null that rests ENTIRELY on one
anchor clause — and the machine classification of that null is WRONG and corrected here.**

### 1. The hypothesis is confirmed as measurement, everywhere

Every statistical gate passed at ALL FOUR positions: winner lift vs the NF-W1 incumbent
**QB +0.1055 (4.1%) · RB +0.1398 (5.5%) · WR +0.1315 (4.8%) · TE +0.0614 (3.4%) CRPS/week**,
fold wins 11–12 of 12 (clause requires 8), PBO ≤ 0.036, DSR ≥ 0.9987, p ≈ 0, joint BH-FDR pass,
coverage floors clear (0.817–0.880), every degenerate loses, and no arm beats its own-form
peeking availability oracle. The PIT gate consumed 14,058 injury source records across 532
per-game groups with **zero** drops. The mechanism read is confirmed too: the zero-leg-only arm
(`inj_zero_leg`) is within 0.0004–0.0043 CRPS of the both-legs arm everywhere and WINS outright
at TE — the lift lives in the availability leg, as registered (NF-W4's thesis in lean form).

### 2. Why QB/RB/WR did not ship: the amended permutation clause fired

The single failing check is `permuted_lift_not_significant`: the permuted arm (injury values
shuffled within position×week — player linkage destroyed, week×position marginal rates
preserved) shows a SMALL but statistically significant lift over base at QB (+0.0096,
p=0.033), RB (+0.0080, p=0.0089), WR (+0.0034, p=0.036); TE (+0.0013, p=0.19) passes. Reading:
the family carries a real **week×position marginal-rate channel** (league-wide listing/Out
rates vary by week) on top of its player-level content. Per the pre-run amendment, a
significant permuted lift means winner−base mis-attributes that share, and the gate refuses.

### 3. The NF-D20 decomposition (a failed anchor is decomposed, never re-labelled)

The content attribution the clause demands — **winner − permuted** — is
**QB +0.0959 · RB +0.1318 · WR +0.1281 · TE +0.0602**: 91–97% of the total lift is
player-level content; the marginal-rate channel is 3–9%. ⭐ And the marginal channel is NOT
leakage — week-level listing rates are PIT-clean, legitimately knowable information. The
clause vetoes mis-ATTRIBUTION, not illegitimacy: the registration promised "the win is the
family's player-level content," and at QB/RB/WR that claim is 91–97% true rather than
entirely true, so the registered gate refuses. The honest headline is "the effect is real and
overwhelmingly player-level; the registration's attribution bar was stricter than the effect's
composition," not "no effect."

### 4. ⚠️ CLASSIFICATION CORRECTION: this null is NOT `POWER_LIMITED`

`classify_null`'s generic fallback labeled QB/RB/WR `POWER_LIMITED` ("insufficient recorded
statistics"). That is the NF-D18 instrument gap in a new costume: the taxonomy has no state
for an ANCHOR/REGISTRATION-CHOICE refusal, so it defaults to a power reading — and a power
reading is actively misleading here. Nothing is underpowered: p ≈ 0 on every primary test, and
MORE folds would make the permuted arm's lift MORE significant, i.e. the clause fails HARDER
with more data. The correct classification is the **`CONSTRAINT_REFUSED` family** (NF-D18):
the null rests on a registration choice, the remedy is a different registration/mechanism —
never more data — and no re-test trigger keyed on sample size should be published for it.

### 5. What the pre-run amendment did (recorded because it decided the verdict)

Under the ORIGINAL strict binary clause ("permuted must not beat base on the raw mean"), TE
would ALSO have failed — permuted edged base by +0.0013 there, a pure coin-flip tie. The
calibrated clause rescued the one legitimate ship from the ~50% false-veto while correctly
flagging the real marginal channel at the other three. Both the strictness and the rescue are
exactly what the amendment was registered to do.

### 6. Shadow 2025: no phantom lift, and the price of a dark feed is measured

With the family structurally unmeasured (all-NaN + observed=0), no arm shows phantom lift —
instead the learned arms pay a small consistent tax vs base (−0.008…−0.037 CRPS/week; trees
split on features that are dark at serve time), while `inj_override` sits at EXACTLY 0.0
(the surgical arm is byte-identical to base when no admissible statuses exist — a wiring
proof). ⇒ **Serving consequence: the family must be ARMED by a live, stamped injury capture
(NF-W0a) before its features serve in 2026; with a dark feed, serve the base champion.**

### 7. Successor registration carded (a null that names where the answer lives)

**NF-W2b:** absorb the marginal channel into the incumbent — add pre-registered week×position
LISTING-RATE features (group rates, no player linkage) to the BASE, then register the injury
family against THAT foil. The matched pair then isolates pure player-level content, and the
permutation clause as amended is satisfiable by construction. Also carded: extending the TE
ship to QB/RB/WR via that registration, and a `classify_null` state for anchor-refusals (the
NF-D18 8th-state gap, now hit twice).

### 8. What SHIP means operationally

Nothing auto-deploys (`best_alpha = 0`, deploy-held). The deliverable is the validated spec:
**TE champion = `lgbm_hurdle` with the injury family in the P(zero) leg** (`inj_zero_leg`;
conditional leg unchanged from NF-W1). Registry/serving staging goes through the NF-G0
governance CLI as an operator step, gated on the NF-W0a capture arming the family in-season.
