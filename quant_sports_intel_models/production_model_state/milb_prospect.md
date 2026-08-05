# Production model state — Baseball MiLB / Prospect family (E7.x MLE ladder + E8.3 SB + prospect board)

_PROD-STATE-1e · written 2026-08-04 · grounded in `betting_ml/sub_model_registry.yaml`, the LIVE served artifacts (S3 reads 2026-08-04 from the laptop: board JSON, both prior parquets, all three Delta projection tables), the E7.x/E8.x ablation memos, and the serving code — NOT roadmap prose. best_alpha = 0 throughout._

> **One-line state:** this is a MODEL FAMILY, not a single model — (i) the **MiLB→MLB MLE ladder** (E7.3 batter + E7.3p pitcher translations → the E7.5/E7.5b batter and E7.5p pitcher priors, SERVING-LIVE inside `eb_batter_posteriors_raw` / `eb_starter_posteriors`), (ii) the **E8.3 stolen-base translation** (shipped to the board only), and (iii) the **prospect board** (E8.0/E8.0b/E8.1 assembly → S3 api-cache JSON, **ADMIN-ONLY, not public until 2027**). Every accuracy number is a translation/prior-calibration claim; **no edge or win-rate claim rides on any of it** (`best_alpha = 0` is stamped in the registry entries, the board build, and the served manifest's own framing block). The family's tried-ledger is the longest in the program — §10.

---

## Family map (which sub-model is which)

| sub-model | story | version (served) | status | consumed by |
|---|---|---|---|---|
| Batter MiLB→MLB MLE | E7.3 | `milb_mle_v1` → raw table now `milb_mle_v2_parkctx` (E7.12 s1) | translation map (research artifact) | E7.5 prior + board `mle*` columns |
| Pitcher MiLB→MLB MLE | E7.3p | `milb_mle_pitcher_v1` → raw table now `milb_mle_pitcher_v2_parkctx` | translation map | E7.5p prior + board pitcher columns |
| Batter rookie prior | E7.5 / E7.5b | `milb_mle_prior_v1` (**mixed provenance** — see §7) | **PROMOTED 2026-08-01, serving-live** | `eb_batter_posteriors_raw` → `avg_eb_{k_pct,bb_pct,iso}` |
| Pitcher cold-start starter prior | E7.5p | `milb_mle_pitcher_prior_v1` | **CHAMPION 2026-07-27, serving-live** | `eb_starter_posteriors` → `starter_eb_{k_pct,bb_pct}` + `eb_gb_pct` |
| Stolen-base translation | E8.3 | `sb_translation_v1` | shipped to the BOARD only (no registry entry) | board `mleSbRate` (weight 0.702 — largest batter weight) |
| Prospect board | E8.0/E8.0b/E8.1 | no model_version — identified by `generated_at` (live: 2026-08-04T01:19:18Z) | **ADMIN-ONLY served surface** | `/fantasy/mlb/prospects` (admin dogfood until 2027) |

## (1) What it predicts + market/output

- **MLE ladder (E7.3/E7.3p):** for every MiLB player, the MLB-equivalent rate line implied by his pre-debut minor-league record, per (player, level) — batter `wOBA/K%/BB%/ISO` (wOBA measured NO-signal, never wired), pitcher `K%/BB%/HR-rate/GB%/xwOBA-against` per TBF (HR-rate + xwOBA-against measured null, never wired). Each metric is a **separate translation**, with a per-metric sd.
- **Rookie priors (E7.5/E7.5b batter, E7.5p pitcher):** the MLE line recalibrated (E13.6 honest-sd) into a **priceable Bayesian prior** for cold-start players — a low-MLB-PA rookie with a MiLB record gets his own translated line as the Beta-Binomial (K%/BB%, and pitcher GB% by balls-in-play) / pseudo-count (ISO) prior instead of the generic archetype/band prior; his own MLB line shrinks toward it as PA/BF accrues (κ = equivalent PA).
- **E8.3 SB:** the MLB-equivalent **stolen-base RATE** (SB per time reaching first = singles+BB+HBP). Explicitly a rate, not a projected SB total (no playing-time projection), and explicitly **not** a success-rate read (success rate is a measured null — corr 0.23, fails deflation).
- **Prospect board:** a ranked dynasty draft board over the (FanGraphs THE BOARD ∪ MLB Pipeline) universe — consensus rank + our independent MLE-translated line + E7.13 historical comps + where they disagree. **Market/output:** an internal draft tool; the served manifest's own framing states *"This board makes no edge or win-rate claim and does not claim to beat FanGraphs. The blend is a display heuristic for ordering a draft board."*
- **What this family is NOT:** a per-game betting signal. Nothing here emits `mart_sub_model_signals` rows or a bet; the betting-path contribution is confined to cold-start feature columns in the pregame feature store (§6).

## (2) Architecture — champions + why they won

### E7.3 / E7.3p — the translation ladder (shared harness `betting_ml/scripts/milb_mle/milb_mle.py`)

- **Champion class: hierarchical partial-pooling regression** (`PartialPoolProjector`) — **won all 4 batter metrics and all 5 pitcher metrics** in the §0.5 bake-offs (memos `e7_3_milb_mle.md`, `e7_3p_milb_mle_pitchers.md`).
- **Bake-off field (8 configs per metric):** `level_mean` null + `identity_no_translation` + `archetype_prior` benchmarks (all non-selectable) · `MultiplicativeFactorProjector` (the Davenport/James factor foil, EB-shrunk `f_cell=(n·f_raw+k·f_global)/(n+k)`, k=12) · `PartialPoolProjector(prior_scale ∈ {2.0, 4.0})` · `GBMProjector((n_est,depth,lr) ∈ {(300,2,0.03),(500,3,0.02)})` with the AAA-Statcast aux channel. **The multiplicative (Davenport-factor) MLE underperformed the level-mean null on all 5 pitcher metrics** — the classic-MLE architecture is refuted on both sides of the ball.
- **Partial-pool design** (`milb_mle.py:535-567`): unpenalized fixed block `[1, z(minor rate), z(age)]`; penalized N(0,τ²) blocks for `level_intercept`, `level_slope` (level × z(feat)), `league_intercept`; solver `betting_ml/utils/hierarchical.py` (the same solver as the NCAAF feeder MLEs) with boundary-avoiding Gamma(2,·) τ prior + multi-start; `fixed_prior_sd = prior_scale × std(y)`.
- **Hyperparameters** (`MleConfig`, `milb_mle.py:252-284`): `min_cell_support=12` (a (level,league) cell earns its own factor), `min_minor_pa=150` (PA batter / TBF pitcher), `pool_prior_scales=(2.0,4.0)`, `gbm_grid=((300,2,0.03),(500,3,0.02))`, plausibility clamps per metric (`PLAUSIBLE_RANGE`, e.g. k_pct [0,0.60], gb_pct [0.10,0.80]) + `MAX_PLAUSIBLE_SD`.
- **Levels:** `LEVEL_ORDER = (Triple-A, Double-A, High-A, Single-A)` — CPX/DSL deliberately not in the incumbent (E8.7 gate PASSED but the refit is a registered future arm, blocked on a ~3.2h backfill).
- **v2_parkctx (E7.12 slice 1):** park-context features improved the batter translations and published `milb_mle_v2_parkctx` / `milb_mle_pitcher_v2_parkctx` into the raw projection tables (this is what the board reads). The **served priors** adopted v2 only where a head-to-head gate cleared (§7).

### E7.5 / E7.5b / E7.5p — the priors (no new fit; a recalibration + wiring architecture)

- **Method:** held-out residual sd — `σ_resid = std(realized MLB − MLE)` over highest-level labelled rows with an `mlb_pa≥150` (TBF; +`mlb_bip≥50` for GB%) floor — converted to a Beta pseudo-count `κ = m(1−m)/σ_resid² − 1`, clipped [20, 400]. ISO uses a regularized pseudo-count `κ_iso = 0.25/iso_prior_sd²` (the Normal-Normal path is documented dead — the "E7.5 ISO lesson"; the pitcher sibling never uses Normal-Normal at all).
- **Why recalibrate:** the E7.3 parameter sd was **5–7.8× too tight**; σ_resid gives honest ~0.68/0.90 coverage (measured per metric in the registry blocks).
- **Why it won:** purged leave-one-debut-cohort-out ablation vs the generic prior — MLE prior wins NLL + MAE on all wired metrics (batter K% MAE −27%, BB% −12%, ISO −6%; pitcher GB% −23%, K% −10%, BB% −8%).
- **E7.5p differences (deliberate):** a **cold-start gate** (`n_prior_seasons == 0` ⇔ under 10 career starts AND under 150 career BF — an established starter keeps the band prior; the E7.3p map is calibrated on first-two-MLB-seasons only); **per-metric evidence units** (K%/BB% weight against BF, GB% against balls-in-play); and the **new served column `eb_gb_pct`** (E7.3p's strongest translation previously had no home).

### E8.3 — SB translation (`sb_translation.py`, `run_e8_3_sb.py`)

- **Champion: `gbm`** (`GBMProjector(300,2,0.03)`; design `[feat, age] + level one-hots`, paired quantile GBMs for sd) — CRPS 0.028151 vs the level-mean foil 0.042065 = **+33.1%**, won **11/11 folds**, PBO(eligible) **0.043**, DSR **1.000**. OOS translation corr **0.702** Pearson (AAA 0.761 · AA 0.717 · A+ 0.707 · A 0.630), n=1,392.
- **Field:** 12 arms — level-mean foil, identity, `degenerate_zero`/`degenerate_mean` (two-sided anchors), `level_factor(_era)`, `ridge_a1(_era)`, `ridge_a10`, `gbm(_era)`, `beta_binom` — plus `oracle_peek`/`permutation` anchors scored every fold and excluded from the trial field (the MH2.1 (a) rule applied at design time).
- **Selector: CRPS primary, MAE reported-never-selected** — a deliberate divergence from E7.3's MAE selector, motivated by NF-D11 (MAE inverts on zero-heavy cohorts). The divergence was load-bearing: `level_factor`/`ridge_a1` beat the winner on MAE (0.0375 vs 0.0386) — **an MAE selector would have shipped a different arm.**
- **The blocker it had to clear first:** the MLB SB *label* did not exist (the rolling-stats mart is Statcast-derived, no SB). E8.3 built `scripts/ingest_mlb_season_hitting_to_s3.py` → `baseball/mlb/season_hitting` (Delta), verified against the official 2024 league total (3,617 SB exact).

### Prospect board (E8.0/E8.0b/E8.1 — an assembly, not a fitted model)

- **Chain:** `build_prospect_board.py` (runner) → `board_assembly.assemble_board` (FanGraphs + MLE scoring) → `fold_pipeline_into_e8_0_board` (MLB Pipeline merge → **roster org correction** → equal-weight consensus) → `attach_comps_to_board` (E7.13 comps, native since E8.1 — missing comp inputs is a HARD STOP, not warn-and-ship) → `export_prospect_board_json.py` (publish).
- **Ranking method:** consensus rank = **plain equal-weight mean** of the ranks that exist (FanGraphs overall/org, Pipeline overall/org) — E7.14, the study that could have justified unequal weights, recorded NULL (§10). Ordering blend: `FV_WEIGHT_BY_TYPE = {batter: 0.35, pitcher: 0.70, two_way: 0.50}` — FV leads for arms, our MLE + age-vs-level leads for bats (the E7.8 finding, restated per-position in the served manifest's framing block). Comp term weight `COMP_RANK_WEIGHT = 0.30`. **Per-metric MLE weights = the measured OOS translation correlations and nothing else** (`MLE_METRIC_WEIGHTS`, `board_assembly.py:306-311`): batter K% .637 / SB rate .702 / BB% .491 / ISO .429; pitcher GB% .551 / BB% .367 / K% .366. Measured nulls (wOBA, xwOBA-against) are **absent entirely, not down-weighted**.
- Final sort `fv, model_score, blend_score, pipeline_overall_rank` → `board_rank` (unique 1..N; the board's join key is **`rank`, not `mlbamId`** — 9 rows carry no MLBAM id).

## (3) Feature contract

Market-blind throughout (no odds column exists anywhere in the family). All features are strictly **pre-debut** (the as-of guard `l.official_date::date < d.debut_date` in the substrate builders — the single WHERE clause the E7.6 leakage screen independently re-audits daily).

**Per-column data dictionary — MLE translation input frame** (one row per (player, level); built by `build_graduated_pairs[_pitchers].py` from `baseball/milb/player_game_logs` (E7.1 Delta) restricted to regular-season rows at the four `LEVEL_ORDER` rungs, **strictly pre-debut** (`official_date < debut_date`)):

| column | who | definition |
|---|---|---|
| `minor_woba` | batter | Fixed-weight wOBA over the aggregated pre-debut line at the level: `(0.69·uBB + 0.72·HBP + 0.89·1B + 1.27·2B + 1.62·3B + 2.10·HR) / (AB + BB − IBB + SF + HBP)` — era-generic single weight set, deliberately (a season-specific set would leak era information across the debut boundary) |
| `minor_k_pct` | both | Batter: SO/PA. Pitcher: SO/TBF |
| `minor_bb_pct` | both | Batter: BB/PA. Pitcher: BB/TBF |
| `minor_iso` | batter | `(TB − H)/AB` — isolated power |
| `minor_hr_rate` | pitcher | HR allowed / TBF |
| `minor_gb_pct` | pitcher | `GO/(GO+AO)` — ground-**OUT** share, all the MiLB box offers. ⚠️ Cross-definition vs the MLB label (Statcast GB/BIP) — the regression *learns the rescale*; stated in the E7.3p report |
| `minor_pa` | both | Total pre-debut PA (batter) / TBF (pitcher) at the level. Eligibility floor **150**; also the reliability weight |
| `minor_start_share` | pitcher | GS/G — role indicator (starter vs reliever K%-inflation confounder). GBM-only impute-flagged aux channel, **not** a hierarchy level |
| `age` | both | PA-weighted age during the level stint (fixed unpenalized main effect in the partial-pool design) |
| `level` | both | One of `Triple-A / Double-A / High-A / Single-A` — the hierarchy's random-intercept + random-slope grouping |
| `league` | both | `mode(league)` at the level — its own random-intercept block (a (level,league) cell needs `min_cell_support=12` to earn a factor; GBM league one-hots need count ≥ 5) |
| `sc_xwoba` | batter aux | AAA-Statcast expected wOBA (quality-of-contact model). **Triple-A rows only** (the E7.2 join is AAA-only), GBM-only, imputed-with-missing-flag |
| `sc_barrels_per_pa_percent` | batter aux | Barrels per PA % — optimal EV×LA contact rate |
| `sc_hardhit_percent` | batter aux | Share of batted balls ≥ 95 mph exit velocity |
| `sc_avg_exit_velocity_mph` | batter aux | Mean exit velocity |
| `sc_avg_bat_speed_mph` | batter aux | Mean bat speed (bat-tracking) |
| `sc_xwoba_against` | pitcher aux | Expected wOBA allowed |
| `sc_swing_miss_percent` | pitcher aux | Whiff rate (swings-and-misses / swings) |
| `sc_avg_pitch_velocity_mph` | pitcher aux | Mean pitch velocity |
| `sc_avg_spin_rate_rpm` | pitcher aux | Mean spin rate |
| `sc_avg_release_extension_ft` | pitcher aux | Mean release extension |
| `sc_hardhit_percent_against` | pitcher aux | Hard-hit rate allowed |
| `mlb_<m>` (label) | both | Realized MLB rate: season-to-date `_std` line at the **last game of each MLB season** (`mart_batter_rolling_stats` / `mart_pitcher_rolling_stats`), PA/TBF-weighted over the first `label_window=2` MLB seasons; floors `min_mlb_pa/tbf=150`. Pitcher GB% label from `stg_batter_pitches` (Statcast GB/BIP), gate `mlb_bip ≥ 50` |
| v2_parkctx adds (E7.12-s1) | both | Park-factor + level×season **run-environment** context features (the run environment carried the lift, not the park — see §10); shipped in the `milb_mle_v2_parkctx` emission |

**Per-column — E8.3 SB frame** (`build_sb_pairs.py`; eligibility `min_minor_pa=150, min_minor_sbo=50, min_mlb_pa=150, min_mlb_sbo=50`):

| column | definition |
|---|---|
| `minor_sbo` / `mlb_sbo` | Stolen-base **opportunities** = times reaching first = singles + BB + HBP |
| `minor_sb_rate` (feature) / `mlb_sb_rate` (label, primary) | SB / SBO — how often he RUNS (and succeeds) per time on first |
| `minor_att_rate` / `mlb_att_rate` | (SB+CS) / SBO — attempt propensity (shipped-eligible, corr 0.707) |
| `minor_succ_rate` / `mlb_succ_rate` | SB / (SB+CS) — efficiency. **Measured null (corr 0.230, NO-SHIP)** — the board cannot claim it |
| `minor_sb_per_pa` / `mlb_sb_per_pa` | SB / PA — the denominator-free form (passes, not switched to) |
| label source | `baseball/mlb/season_hitting` — built BY E8.3 (`ingest_mlb_season_hitting_to_s3.py`); the rolling-stats mart is Statcast-derived and has no SB |

**Per-column — served prior parquet contracts (the exact columns the dbt branch reads; live-verified 2026-08-04):**

`baseball/lakehouse/milb_mle_prior/data.parquet` (batter, 6,376 rows):

| column | definition |
|---|---|
| `batter_id` | MLBAM id (join key into `eb_batter_posteriors_raw`; plain `ON batter_id` — no date predicate, which is why the E7.6 leakage screen exists) |
| `mle_level` | The **highest** MiLB level the player reached — the (player, level) row selected to serve |
| `is_prospect` | True = has a qualifying minor line but **no MLB debut yet** (label UNKNOWN, never 0) |
| `mle_k_pct` / `mle_bb_pct` | The MLB-equivalent translated rate = the **Beta prior MEAN** for the rookie's K%/BB% |
| `k_pct_prior_kappa` / `bb_pct_prior_kappa` | The Beta prior **strength** in equivalent PA: `κ = m(1−m)/σ_resid² − 1`, clipped [20, 400] — i.e. "trust this MLE like κ observed PA." The dbt branch forms `α = mle·κ`, `β = (1−mle)·κ` and lets the rookie's own MLB PA shrink from there |
| `mle_iso` | MLB-equivalent ISO = the prior mean (ISO is not a binomial rate, so no κ column) |
| `iso_prior_sd` | The recalibrated (E13.6, held-out σ_resid) predictive sd of the ISO prior; the dbt SQL converts it to a pseudo-count as `κ_iso = 0.25/iso_prior_sd²` (0.25 = per-PA variance bound of extra-bases-per-AB) — the regularized path that replaced the blown-up Normal-Normal (the "E7.5 ISO lesson") |
| `k_pct_source` / `bb_pct_source` / `iso_source` | E7.5b per-row provenance (`milb_mle_v1_served` vs `milb_mle_v2_parkctx`) — inert to the dbt consumer, load-bearing for audits (it is how §7's mixed provenance was verified) |

`baseball/lakehouse/milb_mle_pitcher_prior/data.parquet` (pitcher, 7,474 rows): `pitcher_id, mle_level, is_prospect` as above, plus `mle_gb_pct / gb_pct_prior_kappa`, `mle_k_pct / k_pct_prior_kappa`, `mle_bb_pct / bb_pct_prior_kappa` — same mean+κ semantics, but the **evidence unit differs per metric** (κ counts binomial trials): GB% shrinks against **balls in play**, K%/BB% against **batters faced**. Applied only when `is_cold_start` (n_prior_seasons = 0); an established starter keeps the band prior. Median served κ: gb 68 / k 81 / bb 146.

**Per-column — what reaches the betting feature store** (`feature_pregame_game_features_raw`, all `::double` type-pinned; per E7.9 only run_diff/pre_lineup's contract carries any of these today):

| column (×home/away) | definition |
|---|---|
| `avg_eb_k_pct` / `avg_eb_bb_pct` / `avg_eb_iso` | Mean of the EB **posterior** rate across the side's confirmed lineup batters — each batter's posterior = his own MLB line shrunk toward his prior, where a cold-start batter's prior is the MLE row above (else ZiPS, else population). Live slate values ~0.224 / 0.086 / 0.161 |
| `starter_eb_k_pct` / `starter_eb_bb_pct` | The probable starter's EB posterior K%/BB% from `eb_starter_posteriors` — κ-blend `(mle·κ + obs·BF)/(κ + BF)`, collapsing to the MLE mean exactly at BF=0 |
| `starter_eb_gb_pct` | The E7.5p-new column: `coalesce(MLE GB%, league anchor)` shrunk toward the pitcher's own prior-season GB% by BIP; populated for **every** starter (observed range 0.261–0.716, 48,629 rows). Served + schema-tested; in **no** model contract (E7.9 clean null) |

**Served vs tried, and whether ADDITIONS were explored (the 1d lesson-5 question):**

- **Wired by measured signal only:** batter K%/BB%/ISO (not wOBA); pitcher GB%/K%/BB% (not HR-rate, not xwOBA-against) — each exclusion is a recorded null in the registry's `not_wired` block, not an omission.
- **Feature additions to the TRANSLATION were extensively explored and are the E7.12/E7.15 program** (park context ADD → v2_parkctx; Heckman survivorship, tool grades, aging curves, trajectory/ladder/player-structure families — see §10 for each verdict). This family is the opposite of K-props: the feature space has been systematically worked, and most additions recorded nulls.
- **Whether the prior's columns reach a served model contract was separately measured (E7.9):** only `run_diff/pre_lineup` carries MLE-moved columns (`home_/away_starter_eb_k_pct`, `away_starter_eb_bb_pct` — 3 of 124 features). The v6 post_lineup champions are 13-feature slim sets with **no `starter_eb_*`/`avg_eb_*` at all**, so **E7.5's batter side currently reaches NO served game-model contract** — it serves through the EB tables and awaits a future retrain that selects it. `eb_gb_pct` is served + reachable but recorded a CLEAN NULL at game level and enters no contract.

**Board columns (served payload, live-read):** 63 keys per player incl. `rank`, consensus fields, `fv/fvPctile`, `mle{K,Bb,Iso,SbRate}(+Sd)`, `mleScore/ageScore/modelScore/blendScore`, comp fields (`compScore`, `compNames`, `compBandLo/Hi`, `compBustRate`…), `disagreement(Label)`, `org/orgSource/orgPrior`, `onFgBoard`. Additive-only contract (NF-C0).

## (4) Training data

- **Source:** S3 lakehouse via DuckDB + Delta, SF-free end to end — `baseball/milb/player_game_logs` + `baseball/milb/statcast_aaa` (features), `baseball/lakehouse/mart_batter_rolling_stats` / `mart_pitcher_rolling_stats` / `stg_batter_pitches` (labels), `baseball/mlb/season_hitting` (E8.3 label). Ingest is the daily `milb_ingest_job` (13:00 UTC, WARN-tier, `default_status=RUNNING`).
- **Window:** `--season-floor 2015` on the substrate build ("keeps the minor lines in the same era as the labels") → **1,750 labelled batter graduates** (E7.3), **2,034 labelled pitcher graduates** (E7.3p), **2,557 labelled (player,level) SB rows** (E8.3). The MiLB lakehouse itself holds 2005–2026 — the 2015 floor is a **BUILD FLAG, not a data limit** (MH2.2 measured 23,719 discarded pre-2015 games across the 2016–17 cohorts; changing it breaks comparability with every E7.12/E7.15 result, so it stands).
- **CV scheme (all fits):** **leave-one-MLB-debut-cohort-out, expanding window** — train on strictly-prior debut cohorts, evaluate the next; ≥2 evaluable cohorts required; 11 folds (2016–2026) at current data. Emission refits the winner per cohort on strictly-prior cohorts only (leakage-safe by construction); prospects train on all graduated cohorts (`emit_cohort=9999`).
- **Fold ceiling note (MH2.2):** both label marts begin 2015 ⇒ 12 cohorts / 11 folds is the max available **today** — a DATA limit, unlike the MLB game model's 3-fold WINDOW choice. Don't reach for MH2.1's widen-the-window lever here.

## (5) Validation — the §0.5 gates

Gate bars (shared `h_harness.py`): fold-win ≥ 0.60 (MH2-calibrated), PBO < 0.20, DSR ≥ 0.95, oracle floor enforced, degenerate anchors scored every run.

**E7.3 batter (per-metric verdicts, 1,750 graduates):**
| metric | OOS corr | DSR | verdict |
|---|---|---|---|
| k_pct | **0.637** | 1.0 | STRONG — wired |
| bb_pct | 0.491 | 0.989 | STRONG — wired |
| iso | 0.429 | — | weak-but-real — wired |
| woba | 0.220 | — | **NO SIGNAL** (ties archetype) — never wired |

**E7.3p pitcher (2,034 graduates):**
| metric | OOS corr | PBO | DSR | verdict |
|---|---|---|---|---|
| gb_pct | **0.551** | 0.000 | 1.000 | STRONG — wired (cross-definition proxy carried) |
| k_pct | 0.366 | 0.014 | 0.786 | weak-but-real — wired (pitcher K% translates far worse than batter 0.637 — a real asymmetry) |
| bb_pct | 0.367 | 0.000 | 0.947 | weak-but-real — wired |
| hr_rate | 0.094 | 0.900 | — | **TIED-FIELD NULL** (beats null by 1e-4 — the E2.1-r read) — not wired |
| xwoba_against | 0.147 | — | 0.030 | **NO SIGNAL** (ties archetype) — not wired |

**E7.5/E7.5p priors:** purged leave-one-debut-cohort-out vs the generic prior — wins NLL+MAE on all six wired metrics (numbers in §2); honest coverage 0.67–0.73 @1σ / 0.90 @1.645σ after E13.6 recalibration. **E7.5b head-to-head** (v2_parkctx-derived challenger vs the SERVED prior, n=538, 10 cohorts, BH-FDR@0.10, fold-win ≥ 0.60): bb_pct ships (0.90 fold-win, p=0.0138), iso ships (0.90, p=0.0043), **k_pct does NOT** (0.30, p=0.73) → served v1 k_pct kept byte-identical.

**E8.3:** primary `sb_rate` PASS (PBO 0.043, DSR ~1.0, 11/11 folds); `att_rate`/`sb_per_pa` PASS; **`succ_rate` NO-SHIP** (PBO 0.229 — genuine instability, not a tie per the NF1.8 flip-distribution read).

**Serving-side gates (the ones CI can't see):** E7.5p W8a parity 29/29 column fingerprints (48,621 rows both sides) + `predict_today` green on the 2026-07-27 slate; E7.5b `verify_mle_prior_serving.py` — the **PA=0 identity check** (a cold-start batter with an MLE must serve `eb_<m> == round(mle_<m>,4)`, since a silently-degraded LEFT JOIN passes any non-null count check): **434/434 on all three metrics**, with the held-back k_pct doubling as a free control.

**Board:** no fit ⇒ no gate; its honest gate is the framing block inside the served manifest (measured correlations as confidence labels; "makes no edge claim") plus the E7.13 comp validation + E7.14/E7.16 accuracy studies (all recorded in §10).

## (6) Serving path

**NOT served through `daily_model_predictions` directly.** Two independent serving surfaces:

**A. Betting-side (the priors) — SF-free lakehouse chain:**
1. Operator-run fits write S3: `mle_projections[_pitchers]` (Delta) → `run_[pitcher_]mle_prior_recalibration.py --s3` → `baseball/lakehouse/milb_mle[_pitcher]_prior/data.parquet` (single overwrite parquet).
2. `run_w1_lakehouse.py::_register_mle_prior_view` registers each parquet as a typed DuckDB view — **fail-safe**: on any read error it creates an EMPTY typed view, so a missing artifact degrades every player to the generic prior and **never HALTs** the serving-critical W8a build.
3. `dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql` (LEFT JOIN on `batter_id`; MLE overrides the effective Beta prior; cold-start precedence `coalesce(mle, ZiPS proj, population mean)`) and `eb_starter_posteriors.sql` (cold-start-gated; κ-blend by BF/BIP; int-normalized join per the INC-17 varchar-join landmine).
4. → `feature_pregame_lineup_features` / `feature_pregame_starter_features` → `feature_pregame_game_features_raw` → the pregame feature store the game models read. (Per E7.9: only run_diff/pre_lineup's contract actually carries an MLE-moved column today.)

**B. Board (admin app surface):**
1. Operator-run `build_prospect_board.py` (laptop, `AWS_DEFAULT_REGION=us-east-2`) → `e8_0_artifacts/e8_0_prospect_board.csv` (+AL/NL sheets, xlsx, comp detail, join report, E8.5 coverage-gap report).
2. Operator-run `export_prospect_board_json.py --s3-bucket credence-prod-s3-api-cache --publish` → `s3://credence-prod-s3-api-cache/fantasy/mlb/<season>/{board,manifest}.json` (region **us-east-1** on the put — the build's us-east-2 would misroute it; `--publish` required, dry-run otherwise; 5.5MB size guard vs Lambda's 6MB cap).
3. API: `app/backend/routers/fantasy.py` — `GET /fantasy/mlb/prospects/{manifest,board}`, **`Depends(get_admin_user)` on both routes** (Cognito `admin` group → token fallback → `ADMIN_EMAILS` legacy). Board served whole (~2.2MB), filtered client-side.
4. Frontend: `/fantasy/mlb/prospects` + `/disagreements` + `/league` — `restrict:"admin"` in nav, `<AdminGuard>` on pages, `enabled: isAdmin` on hooks.
5. **Admin gate = four coupled layers that must move together** (route dep + nav + guard + hooks). **"Not public until 2027" is a product decision enforced by these gates** — no date check in code; the open-up decision is carded as E8.4 (unmade). `/fantasy/mlb/*` inherits the default Cognito authorizer at the API Gateway (the NF3.2 rule inverted: an explicit `NONE` route would UN-gate it).
6. **Freshness is BUILD-TIME, permanently** (the NF3/E9.26b static-JSON decision): a board re-run reaches users only when the exporter re-publishes. Nothing schedules the build or the publish — both operator-run. The daily `milb_ingest_job` refreshes only the substrate + runs the E7.6 guards (WARN-tier).
7. E8.2 roster overlay: `app/backend/routers/fantasy_mlb_league.py` (admin-gated, keyed on board `rank`); E8.5 coverage-gap egress: API Lambda writes `baseball/milb/derived/prospect_board_coverage_gaps/user=<uid>/league=<lid>.json` (the first-ever Lambda WRITE to the artifacts bucket — needed its own IAM grant), read back by the next board build.

## (7) Version + last retrain + cadence ⭐ (MULTIPLE version authorities — name each)

This family has **four distinct version authorities**; assuming any single one misstates the state:

| sub-model | version authority | served version (reconciled) | evidence |
|---|---|---|---|
| MLE translations (raw) | `model_version` column **stamped in the Delta tables** (code constants in `milb_mle.py` / `run_e7_12_slice1.py`) | `milb_mle_v2_parkctx` (12,423 rows) / `milb_mle_pitcher_v2_parkctx` (13,892 rows) | **Live Delta read 2026-08-04.** ⚠️ v2_parkctx has **no registry key of its own** — it exists only as a stamped string. The registry's `milb_mle_v1`/`milb_mle_pitcher_v1` entries describe the harness + v1 bake-off; `promotion_status: pending` there means "not itself a served prior" (the wiring story promotes), NOT "not done". |
| Batter prior (SERVED) | `sub_model_registry.yaml::milb_mle_prior_v1` — **`source_model_by_metric`, not `source_model`** | **MIXED since E7.5b (2026-08-01):** bb_pct + iso from `milb_mle_v2_parkctx`, k_pct from `milb_mle_v1` (held back — did not clear the head-to-head) | Registry `promoted_at: 2026-08-01` **AND live parquet read 2026-08-04**: `k_pct_source=milb_mle_v1_served`, `bb_pct_source=iso_source=milb_mle_v2_parkctx` on all 6,376 rows; S3 mtime 2026-08-01. ✅ reconciled 3-way (registry ↔ parquet ↔ memo) |
| Pitcher prior (SERVED) | registry `milb_mle_pitcher_prior_v1` | `milb_mle_pitcher_prior_v1`, **v1-derived** (champion 2026-07-27) | Live parquet read: 7,474 rows, no source columns, S3 mtime 2026-07-27. ⚠️ **Deliberately NOT re-derived from pitcher v2_parkctx** — a standing ⛔ decision (registry): E7.12 s1p moved only bb_pct; gb_pct (where E7.5p's value concentrates) was DROPPED; and the pitcher runner has no `--incumbent-projections` head-to-head gate yet. **The raw pitcher table saying v2 while the served prior is v1-derived is CORRECT state, not drift.** |
| E8.3 SB | **code constant** `sb_translation.py:47` + the Delta stamp — **NO registry entry** (grep: zero hits, the 1d K-props pattern) | `sb_translation_v1` | Live Delta read: 19,795 rows / 18,403 prospects, all stamped `sb_translation_v1`; consumed via the board weight 0.702 hard-coded in `MLE_METRIC_WEIGHTS` |
| Board | **the served artifact itself** — `generated_at` in board.json/manifest.json (no model_version exists) | `generated_at 2026-08-04T01:19:18Z`, `as_of 2026-08-03`, `source e8_0_prospect_board.csv`, **1,459 players**, `hasComps: true` | **Live S3 read 2026-08-04** of the prod api-cache. ✅ = the post-PR-#564/#566 correct board (the 8/3 draft board); `source` names the RIGHT file (the plain board, not the stale legacy comps CSV) |

- **Retrain cadence: NONE scheduled for any fit.** Every fit/recalibration/board-build/publish is operator-run (grep of pipeline/, crontab: zero invocations). What IS daily: the substrate ingest (13:00 UTC), the E7.6 coverage SLA + leakage screen, and the W8a rebuild that re-reads the (static) prior parquets. The served priors are explicitly "rebuilt when the MLE is retrained."
- **Last retrains:** batter prior 2026-08-01 (E7.5b), pitcher prior 2026-07-27 (E7.5p), SB 2026-08-02 (Delta mtime), board published 2026-08-04T01:19Z (the 8/3 pre-draft regen). Downstream game-model retrain against the new priors: run 2026-07-28, **INCUMBENT_STANDS ×3** (E7.9).
- **Snowflake residual:** the SF-side `eb_*` incrementals (7-day MERGE window) still hold pre-MLE history — the documented operator DROP+rebuild is the only way to backfill them; the DuckDB/S3 branch (what serves) rewrote all history at cutover.

## (8) Honest-framing status — confirmed, at three layers

1. **Registry:** `best_alpha: 0` on all four entries ("a projection + a betting prior, never a market bet" / "a rookie prior, never a market bet" / "a cold-start prior, never a market bet").
2. **Served board artifact (live-read 2026-08-04):** the manifest's `framing` block carries the claim verbatim — *"This board makes no edge or win-rate claim and does not claim to beat FanGraphs"* — plus per-position honesty (FV leads for arms because pitcher stats translate worse; our line leads for bats), per-metric confidence labels that track the measured correlations (`mleIso: weak`, `mlePK: weak`…), and the SB caveat spelled out (a rate not a total; success rate does not translate, "we cannot tell a 30-for-40 runner from a 30-for-32 one"). Measured nulls are surfaced as absences, not hidden.
3. **Blank-cell honesty:** a blank "our line" is explained (CPX/DSL = 0% by construction; otherwise the 150-PA floor) — the E8.1 lesson that the *explanation* is its own defect class on a surface whose pitch is honesty.
4. The betting-side contribution (cold-start priors) carries no edge claim by construction — it feeds features into models whose own honest-framing status is documented in their sections (1a–1c).

## (9) Known limitations + open follow-ups

- **Nothing retrains or republishes automatically.** The board ages until an operator republishes (build-time freshness, stated in code three times); the priors are static parquets; the raw-vs-served version split in §7 is permanent bookkeeping the next auditor must know.
- **Board org staleness is structural:** FanGraphs' `org` is editorial and NEVER updates for trades (measured: 47 rank/level changes, 0 org changes across a deadline week). The PR #564 correction depends on MLB Pipeline ingest (operator-run, not scheduled) and covers only the ~899 Pipeline-ranked players; ~387 FanGraphs-only rows have no second org source. `--skip-pipeline-consensus` silently skips the correction too. Open follow-up: prefer the roster-derived org for ALL players (an E8.x story, not a run).
- **The legacy-artifact landmine is fixed but the class remains:** `resolve_board` now prefers comps-carrying then NEWEST (PR #566, guard-tested red-green), but any on-disk-precedence path can only be validated on a checkout that HAS the stale artifact — a fresh worktree passes by accident (the 2026-08-03 stale-publish incident).
- **CPX/DSL (E8.7) half-landed:** the ingest + feasibility gate PASSED (complex lines translate 0.55–0.98×; K% reliability 0.83–0.85 at ~200 PA) but the refit/SB-bake-off/board-rebuild are **BLOCKED on a ~3.2h operator backfill**; 156 prospects keep the FV-only fallback. The refit must be a registered ARM (not an in-place `LEVEL_ORDER` edit) and should carry K%/BB%/ISO but withhold wOBA (the carve-out, 0.25–0.47×).
- **E8.4 (open the surface to whom, when) is unmade** — the 2027 gate is product policy in four coupled code layers; season rollover additionally needs `MLB_PROSPECT_BOARD_SEASON` moved + a republish or the routes 404.
- **E8.8 (coverage-gap seating):** E8.5 flags board-missing prospects (live draft evidence: drafters repeatedly took off-board players) but there is no mechanism to add one — board membership is strictly (FanGraphs ∪ Pipeline).
- **Pitcher-prior head-to-head gate does not exist yet** (`run_pitcher_mle_prior_recalibration.py` has no `--incumbent-projections`); building it is part of any future pitcher-prior revision — which is itself gated on a slice actually moving pitcher GB%.
- **Train/serve skew is measured and small but real:** starter-consuming models were trained on generic-prior eb columns; 20.3% of starter rows moved (≈36% of games), |Δ eb_k_pct| 0.022–0.030. The 2026-07-28 retrain returned INCUMBENT_STANDS ×3, so the skew persists by verdict, pinned by `test_e7_9_train_serve_consistency.py`.
- **The E7.6 screens are the family's only daily watchdogs** (WARN-tier — correct, MiLB is off the serving path); the leakage screen guards the ONE WHERE clause between the served prior and a leakage bug; the coverage SLA is what caught the 7-day Byparr FanGraphs outage on its first real run.
- **`succ_rate` (SB success) is a recorded no-ship** — the board cannot distinguish an efficient runner from a reckless one, and says so.
- **MH2.2's substrate note stands:** 11 folds is the data max (marts begin 2015); fold RESOLUTION (the `--season-floor 2015` build flag vs 2005+ lakehouse history) is a live-but-untaken lever — changing it breaks comparability with every shipped foil.

## (10) ⭐ TRIED & RESULT ledger

_The longest ledger in the program — that length is the value. Null states per `cv_power.classify_null` (+ the NF-D18 `CONSTRAINT_REFUSED` extension) where recorded. So a future audit never re-recommends a dead end._

### Foundations + translations

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **E7.4 identity xref** (`dim_player_xref`, MLBAM spine) | 2026-07-27 | **SHIPPED** — 40,449 rows; board→MLBAM 99.3%, graduate leg 97.2%; NO fuzzy name leg (the one name-equality hit was two different Michael Masseys) | `e7_4_prospect_xref.md` |
| **E7.3 batter translation bake-off** (partial-pool vs multiplicative vs GBM vs nulls, per metric) | 2026-07-26 | **SHIPPED 3 of 4**: k_pct 0.637/DSR 1.0, bb_pct 0.491/0.989, iso 0.429 weak-but-real; **wOBA NULL** (corr 0.220, DSR 0.032, ties null AND archetype — pre-taxonomy, no state recorded). partial_pool swept; **multiplicative (Davenport) under the null** on wOBA/ISO | `e7_3_milb_mle.md` |
| **E7.3p pitcher translation** | 2026-07-27 | **SHIPPED 3 of 5**: gb_pct 0.551/PBO 0.000/DSR 1.0; k_pct 0.366 / bb_pct 0.367 weak-but-real (pitcher K% ≪ batter K% — real asymmetry); **hr_rate TIED-FIELD NULL** (beats null by 1e-4, PBO 0.900); **xwoba_against NO-SIGNAL** (DSR 0.030). Multiplicative under the null on all 5 — Davenport refuted both sides of the ball | `e7_3p_milb_mle_pitchers.md` |
| **E7.5 batter rookie prior** (recalibrated MLE → eb_batter_posteriors_raw) | 2026-07-26 / regen 08-01 | **SHIPPED, 3/3 ADD** vs generic prior: k_pct MAE −27%, bb −18%, iso −13% (NLL wins all); E13.6 recalibration fixed a 5.2–7.4× too-tight parameter sd (honest cov 0.67–0.69/0.90) | `e7_5_milb_prior_ablation.md` |
| **E7.5p pitcher cold-start prior** (+ NEW `eb_gb_pct`) | 2026-07-27 | **SHIPPED + serving-verified** (parity 29/29): gb MAE −23%, k −10%, bb −8%; pre-registered "modest, concentrated in GB%" HELD. hr_rate/xwoba_against NOT wired (E7.3p nulls) | `e7_5p_pitcher_prior_ablation.md` |
| **E7.5b head-to-head: v2_parkctx-derived prior vs the SERVED prior** | 2026-08-01 | **SPLIT: bb_pct + iso SHIP** (9/10 folds, p=.0138/.0043, BH-FDR true); **k_pct HOLD** (3/10, p=0.73, wrong side on NLL+CRPS) — recorded as a **LOSS/TIE, not underpowered; no re-validation scheduled**. Translation-MAE gain on k_pct was directionally real and did NOT convert to pricing — a translation objective ≠ a calibration objective | `e7_5b_mle_prior_head_to_head.md` |

### FV / scouting-grade line

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **E7.8 FanGraphs FV → MLB projection** (36 arms, 6 gated tests) | 2026-07-27 | **DIFFERENTIATED: pitcher ADD ×2** (unconditional DSR 0.998, debut 0.998, both PBO 0.0), **batter DROP ×3** (best: tied field spread 0.012 = the E2.1-r null read). Mechanism: FV **SUBSTITUTES** for our batter read, **COMPLEMENTS** the pitcher read. First run INVALIDATED by a FanGraphs role-label change (666 relievers typed as batters) — re-run clean | `e7_8_fv_translation.md` |
| **E7.10 pre-debut FV as an incremental cold-start RATE prior** (vs the matched foil C0 = same regression minus FV) | 2026-08-03/04 (PR #572, just shipped) | **NULL — `GENUINE_ABSENCE` ×3** (gb −0.51% / k −0.20% / bb −0.24% CRPS; 1-3/6 folds; placebo-indistinguishable p 0.27–0.89; gb+bb POWERED for a 3% effect and the sign is negative) ⇒ **NO re-test trigger; ⛔ do NOT re-card for more seasons.** Reconciles with E7.8: **FV forecasts WHO ARRIVES; the MLE forecasts HOW HE PITCHES** — FV is CLOSED as a betting rate input. ⭐ Secondary finding the matched foil surfaced: **in-fold recalibration of the served MLE mean HURTS gb_pct by 1.60%** — E7.5p's serve-verbatim choice is now measured, not assumed. Diagnostic arm split the null: k_pct FV = informative-but-REDUNDANT; gb/bb = no signal | `e7_10_fv_starter_prior.md` |
| **E7.14 source accuracy** (FG vs Pipeline vs consensus, 9 arms) | 2026-08-01 | **Q1 NULL** (Δ +0.0040 vs MDE 0.0245 ⇒ equal-weight consensus CONFIRMED, not corrected); **Q2 NOT EARNED**; **Q3 real-but-uncertifiable** — `pipeline_grade` beats FV 5/5 folds, PBO 0.0, but DSR uncomputable at 5 obs and **BH-FDR structurally UNATTAINABLE at 5 folds** (sign-test floor p=.0625 > BH cutoff .0100 — no effect of ANY size could pass). In the unit that grows: needs 8 seasons, has 5 → **2029**. Side result: hindsight-free E7.8 FV replication | `e7_16_artifacts/e7_14_source_accuracy.md` |
| **E7.14b archive-reach spike** (does the FG board archive predate 2018?) | 2026-08-01 | **CLOSED NO at step 0** — `min(season)=2018` in the raw archive; the 2018 floor is the archive's true floor and the 2029 bound is ARCHIVE-INDEPENDENT | story_prompts.md + memory |

### E7.12 improvement slices (the research-memo program)

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **S1 park factors + level×season run-env (batters)** | 2026-08-01 | **4/4 ADD, PUBLISHED** as `milb_mle_v2_parkctx` (k +3.50%, bb +3.34%, iso +5.06%, woba +0.93% — woba's ADD cosmetic, nothing reads mle_woba). ⭐ Self-refuting headline: **the RUN ENVIRONMENT is the mechanism, not the park** (park alone: +0.84% iso max, NEGATIVE bb). Placebo park negative ×4 | `e7_12_slice1_park_level_context.md` |
| **S1p same, pitchers** | 2026-08-01 | **2 ADD / 3 DROP — and both ADDs cosmetic for the board** (bb +3.12%, hr +1.28%; k_pct FDR-DOWNGRADED after a disclosed computed-but-not-enforced BH clause; gb_pct DROP = why the E7.5p prior is deliberately NOT re-derived) | `e7_12_slice1p_park_level_context_pitchers.md` |
| **S2 survivorship correction (IPW + Heckman)** | 2026-07/08 | **Mostly null: 1 ADD per side** (batter k_pct +0.19%, pitcher hr_rate +0.16%, both T1b_ipw_odds). Synthetic-truth oracle: **Heckman is best where selection-on-unobservables exists (0.80 vs 1.42)** — which the live graduate-only gate structurally cannot see | `e7_12_slice2_survivorship*.md` |
| **S3 per-component reliability / level-jump attenuation** | 2026-07-31 | **CLOSED WITHOUT A RUN — already implemented** (per-metric prior_scale, per-block free τ², level_slope block = the attenuation). A correction that REMOVES a story | roadmap item 14 |
| **S4 tool-grade (20-80) component priors** | 2026-07/08 | **ALL DROP ×9 cells** — and the pre-registered batter prediction. Fold set restricted (board starts 2018-07 ⇒ max attainable fold-win 7/11; a perfect signal clears by one). ⚠️ Grade coverage rises with promotion propensity — least available exactly where S2 says help is needed. **The ONE place E7.8's pitcher-ADD asymmetry did NOT reproduce** | `e7_12_slice4_tool_grades*.md` |
| **S5 prospect aging curves (age × translation slope)** | 2026-07/08 | **ALL DROP ×9** (age is already a fixed main effect since E7.3; only the SLOPE was in question). 50% IPW retention floor pre-registered (survivorship manufactures "young translates better") | `e7_12_slice5_aging_curves*.md` |
| **S6 AAA-Statcast as a predictive feature** | 2026-07/08 | **STOP — `UNDEFINED`, explicitly NOT a null**: 3 usable folds < 4 ⇒ PBO uncomputable; MDE 11.95% vs best-ever slice lift ~3.5%; coverage AAA-only (40%/31%), zero in cohorts 2015–21. "A bake-off that cannot detect its own effect is not a null" | `e7_12_slice6_feasibility*.md` |

### E7.15 translation round 2 + MH2.2 (the trajectory saga)

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **H1 within-player level ladder** | 2026-08-02 | **ALL DROP ×9** (winner = foil everywhere); pitcher xwoba_against arms **`INACTIVE`** (Triple-A-only feature ⇒ zero within-player transitions — "a mechanism that cannot act is a finding") | `e7_15_h1_level_ladder*.md` |
| **H2 opponent / competition quality** | 2026-08-02 | **ALL DROP ×8**. Honesty check: survivors with the deflation gates REMOVED = **none** (BH multiplicity binds, not the gate). The adjustment dispersion is real; it just doesn't translate | `e7_15_h2_opponent_quality*.md` |
| **H3 player-level structure + trajectory arms** | 2026-08-02 | **ALL DROP ×9** — bb_pct/iso cleared BH-FDR + PBO but not the field DSR; the recorded 2-arm DSR 0.998 was later **RETIRED by MH2.2** as a post-hoc field cut | `e7_15_h3_player_structure*.md` |
| **H4 regress the TARGET toward true talent** | 2026-08-02 | **ALL DROP ×9** (pitcher k_pct BH true but PBO 0.200 at the bar) | `e7_15_h4_target_regression*.md` |
| **MH2.2 trajectory family AS DECLARED (3 arms, batters)** | 2026-08-03 | **Pre-registered NULL ×4, all states named in advance and reproduced**: woba `GENUINE_ABSENCE` (DSR 0.285); k/bb/iso `POWER_LIMITED` (DSR 0.748/0.849/0.759 vs 0.95; triggers +51/+16/+45 folds). ⭐ The post-hoc 0.998 was bought by **DISPERSION, not multiplicity** (dropping the losing arm collapsed V **19,938×** on bb_pct). 🪤 `classify_null`'s max_field_size trigger = UNSAFE ADVICE against a declared family. Fold ceiling here is a DATA limit (marts begin 2015 ⇒ 11 folds max), unlike MH2.1's window choice | `mh2_2_trajectory_family.md` |
| **MH2.2 pitchers** | 2026-08-03 | **NULL ×5**: k/bb `GENUINE_ABSENCE` (negative lift); **hr_rate `DSR_UNREACHABLE`** (no field size rescues it); gb_pct `POWER_LIMITED` (+1,028 folds — i.e. never); xwoba_against `INACTIVE` (declared pre-run) | `mh2_2_trajectory_family_pitchers.md` |

### Comps + consensus + board

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **E7.11 multi-source consensus** (MLB Pipeline added) | 2026-07-29 | **SHIPPED as a DESCRIPTION** (exempt — no accuracy claim). Pipeline 100% MLBAM-keyed. Access discipline recorded: BA / The Athletic / Prospects Live **REFUSED** (robots/rights) ⇒ overall consensus stays 2 sources deep | `e7_11_prospect_consensus.md` |
| **E7.13 prospect→historical comps** (PECOTA-style, Gower k=25) | 2026-08-01 | **Phase 1 display SHIPPED; batter BLEND_ELIGIBLE (DSR 1.0, CRPS −8.63 vs fv_bucket), pitcher DISPLAY_ONLY (DSR 0.945 ✗); ordering term WIRED @ 0.30** (positive 10/10 fold×type). ⚠️ `comp_only`'s apparent win was an era artifact — it collapsed on the one clean fold. 3 leakage/defect fixes disclosed (retained-`level` = a one-sided outcome leak AUC 0.800; FV-only zero-distance pairs; one-career-7-votes) | `e7_13_prospect_comps.md`, `e7_13_artifacts/` |
| **E7.16 comp pool rebuilt point-in-time** (Pipeline archive 2015–2022, 4 strictly-matured folds) | 2026-08-01 | **Batter BLEND_WIRE — E7.13's deferred verdict resolved 3 years early** (CRPS −8.31, PBO 0.0, DSR 1.0); **pitcher DISPLAY_ONLY = attributable null** (DSR 0.379, fails FDR even with DSR removed). 🚨 Found+fixed the **matched-support defect** in the ordering harness (comp_only's batter "win" +0.1073 → +0.0330 on matched rows; the BLEND wins every cell; **w=0.30 CONFIRMED, not re-picked**). Position asymmetry reproduces a 3rd time WITH a mechanism. **The 8/3 draft file is unchanged — what changed is the WARRANT** | `e7_16_pipeline_comp_pool.md` |
| **E8.0/E8.0b lean draft board** | 2026-07-29/31 | **SHIPPED as a description** (exempt): 1,451 rows, 3 independent reads, no ranking-accuracy claim | `e8_0_prospect_board.md` |
| **E8.2a CBS auto-import probe** | 2026-07-31 | **NO-GO (earned)** — all 4 compliant paths tried live, each fails verifiably ⇒ E8.2 is manual upload only | `e8_2a_cbs_access_probe.md` |
| **Board org correction** (FanGraphs baseline + two lagging Pipeline signals) | 2026-08-03, PR #564 | **SHIPPED** — FG org is editorial and NEVER moves for trades (measured 0/1,286 across a deadline week); rule = whichever Pipeline signal differs from the FG baseline has caught up; both-moved-and-disagree REFUSES to guess; org_rank NULLED on a moved player. 43 stale orgs / 25 wrong-sheet fixed on the draft board | `build_consensus_assembly.py`, changelog |
| **Board export artifact precedence** | 2026-08-03, PR #566 | **FIXED after a live stale-publish** — `resolve_board` took first-existing in a fixed order; a gitignored legacy `e7_13_prospect_board_comps.csv` outranked the fresh build FOREVER and published a 2-day-old board an hour after a good publish. Now: prefer comps-carrying, then NEWEST mtime, loud WARN on a passed-over newer file, always log path+mtime. ⚠️ Class lesson: a fresh worktree CANNOT reproduce it (false PASS) | `export_prospect_board_json.py`, `test_prospect_board_export_source.py` |

### SB + complex levels + downstream

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **E8.3 SB translation** (12 arms, CRPS selector) | 2026-08-03 | **SHIP** — `gbm` +33.1% CRPS vs foil, 11/11 folds, PBO 0.043, DSR 1.000, **OOS corr 0.702 = the strongest metric on the board**. `att_rate`/`sb_per_pa` also pass (sb_per_pa scored higher but NOT switched to — post-leaderboard switching is unregistered selection); **`succ_rate` NO-SHIP `DSR_UNREACHABLE`** (PBO 0.229; no fold count rescues it) — "the board can say how often he RUNS, not how often he makes it." sb_rate's own DSR table = `POWER_LIMITED` (needs 145 folds). ⚠️ The MAE selector would have shipped a different arm (NF-D11 discipline paid off). Blocker cleared first: the MLB SB label didn't exist → built `baseball/mlb/season_hitting` | `e8_3_sb_translation.md` |
| **E8.7 DSL/CPX ingest + complex-translation screen** | 2026-08-03 | **SCREEN PASSES; refit NOT run** (blocked on ~3.2h operator backfill; 156 prospects keep FV-only fallback). Carry K%/BB%/ISO, **withhold wOBA** (0.25–0.47× — the E7.3 wOBA null at a new rung). NOT an INACTIVE story (K% reliability 0.83–0.85 at ~200 PA). Rung from league ID not NAME (2021 renames); rung is per-TEAM not per-game. 3 instrument defects caught by anchors (delta-method → exact multinomial; permutation floor n-dependence; era confound) — the correction CUT the headline (DSL→MLB K% 0.96×→0.58×) | `e8_7_complex_translation.md` |
| **E7.9 retrain vs the new priors** (×3 target/tier bake-offs, 24–28 arms) | 2026-07-28 | **INCUMBENT_STANDS ×3** — best margin +0.0206 (total_runs/post) missed only DSR 0.842 vs 0.95 (PM: park for natural auto-retest, NOT a story). ⚠️ 54–77% of every margin was the **learner swap** (ngboost→glm_elasticnet), not the features — noted, deliberately NOT acted on (a CRPS win doesn't target NGBoost's pricing job). **`eb_gb_pct` = CLEAN NULL at game level, target-dependent sign** (+total_runs/−run_diff, all ≤¼ the noise floor): the −23% metric-level lift does NOT propagate to game skill; column stays served, enters no contract. home_win never tested = a known DEFERRED gap (its next retrain tests it free) | `e7_9_retrain_verdict_summary.md`, `e7_9_train_serve_audit.md` |
| _(cross-family)_ **NF-D18 attenuate-at-the-top** | 2026-08-02 | NFL rookie board, NOT baseball — in this ledger only as the origin of **`CONSTRAINT_REFUSED`**, the 8th null state the baseball memos (E7.10, E8.7) now cite: arms that WIN the metric but are removed by a deterministic constraint get no more-data trigger, ever | `nf_d18_rookie_top_attenuation.md` |
| **Research memo scorecard** (the 2026-07-29 deep-research memo that generated E7.12) | — | Priorities 1→7 scored against reality: #1 ADD · #2 mostly-null · #3 already-implemented · #4 ALL DROP · #5 ALL DROP · #6 UNDEFINED/stop · #7 (embeddings) never run — the one un-run item in the memo | `research_milb_projection_2026-07-29.md` |

### Null-state coverage in this family (the audit map)

`GENUINE_ABSENCE`: E7.10 ×3 · MH2.2 batter woba, pitcher k/bb — no re-test triggers exist for these, by definition.
`POWER_LIMITED`: MH2.2 batter k/bb/iso (+16..+51 folds), pitcher gb (+1,028 = effectively never) · E8.3 sb_rate DSR table (145 folds).
`DSR_UNREACHABLE`: MH2.2 pitcher hr_rate · E8.3 succ_rate — no n rescues either.
`INACTIVE`: E7.15-H1 / MH2.2 pitcher xwoba_against (Triple-A-only feature, zero transitions).
`UNDEFINED`: E7.12-S6 (3 folds < CSCV minimum).
`CONSTRAINT_REFUSED`: NF-D18 (cross-family; the state itself is now available to baseball stories).
`TRUSTWORTHY_DEAD` / `UNKNOWN`: **no instance in this family** — E7.10's pre-registration is the only baseball memo that made TRUSTWORTHY_DEAD reachable by design.

---

### Reconciliation summary (for the umbrella index)

- **Batter prior reconciled ✅ 3-way** (registry `source_model_by_metric` ↔ live parquet `*_source` columns ↔ E7.5b memo): mixed provenance k_pct=v1 / bb_pct,iso=v2_parkctx, promoted 2026-08-01, serving-verified 434/434.
- **Pitcher prior reconciled ✅** (registry champion 2026-07-27 ↔ live parquet mtime/rows) — and the raw pitcher Delta table stamping `v2_parkctx` while the served prior is v1-derived is **CORRECT state by standing ⛔ decision**, not drift; an auditor reading only the projections table would misreport the served version.
- **E8.3 has NO registry entry** (the 1d K-props pattern): version-of-record = code constant + Delta stamp (`sb_translation_v1`) + the board weight; reconciliation is code ↔ artifact ↔ memo, done above.
- **Board reconciled ✅ against the served artifact itself** (the only authority it has): live prod JSON = 1,459 players, generated 2026-08-04T01:19Z from the correct source file — the post-#564/#566 state; no publish recorded since.
- **Headline nuances for the index:** (1) four version authorities in one family — registry alone is insufficient for three of the four sub-models; (2) the family serves TWO unrelated surfaces (betting feature store + admin board) with different freshness models (daily W8a rebuild of static parquets vs operator publish); (3) ADMIN-ONLY until 2027 — the board is deliberately not a public surface, so there is no `daily_model_predictions` row to reconcile; (4) `best_alpha=0` everywhere, honest framing baked into the served artifact itself.
