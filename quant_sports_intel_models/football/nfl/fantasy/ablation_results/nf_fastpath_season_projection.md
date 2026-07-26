# NF-FASTPATH — 2026 NFL fantasy season projections (raw stat-line, MVP-1)

**Model:** `nfl_fantasy_fastpath_v1` · **base season:** 2025 → **projects:** 2026 · **generated:** 2026-07-26T06:05:58.480268+00:00

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + P1A) and must be recalibrated before pricing.

## 1. The projection method (honest framing)

- **Veterans** — a **3-year recency+games-weighted** per-game line (weight = 0.6^age × games, so a career year or a down/injured year regresses toward the player's own baseline — the fix for single-season recency bias, esp. the spiky rushing-TD stat that ranked Trevor Lawrence QB2 off a fluke 9-rush-TD 2025), shrunk toward a conservative positional prior (position median) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve `per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` (Malik Willis was its #1).
- **Usage-share role signal (NF-D2 slice 1)** — expected games is further refined by the base-season USAGE share (snap share for RB/WR, target share for TE; QB untouched), the volume-earner-vs-depth-body separator. Ablated for held-out within-position ρ lift over the MVP-1 baseline (RB +0.009 / WR +0.009 / TE +0.007 / QB +0.000, 2019–2025) — see `ablation_results/nf_d2_snap_role_ablation.md`. Leakage-safe (a realized base-season quantity) and non-double-counting (it moves only playing-time, not the per-game production line).
- **Team-change / depth-jump opportunity (NF-D2 slice 3)** — for a player who CHANGES teams (base-season team ≠ projection-season team) at RB/WR/TE, the per-game line is rescaled toward the NEW role's volume level (a stale old-team line understates a role UPGRADE, overstates a player buried on a new depth chart). Ablated held-out lift over slice-1: RB +0.008 / WR +0.006 / TE +0.007 / QB +0.000, with the MOVER subpopulation +~0.03 — see `ablation_results/nf_d2_team_context_ablation.md`. Leakage-safe (the forward team + role are read from the freshest preseason depth-chart snapshot). Fires only where the depth feed has captured the move, so re-run as the offseason depth charts refresh through camp.
- **Vegas team environment — QB (NF-D2 slice 4)** — a QB's projection is tilted (≤±10%) by the projection-season team's WEEK-1 implied points, a LEAKAGE-SAFE forward read on the offense (a Week-1 line is set before any of the season's games). Ablated held-out QB ρ lift +0.012 (2020–2025) — see `ablation_results/nf_d2_team_context_ablation.md`. QB-scoped (RB/WR/TE carry team context via their own usage line). A richer forward-Vegas signal (preseason win totals) would grow this toward its +0.06 leaky ceiling.
- **Rookies (QB/RB/WR/TE)** — a historical draft-slot → rookie-year production curve (power-law per position, fit on prior classes) nudged by the **NCAAF-P1A residual** (`projected_nfl_z` vs the slot-expected z — talent the draft board disagreed with), with deliberately wide intervals. Defensive/OL rookies carry no fantasy line and are excluded (≈0, per P1A).

## 2. Coverage report

```json
{
  "n_total": 716,
  "n_veterans": 642,
  "n_rookies": 74,
  "by_position": {
    "FB": 16,
    "QB": 90,
    "RB": 163,
    "TE": 162,
    "WR": 285
  },
  "n_rookies_by_pos": {
    "FB": 1,
    "QB": 9,
    "RB": 11,
    "TE": 20,
    "WR": 33
  },
  "n_base_relevant_players_ge4g": 592,
  "n_relevant_gap": 40,
  "pct_relevant_covered": 93.2
}
```

## 3. Multi-season backtest — this model vs realized outcomes

Each PRIOR season below was projected with the SAME model (base = season−1, 3-yr regression) and scored against what actually happened — the FULL projection (veterans + rookies), over players who played ≥6 games. `spearman_all` (rank) is the headline; `sp_<POS>` is within-position rank correlation (what matters for drafting); `topN_hit` = of the realized top-24, how many the model ranked top-24. A signal check across seasons, not a calibration claim.


## 4. Face validity — top 25 overall (projected PPR)

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JALEN HURTS         | QB         | PHI       | veteran  |         16.5 |         318.6 |        240.1 |        397.1 |
| JOSH ALLEN          | QB         | BUF       | veteran  |         16.5 |         316.0 |        223.9 |        408.2 |
| JARED GOFF          | QB         | DET       | veteran  |         16.5 |         312.4 |        238.2 |        386.7 |
| DAK PRESCOTT        | QB         | DAL       | veteran  |         16.5 |         295.8 |        222.1 |        369.4 |
| JUSTIN HERBERT      | QB         | LAC       | veteran  |         16.5 |         294.2 |        219.6 |        368.8 |
| LAMAR JACKSON       | QB         | BAL       | veteran  |         14.5 |         293.8 |        213.1 |        374.6 |
| TREVOR LAWRENCE     | QB         | JAX       | veteran  |         16.5 |         286.7 |        209.8 |        363.6 |
| BAKER MAYFIELD      | QB         | TB        | veteran  |         16.5 |         284.9 |        218.8 |        350.9 |
| MATTHEW STAFFORD    | QB         | LAR       | veteran  |         16.5 |         280.3 |        203.8 |        356.9 |
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         15.5 |         279.9 |        198.2 |        361.7 |
| Fernando Mendoza    | QB         | nan       | rookie   |         12.4 |         268.3 |          5.6 |        531.1 |
| CALEB WILLIAMS      | QB         | CHI       | veteran  |         16.5 |         264.3 |        190.6 |        337.9 |
| PATRICK MAHOMES     | QB         | KC        | veteran  |         15.0 |         262.2 |        191.8 |        332.7 |
| JA'MARR CHASE       | WR         | CIN       | veteran  |         15.8 |         261.4 |        185.4 |        337.3 |
| BO NIX              | QB         | DEN       | veteran  |         16.5 |         253.1 |        183.2 |        323.0 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         15.2 |         251.3 |        176.0 |        326.6 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         15.4 |         247.8 |        165.4 |        330.3 |
| AMON-RA ST. BROWN   | WR         | DET       | veteran  |         15.8 |         247.6 |        171.3 |        324.0 |
| DRAKE MAYE          | QB         | NE        | veteran  |         16.5 |         247.1 |        176.4 |        317.8 |
| JAXSON DART         | QB         | NYG       | veteran  |         15.0 |         246.4 |        171.7 |        321.0 |
| JORDAN LOVE         | QB         | GB        | veteran  |         16.0 |         243.2 |        177.5 |        308.8 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.4 |         243.0 |        156.5 |        329.6 |
| PUKA NACUA          | WR         | LAR       | veteran  |         15.1 |         239.1 |        156.3 |        321.8 |
| JOE BURROW          | QB         | CIN       | veteran  |         12.0 |         229.0 |        154.8 |        303.1 |
| AARON RODGERS       | QB         | PIT       | veteran  |         16.5 |         227.4 |        168.9 |        285.8 |

### Top 12 QB

| player_name      | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JALEN HURTS      | QB         | PHI       | veteran  |         16.5 |         318.6 |        240.1 |        397.1 |
| JOSH ALLEN       | QB         | BUF       | veteran  |         16.5 |         316.0 |        223.9 |        408.2 |
| JARED GOFF       | QB         | DET       | veteran  |         16.5 |         312.4 |        238.2 |        386.7 |
| DAK PRESCOTT     | QB         | DAL       | veteran  |         16.5 |         295.8 |        222.1 |        369.4 |
| JUSTIN HERBERT   | QB         | LAC       | veteran  |         16.5 |         294.2 |        219.6 |        368.8 |
| LAMAR JACKSON    | QB         | BAL       | veteran  |         14.5 |         293.8 |        213.1 |        374.6 |
| TREVOR LAWRENCE  | QB         | JAX       | veteran  |         16.5 |         286.7 |        209.8 |        363.6 |
| BAKER MAYFIELD   | QB         | TB        | veteran  |         16.5 |         284.9 |        218.8 |        350.9 |
| MATTHEW STAFFORD | QB         | LAR       | veteran  |         16.5 |         280.3 |        203.8 |        356.9 |
| Fernando Mendoza | QB         | nan       | rookie   |         12.4 |         268.3 |          5.6 |        531.1 |
| CALEB WILLIAMS   | QB         | CHI       | veteran  |         16.5 |         264.3 |        190.6 |        337.9 |
| PATRICK MAHOMES  | QB         | KC        | veteran  |         15.0 |         262.2 |        191.8 |        332.7 |

### Top 12 RB

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         15.5 |         279.9 |        198.2 |        361.7 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         15.2 |         251.3 |        176.0 |        326.6 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         15.4 |         247.8 |        165.4 |        330.3 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.4 |         243.0 |        156.5 |        329.6 |
| DE'VON ACHANE       | RB         | MIA       | veteran  |         14.4 |         221.5 |        159.8 |        283.1 |
| Jeremiyah Love      | RB         | nan       | rookie   |         16.0 |         208.4 |          0.0 |        443.2 |
| SAQUON BARKLEY      | RB         | PHI       | veteran  |         15.3 |         207.8 |        147.9 |        267.6 |
| DERRICK HENRY       | RB         | BAL       | veteran  |         14.0 |         199.6 |        132.1 |        267.0 |
| KYREN WILLIAMS      | RB         | LAR       | veteran  |         15.1 |         199.5 |        140.2 |        258.8 |
| ASHTON JEANTY       | RB         | LV        | veteran  |         15.3 |         188.1 |        128.3 |        247.8 |
| JAMES COOK III      | RB         | BUF       | veteran  |         14.0 |         185.4 |        119.0 |        251.7 |
| JOSH JACOBS         | RB         | GB        | veteran  |         14.2 |         182.9 |        119.9 |        246.0 |

### Top 12 WR

| player_name        | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JA'MARR CHASE      | WR         | CIN       | veteran  |         15.8 |         261.4 |        185.4 |        337.3 |
| AMON-RA ST. BROWN  | WR         | DET       | veteran  |         15.8 |         247.6 |        171.3 |        324.0 |
| PUKA NACUA         | WR         | LAR       | veteran  |         15.1 |         239.1 |        156.3 |        321.8 |
| JAXON SMITH-NJIGBA | WR         | SEA       | veteran  |         15.3 |         203.7 |        135.4 |        272.0 |
| JUSTIN JEFFERSON   | WR         | MIN       | veteran  |         16.2 |         200.3 |        149.3 |        251.3 |
| CEEDEE LAMB        | WR         | DAL       | veteran  |         14.4 |         197.3 |        140.1 |        254.5 |
| A.J. BROWN         | WR         | NE        | veteran  |         15.7 |         194.8 |        128.9 |        260.8 |
| Jordyn Tyson       | WR         | nan       | rookie   |         13.6 |         191.8 |          0.0 |        401.0 |
| CHRIS OLAVE        | WR         | NO        | veteran  |         15.0 |         186.2 |        129.2 |        243.2 |
| NICO COLLINS       | WR         | HOU       | veteran  |         14.7 |         183.4 |        128.5 |        238.4 |
| ZAY FLOWERS        | WR         | BAL       | veteran  |         15.6 |         178.4 |        124.7 |        232.2 |
| DRAKE LONDON       | WR         | ATL       | veteran  |         14.4 |         175.1 |        106.2 |        244.0 |

### Top 12 TE

| player_name       | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| TREY MCBRIDE      | TE         | ARI       | veteran  |         16.6 |         214.6 |        153.2 |        276.0 |
| BROCK BOWERS      | TE         | LV        | veteran  |         15.1 |         169.1 |        106.4 |        231.9 |
| TRAVIS KELCE      | TE         | KC        | veteran  |         16.6 |         162.5 |        115.8 |        209.3 |
| GEORGE KITTLE     | TE         | SF        | veteran  |         15.1 |         160.1 |        103.3 |        217.0 |
| HAROLD FANNIN JR. | TE         | CLE       | veteran  |         16.2 |         154.8 |        111.4 |        198.2 |
| TYLER WARREN      | TE         | IND       | veteran  |         16.6 |         150.5 |        111.0 |        190.1 |
| DALLAS GOEDERT    | TE         | PHI       | veteran  |         16.1 |         141.4 |         92.7 |        190.2 |
| Kenyon Sadiq      | TE         | nan       | rookie   |         15.3 |         139.5 |          0.0 |        288.6 |
| KYLE PITTS SR.    | TE         | ATL       | veteran  |         16.4 |         137.4 |         78.8 |        196.0 |
| JAKE FERGUSON     | TE         | DAL       | veteran  |         15.8 |         130.5 |         85.1 |        175.9 |
| MARK ANDREWS      | TE         | BAL       | veteran  |         15.8 |         122.4 |         79.2 |        165.5 |
| COLSTON LOVELAND  | TE         | CHI       | veteran  |         15.4 |         118.6 |         68.1 |        169.1 |

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

