# NF-FASTPATH — 2026 NFL fantasy season projections (raw stat-line, MVP-1)

**Model:** `nfl_fantasy_fastpath_v1` · **base season:** 2025 → **projects:** 2026 · **generated:** 2026-07-24T04:41:33.466482+00:00

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + P1A) and must be recalibrated before pricing.

## 1. The projection method (honest framing)

- **Veterans** — realized base-season per-game line, shrunk toward a conservative positional prior (position median over qualified players) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve `per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` (Malik Willis was its #1).
- **Rookies (QB/RB/WR/TE)** — a historical draft-slot → rookie-year production curve (power-law per position, fit on prior classes) nudged by the **NCAAF-P1A residual** (`projected_nfl_z` vs the slot-expected z — talent the draft board disagreed with), with deliberately wide intervals. Defensive/OL rookies carry no fantasy line and are excluded (≈0, per P1A).

## 2. Coverage report

```json
{
  "n_total": 576,
  "n_veterans": 502,
  "n_rookies": 74,
  "by_position": {
    "FB": 11,
    "QB": 76,
    "RB": 127,
    "TE": 140,
    "WR": 222
  },
  "n_rookies_by_pos": {
    "FB": 1,
    "QB": 9,
    "RB": 11,
    "TE": 20,
    "WR": 33
  },
  "n_base_relevant_players_ge4g": 479,
  "n_relevant_gap": 33,
  "pct_relevant_covered": 93.1
}
```

## 3. Holdout-season sanity check (does the veteran method have signal?)

Replicate the veteran projection for an earlier base season and score its projected PPR ranking against the realized next season, over players who actually played the target season. Spearman (rank) is the headline; this is a signal check, not a calibration claim.

|   base_season |   target_season |     n |   spearman |   pearson |   mae_ppr |   top24_overlap |   top24_of |
|--------------:|----------------:|------:|-----------:|----------:|----------:|----------------:|-----------:|
|        2022.0 |          2023.0 | 361.0 |        0.7 |       0.7 |      47.6 |             9.0 |       24.0 |
|        2023.0 |          2024.0 | 366.0 |        0.8 |       0.7 |      48.4 |            10.0 |       24.0 |

## 4. Face validity — top 25 overall (projected PPR)

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN          | QB         | BUF       | veteran  |         16.5 |         302.4 |        212.1 |        392.6 |
| TREVOR LAWRENCE     | QB         | JAX       | veteran  |         16.5 |         296.8 |        218.4 |        375.3 |
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         16.2 |         295.8 |        212.8 |        378.7 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         16.2 |         292.2 |        212.2 |        372.2 |
| DEVON ACHANE        | RB         | MIA       | veteran  |         16.2 |         291.4 |        221.8 |        361.0 |
| DAK PRESCOTT        | QB         | DAL       | veteran  |         16.5 |         287.8 |        215.4 |        360.1 |
| JARED GOFF          | QB         | DET       | veteran  |         16.5 |         284.5 |        215.0 |        354.1 |
| JALEN HURTS         | QB         | PHI       | veteran  |         16.5 |         283.8 |        210.9 |        356.6 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         16.2 |         282.9 |        196.3 |        369.5 |
| MATTHEW STAFFORD    | QB         | LAR       | veteran  |         16.5 |         282.9 |        205.9 |        359.8 |
| PATRICK MAHOMES     | QB         | KC        | veteran  |         15.0 |         279.8 |        206.1 |        353.6 |
| Fernando Mendoza    | QB         | nan       | rookie   |         12.3 |         278.0 |          1.0 |        555.1 |
| JUSTIN HERBERT      | QB         | LAC       | veteran  |         16.5 |         270.3 |        199.5 |        341.2 |
| DRAKE MAYE          | QB         | NE        | veteran  |         16.5 |         269.9 |        195.8 |        343.9 |
| PUKA NACUA          | WR         | LAR       | veteran  |         16.2 |         269.5 |        183.3 |        355.7 |
| CALEB WILLIAMS      | QB         | CHI       | veteran  |         16.5 |         268.0 |        193.8 |        342.2 |
| BO NIX              | QB         | DEN       | veteran  |         16.5 |         267.2 |        195.2 |        339.1 |
| BAKER MAYFIELD      | QB         | TB        | veteran  |         16.5 |         259.4 |        197.7 |        321.0 |
| AMON-RA ST. BROWN   | WR         | DET       | veteran  |         16.2 |         255.0 |        178.0 |        331.9 |
| JA'MARR CHASE       | WR         | CIN       | veteran  |         15.8 |         252.5 |        177.8 |        327.2 |
| JAXON SMITH-NJIGBA  | WR         | SEA       | veteran  |         16.2 |         249.0 |        175.0 |        322.9 |
| DANIEL JONES        | QB         | NYG       | veteran  |         14.0 |         248.4 |        184.2 |        312.7 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.0 |         248.3 |        132.9 |        363.7 |
| TREY MCBRIDE        | TE         | ARI       | veteran  |         16.2 |         241.3 |        175.6 |        307.0 |
| LAMAR JACKSON       | QB         | BAL       | veteran  |         14.5 |         234.1 |        164.4 |        303.8 |

### Top 12 QB

| player_name      | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN       | QB         | BUF       | veteran  |         16.5 |         302.4 |        212.1 |        392.6 |
| TREVOR LAWRENCE  | QB         | JAX       | veteran  |         16.5 |         296.8 |        218.4 |        375.3 |
| DAK PRESCOTT     | QB         | DAL       | veteran  |         16.5 |         287.8 |        215.4 |        360.1 |
| JARED GOFF       | QB         | DET       | veteran  |         16.5 |         284.5 |        215.0 |        354.1 |
| JALEN HURTS      | QB         | PHI       | veteran  |         16.5 |         283.8 |        210.9 |        356.6 |
| MATTHEW STAFFORD | QB         | LAR       | veteran  |         16.5 |         282.9 |        205.9 |        359.8 |
| PATRICK MAHOMES  | QB         | KC        | veteran  |         15.0 |         279.8 |        206.1 |        353.6 |
| Fernando Mendoza | QB         | nan       | rookie   |         12.3 |         278.0 |          1.0 |        555.1 |
| JUSTIN HERBERT   | QB         | LAC       | veteran  |         16.5 |         270.3 |        199.5 |        341.2 |
| DRAKE MAYE       | QB         | NE        | veteran  |         16.5 |         269.9 |        195.8 |        343.9 |
| CALEB WILLIAMS   | QB         | CHI       | veteran  |         16.5 |         268.0 |        193.8 |        342.2 |
| BO NIX           | QB         | DEN       | veteran  |         16.5 |         267.2 |        195.2 |        339.1 |

### Top 12 RB

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         16.2 |         295.8 |        212.8 |        378.7 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         16.2 |         292.2 |        212.2 |        372.2 |
| DEVON ACHANE        | RB         | MIA       | veteran  |         16.2 |         291.4 |        221.8 |        361.0 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         16.2 |         282.9 |        196.3 |        369.5 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.0 |         248.3 |        132.9 |        363.7 |
| Jeremiyah Love      | RB         | nan       | rookie   |         15.7 |         227.3 |          0.0 |        494.0 |
| DERRICK HENRY       | RB         | BAL       | veteran  |         16.2 |         226.6 |        157.1 |        296.1 |
| CHASE BROWN         | RB         | CIN       | veteran  |         16.2 |         223.2 |        163.7 |        282.6 |
| JAMES COOK          | RB         | BUF       | veteran  |         16.2 |         222.9 |        152.7 |        293.2 |
| JOSH JACOBS         | RB         | GB        | veteran  |         15.8 |         197.3 |        133.2 |        261.4 |
| JAVONTE WILLIAMS    | RB         | DEN       | veteran  |         15.2 |         195.7 |        143.0 |        248.5 |
| TRAVIS ETIENNE      | RB         | JAX       | veteran  |         16.2 |         194.6 |        138.7 |        250.6 |

### Top 12 WR

| player_name        | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| PUKA NACUA         | WR         | LAR       | veteran  |         16.2 |         269.5 |        183.3 |        355.7 |
| AMON-RA ST. BROWN  | WR         | DET       | veteran  |         16.2 |         255.0 |        178.0 |        331.9 |
| JA'MARR CHASE      | WR         | CIN       | veteran  |         15.8 |         252.5 |        177.8 |        327.2 |
| JAXON SMITH-NJIGBA | WR         | SEA       | veteran  |         16.2 |         249.0 |        175.0 |        322.9 |
| GEORGE PICKENS     | WR         | PIT       | veteran  |         15.8 |         223.3 |        154.2 |        292.5 |
| CHRIS OLAVE        | WR         | NO        | veteran  |         15.8 |         217.3 |        156.2 |        278.4 |
| Jordyn Tyson       | WR         | nan       | rookie   |         14.1 |         216.2 |          0.0 |        465.6 |
| ZAY FLOWERS        | WR         | BAL       | veteran  |         16.2 |         200.0 |        143.7 |        256.4 |
| Carnell Tate       | WR         | nan       | rookie   |         14.1 |         188.5 |          0.0 |        405.9 |
| NICO COLLINS       | WR         | HOU       | veteran  |         15.8 |         186.0 |        131.8 |        240.2 |
| A.J. BROWN         | WR         | PHI       | veteran  |         15.8 |         181.5 |        117.3 |        245.7 |
| DRAKE LONDON       | WR         | ATL       | veteran  |         13.8 |         181.0 |        111.1 |        250.9 |

### Top 12 TE

| player_name    | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:---------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| TREY MCBRIDE   | TE         | ARI       | veteran  |         16.2 |         241.3 |        175.6 |        307.0 |
| KYLE PITTS     | TE         | ATL       | veteran  |         16.2 |         164.0 |        102.6 |        225.4 |
| BROCK BOWERS   | TE         | LV        | veteran  |         13.8 |         150.2 |         89.9 |        210.5 |
| TRAVIS KELCE   | TE         | KC        | veteran  |         16.2 |         149.6 |        104.5 |        194.7 |
| JAKE FERGUSON  | TE         | DAL       | veteran  |         16.2 |         148.8 |        101.1 |        196.4 |
| DALLAS GOEDERT | TE         | PHI       | veteran  |         15.8 |         147.5 |         97.9 |        197.1 |
| JUWAN JOHNSON  | TE         | NO        | veteran  |         16.2 |         144.2 |        105.6 |        182.9 |
| GEORGE KITTLE  | TE         | SF        | veteran  |         13.8 |         140.2 |         85.8 |        194.7 |
| DALTON SCHULTZ | TE         | HOU       | veteran  |         16.2 |         128.0 |         86.3 |        169.6 |
| Kenyon Sadiq   | TE         | nan       | rookie   |         15.3 |         125.8 |          0.0 |        272.1 |
| HUNTER HENRY   | TE         | NE        | veteran  |         16.2 |         119.0 |         72.0 |        165.9 |
| TUCKER KRAFT   | TE         | GB        | veteran  |         11.8 |         116.7 |         62.1 |        171.2 |

## 5. Face validity — top 15 ROOKIES (P1A-attached)

| player_name      | position   |   draft_overall |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|----------------:|-------------:|--------------:|-------------:|-------------:|
| Fernando Mendoza | QB         |             1.0 |         12.3 |         278.0 |          1.0 |        555.1 |
| Jeremiyah Love   | RB         |             3.0 |         15.7 |         227.3 |          0.0 |        494.0 |
| Jordyn Tyson     | WR         |             8.0 |         14.1 |         216.2 |          0.0 |        465.6 |
| Carnell Tate     | WR         |             4.0 |         14.1 |         188.5 |          0.0 |        405.9 |
| Kenyon Sadiq     | TE         |            16.0 |         15.3 |         125.8 |          0.0 |        272.1 |
| Makai Lemon      | WR         |            20.0 |         14.5 |         115.4 |          0.0 |        248.6 |
| Jadarian Price   | RB         |            32.0 |         13.4 |          95.2 |          0.0 |        206.9 |
| KC Concepcion    | WR         |            24.0 |         14.5 |          84.6 |          0.0 |        182.2 |
| Omar Cooper Jr.  | WR         |            30.0 |         14.5 |          70.6 |          0.0 |        152.1 |
| Denzel Boston    | WR         |            39.0 |         14.5 |          68.8 |          0.0 |        148.2 |
| Ty Simpson       | QB         |            13.0 |         12.3 |          57.6 |          0.2 |        115.1 |
| Germie Bernard   | WR         |            47.0 |         15.6 |          55.4 |          0.0 |        119.4 |
| Eli Stowers      | TE         |            54.0 |         13.6 |          49.7 |          0.0 |        107.5 |
| Antonio Williams | WR         |            71.0 |         15.6 |          46.2 |          0.0 |         99.6 |
| Ted Hurst        | WR         |            84.0 |         15.6 |          43.7 |          0.0 |         94.2 |

## 6. Limitations

- **First-pass MVP** — the full NF1 model (posterior-predictive, weekly, §0.5 bake-off) refines this. The gate here is face-validity + coverage, not a selected model.
- **Expected-games is a role heuristic, not a depth-chart oracle** — offseason moves (trades, signings, camp battles, holdouts) are not yet ingested; a base-season backup who wins a 2026 job is under-projected until depth charts refresh. Surfaced via the wide games interval.
- **Rookie uncertainty is PARAMETER uncertainty** (slot curve + P1A `sd`), not a calibrated predictive interval — NF-C1/pricing must recalibrate (the E13.6 pattern).
- **Rookie team = NULL** (2026 draftees are not in the base-season role dimension) — kept NULL, not guessed.
- **Two-point conversions kept NULL** (rare/idiosyncratic); fumbles-lost is a modest per-touch estimate. Both are small scoring nuisance terms.

