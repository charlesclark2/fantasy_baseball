# MLB Edge Program — Technical Design Spec

**Status:** Draft 1.1 — engineering-ready
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Author:** prepared for Charlie
**Date:** 2026-06-17
**Scope:** Workstreams **A–E** are betting-edge tracks — moving the betting platform from "well-built, no demonstrated market edge" to "selective, validated, market-relative edge" (A overfitting audit, B per-side totals, C closing-line/CLV, D cross-book sharp-anchor, **E player props**). Workstreams **F–H** extend the program: a feature-engineering audit (F), minor-league data + rookie-prior MLEs (G), and a distributional player-projections suite powering a fantasy/Dynasty vertical (H). Grounded in `refined_architecture_proposal.md`, `implementation_guide.md`, and `baseball_data_mart_inventory.md`.

---

## 0. Framing & operating thesis

The system has run **13 independent head-on no-edge confirmations** (4 H2H: Epics 11, 16B.7, 28.4, 28.5; ~9 totals: Epics 10.6, 16B, 17 v1/v3, 27.3, 10.10, plus prior). The promotion gate (`promotion_gate.py`) is correctly judging accuracy-to-truth, and the production champions are honest. The conclusion is not "the models are bad" — it is that **the full-game moneyline and full-game total are efficiently priced, and ~10K noisy labels cannot out-predict that one number.**

These four workstreams deliberately stop optimizing the point model against the closing line and instead attack the four places edge can still exist:

| WS | Name | Thesis | Primary new target |
|----|------|--------|--------------------|
| **A** | CV-hygiene + overfitting audit | Before trusting *any* future edge, quantify how much of "getting closer" is multiple-testing noise. | (audit, not a model) |
| **B** | Per-side generative totals | Compete on the numbers books price *lazily* (F5, team totals, alt-lines) via an honest full distribution. | per-side run distributions → convolved total |
| **C** | Closing-line / CLV model | Predict the *market's own move* (open→close), a far higher-SNR target than the game. | Δ(open→close) and P(beat close) |
| **D** | Cross-book sharp-anchor | Bet the soft book toward the sharp consensus when they diverge. | sharp_fair_prob − soft_price |

**Sequencing summary:** A is a prerequisite gate for trusting B/C/D results. C and D share the market-data plumbing and should be built together. B is independent and unblocks the totals product + the distribution UX. Detailed dependency graph in §6.

---

## Workstream A — CV-Hygiene & Overfitting Audit

### A.0 Why this is first
You have tried many model families and feature sets. Each trial is a chance to find a spurious "edge." Lopez de Prado's central warning (AFML ch. 11–12) is that **with enough trials, an impressive backtest is the default, not the exception.** Two consequences:

1. Your walk-forward CV, though correct in direction, likely still leaks via overlapping feature windows.
2. You currently have no number that says *how likely your next apparent edge is real.* This workstream produces that number. It gates B/C/D.

### A.1 Purged & embargoed walk-forward CV
**Problem.** Your rolling features (`*_7d/_14d/_30d`, `mart_team_rolling_*`, `mart_bullpen_*`) mean a test-day game's feature vector is built from the same recent games that appear as *training labels* in the immediately preceding window. Walk-forward by season does not remove this near-boundary overlap; it inflates CV optimism near each fold edge.

**Spec.**
- Implement `PurgedWalkForwardSplit` in `betting_ml/utils/cv.py`:
  - Forward-chained folds (preserve the existing season-based outer loop).
  - **Purge:** drop training samples whose feature look-back window (max 30d, or the specific feature's window) overlaps `[test_fold_start, test_fold_end]`.
  - **Embargo:** additionally drop training samples within `embargo_days` *after* the test fold (default 3d) to kill leakage from autocorrelated state (bullpen, streaks).
- Parameterize per-feature window length from a registry so purge length is feature-aware, not a blanket 30d.
- **Wire into** `promotion_gate_eval.py`'s `walk_forward_gate` driver as an opt-in split strategy; re-run the current champions through it to get an honest, purge-adjusted baseline.

**Validation gate.** Re-score `home_win` v5, `run_differential` v5, `total_runs` under purged CV. Expected: metrics degrade slightly vs current CV. The *size* of the degradation is the leakage estimate — report it in `ablation_results/purged_cv_recalibration.md`. Any champion whose edge-vs-market *story* depended on near-boundary folds must be re-examined.

### A.2 Sample-uniqueness weighting (sequential bootstrap)
**Problem.** Games are not i.i.d. A starter's consecutive starts, games within a series, and shared bullpen state create concurrent/overlapping information. Equal-weighting over-counts redundant samples.

**Spec.**
- Compute per-game **concurrency** = number of other training games whose feature windows overlap this game's window (AFML §4.3). Derive `avg_uniqueness` per sample.
- Two uses:
  - **Training:** pass `sample_weight = avg_uniqueness` to XGBoost/LightGBM/NGBoost fits (all support sample weights).
  - **CV resampling:** implement `sequential_bootstrap()` for any bagged/ensemble variant so draws favor unique samples.
- Store uniqueness weights as a column alongside the training matrix so every trainer consumes the same weights (drift-guard like your `season_normalization` parity test).

**Validation gate.** Re-fit champions with uniqueness weights under A.1's purged CV. Promotion still governed by `evaluate_promotion` (criteria 1–6). Document whether weighting changes the champion or its calibration.

### A.3 Clustered feature importance (MDA)
**Problem.** ~690 features (`feature_pregame_game_features`), heavily collinear (`home_*`/`away_*` mirror pairs, multiple rolling windows of the same stat). Your Layer-3 stacking weights are "near-uniform" — a classic symptom that single-feature importances are diluted across substitutes. MDI is biased toward high-cardinality/collinear features; you need MDA on *clusters*.

**Spec.**
- `betting_ml/scripts/clustered_feature_importance.py`:
  1. Correlation/distance clustering of the feature matrix (hierarchical on `1 - |ρ|`, or your existing archetype-style clustering) → feature *clusters*.
  2. **Clustered MDA** (AFML §8.5): shuffle each *cluster* together under purged CV, measure score degradation. This attributes signal to a concept (e.g., "starter suppression block") rather than to one column that has six near-duplicates.
- Output a ranked cluster-importance table → `ablation_results/clustered_feature_importance.md`.

**Validation gate / payoff.** Drop or consolidate clusters with importance indistinguishable from noise (paired bootstrap CI crossing 0). Expected: large dimensionality reduction with no accuracy loss, which directly *reduces overfitting surface* for B/C/D and clarifies which Layer-2 sub-models actually carry weight.

### A.4 Probability of Backtest Overfitting (PBO) + Deflated Sharpe
**Problem.** This is the answer to *"are we getting closer to something real?"* Right now it's a feeling. Make it a number.

**Spec.**
- **PBO via Combinatorially-Symmetric Cross-Validation (CSCV)** (AFML §11.4): given the matrix of per-config performance across CV sub-periods (you have many configs already — every challenger, every ablation), compute the probability that the in-sample best config underperforms the median out-of-sample. Report PBO for: (a) the totals model search, (b) the H2H search, (c) any future B/C/D bake-off.
- **Deflated Sharpe Ratio (DSR)** (AFML §14): for any *betting* strategy (D's selective bets, B's derivative bets), deflate the observed Sharpe by the number of trials and the non-normality of returns. A strategy only graduates from shadow to live if **DSR > 0 at 95%** *and* it clears your existing CLV gate.
- Add `betting_ml/utils/overfitting.py` with `pbo_cscv()` and `deflated_sharpe()`; wire a standing report `ablation_results/overfitting_dashboard.md` regenerated whenever a new strategy is proposed.

**Validation gate.** This *is* the gate for the program. **No B/C/D strategy goes live without a PBO and DSR on record.** Set thresholds now: ship-to-shadow requires PBO < 0.5; shadow-to-live requires PBO < 0.2 **and** DSR > 0 (95%) **and** the existing live-CLV gate.

### A.5 Deliverables
- `betting_ml/utils/cv.py` (purged/embargoed split), `overfitting.py` (PBO, DSR), `clustered_feature_importance.py`, uniqueness-weight column + parity test.
- Reports: `purged_cv_recalibration.md`, `clustered_feature_importance.md`, `overfitting_dashboard.md`.
- Updated `promotion_gate_eval.py` to default to purged splits.

---

## Workstream B — Per-Side Generative Totals Model

### B.0 Why this is the totals unlock
Story 29.1 is the whole diagnosis: the totals model is **level-unbiased but per-game variance-deficient** — "it knows the average, not which game is 6 vs 11 runs." Competing on the full-game total mean is competing on the *one number the book prices most carefully.* The escape is to model the **full predictive distribution per side**, convolve to a total distribution, and then **price the markets the book derives lazily** from its full-game line: first-5-innings (F5), team totals, and alternate totals. This is your Epic 32, promoted to a first-class build, and it simultaneously produces the user-facing distribution.

### B.1 Reuse what already exists
You already ship **`offense_v2`** (LightGBM + NegBin) writing per-side `pred_runs_mu`, `pred_runs_dispersion`, `pred_runs_raw`, `uncertainty` to `betting_features.offense_v2_signals`. That is *already a per-side run distribution.* The gap is three things: (1) it's a feature signal, not a calibrated bettable distribution; (2) no home/away dependence structure; (3) no convolution + derivative pricing layer. Build B on top of `offense_v2` rather than from scratch.

### B.2 Model structure
**Stage 1 — per-side conditional count distributions.**
- For each game, side ∈ {home, away}: predict a count distribution of runs scored by that side. Start with NegBin (your `sub_model_output_standard` already mandates NegBin for per-side run counts and justifies it: var/mean = 2.26 > 1.5).
- Inputs: that side's offense (`feature_pregame_lineup_features` / `feature_pregame_expected_lineup` for pre-lineup), the *opposing* starter (`feature_pregame_starter_features`, `eb_starter_posteriors`), opposing bullpen (`eb_bullpen_team_posteriors`, `feature_pregame_bullpen_state_features`), park & environment (`feature_pregame_park_features`, `run_env_v4` signal, `feature_league_contact_baseline` season-normalized contact), weather, umpire. **No market features** (architecture Principle 3 — this stays Layer 2/3).

**Stage 2 — dependence structure (the new part).**
- Home and away runs are *not* independent (shared park, weather, umpire, game pace, and a weak game-state coupling). Independent convolution will misestimate the tails that derivative pricing depends on.
- Implement a **copula** over the two NegBin marginals (Gaussian copula is sufficient and cheap; fit a single correlation ρ, optionally conditioned on park/weather buckets). Calibrate ρ on historical (home_runs, away_runs) pairs from `mart_game_results`.

**Stage 3 — convolution → predictive distributions.**
- Draw N joint samples (home_runs, away_runs) from the copula-coupled marginals → derive sample distributions for:
  - **Total runs** = home + away → main + alt totals.
  - **Run differential** = home − away → feeds H2H/run-line as a *distributional* output (bonus: a distribution-based H2H prob).
  - **Team totals** = each marginal directly.
  - **F5 totals/team-totals:** train a *separate* Stage-1 pair restricted to innings 1–5 run production (starters dominate F5; bullpen barely matters → different, often sharper, signal). F5 is structurally softer at most books.

### B.3 Training targets
- Stage 1 (full game): per-side runs scored (`mart_game_results` home/away final score). Stage 1 (F5): per-side runs through 5 innings (derivable from `mart_pitch_play_event` / play-event marts).
- Stage 2: joint (home, away) empirical dependence.
- **Evaluation target is the distribution, not a point:** CRPS and NLL of the predictive total vs actual (your gate already speaks `crps_ensemble`/`nll_ensemble` — B plugs in as a `SamplesSpec` adapter with zero gate changes).

### B.4 Validation gates (must clear before any derivative bet)
> **Prerequisite — derivative-odds backfill (guide story E2.0):** gate 4 compares the model to each derivative's *own historical close* (F5 / team-total / alt-total), so that backfill (Odds API historical event-odds, post-2023-05-03; shares the WS-E prop-ingestion plumbing) **must complete before this gate can run.** Those odds are **eval/CLV-only — never model features.** Independent of and parallel to the model build, but the long pole for the derivative value path.
> **Market-blind (Principle 3):** the per-side models (Stage 1–3) take **zero** market/odds/line features — the market already prices our baseball info, so a model that sees the line just relearns it. Market data enters only here (eval/CLV) and in WS-C/D. Guard with a CONTRACT-style assertion on the feature matrix.

1. **Distributional accuracy:** `crps_ensemble` of the convolved total beats the current `total_runs` champion's `crps_normal` under purged CV (A.1), via `evaluate_promotion` criteria 1–6.
2. **Honest variance:** std(predictive total) per game must track realized dispersion — PIT histogram flat / coverage at nominal (your calib_80 metric ≥ 0.80, which the current totals model fails).
3. **Un-pause condition (carry the existing rule):** to bet *main-line* totals it must still beat **both** prior-predictive NLL (2.8893) **and** prior-naive Brier (0.248) on rolling-60 live — unchanged. The *new* path to value is derivatives, which are gated separately:
4. **Derivative edge:** for F5/team-totals/alt-lines, the bettable claim is "our distribution prices this line better than the book's derived line." Gate = positive CLV vs the *derivative's own close* + PBO < 0.2 + DSR > 0 (WS-A). Do **not** assume F5 efficiency; measure it.

### B.5 Storage & serving
- New sub-model version `totals_generative_v1` writing to `mart_sub_model_signals` (long SCD-2 in `baseball_data.betting`) and/or a dedicated `totals_generative_signals` table mirroring `offense_v2_signals`. Emit: `total_mu`, `total_sigma`, full quantile grid (P05…P95), `p_over_<line>` for the live line, per-team-total params, F5 params, and the copula ρ used.
- Register in `sub_model_registry.yaml`; backfill leakage-safely (respect the `[[project_layer3_signal_leakage]]` rule — sub-model artifacts must not have seen the scored season).

### B.6 Distribution UX (satisfies "show the user why")
For each surfaced pick, render from the stored predictive samples:
- The predictive **total-runs distribution** (or run-diff for H2H) as a density/histogram, with the **market line** as a vertical rule and the **favorable-side mass shaded** = the model's probability and visual edge.
- Alongside: the existing per-pick **SHAP attribution** (`pick_explanation`, Story 30.15) as the top ± drivers.
- For totals, a small **alt-line ladder** (P(over) at each alternate line) showing where the model most disagrees with the book's ladder.

---

## Workstream C — Closing-Line / CLV Model

### C.0 The target reframe
Predicting the *game* is ~0.50-Brier noise next to the market. Predicting the **closing line from the opening line** is a higher-SNR problem: the close is the open plus information arrival and sharp action, and that move has learnable structure. If you can anticipate the move, you capture CLV *by construction* — and CLV stabilizes far faster than ROI (your own §9 / CLV-backtesting rationale). This converts Layer 4 from "is disagreement actionable?" to "**predict the close.**"

### C.1 What already exists to build on
- `mart_odds_line_movement`: opening + pre-game implied probs, **signed Δ (pregame − open)** for h2h and totals, Bovada-keyed, 2021–2025 (Odds API) + 2026 (Parlay API hourly with leakage guard).
- `mart_closing_line_value`, `mart_prediction_clv`, `mart_clv_labeled_games` (12,797 labeled; truly-live 441 h2h / 385 totals), `feature_pregame_meta_model_features` (7 feature groups), and the **converged Bayesian meta-model** (12.4). C extends this from "P(CLV>0) on our own signals" to "predict the actual close."

### C.2 Model structure (two linked heads)
**Head 1 — line-movement regression (the core new model).**
- Target: **Δ(open→close)** of the fair (de-vigged) line, separately for h2h (prob units) and totals (run units). Predict both the point move and its uncertainty (NGBoost Normal or quantile).
- Features (this is the one place market data is not only allowed but central — Layer 4):
  - Opening line + opening cross-book dispersion (`mart_bookmaker_disagreement`).
  - **Sharp-book state** (shared with WS-D): Pinnacle open and current from `mlb_matches_raw`; Bovada−Pinnacle gap.
  - Early line movement in the first hours after open (from Parlay API hourly snapshots / `mlb_line_movement_raw`).
  - Public betting % (`feature_pregame_public_betting_features`) — money% vs ticket% divergence is a sharp/square indicator.
  - **Lineup/scratch & weather *deltas*** relative to when the line opened (the information the market is about to price): lineup confirmation state (`feature_pregame_lineup_state` SCD-2), starter scratches (`feature_pregame_starter_status`), weather forecast shifts (`feature_pregame_weather_status`).
  - Your Layer-2 baseball signals as a *fair-value anchor* (the model's view of where the line "should" go).

**Head 2 — P(beat the close), i.e. meta-labeling (AFML ch. 3).**
- This is your 12.4 meta-model, kept and sharpened. Primary model proposes a side at the current price; Head 2 outputs P(this bet ends with positive CLV). It consumes Head 1's predicted move + uncertainty as its strongest feature.
- Keep h2h and totals thresholds tuned independently (base rates differ: ~52.5% vs ~46.2% CLV-positive).

### C.3 Training targets & labels
- Head 1: realized Δ(open→close) per game/market from `mart_odds_line_movement` (full 2021–2025 history is usable here — line movement is *market* data, not contaminated by your sub-model leakage issue).
- Head 2: binary positive-CLV label from `mart_clv_labeled_games` (use the **truly-live** subset for honest OOS; the historical-proxy backfill is for exploratory fitting only, clearly flagged).

### C.4 Validation gates
1. **Head 1 skill:** predicted Δ beats a naive "no movement" and a "momentum" baseline on out-of-sample MAE under purged CV. Directional accuracy of the move > 50% with bootstrap CI above 0.5.
2. **The real gate — forward CLV:** following Head 1/Head 2 recommendations yields **positive mean CLV over ≥100 forward live games** (your existing Story 12.5 gate; the serve went live 2026-06-16). This is the binding, honest test.
3. **Overfitting:** PBO < 0.2 and DSR > 0 (WS-A) on the selective-bet return series before any real stake.
4. **No leakage:** every feature is point-in-time as-of prediction (your SCD-2 + `prediction_snapshots` reconstruction already enforces this — reuse `validate_scd2_reconstruction.py`).

### C.5 Operational/timing edge (cheap, high-value)
Head 1 will show that the largest predictable moves cluster around **lineup releases, late scratches, and weather shifts** (architecture Principle 5). The model is only half the play; the other half is *latency* — ingesting and acting on those events before the soft book reprices. Concretely: tighten the Dagster `lineup_monitor_sensor` / pregame-snapshot cadence and decommission the superseded `task_lineup_monitor` (the inventory flags it still racing). Measure your ingestion-to-line-move lead time; that lead *is* the edge Head 1 monetizes.

---

## Workstream D — Cross-Book Sharp-Anchor Strategy

### D.0 Benchmark — RESOLVED (2026-06-17)
**Decision:** Bovada is the book *you* bet; beta users also bet **Caesars and FanDuel**. **Pinnacle is the sharp anchor.** Bovada/Caesars/FanDuel are all soft/recreational books; Pinnacle is the sharp reference (consistent with your existing CLV-vs-Pinnacle-close tests).

**Consequence — the strategy is multi-book and book-aware:**
- The method is "**bet the soft book toward Pinnacle when they diverge**": Pinnacle's de-vigged price is the fair-value estimate; a soft book lagging it is the edge.
- Because users bet *different* soft books with *different* lines, the edge is computed **per soft book**, not once: `edge_book = pinnacle_fair_prob − book_implied_prob` for `book ∈ {bovada, caesars, fanduel}`. The same game can be a bet at Caesars and a pass at FanDuel — recommendations are surfaced per book (see §5.1).

### D.1 Why this is the most likely H2H edge
Head-on H2H is dead (4 confirmations). But the contrarian/disagreement signal had a flicker (Epic 28.6a "AMBER," magnitude roi_devig +0.197 — underconfident-on-chalk, not contrarian). The sharp-anchor reframes that: instead of *your model* vs the market, it's **the sharp market vs the soft book** — a much stronger predictor than your sub-models, and exactly the signal you killed prematurely (Bovada−Pinnacle gap).

### D.2 Strategy structure
- **Signal (per soft book):** `edge_book = pinnacle_fair_prob − book_implied_prob` (de-vigged both sides), for `book ∈ {bovada, caesars, fanduel}`, per game/side, computed at decision time.
  - `pinnacle_fair_prob` from the timestamped Pinnacle feed (Odds API, `regions=eu`), de-vigged. Use the freshest Pinnacle price at the user's bet time, not just the close.
  - Add cross-book dispersion and sharp-vs-soft consensus (`mart_bookmaker_disagreement`, your 37-book breadth).
- **Meta-label (AFML ch. 3, shared with WS-C Head 2):** P(this divergence bet is profitable / beats Bovada's close). Train on historical Bovada-vs-sharp divergences and their realized CLV/outcome. Not every gap is real — some are stale-quote artifacts; the meta-model learns which.
- **Bet rule:** take the Bovada side that the sharp consensus favors, *only* when (edge > threshold) AND (meta P(profit) > tuned threshold) AND (sharp quote is fresh, not stale). Size via σ-aware Kelly (Story 22.4) on the meta-probability.

### D.3 Data requirements — RESOLVED
- **Live sharp feed exists:** timestamped Pinnacle from **The Odds API** (`regions=eu` — Pinnacle is geo-blocked from direct US access). This is the live fair-value anchor for execution.
- **History:** Odds API back to **2024** (extendable). 2024–25 soft-book lines are degraded/near-flat in places (your `[[project_layer3_signal_leakage]]` caveat) — weight/flag them; 2026 live is the clean window. **If the divergence→profit model is data-starved, extend Odds API history before 2024** (cheap relative to the value of an honest backtest).
- Also retains `mlb_matches_raw` Pinnacle open/close (~30–40% coverage) as a secondary/training source.
- Per-book soft lines (Bovada/Caesars/FanDuel) are already in your Odds/Parlay breadth (`mart_odds_outcomes`, 37-book).
- **Stale-quote guard:** freshness flag per Pinnacle price; never anchor to a quote older than a configurable window (recommendation must show "as of" timestamp to the user).

### D.4 Validation gates
1. **Backtest on training-era divergences:** does "bet soft toward sharp" produce positive CLV-vs-Bovada-close and positive de-vig ROI, *net of vig*, on the honest subset? Weight/flag degraded 2024–25 Bovada lines vs sharp 2026 (your `[[project_layer3_signal_leakage]]`/degraded-line caveats apply).
2. **Coverage realism:** how many games/day actually present a fresh, exploitable Bovada-vs-sharp gap above threshold at *your* bet time? (If it's 2/week, that's fine but changes sizing/expectations.)
3. **Overfitting:** PBO < 0.2, DSR > 0 (WS-A).
4. **Forward live CLV** ≥100 games, positive mean — same binding gate as WS-C.

### D.5 Relationship to WS-C
C and D are two heads of the same market model and **must share plumbing**: the sharp-book ingestion, the de-vig utilities, the line-movement features, and the meta-labeling head are common. Build the market-data layer once; C predicts the *move*, D exploits the *cross-book gap*. The meta-model (12.4, converged) is the shared selector.

---

## Workstream E — Player Props & Derivative Markets

### E.0 Why
Player props are the softest, most numerous baseball markets — books price hundreds of lines semi-mechanically, so attention per line is minimal — and they're the best fit for our existing player-level depth (EB posteriors, the `starter_ip_v1` NegBin over outs, archetype matchups). This is a **betting-edge track** (sibling of A–D), built by applying WS-B's distributional machinery to *player* outcomes. **Gated behind WS-A:** with hundreds of markets the multiple-testing risk is the highest of any track, so PBO/DSR is applied **per market with a multiple-comparison correction.**

### E.1 Data
The Odds API event-odds endpoints — live: `cost = markets × regions` per event; historical: `10 × markets × regions` per event per snapshot, with additional-market history only after 2023-05-03. At the 5M-credit/month limit, *both* live ingestion and a full historical backfill are comfortably affordable, so the binding constraint is **modeling discipline, not API cost.** Curated soft books + Pinnacle as the sharp prop anchor where offered.

### E.2 Model
Price each prop from the player's predictive distribution: `pitcher_outs` directly from `starter_ip_v1`'s NegBin over outs; `pitcher_strikeouts` from a starter strikeout distribution; `batter_total_bases`/`hits` from a per-batter PA-level outcome distribution (EB wOBA/ISO + matchup) — all conditioned on expected playing time (Story 33.1). De-vig the book's two-sided price; `edge = model_prob − devigged_market`; show Pinnacle as the reference.

### E.3 Validation
`calib_80 ≥ 0.80` per prop type; edge must survive **PBO < 0.2 and DSR > 0 per market** (multiple-comparison corrected — the crux); positive forward CLV vs the prop's own close; coverage realism. Advisory only — props carry heavy vig and low limits, so most edges wash out and honesty matters.

---

## Workstream F — Feature-Engineering Audit (standalone)

### F.0 Why
Workstreams A–D assume the feature surface is roughly fixed. But we've never systematically swept ~690 features for overlooked structure, and the near-uniform Layer-3 stacking weights are a tell for *both* heavy redundancy and unexploited interactions. This is a cheap, one-time analytical sweep — not a model — that yields a prioritized backlog of feature-add experiments, each then validated through the WS-A gate. It is deliberately separated so feature spelunking doesn't stall the edge tracks.

### F.1 Method
Three passes, run as offline batch over the S3-Parquet training matrix:
1. **Inventory & taxonomy** — every model-input column tagged by family, source, transform, window, platoon split, and *live (pre-game) coverage* (the Story-30.3 imputation risk surfaces here: features dense post-game but sparse at morning serve are optimistic in CV).
2. **Redundancy & importance** — reuse WS-A's clustered MDA (A.3) to separate signal-bearing clusters from dead weight and pure substitutes.
3. **Gap analysis (the creative pass)** — enumerate plausible-but-missing constructions and rank by expected value × feasibility: interactions (park × fly-ball pitcher, wind × batted-ball, platoon × bullpen handedness, ump × pitcher CSW), regime-normalized variants (extend Story-27.7 beyond contact), times-through-order / within-start fatigue, rest/travel × bullpen, catcher-pitcher pairing × framing × ump, pace/sequencing from pitch data, lineup construction/entropy.

### F.2 Output & discipline
A scored backlog (`ablation_results/feature_opportunity_audit.md`). Every candidate is point-in-time/leakage-screened, and nothing merges without beating the **champion** (not the floor) under WS-A purged CV. The audit's value is as much *subtraction* (prune dead clusters, shrinking the overfitting surface) as addition.

---

## Workstream G — Minor-League Data & Rookie Priors

### G.0 Why
The EB posteriors shrink low-MLB-PA players toward a generic archetype prior (`k=200 PA`). For a rookie, that discards the most informative thing we have: their actual minor-league performance. A minor→major translation gives a *performance-based* prior, improving rookie inputs to the betting sub-models and forming the data spine for prospect projections (WS-H).

### G.1 Data
Minor-league game logs via the MLB Stats API minor `sportId`s (AAA=11, AA=12, A+=13, A=14); AAA Statcast (Hawk-Eye) where available (2023+); FanGraphs/prospect xrefs + ETA. All cheap to ingest (no per-call billing).

### G.2 Model — Major League Equivalencies (MLEs)
The crux is the **translation factor**: convert AAA/AA wOBA, K%, BB%, ISO (and Statcast contact metrics where present) into MLB-equivalent rates, adjusting for level, league run environment, and park. Calibrate against graduated players (their pre-call-up minor line vs. their realized MLB line) — this is a supervised, backtestable problem, not a guess. Output a per-player MLB-equivalent line + uncertainty that **replaces the generic archetype prior** in `eb_batter_posteriors` / `eb_starter_posteriors` for low-MLB-PA players.

### G.3 Validation
Rookie calibration before/after, under WS-A purged CV; MLE backtest error on the graduated-player holdout. Strict as-of discipline (only minor-league stats available before the MLB game).

---

## Workstream H — Player Projections Suite & Fantasy Vertical

### H.0 Why & scope
A second B2C product (fantasy advice, Dynasty-focused) is an underdeveloped market that fits our player-modeling depth. Its engine is a **full distributional player-projections suite** — and that engine is reusable analytics, not just a fantasy feature. This is the largest new scope; phase it (MLB rest-of-season first, then multi-year/Dynasty + prospects) and expect it to spin out into its own spec as it grows.

### H.1 Model structure
- **Rest-of-season (ROS), distributional.** Per-player projections for the fantasy categories as **P10/P50/P90 distributions**, not points — reuse WS-B's per-player distributional approach, blending EB posteriors + ZiPS/Steamer (weight by sample) + recent form. Hitters: AVG/OBP/SLG, HR/R/RBI/SB, wOBA/wRC+. Pitchers: ERA/WHIP/K/W/SV/IP/FIP.
- **Playing time is the dominant driver.** Counting stats are volume × rate; project PA/IP from the Story-33.1 P(start)/role model + depth charts. A great rate projection on wrong volume is useless.
- **Multi-year / Dynasty.** Position-specific aging curves → N-year trajectories with uncertainty that *widens* with horizon; Dynasty value = risk-discounted multi-year projection.
- **Prospects (depends WS-G).** MLE-translated minor-league lines + ETA → MLB-equivalent projections and prospect Dynasty value.
- **League-context value.** Convert raw projections to fantasy value (z-scores / SGP / auction $), parameterized by league settings (categories vs. points, roto vs. H2H, redraft vs. Dynasty, roster depth).

### H.2 Validation & framing
Backtest projections vs. realized seasons (rank correlation + distribution calibration/PIT), with **ZiPS/Steamer/industry as the baselines to match-or-beat** — the honest bar, stated plainly. Advisory only; projections + rankings + advice, users manage their own teams. Serve precomputed to Railway PG; render the distribution on the existing player pages.

---

## 5. The distribution-display requirement (cross-cutting)

The user requirement — *show the probability distribution behind each pick* — is satisfied natively by WS-B and reused by C/D:

- **Totals & run-line:** WS-B predictive samples → density plot + market line + shaded favorable mass + alt-line ladder.
- **H2H:** run-differential distribution from WS-B → P(home win) as mass above 0; or the meta-model's P(CLV>0) shown as a conviction band.
- **Every pick:** SHAP `pick_explanation` (30.15) as the top drivers, beside the distribution.
- Render in the existing Streamlit app; the data already flows through `daily_model_predictions` + the signal marts. No new serving infra — add the quantile/sample columns to the prediction write path.

### 5.1 Product note — advisory, B2C, book-aware (RESOLVED)
The end product is **strictly advisory**: it surfaces recommendations + distributions; users place their own bets (no auto-betting; per `[[feedback_no_auto_betting]]` and US market constraints). Two implications:
- **Book-aware recommendations.** A user's view is filtered to *their* book (Bovada / Caesars / FanDuel). The same game shows a different edge — or no edge — depending on which soft book they bet, because `edge_book` is computed per book against Pinnacle (§D.0). Store `book` on each recommendation row; let the user pick their book in the UI.
- **Show the anchor honestly.** Each pick displays: the user-book line, the Pinnacle de-vigged fair value, the gap, the predictive distribution (WS-B), the "as of" timestamp, and the conviction (meta-model P). The user is making the decision — give them the inputs, not just a verdict.

---

## 6. Sequencing & dependencies

```
WS-A (CV-hygiene + overfitting)  ──────────────┐  (gates everything; PBO/DSR required before any go-live)
   │ purged CV, uniqueness, clustered importance │
   └── A.4 PBO/DSR utilities ────────────────────┤
                                                  │
WS-B (per-side generative totals) ── independent ─┤── unblocks totals product + distribution UX
   built on offense_v2 + copula + convolution     │
                                                  │
Market-data layer (shared) ───────────────────────┤
   de-vig utils, sharp-book ingest, line-move feats│
   ├── WS-C (predict the close / CLV) ────────────┤
   └── WS-D (cross-book sharp-anchor) ────────────┘
        (D.0 benchmark decision blocks D)

WS-E (player props) ── built on WS-B machinery; gated behind WS-A (per-market PBO/DSR) ── ingestion is independent plumbing
WS-F (feature audit) ── reuses A.3 clustered MDA ── cheapest right after WS-A; output = feature backlog
WS-G (MiLB + MLEs) ── independent data work ──────── feeds rookie priors (betting) AND WS-H prospects
WS-H (projections / fantasy) ── reuses WS-B machinery + 33.1 playing-time ── prospects blocked by WS-G; highest standalone B2C value
```

### 6.1 Compute & cost pattern (RESOLVED)
Given the existing infra spend (Dagster+, Railway, AWS, Snowflake, The Odds API), keep heavy compute **out of the warehouse**:

- **Extract-once, compute-on-parquet.** Reuse your existing local-parquet-cache pattern (the dev workflow's "first run pulls from Snowflake, subsequent runs read local parquet"). For batch research jobs: materialize the training matrix to **parquet in S3** once, then run all iterations (CV folds, copula sampling, CSCV resamples) against parquet — zero repeated Snowflake scans.
- **Where each job runs:**
  - *WS-A* (purged CV, clustered MDA, PBO/CSCV): embarrassingly parallel over folds/resamples → batch on **EC2** (spot is fine; it's offline research), reading parquet from S3, writing reports + artifacts back to S3. Cap CSCV partition count and bootstrap draws to bound cost; these are one-off/periodic, not daily.
  - *WS-B* copula sampling: the expensive part is N joint draws per game. Vectorize (NumPy) and cap N (e.g. 10k draws/game is plenty for quantiles); run as a **daily batch op in Dagster** scoring only the upcoming slate, writing params + a quantile grid (not raw samples) to the signal mart. Store full samples in S3 only if the UX needs them.
  - *WS-C/D* market models: lightweight (GBM/NGBoost + de-vig arithmetic) → fold into the existing daily Dagster pipeline reading the Pinnacle feed.
- **Serving stays thin:** write only params + quantiles + per-book edges to `daily_model_predictions` / signal marts (Snowflake), so the Streamlit app reads small rows, not sample arrays.
- **Don't `dbtf build` unscoped** (your own cost rule) — new marts use `--select` scoping and incremental MERGE like the rest.

**Recommended order:**
1. **WS-A.1–A.4** (2–3 wks). Produces purged CV + PBO/DSR. Re-baseline current champions honestly.
2. **In parallel:** **WS-B Stage 1–3** (build on `offense_v2`; copula + convolution) and the **shared market-data layer** for C/D.
3. **WS-C Head 1** (predict the move) → **WS-D** (cross-book gap) on the shared layer; both feed the existing 12.4 meta-model (Head 2).
4. **Gate-to-shadow** each strategy with PBO < 0.5; **gate-to-live** with PBO < 0.2 + DSR > 0 + ≥100 forward live games positive CLV.
5. **Distribution UX** ships with WS-B.
6. **WS-E (player props)** builds on WS-B's distributional machinery (`starter_ip_v1` prices `pitcher_outs` directly); ingestion is independent plumbing; go-live is gated per-market behind WS-A.
7. **WS-F (feature audit)** runs right after WS-A (reuses A.3) — a cheap sweep whose backlog feeds every later model.
8. **WS-G (MiLB)** is independent data work that should start **early** (it's cheap and unlocks the highest-value vertical); **WS-H (projections/fantasy)** reuses WS-B's machinery + the playing-time model — start with MLB ROS projections, add Dynasty/prospects once WS-G lands. Per §B2C-value (see the implementation guide §7A), WS-H is plausibly the program's highest standalone B2C value despite sitting last in the dependency order.

---

## 7. Decisions — RESOLVED (2026-06-17)
1. **Benchmark/book:** Bovada = book you bet; beta users on Caesars + FanDuel; **Pinnacle = sharp anchor.** Strategy is multi-book and book-aware (§D.0, §5.1).
2. **Live sharp feed:** timestamped **Pinnacle via The Odds API** (`regions=eu`); history to 2024, extendable (§D.3).
3. **Posture:** strictly **advisory, B2C**, no auto-betting (§5.1). C and D are recommendation engines.
4. **Compute:** local or EC2; heavy jobs read **parquet cached from Snowflake → S3**, not in-warehouse; cost-optimize (§6.1).

### Remaining sub-decision
- **History depth for WS-D/C training:** start with Odds API 2024+; extend earlier only if the divergence→profit model (D) or the line-movement model (C) is data-starved after the first honest backtest. Decide *after* WS-A tells you whether the apparent signal survives PBO.

---

## 8. What success looks like (12 months)
Not "we beat Bovada's closing total." Realistically:
- A **per-side distribution** that prices F5/team-totals/alt-lines with measured, overfitting-audited edge in softer markets.
- A **closing-line model** with demonstrated positive forward CLV — the leading indicator that real edge exists.
- A **sharp-anchor H2H** strategy that bets soft books toward sharp consensus, selectively, with DSR > 0.
- A **trustworthy number** (PBO/DSR) on every claimed edge, so "we're getting closer to something real" becomes a measured fact rather than a hope.
- **Player-prop projections** priced against the soft prop markets, overfitting-audited per market (WS-E).
- A **pruned, audited feature surface** (WS-F) and **minor-league MLEs** (WS-G) closing the rookie-prior gap.
- A **distributional player-projections suite** powering a Dynasty-focused fantasy vertical (WS-H) that matches or beats ZiPS/Steamer — a second B2C product from the same modeling spine, and plausibly the highest standalone B2C value (see implementation-guide §7A).
```
