"""Guards for MLB-HV2-1 — the Bovada H2H market-bias backtest.

Three jobs:
  1. MODEL INDEPENDENCE is a checkable property of the study module, checked in a
     SUBPROCESS (an in-process check is vacuous — pytest has already imported half
     the scientific stack).
  2. The committed PRE-REGISTRATION and the registered family in code cannot drift
     apart.
  3. The pure scoring primitives do what the prereg says they do, on fixtures
     built so that only the clause under test can decide the answer (NF-D17: an
     isolating fixture per clause, or the guard proves nothing).

Every clause here was RED-proven against deliberately broken source — see
`betting_ml/tests/mlb_hv2_1_red_proof.py`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts import mlb_hv2_1_market_bias as mb

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "ablation_results" / "mlb_hv2_1_prereg.md"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Model independence
# ══════════════════════════════════════════════════════════════════════════════

#: Anything whose presence would mean a Credence MODEL, a serving path, or a
#: learner reached the study. `scipy` is deliberately absent from this list — it
#: is a numerics dependency of the deflation gates, not a model.
FORBIDDEN_MODULE_PREFIXES = (
    "sklearn", "lightgbm", "xgboost", "ngboost", "torch", "tensorflow", "statsmodels",
    "betting_ml.models", "betting_ml.data", "pipeline", "dagster",
    "snowflake", "predict_today", "write_serving_store",
)


def _import_probe(module: str, extra_path: Path | None = None) -> tuple[set[str], set[str]]:
    """Import `module` in a clean subprocess; return (baseline, newly_imported).

    The measurement is the DELTA, not the final `sys.modules`. This interpreter
    starts with a bare `snowflake` NAMESPACE package already present (a `.pth`
    artifact of the environment, imported by nobody), so a final-state match would
    fail for every module in the repo for a reason that has nothing to do with the
    study -- a false positive that could only be silenced by WEAKENING the
    forbidden list. The delta answers the question actually being asked: what did
    THIS module cause to be imported."""
    code = (
        "import json, sys\n"
        "_baseline = sorted(sys.modules)\n"
        f"import {module}\n"
        # non-vacuity: the target really did import, so an empty forbidden set is
        # a real result and not the signature of a crashed import.
        f"assert {module!r} in sys.modules, 'target module did not import'\n"
        "json.dump({'baseline': _baseline, 'after': sorted(sys.modules)}, sys.stdout)\n"
    )
    env = dict(os.environ)
    if extra_path:
        env["PYTHONPATH"] = str(extra_path) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, f"probe failed:\n{out.stderr}"
    import json as _json
    payload = _json.loads(out.stdout)
    baseline = set(payload["baseline"])
    return baseline, set(payload["after"]) - baseline


def _leaked(new_modules: set[str]) -> list[str]:
    return sorted(m for m in new_modules
                  if any(m == p or m.startswith(p + ".")
                         for p in FORBIDDEN_MODULE_PREFIXES))


def test_the_study_imports_no_model_serving_or_learner_module():
    _, new = _import_probe("betting_ml.scripts.mlb_hv2_1_market_bias")
    # non-vacuity FIRST: if the probe imported almost nothing we assert on air.
    assert "betting_ml.scripts.mlb_hv2_1_market_bias" in new
    assert len(new) > 20, "probe returned an implausibly small module set"
    assert _leaked(new) == [], (
        "MLB-HV2-1 must be model-independent, but importing it pulled in: "
        f"{_leaked(new)}"
    )


def test_the_probe_can_actually_detect_a_leak(tmp_path):
    """Two-sided: a module that DOES import a forbidden name must be caught, or the
    guard above passes on air (NF1.7 (a)).

    The leaky module is WRITTEN HERE rather than borrowed from the repo, so the
    detector's proof cannot quietly expire the day some other module switches to a
    lazy import -- which is exactly how it first failed."""
    (tmp_path / "hv2_leak_probe.py").write_text("import sklearn.linear_model  # noqa: F401\n")
    _, new = _import_probe("hv2_leak_probe", extra_path=tmp_path)
    assert "hv2_leak_probe" in new, "the leaky probe module did not import"
    assert _leaked(new), ("the leak probe found nothing in a module that imports a "
                          "learner -- the detector, not the study, is broken")


# ══════════════════════════════════════════════════════════════════════════════
# 2. The prereg document and the code cannot drift
# ══════════════════════════════════════════════════════════════════════════════

def _prereg_text() -> str:
    return PREREG.read_text()


def test_prereg_document_matches_the_registered_family():
    text = _prereg_text()
    assert len(mb.REGISTERED_ARMS) == 8
    for arm in mb.REGISTERED_ARMS:
        assert f"`{arm.arm_id}`" in text, f"{arm.arm_id} is registered in code but not in the prereg"
    for anchor in mb.ANCHORS:
        assert f"`{anchor.arm_id}`" in text, f"{anchor.arm_id} missing from the prereg"
    # the prereg may not name an arm the code does not carry
    ids = {a.arm_id for a in mb.REGISTERED_ARMS} | {a.arm_id for a in mb.ANCHORS}
    for token in ("dog_vs_", "road_", "fade_marquee", "anchor_"):
        for line in text.splitlines():
            for word in line.replace("`", " ").split():
                word = word.rstrip('.,;:)')
                if "*" in word:
                    continue
                if word.startswith(token) and word not in ids:
                    pytest.fail(f"prereg names an unregistered arm: {word}")


def test_prereg_document_matches_the_gate_thresholds():
    text = _prereg_text()
    assert mb.DECLARED_FIELD_SIZE == 8 and "declared_field_size = 8" in text
    assert mb.BH_ALPHA == 0.05 and "α = 0.05" in text
    assert mb.MAX_PBO == 0.20 and "PBO < 0.20" in text
    assert mb.MIN_DSR == 0.95 and "≥ 0.95" in text
    assert mb.SEASONS == (2020, 2021, 2022, 2024, 2025, 2026)
    assert "**2020, 2021, 2022, 2024, 2025, 2026**" in text
    assert mb.EXCLUDED_SEASONS == (2023,) and "**2023**" in text
    assert mb.FIRST_PITCH_UTC_HOURS == (3, 23) and "UTC hours 03–23" in text
    assert mb.NOVIG_METHOD == "proportional" and "proportional" in text
    assert set(mb.MARQUEE_TEAMS) == {"ATL", "BOS", "CHC", "LAD", "NYM", "NYY"}
    assert "**ATL, BOS, CHC, LAD, NYM, NYY**" in text


def test_the_fold_clause_is_the_one_the_prereg_states():
    clause = mb.fold_consistency_clause(len(mb.SEASONS), alpha=mb.FOLD_ALPHA)
    assert clause.attainable
    assert clause.wins_required == 5, "the prereg states 5 of 6 season folds"
    assert clause.attained_false_fire == pytest.approx(0.109375, abs=1e-9)
    assert "≥ **5 of 6** season folds" in _prereg_text()


# ══════════════════════════════════════════════════════════════════════════════
# 3. The pure primitives
# ══════════════════════════════════════════════════════════════════════════════

def _frame(rows) -> pd.DataFrame:
    f = pd.DataFrame(rows, columns=list(mb.FRAME_COLUMNS))
    return mb.derive(f)


def _row(game_pk, home, away, home_am, away_am, home_won, season=2024, month=5, hour=23):
    return (game_pk, season, f"{season}-{month:02d}-01", hour, home, away,
            home_am, away_am, home_won)


def test_american_to_decimal_is_the_standard_conversion():
    assert mb.american_to_decimal([-200])[0] == pytest.approx(1.5, abs=1e-12)
    assert mb.american_to_decimal([+150])[0] == pytest.approx(2.5, abs=1e-12)
    assert mb.american_to_decimal([-110])[0] == pytest.approx(1 + 100 / 110, abs=1e-12)


def test_proportional_novig_sums_to_one_and_removes_the_overround():
    d = mb.american_to_decimal([-150, +130])
    ph, pa = mb.novig_proportional([d[0]], [d[1]])
    assert ph[0] + pa[0] == pytest.approx(1.0, abs=1e-12)
    assert ph[0] < 1.0 / d[0], "de-vigging must LOWER the raw implied probability"


def test_shin_and_proportional_differ_on_a_lopsided_price():
    """The sensitivity must actually be a different number, or reporting it is
    decoration (a 'sensitivity' that equals the primary tests nothing)."""
    d = mb.american_to_decimal([-400, +320])
    ph, _ = mb.novig_proportional([d[0]], [d[1]])
    sh, _ = mb.novig_shin([d[0]], [d[1]])
    assert abs(ph[0] - sh[0]) > 1e-4
    assert 0.0 < sh[0] < 1.0


def test_a_flat_stake_win_pays_decimal_minus_one_and_a_loss_pays_minus_one():
    f = _frame([_row(1, "NYY", "BOS", -200, +170, True)])
    arm = next(a for a in mb.REGISTERED_ARMS if a.arm_id == "road_all")
    bets = mb.bet_series(f, arm)
    assert len(bets) == 1
    assert bool(bets["won"].iloc[0]) is False          # road side lost
    assert bets["pnl"].iloc[0] == pytest.approx(-1.0, abs=1e-12)

    f2 = _frame([_row(1, "NYY", "BOS", -200, +170, False)])
    bets2 = mb.bet_series(f2, arm)
    assert bets2["pnl"].iloc[0] == pytest.approx(2.7 - 1.0, abs=1e-12)


def test_the_favorite_buckets_partition_every_non_pickem_game():
    """A1/A2/A3 must be disjoint AND exhaustive over non-pick'em games — a gap
    would silently drop games from family A, an overlap would double-count them."""
    rows = [_row(i, "NYY", "BOS", am, -am + 20, i % 2 == 0)
            for i, am in enumerate([-350, -260, -200, -199, -170, -140, -139, -120, -105], start=1)]
    f = _frame(rows)
    fam_a = [a for a in mb.REGISTERED_ARMS if a.family == "A_favorite_longshot"]
    masks = [a.eligible(f).to_numpy(dtype=bool) for a in fam_a]
    stacked = np.vstack(masks).sum(axis=0)
    assert (stacked == 1).all(), f"favorite buckets are not a partition: {stacked}"


def test_a_pickem_is_excluded_from_every_favorite_referencing_arm():
    f = _frame([_row(1, "NYY", "BOS", -110, -110, True)])
    for arm in mb.REGISTERED_ARMS:
        if arm.arm_id in ("road_all", "fade_marquee"):
            continue
        assert not arm.eligible(f).any(), f"{arm.arm_id} admitted a pick'em"


def test_fade_marquee_bets_against_the_marquee_side_on_both_orientations():
    f = _frame([_row(1, "NYY", "PIT", -150, +130, True),     # marquee at HOME
                _row(2, "PIT", "NYY", +130, -150, True)])    # marquee on the ROAD
    arm = next(a for a in mb.REGISTERED_ARMS if a.arm_id == "fade_marquee")
    assert arm.eligible(f).tolist() == [True, True]
    # game 1: fade NYY => bet the road side; game 2: fade NYY => bet the home side
    assert arm.bet_home(f).tolist() == [False, True]


def test_a_marquee_vs_marquee_game_is_not_eligible():
    f = _frame([_row(1, "NYY", "BOS", -120, +100, True)])
    for aid in ("fade_marquee", "fade_marquee_fav"):
        arm = next(a for a in mb.REGISTERED_ARMS if a.arm_id == aid)
        assert not arm.eligible(f).any(), f"{aid} admitted a marquee-vs-marquee game"


def test_road_all_is_exactly_road_dog_plus_road_fav():
    rows = [_row(i, "NYY", "PIT", am, -am + 20, i % 2 == 0)
            for i, am in enumerate([-350, -120, +140, +200], start=1)]
    f = _frame(rows)
    by = {a.arm_id: a for a in mb.REGISTERED_ARMS}
    n_all = int(by["road_all"].eligible(f).sum())
    n_split = int(by["road_dog"].eligible(f).sum() + by["road_fav"].eligible(f).sum())
    assert n_all == n_split


def test_the_oracle_anchor_never_loses_a_bet():
    rows = [_row(i, "NYY", "PIT", -150, +130, i % 2 == 0) for i in range(1, 9)]
    f = _frame(rows)
    oracle = next(a for a in mb.ANCHORS if a.arm_id == "anchor_oracle_winner")
    bets = mb.bet_series(f, oracle)
    assert bets["won"].all(), "the oracle floor must win every bet by construction"
    assert bets["pnl"].min() > 0


def test_all_home_is_the_exact_mirror_of_road_all():
    rows = [_row(i, "NYY", "PIT", -150, +130, i % 3 == 0) for i in range(1, 13)]
    f = _frame(rows)
    road = next(a for a in mb.REGISTERED_ARMS if a.arm_id == "road_all")
    home = next(a for a in mb.ANCHORS if a.arm_id == "anchor_all_home")
    assert (mb.bet_series(f, road)["won"].to_numpy()
            == ~mb.bet_series(f, home)["won"].to_numpy()).all()


def test_benjamini_hochberg_is_computed_over_the_full_declared_field():
    """The cutoff must scale with the FULL registered list — computing it over a
    surviving subset is the 28.2 subset-mining trap."""
    keep, cutoff = mb.benjamini_hochberg([0.001] + [0.9] * 7, alpha=0.05)
    assert keep[0] and not any(keep[1:])
    assert cutoff == pytest.approx(0.05 * 1 / 8, abs=1e-12)
    # a 2-element field would give a 4x looser cutoff — proof the size matters
    _, cutoff_small = mb.benjamini_hochberg([0.001, 0.9], alpha=0.05)
    assert cutoff_small > cutoff


def test_an_empty_bucket_scores_zero_not_missing():
    """A flat-stake rule that did not fire returns 0. A NaN would break CSCV; a
    dropped row would silently change the arm's population."""
    rows = [_row(1, "NYY", "PIT", -350, +290, True, month=4),
            _row(2, "PIT", "CIN", -105, -115, True, month=5)]
    f = _frame(rows)
    M, buckets = mb.bucket_matrix(f, mb.REGISTERED_ARMS)
    assert M.shape == (len(buckets), 8)
    assert np.isfinite(M).all(), "bucket matrix must be finite everywhere"
    heavy = [a.arm_id for a in mb.REGISTERED_ARMS].index("dog_vs_heavy_fav")
    may = buckets.index("2024-05")
    assert M[may, heavy] == 0.0
