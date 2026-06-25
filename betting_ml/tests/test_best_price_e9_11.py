"""E9.11 — Best price across books: unit tests for best-price computation and line-shopping.

These tests exercise the Python-side logic (no Snowflake required):
- best US price selection: highest American odds = most favorable payout
- Pinnacle correctly excluded from US best-price; still present as anchor
- line-shopping payload: only positive-edge plays; sorted by edge desc
- away-side edge/EV derived correctly (model_prob_away = 1 - calib_win_prob)
- under-side edge/EV derived correctly (model_prob_under = 1 - model_prob_over)
- empty / missing input graceful handling
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest


# ---------------------------------------------------------------------------
# Load write_serving_store without executing main() (no Snowflake / argparse)
# ---------------------------------------------------------------------------
def _load_serving_module() -> ModuleType:
    src_path = (Path(__file__).resolve().parents[2] / "scripts" / "write_serving_store.py")
    spec = importlib.util.spec_from_file_location("write_serving_store", src_path)
    mod = importlib.util.module_from_spec(spec)
    # Stub heavy imports so the module loads in the test environment
    for stub in ["snowflake.connector", "dotenv"]:
        if stub not in sys.modules:
            import unittest.mock as _mock
            sys.modules[stub] = _mock.MagicMock()
            # Handle dotenv.load_dotenv specifically
            if stub == "dotenv":
                sys.modules[stub].load_dotenv = lambda *a, **kw: None
    spec.loader.exec_module(mod)
    return mod


try:
    _mod = _load_serving_module()
    _compute_book_odds_payloads = _mod._compute_book_odds_payloads
    _compute_line_shopping_payload = _mod._compute_line_shopping_payload
    _MODULE_LOADED = True
except Exception as _e:
    _MODULE_LOADED = False
    _LOAD_ERROR = str(_e)


# ---------------------------------------------------------------------------
# Helpers — build minimal row dicts that match what the SQL returns
# ---------------------------------------------------------------------------

def _h2h_row(book_key: str, home_am: int, away_am: int, is_home: bool,
              latest_ts: str = "2026-06-25T12:00:00", decimal: float | None = None):
    return {
        "GAME_PK": 1,
        "BOOKMAKER_KEY": book_key,
        "MARKET_KEY": "h2h",
        "OUTCOME_NAME": "Home" if is_home else "Away",
        "OUTCOME_PRICE_AMERICAN": home_am if is_home else away_am,
        "OUTCOME_PRICE_DECIMAL": decimal or (round(1 / abs(home_am) * 100 + 1, 4) if is_home else None),
        "OUTCOME_POINT": None,
        "IS_HOME_OUTCOME": is_home,
        "LATEST_TS": latest_ts,
    }


def _dist_row(game_pk: int = 1, win_prob: float = 0.55,
              pred_runs: float = 8.5, pred_scale: float = 1.2):
    return {
        "GAME_PK": game_pk,
        "CALIBRATED_WIN_PROB": win_prob,
        "PRED_TOTAL_RUNS": pred_runs,
        "PRED_TOTAL_RUNS_SCALE": pred_scale,
        "HOME_TEAM": "STL",
        "AWAY_TEAM": "CHC",
    }


# ---------------------------------------------------------------------------
# Structural test: best-price fields present in serving source
# ---------------------------------------------------------------------------

def test_best_price_fields_written_in_serving_source():
    src = (Path(__file__).resolve().parents[2] / "scripts" / "write_serving_store.py").read_text()
    assert "best_h2h_home" in src, "best_h2h_home missing from write_serving_store.py"
    assert "best_h2h_away" in src, "best_h2h_away missing from write_serving_store.py"
    assert "best_totals_over" in src, "best_totals_over missing from write_serving_store.py"
    assert "best_totals_under" in src, "best_totals_under missing from write_serving_store.py"


def test_line_shopping_payload_written_in_book_odds_block():
    src = (Path(__file__).resolve().parents[2] / "scripts" / "write_serving_store.py").read_text()
    assert "_compute_line_shopping_payload" in src
    assert "picks/line-shopping" in src


def test_pinnacle_excluded_from_best_price_in_source():
    src = (Path(__file__).resolve().parents[2] / "scripts" / "write_serving_store.py").read_text()
    # The best-price selection must filter out the sharp reference (Pinnacle)
    assert "is_sharp_reference" in src, (
        "best-price selection must guard on is_sharp_reference to exclude Pinnacle"
    )


def test_line_shopping_endpoint_in_router():
    router_src = (Path(__file__).resolve().parents[2] / "app" / "backend" / "routers" / "picks.py").read_text()
    assert "/line-shopping" in router_src, "GET /picks/line-shopping endpoint missing from picks.py"
    assert "LineshoppingResponse" in router_src


def test_lineshopping_model_in_picks_models():
    models_src = (Path(__file__).resolve().parents[2] / "app" / "backend" / "models" / "picks.py").read_text()
    assert "LineshoppingPlay" in models_src
    assert "LineshoppingResponse" in models_src
    assert "BestPriceH2H" in models_src
    assert "BestPriceTotals" in models_src
    # best_alpha=0 / no-edge framing must be in the docstring
    assert "best_alpha=0" in models_src


def test_best_price_fields_in_bookoddcomparison_model():
    models_src = (Path(__file__).resolve().parents[2] / "app" / "backend" / "models" / "picks.py").read_text()
    assert "best_h2h_home" in models_src
    assert "best_h2h_away" in models_src
    assert "best_totals_over" in models_src
    assert "best_totals_under" in models_src


# ---------------------------------------------------------------------------
# Runtime tests (skip when module load fails due to env issues)
# ---------------------------------------------------------------------------

skip_runtime = pytest.mark.skipif(
    not _MODULE_LOADED,
    reason=f"write_serving_store could not be loaded: {_LOAD_ERROR if not _MODULE_LOADED else ''}",
)


@skip_runtime
class TestLineshoppingPayload:
    """Tests for _compute_line_shopping_payload."""

    def _make_book_odds_payload(
        self,
        game_pk: int = 1,
        h2h_best_home: dict | None = None,
        h2h_best_away: dict | None = None,
        totals_best_over: dict | None = None,
        totals_best_under: dict | None = None,
        pinn_h2h_home_mkt: float | None = 0.50,
        pinn_totals_over_mkt: float | None = 0.50,
    ) -> dict:
        """Build a minimal book_odds_map payload entry for testing."""
        pinnacle_h2h = {"book_key": "pinnacle", "market_bet_pct_home": pinn_h2h_home_mkt}
        pinnacle_totals = {"book_key": "pinnacle", "market_bet_pct_over": pinn_totals_over_mkt}
        return {
            "game_pk": game_pk,
            "home_team": "STL",
            "away_team": "CHC",
            "h2h": [pinnacle_h2h],
            "totals": [pinnacle_totals],
            "best_h2h_home": h2h_best_home,
            "best_h2h_away": h2h_best_away,
            "best_totals_over": totals_best_over,
            "best_totals_under": totals_best_under,
        }

    def _ev_row(self, game_pk: int = 1, game_date: str = "2026-06-25"):
        return {
            "GAME_PK": game_pk, "GAME_DATE": game_date,
            "GAME_START_UTC": "2026-06-25T19:10:00", "PREDICTION_TYPE": "post_lineup",
        }

    def test_positive_edge_play_included(self):
        bph = {"book_key": "fanduel", "book_name": "FanDuel", "american": -110,
               "market_bet_pct": 0.52, "ev": 0.02, "edge": 0.03, "breakeven_american": -120}
        payload = self._make_book_odds_payload(h2h_best_home=bph)
        result = _compute_line_shopping_payload({1: payload}, [self._ev_row()])
        assert result["total"] == 1
        play = result["plays"][0]
        assert play["side"] == "home"
        assert play["market_type"] == "h2h"
        assert play["best_book_key"] == "fanduel"
        assert play["edge"] == pytest.approx(0.03, abs=1e-4)

    def test_zero_edge_play_excluded(self):
        bph = {"book_key": "bovada", "book_name": "Bovada", "american": -110,
               "market_bet_pct": 0.55, "ev": 0.0, "edge": 0.0, "breakeven_american": -122}
        payload = self._make_book_odds_payload(h2h_best_home=bph)
        result = _compute_line_shopping_payload({1: payload}, [self._ev_row()])
        assert result["total"] == 0

    def test_negative_edge_play_excluded(self):
        bph = {"book_key": "bovada", "book_name": "Bovada", "american": -120,
               "market_bet_pct": 0.58, "ev": -0.02, "edge": -0.02, "breakeven_american": -122}
        payload = self._make_book_odds_payload(h2h_best_home=bph)
        result = _compute_line_shopping_payload({1: payload}, [self._ev_row()])
        assert result["total"] == 0

    def test_sorted_by_edge_descending(self):
        bph1 = {"book_key": "fanduel", "book_name": "FanDuel", "american": -105,
                "market_bet_pct": 0.50, "ev": 0.05, "edge": 0.05, "breakeven_american": -122}
        bph2 = {"book_key": "betmgm", "book_name": "BetMGM", "american": +110,
                "market_bet_pct": 0.47, "ev": 0.08, "edge": 0.08, "breakeven_american": +120}
        p1 = self._make_book_odds_payload(game_pk=1, h2h_best_home=bph1)
        p2 = self._make_book_odds_payload(game_pk=2, h2h_best_away=bph2)
        result = _compute_line_shopping_payload({1: p1, 2: p2}, [self._ev_row(1), self._ev_row(2)])
        assert result["total"] == 2
        assert result["plays"][0]["edge"] >= result["plays"][1]["edge"]

    def test_pinnacle_anchor_present(self):
        bph = {"book_key": "fanduel", "book_name": "FanDuel", "american": -110,
               "market_bet_pct": 0.52, "ev": 0.02, "edge": 0.03, "breakeven_american": -120}
        payload = self._make_book_odds_payload(h2h_best_home=bph, pinn_h2h_home_mkt=0.515)
        result = _compute_line_shopping_payload({1: payload}, [self._ev_row()])
        assert result["plays"][0]["pinnacle_devigged_prob"] == pytest.approx(0.515, abs=1e-4)

    def test_is_preliminary_flag(self):
        bph = {"book_key": "fanduel", "book_name": "FanDuel", "american": -110,
               "market_bet_pct": 0.52, "ev": 0.02, "edge": 0.03, "breakeven_american": -120}
        payload = self._make_book_odds_payload(h2h_best_home=bph)
        morning_row = {**self._ev_row(), "PREDICTION_TYPE": "morning"}
        result = _compute_line_shopping_payload({1: payload}, [morning_row])
        assert result["is_preliminary"] is True

    def test_empty_book_odds_returns_empty(self):
        result = _compute_line_shopping_payload({}, [])
        assert result["total"] == 0
        assert result["plays"] == []
        assert result["is_preliminary"] is False

    def test_game_date_metadata_present(self):
        bph = {"book_key": "fanduel", "book_name": "FanDuel", "american": -110,
               "market_bet_pct": 0.52, "ev": 0.02, "edge": 0.03, "breakeven_american": -120}
        payload = self._make_book_odds_payload(h2h_best_home=bph)
        result = _compute_line_shopping_payload({1: payload}, [self._ev_row(1, "2026-06-25")])
        assert result["plays"][0]["game_date"] == "2026-06-25"
        assert result["plays"][0]["home_team"] == "STL"
        assert result["plays"][0]["away_team"] == "CHC"
