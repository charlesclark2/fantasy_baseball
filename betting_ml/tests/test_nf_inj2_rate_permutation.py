"""NF-INJ2 — guards for the rate permutation.

Each clause gets its OWN isolating fixture: a fixture that trips two clauses at once proves neither
(NF-D17), and every clause here is RED-proven against deliberately broken source by
`betting_ml/tests/nf_inj2_red_proof.py` before it is trusted.

⛔ These tests never import `pipeline` (E11.23 — `pipeline/__init__.py` reads the dbt manifest, which
is absent in the fast gate, so an import would crash at COLLECTION rather than skip).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as RP
from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as PC

LEARN = ("QB", "RB", "WR", "TE")


def _frame(n_by_pos=None, *, seed: int = 7) -> pd.DataFrame:
    """A synthetic veteran frame with a WIDE availability spread — which is the whole point: the
    defect only becomes visible when a 17-game starter sits beside a 1-game backup, so a fixture
    with uniform games could not tell the arms apart and every clause below would pass vacuously."""
    rng = np.random.default_rng(seed)
    rows = []
    for pos, n in (n_by_pos or {"QB": 12, "RB": 10}).items():
        for i in range(n):
            g = float(rng.uniform(1.0, 17.0))
            rate = float(rng.uniform(4.0, 22.0))
            rows.append({
                "player_id": f"{pos}{i}", "player_name": f"{pos} {i}", "position": pos,
                "proj_games": g,
                "proj_pass_att": 30.0 * g if pos == "QB" else 0.0,
                "proj_pass_cmp": 20.0 * g if pos == "QB" else 0.0,
                "proj_pass_yds": 220.0 * g if pos == "QB" else 0.0,
                "proj_pass_td": 1.5 * g if pos == "QB" else 0.0,
                "proj_pass_int": 0.7 * g if pos == "QB" else 0.0,
                "proj_rush_att": 12.0 * g if pos == "RB" else 2.0 * g,
                "proj_rush_yds": 50.0 * g if pos == "RB" else 8.0 * g,
                "proj_rush_td": 0.4 * g if pos == "RB" else 0.05 * g,
                "proj_targets": 4.0 * g if pos == "RB" else 0.0,
                "proj_rec": 3.0 * g if pos == "RB" else 0.0,
                "proj_rec_yds": 25.0 * g if pos == "RB" else 0.0,
                "proj_rec_td": 0.15 * g if pos == "RB" else 0.0,
                "proj_fumbles_lost": 0.5,
                "_rate": rate,
            })
    d = pd.DataFrame(rows)
    d["point"] = d["_rate"] * d["proj_games"]
    return d


def _args(d: pd.DataFrame, arm: str, *, eligible=None, score=None):
    return dict(base=d["point"].to_numpy(dtype=float), games=d["proj_games"],
                score=(np.arange(len(d), 0, -1, dtype=float) if score is None else score),
                positions=d["position"], arm=arm, learn_positions=LEARN, line=d,
                eligible=(np.ones(len(d), dtype=bool) if eligible is None else eligible))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The declared field
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_declared_field_is_the_pre_registered_six_plus_the_matched_foil():
    """The field is DECLARED, and `declared_field_size` is what makes that an auditable claim to
    `cv_power.classify_null` (MH2.7). A field that quietly grew or shrank would re-commit the
    selection bias DSR exists to deflate."""
    assert RP.ARMS == ("incumbent", "rate_permute", "stratified", "feasibility_clamp",
                       "mvp1_null", "random_order")
    assert RP.DECLARED_FIELD_SIZE == 6 == len(RP.ARMS)
    assert RP.DEGENERATE_ARMS == ("mvp1_null", "random_order")
    assert set(RP.DEGENERATE_ARMS) <= set(RP.ARMS)
    assert RP.MATCHED_FOIL not in RP.ARMS, "the matched foil is an anchor, never a declared trial"
    assert RP.ALL_ARMS == RP.ARMS + (RP.MATCHED_FOIL,)


def test_an_unknown_arm_raises_instead_of_silently_scoring_the_incumbent():
    """A typo that quietly fell through to the incumbent would make the whole bake-off vacuous —
    every arm would score identically and the report would read like a clean tie."""
    d = _frame()
    with pytest.raises(ValueError, match="unknown arm"):
        RP.assign_targets(**_args(d, "rate_permut"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The mechanism
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_rate_permute_hands_out_the_positions_own_per_game_rate_multiset():
    """THE STORY. The incumbent permutes the season POINT multiset; this permutes the per-game RATE
    multiset. Asserted as a multiset identity per position — not as "the numbers changed"."""
    d = _frame()
    t = RP.assign_targets(**_args(d, "rate_permute"))
    for pos in ("QB", "RB"):
        m = (d["position"] == pos).to_numpy()
        got = np.sort(t[m] / d["proj_games"].to_numpy()[m])
        want = np.sort(d["point"].to_numpy()[m] / d["proj_games"].to_numpy()[m])
        assert np.allclose(got, want), f"{pos}: the RATE multiset was not preserved"


def test_the_incumbent_hands_out_the_positions_own_season_point_multiset():
    """The isolating counterpart: the incumbent preserves the POINT multiset, which is exactly the
    property that lets it move availability between players."""
    d = _frame()
    t = RP.assign_targets(**_args(d, "incumbent"))
    for pos in ("QB", "RB"):
        m = (d["position"] == pos).to_numpy()
        assert np.allclose(np.sort(t[m]), np.sort(d["point"].to_numpy()[m]))


def test_rate_permute_never_moves_a_rows_expected_games():
    """Availability stops being permutable — the defect in one line. Each row's implied games
    (`target / assigned_rate`) must be its OWN games, for every row."""
    d = _frame()
    t = RP.assign_targets(**_args(d, "rate_permute"))
    g = d["proj_games"].to_numpy(dtype=float)
    for pos in ("QB", "RB"):
        m = np.flatnonzero((d["position"] == pos).to_numpy())
        rate_desc = np.sort(d["point"].to_numpy()[m] / g[m])[::-1]
        order = m[np.argsort(-np.arange(len(d), 0, -1, dtype=float)[m], kind="stable")]
        assert np.allclose(t[order], rate_desc * g[order]), (
            "a row's target must be someone else's RATE times its OWN games")


def test_the_matched_foil_differs_from_the_primary_in_exactly_one_thing():
    """NF-D15 (g′). The foil keeps the rate permutation and the level scale and removes ONLY the
    per-player availability channel — every row multiplied by the position MEAN games instead of its
    own. If it differed in two things, a foil that lost would not attribute anything."""
    d = _frame()
    prim = RP.assign_targets(**_args(d, "rate_permute"))
    foil = RP.assign_targets(**_args(d, RP.MATCHED_FOIL))
    g = d["proj_games"].to_numpy(dtype=float)
    for pos in ("QB", "RB"):
        m = np.flatnonzero((d["position"] == pos).to_numpy())
        # identical assigned RATES …
        assert np.allclose(np.sort(prim[m] / g[m]), np.sort(foil[m] / np.mean(g[m])))
        # … and the ONLY difference is the multiplier
        assert np.allclose(foil[m] / prim[m], np.mean(g[m]) / g[m])
    assert not np.allclose(prim, foil), "the foil must not collapse onto the primary"


def test_every_arm_leaves_an_ineligible_row_at_its_mvp1_point():
    """NF1.5b's eligibility contract, which every arm inherits: a player the learner cannot speak to
    keeps his MVP-1 level EXACTLY. Guessing his rank would interleave two different scales."""
    d = _frame()
    elig = np.ones(len(d), dtype=bool)
    elig[[0, 5, 13]] = False
    for arm in RP.ALL_ARMS:
        t = RP.assign_targets(**_args(d, arm, eligible=elig))
        assert np.allclose(t[~elig], d["point"].to_numpy()[~elig]), f"{arm} moved an ineligible row"


def test_mvp1_null_is_the_identity_and_random_order_is_not():
    """The two degenerates are genuinely different things, and neither is a no-op by accident."""
    d = _frame()
    assert np.allclose(RP.assign_targets(**_args(d, "mvp1_null")), d["point"].to_numpy())
    r = RP.assign_targets(**_args(d, "random_order"))
    assert not np.allclose(r, d["point"].to_numpy())
    # …and it is SEEDED, so a degenerate cannot move between runs of the same report
    assert np.allclose(r, RP.assign_targets(**_args(d, "random_order")))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The feasibility bound
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_feasibility_clamp_bounds_the_rescale_by_the_physical_envelope():
    """The bound is PER ROW and derived from `REALIZED_MAX_PER_GAME`, so no scaled line can exceed a
    rate no human has ever posted."""
    d = _frame({"QB": 6})
    d.loc[0, "proj_games"] = 1.5           # a backup whose line would breach if scaled up
    hi = RP.feasible_hi(arm="feasibility_clamp", line=d, positions=d["position"],
                        games=d["proj_games"])
    assert isinstance(hi, np.ndarray) and len(hi) == len(d)
    scaled = d["proj_pass_att"].to_numpy() * hi / d["proj_games"].to_numpy()
    assert (scaled <= PC.REALIZED_MAX_PER_GAME["QB"]["passAtt"] + 1e-6).all()


def test_every_other_arm_keeps_the_shipped_scalar_clamp():
    """An arm must not get a quietly different clamp — that would make the comparison a comparison
    of two things."""
    d = _frame()
    for arm in RP.ALL_ARMS:
        hi = RP.feasible_hi(arm=arm, line=d, positions=d["position"], games=d["proj_games"])
        if arm == "feasibility_clamp":
            assert isinstance(hi, np.ndarray)
        else:
            assert hi == 3.5, f"{arm} received a non-shipped clamp"


def test_a_row_the_envelope_cannot_speak_to_is_unbounded_not_silently_clamped():
    """NF1.7 (a): an unevaluable check is not a finding in either direction. A position the envelope
    does not cover must come back `inf`, never a bound invented from another position's ceiling."""
    d = _frame({"QB": 4})
    d["position"] = "FB"
    assert np.isinf(RP.max_feasible_scale(d, d["position"], d["proj_games"])).all()


def test_the_games_floor_is_inert_on_the_real_population():
    """`GAMES_FLOOR` is a guard against an infinite rate, NOT a tuning knob — and "inert" is a
    MEASUREMENT here rather than a claim in a docstring."""
    d = _frame()
    assert RP.games_floor_binding(d["proj_games"]) == 0
    assert RP.games_floor_binding([0.1, 5.0]) == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The serving policy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_board_still_serves_the_incumbent():
    """DEPLOY-HELD. Nothing in this story serves until the PM records a disposition."""
    assert RP.SERVED_ARM == "incumbent"
    RP.assert_coherent()


def test_serving_an_uncleared_arm_is_refused(monkeypatch):
    """A bare flag flip cannot ship a result the record does not support — the check runs at import,
    so the process that flipped it fails rather than the board changing (NF-D22's governance)."""
    monkeypatch.setattr(RP, "SERVED_ARM", "rate_permute")
    monkeypatch.setattr(RP, "GATE_STATUS", "UNRUN")
    with pytest.raises(RuntimeError, match="GATE_STATUS"):
        RP.assert_coherent()


def test_serving_a_cleared_arm_without_a_pm_disposition_is_refused(monkeypatch):
    """Clearing the gates and DECIDING to ship are different facts — NF-D21/NF-D22 were both burned
    by a record that had collapsed them into one flag."""
    monkeypatch.setattr(RP, "SERVED_ARM", "rate_permute")
    monkeypatch.setattr(RP, "GATE_STATUS", "CLEARED")
    monkeypatch.setattr(RP, "PM_DISPOSITION_RECORDED", False)
    with pytest.raises(RuntimeError, match="PM disposition"):
        RP.assert_coherent()


def test_a_degenerate_can_never_be_served(monkeypatch):
    """An arm pre-registered to LOSE must not be reachable as a serving choice, even with the gate
    and disposition flags set — it exists to be eliminated by the metric, not to ship."""
    monkeypatch.setattr(RP, "SERVED_ARM", "mvp1_null")
    monkeypatch.setattr(RP, "GATE_STATUS", "CLEARED")
    monkeypatch.setattr(RP, "PM_DISPOSITION_RECORDED", True)
    with pytest.raises(RuntimeError, match="DEGENERATE"):
        RP.assert_coherent()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# One implementation, both callers
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_frame_bridge_reads_every_envelope_field_through_the_shared_map():
    """`frame_coherence_summary` must read EVERY field the envelope covers, via the shared
    `PARQUET_FIELD` map — so the violation count a bake-off arm scores and the count the publish
    guard reads on the served board are the SAME measurement, not two maps that can drift."""
    d = _frame({"RB": 4})
    # a breach the map must SEE: only reachable if the receiving fields are read, not just passing
    d.loc[0, "proj_rec_yds"] = PC.REALIZED_MAX_PER_GAME["RB"]["recYds"] * d.loc[0, "proj_games"] * 3
    s = PC.frame_coherence_summary(d)
    assert s["applicable"] is True
    assert s["n_violating_players"] == 1
    assert {v["stat"] for v in s["violations"]} == {"recYds"}
    # …and the bridge must offer every envelope field it can, not a hand-picked subset
    row = PC.frame_rows(d)[0]
    for field, col in PC.PARQUET_FIELD.items():
        if col in d.columns:
            assert field in row, f"{field} is in the shared map but the bridge dropped it"


def test_the_shipping_path_delegates_to_the_one_arm_kernel():
    """`nf1_model.apply_learned_ordering` must DELEGATE to `assign_targets`, not carry its own copy
    of the permutation. Two implementations is how the arm a study scored and the arm a board serves
    drift apart while every test stays green (NF-C0e: wired ≠ invoked).

    Asserted by BEHAVIOUR, not by grep: the shipping function is driven under a non-incumbent arm
    and its output must match the kernel's assignment. A private re-implementation would return the
    incumbent's permutation and fail here."""
    from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    d = _frame({"QB": 10, "RB": 10})
    score = np.arange(len(d), 0, -1, dtype=float)
    out = M1.apply_learned_ordering(d, score, positions=LEARN, arm="rate_permute")
    base = SP.score_line(d.copy(), prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)
    want = RP.assign_targets(base=base, games=d["proj_games"], score=score,
                             positions=d["position"], eligible=np.ones(len(d), dtype=bool),
                             arm="rate_permute", learn_positions=LEARN, line=d)
    # ⚠️ ASSERTED ON `nf1_scale`, NOT on the re-scored point, and the reason is a real property of
    # the shipping path: `apply_learned_level` RECOMPUTES `proj_fumbles_lost` from the scaled
    # carries+receptions instead of scaling it, so the achieved PPR lands ~0.5% off the assigned
    # target. `nf1_scale` IS the kernel's target expressed as the clamped rescale, so it compares
    # the two implementations exactly rather than through that pre-existing imprecision.
    want_scale = np.round(np.clip(np.where(base > 1e-6, want / np.where(base > 1e-6, base, 1.0),
                                           1.0), 0.30, 3.5), 4)
    got_scale = pd.to_numeric(out["nf1_scale"], errors="coerce").to_numpy(dtype=float)
    assert np.allclose(got_scale, want_scale, atol=1e-4), (
        "the shipping ordering function did not produce the kernel's assignment — it is carrying a "
        "second implementation")
    inc = M1.apply_learned_ordering(d, score, positions=LEARN, arm="incumbent")
    inc_scale = pd.to_numeric(inc["nf1_scale"], errors="coerce").to_numpy(dtype=float)
    moved = ~np.isclose(got_scale, inc_scale, atol=1e-4)
    assert moved.sum() >= 10, (
        "the arm argument had no effect — the shipping path is ignoring it (and a fixture where the "
        "two arms agree everywhere would make this clause vacuous)")
