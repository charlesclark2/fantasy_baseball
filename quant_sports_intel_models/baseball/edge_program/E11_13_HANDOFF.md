# E11.13 — Python test-suite speedup + structure: operator handoff

_Session 2026-06-25 · Infra track · SPEED + STRUCTURE only (no coverage cut). Kept entirely separate from the E5.2 model change-set — see the two distinct `git add` lists below._

---

## TL;DR

The suite was ~4.5 min serial and that wall-time taxed both CI and every story's pre-handoff gate. Profiling showed the cost is **absurdly concentrated**: **5 Monte-Carlo calibration tests = 251s of the 268s total (94%)**; the other 611 tests run in ~17s combined. Fix = **(1) mark those 5 `slow`, (2) parallelize with `pytest-xdist -n auto`, (3) split CI into a fast gate (`-m "not slow"`) + a slow gate (`-m slow`)**. No test removed, no guard dropped, no IO un-mocked. Effective coverage is unchanged: full parallel run = **616 passed, 1 skipped** (identical to before).

**Headline:** the per-push **fast gate dropped from ~268s → ~15s (17×)**. The slow MC guards still run (separate required CI job, parallelized ~96s).

---

## 1. Profile (`uv run pytest --durations=50`) — the offenders

| Time | Test |
|------|------|
| 82.4s | `test_totals_distribution.py::TestCalibration::test_too_tight_dispersion_fails_flatness` |
| 79.3s | `test_totals_distribution.py::TestCalibration::test_pit_uniform_when_correctly_specified` |
| 72.5s | `test_totals_distribution.py::TestCalibration::test_calib_80_at_or_above_floor_when_calibrated` |
| 8.6s | `test_prop_pricing.py::TestStrikeoutPriceCalibration::test_overconfident_price_fails_flatness` |
| 8.6s | `test_prop_pricing.py::TestStrikeoutPriceCalibration::test_correctly_specified_price_is_pit_flat` |
| <1.5s | _everything else (611 tests, ~17s combined)_ |

All five are **6k-game × 2–4k-draw Monte-Carlo PIT / coverage-floor guards** (E2.3 totals dispersion calibration + E5.2 strikeout calibration). They are genuine regression guards with tight numeric tolerances (`is_flat`, `0.80 ≤ calib_80 ≤ 0.90`). **They were NOT shrunk** — cutting their sample sizes would loosen the very tolerances they pin and risk flaky CI, which is worse than slowness. They were marked `slow` and parallelized instead.

## 2. What changed (mechanism)

- **`pytest-xdist` added to `[project] dependencies`** (NOT a dev group — CI runs `uv sync --no-dev-packages || uv sync`, so a dev-group dep would be dropped and CI would break, same reason `pytest` itself is a main dep). Run with `-n auto`. The 3 ~75s totals tests load-balance onto separate workers and overlap.
- **`slow` marker** registered in `pyproject.toml` (`markers = [...]`, enforced by `--strict-markers` so a typo'd/unregistered marker is a hard error). 5 tests marked `@pytest.mark.slow`. An `integration` marker is also registered but **currently unused** (reserved — all external IO in the suite is already mocked; see §4).
- **`addopts = "--durations=10 --strict-markers"`** in `pyproject.toml`. `-v` dropped from CI (quieter logs); `--durations=10` kept for ongoing slow-test visibility. `-n auto` is **not** in addopts — it's passed per-invocation by CI / the local gate, so a single-file targeted run doesn't pay worker-spawn overhead.
- **CI split** (`.github/workflows/ci.yml`): the old single `unit-tests` job (`pytest -v --tb=short`) became two jobs:
  - **`Unit Tests (fast gate)`** → `uv run pytest -m "not slow" -n auto --tb=short` (+ the existing `predict_today` py_compile and MERGE-pattern guard steps).
  - **`Unit Tests (slow — Monte-Carlo calibration)`** → `uv run pytest -m slow -n auto --tb=short`.
  - **Both are required for merge** (update branch protection to require the new `slow-tests` check alongside the existing `unit-tests`).

## 3. Before / after wall-time (local, this machine)

| Run | Before (serial) | After |
|-----|-----------------|-------|
| Full suite | **267.9s** | 180–199s parallel (`-n auto`) |
| **Fast gate** (`-m "not slow" -n auto`) — the per-push handoff gate | — | **15.4s** ✅ |
| Slow gate (`-m slow -n auto`) | — | 96.6s |

The developer-/CI-facing number is the **fast gate: 15.4s** (the slow job runs on its own CI runner and never blocks it). On CI's runner the absolute numbers differ but the ratio holds.

## 4. External IO — already mocked (no work needed, confirmed)

The addendum flagged "convert tests hitting Snowflake/S3/network to mocks." **Audited — already done.** Every IO-touching test already mocks: `test_stuff_plus_deleak` / `test_predict_today_backfill_batch` (`mock.patch.object(..., get_snowflake_connection / _connect)`), `test_invalidate_permanent_cache` (`MagicMock` cursor), `test_best_price_e9_11` (`sys.modules["snowflake.connector"] = MagicMock()`), `test_savant_ingestion` (mock conn), and the text-as-source pattern (`test_book_odds_leakage_guard.py` reads `write_serving_store.py` and asserts on SQL structure — zero IO). The 5 real offenders are **pure NumPy Monte-Carlo compute**, not IO — so IO-mocking was not the lever here. Pattern documented in CLAUDE.md for future tests.

## 5. xdist-safety (`-n auto` run 3×)

Ran the **full suite under `-n auto` three times** → all green, no order/parallel flakes:
- Run 1: 616 passed, 1 skipped
- Run 2: 616 passed, 1 skipped
- Run 3: 616 passed, 1 skipped

Specifically checked the addendum's flagged risk — the op-diet / narrative **day-keyed `/tmp` state files** (`/tmp/narrative_pick_state_{date}.json`): the tests already `monkeypatch` `_pick_state_path` to a per-test `tmp_path`, so there's no cross-worker collision. `test_dbt_runner.py` loads pipeline modules via `importlib.spec_from_file_location` + `patch.object` (no shared global state). No xdist-unsafe pattern found.

## 6. Anti-regression (suite can't silently re-bloat)

- `--strict-markers` → an unregistered/typo'd marker is an error, not a silent no-op.
- **CLAUDE.md CI-gate section updated** with the fast-gate command (`uv run pytest -m "not slow" -n auto`), the slow-gate command, "both required for merge," and the **>5s ⇒ `@pytest.mark.slow`** rule so new heavy tests land in the slow job, not the fast gate.

## 7. Coverage confirmation

**No test removed. No guard dropped. No (removed, kept) twin pairs — nothing was deleted.** The only changes are 5 `@pytest.mark.slow` decorators, a marker/addopts registration, a new main dep, a CI job split, and docs. Test count is identical (616 passed + 1 skipped, before and after). The INC-13 / leakage-guard / side-attribution / op-diet / contract-guard / bakeoff_strikeouts / prop_pricing guards all still run — just redistributed across two CI jobs.

---

## ⏭️ Operator handoff

### CI-gate result (this session)
- **Python fast gate** `uv run pytest -m "not slow" -n auto` → **611 passed, 1 skipped (15.4s)** ✅
- **Python slow gate** `uv run pytest -m slow -n auto` → **5 passed (96.6s)** ✅
- **Full suite `-n auto` ×3** → 616 passed, 1 skipped each ✅ (xdist-safe)
- dbt: untouched by this change-set (no dbt files modified).

### `git add` — E11.13 (test-infra) ONLY — keep separate from the E5.2 list
```
git add pyproject.toml
git add uv.lock
git add .github/workflows/ci.yml
git add betting_ml/tests/test_totals_distribution.py
git add betting_ml/tests/test_prop_pricing.py
git add CLAUDE.md
git add conftest.py
git add quant_sports_intel_models/baseball/edge_program/E11_13_HANDOFF.md
```
- `conftest.py` is the snowflake-namespace-shadow collection fix (pre-imports the real `snowflake.connector.pandas_tools` so the partial `.lambda_build/package/snowflake` copy can't break collection under any order). It's pure test-collection infra (no model logic), so it belongs with E11.13, not E5.2.
- `test_prop_pricing.py` and `test_totals_distribution.py` appear here **only** for the `@pytest.mark.slow` decorators (E11.13). The E5.2 model logic in `test_prop_pricing.py` was committed/listed under the E5.2 handoff — if both land in one commit that's fine, but the marker edits are the E11.13 delta.

### Post-merge action (operator)
- **Branch protection:** add the new **`Unit Tests (slow — Monte-Carlo calibration)`** check to the required set (alongside `Unit Tests (fast gate)`), so the slow MC guards still gate merges.

### Excluded from git (gitignored / artifacts) — do NOT commit
- none new — `pytest-xdist` is captured in `pyproject.toml` + `uv.lock` only.
