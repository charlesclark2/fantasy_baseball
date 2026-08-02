"""E7.15 H3 — guards for the player-level-structure mechanism.

Fast-gate, pure (no IO). Several of these were written to FAIL on the pre-fix source rather than to
pass vacuously — each is marked ⭐ REGRESSION with the defect it pins.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.h_harness import Anchor, evaluate_anchors
from betting_ml.scripts.milb_mle.level_ladder import LadderSpec, build_transitions, fit_ladder
from betting_ml.scripts.milb_mle.milb_mle import PartialPoolProjector, clone_projector
from betting_ml.scripts.milb_mle.player_structure import (
    MIN_POOLABLE_ROWS,
    PLAYER_SHUFFLED,
    TRAJ_LADDER,
    TRAJ_PRESENT,
    TRAJ_RAW,
    W_DEDUP,
    W_IDENTITY,
    PlayerSpec,
    apply_player_structure,
    bucket_col_for,
    dedup_weights,
    extra_cols_for,
    level_tenure,
    player_coverage,
    player_row_counts,
    player_structure_census,
    shuffled_player_ids,
    trajectory_delta,
    weight_column_for,
)

_LEVELS = ["Single-A", "High-A", "Double-A", "Triple-A"]


def _pairs(n_players: int = 40, seed: int = 7) -> pd.DataFrame:
    """A pairs frame with the real shape: variable rows per player, a shared label per player, and a
    prospect population several times the labelled one."""
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_players):
        n_lvl = 1 + (p % 4)
        labelled = p % 3 != 0          # ~2/3 labelled, the rest prospects
        mlb = float(rng.uniform(0.28, 0.36))
        for i in range(n_lvl):
            rows.append({
                "player_id": f"P{p:03d}", "level": _LEVELS[i], "league": "L1",
                "minor_woba": float(rng.uniform(0.28, 0.40)),
                "minor_pa": float(rng.integers(180, 600)),
                "age": float(rng.uniform(19, 25)),
                "first_minor_season": 2015 + i, "last_minor_season": 2015 + i + (p % 3),
                "debut_cohort": 2019 + (p % 4) if labelled else None,
                "has_mlb_label": labelled, "is_prospect": not labelled,
                "mlb_woba": mlb if labelled else None,
                "mlb_pa": float(rng.integers(150, 1200)) if labelled else None,
            })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════════════
# The incumbent must survive untouched
# ══════════════════════════════════════════════════════════════════════════════════════


def test_default_spec_is_a_byte_noop():
    """`PlayerSpec()` must be the incumbent — the same discipline as ContextSpec()/LadderSpec()."""
    spec = PlayerSpec()
    assert spec.is_noop and spec.label == "baseline"
    assert weight_column_for(spec, None) is None
    assert extra_cols_for(spec) == ()
    assert bucket_col_for(spec) is None


def test_identity_weight_is_constant_so_the_noop_anchor_is_a_real_noop():
    df = _pairs()
    out = apply_player_structure(df, PlayerSpec(weight_mode="identity"), "woba")
    w = out[W_IDENTITY].to_numpy(float)
    assert np.allclose(w, w[0]), "the identity weight must be constant or the no-op anchor is not one"


def test_off_mode_inherits_the_foils_own_weight_not_none():
    """⭐ REGRESSION — a pitcher arm whose shipped config carries `w:mlb_pa` must not silently DROP it.

    If `off` returned None, every H3 arm on the pitcher side would be testing TWO changes at once (the
    new mechanism AND the removal of label-precision weighting) and no result would be attributable.
    """
    assert weight_column_for(PlayerSpec(), "mlb_pa") == "mlb_pa"
    assert weight_column_for(PlayerSpec(weight_mode="dedup"), "mlb_pa") == W_DEDUP


def test_dedup_multiplies_the_base_weight_rather_than_replacing_it():
    df = _pairs()
    n = player_row_counts(df).to_numpy(float)
    base = pd.to_numeric(df["mlb_pa"], errors="coerce")
    base = base.fillna(float(base.median()))
    got = dedup_weights(df, "mlb_pa", power=1.0).to_numpy(float)
    assert np.allclose(got, base.to_numpy(float) / n)


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ The matched foil for the random intercept
# ══════════════════════════════════════════════════════════════════════════════════════


def test_shuffled_grouping_preserves_the_group_size_multiset_on_the_fitted_population():
    """⭐ REGRESSION (the defect the coverage fix exposed) — a GLOBAL permutation unmatches the foil.

    The pairs table is several times the labelled rows, so permuting over ALL rows scatters the fitted
    subset's ids across the whole player pool: on live data that turned 661 true blocks into 1,614
    near-singleton ones, i.e. a foil 2.4x wider with almost no pooling. Its loss would then be partly
    "a badly-conditioned wide block" rather than "the grouping is wrong", while the report looked
    healthy. FAILS on the pre-fix source.
    """
    df = _pairs()
    mask = df["has_mlb_label"].to_numpy(bool)
    shuffled = shuffled_player_ids(df, within=pd.Series(mask, index=df.index))

    true_sizes = sorted(df.loc[mask].groupby("player_id").size().tolist())
    foil_sizes = sorted(shuffled[mask].value_counts().tolist())
    assert true_sizes == foil_sizes, "the shuffled block must have the SAME group-size multiset"
    assert df.loc[mask, "player_id"].nunique() == shuffled[mask].nunique()


def test_a_global_shuffle_would_NOT_be_matched_so_the_guard_above_is_not_vacuous():
    """The negative control for the guard above: prove the unmatched form really is unmatched, so a
    passing test cannot be an accident of the fixture."""
    df = _pairs()
    mask = df["has_mlb_label"].to_numpy(bool)
    global_shuffle = shuffled_player_ids(df, within=None)
    true_sizes = sorted(df.loc[mask].groupby("player_id").size().tolist())
    foil_sizes = sorted(global_shuffle[mask].value_counts().tolist())
    assert true_sizes != foil_sizes


def test_apply_uses_the_metric_specific_fitted_mask_for_the_shuffle():
    df = _pairs()
    mask = df["has_mlb_label"].to_numpy(bool) & df["minor_woba"].notna().to_numpy(bool)
    out = apply_player_structure(df, PlayerSpec(player_re=True, shuffle_players=True), "woba",
                                 fitted_mask=pd.Series(mask, index=df.index))
    true_sizes = sorted(out.loc[mask].groupby("player_id").size().tolist())
    foil_sizes = sorted(out.loc[mask, PLAYER_SHUFFLED].value_counts().tolist())
    assert true_sizes == foil_sizes


def test_shuffle_is_deterministic():
    df = _pairs()
    a = shuffled_player_ids(df, within=df["has_mlb_label"])
    b = shuffled_player_ids(df, within=df["has_mlb_label"])
    assert a.equals(b)


def test_shuffle_foil_requires_the_re_it_foils():
    with pytest.raises(ValueError, match="FOIL FOR player_re"):
        PlayerSpec(shuffle_players=True)


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ Coverage — the mechanism's own units, over the FITTED population
# ══════════════════════════════════════════════════════════════════════════════════════


def test_coverage_denominator_is_the_fitted_population_not_the_whole_pairs_table():
    """⭐ REGRESSION — a fit-side mechanism scored over the prospect rows it never touches.

    Measuring over everything understated every arm toward the inert threshold (live: 81.2% for the
    random intercept against the 94.2% the fit actually gets) and, worse, made the true and shuffled
    blocks LOOK matched at 9,804 apiece. FAILS on the pre-fix source.
    """
    df = _pairs()
    mask = pd.Series(df["has_mlb_label"].to_numpy(bool), index=df.index)
    spec = PlayerSpec(player_re=True)
    out = apply_player_structure(df, spec, "woba", fitted_mask=mask)

    all_rows = player_coverage(out, spec, None)
    fitted = player_coverage(out, spec, None, fitted_mask=mask)
    assert fitted["n_rows"] == int(mask.sum()) < all_rows["n_rows"]
    assert fitted["n_player_blocks"] == df.loc[mask.to_numpy(), "player_id"].nunique()
    assert fitted["n_player_blocks"] < all_rows["n_player_blocks"]


@pytest.mark.parametrize("spec", [
    PlayerSpec(weight_mode="dedup"),
    PlayerSpec(weight_mode="dedup_sqrt"),
    PlayerSpec(player_re=True),
    PlayerSpec(trajectory="raw"),
    PlayerSpec(tenure=True),
])
def test_every_mechanism_reports_activity_in_its_own_units(spec):
    """A fit-side arm moves NO feature value, so a feature-diff activity check would report 0% for all
    of them and the `must_move` guard would block the slice for the wrong reason. Each mechanism must
    report the activity of the thing it actually changes."""
    df = _pairs()
    mask = pd.Series(df["has_mlb_label"].to_numpy(bool), index=df.index)
    out = apply_player_structure(df, spec, "woba", fitted_mask=mask)
    cov = player_coverage(out, spec, None, fitted_mask=mask)
    assert cov["pct_rows_moved"] > 1.0, f"{spec.label} would be judged INERT"


def test_the_foil_itself_moves_nothing():
    df = _pairs()
    spec = PlayerSpec()
    out = apply_player_structure(df, spec, "woba")
    assert player_coverage(out, spec, None)["pct_rows_moved"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════
# Trajectory
# ══════════════════════════════════════════════════════════════════════════════════════


def test_first_level_row_has_no_predecessor_and_is_flagged_not_fabricated():
    df = _pairs()
    traj = trajectory_delta(df, "woba", None)
    first_rows = df.groupby("player_id")["level"].transform(
        lambda s: s.map({lv: i for i, lv in enumerate(_LEVELS)}) ==
        s.map({lv: i for i, lv in enumerate(_LEVELS)}).min())
    assert (traj.loc[first_rows.to_numpy(bool), "present"] == 0.0).all()
    assert (traj.loc[first_rows.to_numpy(bool), "delta"] == 0.0).all()
    assert (traj.loc[~first_rows.to_numpy(bool), "present"] == 1.0).all()


def test_trajectory_delta_is_the_previous_level_difference():
    df = pd.DataFrame({
        "player_id": ["A", "A", "A"], "level": ["Single-A", "High-A", "Double-A"],
        "minor_woba": [0.30, 0.34, 0.31], "minor_pa": [300.0] * 3,
        "first_minor_season": [2015, 2016, 2017], "last_minor_season": [2015, 2016, 2017],
    })
    traj = trajectory_delta(df, "woba", None)
    assert traj["delta"].tolist() == pytest.approx([0.0, 0.04, -0.03])


def test_ladder_translation_changes_the_delta_so_the_matched_foil_is_not_a_tie_by_construction():
    """`T2_traj_raw` foils the ladder's contribution. If the ladder could not change the delta the
    comparison would be vacuous — a mechanism that cannot act (NF1.9)."""
    df = _pairs(n_players=400)
    trans = build_transitions(df, "woba")
    fit = fit_ladder(trans, LadderSpec(mode="direct", weighted=True), "woba")
    assert not fit.fallbacks, "fixture too thin — the rungs fell back to identity"
    raw = trajectory_delta(df, "woba", None)["delta"].to_numpy(float)
    lad = trajectory_delta(df, "woba", fit)["delta"].to_numpy(float)
    assert not np.allclose(raw, lad)


def test_a_thin_ladder_degrades_to_identity_and_that_must_be_visible_not_silent():
    """⭐ The degradation the test above found: below `MIN_RUNG_N` every rung falls back to identity, so
    `T1_traj_ladder` becomes BYTE-IDENTICAL to `T2_traj_raw` and the matched-foil comparison is a pass
    on nothing — the H2 inert-anchor shape in a third costume.

    It must be DETECTABLE rather than inferred from a near-zero margin, which is why the runner reads
    `fit.fallbacks` per fold and reports a vacuous ladder comparison explicitly.
    """
    df = _pairs(n_players=60)
    fit = fit_ladder(build_transitions(df, "woba"),
                     LadderSpec(mode="direct", weighted=True), "woba")
    assert fit.fallbacks, "this fixture is meant to be thin"
    raw = trajectory_delta(df, "woba", None)["delta"].to_numpy(float)
    lad = trajectory_delta(df, "woba", fit)["delta"].to_numpy(float)
    assert np.allclose(raw, lad), "a fully-identity ladder IS a no-op — that is the hazard"


def test_trajectory_and_tenure_enter_as_unpenalized_extra_regressors():
    assert extra_cols_for(PlayerSpec(trajectory="ladder")) == (TRAJ_LADDER, TRAJ_PRESENT)
    assert extra_cols_for(PlayerSpec(trajectory="raw")) == (TRAJ_RAW, TRAJ_PRESENT)
    assert len(extra_cols_for(PlayerSpec(tenure=True))) == 2


def test_level_tenure_counts_repeated_seasons():
    df = _pairs()
    ten = level_tenure(df)
    assert (ten["level_tenure_years"] >= 0).all()
    assert ten["player_n_levels"].max() <= len(_LEVELS)


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ No new projector class — the clone landmine
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_random_intercept_rides_machinery_clone_projector_already_carries():
    """⭐ REGRESSION-BY-DESIGN — a `PartialPoolProjector` SUBCLASS would be silently downgraded.

    `clone_projector` is isinstance-dispatched and returns a PLAIN `PartialPoolProjector`, so a
    subclass's extra config would vanish on every expanding-window refit and the arm would score AS THE
    FOIL under its own name (the documented E7.12-S5 landmine, and the H2 inert-arm class one layer
    out). Using `bucket_col`/`bucket_intercept` means the config round-trips.
    """
    proj = PartialPoolProjector(prior_scale=2.0, bucket_col="player_id", bucket_intercept=True)
    clone = clone_projector(proj)
    assert type(clone) is PartialPoolProjector
    assert clone.bucket_col == "player_id" and clone.bucket_intercept is True
    assert clone.bucket_slope is False


def test_bucket_col_selects_the_true_or_shuffled_grouping():
    assert bucket_col_for(PlayerSpec(player_re=True)) == "player_id"
    assert bucket_col_for(PlayerSpec(player_re=True, shuffle_players=True)) == PLAYER_SHUFFLED
    assert bucket_col_for(PlayerSpec()) is None


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ A scoped refutation must not veto an unrelated mechanism
# ══════════════════════════════════════════════════════════════════════════════════════


def _mae(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols, index=[2019, 2020, 2021, 2022])


def test_a_scoped_refutation_disqualifies_only_its_defender():
    """⭐ REGRESSION (NF-D16 g‴, one instrument over) — a matched foil for ONE mechanism must not veto a
    structurally unrelated candidate that happens to share the metric.

    `A_re_shuffled` foils the random intercept and says nothing about the trajectory arms. A field-wide
    veto would reject a legitimately-better arm for another mechanism's sin — exactly the failure a
    single peeking ceiling produced in NF-D16. FAILS on the pre-fix source, which returned a DROP.
    """
    mae = _mae(
        L0_foil=[0.10, 0.10, 0.10, 0.10],
        P3_player_re=[0.11, 0.11, 0.11, 0.11],      # loses to its own shuffled foil
        A_re_shuffled=[0.09, 0.09, 0.09, 0.09],
        T1_traj_ladder=[0.08, 0.08, 0.08, 0.08],    # innocent, and better than everything
        A_traj_shuffled=[0.12, 0.12, 0.12, 0.12],
    )
    anchors = (
        Anchor("A_re_shuffled", "refute", "shuffled grouping", "regularization, not players",
               defender="P3_player_re"),
        Anchor("A_traj_shuffled", "refute", "shuffled trajectory", "any dispersed regressor",
               defender="T1_traj_ladder"),
    )
    cov = {a.label: {"pct_rows_moved": 90.0} for a in anchors}
    out, verdict, _reason = evaluate_anchors(mae, anchors, "T1_traj_ladder", "L0_foil", coverage=cov)

    assert verdict is None, "a scoped refutation must not BLOCK/DROP the whole metric"
    assert "P3_player_re" in out["refuted_arms"]
    assert "T1_traj_ladder" not in out["refuted_arms"]


def test_an_unscoped_refutation_still_vetoes_the_field():
    """The other half: an anchor with NO defender is a statement about the SELECTION and must still
    drop the metric — H1 and H2 both rely on that and must not change behaviour."""
    mae = _mae(L0_foil=[0.10] * 4, C1=[0.09] * 4, A_placebo=[0.08] * 4)
    anchors = (Anchor("A_placebo", "refute", "placebo", "not the mechanism"),)
    _out, verdict, reason = evaluate_anchors(
        mae, anchors, "C1", "L0_foil", coverage={"A_placebo": {"pct_rows_moved": 90.0}})
    assert verdict == "DROP" and "MECHANISM REFUTED" in reason


# ══════════════════════════════════════════════════════════════════════════════════════
# Census
# ══════════════════════════════════════════════════════════════════════════════════════


def test_census_reports_replication_and_poolability():
    df = _pairs()
    c = player_structure_census(df)
    lab = df[df["has_mlb_label"]]
    assert c["n_rows"] == len(lab)
    assert c["n_players"] == lab["player_id"].nunique()
    assert c["mean_rows_per_player"] == pytest.approx(len(lab) / lab["player_id"].nunique(), rel=1e-6)
    counts = lab.groupby("player_id").size()
    expect = 100.0 * lab["player_id"].isin(counts[counts >= MIN_POOLABLE_ROWS].index).mean()
    assert c["pct_rows_poolable"] == pytest.approx(expect, abs=0.01)


def test_census_is_empty_safe():
    assert player_structure_census(pd.DataFrame(columns=["player_id", "has_mlb_label"]))["n_rows"] == 0


def test_invalid_modes_raise():
    with pytest.raises(ValueError):
        PlayerSpec(weight_mode="nope")
    with pytest.raises(ValueError):
        PlayerSpec(trajectory="nope")


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ The null-analysis extrapolation must extrapolate the gate it names
# ══════════════════════════════════════════════════════════════════════════════════════


def test_null_analysis_extrapolation_matches_its_own_gate():
    """⭐ REGRESSION (found 2026-08-01 reading a LIVE H3 result) — `folds_needed_DSR` was computed
    against a DIFFERENT, easier benchmark than the DSR gate it claims to extrapolate.

    `dsr_report` passes the real per-arm `trial_sharpes`, so `sr0` scales with the field's cross-trial
    dispersion; the extrapolation omitted them and silently substituted a softer bar. Live consequence:
    batter `bb_pct` reported "0 extra seasons needed" against a gate reading DSR 0.607 vs a 0.95 floor —
    an arm described as on the doorstep that was not close (the corrected figure is +129 seasons).

    The invariant that makes it impossible to drift again: at `k = n` the extrapolation MUST reproduce
    the gate's own DSR. FAILS on the pre-fix source.
    """
    import numpy as np
    from betting_ml.scripts.milb_mle.h_harness import dsr_report
    from betting_ml.utils.overfitting import deflated_sharpe

    rng = np.random.default_rng(11)
    folds = list(range(2015, 2026))
    arms = ["L0_foil"] + [f"C{i}" for i in range(6)]
    mae = pd.DataFrame(
        {a: 0.030 - (0.0004 * i) + rng.normal(0, 0.0015, len(folds)) for i, a in enumerate(arms)},
        index=folds)
    eligible = [a for a in arms if a != "L0_foil"]

    gate = dsr_report(mae, eligible)["eligible"]
    skill = (mae["L0_foil"] - mae[gate["arm"]]).dropna().to_numpy(float)

    def _sr(s):
        sd = float(np.std(s, ddof=1)) if len(s) > 2 else 0.0
        return float(np.mean(s) / sd) if sd > 0 else 0.0

    trial_sharpes = [_sr((mae["L0_foil"] - mae[c]).dropna().to_numpy(float)) for c in eligible]

    matched = deflated_sharpe(np.resize(skill, len(skill)), n_trials=len(eligible),
                              trial_sharpes=trial_sharpes).dsr
    assert matched == pytest.approx(gate["dsr"], abs=1e-9), "the extrapolation must reproduce the gate"

    # negative control: the pre-fix call (no trial_sharpes) is a DIFFERENT, easier benchmark
    unmatched = deflated_sharpe(np.resize(skill, len(skill)), n_trials=len(eligible)).dsr
    assert unmatched != pytest.approx(gate["dsr"], abs=1e-6)
    assert unmatched > gate["dsr"], "the pre-fix benchmark was the SOFTER one — that is why it misled"
