"""test_v6_lineage_on_promote.py — E9.26b durable fix: finalize records the SF lineage.

The lag this prevents: finalize_v6_champion.py updated only model_registry.yaml (the served-
artifact source) + S3 on the E13.11 v6 swap, while the Snowflake `model_registry` lineage table
is maintained ONLY by record_promotion() — which was never called. So serving moved to v6 while
the ledger froze at v5, and the Admin → Model Artifact Freshness panel read `ledger_behind`.

finalize now records the lineage right after the S3 upload (post_lineup, real deploy only),
idempotently and non-fatally. These tests pin (1) the honest CV the lineage stamps is the
n-weighted pooled challenger from the promotion gate, and (2) the wiring/guards are in place.
Import-safe for the fast gate (finalize imports pandas/numpy/snowflake.connector but NOT pipeline).
"""
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).parents[2]
_FINALIZE = _REPO / "betting_ml" / "scripts" / "finalize_v6_champion.py"
_RECONCILE = _REPO / "scripts" / "ops" / "reconcile_v6_ledger.py"


def _src(p: Path) -> str:
    return p.read_text()


def test_pooled_gate_metric_matches_gate_json():
    from betting_ml.scripts.finalize_v6_champion import _pooled_gate_metric

    # The n-weighted pooled CHALLENGER metric on the de-leaked purged-CV gate — the honest number
    # recorded on the v6 lineage rows (matches scripts/ops/reconcile_v6_ledger.py).
    assert _pooled_gate_metric("home_win", "post_lineup") == ("brier", 0.2447)
    assert _pooled_gate_metric("run_diff", "post_lineup") == ("mae", 3.4776)
    assert _pooled_gate_metric("total_runs", "post_lineup") == ("mae", 3.4948)
    # Missing gate → None (never a fabricated metric).
    assert _pooled_gate_metric("does_not_exist", "post_lineup") is None


def test_finalize_wires_lineage_recording():
    src = _src(_FINALIZE)
    # The recording is gated on a REAL post_lineup deploy (not --smoke/--no-upload/--no-record-lineage).
    assert "_record_champion_lineage(" in src, "finalize must call the lineage recorder"
    assert 'args.tier == "post_lineup" and not (args.no_upload or args.smoke) and not args.no_record_lineage' in src, \
        "lineage recording must be gated on a real post_lineup deploy"
    # The recorder delegates to the canonical record_promotion() and is NON-FATAL (never fails the deploy).
    assert "from betting_ml.utils.model_registry_tracker import record_promotion" in src, \
        "must use the canonical record_promotion()"
    assert "reconcile_v6_ledger.py" in src, "a failure/skip must point at the manual reconcile fallback"


def test_finalize_never_fabricates_a_cv_on_missing_gate():
    src = _src(_FINALIZE)
    # On a missing gate the recorder returns early (no record_promotion with a faked metric).
    assert "LINEAGE NOT RECORDED" in src and "there is no honest CV to stamp" in src


def test_reconcile_script_is_idempotent_and_covers_three_targets():
    src = _src(_RECONCILE)
    assert _RECONCILE.exists()
    assert "--apply" in src, "reconcile must be dry-run by default"
    assert "from betting_ml.utils.model_registry_tracker import record_promotion" in src
    for t in ("home_win", "run_differential", "total_runs"):
        assert f'"{t}"' in src, f"reconcile must cover {t}"
