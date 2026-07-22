# NCAAF-P1.4 — the game-model bake-off (H2H · spread · total), design + handoff

**Status (2026-07-22):** CODE-COMPLETE + smoke-verified end-to-end (assemble → bakeoff → decide →
finalize) on the real cached matrix. The heavy §0.5 search (all folds × 5 learners × 4 contracts ×
4 forms + Optuna, then the vs-close CLV leg) is **operator-run** (>1-min jobs) — see the run plan
at the bottom. This doc is the design record; the operator's `--stage decide` writes the deflated
leaderboard to `ncaaf_p1_4_game_bakeoff.md`, and `--stage finalize` writes `ncaaf_p1_4_calibration.md`.

## Design — model the JOINT distribution ONCE, derive all 3 markets

Mirrors MLB E2 (per-side → convolve → read off every market). The joint object is the pair
**(margin, total)** where `margin = home − away`, `total = home + away`, because the three markets
are pure reads off it:

| market | read |
|---|---|
| H2H (moneyline) | `P(margin > 0)` |
| spread | `P(margin > line)` (line = −closing home spread) |
| total (O/U) | `P(total > line)` |

The single-market probabilities are MARGINAL (ρ doesn't change them); ρ is carried so a same-game
parlay is coherent and the sides↔totals correlation is honest. This is more coherent than three
unlinked target models, and it is where the P1.2 `strength_margin_sd` gets **recalibrated** from
"1.5× too-tight parameter uncertainty" into a held-out predictive σ (the E13.6 pattern).

## The pre-registered search (every axis counts toward PBO<0.2 / DSR / FDR deflation)

- **Learners** (predict μ_margin, μ_total): `ridge` · `lgbm` · `xgb` · `catboost` ·
  `ngboost_normal` (native per-game σ).
- **Forms** (`ncaaf_game_distribution.FORMS`, the §0.5 ≥3-form axis): `gaussian` (bivariate
  Normal — textbook football + the σ recalibration) · `student_t` (heavy tails for CFB blowouts /
  back-door covers; dof MLE'd on held-out residuals) · `native` (NGBoost per-game σ,
  heteroscedastic) · `count` (home/away NegBin point counts convolved — the MLB-style discrete foil).
- **Contracts** (in-fold): `full` · `strength_only` · `clustered` (|ρ|≥0.95 prune) · `top_k`.
- **Reference/foil = `ridge__strength_only__gaussian`** — the P1.2 strength margin/total prior with
  a held-out-calibrated Gaussian spread. **The bake-off question is exactly "does the full
  180-feature matrix, under a real learner+form, robustly BEAT the strength prior?"** (the PM
  confirm-pass bar). A candidate that doesn't beat strength-only isn't earning its complexity.

## Selection metric + the NCAAF selection-metric-hygiene finding

`downstream_score = PIT_max_decile_dev(margin) + PIT_max_decile_dev(total)` (lower = better),
PIT-only exactly as the MLB E2.1-r metric CORRECTION requires. `calib_80 ≥ 0.80` is a **FLOOR, never
a target**, and every selection metric is sanity-checked against an **oracle floor** (guard
`test_oracle_is_the_scoring_floor`).

⭐ **NCAAF-specific hygiene result:** the MLB landmine — inclusive-integer interval coverage inflates
a correct DISCRETE/low-mean predictive's calib_80 to ~0.82–0.86 — is a LOW-MEAN effect. NCAAF
margin/total are **wide-support** integers (σ ≈ 13 / 17, so ±0.5 rounding is negligible against a
±17-point interval), so a correctly-specified **oracle here covers ≈ 0.80 exactly — there is NO
inflation to exploit**. The oracle guard verified this (the oracle lands at 0.79–0.80, not 0.82+).
Consequently a strict `≥ 0.80` floor would reject a perfect oracle on Monte-Carlo/finite-n noise, so
the floor carries a small sampling tolerance (`_CALIB_FLOOR_TOL = 0.02`) — the wobble runs
DEFLATIONARY here, the opposite of discrete F5. The metric stays PIT-only; an under-dispersed model
(σ halved) sits far below even the tolerant floor and is still disqualified.

## Posterior-predictive propagation (the PM small-sample nudge, 2026-07-22) — a 5th form + a small-N gate

At ~12–15 games/team the honest concern is that the predictive be appropriately WIDE. A
point-estimate + HOMOSCEDASTIC σ (my initial gaussian) is honestly wide *on average* (PIT-flat) but
gives a week-2 team and a week-14 team the same width — understating early-season uncertainty (the
"strength_margin_sd is ~1.5× too tight" trap). Added the **`strength_posterior`** form: a
heteroscedastic Gaussian whose per-game σ PROPAGATES the P1.2 strength posterior,
`σ_g² = σ₀² + k²·(home_sd² + away_sd²)`, with **(σ₀, k) MLE'd on held-out residuals** — k is exactly
the E13.6 recalibration factor the raw sd needs. Per §0.5 it is a CANDIDATE that must beat the
homoscedastic form on the metric, not an assumed win (distinct from the `native` foil's *learned* σ,
which the bake-off found under-covers at 0.72).

**Finding (this is the important one — the aggregate metric HID it):** the strength posterior is
**3.4× wider in weeks 1–3 than week 8+** (corr with games-played −0.65). On the *aggregate* PIT the
two forms tie (posterior 0.0269 vs homoscedastic 0.0242 — within the tied field). But sliced by
season week:

| week bucket | n | margin calib_80 (homosced → posterior) | total calib_80 |
|---|---|---|---|
| **wk 1–2** (thin sample) | 684 | **0.785 → 0.804** | 0.791 → 0.814 |
| wk 3–4 | 783 | 0.794 → 0.799 | 0.807 → 0.814 |
| wk 5+ | 4557 | 0.804 → 0.800 | 0.794 → 0.794 |

**The homoscedastic form under-covers weeks 1–2 (margin 0.785, below the strict 0.80 floor); the
posterior-predictive fixes it (0.804/0.814) and is identical late-season.** k fit ≈ 0.5–0.57
(positive — real propagation, not collapsed). The 4,557 late-season games swamped the 684 early ones
in the aggregate, which is exactly why a small-N slice is now a first-class gate. `stage_finalize`
re-checks calib_80 on `season_order_week ≤ 2` (`_EARLY_SEASON_WEEKS`) as a FLOOR.

⇒ **Honest recommendation:** the two forms are tied on aggregate calibration, so the
posterior-predictive is the honest ship — it holds the early-season floor the homoscedastic form
misses at no aggregate cost, and early-season is exactly where the NCAAF book is softest. Finalize
the reference with `--form strength_posterior`.

## Early-season / cold-start validation (PM follow-up AC, 2026-07-22)

Week 1–3 is a DIFFERENT feature regime (priors-heavy; in-season efficiency NULL) whose quality a
season-averaged calibration HIDES. `stage_finalize` now validates it SEPARATELY (a first-class
floor + PIT), and the **season-forward CV is the E13.7 cold-start analog by construction** — a
week-1 eval game is in a wholly held-out season, so it is predicted from PRIOR-SEASON + PRE-SEASON
data ONLY. Confirmed on the real build (ridge strength_only strength_posterior):

- **Week 1–3 (n=1051):** calib_80 margin 0.792 / total 0.822, margin PIT-flat, early floor **PASS**.
- **Week-1 interval is honestly WIDER:** 80% margin width 43.1 (wk1) vs 40.8 (late), ×1.06 — a
  thin-sample matchup gets a wider interval, which is the CORRECT answer, not a weakness.
- **No current-season peeking:** 100% of week-1 eval games carry NULL in-season efficiency features
  (`home_off_ppa`) — the strength model is on its pre-season prior alone (the P1.2 "sd ~6.7 in wk1"
  regime). The cold-start property is verified, not assumed.

## Downstream season-simulation interface (P1.5 futures — the output is NOT collapsed)

`models/ncaaf_game_predictor.py` exposes the joint predictive as a callable so a later **P1.5
season Monte-Carlo (National-Championship / conference-title futures)** is a thin layer on top, not
a re-derivation. ⭐ The load-bearing contract is the **strength-variance decomposition** the
posterior-predictive form gives for free:

```
σ_g²  =  σ₀²                        (irreducible game noise)
      +  k²·(home_sd² + away_sd²)   (team-strength posterior uncertainty)
```

A season sim draws each team's TRUE strength ONCE per simulated season (from the P1.2
`ncaaf_team_strength_week` posterior: `strength_margin` ± `strength_margin_sd`) and reuses it across
that team's whole schedule — that correlation across a team's 12 games is what makes a futures
number honest. So the sim calls `sample_matchup(..., fixed_strength=True)` → **σ₀ ONLY** per game
(the strength uncertainty is already in the drawn μ); using the full width would DOUBLE-COUNT it.
The served params carry σ₀ and k separately for exactly this. Interface:
`load_params` → `sample_matchup(params, μ_margin, μ_total, strength_var, rng, fixed_strength=…)` →
`market_probabilities(markets, home_spread, total_line)`. P1.4 does NOT build the sim — it just
makes the model callable that way. Guard: `test_predictor_fixed_strength_narrows_to_game_noise_only`.

## CV — season-forward, date-purged (the P1.1 carry-over)

Season-forward PURGED walk-forward (`PurgedWalkForwardSplit`, `year_col=game_year`,
`date_col=game_date`, `min_train_seasons=3`): train on all prior seasons, eval one held-out season
(2018→2025, 8 folds). The purge band + fold ordering are by **calendar date** — monotone with
`season_order_week` and **immune to the postseason `week`=1 collision** — so January playoff games can
never leak into September. The eval season is wholly out of sample. A source guard
(`test_bakeoff_cv_axis_is_season_order_not_raw_week`) mechanically forbids sorting by raw `week`.

## The vs-market / CLV staging join (P1.4 OWNS it)

A cross-source join, row-count-verified on the real lake (the P1.2b dead-bridge lesson):

```
odds_ncaaf_historical (Odds-API team names, commence_time)
   ⋈  games   (season + CFBD team-name PREFIX match)   →   CFBD game id
   →  the CFBD id IS the matrix game_id (int)     (confirmed: games.raw_json.id == matrix.game_id)
```

Only snapshots with `_snapshot_ts < commence_time` are eligible (leakage-safe close); per game the
LATEST such snapshot, cross-book MEDIAN home spread / over total / home ML. Expect **2020–2025**
coverage (odds floor) and the **2 known P0.6 no-close FBS orphans** to drop — not a bug. The closes
live ONLY in the finalize CLV eval, NEVER as training features (`assert_market_blind` on every
contract).

🕒 **Forward-CLV cannot exist pre-season** (NCAAF opens ~Aug 2026). The SHIP bar for P1.4 is the
OFFLINE deflated vs-close eval (2020–2025 historical ATS/OU hit-rate vs breakeven + a placebo, under
PBO/DSR) + calibration (PIT/reliability). Forward-CLV is the in-season confirmation (P0.6b-fed).
`best_alpha = 0` until the gate clears AND a positive vs-close window.

## Smoke verification (2026-07-22 — NOT the final result)

A capped 2-fold, default-param smoke (all four stages ran clean on the 8,325-game / 180-feature
cache):

| config | score | calib_80 (m/t) | H2H Brier |
|---|---|---|---|
| `ridge__strength_only__gaussian` (reference) | 0.0337 | 0.797 / 0.814 | 0.170 |
| `lgbm__full__gaussian` | 0.0388 | 0.797 / 0.813 | 0.175 |

`decide` → **REFERENCE_STANDS** (PBO 0.914 over a 2-config tied field = the null reading, correctly
framed). `finalize` (reference) → margin/total both **PIT-flat**, calib floor PASS, H2H Brier 0.170 —
a genuinely shippable calibrated joint distribution. **This is a 2-fold smoke, not the verdict** —
the operator's full search + Optuna decides whether the full matrix earns its complexity. A
trustworthy null (the strength prior carries) is a valid, expected P1.4 deliverable.

## Files

- `models/ncaaf_game_distribution.py` — the pure joint-distribution core (forms, samplers, held-out
  σ/ρ/dof/r calibration, `derive_markets`, oracle helper). Imports only `totals_distribution`.
- `models/bakeoff_ncaaf_game.py` — the harness (assemble + CLV join, folds, learners, contracts,
  forms incl. `strength_posterior`, Optuna, decide, finalize + cold-start validation + CLV eval).
- `models/ncaaf_game_predictor.py` — the serving + P1.5-facing callable (`sample_matchup`,
  `market_probabilities`, the `fixed_strength` season-sim mode; the strength-decomposition contract).
- `betting_ml/tests/test_ncaaf_game_distribution.py` — 11 fast-gate guards (oracle floor per form,
  derive-markets coherence, dispersion recovery, PIT-flatness, CV-axis source guard).
- artifacts (gitignored / S3): `betting_ml/data/cache/ncaaf_p1_4_game_matrix.parquet` (the one-pull
  cache), `models/artifacts/ncaaf_game_distribution_v1.json` (served params, written by finalize).

## Operator run plan (LAPTOP — off the MLB serving lane, SF-free)

```bash
# 0) one pull → cache (matrix + CLV close join). Needs AWS read creds + region.
AWS_DEFAULT_REGION=us-east-2 uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --assemble

# 1) the bake-off (all folds, 5 learners × 4 contracts × their default form + lgbm student_t/count)
uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage bakeoff

# 2) Optuna — ONE learner per invocation (retrain-per-target convention)
uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage optuna --model-class lgbm --n-trials 40
#   …repeat for xgb, catboost, ngboost_normal, ridge

# 3) deflated verdict (PBO/DSR over every config)
uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage decide

# 4) finalize the winner (or the reference if it stands) → served distribution + PIT gate + CLV eval
uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage finalize \
    --model-class <winner learner> --contract <winner contract> --form <winner form>
```
