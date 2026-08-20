"""run_nf_w8_0c_qb_body.py — NF-W8-0c §0.5: the QB BODY-level comparison and the declared body
re-level field.

Everything decidable in advance is a CONSTANT in `fp_qb_body.py`; this runner READS it (NF-D16).
The narrative pre-registration is committed at `ablation_results/nf_w8_0c_preregistration.md`
BEFORE any scoring run.

⭐ ONE CODE PATH FOR EVERY CERTIFIED GENERATOR. The four consumed generators are built by
`run_nf_w8_0_cross_position.run_position` — the predecessors' own function, driven through
NF-W8-0b's DECIDED `point_reader` — so the reproduction pins cannot drift and the non-QB side is
byte-identical to NF-W8-0b's record. This story ADDS, at QB only, a set of re-assembled arms whose
incumbent is proven EXACTLY equal (CRPS and ranking point, 0.0) to that certified path before any
arm is scored.

PIPELINE (target `league_fantasy_points`, gate league `full_ppr`, NF-W7c's 8-fold axis verbatim):
  · per fold: the four consumed generators (pins) + `direct_points` at QB (family C);
  · family A — the EXACT decomposition of the QB level: the mechanism identity
    `mean(point) − mean(y) = READ + Σ_i w_i·(legmean_i − realized_i)` and the 10-band localisation
    of the `zm_floor`-vs-`direct_points` grid-mean gap. Both deterministic, both ASSERTED as
    identities against the artifact rather than restated in prose (NF-W8-0b §12.5(e));
  · family B — 4 declared real arms (`cond_shift` / `cond_scale` / `avail_relevel` / `leg_scale`)
    fitted on PRIOR folds' OOF rows ONLY, plus one peeking oracle PER FORM (NF-D16 (g‴)), the
    over-corrected magnitude anchor, the permuted-assignment anchor and two degenerates;
  · family C — the architecture comparison against `direct_points` on PIT / CRPS / level;
  · family A′ — the 6 pairwise cross-position contrasts re-tested under the winner, through the
    SAME statistic (`XP.pairwise_gap_tests`) — one implementation (E9.61);
  · the verdict via `QB.body_verdict` (four pre-registered states) + `cross_rankable`.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster. ⛔ It writes NO optimizer input (prereg
§9) and NO predecessor path.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, few draws (artifact _smoke) — no verdict
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0c_qb_body --smoke

    # the decisive run (>2 min — OPERATOR; dominated by the W6d marginal dispatch per fold)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0c_qb_body

    # re-derive every verdict from the stored per-fold arm summaries at ZERO refit cost
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0c_qb_body --rewrite-report

⭐ Per-fold MARGINAL BANKS are cached under `artifacts/nf_w7e_bank_cache/` — NF-W7e's own cache
directory and key scheme, inherited through `W80`, so a machine already holding the W7e/W7f/W8-0
cache pays only for draws + LGBM fits.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_mixture as MX,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_split_allrows as SA,
)
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_body as QB  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_qb_marginal_calibration as QM,
)
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_serve_stat_distributions as W6DS,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w7c_fp_assembly as W7C,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w8_0_cross_position as W80,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w8_0c")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
GATE_LEAGUE = W80.GATE_LEAGUE                      # ⛔ inherited (E2.1-r)

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w8_0c_qb_body.json")
_ROWS_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0c_rows"

#: ⛔ NF-W8-0's and NF-W8-0b's records are DECIDED. A successor that writes a decided story's
#: paths destroys its audit trail with no error and no test failure (the NCAAF-P2.1 S1-serve
#: lesson). Enforced at import, not by review.
_DECIDED_PATHS: tuple[str, ...] = ("nf_w8_0_cross_position", "nf_w8_0_rows", "nf_w8_0_input",
                                   "nf_w8_0b_tail_point", "nf_w8_0b_rows", "nf_w8_0b_input")
for _own in (_ARTIFACT_REL, str(_ROWS_DIR)):
    for _dec in _DECIDED_PATHS:
        if Path(_own).name.startswith(_dec) or f"/{_dec}" in _own:
            raise RuntimeError(f"NF-W8-0c would write a DECIDED predecessor artifact path "
                               f"({_own}) — refused (a successor never writes a decided story's "
                               f"paths)")

#: the NF-W7f record, for the QB incumbent's per-fold CRPS **and** PIT pins (prereg §7)
_W7F_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
            "nf_w7f_qb_marginal.json")
#: the NF-W8-0b record, for the non-QB per-fold identity-bias pins on the tail-completed point
_W8_0B_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
              "nf_w8_0b_tail_point.json")


# ── One fold × QB: the arms, built on the certified incumbent's own intermediates ─────────────
def _score_arm(label: str, bank: np.ndarray, y: np.ndarray, point_reader) -> dict:
    KW.assert_finite_predictive(bank, f"QB/{label}")
    point = point_reader(bank)
    return {
        # ⛔ FULL PRECISION — the pins compare these at 1e-9; a round(…, 6) caps every pin at
        # ~5e-7 and the decisive run returns UNDEFINED (the NF-W8-0 smoke's catch)
        "crps": float(np.mean(KW.crps_dense(bank, y))),
        "pit": QM.pit_detail(KW.randomized_pit_from_bank(bank, y)),
        "coverage": KW.coverage80_dense(bank, y),
        "bias": XP.bias_detail(point, y),
    }


def run_qb_arms(tr_p: pd.DataFrame, te_p: pd.DataFrame, weights: np.ndarray, *, draws: int,
                b_te: np.ndarray, raw_tr: np.ndarray, raw_te: np.ndarray, y_te: np.ndarray,
                prior_ledgers: list[dict], certified: dict,
                certified_point: np.ndarray) -> tuple[dict, dict]:
    """Every NF-W8-0c arm for one fold, plus this fold's ledger for the NEXT fold's parameters.

    The incumbent is re-assembled through `QB.assemble_qq`-shaped machinery and PROVEN identical
    to the certified `zm_floor` summary before any arm is scored — the cross-check that ties this
    harness to the one code path (NF-W7d)."""
    sig_all, _ = SA.sigma_all(raw_tr)
    pi_hat = QM.pi_for_arm(QM.PI_ESTIMATOR, tr_p, te_p, FEATURES, train_raw=raw_tr)
    targets = QM.zero_targets("zm_floor", banks=b_te, pi_hat=pi_hat,
                              cond_rate=QM.conditional_zero_rate(raw_tr),
                              marg_rate=QM.marginal_zero_rate(raw_tr))
    recal = QM.resplice_zero_mass(b_te, targets)
    pi_used, clamp = MX.clamp_pi(pi_hat, recal)
    active = QM.activity_indicator(raw_te)

    banks: dict[str, np.ndarray] = {}
    leg_means: dict[str, np.ndarray] = {}
    totals: dict[str, np.ndarray] = {}
    (banks[QB.INCUMBENT], leg_means[QB.INCUMBENT],
     totals[QB.INCUMBENT]) = QB.assemble_qb(recal, weights, pi=pi_used, corr=sig_all,
                                            draws=draws)

    # ⭐ THE CROSS-CHECK: the re-derived incumbent must BE the certified generator, exactly. A
    # tolerance here would let a silently different intermediate score as `zm_floor` (NF1.7 (a)).
    inc_crps = float(np.mean(KW.crps_dense(banks[QB.INCUMBENT], y_te)))
    inc_point = QB.POINT_READER(banks[QB.INCUMBENT])
    check = {
        "certified_crps": float(certified["scores"]["zm_floor"]),
        "rederived_crps": inc_crps,
        "crps_gap": abs(inc_crps - float(certified["scores"]["zm_floor"])),
        "point_gap": float(np.max(np.abs(inc_point - np.asarray(certified_point, float)))),
    }
    check["matches"] = bool(check["crps_gap"] == 0.0 and check["point_gap"] == 0.0)
    if not check["matches"]:
        raise ValueError(
            f"the re-derived QB incumbent is NOT the certified `zm_floor` "
            f"(CRPS gap {check['crps_gap']:.3e}, point gap {check['point_gap']:.3e}) — refused "
            f"rather than scoring arms against a silently different incumbent (NF-W7d / NF1.7 (a))")

    priced_idx = [i for i in range(FA.N_LEGS) if weights[i] != 0.0]
    params: dict[str, dict] = {}
    drift: dict[str, dict] = {}

    def _build(label: str, arm_form: str, p: dict) -> None:
        """Assemble one arm from its fitted parameters. An INELIGIBLE parameter set keeps the
        incumbent's bank for that fold and is RECORDED — never silently defaulted."""
        params[label] = p
        if not p.get("eligible"):
            banks[label], leg_means[label] = banks[QB.INCUMBENT], leg_means[QB.INCUMBENT]
            totals[label] = totals[QB.INCUMBENT]
            return
        if arm_form == "cond_shift":
            banks[label], leg_means[label], totals[label] = QB.assemble_qb(
                recal, weights, pi=pi_used, corr=sig_all, draws=draws,
                played_shift=float(p["delta"]))
        elif arm_form == "cond_scale":
            k = np.ones(FA.N_LEGS); k[priced_idx] = float(p["kappa"])
            scaled = QB.scale_legs(recal, k)
            pi_s, _ = MX.clamp_pi(pi_hat, scaled)
            drift[label] = QB.marginal_drift(recal, scaled)
            banks[label], leg_means[label], totals[label] = QB.assemble_qb(
                scaled, weights, pi=pi_s, corr=sig_all, draws=draws)
        elif arm_form == "avail_relevel":
            pi_adj = np.clip(pi_hat + float(p["delta_pi"]), 0.0, 1.0)
            pi_a, note = MX.clamp_pi(pi_adj, recal)
            params[label] = p | {"clamp": note,
                                 "mean_pi_moved": float(np.mean(pi_a - pi_used))}
            banks[label], leg_means[label], totals[label] = QB.assemble_qb(
                recal, weights, pi=pi_a, corr=sig_all, draws=draws)
        elif arm_form == "leg_scale":
            scaled = QB.scale_legs(recal, np.asarray(p["kappa"], float))
            pi_s, _ = MX.clamp_pi(pi_hat, scaled)
            drift[label] = QB.marginal_drift(recal, scaled)
            banks[label], leg_means[label], totals[label] = QB.assemble_qb(
                scaled, weights, pi=pi_s, corr=sig_all, draws=draws)
        else:
            raise KeyError(f"unknown arm form `{arm_form}`")

    for arm in QB.REAL_ARMS:
        _build(arm, arm, QB.fit_arm_params(arm, prior_ledgers))

    # ── the per-form peeking oracles (NF-D16 (g‴)): the SAME form, parameter fit on the TEST fold
    this_fold = QB.fold_ledger(point=inc_point, y=y_te, leg_means=leg_means[QB.INCUMBENT],
                               realized=raw_te, pi_used=pi_used, weights=weights)
    for arm in QB.REAL_ARMS:
        p = QB.fit_arm_params(arm, [this_fold])
        if not p.get("eligible"):
            raise ValueError(
                f"the peeking oracle `{QB.ORACLE_OF[arm]}` could not be FORMED on its own test "
                f"fold ({p.get('reason')}) — a ceiling that failed to fit is a failed control, "
                f"never a pass (NF1.7 (a))")
        _build(QB.ORACLE_OF[arm], arm, p)

    # ── the magnitude anchor, registered to LOSE (NF-D20) ────────────────────────────────────────
    p_shift = params["cond_shift"]
    if p_shift.get("eligible"):
        _build("over_cond_shift", "cond_shift",
               p_shift | {"delta": float(p_shift["delta"]) * QB.OVER_SCALE,
                          "over_scale": QB.OVER_SCALE})
    else:
        params["over_cond_shift"] = {"eligible": False, "reason": "`cond_shift` is ineligible "
                                                                  "this fold, so its ×2 anchor "
                                                                  "cannot be formed"}
        banks["over_cond_shift"] = banks[QB.INCUMBENT]
        leg_means["over_cond_shift"] = leg_means[QB.INCUMBENT]
        totals["over_cond_shift"] = totals[QB.INCUMBENT]

    # ── the permuted-assignment anchor: same κ population, wrong legs ────────────────────────────
    p_leg = params["leg_scale"]
    if p_leg.get("eligible"):
        _build("permuted_leg_scale", "leg_scale",
               p_leg | {"kappa": [float(v) for v in
                                  QB.permute_kappa(p_leg["kappa"], priced_idx)],
                        "permuted": True})
    else:
        params["permuted_leg_scale"] = {"eligible": False,
                                        "reason": "`leg_scale` is ineligible this fold, so its "
                                                  "permuted anchor cannot be formed"}
        banks["permuted_leg_scale"] = banks[QB.INCUMBENT]
        leg_means["permuted_leg_scale"] = leg_means[QB.INCUMBENT]
        totals["permuted_leg_scale"] = totals[QB.INCUMBENT]

    # ── the two degenerates (scored EVERY run — NF-D11/NF1.8) ────────────────────────────────────
    prior_y = np.concatenate([np.asarray(l["y_values"], float) for l in prior_ledgers
                              if l.get("y_values")]) if prior_ledgers else np.asarray([])
    if len(prior_y) >= 2:
        banks["climatology_bank"] = QB.climatology_bank(prior_y, len(y_te))
    else:                                    # fold 1: no prior realized rows — use the incumbent's
        banks["climatology_bank"] = banks[QB.INCUMBENT]
        params["climatology_bank"] = {"eligible": False,
                                      "reason": "no prior realized rows — the climatology anchor "
                                                "could not be formed on this fold"}
    banks["nihilist_zero"] = QB.nihilist_bank(len(y_te))

    # ── family C's comparator, built by the SAME call `W80.build_position_banks` makes, and
    # cross-checked against that certified path's own score before it is scored here
    trc, tec = tr_p.copy(), te_p.copy()
    trc[FA.TARGET] = FA.score_realized(raw_tr, weights)
    tec[FA.TARGET] = y_te
    banks[QB.COMPARATOR] = KW.fit_direct_points(trc, tec, FEATURES, FA.TARGET)
    cmp_crps = float(np.mean(KW.crps_dense(banks[QB.COMPARATOR], y_te)))
    check["comparator_certified_crps"] = float(certified["scores"][QB.COMPARATOR])
    check["comparator_crps_gap"] = abs(cmp_crps - float(certified["scores"][QB.COMPARATOR]))
    if check["comparator_crps_gap"] != 0.0:
        raise ValueError(
            f"the re-derived `{QB.COMPARATOR}` comparator is NOT the certified swap construction "
            f"(CRPS gap {check['comparator_crps_gap']:.3e}) — refused (NF-W7d / NF1.7 (a))")

    arms = {label: _score_arm(label, bank, y_te, QB.POINT_READER)
            for label, bank in banks.items()}
    for label in arms:
        arms[label]["params"] = params.get(label, {"eligible": True})
        arms[label]["acts"] = (label == QB.INCUMBENT) or bool(
            np.max(np.abs(banks[label] - banks[QB.INCUMBENT])) > 0.0)
        if label in drift:
            arms[label]["marginal_drift"] = drift[label]

    bands = QB.band_decomposition(banks[QB.INCUMBENT], banks[QB.COMPARATOR])
    decomposition = QB.mechanism_decomposition(
        point=inc_point, y=y_te, leg_means=leg_means[QB.INCUMBENT], realized=raw_te,
        weights=weights, pi_used=pi_used, active=active,
        total_draw_mean=totals[QB.INCUMBENT])
    ledger = this_fold | {"y_values": [float(v) for v in y_te]}
    detail = {
        "arms": arms, "decomposition": decomposition, "bands": bands, "clamp": clamp,
        "identity_matches_certified": check,
        "n_test": int(len(y_te)), "priced_legs": [FA.LEGS[i] for i in priced_idx],
        "points": {label: [float(v) for v in QB.POINT_READER(bank)]
                   for label, bank in banks.items()},
    }
    return detail, ledger


# ── One fold ────────────────────────────────────────────────────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int, matrix_key: str,
             rows_dir: Path, prior_ledgers: list[dict],
             rebuild_banks: bool = False) -> tuple[dict, dict]:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    ctx_te, cache_state = W80._marginals_cached(fold.label, train, test, smap,
                                                matrix_key=matrix_key, rebuild=rebuild_banks)
    positions: dict[str, dict] = {}
    fold_rows: list[pd.DataFrame] = []
    qb_detail: dict | None = None
    ledger: dict | None = None
    for position in XP.POSITIONS:
        FA.assert_assembly_is_priceable(cfg, position)
        weights = FA.leg_weights(cfg, position)
        # ⭐ the certified generators, through the PREDECESSORS' own function and NF-W8-0b's
        # DECIDED point reader — one code path, so the pins cannot drift
        summary, rows = W80.run_position(position, train, test, weights, draws=draws,
                                         ctx_te=ctx_te, point_reader=QB.POINT_READER,
                                         bank_detail=QB.BANK_DETAIL)
        positions[position] = summary
        if rows is None:
            continue
        if position == QB.POSITION:
            tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
            te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
            raw_tr, raw_te = W7C.realized_matrix(tr_p), W7C.realized_matrix(te_p)
            y_te = FA.score_realized(raw_te, weights)
            b_te = W7C.bank_tensor(ctx_te, position, len(te_p))
            qb_detail, ledger = run_qb_arms(
                tr_p, te_p, weights, draws=draws, b_te=b_te, raw_tr=raw_tr, raw_te=raw_te,
                y_te=y_te, prior_ledgers=prior_ledgers, certified=summary,
                certified_point=rows["point_consumed"].to_numpy(float))
            for label, pts in qb_detail["points"].items():
                rows[f"point__{label}"] = np.asarray(pts, float)
        fold_rows.append(rows)
    rows_dir.mkdir(parents=True, exist_ok=True)
    rows_path = rows_dir / f"{fold.label}.parquet"
    if fold_rows:
        pd.concat(fold_rows, ignore_index=True).to_parquet(rows_path, index=False)
    if qb_detail is not None:
        qb_detail.pop("points", None)             # the rows parquet carries them; keep JSON lean
    log.info("[W8-0c] fold %s complete in %.1fs (bank cache %s)", fold.label, time.time() - t0,
             cache_state)
    return ({"label": fold.label, "n_test": int(len(test)), "positions": positions,
             "qb": qb_detail, "bank_cache": cache_state, "rows_path": str(rows_path)},
            ledger or {})


# ── Reproduction pins (prereg §7) ───────────────────────────────────────────────────────────────
def _record(relpath: str, story: str) -> dict | None:
    p = _PROJECT_ROOT / relpath
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    if rec.get("story") != story or rec.get("smoke"):
        return None
    return rec


def _w7f_qb_pins(fold_results: list[dict]) -> dict:
    """QB `zm_floor` per-fold CRPS AND randomized-PIT max-decile-dev vs the NF-W7f record."""
    rec = _record(_W7F_REL, "NF-W7f")
    if rec is None:
        return {"reproduces": False, "n_folds_compared": 0,
                "note": ("the NF-W7f record is absent or a path proof — the QB incumbent's "
                         "reproduction control DID NOT RUN, which is never a pass (NF1.7 (a))")}
    want = {fr["label"]: fr["positions"]["QB"] for fr in rec["fold_results"]
            if not fr["positions"].get("QB", {}).get("skipped")}
    gaps_c, gaps_p, n = [], [], 0
    for fr in fold_results:
        qb = fr.get("qb")
        if not qb or fr["label"] not in want:
            continue
        got = qb["arms"][QB.INCUMBENT]
        gaps_c.append(abs(got["crps"] - float(want[fr["label"]]["scores"]["zm_floor"])))
        gaps_p.append(abs(got["pit"]["max_decile_dev"]
                          - float(want[fr["label"]]["pit_flatness"]["zm_floor"]["max_decile_dev"])))
        n += 1
    if not n:
        return {"reproduces": False, "n_folds_compared": 0,
                "note": "no fold could be compared — DID NOT RUN, never a pass (NF1.7 (a))"}
    return {"reproduces": bool(max(gaps_c) <= QB.REPRODUCTION_TOLERANCE
                               and max(gaps_p) <= QB.REPRODUCTION_TOLERANCE),
            "n_folds_compared": n, "max_abs_crps_gap": float(max(gaps_c)),
            "max_abs_pit_gap": float(max(gaps_p))}


def _w8_0b_non_qb_pins(fold_results: list[dict]) -> dict:
    """Every position's per-fold identity bias on the tail-completed point vs the NF-W8-0b record.

    ⭐ This pins family A′ UNDER `identity` to the decided predecessor's family A exactly: the
    three non-QB positions prove this story moved nothing it was not supposed to move, and QB
    proves the tail-completed POINT read on the certified `zm_floor` bank is the same read
    NF-W8-0b decided on. A gap at ANY position means the cross-position measurement this story
    re-tests is not the one the predecessor recorded."""
    rec = _record(_W8_0B_REL, "NF-W8-0b")
    if rec is None:
        return {"reproduces": False, "n_folds_compared": 0,
                "note": ("the NF-W8-0b record is absent or a path proof — the non-QB "
                         "reproduction control DID NOT RUN, never a pass (NF1.7 (a))")}
    want = {fr["label"]: fr["positions"] for fr in rec["fold_results"]}
    gaps: dict[str, float] = {}
    n = 0
    for fr in fold_results:
        if fr["label"] not in want:
            continue
        n += 1
        for pos in XP.POSITIONS:
            a = fr["positions"].get(pos, {}).get("bias_identity")
            b = want[fr["label"]].get(pos, {}).get("bias_identity")
            if not a or not b:
                continue
            gaps[pos] = max(gaps.get(pos, 0.0), abs(float(a["bias"]) - float(b["bias"])))
    if not gaps:
        return {"reproduces": False, "n_folds_compared": n,
                "note": "no fold cell could be compared — DID NOT RUN (NF1.7 (a))"}
    return {"reproduces": bool(max(gaps.values()) <= QB.REPRODUCTION_TOLERANCE),
            "n_folds_compared": n, "max_abs_gap_by_position": gaps,
            "max_abs_gap": float(max(gaps.values()))}


# ── The derive layer (every verdict from stored per-fold summaries, zero refit) ─────────────────
def _paired(a: list[float], b: list[float]) -> np.ndarray:
    return np.asarray(a, float) - np.asarray(b, float)


def derive_0c(out: dict) -> dict:  # noqa: C901
    """The pre-registered derivation (prereg §3–§6), from stored per-fold summaries only."""
    fold_results = sorted(out["fold_results"], key=lambda r: r["label"])
    labels = [fr["label"] for fr in fold_results]
    skipped = {fr["label"]: [p for p, b in fr["positions"].items() if b.get("skipped")]
               for fr in fold_results}
    any_skipped = any(v for v in skipped.values())

    repro = {pos: W80._reproduction(fold_results, pos) for pos in XP.POSITIONS}
    pins = {"consumed_generators": repro,
            "qb_incumbent_matches_w7f": _w7f_qb_pins(fold_results),
            "non_qb_bias_matches_w8_0b": _w8_0b_non_qb_pins(fold_results),
            "identity_assembly_is_byte_identical": {
                "matches": bool(all(fr["qb"]["identity_matches_certified"]["matches"]
                                    for fr in fold_results if fr.get("qb"))),
                "max_crps_gap": float(max([fr["qb"]["identity_matches_certified"]["crps_gap"]
                                           for fr in fold_results if fr.get("qb")] or [np.inf])),
                "max_point_gap": float(max([fr["qb"]["identity_matches_certified"]["point_gap"]
                                            for fr in fold_results if fr.get("qb")] or [np.inf]))}}
    all_pins = bool(all(r["reproduces"] for r in repro.values())
                    and pins["qb_incumbent_matches_w7f"]["reproduces"]
                    and pins["non_qb_bias_matches_w8_0b"]["reproduces"]
                    and pins["identity_assembly_is_byte_identical"]["matches"])

    qb_folds = [fr for fr in fold_results if fr.get("qb")]

    # ── family A: the decomposition (a measurement — no gate) ───────────────────────────────────
    family_a = {
        "mechanism": QB.pool_mechanism([fr["qb"]["decomposition"] for fr in qb_folds]),
        "bands": QB.pool_bands([fr["qb"].get("bands") for fr in qb_folds]),
        "note": ("family A is a MEASUREMENT with no gate: the mechanism split is an EXACT "
                 "additive identity and the band split sums exactly to the grid-mean gap. Both "
                 "are deterministic functions of the certified banks, so NF-W8-0 §12.3a's "
                 "non-stationarity floor cannot apply to either, and no fold count changes them "
                 "in kind."),
        "tail_lever_closed": {
            "bound_ppr": QB.PRED_TAIL_MECHANISM_BOUND_PPR,
            "note": ("⛔ NF-W8-0b bounded the tail-completion mechanism DETERMINISTICALLY at a "
                     f"{QB.PRED_TAIL_MECHANISM_BOUND_PPR} PPR cross-position spread — ~19× short "
                     "of the artifact. It is not re-read here.")},
    }

    # ── family B: the repair contest on the evaluable folds ─────────────────────────────────────
    evaluable = [fr["label"] for fr in qb_folds
                 if any(fr["qb"]["arms"].get(a, {}).get("params", {}).get("eligible")
                        for a in QB.REAL_ARMS)]
    ev_folds = [fr for fr in qb_folds if fr["label"] in evaluable]
    arm_labels = [QB.INCUMBENT, *QB.REAL_ARMS, *QB.ANCHOR_ARMS, QB.COMPARATOR]

    def _series(label: str, key: str) -> list[float]:
        vals = []
        for fr in ev_folds:
            a = fr["qb"]["arms"].get(label)
            if a is None:
                return []
            vals.append(float(a["bias"]["bias"]) if key == "bias"
                        else float(a["crps"]) if key == "crps"
                        else float(a["pit"]["max_decile_dev"]))
        return vals

    def _pooled_bias(label: str) -> dict:
        cells = [fr["qb"]["arms"][label]["bias"] for fr in ev_folds
                 if label in fr["qb"]["arms"]]
        if not cells:
            return {"pooled": None, "abs_pooled": None, "se": None}
        p = XP.pooled_bias(cells)
        per_fold = [c["bias"] for c in cells]
        se = float(np.std(per_fold, ddof=1) / np.sqrt(len(per_fold))) if len(per_fold) > 1 else None
        return {"pooled": p["bias_pooled"], "abs_pooled": abs(p["bias_pooled"]),
                "fold_mean": p["bias_fold_mean"], "se": se, "n": p["n"]}

    bias_by_arm = {a: _pooled_bias(a) for a in arm_labels if _series(a, "bias")}
    crps_pooled = {a: (float(np.mean(_series(a, "crps"))) if _series(a, "crps") else None)
                   for a in arm_labels}
    pit_pooled = {a: (float(np.mean(_series(a, "pit"))) if _series(a, "pit") else None)
                  for a in arm_labels}
    pit_folds_clear = {a: int(sum(1 for v in _series(a, "pit") if v <= QB.PIT_MAX_DECILE_DEV))
                       for a in arm_labels if _series(a, "pit")}

    inc_crps = _series(QB.INCUMBENT, "crps")
    inc_absbias = [abs(v) for v in _series(QB.INCUMBENT, "bias")]
    clauses_by_arm: dict[str, dict] = {}
    for a in QB.REAL_ARMS:
        if not _series(a, "crps"):
            clauses_by_arm[a] = {"pit_preserved": None, "no_crps_harm": None}
            continue
        harm_p = XP.paired_onesided_p(_paired(_series(a, "crps"), inc_crps))
        clauses_by_arm[a] = {
            # the bar is a FLOOR, inherited and un-relaxed (E2.1-r) — never a target
            "pit_preserved": bool(pit_folds_clear.get(a, 0) == len(ev_folds) and len(ev_folds)),
            "no_crps_harm": not bool(harm_p is not None and harm_p < QB.ALPHA
                                     and float(np.mean(_paired(_series(a, "crps"), inc_crps))) > 0),
            "p_crps_harm": harm_p,
        }

    winner = QB.select_arm(bias_by_arm, clauses_by_arm) if len(ev_folds) >= 4 else None
    clauses: dict[str, object] = {}
    pbo = dsr = None
    p_reduces = None
    deflate_detail: dict = {}
    if winner is not None:
        clauses.update({k: v for k, v in clauses_by_arm[winner].items() if k in QB.ARM_CLAUSES})
        deltas = np.asarray(inc_absbias, float) - np.asarray(
            [abs(v) for v in _series(winner, "bias")], float)
        p_reduces = XP.paired_onesided_p(deltas)
        clauses["reduces_bias"] = bool(p_reduces is not None and p_reduces < QB.ALPHA
                                       and float(np.mean(deltas)) > 0)
        perm = bias_by_arm.get("permuted_leg_scale", {}).get("abs_pooled")
        clauses["beats_permuted"] = (None if perm is None
                                     else bool(bias_by_arm[winner]["abs_pooled"] < perm))
        clauses["degenerates_lose"] = bool(all(
            crps_pooled.get(d) is not None and crps_pooled.get(winner) is not None
            and crps_pooled[d] > crps_pooled[winner] for d in QB.DEGENERATE_ARMS))
        acts = all(fr["qb"]["arms"][winner]["acts"] for fr in ev_folds
                   if winner in fr["qb"]["arms"])
        non_qb_identical = pins["non_qb_bias_matches_w8_0b"]["reproduces"]
        clauses["banks_move_deliberately"] = bool(acts and non_qb_identical)
        mat = pd.DataFrame({a: [abs(v) for v in _series(a, "bias")] for a in QB.ELIGIBLE},
                           index=evaluable)
        deflate_detail = NF18.deflate(mat, subset=list(QB.ELIGIBLE))
        pbo = deflate_detail.get("pbo")
        os_gap = deflate_detail.get("os_gap_pct")
        clauses["pbo_ok"] = bool((pbo is not None and pbo < QB.PBO_MAX)
                                 or (os_gap is not None and os_gap <= QB.OS_GAP_TIE_PCT))
        trial_srs = []
        for a in QB.REAL_ARMS:
            d = np.asarray(inc_absbias, float) - np.asarray(
                [abs(v) for v in _series(a, "bias")], float)
            sd = float(np.nanstd(d, ddof=1))
            trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
        dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
        clauses["dsr_ok"] = bool(dsr is not None and dsr >= QB.DSR_MIN)

    # ── the per-form oracle ceilings (NF-D16 (g‴)) ──────────────────────────────────────────────
    ceilings = {}
    for a in QB.REAL_ARMS:
        o = QB.ORACLE_OF[a]
        if bias_by_arm.get(o, {}).get("abs_pooled") is None or bias_by_arm.get(a) is None:
            continue
        head = abs(bias_by_arm[QB.INCUMBENT]["abs_pooled"]) - bias_by_arm[o]["abs_pooled"]
        got = abs(bias_by_arm[QB.INCUMBENT]["abs_pooled"]) - bias_by_arm[a]["abs_pooled"]
        ceilings[a] = {
            "oracle": o, "oracle_abs_bias": bias_by_arm[o]["abs_pooled"],
            "arm_abs_bias": bias_by_arm[a]["abs_pooled"],
            "ceiling_ppr": float(head),
            "captured_fraction": (None if abs(head) <= 1e-12 else float(got / head)),
            "note": ("one ceiling PER FORM: the forms NEST (`cond_scale` ⊂ `leg_scale`), so a "
                     "single field-wide ceiling would veto a legitimately-better nested form as a "
                     "false inversion (NF-D16 (g‴))")}

    # ── the magnitude anchor, read as registered (NF-D20) ───────────────────────────────────────
    over = bias_by_arm.get("over_cond_shift", {}).get("abs_pooled")
    best_real = min((bias_by_arm[a]["abs_pooled"] for a in QB.REAL_ARMS
                     if bias_by_arm.get(a, {}).get("abs_pooled") is not None), default=None)
    over_anchor = {
        "registered_to": "LOSE", "abs_pooled": over, "best_real_abs_pooled": best_real,
        "lost_as_registered": (None if over is None or best_real is None
                               else bool(over > best_real)),
        "note": ("⛔ if this anchor WINS it is left FAILING and DECOMPOSED, never re-labelled: "
                 "that is a refuted MAGNITUDE hypothesis (the fit UNDER-corrects), obtainable "
                 "only because the anchor was SCORED (NF-D20 / NF-D14 (g′))")}

    # ── family C: the architecture comparison ───────────────────────────────────────────────────
    architecture = None
    hybrid_closes = None
    if len(ev_folds) >= 2 and _series(QB.COMPARATOR, "crps"):
        architecture = QB.architecture_state(
            pit_folds_assembly=pit_folds_clear.get(QB.INCUMBENT, 0),
            pit_folds_direct=pit_folds_clear.get(QB.COMPARATOR, 0),
            n_folds=len(ev_folds),
            crps_delta=_paired(_series(QB.COMPARATOR, "crps"), inc_crps),
            bias_delta=(np.asarray(inc_absbias, float)
                        - np.asarray([abs(v) for v in _series(QB.COMPARATOR, "bias")], float)))

    # ── family A′: the cross-position contrasts under each candidate QB point ───────────────────
    def _family_a_prime(qb_label: str) -> dict:
        bias: dict[str, list[float]] = {p: [] for p in XP.POSITIONS}
        for fr in fold_results:
            for p in XP.POSITIONS:
                if p == QB.POSITION:
                    a = (fr.get("qb") or {}).get("arms", {}).get(qb_label)
                    bias[p].append(float(a["bias"]["bias"]) if a else np.nan)
                else:
                    b = fr["positions"].get(p, {}).get("bias_identity")
                    bias[p].append(float(b["bias"]) if b else np.nan)
        return XP.pairwise_gap_tests(bias)

    a_prime = {QB.INCUMBENT: _family_a_prime(QB.INCUMBENT),
               QB.COMPARATOR: _family_a_prime(QB.COMPARATOR)}
    if winner is not None:
        a_prime[winner] = _family_a_prime(winner)

    def _closes(fa: dict) -> bool | None:
        pairs = fa.get("pairs", {})
        if any(pairs.get(k, {}).get("p_two_sided") is None for k in QB.GAP_PAIRS):
            return None
        return not any(bool(pairs[k]["bh_rejected"]) for k in QB.GAP_PAIRS)

    gap_closed = _closes(a_prime[winner]) if winner is not None else None
    hybrid_closes = _closes(a_prime[QB.COMPARATOR])

    harness_ok = bool(all_pins and not any_skipped and len(ev_folds) >= 4)
    verdict = QB.body_verdict(
        harness_ok=harness_ok, winner=winner,
        winner_clauses=clauses if winner is not None else None,
        gap_closed=gap_closed, architecture=architecture, hybrid_closes_gap=hybrid_closes,
        max_mde_ppr=a_prime[QB.INCUMBENT].get("max_mde_ppr"))

    out["pins"] = pins
    out["family_a"] = family_a
    out["family_b"] = {
        "evaluable_folds": evaluable, "n_evaluable": len(ev_folds),
        "bias_by_arm": bias_by_arm, "crps_pooled": crps_pooled, "pit_pooled": pit_pooled,
        "pit_folds_clearing": pit_folds_clear, "pit_bar": QB.PIT_MAX_DECILE_DEV,
        "arm_constraints": clauses_by_arm,
        "winner": winner, "winner_clauses": clauses,
        "p_reduces_bias_one_sided": p_reduces, "pbo": pbo, "dsr": dsr,
        "deflate_detail": {k: deflate_detail.get(k) for k in
                           ("pbo", "os_gap_pct", "contender_spread_pct", "flips")},
        "oracle_ceilings": ceilings, "over_anchor": over_anchor,
        "declared_field": {"incumbent": QB.INCUMBENT, "real_arms": list(QB.REAL_ARMS),
                           "anchors": list(QB.ANCHOR_ARMS),
                           "declared_field_size": QB.DECLARED_FIELD_SIZE,
                           "comparator_excluded": QB.COMPARATOR},
    }
    out["family_c"] = architecture
    out["family_a_prime"] = a_prime
    out["gap_closed_under_winner"] = gap_closed
    out["gap_closed_under_comparator"] = hybrid_closes
    out["skipped"] = skipped
    out["verdict"] = verdict
    out["cross_rankable"] = verdict["cross_rankable"]
    out["qb_consumption"] = {"decision": XP.QB_CONSUMPTION, "caveat": XP.QB_CONSUMPTION_CAVEAT}
    out["second_reader"] = XP.SECOND_READER
    out["promote_blockers"] = list(QB.PROMOTE_BLOCKERS)

    # ── null classification, per the vertical's rule ─────────────────────────────────────────────
    classification = None
    if verdict["state"] == QB.V_PERSISTS and winner is not None:
        failing = [c for c in QB.ARM_CLAUSES if clauses.get(c) is not True]
        anchor_fail = [c for c in failing if c in QB.ANCHOR_CLAUSES]
        stat_fail = [c for c in failing if c in QB.STATISTICAL_CLAUSES]
        d = np.asarray(inc_absbias, float) - np.asarray(
            [abs(v) for v in _series(winner, "bias")], float)
        sd = float(np.nanstd(d, ddof=1))
        instrument = cv_power.classify_null(
            metric="qb_abs_level_bias", n_folds=len(ev_folds), n_arms=len(QB.REAL_ARMS),
            beats_foil=bool(float(np.nanmean(d)) > 0),
            observed_sr=(float(np.nanmean(d)) / sd if sd > 1e-12 else None),
            var_trials_sr=(float(np.var(np.asarray(trial_srs), ddof=1))
                           if len(QB.REAL_ARMS) > 1 else None),
            fold_wins=int((d > 0).sum()), p_one_sided=p_reduces,
            degenerates_excluded_from_v=True,
            declared_field_size=QB.DECLARED_FIELD_SIZE)
        if anchor_fail:
            classification = {
                "state": "CONSTRAINT_REFUSED", "binding_half": "anchor",
                "failing_anchor_checks": anchor_fail, "failing_statistical_checks": stat_fail,
                "retest_trigger": None,
                "reason": ("the refusal rests on anchor/constraint clauses — more data makes the "
                           "refusal MORE certain, never less (NF-D18); no data trigger is "
                           "published"),
                "instrument_verdict": {"state": instrument.state, "reason": instrument.reason,
                                       "retest_trigger": instrument.retest_trigger}}
        else:
            classification = GE.flag_unsafe_field_shrink(
                {"state": instrument.state, "reason": instrument.reason,
                 "retest_trigger": instrument.retest_trigger,
                 "failing_statistical_checks": stat_fail,
                 "field_remedy_admissible": getattr(instrument, "detail", {}).get(
                     "field_remedy_admissible") if hasattr(instrument, "detail") else None},
                len(QB.REAL_ARMS))
    out["classification"] = classification
    out["classification_scope"] = (
        "⚠️⚠️ ANY TRIGGER ABOVE DESCRIBES FAMILY B ONLY — the FITTED repair contest. Family A is "
        "a DETERMINISTIC decomposition (an exact identity; no fold count changes it in kind) and "
        "family A′'s bar is INHERITED. Reading a fold trigger onto either would be the NF-D18 "
        "misleading-trigger class.")
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901
    v = out["verdict"]
    fb = out["family_b"]
    mech = out["family_a"]["mechanism"]
    L = [
        f"# NF-W8-0c — the QB BODY-level comparison ({v['state']})",
        "",
        f"Generated {out['generated_at']} · gate league **{out['gate_league']}** · "
        f"{out['n_folds']} folds · target `{QB.TARGET}` · position **{QB.POSITION}**",
        "",
        "⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
        "promotes nothing, publishes nothing and writes NO optimizer input.",
        "", "## Verdict", "",
        f"- state: **{v['state']}**",
        f"- **`cross_rankable`: {out['cross_rankable']}**",
        f"- {v['reason']}",
        f"- family-B winner: `{fb['winner']}` · family-C state: "
        f"`{(out.get('family_c') or {}).get('state')}`",
        "", "## Reproduction pins (prereg §7)", "",
        "| pin | reproduces | detail |", "|---|---|---|",
    ]
    for pos in XP.POSITIONS:
        r = out["pins"]["consumed_generators"][pos]
        L.append(f"| `{XP.CONSUMED_GENERATOR_OF[pos]}` @ {pos} | {r['reproduces']} | "
                 f"{r['n_folds_compared']} folds, max gap {r.get('max_abs_gap')} |")
    p7 = out["pins"]["qb_incumbent_matches_w7f"]
    p0b = out["pins"]["non_qb_bias_matches_w8_0b"]
    pid = out["pins"]["identity_assembly_is_byte_identical"]
    L += [f"| QB `zm_floor` CRPS+PIT vs NF-W7f | {p7['reproduces']} | "
          f"{p7['n_folds_compared']} folds, crps {p7.get('max_abs_crps_gap')}, "
          f"pit {p7.get('max_abs_pit_gap')} |",
          f"| per-position identity bias vs NF-W8-0b | {p0b['reproduces']} | "
          f"max gap {p0b.get('max_abs_gap')} by position {p0b.get('max_abs_gap_by_position')} |",
          f"| this story's assembly ≡ the certified path | {pid['matches']} | "
          f"crps gap {pid['max_crps_gap']}, point gap {pid['max_point_gap']} |",
          "", "## Family A — the decomposition (a MEASUREMENT; no gate)", ""]
    if mech.get("pooled"):
        pl = mech["pooled"]
        L += [f"- QB level bias (row-pooled): **{pl['total_bias_ppr']:+.4f} PPR** = "
              f"READ {pl['read_channel_ppr']:+.4f} + MODEL {pl['model_channel_ppr']:+.4f}",
              f"- the model channel splits: availability {pl['availability_channel_ppr']} · "
              f"conditional level {pl['conditional_channel_ppr']}",
              f"- ⭐ the identity is ASSERTED against the artifact, not restated: "
              f"`identity_holds` **{mech['identity_holds']}**, max residual "
              f"{mech['max_abs_identity_residual']:.2e} (tolerance {QB.IDENTITY_TOLERANCE})",
              f"- material channels (≥ {QB.CHANNEL_MATERIAL_PPR} PPR): "
              f"{mech['material_channels'] or 'NONE — every channel is immaterial'}",
              "", "| leg | w | contribution (PPR) | availability part | conditional part | "
              "material |", "|---|---|---|---|---|---|"]
        for leg, d in sorted(mech["legs"].items(),
                             key=lambda kv: -abs(kv[1]["contribution_ppr"] or 0.0)):
            if not d["priced"]:
                continue
            L.append(f"| {leg} | {d['weight']:+g} | {d['contribution_ppr']:+.4f} | "
                     f"{d['availability_part_ppr']} | {d['conditional_part_ppr']} | "
                     f"{d['material']} |")
    bands = out["family_a"]["bands"]
    if bands.get("bands"):
        L += ["", f"### Where along the quantile function the `zm_floor`-vs-`{QB.COMPARATOR}` "
                  f"gap lives", "",
              f"- grid-mean gap (row-pooled): **{bands['gridmean_gap_ppr']:+.4f} PPR** "
              f"(NF-W8-0b recorded {QB.PRED_QB_SWAP_BODY_GAP} on the same construction pair)",
              "", "| level band | contribution (PPR) | share of the gap |", "|---|---|---|"]
        for b in bands["bands"]:
            sh = "—" if b["share"] is None else f"{100.0 * b['share']:.1f}%"
            L.append(f"| {b['level_lo']:.3f}–{b['level_hi']:.3f} | "
                     f"{b['contribution_ppr']:+.4f} | {sh} |")
    L += ["", f"⛔ The TAIL lever is not re-read here: NF-W8-0b bounded it DETERMINISTICALLY at "
              f"{QB.PRED_TAIL_MECHANISM_BOUND_PPR} PPR — ~19× short of the artifact.",
          "", "## Family B — the declared repair field", "",
          f"- evaluable folds: {fb['n_evaluable']} · declared field size "
          f"{fb['declared_field']['declared_field_size']} · winner `{fb['winner']}` · "
          f"PBO {fb['pbo']} · DSR {fb['dsr']}",
          f"- winner clauses: {fb['winner_clauses']}",
          f"- PIT bar **{fb['pit_bar']}** (INHERITED, un-relaxed — a FLOOR, never a target)",
          "", "| arm | pooled bias (PPR) | \\|bias\\| | CRPS | PIT (mean) | folds clearing the "
          "bar | acts |", "|---|---|---|---|---|---|---|"]
    for a in (QB.INCUMBENT, *QB.REAL_ARMS, *QB.ANCHOR_ARMS, QB.COMPARATOR):
        b = fb["bias_by_arm"].get(a, {})
        pooled = b.get("pooled")
        absb = b.get("abs_pooled")
        pooled_s = "—" if pooled is None else f"{pooled:+.4f}"
        abs_s = "—" if absb is None else f"{absb:.4f}"
        acts_s = "yes" if a in fb["arm_constraints"] or a == QB.INCUMBENT else "—"
        L.append(f"| `{a}` | {pooled_s} | {abs_s} | {fb['crps_pooled'].get(a)} | "
                 f"{fb['pit_pooled'].get(a)} | "
                 f"{fb['pit_folds_clearing'].get(a)}/{fb['n_evaluable']} | {acts_s} |")
    L += ["", "### The per-form oracle ceilings (one per FORM — NF-D16 (g‴))", "",
          "| arm | its own form's ceiling (PPR) | captured fraction |", "|---|---|---|"]
    for a, c in fb["oracle_ceilings"].items():
        cf = "—" if c["captured_fraction"] is None else f"{100.0 * c['captured_fraction']:.1f}%"
        L.append(f"| `{a}` | {c['ceiling_ppr']:+.4f} | {cf} |")
    oa = fb["over_anchor"]
    L += ["", f"- magnitude anchor `over_cond_shift` (registered to **LOSE**): "
              f"|bias| {oa['abs_pooled']} vs best real {oa['best_real_abs_pooled']} ⇒ "
              f"lost_as_registered **{oa['lost_as_registered']}**",
          f"  - {oa['note']}",
          "", "## Family C — the architecture comparison (`direct_points` for QB)", ""]
    fc = out.get("family_c")
    if fc:
        L += [f"- state: **{fc['state']}**", f"- {fc['reason']}",
              f"- PIT folds clearing the {QB.PIT_MAX_DECILE_DEV} bar: {fc['pit_folds_clearing']}",
              f"- assembly wins {fc['assembly_wins']} · `direct_points` wins "
              f"{fc['direct_points_wins']}",
              f"- mean CRPS delta (direct − assembly) {fc['mean_crps_delta']:+.4f} · "
              f"mean |bias| delta (assembly − direct) {fc['mean_abs_bias_delta']:+.4f}"]
    else:
        L.append("- UNEVALUABLE on this run (fewer than 2 evaluable folds) — never read as a "
                 "result (NF1.7 (a))")
    L += ["", "## Family A′ — the cross-position contrasts under each candidate QB point", ""]
    for label, fa in out["family_a_prime"].items():
        L.append(f"- under `{label}`: gap_detected **{fa['gap_detected']}** · "
                 + " · ".join(f"{k} {fa['pairs'][k]['gap']} (BH {fa['pairs'][k]['bh_rejected']})"
                              for k in QB.GAP_PAIRS if k in fa["pairs"]))
    L += ["", f"- gap closed under the winner: **{out['gap_closed_under_winner']}** · under "
              f"`{QB.COMPARATOR}`: **{out['gap_closed_under_comparator']}**",
          "", "## Null classification", "", f"- {out.get('classification')}", "",
          out["classification_scope"], "", "## Promote blockers", ""]
    L += [f"- {b}" for b in out["promote_blockers"]]
    path.write_text("\n".join(L) + "\n")


# ── Main ────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W8-0c — the QB body-level comparison (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, few draws (artifact _smoke) — no verdict "
                         "(the reproduction pins cannot hit at smoke draws)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored per-fold summaries (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true",
                    help="ignore the per-fold marginal-bank cache and refit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")
    rows_dir = _ROWS_DIR.with_name(_ROWS_DIR.name + suffix)

    if args.rewrite_report:
        out = json.loads(art.read_text())
        out = derive_0c(out)
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W8-0c report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else FA.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    log.info("NF-W8-0c: %d folds × %d positions, %d draws%s [QB body field: %s]", len(folds),
             len(XP.POSITIONS), draws, " [SMOKE]" if args.smoke else "", list(QB.REAL_ARMS))

    t0 = time.time()
    fold_results: list[dict] = []
    ledgers: list[dict] = []          # ⭐ PRIOR folds only, in chronological order (prereg §4)
    for f in folds:
        fr, ledger = run_fold(f, feat, smap, draws=draws, matrix_key=matrix_key,
                              rows_dir=rows_dir, prior_ledgers=list(ledgers),
                              rebuild_banks=args.rebuild_banks)
        fold_results.append(fr)
        if ledger:
            ledgers.append(ledger)
    out = {
        "story": QB.STORY, "predecessors": list(QB.PREDECESSORS), "phase": "qb_body_relevel",
        "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "matrix_key": matrix_key, "pit_audit": pit_audit, "attach_audit": attach,
        "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "seed": SA._SEED,
        "point_reader": getattr(QB.POINT_READER, "__qualname__", str(QB.POINT_READER)),
        "consumed_generators": dict(XP.CONSUMED_GENERATOR_OF),
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_0c(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W8-0c %s (cross_rankable=%s) → %s (%.1fs)", out["verdict"]["state"],
             out["cross_rankable"], art.name, out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
