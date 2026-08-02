"""NF1.5b — the REFINED market-aware board as the SERVED board.

NF1.5 produced a board that beats consensus ADP at all four positions; the operator ruled (2026-08-01)
to serve it. Re-landing it is a SERVING-PATH change, and the whole risk is that a "just repoint the
read" flip quietly ships something WORSE than the incumbent it replaces. It nearly did: NF1.5's own
build assembled a parallel board instead of transforming the shipped one, and had drifted from it on
three axes that all reach users —

  * UNIVERSE  — 716 players against the shipped 784 (it never saw NF-D11's base-anchor rescue), so
                68 returning veterans would have VANISHED from the draft board.
  * INTERVAL  — every band re-priced as a pre-NF1.9 normal (`point ± 1.2816·κ·sd`, measured coverage
                ~0.55 of nominal 0.80) and stamped `calibrated`, silently reverting the NF1.9
                per-player band on ~90% of the board.
  * SURFACES  — the draft board and the Projections surface read two SEPARATE artifacts, so a
                one-sided repoint ranks the same player differently on two pages with no error.

These pin the invariants that make the re-land safe. Pure/offline: tiny frames, no DuckDB, no S3.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as ex
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as R15
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The re-order is ORDERING-ONLY, and it leaves what it cannot score ALONE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _mvp1_frame(n: int = 6, pos: str = "RB") -> pd.DataFrame:
    """A minimal MVP-1-shaped veteran frame: a raw line that scores, plus the interval drivers.

    ⚠️ The spread is deliberately NARROW (top ≈ 1.6× bottom). `apply_learned_level` rescales each raw
    line by a CLAMPED scalar (0.30–3.5), so on a 6-row toy board a 5× promotion saturates the clamp
    and the row cannot reach its assigned level — which would make a multiset assertion fail for a
    reason that is the shipped mechanism's documented tail guard, not the behaviour under test. (On
    the real 2026 board 20 of 703 veterans saturate it, and the build ALERTs when they do.)
    `proj_fumbles_lost` is derived exactly as the rescale re-derives it, so a scale of 1.0 really is
    a no-op — a hand-picked constant there would move the point by itself."""
    rng = np.random.default_rng(11)
    rush_att = np.linspace(220, 140, n)
    rec = np.linspace(55, 34, n)
    return pd.DataFrame({
        "player_id": [f"00-{i}" for i in range(n)],
        "position": [pos] * n,
        "depth_chart_position_rank": [1 + i % 3 for i in range(n)],
        "games_played": [16] * n,
        "proj_games": [16.0] * n,
        "proj_rush_att": rush_att,
        "proj_rush_yds": np.linspace(1000, 620, n),
        "proj_rush_td": np.linspace(8, 5, n),
        "proj_targets": np.linspace(70, 44, n),
        "proj_rec": rec,
        "proj_rec_yds": np.linspace(480, 300, n),
        "proj_rec_td": np.linspace(3, 1, n),
        "proj_fumbles_lost": np.round((rush_att + rec) * 0.006, 2),
        "fp_ppr_sd": rng.uniform(4.0, 9.0, n),
    })


def _points(df: pd.DataFrame) -> np.ndarray:
    return SP.score_line(df.copy(), prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)


def test_an_eligible_mask_of_all_true_is_the_pre_nf15b_behaviour():
    """The mask is additive: the default path must be untouched, or every prior NF1.x board build
    silently changes meaning."""
    df = _mvp1_frame()
    score = np.arange(len(df))[::-1].astype(float)
    a = M1.apply_learned_ordering(df, score, positions=("RB",))
    b = M1.apply_learned_ordering(df, score, positions=("RB",),
                                  eligible=np.ones(len(df), dtype=bool))
    pd.testing.assert_frame_equal(a, b)


def test_an_ineligible_row_keeps_its_mvp1_point_exactly():
    """A veteran the research frame cannot score (NF-D11's rescued returners) must be served EXACTLY
    as MVP-1 projected him. Guessing his rank from his MVP-1 points would interleave two scales."""
    df = _mvp1_frame(n=6)
    base = _points(df)
    elig = np.array([True, True, True, False, False, True])
    score = np.array([1.0, 5.0, 3.0, np.nan, np.nan, 9.0])   # reverse the eligible order
    out = M1.apply_learned_ordering(df, score, positions=("RB",), eligible=elig)
    got = _points(out)
    assert np.allclose(got[~elig], base[~elig], atol=1e-9), (
        "an unscored veteran was re-levelled — his MVP-1 projection must pass through untouched")
    assert out.loc[~pd.Series(elig), "nf1_scale"].eq(1.0).all()


def test_the_eligible_subset_is_permuted_over_ITS_OWN_multiset():
    """Ordering-only means the per-position point MULTISET is preserved. The eligible rows are handed
    back exactly THEIR OWN levels in learned-rank order — never a level belonging to a row the model
    could not speak to."""
    df = _mvp1_frame(n=6)
    base = _points(df)
    elig = np.array([True, True, True, False, False, True])
    score = np.array([1.0, 5.0, 3.0, np.nan, np.nan, 9.0])
    out = _points(M1.apply_learned_ordering(df, score, positions=("RB",), eligible=elig))
    # the multiset over the eligible rows survives (up to the raw-line rescale's own quantisation —
    # `apply_learned_level` re-clamps cmp/rec and re-rounds fumbles, so this is not byte-equality)
    assert np.allclose(np.sort(out[elig]), np.sort(base[elig]), atol=0.5)
    # and the eligible rows now rank in LEARNED order
    order = np.argsort(-score[elig])
    assert list(np.argsort(-out[elig])) == list(order)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The interval FOLLOWS the point — one function, re-appliable
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _interval_frame() -> pd.DataFrame:
    df = _mvp1_frame(n=5)
    return SP.score_line(df, prefix="proj_")


def test_attaching_the_interval_twice_at_the_same_level_is_idempotent():
    """The retained `fp_ppr_pg_sd` / `games_sd_raw` exist for exactly this: the function OVERWRITES
    `fp_ppr_sd` with the SEASON sd, so a naive re-application would feed the season sd back in as a
    per-game sd and inflate every band by √games."""
    once = SP.attach_season_interval(_interval_frame())
    twice = SP.attach_season_interval(once)
    for col in ("fp_ppr_sd", "fp_ppr_p10", "fp_ppr_p90"):
        assert np.allclose(once[col], twice[col]), f"{col} moved on a no-op re-application"


def test_a_re_levelled_row_gets_a_band_around_its_NEW_point():
    """The defect this replaced: NF1.5 re-assigned the point and kept/re-derived a band for a
    different level, so a player could carry an interval his own projection sat outside."""
    df = _interval_frame()
    first = SP.attach_season_interval(df)
    lifted = first.copy()
    lifted["proj_fp_ppr"] = lifted["proj_fp_ppr"] * 1.6      # a within-multiset promotion
    second = SP.attach_season_interval(lifted)
    assert (second["fp_ppr_p10"] <= second["proj_fp_ppr"]).all()
    assert (second["fp_ppr_p90"] >= second["proj_fp_ppr"]).all()
    assert (second["fp_ppr_p90"] > first["fp_ppr_p90"]).all(), (
        "the band did not move with the point it prices")


def test_the_refined_board_never_rolls_its_own_interval():
    """Source-inspection, because the runtime symptom is invisible: a private normal band still
    emits a plausible-looking p10/p90, just an uncalibrated one, and only the `uncertainty_type`
    column ever said so. The refined board must go through MVP-1's own interval code."""
    src = Path(R15.__file__).read_text()
    body = src.split("def build_season_projection(")[1].split("\ndef ", 1)[0]
    code = "\n".join(ln for ln in body.split("\n")
                     if not ln.strip().startswith("#") and '"""' not in ln)
    assert "SP.attach_season_interval(" in code, (
        "the refined board must re-derive its interval through season_projection, not privately")
    assert "build_projection(" in code, (
        "the refined board must be a transform OF the shipped board, not a parallel assembly")
    for banned in ("1.2815", "z80", "disp_kappa", 'uncertainty_type"] ='):
        assert banned not in code, (
            f"`{banned}` is back in the refined board build — that is the pre-NF1.9 normal band "
            f"this story removed")


def test_the_build_no_longer_exposes_a_dispersion_knob():
    """κ was a second, NF1.5-private interval model layered on the shipped one. Its removal is the
    substance of the fix, so a signature that still accepts it would let it come back silently."""
    import inspect

    assert "disp_kappa" not in inspect.signature(R15.build_season_projection).parameters
    assert not hasattr(R15, "calibrate_season_interval"), (
        "the κ calibration was replaced by `verify_season_interval` — coverage is a FLOOR (E2.1-r), "
        "never a target to rescale toward")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The two serving surfaces cannot disagree about which board they are
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _boards(source: str | None) -> pd.DataFrame:
    df = pd.DataFrame({"config_name": ["full_ppr"] * 3, "n_teams": [12] * 3,
                       "player_id": ["a", "b", "c"]})
    if source is not None:
        df["projection_source"] = source
    return df


def test_a_board_with_no_projection_source_refuses_to_export():
    """A board CSV with no lineage column predates NF1.5b — i.e. it was scored from MVP-1 before the
    flip. That is exactly the stale artifact the guard exists to catch, so it refuses rather than
    warning: a silent disagreement between two serving surfaces is worse than a failed export."""
    with pytest.raises(SystemExit, match="no `projection_source`"):
        ex.assert_board_projection_source(_boards(None), "nf1_5", 2026)


def test_a_mismatched_board_refuses_to_export_and_names_the_fix():
    with pytest.raises(SystemExit) as e:
        ex.assert_board_projection_source(_boards("mvp1"), "nf1_5", 2026)
    msg = str(e.value)
    assert "MISMATCH" in msg
    assert "--projection-source nf1_5" in msg, "the refusal must hand back the re-run command"


def test_matching_sources_pass():
    ex.assert_board_projection_source(_boards("nf1_5"), "nf1_5", 2026)
    ex.assert_board_projection_source(_boards("mvp1"), "mvp1", 2026)


def test_the_board_writer_stamps_the_lineage_it_scored():
    """The guard above is only as good as the column, and the column has to be in the emitted
    schema — a board that computes it and then drops it on the way to the CSV proves nothing."""
    from quant_sports_intel_models.football.nfl.fantasy import run_league_board as LB

    assert "projection_source" in LB.BOARD_COLS
    assert set(LB.PROJECTION_SOURCES) == set(ex.PROJECTION_SOURCES)
    assert LB.DEFAULT_PROJECTION_SOURCE == ex.DEFAULT_PROJECTION_SOURCE == "nf1_5", (
        "the served default is the refined board (the NF1.5b re-land); flipping it back is an "
        "operator decision, not a default")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The HONEST FRAME travels with the data
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _lean_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "position": ["QB", "QB", "RB", "RB", "FB", "TE", "WR"],
        # the un-scored/rookie rows carry `independent` because nothing re-ordered THEM — not
        # because the position is market-blind
        "market_lean": ["market-led-adaptive", "independent", "market-led", "independent",
                        "independent", "market-blend", "market-led"],
    })


def test_a_position_is_labelled_by_its_LEARNER_not_by_a_value_count():
    """Counting values would label every real position "mixed" (rookies and unscored veterans always
    carry `independent`), and a caveat that reads as hedging is not the honest frame — it is noise
    a user learns to skip."""
    lean = ex.market_lean_by_position(_lean_frame())
    assert lean == {"QB": "market-led-adaptive", "RB": "market-led", "TE": "market-blend",
                    "WR": "market-led"}


def test_fb_cannot_claim_the_rb_label():
    """FB folds into RB for display and its rows are never re-ordered. Grouping on the RAW position
    lets FB's `independent` land on the RB key first and silently DROP the caveat for every RB."""
    lean = ex.market_lean_by_position(_lean_frame())
    assert lean["RB"] == "market-led"
    assert "FB" not in lean


def test_a_market_blind_board_carries_no_caveat():
    """There is nothing to caveat on a board with no market input — an unconditional note would
    make the real one unreadable."""
    assert ex.market_lean_by_position(pd.DataFrame({"position": ["QB"]})) == {}


def test_conflicting_learners_are_reported_not_resolved():
    df = pd.DataFrame({"position": ["WR", "WR"], "market_lean": ["market-led", "market-blend"]})
    assert ex.market_lean_by_position(df)["WR"].startswith("mixed:")


def test_the_caveat_never_claims_to_beat_the_market_it_uses():
    """⛔ The sentence this whole re-land must not be allowed to drift into.

    The re-grade DID reproduce beats-ADP (+0.022 pooled, vs the served MVP-1 board's −0.059), but the
    payload note carries NO superiority claim at all, on purpose: (a) at a market-leaning position the
    board incorporates the consensus it would be compared to, so an independent-edge claim there is
    false; (b) the result is NOT positive at every position — RB is a wash — and a browse surface has
    no room for that qualification; (c) ECR/ESPN/Sleeper still order better than we do, so an
    unqualified "beats the market" would be read as a claim we cannot support. The claim belongs to
    the receipts surface that can show its working."""
    note = ex.MARKET_LEAN_NOTE.lower()
    assert "incorporates market consensus" in note
    assert "not an independent read on the market" in note
    assert "re-ordering" in note and "not a re-pricing" in note
    for overclaim in ("we beat", "beat the market", "beat consensus", "every position",
                      "all four", "our edge", "guaranteed", "more accurate"):
        assert overclaim not in note, f"the payload caveat has drifted into a claim: {overclaim!r}"
