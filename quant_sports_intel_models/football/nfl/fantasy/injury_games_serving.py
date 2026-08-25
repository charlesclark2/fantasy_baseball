"""injury_games_serving.py — load the PERSISTED NF-INJ3b hurdle and apply it to a board frame.

⭐ MH2.1: **SERVE THE OBJECT THAT WAS VALIDATED, NEVER A RE-DERIVATION.** The bake-off's winning arm
is a fitted GLM hurdle, so "shipping the caps" is not a constants edit — it is shipping a fitted
object. This module LOADS a coefficient table written once by
`run_nf_inj3b_m_serving_artifact.py`; ⛔ it never fits anything, and `load_artifact` REFUSES a table
whose contract does not match the code that would consume it.

⭐ AND IT IS A COEFFICIENT TABLE, NOT A PICKLE — deliberately, following the NCAAF-P2.1 S1-serve
precedent: version-proof, diffable, reviewable in a PR, and immune to the unpinned-sklearn pickle
landmine that has already cost this repo a serving outage.

⭐ THE DESIGN MATRIX IS BUILT BY `nf_inj3_injury_games._design`, THE BAKE-OFF'S OWN FUNCTION — not
re-implemented here. A study that re-derives the logic it scored measures something else (NF-C0e),
and the artifact's recorded `columns` are asserted against it on every load, so a silent reordering
of the design cannot go unnoticed.

⭐ PM BOUNDARY (D2) IS READ FROM `injury_games_policy`, never restated: only `CERTIFIED_STATUSES`
(RES/PUP) get the fitted arm; `INCUMBENT_STATUSES` (SUS/NFI) keep the shipped constants; an
unflagged row is untouched by either.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit

from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG

#: the artifact's home — a COMMITTED path. ⛔ Not `artifacts/`: a serving artifact under a
#: gitignored path is the NF-INFRA1 deploy-ephemeral time bomb (absent from the image, wiped by a
#: deploy), and this one is a few KB of JSON.
ARTIFACT_DIR = Path(__file__).resolve().parent / "served_artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / POLICY.ARTIFACT_FILENAME

#: the design's column contract, in order. `_design` emits intercept + status dummies (RES is the
#: reference level) + the declared covariates.
DESIGN_COLUMNS: tuple[str, ...] = (
    "intercept", "is_PUP", "is_NFI", "is_SUS",
    *(IG.TIMING_FEATURES + IG.BASE_FEATURES),
)
CONTRACT_VERSION = 1

#: ⚠️⚠️ THE PREREQUISITE A FLIP INHERITS, AND IT IS NOT SATISFIED BY THE BOARD BUILD TODAY.
#: The certified arm is a GLM over these covariates. `prior_games` and `is_qb` exist on the board
#: frame; **`onset_carryover`, `weeks_since_last_game` and `log1p_prior_fp` exist NOWHERE in the
#: board build** — they are derived by `run_nf_inj3_injury_games.build_population` from the
#: warehouse, and `season_projection` has never needed them. So serving this arm for real requires
#: wiring that covariate feed into the build; until then `served_injury_games` RAISES rather than
#: quietly falling back to the incumbent, because a silent fallback would serve the incumbent under
#: the fitted arm's stamp (the NF-C0e "declaration outruns its production" class).
REQUIRED_COVARIATES: tuple[str, ...] = IG.TIMING_FEATURES + IG.BASE_FEATURES


def missing_covariates(df: pd.DataFrame) -> list[str]:
    """Which design covariates the frame does NOT carry."""
    return [c for c in REQUIRED_COVARIATES if c not in df.columns]


def design_columns() -> tuple[str, ...]:
    """The column contract, DERIVED from the bake-off module so it cannot drift from `_design`."""
    return ("intercept", "is_PUP", "is_NFI", "is_SUS",
            *(IG.TIMING_FEATURES + IG.BASE_FEATURES))


def load_artifact(path: Path | None = None) -> dict:
    """Load + VALIDATE the persisted hurdle. A malformed or contract-mismatched table RAISES.

    ⭐ NF1.7 (a): a serving loader that degrades to a default on a bad artifact is how a board
    silently serves something nobody validated. Every failure here is loud."""
    p = Path(path) if path is not None else ARTIFACT_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"injury_games_serving: no persisted hurdle at {p}. It is written by "
            f"`run_nf_inj3b_m_serving_artifact.py` and COMMITTED — a missing one is a build defect, "
            f"never a reason to fall back to the incumbent silently.")
    a = json.loads(p.read_text())
    want = list(design_columns())
    if list(a.get("columns", [])) != want:
        raise ValueError(
            f"injury_games_serving: the artifact's design contract does not match this code. "
            f"artifact={a.get('columns')} code={want}. Re-write the artifact from the committed "
            f"code (the D3 provenance rule); ⛔ do not reorder one to match the other.")
    if int(a.get("contract_version", -1)) != CONTRACT_VERSION:
        raise ValueError(f"injury_games_serving: contract_version "
                         f"{a.get('contract_version')} != {CONTRACT_VERSION}")
    if a.get("model_version") != POLICY.MODEL_VERSION:
        raise ValueError(f"injury_games_serving: artifact model_version {a.get('model_version')!r} "
                         f"!= policy {POLICY.MODEL_VERSION!r}")
    if a.get("arm") != POLICY.ARM:
        raise ValueError(f"injury_games_serving: artifact arm {a.get('arm')!r} != policy "
                         f"{POLICY.ARM!r} — the served object is not the certified one")
    for k in ("b_play", "cond_pooled", "n_games", "train_seasons", "n_train_rows", "fit_at"):
        if k not in a:
            raise ValueError(f"injury_games_serving: artifact is missing {k!r}")
    if len(a["b_play"]) != len(want):
        raise ValueError("injury_games_serving: b_play length does not match the design contract")
    if a.get("b_cond") is not None and len(a["b_cond"]) != len(want):
        raise ValueError("injury_games_serving: b_cond length does not match the design contract")
    return a


def predict_games(artifact: dict, df: pd.DataFrame) -> np.ndarray:
    """The persisted hurdle's expected games for every row of `df`.

    ⭐ Byte-for-byte the arithmetic of `nf_inj3_injury_games.predict_hurdle`, evaluated on the
    PERSISTED coefficients instead of a freshly-fitted object. The 1e-9 reproduction guard
    (`test_nf_inj3b_m_serving_artifact.py`) is what makes that equality a MEASUREMENT."""
    n = int(artifact["n_games"])
    x = IG._design(df, IG.TIMING_FEATURES + IG.BASE_FEATURES)
    p = expit(x @ np.asarray(artifact["b_play"], dtype=float))
    if artifact.get("b_cond") is not None:
        cond = float(n) * expit(x @ np.asarray(artifact["b_cond"], dtype=float))
    else:
        cond = np.full(len(df), float(artifact["cond_pooled"]))
    return p * np.clip(cond, 1e-6, float(n))


def served_injury_games(df: pd.DataFrame, *, artifact: dict | None = None,
                        eg: np.ndarray | None = None,
                        blend: float | None = None,
                        feed_supplied: bool | None = None,
                        row_log: dict | None = None) -> tuple[np.ndarray, dict]:
    """The SERVED expected games for a board frame, honouring the PM boundary and the flip.

    `df` needs `proj_status` and the design covariates; `eg` is the model's PRE-cap expected games
    (defaults to `df["proj_games"]`, which is what the incumbent path consumes).

    Returns `(games, provenance)`. Provenance names, per row-class, WHICH path produced the value —
    a served number whose origin is not recoverable is how a partial rollout becomes undebuggable.

    ⭐ `row_log` is an OUT-PARAM (the INC-41 `run_ref` shape, and the same one `project_veterans`
    already uses for the reported-absence decisions): a dict this fills with the PER-ROW evidence
    `{"certified": bool[], "fitted": float[], "incumbent": float[]}`, aligned to `df`. It is an
    out-param rather than a return value because this function returns the games array and every
    existing caller unpacks exactly two values.

    ⚠️⚠️ IT IS FILLED ON **EVERY** PATH, INCLUDING THE ONES THAT SERVE THE INCUMBENT — and that is
    the load-bearing half. The D6 publish guard's whole job is to tell "the fitted arm ran and moved
    these rows" apart from "the policy is ON but this build served the incumbent anyway", and a row
    log that only existed on the happy path would leave the second case indistinguishable from a
    board that was never asked to flip (NF1.7 (a)).
    """
    eg = (np.asarray(df["proj_games"], dtype=float) if eg is None
          else np.asarray(eg, dtype=float))
    status = df["proj_status"].astype(str)
    incumbent = (IG.incumbent_games(status, eg) if blend is None
                 else IG.incumbent_games(status, eg, blend=blend))

    # ⭐ BOTH population boundaries, read from the policy, never restated here: the D2 status
    #    boundary AND the returner exclusion (`RETURNER_BOUNDARY`). A returner's served games
    #    compose this cap and NF-D11's absence prior, so NF-INJ3b never scored them.
    certified = POLICY.certified_rows(df)

    def _log_rows(fitted: np.ndarray | None) -> None:
        """Fill the out-param. `fitted is None` ⇒ NO row on this frame was produced by the fitted
        arm, which the log states as an all-NaN `fitted` column rather than by being absent."""
        if row_log is None:
            return
        row_log.clear()
        row_log.update(
            certified=certified.copy(),
            incumbent=np.asarray(incumbent, dtype=float).copy(),
            fitted=(np.full(len(df), np.nan) if fitted is None
                    else np.where(certified, np.asarray(fitted, dtype=float), np.nan)))

    if not POLICY.serving_enabled():
        _log_rows(None)
        return incumbent, {"path": "incumbent", "reason": "injury_games_policy.SERVING_ENABLED is "
                                                          "False — DEPLOY-HELD",
                           "n_fitted": 0, "n_incumbent": int(len(df)),
                           "model_version": POLICY.INCUMBENT_MODEL_VERSION}

    # ⭐⭐ A CALL SITE THAT SUPPLIED NO COVARIATE FEED IS NOT THE SERVED BOARD, and this is a
    #    MEASURED consequence of the flip, not a hypothetical: `project_veterans` is called by
    #    NF1.5's INTERNAL research-frame assembly (run_nf1_2.assemble_features) as well as by the
    #    served build, and those calls have no feed. Forcing the policy on process-wide therefore
    #    made every one of them demand covariates and the whole build died — discovered by running
    #    it, not by reading it.
    #    ⛔ This is NOT the silent fallback the block below refuses. The distinction is EXPLICIT:
    #       `feed_supplied=False`  → the caller declared it is not serving  → incumbent, RECORDED
    #       `feed_supplied` unset  → the caller intends the fitted arm      → covariates REQUIRED
    #    ⚠️ The residual risk it creates is real and belongs in a PUBLISH-TIME guard, not here: a
    #    served build that forgot its feed would quietly ship the incumbent. Guard the ARTIFACT at
    #    publish (does the board carry the fitted stamp?), the NF-K1 lesson.
    if feed_supplied is False:
        _log_rows(None)
        return incumbent, {
            "path": "incumbent_no_feed",
            "reason": "the policy is ON but this call site supplied no covariate feed, so it is "
                      "not the served board assembly (e.g. NF1.5's internal research frame). "
                      "RECORDED, never silent.",
            "n_fitted": 0, "n_incumbent": int(len(df)),
            "model_version": POLICY.INCUMBENT_MODEL_VERSION}

    missing = missing_covariates(df)
    if missing:
        # ⛔ LOUD, never a silent fallback: serving the incumbent under the fitted arm's stamp is
        #    strictly worse than failing the build (NF1.7 (a) / NF-C0e).
        raise ValueError(
            f"injury_games_serving: the certified hurdle needs {list(REQUIRED_COVARIATES)} and this "
            f"frame is missing {missing}. `onset_carryover`, `weeks_since_last_game` and "
            f"`log1p_prior_fp` are NOT produced by the board build — a real flip must wire that "
            f"covariate feed in first. ⛔ Refusing to fall back to the incumbent while stamping "
            f"{POLICY.MODEL_VERSION!r}.")
    a = artifact if artifact is not None else load_artifact()
    out = incumbent.copy()
    if certified.any():
        # ⭐ predict on the FULL frame then select: `_design` is row-wise, so a subset predicts
        #    identically, and doing it this way keeps the design construction on one code path.
        out = np.where(certified, predict_games(a, df), incumbent)
    _log_rows(out)
    return out, {
        "path": "fitted_hurdle",
        "n_fitted": int(certified.sum()),
        "n_incumbent": int((~certified).sum()),
        "certified_statuses": list(POLICY.CERTIFIED_STATUSES),
        "incumbent_statuses": list(POLICY.INCUMBENT_STATUSES),
        "pm_boundary": POLICY.PM_BOUNDARY,
        "returner_boundary": POLICY.RETURNER_BOUNDARY,
        "model_version": POLICY.MODEL_VERSION,
        "artifact_fit_at": a.get("fit_at"),
    }
