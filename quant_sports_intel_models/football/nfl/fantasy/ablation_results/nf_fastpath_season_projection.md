# NF-FASTPATH — 2026 NFL fantasy season projections (raw stat-line, MVP-1)

**Model:** `nfl_fantasy_fastpath_v1` · **base season:** 2025 → **projects:** 2026 · **generated:** 2026-07-24T06:12:03.544512+00:00

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + P1A) and must be recalibrated before pricing.

## 1. The projection method (honest framing)

- **Veterans** — a **3-year recency+games-weighted** per-game line (weight = 0.6^age × games, so a career year or a down/injured year regresses toward the player's own baseline — the fix for single-season recency bias, esp. the spiky rushing-TD stat that ranked Trevor Lawrence QB2 off a fluke 9-rush-TD 2025), shrunk toward a conservative positional prior (position median) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve `per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` (Malik Willis was its #1).
- **Rookies (QB/RB/WR/TE)** — a historical draft-slot → rookie-year production curve (power-law per position, fit on prior classes) nudged by the **NCAAF-P1A residual** (`projected_nfl_z` vs the slot-expected z — talent the draft board disagreed with), with deliberately wide intervals. Defensive/OL rookies carry no fantasy line and are excluded (≈0, per P1A).

## 2. Coverage report

```json
{
  "n_total": 704,
  "n_veterans": 630,
  "n_rookies": 74,
  "by_position": {
    "FB": 12,
    "QB": 90,
    "RB": 164,
    "TE": 162,
    "WR": 276
  },
  "n_rookies_by_pos": {
    "FB": 1,
    "QB": 9,
    "RB": 11,
    "TE": 20,
    "WR": 33
  },
  "n_base_relevant_players_ge4g": 573,
  "n_relevant_gap": 40,
  "pct_relevant_covered": 93.0
}
```

## 3. Multi-season backtest — this model vs realized outcomes

Each PRIOR season below was projected with the SAME model (base = season−1, 3-yr regression) and scored against what actually happened — the FULL projection (veterans + rookies), over players who played ≥6 games. `spearman_all` (rank) is the headline; `sp_<POS>` is within-position rank correlation (what matters for drafting); `topN_hit` = of the realized top-24, how many the model ranked top-24. A signal check across seasons, not a calibration claim.

|   projection_season |   n |   spearman_all |   mae_ppr | top24_hit   |   sp_QB |   sp_RB |   sp_WR |   sp_TE |
|--------------------:|----:|---------------:|----------:|:------------|--------:|--------:|--------:|--------:|
|                2019 | 402 |            0.7 |      43.6 | 13/24       |     0.7 |     0.7 |     0.7 |     0.7 |
|                2020 | 421 |            0.8 |      45.3 | 11/24       |     0.6 |     0.6 |     0.7 |     0.7 |
|                2021 | 457 |            0.8 |      42.0 | 12/24       |     0.7 |     0.7 |     0.8 |     0.7 |
|                2022 | 442 |            0.8 |      39.9 | 9/24        |     0.7 |     0.7 |     0.8 |     0.7 |
|                2023 | 441 |            0.7 |      42.6 | 9/24        |     0.6 |     0.7 |     0.7 |     0.8 |
|                2024 | 443 |            0.8 |      43.1 | 8/24        |     0.7 |     0.7 |     0.8 |     0.7 |
|                2025 | 450 |            0.8 |      40.2 | 11/24       |     0.5 |     0.7 |     0.8 |     0.7 |

## 4. Face validity — top 25 overall (projected PPR)

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN          | QB         | BUF       | veteran  |         16.5 |         305.7 |        215.0 |        396.5 |
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         16.2 |         294.0 |        211.4 |        376.7 |
| JALEN HURTS         | QB         | PHI       | veteran  |         16.5 |         284.1 |        211.2 |        357.0 |
| DAK PRESCOTT        | QB         | DAL       | veteran  |         16.5 |         281.2 |        209.9 |        352.5 |
| TREVOR LAWRENCE     | QB         | JAX       | veteran  |         16.5 |         278.7 |        203.0 |        354.4 |
| JARED GOFF          | QB         | DET       | veteran  |         16.5 |         278.6 |        210.1 |        347.1 |
| BAKER MAYFIELD      | QB         | TB        | veteran  |         16.5 |         273.8 |        209.7 |        338.0 |
| BO NIX              | QB         | DEN       | veteran  |         16.5 |         270.6 |        198.1 |        343.1 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         16.2 |         269.3 |        192.7 |        345.8 |
| Fernando Mendoza    | QB         | nan       | rookie   |         12.4 |         268.3 |          5.6 |        531.1 |
| LAMAR JACKSON       | QB         | BAL       | veteran  |         14.5 |         266.5 |        190.9 |        342.1 |
| JUSTIN HERBERT      | QB         | LAC       | veteran  |         16.5 |         266.0 |        195.8 |        336.1 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         16.2 |         262.1 |        178.4 |        345.9 |
| JA'MARR CHASE       | WR         | CIN       | veteran  |         15.8 |         261.6 |        185.5 |        337.7 |
| CALEB WILLIAMS      | QB         | CHI       | veteran  |         16.5 |         260.0 |        187.0 |        333.0 |
| DRAKE MAYE          | QB         | NE        | veteran  |         16.5 |         259.6 |        187.1 |        332.1 |
| MATTHEW STAFFORD    | QB         | LAR       | veteran  |         16.5 |         253.9 |        181.2 |        326.6 |
| AMON-RA ST. BROWN   | WR         | DET       | veteran  |         16.2 |         251.5 |        175.1 |        328.0 |
| PATRICK MAHOMES     | QB         | KC        | veteran  |         15.0 |         250.4 |        182.1 |        318.8 |
| PUKA NACUA          | WR         | LAR       | veteran  |         16.2 |         250.2 |        166.5 |        334.0 |
| DEVON ACHANE        | RB         | MIA       | veteran  |         15.8 |         242.9 |        180.3 |        305.4 |
| JORDAN LOVE         | QB         | GB        | veteran  |         16.0 |         239.1 |        174.1 |        304.2 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.0 |         232.8 |        122.3 |        343.4 |
| SAM DARNOLD         | QB         | MIN       | veteran  |         16.5 |         232.5 |        169.9 |        295.2 |
| Jaxson Dart         | QB         | NYG       | veteran  |         14.0 |         231.2 |        118.4 |        344.0 |

### Top 12 QB

| player_name      | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN       | QB         | BUF       | veteran  |         16.5 |         305.7 |        215.0 |        396.5 |
| JALEN HURTS      | QB         | PHI       | veteran  |         16.5 |         284.1 |        211.2 |        357.0 |
| DAK PRESCOTT     | QB         | DAL       | veteran  |         16.5 |         281.2 |        209.9 |        352.5 |
| TREVOR LAWRENCE  | QB         | JAX       | veteran  |         16.5 |         278.7 |        203.0 |        354.4 |
| JARED GOFF       | QB         | DET       | veteran  |         16.5 |         278.6 |        210.1 |        347.1 |
| BAKER MAYFIELD   | QB         | TB        | veteran  |         16.5 |         273.8 |        209.7 |        338.0 |
| BO NIX           | QB         | DEN       | veteran  |         16.5 |         270.6 |        198.1 |        343.1 |
| Fernando Mendoza | QB         | nan       | rookie   |         12.4 |         268.3 |          5.6 |        531.1 |
| LAMAR JACKSON    | QB         | BAL       | veteran  |         14.5 |         266.5 |        190.9 |        342.1 |
| JUSTIN HERBERT   | QB         | LAC       | veteran  |         16.5 |         266.0 |        195.8 |        336.1 |
| CALEB WILLIAMS   | QB         | CHI       | veteran  |         16.5 |         260.0 |        187.0 |        333.0 |
| DRAKE MAYE       | QB         | NE        | veteran  |         16.5 |         259.6 |        187.1 |        332.1 |

### Top 12 RB

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         16.2 |         294.0 |        211.4 |        376.7 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         16.2 |         269.3 |        192.7 |        345.8 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         16.2 |         262.1 |        178.4 |        345.9 |
| DEVON ACHANE        | RB         | MIA       | veteran  |         15.8 |         242.9 |        180.3 |        305.4 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.0 |         232.8 |        122.3 |        343.4 |
| DERRICK HENRY       | RB         | BAL       | veteran  |         16.2 |         227.3 |        157.7 |        296.9 |
| SAQUON BARKLEY      | RB         | PHI       | veteran  |         16.2 |         210.6 |        151.5 |        269.6 |
| Jeremiyah Love      | RB         | nan       | rookie   |         16.0 |         210.1 |          0.0 |        446.8 |
| JAMES COOK          | RB         | BUF       | veteran  |         16.2 |         209.0 |        140.6 |        277.4 |
| KYREN WILLIAMS      | RB         | LAR       | veteran  |         16.2 |         208.0 |        148.7 |        267.3 |
| JOSH JACOBS         | RB         | GB        | veteran  |         15.8 |         203.2 |        138.3 |        268.1 |
| CHASE BROWN         | RB         | CIN       | veteran  |         16.2 |         201.6 |        145.5 |        257.7 |

### Top 12 WR

| player_name        | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JA'MARR CHASE      | WR         | CIN       | veteran  |         15.8 |         261.6 |        185.5 |        337.7 |
| AMON-RA ST. BROWN  | WR         | DET       | veteran  |         16.2 |         251.5 |        175.1 |        328.0 |
| PUKA NACUA         | WR         | LAR       | veteran  |         16.2 |         250.2 |        166.5 |        334.0 |
| JAXON SMITH-NJIGBA | WR         | SEA       | veteran  |         16.2 |         217.8 |        148.1 |        287.4 |
| CEEDEE LAMB        | WR         | DAL       | veteran  |         14.8 |         203.7 |        146.0 |        261.5 |
| JUSTIN JEFFERSON   | WR         | MIN       | veteran  |         16.2 |         202.9 |        151.7 |        254.2 |
| Jordyn Tyson       | WR         | nan       | rookie   |         13.9 |         199.4 |          0.0 |        416.9 |
| CHRIS OLAVE        | WR         | NO        | veteran  |         15.8 |         196.8 |        138.9 |        254.7 |
| GEORGE PICKENS     | WR         | PIT       | veteran  |         16.2 |         196.6 |        132.5 |        260.7 |
| NICO COLLINS       | WR         | HOU       | veteran  |         15.8 |         194.5 |        139.0 |        250.0 |
| DAVANTE ADAMS      | WR         | NYJ       | veteran  |         14.8 |         193.9 |        138.7 |        249.1 |
| ZAY FLOWERS        | WR         | BAL       | veteran  |         16.2 |         187.7 |        133.2 |        242.3 |

### Top 12 TE

| player_name       | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| TREY MCBRIDE      | TE         | ARI       | veteran  |         16.2 |         212.4 |        151.0 |        273.7 |
| BROCK BOWERS      | TE         | LV        | veteran  |         13.8 |         156.3 |         95.1 |        217.6 |
| TRAVIS KELCE      | TE         | KC        | veteran  |         16.2 |         153.3 |        107.7 |        199.0 |
| GEORGE KITTLE     | TE         | SF        | veteran  |         13.8 |         148.1 |         92.5 |        203.7 |
| Harold Fannin Jr. | TE         | CLE       | veteran  |         15.0 |         144.5 |         78.8 |        210.2 |
| Tyler Warren      | TE         | IND       | veteran  |         15.5 |         142.6 |         80.9 |        204.3 |
| Kenyon Sadiq      | TE         | nan       | rookie   |         15.3 |         139.5 |          0.0 |        288.6 |
| KYLE PITTS        | TE         | ATL       | veteran  |         16.2 |         138.1 |         79.5 |        196.8 |
| JAKE FERGUSON     | TE         | DAL       | veteran  |         16.2 |         135.9 |         89.8 |        181.9 |
| DALLAS GOEDERT    | TE         | PHI       | veteran  |         15.8 |         129.9 |         82.6 |        177.3 |
| Colston Loveland  | TE         | CHI       | veteran  |         15.0 |         128.1 |         60.8 |        195.5 |
| JUWAN JOHNSON     | TE         | NO        | veteran  |         16.2 |         125.7 |         89.8 |        161.6 |

## 5. Face validity — top 15 ROOKIES (P1A-attached)

| player_name      | position   |   draft_overall |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|----------------:|-------------:|--------------:|-------------:|-------------:|
| Fernando Mendoza | QB         |             1.0 |         12.4 |         268.3 |          5.6 |        531.1 |
| Jeremiyah Love   | RB         |             3.0 |         16.0 |         210.1 |          0.0 |        446.8 |
| Jordyn Tyson     | WR         |             8.0 |         13.9 |         199.4 |          0.0 |        416.9 |
| Carnell Tate     | WR         |             4.0 |         13.9 |         173.9 |          0.0 |        363.5 |
| Kenyon Sadiq     | TE         |            16.0 |         15.3 |         139.5 |          0.0 |        288.6 |
| Makai Lemon      | WR         |            20.0 |         14.1 |         116.2 |          0.0 |        242.9 |
| Jadarian Price   | RB         |            32.0 |         13.4 |          91.1 |          0.0 |        193.6 |
| KC Concepcion    | WR         |            24.0 |         14.1 |          84.7 |          0.0 |        177.0 |
| Omar Cooper Jr.  | WR         |            30.0 |         14.1 |          70.2 |          0.0 |        146.7 |
| Denzel Boston    | WR         |            39.0 |         14.1 |          67.8 |          0.0 |        141.8 |
| Ty Simpson       | QB         |            13.0 |         12.4 |          58.9 |          1.2 |        116.5 |
| Germie Bernard   | WR         |            47.0 |         13.9 |          54.3 |          0.0 |        113.5 |
| Eli Stowers      | TE         |            54.0 |         13.7 |          51.7 |          0.0 |        106.9 |
| Antonio Williams | WR         |            71.0 |         13.9 |          44.7 |          0.0 |         93.4 |
| Jonah Coleman    | RB         |           108.0 |         11.6 |          42.1 |          0.0 |         89.6 |

## 6. Limitations

- **First-pass MVP** — the full NF1 model (posterior-predictive, weekly, §0.5 bake-off) refines this. The gate here is face-validity + coverage, not a selected model.
- **Expected-games is a role heuristic, not a depth-chart oracle** — offseason moves (trades, signings, camp battles, holdouts) are not yet ingested; a base-season backup who wins a 2026 job is under-projected until depth charts refresh. Surfaced via the wide games interval.
- **Rookie uncertainty is PARAMETER uncertainty** (slot curve + P1A `sd`), not a calibrated predictive interval — NF-C1/pricing must recalibrate (the E13.6 pattern).
- **Rookie team = NULL** (2026 draftees are not in the base-season role dimension) — kept NULL, not guessed.
- **Two-point conversions kept NULL** (rare/idiosyncratic); fumbles-lost is a modest per-touch estimate. Both are small scoring nuisance terms.

