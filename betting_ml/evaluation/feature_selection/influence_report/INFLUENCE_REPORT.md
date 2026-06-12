# Epic 30 — Feature-Influence Report (what's driving the models, and where to improve)

**Date:** 2026-06-11. **Purpose:** the "see what's influencing them so we can improve them"
deliverable. Two parts: (A) an **immediate synthesis** from existing importance artifacts,
and (B) a **reusable harness** (`betting_ml/scripts/influence_report.py`) to refresh this on
the freshly-scrubbed champions once `run_diff` finishes retraining.

> **Provenance caveat (read first):** Part A uses the importance artifacts on hand
> (`feature_importance_v1.parquet` — XGB home_win SHAP; `feature_selection/*_feature_importance.txt`
> — NGBoost permutation). These were computed on **market-INCLUSIVE** and slightly **stale**
> models (May 2026), whereas the deployed champions are **market-blind** (home_win) and
> post-scrub. So the market features that dominate below are **removed in production** — treat
> their dominance as a signal about circularity, not as the champion's actual top driver. Part B
> regenerates the canonical picture on the real local champions. Directions/magnitudes are
> representative; exact ranks will shift.

---

## Headline findings (all three targets)

**1. The signal is extremely DIFFUSE — there is no silver-bullet feature.**
For home_win, the top-10 features carry only **9%** of total |SHAP|; top-40 = 25%; top-80 = 41%.
The #1 driver is ~1% of the total. This is the fingerprint of a genuinely hard target (MLB game
outcomes have a low skill ceiling) and it explains why dropping any few features — including the
3 identifiers — barely moves CV. **Improvement will not come from one magic feature; it comes
from serving the existing diffuse signal correctly (→ 30.3) and from better-conditioned signal
families.**

**2. There is MASSIVE dead weight — the biggest, most actionable lever here.**

| Target | Features | "Dead-weight" (shuffling doesn't hurt) | Share |
|---|---|---|---|
| run_differential | 294 | **180** exclusion candidates | **61%** |
| total_runs | 311 | 68 exclusion candidates | 22% |
| home_win | 453 | 17 prune + 17 noise-risk | ~7% flagged |

run_diff carries **~180 features that don't measurably help** (mean permutation imp ≤ 0 or
CI-lower < −0.001). That's a huge simplification opportunity: pruning dead features (a) reduces
the serving-skew attack surface (fewer columns to arrive null/misaligned at `predict_today` —
directly relevant to the live-zero-skill problem), (b) reduces overfitting/variance, and (c)
makes the model far easier to debug. **This is a concrete "improve them" action independent of
new data.**

**3. Market signal — two findings (corrected 2026-06-11):**

(a) The dominance of `home_win_prob_consensus` / `total_line_consensus` in the mined artifacts is
an artifact of STALE, market-inclusive evals — those exact columns ARE in the trainers'
`_MARKET_COLS_TO_EXCLUDE`, so they are **not in the deployed contracts**. Disregard them for the
production picture.

(b) **But "market-blind" is INCOMPLETE.** Verified scan of the deployed contracts: all three share
an identical 33-col exclude set that strips moneyline / H2H-consensus / sharp / totals-line columns,
but **6 market-derived columns leak through** (never added to the exclude set):
`over_prob_consensus`, `under_implied_prob`, `total_line_movement`, `home_ml_money_pct`,
`over_ticket_pct`, `market_bookmaker_count`. So the base models are **"consensus-and-moneyline-blind,"
not market-blind** — they still consume totals-market consensus, line movement, and public-betting %.
This violates architecture Principle 3 / §5.6 / §5.7 (base models market-blind) and is a residual
circularity risk for any model-vs-market edge claim. Part B reveals whether these 6 are actually
influential; if so, completing the exclude set is a cleanup action (with an accuracy-vs-blindness
tradeoff — market features help raw accuracy but invalidate edge measurement).

---

## Per-target influence (from current artifacts — refresh via Part B)

### home_win (XGB SHAP, market-inclusive eval)
Signal concentrates in real baseball-mechanism families:
`rolling_batting` (13%), `bullpen` (10.5%), `team_pitching` (10%), `team_offense` (9%),
`platoon_splits` (6%), `starter stuff+/k%/whiff` (~9% combined), `park/weather/ump` (4%).
Top non-market drivers: `away_starter_stuff_plus`, `away_lineup_avg_xwoba_vs_cluster`,
`away_starter_changeup_stuff_plus`, `away_starter_avg_ip_season`, `away_win_pct`,
`home_avg_xwoba_vs_lhp`. → The model leans on starter quality (Stuff+), lineup xwoba-vs-cluster,
bullpen recency, and platoon splits. **Healthy mechanism signal; the problem is live serving, not
the feature set.**

### run_differential (NGBoost permutation, 2025)
Beyond the market #1: `pythagorean_win_exp_diff` (0.030 — strong), `home_pit_k_pct_std`,
`away_win_pct`, `home_starter_xwoba_against_std`, `home_pit_woba_against_30d`,
`away_pit_k_pct_30d`, starter Stuff+. **But 61% of features are dead weight** — the model's real
work is done by ~a dozen features (pythagorean form, pitching k%/woba, starter quality). Strong
candidate for an aggressive prune-and-retrain.

### total_runs (NGBoost permutation — stale `decay_weighted`, NOT the deployed eb champion)
Beyond the market #1/#2: **weather is a top driver** — `humidity_pct` (#3, 0.024), `temp_f`
(#8) — plus `home_starter_fastball_stuff_plus`, `series_game_number`, bullpen/starter whiff and
xwoba. → For totals, **run environment (weather) genuinely matters**; ensure weather is served
well live (it's forecast-based and dome-gated). Note: deployed totals = `eb_enriched` (different
artifact); Part B inspects the freshly-scrubbed local `tuned` totals model instead.

---

## Improvement levers (the payoff)

1. **Prune the dead weight (esp. run_diff's 61%).** Retrain on the strong+moderate tiers only;
   measure CV + 2026 OOS. Smaller contract = smaller serving-skew surface = more trustworthy live.
   This is the highest-leverage, lowest-risk "improve" action and pairs naturally with 30.3.
2. **Fix serving (30.3) — the dominant lever.** home_win is corr 0.42 offline vs 0.001 live; the
   diffuse signal means *every* feature must be served correctly or the thin edge evaporates. No
   feature change rescues a mis-served matrix.
3. **Add distributional signal (30.2).** The unused sub-model μ/dispersion/PI-width layer is the
   one untested *addition*; test it on the cleaned contract (next story).
4. **Weather for totals.** It's a genuine top driver — verify forecast freshness/dome-gating in
   the serve path before any totals unpause.
5. **Accept the diffuse ceiling.** No single-feature fix exists; gains come from serving
   correctness + pruning + (maybe) the Bayesian layer, not from hunting one magic feature.

---

## Part B — refresh on the freshly-scrubbed champions

`betting_ml/scripts/influence_report.py` loads each **local** champion (the post-scrub artifacts,
not the stale S3 ones), computes permutation importance on the honest **2026 OOS** surface,
aggregates by family, and classifies every feature strong/moderate/weak/**dead**/identifier.

```
uv run python betting_ml/scripts/influence_report.py --target all
```

Writes `…/influence_report/influence_all.json` + `influence_report.md`. Run it **after `run_diff`
finishes retraining** so all three local champions are the scrubbed versions. (>1-min run; hand
off.) Notes: home_win uses the fresh 374-feat XGB; run_diff the fresh `ngboost_tuned`; total_runs
inspects the local scrubbed `tuned` model — the deployed totals champion is `eb_enriched` (S3-only),
so its canonical influence needs that artifact pulled, but the tuned proxy is representative.
