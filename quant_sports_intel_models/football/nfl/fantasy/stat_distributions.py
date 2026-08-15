"""stat_distributions.py — NF-W6b: the per-stat distributional successor (pure).

THE STORY IN ONE PARAGRAPH. NF-W6's oracle gate returned CEILING-GATE[BUILD]: on 7 of 12
(position, stat) cells a realized-efficiency oracle beats the champion's per-stat predictive by
6.7–17.1% of CRPS, and the matched-n controls attributed the headroom to FORM, not information —
the champion emits per-stat POINT MEANS wrapped in a position-constant residual bank, which
under-prices the zero atom (pred P(0) 0.23–0.32 vs realized 0.40–0.69 on yards cells) and
expresses no conditional spread (a 12-target week is as wide as a 2-target week). NF-W6b is the
licensed successor: a FRESH-REGISTRATION per-cell-family §0.5 bake-off of distributional forms
that price the atom and the conditional spread — hurdle / quantile-type forms over the champion
feature set, the NF-MARGIN1 exponential tail carried from day one. ⛔ No exotic features; ⛔ the
dead W3/W4/W5 environment/availability/correlation channels stay closed; ⛔ the 4 TD-NO cells
(QB rushing_tds, RB/WR/TE receiving_tds) stay closed — NF-W6 measured a discrete climatology
near-optimal there, and re-opening them needs a different MECHANISM, not more data.

⭐ FRESH REGISTRATION (MH2.2): nothing from NF-W6's oracle field is promoted into this field.
The oracle/matched-n marginal labels appear here only as newly-registered DIAGNOSTIC anchors —
excluded from the PBO field and the DSR trial set (MH2.1 (a)) — never as trials.

THE DoD (PM ruling, settled up front): each cell is judged on PER-STAT MARGINAL CRPS
(`crps_q199`) — the product-facing raw-line question; honest per-stat distributions do not exist
today, so this is the arbitrary-league re-scoring substrate. The assembled-PPR-points effect is
REPORT-ONLY, never a gate: the champion's points hurdle already conditions on usage (NF-W1), the
correlation channel is measured-dead (NF-W5), so a per-stat win need not move assembled points
and the deliverable does not depend on it.

COVERAGE IS A FLOOR, DELIBERATELY ONE-SIDED ON THIS POPULATION (pre-registered): these targets
carry a 0.40–0.69 zero atom, and an honest atom-pricing predictive has q10 = 0 on most rows, so
the inclusive central 80% interval structurally covers the whole atom — coverage(80) ≈
P(y ≤ q90) ≈ atom + 0.9·(1−atom) ≫ 0.80 for a CORRECTLY calibrated arm (NF1.9 (e): a two-sided
coverage TARGET is structurally inverted on a zero-atom population; E2.1-r (a)). The DoD's
two-sidedness is carried by the sharpness degenerates instead: `zero_width` AND `max_width` are
scored every cell and must BOTH lose the primary metric (NF1.7 (c) / NF1.8 — `max_width`
satisfies any coverage floor and must still lose, proving the floor is a constraint, never a
criterion).

⚖️ EDGE-INDEPENDENT (`best_alpha` N/A) · DEPLOY-HELD: this module promotes nothing, publishes
nothing, retrains nothing; research-only, no changelog entry.

Pure module — no lake IO. The runner is `run_nf_w6b_stat_distributions.py`.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W6b"
PRIMARY_METRIC = "crps_q199"
#: The NF-MARGIN1 dense grid — imported, never re-typed (one source of the 199 levels).
EVAL_LEVELS: np.ndarray = MC.EVAL_LEVELS
_SEED = 20260815

#: ⭐ The 8 licensed cells: NF-W6's 7 YES cells + RB rushing_tds by PM ruling (MARGINAL 4.08%,
#: statistically demonstrable, high-value fantasy stat) — admitted as an 8th cell in its own
#: right, carrying the multiplicity.
POSITION_STATS: dict[str, tuple[str, ...]] = {
    "QB": ("passing_yards", "passing_tds", "rushing_yards"),
    "RB": ("rushing_yards", "rushing_tds", "receiving_yards"),
    "WR": ("receiving_yards",),
    "TE": ("receiving_yards",),
}
#: ⛔ The 4 TD-NO cells — CLOSED by NF-W6's measurement (discrete climatology near-optimal,
#: ceiling 0.07–0.38%). Guard-pinned OUT of this field; re-opening needs a different mechanism.
CLOSED_CELLS: tuple[str, ...] = (
    "QB|rushing_tds", "RB|receiving_tds", "WR|receiving_tds", "TE|receiving_tds")
STATS: tuple[str, ...] = (
    "passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receiving_yards")
TD_STATS: tuple[str, ...] = ("passing_tds", "rushing_tds")

#: 4 learner classes (§0.5: ≥3 + a direct-learned foil). Every arm prices the zero atom and/or
#: conditional spread — the mechanism NF-W6's matched-n controls licensed.
REAL_ARMS: tuple[str, ...] = (
    "lgbm_quantile_tail", "lgbm_hurdle_tail", "enet_residual", "knn_quantile")
#: Foils (never shippable; the BINDING one — better mean fold CRPS — sets the bar).
#: `inc_head_bank` IS the champion-faithful incumbent wrapper = the story card's direct-learned
#: foil (the champion's own direct-learned per-stat mean in the minimal distributional costume).
FOILS: tuple[str, ...] = ("inc_head_bank", "inc_climatology")
#: Diagnostic anchors — scored every cell, never trials (MH2.1 (a): excluded from the PBO field
#: and the DSR trial set). `permuted_quantile` is the full winner-form code path on labels
#: permuted within (position, global week). The marginal oracle/matched pair is NF1.9 (f).
ANCHORS: tuple[str, ...] = (
    "nihilist_zero", "zero_width", "max_width", "permuted_quantile",
    "oracle_marginal", "matched_marginal")

#: REPORT-ONLY PPR weights (§5 of the prereg): each cell's CRPS lift × its weight = a points-
#: units MARGINAL contribution. ⛔ Never a gate; never an assembled-joint claim.
PPR_WEIGHTS: dict[str, float] = {
    "passing_yards": 0.04, "passing_tds": 4.0, "rushing_yards": 0.1,
    "rushing_tds": 6.0, "receiving_yards": 0.1}

KNN_K = 300
MIN_TAIL_N = EM.MIN_TAIL_N
FIT_LEVELS: tuple[float, ...] = WP.FIT_LEVELS
TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
POSITIONS = WP.POSITIONS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
CAPTURE_ERA_FOLDS: tuple[str, ...] = EM.CAPTURE_ERA_FOLDS

# Shared helpers — IMPORTED, never re-typed (NF-W2d discipline).
cell_key = EM.cell_key
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
flag_unsafe_field_shrink = GE.flag_unsafe_field_shrink
gate_sensitivity = GE.gate_sensitivity
cell_crps_matrix = EM.cell_crps_matrix
score_bank = EM.score_bank                       # ONE reducer; refuses non-finite (NF-W3 (b))
fdr_two_families = EM.fdr_two_families_w6        # own-family AND pooled; stricter binds (MH2 (a))


def cells() -> tuple[str, ...]:
    return tuple(cell_key(p, s) for p in POSITIONS for s in POSITION_STATS[p])


def all_labels() -> tuple[str, ...]:
    return (*REAL_ARMS, *FOILS, *ANCHORS)


def eligible_labels() -> list[str]:
    """The set the selection actually searches — real arms + foils. Anchors NEVER enter (NF1.8:
    a deflation statistic over a field containing its own anchors measures the anchors; MH2.2:
    no oracle/matched label may be promoted into the trial field)."""
    return [*REAL_ARMS, *FOILS]


#: ⭐ TWO pre-registered multiplicity families — the 6 yards cells and the 2 TD cells; a SHIP
#: must survive own-family AND pooled BH (MH2 (a)).
def fdr_families() -> dict[str, tuple[str, ...]]:
    yards, tds = [], []
    for c in cells():
        (tds if c.split("|", 1)[1] in TD_STATS else yards).append(f"w6b_arm_{c}")
    return {"yards": tuple(yards), "tds": tuple(tds)}


# ── Permutation substrate (per stat) ────────────────────────────────────────────────────────────
def permute_stat_within_pos_week(train: pd.DataFrame, stat: str) -> np.ndarray:
    """The stat's labels permuted WITHIN (position, global week) — destroys the row-level
    feature→label link, preserves every position-week marginal. Seeded per stat."""
    rng = np.random.default_rng(np.random.SeedSequence([_SEED, zlib.crc32(stat.encode())]))
    y = pd.to_numeric(train[stat], errors="coerce").fillna(0.0).to_numpy(dtype=float).copy()
    keys = train["position"].astype(str) + "|" + train["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(train)), index=keys.to_numpy()).groupby(level=0):
        posn = idx.to_numpy()
        if len(posn) > 1:
            y[posn] = y[rng.permutation(posn)]
    return y


# ── The 4 real arms (each returns an (n_test, 199) quantile bank) ───────────────────────────────
def _y(df: pd.DataFrame, stat: str) -> np.ndarray:
    return pd.to_numeric(df[stat], errors="coerce").fillna(0.0).to_numpy(dtype=float)


def arm_lgbm_quantile_tail(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                           stat: str) -> tuple[np.ndarray, dict]:
    """The champion representation a build would inherit: pooled 9-knot LGBM quantile bank
    (champion `_lgbm` construction + position code) + per-position exponential mean-excess tails
    fit on the PURGED calibration slice (NF-MARGIN1: in-sample tails of a boosted model are
    optimistically sharp)."""
    core, cal, note = MC.calibration_split(train)
    cal_knots = EM.fit_cand_knots(core, cal, features, stat)
    tails = EM.tail_betas_by_pos(cal_knots, _y(cal, stat), cal["position"].to_numpy())
    knots_te = EM.fit_cand_knots(train, test, features, stat)
    return EM.knots_to_eval(knots_te, tails, test["position"].to_numpy()), note


def _hurdle_clf():
    """EXACTLY the champion hurdle's classifier construction (`WP.fit_lgbm_hurdle`, verbatim —
    guard-tested against that source)."""
    import lightgbm as lgb
    return lgb.LGBMClassifier(
        n_estimators=250, learning_rate=0.06, num_leaves=63, min_child_samples=40,
        subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
        random_state=WP._SEED, verbose=-1, n_jobs=-1,
    )


def mixture_quantiles199(p0: float, cond_q: np.ndarray) -> np.ndarray:
    """Quantile function of `p0·δ0 + (1−p0)·F_cond` at the dense grid — the WP._mixture_quantiles
    construction on 199 levels. Handles a negative conditional tail (yards can be negative)."""
    cond_q = np.sort(np.asarray(cond_q, dtype=float))
    p0 = float(np.clip(p0, 0.0, 1.0))
    neg_mass = (1.0 - p0) * float((cond_q < 0.0).mean())
    u = EVAL_LEVELS
    scale = max(1.0 - p0, 1e-9)
    v = np.where(u <= neg_mass, u, np.clip(u - p0, 0.0, None)) / scale
    vals = np.interp(np.clip(v, 0.0, 1.0), EVAL_LEVELS, cond_q,
                     left=cond_q[0], right=cond_q[-1])
    out = np.where((u > neg_mass) & (u <= neg_mass + p0), 0.0, vals)
    return np.maximum.accumulate(out)


def arm_lgbm_hurdle_tail(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                         stat: str) -> tuple[np.ndarray, dict]:
    """The per-stat hurdle: champion-construction P(y=0) classifier × conditional-on-nonzero
    9-knot quantile bank + calibration-slice exponential tails, mixed exactly. The form that
    prices the zero atom DIRECTLY — the mechanism NF-W6 licensed."""
    core, cal, note = MC.calibration_split(train)
    y_tr = _y(train, stat)
    clf = _hurdle_clf()
    clf.fit(EM._X_pos(train, features), (y_tr == 0.0).astype(int))
    p0 = clf.predict_proba(EM._X_pos(test, features))[:, 1]

    nz_train = train.loc[y_tr != 0.0]
    cond_knots_te = EM.fit_cand_knots(nz_train, test, features, stat)

    y_core, y_cal = _y(core, stat), _y(cal, stat)
    core_nz, cal_nz = core.loc[y_core != 0.0], cal.loc[y_cal != 0.0]
    cal_knots = EM.fit_cand_knots(core_nz, cal_nz, features, stat)
    tails = EM.tail_betas_by_pos(cal_knots, y_cal[y_cal != 0.0], cal_nz["position"].to_numpy())
    cond199 = EM.knots_to_eval(cond_knots_te, tails, test["position"].to_numpy())

    out = np.empty((len(test), len(EVAL_LEVELS)))
    for i in range(len(test)):
        out[i] = mixture_quantiles199(p0[i], cond199[i])
    return out, note


def arm_enet_residual(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                      stat: str) -> tuple[np.ndarray, dict]:
    """The linear class: ElasticNet mean (median-imputed, standardized) + a per-position residual
    bank fit on the PURGED calibration slice — structurally the incumbent wrapper with a linear
    head, i.e. the 'is the boosted head earning anything' control."""
    from sklearn.linear_model import ElasticNet
    from sklearn.preprocessing import StandardScaler
    core, cal, note = MC.calibration_split(train)

    def _fit_predict(fit_on: pd.DataFrame, predict_on: pd.DataFrame) -> np.ndarray:
        imp = WP._Imputer(list(features)).fit(fit_on)
        sc = StandardScaler().fit(imp.transform(fit_on))
        m = ElasticNet(alpha=0.03, l1_ratio=0.3, random_state=WP._SEED, max_iter=5000)
        m.fit(sc.transform(imp.transform(fit_on)), _y(fit_on, stat))
        return m.predict(sc.transform(imp.transform(predict_on)))

    resid = _y(cal, stat) - _fit_predict(core, cal)
    bank = EM.residual_bank199(resid, cal["position"].to_numpy())
    point_te = _fit_predict(train, test)
    return EM.apply_bank199(point_te, test["position"].to_numpy(), bank), note


def arm_knn_quantile(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                     stat: str, k: int = KNN_K) -> np.ndarray:
    """The neighborhood class (the NF1.9 veteran-band winner's shape): per-position standardized
    kNN, empirical 199-level quantiles of the neighbors' realized stat — prices the atom and the
    conditional spread nonparametrically."""
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    out = np.empty((len(test), len(EVAL_LEVELS)))
    imp = WP._Imputer(list(features)).fit(train)
    for p in POSITIONS:
        tr_sel = (train["position"] == p).to_numpy()
        te_sel = (test["position"] == p).to_numpy()
        if not te_sel.any():
            continue
        if not tr_sel.any():
            raise ValueError(f"knn_quantile: no {p} rows in train — refusing (NF1.7 (a))")
        Xtr = imp.transform(train.loc[tr_sel])
        sc = StandardScaler().fit(Xtr)
        kk = min(k, max(2, int(tr_sel.sum()) - 1))
        nn = NearestNeighbors(n_neighbors=kk).fit(sc.transform(Xtr))
        _, idx = nn.kneighbors(sc.transform(imp.transform(test.loc[te_sel])))
        ytr = _y(train.loc[tr_sel], stat)
        out[te_sel] = np.quantile(ytr[idx], EVAL_LEVELS, axis=1).T
    return out


# ── Gate composition (SEPARATE named clauses — NF-D20: never bundle) ────────────────────────────
W6B_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok")
#: The coverage floor is a CONSTRAINT (NF1.8) — its refusal classifies CONSTRAINT_REFUSED,
#: never POWER_LIMITED (the NF-W7 classifier rule).
W6B_CONSTRAINT_CHECKS: tuple[str, ...] = ("coverage_floor_ok",)
W6B_ANCHOR_CHECKS: tuple[str, ...] = ("degenerates_lose", "permutation_behaves")


def compose_gate_w6b(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "degenerates_lose": bool(sel["anchors"]["nihilist_loses"]
                                 and sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
    }
    return {"checks": checks, "ship": all(checks.values())}


def classify_cell_null(sel: dict, checks: dict, n_folds: int) -> dict | None:
    """Hand classification of a failing cell (⛔ `cv_power.classify_null` is never invoked — the
    n_arms fold-shortage mis-render, 4× hand-corrected in this vertical). Three states:
    GENUINE_ABSENCE (loses on average — no trigger) · POWER_LIMITED (positive but unresolved —
    margin in folds, `flag_unsafe_field_shrink` applied) · CONSTRAINT_REFUSED (statistics green,
    the null rests on coverage/anchor clauses — more data cannot change it, NF-D18/NF-W7)."""
    if all(checks.values()):
        return None
    stat_fail = [c for c in W6B_STATISTICAL_CHECKS if not checks[c]]
    other_fail = [c for c in (*W6B_CONSTRAINT_CHECKS, *W6B_ANCHOR_CHECKS) if not checks[c]]
    if not stat_fail:
        return {
            "state": "CONSTRAINT_REFUSED",
            "reason": (f"every statistical gate passed and the null rests entirely on "
                       f"constraint/anchor clauses {other_fail} — more data cannot change a "
                       f"directional constraint refusal (NF-D18/NF-W7)."),
            "retest_trigger": None,
            "failing_checks": other_fail,
        }
    if not sel["beats_foil"]:
        return {
            "state": "GENUINE_ABSENCE",
            "reason": (f"the winner LOSES to `{sel['binding_foil']}` on average "
                       f"({sel['mean_delta']} CRPS, {sel['fold_wins']}/{n_folds} fold wins) — "
                       f"a negative point estimate is not rescued by more folds or a smaller "
                       f"field. ⛔ No re-test trigger."),
            "retest_trigger": None,
            "failing_checks": stat_fail + other_fail,
        }
    sr = sel.get("observed_sr")
    folds_needed = None
    if sr and sr > 0:
        # approximation: ignores the deflation term sr0 > 0, so this is a LOWER bound on the
        # folds needed (declared — the honest direction for a re-test trigger).
        folds_needed = int(np.ceil((1.6448536269514722 / sr) ** 2)) + 1
    lo, hi = (sel.get("ci95") or [None, None])[:2]
    ci_word = ("spans zero" if lo is not None and hi is not None and lo <= 0.0 <= hi
               else "excludes zero" if lo is not None and hi is not None else "is unevaluable")
    verdict = {
        "state": "POWER_LIMITED",
        "reason": (f"the point estimate is positive ({sel['mean_delta']} CRPS) and the interval "
                   f"{ci_word} (CI95 {sel['ci95']}); fold wins {sel['fold_wins']}/{n_folds} vs "
                   f"required {sel['fold_clause']['required']}; failing statistical gates: "
                   f"{stat_fail} — the effect is smaller than this design resolves."),
        "retest_trigger": (
            f"≥{folds_needed} half-season folds (≈{max(0, folds_needed - n_folds)} more than "
            f"the current {n_folds}) at the observed per-fold Sharpe {sr} — a LOWER bound "
            f"(the deflation term is ignored); calendar-bound."
            if folds_needed else "unevaluable — no positive per-fold Sharpe to extrapolate from"),
        "failing_checks": stat_fail + other_fail,
    }
    return flag_unsafe_field_shrink(verdict, n_declared_arms=len(REAL_ARMS))


def decide_story(gates: dict[str, dict]) -> dict:
    ship = sorted(c for c, g in gates.items() if g["ship"])
    null = sorted(c for c, g in gates.items() if not g["ship"])
    return {
        "ship_cells": ship, "null_cells": null,
        "headline": f"PERSTAT-BAKEOFF ship={len(ship)} null={len(null)} of {len(gates)} cells",
        "reason": (f"per-cell verdicts (no story-level aggregation gate): SHIP {ship or '—'}; "
                   f"recorded nulls {null or '—'}"),
    }


# ── REPORT-ONLY layers ──────────────────────────────────────────────────────────────────────────
def ppr_report(selections: dict[str, dict]) -> dict:
    """Each cell's CRPS lift × its PPR weight = a points-units MARGINAL contribution, summed per
    position. ⛔ REPORT-ONLY (PM ruling): a sum of marginal contributions, NOT an assembled
    joint-points CRPS — the champion's points hurdle already conditions on usage (NF-W1) and the
    correlation channel is measured-dead (NF-W5)."""
    per_cell: dict[str, float | None] = {}
    per_pos: dict[str, float] = {}
    for c, s in selections.items():
        pos, stat = c.split("|", 1)
        d = s.get("mean_delta")
        pts = None if d is None else round(float(d) * PPR_WEIGHTS[stat], 4)
        per_cell[c] = pts
        if pts is not None:
            per_pos[pos] = round(per_pos.get(pos, 0.0) + pts, 4)
    return {
        "per_cell_points_units": per_cell,
        "per_position_sum_points_units": per_pos,
        "note": ("REPORT-ONLY (PM ruling): winner-vs-binding-incumbent CRPS lift × PPR weight, "
                 "summed per position — a sum of MARGINAL contributions in points units, NOT an "
                 "assembled joint-points claim; a per-stat win need not move assembled points."),
    }


def structural_coverage_note(real_p0: float) -> float:
    """The structural coverage(80) expectation for an honest atom-pricing predictive with
    q10 = 0: the interval covers the whole atom plus everything up to q90 of the remainder
    (NF1.9 (e) / E2.1-r (a)) — REPORTED so the floor's one-sidedness is legible per cell."""
    return round(float(real_p0 + (1.0 - real_p0) * 0.9), 4)
