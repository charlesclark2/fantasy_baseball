# NF-W7 pre-registration — Weekly Kicker + DST projections (V1 / Tier-0)

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything below lives as
constants in `kdst_weekly.py`; the runner `run_nf_w7_kdst_weekly.py` READS them (NF-D16). A smoke
run (2 folds, artifacts suffixed `_smoke`) may be used to prove the code path only — no verdict,
no constant may change in response to a smoke score after this file is committed.

⚖️ Edge-independent projection product — `best_alpha` N/A, **deploy-held** (serving = the weekly
path / NF-C6). Research-only: no changelog entry.

## 0. The thesis under test (not assumed)

Weekly K/DST value is largely **opportunity**: teams that score, or stall in the red zone /
inside the 30, generate FG attempts; DST output tracks opponent quality, script and pace. Unlike
the skill positions — where the champion had already absorbed opportunity and NF-W3/W4/W5 came
back null three times — no weekly K/DST model exists at all, so the *components → exact tier
scoring* chain is a genuinely different bet. It must beat an honest climatology null and a
direct-learned points foil OOS, or the null model stands and is recorded.

## 1. Contract confirmation (the card's binding constraint #3)

Checked against `weekly_frame.ALLOWED_FEATURE_CONTRACT` before design:

- `game_context` — CERTIFIED. Used: is_home, div_game, week_index, days_since_last_game,
  roofed_stadium. ⭐ `roofed_stadium` is derived as `roof ∈ {dome, closed, open}` — the STADIUM
  possessing a roof is a structural, schedule-release attribute; the realized open/closed state of
  a retractable roof on game day is NOT used (it is realized information).
- `team_environment` (nflverse pbp, lagged) — CERTIFIED; the spec's own description names "drive
  success" and "red-zone tendencies", exactly the kicker-opportunity block.
- `opponent_matchup` — CERTIFIED.
- `prior_week_box` (nflverse `stats_player_week`, lagged) — CERTIFIED as a family. ⚠️ FINDING,
  recorded not silently absorbed: the spec's prose enumerates the OFFENSIVE-SKILL columns
  ("carries/targets/receptions/…"); the kicking block (`fg_att`, `fg_made_*`, `pat_*`) lives in
  the SAME source with the SAME release timing and the SAME PIT class (postgame, retrospective).
  We read the family certification as covering the source, and flag the description wording as a
  contract-doc gap for the PM — not a violation and not a fillna.
- ⛔ WEATHER (temp/wind) — genuinely predictive for kicking and **BANNED** as a historical
  feature (NF-W0 deferred contract; it may enter only via the NF-W0a forward capture once it
  accrues). Enforced mechanically: the banned-source token scan runs on every aggregation SQL
  (comments stripped) and on every feature name. Markets / depth-chart rank / game-day inactive
  status: banned identically.
- ⛔ No `pbp_participation` legs at all ⇒ the NF-W0c 2023 provider-era boundary is honored by
  EXCLUSION (`ERA_FORBIDDEN_TOKENS` reused verbatim). The two-era read (capture-era 2025 folds vs
  legacy folds) is REPORT-ONLY, per NF-W2d.

## 2. Frames, universes, labels

All lake reads via `query_lake` (DuckDB over the S3 NFL lake), 2016–2025 REG. Each frame is
assembled once → parquet cache keyed on a SHA of story+features+schema (NF-C0e); the PIT gate
re-runs on every load, cache hit or not. `assert_point_in_time` is INVOKED per (season, week)
fail-closed on every frame. ⛔ No `fillna(0)` anywhere: a missing lagged window is NaN
("unmeasured"); learners that cannot pass NaN use TRAIN-fitted median imputation as a device
inside the arm.

- **DST frame** — one row per (season, week, team), 32-team universe, complete by construction.
  Labels: `def_sacks`, `def_int` (def_interceptions), `def_fumble_rec` (fumble_recovery_opp),
  `dst_td` (def_tds + special_teams_tds — both worth 6 in every scheme we score),
  `def_safety`, `def_blocked_kick` (fg+pat+punt blocks), `pa` (opponent score, from schedules),
  `ya` (NET yards allowed = opponent pass+rush+sack_yards_lost — the NF-C0e gross-vs-net lesson,
  reused from `kdst_source`), and the assembled `dst_points` (see §5).
- **Kicker frame** — one row per (season, week, rostered kicker): `weekly_rosters` position=K,
  **status='ACT'** (a frame-definition filter — game-day status is never a FEATURE), LEFT-joined
  to the `stats_player_week` kicking block. A rostered kicker with no stats row realized 0
  attempts — a legal outcome, retained (roster-first, zeros kept; the climatology foil must price
  that atom). Labels: `fg_att`, `xp_att` (pat_att), and `k_points` (see §5).
- **Attempt frame** — one row per pbp FG attempt (kick_distance is 100% non-null on 10,277
  attempts 2016–2025): labels `made` (field_goal_result='made') and `band`
  (0–39 / 40–49 / 50+ from exact distance). Exact kick distance is RETAINED; the league bands are
  applied at scoring time only (§4A.1's requirement).
- XP make: league-rate constant fit on train (≈0.944 measured). ⚠️ DECLARED THIN SCOPE: the
  design gives XP "a separate candidate set"; we pre-register the league-rate constant as the
  assembly input and do NOT bake off kicker-level XP skill (NF1.6 measured kicker make-rate
  ρ=0.085 season-to-season; the E[points] surface of XP-skill variation is ~0.05 pts/wk). This is
  the scope-note trade, stated.

Team codes canonicalized via the measured `TEAM_CODE_CANON` map before any join
(the NF-W3 franchise-code defect); code-set alignment asserted per season.

## 3. Folds, metric, grids, tails

- **Folds**: the NF-W1 axis VERBATIM — 8 expanding half-season blocks 2022H1…2025H2, purge 2
  global weeks (`WP.TEST_BLOCKS`, `WP.build_folds`). Identical axis on every frame (asserted).
- **Selection metric**: `crps_q199` — CRPS via the 2×mean-pinball identity over the DENSE
  199-level grid `MC.EVAL_LEVELS` (the NF-MARGIN1 requirement inherited from day one; the native
  39-level grid is structurally blind to the tails). ⛔ MAE is reported and never selects (the
  targets are zero-heavy — NF-D11/D14).
- **Tails**: parametric count arms emit exact integer-support quantile banks (ppf over the full
  support ⇒ real tails by construction). 9-knot quantile learners are interpolated to 199 levels
  and extended with the exponential mean-excess tail model (`MC.fit_tail_betas` on TRAIN
  exceedances + the MARGIN apply-map) — ⛔ never flat-extended. Assembly banks come from S=4000
  Monte-Carlo draws → empirical 199-level quantiles.
- Categorical legs use their own proper scores (never CRPS-on-a-category): binary log-loss for
  `fg_make`; multiclass log-loss for `fg_band`; **RPS** (ranked probability score — proper for
  ordered categories) for `pa_bucket` / `ya_bucket`.
- Randomized-PIT flatness (max-decile deviation) is REPORTED for every count-leg winner
  (E2.1-r); coverage(80) is a FLOOR (0.80), blocking only beyond 3 binomial SE (NF1.8), on the
  Layer-B assembled banks.

## 4. Layer A — the 12 component legs (arms, foils, anchors — fixed now)

Count legs score `crps_q199`; shared anchors per leg: `nihilist_zero` (the all-zero degenerate —
SCORED every run, must lose; NF-D14), `zero_width`, `max_width` (both sharpness degenerates must
lose; NF1.8), `permuted_within_week` (must lose; its lift over the best foil must be
non-significant, FAILING CLOSED on a None p — NF1.7 (a)), one PEEKING ORACLE PER ARM of that
arm's OWN form (NF-D16 (g‴)) floored AT MATCHED n (NF1.9 (f)), and `matched_n_<arm>` capacity
controls. Foils carry their own-form oracles.

| leg | grain | arms (the declared family) | foils |
|---|---|---|---|
| K1 `fg_att` | kicker-week | `pois_glm`, `negbin_glm`, `lgbm_quantile` | `foil_climatology`, `foil_entity_eb` |
| K2 `xp_att` | kicker-week | same three | same two |
| K3 `fg_make` | attempt | `eb_kicker_curve`, `logit_distance_glm`, `lgbm_classifier` | `foil_league_curve`, `foil_constant_rate` |
| K4 `fg_band` | attempt | `mnlogit`, `eb_dirichlet_kicker`, `lgbm_multiclass` | `foil_league_mix` |
| D1 `def_sacks` | team-week | `pois_glm`, `negbin_glm`, `lgbm_quantile` | `foil_climatology`, `foil_entity_eb` |
| D2 `def_int` | team-week | same three | same two |
| D3 `def_fumble_rec` | team-week | same three | same two |
| D4 `dst_td` | team-week | `eb_pois`, `hurdle_pois` (thin rare family — scope note) | `foil_climatology`, `foil_league_rate` |
| D5 `def_safety` | team-week | same two | same two |
| D6 `def_blocked_kick` | team-week | same two | same two |
| D7 `pa_bucket` | team-week (9 ordered buckets, NF1.6 `PA_BUCKET_EDGES`) | `ordered_logit`, `mnlogit`, `negbin_integrated` | `foil_climatology` (train marginal bucket freqs), `foil_entity_eb` (EB-conditioned mix) |
| D8 `ya_bucket` | team-week (9 ordered buckets, NF1.6 `YA_BUCKET_EDGES`) | `ordered_logit`, `mnlogit`, `gauss_integrated` | same two |

Notes fixed in advance: (a) the rare legs D4–D6 field TWO arms by deliberate thin-scope
registration (empirical-Bayes + a ZIP-style hurdle; NF1.6 measured season-to-season ρ ≈ −0.02…0.17
for these, so the honest prior is that the league-rate foil stands — a null there is expected and
publishable); `flag_unsafe_field_shrink` applies with the declared family size. (b) `pa_bucket` /
`ya_bucket` are the exact-tier discipline: bucket PROBABILITIES are modeled directly; ⛔ no point
estimate is ever passed through a tier table. (c) Layer-A selection per leg = argmin mean score
among the REAL ARMS; the gates (below) decide SHIP vs a classified null for the record. The
assembly consumes each leg's CRPS/score-best REAL ARM regardless of its gate state (the W3
pattern: Layer B tests the chain at its best; Layer B's own gate is what decides the story).

Gates per leg: beats best foil ∧ `cv_power.fold_consistency_clause(8)` (6/8) ∧ PBO < 0.20 over
the eligible field (arms + foils; anchors never — MH2.1 (a)) ∧ DSR ≥ 0.95 over the declared real
family (trial SRs from real arms only; the degenerates are anchors and never enter V — stated as
factual provenance, and the contender-set dispersion is REPORTED beside the whole-field figure
per the MH2.5 field-composition tax) ∧ BH-FDR q=0.10 (see §6) ∧ degenerates lose ∧ permutation
behaves ∧ per-form oracle floors at matched n ∧ (Layer B only) coverage floor.

## 5. Layer B — the story gate (one per target)

Assembled weekly fantasy-points distribution per target, scored `crps_q199`:

- **`k_points`** (modal-default kicker scoring, NF1.6 `K_CONVENIENCE_SCORING`: 3/4/5 by band +
  1/PAT, miss 0 — same convention as the shipped board, so the comparison is same-scale):
  `assembled_k` = MC composition: FG attempts ~ K1-winner bank; each attempt's band ~ K4-winner
  probabilities; make ~ K3-winner P(make | band-representative distance, kicker); XP attempts ~
  K2-winner bank; XP make ~ league rate. Component draws independent (declared V1
  simplification; the coverage floor on the assembled bank is the check that would expose it).
- **`dst_points`** (ESPN modal default, NF1.6 `DST_CONVENIENCE_SCORING` + `DST_PA_TIER_POINTS`:
  sacks 1, INT 2, FR 2, TD 6, safety 2, block 2, PA tier table on the 9-bucket refinement):
  `assembled_dst` = MC composition of D1–D6 winner banks + a PA-bucket draw from the D7-winner
  probabilities → exact tier points. YA buckets (D8) are modeled, scored and emitted but NOT in
  the headline points (not in the modal default — the NF1.6 convention, kept for board
  comparability; any league that scores YA tiers rescored from the emitted probabilities).
- Foils (the eligible field is {real arm + 3 foils} — PBO evaluable at 4 configs):
  - `foil_climatology` — the honest K+DST climatology null: train marginal weekly-points
    quantiles at 199 levels (prices the zero atom by construction). **The card's binding foil.**
  - `foil_board_eb` — entity-EB points rate (prior-season + season-to-date, shrunk to league)
    + train residual bank + exponential tails: the NF1/MVP-1-board-equivalent weekly read.
    ⚠️ COMPARABILITY CAVEAT, declared: the shipped NF1.6 board is SEASON-grain and consumes
    week-1 Vegas implied points (a deferred feature this story may not touch); the in-fold
    weekly EB reconstruction without markets is the comparable form. Recorded as such — "beats
    the board where comparable" (the card's wording), not "beats the shipped artifact".
  - `foil_direct` — the direct-learned points foil: 9-knot LGBM quantile on weekly points with
    the full feature set, interpolated to 199 + exponential tails.
- Anchors: `nihilist_zero`, `zero_width`, `max_width`, `permuted_direct` (direct form, labels
  permuted within week), own-form peeking oracles for the real arm (components refit on the test
  block) and each foil, `matched_n` capacity controls. Coverage(80) floor applies to the real
  arm.
- DSR at Layer B: ONE pre-registered real arm ⇒ sr0=0 (nothing to deflate) — declared; PBO over
  the 4-config eligible field IS evaluable (unlike W3's Layer B). Null states classified via
  `GE.classify_layer_b` hand classification with the instrument verdict recorded beside (the
  `classify_null` n_arms=1 mis-render is a known bug, 3× recurrent in this vertical).

**Ship rule per target**: `assembled_*` beats the BEST foil on mean fold CRPS with every gate
clause green ⇒ SHIP (the components earn the chain). Anything else ⇒ a classified null with the
best foil standing as the honest product (explicitly: "the direct model / climatology stands").
Out-of-family observations are reported as observations, never ships.

## 6. Multiplicity — two declared families, the stricter binds

`component` = the 12 Layer-A legs; `downstream` = {k_points, dst_points}. BH-FDR q=0.10 within
each family AND pooled over all 14; a SHIP must survive BOTH (MH2 (a) — a family is
pre-registered, never discovered).

## 7. Power, checked in advance

At 8 folds: the fold clause is attainable (6/8); PBO is evaluable (Layer A ≥ 5-config eligible
fields, Layer B 4); the sign floor 2⁻⁸ ≈ 0.0039 < the 0.10 BH cutoff; `dsr_ceiling(8) = 0.9999`
vs the 0.95 gate. No gate is structurally unattainable ⇒ any null is a finding, not a design
artifact. Known exception, declared: Layer B DSR with one real arm has sr0=0 (a plain PSR) — the
deflation there is carried by PBO over the 4-config field + both BH families.

## 8. What is deliberately OUT of scope (V2+ / other stories)

Licensed charting (V2/NF-W9); weather (until the NF-W0a forward capture accrues); drive-grain
hierarchical simulation (the §4A.1 "hierarchical drive-outcome model" candidate — priced as one
of the count-arm classes only through its feature set here); kicker-level XP skill (§2);
correlated component draws (NF-W5 measured the roster-grain correlation channel ≤0.5%; if the
assembled coverage floor FAILS here, that is the recorded pointer for a successor, not a
mid-story redesign); any serving/deploy wiring.
