"""Unit tests for the Epic A1 intraday feature-assembly overlay
(betting_ml/utils/data_loader.py).

Covers the pure, I/O-free helpers that overlay today's lineup + starter
features (incl. EB posteriors) onto the carried-forward team row:
  - _platoon_weighted        — handedness-weighted starter-split adjustment
  - _enrich_row_with_today   — non-null overlay + handedness recompute
  - _load_todays_lineup_starter — prefix mapping / meta-column exclusion
  - _resolve_team_id         — cross-source team-name → team_id resolution
"""

import ast
from decimal import Decimal
from pathlib import Path

from betting_ml.utils.data_loader import (
    _enrich_row_with_today,
    _load_todays_lineup_starter,
    _platoon_weighted,
    _resolve_team_id,
)


# ── _platoon_weighted ──────────────────────────────────────────────────────────

class TestPlatoonWeighted:
    def test_weighted_average_is_correct(self):
        # 6 RHB, 3 LHB → 2/3 weight on vs_rhb, 1/3 on vs_lhb
        # (2/3)*0.300 + (1/3)*0.360 = 0.320
        assert _platoon_weighted(6, 3, 0.300, 0.360) == 0.320

    def test_all_rhb_uses_only_vs_rhb(self):
        assert _platoon_weighted(9, 0, 0.310, 0.400) == 0.310

    def test_none_input_returns_none(self):
        assert _platoon_weighted(6, 3, None, 0.360) is None
        assert _platoon_weighted(None, 3, 0.300, 0.360) is None

    def test_zero_denominator_returns_none(self):
        assert _platoon_weighted(0, 0, 0.300, 0.360) is None

    def test_decimal_and_str_inputs_are_coerced(self):
        # Cursor values can arrive as Decimal or str; must not raise.
        assert _platoon_weighted(Decimal("6"), Decimal("3"), Decimal("0.300"), "0.360") == 0.320


# ── _enrich_row_with_today ─────────────────────────────────────────────────────

class TestEnrichRowWithToday:
    def _carried_forward_row(self):
        # Stale values from each team's last completed game.
        return {
            "home_avg_eb_woba": 0.111,            # lineup col — should be overlaid
            "away_avg_eb_woba": 0.222,
            "home_starter_eb_xwoba_against": 0.999,  # starter col — should be overlaid
            "home_off_woba_30d": 0.345,           # team-level — must be preserved
            "home_rhb_count": 1, "home_lhb_count": 1,  # stale; overlaid below
        }

    def _today_dicts(self):
        lineup = {
            (1, "home"): {"home_avg_eb_woba": 0.350, "home_rhb_count": 6, "home_lhb_count": 3},
            (1, "away"): {"away_avg_eb_woba": 0.360, "away_rhb_count": 5, "away_lhb_count": 4},
        }
        starter = {
            (1, "home"): {
                "home_starter_eb_xwoba_against": 0.280,
                "home_starter_xwoba_vs_rhb": 0.300, "home_starter_xwoba_vs_lhb": 0.360,
                "home_starter_k_pct_vs_rhb": 0.25, "home_starter_k_pct_vs_lhb": 0.22,
                "home_starter_bb_pct_vs_rhb": 0.07, "home_starter_bb_pct_vs_lhb": 0.09,
            },
            (1, "away"): {
                "away_starter_xwoba_vs_rhb": 0.310, "away_starter_xwoba_vs_lhb": 0.330,
                "away_starter_k_pct_vs_rhb": 0.24, "away_starter_k_pct_vs_lhb": 0.20,
                "away_starter_bb_pct_vs_rhb": 0.08, "away_starter_bb_pct_vs_lhb": 0.10,
            },
        }
        return lineup, starter

    def test_overlay_replaces_stale_with_today_values(self):
        row = self._carried_forward_row()
        lineup, starter = self._today_dicts()
        n = _enrich_row_with_today(row, 1, lineup, starter)
        assert n == 4  # home+away lineup, home+away starter
        assert row["home_avg_eb_woba"] == 0.350      # overlaid, not 0.111
        assert row["away_avg_eb_woba"] == 0.360
        assert row["home_starter_eb_xwoba_against"] == 0.280

    def test_team_level_columns_are_preserved(self):
        row = self._carried_forward_row()
        lineup, starter = self._today_dicts()
        _enrich_row_with_today(row, 1, lineup, starter)
        assert row["home_off_woba_30d"] == 0.345  # not touched by lineup/starter overlay

    def test_null_today_value_does_not_overwrite_carried_forward(self):
        row = {"home_avg_eb_woba": 0.111}
        lineup = {(1, "home"): {"home_avg_eb_woba": None}}
        _enrich_row_with_today(row, 1, lineup, {})
        assert row["home_avg_eb_woba"] == 0.111  # NULL must not clobber

    def test_handedness_adjustment_is_recomputed_from_overlaid_values(self):
        row = self._carried_forward_row()
        lineup, starter = self._today_dicts()
        _enrich_row_with_today(row, 1, lineup, starter)
        # home lineup (6 RHB / 3 LHB) vs away starter splits (0.310 / 0.330):
        # (2/3)*0.310 + (1/3)*0.330 = 0.317
        assert row["home_lineup_vs_away_starter_xwoba_adj"] == 0.317
        # away lineup (5 RHB / 4 LHB) vs home starter splits (0.300 / 0.360):
        # (5/9)*0.300 + (4/9)*0.360 = 0.327
        assert row["away_lineup_vs_home_starter_xwoba_adj"] == 0.327

    def test_no_overlay_when_game_absent(self):
        row = {"home_avg_eb_woba": 0.111}
        n = _enrich_row_with_today(row, 999, {}, {})
        assert n == 0
        assert row["home_avg_eb_woba"] == 0.111

    def test_has_full_lineup_forced_false_when_no_overlay(self):
        # Carried-forward row falsely marks the game confirmed (stale last-game
        # value); with no lineup overlay today both flags must become False.
        row = {"home_has_full_lineup": True, "away_has_full_lineup": True}
        _enrich_row_with_today(row, 999, {}, {})
        assert row["home_has_full_lineup"] is False
        assert row["away_has_full_lineup"] is False

    def test_has_full_lineup_true_when_overlaid(self):
        row = {}
        lineup = {
            (1, "home"): {"home_has_full_lineup": True},
            (1, "away"): {"away_has_full_lineup": True},
        }
        _enrich_row_with_today(row, 1, lineup, {})
        assert row["home_has_full_lineup"] is True
        assert row["away_has_full_lineup"] is True

    def test_has_full_lineup_false_when_only_one_side_overlaid(self):
        row = {"home_has_full_lineup": True, "away_has_full_lineup": True}
        lineup = {(1, "home"): {"home_has_full_lineup": True}}  # away missing
        _enrich_row_with_today(row, 1, lineup, {})
        assert row["home_has_full_lineup"] is True
        assert row["away_has_full_lineup"] is False


# ── _load_todays_lineup_starter (prefix mapping) ───────────────────────────────

class _FakeCursor:
    def __init__(self, lineup_desc, lineup_rows, starter_desc, starter_rows):
        self._lineup = (lineup_desc, lineup_rows)
        self._starter = (starter_desc, starter_rows)
        self._mode = None

    def execute(self, sql):
        self._mode = "lineup" if "lineup_features" in sql else "starter"

    @property
    def description(self):
        return self._lineup[0] if self._mode == "lineup" else self._starter[0]

    def fetchall(self):
        return self._lineup[1] if self._mode == "lineup" else self._starter[1]


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class TestLoadTodaysLineupStarter:
    def test_prefixing_and_meta_exclusion(self):
        lineup_desc = [("GAME_PK",), ("SIDE",), ("GAME_DATE",), ("GAME_YEAR",), ("AVG_EB_WOBA",)]
        lineup_rows = [
            (1, "home", "2026-06-09", 2026, 0.35),
            (1, "away", "2026-06-09", 2026, 0.36),
        ]
        starter_desc = [("GAME_PK",), ("SIDE",), ("GAME_DATE",), ("GAME_YEAR",), ("EB_XWOBA_AGAINST",)]
        starter_rows = [(1, "home", "2026-06-09", 2026, 0.28)]

        conn = _FakeConn(_FakeCursor(lineup_desc, lineup_rows, starter_desc, starter_rows))
        lineup_by_game, starter_by_game = _load_todays_lineup_starter(conn, "2026-06-09")

        # Lineup col AVG_EB_WOBA -> {side}_avg_eb_woba; meta cols excluded.
        assert lineup_by_game[(1, "home")] == {"home_avg_eb_woba": 0.35}
        assert lineup_by_game[(1, "away")] == {"away_avg_eb_woba": 0.36}
        # Starter col EB_XWOBA_AGAINST -> {side}_starter_eb_xwoba_against.
        assert starter_by_game[(1, "home")] == {"home_starter_eb_xwoba_against": 0.28}
        # game_pk / game_date / game_year / side must not leak into the overlay.
        for d in lineup_by_game.values():
            assert not any(k.endswith(("game_pk", "game_date", "game_year", "side")) for k in d)

    def test_unknown_side_is_skipped(self):
        desc = [("GAME_PK",), ("SIDE",), ("AVG_EB_WOBA",)]
        rows = [(1, "switch", 0.30)]  # not home/away
        conn = _FakeConn(_FakeCursor(desc, rows, desc, []))
        lineup_by_game, _ = _load_todays_lineup_starter(conn, "2026-06-09")
        assert lineup_by_game == {}


# ── _resolve_team_id ───────────────────────────────────────────────────────────

class TestResolveTeamId:
    # Mirrors a slice of dim_team_name_lookup: every Athletics name variant and
    # the canonical Brewers name resolve through the same {name_lower -> team_id}.
    _LOOKUP = {
        "athletics": 13,
        "oakland athletics": 13,
        "sacramento athletics": 13,
        "las vegas athletics": 13,
        "milwaukee brewers": 158,
    }

    def test_athletics_variants_resolve_to_same_team_id(self):
        assert _resolve_team_id("Oakland Athletics", self._LOOKUP) == 13
        assert _resolve_team_id("Sacramento Athletics", self._LOOKUP) == 13
        assert _resolve_team_id("Athletics", self._LOOKUP) == 13

    def test_canonical_name_resolves(self):
        assert _resolve_team_id("Milwaukee Brewers", self._LOOKUP) == 158

    def test_doubleheader_marker_is_stripped(self):
        # Consumer contract: strip the Parlay "G1 "/"G2 " prefix before matching.
        assert _resolve_team_id("G1 Oakland Athletics", self._LOOKUP) == 13
        assert _resolve_team_id("G2 Milwaukee Brewers", self._LOOKUP) == 158

    def test_unmapped_name_returns_none(self):
        # Non-MLB / unknown feed names must not resolve to a team.
        assert _resolve_team_id("Sultanes de Monterrey", self._LOOKUP) is None

    def test_none_passthrough(self):
        assert _resolve_team_id(None, self._LOOKUP) is None


# ── import guard (repo convention: ast.walk, not string search) ────────────────

class TestImportGuard:
    def test_data_loader_does_not_import_training_only_modules(self):
        """The serving-time loader must not pull heavy training-only modules.

        Uses ast.walk over the parsed module (not a substring search) so that a
        mention in a comment/string does not trip the check.
        """
        src = Path(__file__).resolve().parents[1] / "utils" / "data_loader.py"
        tree = ast.parse(src.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = {"mlflow", "betting_ml.models.total_runs_trainer"}
        assert not (imported & forbidden), f"forbidden imports present: {imported & forbidden}"
