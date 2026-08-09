# NF-W2b — the injury family re-registered against a marginal-rate-carrying foil (§0.5 bake-off)

**Generated:** 2026-08-09T04:12:47+00:00 · **gated folds:** 12 half-season blocks (2019H1…2024H2; family ACTIVE on all) · **shadow folds:** 2025H1, 2025H2 (2025 — both families structurally unmeasured, never gated) · **modeled rows:** 84553 · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. The matched foil is `base_rate` (NF-W1 champion + pre-registered week×position listing-rate features): each arm is the identical bundle plus the PLAYER-level `injury_report` family, so the paired delta vs `base_rate` IS the pure player-level attribution (NF-D10). `base_noRate` (the production incumbent) anchors the deployment bar.

**PIT gate (per-game as-of instants; window + injury + rate records):** 532 game-groups / 173813 records (14058 injury, 75202 rate) checked; 0 rows in 0 groups dropped fail-closed.

## Per-position verdicts (gated folds)

### QB — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.0659 |
| oracle_avail__inj  |      2.0683 |
| inj_zero_leg       |      2.4756 |
| inj_both           |      2.4768 |
| inj_override       |      2.4925 |
| base_rate          |      2.5736 |
| inj_permuted       |      2.5807 |
| base_noRate        |      2.5924 |
| pos_marginal       |      4.8170 |
| nihilist_zero      |      6.7135 |

- winner `inj_zero_leg` vs rate foil `base_rate`: mean lift +0.0980 CRPS, fold wins 11/12 (clause requires 8) · PBO 0.1396 · DSR 0.9931 · p 0.0001 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.0968, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.098, 'fold_wins': 11}, 'inj_override': {'mean': 0.0811, 'fold_wins': 12}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1167, 'winner_vs_production_fold_wins': 11, 'marginal_channel_mean': 0.0188, 'marginal_channel_p_one_sided': 0.0035, 'player_content_mean': 0.098}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0071, 'permuted_lift_p_one_sided': 0.8981, 'winner_vs_permuted_mean': 0.105} · coverage(80) {'winner_coverage_80': 0.8205, 'n_rows': 8111, 'binomial_se': 0.0044, 'blocking_shortfall': False}
- MAE (report-only): {'inj_zero_leg': 3.2676, 'base_rate': 3.3825, 'base_noRate': 3.4029, 'nihilist_zero': 6.7135}

### RB — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1868 |
| oracle_avail__base |      2.1875 |
| inj_both           |      2.4784 |
| inj_zero_leg       |      2.4789 |
| inj_override       |      2.5058 |
| base_rate          |      2.6132 |
| inj_permuted       |      2.6175 |
| base_noRate        |      2.6211 |
| pos_marginal       |      3.8360 |
| nihilist_zero      |      5.5872 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1347 CRPS, fold wins 12/12 (clause requires 8) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1347, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.1343, 'fold_wins': 12}, 'inj_override': {'mean': 0.1074, 'fold_wins': 12}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1427, 'winner_vs_production_fold_wins': 12, 'marginal_channel_mean': 0.0079, 'marginal_channel_p_one_sided': 0.0055, 'player_content_mean': 0.1347}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0044, 'permuted_lift_p_one_sided': 0.9127, 'winner_vs_permuted_mean': 0.1391} · coverage(80) {'winner_coverage_80': 0.8358, 'n_rows': 13102, 'binomial_se': 0.0035, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.3315, 'base_rate': 3.505, 'base_noRate': 3.5176, 'nihilist_zero': 5.5872}

### WR — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.1966 |
| oracle_avail__inj  |      2.1967 |
| inj_both           |      2.6735 |
| inj_zero_leg       |      2.6738 |
| inj_override       |      2.7055 |
| base_rate          |      2.7993 |
| inj_permuted       |      2.8022 |
| base_noRate        |      2.8041 |
| pos_marginal       |      3.8876 |
| nihilist_zero      |      5.8070 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1257 CRPS, fold wins 12/12 (clause requires 8) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1257, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.1255, 'fold_wins': 12}, 'inj_override': {'mean': 0.0938, 'fold_wins': 12}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1306, 'winner_vs_production_fold_wins': 12, 'marginal_channel_mean': 0.0048, 'marginal_channel_p_one_sided': 0.0345, 'player_content_mean': 0.1257}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0029, 'permuted_lift_p_one_sided': 0.9526, 'winner_vs_permuted_mean': 0.1287} · coverage(80) {'winner_coverage_80': 0.8368, 'n_rows': 18873, 'binomial_se': 0.0029, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.6215, 'base_rate': 3.7798, 'base_noRate': 3.7895, 'nihilist_zero': 5.807}

### TE — **SHIP — consistency check; the NF-W2 TE ship stands regardless**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      1.3621 |
| oracle_avail__inj  |      1.3645 |
| inj_zero_leg       |      1.7972 |
| inj_both           |      1.7987 |
| inj_override       |      1.8104 |
| base_rate          |      1.8561 |
| base_noRate        |      1.8578 |
| inj_permuted       |      1.8592 |
| pos_marginal       |      2.5840 |
| nihilist_zero      |      3.5336 |

- winner `inj_zero_leg` vs rate foil `base_rate`: mean lift +0.0588 CRPS, fold wins 12/12 (clause requires 8) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.0573, 'fold_wins': 12}, 'inj_zero_leg': {'mean': 0.0589, 'fold_wins': 12}, 'inj_override': {'mean': 0.0457, 'fold_wins': 12}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.0606, 'winner_vs_production_fold_wins': 12, 'marginal_channel_mean': 0.0017, 'marginal_channel_p_one_sided': 0.1881, 'player_content_mean': 0.0589}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0031, 'permuted_lift_p_one_sided': 0.8999, 'winner_vs_permuted_mean': 0.062} · coverage(80) {'winner_coverage_80': 0.8811, 'n_rows': 11006, 'binomial_se': 0.0038, 'blocking_shortfall': False}
- MAE (report-only): {'inj_zero_leg': 2.4192, 'base_rate': 2.497, 'base_noRate': 2.4953, 'nihilist_zero': 3.5336}

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
      "vs": "base_rate",
      "mean_delta": -0.0082,
      "max_abs_delta": 0.0277
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0155,
      "max_abs_delta": 0.0298
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0081,
      "max_abs_delta": 0.0145
    }
  },
  "RB": {
    "inj_both": {
      "vs": "base_rate",
      "mean_delta": -0.0187,
      "max_abs_delta": 0.0337
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0197,
      "max_abs_delta": 0.0325
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0167,
      "max_abs_delta": 0.0179
    }
  },
  "WR": {
    "inj_both": {
      "vs": "base_rate",
      "mean_delta": -0.0324,
      "max_abs_delta": 0.0589
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0307,
      "max_abs_delta": 0.06
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0225,
      "max_abs_delta": 0.0369
    }
  },
  "TE": {
    "inj_both": {
      "vs": "base_rate",
      "mean_delta": -0.0144,
      "max_abs_delta": 0.0162
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0112,
      "max_abs_delta": 0.0139
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0019,
      "max_abs_delta": 0.0054
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
      "beats_production": true,
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
  },
  "RB": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
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
  },
  "WR": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
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
  },
  "TE": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
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
{}
```

## Reading the result (hand-written; the JSON above is the machine record)

**Verdict: SHIP at ALL FOUR positions — the NF-W2 §7 successor registration did exactly what
it was carded to do.** QB/RB/WR, refused at NF-W2 on the attribution clause alone, clear every
gate against the STRONGER rate-carrying foil; TE's NF-W2 ship is corroborated and a unified
rate-augmented TE spec is now available.

### 1. The registered fix worked, and the mechanism proof is two-sided

The single clause that refused QB/RB/WR at NF-W2 — `permuted_lift_not_significant` — now
passes everywhere, and not marginally: the permuted arm's lift over `base_rate` is
**NEGATIVE** at all four positions (QB −0.0071 p=0.898 · RB −0.0044 p=0.913 · WR −0.0029
p=0.953 · TE −0.0031 p=0.900). With the week×position marginal rates IN the foil, the permuted
player columns are pure noise — the channel was fully absorbed, exactly as registered. The
matched pair therefore isolates pure player-level content, and it is large: **QB +0.0980
(11/12 folds) · RB +0.1347 (12/12) · WR +0.1257 (12/12) · TE +0.0589 (12/12) CRPS/week vs the
rate foil** — reproducing NF-W2's winner−permuted attribution estimates (0.0959 / 0.1318 /
0.1281 / 0.0602) through an entirely different construction, which is the strongest kind of
corroboration this harness can produce.

### 2. The three-way decomposition (winner − production = marginal channel + player content)

| pos | winner − base_noRate | = marginal channel (base_noRate − base_rate) | + player content (winner − base_rate) |
|---|---|---|---|
| QB | +0.1167 | +0.0188 (p=0.0035) | +0.0980 |
| RB | +0.1427 | +0.0079 (p=0.0055) | +0.1347 |
| WR | +0.1306 | +0.0048 (p=0.0345) | +0.1257 |
| TE | +0.0606 | +0.0017 (p=0.188, ~0) | +0.0589 |

The marginal channel priced DIRECTLY (a fitted foil, not a permutation residue) is
significant at QB/RB/WR and ~zero at TE — matching NF-W2's 3–9%/91–97% split and explaining
why TE alone passed the original clause. The rate features are not deadweight in the shipped
bundle: they carry a real (small) lift of their own.

### 3. Winner identity is a genuine tie at QB/RB/WR — nothing turns on the arm choice

`inj_zero_leg` vs `inj_both` differ by 0.01–0.05% of CRPS with split flip mass (QB 61/32 ·
RB 59/41 · WR 58/42 — the NF1.8 flip reading: mass on two arms a fraction of a percent apart
IS a tie); TE is decisive for `inj_zero_leg` (98.7%). The scored winners (QB `inj_zero_leg`,
RB/WR `inj_both`, TE `inj_zero_leg`) are what the gates certify and what ships
(serve-what-was-validated, MH2.1 (b)); a UNIFORM `inj_zero_leg` spec across all four would be
defensible on these numbers as an NF-G0 simplification, but that is an operator decision, not
this story's. QB's PBO 0.1396 (the one non-zero, still under the 0.20 gate) is exactly this
tie showing up in the rank statistic — os-gap 0.097% says picking the in-sample winner costs
~a tenth of a percent; the contender spread (3.96%) is arm-vs-override structure, not
instability.

### 4. Shadow 2025: the dark-feed price now covers BOTH families

No phantom lift anywhere. With stamps deleted upstream, the learned arms pay −0.008…−0.032
CRPS vs `base_rate`, `base_rate` itself pays −0.002…−0.023 vs `base_noRate` (the rate
features' own dark tax), and `inj_override` sits at EXACTLY 0.0 (byte-identical wiring
proof). ⇒ the serving consequence is unchanged and now covers the rate family too: **the
shipped specs require a live, stamped injury feed (NF-W0a forward-capture); with a dark feed,
serve the base champion.**

### 5. What SHIP means operationally

Nothing auto-deploys (`best_alpha = 0`, deploy-held). The deliverable is the validated spec
per position — the NF-W1 hurdle over `WP.FEATURES + injury_rate + injury_report` with the
winning arm's form (`PRE_FLIP_SPEC`/`POST_FLIP_SPEC` in `weekly_projection_w2b.py`, pinned to
this artifact by guard test). Staging goes through the NF-G0 governance CLI as an operator
step, gated on the NF-W0a capture arming both families in-season. ⭐ **Flip-tracking
requirement (operator, 2026-08-08): before any flip, capture per-player projections from the
pre-flip AND post-flip specs on the same slate** — `run_nf_w2b_projection_snapshot.py` scores
both spec sets side by side and writes the comparison artifact; run it on the flip week (and
it is runnable today on 2024 held-out weeks as the historical reference).
