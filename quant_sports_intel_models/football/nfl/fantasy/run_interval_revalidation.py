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

from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
    run_veteran_interval_ablation as NF19,
)

log = logging.getLogger("nfl.fantasy.interval_revalidation")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_OUT_JSON = _REPORT_DIR / "nf1_9_interval_revalidation.json"
_OUT_MD = _REPORT_DIR / "nf1_9_interval_revalidation.md"


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
    """The pooled per-position floor read for one population — the BINDING check."""
    floors = NF18.position_floors(rec, positions, tier=1, **floor_kwargs)
    misses = NF18.floor_misses(rec, floors)
    return {
        "floors": floors,
        "coverage": {p: rec.get(f"cov_{p}") for p in positions},
        "n_by_position": {p: rec.get(f"n_{p}") for p in positions},
        "slack_rows": NF18.floor_slack_rows(rec, floors),
        "unconstrained": [p for p in positions if p not in floors],
        "misses": misses,
        "pass": not misses,
        "pooled_coverage": rec.get("coverage_80"),
        "interval_score": rec.get("interval_score"),
    }


def revalidate_rookies(pool_path: Path, from_year: int, to_year: int) -> dict:
    """Re-score NF1.8's shipped rookie band on every available held-out draft class."""
    pool = NF17.load_pool(pool_path)
    folds = NF17.build_folds(pool, list(range(from_year, to_year + 1)))
    if len(folds) < 2:
        return {"population": "rookies", "error": f"only {len(folds)} usable draft classes"}
    cfg = shipped_rookie_cfg()
    rec = NF18.run_arm(folds, cfg)
    if rec is None:
        return {"population": "rookies", "error": "the shipped rookie band did not score"}
    POS = sorted({k[4:] for k in rec if k.startswith("cov_")})
    out = {"population": "rookies", "config": cfg["label"], "form": cfg.get("form"),
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
    floors = {p: KD.NOMINAL_COVERAGE for p in positions if rep.get(f"n_{p}")}
    misses = [p for p, f in floors.items() if (rep.get(f"cov_{p}") or 0.0) < f]
    cohorts = [int(v) for v in sorted(panel["target_season"].unique())]
    out = {
        "population": "kdst",
        "config": (f"SHIPPED K/DST base band (q{KD.BAND_QUANTILES[0]:.2f}/"
                   f"q{KD.BAND_QUANTILES[1]:.2f} ratio quantiles, cluster_z={z})"),
        "form": "empirical_ratio_band",
        "cohorts": rep.get("held_out_seasons", cohorts),
        "n": rep["n"],
        "floors": floors,
        "coverage": {p: rep.get(f"cov_{p}") for p in floors},
        "n_by_position": {p: rep.get(f"n_{p}") for p in floors},
        # margin in ROWS, the NF1.8 convention — "0.83 vs 0.80" reads like a calibration statement;
        # "12 covered rows of slack" is the number that says how close this actually is
        "slack_rows": {p: int(np.floor((rep.get(f"cov_{p}") or 0.0) * (rep.get(f"n_{p}") or 0))
                             - np.ceil(f * (rep.get(f"n_{p}") or 0)))
                       for p, f in floors.items()},
        "unconstrained": [p for p in positions if p not in floors],
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
        rows.append({
            "population": block["population"], "position": p,
            "n (held-out)": block["n_by_position"].get(p),
            "coverage": cov,
            "floor": floor if floor is not None else "unconstrained (n below the pre-registered "
                                                     "minimum)",
            "slack (rows)": block["slack_rows"].get(p),
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
      "(E2.1-r; NF1.8 §1).")
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
    ap.add_argument("--no-report", action="store_true")
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
            print(f"   {p:>3s}: cov {cov} floor {fl if fl is not None else 'unconstrained':>12} "
                  f"slack {b['slack_rows'].get(p)} rows  {mark}")
        nc = b.get("newest_cohort") or {}
        if nc:
            print(f"   newest cohort {nc.get('cohort')} (leading indicator only): n={nc.get('n')} "
                  f"pooled cov={nc.get('pooled_coverage')} {nc.get('coverage')}")
    print(f"\nVERDICT: {'✅ ALL FLOORS MET' if ok else '🚨 FLOOR BREACH — RE-SELECTION TRIGGERED'}")

    _OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _OUT_MD)
    # ⭐ NON-ZERO EXIT ON A BREACH — the trigger, not a log line.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
