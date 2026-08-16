# NF-W6d — pre-registration: distributional outputs for ALL optimizer-input metrics

**Committed 2026-08-15, BEFORE any full run** (smoke path proofs only). Every constant below is
the value in `stat_distributions_d.py`; this document is the narrative, the module is the source
of truth (NF-D16 discipline). Fresh registration (MH2.2): seed **20260817** (≠ W6b 20260815, ≠
W6b-C 20260816); nothing from the NF-W6 / W6b / W6b-C fields is promoted into any field here.

⚖️ Edge-independent projection product — `best_alpha` N/A · deploy-held · research-only · NF-G0
staged. Runtime gate N/A (no `--publish`, no `deploy.sh`, no Dagster/S3/dbt — local artifacts + a
registry entry read only by governance). Every emitted string is a calibrated RANGE, screened
against the shared overclaim denylist (`export_track_record_json._CLAIM_DENYLIST`).

## §0 — Scope

The weekly optimizer-input stat universe = the champion's 11 raw components (`WP.COMPONENTS`:
attempts, passing_yards, passing_tds, passing_interceptions, carries, rushing_yards, rushing_tds,
targets, receptions, receiving_yards, receiving_tds) + 2 scored stats the weekly line does not yet
emit (fumbles_lost = sack+rushing+receiving fumbles lost; two_pt = passing+rushing+receiving 2-pt
conversions). 4 positions × 13 stats = **52 substrate cells**, each served by exactly one of: an
already-certified SHIP (7: NF-W6c + NF-W6c-wire), a NF-W6d Phase-B SHIP, or a NF-W6d Phase-C
calibrated default. `assert_substrate_is_complete()` proves the map (52 cells, once each).

Labels ATTACHED to the certified NF-W6 matrix (cache `57c4cf96bb3c3570`, 84,553 rows, PIT gate on
every load): passing_interceptions / fumbles_lost / two_pt at (season, week, gsis_id), duplicate-
grain-refusing, conservation-guarded (`attach_extra_labels`, the `EM.attach_td_labels` shape). NO
new features (the champion set `WP.FEATURES` + position code, verbatim). W6d matrix cache key
`26c34fbe778c9d87`.

**Gated cells (22)** — QB: attempts, passing_interceptions, carries, rushing_tds, fumbles_lost,
two_pt · RB: carries, targets, receptions, receiving_tds, fumbles_lost, two_pt · WR/TE: targets,
receptions, receiving_tds, fumbles_lost, two_pt. The four TD cells NF-W6 closed (QB rushing_tds,
RB/WR/TE receiving_tds) are RE-GATED on purpose: NF-W6 measured them with non-atom-aware forms
only, and NF-W6b-C then showed an atom-aware neighborhood form beating the climatology by 13% on a
cell that instrument had read at 4% — the atom-aware forms are the "different mechanism" the
closure asked for; this is a fresh measurement, not a re-read.
**Minor channels (22)** — QB receiving; RB passing; WR/TE passing + rushing — Phase-C default
only. **Withheld prior (1)** — RB|receiving_yards (W6b POWER_LIMITED, PM Decision B) — default
until its calendar-bound re-test.

## §1 — Stat classes (declared; they set family, foils, FDR family)

- **COUNT** = attempts, carries, targets, receptions (moderate atom, real conditional spread).
- **EVENT** = receiving_tds, rushing_tds, passing_interceptions, fumbles_lost, two_pt (zero-heavy).

## §2 — Phase A: the ceiling gate

Per cell, per-form block-peeking oracles floored at matched-n controls (NF-D16 (g‴) / NF1.9 (f)),
vs the BINDING incumbent (COUNT: better of `inc_head_bank` / `inc_climatology`; EVENT:
`inc_climatology`). Forms per class — COUNT: marginal, head_bank, cand_quantile, knn, hurdle,
negbin; EVENT: marginal, knn, hurdle, negbin. Conditional oracles are cross-fit within the block
(K=3, `EM.crossfit_ids`); ⭐ their matched controls are sized to the peek's EFFECTIVE fit size,
(K−1)/K of the block (`SDC.matched_window` — the NF-W6b-C refinement; NF1.7 (b): same-family AND
same-sample); the marginal pair keeps the W6 full-block sizing (n-insensitive, comparable to W6).
Metric `crps_q199`. Degenerates (nihilist / zero_width / max_width — from the class's conditional
incumbent where one exists, else the marginal foil) SCORED every cell and must lose (NF-D11/D14).
`MIN_COND_ROWS = 40`: a hurdle form with fewer non-zero rows on its fitting side is INAPPLICABLE
for that (stat, fold) — recorded as None, excluded from that cell's ceiling max and NAMED; never
scored on a constant.

**Decision:** ceiling_pct = 100·(binding inc − best per-form oracle)/binding inc, paired over the
8 NF-W1 folds. stat_ok = CI95 excludes 0 ∧ calibrated fold clause ∧ BH q=0.1 binding own AND
pooled (two families: COUNT cells, EVENT cells). Bands (NF-W5/W6): <2% NO · 2–5% MARGINAL · ≥5%
YES; not stat_ok → NO regardless.
**⭐ License rule (declared here, before the run):** a cell is licensed for Phase B iff its answer
∈ {YES, MARGINAL} ∧ stat_ok. MARGINAL licenses because the block peek is a conservative reader of
atom-aware full-train capacity (a K-fold peek trains on ~2/3 of a ~4k-row block; the bake-off arm
on ~75k rows) — NF-W6b-C measured 4.08% at the gate → 12.97% in the bake-off. A NO is a RECORDED
FINDING (point mean near-optimal → Phase-C default), never forced into a bake-off. PBO UNDEFINED
(anchor contrast); no arm is selected; `classify_null` not invoked.

## §3 — Phase B: the bake-off (cells READ from the Phase-A record, never chosen)

Families — COUNT: `lgbm_quantile_tail`, `lgbm_hurdle_tail`, `knn_quantile`, `count_negbin` (4);
EVENT: `lgbm_hurdle_tail`, `knn_quantile`, `count_negbin` (3, the W6b-C coherent atom-aware
family). ⛔ Banned on EVENT (on the record): `enet_residual`, `inc_head_bank`, `lgbm_quantile_tail`
— a non-atom-aware bank/flat tail cannot express a 60–99% atom and its guaranteed loss inflates
V (the W6b-C mechanism). Foils — COUNT: `inc_head_bank` + `inc_climatology` (binding sets the
bar); EVENT: `inc_climatology`. Permuted anchor: the class's declared arm's identical code path on
labels permuted within (position, gw) — COUNT `lgbm_quantile_tail`, EVENT `knn_quantile`.
Anchors: nihilist / zero_width / max_width + the marginal pair + one oracle/matched pair per
family form. Anchors NEVER enter the trial field (MH2.1 (a)) ⇒ DSR-CONV forward: the degenerate-
excluded V is the structural fact (`degenerates_excluded_from_v=True` = provenance).
`DECLARED_FIELD_SIZE` = 4 (COUNT) / 3 (EVENT) → `cv_power.classify_null(declared_field_size=…)`;
the record reads `field_remedy_admissible` (MH2.7).

**Gates (the W6b-C ten, by identity — `SDC.compose_gate_w6bc`):** beats_foil ∧ fold_consistency
(`fold_consistency_clause(8)`) ∧ PBO<0.2 over the eligible field ∧ DSR≥0.95 ∧ BH q=0.1 (two
families own AND pooled) ∧ coverage floor 0.80 (ONE-SIDED, block SE 3 — NF1.9 (e)) ∧ degenerates
lose ∧ permutation behaves ∧ not_a_foil_tie (1e-4 CRPS) ∧ winner_own_form_floor. Fails closed.
**Null reading:** constraint/anchor-only → CONSTRAINT_REFUSED (hand). Statistical → classify_null,
WITH the DSR MECHANISM attached (`dsr_mechanism`: field SR0, winner SR, most-dispersing arm) — a
DSR failure with winner SR ≤ SR0 is read as field-dispersion (DSR-UNREACHABLE in this field), not
a fold shortage (NF-W6b-C). Report-only: PPR points-units (|weight|: rec 1, rec/rush TD 6, INT/
fumble 2, 2-pt 2, volume 0), atom calibration, era split, gate sensitivity with DSR waived.
**Reproduction control (NF-W2d):** on every fold, BEFORE any new cell, the 7 served cells'
winners are re-fit through `stat_distribution_serving.ARM_DISPATCH` and their fold CRPS must equal
the certifying records' (`nf_w6b_stat_distributions.json` / `nf_w6b_c_rb_rush_tds.json`)
byte-identically; any mismatch ⇒ `invalid: true`, no verdict layer, exit 2.

## §4 — Phase C: the calibrated default (NOT a bake-off winner)

Cells = substrate − the 7 served (45). Pre-registered ORDER — modeled cells: `count_negbin` (NB2
around the champion head mean, purged-calibration dispersion, Poisson at the α floor) → `climatology`
(per-position discrete empirical marginal); minor channels AND yards cells (a yards stat can be
negative, where a count pmf is meaningless): `climatology`. The FIRST form that is
CALIBRATED is the default: coverage(80) ≥ 0.80 one-sided (block SE 3) ∧ randomized-PIT (199 grid,
`randomized_pit_levels`) max-decile-deviation ≤ **0.03** (a materiality bound at 5–10k rows, SE
per decile ≈ 0.003–0.004; declared). ⛔ No CRPS decides a default; the nihilist is SCORED and
reported (NF-D14). If no form calibrates, the last form is emitted with a loud
`calibration_warning` (the optimizer still needs a distribution). Which cells actually TAKE a
default is decided at serve time by subtraction (a SHIP verdict wins).

## §5 — Serving (dispatch-only, NF-G0 staged)

`stat_distribution_serving_d.served_map` derives the 52-cell map FROM THE RECORDS (fail-closed on
absent / smoke / partial / INVALID / wrong-phase) with precedence W6b/W6b-C → W6d-B SHIP → W6d-C
default; `ARM_DISPATCH_D` = the W6c dispatch + `SDC.arm_count_negbin` + `SDD.default_climatology`
by identity (no learner import — AST-guarded); representation = the W6c contract, reused. Staged
as `nfl_fantasy_w6d_v1` on `weekly_stat_distribution` (challenger; promote blocked). Rows carry
`source` + `calibration_warning` so a default is never presented as a conditional projection.

## §6 — Explicitly out of scope (named follow-on)

The arbitrary-league RE-SCORING ASSEMBLY (per-stat distributions → per-player fantasy-point
distribution under a league's scoring, with cross-stat correlation) — its own story; it triggers
the three-implementations parity tax (fantasy_engine / browser TS / Lambda scorer).
