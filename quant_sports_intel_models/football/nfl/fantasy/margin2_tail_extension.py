"""margin2_tail_extension.py — NF-MARGIN2: tail-extension-ONLY recalibration vs the champion
(pure).

THE STORY IN ONE PARAGRAPH. NF-MARGIN1 proved the served champion predictive has NO tails (the
quantile learners end at the 0.05/0.95 knots, extended flat) and demonstrated the TAIL CHANNEL at
all four positions (`pit_recal_tail` − `pit_recal_pos`: 8/8 fold wins, CIs excluding zero,
BH-binding) — but its ARM verdicts were refused by DSR under the field-composition tax of a
6-config eligible set. MH2.2 forbids shrinking that field post hoc; the legitimate successor is
THIS: a fresh pre-registration of the single demonstrated contrast — the per-position exponential
mean-excess tail model attached to the RAW champion bank (`tail_ext`, a construction NF-MARGIN1
never scored, and the exact serving-shaped object) vs the champion as served. One arm, one foil,
full gate battery, honest 1-arm deflation (PBO undefined by design, DSR = PSR at a single trial).

⚠️ THE INSTRUMENT CHANGE THE ARM FORCES (NF-D20 (g⁗) — the instrument must SEE the fix): the
arm's 39 champion-grid columns are BYTE-IDENTICAL to the incumbent's (identity map within the
grid — asserted at runtime), so Winkler-80 and coverage(50/80/95) deltas are IDENTICALLY ZERO and
the 39-level PIT cannot move. Selection is `crps_q199`; PIT accounting runs on the 199-level bank
via `randomized_pit_levels` (the levels-generalized `OA.randomized_pit`, guard-tested to
reproduce it byte-for-byte on a 39-level bank). NF-MARGIN1's `interval_score_improves` /
`pit_flatness_improves` clauses are deliberately NOT carried — a clause the mechanism cannot move
counts an inactive gate as evidence.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: this module promotes nothing and serves
nothing; a clearing arm's serving path (attach per-position tail betas to the served bank — no
refit) is blocked on NF-C6 Ph2 + NF-G0.

Pure module — no lake IO. The runner is `run_nf_margin2_tail_extension.py`; the narrative
pre-registration is `ablation_results/nf_margin2_preregistration.md`, committed BEFORE the run.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-MARGIN2"
PRIMARY_METRIC = MC.PRIMARY_METRIC          # crps_q199 — MARGIN1's declared reason verbatim
EVAL_LEVELS = MC.EVAL_LEVELS
IDX_Q39 = MC.IDX_Q39
_SEED = 20260813  # fresh; the primary metric is deterministic — the seed touches only the PIT
#                   randomization and the permutation draw, so no verdict can turn on it.

#: ONE real arm — the pre-registered single contrast (MH2.2's legitimate path).
REAL_ARMS: tuple[str, ...] = ("tail_ext",)
#: ONE foil — the champion as served. The contrast IS the story.
FOILS: tuple[str, ...] = ("incumbent",)
#: Anchors (excluded from the DSR trial field — automatic at a 1-arm family, MH2.1 (a)):
#:   `zero_width`/`max_width` — the two-sided sharpness degenerates (NF1.7 (c));
#:   `over_ext`      — the arm's betas × OVER_SCALE, the MAGNITUDE degenerate registered to LOSE
#:                     (NF-D20: scored, never reasoned about — if it wins, the mean-excess fit
#:                     UNDER-extends and the magnitude hypothesis is refuted, decomposed);
#:   `permuted_tail` — betas fit on within-(position, week) permuted outcomes. ⭐ Registered
#:                     expectation (NF-D16 (2)): a permutation is near-vacuous against a MARGINAL
#:                     mechanism, so this anchor ATTRIBUTES (marginal vs row-alignment share)
#:                     rather than refutes; the only gate clause is that it must not
#:                     significantly BEAT the arm;
#:   `pooled_tail`   — betas fit position-POOLED (prices per-position conditioning in the tail;
#:                     report-only, informs the serving object).
BASE_ANCHORS: tuple[str, ...] = ("zero_width", "max_width", "over_ext", "permuted_tail",
                                 "pooled_tail")
#: The magnitude degenerate's scale — far enough out that a correct fit must beat it.
OVER_SCALE = 3.0

TEST_BLOCKS = MC.TEST_BLOCKS                # the NF-W1 fold axis, verbatim
PURGE_WEEKS = MC.PURGE_WEEKS
DSR_MIN, FDR_Q = MC.DSR_MIN, MC.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = MC.COVERAGE_FLOOR, MC.COVERAGE_BLOCK_SE
POSITIONS = MC.POSITIONS
MIN_TAIL_N = MC.MIN_TAIL_N

#: ⭐ ONE pre-registered BH family (there is no second): the per-position tests of the single
#: contrast. Own-family IS the pooled correction.
FDR_FAMILY: tuple[str, ...] = tuple(f"margin2_tail_{p}" for p in POSITIONS)

#: The nominal beyond-CHAMPION-grid PIT mass per side (grid ends 0.025/0.975). ⚠️ DIAGNOSTIC
#: ONLY — P(u beyond the champion grid) is ARM-INVARIANT for a tail-only construction (the
#: extension redistributes mass WITHIN (0.975, 1); it cannot change how often y exceeds q975),
#: so a gate on it would be structurally inactive (the NF-D20 (g⁗) trap, caught at design time).
NOMINAL_TAIL = float(WP.Q_LEVELS[0])
#: The nominal beyond-EVAL-grid mass per side (eval ends 0.005/0.995) — THE GATE STATISTIC. The
#: flat incumbent piles ALL beyond-champion-grid mass into the last/first eval cell (u ~
#: U(0.995, 1) above, U(0, 0.005) below ⇒ ~0.04 vs nominal 0.005 per NF-MARGIN1's diagnosis); a
#: correct tail spreads it uniformly, an OVER-extended tail pushes it BELOW nominal — two-sided.
NOMINAL_EXTREME = float(EVAL_LEVELS[0])
#: Eval columns inside the champion grid — byte-identical across incumbent and every tail-family
#: construction (the structural invariant the runner asserts each fold).
WITHIN_GRID: np.ndarray = (EVAL_LEVELS >= WP.Q_LEVELS[0]) & (EVAL_LEVELS <= WP.Q_LEVELS[-1])

oracle_of = GE.oracle_of
matched_n_of = GE.matched_n_of
form_of = MC.form_of
pbo_is_evaluable = GE.pbo_is_evaluable
classify_layer_b = GE.classify_layer_b

# Shared machinery — IMPORTED, never re-typed (NF-W2d discipline).
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
calibration_split = MC.calibration_split
permute_within_pos_week = MC.permute_within_pos_week
fit_tail_betas = MC.fit_tail_betas
apply_level_map = MC.apply_level_map
score_bank = MC.score_bank
winkler_80 = MC.winkler_80
pit_stats = MC.pit_stats
pool_pit_stats = MC.pool_pit_stats
team_total_check = MC.team_total_check
pool_team_total = MC.pool_team_total
TEAM_TOTAL_SAMPLES = MC.TEAM_TOTAL_SAMPLES
MIN_TEAM_K = MC.MIN_TEAM_K


def anchors() -> tuple[str, ...]:
    return (*BASE_ANCHORS, oracle_of("tail_ext"), matched_n_of("tail_ext"))


def all_labels() -> tuple[str, ...]:
    return (*REAL_ARMS, *FOILS, *anchors())


def eligible_labels() -> list[str]:
    """The declared field — the arm and the foil, nothing else (anchors never enter, NF1.8)."""
    return [*REAL_ARMS, *FOILS]


# ── Constructions ───────────────────────────────────────────────────────────────────────────────
def scale_tail(tail: dict, scale: float = OVER_SCALE) -> dict:
    """The magnitude degenerate's parameters: the arm's own betas, scaled. Thin (zero) sides
    stay zero — the degenerate cannot invent a tail the fit refused."""
    out = dict(tail)
    out["beta_hi"] = float(tail["beta_hi"]) * float(scale)
    out["beta_lo"] = float(tail["beta_lo"]) * float(scale)
    return out


_TAIL_FAMILY: tuple[str, ...] = ("tail_ext", "permuted_tail", "pooled_tail")


def build_bank_m2(label: str, params, q39_sorted: np.ndarray) -> np.ndarray:
    """The (n, 199) evaluation bank for one construction. Every tail-family construction is the
    IDENTITY map within the grid + an exponential extension beyond it — so its within-grid
    columns are byte-identical to the incumbent's (asserted by `assert_within_grid_identity`)."""
    form = form_of(label)
    if form in ("incumbent", "zero_width", "max_width"):
        return MC.build_eval_bank(form, None, q39_sorted)
    if form in _TAIL_FAMILY:
        return apply_level_map(q39_sorted, EVAL_LEVELS, tail=params)
    if form == "over_ext":
        return apply_level_map(q39_sorted, EVAL_LEVELS, tail=scale_tail(params))
    raise ValueError(f"unknown construction label: {label}")


def assert_within_grid_identity(bank: np.ndarray, inc_bank: np.ndarray, label: str) -> None:
    """The structural proof that a construction is tail-ONLY: every eval column inside
    [0.025, 0.975] must equal the incumbent's exactly. A violation is a harness bug (the arm
    would be touching levels the pre-registration says it cannot), never a finding."""
    if not np.array_equal(bank[:, WITHIN_GRID], inc_bank[:, WITHIN_GRID]):
        raise ValueError(
            f"`{label}` modified within-grid columns — the pre-registered arm is tail-ONLY; "
            f"refusing to score a construction that is not (NF-D20 (g⁗): the inactive clauses "
            f"are declared on this invariant)")


# ── The PIT instrument, levels-generalized ──────────────────────────────────────────────────────
def randomized_pit_levels(qmat: np.ndarray, y: np.ndarray, rng: np.random.Generator,
                          levels: np.ndarray = EVAL_LEVELS) -> np.ndarray:
    """`OA.randomized_pit` with the level vector as an argument (that function hardwires the
    39-level grid). ⚠️ WHY THIS EXISTS: the arm's 39 champion-grid columns are byte-identical to
    the incumbent's, so a 39-level PIT is STRUCTURALLY BLIND to the fix — the tail-mass gate must
    read the 199-level bank (NF-D20 (g⁗)). Guard-tested to reproduce `OA.randomized_pit`
    byte-for-byte on a 39-level bank with the same rng state."""
    q = np.sort(np.asarray(qmat, dtype=float), axis=1)
    yv = np.asarray(y, dtype=float)[:, None]
    lv = np.asarray(levels, dtype=float)
    n_levels = len(lv)
    if q.shape[1] != n_levels:
        raise ValueError(f"bank has {q.shape[1]} columns but {n_levels} levels were given — "
                         f"a PIT computed on mismatched levels is not a PIT (NF1.7 (a))")
    lo_ct = (q < yv).sum(axis=1)
    hi_ct = (q <= yv).sum(axis=1)
    lo = np.where(lo_ct == 0, 0.0, lv[np.clip(lo_ct - 1, 0, n_levels - 1)])
    hi = np.where(hi_ct >= n_levels, 1.0, lv[np.clip(hi_ct, 0, n_levels - 1)])
    u = lo + rng.random(len(yv)) * np.maximum(hi - lo, 0.0)
    return np.clip(u, 1e-6, 1 - 1e-6)


def pit_stats_m2(u: np.ndarray) -> dict:
    """`MC.pit_stats` + the beyond-EVAL-grid counts the gate needs. ⚠️ WHY the extra thresholds:
    the champion-grid counts (`n_below_grid`/`n_above_grid` at 0.025/0.975) are ARM-INVARIANT for
    a tail-only construction — a gate on them would be structurally inactive (NF-D20 (g⁗)). The
    fix is visible only in how the beyond-mass is DISTRIBUTED, read at the eval ends."""
    base = MC.pit_stats(u)
    uv = np.asarray(u, dtype=float)
    base["n_below_eval"] = int((uv < EVAL_LEVELS[0]).sum())
    base["n_above_eval"] = int((uv > EVAL_LEVELS[-1]).sum())
    return base


def pool_pit_stats_m2(parts: list[dict]) -> dict:
    out = MC.pool_pit_stats(parts)
    n = out.get("n", 0)
    if n:
        out["p_below_eval"] = round(float(sum(p["n_below_eval"] for p in parts) / n), 5)
        out["p_above_eval"] = round(float(sum(p["n_above_eval"] for p in parts) / n), 5)
    return out


def tail_mass_deviation(pooled_pit: dict) -> float:
    """The two-sided calibration statistic: total beyond-EVAL-grid PIT deviation from nominal,
    `|P(u<0.005) − 0.005| + |P(u>0.995) − 0.005|`. The flat incumbent piles all beyond-mass into
    the end cells (deviation ≈ champion-grid tail mass − nominal); a correct tail spreads it to
    nominal; an OVER-extended tail pushes it BELOW nominal and the deviation rises again —
    two-sided from either direction (E2.1-r: a deviation-from-nominal on a density account;
    coverage itself stays a floor elsewhere)."""
    return float(abs(pooled_pit["p_below_eval"] - NOMINAL_EXTREME)
                 + abs(pooled_pit["p_above_eval"] - NOMINAL_EXTREME))


def permuted_not_significantly_better(mean_pb: float, p_pb: float | None) -> bool:
    """The permutation gate clause: `permuted_tail` must not significantly BEAT the arm
    (`mean_pb` = mean of crps[tail_ext] − crps[permuted_tail], positive when permuted is
    better). ⛔ an unevaluable p with a positive mean fails CLOSED (NF1.7 (a)). The permutation
    is otherwise ATTRIBUTION, not refutation — it shares the marginal mechanism BY EXPECTATION
    (NF-D16 (2)), so no clause demands the arm beat it."""
    return bool(mean_pb <= 0 or (p_pb is not None and p_pb >= 0.05))


# ── Gate composition + refusal classification ───────────────────────────────────────────────────
#: PBO is deliberately ABSENT from the statistical set: a 1-arm family has no search to overfit,
#: so CSCV is UNDEFINED by design (GE.pbo_is_evaluable — the NF-W4 Layer-B precedent verbatim).
M2_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_champion", "fold_consistency", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)
M2_ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_not_better", "oracle_floor_respected",
)
#: The story's two-sided calibration gate — a single named clause (NF-D20: never bundle).
M2_CALIBRATION_CHECKS: tuple[str, ...] = ("tail_mass_toward_nominal",)


def compose_gate_margin2(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_champion": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "degenerates_lose": bool(sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]
                                 and sel["anchors"]["over_ext_loses"]),
        "permutation_not_better": bool(sel["anchors"]["permuted_not_significantly_better"]),
        "oracle_floor_respected": bool(sel["anchors"]["oracle_floor_respected_at_matched_n"]),
        "tail_mass_toward_nominal": bool(
            sel["calibration"]["tail_mass_delta_vs_incumbent"] > 0),
    }
    return {"checks": checks, "ship": all(checks.values())}


def hand_classify_refusal_margin2(checks: dict) -> dict | None:
    """The NF-D18/MH2.7 hand check: every statistical gate green, the null resting only on
    anchor/calibration clauses ⇒ CONSTRAINT_REFUSED — more data makes a directional anchor
    refusal fail HARDER, and ⛔ no sample-size re-test trigger may be published."""
    stat_fail = [c for c in M2_STATISTICAL_CHECKS if not checks.get(c, True)]
    other_fail = [c for c in (*M2_ANCHOR_CHECKS, *M2_CALIBRATION_CHECKS)
                  if not checks.get(c, True)]
    if stat_fail or not other_fail:
        return None
    return {
        "state": "CONSTRAINT_REFUSED",
        "reason": ("hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical gate "
                   f"passed and the null rests entirely on anchor/calibration clauses "
                   f"{other_fail}. More data cannot change this verdict."),
        "retest_trigger": None,
        "failing_anchor_checks": other_fail,
    }
