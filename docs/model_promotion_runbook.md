# Model Promotion Runbook (S3 + Contract Integrity)

**Owner:** Charles Clark
**Last updated:** 2026-06-12 (codified promotion gate)
**Applies to:** All three production targets — `home_win`, `total_runs`, `run_differential`

> **Step 0 — the promotion DECISION gate (run BEFORE any S3 push).** Whether a challenger is
> *allowed* to replace the champion is no longer an ad-hoc per-story judgement. It is the
> **codified Case 3 gate** — `betting_ml/utils/promotion_gate.py` (`evaluate_promotion`),
> specified in `implementation_guide.md` → "Champion selection policy → Case 3". In one line:
> **PROMOTE iff the challenger beats the *deployed champion* on accuracy-to-truth across
> COMPLETED held-out seasons — beyond the noise floor, paired-bootstrap significant, with no
> completed-season regression, the current partial season corroboration-only — and the gate
> passes on ≥2 consecutive evals (hysteresis).** Beating the market is NOT required (the champion
> doesn't either). Model-agnostic: Bayesian/posterior-predictive challengers are scored with
> `crps_ensemble` and judged by the same criteria. Only once the gate returns PROMOTE do you run
> the S3 + contract steps below.

> **Why this exists (read first).** The older [`model_deploy_runbook.md`](model_deploy_runbook.md)
> describes the *train → registry → git-tag* flow and assumes the `.pkl` artifacts are
> git-tracked. **That is no longer how a model goes live.** Production (`predict_today.py`)
> loads the champion from the **S3** `artifact_path` in `model_registry.yaml` via
> `betting_ml/utils/artifact_store.load_artifact`. **Training writes LOCAL only**
> (`save_model`); a local retrain changes *nothing* in prod until you upload it to S3.
> This runbook covers the S3 promotion and the integrity checks that the old one predates.
> Use the old runbook for the champion/challenger gate (Step 1b) and rollback-via-tag history;
> use this one to actually push a model live.

---

## The two facts that cause every promotion bug

1. **Prod reads S3, not your working tree.** `save_model()` / a finished `run_*_search.py`
   writes `betting_ml/models/<target>/<name>.pkl` **locally**. `predict_today.py` downloads
   the registry `artifact_path` (an `s3://…` URI) at runtime. A model is not promoted until
   `upload_artifact(local_pkl, s3_uri)` has run **and** the registry points at that URI.
   These two halves (S3 binary + git-tracked registry/contract JSON) must move together.

2. **The contract and the model must agree on feature count, exactly.** Models score by
   **column position**. The sidecar `feature_columns_*.json` (the "contract") must list the
   *same* columns, in the *same* order, that the model was fit on. The trap:
   `build_imputation_pipeline()` appends two indicator columns
   (`has_starter_platoon_data`, `is_new_venue`) to the training matrix, so a model trained
   through that pipeline has **N+2** features. A contract written from the *pre-imputation*
   feature list is 2 short → `predict_today` feeds an N-wide matrix to an (N+2)-feature model
   → opaque `IndexError: index N is out of bounds`. (This was the Story 30.1 bug.)
   - The `predict_today.py` **CONTRACT-GUARD** now fails fast with a clear message if
     `len(contract) != model.n_features`. Do not bypass it — fix the contract.
   - The `run_*_search.py` trainers now write the **post-imputation** column list
     (`list(last_fold["X_train"].columns)`), so freshly trained contracts are correct by
     construction. Hand-patched or legacy contracts still need the check below.

---

## Pre-flight checklist

- [ ] Champion/challenger gate passed (PROMOTE or documented INCONCLUSIVE) — see Step 1b of
      [`model_deploy_runbook.md`](model_deploy_runbook.md). Honest 2026 OOS surface, not just CV.
- [ ] Evaluation / decision doc committed under `betting_ml/evaluation/`.
- [ ] You are in (or about to enter) a **no-prediction window** — see timing note below.
- [ ] You know which targets you are promoting. **Promote per-target**; do not assume all
      three move together (e.g. Story 30.1 promoted `home_win` + `run_differential`;
      `total_runs` stayed on the bet-paused `eb_enriched` lineage).

### Timing: promote in a no-prediction window

Promotion is **not atomic across S3 + git + redeploy**. If a scheduled `predict_today` run
fires while the registry (git) points at the new contract but S3 still has the old model
(or vice-versa), it will score a mismatched matrix. Do the S3 upload, registry edit, and
redeploy as one contiguous block **between** the day's prediction runs (the SLA is predictions
≥30 min before first pitch — promote after the slate locks or early-morning before ingestion).

---

## Step 1 — Verify the local artifact and contract agree (before anything leaves your machine)

Run this for **each target you are promoting**. It is the single check that would have caught
the 30.1 IndexError.

```bash
uv run python -c "
import json, joblib
TARGET='home_win'  # home_win | run_differential | total_runs
PKL='betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl'
CONTRACT='betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json'
m = joblib.load(PKL)
n_model = getattr(m,'n_features', None) or getattr(m,'n_features_in_', None)
raw = json.load(open(CONTRACT)); cols = raw['feature_cols'] if isinstance(raw,dict) else raw
print(f'{TARGET}: model={n_model}  contract={len(cols)}  MATCH={n_model==len(cols)}')
# For home_win (XGB) we can also assert exact name+order:
names = list(getattr(m,'feature_names_in_',[]) or [])
if names: print('  exact name+order match:', names==cols)
assert n_model==len(cols), 'CONTRACT/MODEL MISMATCH — do not promote'
print('  OK to promote')
"
```

If `MATCH=False`: the contract is wrong. If it is missing the two imputation indicators,
append them (`has_starter_platoon_data`, `is_new_venue`) to the end and bump `n_features`;
otherwise regenerate it from the post-imputation training matrix. **Never** edit the model to
match the contract.

---

## Step 2 — Upload the artifact(s) to S3

`upload_artifact(local_path, s3_uri)` — bucket is `baseball-betting-ml-artifacts`. Use the
**exact** `artifact_path` URI you will set in the registry (Step 3). This is idempotent;
re-running overwrites the key.

```bash
uv run python -c "
from betting_ml.utils.artifact_store import upload_artifact
# home_win
upload_artifact('betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl',
                's3://baseball-betting-ml-artifacts/home_win/xgb_classifier_tuned_2026.pkl')
# run_differential
upload_artifact('betting_ml/models/run_differential/ngboost_tuned_2026.pkl',
                's3://baseball-betting-ml-artifacts/run_differential/ngboost_tuned_2026.pkl')
print('uploaded')
"
```

> If you are reusing the same S3 key as the current champion (in-place model swap), first
> copy the old object aside so rollback is possible, or use a new versioned key and set
> `prev_artifact_path` in the registry to the old URI (preferred — see Step 3).

---

## Step 3 — Update `model_registry.yaml` (git-tracked half)

For each promoted target, edit its top-level block in `betting_ml/models/model_registry.yaml`:

1. Move the current `artifact_path` → `prev_artifact_path` (rollback pointer).
2. Set `artifact_path` to the new `s3://…` URI (must match Step 2 exactly).
3. Set `feature_columns_path` to the new contract JSON (git-tracked).
4. Update `cv_brier` / `cv_mae` / `ece_*` / `features` to the new metrics.
5. Set `deployed_date` **and** `promoted_at` to today.
6. **Reset the 28.3 kill-window** (only if this target has a conviction/magnitude monitor —
   `home_win` does): set `attribution_start` to today in the registry's monitoring block
   **and** update the matching `ATTRIBUTION_START` constant in the monitor script. A new
   champion invalidates the prior model's live-attribution sample.

### Kill-window reset touchpoints (home_win)

| Where | What to change |
|---|---|
| `model_registry.yaml` → `home_win` monitoring block | `attribution_start: '<today>'` |
| `scripts/ops/monitor_conviction_h2h.py` | `ATTRIBUTION_START = "<today>"` |
| `scripts/ops/monitor_magnitude_h2h.py` | `ATTRIBUTION_START = "<today>"` |

> `total_runs` is bet-paused on the `eb_enriched` lineage. Promoting a tuned-totals challenger
> is a **separate, gated** decision (beat NLL 2.8893 AND prior-naive Brier 0.248 on a rolling
> 60-game live window) and is a different artifact lineage — do not repoint it as a side effect.

---

## Step 3b — Record the champion lineage (Snowflake temporal registry)  `[Story 30.7]`

The YAML edit in Step 3 changes the *current* champion but does NOT record the **window** the
outgoing champion held. `baseball_data.betting_ml.model_registry` is the canonical temporal
lineage (promoted_date / deprecated_date / is_current); it is only correct if every promotion
calls `record_promotion`. Run it right after the registry edit, once per promoted target:

```
uv run python betting_ml/scripts/record_promotion.py \
  --target home_win --new-version v5 --model-name xgb_market_blind \
  --artifact-path s3://baseball-betting-ml-artifacts/home_win/<artifact>.pkl \
  --feature-columns-path betting_ml/models/home_win/<contract>.json \
  --features <post_pipeline_dim> --training-rows <n> --training-cutoff 2021+ \
  --cv-metric brier --cv-value <cv> --promoted-date <today> \
  --notes "<one-line rationale; note any correctness override>"
```

It closes the prior champion (`deprecated_date = today, is_current = FALSE`) and inserts the new
one (`is_current = TRUE`) in one transaction; idempotent on (target, version) so re-runs are
no-ops. Verify exactly one `is_current = TRUE` per target afterward.

---

## Step 4 — Local smoke test against dev

Run the real entrypoint end-to-end before committing. The CONTRACT-GUARD and FEATURE-ALIGN
checks both run here.

```bash
uv run python scripts/predict_today.py --date $(date +%Y-%m-%d) --no-log-snowflake
```

Confirm:
- No `[CONTRACT-GUARD]` or `[FEATURE-ALIGN] … ABSENT` errors.
- The `features=` line printed per target matches the promoted contract length.
- A full slate of picks renders (probabilities in (0,1), totals plausible).

`--no-log-snowflake` keeps it off the prod table; drop it (or point at `betting_ml_dev`) for a
dev write test.

---

## Step 5 — Commit the git-tracked half

The `.pkl` binaries live in **S3**, not git. The commit carries only the registry, the
contract JSONs, monitor-script edits, trainer/code changes, and eval docs.

```bash
git add betting_ml/models/model_registry.yaml \
        betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json \
        betting_ml/models/run_differential/feature_columns_ngboost_tuned_2026.json \
        scripts/ops/monitor_conviction_h2h.py \
        scripts/ops/monitor_magnitude_h2h.py \
        betting_ml/evaluation/<eval_doc>.md
# (user handles the actual commit + push — see repo policy)
```

> **Repo policy:** the user runs all `git commit` / `git push`. Stage and present the command;
> do not commit on their behalf.

Confirm the new `.pkl` is **gitignored** (it should be — artifacts are S3-tracked):
`git status --short betting_ml/models/` should NOT list the new pkl.

---

## Step 6 — Redeploy prod & post-verify

After the branch merges to `main`, redeploy the prod runtime (Lambda/Dagster image) so it
picks up the new registry. Then on the next live run confirm:

- `daily_model_predictions` rows show the new `model_version` and a fresh `inserted_at`.
- The per-target `features=` log matches the promoted contract.
- For `home_win`, the conviction/magnitude monitors show the reset `attribution_start`
  (the kill-window sample restarts from 0).

---

## Rollback

S3 + git both retain the prior state, so rollback is a pointer swap — no retrain:

1. In `model_registry.yaml`, swap `artifact_path` ↔ `prev_artifact_path` and restore the
   prior `feature_columns_path`.
2. Restore the prior `attribution_start` in the registry + both monitor scripts (if it was reset).
3. Smoke test (Step 4), commit, push, redeploy.

The old S3 object remains at `prev_artifact_path`; if you overwrote a key in place in Step 2
without setting `prev_artifact_path`, you must re-upload the old local `.pkl` first.

---

## Quick reference — what moves where

| Thing | Lives in | Promoted by |
|---|---|---|
| Model binary (`.pkl`) | **S3** (`baseball-betting-ml-artifacts`) | `upload_artifact(...)` (Step 2) |
| `artifact_path` (S3 URI pointer) | git (`model_registry.yaml`) | edit + commit (Step 3) |
| Feature contract (`feature_columns_*.json`) | git | edit + commit (Step 3) |
| Kill-window `attribution_start` | git (registry **+** 2 monitor scripts) | edit + commit (Step 3) |
| Prod runtime | Lambda/Dagster image | redeploy (Step 6) |

**The one invariant:** `len(contract) == model.n_features`, enforced by the predict_today
CONTRACT-GUARD. If it ever fires, the contract is wrong — never the model.
