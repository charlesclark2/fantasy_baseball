"""Guards for TD3 — Champion-promotion safety audit (from E7.9).

E7.9 found `mart_clv_labeled_games.sql` HARDCODED to `model_version='v6'`: promote a new champion
and the app's model-vs-market scorecard silently blanks (no error, no HALT — the E9.26b silent-empty
class). That one mart is now pinned by `test_clv_scorecard_champion_pin_matches_the_registry` in
`test_e7_9_train_serve_consistency.py`. This file extends the same shape — read the hardcoded
literal out of the SOURCE TEXT, compare it to the registry's champion value, go red on drift — to
every OTHER place a champion promotion can leave something silently stale, found by grepping the
whole repo for the same hardcode class (see the story's Step 0).

Enumerated promotion-change surface (checklist; each item below is one test):
  1. `mart_clv_labeled_games.sql` model_version pin           → test_e7_9_train_serve_consistency.py
     (guarded pre-existing; TD3 also fixed its source field — see that test's docstring)
  2. `predict_today.py` / `backfill_predictions.py` both derive the served `model_version` stamp
     from `home_win` specifically (the mechanism guard #1 depends on)   → below
  3. `pipeline/sensors/model_health_alert_sensor.py::_MODEL_VERSION`    → below
  4. `pipeline/sensors/model_health_alert_sensor.py::_GATE_FLOOR_DATE`  → below
  5. `home_win.kill_criterion.attribution_start` ↔
     `scripts/ops/monitor_magnitude_h2h.py::ATTRIBUTION_START`          → below
  6. `home_win.conviction_kill_criterion.attribution_start` ↔
     `scripts/ops/monitor_conviction_h2h.py::ATTRIBUTION_START`         → below
  7. E9.28 permanent-cache invalidation endpoint referenced by the runbook → below
  8. The runbook documents every guard above (closes the loop: a promotion checklist that
     doesn't point at its own guards is exactly the kind of thing that rots)  → below

Investigated and found NOT to need a guard (documented so the next audit doesn't re-derive this):
  - `sub_model_registry.yaml` (edge sub-model champions — bullpen/run_env/offense/etc.) uses a
    DIFFERENT, self-safe pattern: `feature_pregame_sub_model_signals.sql` materializes one column
    PER historical version (`run_env_mu_v4`, `run_env_signal_v3`, ...) and never overwrites/retires
    a column on a sub-model promotion, so there is no "silently zeroes" failure mode. Consumers that
    read the registry (e.g. `betting_ml/utils/probability_layer.py`) already load it dynamically —
    no hardcoded version string found there.
  - `len(contract) == model.n_features` (Steps 1 and the deploy-parity check in the runbook) is
    already mechanically enforced AT RUNTIME by `predict_today.py`'s CONTRACT-GUARD, which HALTs
    (loud failure) rather than silently degrading — the failure mode this audit targets doesn't
    apply, so no new fast-gate guard was added on top of it.
  - `scripts/ops/finalize_v6_champion.py` / `scripts/ops/reconcile_v6_ledger.py` hardcode "v6" by
    NAME and DESIGN — they are one-shot promotion-execution scripts for the E13.11 event. A future
    promotion writes a new same-shaped script (the convention is to name it after the target
    version), it does not reuse/mutate this one, so there is nothing here to pin against a moving
    registry value.

Fast-gate safe: pure source-text inspection (regex over file contents) — no Snowflake/S3/pipeline
import, matching the E7.9 CLV-pin test's shape and the repo's "fast-gate tests must not import
`pipeline`" rule (`test_fast_gate_hygiene.py`).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
SENSOR_PATH = PROJECT_ROOT / "pipeline" / "sensors" / "model_health_alert_sensor.py"
MAGNITUDE_MONITOR_PATH = PROJECT_ROOT / "scripts" / "ops" / "monitor_magnitude_h2h.py"
CONVICTION_MONITOR_PATH = PROJECT_ROOT / "scripts" / "ops" / "monitor_conviction_h2h.py"
PREDICT_TODAY_PATH = PROJECT_ROOT / "scripts" / "predict_today.py"
BACKFILL_PATH = PROJECT_ROOT / "betting_ml" / "scripts" / "backfill_predictions.py"
ADMIN_ROUTER_PATH = PROJECT_ROOT / "app" / "backend" / "routers" / "admin.py"
RUNBOOK_PATH = PROJECT_ROOT / "docs" / "model_promotion_runbook.md"


def _registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text())


# ── #2: the mechanism the CLV pin (and every model_version-stamp guard) depends on ────────────

def test_predict_today_derives_model_version_from_home_win():
    """`predict_today.py` stamps ONE `model_version` per prediction row, covering ALL THREE
    targets, derived solely from `registry["home_win"]["model_version"]` (or its pre_lineup
    variant). If this derivation is ever repointed at a different registry key, every guard that
    pins a downstream consumer to "the home_win champion" (the CLV mart pin, the sensor pins below)
    silently stops meaning what it says."""
    src = PREDICT_TODAY_PATH.read_text()
    assert '_registry["home_win"]["model_version"]' in src, (
        "predict_today.py no longer derives MODEL_VERSION from registry['home_win']['model_version'] "
        "— every guard pinned to 'the home_win champion drives the served model_version stamp' "
        "(the CLV mart pin, the model-health sensor pins) needs re-deriving against the new source."
    )


def test_backfill_predictions_derives_model_version_from_home_win():
    """Same invariant as above, for the historical-backfill writer — it must stamp the SAME
    `model_version` convention as the live path or a re-score after a promotion tags backfilled
    rows inconsistently with live ones."""
    src = BACKFILL_PATH.read_text()
    assert 'registry["home_win"]["model_version"]' in src, (
        "backfill_predictions.py no longer derives model_version from registry['home_win']"
        "['model_version'] — it must match predict_today.py's live-path derivation exactly."
    )


# ── #3/#4: the A2.6 model-health sensor's champion + era pins ─────────────────────────────────

def test_model_health_sensor_pinned_version_matches_the_registry():
    """`model_health_alert_sensor.py` filters its rolling live-skill window to `_MODEL_VERSION`
    so mixed-model noise from a prior champion doesn't pollute the measured spread/corr. Stale
    after a home_win promotion, this does NOT raise — the window finds zero rows for the new
    champion, `evaluate()` reports INSUFFICIENT, and the sensor SkipReasons forever. The A2.6
    regression backstop goes silently dark exactly when a fresh champion needs it most."""
    src = SENSOR_PATH.read_text()
    m = re.search(r'_MODEL_VERSION\s*=\s*"(v\d+)"', src)
    assert m, "model_health_alert_sensor.py: could not find `_MODEL_VERSION = \"vN\"` to pin"
    champion = _registry()["home_win"]["model_version"]
    assert m.group(1) == champion, (
        f"model_health_alert_sensor._MODEL_VERSION={m.group(1)!r} != registry home_win champion "
        f"{champion!r}. Update _MODEL_VERSION (and _GATE_FLOOR_DATE — see the sibling test) in the "
        f"SAME PR as the promotion, or the A2.6 health gate silently stops measuring anything."
    )


def test_model_health_sensor_gate_floor_matches_the_kill_window_reset():
    """`_GATE_FLOOR_DATE` exists so the rolling window never mixes pre-promotion predictions
    (a different, already-diagnosed root cause) with the currently-pinned champion's predictions.
    It must move in lockstep with the champion pin above AND with the registry's own promotion-day
    marker (`kill_criterion.attribution_start`, reset by runbook Step 3 item 6) — otherwise a new
    champion promotion leaves the floor dated to the PRIOR promotion, silently widening the window
    back into stale-era predictions."""
    src = SENSOR_PATH.read_text()
    m = re.search(r"_GATE_FLOOR_DATE\s*=\s*date\((\d+),\s*(\d+),\s*(\d+)\)", src)
    assert m, "model_health_alert_sensor.py: could not find `_GATE_FLOOR_DATE = date(...)` to pin"
    floor_iso = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    attribution_start = str(_registry()["home_win"]["kill_criterion"]["attribution_start"])
    assert floor_iso == attribution_start, (
        f"model_health_alert_sensor._GATE_FLOOR_DATE={floor_iso} != registry "
        f"home_win.kill_criterion.attribution_start={attribution_start}. A promotion that resets "
        "the kill-window (runbook Step 3 item 6) must reset this floor in the same PR."
    )


# ── #5/#6: the 28.3 / 28.6b kill-window attribution_start dual-storage ────────────────────────

def test_magnitude_monitor_attribution_start_matches_the_registry():
    """The runbook's 'Kill-window reset touchpoints' table names this file as a required edit
    alongside the registry, but nothing previously enforced it mechanically — a promotion could
    reset the registry's `attribution_start` and forget this constant, silently mixing pre/post
    -promotion bets in the same 28.3 kill-window count (corrupting the CONFIRM/KILL signal)."""
    src = MAGNITUDE_MONITOR_PATH.read_text()
    m = re.search(r'^ATTRIBUTION_START\s*=\s*"([\d-]+)"', src, re.MULTILINE)
    assert m, "monitor_magnitude_h2h.py: could not find `ATTRIBUTION_START = \"...\"` to pin"
    attribution_start = str(_registry()["home_win"]["kill_criterion"]["attribution_start"])
    assert m.group(1) == attribution_start, (
        f"monitor_magnitude_h2h.ATTRIBUTION_START={m.group(1)!r} != registry "
        f"home_win.kill_criterion.attribution_start={attribution_start!r}. Update both in the same "
        "PR (runbook Step 3 item 6) or the 28.3 kill-window mixes bets across two champion eras."
    )


def test_conviction_monitor_attribution_start_matches_the_registry():
    """Same invariant as the magnitude monitor, for the 28.6b conviction kill-window — it mixes
    the classifier AND run_diff sub-models, so it must reset whenever EITHER is re-promoted."""
    src = CONVICTION_MONITOR_PATH.read_text()
    m = re.search(r'^ATTRIBUTION_START\s*=\s*"([\d-]+)"', src, re.MULTILINE)
    assert m, "monitor_conviction_h2h.py: could not find `ATTRIBUTION_START = \"...\"` to pin"
    attribution_start = str(_registry()["home_win"]["conviction_kill_criterion"]["attribution_start"])
    assert m.group(1) == attribution_start, (
        f"monitor_conviction_h2h.ATTRIBUTION_START={m.group(1)!r} != registry "
        f"home_win.conviction_kill_criterion.attribution_start={attribution_start!r}. Update both "
        "in the same PR or the 28.6b kill-window mixes bets across two champion eras."
    )


# ── #7: E9.28 permanent-cache invalidation (runbook Step 6b) ──────────────────────────────────

def test_permanent_cache_invalidate_endpoint_matches_the_runbook():
    """Step 6b of the runbook is a manual POST to `/admin/cache/invalidate-permanent`, run right
    after every promotion so stale Final-game picks don't linger in the permanent cache (E9.28).
    There's no registry value to drift here — the risk is the ENDPOINT getting renamed/removed
    without the runbook (a copy-pasteable curl command) being updated to match, which silently
    turns Step 6b into a 404 the next time an operator follows it."""
    admin_src = ADMIN_ROUTER_PATH.read_text()
    assert '@router.post("/cache/invalidate-permanent")' in admin_src, (
        "admin.py no longer defines POST /cache/invalidate-permanent — update the runbook's "
        "Step 6b curl command to match the actual route, or restore this route."
    )
    runbook_src = RUNBOOK_PATH.read_text()
    assert "/admin/cache/invalidate-permanent" in runbook_src, (
        "model_promotion_runbook.md no longer documents Step 6b's cache-invalidation endpoint."
    )


# ── #8: the runbook must point at every guard above (close the loop) ──────────────────────────

def test_runbook_references_the_td3_guards():
    """The story's AC is 'runbook updated to reference the guards' — make that mechanical too, so
    a future edit that strips the reference (not just the guard itself) goes red."""
    runbook_src = RUNBOOK_PATH.read_text()
    for needle in (
        "test_clv_scorecard_champion_pin_matches_the_registry",
        "test_td3_promotion_safety.py",
    ):
        assert needle in runbook_src, (
            f"model_promotion_runbook.md no longer references {needle!r} — the promotion checklist "
            "must point at the guard that enforces each item."
        )
