"""E9.48 — guards for the injury / IL status fix.

The bug (2026-07-29): player pages served a WRONG IL status for 62 of the 187 players
flagged as currently on the Injured List. Jesús Luzardo read "On IL since 2024-06-19"
while starting for Philadelphia on 2026-07-24. `is_current` means "no later classified
event exists", so ONE missed clearing event pins a player as injured forever — silently,
across seasons.

Two things are pinned here:
  1. The GUARD's pure logic (betting_ml/monitoring/injury_status_health.py), two-sided:
     it must FAIL on the known-bad shape AND PASS on the known-good one. A boolean gate
     proven only against bad input can be inverted and nobody would know (CLAUDE.md).
  2. The MODEL's classification rules, by source inspection — the specific patterns
     whose absence caused the outage. These are cheap and text-based on purpose: they
     make a silent removal of a clearing rule a red test rather than a stale badge.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from betting_ml.monitoring.injury_status_health import (
    IMPLAUSIBLE,
    OK,
    STALE,
    UNKNOWN,
    classify_feed_freshness,
    classify_il_plausibility,
    summarize,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STG_MODEL = REPO_ROOT / "dbt" / "models" / "staging" / "statsapi" / "stg_statsapi_player_injury_status.sql"
GUARD_SCRIPT = REPO_ROOT / "scripts" / "check_injury_status_health.py"
DAILY_OPS = REPO_ROOT / "pipeline" / "ops" / "daily_ingestion_ops.py"
DAILY_JOB = REPO_ROOT / "pipeline" / "jobs" / "daily_ingestion_job.py"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Feed freshness — the "frozen at a date" class
# ─────────────────────────────────────────────────────────────────────────────

class TestFeedFreshness:
    def test_a_current_feed_passes(self):
        c = classify_feed_freshness(date(2026, 7, 28), asof=date(2026, 7, 29))
        assert c.status == OK and c.ok

    def test_a_frozen_feed_is_stale(self):
        """The signature of the off-season hole: the newest transaction is months old,
        so every IL status is pinned to that date."""
        c = classify_feed_freshness(date(2026, 3, 1), asof=date(2026, 7, 29))
        assert c.status == STALE and not c.ok
        assert "2026-03-01" in c.detail

    def test_the_boundary_is_two_sided(self):
        asof = date(2026, 7, 29)
        assert classify_feed_freshness(date(2026, 7, 25), asof, max_lag_days=4).ok
        assert not classify_feed_freshness(date(2026, 7, 24), asof, max_lag_days=4).ok

    def test_an_empty_read_is_unknown_never_ok(self):
        """A read that returns nothing is the silent-empty class (E9.26b) — it must
        never be scored as healthy."""
        c = classify_feed_freshness(None, asof=date(2026, 7, 29))
        assert c.status == UNKNOWN and not c.ok


# ─────────────────────────────────────────────────────────────────────────────
# 2. IL plausibility — the E9.48 bug signature itself
# ─────────────────────────────────────────────────────────────────────────────

class TestIlPlausibility:
    def test_the_observed_bad_state_fails(self):
        """The live pre-fix numbers (2026-07-29): 299 of 784 current-IL players had
        played since their il_since."""
        c = classify_il_plausibility(current_il_count=784, played_since_il_start=299)
        assert c.status == IMPLAUSIBLE and not c.ok

    def test_the_observed_fixed_state_passes(self):
        """The live post-fix numbers over the same data: 429 flagged, 0 implausible."""
        c = classify_il_plausibility(current_il_count=429, played_since_il_start=0)
        assert c.status == OK and c.ok

    def test_a_single_mis_flagged_player_fails(self):
        """One Luzardo is a trust failure — the tolerance is exactly zero."""
        assert not classify_il_plausibility(400, 1).ok

    def test_an_empty_il_population_is_unknown_never_ok(self):
        c = classify_il_plausibility(current_il_count=0, played_since_il_start=0)
        assert c.status == UNKNOWN and not c.ok

    def test_summarize_names_every_failing_check(self):
        ok, banner = summarize([
            classify_feed_freshness(date(2026, 3, 1), asof=date(2026, 7, 29)),
            classify_il_plausibility(784, 299),
        ])
        assert not ok
        assert "feed_freshness" in banner and "il_plausibility" in banner

    def test_summarize_is_ok_when_both_pass(self):
        ok, _ = summarize([
            classify_feed_freshness(date(2026, 7, 28), asof=date(2026, 7, 29)),
            classify_il_plausibility(429, 0),
        ])
        assert ok


# ─────────────────────────────────────────────────────────────────────────────
# 3. The model's clearing rules — the three mechanisms that caused the outage
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def model_sql() -> str:
    return STG_MODEL.read_text()


class TestClearingRulesArePresentInBothBranches:
    """Both branches must carry the same rules — a dual-branch model where only one
    side got the fix serves a wrong status on whichever target runs (INC-19 class)."""

    @staticmethod
    def _branches(sql: str) -> list[str]:
        duck, rest = sql.split("{% if target.name == 'duckdb' %}", 1)
        duck_body, sf_body = rest.split("{% else %}", 1)
        return [duck_body, sf_body.split("{% endif %}")[0]]

    def test_bare_activation_is_classified_as_a_clear(self, model_sql):
        """Mechanism (a) — 21 players. 'Tampa Bay Rays activated RHP Drew Rasmussen.'
        has no list suffix, so requiring '%from the % injured list%' dropped it."""
        for body in self._branches(model_sql):
            assert "description ilike '%activated%'" in body
            assert "description ilike '%reinstated%'" in body

    def test_roster_moves_clear_the_il(self, model_sql):
        """Mechanism (b) — 29 players. You cannot be recalled / selected / optioned
        while on the MLB IL (Anthony Volpe returned via OPT → CU, never an SC)."""
        for body in self._branches(model_sql):
            assert "type_code in ('CU', 'SE', 'OPT')" in body

    def test_moves_compatible_with_being_injured_do_not_clear(self, model_sql):
        """The inverse guard: a player CAN be traded, claimed, released or DFA'd while
        still injured, so those type codes must never clear an IL interval."""
        for body in self._branches(model_sql):
            clearing = body.split("type_code in (")[1].split(")")[0]
            for code in ("'TR'", "'CLW'", "'REL'", "'DES'", "'OUT'", "'DFA'"):
                assert code not in clearing, f"{code} must not clear an IL interval"

    def test_an_appearance_truncates_an_injured_interval(self, model_sql):
        """Mechanism (c) — the ground-truth backstop, and the only rule immune to a
        Stats API rewording or the off-season feed hole."""
        for body in self._branches(model_sql):
            assert "appearance_close" in body
            assert "mart_batter_rolling_stats" in body
            assert "mart_pitcher_rolling_stats" in body
            assert "min(a.game_date)" in body

    def test_placement_is_evaluated_before_any_clear(self, model_sql):
        """Precedence matters: a description containing both 'activated' and 'on the
        … injured list' must read as a PLACEMENT, never as a clear."""
        for body in self._branches(model_sql):
            placement = body.index("description ilike '% on the % injured list%'")
            bare_clear = body.index("description ilike '%activated%'")
            assert placement < bare_clear

    def test_the_window_order_is_deterministic(self, model_sql):
        """`order by event_date` alone tie-broke arbitrarily between runs, so same-day
        events could produce different intervals on identical input."""
        for body in self._branches(model_sql):
            assert body.count("order by event_date, try_cast(transaction_id as bigint), transaction_id") >= 3

    def test_the_output_column_contract_is_unchanged(self, model_sql):
        """The lakehouse_ext external table pins 6 columns — interval_seq is a join key
        and must not leak into the output (a schema change would break the ext table)."""
        for body in self._branches(model_sql):
            final_select = body.rsplit("from with_next_event w", 1)[0].rsplit("select", 1)[1]
            assert "interval_seq" not in final_select
            for col in ("player_id", "player_name", "status_start_date",
                        "status_end_date", "type_code", "is_injured"):
                assert col in final_select


def _code_only(src: str) -> str:
    """Source with comments and docstrings stripped — these guards must assert on what
    the script DOES, not on what its prose mentions."""
    import ast

    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    return ast.unparse(tree)


class TestGuardIsWired:
    def test_the_guard_runs_in_the_daily_job(self):
        assert "check_injury_status_health_op" in DAILY_JOB.read_text()

    def test_the_op_is_alert_tier_not_halt(self):
        """E11.7: an IL badge is a profile adornment — a stale feed must not take down
        the slate. It must still WARN loudly (never a silent `pass`)."""
        src = DAILY_OPS.read_text()
        op = src.split("def check_injury_status_health_op")[1].split("\n@op")[0]
        assert "context.log.warning" in op
        assert "INJURY_STATUS_STRICT" in op

    def test_the_guard_is_snowflake_free(self):
        """The injury chain is fully migrated; a Snowflake read here would be a red
        flag (CLAUDE.md §0.5) and would not run on the box's serving path."""
        code = _code_only(GUARD_SCRIPT.read_text())
        assert "snowflake" not in code.lower()
        assert "register_lakehouse_views" in code

    def test_the_guard_uses_the_baseball_day_not_utc(self):
        """INC-22: the box runs UTC, so date.today() rolls a day early in US evenings."""
        code = _code_only(GUARD_SCRIPT.read_text())
        assert "current_game_date" in code
        assert "date.today()" not in code
        assert "utcnow" not in code
