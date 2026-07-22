# NCAAF-P1A — college → NFL translation (the NFL feeder; the MLB Edge-E7 analog)

**Model:** `ncaaf_college_nfl_translation_v1` · **target metric:** `target_w_av` · **generated:** 2026-07-22T23:17:22.635942+00:00
**Draft classes emitted:** 2016–2026 (3,804 player projections) · **seed (not emitted):** 2015

> ⚠️ **This is an NFL-rookie PRIOR/projection, not an edge claim.** It translates a player's pre-draft college body of work + combine + recruiting pedigree into a projected early-career NFL outcome, measured against realized NFL production — never a market. `best_alpha = 0` holds. The uncertainty is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a calibrated predictive interval — **N1.2 (rookie-prop pricing) MUST recalibrate on held-out data before pricing** (the E13.6 pattern). The NFL draft is famously noisy: a ROBUST-BUT-WEAK signal (low PBO, DSR possibly <0.95) is a VALID and VALUABLE feeder — reported honestly, not forced. Even a modest projection beats the priors-only NFL rookie market.

## 1. Gates

- ✅ seed class 2015 not emitted (no strictly-prior map exists)
- ✅ every emitted projection was fit on strictly-prior draft classes (n_prior ≥ 1)
- ✅ per-player grain (gsis_id) is unique
- ✅ projection finite + plausible (|z|≤2.59, sd≤1.07)
- ✅ oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)
- ✅ join coverage surfaced: 82.2% carry college production, 49.2% trainable (n=2149)
- ✅ winner beats the position-mean null OOS (MAE 0.7901 < 0.8107)
- ✅ vs draft-slot benchmark: college→NFL winner does NOT beat draft-slot-only (MAE 0.7901 vs 0.6417)
- ✅ PBO computed = 0.000 over 7 configs (<0.2 ✅)
- ✅ DSR computed = 0.994 (n_trials=7) — ≥0.95

## 2. Join coverage (the P1.2b dead-bridge check — PM note #4)

Does every drafted player in the P0.3 xref actually carry P1.1 college production? The college→NFL map trains only on rows that carry BOTH college production AND an NFL outcome; a silently-thin join under-trains it, so the coverage is surfaced here.

|                             |   value |
|:----------------------------|--------:|
| n_xref_rows                 |  4368   |
| n_drafted                   |  3026   |
| n_with_college_production   |  3590   |
| pct_with_college_production |    82.2 |
| n_with_nfl_outcome          |  2624   |
| n_trainable                 |  2149   |
| pct_trainable               |    49.2 |

## 3. The §0.5 bake-off leaderboard (leave-one-draft-class-out expanding-window CV)

Every candidate is fit on STRICTLY-PRIOR draft classes and scored on the held-out class; the metric is MAE on the standardized NFL-outcome target (lower = better). `position_mean` is the NULL FLOOR (ignores the body of work); `draft_slot_ref` is the MARKET-PRIOR benchmark (log draft slot). Both are REPORTED but EXCLUDED from winner selection (`selectable = False`). `oos_skill_vs_null` = how much MAE the config removes vs the null (>0 ⇒ signal).

| config           |   oos_mae |   oos_skill_vs_null | selectable   |
|:-----------------|----------:|--------------------:|:-------------|
| draft_slot_ref   |    0.6417 |              0.1690 | False        |
| stratified_ols   |    0.7901 |              0.0205 | True         |
| partial_pool@2.0 |    0.7987 |              0.0119 | True         |
| partial_pool@4.0 |    0.7988 |              0.0119 | True         |
| position_mean    |    0.8107 |              0.0000 | False        |
| gbm@400-3-0.03   |    0.8150 |             -0.0043 | True         |
| gbm@200-2-0.05   |    0.8181 |             -0.0074 | True         |

**Winner:** `stratified_ols` (best selectable OOS MAE), refit on all labelled draft classes for emission.

### 3b. Headline read

- The college→NFL body of work is a **robust-but-weak** signal: the winner beats the position-mean null out-of-sample (0.7901 < 0.8107) and the beat is CONSISTENT (PBO 0.000 / DSR 0.994 — real, not a lucky draw), but the margin is small.
- ⭐ **The draft slot alone beats it decisively** (slot MAE 0.6417 vs college→NFL 0.7901). The market's draft position encodes far more than college box production + combine (scouting, medicals, film, interviews). So **do NOT use this projection as a standalone rookie board** — its value is as a COMPLEMENT to the draft slot: the RESIDUAL (where college production disagrees with where a player was drafted) is the part N1.2/N1.3 should exploit, by combining both, not P1A alone.
- **Signal concentrates at skill positions**: RB 0.37, TE 0.35, QB 0.32, WR 0.19 carry the projection↔realized correlation; DL 0.00 are near-zero (college defensive box stats translate poorly — expected).
- **Combine + recruiting pedigree add NO signal at this sample size** — every GBM config (the only candidates that use them) scores at or below the null. The college-production composite (used by the linear winners) carries what signal there is.

## 4. Overfitting deflation (PBO / DSR)

- **PBO** = 0.000 over 7 configs × 8 CSCV splits.
  - ⚠️ **Reading a high PBO correctly (E2.1-r):** if the top configs genuinely TIE, a high PBO is the NULL (which tied candidate wins is noise), not overfitting. A high PBO with a WIDE leaderboard spread IS overfitting. Read the spread above.
- **DSR** = 0.994 (observed skill-Sharpe 1.449 vs deflated floor 0.439, n_trials=7). ≥0.95 = the winner's OOS skill survives multiple-testing deflation. **DSR<0.95 here is EXPECTED and OK** — the NFL draft is noisy; a robust-but-weak feeder is still valuable (the P1.2b precedent).

## 5. Does the projection track realized NFL production? (OOS)

Correlation of the emitted `projected_nfl_z` (fit only on strictly-prior classes) with the player's REALIZED standardized NFL outcome, per position group. A positive, position-plausible correlation is the behavioural gate that the map learned something; a flat correlation means the college body of work does not translate and the honest verdict is no signal.

| group   |   proj↔realized corr |
|:--------|---------------------:|
| ALL     |                0.177 |
| DB      |                0.104 |
| DL      |                0.001 |
| LB      |                0.111 |
| QB      |                0.320 |
| RB      |                0.369 |
| TE      |                0.354 |
| WR      |                0.194 |

## 6. Face validity — the top projected rookies (most recent DRAFTED class)

**2026 class (drafted only):** the top projected rookies should be early-round picks at premium positions with strong final college seasons. Read the list, do not just count it — if they are not recognizable early-career contributors, the map is picking up something else.

| player_name            | position_group   | college       |   draft_round |   draft_overall |   projected_nfl_z |   projected_nfl_z_sd |
|:-----------------------|:-----------------|:--------------|--------------:|----------------:|------------------:|---------------------:|
| Tanner Koziol          | TE               | Houston       |             5 |             164 |             0.430 |                0.953 |
| Red Murdock            | LB               | Buffalo       |             7 |             257 |             0.386 |                0.990 |
| Dalton Johnson         | DB               | Arizona       |             5 |             150 |             0.322 |                0.990 |
| Eli Stowers            | TE               | Vanderbilt    |             2 |              54 |             0.293 |                0.953 |
| Dillon Thieneman       | DB               | Oregon        |             1 |              25 |             0.241 |                0.990 |
| Emmanuel McNeil-Warren | DB               | Toledo        |             2 |              58 |             0.240 |                0.990 |
| Jacob Rodriguez        | LB               | Texas Tech    |             2 |              43 |             0.213 |                0.990 |
| A.J. Haulcy            | DB               | LSU           |             3 |              78 |             0.202 |                0.990 |
| Kyle Louis             | LB               | Pittsburgh    |             4 |             138 |             0.197 |                0.990 |
| Jeremiyah Love         | RB               | Notre Dame    |             1 |               3 |             0.166 |                0.918 |
| Cole Wisniewski        | DB               | Texas Tech    |             7 |             244 |             0.158 |                0.990 |
| D'Angelo Ponds         | DB               | Indiana       |             2 |              50 |             0.146 |                0.990 |
| Keyshawn James-Newby   | DL               | New Mexico    |             7 |             252 |             0.142 |                0.999 |
| Genesis Smith          | DB               | Arizona       |             4 |             131 |             0.135 |                0.990 |
| Jordyn Tyson           | WR               | Arizona State |             1 |               8 |             0.127 |                0.977 |

## 7. Limitations

- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks confidence correctly, too tight to price. N1.2 MUST recalibrate on held-out data (E13.6).
- **The target is WITHIN-(position, draft class) standardized** — it captures who produced more AMONG their positional draft peers, not an absolute AV. That is the honestly-learnable signal; absolute cross-position NFL production is not comparable and is not claimed.
- **OL and specialists have NO college box production** (`box_production_available = False`): they get a combine/pedigree-only projection and are excluded from the production VALIDATION.
- **UDFAs carry no NFL-outcome label** (undrafted → no draft-pick outcome row): they are excluded from TRAINING but still receive a college-only projection, flagged `is_udfa` / lower confidence. Weight them accordingly downstream.
- **~11 draft classes (2015–25) is the training ceiling** (the 2014 box-production floor). The seed class is not emitted. A small class count is why the DSR bar is read leniently.
- **Draft slot is a REPORTED benchmark, not a feature of the translation candidates** — the college→NFL map is built from college production + combine + pedigree so it can be COMPARED to the market's draft-slot prior, not built from it.
- **Empirical-Bayes plug-in** (partial-pool winner): the variance components are point estimates, not integrated over — the same posture as P1.2 and MLB's bullpen posteriors.

