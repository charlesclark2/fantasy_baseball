# NF-W2 — pre-registration: the availability channel (current-week injury-report state)

**Committed BEFORE the full run** (the NF-D20 discipline). Every constant here is code in
`weekly_projection_w2.py` (the pure module); the runner (`run_nf_w2_injury_bakeoff.py`) reads it
and restates nothing. `best_alpha = 0` — a projection product, no betting/edge claim.

## The ONE hypothesis (registered, not searched)

**Current-week injury-report state — the final pre-gameday designation (Out / Doubtful /
Questionable / listed-no-designation) plus latest practice participation — improves the weekly
per-game distributional projection, primarily through the zero/availability leg of the hurdle
mixture.** This is NF-W4's "availability is the LARGEST error source" in lean form: the NF-W1
incumbent prices availability only from trailing history (`played_share_l4`, snap lags), so a
player ruled Out on Friday still carries a healthy-history projection into Sunday.

Scoping priors measured before registration (design quantities, not selection):
2016–2024, positions QB/RB/WR/TE — **Out: 2,737 player-weeks, 2,736 scored zero** (mean 0.00 PPR);
Doubtful: 491, 99.2% zero; Questionable: 3,942, 47% zero (mean 5.05); listed-no-designation:
7,479, 24% zero (mean 8.51). ~19% of modeled player-weeks carry a listing. The feed is one row
per player-week (4 dupes in 47,653) and **99.9% of latest `date_modified` stamps land strictly
before gameday** (47,595 / 47,640).

## ⛔ The one thing this story may not do

Promote an arm that has not beaten the **NF-W1 champion itself** (`base_hurdle` — the incumbent
`lgbm_hurdle` spec, refit per fold on its exact FEATURES) on purged held-out weeks under
deflation. The incumbent is simultaneously the **matched foil** (NF-D10: each arm is the
identical bundle plus the injury family, so the paired delta IS the attribution). A foil win, a
gate miss, or an anchor violation is a **recorded NULL** (classified via
`cv_power.classify_null`), never a ship.

## Frame (binding NF-W0/NF-W1 constraints — unchanged)

- Certified roster-first frame rebuilt in memory, 2016–2025 REG, zeros retained; label pinned
  `v1.nflverse.stats_player_week` / `ppr`; scoring population = QB/RB/WR/TE, `label ≠ bye`.
- All NF-W1 features unchanged (`weekly_projection.FEATURES`); snap features NULL-bearing;
  era-forbidden tokens excluded; no markets/weather/depth-rank/game-day-inactive features.
- ⛔ `weekly_rosters.status == 'INA'` stays label-side only. The injury family's admissibility
  bound (below) is **gameday 00:00 UTC**, hours before any kickoff — the family cannot smuggle
  game-day inactives in.

## The new family: `injury_report` (PIT-verified via `date_modified`)

Source: nflverse `injuries` (lake), one row per (season, week, gsis_id) after latest-stamp dedupe.

**Admissibility (fail-closed):** a report row is consumable for a player-week iff
`date_modified` (UTC) **< the player's team's target gameday 00:00 UTC** (the per-game as-of
instant; measured retention 99.9%). A row failing the bound is EXCLUDED and the player-week reads
as unlisted (45 / 47,640 rows; PIT-honesty over completeness). The NF-W0a `assert_point_in_time`
guard receives one extra record per consumed report row with `source_timestamp = date_modified`;
the per-row projection instant is the row's own target gameday 00:00 UTC (a strict refinement of
NF-W1's week-min instant — serving reality is a re-projection before each game's kickoff).

**Features (7, all from the latest admissible row; verified era 2016–2024):**

| column | semantics |
|---|---|
| `injury_report__listed` | 1 = on the report this week; 0 = not on the report (a real semantic zero in the verified era) |
| `injury_report__status_out` | final admissible designation one-hots; listed with NULL designation |
| `injury_report__status_doubtful` | = listed=1 with all three status one-hots 0 (the ~46%-null |
| `injury_report__status_questionable` | `report_status` trap — NULL means "no designation yet", never healthy) |
| `injury_report__practice_dnp` | latest admissible practice participation one-hots; |
| `injury_report__practice_limited` | Full/garbage/absent = both 0 |
| `injury_report__observed` | era presence flag: 1 = the family is measurable (2016–2024) |

**2025 is `prospective_shadow` (upstream deleted `date_modified`): the whole family is NaN with
`observed = 0`** — ⛔ never `fillna(0)`; NULL = unmeasured, not healthy (the NF-W0b snap
discipline applied to this family). Production 2026 re-arms the family via NF-W0a's own capture.

## Folds

- **12 GATED expanding-window half-season blocks: 2019H1 … 2024H2** (H1 = weeks 1–9; purge 2
  global weeks; burn-in 2016–2018). The family is ACTIVE and PIT-verifiable on all 12 — the
  NF-D20 active-fold discipline: the report states each fold's listed share and Out∪Doubtful
  share alongside the pass count. 12 active folds are available TODAY (the MH2 window lesson);
  `fold_consistency_clause(12)` requires 8/12.
- **2 SHADOW blocks: 2025H1, 2025H2 — NOT gated.** The family is structurally unmeasured there
  (all-NaN + observed=0), so the registered expectation is a near-tie of every arm with
  `base_hurdle` — the NF1.9 "a mechanism that cannot act" proof, run because the harness makes it
  free, reported beside the verdict.

## The field

**Real arms (the declared 3-arm family — ONE coherent mechanism family, availability
incorporation; this is the DSR trial field):**

| arm | form |
|---|---|
| `inj_both` | hurdle with the injury family in BOTH legs (P(zero) classifier + conditional quantile bank) |
| `inj_zero_leg` | injury family in the P(zero) leg ONLY; conditional leg = the SHARED base fit (mechanism-targeted: availability, not efficiency) |
| `inj_override` | base hurdle untouched except: test rows with admissible Out∪Doubtful get `p0 ←` the train-fold pooled empirical P(zero | Out∪Doubtful) over observed listed rows (raises if that cell has <200 train rows — an anchor that fails to fit must fail loudly, NF1.7 (a)) |

**Foil / incumbent (non-shippable in this field; if nothing beats it, it stands):**
`base_hurdle` — the NF-W1 champion spec refit per fold (mechanically identical to
`weekly_projection.fit_lgbm_hurdle`; guard-tested equal).

**Anchors (diagnostic — excluded from the PBO matrix and the DSR trial field, MH2.1 (a)):**

| anchor | role | registered expectation |
|---|---|---|
| `nihilist_zero` | all-zero degenerate ceiling | MUST lose to every real arm (measured every run, never reasoned — NF-D14) |
| `pos_marginal` | train climatology per position (the all-mean analog) | MUST lose |
| `inj_permuted` | `inj_both`'s exact form with the injury columns' values permuted within (position × global week) in train AND test | see the PRE-RUN AMENDMENT below — (a) the winner MUST beat it (content over capacity, the positive NF-D10 check); (b) its lift over `base_hurdle` must not be statistically significant (one-sided paired p ≥ 0.05) |
| `oracle_avail__base` | PEEKING availability ceiling of the base form: `p0 = 1{y=0}` realized, base's conditional leg | floors `base_hurdle` / `inj_zero_leg` / `inj_override` (their shared conditional form) |
| `oracle_avail__inj` | same, with `inj_both`'s conditional leg | floors `inj_both` |

Per NF-D16, each arm is floored by the peeking version of **its own form**: an arm beating its
own availability oracle is a metric-inversion tell, never a win. The two oracles differ only in
the conditional leg (same family, same sample, same capacity — the NF1.7 (b) requirements hold by
construction).

### ⚠️ PRE-RUN AMENDMENT (2026-08-08, committed BEFORE the full 12-fold run; disclosed)

The first registration's permutation clause was the strict binary "`inj_permuted` must not beat
`base_hurdle` on the raw mean". The smoke (2 folds — a code-path validation, artifacts suffixed
`_smoke`) surfaced what is in fact an ANALYTIC defect in that clause, not an empirical result:
when the permuted family is INERT (the expected case), the two arms are a statistical tie, and a
strict `≥` on tied means is a **~50% false-veto coin flip** — the NF1.8 "a rank statistic cannot
tell a tie from a loss" lesson, and exactly the un-calibrated-clause class MH2-H8 exists to fix.
The measured smoke magnitudes (permuted "beating" base by 0.0003–0.014 CRPS vs arm lifts of
0.05–0.15) are tie-scale, consistent with the analytic reading. The amended clause is
calibrated, two-part, and STRICTER on the question that matters (content):

1. **`winner_beats_permuted`** — the winning arm's mean fold CRPS must beat `inj_permuted`'s
   (the positive content-over-capacity attribution check; the permuted arm is the capacity foil).
2. **`permuted_lift_not_significant`** — `inj_permuted`'s lift over `base_hurdle` must be
   non-positive OR non-significant (one-sided paired p ≥ 0.05 over the 12 folds). A significant
   permuted lift means the added columns carry non-player-level (week×position marginal-rate)
   signal, and the attribution must then be read as winner−permuted, not winner−base.

The winner−permuted paired delta is reported per position either way (the content attribution).

## Metric

- **Selection: CRPS** (`crps_q39`), identical 39-level representation for every arm, monotone
  rearrangement uniformly applied. ⛔ MAE reported, never selects (inverted at QB/TE on this
  frame — NF-D11/NF-D14).
- Coverage of the central 80% interval is a **FLOOR** (0.80): reported with binomial SE, blocking
  only beyond 3 SE (NF1.8 rows-not-decimals).

## Gates (per position; ship unit = per-position champion)

SHIP requires ALL of: winner (among the 3 arms, mean fold CRPS over the 12 gated folds) beats
`base_hurdle` · `cv_power.fold_consistency_clause(12)` = 8/12 paired fold wins · PBO < 0.20 over
the eligible set {3 arms + `base_hurdle`} (`NF18.deflate`; flips + contender spread + os-gap
reported) · DSR ≥ 0.95 over the declared 3-arm family (paired per-fold deltas vs `base_hurdle`;
`M14.deflated_sharpe`) · BH-FDR q = 0.10 across the 4 position tests · every MUST-lose anchor
loses · the amended permutation pair (`winner_beats_permuted` AND
`permuted_lift_not_significant`) holds · no arm beats its own-form availability oracle ·
coverage floor not in blocking shortfall. Anything else ⇒ the position's verdict is a `classify_null` state, recorded
with the NF-D20 active-fold count.

## Outputs

- `ablation_results/nf_w2_injury_bakeoff.{md,json}`; `--smoke` writes `*_smoke` artifacts that
  can never be mistaken for the real search.
- Attribution table (the matched-pair deltas ARE the attribution), the shadow-2025 tie check, the
  per-fold activity table, and the coverage floor report.
- Registry/serving are untouched — a promotion is registered in `sub_model_registry.yaml` only on
  a SHIP verdict, and any staging goes through the NF-G0 governance CLI as an operator step.
