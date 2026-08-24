"""run_interval_revalidation.py — the STANDING ANNUAL RE-VALIDATION of every shipped 80% interval band
(NF1.8 rookies + NF1.9 veterans + NF1.6 K/DST) against its pre-registered coverage floor.

⚠️ WHY THIS EXISTS, and why a one-off number was not enough. **A per-position coverage floor is
INVISIBLE at serving time.** Coverage needs REALIZED OUTCOMES, so nothing in the board-build path, the
export guard or the API can notice a floor breaking — it would degrade silently for years. That is not
hypothetical: it is exactly how the VETERAN band — 90% of the draft board — went five stories (NF1.4,
NF1.5, NF1.7, NF1.8, NF3) without a single coverage number attached to it, while covering 0.55 of its
nominal 0.80. `audit_interval_quality()` catches a DEGENERATE band; only realized outcomes catch a
MISCALIBRATED one.

So the floors get an owner and a cadence:

  ▸ RUN IT ONCE A SEASON, after the completed season's outcomes land in the NFL marts (and after a new
    rookie class's first year completes).
  ▸ It re-scores the SHIPPED band of each population — not the whole bake-off — so it is cheap.
  ▸ **A floor breach exits NON-ZERO. It is a RE-SELECTION TRIGGER, not a log line.** The response is to
    re-run that population's bake-off, NOT to move the floor (a floor that moves until something clears
    it is not a floor — E2.1-r, and NF1.8 §1).

⚠️ WHAT IS AND IS NOT THE TRIGGER. The binding check is the POOLED-over-all-held-out-cohorts
per-position coverage — the same statistic each selection was made on. A SINGLE new season/class is far
too thin per position to be a trigger on its own (one veteran season carries ~55 QBs; one rookie class
~12), so the newest cohort is reported as a LEADING INDICATOR and never gates. Reporting it is the
point: a new cohort that misses badly will move the pooled number next year, and that is when to look.

⭐ NF1.6 ADDED A THIRD POPULATION — **K + DST** — AND THE DECISION TO COVER IT HERE WAS DELIBERATE.
The alternative (scoping the two new positions out of this check) was rejected precisely because
leaving a brand-new band silently unmonitored is the failure mode this file exists to prevent. Two
things differ for it, and both are intentional:

  ▸ **Its breach RESPONSE is to WIDEN, not to re-select.** The rookie/veteran bands were SELECTED by a
    §0.5 bake-off, so a breach re-triggers that selection. The K/DST band is *reported, not selected*
    — a deliberately BASE band on the two least predictable fantasy positions, with no candidate
    field behind it. So a breach there means widen the base band honestly
    (`kdst_projection.RatioBand.widen`, or raise `BAND_CLUSTER_Z`) and re-report. It still does NOT
    mean move the floor (E2.1-r).
  ▸ **Its floor is per POSITION (K, DST), not per offensive position**, and it is a FLOOR at the
    nominal 0.80 exactly as the other two are.

📌 A NON-GATING CADENCE POINTER — NF-D15's data-availability RE-RUN (carried by NF-D16, PM ruling 2).
NF-D15 recorded a rookie-POINT effect that was real-but-UNDERPOWERED: it reproduced on the selecting
metric and passed PBO, but failed DSR/BH-FDR purely at n = 7 held-out draft classes. Its computed
power-in-classes said **TE needs 10 classes (⇒ re-runnable once the 2028 rookie season completes) and
RB needs 11 (⇒ 2029)**; WR needs ~29, i.e. it is a genuine absence at any n this program will have. So
when this harness is next run for one of those seasons, ALSO re-run:

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d15_point_scaling

⚠️ **THIS IS A POINTER, NOT A GATE, AND THE DISTINCTION IS DELIBERATE.** This file's contract is
"a coverage-FLOOR breach exits NON-ZERO"; NF-D15's trigger is a *data-availability* re-run with no
floor attached to it. Folding it into the exit code would make a non-zero exit mean two different
things and corrupt the one contract every reader of this harness relies on. It lives here because this
is the file with the annual cadence and an owner, which is the only property the pointer needs.

⚠️ THE POSITION TO WATCH IS ROOKIE **RB**. NF1.8 shipped with per-position floor margins, in ROWS, of
QB 1 / RB **0** / TE 12 / WR 8 — i.e. rookie RB clears its floor with ZERO covered rookie-seasons of
slack, so it is the floor a future class breaks first. The veteran margins are much larger (64–337 rows)
because the population is ~10× bigger, not because the band is more certain.

⭐ NF-D22 — **THE FLOOR THIS CHECK GATES ON IS NOW POWER-DERIVED, AND THE MARGINS ABOVE ARE WHY.**
"RB clears with ZERO rows of slack" was read for a year as a statement about the BAND. It is mostly a
statement about the FLOOR: a hard point-estimate floor at nominal rejects a *perfectly calibrated*
band with probability ≈ 0.5 at every n this program has (measured exactly: 0.456 at n = 81, **0.500**
at n = 148, 0.489 at n = 3000). A gate whose refusals are coin tosses is not conservative, it is
uninformative — and its refusals still read as evidence, which is worse than not gating at all.

So the floor is now the exact one-sided Binomial acceptance bound at a PRE-REGISTERED false-reject
target (`betting_ml.utils.coverage_power_floor`, target 0.05 — NF1.8's own Tier-2 level, only now
applied to every constrained group instead of a hardcoded two-position tuple, and computed exactly
rather than through a normal approximation that does not honour the rate it advertises). It is a
function of the group's `n` and that target and NOTHING ELSE, and it self-attenuates: 0.667 at
n = 30, 0.743 at n = 148, 0.788 at n = 3000, 0.792 at n = 6000 → nominal. Nothing had to decide which
groups count as "thin".

  ⛔ THE FLOOR STILL MAY NOT MOVE, AND A BREACH IS STILL A RE-SELECTION TRIGGER (E2.1-r; NF1.8 §1).
     What changed is that a breach now MEANS something. Both readings are printed side by side in
     every run (`floors` / `floors_at_nominal`, `slack_rows` / `slack_rows_at_nominal`) so the change
     is visible in the artifact rather than only in a changelog.
  ⛔ THE §0.5 SELECTION FLOOR IS UNTOUCHED. `run_rookie_perposition_ablation.position_floors` still
     governs bake-off ELIGIBILITY at the hard nominal level. There a FIELD of arms exists and the
     METRIC does the selecting; here there is one shipped band and the floor is the whole decision.
     Relaxing eligibility inside recorded searches would re-decide them post hoc.

RUN ON THE LAPTOP (~1 min with a warm panel; add --rebuild-panel after a new season lands):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation

    # after a new completed season has landed in the NFL marts:
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation \\
      --rebuild-panel --rebuild-kdst-panel
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import coverage_power_floor as CPF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    rookie_publish_policy as _ROOKIE_POLICY,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
    run_veteran_interval_ablation as NF19,
)

log = logging.getLogger("nfl.fantasy.interval_revalidation")

#: Only ever used when a caller omits `nominal` — every real call passes its population's own
#: pre-registered value, so this is a guard against a silent 0-coverage floor, not a policy.
CPF_NOMINAL_DEFAULT = 0.80

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
#: ⛔ THE DECIDED ARTIFACT — NF1.9's committed standing record. Writing it is now an EXPLICIT act
#: (`--out nf1_9_interval_revalidation`), never a side effect (NF-INJ3b D4).
DECIDED_STEM = "nf1_9_interval_revalidation"
#: the DEFAULT stem: a neutral "latest run" path belonging to NO story. A session that needs this
#: re-validation as a GATE on its own change (NF-INJ3b's ship path did) must not be able to rewrite
#: NF1.9's record on the way past — which it previously did EVEN UNDER `--no-report`.
DEFAULT_STEM = "nf1_9_interval_revalidation_latest"
_OUT_JSON = _REPORT_DIR / f"{DECIDED_STEM}.json"
_OUT_MD = _REPORT_DIR / f"{DECIDED_STEM}.md"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The shipped configs, DERIVED FROM THE SERVED CONSTANTS (never re-typed)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def shipped_rookie_cfg() -> dict:
    """NF1.8's shipped rookie band, read off `season_projection`'s own constants.

    ⚠️ Derived, not hardcoded: a re-validation that pins a literal would keep validating the band the
    code USED to serve after someone changes a constant — which is the one failure mode a standing
    check must not have."""
    return {"label": "SHIPPED rookie band", "arm": "model", "form": SP._ROOKIE_BAND_FORM,
            "k": SP._ROOKIE_BAND_K, "resid_sd_gain": SP._ROOKIE_BAND_RESID_SD_GAIN,
            "qreg_alpha": SP._ROOKIE_BAND_QREG_ALPHA,
            "qreg_per_pos": SP._ROOKIE_BAND_QREG_PER_POS,
            "cqr_mode": SP._ROOKIE_BAND_CQR_MODE, "cqr_scale": SP._ROOKIE_BAND_CQR_SCALE}


def shipped_veteran_cfg() -> dict:
    """NF1.9's shipped veteran band, read off `season_projection`'s own constants (see above)."""
    if not SP._VET_BAND_PER_PLAYER:
        return {"label": "SHIPPED veteran band (PER-PLAYER BAND IS DISABLED — the served band is the "
                         "normal approximation)", "arm": "incumbent"}
    return {"label": "SHIPPED veteran band", "arm": "model", "form": SP._VET_BAND_FORM,
            "k": SP._VET_BAND_K, "sd_gain": SP._VET_BAND_SD_GAIN,
            "qreg_alpha": SP._VET_BAND_QREG_ALPHA, "qreg_per_pos": SP._VET_BAND_QREG_PER_POS,
            "cqr_mode": SP._VET_BAND_CQR_MODE, "cqr_scale": SP._VET_BAND_CQR_SCALE}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring one population
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _floor_block(rec: dict, positions: list[str], floor_kwargs: dict) -> dict:
    """The pooled + per-position floor read for one population — the BINDING check.

    ⭐ NF-D22: THE FLOOR IS NOW POWER-DERIVED (`betting_ml.utils.coverage_power_floor`), NOT A HARD
    POINT ESTIMATE AT NOMINAL. The rule it replaces rejected a *perfectly calibrated* band about half
    the time at every n this program has (exactly 0.500 at n = 148, 0.456 at n = 81, 0.489 at
    n = 3000) — so a breach carried almost no information and a refusal read as evidence when it was
    a coin toss. The floor here is the exact one-sided Binomial acceptance bound at a pre-registered
    false-reject TARGET, derived from the group's `n` and that target and NOTHING else; it converges
    to nominal as n grows, so nothing had to decide which groups are "thin".

    ⛔ THIS IS THE **GATE** FLOOR, NOT THE **SELECTION** FLOOR. `NF18.position_floors` — the
    eligibility constraint inside a §0.5 bake-off, where a FIELD of arms exists and the METRIC does
    the selecting — is deliberately untouched, because relaxing eligibility there would re-decide
    searches that are already recorded. Here there is one shipped band, no field and no metric, so
    the floor *is* the whole decision, which is exactly and only where a ~50% false-reject rate is
    fatal. See the module docstring of `coverage_power_floor` for the full prohibition list.

    ⚠️ A breach under the new rule is STILL a re-selection trigger and the floor still may not move.
    Both floors are reported side by side so the change is visible in every run rather than inferable
    from a changelog: `floors_at_nominal` and `slack_rows_at_nominal` preserve the previous reading.
    """
    nominal = float(floor_kwargs.get("nominal", CPF_NOMINAL_DEFAULT))
    min_n = floor_kwargs.get("min_n")
    n_by = {p: rec.get(f"n_{p}") for p in positions}
    cov_by = {p: rec.get(f"cov_{p}") for p in positions}
    table = CPF.floor_table(n_by, nominal=nominal, min_n=min_n, coverage_by_group=cov_by)

    # The POOLED floor runs the IDENTICAL rule over the pooled row count. It is materially tighter
    # (larger n ⇒ closer to nominal), which is what makes the two-tier structure the substantive
    # backstop against a band resting on each thin group's own low floor — MEASURED below, never
    # assumed.
    pooled_n = int(rec.get("n") or 0)
    pooled_cov = rec.get("coverage_80")
    pooled = (CPF.group_floor(pooled_n, nominal=nominal, coverage=pooled_cov)
              if pooled_n > 0 else None)
    misses = list(table["misses"])
    if pooled is not None and pooled_cov is not None and not pooled["met"]:
        misses.insert(0, f"pooled {pooled['coverage']}<{pooled['floor']:.4f} "
                         f"({pooled['covered_rows']}/{pooled_n} covered, "
                         f"{pooled['covered_rows_required']} required)")
    # ⚠️ A position whose coverage could not be read is NOT a pass (NF1.7 (a)) — it is a check with
    #    no subject, and scoring that green is how a floor becomes decoration.
    misses += [f"{p} coverage unavailable — NOT scored as met" for p in table["coverage_unavailable"]]

    # NF1.8's previous reading, preserved verbatim beside the new one.
    nominal_floors = {p: nominal for p, n in n_by.items()
                      if int(n or 0) > 0 and (min_n is None or int(n) >= int(min_n))}
    return {
        "floor_rule": table["floor_rule"],
        "target_false_reject_rate": table["target_false_reject_rate"],
        "target_provenance": table["target_provenance"],
        "floors": table["floors"],
        "floor_detail": table["detail"],
        "floors_at_nominal": nominal_floors,
        "coverage": cov_by,
        "n_by_position": n_by,
        "slack_rows": {p: b["slack_rows"] for p, b in table["detail"].items()
                       if "slack_rows" in b},
        "slack_rows_at_nominal": {p: b["slack_rows_at_nominal_floor"]
                                  for p, b in table["detail"].items()
                                  if "slack_rows_at_nominal_floor" in b},
        "unconstrained": table["unconstrained"],
        "misses": misses,
        "misses_at_nominal_floor": NF18.floor_misses(
            rec, NF18.position_floors(rec, positions, tier=1, **floor_kwargs)),
        "pass": not misses,
        "pooled_coverage": pooled_cov,
        "pooled_floor": (pooled or {}).get("floor"),
        "pooled_floor_detail": pooled,
        "pooled_backstop": CPF.pooled_backstop_check(
            pooled_n or 1, [b["n"] for b in table["detail"].values()], nominal=nominal),
        "family_false_reject": table["family"],
        "interval_score": rec.get("interval_score"),
    }


def revalidate_rookies(pool_path: Path, from_year: int, to_year: int) -> dict:
    """Re-score NF1.8's shipped rookie band on every available held-out draft class."""
    pool = NF17.load_pool(pool_path)
    # ⭐ NF-D21: `build_folds` resolves its λ from the SERVED rookie policy, so this standing check
    #    re-scores the band against the point the product ACTUALLY serves. That was not true before
    #    NF-D21 — the folds recalibrated at λ=1 while serving ran the correction OFF, so the floors
    #    were being confirmed on a point nobody was shown. λ is RECORDED in the report below, because
    #    "the floors held" means nothing without saying which point they held around.
    served_lambda = _ROOKIE_POLICY.serving_lambda()
    folds = NF17.build_folds(pool, list(range(from_year, to_year + 1)))
    if len(folds) < 2:
        return {"population": "rookies", "error": f"only {len(folds)} usable draft classes"}
    cfg = shipped_rookie_cfg()
    rec = NF18.run_arm(folds, cfg)
    if rec is None:
        return {"population": "rookies", "error": "the shipped rookie band did not score"}
    POS = sorted({k[4:] for k in rec if k.startswith("cov_")})
    out = {"population": "rookies", "config": cfg["label"], "form": cfg.get("form"),
           "rookie_point_shrink_lambda": served_lambda,
           "rookie_selection_status": (_ROOKIE_POLICY.SELECTION_STATUS if served_lambda
                                       else "incumbent"),
           "cohorts": [f.year for f in folds], "n": rec["n"],
           **_floor_block(rec, POS, {"min_n": NF18._POS_FLOOR_MIN_N,
                                     "tier2_positions": NF18._TIER2_POSITIONS,
                                     "nominal": NF18._NOMINAL})}
    # the NEWEST cohort as a LEADING INDICATOR (never a trigger — one class is ~80 rookie-seasons)
    newest = folds[-1]
    nrec = NF18.run_arm([newest], cfg)
    out["newest_cohort"] = {
        "cohort": newest.year, "n": (nrec or {}).get("n"),
        "pooled_coverage": (nrec or {}).get("coverage_80"),
        "coverage": {p: (nrec or {}).get(f"cov_{p}") for p in POS},
        "note": "LEADING INDICATOR ONLY — one draft class is far too thin per position to gate on",
    }
    return out


def revalidate_veterans(panel_dir: Path, from_year: int, to_year: int) -> dict:
    """Re-score NF1.9's shipped veteran band on every available held-out target season."""
    panel = NF19.load_panel(panel_dir)
    folds = NF19.build_folds(panel, list(range(from_year, to_year + 1)))
    if len(folds) < 2:
        return {"population": "veterans", "error": f"only {len(folds)} usable target seasons"}
    cfg = shipped_veteran_cfg()
    rec = NF19.run_arm(folds, cfg)
    if rec is None:
        return {"population": "veterans", "error": "the shipped veteran band did not score"}
    POS = sorted({k[4:] for k in rec if k.startswith("cov_")})
    out = {"population": "veterans", "config": cfg["label"], "form": cfg.get("form"),
           "cohorts": [f.year for f in folds], "n": rec["n"],
           "below_p10": rec.get("below_p10"), "above_p90": rec.get("above_p90"),
           **_floor_block(rec, POS, {"min_n": NF19._POS_FLOOR_MIN_N,
                                     "tier2_positions": NF19._TIER2_POSITIONS,
                                     "nominal": NF19._NOMINAL})}
    newest = folds[-1]
    nrec = NF19.run_arm([newest], cfg)
    out["newest_cohort"] = {
        "cohort": newest.year, "n": (nrec or {}).get("n"),
        "pooled_coverage": (nrec or {}).get("coverage_80"),
        "coverage": {p: (nrec or {}).get(f"cov_{p}") for p in POS},
        "above_p90": (nrec or {}).get("above_p90"),
        "note": "LEADING INDICATOR ONLY — one target season is far too thin per position to gate on",
    }
    return out


def revalidate_kdst(panel_path: Path, *, widen: float = 1.0,
                    cluster_z: float | None = None) -> dict:
    """Re-score NF1.6's shipped K/DST BASE band against its per-position coverage floors.

    ⚠️ The band config is DERIVED from `kdst_projection`'s own served constants (`BAND_QUANTILES`,
    `BAND_CLUSTER_Z`), never re-typed here — a re-validation that pins a literal keeps validating the
    band the code USED to serve after someone changes a constant, which is the one failure mode a
    standing check must not have.

    ⚠️ An unreadable or empty panel is an ERROR, not a pass. `main` treats a block without
    `pass is True` as a failure, so a population this check could not load can never be mistaken for
    a population that cleared its floor (the NF1.7 vacuous-anchor lesson wearing an ops hat)."""
    from quant_sports_intel_models.football.nfl.fantasy import kdst_projection as KD
    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16

    if not Path(panel_path).exists():
        return {"population": "kdst",
                "error": f"no K/DST band panel at {panel_path} — run "
                         f"`run_kdst_projection.py --rebuild-panel` first"}
    panel = pd.read_parquet(panel_path)
    if panel.empty:
        return {"population": "kdst", "error": f"the K/DST band panel at {panel_path} is EMPTY"}
    z = KD.BAND_CLUSTER_Z if cluster_z is None else float(cluster_z)
    try:
        rep = NF16.walk_forward_coverage(panel, widen=widen, cluster_z=z)
    except Exception as exc:  # noqa: BLE001 — an errored block is NOT a pass (see docstring)
        return {"population": "kdst", "error": f"the K/DST band did not score: {exc}"}
    positions = sorted(str(p) for p in panel["position"].dropna().unique())
    # ⭐ NF-D22 — the SAME power-derived floor as the other two populations, with no K/DST-specific
    #    carve-out. K and DST are the THINNEST groups this check has (~45 kickers and ~32 DSTs a
    #    season), so a hard point-estimate floor at nominal was least informative exactly here. The
    #    breach RESPONSE stays different by design (widen, do not re-select — `breach_response`
    #    below); only the floor's DERIVATION changed. `nominal` is still read off the served constant
    #    `KD.NOMINAL_COVERAGE`, never re-typed.
    kd_table = CPF.floor_table(
        {p: rep.get(f"n_{p}") for p in positions}, nominal=KD.NOMINAL_COVERAGE,
        coverage_by_group={p: rep.get(f"cov_{p}") for p in positions})
    floors = dict(kd_table["floors"])
    # ⚠️ A position whose coverage could not be read is NOT a pass (NF1.7 (a)).
    misses = list(kd_table["misses"]) + [
        f"{p} coverage unavailable — NOT scored as met" for p in kd_table["coverage_unavailable"]]
    cohorts = [int(v) for v in sorted(panel["target_season"].unique())]
    table_unconstrained = sorted(set(kd_table["unconstrained"]) | {p for p in positions
                                                                  if p not in floors})
    out = {
        "population": "kdst",
        "config": (f"SHIPPED K/DST base band (q{KD.BAND_QUANTILES[0]:.2f}/"
                   f"q{KD.BAND_QUANTILES[1]:.2f} ratio quantiles, cluster_z={z})"),
        "form": "empirical_ratio_band",
        "cohorts": rep.get("held_out_seasons", cohorts),
        "n": rep["n"],
        "floor_rule": kd_table["floor_rule"],
        "target_false_reject_rate": kd_table["target_false_reject_rate"],
        "floors": floors,
        "floor_detail": kd_table["detail"],
        "floors_at_nominal": {p: KD.NOMINAL_COVERAGE for p in floors},
        "family_false_reject": kd_table["family"],
        "coverage": {p: rep.get(f"cov_{p}") for p in floors},
        "n_by_position": {p: rep.get(f"n_{p}") for p in floors},
        # margin in ROWS, the NF1.8 convention — "0.83 vs 0.80" reads like a calibration statement;
        # "12 covered rows of slack" is the number that says how close this actually is
        "slack_rows": {p: b["slack_rows"] for p, b in kd_table["detail"].items()
                       if "slack_rows" in b},
        "slack_rows_at_nominal": {p: b["slack_rows_at_nominal_floor"]
                                  for p, b in kd_table["detail"].items()
                                  if "slack_rows_at_nominal_floor" in b},
        "unconstrained": table_unconstrained,
        "misses": misses,
        "pass": not misses,
        "pooled_coverage": rep["coverage_80"],
        "interval_score": rep["interval_score"],
        "below_p10": rep["below_p10"],
        "above_p90": rep["above_p90"],
        "beats_degenerates": rep["beats_degenerates"],
        "breach_response": ("WIDEN the base band (kdst_projection.RatioBand.widen / BAND_CLUSTER_Z) "
                            "and re-report — this band is REPORTED, not selected, so there is no "
                            "bake-off to re-run. Do NOT move the floor."),
    }
    # newest cohort as a LEADING INDICATOR (one season is ~32 DSTs + ~45 kickers — far too thin)
    newest = max(cohorts)
    try:
        nrec = NF16.walk_forward_coverage(panel[panel["target_season"] <= newest],
                                         min_train_targets=len(cohorts) - 1, widen=widen,
                                         cluster_z=z)
        out["newest_cohort"] = {
            "cohort": newest, "n": nrec["n"], "pooled_coverage": nrec["coverage_80"],
            "coverage": {p: nrec.get(f"cov_{p}") for p in floors},
            "above_p90": nrec["above_p90"],
            "note": "LEADING INDICATOR ONLY — one season is ~32 DSTs + ~45 kickers, far too thin "
                    "to gate a per-position floor",
        }
    except Exception as exc:  # noqa: BLE001 — advisory block only; never gates
        out["newest_cohort"] = {"cohort": newest, "note": f"not scorable ({exc})"}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".3f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def rows_for(block: dict) -> list[dict]:
    if block.get("error"):
        return [{"population": block["population"], "position": "—", "error": block["error"]}]
    rows = []
    for p in sorted(block["coverage"]):
        floor = block["floors"].get(p)
        cov = block["coverage"].get(p)
        detail = (block.get("floor_detail") or {}).get(p) or {}
        rows.append({
            "population": block["population"], "position": p,
            "n (held-out)": block["n_by_position"].get(p),
            "coverage": cov,
            "floor (power-derived)": floor if floor is not None else
            "unconstrained (n below the pre-registered minimum)",
            "slack (rows)": block["slack_rows"].get(p),
            # ⭐ THE PREVIOUS READING, KEPT VISIBLE. A floor change that only shows up in a
            #    changelog is a floor change a future reader cannot audit; carrying both columns
            #    makes "what would the old rule have said" a glance rather than an archaeology dig.
            "floor at nominal (previous rule)": (block.get("floors_at_nominal") or {}).get(p),
            "slack at nominal (rows)": (block.get("slack_rows_at_nominal") or {}).get(p),
            "P(reject | truly nominal)": detail.get("false_reject_rate"),
            "…under the previous rule": detail.get("false_reject_rate_at_nominal_floor"),
            "detectable shortfall": detail.get("detectable_shortfall"),
            "verdict": ("—" if floor is None else
                        "✅ met" if (cov or 0) >= floor else "🚨 BREACH → RE-SELECT"),
        })
    return rows


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# Interval-band re-validation — the standing annual check on both per-position coverage floors")
    p("")
    p(f"**Generated:** {out['generated_at']} · **verdict: "
      f"{'✅ ALL FLOORS MET' if out['pass'] else '🚨 FLOOR BREACH — RE-SELECTION TRIGGERED'}**")
    p("")
    p("⚠️ **A per-position coverage floor is invisible at serving time** — coverage needs realized "
      "outcomes, so no board build, export guard or API check can see it break. That is how the veteran "
      "band went five stories at 0.55 coverage of its nominal 0.80. This check is the owner of both "
      "floors; a breach is a **RE-SELECTION TRIGGER** (re-run that population's bake-off), never a "
      "reason to move the floor.")
    p("")
    p("## The floor in force — a DESIGN table, computable before any band is scored (NF-D22)")
    p("")
    p("Every floor below is a function of the group's held-out row count and a **pre-registered "
      "false-reject target** (0.05 — NF1.8's own Tier-2 level), and of nothing else. No observed "
      "coverage reaches the derivation: `power_floor(n, nominal, target)` has no coverage argument "
      "and a guard asserts its signature never gains one. That is what makes it a floor rather than "
      "a number reverse-engineered from something that failed (E2.1-r).")
    p("")
    p("The rule it replaces was a hard point estimate at nominal, whose false-reject rate against a "
      "**perfectly calibrated** band is ≈ 0.5 at every sample size this program has — so a breach "
      "carried almost no information while its refusals still read as evidence. Both columns are "
      "kept below so the change is auditable per run.")
    p("")
    drows = []
    for b in out["blocks"]:
        for g, d in sorted((b.get("floor_detail") or {}).items()):
            drows.append({
                "population": b.get("population"), "group": g, "n": d.get("n"),
                "floor (NF-D22)": d.get("floor"),
                "covered rows required": d.get("covered_rows_required"),
                "…at the nominal floor": d.get("covered_rows_required_at_nominal_floor"),
                "relaxation (rows)": d.get("relaxation_rows"),
                "P(reject | truly nominal)": d.get("false_reject_rate"),
                "…under the previous rule": d.get("false_reject_rate_at_nominal_floor"),
                "detectable shortfall": d.get("detectable_shortfall"),
                "thin?": d.get("is_thin"),
            })
    p(_md(pd.DataFrame(drows)) if drows else "_no constrained group scored_")
    p("")
    p("⚠️ **`detectable shortfall` is the floor's RESOLUTION and is reported with every verdict.** "
      "It is the largest true coverage the floor rejects with ≥80% probability. A floor that cannot "
      "resolve a defect has not cleared the band, it has failed to look — so a ✅ here means \"not "
      "shown to be broken at this n\", never \"shown to be right\" (NF1.7 (a)).")
    p("")
    p("⚠️ **Multiplicity is REPORTED AND NOT CORRECTED FOR, deliberately.** Every floor must hold, "
      "so the rate at which the whole check falsely fires compounds across groups:")
    p("")
    frows = [{"population": b.get("population"),
              "floors": (b.get("family_false_reject") or {}).get("n_floors"),
              "family false-reject (NF-D22)":
                  (b.get("family_false_reject") or {}).get("family_false_reject_rate"),
              "…under the previous rule":
                  (b.get("family_false_reject") or {}).get(
                      "family_false_reject_rate_at_nominal_floor")}
             for b in out["blocks"] if b.get("family_false_reject")]
    p(_md(pd.DataFrame(frows)) if frows else "_not computed_")
    p("")
    p("A Bonferroni split would bound the family figure — by making **every individual floor "
      "looser**, which is precisely the adjustment a reader should distrust from a story whose "
      "downstream consequence is a previously-refused publish clearing. The per-group "
      "pre-registered target binds; this is the caveat beside it, not a lever (NF1.8: report both "
      "conventions, let the pre-registered one bind).")
    p("")
    p("### The substantive backstop — MEASURED, not asserted")
    p("")
    p("The objection to a self-attenuating per-group floor is that a band could rest near every "
      "thin group's own low floor. It cannot: the POOLED check runs the identical rule over a "
      "several-times-larger `n`, so its floor sits closer to nominal than any single group's.")
    p("")
    brows = [{"population": b.get("population"), **(b.get("pooled_backstop") or {})}
             for b in out["blocks"] if b.get("pooled_backstop")]
    if brows:
        p(_md(pd.DataFrame([{k: v for k, v in r.items() if k != "note"} for r in brows])))
    else:
        p("_not computed_")
    p("")
    p("## Pooled per-position coverage — the BINDING check")
    p("")
    rows = []
    for b in out["blocks"]:
        rows += rows_for(b)
    p(_md(pd.DataFrame(rows)))
    p("")
    p("## Newest cohort — a LEADING INDICATOR, never a gate")
    p("")
    p("One draft class (~80 rookie-seasons) or one target season (~600 veteran-seasons, ~55 per thin "
      "position) is far too small to gate a per-position floor: a perfectly-calibrated band fails a "
      "hard point-estimate floor at nominal about half the time (NF1.8 §3). A newest cohort that misses "
      "badly is a reason to LOOK, because it will move the pooled number next year.")
    p("")
    nrows = []
    for b in out["blocks"]:
        nc = b.get("newest_cohort") or {}
        if not nc:
            continue
        nrows.append({"population": b["population"], "cohort": nc.get("cohort"), "n": nc.get("n"),
                      "pooled coverage": nc.get("pooled_coverage"),
                      **{f"cov {k}": v for k, v in (nc.get("coverage") or {}).items()}})
    p(_md(pd.DataFrame(nrows)))
    p("")
    p("## What to do on a breach")
    p("")
    p("1. **Do NOT adjust the floor.** A floor that moves until something clears it is not a floor "
      "(E2.1-r; NF1.8 §1). ⭐ That prohibition BINDS HARDER after NF-D22, not less: the false-reject "
      "target is not a tuning knob, it is NF1.8's own pre-registered level, and a breach under a "
      "calibrated rule is now genuine evidence rather than a coin toss. The one honest response is "
      "to re-select (or, for K/DST, to widen).")
    p("2. Re-run the bake-off for the breaching population — it re-selects under the same "
      "pre-registered floor, anchors and deflation:")
    p("")
    p("```")
    p("# rookies (NF1.8):")
    p("uv run python -m quant_sports_intel_models.football.nfl.fantasy."
      "run_rookie_perposition_ablation")
    p("# veterans (NF1.9):")
    p("uv run python -m quant_sports_intel_models.football.nfl.fantasy."
      "run_veteran_interval_ablation --rebuild-panel")
    p("```")
    p("")
    p("   ⭐ **EXCEPT for the NF1.6 K/DST population, whose response is different by design.** That "
      "band is *reported, not selected* — a deliberately BASE band with no candidate field behind "
      "it — so there is no bake-off to re-run. Widen it honestly instead and re-report:")
    p("")
    p("```")
    p("# K/DST (NF1.6) — widen, do not re-select:")
    p("uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_kdst_projection \\")
    p("  --rebuild-panel --widen 1.15    # or raise kdst_projection.BAND_CLUSTER_Z")
    p("```")
    p("")
    p("   Widening is monotone by construction (it inflates the half-widths around 1.0, so it can "
      "only ever widen, never sharpen one side — the NF1.7 (d) widen-only invariant).")
    p("")
    p("3. ⚠️ **Rookie RB is the position to watch** — NF1.8 shipped it with **0 rows** of slack above "
      "its floor, so it is the one a new class breaks first.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="standing annual re-validation of the rookie + veteran interval floors")
    ap.add_argument("--rookie-pool", default=str(NF17._POOL_CACHE))
    ap.add_argument("--veteran-panel", default=str(NF19._PANEL_CACHE))
    ap.add_argument("--rookie-from", type=int, default=2019)
    ap.add_argument("--rookie-to", type=int, default=2025)
    ap.add_argument("--veteran-from", type=int, default=NF19._FOLD_FROM)
    ap.add_argument("--veteran-to", type=int, default=NF19._FOLD_TO)
    ap.add_argument("--rebuild-panel", action="store_true",
                    help="rebuild the veteran band panel from the local NFL marts first (do this "
                         "after a new completed season lands)")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default="main_nfl_marts")
    ap.add_argument("--kdst-panel", default=None,
                    help="NF1.6 K/DST walk-forward band panel (default: the run_kdst_projection cache)")
    ap.add_argument("--rebuild-kdst-panel", action="store_true",
                    help="rebuild the NF1.6 K/DST band panel from the local NFL marts + lake first "
                         "(do this after a new completed season lands)")
    ap.add_argument("--only", choices=("rookies", "veterans", "kdst"), default=None)
    ap.add_argument("--no-report", action="store_true",
                    help="compute + print, write NOTHING. ⭐ This previously still rewrote the "
                         "decided JSON — a --no-report that writes is not a --no-report.")
    ap.add_argument("--out", default=DEFAULT_STEM,
                    help=f"output stem under ablation_results/ (default {DEFAULT_STEM!r}). Pass "
                         f"--out {DECIDED_STEM} to DELIBERATELY refresh NF1.9's decided record.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    from quant_sports_intel_models.football.nfl.fantasy import run_kdst_projection as NF16
    kdst_panel = Path(args.kdst_panel) if args.kdst_panel else NF16._PANEL_CACHE

    if args.rebuild_panel:
        NF19.rebuild_panel(args.duckdb, args.schema, 2007, args.veteran_to)
    if args.rebuild_kdst_panel:
        log.info("rebuilding the NF1.6 K/DST band panel …")
        NF16.main(["--duckdb", args.duckdb, "--rebuild-panel", "--no-report"])

    blocks = []
    if args.only not in ("veterans", "kdst"):
        blocks.append(revalidate_rookies(Path(args.rookie_pool), args.rookie_from, args.rookie_to))
    if args.only not in ("rookies", "kdst"):
        blocks.append(revalidate_veterans(Path(args.veteran_panel), args.veteran_from,
                                          args.veteran_to))
    # ⭐ NF1.6 — the K/DST base band. Included by DECISION (see the module docstring): a brand-new
    #    band left unmonitored is exactly the gap that let the veteran band go five stories at 0.55
    #    of nominal.
    if args.only not in ("rookies", "veterans"):
        blocks.append(revalidate_kdst(kdst_panel))
    # ⚠️ An ERRORED block is NOT a pass. A re-validation that silently skips a population it could not
    #    load is the NF1.7 anchor lesson (an absent check passes on NOTHING) wearing an ops hat.
    ok = all(b.get("pass") is True for b in blocks)
    out = {"pass": bool(ok), "blocks": blocks,
           "generated_at": datetime.now(timezone.utc).isoformat()}

    print("\n=== interval-band re-validation ===")
    for b in blocks:
        if b.get("error"):
            print(f"🚨 {b['population']}: ERROR — {b['error']}")
            continue
        print(f"\n{b['population']}  ({b['config']}, form={b.get('form')}) — "
              f"{b['n']} held-out rows over cohorts {b['cohorts'][0]}–{b['cohorts'][-1]}; "
              f"pooled coverage {b['pooled_coverage']}, IS80 {b['interval_score']}")
        for p in sorted(b["coverage"]):
            fl = b["floors"].get(p)
            cov = b["coverage"].get(p)
            mark = "—" if fl is None else ("✅" if (cov or 0) >= fl else "🚨 BREACH")
            prev = (b.get("slack_rows_at_nominal") or {}).get(p)
            print(f"   {p:>3s}: cov {cov} floor {fl if fl is not None else 'unconstrained':>12} "
                  f"slack {b['slack_rows'].get(p)} rows  {mark}"
                  f"   (previous rule: floor {(b.get('floors_at_nominal') or {}).get(p)}, "
                  f"slack {prev} rows)")
        nc = b.get("newest_cohort") or {}
        if nc:
            print(f"   newest cohort {nc.get('cohort')} (leading indicator only): n={nc.get('n')} "
                  f"pooled cov={nc.get('pooled_coverage')} {nc.get('coverage')}")
    print(f"\nVERDICT: {'✅ ALL FLOORS MET' if ok else '🚨 FLOOR BREACH — RE-SELECTION TRIGGERED'}")

    # ⭐ `--no-report` now writes NOTHING AT ALL. The JSON write used to sit OUTSIDE this branch,
    #    so `--no-report` rewrote NF1.9's decided record anyway — the defect NF-INJ3b hit.
    if not args.no_report:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (_REPORT_DIR / f"{args.out}.json").write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"{args.out}.md")
        print(f"wrote {args.out}.json + {args.out}.md")
        if args.out != DECIDED_STEM:
            print(f"  ⚠️ NF1.9's decided record ({DECIDED_STEM}.*) was NOT updated. To refresh it "
                  f"deliberately: --out {DECIDED_STEM}")
    # ⭐ NON-ZERO EXIT ON A BREACH — the trigger, not a log line.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
