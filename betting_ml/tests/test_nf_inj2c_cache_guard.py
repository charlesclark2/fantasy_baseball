"""NF-INJ2c — `cache_is_current` must guard the family of the cache it protects.

🧨 THE DEFECT (2026-09-03). `run_nf1_5.build_pool` guarded its **120-column** pool with
`run_nf1_2.cache_is_current(cached)`, whose family defaults to `M12.REFINEMENT_COLS` — NF1.2's
OWN **20** columns. The guard therefore validated 20/120 and was structurally blind to the other
100. A Jul-31 cache missing **5** of NF1.5's registered columns was served as "current" for over
a month, silently degrading every local NF1.5 fit, and cost three VOIDed NF-INJ2c node-3b runs
before the cause was found (the reproduction pin moved 5.64 → 1.82 the moment the pool rebuilt).

A guard that checks a DIFFERENT family than the cache it protects cannot fail for the reason it
exists — the NF1.7(a) vacuous-anchor class, sitting in the build path rather than in a test.
"""
from __future__ import annotations

import re

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf1_2_model as M12
from quant_sports_intel_models.football.nfl.fantasy import nf1_3_model as M13
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_2 import (
    cache_is_current,
    missing_registered_cols,
)

_SRC = __import__("pathlib").Path(N15.__file__)


def _strip_comments(src: str) -> str:
    """INC-38: a source-inspection guard that prose can satisfy is not a guard."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


@pytest.fixture(scope="module")
def registered() -> list[str]:
    cols = sorted(N15.POOL_REQUIRED_COLS)
    assert cols, "POOL_REQUIRED_COLS is empty — every assertion below would pass on nothing"
    return cols


@pytest.fixture()
def complete_pool(registered: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: [1.0, 2.0] for c in registered})


# ── the historical case ───────────────────────────────────────────────────────────────────────
def _five_unchecked_by_the_old_family(registered: list[str]) -> list[str]:
    """5 registered columns OUTSIDE NF1.2's family — i.e. exactly where the real 5 went missing."""
    outside = [c for c in registered if c not in set(M12.REFINEMENT_COLS)]
    assert len(outside) >= 5, (
        "fewer than 5 registered columns sit outside NF1.2's family — the historical case can no "
        "longer be reproduced, so this test would be vacuous")
    return outside[:5]


def test_a_pool_missing_five_registered_columns_REFUSES(complete_pool, registered):
    """The exact historical shape: 5 of the registered columns absent ⇒ rebuild, never trust."""
    dropped = _five_unchecked_by_the_old_family(registered)
    stale = complete_pool.drop(columns=dropped)
    assert len(stale.columns) == len(registered) - 5

    assert cache_is_current(stale, N15.POOL_REQUIRED_COLS) is False
    assert missing_registered_cols(stale, N15.POOL_REQUIRED_COLS) == sorted(dropped)


def test_the_OLD_behaviour_would_have_PASSED_that_same_pool(complete_pool, registered):
    """The regression that proves the fix bites, not merely that the new code is self-consistent.

    Guarding with NF1.2's family — the pre-fix default — accepts the very pool the fix refuses."""
    stale = complete_pool.drop(columns=_five_unchecked_by_the_old_family(registered))
    assert cache_is_current(stale, M12.REFINEMENT_COLS) is True, (
        "the pre-fix family no longer accepts the stale pool — this regression can no longer "
        "demonstrate the defect and must be re-anchored, not deleted")
    assert cache_is_current(stale, N15.POOL_REQUIRED_COLS) is False


def test_a_complete_pool_is_still_accepted(complete_pool):
    """The fix must not turn every healthy cache into a rebuild."""
    assert cache_is_current(complete_pool, N15.POOL_REQUIRED_COLS) is True
    assert missing_registered_cols(complete_pool, N15.POOL_REQUIRED_COLS) == []


def test_an_absent_or_empty_pool_refuses(registered):
    """NF1.7(a): unevaluable is never a pass."""
    assert cache_is_current(None, N15.POOL_REQUIRED_COLS) is False
    assert cache_is_current(pd.DataFrame(), N15.POOL_REQUIRED_COLS) is False


# ── the anti-drift property ───────────────────────────────────────────────────────────────────
def test_the_required_family_is_DERIVED_so_a_new_feature_joins_without_an_edit(registered):
    """Hand-listing is how the guard rotted in the first place; assert it is computed."""
    expected = (
        {c for feats in M13.POSITION_FEATURES.values() for c in feats}
        | set(M13.MARKET_FEATURES)
        | set(M12.REFINEMENT_COLS)
        | {"real_fp_ppr", "real_games"}
    )
    assert set(N15.POOL_REQUIRED_COLS) == expected


def test_the_family_covers_every_column_the_learners_consume(registered):
    """The set whose absence can change a fit must be inside the guarded family."""
    consumed = {c for feats in M13.POSITION_FEATURES.values() for c in feats}
    assert consumed, "POSITION_FEATURES is empty — this assertion would pass on nothing"
    assert consumed <= set(N15.POOL_REQUIRED_COLS)


def test_the_family_is_strictly_wider_than_the_one_that_rotted():
    """20/120 was the blind spot; the fix must measurably widen it."""
    assert set(M12.REFINEMENT_COLS) < set(N15.POOL_REQUIRED_COLS)
    assert len(N15.POOL_REQUIRED_COLS) > 2 * len(M12.REFINEMENT_COLS)


# ── wired ≠ invoked ───────────────────────────────────────────────────────────────────────────
def test_build_pool_actually_passes_the_family_to_the_guard():
    """NF-C0e: a constant that exists but reaches no call site is not a guard."""
    src = _strip_comments(_SRC.read_text())
    calls = re.findall(r"missing_registered_cols\(\s*cached\s*,\s*POOL_REQUIRED_COLS\s*\)", src)
    assert calls, (
        "run_nf1_5.build_pool no longer guards its cache with POOL_REQUIRED_COLS — the pool would "
        "again be validated against a family that is not its own")
    assert "def build_pool" in src
