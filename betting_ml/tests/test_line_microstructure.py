"""Fast-gate tests for E13.16 line-movement microstructure (betting_ml/utils/line_microstructure.py).

All synthetic — NO S3 / Snowflake / network, and NO `pipeline` import (the fast gate has no dbt
manifest → importing pipeline crashes at collection; per CLAUDE.md, fast-gate tests import only from
`betting_ml`). Proves the pure math (trajectory features, CLV signs, forced sides), the engine's
detect-AND-reject behaviour (a planted reversion FIRES; an efficient martingale + the placebo control
stay NULL), and the anti-data-mining discipline (game-level collapse, deflation).
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils import line_microstructure as lm
from betting_ml.scripts.line_microstructure.eval_line_microstructure import make_smoke_frame

_MODULE = Path(lm.__file__)


# ── source-inspection guard: the module must NOT import `pipeline` (fast-gate safety) ────────────
def test_module_does_not_import_pipeline():
    tree = ast.parse(_MODULE.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "pipeline" not in imported, f"line_microstructure must not import pipeline; got {imported}"


# ── trajectory features ──────────────────────────────────────────────────────────────────────
def test_trajectory_features_drift_and_reversals():
    # up, up, down, up → one reversal at each sign flip: +,+,-,+ → flips at idx 1→2 and 2→3 = 2
    vals = [8.0, 8.5, 9.0, 8.0, 8.5]
    hours = [6.0, 4.5, 3.0, 1.5, 1.0]
    f = lm.trajectory_features(vals, hours)
    assert f["n_snaps"] == 5
    assert f["open_val"] == 8.0 and f["close_val"] == 8.5
    assert f["open_close_gap"] == pytest.approx(0.5)
    assert f["n_reversals"] == 2
    assert f["max_excursion"] == pytest.approx(1.0)      # peak at 9.0 = +1.0 from open
    assert f["path_length"] == pytest.approx(0.5 + 0.5 + 1.0 + 0.5)


def test_trajectory_features_monotone_no_reversal():
    f = lm.trajectory_features([7.0, 7.5, 8.0], [3.0, 2.0, 1.0])
    assert f["n_reversals"] == 0
    assert f["retention"] == pytest.approx(1.0)          # all of the move stuck


def test_nearest_anchor_idx():
    hours = [6.0, 4.5, 3.0, 1.5, 1.0]   # window 6→1, span 5h
    assert lm.nearest_anchor_idx(hours, 0.0) == 0        # open
    assert lm.nearest_anchor_idx(hours, 1.0) == 4        # close
    # 50% ⇒ target 3.5h ⇒ nearest is 3.0 (idx 2)
    assert lm.nearest_anchor_idx(hours, 0.5) == 2


# ── CLV signs (beat-the-close) ─────────────────────────────────────────────────────────────────
def test_clv_runs_signs():
    # over: you want the number to RISE; anchor 8.0 → close 8.5 ⇒ beat close by +0.5
    assert lm.clv_runs("over", 8.0, 8.5) == pytest.approx(0.5)
    assert lm.clv_runs("under", 8.0, 8.5) == pytest.approx(-0.5)
    assert lm.clv_runs("under", 9.0, 8.0) == pytest.approx(1.0)
    assert np.isnan(lm.clv_runs("over", np.nan, 8.5))


def test_clv_prob_signs():
    # home: fair prob rose 0.50→0.55 after you bet ⇒ +0.05 CLV
    assert lm.clv_prob("home", 0.50, 0.55) == pytest.approx(0.05)
    assert lm.clv_prob("away", 0.50, 0.55) == pytest.approx(-0.05)  # away side prob fell
    assert lm.clv_prob("away", 0.60, 0.50) == pytest.approx(0.10)


# ── build_decisions: forced sides are trajectory-only ─────────────────────────────────────────
def _mini_totals_frame(game_pk=2, line_path=(8.0, 8.8, 8.6, 8.2, 7.6)):
    """One game, one book, totals, 5 snaps with a specified line path."""
    hours = [6.0, 4.5, 3.0, 1.5, 1.0]
    rows = []
    for h, lv in zip(hours, line_path):
        row = {c: np.nan for c in lm.__dict__.get("DEC_COLS", [])}  # placeholder
        rows.append({"game_pk": game_pk, "season": 2026, "ym": "2026-05", "book": "bovada",
                     "market": "totals", "snapshot_ts": f"2026-05-01T{int(24 - h):02d}:00:00Z",
                     "hours_to_commence": h, "line": lv, "fair_over": 0.5, "fair_home": np.nan,
                     "over_price": -110, "under_price": -110, "home_price": np.nan,
                     "away_price": np.nan, "realized_total": 9.0, "home_won": 1.0})
    return pd.DataFrame(rows)


def test_build_decisions_reversion_and_continuation_opposite_sides():
    # line moves UP early (8.0→8.8, +0.8 ≥ θ) then reverts DOWN to 7.6 by close.
    dec = lm.build_decisions(_mini_totals_frame())
    rev = dec[(dec["signal"] == "reversion") & (dec["anchor"] == "t50")]
    con = dec[(dec["signal"] == "continuation") & (dec["anchor"] == "t50")]
    assert len(rev) == 1 and len(con) == 1
    # early move is UP ⇒ reversion bets UNDER (against), continuation bets OVER (with)
    assert rev["side"].iloc[0] == "under"
    assert con["side"].iloc[0] == "over"
    # reversion CLV at t50 (line 8.6) → close (7.6): under ⇒ 8.6 − 7.6 = +1.0 (beat the close)
    assert rev["clv"].iloc[0] == pytest.approx(1.0)
    assert con["clv"].iloc[0] == pytest.approx(-1.0)
    # trigger magnitude = |open→t50 move| = |8.6 − 8.0| = 0.6
    assert rev["trigger_mag"].iloc[0] == pytest.approx(0.6)


def test_build_decisions_static_and_placebo_present():
    dec = lm.build_decisions(_mini_totals_frame(game_pk=2))
    sigs = set(dec["signal"])
    assert {"static_over", "static_under", "placebo"} <= sigs
    # placebo side is game_pk parity — game_pk 2 is even ⇒ 'over' for totals
    assert dec[dec["signal"] == "placebo"]["side"].iloc[0] == "over"
    dec_odd = lm.build_decisions(_mini_totals_frame(game_pk=3))
    assert dec_odd[dec_odd["signal"] == "placebo"]["side"].iloc[0] == "under"


def test_build_decisions_coarse_game_only_static():
    # a 2-snap (open+close only) game has NO interior anchor ⇒ path signals are excluded (logged)
    hours = [3.0, 1.0]
    rows = [{"game_pk": 4, "season": 2026, "ym": "2026-05", "book": "bovada", "market": "totals",
             "snapshot_ts": f"2026-05-01T{int(24 - h):02d}:00:00Z", "hours_to_commence": h,
             "line": lv, "fair_over": 0.5, "fair_home": np.nan, "over_price": -110,
             "under_price": -110, "home_price": np.nan, "away_price": np.nan,
             "realized_total": 9.0, "home_won": 1.0} for h, lv in zip(hours, (8.0, 8.5))]
    dec = lm.build_decisions(pd.DataFrame(rows))
    assert (dec["signal"] == "reversion").sum() == 0     # no interior anchor
    assert (dec["signal"] == "static_over").sum() == 1   # static still computable


# ── stale-quote filter (adversarial control) ────────────────────────────────────────────────
def _snap_row(game_pk, book, market, hour, line=np.nan, fair_home=np.nan):
    return {"game_pk": game_pk, "season": 2026, "ym": "2026-05", "book": book, "market": market,
            "snapshot_ts": f"2026-05-01T{int(hour):02d}:00:00Z", "hours_to_commence": 24 - hour,
            "line": line, "fair_over": np.nan, "fair_home": fair_home, "over_price": -110,
            "under_price": -110, "home_price": np.nan, "away_price": np.nan,
            "realized_total": np.nan, "home_won": np.nan}


def test_drop_stale_snaps_removes_off_market_outlier_keeps_marketwide_move():
    # same hour-bucket, 4 books: three agree at 8.5, one is a stale 10.5 outlier (>0.75 off) → dropped
    rows = [_snap_row(1, b, "totals", 20, line=8.5) for b in ["pinnacle", "betmgm", "fanduel"]]
    rows.append(_snap_row(1, "bovada", "totals", 20, line=10.5))     # stale spike
    # a later bucket where the WHOLE market moved to 9.5 (market-wide) → all kept
    rows += [_snap_row(1, b, "totals", 22, line=9.5) for b in ["pinnacle", "betmgm", "fanduel", "bovada"]]
    kept, stats = lm.drop_stale_snaps(pd.DataFrame(rows))
    assert stats["n_stale_dropped"] == 1
    # the stale bovada 10.5 outlier is dropped; the market-wide bovada 9.5 is kept
    assert not ((kept["book"] == "bovada") & (kept["line"] == 10.5)).any()
    assert ((kept["book"] == "bovada") & (kept["line"] == 9.5)).any()


def test_drop_stale_snaps_keeps_thin_buckets():
    # only 2 books in the bucket (< min_books=3) → no reliable consensus → nothing dropped even if apart
    rows = [_snap_row(2, "pinnacle", "totals", 20, line=8.5),
            _snap_row(2, "bovada", "totals", 20, line=10.5)]
    kept, stats = lm.drop_stale_snaps(pd.DataFrame(rows))
    assert stats["n_stale_dropped"] == 0 and len(kept) == 2


# ── the engine: detect the planted edge, reject the control + the efficient market ──────────────
@pytest.fixture(scope="module")
def smoke_eval():
    # 260 games keeps the deflation out of the small-sample-noise regime; the four consumers are
    # marked `slow` (>5s to build the decisions) so they land in the slow job, not the fast gate.
    frame = make_smoke_frame(n_games=260, seed=3)
    dec = lm.build_decisions(frame)
    return lm.evaluate(dec)


@pytest.mark.slow
def test_placebo_control_never_survives(smoke_eval):
    assert not smoke_eval["candidates"]["control_breaks"], \
        "placebo (trajectory-independent side) must NOT produce a surviving candidate"


@pytest.mark.slow
def test_planted_reversion_fires(smoke_eval):
    real = smoke_eval["candidates"]["candidates"]
    assert real, "the planted totals reversion should surface at least one candidate"
    assert any(c["signal"] == "reversion" and c["market"] == "totals" for c in real)


@pytest.mark.slow
def test_totals_grid_is_not_overfit_but_h2h_is_efficient(smoke_eval):
    # planted totals signal ⇒ PBO low (persists OOS); martingale h2h ⇒ PBO high (no persistence)
    pbo_tot = smoke_eval["markets"]["totals"]["deflation"]["pbo"]["pbo"]
    assert pbo_tot < 0.2, f"totals PBO should be low with a planted signal; got {pbo_tot}"
    h2h = smoke_eval["markets"].get("h2h")
    if h2h and np.isfinite(h2h["deflation"]["pbo"].get("pbo", np.nan)):
        assert not any(c["market"] == "h2h" for c in smoke_eval["candidates"]["candidates"]), \
            "the efficient (martingale) h2h market must yield no candidate"


@pytest.mark.slow
def test_configs_scored_game_level(smoke_eval):
    # n (unique games) must never exceed the games in that market (quotes collapsed to games)
    for mk, mv in smoke_eval["markets"].items():
        for c in mv["configs"]:
            assert c["n"] <= mv["n_games"]
            assert c["n_quotes"] >= c["n"]               # quotes ≥ games (collapse happened)
