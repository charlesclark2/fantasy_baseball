"""NF-W7c — guards for the arbitrary-league fantasy-point ASSEMBLY.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS FILE DEFENDS
═══════════════════════════════════════════════════════════════════════════════════════════════════

Four properties, and each one is a defect class this repo has already been bitten by:

  1. ⭐ THERE IS NO FOURTH SCORER. NF-EPIC 1 put ONE scoring policy in three implementations under
     a merge-gate parity test. The assembly must not become a fourth: it reads
     `ScoringRules.points_for` and dots the result with the draw. The guard proves the linear form
     equals `fantasy_engine.scoring.score_players` EXACTLY on real published payload rows, so a
     scoring-rule change still moves exactly three implementations and this follows for free.

  2. THE COPULA LAYER ADDS ONLY DEPENDENCE. Σ=I is byte-identical to the independent draw, and no
     Σ moves a leg's marginal. Without this, "the marginals are frozen" is a claim, not a fact.

  3. AN UNEVALUABLE ESTIMATE NEVER BECOMES "INDEPENDENT". NF1.7 (a): a check that did not run is
     not a pass. Both estimators REFUSE below the row floor rather than returning an identity, and
     a structurally-constant leg is RECORDED rather than silently absorbed.

  4. LABELLING CARRIES WHERE IT BITES AND NOWHERE ELSE. NF-W6d's promote blocker binds the
     assembly: a Phase-C DEFAULT among the stats a league PRICES must surface; a default on a leg
     the league weights at 0 must NOT (a warning about something that cannot matter is the
     alert-fatigue direction E11.30 warns about). Both directions are asserted.

⛔ ANCHORED IN ITS OWN CLAUSES (the E9.60 coupling trap): nothing here is bolted onto an older
story's guard, and every clause fails only for NF-W7c's property.

⚠️ NF-D17: where a clause lives inside an `and`-composed rule, its fixture SATISFIES the other
clauses so only the named one can flip the result — otherwise the guard passes on nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pd = pytest.importorskip("pandas", reason="the assembly is a pandas/numpy surface")

from app.backend.services import projection_fields  # noqa: E402
from quant_sports_intel_models.fantasy_engine.league_config import (  # noqa: E402
    LeagueConfig,
    ScoringRules,
)
from quant_sports_intel_models.fantasy_engine.scoring import score_players  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import joint_draw as JD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD  # noqa: E402

_PARITY_FIXTURE = Path(__file__).parent / "fixtures" / "nf_epic1_projection_rows.json"
_SKILL = ("QB", "RB", "WR", "TE")


# ── shared fixtures ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def payload_rows() -> list[dict]:
    """REAL published projection rows (NF-C0e: never hand-written JSON — a fixture an author typed
    cannot disconfirm the author's own assumption about what the payload carries)."""
    rows = [r for r in json.loads(_PARITY_FIXTURE.read_text())
            if str(r.get("pos", "")).upper() in _SKILL]
    assert len(rows) >= 50, "too thin to exercise four positions"
    return rows


@pytest.fixture(scope="module")
def stat_matrix(payload_rows) -> np.ndarray:
    """(n, 13) raw stat lines lifted from the payload in `FA.LEGS` order.

    ⭐ The lift routes leg → `FA.STAT_KEY` → `projection_fields.STAT_FIELD` → payload field, so it
    also exercises the three-way key pin: a canonical key renamed in any scoring implementation
    makes this KeyError rather than silently zeroing a term."""
    return np.array(
        [[float(r.get(projection_fields.STAT_FIELD[FA.STAT_KEY[leg]]) or 0.0) for leg in FA.LEGS]
         for r in payload_rows], dtype=float)


def _engine_frame(payload_rows, stat_matrix) -> pd.DataFrame:
    """The same lines under `NFL_PROFILE`'s own column names — a pure rename, no arithmetic (any
    arithmetic here would make the parity result a statement about this helper)."""
    df = pd.DataFrame({LP.NFL_PROFILE.stat_columns[FA.STAT_KEY[leg]]: stat_matrix[:, i]
                       for i, leg in enumerate(FA.LEGS)})
    df[LP.NFL_PROFILE.position_column] = [str(r["pos"]).upper() for r in payload_rows]
    return df


def _banks(n: int, seed: int = 0, atom_leg: int | None = 0) -> np.ndarray:
    """(n, 13, 199) monotone quantile banks, one with a zero atom (the substrate's real shape)."""
    rng = np.random.default_rng(seed)
    b = np.sort(rng.gamma(2.0, 3.0, size=(n, FA.N_LEGS, FA.N_LEVELS)), axis=2)
    if atom_leg is not None:
        b[:, atom_leg, :80] = 0.0
    return b


def _served_map(source: str = SDSD.SOURCE_W6D_SHIP) -> dict[str, dict]:
    return {cell: {"form": "knn_quantile", "source": source, "calibration_warning": None}
            for cell in SDD.substrate_cells()}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The stat-key map — three INDEPENDENTLY red-provable clauses (NF-D17)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_stat_key_map_is_exhaustive_injective_and_lands_in_the_profile():
    assert FA.assert_stat_key_map()["n_legs"] == 13
    assert set(FA.STAT_KEY) == set(SDD.ALL_STATS)


def test_only_the_exhaustiveness_clause_fires_on_a_missing_leg(monkeypatch):
    """The fixture keeps the map injective and profile-valid, so ONLY exhaustiveness can fail."""
    trimmed = {k: v for k, v in FA.STAT_KEY.items() if k != "two_pt"}
    monkeypatch.setattr(FA, "STAT_KEY", trimmed)
    with pytest.raises(ValueError, match="does not cover the substrate legs"):
        FA.assert_stat_key_map()


def test_only_the_injectivity_clause_fires_on_a_duplicated_key(monkeypatch):
    """Still exhaustive (13 keys) and every value is a real profile column — only injectivity can
    fail, so a pass here is about injectivity and nothing else."""
    dupe = dict(FA.STAT_KEY, two_pt="rec")
    monkeypatch.setattr(FA, "STAT_KEY", dupe)
    with pytest.raises(ValueError, match="not injective"):
        FA.assert_stat_key_map()


def test_only_the_profile_clause_fires_on_an_unknown_canonical_key(monkeypatch):
    """Exhaustive and injective — the single defect is a key the profile does not carry."""
    bogus = dict(FA.STAT_KEY, two_pt="two_point_conversions_typo")
    monkeypatch.setattr(FA, "STAT_KEY", bogus)
    with pytest.raises(ValueError, match="the NFL profile does not carry"):
        FA.assert_stat_key_map()


def test_the_canonical_keys_exist_in_all_three_scoring_implementations():
    """⭐ The three-way pin. `STAT_FIELD` is itself mirrored between the Lambda and the browser TS
    (`test_nf_epic1_payload_split`), so landing inside it + the profile reaches all three."""
    missing_backend = sorted(set(FA.STAT_KEY.values()) - set(projection_fields.STAT_FIELD))
    assert not missing_backend, f"canonical keys unknown to the Lambda scorer: {missing_backend}"
    ts = (Path(__file__).resolve().parents[2] / "frontend" / "lib" / "league-config.ts").read_text()
    absent = [k for k in FA.STAT_KEY.values() if f'"{k}"' not in ts]
    assert not absent, f"canonical keys absent from the browser STAT_FIELD: {absent}"


def test_a_scorable_term_lands_in_exactly_one_bucket():
    """Modeled / skill-gap / out-of-scope PARTITION the profile — a new scorable term cannot land
    nowhere (and then be silently scored as 0) or in two places."""
    buckets = [set(FA.STAT_KEY.values()), set(FA.SKILL_UNMODELED_KEYS), set(FA.OUT_OF_SCOPE_KEYS)]
    assert set().union(*buckets) == set(LP.NFL_PROFILE.stat_columns)
    for i, a in enumerate(buckets):
        for b in buckets[i + 1:]:
            assert not (a & b), f"a term is in two buckets: {sorted(a & b)}"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⭐ NO FOURTH SCORER — the assembly's linear form IS `fantasy_engine`
# ═══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("preset", sorted(LP.PRESETS))
def test_the_weight_vector_reproduces_score_players_exactly(payload_rows, stat_matrix, preset):
    """THE parity guard. If this holds, NF-W7c adds no scoring implementation — it consumes the
    authority — so the NF-EPIC 1 merge gate keeps covering every scoring rule unchanged."""
    config = LP.get_preset(preset)
    frame = _engine_frame(payload_rows, stat_matrix)
    engine = score_players(frame, config, LP.NFL_PROFILE, with_interval=False)["league_points"]
    mine = np.array([FA.leg_weights(config, str(r["pos"]).upper()) @ stat_matrix[i]
                     for i, r in enumerate(payload_rows)])
    assert np.allclose(engine.to_numpy(), mine, rtol=0, atol=1e-9), (
        f"{preset}: the assembly's linear form drifted from fantasy_engine — a FOURTH scorer has "
        f"appeared and the NF-EPIC 1 parity gate does not cover it")


def test_that_parity_is_not_vacuous(payload_rows, stat_matrix):
    """Non-vacuity (the INC-38/NF1.7 (a) family): the fixture must actually carry the paid stat
    line, and the presets must price it — otherwise the equality above is 0 == 0."""
    assert float(np.abs(stat_matrix).sum()) > 0, "the lifted stat matrix is all zeros"
    priced = FA.priced_legs(LP.get_preset("full_ppr"), "WR")
    assert len(priced) >= 6, f"the gate league prices only {priced} — parity would be near-trivial"
    scored = np.array([FA.leg_weights(LP.get_preset("full_ppr"), str(r["pos"]).upper())
                       @ stat_matrix[i] for i, r in enumerate(payload_rows)])
    assert float(scored.max()) > 50.0, "no row scores materially — the fixture is inert"


def test_the_presets_price_nothing_the_substrate_cannot_model(payload_rows):
    """Makes the parity guard's scope explicit: the shipped presets have NO unmodeled priced term,
    which is WHY the linear form can equal `score_players` on them."""
    for name in sorted(LP.PRESETS):
        for pos in _SKILL:
            assert FA.unpriced_scored_terms(LP.get_preset(name), pos) == {}, name


def test_a_league_pricing_an_unmodeled_term_is_refused_and_the_gap_is_real(stat_matrix):
    """The other side of the same coin — and the reason the refusal is not pedantry: a league with
    a per-completion bonus genuinely scores MORE than the assembly can express, so scoring the
    missing term as 0 would understate points with no signal anywhere."""
    cfg = LeagueConfig(
        name="cmp_bonus", sport="nfl", n_teams=12,
        scoring=ScoringRules(per_stat=dict(LP.get_preset("full_ppr").scoring.per_stat,
                                           pass_cmp=0.5)),
        roster=LP.get_preset("full_ppr").roster)
    with pytest.raises(ValueError, match="scoring them as 0 would UNDERSTATE"):
        FA.assert_assembly_is_priceable(cfg, "QB")
    waived = FA.assert_assembly_is_priceable(cfg, "QB", allow_unpriced=True)
    assert waived["unpriced_scored_terms"] == {"pass_cmp": 0.5} and not waived["complete"], (
        "allow_unpriced must still RETURN the gap — it is a waiver, not an eraser")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Per-league re-scoring is correct AND different (the arithmetic-checkable fixture)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_half_ppr_minus_standard_is_exactly_half_a_point_per_reception(stat_matrix):
    """⭐ THE arithmetic fixture: the ONLY difference between these two leagues is 0.5/reception,
    so the point difference must be exactly 0.5 × receptions — checkable by hand, on every row."""
    rec = stat_matrix[:, FA.LEGS.index("receptions")]
    for pos in _SKILL:
        w_std = FA.leg_weights(LP.get_preset("standard"), pos)
        w_half = FA.leg_weights(LP.get_preset("half_ppr"), pos)
        delta = stat_matrix @ (w_half - w_std)
        assert np.allclose(delta, 0.5 * rec, atol=1e-9), pos
    assert float(rec.sum()) > 0, "no receptions in the fixture — the check would be 0 == 0"


def test_te_premium_moves_tight_ends_and_only_tight_ends(stat_matrix):
    """A position bonus must reach exactly its position — `points_for`'s per-position argument is
    load-bearing, and a scorer that ignored it would pass every position-agnostic check."""
    full, prem = LP.get_preset("full_ppr"), LP.get_preset("te_premium")
    rec_i = FA.LEGS.index("receptions")
    assert FA.leg_weights(prem, "TE")[rec_i] - FA.leg_weights(full, "TE")[rec_i] == pytest.approx(0.5)
    for pos in ("QB", "RB", "WR"):
        assert np.array_equal(FA.leg_weights(prem, pos), FA.leg_weights(full, pos)), pos


def test_the_same_player_scores_differently_under_two_leagues(stat_matrix):
    """The story's product claim, asserted rather than assumed: re-scoring is a real re-scoring."""
    w_std = FA.leg_weights(LP.get_preset("standard"), "WR")
    w_ppr = FA.leg_weights(LP.get_preset("full_ppr"), "WR")
    assert not np.allclose(stat_matrix @ w_std, stat_matrix @ w_ppr)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The copula layer adds ONLY dependence
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_sigma_identity_is_byte_identical_to_the_independent_draw():
    """The mechanical statement that independence is a SPECIAL CASE of the declared field — which
    is what makes the matched independent foil a fair comparison rather than a different draw."""
    banks, w = _banks(8), np.ones(FA.N_LEGS)
    a = FA.assemble_fp_bank(banks, w, mode="indep", draws=200, seed=5)
    b = FA.assemble_fp_bank(banks, w, mode="copula", corr=np.eye(FA.N_LEGS), draws=200, seed=5)
    assert np.array_equal(a, b), "Σ=I is not the independent draw — the copula layer moves more "\
                                 "than dependence"


def test_no_correlation_matrix_moves_a_leg_marginal():
    """Each leg is still inverse-CDF of a U(0,1), so its marginal is its OWN CERTIFIED BANK for
    any Σ.

    ⚠️ ANCHORED ON THE BANK, NOT ON THE OTHER DRAW MODE. The first cut of this guard compared the
    copula draw to the independent draw — which is blind to anything that moves BOTH (a common
    rescale, a shared clip, a 'variance correction'), and its own red proof caught it staying
    green. The bank is the thing the marginal is certified to be, so that is what it is compared
    against; residual difference is Monte-Carlo only, proven by it SHRINKING as draws grow (a
    fixed tolerance could not tell MC noise from a small systematic shift)."""
    banks = _banks(6, seed=3)
    sigma = JD.psd_clamp(np.full((FA.N_LEGS, FA.N_LEGS), 0.6) + 0.4 * np.eye(FA.N_LEGS))
    leg = FA.LEGS.index("passing_yards")            # continuous: no rounding to blur the read
    idx = [19, 99, 179]                             # the grid's 0.10 / 0.50 / 0.90 levels
    truth = banks[:, leg, idx]
    drifts = []
    for draws in (2_000, 50_000):
        z = np.random.default_rng(11).standard_normal((6, draws, FA.N_LEGS))
        row = []
        for u in (JD.independent_uniforms(z), JD.gaussian_copula_uniforms(z, sigma)):
            drawn = FA.draw_legs(banks, u)[:, :, leg]
            emp = np.quantile(drawn, FA.EVAL_LEVELS[idx], axis=1).T
            row.append(float(np.max(np.abs(emp - truth))))
        drifts.append(max(row))
    assert drifts[1] < drifts[0] / 2.0, (
        f"the drawn marginal does not converge to its own bank as draws grow ({drifts}) — the "
        f"draw layer is moving the certified marginal, not just the joint law")


def test_dependence_moves_the_assembled_dispersion_analytically_and_in_the_draw():
    """NF-MARGIN2 / NF-D20 — a statistic the arm cannot move is décor, not a gate. Both halves."""
    banks, w = _banks(10, seed=4), np.ones(FA.N_LEGS)
    eye = np.eye(FA.N_LEGS)
    sigma = JD.psd_clamp(np.full((FA.N_LEGS, FA.N_LEGS), 0.5) + 0.5 * eye)
    assert FA.assembled_sum_sd(banks, w, sigma).mean() > FA.assembled_sum_sd(banks, w, eye).mean()
    wide = FA.assemble_fp_bank(banks, w, mode="copula", corr=sigma, draws=2_000, seed=9)
    narrow = FA.assemble_fp_bank(banks, w, mode="indep", draws=2_000, seed=9)
    assert (wide[:, 179] - wide[:, 19]).mean() > (narrow[:, 179] - narrow[:, 19]).mean(), (
        "correlated draws do not widen the assembled 10–90 band — the independence foil could "
        "never be beaten on coverage and the gate clause would be inactive")


def test_the_comonotone_anchor_flips_the_NEGATIVELY_weighted_legs():
    """⭐ Two priced legs score NEGATIVELY (fumbles lost, interceptions). The comonotone degenerate
    must co-move in the POINTS direction, not the OUTCOME direction — otherwise yards and
    interceptions rise together, their contributions partly CANCEL in the weighted sum, and the
    'over-correlated ceiling' is neither a ceiling nor the proof that the coverage floor was not
    promoted into a selection criterion (NF-D18)."""
    w = FA.leg_weights(LP.get_preset("full_ppr"), "QB")
    flip = FA.comonotone_flip(w)
    flipped = {leg for leg, f in zip(FA.LEGS, flip) if f}
    assert flipped == {"passing_interceptions", "fumbles_lost"}, flipped
    assert all(w[i] < 0 for i, f in enumerate(flip) if f)
    assert all(w[i] >= 0 for i, f in enumerate(flip) if not f)


def test_the_comonotone_anchor_is_the_MAXIMAL_dispersion_ceiling():
    """The property the flip exists for, measured rather than argued: with real (mixed-sign)
    league weights the comonotone draw must be strictly WIDER than both the independent draw and
    a strongly-correlated copula — that is what makes it the registered ceiling."""
    banks = _banks(12, seed=11, atom_leg=None)
    w = FA.leg_weights(LP.get_preset("full_ppr"), "QB")
    assert (w < 0).any(), "fixture premise: the gate league prices something negatively"
    sigma = JD.psd_clamp(np.full((FA.N_LEGS, FA.N_LEGS), 0.5) + 0.5 * np.eye(FA.N_LEGS))
    def width(mode, corr=None):
        b = FA.assemble_fp_bank(banks, w, mode=mode, corr=corr, draws=4_000, seed=21)
        return float((b[:, 179] - b[:, 19]).mean())
    comono, indep, copula = width("comonotone"), width("indep"), width("copula", sigma)
    assert comono > copula > indep, (
        f"comonotone {comono:.2f} / copula {copula:.2f} / indep {indep:.2f} — the degenerate is "
        f"not the maximal-dispersion ceiling it is registered as")


def test_a_comonotone_draw_without_the_league_weights_is_refused():
    """The flip cannot be guessed from the legs alone — it depends on the league's signs — so the
    orientation is REQUIRED rather than silently defaulted to the outcome direction."""
    with pytest.raises(ValueError, match="needs the league weights to orient the flip"):
        FA._uniforms(np.zeros((2, 3, FA.N_LEGS)), "comonotone", None, None)


def test_a_zero_weight_leg_cannot_influence_the_assembled_distribution():
    """Why the labelling is over PRICED legs: an unpriced leg contributes identically 0, so its
    provenance cannot matter to the answer. Asserted, not argued."""
    banks, w = _banks(6, seed=6), np.ones(FA.N_LEGS)
    w[3] = 0.0
    mutated = banks.copy()
    mutated[:, 3, :] = mutated[:, 3, :] * 100.0 + 500.0
    assert np.array_equal(FA.assemble_fp_bank(banks, w, mode="indep", draws=200, seed=2),
                          FA.assemble_fp_bank(mutated, w, mode="indep", draws=200, seed=2))


def test_integer_legs_draw_integers_and_yardage_stays_continuous():
    banks = _banks(5, seed=8, atom_leg=None)
    z = np.random.default_rng(1).standard_normal((5, 500, FA.N_LEGS))
    drawn = FA.draw_legs(banks, JD.independent_uniforms(z))
    for i, leg in enumerate(FA.LEGS):
        col = drawn[:, :, i]
        assert (col >= 0).all(), f"{leg}: a negative quantity was drawn"
        if leg in FA.INTEGER_LEGS:
            assert np.array_equal(col, np.rint(col)), f"{leg} is a count but drew a fraction"
        else:
            assert not np.array_equal(col, np.rint(col)), f"{leg} is yardage but was rounded"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. An unevaluable estimate never becomes "independent" (NF1.7 (a))
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_raw_rank_estimator_refuses_below_the_row_floor():
    rng = np.random.default_rng(2)
    raw = rng.gamma(2.0, 2.0, size=(FA.MIN_ESTIMATION_ROWS - 1, FA.N_LEGS))
    with pytest.raises(ValueError, match="must not masquerade as independence"):
        FA.position_sigma(raw)


def test_the_pit_estimator_refuses_below_the_row_floor():
    n = FA.MIN_ESTIMATION_ROWS - 1
    rng = np.random.default_rng(2)
    with pytest.raises(ValueError, match="must not masquerade as independence"):
        FA.position_sigma_pit(_banks(n, seed=1, atom_leg=None),
                              rng.gamma(2.0, 2.0, size=(n, FA.N_LEGS)))


def test_a_structurally_constant_leg_is_recorded_not_silently_absorbed():
    """A WR's pass attempts are 0 every week: that leg has no co-movement to estimate. It is
    dropped, embedded as identity, and NAMED — the NF1.9 distinction between 'a mechanism that
    cannot act' and an omission nobody can see."""
    rng = np.random.default_rng(5)
    raw = rng.gamma(2.0, 2.0, size=(300, FA.N_LEGS))
    raw[:, 0] = 0.0
    sigma, note = FA.position_sigma(raw)
    assert note["degenerate_legs"] == [FA.LEGS[0]] and note["n_estimated_legs"] == FA.N_LEGS - 1
    assert np.array_equal(sigma[0], np.eye(FA.N_LEGS)[0]), "a constant leg must embed as identity"
    assert note["estimator"] == "spearman_raw_ranks", "⭐ raw OUTCOME ranks, not residual PITs"


def test_an_all_constant_slice_refuses_rather_than_returning_an_identity():
    raw = np.zeros((300, FA.N_LEGS))
    raw[:, 4] = np.arange(300.0)
    with pytest.raises(ValueError, match="refusing rather than returning a silent identity"):
        FA.position_sigma(raw)


def test_every_declared_arm_has_a_distinct_estimator_and_an_unknown_one_is_refused():
    rng = np.random.default_rng(9)
    raw = rng.gamma(2.0, 2.0, size=(400, FA.N_LEGS))
    banks = _banks(400, seed=2, atom_leg=None)
    sigmas = {a: FA.sigma_for_arm(a, raw=raw, banks=banks, realized=raw)[0] for a in FA.REAL_ARMS}
    for i, a in enumerate(FA.REAL_ARMS):
        for b in FA.REAL_ARMS[i + 1:]:
            assert not np.allclose(sigmas[a], sigmas[b]), f"{a} and {b} estimate the same Σ — the "\
                                                          f"field is narrower than it is declared"
    with pytest.raises(KeyError, match="not in the pre-registered family"):
        FA.sigma_for_arm("joint_whatever", raw=raw)


def test_the_double_probe_is_a_strictly_larger_dependence_than_its_base():
    """`joint_double` is the NF-D20 magnitude probe registered as a REAL arm — it must actually
    probe a larger magnitude, or an under-correcting estimator could hide behind an inert arm."""
    rng = np.random.default_rng(12)
    base_raw = rng.multivariate_normal(
        np.zeros(FA.N_LEGS), JD.psd_clamp(np.full((FA.N_LEGS, FA.N_LEGS), 0.3)
                                          + 0.7 * np.eye(FA.N_LEGS)), size=500)
    base, _ = FA.sigma_for_arm("joint_rank", raw=base_raw)
    doubled, _ = FA.sigma_for_arm("joint_double", raw=base_raw)
    off = ~np.eye(FA.N_LEGS, dtype=bool)
    assert np.abs(doubled[off]).mean() > np.abs(base[off]).mean()


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Labelling carries where it bites — and NOWHERE else
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_default_on_a_priced_leg_surfaces_at_the_assembled_level():
    """NF-W6d's promote blocker, honoured: 'the assembly consumer must read
    `source`/`calibration_warning` and never present a default as a conditional projection'."""
    smap = _served_map()
    smap["WR|receptions"] = {"form": "climatology", "source": SDSD.SOURCE_W6D_DEFAULT,
                             "calibration_warning": "coverage floor met by a wide default"}
    label = FA.assembled_labelling(smap, LP.get_preset("full_ppr"), "WR")
    assert label["source"] == FA.ASSEMBLED_SOURCE_PARTIAL
    assert label["default_priced_legs"] == ["receptions"]
    assert "calibrated DEFAULT" in label["calibration_warning"]
    assert label["leg_calibration_warnings"]["receptions"]


def test_a_default_on_an_UNPRICED_leg_does_not_raise_a_caveat():
    """The other direction, and it is the one that keeps warnings meaningful: standard leagues do
    not score targets, so a calibrated default there cannot move the assembled distribution and
    must not caveat it (E11.30's alert-fatigue direction)."""
    cfg = LP.get_preset("full_ppr")
    assert "targets" not in FA.priced_legs(cfg, "WR"), "fixture premise: targets are unpriced"
    smap = _served_map()
    smap["WR|targets"] = {"form": "climatology", "source": SDSD.SOURCE_W6D_DEFAULT,
                          "calibration_warning": "a wide default"}
    label = FA.assembled_labelling(smap, cfg, "WR")
    assert label["source"] == FA.ASSEMBLED_SOURCE_SHIP and not label["default_priced_legs"]
    assert label["calibration_warning"] is None


def test_an_all_default_priced_set_is_labelled_default_not_partial():
    label = FA.assembled_labelling(_served_map(SDSD.SOURCE_W6D_DEFAULT),
                                   LP.get_preset("full_ppr"), "WR")
    assert label["source"] == FA.ASSEMBLED_SOURCE_DEFAULT


def test_a_missing_cell_for_a_priced_leg_refuses_rather_than_assembling():
    smap = _served_map()
    del smap["WR|receptions"]
    with pytest.raises(KeyError, match="no cell for a PRICED leg"):
        FA.assembled_labelling(smap, LP.get_preset("full_ppr"), "WR")


def test_the_default_source_string_is_imported_from_the_module_that_stamps_it():
    """A re-typed source string would drift silently and the caveat would simply stop firing —
    the NF-C0e wrong-key class, where the test that reads back the code's own constant proves
    nothing. Pinned against the SERVING module."""
    assert FA.DEFAULT_SOURCES == frozenset({SDSD.SOURCE_W6D_DEFAULT})
    assert SDSD.SOURCE_W6D_SHIP not in FA.DEFAULT_SOURCES


def test_the_manifest_carries_the_labelling_and_the_gap_together():
    m = FA.representation_manifest(LP.get_preset("full_ppr"), "WR", _served_map())
    assert m["story"] == "NF-W7c" and m["complete"] is True
    assert m["labelling"]["source"] == FA.ASSEMBLED_SOURCE_SHIP
    assert set(m["weights"]) == set(FA.LEGS)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The declared field (⛔ never trimmed or grown after a score — MH2 (a))
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_matched_independent_draw_is_a_FOIL_so_beating_it_is_a_gate_clause():
    """The card's binding requirement. As a FOIL it enters `beats_foil` and PBO's eligible set; as
    a mere anchor it could not refuse the story (NF-D20's eligibility lesson)."""
    assert "assembled_indep" in FA.FOILS
    assert "assembled_indep" not in FA.DEGENERATES and "assembled_indep" not in FA.REAL_ARMS
    assert set(FA.ELIGIBLE) == set(FA.REAL_ARMS) | set(FA.FOILS)


def test_the_over_correlated_degenerate_is_scored_and_registered_to_lose():
    """NF-D18: scoring the degenerate is what PROVES the coverage floor was not quietly promoted
    into a selection criterion — the comonotone arm SATISFIES the floor trivially and must still
    lose the metric."""
    assert "assembled_comonotone" in FA.DEGENERATES
    assert "assembled_comonotone" not in FA.ELIGIBLE


def test_the_field_partitions_and_every_arm_has_its_own_form_oracle():
    assert not set(FA.REAL_ARMS) & set(FA.FOILS)
    assert not set(FA.ELIGIBLE) & set(FA.DEGENERATES)
    for arm in FA.REAL_ARMS:                       # NF-D16 (g‴): the joint forms NEST one another
        assert f"oracle__{arm}" in FA.ANCHORS and f"matched_n__{arm}" in FA.ANCHORS
    for foil in FA.FOILS_WITH_ORACLE:
        assert f"oracle__{foil}" in FA.ANCHORS
    # ⛔ the independent foil estimates NOTHING, so it must NOT carry a fabricated oracle
    assert "assembled_indep" not in FA.FOILS_WITH_ORACLE
    assert "oracle__assembled_indep" not in FA.ANCHORS


def test_the_gate_clause_partition_covers_every_declared_check():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    sel = {"beats_foil": True, "fold_clause": {"passes": True}, "pbo": 0.0, "dsr": 1.0,
           "coverage": {"blocking_shortfall": False}, "pit_flat_ok": True,
           "anchors": {"degenerates_lose": True, "winner_beats_permuted": True,
                       "permuted_lift_not_significant": True,
                       "oracle_floors_respected_at_matched_n": True},
           "dependence_checks": {k: True for k in
                                 ("independence_under_disperses", "dependence_moves_coverage",
                                  "beats_indep_on_coverage")}}
    checks = R.compose_gate(sel, True)["checks"]
    declared = set(FA.STATISTICAL_CHECKS) | set(FA.ANCHOR_CHECKS)
    assert set(checks) == declared, (
        f"a gate clause exists that no partition claims — a CONSTRAINT_REFUSED classification "
        f"would mis-read it: {set(checks) ^ declared}")
    assert R.compose_gate(sel, True)["ship"] is True
    assert R.compose_gate(sel, False)["ship"] is False


def test_the_coverage_floor_is_inherited_and_not_locally_softened():
    """⛔ E2.1-r / NF1.8 / NF-D18: a floor may never be relaxed to let a story pass."""
    from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW
    assert (FA.COVERAGE_FLOOR, FA.COVERAGE_BLOCK_SE) == (KW.COVERAGE_FLOOR, KW.COVERAGE_BLOCK_SE)
    assert (FA.PBO_MAX, FA.DSR_MIN) == (KW.PBO_MAX, KW.DSR_MIN)


def test_the_promote_blockers_name_the_deploy_hold_and_the_default_caveat():
    joined = " ".join(FA.PROMOTE_BLOCKERS).lower()
    assert "deploy-held" in joined and "calibration_warning" in joined
    assert any("unpriced_scored_terms" in b for b in FA.PROMOTE_BLOCKERS)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The SERVING half — a challenger may not serve itself into existence
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _record(tmp_path: Path, **over) -> Path:
    rec = {"story": "NF-W7c", "smoke": False,
           "verdict": {"story_verdict": "SHIP", "ship_positions": ["WR"]},
           "selections": {"WR": {"winner": "joint_rank"}}}
    rec.update(over)
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(rec))
    return p


def test_the_certified_arm_is_read_from_the_record(tmp_path):
    assert FA.certified_arms(_record(tmp_path)) == {"WR": "joint_rank"}


@pytest.mark.parametrize("over,match", [
    ({"smoke": True}, "path proof is not a decision record"),
    ({"story": "NF-W6d"}, "story NF-W6d"),
    ({"verdict": {"story_verdict": "NULL", "ship_positions": []}}, "ships NO position"),
    ({"verdict": {}}, "no verdict layer"),
])
def test_the_serving_path_refuses_an_uncertified_record(tmp_path, over, match):
    """Fail-closed on every shape that is not a decision: a smoke, another story's record, a NULL
    verdict, a record with no verdict layer. A DEPLOY-HELD challenger must not be able to reach
    serving through a path proof (the W6d fail-closed contract, inherited)."""
    with pytest.raises((ValueError, KeyError), match=match):
        FA.certified_arms(_record(tmp_path, **over))


def test_a_missing_record_refuses_rather_than_defaulting(tmp_path):
    with pytest.raises(FileNotFoundError, match="READ from the §0.5 record, never"):
        FA.certified_arms(tmp_path / "absent.json")


def test_the_record_writer_and_the_record_reader_cannot_drift_onto_different_files():
    """The runner writes the artifact `certified_arms` later READS. Two literal copies of that
    path is a silent-staleness bomb (the repo's stale-preference class): the reader would keep
    serving an old file while the writer moved on, with nothing to notice."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    assert R._ARTIFACT_REL is FA.RECORD_RELPATH, (
        "the runner defines its own artifact path instead of reading the serving module's")
    assert FA.RECORD_RELPATH.endswith("nf_w7c_fp_assembly.json")


def test_even_a_smoke_run_reads_the_REAL_w6d_records_never_a_path_proof():
    """⭐ The runner's `suffix` names ITS OWN artifact; the W6d records are a committed INPUT.

    Letting one variable do both jobs (a) made `--smoke` demand a `nf_w6d_defaults_smoke.json`
    that has never existed, and (b) passed `allow_path_proof=True`, which would have let a PATH
    PROOF supply the served map a real assembly is built from. Reading the full records is both
    the working path and the STRICTER one — asserted on the source so the loophole cannot come
    back as a convenience during a future debugging session."""
    import inspect

    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    src = "\n".join(ln for ln in inspect.getsource(R.main).splitlines()
                    if not ln.lstrip().startswith("#"))          # prose cannot satisfy a guard
    assert 'record_paths("")' in src, (
        "the runner no longer pins the W6d records to the FULL (decision-grade) variants")
    assert "allow_path_proof" not in src, (
        "the runner passes allow_path_proof — a path-proof W6d record could feed the assembly")


def test_the_smoke_still_writes_its_OWN_artifact_as_a_path_proof():
    """The other half of the split: this story's own smoke output stays suffixed `_smoke`, so it
    remains unservable (`certified_arms` refuses it) even though its INPUTS are decision-grade."""
    import inspect

    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    src = inspect.getsource(R.main)
    assert 'suffix = "_smoke" if args.smoke else ""' in src
    assert 'art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")' in src


def test_the_marginals_are_built_once_per_FOLD_not_once_per_position():
    """⭐ `serve_banks` fits per (form, stat) across EVERY position and then slices, so a marginal
    context is position-INDEPENDENT. Building one inside the position loop repeats the identical
    ~113 LightGBM fits 4× per fold — measured at 868.7s for ONE position on the 2025H2 fold.
    Pinned on source (comment-stripped, so prose cannot satisfy it)."""
    import inspect

    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    body = "\n".join(ln for ln in inspect.getsource(R.run_position).splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "_marginals(" not in body, (
        "run_position builds a marginal context — that is position-independent work being redone "
        "once per position (4× per fold)")
    fold = inspect.getsource(R.run_fold)
    assert fold.count("_marginals(") == 2, (
        "run_fold should build exactly the two fold-level contexts (test + residual-PIT window)")


def test_the_residual_pit_window_is_capped_and_the_marginal_fit_is_not():
    """The cap is on the rows PITs are COMPUTED over, never on the FIT. `pit_window` selects from
    train, and `run_fold` still fits on the FULL train frame — if the cap reached the fit, the
    `joint_pit` arm would consume a predictive no other arm serves."""
    import inspect

    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    assert FA.PIT_ESTIMATION_ROWS >= 2_000, "too few rows to estimate a 13×13 correlation"
    src = inspect.getsource(R.run_fold)
    assert "_marginals(train, pit_frame, smap)" in src, (
        "the residual-PIT context must FIT on the full train frame and only PREDICT on the window")
    frame = pd.DataFrame({"gw": list(range(100)), "x": list(range(100))})
    assert len(R.pit_window(frame, 10)) == 10
    assert R.pit_window(frame, 10)["gw"].min() == 90, "the window must be the most RECENT rows"
    assert len(R.pit_window(frame, 500)) == 100, "a window wider than train is the whole train"


def test_the_served_assembly_produces_a_valid_bank_with_its_labelling():
    train_raw = np.random.default_rng(3).gamma(2.0, 2.0, size=(400, FA.N_LEGS))
    served = FA.serve_fp_frame({"WR": train_raw}, {"WR": _banks(30, seed=4)},
                               LP.get_preset("full_ppr"), _served_map(), {"WR": "joint_rank"},
                               draws=300)
    row = served["WR"]
    FA.assert_served_representation(row["bank"])
    s = row["summaries"]
    assert set(s) == set(FA.SUMMARY_COLUMNS)
    assert (s["p10"] <= s["p50"]).all() and (s["p50"] <= s["p90"]).all()
    assert ((0 <= s["p_boom"]) & (s["p_boom"] <= 1)).all()
    assert row["labelling"]["source"] == FA.ASSEMBLED_SOURCE_SHIP and row["complete"] is True


def test_sigma_is_estimated_on_TRAIN_so_the_served_slate_cannot_move_it():
    """No peeking: the dependence comes from train rows, so two different serve slates under the
    same train history must carry the SAME Σ."""
    train_raw = np.random.default_rng(3).gamma(2.0, 2.0, size=(400, FA.N_LEGS))
    args = (LP.get_preset("full_ppr"), _served_map(), {"WR": "joint_rank"})
    a = FA.serve_fp_frame({"WR": train_raw}, {"WR": _banks(20, seed=1)}, *args, draws=100)
    b = FA.serve_fp_frame({"WR": train_raw}, {"WR": _banks(20, seed=99)}, *args, draws=100)
    assert a["WR"]["sigma_note"] == b["WR"]["sigma_note"]
    assert not np.array_equal(a["WR"]["bank"], b["WR"]["bank"]), "different slates, same bank — "\
                                                                 "the serve input is being ignored"


def test_a_certified_joint_pit_arm_refuses_without_its_own_estimation_input():
    """`joint_pit`'s scale is defined against the marginals, so serving it needs the in-sample
    train predictives. Absent them the answer is a REFUSAL, never a quiet downgrade to another
    arm's Σ (which would serve something no gate ever certified)."""
    train_raw = np.random.default_rng(3).gamma(2.0, 2.0, size=(400, FA.N_LEGS))
    with pytest.raises(ValueError, match="refusing rather than quietly serving"):
        FA.serve_fp_frame({"WR": train_raw}, {"WR": _banks(20, seed=1)},
                          LP.get_preset("full_ppr"), _served_map(), {"WR": "joint_pit"})


@pytest.mark.parametrize("mutate,match", [
    (lambda b: b * np.nan, "non-finite"),
    (lambda b: b[:, ::-1], "NOT monotone"),
    (lambda b: b[:, :50], "expected"),
])
def test_the_served_representation_refuses_a_broken_bank(mutate, match):
    good = np.sort(np.random.default_rng(1).gamma(2.0, 3.0, size=(4, FA.N_LEVELS)), axis=1)
    FA.assert_served_representation(good)
    with pytest.raises(ValueError, match=match):
        FA.assert_served_representation(mutate(good))


def test_the_default_contribution_share_is_measured_and_never_thresholded():
    """⭐ Every position labels `partial_default` against the real NF-W6d map (minor channels are
    Phase-C defaults and standard leagues price them), so the LABEL alone cannot tell a 0.2% from
    a 40% dependence on a default. This measures the share — and asserts no cutoff was invented
    after seeing the answer (E2.1-r)."""
    smap = _served_map()
    for leg in ("passing_yards", "fumbles_lost"):
        smap[f"WR|{leg}"] = {"form": "climatology", "source": SDSD.SOURCE_W6D_DEFAULT,
                             "calibration_warning": "w"}
    share = FA.default_contribution_share(_banks(25, seed=7), LP.get_preset("full_ppr"), "WR", smap)
    assert share["threshold_applied"] is None and "E2.1-r" in share["note"]
    assert 0.0 < share["mean_default_contribution_share"] < 1.0
    assert share["default_priced_legs"] == ["fumbles_lost", "passing_yards"]
    clean = FA.default_contribution_share(_banks(25, seed=7), LP.get_preset("full_ppr"), "WR",
                                          _served_map())
    assert clean["mean_default_contribution_share"] == 0.0, "no default legs ⇒ a zero share"


def test_the_real_served_map_assembles_for_every_position():
    """⚠️ Against the REAL committed 52-cell NF-W6d map, not a fixture — a fixture built from my
    own assumption about the map cannot disconfirm it (NF-C0e)."""
    from quant_sports_intel_models.football.nfl.fantasy import (
        run_nf_w6d_serve_stat_distributions as W6DS,
    )
    gate, bake, defs = W6DS.record_paths("")
    if not gate.exists():
        pytest.skip("the committed NF-W6d records are not present in this checkout")
    smap = SDSD.served_map(gate, bake, defs)
    assert len(smap) == 52
    for pos in _SKILL:
        label = FA.assembled_labelling(smap, LP.get_preset("full_ppr"), pos)
        assert len(label["priced_legs"]) == 10, pos
        assert label["unpriced_legs"] == ["attempts", "carries", "targets"], pos
        assert label["source"] in (FA.ASSEMBLED_SOURCE_SHIP, FA.ASSEMBLED_SOURCE_PARTIAL,
                                   FA.ASSEMBLED_SOURCE_DEFAULT)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The verdict layer, end to end on SYNTHETIC fold scores
#
# ⭐ WHY THIS IS WORTH ITS LENGTH. The real run is an expensive operator job; a defect in
# selection / gating / classification / the report writer would surface only AFTER it, and the
# operator would pay for the run twice. The verdict layer is DERIVED from stored fold scores at
# zero refit cost (NF-W2e / NF-W3), which is exactly what lets it be exercised here for free.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _fold(label: str, *, winner_edge: float, n: int = 400, indep_cov: float = 0.74,
          comono_cov: float = 0.93, win_cov: float = 0.81, pit: float = 0.02) -> dict:
    """One synthetic fold: the joint arms beat both foils, the degenerates lose by a mile, each
    arm loses to its own oracle, and coverage orders indep < winner < comonotone."""
    base = 10.0
    scores = {a: base - winner_edge * (1.0 if a == "joint_rank" else 0.5)
              for a in FA.REAL_ARMS}
    scores.update({"assembled_indep": base, "foil_direct_points": base + 0.05,
                   "assembled_comonotone": base + 0.9, "permuted_direct": base + 1.5,
                   "nihilist_zero": base + 8.0, "zero_width": base + 5.0,
                   "max_width": base + 4.0})
    for a in FA.REAL_ARMS:
        scores[f"oracle__{a}"] = scores[a] - 0.4          # a peek can only help (same form)
        scores[f"matched_n__{a}"] = scores[a] + 0.2
    for f in FA.FOILS:
        scores[f"oracle__{f}"] = scores[f] - 0.4
    cov = {a: {"coverage": win_cov, "n": n, "binomial_se": 0.02, "blocking_shortfall": False}
           for a in FA.REAL_ARMS}
    cov["assembled_indep"] = {"coverage": indep_cov, "n": n, "binomial_se": 0.02,
                              "blocking_shortfall": True}
    cov["foil_direct_points"] = {"coverage": 0.78, "n": n, "binomial_se": 0.02,
                                 "blocking_shortfall": False}
    cov["assembled_comonotone"] = {"coverage": comono_cov, "n": n, "binomial_se": 0.02,
                                   "blocking_shortfall": False}
    watched = (*FA.REAL_ARMS, *FA.FOILS, "assembled_comonotone")
    pos = {"scores": scores, "coverage": cov,
           "pit_flatness": {lab: {"max_decile_dev": pit, "n": n} for lab in watched},
           "n_train": 900, "n_test": n,
           "sigma_notes": {a: {"estimator": "spearman_raw_ranks"} for a in FA.REAL_ARMS},
           "sigma_mean_abs_offdiag": {a: 0.12 for a in FA.REAL_ARMS},
           "analytic_sum_sd": {"indep": 6.0, "joint_rank": 8.4}}
    return {"label": label, "n_test": n, "positions": {p: dict(pos) for p in FA.POSITIONS}}


def _synthetic_run(**kw) -> dict:
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    folds = [_fold(f"f{i}", winner_edge=0.30 + 0.01 * i, **kw) for i in range(8)]
    return R.derive_verdict_layer({"n_folds": 8, "fold_results": folds,
                                   "generated_at": "2026-08-15T00:00:00Z"})


def test_a_clean_synthetic_run_ships_and_names_the_dependence_win():
    out = _synthetic_run()
    assert out["verdict"]["story_verdict"] == "SHIP"
    assert sorted(out["verdict"]["ship_positions"]) == sorted(FA.POSITIONS)
    for pos, sel in out["selections"].items():
        assert sel["winner"] in FA.REAL_ARMS and sel["delta_vs_indep_crps"] > 0, pos
        assert all(sel["dependence_checks"].values()), pos
        assert out["gates"][pos]["ship"] is True


def test_a_winner_that_does_NOT_beat_the_independent_foil_cannot_ship():
    """⭐ THE CARD'S BINDING REQUIREMENT, asserted: independence is a MEASURED, REFUSED
    simplification. Give the independent foil the best score and the story must not ship — with
    `beats_foil` naming the reason, because `assembled_indep` is a FOIL and not an anchor."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    folds = [_fold(f"f{i}", winner_edge=-0.30) for i in range(8)]
    out = R.derive_verdict_layer({"n_folds": 8, "fold_results": folds,
                                  "generated_at": "x"})
    assert out["verdict"]["story_verdict"] == "NULL"
    for pos in FA.POSITIONS:
        assert out["gates"][pos]["checks"]["beats_foil"] is False, pos
        assert out["selections"][pos]["delta_vs_indep_crps"] < 0, pos


def test_a_coverage_only_refusal_classifies_CONSTRAINT_REFUSED_with_no_data_trigger():
    """NF-D18: a null resting solely on the pre-registered floor is NOT power-limited — more folds
    shrink the SE and make the refusal MORE certain, so publishing a 'more seasons' trigger would
    be actively misleading.

    ⚠️ NF-D17: the fixture must satisfy every OTHER clause so only the floor can flip the result.
    A first cut set the winner to 0.70 while leaving the independent foil at 0.74 — which ALSO
    failed `beats_indep_on_coverage`, so the test would have passed on an `and`-gate refusing for
    a different reason entirely. The foil is dropped to 0.60 to isolate the floor."""
    out = _synthetic_run(win_cov=0.70, indep_cov=0.60)
    assert out["verdict"]["story_verdict"] == "NULL"
    for pos in FA.POSITIONS:
        checks = out["gates"][pos]["checks"]
        assert checks["coverage_floor_ok"] is False
        assert all(v for k, v in checks.items() if k != "coverage_floor_ok"), pos
        state = out["null_states"][pos]
        assert state["state"] == "CONSTRAINT_REFUSED", pos
        # the substantive claim: the trigger must REFUSE a data remedy, not prescribe one. The
        # misleading direction NF-D18 names is a "re-test with N more seasons" on a shortfall no
        # sample size can move — so the trigger says NONE and points at a different MECHANISM.
        trigger = state.get("retest_trigger") or ""
        assert trigger.startswith("NONE"), f"{pos}: a floor refusal published a data trigger"
        assert "FRESH registration" in trigger and "never a post-hoc floor change" in trigger


def test_an_inactive_dependence_knob_refuses_rather_than_reading_as_a_clean_null():
    """NF-D20: if the knob's full range cannot move coverage, the gate clause is décor and the
    result is a CONSTRAINT/registration refusal — not a tidy statistical null a reader would
    mistake for evidence about dependence."""
    out = _synthetic_run(comono_cov=0.74, indep_cov=0.74)
    for pos in FA.POSITIONS:
        c = out["gates"][pos]["checks"]
        assert c["dependence_moves_coverage"] is False
        assert c["independence_under_disperses"] is False
    assert out["verdict"]["story_verdict"] == "NULL"


def test_a_pit_flatness_failure_blocks_a_ship_even_with_coverage_green():
    """E2.1-r: on an atom-bearing discrete target, coverage is a FLOOR and PIT flatness is the
    calibration TARGET — a wide-but-misshapen predictive must not pass on coverage alone."""
    out = _synthetic_run(pit=0.20)
    for pos in FA.POSITIONS:
        assert out["gates"][pos]["checks"]["pit_flat_ok"] is False
        assert out["gates"][pos]["checks"]["coverage_floor_ok"] is True
    assert out["verdict"]["story_verdict"] == "NULL"


def test_a_refused_fold_is_dropped_from_the_fold_count_not_silently_counted():
    """A fold whose anchors could not be evaluated is REFUSED (NF1.7 (a) — a check that did not
    run is not a pass) and must leave the fold count, so the fold-consistency clause and the
    power classification are computed on the folds that actually produced a verdict."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    folds = [_fold(f"f{i}", winner_edge=0.30) for i in range(8)]
    for fr in folds[:3]:
        fr["positions"]["WR"] = {"skipped": "matched-n control below the estimation floor"}
    out = R.derive_verdict_layer({"n_folds": 8, "fold_results": folds, "generated_at": "x"})
    assert out["selections"]["WR"]["n_folds_used"] == 5
    assert out["selections"]["QB"]["n_folds_used"] == 8, "an unrelated position must be unaffected"


def test_a_position_refused_on_every_fold_is_reported_unavailable_not_null():
    """'We could not evaluate this position' and 'this position produced a null' are different
    findings — collapsing them would publish a null nobody measured."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    folds = [_fold(f"f{i}", winner_edge=0.30) for i in range(8)]
    for fr in folds:
        fr["positions"]["TE"] = {"skipped": "below the estimation floor"}
    out = R.derive_verdict_layer({"n_folds": 8, "fold_results": folds, "generated_at": "x"})
    assert out["unavailable_positions"] == ["TE"]
    assert "TE" not in out["selections"] and "TE" not in out["verdict"]["null_positions"]
    assert "TE" not in out["verdict"]["ship_positions"]


def test_the_report_writer_survives_both_a_ship_and_a_null(tmp_path):
    """A report that crashes after an expensive operator run costs the run twice."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    for name, out in (("ship", _synthetic_run()),
                      ("null", _synthetic_run(win_cov=0.70, indep_cov=0.60))):
        p = tmp_path / f"{name}.md"
        R.write_report(out, p)
        text = p.read_text()
        assert "NF-W7c" in text and "best_alpha" in text and "DEPLOY-HELD" in text
        assert "Did correlation earn its place?" in text
        for blocker in FA.PROMOTE_BLOCKERS:
            assert blocker in text, f"{name}: a promote blocker is missing from the report"


def test_classify_null_is_given_the_declared_field_size(monkeypatch):
    """MH2.7: `classify_null` must be told the PRE-REGISTERED field so it REFUSES to prescribe a
    smaller one — a 'trim the field' remedy IS the selection bias DSR exists to deflate."""
    from betting_ml.utils import cv_power
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as R
    seen: dict = {}
    real = cv_power.classify_null

    def spy(**kw):
        seen.update(kw)
        return real(**kw)

    monkeypatch.setattr(cv_power, "classify_null", spy)
    _synthetic_run(win_cov=0.70, indep_cov=0.60)
    assert seen.get("declared_field_size") == len(FA.REAL_ARMS)
    assert seen.get("degenerates_excluded_from_v") is True


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 10. RED PROOFS — every guard above is only worth what a deliberate break proves
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _assert_red(fn, *args, **kwargs) -> None:
    """Run a clause that is EXPECTED to fail on broken source.

    ⚠️ Catches `BaseException`, not `Exception`: pytest's `Failed` (raised by a failing `assert`
    inside `pytest.raises`, and by `pytest.fail`) derives from `BaseException`, so an
    `except Exception` red proof lets a deliberate break sail straight through and reports
    SUCCESS — a red proof that structurally cannot fail (NF-W6c)."""
    try:
        fn(*args, **kwargs)
    except BaseException:
        return
    raise AssertionError(f"{getattr(fn, '__name__', fn)} stayed GREEN on deliberately broken "
                         f"source — the guard cannot fail and is decorative")


def test_red_proof_a_fourth_scorer_that_drops_the_position_bonus_is_caught(payload_rows,
                                                                          stat_matrix,
                                                                          monkeypatch):
    """Break: `leg_weights` ignores the per-position bonus (the most plausible real drift — a
    scorer that forgets TE premium looks right on three of four positions)."""
    monkeypatch.setattr(FA, "leg_weights", lambda cfg, pos: np.array(
        [cfg.scoring.per_stat.get(FA.STAT_KEY[leg], 0.0) for leg in FA.LEGS], dtype=float))
    _assert_red(test_the_weight_vector_reproduces_score_players_exactly,
                payload_rows, stat_matrix, "te_premium")
    _assert_red(test_te_premium_moves_tight_ends_and_only_tight_ends, stat_matrix)


def test_red_proof_a_silent_identity_fallback_is_caught(monkeypatch):
    """Break: the estimator swallows its own refusal and returns independence — exactly the
    NF1.7 (a) failure the floor exists to prevent, and the one a caller would never notice."""
    real = FA.position_sigma

    def swallowing(raw, *, min_rows=FA.MIN_ESTIMATION_ROWS):
        try:
            return real(raw, min_rows=min_rows)
        except ValueError:
            return np.eye(FA.N_LEGS), {"estimator": "spearman_raw_ranks", "n_rows": 0,
                                       "degenerate_legs": [], "n_estimated_legs": FA.N_LEGS}

    monkeypatch.setattr(FA, "position_sigma", swallowing)
    _assert_red(test_the_raw_rank_estimator_refuses_below_the_row_floor)
    _assert_red(test_an_all_constant_slice_refuses_rather_than_returning_an_identity)


def test_red_proof_labelling_that_ignores_pricing_is_caught_in_BOTH_directions(monkeypatch):
    """Break: labelling over ALL legs instead of the PRICED ones. That still passes the
    'a default surfaces' clause — it only breaks the 'unpriced default stays quiet' one, which is
    precisely why both directions are asserted."""
    monkeypatch.setattr(FA, "priced_legs", lambda cfg, pos: FA.LEGS)
    _assert_red(test_a_default_on_an_UNPRICED_leg_does_not_raise_a_caveat)
    test_a_default_on_a_priced_leg_surfaces_at_the_assembled_level()   # still green — as expected


def test_red_proof_a_copula_that_perturbs_the_marginal_is_caught(monkeypatch):
    """Break: the draw layer rescales values by a Σ-dependent factor — a plausible-looking
    'variance correction' that silently moves every marginal off its certified bank."""
    real = FA.draw_legs
    monkeypatch.setattr(FA, "draw_legs", lambda b, u: real(b, u) * 1.10)
    _assert_red(test_no_correlation_matrix_moves_a_leg_marginal)


def test_red_proof_an_unpriced_term_scored_as_zero_is_caught(monkeypatch):
    """Break: `unpriced_scored_terms` reports nothing, so the assembly silently under-states a
    league's points — the defect class that is invisible because nothing errors."""
    monkeypatch.setattr(FA, "unpriced_scored_terms", lambda cfg, pos: {})
    _assert_red(test_a_league_pricing_an_unmodeled_term_is_refused_and_the_gap_is_real, None)


def test_red_proof_a_dependence_knob_that_cannot_move_coverage_is_caught(monkeypatch):
    """Break: the copula ignores Σ (the arm becomes décor — NF-D20's inactive-gate class, which
    would otherwise read as a clean, well-behaved null)."""
    monkeypatch.setattr(JD, "gaussian_copula_uniforms",
                        lambda z, corr: JD.independent_uniforms(z))
    _assert_red(test_dependence_moves_the_assembled_dispersion_analytically_and_in_the_draw)
