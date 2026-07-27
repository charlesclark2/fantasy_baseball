# NF-FASTPATH — 2026 NFL fantasy season projections (raw stat-line, MVP-1)

**Model:** `nfl_fantasy_fastpath_v1` · **base season:** 2025 → **projects:** 2026 · **generated:** 2026-07-27T08:54:57.868320+00:00

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + P1A) and must be recalibrated before pricing.

## 1. The projection method (honest framing)

- **Veterans** — a **3-year recency+games-weighted** per-game line (weight = 0.6^age × games, so a career year or a down/injured year regresses toward the player's own baseline — the fix for single-season recency bias, esp. the spiky rushing-TD stat that ranked Trevor Lawrence QB2 off a fluke 9-rush-TD 2025), shrunk toward a conservative positional prior (position median) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve `per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` (Malik Willis was its #1).
- **Usage-share role signal (NF-D2 slice 1)** — expected games is further refined by the base-season USAGE share (snap share for RB/WR, target share for TE; QB untouched), the volume-earner-vs-depth-body separator. Ablated for held-out within-position ρ lift over the MVP-1 baseline (RB +0.009 / WR +0.009 / TE +0.007 / QB +0.000, 2019–2025) — see `ablation_results/nf_d2_snap_role_ablation.md`. Leakage-safe (a realized base-season quantity) and non-double-counting (it moves only playing-time, not the per-game production line).
- **Team-change / depth-jump opportunity (NF-D2 slice 3)** — for a player who CHANGES teams (base-season team ≠ projection-season team) at RB/WR/TE, the per-game line is rescaled toward the NEW role's volume level (a stale old-team line understates a role UPGRADE, overstates a player buried on a new depth chart). Ablated held-out lift over slice-1: RB +0.008 / WR +0.006 / TE +0.007 / QB +0.000, with the MOVER subpopulation +~0.03 — see `ablation_results/nf_d2_team_context_ablation.md`. Leakage-safe (the forward team + role are read from the freshest preseason depth-chart snapshot). Fires only where the depth feed has captured the move, so re-run as the offseason depth charts refresh through camp.
- **Vegas team environment — QB (NF-D2 slice 4)** — a QB's projection is tilted (≤±10%) by the projection-season team's WEEK-1 implied points, a LEAKAGE-SAFE forward read on the offense (a Week-1 line is set before any of the season's games). Ablated held-out QB ρ lift +0.012 (2020–2025) — see `ablation_results/nf_d2_team_context_ablation.md`. QB-scoped (RB/WR/TE carry team context via their own usage line). A richer forward-Vegas signal (preseason win totals) would grow this toward its +0.06 leaky ceiling.
- **Injury / availability (NF-D2 slice 5)** — a player flagged unavailable in the projection-season roster (reserve/IR, PUP, NFI, suspension) has expected games CAPPED toward the empirical status level (RES→3.7 g, PUP→2.4 vs ACT→13.2), so a shelved player is not ranked as startable. Leakage-safe (a preseason designation). The measured ρ lift is small (the eval excludes players with <6 realized games — the very ones this fixes) — it is a CORRECTNESS fix. ⚠️ The nflverse injury REPORT is in-season only and 2026 is unpublished; the roster PUP/IR flag is the forward source and populates through camp, so re-run as designations land (a live injury-news feed would surface offseason-surgery cases earlier).
- **ADP market consensus (NF-D2 #6 / NF-D3) — tested; ships OFF, kept as the BENCHMARK.** Preseason ADP (Fantasy Football Calculator real-draft consensus, leakage-safe) is the strongest single forward ordering signal, but it is the MARKET's output, not orthogonal information. Ablated 2019–2024, a clean POSITION SPLIT emerged: at QB/RB the market OUT-ORDERS the box-score model (covered-tier ρ QB 0.48 vs 0.33, RB 0.62 vs 0.52) and the model's fades are noise; at WR/TE the model TIES/BEATS ADP and — crucially — where model and ADP most disagree the MODEL predicts the realized finish better (overall 0.51 vs 0.28). A blanket blend is net-negative on the board and would erase that disagreement edge, so this NON-MARKET projection stays independent (`_ADP_PRIOR_BLEND=0.0`). ADP is delivered as the NF-D3 benchmark asset (`run_adp_ingest.py` → `nfl/fantasy/benchmarks/`) + an optional evidence-backed QB/RB-scoped prior (`blend_adp_prior`). See `ablation_results/nf_d2_adp_ablation.md`.
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
| JOSH ALLEN          | QB         | BUF       | veteran  |         16.5 |         325.7 |        232.2 |        419.2 |
| JALEN HURTS         | QB         | PHI       | veteran  |         16.5 |         318.2 |        239.7 |        396.6 |
| JARED GOFF          | QB         | DET       | veteran  |         16.5 |         311.4 |        237.3 |        385.5 |
| LAMAR JACKSON       | QB         | BAL       | veteran  |         14.5 |         296.9 |        215.5 |        378.2 |
| DAK PRESCOTT        | QB         | DAL       | veteran  |         16.5 |         293.4 |        220.1 |        366.7 |
| JUSTIN HERBERT      | QB         | LAC       | veteran  |         16.5 |         290.6 |        216.6 |        364.6 |
| MATTHEW STAFFORD    | QB         | LAR       | veteran  |         16.5 |         284.8 |        207.6 |        362.0 |
| TREVOR LAWRENCE     | QB         | JAX       | veteran  |         16.5 |         282.5 |        206.2 |        358.8 |
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         15.5 |         279.9 |        198.2 |        361.7 |
| BAKER MAYFIELD      | QB         | TB        | veteran  |         16.5 |         279.2 |        214.1 |        344.3 |
| PATRICK MAHOMES     | QB         | KC        | veteran  |         15.0 |         271.2 |        199.0 |        343.3 |
| Fernando Mendoza    | QB         | nan       | rookie   |         12.4 |         268.3 |         26.5 |        277.0 |
| CALEB WILLIAMS      | QB         | CHI       | veteran  |         16.5 |         266.4 |        192.5 |        340.4 |
| BO NIX              | QB         | DEN       | veteran  |         16.5 |         265.4 |        193.7 |        337.2 |
| DRAKE MAYE          | QB         | NE        | veteran  |         16.5 |         261.5 |        188.7 |        334.3 |
| JA'MARR CHASE       | WR         | CIN       | veteran  |         15.8 |         261.4 |        185.4 |        337.3 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         15.2 |         251.3 |        176.0 |        326.6 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         15.4 |         247.8 |        165.4 |        330.3 |
| AMON-RA ST. BROWN   | WR         | DET       | veteran  |         15.8 |         247.6 |        171.3 |        324.0 |
| JORDAN LOVE         | QB         | GB        | veteran  |         16.0 |         245.1 |        179.1 |        311.1 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.4 |         243.0 |        156.5 |        329.6 |
| JAXSON DART         | QB         | NYG       | veteran  |         15.0 |         242.5 |        168.5 |        316.5 |
| PUKA NACUA          | WR         | LAR       | veteran  |         15.1 |         239.1 |        156.3 |        321.8 |
| AARON RODGERS       | QB         | PIT       | veteran  |         16.5 |         228.2 |        169.7 |        286.8 |
| JOE BURROW          | QB         | CIN       | veteran  |         12.0 |         227.4 |        153.6 |        301.1 |

### Top 12 QB

| player_name      | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| JOSH ALLEN       | QB         | BUF       | veteran  |         16.5 |         325.7 |        232.2 |        419.2 |
| JALEN HURTS      | QB         | PHI       | veteran  |         16.5 |         318.2 |        239.7 |        396.6 |
| JARED GOFF       | QB         | DET       | veteran  |         16.5 |         311.4 |        237.3 |        385.5 |
| LAMAR JACKSON    | QB         | BAL       | veteran  |         14.5 |         296.9 |        215.5 |        378.2 |
| DAK PRESCOTT     | QB         | DAL       | veteran  |         16.5 |         293.4 |        220.1 |        366.7 |
| JUSTIN HERBERT   | QB         | LAC       | veteran  |         16.5 |         290.6 |        216.6 |        364.6 |
| MATTHEW STAFFORD | QB         | LAR       | veteran  |         16.5 |         284.8 |        207.6 |        362.0 |
| TREVOR LAWRENCE  | QB         | JAX       | veteran  |         16.5 |         282.5 |        206.2 |        358.8 |
| BAKER MAYFIELD   | QB         | TB        | veteran  |         16.5 |         279.2 |        214.1 |        344.3 |
| PATRICK MAHOMES  | QB         | KC        | veteran  |         15.0 |         271.2 |        199.0 |        343.3 |
| Fernando Mendoza | QB         | nan       | rookie   |         12.4 |         268.3 |         26.5 |        277.0 |
| CALEB WILLIAMS   | QB         | CHI       | veteran  |         16.5 |         266.4 |        192.5 |        340.4 |

### Top 12 RB

| player_name         | position   | team_id   | source   |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:--------------------|:-----------|:----------|:---------|-------------:|--------------:|-------------:|-------------:|
| CHRISTIAN MCCAFFREY | RB         | SF        | veteran  |         15.5 |         279.9 |        198.2 |        361.7 |
| BIJAN ROBINSON      | RB         | ATL       | veteran  |         15.2 |         251.3 |        176.0 |        326.6 |
| JONATHAN TAYLOR     | RB         | IND       | veteran  |         15.4 |         247.8 |        165.4 |        330.3 |
| JAHMYR GIBBS        | RB         | DET       | veteran  |         14.4 |         243.0 |        156.5 |        329.6 |
| DE'VON ACHANE       | RB         | MIA       | veteran  |         14.4 |         221.5 |        159.8 |        283.1 |
| Jeremiyah Love      | RB         | nan       | rookie   |         16.0 |         208.4 |         10.4 |        244.6 |
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
| Jordyn Tyson       | WR         | nan       | rookie   |         13.6 |         191.8 |         28.9 |        216.3 |
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
| HAROLD FANNIN JR. | TE         | CLE       | veteran  |         16.2 |         154.8 |        111.4 |        198.2 |
| TYLER WARREN      | TE         | IND       | veteran  |         16.6 |         150.5 |        111.0 |        190.1 |
| DALLAS GOEDERT    | TE         | PHI       | veteran  |         16.1 |         141.4 |         92.7 |        190.2 |
| Kenyon Sadiq      | TE         | nan       | rookie   |         15.3 |         139.5 |          5.3 |        175.1 |
| KYLE PITTS SR.    | TE         | ATL       | veteran  |         16.4 |         137.4 |         78.8 |        196.0 |
| JAKE FERGUSON     | TE         | DAL       | veteran  |         15.8 |         130.5 |         85.1 |        175.9 |
| MARK ANDREWS      | TE         | BAL       | veteran  |         15.8 |         122.4 |         79.2 |        165.5 |
| COLSTON LOVELAND  | TE         | CHI       | veteran  |         15.4 |         118.6 |         68.1 |        169.1 |
| JUWAN JOHNSON     | TE         | NO        | veteran  |         15.5 |         118.4 |         83.2 |        153.7 |

## 5. Face validity — top 15 ROOKIES (P1A-attached)

**NF1.4 rookie over-placement gate** (advisory — a genuinely exceptional class may trip it): the #1 overall slot must be a veteran, no rookie inside the overall top 10, and no rookie projected above the Q90 of realized rookie seasons at his position over the FULL drafted population.

```json
{
  "pass": false,
  "n_rookies": 74,
  "placement": {
    "top1_is_rookie": false,
    "n_rookies_in_top10": 0,
    "best_rookie_overall_rank": 12,
    "best_rookie": "Fernando Mendoza"
  },
  "level": {
    "historical_caps": {
      "QB": 214.2,
      "RB": 189.8,
      "TE": 106.7,
      "WR": 179.2
    },
    "positions_over_cap": [
      {
        "position": "QB",
        "max_projected": 268.3,
        "historical_cap": 214.2
      },
      {
        "position": "RB",
        "max_projected": 208.4,
        "historical_cap": 189.8
      },
      {
        "position": "TE",
        "max_projected": 139.5,
        "historical_cap": 106.7
      },
      {
        "position": "WR",
        "max_projected": 191.8,
        "historical_cap": 179.2
      }
    ]
  }
}
```

| player_name      | position   |   draft_overall |   proj_games |   proj_fp_ppr |   fp_ppr_p10 |   fp_ppr_p90 |
|:-----------------|:-----------|----------------:|-------------:|--------------:|-------------:|-------------:|
| Fernando Mendoza | QB         |             1.0 |         12.4 |         268.3 |         26.5 |        277.0 |
| Jeremiyah Love   | RB         |             3.0 |         16.0 |         208.4 |         10.4 |        244.6 |
| Jordyn Tyson     | WR         |             8.0 |         13.6 |         191.8 |         28.9 |        216.3 |
| Carnell Tate     | WR         |             4.0 |         13.6 |         172.9 |         28.9 |        216.3 |
| Kenyon Sadiq     | TE         |            16.0 |         15.3 |         139.5 |          5.3 |        175.1 |
| Makai Lemon      | WR         |            20.0 |         14.1 |         100.4 |         28.9 |        216.3 |
| Jadarian Price   | RB         |            32.0 |         13.8 |          89.1 |         10.4 |        244.6 |
| KC Concepcion    | WR         |            24.0 |         14.1 |          74.4 |         28.9 |        216.3 |
| Omar Cooper Jr.  | WR         |            30.0 |         14.1 |          62.9 |         28.9 |        216.3 |
| Denzel Boston    | WR         |            39.0 |         14.1 |          62.2 |         28.9 |        216.3 |
| Ty Simpson       | QB         |            13.0 |         12.4 |          58.9 |         26.5 |        277.0 |
| Eli Stowers      | TE         |            54.0 |         13.9 |          51.7 |          5.3 |        175.1 |
| Germie Bernard   | WR         |            47.0 |         14.1 |          50.6 |         28.9 |        216.3 |
| Antonio Williams | WR         |            71.0 |         14.1 |          43.0 |         28.9 |        216.3 |
| Max Klare        | TE         |            61.0 |         13.9 |          41.6 |          5.3 |        175.1 |

## 6. Limitations

- **First-pass MVP** — the full NF1 model (posterior-predictive, weekly, §0.5 bake-off) refines this. The gate here is face-validity + coverage, not a selected model.
- **Expected-games is a role heuristic, not a depth-chart oracle** — offseason moves (trades, signings, camp battles, holdouts) are not yet ingested; a base-season backup who wins a 2026 job is under-projected until depth charts refresh. Surfaced via the wide games interval.
- **Rookie uncertainty is PARAMETER uncertainty** (slot curve + P1A `sd`), not a calibrated predictive interval — NF-C1/pricing must recalibrate (the E13.6 pattern).
- **Rookie team = NULL** (2026 draftees are not in the base-season role dimension) — kept NULL, not guessed.
- **Two-point conversions kept NULL** (rare/idiosyncratic); fumbles-lost is a modest per-touch estimate. Both are small scoring nuisance terms.

