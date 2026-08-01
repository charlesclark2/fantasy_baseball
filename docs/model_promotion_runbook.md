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

> **TD3 — mechanically-guarded promotion touchpoints (read first).** E7.9 found
> `mart_clv_labeled_games.sql` hardcoded to a champion `model_version` — promote a new champion
> and the app's model-vs-market scorecard silently blanks (no error). This runbook's steps rely on
> a human remembering every place a promotion touches; one miss zeroes a user-facing panel or goes
> silently dark. TD3 enumerated the whole surface via a repo-wide grep and added a **fast-gate test
> per item** (mirroring the CLV pin) that reddens BEFORE prod breaks, instead of after:
> `betting_ml/tests/test_e7_9_train_serve_consistency.py::test_clv_scorecard_champion_pin_matches_the_registry`
> and `betting_ml/tests/test_td3_promotion_safety.py` (7 more guards — see its module docstring for
> the full checklist + what was investigated and found NOT to need one). **Run
> `uv run pytest betting_ml/tests/test_td3_promotion_safety.py betting_ml/tests/test_e7_9_train_serve_consistency.py`
> after any promotion** (or just the fast gate — both files are in it) — every touchpoint marked
> ⚙️GUARDED below is mechanically enforced by one of these tests; anything else still needs a human.

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
7. **If you promoted `home_win`** (or its `pre_lineup_model_version`): the served
   `daily_model_predictions.model_version` stamp is derived SOLELY from
   `registry["home_win"]["model_version"]` (`predict_today.py` / `backfill_predictions.py` — TD3
   traced this; every downstream pin below keys off home_win, not the target you may think of as
   "the one that moved"). Update `mart_clv_labeled_games.sql`'s `model_version = '<vN>'` pin and
   `pipeline/sensors/model_health_alert_sensor.py`'s `_MODEL_VERSION` + `_GATE_FLOOR_DATE` to match.

### Kill-window / champion-pin reset touchpoints (home_win)  ⚙️ mechanically guarded — see the note at the top of this doc

| Where | What to change | Guard |
|---|---|---|
| `model_registry.yaml` → `home_win.kill_criterion` | `attribution_start: '<today>'` | ⚙️ `test_magnitude_monitor_attribution_start_matches_the_registry` |
| `scripts/ops/monitor_magnitude_h2h.py` | `ATTRIBUTION_START = "<today>"` | ⚙️ same test |
| `model_registry.yaml` → `home_win.conviction_kill_criterion` | `attribution_start: '<today>'` | ⚙️ `test_conviction_monitor_attribution_start_matches_the_registry` |
| `scripts/ops/monitor_conviction_h2h.py` | `ATTRIBUTION_START = "<today>"` | ⚙️ same test |
| `dbt/models/mart/mart_clv_labeled_games.sql` | `model_version = '<vN>'` (home_win's, not the promoted target's — see item 7 above) | ⚙️ `test_clv_scorecard_champion_pin_matches_the_registry` |
| `pipeline/sensors/model_health_alert_sensor.py` | `_MODEL_VERSION = "<vN>"` | ⚙️ `test_model_health_sensor_pinned_version_matches_the_registry` |
| `pipeline/sensors/model_health_alert_sensor.py` | `_GATE_FLOOR_DATE = date(<today>)` | ⚙️ `test_model_health_sensor_gate_floor_matches_the_kill_window_reset` |

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

### Contract deploy-parity check (catches "contract not committed")  `[added 2026-06-12 after a prod CONTRACT-GUARD outage]`

The local smoke test only proves the **working-tree** contract matches the model. Prod loads the
model binary from **S3** but the contract JSON from the **deployed git image** — so if the new
contract is edited locally but **left out of the deploy commit**, the working-tree smoke test passes
yet prod scores a new model against the OLD committed contract → `[CONTRACT-GUARD]` failure in
`lineup_predict` (this is exactly what happened on 2026-06-12: the v5 registry + S3 models deployed
but the 211/169 contract JSONs were never committed, so `HEAD` still had 376).

Run this parity check for every promoted target. It compares, per target, the registry's `features`
count against the contract length in your **working tree** AND in **`HEAD`** (what will actually
deploy). They must all agree:

```bash
uv run python - <<'PY'
import json, subprocess, yaml
reg = yaml.safe_load(open("betting_ml/models/model_registry.yaml"))
def clen(ref, path):                       # ref=None → working tree; else git show <ref>:<path>
    raw = open(path).read() if ref is None else subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True).stdout
    d = json.loads(raw); c = d["feature_cols"] if isinstance(d, dict) else d
    return len(c)
bad = False
for tgt in ("home_win", "run_differential", "total_runs"):
    e = reg[tgt]; path = e["feature_columns_path"]; want = e.get("features")
    wt = clen(None, path)
    try:    head = clen("HEAD", path)
    except Exception: head = None
    ok = (wt == want == head)
    bad |= not ok
    print(f"{tgt:16s} registry.features={want}  working_tree={wt}  HEAD={head}  "
          f"{'OK' if ok else '*** MISMATCH — do NOT deploy ***'}")
print("\nALL GOOD" if not bad else
      "\nFIX: a MISMATCH where working_tree != HEAD means the contract change is NOT in your deploy "
      "commit — `git add` the contract JSON, recommit, and re-run this check before Step 6.")
PY
```

- **`working_tree != HEAD`** ⇒ the new contract is uncommitted; it will NOT deploy. Stage + commit it
  (Step 5), then re-run this check — `HEAD` must update to match.
- **`registry.features != working_tree`** ⇒ the YAML and the contract disagree (e.g. a pre-imputation
  contract missing the imputation indicators); regenerate the contract before promoting.

**Re-run this AFTER Step 5 (commit)** — `HEAD` only reflects the committed contract once you've committed.
Do not redeploy (Step 6) until this prints `ALL GOOD`.

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

## Step 6b — Purge permanent caches (E9.28)  `[run immediately after Step 6 on every promotion]`

⚙️ The endpoint below is pinned to this doc by `test_permanent_cache_invalidate_endpoint_matches_the_runbook`
(TD3) — if the route is ever renamed, that test (not a live 404 an operator hits mid-promotion)
is what catches it.

Champion promotions leave stale **permanent** blobs in both stores — the `is_permanent=TRUE`
`picks/game/%` rows in Railway PG and the `api-cache/permanent/picks/game/` objects in S3.
Day-scoped invalidations (`/admin/cache/invalidate`) never touch these, so without this step
users see the old model's picks on Final-game detail pages until the blob TTL expires.

Call the admin endpoint once (requires admin auth):

```bash
curl -X POST https://<api-base>/admin/cache/invalidate-permanent \
  -H "Authorization: Bearer <admin-token>"
```

Expected response:
```json
{
  "status": "ok",
  "s3_objects_deleted": <N>,
  "pg_rows_deleted": <M>,
  "message": "Permanent picks/game cache cleared: N S3 objects, M PG rows. ..."
}
```

The call is **idempotent** — safe to re-run if uncertain. Stale blobs regen lazily on the
next page load (no warm-up needed). Scope is targeted: only `picks/game/*` permanent entries
are deleted; other permanent blobs (e.g. non-pick data) are untouched.

---

## Rollback

S3 + git both retain the prior state, so rollback is a pointer swap — no retrain:

1. In `model_registry.yaml`, swap `artifact_path` ↔ `prev_artifact_path` and restore the
   prior `feature_columns_path`.
2. Restore the prior `attribution_start` in the registry + both monitor scripts (if it was reset),
   and the prior `model_version` in `mart_clv_labeled_games.sql` + the model-health sensor's
   `_MODEL_VERSION` / `_GATE_FLOOR_DATE` if home_win was the rolled-back target (see the
   touchpoints table above) — ⚙️ the same guards that catch a forward promotion catch a rollback
   that skips these.
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
