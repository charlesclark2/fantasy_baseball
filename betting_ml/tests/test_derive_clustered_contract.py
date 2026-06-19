"""E1.8 — regression guards for the reproducible clustered-contract derivation.

Locks in two properties of betting_ml/scripts/derive_clustered_contract.py:
  1. The shipped totals contract is a DETERMINISTIC function of its source MDA — re-running
     the E1.3 rule (non-noise cluster members) on the fully de-leaked importance JSON must
     reproduce the on-disk contract exactly. Catches any out-of-band hand-edit drift.
  2. The leakage guard refuses to derive a production contract from a still-leaky MDA
     run (the exact trap E1.8 hit: the stuffplus_deleaked A/B ran with bullpen=static).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from betting_ml.scripts.derive_clustered_contract import _signal_members, derive

_ROOT = Path(__file__).resolve().parents[2]
_JSON_DIR = _ROOT / "betting_ml" / "evaluation" / "feature_selection" / "clustered_importance"
_BULLPEN_V3 = _JSON_DIR / "clustered_importance_total_runs_bullpen_v3.json"
_STUFFPLUS_STATIC = _JSON_DIR / "clustered_importance_total_runs_stuffplus_deleaked.json"
_CLEAN_MDA = _JSON_DIR / "clustered_importance_total_runs_bullpen_v3_stuffplus_deleaked.json"
_TOTALS_CONTRACT = (_ROOT / "betting_ml" / "models" / "total_runs"
                    / "feature_columns_ngboost_pruned_clustered_deleaked_2026.json")


@pytest.mark.skipif(not _CLEAN_MDA.exists() or not _TOTALS_CONTRACT.exists(),
                    reason="clean (both-de-leak) MDA JSON or totals contract not present")
def test_shipped_contract_matches_derivation():
    """The on-disk totals contract == the E1.3 rule applied to its fully de-leaked source MDA."""
    derived = set(_signal_members(json.loads(_CLEAN_MDA.read_text())))
    shipped = set(json.loads(_TOTALS_CONTRACT.read_text())["feature_cols"])
    assert derived == shipped, f"contract drift: +{sorted(derived - shipped)} / -{sorted(shipped - derived)}"


@pytest.mark.skipif(not _STUFFPLUS_STATIC.exists(), reason="stuffplus_deleaked importance JSON not present")
def test_guard_blocks_static_bullpen_source(tmp_path):
    """Deriving a production contract from a static-bullpen run must raise (re-imports the leak)."""
    with pytest.raises(SystemExit, match="LEAKY SOURCE"):
        derive("total_runs", _STUFFPLUS_STATIC, allow_leaky=False, dry_run=True, date="2026-06-19")


@pytest.mark.skipif(not _BULLPEN_V3.exists(), reason="bullpen_v3 importance JSON not present")
def test_guard_blocks_leaky_stuffplus_source():
    """bullpen_v3 alone is still Stuff+-leaky → must also be refused for a production write."""
    with pytest.raises(SystemExit, match="LEAKY SOURCE"):
        derive("total_runs", _BULLPEN_V3, allow_leaky=False, dry_run=True, date="2026-06-19")
