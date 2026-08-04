# NF1.6 — BASE 2026 K + DST season projections (position-universe extension)

**Model:** `nfl_fantasy_kdst_base_v1` · **base season:** 2025 → **projects:** 2026 · **generated:** 2026-08-04T04:49:04.857112+00:00

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the betting posture). The gate is FACE-VALIDITY + COVERAGE + honest uncertainty.

> 🚨 **READ THIS BEFORE READING A RANK.** K and DST are the LEAST PREDICTABLE fantasy positions, and this is a **BASE** model by design. The value it delivers is **COMPLETENESS** (the K/DST roster slots now fill instead of rendering "not projected") and **relative TIERING** (better vs worse situations) — **not precision**. Treat the output as streaming-tier guidance. The intervals are deliberately WIDE and they are the honest part of the product; a rank ordering inside a tier is noise.

## 1. Why the model looks the way it does — every shrink is a MEASURED reliability

Lag-1 autocorrelation of the PER-GAME rate, re-measured from this run's own training panel (640 team-season rows, targets 2006–2025):

| component         |   n |   lag1_r | declared_noise   |
|:------------------|----:|---------:|:-----------------|
| def_sacks         | 640 |    0.270 | False            |
| def_int           | 640 |    0.268 | False            |
| def_fumble_rec    | 640 |    0.230 | False            |
| def_td            | 640 |    0.130 | True             |
| st_td             | 640 |    0.230 | False            |
| def_safety        | 640 |    0.011 | True             |
| def_blocked_kick  | 640 |    0.061 | True             |
| def_forced_fumble | 640 |    0.262 | False            |

Three findings drive the whole design:

1. **DST carries MODEST signal, and only in the volume takeaways.** The retained components (sacks / INT / fumble-recoveries / ST TDs) persist at ρ = 0.230–0.270, and points-allowed/game at ρ ≈ 0.32. The three DECLARED-NOISE components (defensive TDs, safeties, blocked kicks) sit at ρ = 0.011–0.130 — low enough that projecting a team's 5 defensive TDs forward would manufacture precision that does not exist — so they are projected at the **league mean** and said to be. This is exactly why the product's claim is TIERS. ⚠️ Note these reliabilities are measured against the model's OWN 3-season recency-weighted prior, which is a better predictor than a bare one-season lag; the single-season-lag figures are lower still (sacks 0.252, INT 0.259, fumble-rec 0.223, ST TD 0.166, def TD 0.094, blocked 0.019, safety −0.018).
2. **A kicker's ACCURACY is near-random year-to-year (ρ = 0.085) but his TEAM'S SCORING ENVIRONMENT is partly forecastable.**

   ⚠️ **THE CONTEMPORANEOUS RELATIONSHIP AND THE FORECASTABLE ONE ARE WILDLY DIFFERENT, AND ONLY THE SECOND IS A MODEL INPUT.** Measured on realized seasons, PAT attempts/game correlate **0.948** with points/game (slope 0.132) — PAT volume essentially *is* offensive touchdowns, an almost mechanical identity. But the projection cannot see the realized season; it sees the FORWARD points estimate (week-1 Vegas implied points blended with a regressed prior), and against that the correlation is only **0.377** (fitted slope 0.115). Quoting the 0.948 as though it were the model's accuracy would be a train/serve inconsistency dressed up as a finding — the near-identity is real, but our ability to know next season's offense is what actually bounds the projection, and that is far weaker.

   FG attempts are weaker again: **0.033** against the forward estimate (0.19 contemporaneously) and **NON-MONOTONE** — the fitted quadratic (+0.00026·x² -0.0053·x +1.916) turns DOWN past ≈25 points/game, because elite offenses score touchdowns instead of kicking field goals (measured: FG att/g by team-scoring quintile runs 1.769 → 1.889 → 1.969 → 1.977 → **1.955**). So FG-attempt volume is close to a constant ~1.94/game for everybody, and a kicker's ranking is driven by PAT volume (his offense) plus distance mix (his leg).
3. **Leg strength IS real.** The share of a kicker's attempts from ≥50 yards persists at ρ = 0.429 — by far the strongest kicker-side signal, and 5× the reliability of his make rate — so the distance MIX is genuinely per-kicker (shrunk with a 60-attempt prior) while the make rate WITHIN a bucket is not (shrunk with a 200-attempt prior ≈ two and a half full seasons, i.e. a kicker's own record barely moves the projection). That matters because distance-bucketed FG scoring (3/4/5) pays for leg strength.

## 2. What it emits — RAW components, so any league's scoring can score it

Mirrors MVP-1's raw-line philosophy. `proj_fp_std` is a **CONVENIENCE** total for ranking/validation only; NF-C1 rescores the raw components per league.

```
DST  proj_def_sacks · proj_def_int · proj_def_fumble_rec · proj_def_td · proj_st_td ·
     proj_def_safety · proj_def_blocked_kick · proj_dst_points_allowed ·
     proj_dst_pa_per_game(_sd) · proj_dst_pa_g_{0,1_6,7_13,14_17,18_20,21_27,28_34,35_45,46p}
K    proj_fg_att · proj_fg_made · proj_fg_made_0_39/_40_49/_50_plus · proj_fg_missed ·
     proj_pat_att · proj_pat_made
```

⭐ **WHY THE POINTS-ALLOWED DISTRIBUTION IS EMITTED AS EXPECTED-GAMES-PER-BUCKET, and why that un-blocks NF-C0b without NF1.6 depending on it.** DST points-allowed scoring is a per-game TIER table, which is **not linear in season points allowed** — so a season total cannot be scored under it. But `Σ_bucket tier_points × E[games in bucket]` **is** linear in the emitted columns, so the existing sport-agnostic linear scorer expresses ANY tier scheme exactly, with **no engine change**. The nine bucket edges are the common REFINEMENT of the ESPN (0/1-6/7-13/14-17/18-27/28-34/35-45/46+) and Yahoo (0/1-6/7-13/14-20/21-27/28-34/35+) schemes, so both are exact unions of them; a scheme with other edges re-integrates from `proj_dst_pa_per_game` + `_sd`, and is told so rather than silently mis-scored.

⭐ **WHY THE DISTRIBUTION IS EMPIRICAL, NOT PARAMETRIC.** A shutout is the most valuable game outcome under every tier scheme, and P(0 PA) = **0.0099** in the data. A negative binomial matched to the observed mean/variance of team points allowed puts **~1e-4** there — it misses the single most valuable atom by two orders of magnitude, because NFL scores are lumpy multiples of 3 and 7 rather than a smooth count. So the bucket mix is read off the EMPIRICAL conditional distribution of per-game points allowed given the team's projected rate (13934 team-games, quantile-binned with linear interpolation), which reproduces the atom by construction — and reproduces the observed monotonicity (best-quintile defenses are shut-out-capable ~2.4% of games, worst-quintile ~0.0%).

## 3. Coverage — the honest number, measured on the RIGHT population

⚠️ **The panel is the PRESEASON universe LEFT-JOINED to realized outcomes with a 0 fill, never an inner join behind a games filter.** A kicker who made a week-1 roster and was then cut realises exactly 0 fantasy points, and that is **0.1979** of the held-out kicker population. Deleting it is precisely how the veteran band shipped five stories covering 0.55 of its nominal 0.80 (NF1.9). Coverage below is a **FLOOR** (≥ nominal 0.80), never a target to tune toward — both these targets are heavily skewed with a point mass at 0, which is the exact shape that makes a coverage TARGET structurally inverted (NF1.9 (e)).

| position   |   n (held-out) |   coverage |   floor |   mean width |   interval score | verdict   |
|:-----------|---------------:|-----------:|--------:|-------------:|-----------------:|:----------|
| DST        |            320 |      0.897 |   0.800 |       85.300 |           97.110 | ✅ met    |
| K          |            475 |      0.830 |   0.800 |      106.600 |          151.430 | ✅ met    |

Pooled over rows: coverage **0.8566** (nominal 0.8), below-p10 0.083, above-p90 0.0604, mean width 98.02, interval score 129.562. Held-out seasons 2016–2025, walk-forward (the band never sees its own evaluation season).

Per BAND GROUP — the one split that materially matters (a locked-in starting kicker and a camp body have completely different outcome distributions; mean games share 0.923 vs 0.140):

| band group   |   n |   coverage |   mean width |
|:-------------|----:|-----------:|-------------:|
| DST          | 320 |      0.897 |       85.300 |
| K_reserve    | 193 |      0.850 |      112.700 |
| K_starter    | 282 |      0.816 |      102.400 |

### ⭐ The parameter-uncertainty widening — what it fixed, and what it cost

The first cut of this band used the POOLED ROW quantile of `realized / projected` per group. It **breached both floors** — and the diagnosis is structural, not a tuning problem: the quantile itself MOVES SEASON TO SEASON. Measured on the panel, the K-starter ratio q10 ranges from **0.31 to 0.94** across the 15 held-out seasons, while the pooled row quantile is a single 0.63. Rows inside a season share that season's regime and are **not independent draws** — the same class-clustering NF1.8 makes explicit for per-position floors. A band that quotes the pooled quantile is therefore implicitly claiming to know next season's quantile exactly, and it under-covers by precisely that unmodelled spread.

So each bound is shifted OUTWARD by `z ×` the ACROSS-SEASON SD of that bound, with **z = 1.0 fixed in advance** (`BAND_CLUSTER_Z`) — the same parameter-uncertainty widening NF1.4/NF1.7 apply to rookie intervals for P1A's `sd`. The shift is outward-only, so it can never sharpen a bound (the NF1.7 (d) widen-only invariant).

| band                                                         |   coverage |   cov K |   cov DST |   mean width |   interval score |
|:-------------------------------------------------------------|-----------:|--------:|----------:|-------------:|-----------------:|
| pooled row quantile (z = 0) — INELIGIBLE, breaches the floor |      0.756 |   0.731 |     0.794 |       72.210 |          128.589 |
| + parameter-uncertainty widening (z = 1.0) — SHIPPED         |      0.857 |   0.830 |     0.897 |       98.020 |          129.562 |

⚖️ **The widening is NOT a free lunch and is not presented as one: it cost +0.76% of interval score.** That is the correct trade to make here — the coverage floor is a hard CONSTRAINT and the pooled-quantile band is ineligible under it, so the interval score only ranks arms that already satisfy the floor (NF1.8). Reporting the cost is what keeps that a stated trade rather than a hidden one.

⚠️ **DST over-covers (0.8969 against a 0.80 floor) and is DELIBERATELY NOT sharpened toward nominal.** Coverage is a FLOOR, never a target to minimise distance to (E2.1-r), and every notch of tightening moves the band toward the `max_width` degenerate's side of the trade rather than away from it (NF1.8). There is also a structural reason to expect coverage above nominal on these two populations: both targets have a point mass at 0 with a bound floored at 0, so the left tail is close to un-missable — the same zero-atom geometry that made a 0.80 coverage TARGET structurally inverted on the veteran board (NF1.9 (e)). 0.1979 of the held-out kicker rows realise exactly 0.

### The two-sided degenerate anchors

There is no candidate field here to overfit — the band is **reported, not selected** — but a band that a degenerate beats on a proper score is a band nobody should ship. `zero_width` is maximally SHARP (pays the full miss penalty); `max_width` is maximally WIDE (satisfies ANY coverage floor and pays its own width). **Both must lose** the interval score, and the `max_width` line is the standing proof that the coverage figure is a CONSTRAINT rather than a criterion (NF1.8): a degenerate satisfies it, and the interval score then eliminates the degenerate.

| arm                            |   interval score |   coverage |   mean width |
|:-------------------------------|-----------------:|-----------:|-------------:|
| SHIPPED base band              |          129.562 |      0.857 |       98.020 |
| zero_width (degenerate, sharp) |          274.064 |      0.000 |        0.000 |
| max_width (degenerate, wide)   |          202.000 |      1.000 |      202.000 |

**Beats both degenerates: ✅ yes**

### The shipped band

```json
{
  "quantiles": [
    0.1,
    0.9
  ],
  "widen": 1.0,
  "cluster_z": 1.0,
  "groups": {
    "DST": [
      0.5515,
      1.3488
    ],
    "K_reserve": [
      -0.1619,
      3.1456
    ],
    "K_starter": [
      0.4243,
      1.3354
    ]
  },
  "raw_groups_before_cluster_widen": {
    "DST": [
      0.636,
      1.259
    ],
    "K_reserve": [
      0.0,
      2.2718
    ],
    "K_starter": [
      0.6281,
      1.2727
    ]
  },
  "across_season_sd_of_the_quantile": {
    "DST": {
      "sd_lo": 0.0844,
      "sd_hi": 0.0897,
      "n_seasons": 15
    },
    "K_reserve": {
      "sd_lo": 0.1619,
      "sd_hi": 0.8738,
      "n_seasons": 12
    },
    "K_starter": {
      "sd_lo": 0.2038,
      "sd_hi": 0.0628,
      "n_seasons": 15
    }
  },
  "pooled": {
    "DST": [
      0.5515,
      1.3488
    ],
    "K": [
      -0.3675,
      1.7014
    ]
  },
  "n_by_group": {
    "DST": 480,
    "K_reserve": 219,
    "K_starter": 422
  },
  "fell_back": []
}
```

The band is empirical quantiles of `realized / projected` per band group — a MULTIPLICATIVE shape, because both targets floor at exactly 0 with a long right tail, so an additive symmetric band would push the lower bound below the floor and understate the upside. **p10 and p90 are emitted INDEPENDENTLY** and carried through the league rescore via `SportProfile.base_p10_column/base_p90_column` — never reconstructed from a single `sd`, which would re-symmetrise a skewed band and slide it off its own point (the exact bug NF1.7 fixed for rookies). `apply_band` enforces `lo ≤ point ≤ hi`.

## 4. Held-out rank signal — modest, and that IS the finding

| position        |   n |   spearman |   pearson |    mae |   top8_hit_rate |   n_seasons | note                                                                   |
|:----------------|----:|-----------:|----------:|-------:|----------------:|------------:|:-----------------------------------------------------------------------|
| DST             | 480 |      0.322 |     0.321 | 22.100 |           0.400 |          15 | nan                                                                    |
| K               | 641 |      0.651 |     0.758 | 28.600 |           0.358 |          15 | nan                                                                    |
| K_starters_only | 422 |      0.231 |     0.145 | 25.400 |           0.375 |          15 | the HONEST kicker read — pooled K is inflated by job status, not skill |

These numbers are **not** a gate. A projection product whose stated value is completeness + tiering does not get withheld because the ceiling on K/DST predictability is low; the honest response is to report the ceiling, keep the intervals wide, and label the surface as streaming-tier guidance. A DST rank correlation in this range means the model separates **good situations from bad ones** and does not pretend to separate DST3 from DST7.

## 5. Face validity — the edge-independent gate

**Verdict: ✅ PASS**

| check                                 | pass   |   spearman | requires   | note                                                         |   violations |   max_abs_gap |
|:--------------------------------------|:-------|-----------:|:-----------|:-------------------------------------------------------------|-------------:|--------------:|
| dst_points_ranks_track_points_allowed | True   |     -0.864 | <= -0.3    | a top-ranked DST must be projected to ALLOW FEWER points     |      nan     |       nan     |
| k_points_track_team_scoring_env       | True   |      0.963 | >= 0.3     | a top-ranked starting K must sit on a higher-scoring offense |      nan     |       nan     |
| interval_contains_its_point           | True   |    nan     | nan        | nan                                                          |        0.000 |       nan     |
| pa_bucket_mass_sums_to_games          | True   |    nan     | nan        | nan                                                          |      nan     |         0.000 |

## 6. The 2026 board (top of each position)

### DST

| player_name   | team_id   |   proj_games |   proj_fp_std |   fp_p10 |   fp_p90 |   proj_dst_pa_per_game |   proj_def_sacks |   proj_def_int |
|:--------------|:----------|-------------:|--------------:|---------:|---------:|-----------------------:|-----------------:|---------------:|
| DEN D/ST      | DEN       |       17.000 |       119.814 |   66.079 |  161.600 |                 20.750 |           47.814 |         13.494 |
| HOU D/ST      | HOU       |       17.000 |       118.063 |   65.113 |  159.238 |                 21.319 |           42.239 |         15.879 |
| SEA D/ST      | SEA       |       17.000 |       117.469 |   64.786 |  158.436 |                 21.294 |           41.866 |         14.794 |
| PIT D/ST      | PIT       |       17.000 |       116.088 |   64.024 |  156.574 |                 21.880 |           41.593 |         15.023 |
| MIN D/ST      | MIN       |       17.000 |       113.665 |   62.688 |  153.306 |                 21.829 |           42.441 |         14.144 |
| LAC D/ST      | LAC       |       17.000 |       112.854 |   62.240 |  152.212 |                 21.425 |           41.663 |         15.077 |
| PHI D/ST      | PHI       |       17.000 |       112.722 |   62.168 |  152.034 |                 21.366 |           40.264 |         13.510 |
| BUF D/ST      | BUF       |       17.000 |       112.712 |   62.162 |  152.021 |                 21.753 |           39.331 |         14.664 |
| DET D/ST      | DET       |       17.000 |       110.368 |   60.870 |  148.859 |                 22.142 |           40.824 |         14.526 |
| LAR D/ST      | LAR       |       17.000 |       109.765 |   60.537 |  148.046 |                 22.420 |           40.746 |         14.343 |
| BAL D/ST      | BAL       |       17.000 |       109.548 |   60.417 |  147.753 |                 21.793 |           40.380 |         13.823 |
| JAX D/ST      | JAX       |       17.000 |       109.430 |   60.352 |  147.594 |                 22.194 |           37.293 |         15.100 |

### K

| player_name      | team_id   |   proj_games |   proj_fp_std |   fp_p10 |   fp_p90 |   proj_fg_made |   proj_pat_made |   team_points_est_pg | is_primary   |
|:-----------------|:----------|-------------:|--------------:|---------:|---------:|---------------:|----------------:|---------------------:|:-------------|
| Jake Bates       | DET       |       15.871 |       137.665 |   58.416 |  183.843 |         25.970 |          44.523 |               26.813 | True         |
| Cameron Dicker   | LAC       |       15.871 |       136.103 |   57.753 |  181.758 |         26.245 |          42.241 |               25.526 | True         |
| Evan McPherson   | CIN       |       15.871 |       135.501 |   57.498 |  180.955 |         25.393 |          42.469 |               25.655 | True         |
| Brandon Aubrey   | DAL       |       15.871 |       134.716 |   57.165 |  179.906 |         25.474 |          40.221 |               24.388 | True         |
| Tyler Loop       | BAL       |       15.871 |       133.441 |   56.624 |  178.203 |         26.440 |          42.072 |               25.431 | True         |
| Harrison Mevis   | LAR       |       15.871 |       132.709 |   56.313 |  177.225 |         26.143 |          41.335 |               25.016 | True         |
| Jake Elliott     | PHI       |       15.871 |       132.151 |   56.076 |  176.480 |         25.706 |          40.504 |               24.547 | True         |
| Chase McLaughlin | TB        |       15.871 |       131.953 |   55.992 |  176.216 |         26.093 |          39.101 |               23.757 | True         |
| Jason Myers      | SEA       |       15.871 |       131.658 |   55.867 |  175.822 |         25.482 |          39.039 |               23.722 | True         |
| Cam Little       | JAX       |       15.871 |       130.799 |   55.503 |  174.675 |         25.694 |          38.602 |               23.475 | True         |
| Tyler Bass       | BUF       |       15.871 |       130.477 |   55.366 |  174.245 |         25.889 |          39.549 |               24.009 | True         |
| Cairo Santos     | CHI       |       15.871 |       130.157 |   55.230 |  173.817 |         25.644 |          37.629 |               22.927 | True         |

## 7. Model coefficients

```json
{
  "dst": {
    "components": {
      "def_sacks": {
        "slope": 0.381,
        "intercept": 1.4299,
        "league_mean": 2.3035,
        "n": 640,
        "r": 0.2696,
        "forced_mean": false
      },
      "def_int": {
        "slope": 0.3745,
        "intercept": 0.5357,
        "league_mean": 0.8714,
        "n": 640,
        "r": 0.2676,
        "forced_mean": false
      },
      "def_fumble_rec": {
        "slope": 0.3251,
        "intercept": 0.3886,
        "league_mean": 0.5867,
        "n": 640,
        "r": 0.2296,
        "forced_mean": false
      },
      "def_td": {
        "slope": 0.0,
        "intercept": 0.0878,
        "league_mean": 0.0878,
        "n": 640,
        "r": 0.0,
        "forced_mean": true
      },
      "st_td": {
        "slope": 0.3288,
        "intercept": 0.0343,
        "league_mean": 0.0517,
        "n": 640,
        "r": 0.2303,
        "forced_mean": false
      },
      "def_safety": {
        "slope": 0.0,
        "intercept": 0.0309,
        "league_mean": 0.0309,
        "n": 640,
        "r": 0.0,
        "forced_mean": true
      },
      "def_blocked_kick": {
        "slope": 0.0,
        "intercept": 0.0791,
        "league_mean": 0.0791,
        "n": 640,
        "r": 0.0,
        "forced_mean": true
      },
      "def_forced_fumble": {
        "slope": 0.3662,
        "intercept": 0.5421,
        "league_mean": 0.8713,
        "n": 640,
        "r": 0.2624,
        "forced_mean": false
      }
    },
    "points_allowed": {
      "slope": 0.4519,
      "intercept": 12.397,
      "sos_coef": 0.2933,
      "league_mean_pg": 22.48,
      "resid_sd_pg": 3.274,
      "n": 640,
      "r": 0.3577
    },
    "pa_mix": {
      "n_games": 13934,
      "anchors": [
        17.1,
        20.09,
        21.91,
        24.07,
        27.34
      ],
      "mix": [
        [
          0.0335,
          0.0846,
          0.2622,
          0.1866,
          0.0992,
          0.1984,
          0.0938,
          0.041,
          0.0007
        ],
        [
          0.0151,
          0.0536,
          0.1809,
          0.1755,
          0.1194,
          0.2524,
          0.1374,
          0.0611,
          0.0047
        ],
        [
          0.0074,
          0.0348,
          0.1592,
          0.1595,
          0.1054,
          0.2734,
          0.1673,
          0.0822,
          0.0109
        ],
        [
          0.0062,
          0.0248,
          0.1135,
          0.1336,
          0.0989,
          0.2851,
          0.2052,
          0.1139,
          0.0186
        ],
        [
          0.0029,
          0.0108,
          0.0712,
          0.0958,
          0.0861,
          0.2665,
          0.242,
          0.1877,
          0.0369
        ]
      ],
      "labels": [
        "0",
        "1_6",
        "7_13",
        "14_17",
        "18_20",
        "21_27",
        "28_34",
        "35_45",
        "46p"
      ]
    },
    "yards_allowed": {
      "slope": 0.4786,
      "intercept": 178.044,
      "sos_coef": 2.6152,
      "league_mean_pg": 340.593,
      "resid_sd_pg": 28.97,
      "n": 640,
      "r": 0.3843
    },
    "ya_mix": {
      "n_games": 13912,
      "anchors": [
        289.65,
        319.83,
        336.24,
        352.44,
        381.82
      ],
      "mix": [
        [
          0.0057,
          0.1316,
          0.4181,
          0.2173,
          0.1388,
          0.0592,
          0.0219,
          0.0068,
          0.0007
        ],
        [
          0.0014,
          0.0591,
          0.3443,
          0.235,
          0.2092,
          0.1057,
          0.0337,
          0.0097,
          0.0018
        ],
        [
          0.0,
          0.0404,
          0.2812,
          0.243,
          0.2325,
          0.1278,
          0.0552,
          0.0159,
          0.004
        ],
        [
          0.0004,
          0.0258,
          0.2213,
          0.2407,
          0.2353,
          0.1714,
          0.0753,
          0.0222,
          0.0075
        ],
        [
          0.0004,
          0.0087,
          0.1532,
          0.1824,
          0.2383,
          0.2257,
          0.1139,
          0.0537,
          0.0238
        ]
      ],
      "labels": [
        "0_99",
        "100_199",
        "200_299",
        "300_349",
        "350_399",
        "400_449",
        "450_499",
        "500_549",
        "550p"
      ]
    }
  },
  "kicker": {
    "pat_att_coef": [
      -0.1978,
      0.1151
    ],
    "fg_att_coef": [
      1.915774,
      -0.005266,
      0.00026
    ],
    "pat_att_r": 0.3769,
    "fg_att_r": 0.0332,
    "league_att_mix": {
      "0_39": 0.5594,
      "40_49": 0.3004,
      "50_plus": 0.1402
    },
    "league_make": {
      "0_39": 0.9389,
      "40_49": 0.769,
      "50_plus": 0.6389
    },
    "pat_make": 0.9709,
    "make_shrink_attempts": 200.0,
    "mix_shrink_attempts": 60.0,
    "games_table": {
      "active=False,primary=False": 0.129,
      "active=False,primary=True": 0.4179,
      "active=True,primary=False": 0.6448,
      "active=True,primary=True": 0.9336
    },
    "n": 640
  },
  "diagnostics": {
    "n_dst_train_rows": 640,
    "n_team_kick_rows": 640,
    "n_kicker_games_rows": 810,
    "train_targets": [
      2006,
      2025
    ]
  }
}
```

## 8. Standing monitoring — the K/DST coverage floors have an OWNER

⭐ **DECISION: `run_interval_revalidation.py` is EXTENDED to cover the K/DST floors.** The alternative (scoping K/DST out of the standing check) was rejected: a per-position coverage floor is INVISIBLE at serving time — coverage needs realized outcomes, so no board build, export guard or API check can notice it break — and leaving two brand-new positions with silently-unmonitored bands is *precisely* the gap that let the veteran band go five stories at 0.55 of nominal. Run it once a season after the completed season lands:

```
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation \
  --rebuild-kdst-panel
```

⚠️ **The breach RESPONSE differs from the rookie/veteran populations, deliberately.** Those bands were SELECTED by a §0.5 bake-off, so a breach re-triggers that selection. The K/DST band is **reported, not selected** — there is no candidate field to re-run. A breach here means WIDEN THE BASE BAND HONESTLY (`RatioBand.widen`, which is monotone: it inflates the half-widths around 1.0 so it can only ever widen, never sharpen one side — the NF1.7 (d) widen-only invariant) and re-report. It does **not** mean move the floor: a floor that moves until something clears it is not a floor (E2.1-r).

## 9. Limitations — stated, not buried

- **This is a BASE model on the two least predictable fantasy positions.** Deliberately so (the story's own framing): the win is completeness + honest tiering. It is NOT a §0.5 bake-off, no model class was selected, and no `best_alpha`/PBO claim is made or implied.
- **Defensive TDs, safeties and blocked kicks are projected at the LEAGUE MEAN** because their measured year-over-year reliability is indistinguishable from zero. Any league that scores them heavily should read those columns as "the league-average expectation", not as a team-specific forecast. They are emitted rather than dropped so a league CAN score them.
- **A kicker's make rate is barely his own.** The 200-attempt shrink prior means a kicker's personal accuracy record moves his projection very little. That is the measurement (ρ = 0.085), not a shortcut — but it does mean the model will never tell you a kicker is "more accurate", only that his offense is better and his leg is stronger.
- **Kicker JOB security is a roster heuristic, not an oracle.** The incumbent is resolved by recency-weighted prior FG volume, and expected games come from a 4-cell empirical table. A genuine open camp battle is expressed as two rows each carrying the non-primary games share — honest, but it means neither row is right if the battle resolves cleanly. Re-run through camp as the roster feed refreshes.
- **FG-attempt volume is close to unforecastable** (r ≈ 0.19 with team scoring, and NON-MONOTONE). The model therefore assigns nearly the league-average attempt rate to everyone. A kicker's ranking is driven by PAT volume (his offense) and distance mix (his leg), which is the honest decomposition.
- **The points-allowed distribution is conditional on the projected RATE only.** It does not model within-season correlation, weather, or specific matchups; it is the league's empirical game-level shape for a defense of that quality.
- **A tier scheme whose points-allowed edges are not a union of the nine emitted buckets** cannot be scored exactly from the bucket columns — it must re-integrate from `proj_dst_pa_per_game`/`_sd`. ESPN and Yahoo both are exact.
- **NULL/unknown is kept NULL.** A team with no prior defensive history, or a kicker with no NFL attempts, is projected at the league mean and marked `confidence = very_low` rather than being given a fabricated team-specific number.

