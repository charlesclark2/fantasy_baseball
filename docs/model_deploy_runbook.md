# Model Deploy Runbook

**Owner:** Charles Clark  
**Last updated:** 2026-05-04 (Card 8.H2)  
**Applies to:** All three production targets — `home_win`, `total_runs`, `run_differential`

---

## Overview

This runbook governs every production model deploy. Follow all seven steps in order. Do not skip steps — the smoke test and registry update are both required before tagging. Rollback instructions are at the end.

All production artifacts are listed in `betting_ml/models/model_registry.yaml`. Each deploy updates that file and is captured in a git tag of the form `model/{target}/v{N}`.

---

## Step 1 — Train and evaluate

Run the appropriate training script and confirm the new artifact meets the acceptance bar:

| Target | Training script | Acceptance bar |
|---|---|---|
| `home_win` | `betting_ml/scripts/train_elasticnet_prod.py` | CV Brier ≤ current registry `cv_brier` + 0.002 |
| `total_runs` | `betting_ml/scripts/retrain_models.py` (Card 7.D) | CV MAE ≤ current registry `cv_mae` × 1.01 |
| `run_differential` | `betting_ml/scripts/retrain_models.py` (Card 7.D) | CV MAE ≤ current registry `cv_mae` × 1.01 |

The training script prints a summary of CV metrics. Record these — they go into the registry and the evaluation doc in step 3.

Write an evaluation doc in `betting_ml/evaluation/` summarising the results before proceeding. CI will block the merge (step 6) if no evaluation doc exists for the deploy.

---

## Step 2 — Write artifact

The training script serializes the artifact automatically. Confirm it landed at the expected path:

```
betting_ml/models/{target}/{model_name}_{year}.pkl
```

Example: `betting_ml/models/home_win/elasticnet_2026.pkl`

If the file is new (not previously tracked by git), add a negation exception to `.gitignore`:

```
# In .gitignore — add an exception per production artifact deployed (8.H2 protocol)
!betting_ml/models/home_win/elasticnet_2026.pkl
```

Do not remove the old artifact. It becomes the `rollback_artifact_path` in step 3.

---

## Step 3 — Update model_registry.yaml

Edit `betting_ml/models/model_registry.yaml` for the target being deployed:

1. Move the current `artifact_path` value to `rollback_artifact_path`
2. Set `artifact_path` to the new pkl path
3. Bump `model_version` (e.g. `v0` → `v1`)
4. Set `deployed_date` to today's date
5. Update `cv_brier` / `cv_mae`, `ece_raw`, `features`, `training_rows`, `training_cutoff`, `notes`

Example diff for `home_win`:

```yaml
home_win:
  model_name: elasticnet
  model_version: v1          # bumped from v0
  cv_brier: 0.2425           # new CV result
  ece_raw: 0.0202
  features: 453
  training_rows: 10256
  training_cutoff: "2021+"
  artifact_path: betting_ml/models/home_win/elasticnet_2026.pkl   # new
  rollback_artifact_path: betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl  # was artifact_path
  deployed_date: "2026-05-04"
  selected_at: "2026-05-04T00:00:00Z"
  notes: "..."
```

---

## Step 4 — Smoke test

Run the smoke test locally before committing anything:

```bash
uv run python -c "
import numpy as np
from betting_ml.utils.model_io import load_model
m = load_model('home_win')   # replace 'home_win' with target
p = m.predict_proba(np.zeros((1, m.n_features_in_)))[0, 1]
assert 0.0 < p < 1.0, f'Bad probability: {p}'
print(f'OK — p={p:.4f}, n_features={m.n_features_in_}')
"
```

**Stop here if the smoke test fails.** Do not commit a broken artifact.

---

## Step 5 — Commit and tag

Stage only the deploy-related files:

```bash
git add .gitignore                                        # if new negation exception added
git add betting_ml/models/{target}/{new_artifact}.pkl
git add betting_ml/models/model_registry.yaml
git add betting_ml/scripts/{training_script}.py           # if updated
git add betting_ml/evaluation/{eval_doc}.md
git commit -m "Deploy {model_name} as {target} v{N} (Card 7.D)"
```

Tag the commit immediately after:

```bash
git tag model/{target}/v{N}
```

Example: `git tag model/home_win/v3`

Tags are how we recover a specific artifact + registry state. Never skip the tag.

---

## Step 6 — Open PR and merge

Push the branch and open a PR against `main`:

```bash
git push
git push origin model/{target}/v{N}   # push the tag explicitly
```

**CI must pass before merge.** The `model-smoke-test` job in `ci.yml` reloads the artifact and asserts a valid probability on every PR. If it fails, do not merge.

Reviewer checklist before approving:
- [ ] Evaluation doc present in `betting_ml/evaluation/`
- [ ] `model_registry.yaml` has both `artifact_path` and `rollback_artifact_path`
- [ ] CV metrics are within acceptance bar (Step 1)
- [ ] `deployed_date` and `model_version` are updated
- [ ] Git tag exists and points to the deploy commit

---

## Step 7 — Post-deploy verification

After the PR merges:

1. Confirm the tag is on the merge commit (or the deploy commit if you used a merge commit):
   ```bash
   git log --oneline model/{target}/v{N}
   ```

2. Verify `predict_today.py` is loading the correct model version by checking `MODEL_VERSION` matches the registry `model_version`.

3. On the next prediction run, confirm `daily_model_predictions` rows show the new `model_version` value.

---

## Rollback procedure

If a deployed model is producing bad predictions, swap `artifact_path` and `rollback_artifact_path` in `model_registry.yaml`, commit, push, and retag:

```bash
# 1. Edit model_registry.yaml — swap artifact_path ↔ rollback_artifact_path, decrement model_version
# 2. Commit
git commit -m "Rollback {target} to v{N-1} (revert Card 7.D)"

# 3. Retag (force-update the current version tag to the rollback commit)
git tag -f model/{target}/v{N} HEAD

# 4. Push
git push
git push origin model/{target}/v{N} --force
```

The old artifact is always preserved on disk and in git — rollback does not require a retrain.

---

## Registry version history

| Tag | Target | Model | Deployed | CV metric |
|---|---|---|---|---|
| `model/home_win/v2` | `home_win` | elasticnet (Pipeline) | 2026-05-04 | Brier 0.2425, ECE 0.0202 |
| `model/home_win/v1` | `home_win` | xgb_classifier_tuned + Platt | pre-7.MB | Brier 0.2439 |
