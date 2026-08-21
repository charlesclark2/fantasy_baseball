# Production model state — NCAAF (game model + season-simulation futures)

**PROD-STATE-1g** · written 2026-08-04 · branch `prod-state-1g` · `best_alpha = 0` throughout.
Sibling sections: [`mlb_h2h.md`](mlb_h2h.md) · [`mlb_pitcher_k_props.md`](mlb_pitcher_k_props.md) · [`milb_prospect.md`](milb_prospect.md) · [`nfl_season_fantasy.md`](nfl_season_fantasy.md).

---

## ⚠️ SERVING STATUS — READ FIRST (this section's defining nuance)

> **NCAAF is NOT SERVING TODAY, and there is NO served `daily_model_predictions` version to reconcile against.**
> It is in scope as the 7th production model because **it would serve at NCAAF season start if left untouched** —
> the code side is complete and frozen; only the operator box-enables and the entire Phase-3 app remain.

Read that claim precisely, because it is easy to over- or under-state. Verified against code + the ablation
artifacts, the honest decomposition is:

| layer | state today | would it "run" at season start untouched? |
|---|---|---|
| Raw ingest (CFBD, Odds API) | ✅ built; **odds capture is LIVE and RUNNING on the box** (P0.6c, 2026-08-01) | ✅ yes — already running |
| Pre-season roll-forward (schedule + covariates) | ✅ built; schedule ships `default_status=STOPPED`, operator-enabled per P0.7 | ✅ yes (operator-verifiable) |
| dbt marts (`sports_dbt`, `ncaaf_marts`) | ✅ built; `sports_ncaaf_dbt_schedule` ships **STOPPED** | ⚠️ only if the operator enables it |
| P1.2 strength → P1.3 matrix → P1.4 distribution → P1.5 board | ✅ built + frozen; outputs land in the **S3 _research_ lakehouse** | ✅ yes — a board renders to S3 |
| Serving store / API / frontend | ⛔ **DOES NOT EXIST** (P3.1 keystone unbuilt; the whole NCAAF frontend is net-new) | ⛔ **no — nothing reaches a user** |

⇒ **"Would serve" means the model would keep PRODUCING calibrated output into S3 on the 2026 season; it does
NOT mean a user-facing surface appears.** The model is FROZEN and stable; the PRODUCT does not exist yet.
Keeping those two apart is the whole point of this section — see field (9).

**Version authority (field 7's real answer): NOT the registry.** NCAAF has **no `sub_model_registry.yaml`
entry** — verified: `grep -i "ncaaf|football|college" betting_ml/sub_model_registry.yaml` returns exactly **2
hits, both prose inside the `milb_mle_v1` description** (it credits the shared `hierarchical.py` solver
promoted out of the football tree). All 18 top-level registry keys (17 sub-models + the `bet_gate` config
block) are MLB/MiLB. The version-of-record is:

1. **the committed artifact JSONs** under `quant_sports_intel_models/football/ncaaf/models/artifacts/` — each
   carries a `model_version` / `version` string and a `generated_at`; and
2. **the `ablation_results/ncaaf_*.md` + `.json` memos** that gated them; and
3. `ncaaf_mart_inventory.md` for the mart/table catalogue.

⭐ Unlike MLB's champions (gitignored `.pkl` in S3), **the served NCAAF distribution parameters are a
committed, human-readable JSON in git** — a small but real governance advantage: the version-of-record is
diffable and cannot silently drift from the repo.

### Corrections to the brief / upstream docs (grounded, stated rather than silently absorbed)

| # | claim as written upstream | ground truth |
|---|---|---|
| 1 | "the **6** P2 stories" (PROD-STATE-1g brief) | the catalogue carries **10** P2 stories — P2.0, P2.1, P2.2, P2.3, P2.4, P2.5, P2.6, P2.7, P2.8, P2.9 — reorganised into **3 explicit tracks** by a 2026-08-03 PM pushback resolution (field 9) |
| 2 | the matrix width — "**180**-feature" (P1.4 memo prose) vs "**174** feature columns" (P1.3 artifact) | **both are right about different counts, and 180 is the one that matters.** Enumerated from the mart SQL + `feature_columns()`: the matrix is **200 output columns**; the **model-eligible `full` contract is exactly 180** (200 − 14 in-matrix id/CV-axis columns − 6 `label_*`); the artifact's **174 counts `home_*`/`away_*`-PREFIXED columns**, six of which are identity (4 string names/conferences — ineligible — plus the 2 numeric team ids). ⚠️ Incidental finding: **`home_team_id`/`away_team_id` are BIGINT and NOT in `_ID_COLS`, so the two numeric team ids WERE feature-eligible in the `full` contract** — despite the code comment saying team identity is excluded (it excludes the string NAMES only). Zero shipped impact (the `full` contract lost deflation and the served `strength_only` contract selects by prefix), but a P2 re-run of the full matrix should add them to `_ID_COLS` |
| 3 | P1.2 winner accuracy "**71.7%**" (`ncaaf_roadmap.md` §Phase-1B.3) | the P1.2 memo + `ncaaf_team_strength_summary.json` record **0.723** over 8,303 walk-forward games. The roadmap's 71.7% is a stale earlier-build figure. *(Same class, same doc: the roadmap's P1A "**3,804** rookie projections" is superseded by the 2026-07-29 refit's **3,829** — both are documentation lag against a later artifact, never deployment drift)* |
| 4 | P0.6c "roadmap: still to do / P0.6b STILL UNBUILT" (`ncaaf_roadmap.md` Phase-3 bullet + §P0.7) | **P0.6c is DONE and LIVE in prod since 2026-08-01** — T-1 + close snapshots backfilled 2020–2025, `NCAAF_ODDS_CAPTURE_T1=1` on the box, `sports_ncaaf_odds_capture_schedule` **RUNNING**. The roadmap text is stale; the story catalogue is current |
| 5 | the shipped model is "the reference `ridge/strength_only/gaussian`" (a natural reading of `REFERENCE_STANDS`) | ⭐ **the SHIPPED form is `strength_posterior`, not `gaussian`** — see field (2)/(5). The decide stage's reference is the gaussian; the form was swapped at `finalize` on a pre-registered early-season floor |
| 6 | `ncaaf_pm_pushback_response.md` cited by the story catalogue (2026-08-03) | **not present in this repo** — an external PM/author document. Its *conclusions* are transcribed into `ncaaf_story_prompts.md`; the source itself is not auditable here |
| 7 | §0.5 gate "PBO / DSR / **BH-FDR**" | P1.4's recorded gates are **PBO + DSR only** (`gates: {full_search_deflated: false, market_blind: true}`). **No BH-FDR figure was computed or recorded** for P1.4. Stated, not inferred |

---

## (1) What it predicts + the market/output

Two shipped products plus two feeder/sub-models, all market-blind.

### 1a. P1.4 — the game model (the flagship)

Models the **JOINT (margin, total) pregame scoring distribution ONCE**, then **derives all three markets** as
pure reads off it (mirrors MLB E2's per-side → convolve → read-off-every-market design):

| market | read off the joint |
|---|---|
| H2H / moneyline | `P(margin > 0)` |
| spread | `P(margin > line)` (line = −closing home spread) |
| total (O/U) | `P(total > line)` |

`margin = home − away`, `total = home + away`. The three single-market probabilities are **marginal** (ρ does
not change them); ρ is carried so a **same-game parlay is coherent** and the sides↔totals correlation is
honest. Output object: `models/ncaaf_game_predictor.py` → `load_params` → `sample_matchup(...)` →
`market_probabilities(...)`, plus a 19-level quantile grid (0.05…0.95) for distributional rendering.

### 1b. P1.5 — season-simulation futures

A 20,000-sim posterior-predictive season Monte-Carlo **on top of** the P1.4 game model, emitting per team:
`E[wins]` · `P(conference title)` · `P(CFP)` · `P(first-round bye)` · `P(reach final)` · `P(national title)`.
A live **2026 pre-season board (138 teams)** renders to S3 today.

### 1c. Feeder / sub-models inside the same tree (in the ledger, not the product)

- **P1.2 — team-strength engine** (`ncaaf_team_strength_v1`): week-by-week point-in-time neutral-field strength
  per team. Not a market output — it **is** the entire served feature contract of P1.4 (field 3).
- **P1.2b — freshman-production prior** (`ncaaf_freshman_projection_v1`): recruit rating → first-season
  production. A *feature-tier* sub-model; **not** in the served P1.4 contract.
- **P1A — college→NFL translation** (`ncaaf_college_nfl_translation_v1`): 3,829 `gsis_id`-keyed rookie
  projections. Physically in the NCAAF tree; its **consumer is NFL** (N1.2 rookie props / N1.3 dynasty), so it
  is out of scope as an *NCAAF product* but is recorded in the field-(10) ledger because its result changes
  what a future audit should recommend.

**Not predicted / not offered:** player props (P0.1 found NCAAF props THIN — marquee games/top players only),
live/in-game, derivatives, any pick or bet recommendation.

---

## (2) Architecture — champion + why it won

### 2a. The shipped P1.4 configuration

> ⭐⭐ **SUPERSEDED 2026-08-17 by NCAAF-P2.1 S1-serve — read §2a′ below FIRST.** The served contract
> is now **`strength_pace`** (`strength_only` ∪ the certified pace composites) and the served
> artifacts are **`ncaaf_game_distribution_v2.json` + `ncaaf_game_mean_v2.json`**. Everything in
> this §2a remains TRUE of the P1.4 record and of the frozen v1 artifact (which is still on disk and
> still byte-reproducible) — it is simply no longer what serves.

**`ridge / strength_only / strength_posterior`** — merged 2026-07-22, finalized on the operator run
2026-07-23, verdict **`REFERENCE_STANDS`**.

| axis | shipped value | note |
|---|---|---|
| learner (predicts μ_margin, μ_total) | **Ridge**, `alpha = 10.0`, on a `StandardScaler`-fitted frame; one Ridge per target | the pre-registered reference learner |
| feature contract | **`strength_only`** — the P1.2 strength prior alone (25 columns, field 3) | the FOIL the full matrix had to beat, and did not |
| distributional form | **`strength_posterior`** — heteroscedastic bivariate, per-game σ propagating the P1.2 posterior | ⭐ **not** the reference's `gaussian` — see 2c |
| seed | 42 | deterministic |

**Served parameters** (`models/artifacts/ncaaf_game_distribution_v1.json`, fit 2026-07-23, 6,024 OOS games):

```
version        ncaaf_game_distribution_v1      form           strength_posterior
sigma_margin   16.086901549597975              sigma_total    16.746709708076466
rho            0.05603365986298882             dof            30.0
sigma0_margin  15.608306376557337              k_margin       0.5733998774193014
sigma0_total   16.435109098643373              k_total        0.4986582179537887
r_home 200.0 · r_away 200.0   (NegBin `count`-form params — carried, INERT under strength_posterior)
n_draws 10000 · quantile_levels 0.05…0.95 (19)
dispersion_calibration: held-out OOS residuals (leakage-safe; the MLB E13.6 pattern)
```

**The width decomposition — the load-bearing contract** (and the reason P1.5 is a thin layer, not a
re-derivation):

```
σ_g²  =  σ₀²                        (irreducible game noise)
      +  k²·(home_sd² + away_sd²)   (P1.2 team-strength posterior uncertainty)
```

`(σ₀, k)` are MLE'd on held-out residuals — `k ≈ 0.50–0.57`, positive, i.e. **real propagation, not a
collapsed knob**. Per-game σ_margin ranges 15.9 → 16.6. A season sim draws each team's strength ONCE per
simulated season and must therefore call `sample_matchup(..., fixed_strength=True)` → **σ₀ only**, or the
strength uncertainty is DOUBLE-COUNTED. The served params carry σ₀ and k separately for exactly this.
Guard: `test_predictor_fixed_strength_narrows_to_game_noise_only`.

### 2a′. ⭐ What serves TODAY — `ridge / strength_pace / strength_posterior` (S1-serve, 2026-08-17)

NCAAF-P2.1 **S1** certified `pace` (+0.062 CRPS, 8/8 folds, per-fold DSR 0.998); **S1b** fixed the
served representation as the 2-column composite. **S1-serve** deployed both.
Read-out: [`../football/ncaaf/ablation_results/ncaaf_p2_1_s1_serve_readout.md`].

| axis | shipped value | changed vs §2a? |
|---|---|---|
| learner | Ridge, `alpha = 10.0`, one per target | no |
| feature contract | **`strength_pace`** = the 25 `strength_only` columns **+ `pace_sum`, `pace_diff`** (27) | ⭐ YES |
| distributional form | `strength_posterior` | no |
| served dispersion | `models/artifacts/ncaaf_game_distribution_v2.json` | ⭐ new file; v1 retained + frozen |
| served **mean** | `models/artifacts/ncaaf_game_mean_v2.json` — a coefficient table | ⭐ **NEW ARTIFACT CLASS** |

```
version  ncaaf_game_distribution_v2     form           strength_posterior
sigma_margin  16.08…                    sigma_total    16.64…      (was 16.75 under strength_only)
sigma0_margin 15.61…                    k_margin       0.572…
sigma0_total  16.19…                    k_total        0.571…
```

**μ IS NO LONGER IMPLICIT.** P1.4 shipped a dispersion artifact and *no* mean model: μ was rebuilt
analytically by P1.5 and supplied by the caller everywhere else. That was safe only while the
contract was `strength_only`. Serving a σ refit on pace residuals against a pace-free μ is the E7.9
train/serve mismatch, so the mean is now persisted as a **coefficient table** (columns, train-mean
impute vector, scaler mean/scale, ridge coef+intercept per target) — deliberately **not a pickle**
(the MLB unpinned-sklearn `_loss` landmine); a coefficient table is version-proof and diffable.
`ncaaf_game_predictor.load_served_pair()` **RAISES** if the dispersion and the mean were fitted on
different contracts, so the mismatch cannot be assembled by accident.

⭐ **A NULL feature contributes EXACTLY 0.0 to μ** (the scaler mean equals the NaN fill), so the
pace term is **inert pre-season** — 100 % of week-1 team-week rows are NULL — and a week-1 board is
byte-identical to the pre-S1-serve one (verified on the real 2026 board, not just in a unit test).
Pace acts from week 2 (`--as-of-week ≥ 2`).

**What measurably improved:** the served TOTAL distribution's PIT-flatness gate went **FAIL → PASS**
(max-decile-dev 0.0218 → 0.0173) and σ_total tightened 16.75 → 16.64. The P1.5 season-board gate is
**unchanged** (every leg inside seed noise) — correctly, since that board is a pre-season,
margin-only read and pace is a total-axis in-season effect. `best_alpha = 0` is untouched
(ATS 0.509 / O-U 0.513 vs a 0.5238 breakeven).

⚠️ **The P1.4 SEARCH FIELD IS STILL THE FROZEN FOUR.** `strength_pace` lives in
`POST_P1_4_CONTRACTS`, servable via `--contract` but outside `--stage bakeoff`'s sweep — pace was
certified under its OWN registration (P2.1 → S1), never inside P1.4's deflation. Re-running the
P1.4 bake-off or finalizing on `strength_only` reproduces the recorded record exactly (verified).

### 2b. Why it won — the bake-off, in one line

**It won by not losing.** 125 deflated configs (8 folds × 5 learners × 4 contracts × 4 forms + Optuna:
lgbm 40 / xgb 40 / catboost 21 trials), 32 CV buckets. The tuned gradient learners edged the reference on raw
score — `xgb__full__gaussian` 0.01920 vs the reference's 0.02420 — but the field was **densely tied** (top-15
span 0.0192 → 0.0226 ≈ 17%) and **neither PBO nor DSR cleared**:

| deflation stat | value | gate | result |
|---|---|---|---|
| full-search PBO | **0.648** | < 0.20 | ❌ FAIL |
| best DSR | **0.0075** | ≥ 0.95 (>0 minimally) | ❌ FAIL |
| `winner` | `null` | — | no promotion |
| `gain_vs_reference` | `0.0` | — | — |

Per the MLB **E2.1-r** reading: *a high PBO over a genuinely TIED field is the NULL, not overfitting* — "which
tied learner wins" is noise. ⇒ **the full 180-column matrix does NOT robustly beat the strength prior, so the
strength-prior-only choice is PROVEN, not a shortcut.** That is the single most decision-relevant fact in this
document for any future audit (field 10, entry T-1).

### 2c. ⭐ The form swap — the nuance `REFERENCE_STANDS` hides

The decide stage's reference is **`ridge__strength_only__gaussian`**. The **shipped** config is
**`ridge__strength_only__strength_posterior`**. The swap was deliberate and is documented, but it was **not
made on the primary selection metric** — on aggregate PIT the posterior form scores **0.0269 vs the
homoscedastic 0.0242, i.e. slightly WORSE**, and 0.0269 sits outside the top-15 band (which ends at 0.0226).

It ships on a **pre-registered small-N gate** added 2026-07-22, because the aggregate metric HID a real
defect. Sliced by season week:

| week bucket | n | margin calib_80 (homosced → posterior) | total calib_80 |
|---|---|---|---|
| **wk 1–2** (thin sample) | 684 | **0.785 → 0.804** | 0.791 → 0.814 |
| wk 3–4 | 783 | 0.794 → 0.799 | 0.807 → 0.814 |
| wk 5+ | 4,557 | 0.804 → 0.800 | 0.794 → 0.794 |

The homoscedastic form **under-covers weeks 1–2** (0.785, below the strict 0.80 floor); the posterior-predictive
fixes it at **no late-season cost** — and it is 3.4× wider in weeks 1–3 than week 8+ (corr with games-played
−0.65). The 4,557 late-season games swamped the 684 early ones in the aggregate.

⚠️ **CORRECTED 2026-08-20 by NCAAF-VAL1.** An earlier version of this paragraph added "early season is also
exactly where the college book is softest" as extra justification. **That clause is REFUTED**: stratifying the
vs-close CLV by pre-registered `season_order_week` bucket found weeks 1–3 to be the WORST bucket in both
markets (ATS 0.4936, O/U 0.4950 vs a 0.5238 breakeven), and its interval EXCLUDES a decision-changing edge.
The form choice above stands entirely on its CALIBRATION half — which is measured, reproduced and unaffected.
See `football/ncaaf/ablation_results/ncaaf_val1_clv_week_strat.md`.

**For an auditor:** this is a documented judgment call, not a metric violation — a candidate was selected on a
pre-registered FLOOR after the primary metric declared a tie. Record it as such; do not "discover" it later as
a discrepancy, and do not re-litigate it without re-running the early-season slice.

### 2d. The P1.2 strength engine (what actually produces μ)

A **hierarchical partial-pooling mixed-effects model, team nested in conference**, solved by
`models/hierarchical.py` (a sport-agnostic penalized-Gaussian solver: closed-form Gaussian posterior +
marginal-likelihood variance components, so ~200 leakage-safe refits run in minutes instead of NUTS-hours).
`strength_margin` = neutral-field points above an average FBS team, decomposed into **three additive, auditable
pieces**: conference pooling level + pre-season covariates + this season's games.

Fitted hyperparameters (stage A, each fit on **strictly prior seasons**):

| season | σ | home_field | tau_team | tau_conference | converged |
|---:|---:|---:|---:|---:|:--|
| 2021 | 8.186 | 2.095 | 7.495 | 2.423 | ✅ |
| 2022 | 8.351 | 1.866 | 7.603 | 1.934 | ✅ |
| 2023 | 8.442 | 1.817 | 7.271 | 1.654 | ✅ |
| 2024 | 8.679 | 1.991 | 6.668 | 1.252 | ✅ |
| 2025 | 8.202 | 2.561 | 6.934 | 1.055 | ✅ |
| **2026** | **7.936** | **2.848** | **7.050** | **1.769** | ✅ |

The 2026 row is the one that would drive a 2026 board. `home_field` is a **single league-wide constant** —
that is the model's biggest known structural gap (field 9 / P2.1 H1).

Pre-season covariate coefficients (points of strength per 1 sd): `prior_strength` **+4.342** ·
`hc_recent_sp_overall` **+4.120** · `team_talent` **+2.327** · `returning_ppa_pct` **+1.161** ·
`roster_continuity_pct` −0.292 · `hc_change_from_prev` / `is_first_year_at_school` −0.490 ·
`portal_net_stars` +0.002. (The `off__*` / `def__*` variants are NaN — they are not fit in the margin model.)

### 2e. P1.5 mechanics

1. **Draw each team's true season strength ONCE** per simulated season from its P1.2 week-1 posterior
   (`strength_margin ± strength_margin_sd`, `strength_sd_scale = 1.0` shipped) and **reuse it across that
   team's whole schedule** — the cross-game correlation that makes a futures number honest.
2. Simulate every game with `fixed_strength=True` (σ₀ only).
   `μ_margin = HFA + (sm_home − sm_away)` · `μ_total = 2·league_base + (off_h + off_a) − (def_h + def_a)`.
   ⚠️ **Sign trap:** `strength_offense` and `strength_defense` are BOTH higher-is-better (defense = points
   PREVENTED) ⇒ net strength is their **SUM**; the total subtracts the two defenses.
3. Bookkeeping → conference standings → simulated neutral CCG between the top two → the **2026 12-team CFP,
   STRAIGHT SEEDING** (the 2025-26 rule change, *not* the 2024 champions-seeded-1–4 rule): 5 auto-qualifiers
   (4 Power champions + best G5), top-4 byes, 5v12…8v9, simulated to a champion.
4. Count frequencies over N = 20,000 sims.

Mean-map fidelity verified against the served model: residual sd 16.4 vs served σ 16.1. Ruleset is explicit and
swappable (`CfpFormat`); tiebreak = (conf win-pct, overall win-pct, drawn strength) — a stated proxy.

---

## (3) Feature contract — what is actually served

### 3a. ⭐ The served contract is 25 columns, all from P1.2

`bakeoff_ncaaf_game._STRENGTH_PREFIXES = ("home_strength", "away_strength", "strength_margin_diff")` selects
the `strength_only` contract off `feature_ncaaf_pregame_matrix`. Enumerated from the mart SQL, that is
**12 home + 12 away + 1 differential = 25 columns**:

| column (× `home_` / `away_`) | meaning | note |
|---|---|---|
| `_strength_margin` | neutral-field points above an average FBS team | **the** point feature |
| `_strength_margin_sd` | posterior **PARAMETER** uncertainty of that estimate | ⚠️ ~1.5× too tight as a predictive sd — feeds the `k²` term, never priced raw |
| `_strength_offense` | points SCORED above average (higher = better) | totals leg |
| `_strength_defense` | points PREVENTED above average (higher = better) | 🚨 net = offense **+** defense; subtracting returns ~0 for everyone |
| `_strength_conf_component` | the conference pooling level (μ_conf) the team is shrunk toward | a pooling level, **not** a causal claim |
| `_strength_cov_component` | total pre-season covariate contribution | = roster_flux + coaching + talent + carryover |
| `_strength_team_component` | this season's games contribution | 0 at week 1 by construction |
| `_strength_cov_roster_flux` | returning production + roster continuity + net portal stars | the NIL/portal channel |
| `_strength_cov_coaching` | HC change / first-year / prior SP+ profile | HC-only |
| `_strength_cov_talent` | 247 team-talent composite contribution | |
| `_strength_has_sufficient_sample` | boolean sample-adequacy flag | cast 0/1 |
| `_strength_hyper_prior_seasons` | # prior seasons the row's hyperparameters were fit on | 2015 = 1 (thin) |
| `strength_margin_diff` *(game-level, not per side)* | `home_strength_margin − away_strength_margin` | the single-number read |

Grain: `(season, team_id, as_of_week)` **1:1**, as-of the game's own kickoff week. Booleans are features
(0/1/NaN); NULL is kept NULL and never imputed to 0.

### 3b. The training frame that EXISTS but is NOT served — full data dictionary

`feature_ncaaf_pregame_matrix` — **9,086 FBS-vs-FBS games (2014–2025) × 200 output columns**. Per-matchup
grain, `home_*`/`away_*` side by side. The complete accounting (enumerated from the mart SQL — nothing below
is inferred from prose):

| bucket | n | contents |
|---|---:|---|
| id / CV-axis (in `_ID_COLS`, **never features**) | 14 | `sport`, `game_id`, `season`, `week` ⚠️ reporting-only, `season_order_week` ⭐ the as-of axis, `season_type`, `is_postseason`, `game_date`, `start_date`, `game_venue_timezone`, `home_team`, `away_team`, `home_conference`, `away_conference` |
| `label_*` post-kickoff targets (**never features**) | 6 | `label_is_completed`, `label_home_points`, `label_away_points`, `label_total_points`, `label_home_margin`, `label_home_win` |
| **model-eligible (`full` contract)** | **180** | 82 per side (below) × 2 + 16 game-level (below) — incl. the 2 numeric team ids (banner correction #2) |

The assemble stage appends `game_year` (CV axis, in `_ID_COLS`) and the 6 CLV close columns
(`close_home_spread`, `close_total`, `close_home_ml_american`, `close_home_ml_prob`, `close_snapshot_ts`,
`has_close`) — all excluded from every contract (`_CLOSE_COLS` + `assert_market_blind`).

#### Game-level eligible columns (16)

| column | meaning |
|---|---|
| `home_team_id` / `away_team_id` | CFBD numeric team ids — ⚠️ eligible by accident (banner correction #2); an arbitrary integer key, not a designed feature |
| `is_conference_game` | both teams in the same conference AND the game counts for conference standings |
| `is_neutral_site` | neutral-site flag (also gates travel/altitude to NULL) |
| `is_same_conference` | `home_conference = away_conference` (overlaps `is_conference_game` but ignores scheduling designation) |
| `rest_days_diff` | `home_rest_days − away_rest_days` |
| `game_venue_elevation_m` | venue elevation (metres) |
| `game_venue_is_dome` / `game_venue_is_grass` | venue construction / surface booleans |
| `away_altitude_change_m` | game-venue elevation − the away team's OWN home-venue elevation (a body-adjustment signal); NULL on neutral sites |
| `away_travel_km` | great-circle km from the away team's home venue to the game venue; home travels ~0; NULL on neutral sites or missing geo |
| `strength_margin_diff` | `home_strength_margin − away_strength_margin` — ⭐ in the SERVED contract (§3a) |
| `adj_net_ppa_diff` | home − away opponent-adjusted net PPA (the efficiency headline differential) |
| `team_talent_diff` | home − away 247 talent composite |
| `home_rest_days` / `away_rest_days` | days since each team's previous game |

#### Per-side eligible columns (82 × `home_`/`away_` = 164)

Every column below exists in both `home_*` and `away_*` variants. **Sign convention on all `off_`/`def_`
efficiency:** offense higher = better for the team; defense = what the team ALLOWS, so lower `def_ppa` /
`def_success_rate` / `def_explosiveness` is better (⚠️ distinct from the P1.2 `strength_defense` sign trap,
where higher = more points PREVENTED).

**Strength (P1.2) — 12, the SERVED family:** described column-by-column in §3a
(`_strength_margin`, `_sd`, `_offense`, `_defense`, `_conf_component`, `_cov_component`, `_team_component`,
`_cov_roster_flux`, `_cov_coaching`, `_cov_talent`, `_hyper_prior_seasons`, `_has_sufficient_sample`).

**Record / scoring base — 6** (as-of, current season to date):

| column | meaning |
|---|---|
| `_games_played` | games played so far this season (0 at week 1) |
| `_has_sufficient_sample` | boolean: enough games for the rolling metrics to be meaningful |
| `_win_pct` | season-to-date win % |
| `_points_for_per_game` / `_points_against_per_game` | season-to-date scoring for/against per game |
| `_margin_per_game` | season-to-date average margin |

**Efficiency, raw (P1.1) — 10** (per-play PPA = CFBD's EPA analog; "success" = CFBD's down-and-distance
success definition):

| column | meaning |
|---|---|
| `_off_ppa` / `_def_ppa` | mean predicted-points-added per offensive play / allowed per defensive play |
| `_off_success_rate` / `_def_success_rate` | share of successful plays run / allowed |
| `_off_explosiveness` / `_def_explosiveness` | mean PPA on successful plays (big-play tilt), run / allowed |
| `_off_clean_ppa` / `_def_clean_ppa` | the same PPA **restricted to scrimmage plays outside garbage time** (`is_scrimmage_play and not is_garbage_time`) — the score-effects-robust read |
| `_off_clean_success_rate` / `_def_clean_success_rate` | success rate under the same garbage-time exclusion |

**Line / trench (unit proxies) — 4:**

| column | meaning |
|---|---|
| `_off_line_yards` / `_def_line_yards` | line yards per rush credited to the OL / allowed by the DL (the standard rushing decomposition) |
| `_off_stuff_rate` / `_def_stuff_rate` | share of rushes stopped at/behind the line, suffered / inflicted |

**Pace / style — 3:** `_off_plays_per_game` · `_possession_seconds_per_game` · `_seconds_per_play`
(tempo — lower = faster).

**Box-score rates — 6:** `_total_yards_per_game` · `_rushing_yards_per_game` · `_passing_yards_per_game` ·
`_turnovers_per_game` · `_third_down_rate` (conversion %) · `_completion_rate`. (The two scoring per-game
columns sit under record/scoring above.)

**Drive quality — 5** (from `fact_ncaaf_drive`):

| column | meaning |
|---|---|
| `_points_per_drive` | points per offensive drive |
| `_scoring_opportunity_rate` | share of drives reaching the opponent's 40 (`end_yards_to_goal ≤ 40`) |
| `_three_and_out_rate` | share of drives that go three-and-out |
| `_explosive_drive_rate` | share of drives gaining ≥ 40 yards |
| `_avg_start_yards_to_goal` | average starting field position (higher = worse field position) |

**Efficiency, opponent-adjusted (P1.1 2-pass) — 9:**

| column | meaning |
|---|---|
| `_adj_off_ppa` / `_adj_def_ppa` / `_adj_net_ppa` | PPA after the 2-pass schedule adjustment (net = off − def) |
| `_adj_off_success_rate` / `_adj_def_success_rate` | schedule-adjusted success rates |
| `_adj_points_for_per_game` / `_adj_points_against_per_game` | schedule-adjusted scoring rates |
| `_sos_opponent_net_ppa` | strength of schedule = mean opponent net PPA faced |
| `_has_reliable_adjustment` | boolean: enough games for the adjustment to be stable |

**Roster continuity / portal / talent (P0.4, pre-season broadcast) — 10:**

| column | meaning |
|---|---|
| `_returning_ppa_pct` | share of last season's production (PPA) returning (CFBD `/player/returning`) |
| `_returning_usage` | share of last season's usage returning |
| `_roster_continuity_pct` | returning players ÷ current roster size |
| `_roster_retention_pct` | returning players ÷ LAST season's roster size (churn read from the other side) |
| `_portal_net_count` | portal ins − outs |
| `_portal_in_blue_chip` / `_portal_out_blue_chip` | 4★/5★ portal arrivals / departures |
| `_team_talent` | 247 team talent composite |
| `_team_talent_yoy_delta` | year-over-year change in that composite |
| `_portal_data_covered` | ⚠️ era flag: pre-2021 portal data does not exist — 0 there is UNKNOWN, not "no churn" |

**Freshman prior (P1.2b, pre-season broadcast) — 5:** `_n_incoming_freshmen` ·
`_freshman_proj_production` (Σ projected first-season production over the incoming class, standardized z) ·
`_freshman_top_proj_production` (the class's best single projection) · `_freshman_avg_rating` (mean composite
recruiting rating) · `_freshman_blue_chip_count` (4★/5★ count).

**Coaching, HC-only (P0.5, pre-season broadcast) — 7:**

| column | meaning |
|---|---|
| `_hc_tenure_years` | head coach's years at this school |
| `_hc_first_year_at_school` / `_hc_change_from_prev` | new-at-school / changed-since-last-season flags |
| `_hc_prior_sp_overall` / `_hc_prior_sp_offense` / `_hc_prior_sp_defense` | the coach's PRIOR career SP+ track record (overall/off/def) — quality + scheme profile, not just a change flag |
| `_hc_is_first_time` | first-time head coach anywhere (censoring flag for the prior-SP+ columns) |

**QB continuity — 5** (derived from `fact_ncaaf_player_game`, strictly prior starts only — the derivable
half; ⚠️ NOT an availability/injury signal, none exists for CFB):

| column | meaning |
|---|---|
| `_qb_starts_prior` | the current-era starter's career starts before this game |
| `_qb_distinct_starters_prior` | distinct QB starters used this season (instability) |
| `_qb_starter_changed_recent` | starter changed in the recent window |
| `_qb_trailing_ypa` / `_qb_trailing_qbr` | the starter's trailing yards-per-attempt / QBR over strictly prior starts |

*(Count check: 12 + 6 + 10 + 4 + 3 + 6 + 5 + 9 + 10 + 5 + 7 + 5 = 82 per side ✓; ×2 + 16 game-level = 180
eligible ✓; + 14 id + 6 labels = 200 ✓.)*

The families map to source marts as follows:

| family | representative columns | source mart | join grain | as-of |
|---|---|---|---|---|
| **Team strength (P1.2)** ⭐ **SERVED** | `{h,a}_strength_margin`, `_offense`, `_defense`, `_sd` | `ncaaf_team_strength_week` | (season, team_id, as_of_week) 1:1 | kickoff week |
| Efficiency (raw) | `_off_ppa`, `_success_rate`, `_explosiveness`, `_clean_*` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Efficiency (opp-adj) | `_adj_net_ppa`, `_adj_off/def_*`, `_sos_opponent_net_ppa` | `rollup_ncaaf_team_week_opponent_adjusted` | 1:1 | kickoff week |
| Pace / style | `_off_plays_per_game`, `_seconds_per_play`, `_possession_seconds_per_game` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Line / trench (UNIT proxies) | `_off/def_line_yards`, `_off/def_stuff_rate` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Drive quality | `_points_per_drive`, `_scoring_opportunity_rate`, `_three_and_out_rate` | `rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |
| Roster continuity / portal / talent | `_returning_ppa_pct`, `_roster_continuity_pct`, `_portal_net_count`, `_team_talent` | `ncaaf_team_roster_continuity` (P0.4) | (season, team) BROADCAST | pre-season |
| Freshman prior (P1.2b) | `_freshman_proj_production`, `_top_proj_production`, `_avg_rating`, `_blue_chip_count` | `ncaaf_team_freshman_prior` | (season, team) BROADCAST | pre-season |
| Coaching (HC-only, P0.5) | `_hc_tenure_years`, `_hc_change_from_prev`, `_hc_prior_sp_*` | `ncaaf_team_coaching_change` | (season, team) BROADCAST | pre-season |
| QB continuity | `_qb_starts_prior`, `_qb_distinct_starters_prior`, `_qb_starter_changed_recent`, `_qb_trailing_ypa/qbr` | `fact_ncaaf_player_game` (derived) | per side, prior starts only | strictly prior games |
| Situational / rest | `is_neutral_site`, `is_conference_game`, `_rest_days`, `season_order_week` | `dim_ncaaf_game` + schedule | game-level | kickoff |
| Environment (travel/altitude) | `away_travel_km`, `away_altitude_change_m`, `game_venue_elevation_m`, `_is_dome/grass` | `dim_ncaaf_team` venue geo | game-level, non-neutral | kickoff |

Per-family coverage is reported per season in `ncaaf_p1_3_feature_matrix.md`; the legitimately-empty cells are
labelled (strength NULL for 2014; portal a real 0 only from 2021; efficiency/pace/QB NULL at each team's week
1; travel NULL on neutral sites by design).

### 3c. ⭐ Were feature ADDITIONS explored? — **YES, exhaustively, and they LOST**

This is the opposite posture from MLB K-props (whose pre-registered set is the only set ever tested). NCAAF ran
**four pre-registered contracts** — `full` (all 180 model-eligible) · `strength_only` (25) · `clustered` (|ρ|≥0.95 redundancy
prune) · `top_k` (in-fold gain top-60) — crossed with 5 learners × 4 forms + Optuna, **125 configs, every one
counted toward deflation**. The full matrix did not survive. ⇒ **the NCAAF feature space is EXHAUSTED at this
level of search, not untried.** A future audit recommending "add more features" is re-running a dead end; the
open lever is **structure** (HFA, matchup interactions, latent O/D/pace), not width — and the roadmap says so
explicitly ("a feature-expansion story would be low-EV padding, deliberately NOT added").

### 3d. Explicitly excluded / not in the matrix (and why)

- **Market/closing-line columns** (`close_home_spread`, `close_total`, `close_home_ml_*`, `close_snapshot_ts`,
  `has_close`) — excluded from every contract by `assert_market_blind`, which runs on the column list before
  any fit. They live **only** in the finalize CLV eval.
- **Team / conference NAMES** — high-cardinality identifiers; team quality is already encoded by the strength
  ratings, and one-hot-encoding names would only invite memorisation.
- **Injury / availability** — college football has **no mandated injury report** and P0.1 established no source.
  The QB block is the derivable half only (starter continuity + trailing efficiency from strictly prior starts).
- **OC/DC coordinators** — no free CFBD endpoint; deferred like NIL-$.
- **`is_rivalry`** — no confirmed CFBD field or maintained pair list, so it is **dropped rather than guessed**.
- **Individual OL production** — confirmed PFF-only gap; only unit-level trench proxies exist.
- **aDOT / air yards / CPOE** — corrected by P0.1: **not free anywhere** (PFF-only).
- **NIL $ valuations** — paid/scraped (On3/Rivals); the free transfer/roster-continuity signal ships instead.

---

## (4) Training data

| | |
|---|---|
| **Primary source** | **CFBD (CollegeFootballData) API**, Patreon **Tier-3 ≈ $10/mo** (75k calls) — the one recurring NCAAF cost. Backfill needed ~15,800 calls; the free 1,000/mo tier was confirmed insufficient live |
| **Market source** | **The Odds API** — `odds_ncaaf_historical`, closing lines **2020–2025** (10,394 rows / 5,531 games, 27 books incl. Bovada) + a **T-1 (~24h pre-kickoff) snapshot** since P0.6c (2026-08-01), distinguished by `_snapshot_kind` ∈ {`close`,`t1`} |
| **Feeder source** | nflverse (college→NFL outcomes), bridged on the deterministic draft slot `(season, overall pick)` — 99.7% of CFBD draft picks 2015–25 resolve to a `gsis_id` |
| **Storage** | **S3 Delta**, `s3://credence-sports-lakehouse/ncaaf/{raw,derived}/<source>/` (season = a Delta partition inside). ⛔ **Snowflake-FREE — entirely off the MLB serving lane** |
| **Transform** | `dbt-duckdb`, the shared `sports_dbt` project (schemas `ncaaf_staging` / `ncaaf_marts`) — 21 NCAAF marts (4 dims, 4 facts, 3 rollups, the feature matrix, the model output marts, the xref) |
| **Fact volumes (P1.1)** | 18,124 team-games · 539k player-games · 214k drives · **1.55M plays** |
| **Player-advanced floor** | **2014** — `/ppa/players/games` and `/plays/stats` return zero before 2013/14 (team/box/PBP reach to 2004). ⇒ the backfill window is 2014–2025 |

### Windows per model

| model | training window | emitted | rows |
|---|---|---|---|
| P1.2 strength | 2014 seed (**not emitted**) → hyperparams from strictly prior seasons | **2015–2026** | 23,130 team-weeks |
| P1.3 matrix | — | 2014–2025 | 9,086 games × 200 cols |
| **P1.4 distribution** | 2018→2025 CV, calibrated on pooled OOS residuals | served params | **6,024 OOS games** |
| P1.4 CLV eval | 2020–2025 (odds floor) | — | 4,182 games with a close (ATS n=4,110 / O-U n=4,129) |
| P1.2b freshman | 2014 seed (not emitted) | 2015–2025 (11 classes) | 16,541 recruit priors + 1,424 team rows |
| P1A feeder | 2015 seed (not emitted) | 2016–2026 (11 classes) | 3,829 projections (2,149 trainable = 49.0%) |

### CV scheme — season-forward, DATE-purged

`PurgedWalkForwardSplit(year_col="game_year", date_col="game_date", min_train_seasons=3)`: train on all prior
seasons, evaluate one wholly held-out season → **2018→2025 = 8 folds** (32 CV buckets recorded).

⭐ **The purge band and fold ordering are by CALENDAR DATE, deliberately.** CFBD **restarts `week` at 1 for the
postseason**, so raw `week` sorts January's title game before September's week 2 — a live leak P1.1 caught and
cured (2024 Ohio State had FIVE games at `week ≤ 1`, and every as-of row from week 2 on absorbed them). The
only column that may order a season is **`season_order_week`**, and it is monotone in `game_date`. A source
guard, `test_bakeoff_cv_axis_is_season_order_not_raw_week`, **mechanically forbids** sorting by raw `week`.

Because an eval game sits in a wholly held-out season, there is **no within-season train/eval overlap at all**,
and the design **is the E13.7 cold-start analog by construction** — a week-1 eval game is predicted from
prior-season + pre-season data only. Verified, not assumed: **100% of week-1 eval games carry NULL in-season
efficiency** (`home_off_ppa`).

**Cost hygiene (§0.5):** ONE pull → one parquet cache (`betting_ml/data/cache/ncaaf_p1_4_game_matrix.parquet`);
every learner × contract × form × Optuna trial × fold reads that cache.

---

## (5) Validation — the §0.5 gate it passed (and the ones it did not)

### 5a. Selection metric + its hygiene proof

`downstream_score = PIT_max_decile_dev(margin) + PIT_max_decile_dev(total)` — **PIT-only**, lower better,
exactly as the MLB **E2.1-r metric correction** requires. `calib_80 ≥ 0.80` is a **FLOOR, never a target**.
`h2h Brier` is secondary. Every metric is sanity-checked against an **oracle floor** (guard
`test_oracle_is_the_scoring_floor`).

⭐ **The NCAAF-specific hygiene finding, and it runs the OPPOSITE way from MLB.** The MLB landmine —
inclusive-integer interval coverage inflates a correct DISCRETE predictive's `calib_80` to ~0.82–0.86 — is a
**low-mean** effect. NCAAF margin/total are **wide-support** integers (σ ≈ 13/17, so ±0.5 rounding is
negligible against a ±17-point interval), so a correctly-specified **oracle covers ≈ 0.80 exactly — there is NO
inflation to exploit**; the oracle guard measured it landing at 0.79–0.80, not 0.82+. Consequently a strict
`≥ 0.80` floor would **reject a perfect oracle on finite-n noise**, so the floor carries a small sampling
tolerance `_CALIB_FLOOR_TOL = 0.02`. **The wobble is DEFLATIONARY here** — the opposite direction from discrete
F5 baseball. An under-dispersed model (σ halved) still sits far below even the tolerant floor.

### 5b. The deflation result (the headline)

| statistic | value | gate | verdict |
|---|---|---|---|
| configs scored | **125** (all counted) | — | — |
| CV buckets | 32 | — | — |
| **full-search PBO** | **0.648** | < 0.20 | ❌ **FAIL** |
| **best DSR** | **0.0075** | ≥ 0.95 | ❌ **FAIL** |
| BH-FDR | **not computed** | — | ⚠️ named in the story spec, absent from the recorded gates |
| market-blind contract guard | held on **every** contract | required | ✅ |
| `gates.full_search_deflated` | `false` | — | recorded honestly |
| **verdict** | **`REFERENCE_STANDS`** | — | trustworthy tied-field NULL |

Read correctly (E2.1-r): the field is **tied** (top-15 span 17%), so a high PBO is the null — not overfitting.
The discriminator is the **spread**, and here it is narrow.

### 5c. The shipped distribution's gate (pooled, 6,024 OOS games 2018–2025)

| dist | calib_80 | PIT max-decile-dev | PIT-flat |
|---|---|---|---|
| margin | **0.800** | **0.0080** | ✅ |
| total | **0.802** | **0.0218** | ❌ |

- **calib floor: PASS ✅** · **PIT-flat: FAIL ❌** (the total) · **H2H Brier 0.1814** (pred rate 0.566 vs
  observed 0.583).
- ⚠️ **Honest caveat, carried forward:** the total marginal is *calibrated* (floor pass) but **mildly
  non-flat** — PITdev 0.0218, just over the ~0.02 bar. A small total-shape residual, acceptable for a
  market-blind product distribution at `best_alpha=0`, and now the clearest model-level target (P2.5). Margin —
  the H2H/spread driver — is cleanly flat.

**Early-season / cold-start floor (`season_order_week ≤ 3`, n = 1,051):** calib_80 margin **0.792** / total
**0.822**, margin PIT-flat ✅, **floor PASS ✅**; week-1 80% margin interval **43.06 vs 40.76 late-season
(×1.056)** — honestly wider when both teams have zero in-season games, which is the correct answer, not a
weakness; **cold-start no-peek 100%** ✅.

`gate_pass = {calib_floor: true, pit_flat: false, early_season_floor: true, cold_start_no_peek: true}`.

### 5d. ⭐ vs the CLOSING LINE (2020–2025) — the clean null that sets `best_alpha = 0`

| leg | model-side hit | n | benchmark |
|---|---|---|---|
| **ATS** | **0.4961** | 4,110 | placebo **0.4968** · breakeven **0.5238** |
| **O/U** | **0.5229** | 4,129 | breakeven **0.5238** |

**Both below breakeven; ATS is indistinguishable from its own placebo.** ⇒ a **clean, honest game-line null** —
the model is calibrated to reality but **does not beat the market game line**. `best_alpha = 0`.
Forward CLV cannot exist pre-season and is the in-season P0.6b/P0.6c-fed follow-on. Only snapshots with
`_snapshot_ts < commence_time` are eligible (leakage-safe close); the closes live **only** in the finalize CLV
eval, never as training features.

### 5e. P1.2 accuracy (vs realized margin — never vs a market)

| predictor | n | MAE | RMSE | winner accuracy |
|---|---:|---:|---:|---:|
| **strength model** | 8,303 | **13.001** | 16.429 | **0.723** |
| home-field only | 8,303 | 16.436 | 20.986 | 0.578 |
| zero (coin flip) | 8,303 | 16.743 | 21.292 | 0.420 |

Stable across all 11 seasons (12.35–13.93). Face validity: 2024 season-end top-3 = Ohio State / Notre Dame /
Texas — the actual CFP semifinal field, **with zero ranking input**. Independent-fit cross-check:
`strength_offense + strength_defense` correlates with `strength_margin` at **0.999**.

⚠️ **The honest self-flag that gated P1.4's whole design:** the emitted `strength_margin_sd` is
**PARAMETER uncertainty and is ~1.5× too tight as a predictive sd** — standardized-residual sd **1.469**
(1.00 = calibrated), realized 80% coverage **0.629** vs target 0.80, 95% coverage 0.823 vs 0.95. The cause is
stated rather than hand-waved: `residual_sigma` comes from a **recency-weighted** fit, so the fitted σ is the
variance a maximally-weighted observation would have, not the average game's (shortfall ≈ `E[1/w]`); two
smaller contributors are the empirical-Bayes plug-in and treating a game's two team-rows as independent.
**P1.4's `k` is exactly the E13.6 recalibration of that sd** — which is why the served form propagates it
through `k²` rather than consuming it raw.

### 5f. P1.5 held-out calibration (2016–2025 pre-season; 2015 dropped = P1.2 thin-seed noise)

- **9 of 10 national champions were pre-season TOP-4** on a market-blind board with no ranking input (the only
  miss: the 2025 Indiana shock).
- Expected-wins **MAE 1.64**, bias ≈ 0 (the cleanest dense game-layer check).
- Conference-title **Brier skill +0.04** (skillful); reliability well-calibrated with mild mid-bin
  over-confidence. `--strength-sd-scale ≈ 1.3` marginally improves that, but the natty prefers 1.0 ⇒
  **1.0 ships** (draw straight from the posterior).
  ⚠️ **Two corrections recorded 2026-08-17 (S1-serve re-run; neither is a model change).** (a) The
  figure was **+0.05** on the July marts and is **+0.04** on today's rebuilt marts — a DATA-VINTAGE
  difference, reproduced on unmodified `dev` with the frozen v1 artifact. (b) The gate had a real
  defect: once 2026 entered the strength mart, its 136 conference-eligible teams were scored as
  "did not win a title" (n 1257→1393, skill 0.0513→0.0272) — an **undecided outcome read as a
  negative one**, indistinguishable from a regression. Fixed; a season with no decided conference
  championships is now excluded from the leg with a loud ALERT, and the scored-season list is
  recorded on the result. The natty leg always had this guard; the conference leg did not.

### 5g. Sub-model gates

| model | selection | PBO | DSR | verdict |
|---|---|---:|---:|---|
| P1.2b freshman | leave-one-CLASS-out expanding CV, standardized-production MAE | **0.000** (6 configs × 8 CSCV) | **0.821** | winner `gbm@200-2-0.05` beats the position-mean null OOS (0.7011 < 0.7164, ~2% skill); DSR < 0.95 ⇒ **real but weak**; PBO/DSR reported, not HALTed |
| P1A feeder | leave-one-DRAFT-CLASS-out expanding CV | **0.000** (7 configs × 8 CSCV) | **0.994** | winner `stratified_ols` beats the null (0.7901 < 0.8107) **robustly** — but **loses decisively to draft slot alone (0.6417)** |

Both carry oracle-floor guards ("no candidate beats a target-seeing oracle → the metric is not inverted") and
leakage gates **verified to FAIL on a tampered class** — green means something.

---

## (6) Serving path — ⛔ NOT SERVING

### 6a. What does NOT exist

- ⛔ **No serving store.** No DynamoDB table, no S3 serving payload, no Railway PG. Model outputs land in the
  **research** lakehouse only.
- ⛔ **No API surface.** No FastAPI NCAAF router in `app/backend/`; therefore no API-Gateway route and no
  Cognito-authorizer question.
- ⛔ **No frontend.** The entire NCAAF vertical is net-new in `frontend/`; nothing exists.
- ⛔ **No `daily_model_predictions` row, no `model_version` column, no tier — nothing to reconcile.**
- ⛔ **No registry entry** (verified — see the banner).
- ⛔ **No `write_serving_store` / `predict_today` participation.** NCAAF touches **no** MLB serving code path
  and **no** Snowflake object.

**P3.1 (serving plumbing) is the declared keystone that gates every P3 surface**, and it is unbuilt.

### 6b. What DOES exist and run

The pipeline that would keep producing into S3:

```
CFBD API ─┐
          ├─► ingest/ (Lambda-style pulls) ──► s3://credence-sports-lakehouse/ncaaf/raw/<source>/  (Delta)
Odds API ─┘                                                   │
                                                              ▼
                       dbt-duckdb `sports_dbt` (ncaaf_staging → ncaaf_marts, 21 marts)
                                                              │
   ┌──────────────────────────────────────────────────────────┤
   ▼                                    ▼                     ▼
run_team_strength.py             run_feature_matrix.py   run_season_simulation.py
 → ncaaf_team_strength_week       → feature_pregame_matrix  → season_simulation_board
 → s3 …/ncaaf/derived/            → s3 …/ncaaf/derived/     → s3 …/ncaaf/derived/
                                                              ▲
                        bakeoff_ncaaf_game.py --stage finalize ┘
                        → models/artifacts/ncaaf_game_distribution_v2.json  (σ — SERVES, committed)
                        → models/artifacts/ncaaf_game_mean_v2.json          (μ — SERVES, committed)
                        → models/artifacts/ncaaf_game_distribution_v1.json  (the frozen P1.4 record;
                          still committed, still byte-reproducible, no longer served — §2a′)
```

**Dagster jobs (all NCAAF-scoped, none on the MLB daily graph):**

| job | schedule | code default | live state |
|---|---|---|---|
| `sports_ncaaf_dbt_build_job` | `sports_ncaaf_dbt_schedule` (game-day morning) | **STOPPED** | operator-gated — assume STOPPED unless enabled |
| `sports_ncaaf_roll_forward_job` | `sports_ncaaf_roll_forward_schedule` (Mon 06:00 PT, Feb–Aug) | **STOPPED** | P0.7 records the operator **enabled** it 2026-07-24 (⏭️ operator-verifiable) |
| `sports_ncaaf_odds_capture_job` | `sports_ncaaf_odds_capture_schedule` (Mon 08:00 PT, Aug–Jan) | **STOPPED** | ⭐ **RUNNING** per P0.6c (2026-08-01), with `NCAAF_ODDS_CAPTURE_T1=1` on the box |

⚠️ **The `default_status=STOPPED` on all three is a DELIBERATE E11.23 carve-out** (operator-gated schedules
that need a prereq key or spend an external budget), not an oversight — but it carries the documented cost:
a STOPPED schedule **silently never fires**, the "silently never runs" outage class. The intended state lives
in `BOX_OPERATIONS.md §10`. **This section cannot read Dagit**, so the live states above are sourced from the
story-catalogue records and are **operator-verifiable**, not independently confirmed here.

### 6c. The one NCAAF component that IS live in production today

**P0.6c closing-line + T-1 capture.** `odds_ncaaf_historical` carries both a ~5-minute close and a ~24h-prior
(T-1) snapshot per game, distinguishable by `_snapshot_kind`. Backfilled 2020–2025 (62,633 credits, T-1 only;
verify PASS all six seasons, 0% FBS-orphan, Bovada present). The merge dedup key `(event_id,
_requested_snapshot)` keeps close and T-1 from clobbering each other — pinned by a snapshot-grain regression
test. ⚠️ Its PR was recorded **open, not yet merged to main** as of 2026-08-01 — worth confirming.
⚠️ `--weeks` semantics **changed**: it now SKIPS already-captured kickoffs per snapshot-kind (only `--force`
re-pulls), so any runbook calling `--weeks` a full bypass of the coverage diff is **stale**.

---

## (7) Version + last retrain + cadence

### 7a. Version authorities (there are FIVE, and none is the registry)

| component | version-of-record | value | last fit / generated |
|---|---|---|---|
| **P1.4 game distribution** | committed artifact JSON `models/artifacts/ncaaf_game_distribution_v1.json` (+ `ablation_results/ncaaf_p1_4_calibration.json`) | `ncaaf_game_distribution_v1` | **2026-07-23** |
| **P1.2 strength engine** | `models/artifacts/ncaaf_team_strength_summary.json` + the `ncaaf_team_strength_week` mart | `ncaaf_team_strength_v1` | **2026-07-24T07:20:25Z** (23,130 rows, 2015–2026) |
| **P1.5 futures board** | ⚠️ **no version string** — the board parquet + its `.meta.json` (form, σ₀, hfa, league_base, `strength_sd_scale`, CFP format, n_sims) in `ncaaf/derived/season_simulation_board/` | *(none)* | 2026-07-24 (2026 board, as-of week 1) |
| **P1.2b freshman prior** | `ncaaf_freshman_projection_summary.json` | `ncaaf_freshman_projection_v1` | 2026-07-22T04:43Z |
| **P1A college→NFL feeder** | `ncaaf_college_nfl_translation_summary.json` | `ncaaf_college_nfl_translation_v1` | **2026-07-29T20:37Z** (the most recently refit NCAAF-tree model) |

⭐ **P1.5's missing version string is a real governance gap** — the futures board is a *published product
artifact* whose provenance rests entirely on a sidecar meta JSON with no semantic version. If P1.4's params are
ever refit, two boards become indistinguishable by name.

### 7b. Retrain cadence — and the drift asymmetry that matters

| component | cadence | mechanism |
|---|---|---|
| P1.2 strength | **weekly in pre-season** (roll-forward job's mart-rebuild step) + a **once-per-season close-to-kickoff refit** | `sports_ncaaf_roll_forward_job` (Feb–Aug) then `sports_ncaaf_dbt_schedule` in-season |
| P1.3 matrix | rebuilt with the marts | dbt |
| **P1.4 σ/ρ/dof/k calibration** | ⛔ **NONE — frozen at 2026-07-23, no scheduled refit, no drift monitor, no refit/rollback trigger** | manual `--stage finalize` |
| P1.5 board | on demand (`run_season_simulation --season 2026 --s3`) | manual / operator |
| P1A feeder | **annual manual draft-class refresh** (tell: the latest class reads all-UDFA) | manual |

⭐ **THE ASYMMETRY, stated plainly because it is the most audit-relevant governance finding in this document:**
**the μ side refreshes and the σ side does not.** P1.2 strength (which produces μ) re-fits as 2026 covariates
publish, while the P1.4 dispersion calibration `(σ₀, k, ρ, dof)` is frozen from a 2018–2025 held-out fit with
**no cadence, no drift monitor, and no refit trigger**. Every published probability and every futures number
consumes both. This is the same class of gap KP-V2.0 opened for MLB K-props (no registry entry, no drift
monitor, no scheduled retrain) — NCAAF has it too, and additionally has no registry entry at all.
`best_alpha = 0` bounds the harm (no bet rides on it), but a **calibration-drift monitor is a genuine
prerequisite before any P3 surface publishes these numbers to users** — and the P2 program already names
"in-season calibration monitoring (rolling PIT/coverage/CRPS + model-version drift)" as a committed-track item
that the P3.7 track-record surface would consume.

### 7c. Reconciliation

**No mismatch is possible and none is claimed** — there is no served artifact to disagree with the docs. The
artifact JSONs, the ablation memos, and `ncaaf_mart_inventory.md` are **mutually consistent** on every figure
this document quotes; the only doc-vs-artifact drifts found are the **stale roadmap prose** items in
corrections #3 and #4 of the banner (a stale winner-accuracy figure and a stale P0.6b/P0.6c status), both of
which are documentation lag, **not** deployment drift.

---

## (8) Honest-framing status — `best_alpha = 0`, confirmed

✅ **Confirmed: no edge, win-rate, ROI, or bet recommendation rides on any NCAAF model.**

- **Game lines:** the vs-close CLV leg is a **clean measured null** (ATS 0.4961 ≈ placebo 0.4968; O/U 0.5229;
  both under the 0.5238 breakeven). Recorded verbatim in both the memo and the JSON:
  *"best_alpha=0 until this beats breakeven AND the placebo under deflation, confirmed by a forward in-season
  CLV window."*
- **Futures:** *"Product value, not an edge claim"* — futures carry a 20–40% hold and are brand/public-shaped;
  the de-vig-vs-market leg is a **scaffold** (`--futures-csv`) because historical futures odds were never
  captured (P0.6 is game-lines-only).
- **Every sub-model memo opens with an explicit disclaimer** — P1.2 (*"a strength PRIOR, not an edge claim…
  never against a market price"*), P1.2b, P1A, P1.3 all carry one.
- **Market-blind is enforced mechanically, not by convention:** `assert_market_blind` runs on every contract's
  column list **before any fit**; closing lines exist only in the finalize CLV eval.
- **Brand directives already on record for the unbuilt app:** P3 is **probability-first / distributional**
  (lead with the win probability and the margin/total curve, not a pick); **P3.7's framing is brand-critical** —
  a market-blind projection/calibration track record, *"never a win-rate/edge claim… labeled as a backtest, not
  'we called these live'"*.
- **A product-language policy exists** (2026-08-03) banning "edge" / "market-beating" / "best bet" /
  "expected profit" / "winning subset" / any place-this-bet recommendation from the product surface, regardless
  of what the gated edge-research track finds.

⚠️ **One naming tension to watch, flagged not resolved:** the P2 catalogue contains **P2.3 "BEST-AVAILABLE-BETS"
— a confidence-RANKED pick surface**. Its own spec keeps the deflation-gated realized-edge question separate
and the product-language policy forbids the phrase — but the story TITLE is exactly the language the policy
bans. If P2.3 ever ships, the surface copy must be reviewed against that policy explicitly.

---

## (9) Known limitations + open follow-ups

### 9a. ⭐ The framing that matters most: FROZEN MODEL ≠ EXISTING PRODUCT

The NCAAF model set is **built, validated, and frozen** (Phase 1 complete, both launch data-gates closed). The
NCAAF **product does not exist** — no serving store, no API, no page. These are independent axes and conflating
them is the single easiest mistake to make about this vertical. An explicit operator decision (2026-07-26)
governs the sequencing: **P2 model refinement runs AHEAD of P3 app work** — *"a better model is more important
than getting it live in the app — we don't want to surface something that hasn't been built really well"* —
with the **accepted, on-record trade-off that NCAAF is NOT live for the 8/29 kickoff and launches mid-season on
the refined model.** The Phase-3 "8/29 soft deadline" in older roadmap prose is **superseded**.

### 9b. Model-level limitations (each with its named successor story)

| # | limitation | evidence | successor |
|---|---|---|---|
| L1 | **ONE constant league-wide HFA** — `margin = hfa + (θ_h − θ_a)`, so OSU-home ≈ UMass-home ≈ 2–3 pts. Real HFA varies with altitude, crowd/venue, dome, visitor travel; the book prices it per venue | fitted `home_field` 1.82–2.85 pts, a single scalar per season | **P2.1 H1** — named "the biggest clean win" |
| L2 | **The spread leg is not matchup-aware** — it runs on NET `strength_margin`, so two same-net teams with opposite profiles get an identical spread. ⚠️ the TOTALS leg already uses the offense/defense split | model formula | **P2.1** (the "sharpest edge angle") |
| L3 | **Total PIT is mildly non-flat** (PITdev 0.0218 vs the ~0.02 bar) — calibrated but a residual shape defect | §5c | **P2.5** (subsumes P2.1 H14/H15) |
| L4 | `strength_margin_sd` is **parameter uncertainty, ~1.5× too tight** as a predictive sd | §5e | mitigated (P1.4's `k`); structurally open |
| L5 | **`μ_conf` under-exploited** — an explicit decomposition output used only for shrinkage today | model formula | **P2.1(c)** / **P2.6** |
| L6 | **Empirical-Bayes plug-in throughout** — σ, tau_team, tau_conference, covariate coefficients are point estimates from the prior-season fit, not integrated over | P1.2 §7 | open by design |
| L7 | **P1.2 points-model convergence warnings** on 2018/2019/2020/2021/2023 (variance-component optimizer hit max evaluations) and a 2025 `conf_def` component **hit a bound at 0.001 (unidentified)** | P1.2 run notes | ⚠️ **not tracked by any successor story** — flagged here |
| L8 | **2015 is thinly calibrated** — hyperparameters from a single prior season (759 games); disclosed per row via `hyper_n_prior_seasons` / `hyper_n_games` | P1.2 §7 | downstream may down-weight |
| L9 | **Pre-2021 portal data does not exist** — `portal_data_covered = false`; a `portal_net_stars_missing` indicator, **never a fabricated 0** | P0.4 / P1.3 | data-era limit |
| L10 | **P1.5 committee seeding is a transparent heuristic, not the committee**; **divisions are not modelled**; multi-way NCAA tiebreakers are approximated by the strength ordering | P1.5 §limitations | stated + swappable (`CfpFormat`) |
| L11 | **No historical futures odds exist** ⇒ the futures de-vig/edge leg is a scaffold | P1.5 | data-gated |
| L12 | **Forward CLV cannot exist pre-season** — the ship bar was the offline vs-close eval; forward CLV is the in-season confirmation | P1.4 | P0.6b/P0.6c-fed, post-kickoff |
| L13 | **P1.5 has no version string** (§7a); **P1.4 calibration has no refit cadence or drift monitor** (§7b) | this doc | governance gap |

### 9c. Data-coverage gaps (structural, priced in)

No CFB injury/availability source (⇒ QB block is continuity-only) · OC/DC coordinators unavailable free ·
individual-OL production is a confirmed PFF-only gap · aDOT/air-yards/CPOE are PFF-only · no snap counts (proxy
= `/player/usage`) · no `is_rivalry` (dropped, not guessed) · neutral-site venue geography left NULL by design ·
NCAAF props are THIN (marquee only) ⇒ **no MLB-style prop engine is possible here** · PFF College is a
**website subscription, not an API/bulk licence** — an edge-gated *licensing* project, never a line item.

### 9d. Open follow-ups

**Operator / ops:**
1. Confirm the live Dagit state of all three NCAAF schedules against `BOX_OPERATIONS.md §10` (this doc could
   not read them).
2. **The close-to-kickoff P1.2 refit** — the 2026 board currently leans on cold-start / 2025 carry-forward
   (Indiana leads); re-fit once fall-camp covariates publish, then re-render the board.
3. Confirm the **P0.6c PR merged to main** (recorded open on 2026-08-01).
4. Post-kickoff acceptance: `verify_odds_historical.py --seasons 2026`.

**Program (10 P2 stories in 3 tracks, per the 2026-08-03 pushback resolution):**
- **① COMMITTED CALIBRATION TRACK — ships regardless of edge; the product IS honest probability:**
  P2.1 H1 (HFA) · **P2.5** (total-distribution shape) · **P2.6** (latent O/D/pace + dynamic state-space
  strength, incl. cold-start init) · P2.1 H16 / P2.6 cold-start · a calibration/label audit that re-confirms
  outcome-label integrity and **FREEZES the strength-only reference** · in-season calibration monitoring.
- **② PROBE-FIRST DATA TRACK:** **P2.7** (player-availability feasibility probe — probe the source *before*
  modelling); coordinators stay deferred.
- **③ GATED EDGE-RESEARCH TRACK — research-only, high prior of a deflated null, ⛔ nothing ships as edge:**
  **P2.0** (market & timestamp audit + executable-price policy + market-only baselines — the foundation),
  P2.4 (market-as-measurement fusion, design-only), P2.9 (T-1↔close displacement — ⚠️ renamed from
  "line-movement modelling" because **2 snapshots support ONE delta, not a movement curve**), P2.3 (subset
  selection), P2.8 (portfolio, hard-gated on a real survivor).
- **Commit decision:** sessions committed for HFA, total-dist, parsimonious O/D/pace, cold-start, and the
  availability probe; design-only permitted for fusion; **⛔ not committed:** subset selection, portfolio,
  dense movement, complex mixtures/copulas, broad availability modelling.
- 📏 **A power discipline is now MANDATORY on every §0.5 leg:** run a power analysis **before fitting**
  (min-useful ΔCRPS/ΔBrier → simulate → reproduce the planned folds → P(select the right candidate) → shrink
  complexity or pre-label EXPLORATORY if power is inadequate); **start parsimonious** — at N ≈ 5,500
  odds-games the testable/underpowered split is the default (✅ parsimonious HFA, Student-t, low-dim
  conditional variance, strongly-pooled O/D/pace, static/small-global fusion, compact cold-start ·
  ⚠️ likely underpowered: flexible copulas, large mixtures, team-specific evolution variance, book
  microstructure, portfolio covariance); and **classify every null** DEFLATED_NULL · UNDERPOWERED_INCONCLUSIVE ·
  DATA_GATED · CALIBRATION_IMPROVEMENT · SURVIVOR — ⛔ never read an underpowered null as proof of absence.
  (This is the NCAAF-local restatement of MH2's `GENUINE_ABSENCE` vs `POWER_LIMITED` distinction.)

**Product (Phase 3 — 9 stories, ALL unbuilt):** **P3.1 serving plumbing (KEYSTONE — gates 3.2–3.7)** ·
P3.2 game-predictions surface (flagship, distributional curves) · P3.3 team stats · P3.4 player stats ·
P3.5 conference standings · P3.6 futures board · P3.7 backtest/track-record (⚠️ framing brand-critical) ·
P3.8 team logos/assets · P3.9 nav + entitlement (NCAAF is **betting-only ⇒ FREE** per E9.45).

---

## (10) ⭐ TRIED & RESULT LEDGER

*The audit-critical field: what has already been tested, and what came back — so a later audit does not
re-recommend a dead end. Null states follow `cv_power.classify_null` where a §0.5 gate was actually run.*

### 10a. Architecture / learner class

| # | candidate | when | result | null state | source |
|---|---|---|---|---|---|
| T-1 | ⭐ **The full 180-column pregame matrix (`full` contract) under 5 learners × 4 forms + Optuna — "does more data beat the strength prior?"** | 2026-07-23 | ❌ **LOST.** Tuned xgb/lgbm/catboost edged the reference on raw score (0.0192 vs 0.0242) but **PBO 0.648 / best DSR 0.0075** — did not survive deflation over a **tied** field (top-15 span 17%). ⇒ **the strength-prior-only choice is PROVEN, not assumed** | **trustworthy tied-field NULL** (`REFERENCE_STANDS`; the E2.1-r reading — high PBO over a tied field IS the null) | `ncaaf_p1_4_game_model.md` · `ncaaf_p1_4_game_bakeoff.{md,json}` |
| T-2 | `lgbm` (Optuna, 40 trials) | 2026-07-23 | ❌ lost — best 0.02040, inside the tie band | part of T-1 | bakeoff JSON |
| T-3 | `xgb` (Optuna, 40 trials) | 2026-07-23 | ❌ lost — best raw score 0.01920 (rank 1) but **no promotion**; `winner: null`, `gain_vs_reference: 0.0` | part of T-1 | bakeoff JSON |
| T-4 | `catboost` (Optuna, 21 trials) | 2026-07-23 | ❌ lost — best 0.02050 | part of T-1 | bakeoff JSON |
| T-5 | `ngboost_normal` (native per-game σ — the learned-heteroscedasticity foil) | 2026-07-23 | ❌ lost — the **`native` form UNDER-COVERS at 0.72** calib_80 | genuine loss (a measured coverage failure, not a tie) | `ncaaf_p1_4_game_model.md` |
| T-6 | **`ridge` + `strength_only`** | 2026-07-23 | ✅ **SHIPPED** (as the reference that stood) | — | — |

### 10b. Distributional form (the ≥3-form §0.5 axis)

| # | candidate | result | note |
|---|---|---|---|
| T-7 | `gaussian` (bivariate Normal + E13.6 σ recalibration) | the **decide-stage reference** (0.0242) — but **not shipped** | under-covers wk 1–2 at 0.785 |
| T-8 | ⭐ **`strength_posterior`** (heteroscedastic; per-game σ propagates the P1.2 posterior, `(σ₀,k)` MLE'd held-out) | ✅ **SHIPPED at `finalize`** | scores 0.0269 aggregate (worse than 0.0242) but **holds the pre-registered early-season floor** at 0.804/0.814 where the gaussian misses; identical late-season. `k ≈ 0.50–0.57` (positive ⇒ real propagation) |
| T-9 | `student_t` (heavy tails for blowouts / back-door covers; dof MLE'd) | ❌ lost — best `lgbm__full__student_t` 0.02150 | inside the tie band |
| T-10 | `native` (NGBoost learned σ) | ❌ lost — **calib_80 0.72** | the clearest single-form failure |
| T-11 | `count` (home/away NegBin convolved — the MLB-style discrete foil) | ❌ lost | `r_home/r_away = 200` survive as inert artifact fields |

### 10c. Feature contract / selection

| # | candidate | result | null state |
|---|---|---|---|
| T-12 | `clustered` (\|ρ\| ≥ 0.95 redundancy prune) | ❌ lost — best `lgbm__clustered__gaussian` 0.02170 | tied-field |
| T-13 | `top_k` (in-fold gain top-60) | ❌ lost | tied-field |
| T-14 | **Adding features generally** | ⛔ **CLOSED AS A DIRECTION** — the roadmap states a feature-expansion story would be "low-EV padding, deliberately NOT added"; the open lever is **structure**, not width | consequence of T-1 |

### 10d. Feature-family / sub-model findings

| # | candidate | when | result | null state | source |
|---|---|---|---|---|---|
| T-15 | **Freshman-production prior from recruiting rating (P1.2b)** — 4 pre-registered classes: partial-pool (`hierarchical.py`), position-stratified OLS, GBM, position-mean NULL floor | 2026-07-21/22 | 🟡 **REAL BUT WEAK.** `gbm@200-2-0.05` beats the null OOS (MAE 0.7011 < 0.7164, ~2% skill), **PBO 0.000** (robust) but **DSR 0.821 < 0.95**. Emitted anyway as a candidate FEATURE; proj↔realized corr TE 0.30 / DL 0.28 / WR 0.27 / ALL 0.20, ATH ~0.02 | **POWER-LIMITED** (real, doesn't clear strict live-grade deflation; PBO/DSR reported, not HALTed) | `ncaaf_p1_2b_freshman_projection.md` |
| T-16 | **The freshman prior inside the P1.4 game model** | 2026-07-23 | ❌ **not in the served contract** — it lives in the `full` matrix, which lost | subsumed by T-1 | — |
| T-17 | **Roster/portal/NIL flux as a strength covariate** | 2026-07-20 | ✅ **KEPT — sanity check PASSED.** Component sd 2.07 pts across teams (max \|contribution\| 27.4); the biggest movers are plausibly-churned teams (2021 UMass −27.4, 2019 UConn, 2019 Rutgers), *read* not merely counted | validated | `ncaaf_p1_2_team_strength.md` §3 |
| T-18 | **NIL $ valuations** | 2026-07 | ⛔ **DEFERRED — never ground-truthed** (no public bulk API ⇒ scrape/enterprise, like PFF). Revisit only if an ablation shows residual error the roster-$ channel would explain beyond portal-flux + returning-production | **not tested** (not a null) | `ncaaf_data_inventory.md §10` |
| T-19 | **OC/DC coordinator data** | 2026-07-19 | ⛔ **DEFERRED — no free source** (FootballScoop/ESPN, no API). HC-only shipped | not tested | P0.5 |
| T-20 | **`is_rivalry`** | 2026-07-21 | ⛔ **DROPPED, not guessed** — no confirmed CFBD field or maintained pair list | not tested | P1.3 |
| T-21 | **Travel / altitude** | 2026-07-21 | ✅ **SHIPPED into the matrix, reversing an earlier "drop it" banner** — `venue_latitude/longitude` ARE staged, so travel/altitude are buildable for the non-neutral majority (~86–88% coverage). ⭐ Carry the correction to NFL/NCAAB | corrected assumption | P1.3 §4 |
| T-22 | **P1.1's 2-pass opponent-adjusted rollup vs the P1.2 estimator** | 2026-07-20 | 🟡 **KEPT INDEPENDENT.** Two independent routes to opponent-adjusted strength; §5 lets them be *compared* rather than making one depend on the other. **Fusing them was explicitly left as a P1.3/P1.4 question and is still OPEN** | open, untried | P1.2 §7 |

### 10e. Uncertainty / calibration mechanisms

| # | candidate | result | null state |
|---|---|---|---|
| T-23 | **Consuming `strength_margin_sd` directly as a predictive sd** | ❌ **REFUTED BY MEASUREMENT** — standardized-residual sd 1.469, 80% coverage 0.629 vs 0.80. Cause identified (recency-weighted σ ⇒ the fitted σ is a maximally-weighted observation's, shortfall ≈ E[1/w]) | measured failure |
| T-24 | **The E13.6 held-out recalibration `k`** | ✅ **SHIPPED** — `k_margin 0.573 / k_total 0.499`, positive ⇒ genuine propagation | won |
| T-25 | **The oracle-floor metric-hygiene check** | ✅ ran; ⭐ found the **opposite** of MLB — wide-support integers ⇒ an oracle covers ≈ 0.80 exactly, **no inflation to exploit**, so a strict floor would reject a perfect oracle ⇒ a **deflationary** ±0.02 sampling tolerance was added | hygiene finding |
| T-26 | **`--strength-sd-scale = 1.3` for the futures board** | ❌ **NOT SHIPPED** — marginally improves conference-title reliability but the natty prefers 1.0 ⇒ **1.0 ships** (draw straight from the posterior) | tested and declined |
| T-27 | **A bottom-up game-level Monte-Carlo for futures** | ✅ **the RIGHT tool here** — explicitly contrasted with MLB's **E13.2 null**; season-long MC is where full-season simulation earns out | cross-sport reuse |

### 10f. Market / edge

| # | candidate | when | result | null state | source |
|---|---|---|---|---|---|
| T-28 | ⭐ **ATS vs the closing line, 2020–2025** | 2026-07-23 | ❌ **0.4961** (n=4,110) vs **placebo 0.4968** and breakeven 0.5238 — indistinguishable from a placebo | **clean measured null** ⇒ `best_alpha=0` | `ncaaf_p1_4_calibration.json` |
| T-29 | **O/U vs the closing line, 2020–2025** | 2026-07-23 | ❌ **0.5229** (n=4,129) — below the 0.5238 breakeven | clean measured null | same |
| T-30 | **Forward (in-season) CLV** | — | ⏸️ **STRUCTURALLY IMPOSSIBLE pre-season** — the offline vs-close eval was the ship bar; forward CLV is the P0.6b/P0.6c-fed in-season confirmation | **DATA_GATED / not-yet-runnable** | P1.4 |
| T-31 | **Futures de-vig vs market** | — | ⏸️ **scaffold only** (`--futures-csv`) — historical futures odds were never captured (P0.6 = game lines only); the verdict needs a multi-season backtest | DATA_GATED | P1.5 |
| T-32 | **Grouping odds coverage BY CFBD `week`** | 2026-07-25 | ❌ **BROKEN — postseason bowls are numbered week 1,2,3… and COLLIDE with regular-season weeks** once `season_type="both"`; it flagged an already-85%-covered season as needing re-capture. **Fix = KICKOFF-GRAIN diffing** (`commence_time`, never CFBD week) | mechanism bug, cured | P0.6b |

### 10g. Leakage / correctness findings (bugs the build caught — all SILENT, none CI-catchable)

| # | finding | result |
|---|---|---|
| T-33 | ⭐ **CFBD restarts `week` at 1 for the POSTSEASON** ⇒ raw `week` sorted January's title game before September's week 2. 2024 Ohio State had FIVE games at `week ≤ 1` and every as-of row from wk2 on absorbed them | 🚨 **A LIVE LEAK, caught and cured** — `season_order_week` is the only column that may order a season; 3 singular leakage gates, **one deliberately DATE-based because a week-based test re-uses the broken ordering and passes green**; plus a source guard forbidding a raw-`week` sort in the bake-off |
| T-34 | ML variance components **genuinely COLLAPSE to zero** on a thin fit — the likelihood peaks at `tau_team = 0`, silently deleting the team level of a *team*-strength model | cured with a boundary-avoiding Gamma(2,·) prior on each tau + multi-start; pinned by a regression test |
| T-35 | 🚨 **`strength_offense − strength_defense` is a trap** — both are signed higher-is-better (defense = points PREVENTED) ⇒ net strength is their **SUM**; subtracting returns ~0 for every team | documented in the mart SQL, the memos, and the sim's sign convention |
| T-36 | A **"flat" prior that was secretly a 1,000-point prior AND leaked** → one barely-supported covariate reported ±913 pts of uncertainty (2021 New Mexico State) | cured by scaling priors to the data + a plausibility gate; accuracy unchanged |
| T-37 | A **recency-weighting bug** that quietly ran a "4-season" fit on the last few weeks — it surfaced **only as MIScalibration** (intervals covering half their claim), never as an error | fixed; improved calibration **and** accuracy |
| T-38 | The recruit↔college bridge was documented as `athleteId ↔ recruitIds` — **7 matches in 12 seasons, effectively dead** | 🔧 corrected to `roster.recruit_ids ↔ recruiting.id` ⇒ **18,306 recruit↔production pairs**. ⭐ the "dead-bridge" lesson that made **row-count verification of every cross-source join** standard here (P1.4's CLV join was row-count-verified on the real lake for exactly this reason) |
| T-39 | **A season default pinned to 2020–2024** was stale-by-a-season the day it merged | cured by a clock-derived `last_completed_season()` / `current_season()`; never pin a season |
| T-40 | **P0.7's "P1.2 re-run = no code change" premise was WRONG** — P1.2 built its universe from results-only `fact_ncaaf_team_game` (0 rows for 2026) so it could not emit | fixed backward-compatibly via `run_strength(schedule_teams=…)`; 2015–2025 output **byte-identical**, guarded |
| T-41 | ⭐ **Model-quality gates here are BEHAVIOURAL, not green-checkmark** — 3 of the 4 P1.2 bugs were SILENT and **CI could not have caught any** (it mocks all IO). The leakage gate was **verified to actually FAIL on a tampered row**, so its green means something | the standing standard for this vertical |
| T-46 | **`home_team_id`/`away_team_id` (BIGINT) were feature-eligible in the `full` contract** — `_ID_COLS` excludes the string team/conference NAMES but not the numeric ids, despite the code comment claiming team identity is excluded (found by this audit's column enumeration, 2026-08-04) | ⚠️ open hygiene item, zero shipped impact — the `full` contract lost deflation and `strength_only` selects by `_STRENGTH_PREFIXES`; add both ids to `_ID_COLS` before any P2 re-run of the full matrix |

### 10h. The NFL feeder (P1A — in the tree, consumed by NFL)

| # | candidate | when | result | null state | source |
|---|---|---|---|---|---|
| T-42 | **College body of work → NFL rookie outcome** (`stratified_ols` winner, 7 configs) | 2026-07-29 | 🟡 **REAL AND ROBUST BUT WEAK** — beats the position-mean null OOS (0.7901 < 0.8107), **PBO 0.000 / DSR 0.994** | robust small effect | `ncaaf_p1a_college_nfl_translation.md` |
| T-43 | ⭐ **vs the DRAFT-SLOT benchmark** | 2026-07-29 | ❌ **LOSES DECISIVELY — slot-only MAE 0.6417 vs 0.7901.** ⇒ **do NOT use P1A as a standalone rookie board**; its value is the **RESIDUAL** where college production disagrees with draft position | **the decision-relevant finding** | same |
| T-44 | **Combine + recruiting pedigree as features** | 2026-07-29 | ❌ **NO SIGNAL at this sample size** — every GBM config (the only candidates that use them) scores **at or below the null** (−0.0046 / −0.0071 skill) | genuine absence at n≈2,149 | same |
| T-45 | **Signal by position** | 2026-07-29 | concentrated at skill positions — RB 0.369 / TE 0.354 / QB 0.320 / WR 0.194; **DL ≈ 0.001** (college defensive box stats translate poorly — expected) | measured | same |

### 10i. Cross-sport leverage established here (do not rebuild)

- **`hierarchical.py`** — the partial-pooling solver — is **reusable UNCHANGED by NFL and NCAAB** (same shape:
  many entities, few games, sparse schedule) and was **promoted out of the football tree into
  `betting_ml/utils/`**, where MLB's MiLB MLEs now cite it. It was also **reused unchanged** as one of P1.2b's
  bake-off candidates.
- **`season_simulation.py` is SPORT-AGNOSTIC** ⇒ NFL N1.1 (Super Bowl / division / conference futures) is the
  same engine on the NFL game model.
- The **draft-slot spine** `(season, overall pick)` — 99.7% resolution to `gsis_id` — replaced an ID join that
  does not exist (CFBD and nflverse share **no player ID**).

---

## Reconciliation summary (for the umbrella index)

| field | verdict |
|---|---|
| **Docs-vs-served mismatch?** | **N/A — NOT SERVING.** No serving store, no API, no frontend, no `daily_model_predictions` row, **no `sub_model_registry.yaml` entry** (verified: 2 hits, both prose inside `milb_mle_v1`). Nothing to disagree with. **This is the honest state, not a defect.** |
| **Would it serve at season start untouched?** | **Partly — and the distinction is the point.** The ingest/mart/model pipeline would keep producing calibrated output into the S3 *research* lakehouse (odds capture is already RUNNING live); **no user-facing surface exists or would appear.** Model FROZEN ≠ product EXISTS. |
| **Version authority** | **FIVE authorities, none of them the registry** — 4 committed artifact JSONs (`ncaaf_game_distribution_v1` · `ncaaf_team_strength_v1` · `ncaaf_freshman_projection_v1` · `ncaaf_college_nfl_translation_v1`) + the `ablation_results/ncaaf_*` memos. ⭐ **P1.5's futures board has NO version string at all.** |
| **Ratified-but-held?** | None. Nothing awaits publication — the gap is a *product*, not a *decision*. |
| **`best_alpha = 0`** | ✅ Confirmed and **measured**: ATS 0.4961 ≈ placebo 0.4968, O/U 0.5229, both < the 0.5238 breakeven. Market-blindness is enforced mechanically (`assert_market_blind` on every contract before any fit). |
| **Headline findings** | (1) ⭐ **The full 180-column matrix FAILED deflation (PBO 0.648 / DSR 0.0075) ⇒ strength-prior-only is PROVEN** — a feature-expansion recommendation is a re-run of a dead end. (2) ⭐ **The SHIPPED form is `strength_posterior`, not the decided reference's `gaussian`** — swapped at finalize on a pre-registered early-season floor, and it scores *worse* on the aggregate metric (0.0269 vs 0.0242). (3) ⭐ **μ refreshes but σ does not** — P1.4's calibration is frozen at 2026-07-23 with no cadence, drift monitor, or refit trigger, while P1.2 strength re-fits; a calibration-drift monitor is a prerequisite before any P3 surface publishes these numbers. (4) **P0.6c is LIVE in prod** (odds capture RUNNING since 2026-08-01) — the roadmap text saying otherwise is stale. (5) The total PIT is **mildly non-flat (0.0218)** — the clearest model-level target (P2.5). |
| **Corrections to the brief** | 7, tabulated at the top: "6 P2 stories" → **10 in 3 tracks**; matrix width disambiguated — **180 model-eligible / 174 prefixed / 200 total** (and the 2 numeric team ids were eligible by accident); winner accuracy 71.7% → **72.3%**; P0.6b/P0.6c status stale; the shipped form is not the reference form; `ncaaf_pm_pushback_response.md` is **not in this repo**; **no BH-FDR was computed** for P1.4. |
