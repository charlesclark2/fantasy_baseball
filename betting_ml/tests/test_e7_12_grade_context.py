"""E7.12 SLICE 4 — the as-of scouting-grade context and the arms built on it.

This slice's failure mode is the loudest in the whole program: **a grade published after the player
debuted has the answer in it**, and the leak produces a huge, entirely fake win that looks like the best
result E7.12 has ever produced. So the as-of guard gets a leakage test that plants a contaminated grade
and asserts it is refused, not merely a shape check.

The second failure mode is subtler and is the one the design is actually built around: **grade coverage
rises monotonically with promotion propensity** (batters 38.0/58.1/68.1% across S2's terciles), so
"this player was RANKED" is itself a selection signal. An arm that beats the baseline because ranked
players are better prospects has credited SELECTION to SCOUTING. `A_flag_only` is the disqualifier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.grade_context import (
    ACTIVE_FOLD_MIN,
    FLAG_COL,
    FV_COL,
    GRADE_FOR_METRIC,
    SIDE_GRADES,
    asof_grades,
    grade_coverage,
)


def _board(seasons=(2019, 2020, 2021), players=("fg1", "fg2")):
    rows = []
    for s in seasons:
        for i, fg in enumerate(players):
            rows.append({
                "fg_minor_id": fg, "season": s, FV_COL: 45.0 + i,
                # grade RISES with season so "which snapshot was used" is readable off the value
                "grade_hit": 40.0 + (s - 2019) * 10 + i,
                "grade_game_pwr": 45.0 + (s - 2019) * 10,
                "grade_raw_pwr": 50.0, "grade_spd": 50.0, "grade_fld": 50.0,
                "grade_fb": 55.0 + (s - 2019) * 10, "grade_cmd": 45.0 + (s - 2019) * 10,
                "grade_sl": 50.0, "grade_cb": 50.0, "grade_ch": 50.0, "grade_ct": 50.0,
                "grade_spl": 50.0,
            })
    return pd.DataFrame(rows)


def _xref(players=("fg1", "fg2"), ids=(100, 200)):
    return pd.DataFrame({"fg_minor_id": list(players), "mlbam_id": list(ids)})


def _pairs(debuts=(2022, 2020)):
    return pd.DataFrame({
        "player_id": [100, 200], "level": ["Double-A", "Double-A"],
        "debut_cohort": list(debuts), "has_mlb_label": [True, True],
    })


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The as-of guard — the whole slice
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_asof_join_takes_the_LATEST_snapshot_STRICTLY_BEFORE_the_debut_season():
    """A 2022 debut may use the 2021 board; a 2020 debut may use only 2019.

    The grade rises with season in the fixture, so the VALUE identifies which snapshot was taken — a
    shape-only assertion would pass on a join that silently took the newest board for everyone."""
    ctx = asof_grades(_pairs(debuts=(2022, 2020)), _board(), _xref(), side="batter")
    by = ctx.set_index("player_id")
    assert by.loc[100, "board_season"] == 2021, "2022 debut ⇒ latest admissible snapshot is 2021"
    assert by.loc[100, "grade_hit"] == 60.0                       # 40 + (2021-2019)*10 + 0
    assert by.loc[200, "board_season"] == 2019, "2020 debut ⇒ only the 2019 board predates it"
    assert by.loc[200, "grade_hit"] == 41.0                       # 40 + 0 + 1


def test_a_grade_from_the_DEBUT_SEASON_ITSELF_is_REFUSED():
    """🚨 THE LEAKAGE TEST. The bound is `<`, not `<=`, and the boundary is exactly where contamination
    hides: a board dated 2019-07-01 is published MID-SEASON, so for a player who debuted in 2019 it may
    well post-date the callup. `<=` would admit precisely the grades most likely to be contaminated, on
    the cohort boundary where nobody looks."""
    ctx = asof_grades(_pairs(debuts=(2019, 2019)), _board(seasons=(2019, 2020)), _xref(),
                      side="batter")
    assert ctx["board_season"].isna().all(), (
        "a same-season board must NOT be admitted", ctx[["player_id", "board_season"]])
    assert (ctx[FLAG_COL] == 0.0).all()


def test_a_player_with_NO_admissible_snapshot_gets_NULL_grades_and_a_ZERO_FLAG_not_a_default():
    """A blank must never become 0 — a 0 grade is a real scouting statement ('scouted and terrible') and
    would poison any downstream mean. Absence is encoded in the FLAG, not in the value."""
    ctx = asof_grades(_pairs(debuts=(2016, 2016)), _board(), _xref(), side="batter")
    assert ctx["grade_hit"].isna().all(), "no admissible board ⇒ NULL, never 0.0"
    assert (ctx[FLAG_COL] == 0.0).all(), "…and the indicator says so"


def test_a_PROSPECT_with_no_debut_season_may_use_EVERY_snapshot():
    """Nothing has happened yet that a grade could leak, so the emission population is unrestricted —
    and a guard that refused them would silently strip grades from exactly the players the board serves."""
    p = _pairs(debuts=(np.nan, np.nan))
    ctx = asof_grades(p, _board(), _xref(), side="batter")
    assert (ctx["board_season"] == 2021).all(), "a prospect takes the newest board"


def test_every_pairs_row_survives_the_join_so_the_eval_population_is_UNCHANGED():
    """The arms are compared on an identical population (`run_ladder` asserts it). A grade join that
    INNER-joined would silently drop the ungraded players — which is both the population change the
    story prompt forbids and a large one here (45% of labelled batter rows)."""
    p = pd.concat([_pairs(), pd.DataFrame({
        "player_id": [999], "level": ["Triple-A"], "debut_cohort": [2021],
        "has_mlb_label": [True]})], ignore_index=True)
    ctx = asof_grades(p, _board(), _xref(), side="batter")
    assert len(ctx) == len(p)
    assert set(zip(ctx["player_id"], ctx["level"])) == set(zip(p["player_id"], p["level"]))
    assert ctx.loc[ctx["player_id"] == 999, FLAG_COL].iloc[0] == 0.0


def test_the_bridge_goes_through_the_XREF_because_the_boards_own_mlbam_id_is_ALL_NULL():
    """🪤 `the_board.mlbam_id` is the void-typed column the E7.4 landmine names — it is 100% NULL on the
    live table. A join on it would match nothing and produce a clean, entirely FALSE null for the whole
    slice. This pins that the identity path is `fg_minor_id` → xref → MLBAM."""
    ctx = asof_grades(_pairs(), _board(), _xref(), side="batter")
    assert ctx[FLAG_COL].sum() > 0, "the xref bridge must actually match"
    empty = asof_grades(_pairs(), _board(), _xref(players=("nope",), ids=(1,)), side="batter")
    assert empty[FLAG_COL].sum() == 0, "…and an unmatched bridge must yield NO grades, not fabricated ones"


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. The power constraint the fold restriction exists for
# ══════════════════════════════════════════════════════════════════════════════════════


def test_coverage_reports_which_folds_are_STRUCTURALLY_INERT():
    """The board begins 2018-07-01, so the earliest debut cohorts can have no admissible grade at all and
    their folds carry no graded TRAINING row. The grade arm is byte-identical to the baseline there,
    scores `delta = 0`, and the `d > 0` fold test counts that as a LOSS — capping the achievable
    fold-win-rate at 7/11 = 0.636 against a 0.60 gate, so a PERFECT signal would clear by one fold.

    Scoring a mechanism on folds where it provably cannot act is not a stricter test, it is a broken one.
    This pins that the inert cohorts are identified and reported rather than silently counted."""
    p = pd.DataFrame({
        "player_id": [100, 200, 100, 200], "level": ["A", "A", "B", "B"],
        "debut_cohort": [2016, 2016, 2022, 2022], "has_mlb_label": [True] * 4})
    ctx = asof_grades(p, _board(), _xref(), side="batter")
    cov = grade_coverage(ctx, p, side="batter")
    old = cov[cov["debut_cohort"] == 2016].iloc[0]
    new = cov[cov["debut_cohort"] == 2022].iloc[0]
    assert old["coverage"] == 0.0 and not old["fold_is_active"]
    assert new["coverage"] == 1.0 and new["fold_is_active"]
    assert ACTIVE_FOLD_MIN == 2020


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. The grade→component map is SPARSE on purpose
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_component_with_NO_scouting_analogue_has_NO_mapped_grade():
    """⭐ The gaps are honest, not oversights, and this test is what keeps a future session from "fixing"
    them by inventing a mapping.

    Batter grades are {Hit, Game, Raw, Spd, Fld} — there is **nothing in that set describing plate
    discipline**, so `bb_pct` has no batter grade. (The story prompt wrote "CMD→BB%" for batters; CMD is
    a PITCHER grade and is simply absent from the batter set — trust the field list, not the prose.)
    `gb_pct` and `xwoba_against` likewise have no single-tool analogue. Those arms are UNSELECTABLE
    NO-OPS, the slice-1p `xwoba_against` precedent, never a fabricated neutral."""
    assert "bb_pct" not in GRADE_FOR_METRIC["batter"], (
        "batters carry no plate-discipline grade — do not invent one")
    assert GRADE_FOR_METRIC["batter"]["k_pct"] == "grade_hit"
    assert GRADE_FOR_METRIC["batter"]["iso"] == "grade_game_pwr", (
        "GAME power, not RAW — game power is what actually shows up in ISO")
    assert GRADE_FOR_METRIC["pitcher"]["bb_pct"] == "grade_cmd"
    assert GRADE_FOR_METRIC["pitcher"]["k_pct"] == "grade_fb"
    for m in ("gb_pct", "xwoba_against"):
        assert m not in GRADE_FOR_METRIC["pitcher"]
    # every mapped grade must exist in its side's grade set, or the arm silently scores NaN and vanishes
    for side, mapping in GRADE_FOR_METRIC.items():
        for metric, col in mapping.items():
            assert col in SIDE_GRADES[side], (side, metric, col)


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. The arms — and the foil that keeps selection from being credited to scouting
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_ladder_carries_the_FLAG_ONLY_foil_on_every_metric():
    """🚨 THE LOAD-BEARING FOIL. Grade coverage rises monotonically with S2's promotion propensity
    (batters 38.0/58.1/68.1%), so *being ranked* carries real signal that has nothing to do with the tool
    grade. Without this arm, a slice that beats the baseline because ranked players are better prospects
    would be reported as "scouting grades improve the translation"."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES
    from betting_ml.scripts.milb_mle.run_e7_12_slice4 import ladder_for

    for name, side in SIDES.items():
        for metric in side.metrics:
            labels = {a.label for a in ladder_for(side, metric)}
            assert "A_flag_only" in labels, (name, metric)
            assert "G0_shipped" in labels
            if metric in GRADE_FOR_METRIC[name]:
                assert {"G1_grade", "G3_fv_only", "A_grade_placebo"} <= labels, (name, metric)


def test_the_flag_only_foil_BEATING_the_grade_arm_DROPS_the_metric():
    """…and it must be a DISQUALIFIER, not a footnote — the E7.12 house failure is a statistic that is
    computed, printed, and never consumed."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice4 import s4_verdict

    board = pd.DataFrame([
        {"arm": "G0_shipped", "kind": "ladder", "selectable": True, "oos_mae": 0.040,
         "fold_win_rate": 0.0},
        {"arm": "G1_grade", "kind": "ladder", "selectable": True, "oos_mae": 0.039,
         "fold_win_rate": 0.85},
    ])
    anchors = {"grade_placebo_vs_grade": {"violated": False},
               "flag_only_vs_grade": {"violated": True}}
    v, w, reasons = s4_verdict(board, anchors, "grade_hit", [])
    assert v == "DROP" and w == "G0_shipped"
    assert any("SELECTION, not scouting" in r for r in reasons), reasons


def test_the_grade_placebo_permutes_WITHIN_board_season_and_leaves_the_flag_alone():
    """The placebo must keep the season's grade distribution and destroy only the player↔grade pairing —
    otherwise a loss is attributable to a different distribution rather than to the grade carrying no
    information. And it must NOT permute the FLAG: the placebo tests the grade VALUE, so 'who was
    ranked' has to stay true or the arm becomes a different experiment."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice4 import _Z, _prepare, ladder_for
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES

    rng = np.random.default_rng(0)
    n = 60
    frame = pd.DataFrame({
        "board_season": np.repeat([2020, 2021], n // 2),
        "grade_hit": np.arange(n, dtype=float),
        FLAG_COL: 1.0,
    })
    arms = {a.label: a for a in ladder_for(SIDES["batter"], "k_pct")}
    out, cols = _prepare(frame, arms["A_grade_placebo"], rng)
    assert set(cols) == {f"{_Z}grade_hit", f"{_Z}{FLAG_COL}"}
    for s, d in out.groupby("board_season"):
        assert np.array_equal(np.sort(d[f"{_Z}grade_hit"].to_numpy()),
                              np.sort(d["grade_hit"].to_numpy())), s
    np.testing.assert_array_equal(out[f"{_Z}{FLAG_COL}"].to_numpy(), frame[FLAG_COL].to_numpy())


def test_the_GRADED_FOLD_WIN_RATE_is_a_power_diagnostic_and_NOT_part_of_the_gate():
    """⭐ THE INSTRUMENT THAT SEPARATES A CLEAN NULL FROM AN UNDERPOWERED ONE — and the reason it must
    stay OUT of the gate.

    23-45% of held-out rows have no grade and fall back to the incumbent, so an arm could work and still
    lose the overall fold test to dilution. `graded_fold_win_rate` re-runs the SAME test on the graded
    rows alone to check. On the live pitcher K% run it came back IDENTICAL to the overall rate
    (0.571 both), which REFUTES the dilution explanation and makes that null a real one — the +1.04% mean
    lift on graded rows is carried by a minority of folds, i.e. unstable rather than absent.

    It is a diagnostic and not a criterion because selecting on it would be selecting on the subset where
    the arm looks best, which is the whole failure mode the pre-registered gate exists to prevent."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice4 import _graded_fold_mae, s4_verdict

    rows = pd.DataFrame({
        "fold": [2020] * 4 + [2021] * 4,
        "arm": ["G0_shipped", "G1_grade"] * 4,
        "graded": [True, True, False, False] * 2,
        "abs_err": [0.05, 0.01, 0.05, 0.05, 0.05, 0.01, 0.05, 0.05],
        "player_id": [1, 1, 2, 2, 1, 1, 2, 2], "level": ["A"] * 8,
    })
    gm = _graded_fold_mae(rows, [2020, 2021], ["G0_shipped", "G1_grade"])
    assert gm.loc[2020, "G1_grade"] == pytest.approx(0.01), "graded rows only — the 0.05s are excluded"
    assert gm.loc[2020, "G0_shipped"] == pytest.approx(0.05)

    # the gate must ignore it: an arm that wins the graded subset but fails the overall fold bar DROPS
    board = pd.DataFrame([
        {"arm": "G0_shipped", "kind": "ladder", "selectable": True, "oos_mae": 0.040,
         "fold_win_rate": 0.0, "graded_fold_win_rate": 0.0},
        {"arm": "G1_grade", "kind": "ladder", "selectable": True, "oos_mae": 0.039,
         "fold_win_rate": 0.571, "graded_fold_win_rate": 1.0},
    ])
    v, w, _ = s4_verdict(board, {"grade_placebo_vs_grade": {"violated": False},
                                 "flag_only_vs_grade": {"violated": False}}, "grade_fb", [])
    assert (v, w) == ("DROP", "G0_shipped"), (
        "a perfect graded-subset record must NOT rescue an arm that failed the pre-registered gate")


def test_prepare_NEVER_mutates_the_shared_frame():
    """🪤 The placebo permutes values. If it wrote back over the frame the fold loop reuses, every LATER
    arm in that fold would silently score against poisoned grades — and the leaderboard would look
    completely normal. This is why `_prepare` copies under a `_g_` prefix."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice4 import _prepare, ladder_for
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES

    frame = pd.DataFrame({"board_season": [2020] * 40, "grade_hit": np.arange(40, dtype=float),
                          FLAG_COL: 1.0})
    before = frame["grade_hit"].to_numpy().copy()
    arms = {a.label: a for a in ladder_for(SIDES["batter"], "k_pct")}
    for label in ("A_grade_placebo", "G1_grade", "A_flag_only"):
        _prepare(frame, arms[label], np.random.default_rng(1))
    np.testing.assert_array_equal(frame["grade_hit"].to_numpy(), before)
