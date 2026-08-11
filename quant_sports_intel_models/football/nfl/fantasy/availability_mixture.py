"""availability_mixture.py — NF-W4: the availability & playing-time mixture (pure).

THE STORY IN ONE PARAGRAPH. Availability is flagged as the LARGEST single error source in the v3
accounting — the mechanism that generates the zero atom in the weekly target. NF-W4 builds a
distributional availability mixture — P(active) × P(plays | active) × snap/usage share, per
player-week — CONSUMING the certified injury family (NF-W2/W2b/W2c/W2d + the wayback capture
store), never re-deriving it. ⭐ AND IT IS GATED TWICE (the NF-W3 two-layer method): Layer A asks
whether either availability target beats its own honest climatology baseline; Layer B asks the
only question that decides whether any of it is worth serving — does injecting the PROJECTED
availability into the assembled player projection beat the INJURY-AWARE champion (the NF-W2b/W2d
certified per-position winners over the NF-W1 `lgbm_hurdle`) on held-out weeks? A component that
wins Layer A and loses Layer B is a RECORDED NULL, not a served model (captured-stays-captured).

⭐ ORACLE-FIRST (NF-W3's transferable discipline): before any arm is judged, the realized-
availability ORACLE — the peeking substitution of the target week's realized played indicator and
snap share — is scored per position, every run. It bounds the whole availability channel from
above, two-sided: a null under a small ceiling is "nothing to find", a null under a large ceiling
is "the models missed it", and those are different findings.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS PRE-REGISTERED (narrative copy: `ablation_results/nf_w4_preregistration.md`)
────────────────────────────────────────────────────────────────────────────────────────────────
  · TARGETS. T1 `played` — the frame label collapsed to {played, not-played} on the modeled
    (ex-bye) population: P(played) IS P(active) × P(plays | active), and the structural
    decomposition is fielded as an ARM (`two_stage`), tested rather than assumed. T2 `snap_share`
    — realized `offense_pct` CONDITIONAL on played, scored ONLY where measured (snap NULL-bearing,
    NF-W0b: an unmeasured share is excluded and COUNTED, ⛔ never fillna(0)).
  · METRIC. CRPS everywhere; ⛔ MAE never selects and never gates (availability is maximally
    zero-heavy — the NF-D11/NF-D14 inversion regime; the all-zero degenerate is SCORED every run).
    T2 + Layer B use the shared 39-level grid identity (`crps_q39`). T1 predictives are two-point
    distributions, so the SAME functional is evaluated in CLOSED FORM (`crps_bernoulli` — the
    dense-grid limit of the identical pinball identity; a 39-level grid would quantize p to 0.025
    and silently tie arms). Declared here, before any score.
  · FOLDS. The NF-W1 axis verbatim (8 expanding half-season blocks 2022H1…2025H2, purge 2 global
    weeks) on the NF-W2d two-era matrix — injury features are nflverse-stamped ≤2024 and wayback-
    capture-stamped in 2025 (as-of-instant observations; observed flag per row).
  · FIELD. 4 structurally different arm classes per target + 2 climatology foils (the best foil
    binds). Anchors are DIAGNOSTIC, never trials (MH2.1 (a)) — excluded from the PBO matrix and
    the DSR trial field.
  · GATES (Layer A, per target): beats_foil ∧ fold_consistency (cv_power clause at 8 ⇒ 6/8) ∧
    PBO < 0.20 over the eligible field ∧ DSR ≥ 0.95 over the declared 4-arm family ∧ BH-FDR
    q = 0.10 (two declared families, the stricter binds) ∧ degenerates lose ∧ permutation behaves
    (fails CLOSED on a None p — NF1.7 (a)) ∧ per-form oracle floors at matched n (NF-D16 (g‴) /
    NF1.9 (f)) ∧ coverage floor. Layer B: the same minus PBO — Layer B fields exactly ONE
    pre-registered contrast, so CSCV has no field to resample and PBO is DECLARED UNDEFINED UP
    FRONT rather than registered and then disclaimed (the NF-W3 mis-specification, not repeated).
  · POWER IS CHECKED IN ADVANCE: at 8 folds the fold clause is attainable (6/8), PBO is evaluable
    for Layer A (6-config eligible field), the sign floor 2⁻⁸ = 0.0039 < the 0.10 BH cutoff, and
    dsr_ceiling(8) ≈ 0.9999 against a 0.95 gate. One clause is STRUCTURALLY NEAR-INACTIVE and
    said so in advance (NF-D20): T1's central-80% interval of a two-point predictive spans {0,1}
    whenever p ∈ (0.10, 0.90), so its coverage floor cannot bind on most rows — recorded as
    inactive-not-passing, never credited.
  · EXPECTED-LIFT SIZING (NF-W2d/W2e): any forward-looking magnitude quotes the 2025
    as-of-capture folds (reported separately), not the legacy stamp era — the injury lever priced
    ~⅓ of its vendor-stamped size at RB on the capture era. And ⛔ no freshness bound is
    tightened here: NF-W2e MEASURED that a ≤1d consumption rule LOSES; the fresh/stale gradient
    is real but the lever is capture cadence, not filtering.

NF-W0 BINDING CONSTRAINTS, honored mechanically:
  (1) allowed_feature_contract only — unknown provenance is a REJECTION
      (`assert_feature_provenance_w4`; the `availability_projection` family is registered in the
      contract as a DERIVED family over certified inputs);
  (2) roster-first certified frame (the NF-W2d matrix IS that frame + families);
  (3) `assert_point_in_time` is INVOKED at the assembly boundary — NF-W4 introduces NO new
      source, so the W2d gate (window records + injury records + rate records, two provenance
      shapes) covers everything consumed; the availability projections are in-fold model outputs
      over already-gated columns;
  (4) snap features NULL-bearing — ⛔ no fillna(0) anywhere; T2's population is played+measured,
      with exclusions counted; model-internal TRAIN-fitted median imputation is the declared
      device for NaN-incapable learners (presence flags retained);
  (5) ⛔ no markets / weather / depth-chart rank / GAME-DAY INACTIVE STATUS as features — the
      last is the leak this story is uniquely exposed to (you PREDICT availability, never read
      it): the roster `status` column and the realized `offense_pct`/`label` exist on the row and
      are targets, so the provenance guard carries an explicit target-leak clause.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: this module promotes nothing and serves
nothing; serving is NF-W8 / NF-C6 Ph2.

Pure module — no lake IO. The runner is `run_nf_w4_availability_bakeoff.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W4"
#: T2 + Layer B share NF-W1's grid reducer; T1 is the SAME functional in closed form (see below).
SELECTION_METRIC = WP.SELECTION_METRIC
T1_SELECTION_METRIC = "crps_bernoulli_exact"
Q_LEVELS = WP.Q_LEVELS
FIT_LEVELS = WP.FIT_LEVELS
TEST_BLOCKS = WP.TEST_BLOCKS                     # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE

#: The two component targets. T1 is the zero-atom generator; T2 is workload conditional on play.
TARGETS: tuple[str, ...] = ("played", "snap_share")

#: 4 structurally different classes per target (§0.5): linear GLM · boosting · the STRUCTURAL
#: mixture decomposition (T1) / parametric Beta overdispersion (T2) · nonparametric neighbourhood.
REAL_ARMS: dict[str, tuple[str, ...]] = {
    "played": ("logit_glm", "lgbm_binary", "two_stage", "knn_rate"),
    "snap_share": ("frac_logit", "beta_mom", "lgbm_quantile", "knn_quantile"),
}
#: Honest climatology baselines (the story's direct-learned foil): the player's OWN lagged
#: availability level, EB-shrunk — optionally adjusted by a deterministic train-fitted injury-
#: designation lookup (`foil_clim_inj`). The BEST foil binds. Never shippable.
FOILS: tuple[str, ...] = ("foil_clim", "foil_clim_inj")
#: Diagnostic anchors — EXCLUDED from the PBO matrix and the DSR trial field (MH2.1 (a)).
BASE_ANCHORS: tuple[str, ...] = (
    "nihilist_zero", "marginal_train", "zero_width", "max_width", "permuted_within",
)

oracle_of = GE.oracle_of              # peeking ceiling of an arm's OWN form (NF-D16 (g‴))
matched_n_of = GE.matched_n_of        # block-sized capacity control (NF1.9 (f))


def anchors_for(target: str) -> tuple[str, ...]:
    arms = REAL_ARMS[target]
    return (*BASE_ANCHORS,
            *(oracle_of(a) for a in arms), *(oracle_of(f) for f in FOILS),
            *(matched_n_of(a) for a in arms))


def all_labels(target: str) -> tuple[str, ...]:
    return (*REAL_ARMS[target], *FOILS, *anchors_for(target))


def eligible_labels(target: str) -> list[str]:
    """The set the selection actually searched — real arms + foils (NF1.8: a deflation statistic
    over a field containing its own anchors measures the anchors)."""
    return [*REAL_ARMS[target], *FOILS]


#: ⭐ TWO pre-registered multiplicity families; the STRICTER reading binds, and the pooled
#: 6-hypothesis correction is also computed (MH2 (a)).
FDR_FAMILIES: dict[str, tuple[str, ...]] = {
    "component": TARGETS,
    "downstream": tuple(WP.POSITIONS),
}

#: EB shrinkage toward the position level, in GAMES of evidence; the lagged-4 window's weight.
EB_KAPPA_AVAIL = 4.0
N_L4_EVIDENCE = 4.0
#: The deterministic injury-designation lookup classes for `foil_clim_inj`. T1 replaces the
#: climatology P(played) with the train empirical P(played | class); T2 multiplies the share
#: point by the train mean-share ratio (playing after Out/Doubtful is too rare to fit a T2
#: multiplier — those classes keep the climatology point, declared).
INJ_GATE_CLASSES_T1: tuple[str, ...] = ("out", "doubtful", "questionable",
                                        "listed_no_designation")
INJ_MULT_CLASSES_T2: tuple[str, ...] = ("questionable", "listed_no_designation")
#: A lookup cell thinner than this falls back to the un-adjusted climatology for that class and
#: the fallback is COUNTED (returned + surfaced in the artifact) — loud, never silent
#: (NF1.7 (a)); a hard raise would be the wrong failure mode for the per-slice expanding-window
#: refits, where early slices are legitimately thin.
MIN_CELL = 200
SHARE_MULT_CLIP = (0.25, 1.50)

#: Layer A features — all columns of the certified NF-W2d matrix; ⭐ CONSUMES the injury family
#: (both eras) rather than re-deriving it. All lagged / as-of admissible; NULL-bearing.
AVAIL_FEATURES: tuple[str, ...] = (
    "game_context__is_home",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "prior_week_box__played_share_l4",
    "prior_week_box__games_s2d",
    "prior_week_box__ppr_l1",
    "prior_week_box__ppr_l4_mean",
    "prior_week_box__ppr_s2d_mean",
    "prior_week_box__targets_l4",
    "prior_week_box__carries_l4",
    "snap_share__l1",
    "snap_share__l4_mean",
    "snap_share__observed_l4",
    "prior_season_priors__games_prior",
    "prior_season_priors__ppg_prior",
    "prior_season_priors__rookie_flag",
    *W2.INJURY_FEATURES,
    *W2B.RATE_FEATURES,
)

#: The Layer-B block injected into the champion (both hurdle legs — P(played) generates the zero
#: atom; the share moves conditional usage). `expected_avail` is ALWAYS recomputed as the product
#: of the (possibly substituted / shuffled) parents so the vector stays coherent.
AVAIL_PROJ_FEATURES: tuple[str, ...] = (
    "availability_projection__p_played",
    "availability_projection__snap_share",
    "availability_projection__expected_avail",
    "availability_projection__share_sd",
)
#: What the realized-availability ORACLE substitutes: the realized played indicator ALWAYS; the
#: realized share only WHERE MEASURED (an unmeasured share keeps the projection — ⛔ never a
#: fabricated 0); the product is recomputed. `share_sd` is NOT substituted — a realized value has
#: no spread, and zeroing it would change the column's meaning rather than its accuracy (NF-W3).
ORACLE_SUBSTITUTED: tuple[str, ...] = (
    "availability_projection__p_played",
    "availability_projection__snap_share",
    "availability_projection__expected_avail",
)

USED_FAMILIES_W4: tuple[str, ...] = W2D.USED_FAMILIES_W2D + ("availability_projection",)

#: Deferred-contract sources that may never appear in a feature NAME (constraint (5)).
BANNED_FEATURE_TOKENS: tuple[str, ...] = (
    "spread_line", "total_line", "vegas", "moneyline",
    "depth_chart", "depth_team", "gameday_inactive", "weather",
)
#: ⛔ THE TARGET-LEAK CLAUSE — unique to this story: availability is PREDICTED, never read. The
#: realized snap column, the frame label and the game-day roster status live on the row as
#: TARGETS/labels; any feature name touching them rejects the build.
TARGET_LEAK_TOKENS: tuple[str, ...] = ("offense_pct", "_t_played", "_t_share")
TARGET_LEAK_EXACT: tuple[str, ...] = ("label", "status")

#: ── Layer B field (declared here; never trimmed or grown after a score — MH2 (a)) ──────────────
#: The foil is the INJURY-AWARE champion: the NF-W2b/W2d certified per-position winners over the
#: NF-W1 `lgbm_hurdle` (imported, never re-typed; guard-pinned to the committed W2d artifact).
INCUMBENT_OF_POSITION: dict[str, str] = dict(W2B.POST_FLIP_SPEC)
LAYER_B_FOIL = "champion_inj"
LAYER_B_REAL_ARMS: tuple[str, ...] = ("champion_avail",)
LAYER_B_ANCHORS: tuple[str, ...] = (
    "champion_avail_foil", "champion_avail_shuffled", "champion_avail_oracle",
)
LAYER_B_ELIGIBLE: tuple[str, ...] = (LAYER_B_FOIL, *LAYER_B_REAL_ARMS)
#: The matched foil-availability arm's forms: the strongest NON-learned availability shape
#: (climatology + deterministic designation lookup), so `champion_avail` beating
#: `champion_avail_foil` attributes the lift to the LEARNED component, not to "availability-shaped
#: context in any form" (NF-D10 matched-pair discipline, NF-W3's `champion_env_foil` analogue).
FOIL_FORMS: dict[str, str] = {"played": "foil_clim_inj", "snap_share": "foil_clim_inj"}
#: The four Layer-B variants of each incumbent form.
VARIANTS: tuple[str, ...] = ("avail", "avail_foil", "avail_shuffled", "avail_oracle")

_SEED = 20260810

# Shared verdict / reporting helpers — IMPORTED, never re-typed (NF-W2d discipline).
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
assert_finite_predictive = GE.assert_finite_predictive
flag_unsafe_field_shrink = GE.flag_unsafe_field_shrink
gate_sensitivity = GE.gate_sensitivity
#: Layer A gate + hand classification: check NAMES match GE's exactly, so the shipped composers
#: are reused wholesale (a re-typed clause is a clause that can drift).
compose_gate = GE.compose_gate
hand_classify_refusal = GE.hand_classify_refusal
classify_layer_b = GE.classify_layer_b
matched_n_train = GE.matched_n_train


# ── Provenance (fail-closed; five independently RED-provable clauses) ───────────────────────────
def assert_feature_provenance_w4(feature_columns) -> None:
    """Reject any feature whose provenance is not checkable against the NF-W0 contract.

    Five clauses, each independently RED-provable (NF-D17 — one isolating fixture per clause):
      1. ⛔ no TARGET leak — the realized snap column, the frame label and the roster status are
         what this story PREDICTS; their appearance in a feature name rejects the build. Runs
         FIRST: the exact names carry no family separator, so behind the prefix clause this
         check would be unreachable for them (a dead clause — the NF-D17 vacuity shape);
      2. every column is `<family>__<detail>` with family ∈ USED_FAMILIES_W4;
      3. no LEAKY token (WF.LEAKY_COLUMNS, token-boundary rule);
      4. no participation-ERA token (the 2023 provider switch — NF-W0c);
      5. no DEFERRED-contract source token (markets / weather / depth chart / game-day inactive).
    Then the certified NF-W0 clause runs on the family names themselves.
    """
    cols = list(feature_columns)
    # ⭐ the target-leak clause runs FIRST: the exact names (`label`, `status`) carry no family
    # separator, so behind the prefix clause this check would be UNREACHABLE for them — a dead
    # clause is the NF-D17 vacuity shape, and the ordering is itself guard-tested.
    target_leak = [c for c in cols
                   if c in TARGET_LEAK_EXACT or any(tok in c for tok in TARGET_LEAK_TOKENS)]
    if target_leak:
        raise WF.LeakageError(
            f"target-leak features reject this build: {sorted(target_leak)} — availability is "
            f"PREDICTED, never read: the realized snap column, the frame label and the game-day "
            f"roster status are labels/targets on the row, not features"
        )
    bad = [c for c in cols if "__" not in c or c.split("__", 1)[0] not in USED_FAMILIES_W4]
    if bad:
        raise WF.LeakageError(
            f"features with unknown provenance reject the build: {sorted(bad)} — every NF-W4 "
            f"feature must be named '<family>__<detail>' with family in {USED_FAMILIES_W4}"
        )
    leaky = [c for c in cols
             if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_")
                    for tok in WF.LEAKY_COLUMNS)]
    if leaky:
        raise WF.LeakageError(f"leaky feature columns reject the build: {sorted(leaky)}")
    era = [c for c in cols if any(tok in c for tok in WP.ERA_FORBIDDEN_TOKENS)]
    if era:
        raise WF.LeakageError(
            f"participation-era features reject this build: {sorted(era)} — the 2023 provider "
            f"switch (NF-W0c) forbids pooling pressure/coverage/route legs without an era split"
        )
    banned = [c for c in cols if any(tok in c for tok in BANNED_FEATURE_TOKENS)]
    if banned:
        raise WF.LeakageError(
            f"deferred-contract features reject this build: {sorted(banned)} — markets, weather, "
            f"depth-chart rank and game-day inactive status are NF-W0 DEFERRED, not allowed"
        )
    WF.assert_no_leakage(pd.DataFrame(),
                         feature_columns=sorted({c.split("__", 1)[0] for c in cols}),
                         projection_week=0)


# ── Targets ─────────────────────────────────────────────────────────────────────────────────────
def attach_availability_targets(feat: pd.DataFrame) -> pd.DataFrame:
    """Attach the two availability targets to the (ex-bye) W2d matrix.

    `_t_played` collapses the frame label to the played indicator (byes never reach this frame —
    they are excluded by the assembly boundary, and a bye is a deterministic zero knowable at
    schedule release). `_t_share` is the realized `offense_pct`, kept NaN where unmeasured —
    ⛔ never fillna(0): an unmeasured share is unknown, not zero (NF-W0b).
    """
    f = feat.copy()
    if (f["label"] == WF.LABEL_BYE).any():
        raise ValueError("bye rows reached the availability targets — the assembly boundary "
                         "should have excluded them (a bye is a deterministic zero, not an "
                         "availability outcome)")
    f["_t_played"] = (f["label"] == WF.LABEL_PLAYED).astype(float)
    f["_t_share"] = pd.to_numeric(f["offense_pct"], errors="coerce").clip(0.0, 1.0)
    return f


def t2_mask(df: pd.DataFrame) -> np.ndarray:
    """The T2 population: played AND measured. The exclusion (played but unmeasured) is a COUNTED
    population fact, never an imputation."""
    return ((df["_t_played"].to_numpy(dtype=float) == 1.0)
            & df["_t_share"].notna().to_numpy())


def t2_exclusion_counts(df: pd.DataFrame) -> dict:
    played = df["_t_played"].to_numpy(dtype=float) == 1.0
    measured = df["_t_share"].notna().to_numpy()
    return {
        "n_rows": int(len(df)),
        "n_played": int(played.sum()),
        "n_scored": int((played & measured).sum()),
        "n_played_unmeasured_excluded": int((played & ~measured).sum()),
    }


# ── T1 scoring: the SAME CRPS functional, evaluated in closed form ──────────────────────────────
def assert_finite_p(p: np.ndarray, label: str) -> np.ndarray:
    """A probability vector with NaN cells is the silent-partial-failure class (NF-W3's reducer
    rule, applied to the T1 representation): refuse it, never nan-mean past it."""
    p = np.asarray(p, dtype=float)
    bad = int((~np.isfinite(p)).sum())
    if bad:
        raise ValueError(
            f"arm `{label}` emitted {bad} non-finite P(played) cells of {p.size} — a NaN "
            f"predictive is scored on a silently different population by any nan-aware mean"
        )
    return np.clip(p, 1e-6, 1 - 1e-6)


def crps_bernoulli(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Exact CRPS of a Bernoulli predictive for a {0,1} outcome — the dense-grid limit of the
    pinball identity `crps_q39` uses everywhere else (a 39-level grid would quantize p to 0.025
    and silently tie arms). Algebraically (y − p)²."""
    return (np.asarray(y, dtype=float) - np.asarray(p, dtype=float)) ** 2


def crps_point(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Exact CRPS of a point-mass predictive: |y − x| (the zero_width degenerate's own form)."""
    return np.abs(np.asarray(y, dtype=float) - np.asarray(x, dtype=float))


#: Exact CRPS of Uniform[0,1] for a {0,1} outcome (the max_width degenerate's own form).
CRPS_UNIFORM01 = 1.0 / 3.0


def t1_interval_coverage(p: np.ndarray, y: np.ndarray) -> dict:
    """Central-80% coverage of the two-point predictive, in the WP.interval_coverage shape.

    ⚠️ STRUCTURALLY NEAR-INACTIVE (declared in advance, NF-D20): for p ∈ (0.10, 0.90) the band is
    the whole {0,1} support, so coverage ≈ 1 and the floor cannot bind — this clause is recorded
    as inactive on T1, never credited as a pass."""
    p = np.asarray(p, dtype=float)
    yv = np.asarray(y, dtype=float)
    q10 = (0.10 > (1.0 - p)).astype(float)
    q90 = (0.90 > (1.0 - p)).astype(float)
    inside = (yv >= q10) & (yv <= q90)
    n = len(yv)
    cov = float(inside.mean()) if n else float("nan")
    nominal = 0.80
    se = float(np.sqrt(nominal * (1 - nominal) / n)) if n else float("nan")
    return {"coverage": cov, "n": n, "nominal": nominal, "binomial_se": se,
            "blocking_shortfall": bool(n and (nominal - cov) > COVERAGE_BLOCK_SE * se),
            "structurally_inactive": True}


# ── Shared fitting plumbing (train-fitted medians; a device inside an arm, never a data edit) ───
def _X(df: pd.DataFrame, features, medians: dict[str, float] | None = None) -> np.ndarray:
    Xcols = []
    for c in features:
        v = pd.to_numeric(df[c], errors="coerce")
        if medians is not None:
            v = v.fillna(medians[c])
        Xcols.append(v.to_numpy(dtype=float))
    Xcols.append(WP._pos_codes(df))
    return np.column_stack(Xcols)


def train_medians(train: pd.DataFrame, features) -> dict[str, float]:
    out = {}
    for c in features:
        m = pd.to_numeric(train[c], errors="coerce").median()
        out[c] = float(m) if np.isfinite(m) else 0.0
    return out


# ── T1 arms (each returns a P(played) vector; the closed-form reducer scores it) ────────────────
def fit_t1_logit(train, test, features, *, y_train=None) -> np.ndarray:
    """Linear class: L2 logistic GLM on standardized, median-imputed features."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = (train["_t_played"].to_numpy(dtype=float) if y_train is None
         else np.asarray(y_train, dtype=float))
    m = LogisticRegression(C=1.0, max_iter=2000, random_state=_SEED)
    m.fit(sc.transform(_X(train, features, med)), (y == 1.0).astype(int))
    return m.predict_proba(sc.transform(_X(test, features, med)))[:, 1]


def _lgbm_clf():
    import lightgbm as lgb
    return lgb.LGBMClassifier(
        n_estimators=250, learning_rate=0.06, num_leaves=63, min_child_samples=40,
        subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
        random_state=_SEED, verbose=-1, n_jobs=-1,
    )


def fit_t1_lgbm(train, test, features, *, y_train=None) -> np.ndarray:
    """Boosting class: GBM classifier (NaN passed through natively)."""
    y = (train["_t_played"].to_numpy(dtype=float) if y_train is None
         else np.asarray(y_train, dtype=float))
    m = _lgbm_clf()
    m.fit(_X(train, features), (y == 1.0).astype(int))
    return m.predict_proba(_X(test, features))[:, 1]


def fit_t1_two_stage(train, test, features, *, y_train=None) -> np.ndarray:
    """⭐ The story's named STRUCTURAL decomposition, fielded as a candidate rather than assumed:
    P(played) = P(active) × P(plays | active), where active = not game-day inactive (the frame
    label's own decomposition of the zero atom). Two GBM classifiers composed."""
    if y_train is not None:
        raise ValueError("two_stage decomposes the frame label itself; a y_train override would "
                         "sever the stages from the labels they decompose — the permutation "
                         "anchor is pre-registered on the plain boosting class instead")
    active_tr = (train["label"] != WF.LABEL_INACTIVE).to_numpy()
    m_active = _lgbm_clf()
    m_active.fit(_X(train, features), active_tr.astype(int))
    p_active = m_active.predict_proba(_X(test, features))[:, 1]

    dressed = train.loc[active_tr]
    plays_tr = (dressed["label"] == WF.LABEL_PLAYED).to_numpy()
    m_plays = _lgbm_clf()
    m_plays.fit(_X(dressed, features), plays_tr.astype(int))
    p_plays = m_plays.predict_proba(_X(test, features))[:, 1]
    return p_active * p_plays


def fit_t1_knn(train, test, features, *, y_train=None, k: int = 300) -> np.ndarray:
    """Nonparametric neighbourhood: per-position kNN played-rate."""
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    y = (train["_t_played"].to_numpy(dtype=float) if y_train is None
         else np.asarray(y_train, dtype=float))
    out = np.full(len(test), np.nan)
    for pos in WP.POSITIONS:
        tr_sel = (train["position"] == pos).to_numpy()
        te_sel = (test["position"] == pos).to_numpy()
        if not te_sel.any():
            continue
        if not tr_sel.any():
            out[te_sel] = float((y == 1.0).mean())
            continue
        Xtr = _X(train.loc[tr_sel], features, med)
        Xte = _X(test.loc[te_sel], features, med)
        sc = StandardScaler().fit(Xtr)
        kk = int(min(k, max(2, tr_sel.sum() - 1)))
        nn = NearestNeighbors(n_neighbors=kk).fit(sc.transform(Xtr))
        _, idx = nn.kneighbors(sc.transform(Xte))
        out[te_sel] = (y[tr_sel][idx] == 1.0).mean(axis=1)
    return out


T1_PROB_FITTERS = {
    "logit_glm": fit_t1_logit, "lgbm_binary": fit_t1_lgbm,
    "two_stage": fit_t1_two_stage, "knn_rate": fit_t1_knn,
}


# ── T2 arms (each returns an [n, 39] share-quantile matrix on the T2 population) ────────────────
def _clip01(q: np.ndarray) -> np.ndarray:
    return np.clip(q, 0.0, 1.0)


def _frac_logit_mean(train, test, features, *, y_train=None):
    """Fractional logistic GLM mean (statsmodels Binomial quasi-likelihood on a [0,1] target)."""
    import statsmodels.api as sm
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    Xtr = sm.add_constant(sc.transform(_X(train, features, med)), has_constant="add")
    Xte = sm.add_constant(sc.transform(_X(test, features, med)), has_constant="add")
    y = (train["_t_share"].to_numpy(dtype=float) if y_train is None
         else np.asarray(y_train, dtype=float))
    res = sm.GLM(np.clip(y, 0.0, 1.0), Xtr, family=sm.families.Binomial()).fit(maxiter=200)
    return (np.clip(res.predict(Xtr), 1e-6, 1 - 1e-6),
            np.clip(res.predict(Xte), 1e-6, 1 - 1e-6), y)


def fit_t2_frac_logit(train, test, features, *, y_train=None) -> np.ndarray:
    """Linear class: fractional-logit mean + TRAIN empirical residual bank, clipped to [0,1]."""
    p_tr, p_te, y = _frac_logit_mean(train, test, features, y_train=y_train)
    r = np.clip(y, 0.0, 1.0) - p_tr
    bank = np.quantile(r[np.isfinite(r)], Q_LEVELS)
    return _clip01(p_te[:, None] + bank[None, :])


def fit_t2_beta_mom(train, test, features, *, y_train=None) -> np.ndarray:
    """Parametric class: the same mean under a Beta predictive with MoM concentration — the
    overdispersion hypothesis tested, not assumed (φ → large ⇒ near-degenerate)."""
    from scipy.stats import beta as beta_dist
    p_tr, p_te, y = _frac_logit_mean(train, test, features, y_train=y_train)
    resid_var = float(np.nanmean((np.clip(y, 0.0, 1.0) - p_tr) ** 2))
    mean_pv = float(np.nanmean(p_tr * (1 - p_tr)))
    # Var = p(1−p)/(1+φ) ⇒ φ = mean(p(1−p))/resid_var − 1; no excess ⇒ φ large ⇒ sharp.
    phi = (mean_pv / resid_var - 1.0) if resid_var > 1e-12 else 1e6
    phi = float(np.clip(phi, 1.0, 1e6))
    a, b = phi * p_te, phi * (1.0 - p_te)
    return _clip01(beta_dist.ppf(Q_LEVELS[None, :], a[:, None], b[:, None]))


def fit_t2_lgbm_quantile(train, test, features, *, y_train=None) -> np.ndarray:
    """Boosting class: 9-knot quantile bank interpolated onto the 39 levels."""
    Xtr = _X(train, features)
    Xte = _X(test, features)
    y = (train["_t_share"].to_numpy(dtype=float) if y_train is None
         else np.asarray(y_train, dtype=float))
    ok = np.isfinite(y)
    knots = np.empty((len(test), len(FIT_LEVELS)))
    for j, alpha in enumerate(FIT_LEVELS):
        m = WP._lgbm({"objective": "quantile", "alpha": alpha, "n_estimators": 200,
                      "num_leaves": 31, "min_child_samples": 30})
        m.fit(Xtr[ok], y[ok])
        knots[:, j] = m.predict(Xte)
    return _clip01(WP.interp_to_levels(np.array(FIT_LEVELS), knots))


def fit_t2_knn_quantile(train, test, features, *, y_train=None, k: int = 200) -> np.ndarray:
    """Nonparametric neighbourhood: per-position empirical quantiles of neighbour shares."""
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    y = (train["_t_share"].to_numpy(dtype=float) if y_train is None
         else np.asarray(y_train, dtype=float))
    out = np.full((len(test), len(Q_LEVELS)), np.nan)
    ok = np.isfinite(y)
    for pos in WP.POSITIONS:
        tr_sel = (train["position"] == pos).to_numpy() & ok
        te_sel = (test["position"] == pos).to_numpy()
        if not te_sel.any():
            continue
        if not tr_sel.any():
            out[te_sel] = np.quantile(y[ok], Q_LEVELS)[None, :]
            continue
        Xtr = _X(train.loc[tr_sel], features, med)
        Xte = _X(test.loc[te_sel], features, med)
        sc = StandardScaler().fit(Xtr)
        kk = int(min(k, max(2, tr_sel.sum() - 1)))
        nn = NearestNeighbors(n_neighbors=kk).fit(sc.transform(Xtr))
        _, idx = nn.kneighbors(sc.transform(Xte))
        out[te_sel] = np.quantile(y[tr_sel][idx], Q_LEVELS, axis=1).T
    return _clip01(out)


T2_QMAT_FITTERS = {
    "frac_logit": fit_t2_frac_logit, "beta_mom": fit_t2_beta_mom,
    "lgbm_quantile": fit_t2_lgbm_quantile, "knn_quantile": fit_t2_knn_quantile,
}


# ── The injury-designation class of a row (NaN-safe: unobserved rows classify to None) ──────────
def inj_class(df: pd.DataFrame) -> pd.Series:
    """out / doubtful / questionable / listed_no_designation / None. Reads the admissible
    engineered family only — NaN (unobserved) rows classify to None, never to healthy."""
    listed = pd.to_numeric(df["injury_report__listed"], errors="coerce") == 1.0
    out_ = pd.to_numeric(df["injury_report__status_out"], errors="coerce") == 1.0
    dbt = pd.to_numeric(df["injury_report__status_doubtful"], errors="coerce") == 1.0
    qst = pd.to_numeric(df["injury_report__status_questionable"], errors="coerce") == 1.0
    cls = pd.Series([None] * len(df), index=df.index, dtype="object")
    cls[listed] = "listed_no_designation"
    cls[listed & qst] = "questionable"
    cls[listed & dbt] = "doubtful"
    cls[listed & out_] = "out"
    return cls


# ── Foils (the honest climatology nulls) ────────────────────────────────────────────────────────
def train_pos_played_rate(train: pd.DataFrame) -> dict[str, float]:
    out = {}
    for pos in WP.POSITIONS:
        sel = train["position"] == pos
        out[pos] = float(train.loc[sel, "_t_played"].mean()) if sel.any() else float(
            train["_t_played"].mean())
    return out


def foil_point_t1(df: pd.DataFrame, pos_rate: dict[str, float]) -> np.ndarray:
    """Climatology P(played): the player's lagged-4 played share, EB-shrunk toward the position
    rate. A missing window (first appearance) is honestly the position rate — never 0."""
    l4 = pd.to_numeric(df["prior_week_box__played_share_l4"], errors="coerce")
    base = df["position"].map(pos_rate).astype(float)
    p = np.where(
        l4.notna(),
        (EB_KAPPA_AVAIL * base + N_L4_EVIDENCE * l4.fillna(0.0)) / (EB_KAPPA_AVAIL + N_L4_EVIDENCE),
        base,
    )
    return np.clip(p, 1e-6, 1 - 1e-6)


def fit_class_p_t1(train: pd.DataFrame) -> tuple[dict[str, float], list[str]]:
    """Train empirical P(played | designation class) over OBSERVED listed rows. A cell thinner
    than MIN_CELL falls back to the climatology for that class and is COUNTED (returned), never
    silent (NF1.7 (a))."""
    observed = pd.to_numeric(train["injury_report__observed"], errors="coerce") == 1.0
    cls = inj_class(train)
    out: dict[str, float] = {}
    fallbacks: list[str] = []
    for c in INJ_GATE_CLASSES_T1:
        sel = observed & (cls == c)
        n = int(sel.sum())
        if n < MIN_CELL:
            fallbacks.append(f"{c} (n={n})")
            continue
        out[c] = float(train.loc[sel, "_t_played"].mean())
    return out, fallbacks


def foil_point_t1_inj(df: pd.DataFrame, pos_rate: dict[str, float],
                      class_p: dict[str, float]) -> np.ndarray:
    """Climatology + the deterministic designation lookup: an admissibly-designated row's
    P(played) is the train empirical rate for its class; everything else is climatology."""
    p = foil_point_t1(df, pos_rate)
    cls = inj_class(df)
    for c, pc in class_p.items():
        sel = (cls == c).to_numpy()
        if sel.any():
            p = np.where(sel, np.clip(pc, 1e-6, 1 - 1e-6), p)
    return p


def train_pos_share(train_t2: pd.DataFrame) -> dict[str, float]:
    out = {}
    pooled = float(pd.to_numeric(train_t2["_t_share"], errors="coerce").mean())
    for pos in WP.POSITIONS:
        sel = train_t2["position"] == pos
        v = float(pd.to_numeric(train_t2.loc[sel, "_t_share"], errors="coerce").mean()) if sel.any() else pooled
        out[pos] = v if np.isfinite(v) else pooled
    return out


def foil_point_t2(df: pd.DataFrame, pos_share: dict[str, float]) -> np.ndarray:
    """Climatology share: the player's lagged snap-share mean, EB-shrunk toward the position
    level. NULL-bearing input: a missing window is the position level, never 0 (NF-W0b)."""
    l4 = pd.to_numeric(df["snap_share__l4_mean"], errors="coerce")
    base = df["position"].map(pos_share).astype(float)
    pt = np.where(
        l4.notna(),
        (EB_KAPPA_AVAIL * base + N_L4_EVIDENCE * l4.fillna(0.0)) / (EB_KAPPA_AVAIL + N_L4_EVIDENCE),
        base,
    )
    return np.clip(pt, 0.0, 1.0)


def fit_class_mult_t2(train_t2: pd.DataFrame) -> tuple[dict[str, float], list[str]]:
    """Train mean-share multiplier per designation class (share|class ÷ share|unlisted), clipped.
    Thin cells fall back to 1.0 and are COUNTED. Out/Doubtful are pre-registered OUT of this
    device — playing after those designations is too rare to fit."""
    observed = pd.to_numeric(train_t2["injury_report__observed"], errors="coerce") == 1.0
    cls = inj_class(train_t2)
    share = pd.to_numeric(train_t2["_t_share"], errors="coerce")
    unl = observed & cls.isna()
    base = float(share[unl].mean()) if int(unl.sum()) >= MIN_CELL else float(share.mean())
    out: dict[str, float] = {}
    fallbacks: list[str] = []
    for c in INJ_MULT_CLASSES_T2:
        sel = observed & (cls == c)
        n = int(sel.sum())
        if n < MIN_CELL or not np.isfinite(base) or base <= 0:
            fallbacks.append(f"{c} (n={n})")
            continue
        out[c] = float(np.clip(float(share[sel].mean()) / base, *SHARE_MULT_CLIP))
    return out, fallbacks


def foil_point_t2_inj(df: pd.DataFrame, pos_share: dict[str, float],
                      class_mult: dict[str, float]) -> np.ndarray:
    pt = foil_point_t2(df, pos_share)
    cls = inj_class(df)
    for c, m in class_mult.items():
        sel = (cls == c).to_numpy()
        if sel.any():
            pt = np.where(sel, np.clip(pt * m, 0.0, 1.0), pt)
    return pt


def residual_bank_t2(y: np.ndarray, point: np.ndarray) -> np.ndarray:
    r = np.asarray(y, float) - np.asarray(point, float)
    r = r[np.isfinite(r)]
    return np.quantile(r, Q_LEVELS)


def apply_bank_t2(point: np.ndarray, bank: np.ndarray) -> np.ndarray:
    return _clip01(np.asarray(point, float)[:, None] + bank[None, :])


# ── Permutation (within position × global week; destroys player identity, keeps marginals) ──────
def permute_within_pos_week(df: pd.DataFrame, values: np.ndarray, seed: int = _SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y = np.asarray(values, dtype=float).copy()
    keys = df["position"].astype(str) + "|" + df["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(df)), index=keys).groupby(level=0):
        pos = idx.to_numpy()
        if len(pos) > 1:
            y[pos] = rng.permutation(y[pos])
    return y


# ── Layer A → Layer B: the availability projections (a PROJECTION on both fold sides) ───────────
def _point_and_sd(qmat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    q = np.sort(np.asarray(qmat, dtype=float), axis=1)
    lo = q[:, int(np.argmin(np.abs(Q_LEVELS - 0.10)))]
    hi = q[:, int(np.argmin(np.abs(Q_LEVELS - 0.90)))]
    return q.mean(axis=1), (hi - lo) / (2 * 1.2815515655446004)


def t1_form_prob(form: str, fit_on: pd.DataFrame, rows: pd.DataFrame) -> np.ndarray:
    """P(played) under any T1 form — real arm or foil — fit on `fit_on`, predicted for `rows`."""
    if form == "foil_clim":
        return foil_point_t1(rows, train_pos_played_rate(fit_on))
    if form == "foil_clim_inj":
        pos_rate = train_pos_played_rate(fit_on)
        class_p, _ = fit_class_p_t1(fit_on)
        return foil_point_t1_inj(rows, pos_rate, class_p)
    return T1_PROB_FITTERS[form](fit_on, rows, list(AVAIL_FEATURES))


def t2_form_predict(form: str, fit_on: pd.DataFrame, rows: pd.DataFrame
                    ) -> tuple[np.ndarray, np.ndarray]:
    """(share point, share sd) under any T2 form, fit on `fit_on`'s T2 population."""
    tr = fit_on.loc[t2_mask(fit_on)]
    if form == "foil_clim":
        pos_share = train_pos_share(tr)
        pt = foil_point_t2(rows, pos_share)
        bank = residual_bank_t2(tr["_t_share"].to_numpy(float), foil_point_t2(tr, pos_share))
        return _point_and_sd(apply_bank_t2(pt, bank))
    if form == "foil_clim_inj":
        pos_share = train_pos_share(tr)
        mult, _ = fit_class_mult_t2(tr)
        pt = foil_point_t2_inj(rows, pos_share, mult)
        bank = residual_bank_t2(tr["_t_share"].to_numpy(float),
                                foil_point_t2_inj(tr, pos_share, mult))
        return _point_and_sd(apply_bank_t2(pt, bank))
    return _point_and_sd(T2_QMAT_FITTERS[form](tr, rows, list(AVAIL_FEATURES)))


def avail_projection_frame(feat: pd.DataFrame, fold: WP.Fold, forms: dict[str, str]
                           ) -> pd.DataFrame:
    """(p_played, snap_share, share_sd) for EVERY row in the fold's scope, index-aligned to feat.

    ⚠️ A projected feature must be a PROJECTION on both sides of the fold, or the player model
    learns to trust a value serving will never have (NF-W3). TEST rows use the form fit on the
    whole fold-train; TRAIN rows use an EXPANDING WINDOW inside the training span (season s
    predicted by a fit on seasons < s, with a two-season burn-in minimum whose in-sample optimism
    biases the gate AGAINST the new arm — declared, in that direction, before the run).
    """
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    seasons = sorted(train["season"].unique())
    pieces: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for i, s in enumerate(seasons):
        rows = train[train["season"] == s]
        fit_on = train[train["season"] < s] if i >= 2 else train[train["season"].isin(seasons[:2])]
        pieces.append((rows, fit_on))
    pieces.append((test, train))

    idx_parts, p_parts, pt_parts, sd_parts = [], [], [], []
    for rows, fit_on in pieces:
        if not len(rows):
            continue
        p = assert_finite_p(t1_form_prob(forms["played"], fit_on, rows),
                            f"proj_played[{forms['played']}]")
        pt, sd = t2_form_predict(forms["snap_share"], fit_on, rows)
        idx_parts.append(rows.index.to_numpy())
        p_parts.append(p)
        pt_parts.append(np.clip(pt, 0.0, 1.0))
        sd_parts.append(np.clip(sd, 0.0, None))
    idx = np.concatenate(idx_parts)
    return pd.DataFrame({
        "p_played": np.concatenate(p_parts),
        "snap_share": np.concatenate(pt_parts),
        "share_sd": np.concatenate(sd_parts),
    }, index=idx)


def attach_avail_features(feat: pd.DataFrame, proj: pd.DataFrame, *,
                          realized: bool = False, shuffle_seed: int | None = None
                          ) -> pd.DataFrame:
    """Attach the availability block under the pre-registered AVAIL_PROJ_FEATURES names.

    `realized=True` is the ORACLE: the realized played indicator ALWAYS, the realized share only
    WHERE MEASURED (an unmeasured share keeps the projection — never a fabricated value).
    `shuffle_seed` permutes the block jointly across PLAYERS within (position, global week) —
    the same values, the wrong players. `expected_avail` is recomputed LAST from the (possibly
    substituted / shuffled) parents, so the vector stays coherent under every variant."""
    out = feat.copy()
    for c in AVAIL_PROJ_FEATURES:
        out[c] = np.nan
    idx = proj.index
    p = proj["p_played"].to_numpy(dtype=float)
    share = proj["snap_share"].to_numpy(dtype=float)
    sd = proj["share_sd"].to_numpy(dtype=float)

    if realized:
        p = out.loc[idx, "_t_played"].to_numpy(dtype=float)
        realized_share = out.loc[idx, "_t_share"].to_numpy(dtype=float)
        share = np.where(np.isfinite(realized_share), realized_share, share)
    if shuffle_seed is not None:
        sub = out.loc[idx]
        stacked = np.column_stack([p, share, sd])
        rng = np.random.default_rng(shuffle_seed)
        keys = sub["position"].astype(str) + "|" + sub["gw"].astype(str)
        order = np.arange(len(sub))
        for _, grp in pd.Series(order, index=keys).groupby(level=0):
            posn = grp.to_numpy()
            if len(posn) > 1:
                stacked[posn] = stacked[rng.permutation(posn)]
        p, share, sd = stacked[:, 0], stacked[:, 1], stacked[:, 2]

    out.loc[idx, "availability_projection__p_played"] = p
    out.loc[idx, "availability_projection__snap_share"] = share
    out.loc[idx, "availability_projection__share_sd"] = sd
    out.loc[idx, "availability_projection__expected_avail"] = p * share
    return out


def assert_avail_block_attached(frames: dict[str, pd.DataFrame], scope: np.ndarray,
                                fold_label: str) -> dict[str, float]:
    """⭐ NON-VACUITY: an all-NaN availability block would make every Layer-B comparison a
    comparison of the champion against itself — the whole gate would pass on nothing (NF-C0e
    wired-≠-invoked, NF1.7 (a)). Assert the block actually landed on the fold's scope."""
    coverage = {
        label: float(frame.loc[scope, list(AVAIL_PROJ_FEATURES)].notna().all(axis=1).mean())
        for label, frame in frames.items()
    }
    if min(coverage.values()) < 0.99:
        raise ValueError(
            f"the NF-W4 availability block did not attach to the player frame: coverage "
            f"{coverage} on fold {fold_label} — a NaN block makes champion_avail identical to "
            f"the champion and the Layer-B gate would pass on nothing"
        )
    return coverage


# ── Layer B gate (⭐ NO PBO clause — declared UNDEFINED up front, the NF-W3 lesson applied) ──────
LAYER_B_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_champion", "fold_consistency", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)
LAYER_B_ANCHOR_CHECKS: tuple[str, ...] = ("permutation_behaves", "oracle_floor_respected")


def layer_b_gate_w4(sel: dict, fdr_pass: bool) -> dict:
    """Layer B's gate. PBO is deliberately ABSENT: the field is one pre-registered contrast, so
    CSCV has no field to resample — NF-W3 registered `pbo_ok` anyway and then had to disclaim it
    as a mis-specification; NF-W4 declares it UNDEFINED before the run instead."""
    checks = {
        "beats_champion": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_shuffled"]
                                    and sel["anchors"]["shuffled_lift_not_significant"]),
        "oracle_floor_respected": bool(sel["anchors"]["respects_realized_oracle"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}


def hand_classify_layer_b_refusal(checks: dict) -> dict | None:
    """CONSTRAINT_REFUSED for Layer B (the NF-D18/MH2.7 classify_null gap): every statistical
    clause green, the null resting only on anchor clauses ⇒ more data makes it fail HARDER and
    ⛔ no sample-size re-test trigger may be published."""
    stat_fail = [c for c in LAYER_B_STATISTICAL_CHECKS if not checks.get(c, True)]
    anchor_fail = [c for c in LAYER_B_ANCHOR_CHECKS if not checks.get(c, True)]
    if stat_fail or not anchor_fail:
        return None
    return {
        "state": "CONSTRAINT_REFUSED",
        "reason": ("hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical "
                   f"clause passed and the null rests entirely on anchor clauses {anchor_fail}. "
                   f"More data cannot change this verdict."),
        "retest_trigger": None,
        "failing_anchor_checks": anchor_fail,
    }
