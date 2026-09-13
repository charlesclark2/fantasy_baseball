"""NF-INJ4b-SHIP — the SHIP's own invariants: the served object, the wiring, and the one thing that
keeps the user-facing copy honest.

⭐ **WHAT THIS SUITE IS FOR, stated because it is not the model's suite.** NF-INJ4b's nine gates are
SETTLED and are never re-read here (E2.1-r): this story measures the SHIP, not the model. What can
still go wrong is everything between a certified arm and a served board — the wrong constants, a
build-time re-fit, a channel nobody calls, a rollback that moves the code but not the copy.

⛔ **THE DECLARATION-VS-PRODUCTION CLAUSE IS THE LOAD-BEARING ONE** and it runs in BOTH directions.
NF-C0e names the failure where a declaration outruns its production (a field wired everywhere and
computed nowhere). NF-INJ4b-SHIP can fail the mirror image too: the discount serves while the copy
still says we ignore it. Both are invisible on a rendered board — a games figure looks identical
either way — so neither is caught by looking.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import (
    designation_discount_policy as POLICY,
)
from quant_sports_intel_models.football.nfl.fantasy import (
    designation_discount_serving as DDS,
)
from quant_sports_intel_models.football.nfl.fantasy import (
    nf_inj4_designation_duration as DD,
)
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

_REPO = Path(__file__).resolve().parents[2]
_FANTASY = _REPO / "quant_sports_intel_models/football/nfl/fantasy"
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_DECISIVE = _FANTASY / "ablation_results/nf_inj4b_designation_duration.json"
_COUNTERFACTUAL = _FANTASY / "ablation_results/nf_inj4b_counterfactual.json"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. THE SERVED OBJECT IS THE CERTIFIED ONE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_served_arm_is_the_one_the_decisive_run_certified():
    """⛔ NF-INJ4b §3b(3), as a guard. The counterfactual's first magnitude table priced the
    REGISTERED arm instead of the CERTIFIED WINNER — `out ×0.8682` against `×0.8639` — and produced
    a plausible, wrong operator packet. A transcription slip has no symptom; it has to be pinned."""
    decisive = json.loads(_DECISIVE.read_text())
    assert decisive["ship"] is True, "the decisive run no longer records ship=True"
    assert POLICY.ARM == decisive["winner"], (
        f"the policy serves {POLICY.ARM!r} but the decisive run certified {decisive['winner']!r}")
    artifact = json.loads(
        (_FANTASY / "served_artifacts" / POLICY.ARTIFACT_FILENAME).read_text())
    assert artifact["arm"] == decisive["winner"], (
        "the persisted serving artifact was fitted from a different arm than the certified winner")


def test_the_served_constants_are_the_ones_in_the_operator_packet():
    """⭐ The operator's ship decision is made against the counterfactual's magnitude table. If the
    board served different numbers, they would have approved one thing and shipped another — and
    nothing downstream would ever show it."""
    packet = {r["designation"]: r for r
              in json.loads(_COUNTERFACTUAL.read_text())["magnitude_table"]["rows"]}
    for level, got in POLICY.load_constants().items():
        assert level in packet, f"{level} is served but absent from the operator packet"
        assert got["rate_multiplier"] == pytest.approx(packet[level]["rate_multiplier"], abs=1e-9)
        assert got["expected_games_missed"] == pytest.approx(
            packet[level]["expected_games_missed"], abs=1e-9)


def test_the_serving_path_never_refits_the_model():
    """⭐ MH2.1 (b) — serve the object that was VALIDATED, never a re-derivation — AND NF-INFRA1: the
    fitting frame is GITIGNORED, so a build-time fit would be absent from the box image entirely.

    Pinned on the SOURCE because the symptom on the box is not a wrong number, it is a dead build
    (or, worse, whatever a bare `except` decided)."""
    src = (_FANTASY / "designation_discount_serving.py").read_text()
    body = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for verb in ("fit_predict", "read_parquet", "_designation_frame"):
        assert verb not in body, (
            f"the serving module calls {verb!r} — it must DISPATCH to the persisted constants, not "
            f"reach for the gitignored fitting frame (NF-INFRA1 / MH2.1 (b))")


def test_only_the_three_disclosed_designations_are_priced():
    """⛔ `none_listed` (×0.9906) is the arm's BASELINE HAZARD, reported for context. Serving it
    would discount ~2,400 undesignated players — a board-wide LEVEL SHIFT, a different change from
    the one that was certified and the one the counterfactual priced (59 designated rows/board)."""
    served = set(POLICY.load_constants())
    assert served == {"out", "doubtful", "questionable"}, (
        f"the served designation set is {sorted(served)}. Anything beyond the three DISCLOSED "
        f"designations is a different intervention from the certified one")
    assert DD.DESIGNATION_NONE not in served, (
        "the no-designation baseline hazard is being SERVED — that is a level shift on every row")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. THE ARITHMETIC MATCHES THE PACKET THE DECISION IS MADE ON
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_serving_cap_reproduces_the_counterfactuals_arithmetic_exactly():
    """The counterfactual scales `league_points` by a constant per-designation multiplier; the
    serving path caps `proj_games` with `remaining_season_rate_cap` and rescales the line. Those are
    the same operation to machine precision, and that is what makes the packet's rank moves a
    statement about what the board will do rather than about a different model."""
    from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI

    packet = {r["designation"]: r["rate_multiplier"] for r
              in json.loads(_COUNTERFACTUAL.read_text())["magnitude_table"]["rows"]}
    label_of = {str(v).strip().lower(): str(v) for v in SI.WEEKLY_DESIGNATIONS.values()}
    games = [17.0, 14.0, 12.5, 9.0]
    for level in POLICY.load_constants():
        # ⛔ DRIVE THE SHIPPED CALLABLE, never a re-derivation of its arithmetic here. A test that
        #    recomputes `games × multiplier` the way the code does is a restatement of the code and
        #    could not catch the defect this clause exists for (NF-C0e). The expected value comes
        #    from the PACKET, which is the independent side of the comparison.
        frame = pd.DataFrame({"player_id": [f"p{i}" for i in range(len(games))],
                              "proj_games": games})
        cb = DDS.designation_games_callable(
            2026, designations={f"p{i}": label_of[level] for i in range(len(games))})
        got = cb(frame)
        for g, capped in zip(games, got):
            assert capped == pytest.approx(g * packet[level], abs=1e-9), (
                f"the SERVED cap for {level} at {g} games is not the packet's constant rate "
                f"(×{packet[level]}) — the operator packet's rank moves would describe a different "
                f"board than the one this build would publish")


def test_a_padded_feed_id_still_reaches_its_row():
    """NF-C9's id lesson, on the SERVING path this time. 275 of 2,501 live feed rows carry a leading
    space in `player_id`; a silent non-match here would leave exactly the highest-value designated
    players undiscounted, and would look identical to a feed that said nothing about them."""
    df = pd.DataFrame({"player_id": ["00-0035700", " 00-0035640 "], "proj_games": [17.0, 17.0]})
    cb = DDS.designation_games_callable(
        2026, designations={" 00-0035700": "Out", "00-0035640": "Questionable"})
    got = cb(df)
    assert got[0] == pytest.approx(17.0 * 0.8639, abs=1e-3)
    assert got[1] == pytest.approx(17.0 * 0.9629, abs=1e-3)


def test_an_unpriceable_label_raises_rather_than_silently_applying_nothing():
    """⛔ NF-INJ4b §3b(2): a label-case mismatch made the whole discount a no-op — 89 designated
    players, zero movement, no error, and an id-join coverage reading a healthy 89. A silent
    no-discount is byte-indistinguishable from a correctly-applied one that moved nothing."""
    with pytest.raises(RuntimeError, match="no constant"):
        DDS.designation_games_callable(2026, designations={"00-0001": "questionable"})


def test_an_unreadable_feed_degrades_loudly_to_the_pre_ship_board():
    """⚖️ ALERT-tier: a feed outage must not fail the board build (the boards are the draft-critical
    output), but it must never be silent either. `None` makes the availability owner take its
    no-designation branch, which is byte-identical to the pre-NF-INJ4b path BY CONSTRUCTION."""
    log: dict = {}
    assert DDS.designation_games_callable(2026, designations=None, row_log=log) is None
    assert log["feed_readable"] is False and log["rows_moved"] == 0, (
        "an unreadable feed did not record that it applied nothing — 'served with the discount' and "
        "'served without it' must be distinguishable on the build record, not inferred from a stamp")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⛔⛔ THE DECLARATION AND THE PRODUCTION SHIP TOGETHER — IN BOTH DIRECTIONS
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _how_modelled_prose() -> str:
    src = _CLAIM_COPY_TS.read_text()
    tail = src.split("export const WEEKLY_DESIGNATION_HOW_MODELLED", 1)
    assert len(tail) == 2, (
        "WEEKLY_DESIGNATION_HOW_MODELLED is not exported from the canonical copy module — this "
        "clause cannot be evaluated, and an unevaluable check is never a pass (NF1.7 (a))")
    body = tail[1].split("\nexport const ", 1)[0]
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
    assert literals, "no prose extracted — the coherence clause below would be vacuous"
    return " ".join(literals).lower()


def test_the_user_facing_copy_and_the_served_policy_cannot_disagree():
    """⭐⭐ THE CLAUSE THAT MAKES 'THE COPY DEPLOYS WITH THE DISCOUNT' MECHANICAL RATHER THAN A
    CONVENTION — and it is the whole reason NF-C9's retirement rides this PR instead of a later one.

    Two failures, mirror images, both invisible on a rendered board because a games figure looks the
    same whichever is true:

      · policy ON, copy still denying  → we disclaim work we have done. That is the state this PR
        would have shipped if the copy had been left alone, and the ENTIRE 52-clause NF-C9 suite
        went green over it, because its boundary clause was keyed on token spellings in a file the
        wiring does not touch (the NF-CAP1 re-key).
      · policy OFF, copy still claiming → we advertise a discount of exactly zero. This is the one a
        ROLLBACK produces, and it is the more dangerous of the two: the rollback is a one-line flag
        flip that feels complete on its own.
    """
    prose = _how_modelled_prose()
    claims_adjustment = "takes this into account" in prose
    denies_adjustment = "does not take this into account" in prose
    assert claims_adjustment != denies_adjustment, (
        "WEEKLY_DESIGNATION_HOW_MODELLED neither clearly claims nor clearly denies the adjustment — "
        "this clause cannot compare it against the policy, so it would pass on nothing")
    if POLICY.serving_enabled():
        assert claims_adjustment, (
            "⛔ THE DISCOUNT IS SERVING AND THE COPY DENIES IT. Every surface rendering "
            "WEEKLY_DESIGNATION_HOW_MODELLED is telling readers their projected-games figure "
            "ignores a designation it is in fact discounting. Fix the COPY, not this test")
    else:
        assert denies_adjustment, (
            "⛔ THE DISCOUNT IS OFF AND THE COPY CLAIMS IT. This is the rollback state: flipping "
            "designation_discount_policy.SERVING_ENABLED back to False is NOT complete on its own — "
            "WEEKLY_DESIGNATION_HOW_MODELLED must revert in the SAME change, or the board advertises "
            "a discount of exactly zero")


def test_the_board_publish_is_a_running_schedule_so_the_merge_is_the_deploy():
    """⚠️⚠️ THE OPERATOR-FACING FACT, pinned so it cannot quietly stop being true.

    Unlike the API Lambda — which needs an explicit `deploy.sh`, and whose skew this repo has been
    bitten by repeatedly — the season board is published by a Dagster schedule that ships
    `default_status=RUNNING` and runs `export_draft_board_json --publish` from the box image, which
    is built from `main` on merge. **There is no gate between merging this and serving it.**

    That is the MH2.1 (c) promotion-mechanics landmine on the fantasy board, and it is the single
    fact the ship packet most needs the operator to have read. If this schedule ever stops being
    RUNNING, the packet's "merging is the deploy" framing becomes wrong in the safe direction — but
    it becomes wrong, so it is pinned."""
    sched = (_REPO / "pipeline/schedules/sports_rollforward_schedules.py").read_text()
    body = sched.split("def sports_nfl_board_publish_schedule", 1)
    assert len(body) == 2, "the board publish schedule was renamed — re-read the deploy path"
    decorator = sched.split("@schedule(", )[-2] if "@schedule(" in sched else ""
    assert "default_status=DefaultScheduleStatus.RUNNING" in sched, (
        "the board publish schedule no longer self-starts — the packet's 'merging is the deploy' "
        "statement needs re-reading before the operator relies on it")
    job = (_REPO / "pipeline/jobs/sports_nfl_board_publish_job.py").read_text()
    assert '"--publish"' in job, (
        "the board publish job no longer publishes — the deploy path this packet describes has moved")


def test_the_historical_boundary_is_not_expressible_as_an_accident():
    """A live designation must never reach a BACKTEST board (the hindsight boundary
    `market_freshness.should_refresh_market` enforces for ADP/ECR). Pinned on the caller, because
    the alternative is rebuilding a 2019 board to find out."""
    caller = (_FANTASY / "run_season_projection.py").read_text()
    assert "_current_season()" in caller.split("_designation_games = (", 1)[1][:400], (
        "the designation channel is no longer gated on the current season")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. THE CHANNEL COMPOSES, IT DOES NOT STACK — re-asserted on the real owner
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_disjointness_holds_at_the_ACTUALLY_SERVED_multipliers():
    """⭐ The registered both-channels row is pinned by `test_nf_inj4_designation_duration.py` at the
    magnitude the study registered. This clause asks the SHIP's version of the question: does the
    invariant still hold at the constants the board is ABOUT TO SERVE?

    ⛔ Not a duplicate. The registered test would keep passing if the served artifact drifted to a
    different magnitude, because it hardcodes the study's own figure. This one reads the served
    constants, so a future artifact rebuild that changed them cannot quietly produce a board where
    the strongest cap is no longer the one that owns the row.

    The stacked answer is materially different and is what a SEQUENTIAL application silently
    produces — two rate caps compounding, which is the double-discount the NEWS-1 rule exists to
    prevent, arriving through a channel that rule predates."""
    current = 14.0
    news_missed = 6.0
    for level, c in POLICY.load_constants().items():
        desig = DD.remaining_season_rate_cap(
            current, DD.SEASON_GAMES * (1.0 - c["rate_multiplier"]))
        news = DD.remaining_season_rate_cap(current, news_missed)
        composed, owner = DD.compose_availability_caps(
            current, designation_games=desig, news_games=news)
        stacked = DD.remaining_season_rate_cap(desig, news_missed)

        assert composed == pytest.approx(min(desig, news)), (
            f"{level}: the composition is not the single strongest cap")
        assert owner in (DD.CHANNEL_DESIGNATION, DD.CHANNEL_NEWS), (
            f"{level}: exactly one channel must own the row, got {owner!r}")
        assert composed > stacked + 1e-9, (
            f"{level}: the composed cap ({composed:.4f}) is no better than the STACKED one "
            f"({stacked:.4f}) — two rate caps are compounding, which is the double-discount the "
            f"NEWS-1 rule exists to prevent")


def test_the_designation_cap_stamps_the_disjointness_flag_through_the_real_owner():
    """The behavioural half, on the real availability owner: `reported_absence_games` skips a row on
    `_formal_discount_applied`, so a designation cap that did not set it would let a player carrying
    BOTH a news cap and a live designation take both.

    ⚠️ The line rescale needs a full stat line, so the frame is built the way the registered suite
    builds it — a two-column frame raises in `rescale_line_to_games` and the clause would never
    reach its assertion."""
    n = 2
    df = SP.score_line(pd.DataFrame({
        "player_id": ["p0", "p1"], "player_name": ["P0", "P1"], "position": ["RB"] * n,
        "proj_games": [14.0, 14.0],
        "proj_pass_att": np.zeros(n), "proj_pass_cmp": np.zeros(n), "proj_pass_yds": np.zeros(n),
        "proj_pass_td": np.zeros(n), "proj_pass_int": np.zeros(n),
        "proj_rush_att": np.full(n, 200.0), "proj_rush_yds": np.full(n, 900.0),
        "proj_rush_td": np.full(n, 7.0),
        "proj_targets": np.full(n, 60.0), "proj_rec": np.full(n, 45.0),
        "proj_rec_yds": np.full(n, 380.0), "proj_rec_td": np.full(n, 2.0),
        "proj_fumbles_lost": np.full(n, 1.5), "proj_two_pt": np.zeros(n),
    }), prefix="proj_")
    out_mult = POLICY.load_constants()["out"]["rate_multiplier"]
    capped = np.array([14.0 * out_mult, 14.0], dtype=float)
    out = SP.apply_availability_chain(df.copy(), designation_games=lambda _d: capped)

    flag = out[SP.FORMAL_APPLIED_COL].to_numpy(dtype=bool)
    assert flag[0], (
        "the designation cap moved row 0 and did NOT stamp the disjointness flag — the news channel "
        "will now stack on top of it")
    assert not flag[1], "an untouched row must not be flagged"
    assert out[SP.DESIGNATION_APPLIED_COL].to_numpy(dtype=bool)[0], (
        "the owning channel is no longer recorded per row")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. THE BATTERY'S OWN NO-OP CONTROL, AS A GUARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_an_empty_designation_map_moves_nothing_on_a_board_whose_vor_is_ROUNDED():
    """⭐⭐ THE BATTERY'S NO-OP CONTROL, PROMOTED FROM A RUNTIME CHECK TO A GUARD — and it exists
    because the RED proof found nothing covering it.

    The battery's control caught a real defect at runtime: re-deriving `vor` as `pts − repl` instead
    of applying the delta to the PUBLISHED value moved **1,113 ranks across the 14 boards under an
    EMPTY designation map**. The published board rounds `pts`, `repl` and `vor` each to one decimal,
    so `pts − repl` differs from the published `vor` by up to 0.1 — a rounding residue, not a
    discount — and that difference would have reached the operator packet as phantom movement on
    rows nothing had touched. Same shape as the `(config_name, n_teams)` defect that made 1,715 of
    1,716 rows 'move' in NF-INJ4b's own counterfactual.

    ⚠️ **THE FIXTURE IS THE WHOLE TEST.** Its `vor` is deliberately NOT `pts − repl`: with a
    consistent fixture both implementations agree and the clause is vacuous. The two must DISAGREE
    on the fixture or it cannot tell them apart (the NF-C6b rank-gate lesson: a gate needs a fixture
    where the two orderings differ)."""
    from quant_sports_intel_models.football.nfl.fantasy import (
        run_nf_inj4b_ship_battery as BAT,
    )

    board = pd.DataFrame({
        "id": ["00-0001", "00-0002", "00-0003"],
        "name": ["A", "B", "C"], "pos": ["RB", "WR", "QB"], "team": ["X", "Y", "Z"],
        "pts": [350.5, 314.9, 310.2], "repl": [150.1, 150.1, 150.1],
        # ⛔ ROUNDED, and NOT equal to `pts - repl` — 350.5-150.1 = 200.40000000000003, published
        #    as 200.4; the residue is exactly what a re-derivation reintroduces.
        "vor": [200.4, 164.8, 160.0],
        "g": [17.0, 16.0, 15.0],
        "ptsP10": [104.0, 101.5, 103.9], "ptsP90": [420.0, 400.0, 390.0],
        "vorP10": [-46.1, -48.6, -46.2], "vorP90": [269.9, 249.9, 239.9],
        "ovrRank": [1, 2, 3], "adp": [1.0, 2.0, 3.0], "bye": [5, 6, 7],
        "rookie": [False, False, False],
    })
    assert not np.allclose(board["pts"] - board["repl"], board["vor"], atol=1e-12), (
        "the fixture's vor now EQUALS pts − repl, so a re-derivation and a delta agree on it and "
        "this clause can no longer tell them apart — it would pass on nothing")

    cand = BAT.candidate_board(board, {})
    for col in ("pts", "g", "vor", "ptsP10", "ptsP90", "vorP10", "vorP90"):
        worst = float(np.nanmax(np.abs(board[col].astype(float).to_numpy()
                                       - cand[col].astype(float).to_numpy())))
        assert worst <= BAT.EPS, (
            f"an EMPTY designation map moved `{col}` by {worst:.3e} (> {BAT.EPS}). The candidate "
            f"board must reproduce the published one when nothing is designated, or every figure "
            f"in the operator packet carries a rounding residue reported as movement")


def test_the_manifest_stamp_is_actually_EXERCISED_and_says_what_it_does_not_know():
    """⭐ NF-TR2's lesson, applied to this story's own build-time block: a stamp that only ever runs
    inside a 2,000-line entrypoint ships a NameError past a green suite, because nothing INVOKES it.

    It also has to be honest about its own scope. `eligible_rows_on_projections` counts rows the
    discount COULD touch; it is not what the build moved, and a reader who took it for that would be
    reading a configuration as a measurement (NF-C0e). The payload says so in its own text."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX

    pdf = pd.DataFrame({"player_id": ["00-0001", " 00-0002 ", "00-0003"]})
    stamp = EX.designation_discount_stamp(pdf, {"00-0001": "Out", "00-0002": "Questionable"})
    assert stamp is not None, "the stamp returned None on a perfectly readable feed"
    assert stamp["designation_discount_serving_enabled"] is POLICY.serving_enabled()
    assert stamp["feed_readable"] is True
    assert stamp["eligible_rows_on_projections"] == 2, (
        "the eligible count did not normalise the padded feed id — the same silent-miss that cost "
        "Josh Jacobs and DK Metcalf their disclosure on a published board (NF-C9)")
    assert "NOT what the build moved" in stamp["records_what"], (
        "the stamp no longer states that it records a CONFIGURATION rather than an outcome")

    # ⛔ an unreadable feed must not be scored as 'nothing was eligible'
    blind = EX.designation_discount_stamp(pdf, None)
    assert blind["feed_readable"] is False and blind["eligible_rows_on_projections"] is None, (
        "an unreadable feed reported an eligible count — 0 and 'we could not look' are different "
        "facts, and one of them is a pass")
