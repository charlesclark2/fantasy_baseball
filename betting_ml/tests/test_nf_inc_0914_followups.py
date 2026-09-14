"""NF-INC-0914 follow-ups — the build's own record must survive a multi-leg build, and a
draft-board MARKET vintage must not page for ten months about an input nobody can act on.

🔴 FOLLOW-UP 1 — A LAST-WRITER-WINS COUNTER BESIDE AN ACCUMULATING ONE. The 2026-09-14 restore
published `rows_moved: 86` beside `designated_rows_on_frame: 0`. `designation_games_callable` is
invoked ONCE PER LEG (veteran, then rookie — `run_season_projection` hands both the SAME `row_log`)
and the two counters were written differently: `rows_moved` with `+=`, `designated_rows_on_frame`
with `=`. The rookie leg, carrying no designated rows, clobbered the veteran leg's 86.

⭐ PROVABLY AN OVERWRITE, NOT A MISFIRE — and the proof is structural rather than empirical: within
ONE call `moved` only increments after the null-label guard, so `moved <= designated` always holds
and 86-beside-0 cannot be produced by a single pass.

⛔ IT WAS NOT COSMETIC. `run_nf_inj4b_ship_battery --verify-published` short-circuits on
`designated in (None, 0)` and returned a FALSE `⛔ UNVERIFIABLE` (exit 2) — disabling the ONLY
automated per-row check the designation discount has, on a board where the discount had in fact
reached all 86 rows.

⭐ THE FIX IS DELIBERATELY ONE LINE. A first cut also added a "reached but correctly unmoved"
bucket, on the theory that a player already below his cap would otherwise read as a missed discount
once the counter accumulated. That was wrong on a MEASURED fact: `remaining_season_rate_cap` is a
RATE, not a ceiling (the PM ruled the ceiling form out on 2026-08-23 because it moved 5 of 6 real
rows by zero), so a priceable designated row always moves and `designated - moved` was already an
honest miss count. The elaboration was dropped rather than shipped; a clause below pins the rate
property instead, so if the form ever changes the guard says so rather than the consumer quietly
false-alarming.

🔴 FOLLOW-UP 2 — A BAR THAT PAGES FOR TEN MONTHS ABOUT AN IRRELEVANT INPUT. ADP and ECR are MARKET
inputs to a DRAFT board; once week 1 kicks off nobody drafts off it, so a stale market cannot reach
a user decision (operator, 2026-09-14). Left alone, the 96h bar pages on every weekly publish from
mid-September to August with no action available — the muted-monitor pattern.

⭐ THE LAG IS STILL MEASURED AND STILL PUBLISHED on the `[METRIC]` line year-round; only the PAGE is
withheld. That is the difference between suppressing an alert and creating a blind spot (NF1.7 (a)).
And the seasonal boundary reuses `is_draft_season` — the predicate that ALREADY owns the publish
cadence — rather than inventing a second one (INC-30/36/38).

Also corrected here: the ECR bar's `why` text called it "the expert-consensus reference column
shown beside every projection". It is not a display column — `nf1_3_model` builds
`market_rank = ecr.where(ecr.notna(), adp)` (ECR-PRIMARY) and `nf1_5_model` imports that module, so
a stale ECR shifts WITHIN-POSITION ORDERING. An alert that understates its own blast radius invites
under-reaction.
"""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from betting_ml.monitoring import nfl_board_freshness as NBF
from quant_sports_intel_models.football.nfl.fantasy import designation_discount_serving as DDS

_FIXTURE = Path(__file__).parent / "fixtures" / "nf_infra2_published_manifest.json"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The build's record survives a multi-leg build
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _leg(pids: list[str], games: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"player_id": pids, "proj_games": games})


def test_the_designated_count_accumulates_across_legs_like_the_moved_count():
    """The incident's exact shape: a second leg carrying NO designated rows must not zero the first.

    ⭐ This is the clause that fails on the historical break — with `=` the rookie leg's 0 lands on
    the record and the served manifest publishes `moved: 2` beside `designated: 0`."""
    log: dict = {}
    cb = DDS.designation_games_callable(
        2026, designations={"v1": "Out", "v2": "Questionable"}, row_log=log)

    cb(_leg(["v1", "v2"], [17.0, 17.0]))          # veteran leg — 2 designated
    assert log["designated_rows_on_frame"] == 2 and log["rows_moved"] == 2

    cb(_leg(["r1", "r2"], [17.0, 17.0]))          # rookie leg — 0 designated
    assert log["rows_moved"] == 2, "moved must not regress"
    assert log["designated_rows_on_frame"] == 2, (
        "the designated count must ACCUMULATE like `rows_moved` beside it — a leg with no "
        "designated rows overwrote the total and published `moved: 86` beside `designated: 0` "
        "on 2026-09-14, which made --verify-published return a false UNVERIFIABLE")


def test_a_priceable_designated_row_always_moves_so_designated_minus_moved_is_an_honest_miss():
    """⭐ WHY THERE IS NO "reached but unmoved" BUCKET — measured, not assumed.

    The first cut of this fix added one, on the theory that a player already projected below his
    cap is reached and correctly left alone. That rests on the cap being a CEILING. It is not:
    `remaining_season_rate_cap` is a RATE (`current x (17 - missed)/17`), and the PM ruled the
    ceiling form OUT on 2026-08-23 precisely because it moved 5 of 6 real rows by zero.

    So even a deep backup at 0.4 projected games moves, and `designated - moved` remains an honest
    miss count. This pins that property, because the moment it stops holding the consumer's strict
    `moved < designated` clause starts false-alarming — and the tempting repair would be to weaken
    a guard rather than to notice the form had changed."""
    log: dict = {}
    cb = DDS.designation_games_callable(2026, designations={"deep": "Questionable"}, row_log=log)
    out = cb(_leg(["deep"], [0.4]))

    assert out[0] < 0.4 - 1e-9, (
        "a rate cap must reduce even a tiny projection — if this fails the cap has become a "
        "ceiling and `designated - moved` is no longer a miss count")
    assert log["rows_moved"] == 1 and log["designated_rows_on_frame"] == 1
    assert "rows_already_at_cap" not in log, (
        "no at-cap bucket should exist under a rate cap; adding one would invite weakening the "
        "consumer's miss clause for a state that cannot occur")


def test_every_designated_row_on_a_healthy_frame_is_accounted_for_as_moved():
    """`designated == moved` on finite, positively-projected rows — the invariant the consumer's
    `moved < designated` clause depends on."""
    log: dict = {}
    cb = DDS.designation_games_callable(
        2026, designations={"a": "Out", "b": "Questionable", "c": "Doubtful"}, row_log=log)
    cb(_leg(["a", "b", "c", "undesignated"], [17.0, 0.3, 12.0, 17.0]))

    assert log["designated_rows_on_frame"] == 3, "the undesignated row must not be counted"
    assert log["rows_moved"] == 3, "every priceable designated row moves under a rate cap"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The market vintages page in draft season and go quiet after it — still measured either way
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_market_feeds_are_declared_draft_season_only_and_the_model_input_is_not():
    """ADP/ECR are seasonal; `depth_chart_as_of` is a year-round model input and must stay armed."""
    by_name = {s.name: s for s in NBF.REQUIRED_FEED_STAMPS}
    assert by_name["adp_as_of"].draft_season_only is True
    assert by_name["ecr_as_of"].draft_season_only is True
    assert by_name["depth_chart_as_of"].draft_season_only is False, (
        "the depth chart decays into the PROJECTION itself, not into a draft-time ordering — it "
        "must keep paging out of season")


def test_the_ecr_reason_names_the_ordering_feature_not_a_display_column():
    """The alert must not understate its own blast radius.

    ECR is ECR-PRIMARY in `market_rank` (`nf1_3_model`, consumed by `nf1_5_model`), so a stale ECR
    shifts within-position ordering. The retired wording is asserted ABSENT as well as the new one
    present — a presence-only check cannot see a partial revert."""
    why = {s.name: s.why for s in NBF.REQUIRED_FEED_STAMPS}["ecr_as_of"]
    assert "market_rank" in why and "ORDERING" in why.upper()
    assert "reference column shown beside every projection" not in why, (
        "the retired wording described ECR as a display column; it is an ordering feature")


@pytest.mark.parametrize(
    "day,armed",
    [(date(2026, 8, 1), True),     # draft season opens
     (date(2026, 9, 15), True),    # last day of the window
     (date(2026, 9, 17), True),    # inside the boundary lookback — still armed, the SAFE direction
     (date(2026, 9, 18), False),   # clear of it
     (date(2026, 12, 1), False)],  # deep out of season
)
def test_market_inputs_matter_errs_toward_keeping_the_page_armed(day, armed):
    """⭐ `any` over the lookback, the MIRROR of `cadence_hours`' `all`.

    There, erring toward the looser bar is safe. Here the ALERT is what is at stake, so the safe
    direction is to keep paging — two extra days rather than going quiet one day early. It also
    absorbs the UTC-vs-Pacific skew between this monitor and the publish schedule."""
    assert NBF.market_inputs_matter(day) is armed


def test_the_same_board_pages_in_season_and_goes_quiet_after_it_while_still_measuring():
    """Two-sided, on the committed real manifest: identical bytes, two dates.

    ⛔ The MEASUREMENT must survive in both — a suppressed page that also stopped measuring would
    be a blind spot, not a fatigue fix (NF1.7 (a))."""
    blob = json.loads(_FIXTURE.read_text())
    started = datetime.fromisoformat(blob["generated_at"]) - timedelta(hours=0.5)
    stale = datetime.fromisoformat(blob["generated_at"]) + timedelta(hours=96.0 + 24)

    in_season = NBF.verify_manifest(blob, started=started, now=stale)
    assert NBF.market_inputs_matter(stale.date()), "fixture precondition: this date is in season"
    assert any(a.startswith("ecr_as_of") for a in in_season["alerts"]), (
        "inside draft season a stale ECR must still page — the bar is not loosened")

    out = stale.replace(month=12, day=1)
    off_season = NBF.verify_manifest(blob, started=started, now=out)
    assert not any(a.startswith("ecr_as_of") for a in off_season["alerts"]), (
        "out of season a stale market vintage must not page — nobody can act on it")
    assert off_season["stamps"]["ecr_as_of"] is not None, (
        "the lag must still be MEASURED and reported out of season — withholding the page must "
        "never become withholding the measurement")
    assert any(a.startswith("depth_chart") for a in off_season["alerts"]), (
        "the year-round model input must still page out of season, or this change has silenced "
        "more than the market feeds")


def test_a_missing_market_stamp_is_still_FATAL_out_of_season():
    """Seasonality gates the STALENESS page only. An ABSENT vintage is a different fact — the board
    shipped not knowing what it was built on — and stays fatal year-round."""
    blob = json.loads(_FIXTURE.read_text())
    blob.pop("ecr_as_of")
    started = datetime.fromisoformat(blob["generated_at"]) - timedelta(hours=0.5)
    res = NBF.verify_manifest(blob, started=started,
                              now=datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert any("ecr_as_of" in f for f in res["fatal"]), res


def test_the_seasonal_gate_reuses_the_cadence_owner_rather_than_a_second_boundary():
    """One logical boundary, one owner (INC-30/36/38). `market_inputs_matter` must be defined in
    terms of `is_draft_season`, not a re-spelled month/day window that can drift away from it."""
    src = Path(NBF.__file__).read_text()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "market_inputs_matter")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "is_draft_season" in called, (
        "the seasonal gate must delegate to the cadence owner; a second hand-written window is "
        "the one-logical-thing-many-owners shape this repo keeps paying for")
