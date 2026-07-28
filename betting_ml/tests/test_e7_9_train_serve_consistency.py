"""Guards for MLB Edge-E7.9 (train/serve consistency: MiLB-MLE backfill + eb_gb_pct).

Fast-gate safe: imports only `betting_ml` + inspects source. Nothing here touches Snowflake, S3,
`pipeline`, or a model fit — the heavy arms are exercised by the operator's real run, and the
runtime-gate rule (CI-green is not sufficient) applies to this story like any other.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from betting_ml.scripts import e7_9_train_serve_consistency as e79

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT = PROJECT_ROOT / "dbt"


# ── the eb_gb_pct join: the whole point of the story ──────────────────────────────────────────

def test_eb_gb_pct_is_selected_in_the_starter_feature_block():
    """E7.5p landed eb_gb_pct with no consumer, so its measured −23% cold-start lift never reached
    a prediction. If this join is dropped, the story silently reverts to that state."""
    sql = (DBT / "models/feature/feature_pregame_starter_features.sql").read_text()
    # once in the eb_posteriors CTE projection, once in the final select
    assert sql.count("eb_gb_pct") >= 2, "eb_gb_pct must be projected AND selected in the final"
    assert "eb.eb_gb_pct" in sql, "the final select must read eb_gb_pct off the EB posterior alias"


def test_eb_gb_pct_reaches_the_game_grain_on_both_sides():
    sql = (DBT / "models/feature/feature_pregame_game_features_raw.sql").read_text()
    for side in ("home", "away"):
        assert f"{side}_starter_eb_gb_pct" in sql, f"{side} side missing the game-grain gb column"


def test_new_gb_columns_are_double_pinned():
    """INC-19: a new numeric column that can ever be FLOAT MUST be ::double-pinned in the TYPE-PIN
    block AND present in the type-contract manifest, or an upstream NUMBER<->FLOAT flip re-opens the
    recurring incremental-drift HALT."""
    sql = (DBT / "models/feature/feature_pregame_game_features_raw.sql").read_text()
    manifest = json.loads(
        (DBT / "type_contracts/feature_pregame_game_features_raw.types.json").read_text()
    )
    for side in ("home", "away"):
        col = f"{side}_starter_eb_gb_pct"
        assert f"{col}::double as {col}" in sql, f"{col} is not ::double-pinned"
        assert col in manifest["all_columns"], f"{col} missing from the contract manifest"
        assert col in manifest["double_pinned"], f"{col} not marked double_pinned"


def test_eb_gb_pct_has_a_range_test_now_that_the_column_exists():
    """E7.5p deliberately deferred this (a dbt test naming a not-yet-existing column is a HARD
    error). E7.9 is where it lands — and the bounds must stay a plausibility envelope, not a
    fitted quantile that a normal season could trip."""
    schema = yaml.safe_load((DBT / "models/eb_posteriors/schema.yml").read_text())
    col = None
    for model in schema["models"]:
        if model["name"] != "eb_starter_posteriors":
            continue
        col = next((c for c in model["columns"] if c["name"] == "eb_gb_pct"), None)
    assert col is not None, "eb_gb_pct column entry vanished from eb_posteriors/schema.yml"
    tests = col.get("tests") or []
    rng = next((t["dbt_utils.accepted_range"] for t in tests
                if isinstance(t, dict) and "dbt_utils.accepted_range" in t), None)
    assert rng is not None, "eb_gb_pct must carry a dbt_utils.accepted_range test"
    args = rng["arguments"]
    assert args["min_value"] <= 0.20 and args["max_value"] >= 0.72, (
        "bounds must stay outside the observed 0.261-0.716 envelope — a tight range would fire on "
        "a legitimate extreme-groundball starter"
    )
    # NULL is legal by design (no MLE and no league anchor in the earliest season)
    assert "not_null" not in tests, "eb_gb_pct is nullable by design; a not_null test would be wrong"


# ── the audit: the premise check that scopes the retrain ──────────────────────────────────────

def test_affected_column_set_excludes_xwoba():
    """Neither MLE wires xwoba_against — it keeps its experience-band prior verbatim. Including it
    in the affected set would overstate the skew and mis-scope the retrain."""
    assert not any("xwoba" in c for c in e79.MLE_AFFECTED_COLS)
    assert set(e79.E75P_STARTER_COLS) == {
        "home_starter_eb_k_pct", "away_starter_eb_k_pct",
        "home_starter_eb_bb_pct", "away_starter_eb_bb_pct",
    }
    # eb_gb_pct is the E7.9 ADDITION, not a moved incumbent column — keep the two sets disjoint.
    assert not set(e79.E79_GB_COLS) & set(e79.MLE_AFFECTED_COLS)


def test_audit_finds_the_run_diff_pre_lineup_skew_and_only_that():
    """The story's premise ('the served totals + run-diff models are skewed') is only true where an
    MLE-moved column is actually IN a served contract. Pinning the measured answer stops a future
    session from re-assuming a broad skew that the 13-feature v6 slim contracts do not have."""
    audit = e79.audit_served_contracts()
    skewed = {k for k, v in audit.items() if v.get("train_serve_skew")}
    assert skewed == {"run_diff/pre_lineup"}, (
        f"expected only run_diff/pre_lineup to carry MLE-moved columns; got {skewed}. If a contract "
        f"legitimately changed, update this guard IN THE SAME PR and re-scope the retrain."
    )
    assert audit["run_diff/pre_lineup"]["n_mle_affected"] == 3


def test_no_served_contract_already_carries_eb_gb_pct():
    """Sanity: eb_gb_pct is new. If a contract already had it, the E7.9 `plus_gb` arm would be a
    no-op duplicate of the incumbent and would corrupt the PBO surface."""
    audit = e79.audit_served_contracts()
    for name, v in audit.items():
        assert not v.get("has_gb_already"), f"{name} unexpectedly already carries a gb column"


# ── the bake-off's pre-registered structure ───────────────────────────────────────────────────

def test_variants_never_duplicate_the_incumbent_column_set():
    """Two identically-columned arms would double-count in the PBO surface and understate the
    multiple-testing burden — so a variant whose added columns are absent must be DROPPED."""
    base = e79._read_contract(e79.SERVED_CONTRACTS[("total_runs", "post_lineup")])
    # matrix with the incumbent columns but neither gb nor any MLE-moved column
    variants = e79.build_arm_contracts("total_runs", "post_lineup", set(base))
    assert list(variants) == ["incumbent"], f"expected only the incumbent arm; got {list(variants)}"

    full = set(base) | set(e79.E79_GB_COLS) | set(e79.MLE_AFFECTED_COLS)
    variants = e79.build_arm_contracts("total_runs", "post_lineup", full)
    assert set(variants) == {"incumbent", "plus_gb", "plus_eb", "plus_both"}
    seen = set()
    for name, cols in variants.items():
        key = tuple(sorted(cols))
        assert key not in seen, f"variant {name} duplicates another arm's column set"
        seen.add(key)
    assert set(variants["plus_gb"]) - set(variants["incumbent"]) == set(e79.E79_GB_COLS)


def test_imputer_added_columns_are_stripped_from_a_served_sidecar():
    """The served sidecar is the POST-imputation column list; build_imputation_pipeline re-adds
    those two indicators. Leaving them in would double them and break the contract guard."""
    cols = e79._read_contract(e79.SERVED_CONTRACTS[("run_diff", "post_lineup")])
    assert not set(cols) & set(e79.IMPUTER_ADDED)


def test_oracle_spec_is_unbeatable_on_a_proper_score():
    """E2.1-r: the oracle floor is the harness's own sanity check. If it were beatable the guard
    would never fire and an inverted metric could crown a winner."""
    import numpy as np
    from betting_ml.utils.promotion_gate import PredictiveOutput

    y = np.array([3.0, 7.0, 11.0, 4.0])
    oracle = e79._OracleSpec().fit_predict(None, y, None, y)
    naive = PredictiveOutput.normal(np.full(len(y), y.mean()), np.full(len(y), 3.0))
    assert oracle.score_to_truth(y, "crps").mean() < naive.score_to_truth(y, "crps").mean()


@pytest.mark.parametrize("gate", [
    "beats_incumbent_by_more_than_noise_floor", "pbo_lt_0_2",
    "dsr_gt_0_at_95", "calibration_not_degraded",
])
def test_all_four_gates_are_required_to_ship(gate):
    """`ship = all(gates.values())` — the default is INCUMBENT_STANDS. This pins that no gate can be
    quietly dropped to manufacture a promotion."""
    src = Path(e79.__file__).read_text()
    assert f'"{gate}"' in src, f"pre-registered gate {gate} is missing from the harness"
    assert "ship = all(gates.values())" in src, "the conjunctive ship rule was weakened"


def test_pbo_and_dsr_thresholds_match_the_repo_discipline():
    assert e79.PBO_MAX == 0.2
    assert e79.DSR_MIN_CONF == 0.95
    assert e79.BEST_ALPHA == 0, "E7.9 is a calibration/consistency story — never an edge claim"


# ── E7.9 step 7 (conditional): the promotion landmine the backfill would walk into ────────────

def test_clv_scorecard_champion_pin_matches_the_registry():
    """`mart_clv_labeled_games` HARDCODES the champion `model_version` in its dedup filter. On the
    day a new champion is promoted, that mart silently returns ZERO rows — the app's model-vs-market
    scorecard goes blank — until the pin is edited. E7.9 step 7 (re-score history after a promotion)
    walks straight into this, so the pin is now mechanically tied to the registry: promote and this
    test goes red until you update BOTH."""
    sql = (DBT / "models/mart/mart_clv_labeled_games.sql").read_text()
    registry = yaml.safe_load((PROJECT_ROOT / "betting_ml/models/model_registry.yaml").read_text())
    champion = registry["run_differential"]["model_version"]
    assert f"model_version = '{champion}'" in sql, (
        f"mart_clv_labeled_games is pinned to a model_version other than the registry champion "
        f"'{champion}'. A promotion MUST update this pin in the same PR or the scorecard zeroes."
    )


def test_backfill_writer_cannot_overwrite_the_live_served_record():
    """The story's ⚠️: a hindsight re-score must never silently replace honest real-time history.
    `backfill_predictions.py` is INSERT-only, stamps `is_backfill=True`, and skips existing
    (game_pk, model_version, retrain_tag) — three independent reasons a live row survives. Pin all
    three; a MERGE/UPDATE creeping in here would quietly rewrite the track record."""
    src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
    assert '"is_backfill":            True' in src, "backfilled rows must be flagged is_backfill"
    assert "INSERT INTO" in src
    upper = src.upper()
    assert "MERGE INTO" not in upper, "a MERGE could overwrite a live served row"
    assert "UPDATE " not in upper.replace("UPDATE THE", ""), "an UPDATE could rewrite live history"
    assert "_get_existing_game_pks" in src, "the idempotency skip must stay"
