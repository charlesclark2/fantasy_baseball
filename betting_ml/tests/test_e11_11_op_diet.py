"""E11.11 — regression guards for lineup_monitor_job op diet.

Two change-gated skip guards:

  1. Narrative pick-delta guard (generate_pick_narratives.py --pick-delta-guard):
     - Cortex calls skip when picks are unchanged since last generation cycle.
     - Cached narratives are RESTORED (fast UPDATE) for unchanged-pick games.
     - A FORCED pick change (new pick_side or materially different prob) must
       re-generate via Cortex on the same cycle (30.13 self-heal invariant).

  2. Umpire once-captured guard (ingest_umpires.py --skip-if-exists):
     - Ingest is skipped when today's statsapi assignments already exist.
     - First ingest of the day (no existing rows) runs normally.

Guards are CHANGE-gated, never timer-gated: a real lineup/odds change on the
same game_pk must still produce a fresh narrative before write_serving_store.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO))

from betting_ml.scripts.generate_pick_narratives import (
    _compute_pick_delta,
    _pick_fingerprint,
    _pick_state_path,
    _load_pick_state,
    _save_pick_state,
)


# ── _pick_fingerprint ─────────────────────────────────────────────────────────

def test_pick_fingerprint_stable():
    """Same pick side + same prob → identical fingerprint."""
    assert _pick_fingerprint("home", 0.58) == _pick_fingerprint("home", 0.5801)


def test_pick_fingerprint_side_change():
    """Flip in pick_side → different fingerprint."""
    assert _pick_fingerprint("home", 0.58) != _pick_fingerprint("away", 0.58)


def test_pick_fingerprint_prob_change():
    """Prob shift > 0.005 → different fingerprint (rounds to 2dp)."""
    assert _pick_fingerprint("home", 0.58) != _pick_fingerprint("home", 0.59)


def test_pick_fingerprint_none_safe():
    """None inputs must not raise; unknown/0.5 is the fallback."""
    fp = _pick_fingerprint(None, None)
    assert fp == "unknown:0.5"


# ── _compute_pick_delta ───────────────────────────────────────────────────────

def _make_current(game_pk: int, pick_side: str, prob: float,
                  narrative: str | None = None, model_version: str = "v5") -> dict:
    return {
        game_pk: {
            "layer4_h2h_decision": pick_side,
            "calibrated_win_prob": prob,
            "pick_narrative": narrative,
            "model_version": model_version,
        }
    }


def _make_state(game_pk: int, pick_side: str, prob: float,
                narrative: str = "cached text", model_version: str = "v5") -> dict:
    return {
        str(game_pk): {
            "pick_fp": _pick_fingerprint(pick_side, prob),
            "model_version": model_version,
            "narrative": narrative,
        }
    }


class TestComputePickDelta:
    """_compute_pick_delta classifies games into changed_or_new vs to_restore."""

    def test_no_state_file_forces_all_changed(self):
        """Empty state → all games are 'changed_or_new' (first run of day)."""
        current = _make_current(100, "home", 0.58)
        changed, to_restore = _compute_pick_delta(current, state={})
        assert 100 in changed
        assert not to_restore

    def test_unchanged_pick_with_null_narrative_goes_to_restore(self):
        """Pick unchanged + narrative NULLed by predict_today → restore (not Cortex)."""
        current = _make_current(100, "home", 0.58, narrative=None)
        state = _make_state(100, "home", 0.58)
        changed, to_restore = _compute_pick_delta(current, state)
        assert 100 not in changed
        assert 100 in to_restore

    def test_unchanged_pick_with_existing_narrative_no_action(self):
        """Pick unchanged + narrative already populated → neither bucket."""
        current = _make_current(100, "home", 0.58, narrative="existing text")
        state = _make_state(100, "home", 0.58)
        changed, to_restore = _compute_pick_delta(current, state)
        assert 100 not in changed
        assert 100 not in to_restore

    def test_changed_pick_side_goes_to_changed(self):
        """Pick side flips (home→away) → must re-generate via Cortex."""
        current = _make_current(100, "away", 0.42, narrative=None)
        state = _make_state(100, "home", 0.58)
        changed, to_restore = _compute_pick_delta(current, state)
        assert 100 in changed
        assert 100 not in to_restore

    def test_changed_prob_bucket_goes_to_changed(self):
        """Pick side same but prob shifts > 0.005 → re-generate."""
        current = _make_current(100, "home", 0.65, narrative=None)
        state = _make_state(100, "home", 0.58)
        changed, to_restore = _compute_pick_delta(current, state)
        assert 100 in changed
        assert 100 not in to_restore

    def test_mixed_games(self):
        """One changed, one unchanged-null, one unchanged-populated — each lands correctly."""
        current = {
            101: {"layer4_h2h_decision": "away", "calibrated_win_prob": 0.42,
                  "pick_narrative": None, "model_version": "v5"},
            102: {"layer4_h2h_decision": "home", "calibrated_win_prob": 0.58,
                  "pick_narrative": None, "model_version": "v5"},
            103: {"layer4_h2h_decision": "home", "calibrated_win_prob": 0.60,
                  "pick_narrative": "already there", "model_version": "v5"},
        }
        state = {
            "101": {"pick_fp": _pick_fingerprint("home", 0.58), "model_version": "v5", "narrative": "old"},
            "102": {"pick_fp": _pick_fingerprint("home", 0.58), "model_version": "v5", "narrative": "cached"},
            "103": {"pick_fp": _pick_fingerprint("home", 0.60), "model_version": "v5", "narrative": "cached"},
        }
        changed, to_restore = _compute_pick_delta(current, state)
        assert 101 in changed      # pick side flipped
        assert 101 not in to_restore
        assert 102 in to_restore   # unchanged pick, NULL narrative → restore
        assert 102 not in changed
        assert 103 not in changed  # unchanged + populated
        assert 103 not in to_restore

    def test_skip_when_empty_current(self):
        """No has_odds games today → both buckets empty (nothing to do)."""
        changed, to_restore = _compute_pick_delta(current={}, state={"100": {}})
        assert not changed
        assert not to_restore


# ── 30.13 self-heal invariant: forced pick change must trigger re-generation ──

class TestSelfHealInvariant:
    """A real lineup change that flips the pick must land in changed_or_new
    (not silently skipped). This verifies the 30.13 self-heal path through
    the delta guard: re-score → pick changes → delta guard detects it →
    Cortex regenerates → serve picks up fresh narrative."""

    def test_pitcher_change_that_flips_pick_triggers_regen(self):
        """Simulates: starter scratched, model flips from home→away after re-score."""
        # Before (state from last narrative run): home pick, prob 0.58
        state = _make_state(200, "home", 0.58, narrative="Yankees favored…")

        # After re-score: pick flipped to away (new starter weaker)
        current = _make_current(200, "away", 0.43, narrative=None)

        changed, to_restore = _compute_pick_delta(current, state)
        assert 200 in changed, "pick flip must land in changed_or_new (Cortex required)"
        assert 200 not in to_restore, "changed game must not be restored from stale cache"

    def test_pitcher_change_same_pick_restores_not_regenerates(self):
        """Simulates: roster move, but model pick unchanged — restore is correct."""
        state = _make_state(201, "home", 0.60, narrative="Cubs favored…")

        # Re-score produced same pick (slightly different prob, same bucket)
        current = _make_current(201, "home", 0.601, narrative=None)

        changed, to_restore = _compute_pick_delta(current, state)
        assert 201 not in changed, "unchanged pick must NOT trigger Cortex"
        assert 201 in to_restore, "unchanged pick with NULL narrative must restore from cache"


# ── umpire once-captured guard ────────────────────────────────────────────────

class TestUmpireSkipIfExists:
    """lineup_ingest_umpires passes --skip-if-exists to ingest_umpires.py."""

    def test_op_passes_skip_if_exists_flag(self):
        """lineup_ingest_umpires must include --skip-if-exists in the script args."""
        import ast
        src = (_REPO / "pipeline" / "ops" / "sensor_ops.py").read_text()
        tree = ast.parse(src)

        # Find calls to _run_script inside lineup_ingest_umpires
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "lineup_ingest_umpires":
                func_src = ast.unparse(node)
                assert "--skip-if-exists" in func_src, (
                    "lineup_ingest_umpires must pass --skip-if-exists to ingest_umpires.py "
                    "(E11.11 once-captured guard)"
                )
                break
        else:
            pytest.fail("lineup_ingest_umpires not found in sensor_ops.py")

    def test_ingest_umpires_has_skip_if_exists_arg(self):
        """ingest_umpires.py must declare --skip-if-exists in argparse."""
        src = (_REPO / "scripts" / "ingest_umpires.py").read_text()
        assert "skip-if-exists" in src, (
            "ingest_umpires.py must add --skip-if-exists to argparse (E11.11)"
        )

    def test_skip_if_exists_guard_writes_nothing_for_an_unchanged_slate(self):
        """--skip-if-exists must make a repeat tick a genuine no-op: no rows written.

        ⚠️ THIS TEST REPLACES A VACUOUS ONE (FU-3, 2026-08-02). The original
        `test_skip_if_exists_guard_on_existing_rows` stubbed a Snowflake cursor, then
        `main()` was NEVER CALLED — it re-implemented the branch inline and asserted
        `not called_fetch`, which is trivially true when nothing runs. Proven vacuous by
        deleting the entire guard from `ingest_umpires.py`: the test still passed. That is
        the NF1.7 (a) class (a check that cannot fail is not a check), and it is why the
        `and do_sf` conjunct — which disabled the guard for the whole S3 era — shipped and
        survived unnoticed.

        This version drives the REAL `main()` on the REAL S3 write leg. Depth (wave
        announcements, reassignment, fail-open, the live DuckDB read) lives in
        `test_ingest_umpires_per_game_skip.py`.
        """
        import argparse
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ingest_umpires_e1111", _REPO / "scripts" / "ingest_umpires.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        fetched = [{"game_pk": 101, "game_date": "2026-06-23", "season": 2026,
                    "umpire_name": "Ump One", "umpire_id": "111"}]
        args = argparse.Namespace(date="2026-06-23", dry_run=False, skip_if_exists=True)
        written = []

        with patch.object(mod, "w11_write_mode", return_value="s3"), \
             patch.object(mod, "fetch_hp_umpires", return_value=fetched), \
             patch.object(mod, "existing_statsapi_assignments",
                          return_value={101: ("111", "Ump One")}), \
             patch.object(mod, "write_raw_rows_s3",
                          side_effect=lambda _s, rows, **kw: written.append(rows)), \
             patch.object(mod.argparse.ArgumentParser, "parse_args", return_value=args):
            mod.main()

        assert written == [], (
            "an unchanged slate must write NOTHING — every write re-stamps loaded_at and "
            "bumps the E11.24-6a umpire-rebuild watermark"
        )


# ── narrative op wires --pick-delta-guard ─────────────────────────────────────

def test_narrative_op_passes_pick_delta_guard():
    """generate_pick_narratives_op must pass --pick-delta-guard to the script."""
    import ast
    src = (_REPO / "pipeline" / "ops" / "daily_ingestion_ops.py").read_text()
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_pick_narratives_op":
            func_src = ast.unparse(node)
            assert "--pick-delta-guard" in func_src, (
                "generate_pick_narratives_op must pass --pick-delta-guard (E11.11)"
            )
            break
    else:
        pytest.fail("generate_pick_narratives_op not found in daily_ingestion_ops.py")


# ── state-file round-trip ─────────────────────────────────────────────────────

def test_state_file_round_trip(tmp_path, monkeypatch):
    """save then load produces identical dict."""
    monkeypatch.setattr(
        "betting_ml.scripts.generate_pick_narratives._pick_state_path",
        lambda d: tmp_path / f"state_{d}.json",
    )
    from betting_ml.scripts.generate_pick_narratives import _save_pick_state, _load_pick_state
    data = {"100": {"pick_fp": "home:0.58", "model_version": "v5", "narrative": "test"}}
    _save_pick_state("2026-06-23", data)
    loaded = _load_pick_state("2026-06-23")
    assert loaded == data


def test_load_pick_state_missing_file(tmp_path, monkeypatch):
    """Missing state file → empty dict (first run of day)."""
    monkeypatch.setattr(
        "betting_ml.scripts.generate_pick_narratives._pick_state_path",
        lambda d: tmp_path / f"state_{d}.json",
    )
    from betting_ml.scripts.generate_pick_narratives import _load_pick_state
    assert _load_pick_state("2099-01-01") == {}
