"""NCAAF-CLV-repair — the vs-close eval reads the rows that carry a close.

`bakeoff_ncaaf_game._clv_eval` (P1.4 → S1-serve) and `ncaaf_val1_clv_week_strat.score_config`
(VAL1) both selected their close-carrying rows with `df[mask].reset_index(drop=True)` and then
indexed the `(n_games, n_draws)` predictive-draw array with the RESET index `0..n−1` — the FIRST n
rows of the draw array, not the rows carrying a close. NCAAF-VAL2 §2 measured it at 100 % of 4,182
rows misindexed, with the model's side agreeing with `sign(μ − close)` on 0.697 instead of 0.980.

⭐ WHY A SOURCE GUARD IS NOT ENOUGH HERE, and what actually makes this file bite: the defect's
symptom is NOISE. The repaired and the broken read produce hit rates that are individually
plausible, and on this very cache the ATS leg lands on **exactly 2039/4110 both ways** while 46 % of
the underlying sides flip. A before/after comparison of the headline number is therefore incapable
of telling the two apart. So the load-bearing test below is NUMERICAL: it drives the REAL
`_clv_eval` over draws whose row index is recoverable from their value, where the repaired and the
broken read give opposite, unambiguous answers.

Replaces the deliberate `..._is_still_present_TRIPWIRE` guard in the NCAAF-VAL2 suite, whose
docstring required the repair to ship with re-runs of P1.4, S1-serve and VAL1. Those ran; see
`ablation_results/ncaaf_val1_clv_week_strat.md` §0 and `ncaaf_clv_row_alignment_repair.md`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as B
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val1_clv_week_strat as V1

#: the two repaired call sites: (module, function name)
CALL_SITES = ((B, "_clv_eval"), (V1, "score_config"))


def _fn_source(mod, name: str) -> str:
    """The function's source with COMMENTS AND DOCSTRING STRIPPED.

    ⛔ Load-bearing (INC-38): the repair's own comments quote the defect verbatim — "`m.index` after
    `reset_index(drop=True)`" — so a raw text scan would match the PROSE explaining the fix and pass
    on source where the fix had been deleted. `ast.unparse` drops comments; the docstring is dropped
    explicitly. Prose must not be able to satisfy this file.
    """
    tree = ast.parse(Path(mod.__file__).read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    body = list(fn.body)
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return "\n".join(ast.unparse(s) for s in body)


@pytest.mark.parametrize("mod,name", CALL_SITES, ids=lambda v: getattr(v, "__name__", v))
def test_the_true_row_positions_are_recovered_before_any_reset(mod, name):
    """`np.flatnonzero(mask)` must be taken BEFORE the frame is re-indexed.

    Order is the whole defect: after `reset_index(drop=True)` the original positions are GONE, so a
    recovery taken afterwards cannot be a recovery."""
    src = _fn_source(mod, name)
    assert "np.flatnonzero(" in src, f"{name}: no `np.flatnonzero` — the true positions are not recovered"
    assert src.index("np.flatnonzero(") < src.index("reset_index(drop=True)"), (
        f"{name}: `np.flatnonzero` is taken AFTER `reset_index(drop=True)`; by then the original "
        "row positions no longer exist and the recovery is not one")


@pytest.mark.parametrize("mod,name", CALL_SITES, ids=lambda v: getattr(v, "__name__", v))
def test_a_reset_index_is_never_used_as_a_draw_array_index(mod, name):
    """The defect in one line: `idx = m.index.to_numpy()` on a reset frame."""
    src = _fn_source(mod, name)
    assert "m.index.to_numpy()" not in src, (
        f"{name}: reads `m.index` off a reset frame — that is `0..n−1`, the FIRST n rows of the "
        "draw array, not the rows carrying a close (NCAAF-VAL2 §2)")


@pytest.mark.parametrize("mod,name", CALL_SITES, ids=lambda v: getattr(v, "__name__", v))
def test_the_merge_row_count_is_asserted_because_the_read_is_positional(mod, name):
    """`merged` row i must BE `dists[...][i]`.

    The recovered positions index the draw arrays, which are built from `oos`. That correspondence
    survives the close join only while the join neither drops nor duplicates a row — a duplicated
    close key would silently re-index every read. `build_offset_frame` (VAL2) already asserted this;
    the two eval paths did not."""
    tree = ast.parse(Path(mod.__file__).read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    # ⭐ Read the CONDITION of a HALTing `if`, and require it to BE the row-count comparison — not
    # merely to CONTAIN it. Asserting the substring is vacuous: `if False and len(merged) != ...`
    # keeps the text and disables the HALT, and the RED proof caught exactly that (the E11.24 #815
    # "a break that lands but does not move the asserted predicate" class).
    halting = [ast.unparse(n.test).strip() for n in ast.walk(fn)
               if isinstance(n, ast.If) and any(isinstance(c, ast.Raise) for c in ast.walk(n))]
    assert "len(merged) != len(oos)" in halting, (
        f"{name}: no REACHABLE HALT is conditioned on exactly the close join's row-count "
        f"invariant (halting conditions found: {halting}); the positional read below it is "
        "unsound under a duplicated close key")


def test_the_repaired_eval_reads_the_rows_that_carry_a_close():
    """⭐ THE NUMERICAL GUARD — drives the REAL `_clv_eval`.

    Draw row `i` is the constant `i`, so the value read NAMES the row it came from. Only the last
    half of the games carry a close, and each close is set just below its OWN row's constant. So:

      * reading the TRUE positions  → every draw is above its line → model takes OVER / HOME
      * reading the reset `0..n−1`  → every draw is far below      → model takes UNDER / AWAY

    and the realised outcomes are set so the OVER/HOME side always wins. A repaired read scores
    1.0; the broken read scores 0.0. There is no tolerance and no near-50 % ambiguity to hide in —
    which is exactly what the headline hit rate could not provide.
    """
    n_games, n_close = 300, 150
    first = n_games - n_close                       # close-carrying rows are 150..299
    gid = np.arange(n_games)
    # row i's draws are all exactly `i` — the value identifies the row
    draws = np.repeat(gid.astype(float)[:, None], 8, axis=1)
    dists = {"margin": draws, "total": draws}

    oos = pd.DataFrame({
        "game_id": gid,
        # realised outcomes sit ABOVE every line, so OVER / HOME is always the winning side
        "y_margin": np.full(n_games, 10_000.0),
        "y_total": np.full(n_games, 10_000.0),
    })
    true_pos = np.arange(first, n_games, dtype=float)
    df = pd.DataFrame({
        "game_id": gid,
        "has_close": gid >= first,
        # line just below the TRUE row's constant  ⇒ true read is over/home, reset read is under/away
        "close_total": np.where(gid >= first, gid - 0.5, np.nan).astype(float),
        "close_home_spread": np.where(gid >= first, -(gid - 0.5), np.nan).astype(float),
    })
    assert len(true_pos) == n_close

    out = B._clv_eval(oos, df, dists, np.random.default_rng(0))
    assert out["n_with_close"] == n_close, "the close selection itself changed"
    assert out["ou_hit_rate"] == 1.0, (
        f"O/U side is wrong ({out['ou_hit_rate']}): the eval read rows 0..n−1 of the draw array "
        "instead of the rows carrying a close (NCAAF-VAL2 §2)")
    assert out["ats_hit_rate"] == 1.0, (
        f"ATS side is wrong ({out['ats_hit_rate']}): same misaligned read on the margin leg")


def test_the_numerical_guard_would_catch_the_original_defect():
    """Two-sided: the fixture must be able to FAIL, or it certifies nothing (NF1.7(a)).

    Replays the ORIGINAL broken index (`0..n−1`) over the same fixture and asserts it scores 0.0 —
    the opposite extreme. A fixture on which broken and repaired both score 1.0 would be decoration.
    """
    n_games, n_close = 300, 150
    first = n_games - n_close
    gid = np.arange(n_games)
    draws = np.repeat(gid.astype(float)[:, None], 8, axis=1)
    tot_line = np.arange(first, n_games, dtype=float) - 0.5
    y_t = np.full(n_close, 10_000.0)

    as_coded = np.arange(n_close)                       # the defect: the reset index
    repaired = np.flatnonzero(gid >= first)             # the fix: true positions

    def ou_hit(idx: np.ndarray) -> float:
        p_over = (draws[idx] > tot_line[:, None]).mean(axis=1)
        return float(np.where(p_over >= 0.5, y_t > tot_line, y_t < tot_line).mean())

    assert ou_hit(repaired) == 1.0
    assert ou_hit(as_coded) == 0.0, "the fixture cannot distinguish the broken read — it proves nothing"


def test_val1_pins_its_reproduction_target_to_the_repaired_parent_not_its_own_output():
    """§2a is a PARENT check. Its targets must name the S1-serve run they came from.

    The pre-repair targets (`ats_n` 4114 / `ou_hit` 0.513) were produced by the misaligned read, so
    the pin was pinning a number the defect made. Re-anchored onto S1-serve's repaired re-run — and
    ⛔ never onto VAL1's own output, which would make the pin a restatement of the thing it checks.
    """
    assert V1.PIN["source"].startswith("ncaaf_s1_serve_calibration"), \
        "the pin does not record which parent run its targets came from"
    assert "repaired" in V1.PIN["source"], "the pin does not record that the parent was repaired"
    assert V1.PIN["source_n_with_close"] and V1.PIN["source_cache_assembled_at"], \
        "the pin does not record the cache vintage its targets are bound to"
    # the clause itself is unchanged: strict on population, tolerant on rates
    assert V1.PIN["tol"] == 0.010
    good = {"ats": {"n": V1.PIN["ats_n"], "hit_rate": V1.PIN["ats_hit"], "placebo": V1.PIN["ats_placebo"]},
            "ou": {"n": V1.PIN["ou_n"], "hit_rate": V1.PIN["ou_hit"], "placebo": 0.50}}
    assert V1.check_pin(good)["all_ok"] is True
    assert V1.check_pin({**good, "ou": {**good["ou"], "n": V1.PIN["ou_n"] - 1}})["all_ok"] is False
    assert V1.check_pin({**good, "ou": {**good["ou"],
                                        "hit_rate": V1.PIN["ou_hit"] + 2 * V1.PIN["tol"]}})["all_ok"] is False
