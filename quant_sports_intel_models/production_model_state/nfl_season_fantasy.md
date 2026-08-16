# Production model state — NFL Season Fantasy (NF1.x projections + NF-C0 scoring + NF-D recalibrations)

_PROD-STATE-1f · written 2026-08-04 · grounded in the LIVE served S3 api-cache artifact (live-read 2026-08-04), the NF ablation memos (`quant_sports_intel_models/football/nfl/fantasy/ablation_results/`), and the serving/model code — NOT roadmap prose. best_alpha = 0 throughout; this is a projection PRODUCT, not a betting market._

> **One-line state:** the served 2026 draft board is the **NF1.5 market-aware refined ordering** (`projection_source="nf1_5"`, `model_version="nfl_fantasy_nf1_5_v1"`) laid over **MVP-1's calibrated point levels and 80% bands** (NF1.8 rookie / NF1.9 veteran / NF1.6 K-DST intervals, all floors re-validated ✅ 2026-08-01), published as build-time static JSON to `s3://credence-prod-s3-api-cache/fantasy/nfl/2026/` and scored into any league by the NF-C0/NF-C0b import+scoring machinery. **The core is stable, calibrated, and honestly framed** (`market_lean_note` in the live payload; the public track-record claim's own CI includes zero and the page says so). **One ratified model win is deliberately HELD from serving** (NF-D16 rookie level recalibration — serving flip OFF), and **NF-D21 (🟢 READY, unstarted as of this read) is the PM-judgment story that would flip it ON at a board-blind λ=0.5 shrink.** The long open-story list (20 carded + 12 spec one-liners) reflects that this is the ACTIVE LAUNCH product, not instability in what is served.

---

## (1) What it predicts + market/output

- **Target:** full-season NFL fantasy production per draft-relevant player for the upcoming season (2026) — a **raw season stat line** (games, pass/rush/receiving attempts-yards-TDs, fumbles, two-point conversions, long-TD bonuses, K field-goal distance mix, DST events + points/yards-allowed **expected-games-per-bucket** distributions), plus convenience `fp_{std,half,ppr}` scorings and a **per-player 80% interval** (`fpP10/fpP90` + `uncType` provenance).
- **Coverage (live-read 2026-08-04):** **858 players** = 784 QB/RB/WR/TE (703 veterans + 81 rookies) + 74 K/DST (42 K + 32 DST). Base season 2025 → projection season 2026.
- **Output surfaces (all gated behind `require_fantasy_access` / `fantasy_comp` beta except the public track record):** `/fantasy/projections`, `/fantasy/rankings`, `/fantasy/league-board` (NF3), the **draft optimizer** `/fantasy/draft` (NF-C2, client-side snake-draft engine), player pages with history + feature-transparency panels (NF3.1/3.3/3.4), **My Teams** (NF-C6), **league import + manual settings editor + client-side custom-league scoring** (NF-C0/NF-C0b), and the **public** `/fantasy/track-record` receipts page (NF3.2).
- **Not a market model.** No odds, no edge, no bet recommendation anywhere on the surface; the roadmap's own gate for this vertical is "product metric + calibration, NOT the betting PBO/DSR deflation" (deflation is still run — to *record nulls honestly*, see field 10). `best_alpha = 0`.

## (2) Architecture — champion + why it won

### The single most important structural fact: TWO stacked models — "level" vs "ordering"

| Layer | Module | What it owns |
|---|---|---|
| **MVP-1 / "fastpath"** (`nfl_fantasy_fastpath_v1`) | `football/nfl/fantasy/season_projection.py` (pure) + `run_season_projection.py` (IO) | The **point LEVEL**, the raw stat line, and every **80% interval**. Heuristic / empirical-Bayes construction, not a fitted learner. |
| **NF1.5 refined ordering** (`nfl_fantasy_nf1_5_v1`) | `nf1_5_model.py` + `run_nf1_5.py` | The **within-position ORDERING only**. Learned per-position market-aware blends. Re-assigns MVP-1's own calibrated point **multiset** via `apply_learned_ordering` (a within-position monotone quantile remap) — *"the point projections and their 80% bands are MVP-1's calibrated numbers; NF1.5 changes WHICH player gets which level, nothing else"* (`export_draft_board_json.py:62-79`). |

This split is a load-bearing lesson (NF1's own level-vs-ordering bug): a learner trained on ≥6-game realized outcomes carries survivorship-inflated LEVELS, so a learner selected on ORDERING is used for RANK only, never for LEVEL.

### MVP-1 (the level model) — construction + every shipped constant

Veterans: a **3-yr recency+games-weighted per-game line** (`_RECENCY_DECAY=0.6`, `_WINDOW_YEARS=3`), EB-shrunk `w=g/(g+5)` (`_SHRINK_K=5.0`) toward a conservative positional median prior, × an **expected-games** estimate blending depth-chart role with base-season durability and usage (`_USAGE_ROLE_BLEND=0.4`; RB/WR implied games `3+14·snap_share`, TE `6+55·target_share`), with the NF-D2/D4/D11 correction layers: team-change opportunity rescale (`_MOVER_OPP_BLEND=0.35`, cap 1.6, RB/WR/TE only), QB Vegas-environment tilt (`_ENV_TILT_BLEND=0.06`, clamp [0.92,1.10], QB only), injury-status games caps (`RES/PUP/NFI=4.0, SUS=7.0`, `_INJURY_OVERRIDE_BLEND=0.7`), and the **NF-D11 return-from-absence prior** (`ratio` family @ blend 1.0 — a multiplicative haircut on expected games for players who missed the whole base season; §0.5-selected, PBO 0.0). `_XFP_TD_BLEND=0.0` — the NF-D7 TD-regression heuristic blend is **OFF** (recorded null).

Rookies: **slot curve** — a per-position log-log draft-slot → rookie-fantasy-points power law, shrunk 15% to the positional mean (`_ROOKIE_SHRINK_TO_MEAN=0.15`), clipped at the P93 of historical rookie fp (`_ROOKIE_FP_CEILING_Q=0.93` — a top pick can't exceed a P93 rookie outcome), × the NCAAF-P1A residual nudge (`residual_lambda=0.12`, clipped [0.75,1.35]), then allocated to a raw stat line via positional median composition and rescaled so the scored PPR equals the bounded target. The rookie leg is **not learned** (served stamp `nf1_5_learner="rookie_slot_curve"`).

### NF1.5 (the ordering layer) — per-position champions + fitted hyperparameters

All four winners are variants of one class, **`PosRefinedBlend`** (`nf1_5_model.py:375-415`):

```
w_i   = clip(blend_w − disp_slope · z(market_dispersion_i), 0, 1)
score = (1 − w_i) · z(anchor_i) + w_i · z(market_score_i)
```

Winners are stored as DATA (`ablation_results/nf1_5_feature_combination_bakeoff.json`) and read back by `run_nf1_5.py --mode build`:

| Pos | Champion | Fitted hyperparameters | Inner (market-blind) anchor (from NF1.1) |
|---|---|---|---|
| QB | `pos_learned_adaptive_blend` | `blend_w=0.9221`, `disp_slope=0.1730` | `pos_gbm` — LightGBM `n_estimators=150, num_leaves=18, lr=0.0370, min_child_samples=7, reg_lambda=1.795` |
| RB | `pos_blend_flat` | `blend_w=0.9477` | `pos_ridge` — `alpha=0.9504` |
| WR | `pos_learned_blend` | `blend_w=0.8494` | `pos_ridge` — `alpha=1.3801` |
| TE | `pos_learned_blend` | `blend_w=0.6473` | `pos_similarity` — kNN comparables `k=35, weight_power=2.638, mvp1_emphasis=3.030` |

`anchor="learned"` fits the NF1.1 per-position winner **in-fold** as the inner anchor. The high `blend_w` values are the honest read: **QB/RB/WR lean heavily on consensus** (served `market_lean`: QB `market-led-adaptive`, RB/WR `market-led`, TE `market-blend`).

**Why it won:** the whole NF1→NF1.5 arc (field 10) proved the **market-blind ceiling** three+ ways, then NF1.3/NF1.5 showed the market-aware blend is the **first board to beat ADP** on the product metric. NF1.5 stage-1's refined blends beat the NF1.3 incumbent at all four positions on held-out `top_tier_rho`; **none cleared the betting deflation gate (PBO/DSR)** — the recorded `refined_gates` are all `false`, and it ships on the **product metric + calibration + PM ruling**, the vertical's declared gate, under the standing "tracks the market + adds our signal, never an independent edge" posture. NF1.5b's serving re-grade (2026-08-01): served refined board vs ADP pooled Δρ **+0.022** vs the previous MVP-1 board's **−0.059**.

### ⚠️ MEASURED LEVEL BIAS — the served point LEVELS sit systematically BELOW realized (NF-TR1 finding, 2026-08-07)

The public track-record page surfaced a systematic **downward LEVEL SHIFT** of the served point projections vs realized outcomes — a property of the **LEVEL model (MVP-1)**, NOT the ordering (NF1.5) and NOT the intervals in isolation. ⭐ **It is a LEVEL shift, not a fat-tails / top-end miss:** the MEDIAN tracks the MEAN (a tail miss leaves the median near zero and drags only the mean; here the whole distribution is shifted down).

Measured, pooled **1,165 player-seasons 2019–2025** (unconditional per-position means — same players both sides, ⛔ NOT conditioned on the outcome):

| | mean bias | median bias | our/actual |
|---|---|---|---|
| Pooled | −37.7 | −34.5 | — |
| QB | −19.8 | −18.7 | 0.923 |
| RB | −49.1 | −44.0 | **0.693** |
| WR | −37.5 | −34.6 | 0.778 |
| TE | −26.8 | −24.9 | 0.816 |

Every position is negative, every season is negative (2019 −44.8 → 2025 −26.5, **improving** over time); **RB worst, QB nearly calibrated.**

**Shape / cause (two counts, one intentional, one a real miscalibration):** the bias ordering (RB>WR>TE>QB) matches the live board's projected-games ordering EXACTLY (RB 13.9 / WR 14.4 / TE 14.8 / QB 15.1 of 17), so the **expected-games (availability) discount carries MOST of it** — the served number is deliberately an **EXPECTED** (availability-weighted) point total, structurally lower than the "if-healthy" numbers most competitors publish. But availability does **not fully close it**: RB's games ratio 0.818 vs the measured 0.693 leaves **~15% unexplained at the worst position**. That residual is almost certainly the **NF-D11/NF-D15 effect** — MAE is minimized at the conditional median, so it *pays for pessimism* on a right-skewed target (fantasy points are right-skewed), and NF-D15 directly measured pooled bias moving FURTHER from zero while MAE improved. So the level is conservative on TWO counts (availability = intentional/honest; median-optimal pessimism = a genuine miscalibration).

**What it affects — and doesn't:**
- ⛔ Does **NOT** touch the NF-TR1 ranking claim: Δρ is rank-based and **invariant to any monotone level transformation** — the +0.022 stands.
- ✅ Ranking / draft ORDER is fine (why the product still works — you draft in the right order).
- 🔴 **Any ABSOLUTE-points use is affected**: track-record page credibility (a reader sees Bijan 236 proj vs 371 actual and reads "broken"), trade valuation, start/sit margins, projected league totals — the absolute number is **not comparable to another site's "if-healthy" number**.

> ### ⚠️⚠️ AMENDED BY NF-RECAL1 (2026-08-08) — THE MAGNITUDE ABOVE IS POPULATION-DEPENDENT AND DOES NOT REPRODUCE
>
> NF-RECAL1's premise check re-measured this bias on the veteran walk-forward panel (2019–2025) with
> the tier fixed by the INCUMBENT's own projection (NF1.1's fixed-anchor rule). **The SIGN and the
> per-position ORDERING reproduce at all four positions; the MAGNITUDE does not — it is ~3× smaller.**
>
> | population (2019–2025 veterans) | n | mean bias | our/actual | % zero outcome |
> |---|---|---|---|---|
> | universe, unconditional | 8,099 | **+0.84** | 1.013 | 0.324 |
> | draftable tier (top 156/season), **INCUMBENT anchor** ⭐ | 2,028 | **−12.85** | 0.919 | 0.075 |
> | draftable tier (top 156/season), REALIZED anchor ⛔ | 2,028 | **−64.80** | 0.661 | **0.000** |
> | played ≥6 games ⛔ | 4,708 | −23.83 | 0.773 | 0.024 |
>
> ⭐ **The `% zero outcome` column is the mechanism, and it is the tell.** Anchoring the tier on the
> REALIZED outcome removes **100%** of the zero-outcome seasons; the incumbent anchor keeps 7.5% and
> the unconditional universe 32.4%. Every zero-outcome row is one the projection necessarily
> over-projects, so removing them mechanically manufactures a downward bias — which is **caution 1
> below, applied to a LEVEL statistic instead of the decile table it was written for.** The −37.7
> figure sits between the two outcome-conditioned readings and above the honest one.
>
> ⇒ **The honest statement is "the draftable tier runs ~13 PPR cold, RB worst (−21.5) and QB
> essentially calibrated (−0.6, our/actual 0.997)", not −37.7 board-wide.** ⛔ Do not re-derive a
> correction from the −37.7 figure.
>
> ⭐ **AND THE TIER-VS-UNIVERSE TENSION IS REAL EVEN AT THE HONEST SIZE, WHICH IS THE FINDING A
> SUCCESSOR NEEDS.** A correction fitted on the incumbent-anchored TIER is applied BOARD-WIDE at
> serving time, and NF-RECAL1 measured what that costs: every recalibrating arm moves the UNIVERSE
> bias from the incumbent's **+0.84 to +5.5…+7.1** while improving the tier. The board is not
> uniformly cold — it is cold at the top and slightly hot overall — so a single per-position level
> cannot fix both ends, and a correction sized on the −37.7 figure would be worse again. (That figure
> was not reproducible exactly because its population is not recorded; it also includes rookies,
> whose leg is separately and knowingly cold.) Full measurement:
> `ablation_results/nf_recal1_level_recalibration.md` §0–1.

> ### ✅ RESOLVED BY NF-TR2 / NF-TR2b (2026-08-15) — DECOMPOSED, THEN CORRECTED (code-ready, deploy-held)
>
> **The decomposition (Step 1, exact row identity `p−y = r̂(ĝ−g) + g(r̂−r)`, incumbent-anchored
> 2013–2025 tier, n 2,028, bias −12.85):** availability **+3.7** — we slightly OVER-project games on
> the tier, so the injury discount is NOT the cause and stays — and per-game RATE **−16.6**; rate
> ratio RB 0.864 · TE 0.837 · WR 0.848 · QB 0.985 ⇒ a per-position PROPORTIONAL rate lowball. The
> "availability carries most of it" reading above came from the LIVE board's projected games against
> a differently-scoped population.
>
> **The correction that ships (NF-TR2b, `veteran_level_policy`):** a per-position MULTIPLICATIVE
> constant on the per-game rate, `k_q = Σ realized / Σ projected` over the tier rows of the trailing
> 5 target seasons (window DERIVED from the thinnest position's rows/season, not tuned), fitted at
> build time walk-forward (a backtest board for Y is fitted on < Y). Held-out 2013–2025: CRPS 49.34
> vs 49.92, PBO 0.0, DSR 0.9995 (declared 3-trial field) / 0.999 (under NF-B3's field), p 0.0002;
> pooled OOF tier bias −12.85 → +1.41 (RB −21.5→−5.3, WR −15.8→+1.4, TE −9.1→+3.1, QB −0.6→+7.6
> within 2·SE); within-position order EXACT; rookies untouched; games untouched. 2026 board: k = QB
> 0.929 · RB 1.248 · WR 1.100 · TE 1.112 (QB −7.1% / RB +24.8% / WR +10.0% / TE +11.2%) — RBs move
> UP the overall board relative to QBs. ⭐ The full-history mean-match (NF-TR2) was REFUSED by its own
> no-inflation gate — the level is NON-STATIONARY (2007–09 a different regime; QB slightly HOT since
> 2019) — which is why the window exists.
>
> ⭐ **THE BAND IS UNCHANGED, and that is a finding:** the served `knn_norm` band is built from
> REALIZED outcomes of similarly-projected players, so it already sat at the realized level (the point
> sat at 0.46 of its own band). Serving queries the band model at the incumbent-equivalent point so
> the NF1.9-validated band stays byte-identical; NF-RECAL1/B3's scaling of the band with the point is
> what put their CRPS optimum at λ≈0.5. Records: `ablation_results/nf_tr2_level_recalibration.md` +
> `..._b.md`. ⏭️ Post-merge operator: rebuild + republish the board (NF-FRESH2 loop), stage/promote
> `level_model_version` in the NF-G0 registry, re-run `run_interval_revalidation`.

**Two durable methodology cautions:**
1. ⛔ **Do NOT cite the outcome-BUCKETED decile table** (−123 on the top realized decile, +45 on the bottom) as evidence of bias/compression — that pattern appears even for a **perfectly-calibrated** projection because sorting on the REALIZED outcome selects for positive noise; it cannot distinguish bias from correct shrinkage. The **unconditional per-position means above** are the honest statistic.
2. The games figures are from the **live 2026 board** while the bias is from the **frozen backtest** — suggestive, not proof of the availability decomposition; the same gap must be **confirmed on the live board** (2026 has no realized outcomes yet) before scoping any recalibration.

**Remediation:** ✅ **LABELING SHIPPED 2026-08-07** — every projected-points figure is now labelled "Expected pts" (availability-adjusted, tappable definition) with projected games shown beside it on the track record; the page states IN COPY that availability "is not the only reason a projection lands under a finished season" (guarded both directions — Bijan's 15.0/17 games = a 12% discount vs his 36% shortfall, so the row visibly does NOT close on availability alone); ⛔ no surface cites the decile table (guarded across the tree). A **"show if-healthy" comparability follow-on is carded** (if_healthy = expected_pts × 17/expected_games — derivable from the two served fields, restores comparability to other sites' "if-healthy" numbers; still carries the ~15% residual). The remaining real fix = a **per-position level recalibration** (NF-D16 found a per-position constant recalibration independently beat the incumbent, p=0.0052, but it is HELD — ⚠️ a level shift is rank-neutral WITHIN position but REORDERS players ACROSS positions on the shared board, so it needs the whole-board PLACEMENT gate; a §0.5 selection story, post-launch, CRPS not MAE since the inversion is the cause).

### Interval machinery (all in `season_projection.py`, all §0.5-selected except K/DST)

| Population | Shipped form | Key constants | Selected on |
|---|---|---|---|
| **Rookies** (NF1.7→NF1.8) | `qreg_sqrt + cqr[pos,add]` — linear quantile regression (pinball τ=0.10/0.90) on √scale + a **Mondrian (per-position) conformalized-quantile-regression** layer | `_ROOKIE_BAND_FORM="qreg_sqrt"`, `_ROOKIE_BAND_QREG_ALPHA=0.01`, `_ROOKIE_BAND_CQR_MODE="pos"`, `_ROOKIE_BAND_CQR_SCALE="add"`, K=4 cross-conformal folds, min-calib 20 → pooled fallback (recorded, never silent), widener **OFF** (`RESID_SD_GAIN=0.0`) | Winkler/Gneiting interval score (IS80), coverage a per-position **FLOOR** — IS80 183.407; QB 0.741→**0.815**, RB→0.804, TE→0.900, WR→0.835 |
| **Veterans** (NF1.9) | `knn_norm k300` — per-player neighbourhood quantiles in position-normalised prediction space | `_VET_BAND_PER_PLAYER=True`, `_VET_BAND_K=300`, band features `(log_pred, log_sd, games, base_games, snap, returner)`, conformal **OFF** (mathematical no-op — ~29% of conformity scores exactly 0), widener OFF | IS80 205.96→**160.89 (−21.9%)**, coverage **0.545→0.890**; PBO(eligible)=0.0 over 1,716 splits. ✅ **NF1.9-R (2026-08-08) re-measured it on the DRAFTABLE TIER: 0.845 (2019–2025) / 0.833 full-window, gated positions all ≥0.80 (TE 0.739 @ n=251 carried un-gated) — the "~0.50 tier" figure was the pre-NF1.9 normal band's; a 21-arm tier re-selection TIED the incumbent (recorded null)** |
| **K/DST** (NF1.6) | empirical `RatioBand` + `BAND_CLUSTER_Z=1.0` across-season-SD widening | reported, **not selected** (no candidate field) — breach response = widen honestly, never re-select | DST 0.897 / K 0.830 vs 0.80 floor |

Fallback ladder (rookies): `calibrated_per_player` → `calibrated` (NF1.4 tercile) → `parameter` (legacy `fp×cv`, covers 0.678). Live payload: **784/784 skill players `calibrated_per_player`**, 74 K/DST `empirical_ratio_band_80`.

### Scoring engine (NF-C0/NF-C1 — the other half of the product)

`quant_sports_intel_models/fantasy_engine/` (sport-agnostic: `league_config.py` / `scoring.py` / `settings.py` / `vor.py` / `draft.py`) scores the raw stat line under any league config: `league_points = Σ points(stat,pos) × raw_stat`, VOR replacement via greedy flex allocation, per-side interval carry (`league_p10 = base_p10 × league_points/base_points` — asymmetric bands survive the rescore). **Custom/imported leagues are scored CLIENT-SIDE** (`frontend/lib/league-scoring.ts` — a lock-step TS port; forced, not chosen: the API Lambda bundles no pandas/numpy and sits near the zip size cap). Coverage of a league's rules is **mechanical** (`settings.resolve_scoring` → `applied`/`derived`/`captured` — a term is "applied" only if a projection column actually exists; nothing self-promotes).

## (3) Feature contract — the full input-feature dictionary

Market-blind for the level model and blind anchors; the served ordering layer is **deliberately market-aware** (ADP/ECR enter as features — that IS the design, labeled per-position in the payload). Every feature below is a base-season realized quantity or a leakage-safe forward designation (depth charts / staff / contracts as of the projection preseason; NF-D10's March-15 as-of rule measured 0 leaks).

### (i) MVP-1's base-season input frame (the level model's raw inputs)

From `main_nfl_marts.fct_player_week` per (player, season), games where `played_flag and not is_bye` (`run_season_projection._MULTI_SEASON_SQL`):

| column | meaning |
|---|---|
| `games_played`, `position` | Games actually played in that season; position (FB→RB aliased) |
| `pass_att_tot`, `pass_cmp_tot`, `pass_yds_tot`, `pass_td_tot`, `pass_int_tot` | Season passing volume/production totals |
| `rush_att_tot`, `rush_yds_tot`, `rush_td_tot` | Season rushing totals |
| `targets_tot`, `rec_tot`, `rec_yds_tot`, `rec_td_tot` | Season receiving totals |
| `fp_ppr_tot`, `fp_ppr_sd` | Season PPR points and game-to-game PPR standard deviation (volatility) |
| `snap_share` | avg offensive snap % where >0 — the RB/WR "volume-earner" role signal (NF-D2 slice 1) |
| `target_share`, `carry_share` | Share of team targets / carries — receiving and rushing role |

These become 12 per-game shrunk stats (`_VET_PERGAME_STATS`), recency-weighted over the 3-yr window, then multiplied by expected games. Plus (level-model side-inputs): depth-chart rank (`dim_player_role` / `stg_nfl_depth_charts_current`), Sleeper injury statuses (NF-D5), team-change designations, preseason Vegas win totals + Week-1 implied points (NF-D4), and the NF-D11 roster-evidence branches (`stg_nfl_depth_charts_current` 2025+, `stg_nfl_weekly_rosters` back to 2002).

### (ii) The NF1 core market-blind learner contract — `nf1_model.FEATURES` (13)

These are the features the NF1.x learner classes (and the served NF1.5 inner anchors) consume; 12 of the 13 ship to the UI as `manifest.featureLegend` with plain-language labels, and the NF3.4 per-player `contrib.drivers[]` attribute the projection to them.

| feature | what it represents |
|---|---|
| `mvp1_fp` | MVP-1's heuristic season projection (PPR) — the incumbent prior the learner re-weights against (never a target) |
| `pergame_fp` | Recency-weighted per-game scoring pace (PPR/g), before expected games |
| `base_games` | Base-season games played (durability / sample strength) |
| `expected_games` | MVP-1's role/usage expected-games estimate for the projection season |
| `snap_share` | Base-season offensive snap share |
| `target_share` | Base-season target share (receiving role) |
| `carry_share` | Base-season carry share (rushing role) |
| `depth_rank` | Forward depth-chart rank (current depth chart at serve; weeks 1–3 in backtest) |
| `mover_scale` | NF-D2 slice-3 team-change opportunity multiplier (1.0 = stayer) |
| `team_env` | NF-D4 forward-Vegas team environment — 0.5/0.5 z-blend of preseason win total × Week-1 implied points |
| `injury_cap_ratio` | NF-D2 slice-5 availability ratio (<1 = shelved: RES/PUP/NFI/SUS games cap applied) |
| `age` | Player age at the projection season (the aging-curve feature NF1 added over MVP-1 — its largest ablation contributor, −0.010 when dropped) |
| `fp_sd` | Base-season game-to-game PPR standard deviation (volatility) |

### (iii) NF-D7 xFP block — `nf1_1_model.XFP_FEATURES` (6)

| feature | what it represents |
|---|---|
| `xfp_pg` | Opportunity-based expected fantasy points/game (composed from the four below at PPR weights) |
| `td_luck_ratio` | (actual − expected) rush+rec TDs per game — >0 = TD-lucky (mean-reversion signal) |
| `xrush_td_pg` | Expected rushing TD/g from carry field position (`yardline_100`-bucket conversion rates) |
| `xrec_td_pg` | Expected receiving TD/g from target field position |
| `xrec_pg` | Expected catches/g = Σ catch probability (`cp`) over targets |
| `xrec_yds_pg` | Expected receiving yards/g = Σ `cp·(air_yards + xYAC)` |

### (iv) Pre-registered per-position sets — `nf1_1_model.POSITION_FEATURES`

- **QB** (14): core minus `target_share`, plus `xrush_td_pg`, `td_luck_ratio` (receiving-xFP legs are noise for a QB)
- **RB** (19): core + all 6 xFP
- **WR / TE** (17 each): core minus `carry_share`, plus `xrec_pg`, `xrec_yds_pg`, `xrec_td_pg`, `xfp_pg`, `td_luck_ratio` — with **xFP dropped at WR** by NF1.2's settled null (`nf1_2_model.BASE_POSITION_FEATURES`)

### (v) NF1.3/NF1.5 market axes — the features the SERVED ordering layer adds

| feature | what it represents |
|---|---|
| `market_rank` | Unified consensus overall rank — FantasyPros ECR primary, FFC ADP fallback (lower = better) |
| `market_dispersion` | Consensus uncertainty — ECR `rank_std`, ADP `stdev` fallback (drives the QB adaptive `disp_slope`: the blend trusts the market LESS where experts disagree more) |
| `market_score` | `−market_rank` (direction-aligned; consumed by the blend classes) |

Upstream: `adp_source.py` (FFC, format-matched per preset — superflex→`2qb`), `mfl_adp_source.py` (MFL, the deep second source; FFC has zero 2025 archive), `fantasypros_source.py` (ECR), `espn_source.py`, `sleeper_source.py` (benchmarks).

### (vi) Rookie feature blocks — `nf1_4_rookie.FEATURE_BLOCKS` (served: slot + p1a only)

| block | columns | what it represents | served? |
|---|---|---|---|
| `slot` | `log_overall`, `draft_round`, `is_top10`, `is_day1` | Draft capital — the backbone | ✅ (the slot curve) |
| `p1a` | `projected_nfl_z`, `p1a_slot_residual` | NCAAF-P1A college→NFL projection z + its residual vs slot-expected z (talent the draft board disagreed with) | ✅ (residual nudge λ=0.12; `projected_nfl_z_sd` also a rookie-band regression feature) |
| `athletic` | `forty_z`, `vertical_z`, `broad_z`, `cone_z`, `shuttle_z`, `bmi_z`, `athletic_composite`, `has_combine` | Combine drills z-scored per position | ⛔ tried, null (NF1.4) |
| `breakout` | `breakout_season_index`, `breakout_class_year`, `career_index_at_draft`, `n_college_seasons`, `early_breakout`, `has_breakout` | Breakout-age proxy + early declare | ⛔ tried, null |
| `recruit` | `recruit_composite_rating`, `recruit_stars_f` | 247 composite pedigree | ⛔ tried, null |

### (vii) Interval-band features (what prices the served 80% bands)

- **Rookie band** (NF1.7/1.8 qreg): `log(point)`, `log(draft slot)`, P1A `projected_nfl_z_sd`, position — plus the per-position Mondrian conformity layer.
- **Veteran band** (NF1.9 `_VET_BAND_FEATURES`): `log_pred` (log point projection), `log_sd` (log base fp_sd), `games`, `base_games`, `snap` (snap share), `returner` (NF-D11 return-from-absence flag). Assembled once in `veteran_band_inputs` so fit and serve cannot drift.

### (viii) K/DST inputs + emitted distribution (NF1.6)

Inputs: team points-allowed and yards-allowed per-game histories, kicker FG attempt volume + distance mix (≥50-yd attempt share is the one real skill signal, ρ=0.429; make rate ρ=0.085 → shrunk with a 200-attempt prior; distance mix 60-attempt prior), PAT volume vs the **forward** team-points estimate (deliberately the forward ρ≈0.38, not the contemporaneous 0.948), DST sacks/INT/fumble-recovery/forced-fumble rates (retained, lag-1 ρ 0.23–0.27) vs def-TD/safety/blocked (declared noise, projected at league mean). Emitted: `proj_dst_pa_g_<bucket>` + `proj_dst_ya_g_<bucket>` over 9 buckets each (`0,1_6,7_13,14_17,18_20,21_27,28_34,35_45,46p` points; `0_99…550p` yards) — **expected GAMES per bucket**, which makes ANY league tier table exactly linear in the emitted columns (the NF1.6 design trick; buckets are the common refinement of the ESPN + Yahoo schemes).

### (ix) Emitted raw-stat serving contract

`RAW_STAT_COLS`: `proj_games, proj_pass_att, proj_pass_cmp, proj_pass_yds, proj_pass_td, proj_pass_int, proj_rush_att, proj_rush_yds, proj_rush_td, proj_targets, proj_rec, proj_rec_yds, proj_rec_td, proj_fumbles_lost, proj_two_pt` + NF-C0e graduated terms (`two_pt`, `pass/rush/rec_td_40p` — long-TD bonuses applied as league-constant shares of projected TDs, ~0.13 passing / ~0.06 rushing, honestly framed as "your league's bonus in proportion to projected TDs", not "we predict who scores long TDs") + K/DST columns + NF1.5 provenance extras (`nf1_scale, nf1_5_learner, nf1_5_blend_w, nf1_5_disp_slope, market_lean`).

### (x) Tried-and-dropped feature families (separate from served — all recorded nulls, field 10)

NF1.2's 8 refinement families (`sos` pass/rush schedule strength · `system` team pass rate/pace/mover pass-rate delta · `qbcorr` team-QB quality · `oline` O-line cap share · `contract` NF-D8 log-APY/guaranteed-ratio/cap-hit%/skill-cap concentration · `opp` air-yards share + WOPR · `spill` teammate_fp + vacated volume · `coach` NF-D10 new-OC/HC/tenure/continuity/prior-pass-rate-delta), the NF1.4 rookie athletic/breakout/recruit blocks, and hand-constructed recency K-rates. **Feature ADDITIONS have been explored exhaustively** — two full pre-registered family sweeps (NF1.2 at ~140 configs/position; NF1.5 stage-2 at 451–811 configs/position over 9 bundles × 6 learner classes, 16 scored seasons) plus NF-D10's matched-foil coach test. The market-blind feature space is a **proven ceiling**, not an untried one. Probed-and-unavailable: `yprr`, `catchable_rate` (PFF-gated); PFR/Spotrac/OverTheCap scrapes refused (robots/ToS).

## (4) Training data

- **Source:** the S3 **sports lakehouse** (`s3://credence-sports-lakehouse/`, `SPORTS_LAKE_REGION=us-east-2`) — nflverse-derived dbt marts in `quant_sports_intel_models/sports_dbt/` (DuckDB over Delta; Snowflake-free by construction): `fct_player_week` (box-score-anchored spine — the NF-FASTPATH grain/coverage fixes), `dim_player_role` / `stg_nfl_depth_charts` (two-schema union with ASOF week bucketing for the 2025+ ESPN-daily reshape), `stg_nfl_schedules`, `stg_nfl_injuries`, nflverse contracts (NF-D8, CC-BY-4.0 republication), NCAAF-P1A college→NFL projections + the NF-D12 ESPN-id→gsis bridge, coaching stints (NF-D10), and the benchmark Deltas (`adp/ecr/sleeper/espn_benchmark`, MFL ADP).
- **Windows:** MVP-1 level model = base season + 2 prior (recency-weighted). NF1.5 learner pool = **base seasons 2006–2024, 6,736 player-season rows** (2.25× the original 2017-base pool; snap data 0 pre-2012 and market coverage NaN pre-~2010 degrade by design and are disclosed). Rookie models: draft classes 2016–2026 (872 drafted skill rookies; 7 held-out classes 2019–2025). Veteran interval panel: 13 held-out seasons 2013–2025, **8,398 veteran-seasons, LEFT-joined** so zero-game seasons score as real 0s (26.2% zero-game — the rows every rank backtest correctly drops and every interval backtest must keep).
- **CV scheme:** walk-forward by season (fit target < Y, predict Y) for the learners; walk-forward by **draft class** for everything rookie; interval nuisance layers (conformal quantiles, band fits) fitted strictly in-fold (`fit_veteran_band_from_panel` uses only target seasons before the served one). Purged/embargoed in the sense that no target-season information enters any feature (forward designations date-anchored; NF-D10's March-15 rule measured 78/78 mid-season changes leak-free).

## (5) Validation — the gate it passed

**The fantasy vertical's declared gate is product metric + calibration, not betting deflation** (deflation IS computed on every search — that's how the program records trustworthy nulls; see field 10).

- **Product (ordering):** NF1.5b serving re-grade 2026-08-01 (784-player universe, 6 seasons 2019–2024): served refined board vs **ADP pooled within-position Δρ +0.022** (us 0.517 vs ADP 0.494) vs the prior MVP-1 board's −0.059. Per position QB +0.031 / WR +0.037 / TE +0.021 / **RB −0.000 (a wash — the stored "all four positions" claim did NOT reproduce and is not claimed)**; per season 4 wins / 1 tie / 1 loss (2020). **ADP-specific:** ECR −0.013, ESPN −0.051, Sleeper −0.125 still order better than us. High-conviction ADP-fade record (the one airtight claim, market-blind baseline): fade ρ 0.478 vs the market's 0.247.
- **Calibration (levels + intervals):** season interval pooled **calib_80 = 0.847** on the served board (floor 0.80), 100% of skill rows `calibrated_per_player`. Standing annual re-validation (`run_interval_revalidation.py`, 2026-08-01): **✅ ALL FLOORS MET** — rookies QB 0.815 / RB 0.804 (**0 rows of slack — the program's tightest floor**) / TE 0.920 / WR 0.835; veterans QB 0.858 / RB 0.886 / TE 0.888 / WR 0.907; K/DST 0.830/0.897. A floor breach exits non-zero = a **re-selection trigger** (never move the floor); K/DST breach = widen, never re-select.
- **Deflation posture of the served ordering:** NF1.5 stage-1's four position winners each beat the incumbent and pass BH-FDR with clean placebos, but **none clears PBO<0.2 / DSR≥0.95** — recorded `refined_gates` all false. The ship rests on the product metric + calibration + the PM dual-board ruling, under the standing honest frame ("tracks the market + adds our signal"). The interval selections DID clear their own deflation cleanly (NF1.9 PBO(eligible)=0.0; NF1.7 PBO 0.029; NF1.8 read as a two-arm tie via the flip distribution).
- **Public receipts** (NF3.2 + NF-D17): the public track-record page's headline Δρ +0.022 carries its own 90% paired bootstrap **[−0.006, +0.051] — includes zero**, verified population-insensitive (NF-D17: matched-population premise refuted; the MFL +0.173 figure is a DEPTH effect and deliberately not the headline).

## (6) Serving path ⭐ — and the SERVED / HELD / PENDING separation

### The pipeline (build-time static JSON — there is NO request-time model)

```
[operator, laptop] run_season_projection.py  → MVP-1 levels + bands → lake: nfl/fantasy/derived/season_projections
                   run_nf1_5.py --mode build → refined ordering      → lake: nfl/fantasy/derived/nf1_5_season_projections (own prefix)
                   run_kdst_projection.py    → K/DST                 → lake: nfl/fantasy/derived/kdst_projections
                   run_league_board.py       → 14 preset×size boards → lake: nfl/fantasy/derived/league_boards (replaceWhere by season)
                   export_draft_board_json.py --projection-source nf1_5 [--publish]
                        → s3://credence-prod-s3-api-cache/fantasy/nfl/2026/{manifest,projections,board_<cfg>_<size>}.json  (16 files)
                   export_track_record_json.py → …/fantasy/nfl/track_record/   (public receipts)
                   export_player_history_json.py → single-key patch of projections.json (history block)
[API]    app/backend/routers/fantasy.py    (gated /fantasy/nfl/{manifest,projections,board}; /fantasy/leagues; /my-teams)
         app/backend/routers/fantasy_public.py (unauthenticated /fantasy/nfl/track-record/*)
         app/backend/routers/fantasy_import.py (NF-C0 platform import + telemetry, beta-gated)
[UI]     frontend/app/fantasy/* — boards/optimizer/players server-gated; custom-league scoring CLIENT-SIDE (league-scoring.ts)
```

Deliberate architecture calls: static JSON because a wide `lakehouse_query` from the API Lambda fails **silently** to `[]` (the E9.26b class), and because a public Next.js `/data/` asset URL bypassed the paid gate (E9.45 removed it). **A model re-run reaches users only via re-export + `--publish`** — "model shipped" ≠ "users see it".

**Publish guards** (accumulated, all live): exporter **defaults to DRY-RUN**, explicit `--publish` + loud banner (NF-D12); `--publish` **hard-errors** on an unresolved bucket (NF1.7 — pass `--s3-bucket credence-prod-s3-api-cache` explicitly, `$CACHE_BUCKET` is NOT reliably in the operator shell); the two serving blobs built by two scripts (`board_*` vs `projections`) both take `--projection-source`, and the export **REFUSES on a mismatch** (NF1.5b); single-key patches byte-diff-verify every other field before touching S3 (NF3.3's `diff_verify`); frontend merges BEFORE data publishes when a caveat component is involved (NF1.5b deploy-order lesson). Backend changes ship only via manual `infrastructure/lambda/deploy.sh` (no CI/CD — the NF-C0 skew class).

### ⭐ SERVED vs RATIFIED-BUT-HELD vs PENDING (the defining complexity — what is on the wire today)

**SERVED (live, verified in the payload 2026-08-04):**
- The **NF1.5 market-aware refined ordering** over **MVP-1 calibrated levels** (`projection_source="nf1_5"`, `model_version="nfl_fantasy_nf1_5_v1"`, generated 2026-08-04T04:49Z) — 858 players, per-position `market_lean` labels + the standing `market_lean_note` caveat in the payload itself.
- The **NF1.8 rookie + NF1.9 veteran + NF1.6 K/DST intervals** (784 `calibrated_per_player`, 74 `empirical_ratio_band_80`), all floors green.
- The **NF-D11 universe fix** (return-from-absence players restored + priced) and **NF-D12** coverage guard/publish guard.
- The **NF-C0 scoring/import machinery**: Sleeper import (public API) + ESPN via user-mediated paste (NF-C0f) + manual editor (NF-C0b) + client-side custom-league scoring + NF-C0c Sleeper ID bridge + NF-C0d telemetry + the **NF-C0e graduated terms** (9 DST yards-allowed tier columns, `def_forced_fumble`, `two_pt`, 3 long-TD bonuses — the 2026-08-04 04:49Z republish IS the NF-C0e artifact, with the ESPN wrong-key yardage outage fixed).
- App surfaces NF3/NF3.1/NF3.2 (public receipts)/NF3.3 (history)/NF3.4 (per-player TreeSHAP transparency — **stamped `nfl_fantasy_nf1_v1`**, the research model, a labeled difference-by-decision)/NF3.7, NF-C2 draft optimizer, NF-C6 My Teams Phase 1.

**RATIFIED-BUT-HELD (built + validated, serving OFF — zero of it on the wire):**
- **NF-D16 rookie per-position affine level recalibration** — the first NF-fantasy MODEL win after five deflated nulls (pooled draftable-tier MAE 1.0738→0.9407, 7/7 classes, PBO 0.029, DSR 0.996, p=0.0033, bias −20.87→−5.41). **HELD by PM ruling (option C, 2026-08-01)** because the level shift re-orders rookies ACROSS positions and places the top rookie at overall rank 6 — outside the NF-D17-validated placement clause's entire observed reality support (min 7 across seven classes; bar rank ≥12, threshold-invariant). The hold is a **commented-out kwarg, not a flag**: `run_season_projection.py:879-899` simply does not pass `recal_hist=_rookie_full`; `curve.fp_recal` stays `{}` and a pinned test proves byte-identical points. Re-affirmed held by NF-D18 and NF-D20.
- (Related serving-OFF plumbing, held for different reasons: **NF-D14** availability-band feature — default-OFF after a clean interval-gate null; **NF-D15** availability-scaled point — nothing ships, PM-ratified "real-but-underpowered, NOT absent" with scheduled re-runs. Neither is "ratified for serving"; only NF-D16 is. The brief's shorthand grouping all three as "ratified-but-held" over-generalizes — precision here per the record.)

**PENDING (status as of this read, 2026-08-04):**
- **NF-D21 — "publish NF-D16 at a board-blind conservative shrink (λ=0.5)": 🟢 READY, NOT STARTED.** Exists only as the story card (`nfl_fantasy_story_prompts.md:528`); zero code hits for `NF-D21`; no memo, no branch, nothing published. It records the operator's Route-1 DECISION (2026-08-04) after NF-D20's `CONSTRAINT_REFUSED` null: apply a global λ=0.5 shrink (the board-blind interval midpoint — numerically `rookie_shrink_selection.FOIL_LAMBDA`, the foil NF-D20 disclosed would have shipped had it been registered shippable: Δ−0.0789, PBO 0.0, DSR 0.9999, clears the 2026 cap at rank 12) to NF-D16's affine on RB/TE/WR (**QB untouched**), flip serving ON, republish, and **re-run `run_interval_revalidation`** (required — a level shift moves the band centre). Explicitly framed as a **PM-judgment publish, NOT a §0.5 selection** (⛔ no re-run of the in-fold selection; ⛔ no pre-registering λ=0.5 "as selected" — that is the E2.1-r laundering NF-D20 forbade). **Until NF-D21 runs, the served rookie point is the un-recalibrated slot curve** — corroborated in the live payload (top rookie by projected points is a QB, Fernando Mendoza 270.2 PPR; top board rookie Jeremiyah Love RB at overall 11 on half-PPR/12).
- **NF-C0g Yahoo import** — code-complete + deployed + SSM-provisioned, gated off (`YAHOO_IMPORT_ENABLED` unset), **blocked externally** on Yahoo's application review (chase by 2026-08-15; falls back to Sleeper + manual editor for the operator's 8/22 draft).

## (7) Version + last retrain + cadence (reconciled against the SERVED artifact)

**⭐ Version authority — named first: the ARTIFACT STAMP, not a registry.** There is **no `sub_model_registry.yaml` entry** for anything NFL-fantasy (grep: zero model entries) and no `daily_model_predictions` involvement. The version of record is (a) the `model_version` + `projection_source` stamps carried IN the served payload (written from code constants at build time), and (b) the per-position champion selections stored as data in `ablation_results/nf1_5_feature_combination_bakeoff.json` (+`nf1_1_per_position.json` inner anchors), read back by `--mode build`. The `projection_source` toggle + export-time mismatch refusal is the closest thing to a version-authority *mechanism* in the family.

| what | value | evidence |
|---|---|---|
| Served `model_version` | **`nfl_fantasy_nf1_5_v1`** | **Live S3 read 2026-08-04** of `projections.json` — matches `nf1_5_model.MODEL_VERSION` (code) and the NF1.5b serving record. ✅ reconciled |
| Served `projection_source` | **`nf1_5`** ("market-aware refined (NF1.5)") | live `manifest.projectionSource` + `projections.projection_source`; matches `DEFAULT_PROJECTION_SOURCE` | 
| Underlying level model | `nfl_fantasy_fastpath_v1` (MVP-1) — overwritten by the NF1.5 stamp in the served blob by design | `run_nf1_5.py:578` |
| K/DST sub-lineage | `nfl_fantasy_kdst_base_v1` | code constant; K/DST rows live in the same payload (`lowPred` flags) |
| NF3.4 transparency block | `featureContributionsMeta.model_version = "nfl_fantasy_nf1_v1"` (generated 2026-08-02) | **difference-by-decision, NOT drift** — the contrib panel deliberately runs the NF1 research GBM for TreeSHAP attribution; every payload carries its own stamp so the difference is labeled |
| Payload freshness | `generated_at = 2026-08-04T04:49:33Z`; all 16 S3 objects same write | = the NF-C0e post-merge republish (#575/#577/#578 chain). ✅ current |
| Board provenance | board **rows** carry no per-row `projection_source` in the served JSON; provenance rides `manifest.projectionSource` + the export-time `assert_board_projection_source` refusal (the stamp lives on the lake/board artifacts the exporter checks) | live read + `export_draft_board_json.py` |
| Rookie recalibration | **OFF in the served payload** (NF-D16 held; NF-D21 unstarted) | code (`recal_hist` not passed) + payload corroboration (top rookie = QB by points) |
| Retrain cadence | **None scheduled.** No Dagster job, no cron — every build/publish is an operator command. Standing cadences: **annual interval re-validation** (`run_interval_revalidation.py`, breach = re-selection trigger); data roll-forward job (`sports_nfl_rollforward_job`, weekly Mon 06:15 PT Mar–Aug, operator-gated/STOPPED); Sleeper injuries daily through camp; standing rule "any data expansion ⇒ a full deflated re-bake-off" | code + catalog |
| Scheduled re-test triggers | NF1.5 stage-2 WR `pos_mlp×base` auto-retest when 2026 accrues (PBO 0.2188 vs 0.20); NF-D15 TE @10 classes (2028), RB @11 (2029), WR dropped; NF-C0e yards-allowed family re-validate after 2026 | memos |

## (8) Honest-framing status — confirmed, and enforced in the payload

- **`best_alpha = 0`** — no bet, no edge, no win-rate claim rides on any of this; the vertical never touches the betting decision layer.
- **The market-aware caveat ships IN the data** (live-read): `market_lean_note` — "…the ranking INCORPORATES market consensus (ADP/ECR)… a re-ORDERING of the same numbers, not a re-pricing" — plus per-position `market_lean` labels and per-row `mktLean`. At market-led positions a small Δρ-vs-ADP is the DESIGN, never an edge claim.
- **Claim scope is locked and narrow:** "beats ADP on average over 2019–2024" (never "at every position", never "beats the market" — ECR/ESPN/Sleeper still order better); the public track-record page carries the +0.022 WITH its zero-including CI and a "multi-season average, not a promise" caveat; the fade claim cites the market-blind MVP-1 baseline (0.478 vs 0.247). NF-D17 hardened this against the "matched population" upgrade temptation (premise refuted by measurement) and NF3.2's `_CLAIM_DENYLIST` polices copy.
- **ADP is shown as a neutral reference column** with format-matched samples (superflex→2qb — a single ADP column would fabricate +27 "value" on every QB of a superflex board); no surface says we out-rank consensus.
- **Low-predictability honesty:** K/DST rows carry `lowPred`/`predNote` (DST ρ 0.322, starter-K 0.231 measured and disclosed); NF-C0e's long-TD terms are framed as league-constant shares, not player prediction; NF-C0b coverage verdicts (`applied/derived/captured`) are mechanical so no league setting can silently score zero while claiming support.

## (9) Known limitations + open follow-ups

**Read this correctly: the served core is stable, trustworthy, and calibrated** (fields 5–8); the open list is long because this is the **active launch product** — surface build-out and adapters, not defects in what is served. **Count: 20 carded open stories + 12 NF-W spec one-liners = 32**, plus a handful of operational opens.

Model/serving limitations (the ones an auditor should know):
1. **The rookie point level is knowingly COLD** (tier_bias −32…−58 PPR per position; three independent confirmations) and the ratified fix (NF-D16) is deliberately held — the cure ships only via NF-D21's judgment-call shrink. Until then top-rookie placement is conservative by construction.
2. **Rookie RB interval floor has 0 rows of slack** — the program's tightest constraint; a new class is the likeliest first breach (the annual re-validation exits non-zero and triggers a re-selection).
3. **Interval floors are invisible at serving time** (coverage needs realized outcomes) — the annual re-validation is the only detector; the veteran band went unmeasured at 0.545 coverage for five stories before NF1.9, which is why that check now exists and must actually be run each season.
4. **No scheduled retrain / no drift monitor beyond the interval check** — the board is an operator-triggered snapshot; "model shipped" ≠ "users see it" without a re-export.
5. **Deep systems still out-order us** (Sleeper-Rotowire −0.125 the toughest); top-tier QB/RB ordering is structurally market-led. The evidenced remaining levers are the WEEKLY arc (NF-W) and depth-conditional framing (NF3.8), not more season-level blind features (proven ceiling).
6. **Weekly is a recorded null as scalar tilts** — NF1's weekly leg ships flat; a real weekly model is the NF-W epic (V0 data-audit-gated, all V1+ frozen).
7. `te_premium` exists in `CONFIG_LABELS` but was never landed as a board — UIs must stay manifest-driven.
8. Roadmap staleness: the roadmap doc still carries the pre-NF-C0f "ESPN = earned NO-GO" line, superseded by the paste-flow ship (the red line on automated cookie replay stands).

Open stories (carded): **NF-D21** (publish NF-D16 @ λ=0.5 — 🟢 READY), **NF-C0g** Yahoo (externally blocked, ⏰ chase 2026-08-15), **NF-C0h** CBS/MFL/Fantrax adapters, **NF-W epic** (NF-W0 🟢 READY; NF-W0a/0b/1 SPEC; NF-W2–13 frozen one-liners), **NF2** dynasty, **NF3.5** LLM narrative (deferred), **NF3.6** weekly variance surface (🟢 scoped), **NF3.8** depth-conditional receipts (🟢 pre-launch hook), **NF-D9** NLP sentiment (parked), **NF-C1** full league keystone, **NF-C2.1** mock-draft sim, **NF-C3** trade calculator, **NF-C4** waivers, **NF-C5** auction, **NF-C6 Phase 2** (gated on NF-W1), deep-learning umbrella (low-prior). Operational opens: NF-C0d dev→main frontend deploy; NF-C0e's telemetry-purge endpoint absence + QA-noise pollution; NF-D19's post-deploy spot-check; past-season boards deliberately unpublished.

## (10) ⭐ TRIED & RESULT ledger

_So a future audit never re-runs a settled recalibration or re-recommends a dead feature family. Null states per `cv_power.classify_null` where applicable — note this program **added the 8th state, `CONSTRAINT_REFUSED`** (NF-D18/NF-D20), for nulls a deterministic product constraint causes, where more data can never change the verdict._

### The projection bake-off arc (NF1.x)

| candidate / mechanism | when | result | source memo |
|---|---|---|---|
| MVP-1 heuristic (recency-weighted EB per-game × expected games; rookie slot curve) | NF-FASTPATH 2026-07-23/24 | **SHIPPED as the level model** (still owns every served point + band). Holdout Spearman 0.73–0.80; expected-games fix killed the naïve `per_game×17` backup-inflation | `nf_fastpath_season_projection.md` |
| Pooled learned re-weighting (ridge/elasticnet/GBM vs MVP-1 null) | NF1 2026-07-26 | GBM wins ordering (ρ 0.732 vs 0.718; only learner improving QB) but **product verdict = INCUMBENT STANDS**; level use forbidden (survivorship) → ordering-only mechanism built. Weekly scalar-tilt leg **NULL** (all Δ≤0) | `nf1_model_report.md`, `nf1_weekly_bakeoff.md` |
| Per-position blind models + top-tier metric | NF1.1 2026-07-27 | Beats null at all 4, **NULL at the deflation gate** (QB PBO 0.83 = top-tier QB IS the market signal) | `nf1_1_per_position.md` |
| 7 blind refinement families (sos/system/qbcorr/oline/contract/opp/spill) + xFP | NF1.2 2026-07-27 | **CLEAN NULL** — none passes; H-CONTRACT RB-only positive; TE near-miss (PBO 0.143, DSR 0.24); xFP dropped at WR (net drag) | `nf1_2_refinements.md` |
| Market-aware per-position blends (ADP/ECR as features) | NF1.3 2026-07-27 | **Product win at QB/RB** (first board to beat ADP, +0.015 pooled) but deflation-null; fade edge erodes 0.543→0.478 by design. Serving HELD (dual-board posture) | `nf1_3_per_position.md` |
| Rookie prior "runs hot — recalibrate" | NF1.4 2026-07-27 | **Premise REFUTED — the prior is COLD** at every position; 134-config search null; shipped only the rookie interval fix (0.680→0.790) + the placement face-validity clause | `nf1_4_rookie.md` |
| Refined market blends (adaptive/learned/flat) vs NF1.3 incumbent | NF1.5 stage 1, 2026-07-28 | All 4 positions beat the incumbent; FDR-pass, placebo clean, **PBO/DSR fail (standing posture)**; product best-ever (ADP win-rate crossed 0.5 first time). **SHIPPED via NF1.5b** | `nf1_5_feature_combination_bakeoff.md` |
| Blind combination sweep at full power (9 bundles × 6 classes incl. MLP/two-part/lambdarank, 16 seasons, 451–811 cfg/pos) | NF1.5 stage 2 | **DECISIVE NULL — DSR binding at all 4** ⇒ market-blind season-level ceiling proven (6th confirmation). Honest near-miss: WR `pos_mlp×base` PBO 0.2188 (auto-retest when 2026 accrues). ⛔ Decline new blind season-level feature stories | same |
| NF1.5b serving re-land | 2026-08-01 | **SHIPPED** — re-grade +0.022 vs ADP; "all 4 positions" did NOT reproduce (RB wash); found + fixed the parallel-board drift (716-vs-784 universe, pre-NF1.9 band reversion) and the two-blob two-script skew (`--projection-source` + export refusal) | `nf1_5b_serving_reland.md` |
| K/DST base projection | NF1.6 2026-07-30 | **SHIPPED + LIVE** — completeness/tiering, explicitly not precision (DST ρ 0.322, starter-K 0.231); expected-games-per-bucket makes any tier table linear; NegBin rejected (misses P(shutout) by 2 orders). NF1.6b bye-clustering = WON'T-DO | `nf1_6_kdst_base_projection.md` |

### The interval arc

| candidate | when | result | source |
|---|---|---|---|
| Rookie per-player band (44 configs; qreg vs kNN vs ratio families) | NF1.7 2026-07-29 | **SHIPPED `qreg α0.01`** — IS80 −10.4%, coverage 0.808, PBO 0.029. Recorded the four ways an anchor set lies (oracle-fails-to-fit = vacuous pass; same-family-same-sample; two degenerates; widen-only must be monotone) | `nf1_7_rookie_intervals.md` |
| Rookie per-POSITION floor (80 configs) | NF1.8 2026-07-29 | **SHIPPED `qreg_sqrt+cqr[pos,add]`** — Mondrian conformal wins where per-position FITTING loses (QB 0.716); pooled-conformal foil a no-op (attribution). PBO 0.514 correctly read as a two-arm TIE via flip distribution, not overfitting. RB floor 0 rows slack | `nf1_8_rookie_perposition_floor.md` |
| Veteran band (the unmeasured 90% of the board) | NF1.9 2026-07-29 | **SHIPPED `knn_norm k300`** — served normal band covered 0.545 of nominal 0.80; fix −21.9% IS80, coverage 0.890, PBO(elig) 0.0. Conformal a mathematical no-op on a 31%-zero population; coverage structurally non-binding ⇒ a 0.80 TARGET would be inverted (kept a floor). `normal_cov` foil prices the naive fix at +7.2% | `nf1_9_veteran_perposition_floor.md` |
| Annual re-validation harness | NF1.9 | **STANDING** — 2026-08-01 run: all floors met. Breach = re-select (rookie/vet) or widen (K/DST), never move the floor | `nf1_9_interval_revalidation.md` |

### The NF-D matched-foil / recalibration series

| candidate | when | result + null state | source |
|---|---|---|---|
| NF-D2 projection-quality sources (6 slices) | 2026-07-26 | Slices 1/3/4/5 shipped as MVP-1 layers (snap-share expected games, mover, Vegas env, injury caps); slice 2 null; **slice 6 ADP-blend = benchmark-not-blend** (`_ADP_PRIOR_BLEND=0.0` — a blanket blend erases the disagreement edge) | `nf_d2_*` |
| NF-D3 competitor scorecard | 2026-07-26 (+ESPN files 2026-08-01) | **STANDING instrument** — we lose overall ordering to every consensus, win high-conviction ADP fades 0.478 vs 0.247; ESPN loader's two real bugs (split-type dup; shifted position_id) caught by an implausible outlier | `nf_d3_benchmark_scorecard.md` |
| NF-D6 roster-churn defense signal | 2026-07-27 | **Honest NULL** (kept as diagnostic); forward defense strength shipped as the `sos` substrate | `nf_d6_*` |
| NF-D7 xFP heuristic TD-regression blend | 2026-07-27 | Construct valid, **heuristic blend NULL** → features-only delivery (`_XFP_TD_BLEND=0.0`) | `nf_d7_*` |
| NF-D8 contract features (nflverse CC-BY republication after Spotrac/OTC refusals) | 2026-07-27 | Data shipped; feature family folded into NF1.2/NF1.5 sweeps (contract bundle in QB/RB winners' cells but **never deflation-clears**) | `nf_d8_*` |
| NF-D10 coaching-change family (H-COACH) | 2026-07-31 | **ATTRIBUTABLE NULL via matched foils** — with-vs-without pairs negative 7/10, no position positive on both; the lone positive attributed to a contract/opp interaction. Data (HC/OC effective-dated stints) ships as WEEKLY-model substrate. ⛔ Don't re-litigate season-level | `nf_d10_coaching_source.md` |
| NF-D11 return-from-absence prior (21 configs, 6 families) | 2026-07-29 | **SHIPPED `ratio @ blend 1.0`** (PBO 0.0, spread 35.8% = separated winner). ⭐ **MAE inversion measured live** — the all-zero degenerate WINS MAE on a 43%-zero cohort → CRPS primary + two-sided anchors now standard | `nf_d11_absence_prior.md` |
| NF-D13 scorecard aggregate-vs-member audit | 2026-08-01 | **CLEAN NULL, structural** — pairwise design cannot express the E7.11 defect; regression test pinned | memory/`nf_d13` |
| NF-D14 rookie-QB availability prior | 2026-07-31 | **CLEAN NULL at the gate** (leg-1 signal large + real, CRPS −31% QB, PBO 0.0; leg-2: no arm clears every floor AND beats the shipped band) ⇒ rookie-QB interval variance **irreducible at this n; question RETIRED**. Plumbing default-OFF. MAE-inversion refinement: it inverts on the conditional MEDIAN, not the zero atom | `nf_d14_rookie_availability.md` |
| NF-D15 availability-scaled rookie point (RB/TE/WR) | 2026-08-01 | **RECORDED NULL — "blocked by the three-test BH multiplicity at n=7, NOT absent"** (PM-ratified relabel). Lift reproduces; DSR+FDR fail. ⭐ Matched foil **REFUTED NF-D14's stated level mechanism** (effect is per-player; bias moves AWAY from zero while MAE improves). Re-runs: TE 2028 @10 classes, RB 2029 @11; **WR = GENUINE ABSENCE, dropped** | `nf_d15_rookie_point_scaling.md` |
| **NF-D16 per-position affine level recalibration** | 2026-08-01 | **✅ RATIFIED (the first model win after five deflated nulls: MAE 1.0738→0.9407, PBO 0.029, DSR 0.996) — ⏸️ PUBLISH HELD** on the placement clause (rank 6 vs bar ≥12). Per-form peeking-ceiling lesson (a nested form legitimately beats the constant's ceiling). Post-ship re-run: the residual 0.0152 gap is **class-variable, not learnable in-fold** (`skill_vs_null` −0.017) — that lead is CLOSED | `nf_d16_rookie_point_recalibration.md` + `_post_ship.md` |
| NF-D17(a) placement-clause validation | inside NF-D16 | Clause **VALIDATED, not mis-specified** — rank-space mirror gives cap ≈ one board slot from the incumbent's; breach rates match reality; threshold-invariant Q05–Q25 ⇒ genuine veto, un-reverse-engineerable | same |
| NF-D17(b) track-record Δρ population sensitivity | 2026-08-03 | **RECORDED NULL, premise refuted** — matching moves nothing (FFC ⊂ MFL); shipped +0.022 stands WITH its zero-including CI; MFL +0.173 is a DEPTH effect, not the headline. One-sided top-N truncation manufactures a 0.20-wide Δρ | `nf_d17_track_record_population.md` |
| NF-D18 attenuate-at-the-top (power/huber/qmap/isotonic @ λ=1) | 2026-08-02 | **RECORDED NULL — `CONSTRAINT_REFUSED`** (the 8th null state, coined here; `classify_null`'s POWER_LIMITED rejected as a misleading trigger — no amount of draft classes moves a board rank). 3 of 4 shapes place the top rookie WORSE; **frontier finding: a plain global shrink clears the cap to λ=0.75 retaining 81.5% of the gain** (measured, ⛔ not taken — un-pre-registerable). Premises refuted by fits: "concave" came back convex; huber went the wrong way (the influential extremes are the zeros) | `nf_d18_rookie_top_attenuation.md` |
| NF-D20 in-fold shrink selection under a per-fold placement constraint | 2026-08-04 | **FINAL RECORDED NULL — `CONSTRAINT_REFUSED`.** Every recalibrating arm beats the incumbent on the metric AND is refused by C2 out-of-sample; the **blind λ=0.5 constant satisfies C2 on every board while no in-fold rule does** (the constraint is INACTIVE on 4/8 boards — best rookie a QB — so its activity is a draft-class accident, unlearnable). `over_scale` (λ=2, registered to lose) beat every real arm = refuted magnitude hypothesis, gate left False. Disclosed: blind-half would have shipped had it been registered shippable — the null rests on a registration choice, stated plainly. ⛔ a successor may not pre-register λ=0.5 | `nf_d20_infold_shrink.md` |
| **NF-RECAL1 veteran LEVEL recalibration** (5 forms × 2 λ-rules, per-game primary + season-total matched foil, CRPS) | 2026-08-08 | **RECORDED NULL — `CONSTRAINT_REFUSED`.** All 5 unconstrained arms BEAT the incumbent on CRPS (best `pos_affine` 50.68 vs 53.04, 6/7 folds) and every one is refused OUT-OF-SAMPLE by **C3, the interval-coverage floor — the same gate that refused NF-D21**, on a different leg. ⭐ Premise AMENDED: the motivating −37.7 does not reproduce (−12.85 on the pre-registered population; the realized-anchored slice strips 100% of zero outcomes). ⭐ `over_scale` (λ=2, registered to lose) WON ⇒ refuted MAGNITUDE, not a metric inversion — the fit under-corrects. Three method findings: a peeking ceiling needs matched **OBJECTIVE** as well as family+sample; permutation vacuity is a property of the **SPACE**; a leg-scoped constant is **not** whole-board monotone. ⚠️ **AMENDED BY NF1.9-R (2026-08-08): C3's "incumbent band" was the panel's `served_p10/p90` = the PRE-NF1.9 NORMAL band, so its Finding-3 "~0.50 tier coverage of the SERVED band" is mis-attributed — the served knn band covers 0.845 there. FLAGGED, not re-litigated: whether the level null changes under the served band needs a PM re-read of this record.** ⚠️⚠️ **RE-READ DONE = NF-C3-REREAD (2026-08-08, row below): the CONSTRAINT_REFUSED state does NOT stand — corrected state `POWER_LIMITED` at the DEFLATION gate (DSR 0.642<0.95 ⇒ still nothing ships); the `over_scale`-wins magnitude anomaly and the `no_lift` attribution were panel-band artifacts too (on the served band λ=2 LOSES, the optimum is λ≈0.5, and the winner carries the `level_fix` signature). The premise finding (−12.85) and C1/C2 findings stand** | `nf_recal1_level_recalibration.md` |
| **NF1.9-R veteran band re-selected on the DRAFTABLE TIER** (21 arms: knn k-grid, tier-fit knn/qreg, Mondrian `cqr_tier[pos\|mag\|pool]`, scale/coverage nulls; TIER IS80 selects, coverage floors + universe guard constrain) | 2026-08-08 | **RECORDED NULL (TIE) + THE PREMISE CORRECTED.** ⭐⭐ The motivating "~0.50 on the tier" reproduces TO THE DIGIT (0.5046) against the **pre-NF1.9 NORMAL band** (the panel's `served_p10/p90`, which NF-RECAL1's C3 read as "the incumbent"); the band ON THE WIRE covers **0.845** on the 2019–2025 tier / 0.833 full-window — QB 0.856 · RB 0.824 · WR 0.855 ≥ the 0.80 floor (TE 0.739 @ n=251 CARRIED not gated — NF-D22's job). Universe IS80 reproduced EXACTLY (160.888). Best arm leads 0.17% = TIE (PBO 0.42, DSR 0.02, p 0.31; ~95 folds needed = unreachable ⇒ genuine). `scale_tier` fitted ×~1.0 (served width already score-optimal on the tier); `cov_tier` made coverage AND score worse (E2.1-r live); pooled conformal foil a no-op while Mondrian `cqr_tier[pos]` acts — lifting un-gated TE 0.739→0.819 at equal score (⛔ not promoted; recorded as NF-D22's first re-score). Tier-overlay machinery kept DARK (`_VET_TIER_RECAL=False`, no selected form). Nothing served changed | `nf1_9r_veteran_tier_band.md` |
| **NF-C3-REREAD — NF-RECAL1's C3 + NF-D21's floor gate re-read under the CORRECT served band** (a GATE re-read, no new model; step-0 refit reproduces universe IS80 160.888 Δ0.00% / tier 0.8452 / panel 0.5046 before any gate is read) | 2026-08-08 | **SPLIT VERDICT.** ⭐⭐ **NF-RECAL1's `CONSTRAINT_REFUSED` does NOT stand** — the mis-specification sat in BOTH terms of `min(floor, coverage_incumbent)`, so the corrected (STRICTER, 0.80-class) bar passes MORE arms: `global_const/pos_const · unconstrained` clear the corrected C3 on every fold (ε-insensitive; `pos_affine` refused by C1-2021 negative slope, band-independent); the full pre-registered replay yields winner `global_const · infold` λ≈0.5 (48.700 vs 48.808, bias −12.59→−5.44 = `level_fix`) passing every constraint + PBO 0.143 + p 0.082 but **FAILING whole-field DSR 0.642<0.95 ⇒ SHIP=FALSE** ⇒ corrected null = **`POWER_LIMITED` at the deflation gate**; reachable-now re-test = operator board rebuild `--backtest-from 2013` (13 constraint-evaluable folds) = **B3**'s first step. ✅ **NF-D21's refusal STANDS** — its band is the rookie model-path refit (never a `served_*` column; sweep reproduced row-for-row), the corrected C3 structure reduces to the bare 0.80 floor (λ=0 RB 0.8041≥0.80), λ=0.5 RB still 0.7905 = −2 rows @ n=148 ⇒ truly CLOSED. ⚠️ Harness finding: `coverage_floor_check`'s round-then-ceil makes coverage EQUAL to the incumbent's fail by 1 row (λ=0 "fails" against itself — in the recorded run too; cosmetic, ε-sensitivity changes no headline; fix belongs to B3). Nothing served changed | `nf_c3_reread.md` |
| **NF-D21 publish-at-λ=0.5** | — | **🟢 READY, UNSTARTED as of 2026-08-04** — the PM-judgment Route-1 publish (see field 6 PENDING). Not a selection; NF-D20's numbers are evidence base only | catalog:528 |

### The NF-C0 scoring/import findings

| candidate / finding | when | result | source |
|---|---|---|---|
| Sleeper import (public API) | NF-C0 2026-08-01 | **SHIPPED LIVE** (verified real league); stat-ID map verified by identity, not label (bucket sums = 17.000 games; FG partitions) | catalog |
| ESPN automated access | NF-C0 probe | **NO-GO on the red line** (cookie replay = password-equivalent) — **reopened on a DIFFERENT mechanism**, not reversed: NF-C0f user-mediated paste **SHIPPED** (server never sees a cookie). Two-ID-space landmine (`defaultPositionId` 4=TE vs slot 4=WR); 3.29MB payload → denylist prune; scrubber narrowed `\bSWID\b`→`SWID=` (over-matching would have refused 100% of honest imports) | `nf_c0_espn_access_probe.md` + catalog |
| Yahoo OAuth import | NF-C0/NF-C0g | Code-complete + SecureString SSM; **externally blocked** on Yahoo's review gate (no SLA); enable = one env flag, no redeploy | catalog |
| Manual league editor + mechanical coverage | NF-C0b 2026-08-01 | **SHIPPED** — the floor that lets adapters stay principled; `applied/derived/captured` enforced by code | catalog |
| **NF-C0e captured-terms graduation + the ESPN yardage outage** | 2026-08-03/04 | **15 terms GRADUATED** (9 DST yards-allowed tiers +9.3–9.5% MAE vs a points-allowed control at +7.0%; `def_forced_fumble`; `two_pt`; 3 long-TD bonuses) under a **degenerate-beating gate on BOTH MAE and RMSE** — `fum` won MAE 7/7 and LOST RMSE 7/7 (the NF-D11 inversion live) ⇒ held. `pat_missed` held (8/16 folds — availability is not evidence); `st_player_td`/`fumble_rec_td` = mechanism-cannot-act (no return-volume projection). 🚨 **Live outage found: ESPN stat ids mapped onto Sleeper's keys — every ESPN league scored ZERO yardage since ESPN import shipped**; survived a vacuous read-back-the-key-you-wrote test. ⭐ `|weight|` ≠ impact — `|weight|×VOLUME` is (pass_yd ranked dead last while most consequential). Two post-merge "declaration outran production" defects: module shipped uninvoked (cure: `CONSUMER_CALLERS` + exhaustiveness guard); stale cache keyed on params-not-query published a graduated term all-NULL (cure: SHA-of-query cache key). Yards allowed must be NET of sacks (gross shifts every defense a tier rung) | `nf_c0e_captured_terms.md` |
| NF-C0d import telemetry | 2026-08-03 | **SHIPPED** — occurrences × avg|weight| ranking; privacy structural (no field for identity); known caveats: QA noise, no purge endpoint | catalog |
| NF-C0c Sleeper player-ID bridge | 2026-08-01 | **SHIPPED** — gsis-direct + name/pos crosswalk fallback; Sleeper-only problem (ESPN returns names inline) | catalog |
| NF-D12 rookie-coverage + publish guard | 2026-07-29 | **SHIPPED** — nflverse null-gsis race bridged (27/257 of the 2026 class incl. Carson Beck); exporter default-DRY-RUN + `--publish` | memory/`nf_d12` |

---

### Reconciliation summary (for the umbrella index)

- **Served version reconciled ✅** — live S3 payload (2026-08-04T04:49Z, the NF-C0e republish): `model_version=nfl_fantasy_nf1_5_v1`, `projection_source=nf1_5`, 858 players, 784/784 skill rows `calibrated_per_player`, `market_lean` + caveat present. Matches code constants and the NF1.5b serving record. **No registry entry exists — version authority is the artifact stamp + the bake-off JSON read back at build time** (registry-based reconciliation structurally impossible; doc it, don't "fix" it).
- **Differences-by-decision, NOT mismatches:** (a) NF3.4's transparency block stamps `nfl_fantasy_nf1_v1` (research model, self-labeled); (b) the served rookie point is deliberately the un-recalibrated slot curve while a ratified better model (NF-D16) sits HELD — that is a recorded PM decision (placement clause), with **NF-D21 (🟢 READY, unstarted) queued to flip it on at a board-blind λ=0.5**; (c) `projections.json`'s stamp intentionally overwrites the fastpath stamp although MVP-1 owns the levels — the two-layer design, documented in the exporter.
- **Brief corrections (per the umbrella's expect-errors lesson):** the task brief's "HELD = NF-D14/NF-D15/NF-D16" over-groups — only **NF-D16** is ratified-but-held; NF-D14 is a clean null (plumbing default-OFF) and NF-D15 a PM-ratified underpowered null with scheduled re-runs (nothing ratified for serving). Also the roadmap doc still carries the superseded "ESPN NO-GO" line (stale; the paste flow shipped without relaxing the red line).
- **Honest framing confirmed** in the live payload and on the public receipts page (zero-including CI disclosed). `best_alpha = 0`.
- **Headline nuance for the index:** the served core is **stable + calibrated** (all interval floors green 2026-08-01); the 32-item open list is launch-product build-out, not serving drift.
