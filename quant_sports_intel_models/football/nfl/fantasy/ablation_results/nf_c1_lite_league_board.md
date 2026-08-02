# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-08-02T03:48:56.432702+00:00

> 🧮 **Sections 1–3 below are shown at the 12-team reference size** (the modal redraft size); the boards are landed for every scored size — see §4 for the league-size effect. The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not part of the format name.

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is (1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie intervals remain PARAMETER uncertainty and must be recalibrated before pricing.

## 1. Face validity — the preset deltas that prove the scarcity math

| preset    | best_QB    |   best_QB_overall_rank |   WR+TE_in_top10 |   RB_in_top10 |
|:----------|:-----------|-----------------------:|-----------------:|--------------:|
| standard  | JOSH ALLEN |                     13 |                1 |             9 |
| half_ppr  | JOSH ALLEN |                     15 |                4 |             6 |
| full_ppr  | JOSH ALLEN |                     19 |                4 |             6 |
| superflex | JOSH ALLEN |                      2 |                3 |             4 |

- ✅ **Superflex lifts QBs:** the best QB's overall rank should jump sharply from full-PPR to superflex (a QB-eligible SUPERFLEX slot roughly doubles QB starter demand → QB replacement drops → QB VOR rises). This is the direct check the flex-allocation math is right.
- ✅ **PPR lifts pass-catchers:** WR/TE representation in the top 10 should rise from standard → half → full PPR as receptions gain value.

## 2. Positional scarcity — the replacement-level definition (auditable)

Replacement level per position = the points of the FIRST non-startable player (the best player available for free). DEMAND = dedicated starter spots + the position's allocated share of the FLEX/SUPERFLEX pool (allocated greedily, most-restrictive slot first). VOR = league points − this replacement level.

### standard

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                265.4 |
| RB         |                   24 |                8 |              32 |                 94.3 |
| TE         |                   12 |                0 |              12 |                 71.5 |
| WR         |                   24 |                4 |              28 |                 94.4 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                265.4 |
| RB         |                   24 |                1 |              25 |                129.9 |
| TE         |                   12 |                0 |              12 |                117.0 |
| WR         |                   24 |               11 |              35 |                131.0 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |               12 |              24 |                191.8 |
| RB         |                   24 |                1 |              25 |                129.9 |
| TE         |                   12 |                0 |              12 |                117.0 |
| WR         |                   24 |               11 |              35 |                131.0 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | BIJAN ROBINSON      | RB         |                 1 |         15.2 |           222.4 |                 94.3 | 128.1 |     -12.0 |     181.7 |
|              2 | JONATHAN TAYLOR     | RB         |                 2 |         15.4 |           213.9 |                 94.3 | 119.6 |      -3.1 |     211.5 |
|              3 | JAHMYR GIBBS        | RB         |                 3 |         14.4 |           200.7 |                 94.3 | 106.4 |     -10.4 |     187.1 |
|              4 | CHRISTIAN MCCAFFREY | RB         |                 4 |         15.5 |           193.5 |                 94.3 |  99.3 |     -16.5 |     172.1 |
|              5 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           173.5 |                 94.3 |  79.3 |     -16.0 |     166.8 |
|              6 | JAMES COOK III      | RB         |                 6 |         14.0 |           173.5 |                 94.3 |  79.2 |      -6.7 |     192.1 |
|              7 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           165.6 |                 94.4 |  71.3 |     -31.2 |     121.9 |
|              8 | Jeremiyah Love      | RB         |                 7 |         16.0 |           164.6 |                 94.3 |  70.3 |     -68.7 |     202.3 |
|              9 | DERRICK HENRY       | RB         |                 8 |         14.0 |           162.7 |                 94.3 |  68.4 |     -40.0 |     186.7 |
|             10 | ASHTON JEANTY       | RB         |                 9 |         15.3 |           161.4 |                 94.3 |  67.2 |     -16.0 |     166.3 |
|             11 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           161.1 |                 94.3 |  66.8 |     -24.1 |     187.6 |
|             12 | PUKA NACUA          | WR         |                 2 |         15.1 |           159.7 |                 94.4 |  65.3 |     -30.1 |     125.7 |
|             13 | JOSH ALLEN          | QB         |                 1 |         16.5 |           325.7 |                265.4 |  60.3 |    -134.7 |     181.6 |
|             14 | CHASE BROWN         | RB         |                11 |         14.2 |           152.9 |                 94.3 |  58.6 |     -17.1 |     158.0 |
|             15 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           152.2 |                 94.4 |  57.9 |     -29.3 |     123.6 |
|             16 | KYREN WILLIAMS      | RB         |                12 |         15.1 |           150.8 |                 94.3 |  56.6 |     -38.8 |     170.0 |
|             17 | KENNETH WALKER III  | RB         |                13 |         13.9 |           148.4 |                 94.3 |  54.1 |     -34.2 |     174.7 |
|             18 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           318.2 |                265.4 |  52.7 |    -131.4 |     183.7 |
|             19 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           123.9 |                 71.5 |  52.4 |     -32.8 |      63.4 |
|             20 | OMARION HAMPTON     | RB         |                14 |         12.1 |           142.4 |                 94.3 |  48.2 |     -36.6 |     161.6 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | BIJAN ROBINSON      | RB         |                 1 |         15.2 |           279.9 |                129.9 | 150.0 |     -26.2 |     217.5 |
|              2 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           261.4 |                131.0 | 130.3 |     -31.2 |     210.3 |
|              3 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           251.3 |                129.9 | 121.4 |     -28.8 |     215.9 |
|              4 | JAHMYR GIBBS        | RB         |                 3 |         14.4 |           247.8 |                129.9 | 117.9 |     -26.2 |     217.5 |
|              5 | PUKA NACUA          | WR         |                 2 |         15.1 |           247.6 |                131.0 | 116.6 |     -31.2 |     210.3 |
|              6 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           243.0 |                129.9 | 113.1 |     -26.2 |     217.5 |
|              7 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           239.1 |                131.0 | 108.0 |     -28.7 |     211.2 |
|              8 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           214.6 |                117.0 |  97.6 |     -49.9 |     116.6 |
|              9 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           221.5 |                129.9 |  91.5 |     -29.9 |     203.2 |
|             10 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.4 |                129.9 |  78.5 |     -97.4 |     245.7 |
|             11 | ASHTON JEANTY       | RB         |                 7 |         15.3 |           207.8 |                129.9 |  77.8 |     -29.1 |     205.4 |
|             12 | JAXON SMITH-NJIGBA  | WR         |                 4 |         15.3 |           203.7 |                131.0 |  72.7 |     -31.5 |     197.8 |
|             13 | JAMES COOK III      | RB         |                 8 |         14.0 |           199.5 |                129.9 |  69.6 |     -29.1 |     199.4 |
|             14 | CHASE BROWN         | RB         |                 9 |         14.2 |           199.5 |                129.9 |  69.6 |     -29.1 |     199.4 |
|             15 | CEEDEE LAMB         | WR         |                 5 |         14.4 |           200.3 |                131.0 |  69.3 |     -31.8 |     195.2 |
|             16 | DRAKE LONDON        | WR         |                 6 |         14.4 |           197.3 |                131.0 |  66.3 |     -31.5 |     193.9 |
|             17 | JUSTIN JEFFERSON    | WR         |                 7 |         16.2 |           194.8 |                131.0 |  63.8 |     -28.6 |     194.0 |
|             18 | Jordyn Tyson        | WR         |                 8 |         13.6 |           191.4 |                131.0 |  60.4 |    -112.5 |     199.9 |
|             19 | JOSH ALLEN          | QB         |                 1 |         16.5 |           325.7 |                265.4 |  60.3 |    -134.7 |     181.6 |
|             20 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           188.1 |                129.9 |  58.1 |     -47.9 |     199.2 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | BIJAN ROBINSON      | RB         |                 1 |         15.2 |           279.9 |                129.9 | 150.0 |     -26.2 |     217.5 |
|              2 | JOSH ALLEN          | QB         |                 1 |         16.5 |           325.7 |                191.8 | 133.9 |     -61.1 |     255.2 |
|              3 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           261.4 |                131.0 | 130.3 |     -31.2 |     210.3 |
|              4 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           318.2 |                191.8 | 126.4 |     -57.8 |     257.3 |
|              5 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           251.3 |                129.9 | 121.4 |     -28.8 |     215.9 |
|              6 | DRAKE MAYE          | QB         |                 3 |         16.5 |           311.4 |                191.8 | 119.6 |     -57.8 |     255.2 |
|              7 | JAHMYR GIBBS        | RB         |                 3 |         14.4 |           247.8 |                129.9 | 117.9 |     -26.2 |     217.5 |
|              8 | PUKA NACUA          | WR         |                 2 |         15.1 |           247.6 |                131.0 | 116.6 |     -31.2 |     210.3 |
|              9 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           243.0 |                129.9 | 113.1 |     -26.2 |     217.5 |
|             10 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           239.1 |                131.0 | 108.0 |     -28.7 |     211.2 |
|             11 | JOE BURROW          | QB         |                 4 |         12.0 |           296.9 |                191.8 | 105.1 |     -57.5 |     249.7 |
|             12 | JAYDEN DANIELS      | QB         |                 5 |         11.5 |           293.4 |                191.8 | 101.7 |     -45.8 |     241.4 |
|             13 | JALEN HURTS         | QB         |                 6 |         16.5 |           290.6 |                191.8 |  98.8 |     -59.0 |     241.4 |
|             14 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           214.6 |                117.0 |  97.6 |     -49.9 |     116.6 |
|             15 | CALEB WILLIAMS      | QB         |                 7 |         16.5 |           284.8 |                191.8 |  93.0 |     -62.5 |     237.8 |
|             16 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           221.5 |                129.9 |  91.5 |     -29.9 |     203.2 |
|             17 | JUSTIN HERBERT      | QB         |                 8 |         16.5 |           282.5 |                191.8 |  90.7 |     -61.4 |     237.8 |
|             18 | TREVOR LAWRENCE     | QB         |                 9 |         16.5 |           279.2 |                191.8 |  87.4 |     -64.6 |     226.2 |
|             19 | DAK PRESCOTT        | QB         |                10 |         16.5 |           271.2 |                191.8 |  79.4 |     -61.1 |     238.9 |
|             20 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.4 |                129.9 |  78.5 |     -97.4 |     245.7 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     265.4 |     129.9 |     131.0 |     117.0 |             19 |                    108 |
| full_ppr |        10 |     268.3 |     132.0 |     137.9 |     118.6 |             17 |                     90 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK instead of rendering "not projected", scored off raw components (distance-bucketed FG; DST takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). ⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE (FB folded into RB) + K/DST.
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

