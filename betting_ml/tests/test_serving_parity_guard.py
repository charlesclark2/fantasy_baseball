"""Epic E12 — standing serving-parity assertion (no Snowflake; runs in CI).

Story 30.3 diagnosed the offline→live skill collapse as point-in-time SERVING
SKEW: strong-tier (lineup-gated) features arrive NULL at the sparse morning serve
and get flattened to a single training constant, so the live matrix carries ~none
of the signal the model trained on. Story 33.0 FIXED the morning tier by routing
the live pre-lineup run to a DISTINCT model whose contract DROPS the lineup-gated
families it can't yet serve, so there is no train/serve skew within that tier.

These tests are the STANDING GUARD that the skew can't silently return — they lock
the invariants the fix depends on, with NO Snowflake / no model loading:

  1. The pure parity verdict (`compute_target_parity`) fails on the exact two
     live-skill killers (structural-absent, strong-tier flattened) and passes a
     clean served matrix.
  2. `resolve_serve_variant` routes the live morning run to the pre-lineup contract
     exactly as `predict_today` does, and fail-safes to the champion.
  3. The pre-lineup contract is a SUBSET of the champion contract for every target
     (a re-fit can't smuggle in a feature the morning tier can't serve).
  4. The pre-lineup contracts actually DROP the lineup-gated families (the Class-A
     premise) — so a future re-fit that re-adds a morning-NULL family trips here
     instead of silently reintroducing the skew.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from betting_ml.scripts.serving_parity_report import (
    compute_target_parity,
    resolve_serve_variant,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY = yaml.safe_load((PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml").read_text())
_TARGETS = ("total_runs", "run_differential", "home_win")

# A representative strong-tier driver set (mirrors the harness default); the lineup-
# gated members are the ones that are legitimately NULL pre-lineup.
_STRONG = ["home_elo", "away_elo", "elo_diff",
           "home_avg_eb_woba", "away_avg_eb_woba",
           "home_lineup_avg_xwoba_vs_cluster", "away_lineup_avg_xwoba_vs_cluster",
           "home_bp_eb_xwoba", "away_bp_eb_xwoba"]


def _contract(path: str) -> list[str]:
    raw = json.loads((PROJECT_ROOT / path).read_text())
    return raw["feature_cols"] if isinstance(raw, dict) else raw


# ── 1. pure parity verdict ─────────────────────────────────────────────────────

class TestComputeTargetParity:
    def test_clean_matrix_passes(self):
        contract = ["home_elo", "away_elo", "park_run_factor", "over_american"]
        served = set(contract)
        r = compute_target_parity(contract, served, all_null_cols=set(), strong_tier=_STRONG)
        assert r["parity_ok"] is True
        assert r["absent"] == []
        assert r["strong_tier_degraded"] == []

    def test_structurally_absent_column_fails(self):
        # A contract column missing from the served matrix is silently 0.0-filled —
        # a value never seen at train time. Must fail parity.
        contract = ["home_elo", "away_elo", "park_run_factor"]
        served = {"home_elo", "away_elo"}  # park_run_factor absent
        r = compute_target_parity(contract, served, all_null_cols=set(), strong_tier=_STRONG)
        assert r["parity_ok"] is False
        assert "park_run_factor" in r["absent"]

    def test_strong_tier_all_null_fails(self):
        # elo served but ENTIRELY null across the slate → constant-imputed → zero
        # discrimination. This is the 2026-06 incident signature; must fail.
        contract = ["home_elo", "away_elo", "park_run_factor"]
        served = set(contract)
        r = compute_target_parity(contract, served, all_null_cols={"home_elo"}, strong_tier=_STRONG)
        assert r["parity_ok"] is False
        assert "home_elo" in r["strong_tier_degraded"]

    def test_non_strong_all_null_is_reported_but_does_not_fail(self):
        # over_american (an odds column) is null for a comparable fraction in
        # training and is not a strong driver — report it, don't fail parity.
        contract = ["home_elo", "away_elo", "over_american"]
        served = set(contract)
        r = compute_target_parity(contract, served, all_null_cols={"over_american"}, strong_tier=_STRONG)
        assert r["parity_ok"] is True
        assert "over_american" in r["served_but_all_null"]
        assert r["strong_tier_degraded"] == []

    def test_strong_tier_intersected_with_contract(self):
        # A strong-tier feature the served contract DOESN'T use can't degrade it,
        # even if it's all-null in the frame.
        contract = ["home_elo", "away_elo"]  # no lineup features
        served = set(contract)
        r = compute_target_parity(
            contract, served,
            all_null_cols={"home_lineup_avg_xwoba_vs_cluster"},  # not in contract
            strong_tier=_STRONG,
        )
        assert r["parity_ok"] is True
        assert r["strong_tier_total"] == 2  # only the two elo cols are in-contract


# ── 2. serve-variant routing mirrors predict_today ─────────────────────────────

class TestResolveServeVariant:
    @pytest.mark.parametrize("target", _TARGETS)
    def test_live_morning_routes_to_pre_lineup(self, target):
        variant, path = resolve_serve_variant(_REGISTRY, target, use_pre_lineup=True)
        # All three pre-lineup artifacts are wired (Story 33.0) → morning serves them.
        assert variant == "pre_lineup"
        assert "pre_lineup" in path

    @pytest.mark.parametrize("target", _TARGETS)
    def test_post_lineup_routes_to_champion(self, target):
        variant, path = resolve_serve_variant(_REGISTRY, target, use_pre_lineup=False)
        assert variant == "prod"
        assert path == _REGISTRY[target]["feature_columns_path"]

    def test_fail_safe_to_champion_when_pre_lineup_unwired(self):
        reg = {"x": {"feature_columns_path": "champ.json"}}  # no pre_lineup keys
        variant, path = resolve_serve_variant(reg, "x", use_pre_lineup=True)
        assert variant == "prod"
        assert path == "champ.json"


# ── 3 + 4. the 33.0 tier-split contract invariants ─────────────────────────────

class TestPreLineupContractInvariants:
    @pytest.mark.parametrize("target", _TARGETS)
    def test_pre_lineup_is_subset_of_champion(self, target):
        """A pre-lineup re-fit must not add a feature the champion (and thus the
        feature store) doesn't carry — that would be an unservable/0.0-filled column."""
        entry = _REGISTRY[target]
        champ = set(_contract(entry["feature_columns_path"]))
        pre = set(_contract(entry["pre_lineup_feature_columns_path"]))
        extra = pre - champ
        assert not extra, f"{target}: pre-lineup contract has non-champion features: {sorted(extra)}"

    @pytest.mark.parametrize("target", _TARGETS)
    def test_pre_lineup_drops_lineup_gated_families(self, target):
        """The Class-A premise: the pre-lineup contract must carry FAR FEWER
        lineup-gated features than the champion (those are NULL before lineups post).
        Locks the fix — a re-fit that re-introduces the heavy lineup families trips here.
        """
        import re
        # lineup composition families that are unknown until a lineup is posted.
        # (Starter-EB / bullpen-EB are pitcher/team gated, available pre-lineup, so
        # they're intentionally NOT matched here.)
        gated = re.compile(r"lineup_avg|lineup_archetype|_vs_cluster|lineup_slot|xwoba_vs_(?:lhp|rhp)", re.I)
        entry = _REGISTRY[target]
        champ_gated = [c for c in _contract(entry["feature_columns_path"]) if gated.search(c)]
        pre_gated = [c for c in _contract(entry["pre_lineup_feature_columns_path"]) if gated.search(c)]
        assert len(pre_gated) < len(champ_gated), (
            f"{target}: pre-lineup carries {len(pre_gated)} lineup-gated features vs champion "
            f"{len(champ_gated)} — the tier split must DROP them (else the morning skew returns)."
        )

    @pytest.mark.parametrize("target", _TARGETS)
    def test_both_contracts_exist_and_nonempty(self, target):
        entry = _REGISTRY[target]
        for key in ("feature_columns_path", "pre_lineup_feature_columns_path"):
            cols = _contract(entry[key])
            assert cols, f"{target}.{key} contract is empty"
