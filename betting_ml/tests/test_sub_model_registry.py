"""
Unit tests for betting_ml/scripts/sub_model_registry.py

Tests use a temporary YAML file so the real registry is never modified.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pytest
import yaml

from betting_ml.scripts.sub_model_registry import (
    get_entry,
    list_champions,
    load_registry,
    promote,
    register,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SEED_REGISTRY: dict = {
    "run_env_v1": {
        "artifact_path": "models/sub_models/run_env_v1.pkl",
        "promotion_status": "champion",
        "promoted_at": "2026-06-01",
    },
    "run_env_v2": {
        "artifact_path": "models/sub_models/run_env_v2.pkl",
        "promotion_status": "challenger",
        "promoted_at": None,
    },
    "offense_v1": {
        "artifact_path": "models/sub_models/offense_v1.pkl",
        "promotion_status": "pending",
        "promoted_at": None,
    },
}


@pytest.fixture
def reg_path(tmp_path: Path) -> Path:
    path = tmp_path / "sub_model_registry.yaml"
    with open(path, "w") as fh:
        yaml.dump(copy.deepcopy(_SEED_REGISTRY), fh)
    return path


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------

class TestLoadRegistry:
    def test_returns_dict(self, reg_path):
        result = load_registry(reg_path)
        assert isinstance(result, dict)

    def test_all_keys_present(self, reg_path):
        result = load_registry(reg_path)
        assert set(result) == {"run_env_v1", "run_env_v2", "offense_v1"}

    def test_empty_file_returns_empty_dict(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        assert load_registry(path) == {}


# ---------------------------------------------------------------------------
# get_entry
# ---------------------------------------------------------------------------

class TestGetEntry:
    def test_returns_entry(self, reg_path):
        entry = get_entry("run_env_v1", reg_path)
        assert entry["promotion_status"] == "champion"

    def test_raises_on_missing(self, reg_path):
        with pytest.raises(KeyError, match="starter_v1"):
            get_entry("starter_v1", reg_path)

    def test_returns_deep_copy(self, reg_path):
        entry = get_entry("run_env_v1", reg_path)
        entry["promotion_status"] = "mutated"
        # original on disk should be unchanged
        assert get_entry("run_env_v1", reg_path)["promotion_status"] == "champion"


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_adds_new_entry(self, reg_path):
        register("starter_v1", {"promotion_status": "pending", "artifact_path": "x.pkl"}, path=reg_path)
        assert "starter_v1" in load_registry(reg_path)

    def test_merges_into_existing_by_default(self, reg_path):
        register("offense_v1", {"cv_score": 2.85}, path=reg_path)
        entry = get_entry("offense_v1", reg_path)
        assert entry["cv_score"] == 2.85
        assert entry["promotion_status"] == "pending"  # not overwritten

    def test_overwrite_replaces_entirely(self, reg_path):
        register("offense_v1", {"promotion_status": "deprecated"}, overwrite=True, path=reg_path)
        entry = get_entry("offense_v1", reg_path)
        assert "artifact_path" not in entry  # prior field gone

    def test_invalid_status_raises(self, reg_path):
        with pytest.raises(ValueError, match="invalid promotion_status"):
            register("new_v1", {"promotion_status": "invalid"}, path=reg_path)


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

class TestPromote:
    def test_challenger_to_champion(self, reg_path):
        promote("run_env_v2", new_status="champion", path=reg_path)
        assert get_entry("run_env_v2", reg_path)["promotion_status"] == "champion"

    def test_prior_champion_deprecated_on_promotion(self, reg_path):
        promote("run_env_v2", new_status="champion", path=reg_path)
        assert get_entry("run_env_v1", reg_path)["promotion_status"] == "deprecated"

    def test_champion_to_deprecated(self, reg_path):
        promote("run_env_v1", new_status="deprecated", path=reg_path)
        assert get_entry("run_env_v1", reg_path)["promotion_status"] == "deprecated"

    def test_invalid_transition_raises(self, reg_path):
        with pytest.raises(ValueError, match="Invalid transition"):
            promote("run_env_v1", new_status="challenger", path=reg_path)

    def test_missing_entry_raises(self, reg_path):
        with pytest.raises(KeyError, match="starter_v1"):
            promote("starter_v1", new_status="champion", path=reg_path)

    def test_promoted_at_stamped(self, reg_path):
        from datetime import date
        today = str(date.today())
        promote("run_env_v2", new_status="champion", path=reg_path)
        assert get_entry("run_env_v2", reg_path)["promoted_at"] == today

    def test_pending_to_challenger(self, reg_path):
        promote("offense_v1", new_status="challenger", path=reg_path)
        assert get_entry("offense_v1", reg_path)["promotion_status"] == "challenger"


# ---------------------------------------------------------------------------
# list_champions
# ---------------------------------------------------------------------------

class TestListChampions:
    def test_returns_only_champions(self, reg_path):
        champs = list_champions(reg_path)
        assert set(champs) == {"run_env_v1"}

    def test_reflects_promotion(self, reg_path):
        promote("run_env_v2", new_status="champion", path=reg_path)
        champs = list_champions(reg_path)
        assert "run_env_v2" in champs
        assert "run_env_v1" not in champs
