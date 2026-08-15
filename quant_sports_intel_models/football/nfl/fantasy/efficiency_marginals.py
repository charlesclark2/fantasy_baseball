"""efficiency_marginals.py — NF-W6: per-stat distributional targets — THE ORACLE DECISION GATE
(pure).

THE STORY IN ONE PARAGRAPH. Three consecutive component studies came back null against the
champion — NF-W3 (environment), NF-W4 (availability), NF-W5 (correlation) — and NF-MARGIN1/2/3
then found the real frontier in the MARGINAL SHAPE of the points predictive. NF-W6 asks the
narrower per-stat question: can the champion's per-stat distributional targets — receiving /
rushing / passing yards + TDs — be improved AS MARGINALS? ⭐ Given three component nulls, this
story does NOT open with a bake-off. It opens with the DECISION GATE: score realized-efficiency
ORACLES (peek the test block's realized yards/TDs per position — every declared form, matched-n)
against the champion's per-stat predictive, and only a demonstrably LARGE ceiling licenses the
§0.5 bake-off. A small ceiling is a complete, valuable result: "the champion's per-stat marginals
are already near the ceiling."

⭐ TWO FRAMING CORRECTIONS BAKED IN (the story card): this is NOT a simulator component (NF-W8's
§9 premise is measured-dead — NF-W5), and it is NOT a marginal point-forecast improvement in the
W3/W4/W5 sense (those all nulled; the champion absorbs environment, availability and correlation).

WHAT "THE CHAMPION'S PER-STAT PREDICTIVE" IS — STATED PLAINLY, because it is the incumbent this
story measures a ceiling over. The NF-W1 champion emits raw stat-line components as POINT MEANS
only (`WP.fit_component_head`: pooled LGBM regression means over the champion feature set,
clipped at 0 — "advisory raw lines beside the gated points distribution"). NO per-stat
DISTRIBUTION is served today. The incumbent distributional forms are therefore the two minimal
champion-faithful constructions, both built ONLY from champion machinery:
  · `inc_head_bank`    — the champion component-head mean + a per-position empirical residual
                         bank on the dense grid. ⭐ The bank is fit on a PURGED CALIBRATION SLICE
                         (`MC.calibration_split`) — in-sample residuals of a boosted model are
                         optimistically sharp (NF-MARGIN1), and an artificially sharp incumbent
                         would INFLATE the measured ceiling, i.e. bias toward BUILD. The mean the
                         incumbent serves is the full-train head, exactly as the champion emits.
  · `inc_climatology`  — the per-position train empirical marginal of the stat. For the
                         zero-heavy TD targets this is the honest discrete null and may
                         legitimately be the better incumbent form.
The ceiling is measured against the BINDING incumbent (the better of the two by mean fold CRPS):
you would not build a bake-off to beat the WORSE of two trivial forms. This selection LOWERS the
ceiling (favors NO); the oracle-side max RAISES it (favors YES) — both declared, and the NF-W5
rule carries: the estimator's bias direction favors a BUILD, so a NO is conservative.

THE ORACLES — WHAT "PEEK REALIZED YARDS/TD PER POSITION" MEANS HERE. A ROW-level peek is a
zero-CRPS degenerate, not a ceiling. The oracle peeks the BLOCK: each declared form re-fit on the
test block itself (NF-W1's `anchor_oracle_marginal` semantics, per stat), with CONDITIONAL forms
CROSS-FIT within the block (K = CROSSFIT_K) so no row's own label reaches its own prediction —
the peek is the block's realized efficiency REGIME (its conditional structure + its residual
distribution), not the answers row by row. Three forms (NF-D16 (g‴): per-form ceilings, because
the forms differ in capacity), each with a matched-n control (NF1.9 (f)):
  · `oracle__inc_climatology`    — per-position empirical marginal ON the block (the story
                                   card's phrase, literally).
  · `oracle__inc_head_bank`      — cross-fit head mean on the block + the block's residual bank.
  · `oracle__cand_lgbm_quantile` — the form a bake-off arm would take: cross-fit 9-knot pooled
                                   quantile bank + ⭐ the NF-MARGIN1 exponential mean-excess TAIL
                                   beyond the knots (inherited from day one — a knot form with
                                   flat extension has no tails, and the ceiling instrument must
                                   be able to SEE tail headroom). ⭐ WHY THIS FORM IS REQUIRED:
                                   the two incumbent-form oracles carry position-CONSTANT banks —
                                   structurally blind to conditional heteroscedasticity (a
                                   12-target WR week is wider than a 2-target TE week), which is
                                   precisely where per-stat headroom would live. A ceiling
                                   estimator missing that channel could return a FALSE NO.

THE METRIC IS `crps_q199` (the NF-MARGIN1 dense grid): the native 39-level grid is structurally
blind to beyond-grid tail work, and a build's arms would carry tail models — so the ORACLE stage
must already score on the grid that can see them. TD targets are zero-heavy → CRPS, never MAE
(NF-D11/D14: MAE inverts at the conditional median; the all-zero `nihilist_zero` degenerate is
SCORED every cell, never reasoned about, and must LOSE).

THE PRE-REGISTERED DECISION RULE (narrative copy: ablation_results/nf_w6_preregistration.md).
Per (position, stat) cell: ceiling_pct = 100 · (binding incumbent − best per-form oracle CRPS) /
binding incumbent CRPS, paired over the 8 NF-W1 folds. `ceiling_stat_ok` = CI95 excludes zero ∧
calibrated fold clause ∧ BH binding (own family AND pooled — MH2 (a); two declared families:
yards cells, TD cells). Bands on ceiling_pct — the NF-W5 precedent bands, calibrated against this
vertical's own history (NF-W3's 2–3% recorded as "cannot justify the chain"; NF-MARGIN wins live
well below 2%): < 2% → NO · 2–5% → MARGINAL (PM decision, nothing built in-session) · ≥ 5% → YES
(build the §0.5 bake-off for THAT cell's family). Not stat_ok → NO regardless of magnitude.
Story verdict: BUILD iff any cell is YES; else RECORDED NULL with MARGINAL cells named. PBO is
UNDEFINED at this stage (a pre-registered anchor contrast, not a searched field — the NF-W5
ceiling rule verbatim); DSR does not arise (no arm is selected); `cv_power.classify_null` is NOT
invoked (the n_arms=1 fold-shortage mis-render is a known instrument bug — NF-W3 (c); the
decision object here is bands, not a null state).

NF-W0 CONSTRAINTS HONORED BY CONSTRUCTION: the matrix is the NF-W1 certified build (PIT gate on
every build, provenance-checked features, NULL-bearing snaps untouched); NO new features exist in
this story, so ⛔ no fillna(0) on any NULL-bearing input arises (the TD label attach fills
LABEL-side zeros for rostered-no-stat weeks — the frame's retained-zero convention, identical to
the existing yards/receptions attach, conservation-guarded); NO pbp source is read, so the
NF-W3 franchise-code/era traps are honored by absence (declared, not silent).

⚖️ EDGE-INDEPENDENT (`best_alpha` N/A) · DEPLOY-HELD: this module promotes nothing, publishes
nothing, retrains nothing; research-only, no changelog entry.

Pure module — no lake IO. The runner is `run_nf_w6_efficiency_marginals.py`.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W6"
PRIMARY_METRIC = "crps_q199"
#: The NF-MARGIN1 dense grid — imported, never re-typed (one source of the 199 levels).
EVAL_LEVELS: np.ndarray = MC.EVAL_LEVELS
_SEED = 20260814

#: The per-position stat cells. Scope is DECLARED: QB rushing is a real fantasy channel and is
#: in; WR/TE rushing and QB/RB passing-adjacent receiving are excluded as minor channels (a
#: future story may widen the map; nothing here forbids it).
POSITION_STATS: dict[str, tuple[str, ...]] = {
    "QB": ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds"),
    "RB": ("rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds"),
    "WR": ("receiving_yards", "receiving_tds"),
    "TE": ("receiving_yards", "receiving_tds"),
}
STATS: tuple[str, ...] = (
    "passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
    "receiving_yards", "receiving_tds",
)
TD_STATS: tuple[str, ...] = ("passing_tds", "rushing_tds", "receiving_tds")

#: Incumbent reference forms (foil-class: never shippable, the BINDING one sets the bar).
INCUMBENT_FORMS: tuple[str, ...] = ("inc_head_bank", "inc_climatology")
#: The declared oracle forms (NF-D16 (g‴)) — each gets `oracle__<form>` + `matched_n__<form>`.
ORACLE_FORMS: tuple[str, ...] = ("inc_climatology", "inc_head_bank", "cand_lgbm_quantile")
#: Degenerate/diagnostic anchors — scored every cell, never trials (MH2.1 (a)).
BASE_ANCHORS: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width")

oracle_of = GE.oracle_of
matched_n_of = GE.matched_n_of

#: In-block cross-fit folds for the conditional oracles: the peek is the block's REGIME, never
#: the row's own label (a row-level peek is a zero-CRPS degenerate, not a ceiling).
CROSSFIT_K = 3
#: The NF-W5 precedent decision bands on ceiling_pct (NO < 2.0 ≤ MARGINAL < 5.0 ≤ YES).
CEILING_BANDS: tuple[float, float] = (2.0, 5.0)
#: A per-position bank/climatology below this many rows REFUSES (NF1.7 (a)) — the residual bank
#: falls back to the POOLED bank first (the WP.residual_bank convention) and refuses only if the
#: pooled sample is also thin.
MIN_BANK_ROWS = 50
#: Exponential-tail fit floor (the NF-MARGIN1 convention): a side with fewer exceedances gets
#: beta 0 (flat, the as-served behavior) and is COUNTED — loud, never silent.
MIN_TAIL_N = 10
MAX_WIDTH_SCALE = 3.0
#: The candidate form's knot levels — the champion's own 9 knots (the representation a bake-off
#: arm would inherit), plus the NF-MARGIN1 tail beyond them.
FIT_LEVELS: tuple[float, ...] = WP.FIT_LEVELS

TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
POSITIONS = WP.POSITIONS
FDR_Q = WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
#: Report-only era split (NF-W2d/W2e): derived from the fold axis, never re-typed.
CAPTURE_ERA_FOLDS: tuple[str, ...] = tuple(
    f"{s}H{h}" for s, h in WP.TEST_BLOCKS if s >= 2025)

# Shared verdict / reporting helpers — IMPORTED, never re-typed (NF-W2d discipline).
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
matched_n_train = GE.matched_n_train


def cell_key(pos: str, stat: str) -> str:
    return f"{pos}|{stat}"


def cells() -> tuple[str, ...]:
    return tuple(cell_key(p, s) for p in POSITIONS for s in POSITION_STATS[p])


def anchors() -> tuple[str, ...]:
    return (*BASE_ANCHORS,
            *(oracle_of(f) for f in ORACLE_FORMS),
            *(matched_n_of(f) for f in ORACLE_FORMS))


def all_labels() -> tuple[str, ...]:
    return (*INCUMBENT_FORMS, *anchors())


#: ⭐ TWO pre-registered multiplicity families over the CEILING tests — yards cells and TD cells;
#: own family AND pooled computed, the STRICTER binds (MH2 (a)).
def fdr_families() -> dict[str, tuple[str, ...]]:
    yards, tds = [], []
    for c in cells():
        (tds if c.split("|", 1)[1] in TD_STATS else yards).append(f"w6_ceiling_{c}")
    return {"yards": tuple(yards), "tds": tuple(tds)}


def fdr_two_families_w6(yards_p: dict[str, float | None],
                        tds_p: dict[str, float | None]) -> dict:
    """MH2 (a): both declared families corrected within themselves AND pooled; a YES must survive
    BOTH, so no verdict can turn on the family choice. (The NF-W3 composer's shape, on this
    story's families — local because a pure module must not import a story runner.)"""
    own = {**M14.bh_fdr(yards_p, q=FDR_Q), **M14.bh_fdr(tds_p, q=FDR_Q)}
    pooled_in = {f"yards::{k}": v for k, v in yards_p.items()}
    pooled_in.update({f"tds::{k}": v for k, v in tds_p.items()})
    pooled = {k.split("::", 1)[1]: v for k, v in M14.bh_fdr(pooled_in, q=FDR_Q).items()}
    binding = {k: bool(own.get(k) and pooled.get(k)) for k in own}
    return {"own_family": own, "pooled": pooled, "binding": binding}


# ── Label attach (TDs join the matrix; yards are already on it) ─────────────────────────────────
def attach_td_labels(feat: pd.DataFrame, stats_feed: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Merge the three TD label columns onto the certified matrix at (season, week, gsis_id).

    LABEL-side realized values, exactly the existing yards/receptions attach in
    `WP.engineer_features`: a rostered-no-stat week is a REAL ZERO (the frame's retained-zero
    convention) — this is a label fill on rows the certified frame already carries, NOT a
    fillna(0) on a NULL-bearing FEATURE (NF-W0b constraint (9) is about features).

    Two refusals, both loud (NF1.7 (a)):
      · a duplicate (season, week, gsis_id) key in the feed REFUSES — a consensus/label keyed on
        an unresolved grain splits one player into two half-truths (the MLB-props grain lesson);
      · a conservation mismatch REFUSES — the summed TDs on the matrix over matched keys must
        equal the feed's sums over the same keys (the NF-W3 row-conservation rule for joins).
    """
    keys = ["season", "week", "gsis_id"]
    s = stats_feed.rename(columns={"player_id": "gsis_id"})[keys + list(TD_STATS)].copy()
    for c in ("season", "week"):
        s[c] = s[c].astype("int64")
    dup = int(s.duplicated(keys).sum())
    if dup:
        raise ValueError(
            f"stats feed carries {dup} duplicate (season, week, gsis_id) keys — refusing to "
            f"attach TD labels on an unresolved grain")
    for c in TD_STATS:
        if c in feat.columns:
            raise ValueError(f"matrix already carries `{c}` — refusing a second attach "
                             f"(a double merge silently suffixes and orphans the label)")
    merged = feat.merge(s, on=keys, how="left")
    if len(merged) != len(feat):
        raise ValueError(
            f"TD label attach changed the row count {len(feat)} → {len(merged)} — the join key "
            f"is not unique on one side; refusing (NF-W3 conservation)")
    feed_in_frame = s.merge(feat[keys].drop_duplicates(), on=keys, how="inner")
    audit: dict = {"n_rows": int(len(merged)), "feed_dup_keys": dup}
    for c in TD_STATS:
        matrix_sum = float(pd.to_numeric(merged[c], errors="coerce").sum())
        feed_sum = float(pd.to_numeric(feed_in_frame[c], errors="coerce").sum())
        if abs(matrix_sum - feed_sum) > 1e-6:
            raise ValueError(
                f"TD conservation FAILED for `{c}`: matrix {matrix_sum} vs feed-over-matched-keys "
                f"{feed_sum} — the attach corrupted the label")
        audit[f"{c}_total"] = matrix_sum
        audit[f"{c}_filled_zero_rows"] = int(merged[c].isna().sum())
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0.0)
    return merged, audit


def assert_stat_labels_present(feat: pd.DataFrame) -> None:
    missing = [c for c in STATS if c not in feat.columns]
    if missing:
        raise ValueError(f"matrix is missing per-stat label columns {missing} — the yards labels "
                         f"ride the NF-W1 matrix and TDs come from attach_td_labels")


# ── Banks (all at the 199-level dense grid — no representation truncation) ──────────────────────
def climatology_bank(y: np.ndarray, pos: np.ndarray) -> dict[str, np.ndarray]:
    """Per-position empirical quantiles of the stat at the dense grid. REFUSES a thin position
    (NF1.7 (a)) — an anchor that fails to fit must never silently pass."""
    out: dict[str, np.ndarray] = {}
    yv = np.asarray(y, dtype=float)
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        yp = yv[sel]
        yp = yp[np.isfinite(yp)]
        if len(yp) < MIN_BANK_ROWS:
            raise ValueError(f"climatology for {p} fit on {len(yp)} rows < {MIN_BANK_ROWS} — "
                             f"refusing (NF1.7 (a))")
        out[p] = np.quantile(yp, EVAL_LEVELS)
    return out


def residual_bank199(resid: np.ndarray, pos: np.ndarray) -> dict[str, np.ndarray]:
    """Per-position empirical residual quantiles at the dense grid — the champion's own
    residual-bank pattern (`WP.residual_bank`), on 199 levels. A thin position falls back to the
    POOLED bank (the WP convention); a thin pooled sample REFUSES."""
    r = np.asarray(resid, dtype=float)
    r_ok = r[np.isfinite(r)]
    if len(r_ok) < MIN_BANK_ROWS:
        raise ValueError(f"residual bank fit on {len(r_ok)} rows < {MIN_BANK_ROWS} — refusing "
                         f"(NF1.7 (a))")
    pooled = np.quantile(r_ok, EVAL_LEVELS)
    out: dict[str, np.ndarray] = {}
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        rp = r[sel]
        rp = rp[np.isfinite(rp)]
        out[p] = np.quantile(rp, EVAL_LEVELS) if len(rp) >= MIN_BANK_ROWS else pooled
    return out


def apply_bank199(point: np.ndarray, pos: np.ndarray, bank: dict[str, np.ndarray]) -> np.ndarray:
    out = np.empty((len(point), len(EVAL_LEVELS)))
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        if sel.any():
            out[sel] = np.asarray(point, dtype=float)[sel][:, None] + bank[p][None, :]
    return out


# ── The champion component head (byte-identical construction to WP.fit_component_head) ──────────
def head_model():
    """EXACTLY the champion component head's learner — the same `WP._lgbm` call with the same
    override dict (guard-tested against `fit_component_head`'s own source)."""
    return WP._lgbm({"objective": "regression", "n_estimators": 200})


def _X_pos(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    X = df[list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return np.column_stack([X, WP._pos_codes(df)])


def fit_head_mean(train: pd.DataFrame, predict_on: pd.DataFrame, features: list[str],
                  stat: str) -> np.ndarray:
    """The champion head's mean for one stat: pooled LGBM regression + position code, predictions
    clipped at 0 (the `fit_component_head` convention, verbatim)."""
    y = pd.to_numeric(train[stat], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    m = head_model()
    m.fit(_X_pos(train, features), y)
    return np.clip(m.predict(_X_pos(predict_on, features)), 0.0, None)


def inc_head_bank(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                  stat: str) -> tuple[np.ndarray, dict]:
    """The incumbent conditional form: full-train head mean (as the champion emits) + a residual
    bank measured on the PURGED calibration slice (honest OOS residuals — NF-MARGIN1's lesson:
    in-sample residuals of a boosted model are optimistically sharp, and a too-sharp incumbent
    inflates the ceiling toward BUILD)."""
    core, cal, note = MC.calibration_split(train)
    mean_cal = fit_head_mean(core, cal, features, stat)
    resid = pd.to_numeric(cal[stat], errors="coerce").fillna(0.0).to_numpy(float) - mean_cal
    bank = residual_bank199(resid, cal["position"].to_numpy())
    mean_te = fit_head_mean(train, test, features, stat)
    return apply_bank199(mean_te, test["position"].to_numpy(), bank), note


# ── Cross-fit (the block-regime peek that never sees a row's own label) ─────────────────────────
def crossfit_ids(n: int, k: int, fold_label: str, stat: str) -> np.ndarray:
    if k < 2:
        raise ValueError(f"CROSSFIT_K={k} < 2 — a 1-fold 'cross-fit' is an in-sample fit and the "
                         f"oracle would memorize rows (refusing)")
    rng = np.random.default_rng(np.random.SeedSequence(
        [_SEED, zlib.crc32(fold_label.encode()), zlib.crc32(stat.encode())]))
    return rng.permutation(np.arange(n) % k)


def oracle_climatology(test: pd.DataFrame, stat: str) -> np.ndarray:
    """Peek realized yards/TD per position — the block's own empirical marginal (the story card's
    phrase, literally; `WP.anchor_oracle_marginal` semantics per stat, dense grid)."""
    y = pd.to_numeric(test[stat], errors="coerce").fillna(0.0).to_numpy(float)
    bank = climatology_bank(y, test["position"].to_numpy())
    return apply_bank199(np.zeros(len(test)), test["position"].to_numpy(), bank)


def oracle_head_bank(test: pd.DataFrame, features: list[str], stat: str,
                     fold_label: str) -> np.ndarray:
    """The conditional-form block peek: K-fold cross-fit head means within the block (no row sees
    its own label) + the block's cross-fit residual bank (the residual-DISTRIBUTION peek is
    deliberate — that IS the realized-efficiency regime)."""
    ids = crossfit_ids(len(test), CROSSFIT_K, fold_label, stat)
    y = pd.to_numeric(test[stat], errors="coerce").fillna(0.0).to_numpy(float)
    mean = np.empty(len(test))
    for j in range(CROSSFIT_K):
        hold = ids == j
        mean[hold] = fit_head_mean(test.loc[~hold], test.loc[hold], features, stat)
    bank = residual_bank199(y - mean, test["position"].to_numpy())
    return apply_bank199(mean, test["position"].to_numpy(), bank)


# ── The candidate quantile form (+ the NF-MARGIN1 exponential tail, from day one) ───────────────
def fit_cand_knots(train: pd.DataFrame, predict_on: pd.DataFrame, features: list[str],
                   stat: str) -> np.ndarray:
    """Pooled 9-knot LGBM quantile bank for one stat (the champion representation a bake-off arm
    would inherit)."""
    y = pd.to_numeric(train[stat], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    Xtr, Xte = _X_pos(train, features), _X_pos(predict_on, features)
    knots = np.empty((len(predict_on), len(FIT_LEVELS)))
    for j, alpha in enumerate(FIT_LEVELS):
        m = WP._lgbm({"objective": "quantile", "alpha": alpha})
        m.fit(Xtr, y)
        knots[:, j] = m.predict(Xte)
    return np.sort(knots, axis=1)


def tail_betas_by_pos(knots_sorted: np.ndarray, y: np.ndarray,
                      pos: np.ndarray) -> dict[str, dict]:
    """Per-position exponential exceedance scales beyond the end knots (mean-excess = the
    exponential MLE — the MC.fit_tail_betas convention on the knot representation). A side with
    < MIN_TAIL_N exceedances gets beta 0 (flat = the as-served truncation) and is COUNTED."""
    out: dict[str, dict] = {}
    yv = np.asarray(y, dtype=float)
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        if not sel.any():
            out[p] = {"beta_hi": 0.0, "beta_lo": 0.0, "n_hi": 0, "n_lo": 0,
                      "thin_hi": True, "thin_lo": True}
            continue
        q_lo, q_hi = knots_sorted[sel, 0], knots_sorted[sel, -1]
        yp = yv[sel]
        hi_exc = yp[yp > q_hi] - q_hi[yp > q_hi]
        lo_exc = q_lo[yp < q_lo] - yp[yp < q_lo]
        out[p] = {"beta_hi": float(np.mean(hi_exc)) if len(hi_exc) >= MIN_TAIL_N else 0.0,
                  "beta_lo": float(np.mean(lo_exc)) if len(lo_exc) >= MIN_TAIL_N else 0.0,
                  "n_hi": int(len(hi_exc)), "n_lo": int(len(lo_exc)),
                  "thin_hi": bool(len(hi_exc) < MIN_TAIL_N),
                  "thin_lo": bool(len(lo_exc) < MIN_TAIL_N)}
    return out


def knots_to_eval(knots_sorted: np.ndarray, tails: dict[str, dict],
                  pos: np.ndarray) -> np.ndarray:
    """Interpolate 9 knots onto the dense grid with exponential tails beyond the end knots
    (x = q95 + beta_hi·ln((1−0.95)/(1−u)) above, mirrored below — continuous at the joint;
    beta 0 ⇒ flat, the as-served NF-MARGIN1 truncation). Monotone by construction."""
    kl = np.asarray(FIT_LEVELS, dtype=float)
    out = np.empty((knots_sorted.shape[0], len(EVAL_LEVELS)))
    inner = np.clip(EVAL_LEVELS, kl[0], kl[-1])
    above = EVAL_LEVELS > kl[-1]
    below = EVAL_LEVELS < kl[0]
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        if not sel.any():
            continue
        t = tails[p]
        for i in np.where(sel)[0]:
            row = np.interp(inner, kl, knots_sorted[i])
            if above.any() and t["beta_hi"] > 0:
                row[above] = knots_sorted[i, -1] + t["beta_hi"] * np.log(
                    (1.0 - kl[-1]) / (1.0 - EVAL_LEVELS[above]))
            if below.any() and t["beta_lo"] > 0:
                row[below] = knots_sorted[i, 0] - t["beta_lo"] * np.log(
                    kl[0] / EVAL_LEVELS[below])
            out[i] = row
    return out


def oracle_cand_quantile(test: pd.DataFrame, features: list[str], stat: str,
                         fold_label: str) -> tuple[np.ndarray, dict]:
    """The candidate-form block peek: cross-fit knots within the block + the block's per-position
    tail betas. This is the only oracle that can express conditional heteroscedasticity — its
    ceiling bounds what a quantile-learner bake-off arm could reach."""
    ids = crossfit_ids(len(test), CROSSFIT_K, fold_label, stat + "|cand")
    knots = np.empty((len(test), len(FIT_LEVELS)))
    for j in range(CROSSFIT_K):
        hold = ids == j
        knots[hold] = fit_cand_knots(test.loc[~hold], test.loc[hold], features, stat)
    y = pd.to_numeric(test[stat], errors="coerce").fillna(0.0).to_numpy(float)
    tails = tail_betas_by_pos(knots, y, test["position"].to_numpy())
    return knots_to_eval(knots, tails, test["position"].to_numpy()), tails


def matched_cand_quantile(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                          stat: str) -> np.ndarray:
    """The candidate form fit honestly on the block-sized recent train window (NF1.9 (f)) —
    the capacity control the oracle reading is checked against. Window-in-sample tails
    (declared: any optimism here favors matched_n, i.e. makes `oracle_beats_matched_n`
    HARDER to claim — conservative)."""
    window = matched_n_train(train, test)
    knots = fit_cand_knots(window, test, features, stat)
    w_knots = fit_cand_knots(window, window, features, stat)
    y_w = pd.to_numeric(window[stat], errors="coerce").fillna(0.0).to_numpy(float)
    tails = tail_betas_by_pos(w_knots, y_w, window["position"].to_numpy())
    return knots_to_eval(knots, tails, test["position"].to_numpy())


def matched_head_bank(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                      stat: str) -> np.ndarray:
    """Head+bank on the matched window (window-in-sample bank — same declared bias direction)."""
    window = matched_n_train(train, test)
    mean_w = fit_head_mean(window, window, features, stat)
    resid = pd.to_numeric(window[stat], errors="coerce").fillna(0.0).to_numpy(float) - mean_w
    bank = residual_bank199(resid, window["position"].to_numpy())
    mean_te = fit_head_mean(window, test, features, stat)
    return apply_bank199(mean_te, test["position"].to_numpy(), bank)


def matched_climatology(train: pd.DataFrame, test: pd.DataFrame, stat: str) -> np.ndarray:
    window = matched_n_train(train, test)
    y = pd.to_numeric(window[stat], errors="coerce").fillna(0.0).to_numpy(float)
    bank = climatology_bank(y, window["position"].to_numpy())
    return apply_bank199(np.zeros(len(test)), test["position"].to_numpy(), bank)


# ── Degenerate anchors (measured every cell, never reasoned about — NF-D14) ─────────────────────
def anchor_nihilist(n: int) -> np.ndarray:
    return np.zeros((n, len(EVAL_LEVELS)))


def anchor_zero_width(bank: np.ndarray) -> np.ndarray:
    med = np.sort(bank, axis=1)[:, len(EVAL_LEVELS) // 2]
    return np.repeat(med[:, None], len(EVAL_LEVELS), axis=1)


def anchor_max_width(bank: np.ndarray) -> np.ndarray:
    b = np.sort(bank, axis=1)
    med = b[:, len(EVAL_LEVELS) // 2][:, None]
    return med + MAX_WIDTH_SCALE * (b - med)


# ── Scoring ─────────────────────────────────────────────────────────────────────────────────────
_I10 = int(np.searchsorted(EVAL_LEVELS, 0.10))
_I90 = int(np.searchsorted(EVAL_LEVELS, 0.90))


def score_bank(bank: np.ndarray, y: np.ndarray) -> dict:
    """One reducer for every construction — REFUSES a non-finite predictive (NF-W3 (b): an arm
    silently scored on a smaller population is not in the same contest)."""
    b = np.asarray(bank, dtype=float)
    if not np.isfinite(b).all():
        raise ValueError(f"non-finite predictive: {int((~np.isfinite(b)).sum())} bad values — "
                         f"refusing to nanmean past a broken construction (NF-W3 (b))")
    yv = np.asarray(y, dtype=float)
    if not np.isfinite(yv).all():
        raise ValueError("non-finite labels reached the reducer — the attach is broken")
    q = np.sort(b, axis=1)
    crps = WP.crps_from_quantiles(q, yv, EVAL_LEVELS)
    inside = (yv >= q[:, _I10]) & (yv <= q[:, _I90])
    return {"crps_q199": float(np.mean(crps)),
            "coverage_80": float(np.mean(inside)),
            "pred_p0": float(np.mean((q <= 1e-9).mean(axis=1))),
            "real_p0": float(np.mean(yv == 0.0)),
            "n": int(len(yv))}


# ── Ceiling composition (pure, from stored per-fold scores — derived, never stored) ─────────────
def cell_crps_matrix(fold_results: list[dict], cell: str,
                     metric: str = PRIMARY_METRIC) -> pd.DataFrame:
    return pd.DataFrame({fr["label"]: {lab: fr["cells"][cell]["scores"][lab][metric]
                                       for lab in fr["cells"][cell]["scores"]}
                         for fr in fold_results}).T


def select_cell(fold_results: list[dict], cell: str, n_folds: int) -> dict:
    """The per-cell ceiling selection — everything downstream (decision, FDR, verdict words) is
    derived from THIS dict, which itself derives from stored fold scores (NF-W2e/W3: a verdict is
    re-derivable at zero refit cost)."""
    crps = cell_crps_matrix(fold_results, cell)
    mean_crps = crps.mean(axis=0)
    binding_inc = str(mean_crps[list(INCUMBENT_FORMS)].idxmin())
    inc = crps[binding_inc].to_numpy(dtype=float)
    clause = cv_power.fold_consistency_clause(n_folds)

    per_form: dict[str, dict] = {}
    for f in ORACLE_FORMS:
        d = inc - crps[oracle_of(f)].to_numpy(dtype=float)
        m, lo, hi = paired_ci95(d)
        per_form[f] = {
            "mean_delta": None if m is None else round(m, 5),
            "ci95": [None if lo is None else round(lo, 5),
                     None if hi is None else round(hi, 5)],
            "fold_wins": int((d > 0).sum()),
            "oracle_mean": round(float(mean_crps[oracle_of(f)]), 5),
            "matched_n_mean": round(float(mean_crps[matched_n_of(f)]), 5),
            # NF1.9 (f): the peek is INFORMATIVE only if it beats the same form at matched n —
            # else its edge is recency/capacity, not block information. Report-only.
            "oracle_beats_matched_n": bool(mean_crps[oracle_of(f)]
                                           < mean_crps[matched_n_of(f)]),
        }
    best_form = max(per_form, key=lambda f: (per_form[f]["mean_delta"]
                                             if per_form[f]["mean_delta"] is not None
                                             else -np.inf))
    deltas = inc - crps[oracle_of(best_form)].to_numpy(dtype=float)
    mean_d, lo, hi = paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    pval = M14.onesided_paired_pvalue(deltas)
    mean_inc = float(np.mean(inc))
    pct = (100.0 * mean_d / mean_inc) if (mean_d is not None and mean_inc > 0) else None

    fold_labels = [fr["label"] for fr in fold_results]
    cap = [i for i, lbl in enumerate(fold_labels) if lbl in CAPTURE_ERA_FOLDS]
    leg = [i for i, lbl in enumerate(fold_labels) if lbl not in CAPTURE_ERA_FOLDS]

    inc_cov = [fr["cells"][cell]["scores"][binding_inc] for fr in fold_results]
    n_tot = sum(s["n"] for s in inc_cov)
    cov = (sum(s["coverage_80"] * s["n"] for s in inc_cov) / n_tot) if n_tot else float("nan")

    return {
        "cell": cell, "n_rows": int(n_tot),
        "selection_metric": PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "binding_incumbent": binding_inc,
        "mean_incumbent": round(mean_inc, 5),
        "per_form": per_form, "best_form": best_form,
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "p_one_sided": pval,
        "ceiling_pct": None if pct is None else round(pct, 3),
        "anchors": {
            # NF-D11/D14: measured every run. On TD cells the nihilist losing is the proof the
            # metric is sound (CRPS, not MAE — an all-zero arm winning = metric inverted).
            "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[binding_inc]),
            "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[binding_inc]),
            "max_width_loses": bool(mean_crps["max_width"] > mean_crps[binding_inc]),
        },
        "incumbent_calibration": {
            "coverage_80": round(float(cov), 4),
            "pred_p0_mean": round(float(np.mean(
                [s["pred_p0"] for s in inc_cov])), 4),
            "real_p0": round(float(np.mean([s["real_p0"] for s in inc_cov])), 4),
        },
        "era_note": {
            "capture_folds": [fold_labels[i] for i in cap],
            "capture_mean_delta": (round(float(np.mean(deltas[cap])), 5) if cap else None),
            "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 5) if leg else None),
            "note": "REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.",
        },
        "estimator_note": ("max over the per-form block-peeking oracles vs the BINDING (better) "
                           "incumbent — the oracle-side max is upward-biased by selection over "
                           "the declared forms and the peek favors YES, so a NO is conservative "
                           "(pre-registered; the NF-W5 rule)."),
        "pbo": None,
        "pbo_state": ("UNDEFINED — the ceiling is a pre-registered anchor contrast, not a "
                      "searched field; declared before the run (the NF-W5 ceiling rule)."),
        "fdr_binding": None,   # injected by the runner's verdict layer
    }


# ── The decision (bands + stat_ok; fails closed) ────────────────────────────────────────────────
def decide_cell(sel: dict) -> dict:
    """NO / MARGINAL / YES per cell — the NF-W5 decision shape on this story's object. Fails
    closed: an unevaluable pct or interval is a NO."""
    pct = sel.get("ceiling_pct")
    lo = (sel.get("ci95") or [None, None])[0]
    stat_ok = bool(
        pct is not None and lo is not None and lo > 0
        and sel["fold_clause"]["passes"]
        and sel.get("fdr_binding") is True
    )
    if pct is None or not stat_ok:
        answer = "NO"
        reason = (f"ceiling unevaluable — NO (fails closed)" if pct is None else
                  f"ceiling {pct:.2f}% is not statistically demonstrable (CI-excludes-zero "
                  f"{bool(lo is not None and lo > 0)}, fold clause "
                  f"{sel['fold_clause']['passes']}, BH binding {sel.get('fdr_binding')}) — NO "
                  f"regardless of magnitude")
    elif pct < CEILING_BANDS[0]:
        answer = "NO"
        reason = (f"ceiling {pct:.2f}% < the {CEILING_BANDS[0]}% band — the champion's "
                  f"per-stat marginal is already near its ceiling on this cell")
    elif pct < CEILING_BANDS[1]:
        answer = "MARGINAL"
        reason = (f"ceiling {pct:.2f}% sits in the {CEILING_BANDS[0]}–{CEILING_BANDS[1]}% band "
                  f"— a PM decision; nothing is built in-session")
    else:
        answer = "YES"
        reason = (f"ceiling {pct:.2f}% ≥ {CEILING_BANDS[1]}% — a §0.5 bake-off on this cell's "
                  f"family is licensed")
    return {"answer": answer, "stat_ok": stat_ok, "bands": list(CEILING_BANDS),
            "ceiling_pct": pct, "reason": reason}


def decide_story(cell_decisions: dict[str, dict]) -> dict:
    """BUILD iff any cell is YES; else a RECORDED NULL with MARGINAL cells named for the PM."""
    yes = sorted(c for c, d in cell_decisions.items() if d["answer"] == "YES")
    marginal = sorted(c for c, d in cell_decisions.items() if d["answer"] == "MARGINAL")
    if yes:
        answer = "BUILD"
        reason = (f"{len(yes)} cell(s) clear the YES band with stat_ok — the §0.5 bake-off is "
                  f"licensed for: {yes}")
    else:
        answer = "NULL"
        reason = ("no cell clears the YES band — the champion's per-stat marginals are already "
                  "near their ceiling; the null is recorded and NOTHING is built (the story "
                  "card's likely outcome, and a legitimate one)"
                  + (f"; MARGINAL cells for the PM: {marginal}" if marginal else ""))
    return {"answer": answer, "yes_cells": yes, "marginal_cells": marginal, "reason": reason}


# ── Positive control (MH2.1 (d): the instrument must SEE a known regime shift) ──────────────────
def positive_control_shift(test: pd.DataFrame, stat: str, pos: str,
                           train_bank: dict[str, np.ndarray], scale: float = 1.3) -> dict:
    """Scale the block's realized stat ×`scale` for one position and re-score incumbent-vs-oracle
    climatology. The peeking oracle refits on the shifted block; the train-fit incumbent cannot —
    the measured ceiling MUST grow. Returns both readings; the runner asserts growth in --smoke
    and the guards assert it on synthetic data."""
    sel = (test["position"] == pos).to_numpy()
    sub = test.loc[sel]
    y = pd.to_numeric(sub[stat], errors="coerce").fillna(0.0).to_numpy(float)
    if len(y) < MIN_BANK_ROWS:
        raise ValueError(f"positive control on {pos}|{stat}: {len(y)} rows < {MIN_BANK_ROWS} — "
                         f"refusing (NF1.7 (a))")
    inc_bank = np.repeat(train_bank[pos][None, :], len(sub), axis=0)

    def ceiling_for(yv: np.ndarray) -> float:
        orc = np.repeat(np.quantile(yv, EVAL_LEVELS)[None, :], len(sub), axis=0)
        return score_bank(inc_bank, yv)["crps_q199"] - score_bank(orc, yv)["crps_q199"]

    base, shifted = ceiling_for(y), ceiling_for(y * scale)
    return {"stat": stat, "position": pos, "scale": scale,
            "ceiling_unshifted": round(base, 5), "ceiling_shifted": round(shifted, 5),
            "instrument_sees_the_shift": bool(shifted > base)}
