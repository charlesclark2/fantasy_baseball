# NF-FASTPATH — 2026 NFL fantasy season projections (raw stat-line, MVP-1)

**Model:** `nfl_fantasy_fastpath_v1` · **base season:** 2025 → **projects:** 2026 · **generated:** 2026-07-25T06:56:16.387344+00:00

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + P1A) and must be recalibrated before pricing.

## 1. The projection method (honest framing)

- **Veterans** — a **3-year recency+games-weighted** per-game line (weight = 0.6^age × games, so a career year or a down/injured year regresses toward the player's own baseline — the fix for single-season recency bias, esp. the spiky rushing-TD stat that ranked Trevor Lawrence QB2 off a fluke 9-rush-TD 2025), shrunk toward a conservative positional prior (position median) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve `per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` (Malik Willis was its #1).
- **Rookies (QB/RB/WR/TE)** — a historical draft-slot → rookie-year production curve (power-law per position, fit on prior classes) nudged by the **NCAAF-P1A residual** (`projected_nfl_z` vs the slot-expected z — talent the draft board disagreed with), with deliberately wide intervals. Defensive/OL rookies carry no fantasy line and are excluded (≈0, per P1A).

## 2. Coverage report

```json
{
  "n_total": 721,
  "n_veterans": 647,
  "n_rookies": 74,
  "by_position": {
    "FB": 18,
    "QB": 90,
    "RB": 163,
    "TE": 163,
    "WR": 287
  },
  "n_rookies_by_pos": {
    "FB": 1,
    "QB": 9,
    "RB": 11,
    "TE": 20,
    "WR": 33
  },
  "n_base_relevant_players_ge4g": 596,
  "n_relevant_gap": 40,
  "pct_relevant_covered": 93.3
}
```

## 3. Multi-season backtest — this model vs realized outcomes

Each PRIOR season below was projected with the SAME model (base = season−1, 3-yr regression) and scored against what actually happened — the FULL projection (veterans + rookies), over players who played ≥6 games. `spearman_all` (rank) is the headline; `sp_<POS>` is within-position rank correlation (what matters for drafting); `topN_hit` = of the realized top-24, how many the model ranked top-24. A signal check across seasons, not a calibration claim.


## 4. Face validity — top 25 overall (projected PPR)

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN          | QB         | BUF       | veteran  |         16.5 |         314.1 |        222.2 |        406.0 |
| JALEN HURTS         | QB         | PHI       | veteran  |         16.5 |         296.5 |        221.6 |        371.4 |
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         16.2 |         293.9 |        211.2 |        376.5 |
| JARED GOFF          | QB         | DET       | veteran  |         16.5 |         282.4 |        213.3 |        351.6 |
| DAK PRESCOTT        | QB         | DAL       | veteran  |         16.5 |         281.1 |        209.8 |        352.4 |
| TREVOR LAWRENCE     | QB         | JAX       | veteran  |         16.5 |         278.5 |        202.9 |        354.2 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         16.2 |         274.7 |        184.9 |        364.4 |
| BAKER MAYFIELD      | QB         | TB        | veteran  |         16.5 |         273.7 |        209.5 |        337.8 |
| LAMAR JACKSON       | QB         | BAL       | veteran  |         14.5 |         270.6 |        194.2 |        346.9 |
| BO NIX              | QB         | DEN       | veteran  |         16.5 |         270.4 |        197.9 |        342.9 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         16.2 |         269.1 |        192.6 |        345.6 |
| Fernando Mendoza    | QB         | nan       | rookie   |         12.4 |         268.3 |          5.6 |        531.1 |
| JUSTIN HERBERT      | QB         | LAC       | veteran  |         16.5 |         265.8 |        195.7 |        335.9 |
| PATRICK MAHOMES     | QB         | KC        | veteran  |         15.0 |         262.0 |        191.6 |        332.5 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         16.2 |         262.0 |        178.2 |        345.8 |
| MATTHEW STAFFORD    | QB         | LAR       | veteran  |         16.5 |         260.7 |        187.1 |        334.4 |
| JA'MARR CHASE       | WR         | CIN       | veteran  |         15.8 |         260.1 |        184.2 |        335.9 |
| CALEB WILLIAMS      | QB         | CHI       | veteran  |         16.5 |         259.9 |        186.9 |        332.9 |
| DRAKE MAYE          | QB         | NE        | veteran  |         16.5 |         259.5 |        187.0 |        332.0 |
| PUKA NACUA          | WR         | LAR       | veteran  |         16.2 |         257.6 |        173.0 |        342.3 |
| AMON-RA ST. BROWN   | WR         | DET       | veteran  |         16.2 |         254.3 |        177.4 |        331.1 |
| JAXSON DART         | QB         | NYG       | veteran  |         15.0 |         247.5 |        172.7 |        322.4 |
| DE'VON ACHANE       | RB         | MIA       | veteran  |         15.8 |         242.7 |        180.2 |        305.3 |
| JORDAN LOVE         | QB         | GB        | veteran  |         16.0 |         239.0 |        173.9 |        304.0 |
| DERRICK HENRY       | RB         | BAL       | veteran  |         16.2 |         230.8 |        160.7 |        300.9 |

### Top 12 QB

| player_name      | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN       | QB         | BUF       | veteran  |         16.5 |         314.1 |        222.2 |        406.0 |
| JALEN HURTS      | QB         | PHI       | veteran  |         16.5 |         296.5 |        221.6 |        371.4 |
| JARED GOFF       | QB         | DET       | veteran  |         16.5 |         282.4 |        213.3 |        351.6 |
| DAK PRESCOTT     | QB         | DAL       | veteran  |         16.5 |         281.1 |        209.8 |        352.4 |
| TREVOR LAWRENCE  | QB         | JAX       | veteran  |         16.5 |         278.5 |        202.9 |        354.2 |
| BAKER MAYFIELD   | QB         | TB        | veteran  |         16.5 |         273.7 |        209.5 |        337.8 |
| LAMAR JACKSON    | QB         | BAL       | veteran  |         14.5 |         270.6 |        194.2 |        346.9 |
| BO NIX           | QB         | DEN       | veteran  |         16.5 |         270.4 |        197.9 |        342.9 |
| Fernando Mendoza | QB         | nan       | rookie   |         12.4 |         268.3 |          5.6 |        531.1 |
| JUSTIN HERBERT   | QB         | LAC       | veteran  |         16.5 |         265.8 |        195.7 |        335.9 |
| PATRICK MAHOMES  | QB         | KC        | veteran  |         15.0 |         262.0 |        191.6 |        332.5 |
| MATTHEW STAFFORD | QB         | LAR       | veteran  |         16.5 |         260.7 |        187.1 |        334.4 |

### Top 12 RB

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         16.2 |         293.9 |        211.2 |        376.5 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         16.2 |         274.7 |        184.9 |        364.4 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         16.2 |         269.1 |        192.6 |        345.6 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         16.2 |         262.0 |        178.2 |        345.8 |
| DE'VON ACHANE       | RB         | MIA       | veteran  |         15.8 |         242.7 |        180.2 |        305.3 |
| DERRICK HENRY       | RB         | BAL       | veteran  |         16.2 |         230.8 |        160.7 |        300.9 |
| SAQUON BARKLEY      | RB         | PHI       | veteran  |         16.2 |         221.0 |        160.4 |        281.7 |
| JAMES COOK III      | RB         | BUF       | veteran  |         16.2 |         215.3 |        146.0 |        284.5 |
| KYREN WILLIAMS      | RB         | LAR       | veteran  |         16.2 |         214.5 |        154.2 |        274.8 |
| Jeremiyah Love      | RB         | nan       | rookie   |         16.0 |         208.4 |          0.0 |        443.2 |
| JOSH JACOBS         | RB         | GB        | veteran  |         15.8 |         203.1 |        138.1 |        268.0 |
| CHASE BROWN         | RB         | CIN       | veteran  |         16.2 |         201.4 |        145.3 |        257.5 |

### Top 12 WR

| player_name        | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JA'MARR CHASE      | WR         | CIN       | veteran  |         15.8 |         260.1 |        184.2 |        335.9 |
| PUKA NACUA         | WR         | LAR       | veteran  |         16.2 |         257.6 |        173.0 |        342.3 |
| AMON-RA ST. BROWN  | WR         | DET       | veteran  |         16.2 |         254.3 |        177.4 |        331.1 |
| JAXON SMITH-NJIGBA | WR         | SEA       | veteran  |         16.2 |         216.4 |        146.9 |        286.0 |
| CEEDEE LAMB        | WR         | DAL       | veteran  |         14.8 |         202.2 |        144.7 |        259.6 |
| JUSTIN JEFFERSON   | WR         | MIN       | veteran  |         16.2 |         201.4 |        150.4 |        252.4 |
| NICO COLLINS       | WR         | HOU       | veteran  |         15.8 |         196.5 |        140.7 |        252.4 |
| CHRIS OLAVE        | WR         | NO        | veteran  |         15.8 |         195.3 |        137.6 |        252.9 |
| A.J. BROWN         | WR         | PHI       | veteran  |         15.8 |         195.0 |        129.0 |        260.9 |
| Jordyn Tyson       | WR         | nan       | rookie   |         13.6 |         191.8 |          0.0 |        401.0 |
| ZAY FLOWERS        | WR         | BAL       | veteran  |         16.2 |         186.2 |        131.9 |        240.5 |
| Carnell Tate       | WR         | nan       | rookie   |         13.6 |         172.9 |          0.0 |        361.4 |

### Top 12 TE

| player_name       | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| TREY MCBRIDE      | TE         | ARI       | veteran  |         16.2 |         210.8 |        149.7 |        271.9 |
| TRAVIS KELCE      | TE         | KC        | veteran  |         16.2 |         159.7 |        113.1 |        206.2 |
| BROCK BOWERS      | TE         | LV        | veteran  |         13.8 |         154.6 |         93.6 |        215.6 |
| HAROLD FANNIN JR. | TE         | CLE       | veteran  |         15.8 |         150.1 |        107.0 |        193.2 |
| TYLER WARREN      | TE         | IND       | veteran  |         16.2 |         147.9 |        108.4 |        187.3 |
| GEORGE KITTLE     | TE         | SF        | veteran  |         13.8 |         146.4 |         91.0 |        201.7 |
| Kenyon Sadiq      | TE         | nan       | rookie   |         15.3 |         139.5 |          0.0 |        288.6 |
| DALLAS GOEDERT    | TE         | PHI       | veteran  |         15.8 |         138.7 |         90.3 |        187.2 |
| KYLE PITTS SR.    | TE         | ATL       | veteran  |         16.2 |         136.6 |         78.1 |        195.0 |
| JAKE FERGUSON     | TE         | DAL       | veteran  |         16.2 |         134.3 |         88.5 |        180.1 |
| MARK ANDREWS      | TE         | BAL       | veteran  |         16.2 |         126.0 |         82.5 |        169.6 |
| COLSTON LOVELAND  | TE         | CHI       | veteran  |         16.2 |         125.3 |         73.7 |        176.8 |

## 5. Face validity — top 15 ROOKIES (P1A-attached)

| player_name      | position   |   draft_overall |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|----------------:|-------------:|--------------:|-------------:|-------------:|
| Fernando Mendoza | QB         |             1.0 |         12.4 |         268.3 |          5.6 |        531.1 |
| Jeremiyah Love   | RB         |             3.0 |         16.0 |         208.4 |          0.0 |        443.2 |
| Jordyn Tyson     | WR         |             8.0 |         13.6 |         191.8 |          0.0 |        401.0 |
| Carnell Tate     | WR         |             4.0 |         13.6 |         172.9 |          0.0 |        361.4 |
| Kenyon Sadiq     | TE         |            16.0 |         15.3 |         139.5 |          0.0 |        288.6 |
| Makai Lemon      | WR         |            20.0 |         14.1 |         100.4 |          0.0 |        209.8 |
| Jadarian Price   | RB         |            32.0 |         13.8 |          89.1 |          0.0 |        189.4 |
| KC Concepcion    | WR         |            24.0 |         14.1 |          74.4 |          0.0 |        155.5 |
| Omar Cooper Jr.  | WR         |            30.0 |         14.1 |          62.9 |          0.0 |        131.5 |
| Denzel Boston    | WR         |            39.0 |         14.1 |          62.2 |          0.0 |        130.0 |
| Ty Simpson       | QB         |            13.0 |         12.4 |          58.9 |          1.2 |        116.5 |
| Eli Stowers      | TE         |            54.0 |         13.9 |          51.7 |          0.0 |        106.9 |
| Germie Bernard   | WR         |            47.0 |         14.1 |          50.6 |          0.0 |        105.7 |
| Antonio Williams | WR         |            71.0 |         14.1 |          43.0 |          0.0 |         89.8 |
| Max Klare        | TE         |            61.0 |         13.9 |          41.6 |          0.0 |         86.1 |

## 6. Limitations

- **First-pass MVP** — the full NF1 model (posterior-predictive, weekly, §0.5 bake-off) refines this. The gate here is face-validity + coverage, not a selected model.
- **Expected-games is a role heuristic, not a depth-chart oracle** — offseason moves (trades, signings, camp battles, holdouts) are not yet ingested; a base-season backup who wins a 2026 job is under-projected until depth charts refresh. Surfaced via the wide games interval.
- **Rookie uncertainty is PARAMETER uncertainty** (slot curve + P1A `sd`), not a calibrated predictive interval — NF-C1/pricing must recalibrate (the E13.6 pattern).
- **Rookie team = NULL** (2026 draftees are not in the base-season role dimension) — kept NULL, not guessed.
- **Two-point conversions kept NULL** (rare/idiosyncratic); fumbles-lost is a modest per-touch estimate. Both are small scoring nuisance terms.

