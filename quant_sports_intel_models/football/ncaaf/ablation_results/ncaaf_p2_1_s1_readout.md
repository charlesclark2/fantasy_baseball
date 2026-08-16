# NCAAF-P2.1 S1 — `pace` under a lower-variance gate design: read-out, attribution and handoff

**Status (2026-08-15): ✅ RUN COMPLETE — verdict `SHIP` on the pre-registered binding gate.**
Machine dossier: [`ncaaf_p2_1_s1_pace.md`](./ncaaf_p2_1_s1_pace.md) / `.json` (written by `--stage decide`).
Contract: [`ncaaf_p2_1_s1_preregistration.md`](./ncaaf_p2_1_s1_preregistration.md) — committed
`4c8d208e`, BEFORE the harness (`a0f37e51`) and BEFORE the run. That ordering is the artifact.

**One-line result:** `pace` reproduces P2.1 exactly (max |Δ per-fold CRPS| = 0.0; +0.0620 CRPS,
8/8 folds, p = 0.0020, PBO 0.03) and clears the separately-registered per-FOLD DSR at **0.9981**
(SR 1.49 vs SR0 0.32; N = 8, V = 0.047) — also 0.995 at the lineage-inclusive N = 30. All six
anchor checks hold. `best_alpha = 0` — this is a calibration ship, not an edge claim (ATS 0.5057 /
O/U 0.5141, both under the 0.5238 breakeven).

⭐ **But read §2 before quoting the mechanism** — the story's premise ("the gap is the series
definition alone") is *half* right, and the honest attribution says the coherent FIELD did more of the
work than the series did.

---

## 1. What was fixed forward, and what came back

| pre-registered | outcome |
|---|---|
| primary = `pace` (the P2.1 H9 block VERBATIM, 8 cols); ONLY it can ship | cleared every gate → **PROMOTED** |
| field = 3 pace representations, all strict subsets of the H9 columns (`pace` · `pace_axis` = {`pace_sum`,`pace_diff`} · `pace_total_axis` = {`pace_sum`}); N = 8 with the 4 anchors; V over the 3 real arms | both siblings ALSO cleared every arm-level gate (+0.0803 / +0.0789, 8/8, p 0.0005 / 0.0008) — reported as `FIELD_MEMBER_CLEARED_NOT_PROMOTABLE`, never promoted |
| DSR on the per-FOLD series (binding, degenerate-excluded); PBO on P2.1's per-BUCKET series | DSR 0.9981 ✅ · PBO 0.03 ✅ |
| reproduction check R (byte-identical harness) | max abs dev **0.0** on `reference` and `pace` across all 8 folds ✅ |
| anchors: oracle floor / permute / zero_width / max_width | 1.4042 vs best real 18.4387 · 21.80 loses · 23.19 loses + fails floor (0.195/0.185) · 27.46 loses + satisfies floor (1.000/0.999) ✅ |
| S1-V1…V7 code verifications | pace is in NO reference column, is NOT a P1.2 covariate, correlates weakly with the ratings (|ρ| ≤ 0.25 — a team-level echo, not the game-level tempo), acts on the TOTAL axis (ρ(`pace_sum`, total) = −0.24), is RAW (no target encoding), and is 100 % NULL ⇒ inert on week-1 rows |

The per-fold deltas by eval season: 2018 +0.066, 2019 +0.032, 2020 +0.106, 2021 +0.033,
2022 +0.062, 2023 +0.004, 2024 +0.067, 2025 +0.136 — identical to P2.1 §9.3.

## 2. Which lever did the work — the finding that outlives the verdict

S1 changed **two** things relative to P2.1's DSR: the return SERIES (bucket → fold) and the FIELD
(16 heterogeneous arms → 3 pace representations, which sets both `V` and `N`). The binding cell was
fixed before the run; `--stage decide` computes the other three from the P2.1 record so the
dependence is auditable (the (bucket, P2.1-field) cell reproduces P2.1's 0.0409 exactly):

| series ＼ field | P2.1 field (16 arms, N = 22) | S1 field (3 pace reps, N = 8) |
|---|---|---|
| per-BUCKET (P2.1's series) | **0.0409** — SR 0.53 vs SR0 0.87 (V 0.20) ← P2.1's record | **0.9809** — SR 0.53 vs SR0 0.12 (V 0.007) |
| per-FOLD (S1's series) | **0.3903** — SR 1.49 vs SR0 1.60 (V **0.68**) | **0.9981** — SR 1.49 vs SR0 0.32 (V 0.047) ⭐ binding |

Read across the rows and down the columns:

* **The series alone would NOT have rescued `pace`.** Under P2.1's field the per-fold series posts
  0.39 — because the 16 heterogeneous arms have a per-fold Sharpe DISPERSION of **0.68** (the 0/8
  losers such as `hfa_team_eb`, −0.145 CRPS, carry large NEGATIVE per-fold Sharpes), which pushes
  SR0 to 1.60, above `pace`'s own 1.49. The series raises SR (0.53 → 1.49); it cannot lower SR0.
* **The coherent field alone WOULD have** — even on P2.1's noisier bucket series, `pace` clears at
  0.98 once V is measured over the three pace representations (V 0.007, SR0 0.12).
* Both together give the binding 0.998. So: **field coherence was the PRIMARY lever; the series was
  the SECONDARY lever.** P2.1 §9.6 diagnosed the failure as "the series"; that was incomplete. The
  correct diagnosis is the NF-W6b-C / MH2.2 mechanism — *a heterogeneous declared field inflates the
  cross-trial dispersion `V` that DSR deflates against, and it does so MORE on the per-fold series
  (V 0.68) than on the per-bucket one (V 0.20)*, because far-out losers are far-out on every series.

Is the ship therefore legitimate? Yes, and for the reasons the program has already ratified, not
for a reason invented here: MH2 (a) says a family gets its OWN pre-registered field and that
"bundling unrelated mechanisms OVER-taxes a real finding" — while "trimming a field after the fact
UNDER-taxes it". S1 is a **fresh registration** whose 3-arm field was declared FORWARD, on
mechanistic grounds (the pace feature and its representations — no new column, no other mechanism),
exactly as the story instructed and exactly the shape NF-W6b-C, MARGIN2→3 and W7→W7b shipped under.
The lineage-inclusive figure (N = 30, 0.995) shows the multiplicity of P2.1's search does not
overturn it. What the 2×2 adds is the honest caption: **the verdict rests on the declared family, not
on the fold series** — a reader who thinks the family was too narrow should say so about §2 of the
pre-registration, not about the arithmetic.

⭐ **Carry-forward rule (sharper than P2.1 §9.6):** when a real effect fails DSR inside a
heterogeneous battery, the FIRST lever to inspect is the field's `V` (compute the 2×2 above), and
the successor's job is to declare a coherent family forward; changing the return series is a
smaller, secondary win. And **do not read `classify_null`'s `max_field_size = 0` as "no field ever
clears"** — that figure is computed at the *battery's* V; a coherent family changes V, not just N.
(P2.1's `DSR_UNREACHABLE` label was correct *for its own field*; the remedy text "field size is not
a lever" was true of N and false of V — the MH2.2 lesson, "the post-hoc DSR jump was bought by V
collapsing, not by the trial count", now measured on a case where the family was declared FORWARD.)

## 3. Attribution — where in the block the effect lives

| read | result | meaning |
|---|---|---|
| `pace` (8 cols) vs `pace_axis` (2 cols) | `pace_axis` is BETTER by **0.018 CRPS** | the six per-side LEVELS do not add — they *cost*. S1-V4 predicted this: `seconds_per_play = possession_seconds / off_plays` is an exact ratio identity and the composites are exact linear combinations of the levels, so the 8-column block spans a lower-dimensional space and the ridge penalty pays for the redundancy. |
| `pace_axis` vs `pace_total_axis` (`pace_sum` only) | +0.0014 — at the edge of the 1e-3 tie band | essentially NO margin-axis content: the effect is the possessions channel on the TOTAL, as registered (H9: "the SUM on the total axis, where pace should act"). |

⛔ **The primary still ships as registered.** The pre-registration fixed the ship candidate as the
P2.1 arm and said a better sibling is a *successor hypothesis*, never a promotion from this run —
"pick the best of three" is precisely the search the registration bounds. So the shipped contract is
the 8-column block; the 2-column composite representation is a strong-prior, cheap successor
(**S1b**: register `pace_axis` — or `pace_sum` alone — as the primary, forward; expected +0.018 over
S1). It should be folded into the serving story below rather than run as a separate research
session, because whichever representation serves has to be the one the mean map carries.

## 4. What "SHIP" means operationally — and why the retrain is a code prerequisite, not a command

The story's closeout expects "the retrain + P1.5 re-point + serving publish" as post-merge operator
commands. On contact with the code, three facts change that (all recorded in the pre-registration
§5, before the run):

1. **The served P1.4 artifact carries no mean model.** `ncaaf_game_distribution_v1.json` = dispersion
   parameters (σ₀, k, ρ, form) + a contract NAME. `bakeoff_ncaaf_game --stage finalize` refits the
   dispersion on OOS residuals of a named contract; the contract set today is
   `full · strength_only · clustered · top_k` — **no pace contract exists**, and the P1.4 matrix cache
   carries the six side columns but NOT `pace_sum` / `pace_diff` (those are P2.1-derived).
2. **P1.5's season sim rebuilds μ ANALYTICALLY** from the P1.2 strengths (`season_simulation.py`:
   `μ_margin = HFA·(not neutral) + Δstrength`, `μ_total = 2·base + Σoff − Σdef` — "not an independent
   pace axis", per its own docstring). It never reads a ridge. Re-pointing it at a σ refit under a
   pace contract WITHOUT a pace term in μ would be a train/serve mismatch (E7.9 class): σ fitted on
   pace-mean residuals, served against a strength-only mean.
3. **NCAAF is not serving a product surface** (`production_model_state/ncaaf.md`: no store / API /
   frontend; boards land in the S3 research lakehouse; the app is sequenced mid-season on the refined
   model). And by S1-V6 the **pre-season board is untouched by pace by construction** — week-1 rows
   are 100 % NULL ⇒ mean-imputed ⇒ inert. `pace` is an IN-SEASON effect (`--as-of-week` boards and
   standalone game distributions).

⇒ **There is no correct operator-only command today that lands `pace` in a served artifact.** The
retrain is a small, well-scoped code story — **S1-serve** — and I am stating that plainly rather than
handing over a command that would produce a mismatched artifact:

**S1-serve (needs a session, ~half a day; the pre-season kickoff is NOT at risk because pace is
inert pre-season):**
1. `bakeoff_ncaaf_game.py`: add a `strength_pace` contract = `strength_only ∪ the pace block`
   (derive `pace_sum`/`pace_diff` at `--assemble`, kept OUT of `full` so P1.4's frozen record is not
   silently redefined). Decide the served representation there — the S1 primary (8 cols) or, if
   S1b is registered and clears, the 2-col composite.
2. Persist a **mean artifact** beside the dispersion (`ncaaf_game_mean_v2.json`: the standardized
   ridge coefficients + train means for the served contract) so μ is no longer implicit.
3. `season_simulation.py` / `run_season_simulation.py`: an optional pace term in the mean map,
   read from the mean artifact, with per-team as-of-week pace joined in `load_strength`/schedule
   (NULL ⇒ inert, so week-1 boards are byte-identical to today's — pin that with a guard).
4. Re-run P1.5's held-out calibration gate (`run_season_simulation --calibrate`, ~minutes) —
   the sim's own gate must be re-cleared, not assumed.
5. Then, and only then, the operator commands (LAPTOP, Snowflake-free):
   `AWS_DEFAULT_REGION=us-east-2 uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage finalize --model-class ridge --contract strength_pace --form strength_posterior`
   → writes `ncaaf_game_distribution_v2.json` + the mean artifact; then
   `AWS_DEFAULT_REGION=us-east-2 uv run python -m quant_sports_intel_models.football.ncaaf.models.run_season_simulation --season 2026 --s3`
   → re-renders the board. Publish = merge to `main` (the box image carries the artifacts).

## 5. Files

- `models/p2_1_s1_pace.py` — the S1 harness (battery on the P2.1 folds via `bakeoff_ncaaf_p2_1.score_arm_fold(..., blocks=S1_BLOCKS)`; decide on the DECLARED series; reproduction check; the 2×2 lever decomposition; dossier render).
- `models/bakeoff_ncaaf_p2_1.py` — ONE change: a `blocks=` injection point on `_arm_columns` / `score_arm_fold` (default = P2.1's `BLOCKS`; P2.1's 25 guards unchanged and green).
- `betting_ml/tests/test_ncaaf_p2_1_s1_pace.py` — 17 fast-gate guards (`football` shard; imports no `pipeline`); 6 RED-proven against deliberately broken source (binding DSR read from the bucket series · `classify_null` fed the bucket Sharpe · `V` measured incl. anchors · verdict without the reproduction check · the <3-fold UNDEFINED guard disabled · a non-pace column smuggled into the field).
- `ablation_results/ncaaf_p2_1_s1_preregistration.md` — the contract (committed first).
- `ablation_results/ncaaf_p2_1_s1_pace.{md,json}` + `ncaaf_p2_1_s1_pace_scores.json` — the run.
- artifacts (gitignored, re-creatable): `betting_ml/data/cache/ncaaf_p2_1_battery.parquet` (`--assemble`, 29 s).

## 6. Honest framing

`best_alpha = 0`. Nothing here is an edge claim; the vs-close leg is unchanged from P2.1 (both sides
under breakeven, and the reference's own ATS moved 0.4996 → 0.5009 only because `--assemble`
re-pulled the live P0.6c close staging — two fewer pushes, `ats_n` 4115 → 4113 — the model path is
byte-identical). What ships is a small, real, reproducible calibration improvement (+0.062 CRPS,
~0.3 % of the reference's 18.52) on the total axis, in-season only.
