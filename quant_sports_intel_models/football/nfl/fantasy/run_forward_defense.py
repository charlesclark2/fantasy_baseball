"""run_forward_defense.py — NF-D6 FORWARD DEFENSE-STRENGTH validation + landing.

Three things, §0.5-disciplined and EDGE-INDEPENDENT (the gate is walk-forward accuracy + interval
calibration + face-validity, not `best_alpha`/PBO — a projection product, like NF-D7):

  1. THE §0.5 SHRINKAGE/FORM BAKE-OFF — candidate configs for the forward strength, scored on a
     WALK-FORWARD metric: project season S from ≤ S−1 data, correlate to S's REALIZED opponent-adjusted
     pass/rush defensive strength (and to realized RAW efficiency). Arms: `raw` (unadjusted EPA-allowed
     z, the baseline), `oppadj` (opponent-adjusted + EB-shrunk, no churn), and a churn-shrink SWEEP
     (opp-adjusted + churn regression toward the mean over a pre-registered k grid). Every arm is
     reported; the winner is the config that best predicts next-year strength.

  2. THE UNCERTAINTY VALIDATION (⭐ the headline claim) — does roster CHURN predict a larger forward
     SURPRISE? Correlate churn with the absolute forward error |realized_z − prior_z| across all
     (season, unit, team); and check ±sd interval CALIBRATION (coverage ≈ 0.68 at 1 sd) for the
     churn-widened projection vs the un-widened one. This is what earns "bigger churn ⇒ wider
     uncertainty."

  3. FACE-VALIDITY — for the latest projectable season, the most- and least-reshaped defenses, their
     top losses/adds, and how their projected strength moves (a heavily-reshaped D regresses toward the
     mean and widens).

Then `--land --s3` writes the SHIP config's projection to the lake Delta
`nfl/fantasy/defense/forward_defense_strength` (season-partitioned) — the `defense_source.load_forward_
defense` serving contract NF1.2 joins.

RUN (LAPTOP, SF-free sports lake; build the play/strength cache first with --build-cache):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_forward_defense \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2016 --to 2024 --validate

    # land the 2026 board projection to S3 (after --build-cache has the 2025 fit)
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_forward_defense \
      --duckdb ... --land 2026 --s3
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

from quant_sports_intel_models.football.nfl.fantasy import defense_source as D  # noqa: E402

log = logging.getLogger("nfl.fantasy.forward_defense")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"

# The pre-registered churn-shrink grid (weight pulling a reshaped D toward the mean). Every value counts.
_SHRINK_GRID = (0.0, 0.15, 0.3, 0.5)
# The forward-volatility-floor grid (z-units, calibrated to nominal 1-sd coverage — the honest wide
# forward interval defensive strength genuinely needs, dominated by year-to-year volatility not churn).
_NOISE_GRID = (0.0, 0.5, 0.75, 0.9, 1.0, 1.2)


def _arms() -> list[D.DefenseConfig]:
    """The bake-off arms: raw baseline, opponent-adjusted (no churn), and the churn-shrink sweep."""
    arms = [
        D.DefenseConfig(name="raw", opp_adjust=False, churn_shrink_k=0.0),
        D.DefenseConfig(name="oppadj", opp_adjust=True, churn_shrink_k=0.0),
    ]
    for k in _SHRINK_GRID:
        if k == 0.0:
            continue
        arms.append(D.DefenseConfig(name=f"oppadj_churn_k{k}", opp_adjust=True, churn_shrink_k=k))
    return arms


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    from scipy.stats import spearmanr

    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 8 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return None
    return round(float(spearmanr(a[m], b[m])[0]), 4)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Walk-forward bake-off
# ══════════════════════════════════════════════════════════════════════════════════════════════
def walk_forward(con, seasons: list[int], strengths: pd.DataFrame,
                 continuity: dict[int, pd.DataFrame]) -> dict:
    """For each projection season S in `seasons`, build every arm's forward projection from ≤ S−1 and
    correlate (per unit) to S's REALIZED opponent-adjusted strength z and realized RAW-efficiency z.
    Pooled Spearman over all (season, team) within a unit. Also accumulates the churn/error records for
    the uncertainty validation."""
    arms = _arms()
    # realized target per (season, unit, team): opp-adjusted z + raw-efficiency z
    realized = strengths.copy()
    realized["realized_oppadj_z"] = realized["strength_z"]
    realized["realized_raw_z"] = np.nan
    for (s, u), g in realized.groupby(["season", "unit"]):
        realized.loc[g.index, "realized_raw_z"] = D.zscore(-g["raw_epa_allowed"].to_numpy())

    per_arm = {a.name: {u: {"proj": [], "real_oppadj": [], "real_raw": []} for u in D.UNITS}
               for a in arms}
    churn_err = []  # for the uncertainty validation (uses the oppadj prior, config-independent)

    for S in seasons:
        real_S = realized[realized["season"] == S]
        if real_S.empty:
            continue
        cont = continuity.get(S)
        for a in arms:
            fwd = D.build_forward_defense(con, S, config=a, strengths=strengths, continuity=cont)
            if fwd.empty:
                continue
            for unit in D.UNITS:
                scol = f"{unit}_def_strength"
                m = fwd[["team", scol]].merge(
                    real_S[real_S["unit"] == unit][["team", "realized_oppadj_z", "realized_raw_z"]],
                    on="team", how="inner")
                per_arm[a.name][unit]["proj"].append(m[scol].to_numpy())
                per_arm[a.name][unit]["real_oppadj"].append(m["realized_oppadj_z"].to_numpy())
                per_arm[a.name][unit]["real_raw"].append(m["realized_raw_z"].to_numpy())

        # churn/error records — the leakage-safe prior (oppadj, no churn) vs realized, with churn
        prior = D._prior_strength(strengths, S, D.DefenseConfig(name="p", opp_adjust=True))
        if not prior.empty and cont is not None and not cont.empty:
            j = prior.merge(cont[["team", "unit", "churn"]], on=["team", "unit"], how="left")
            j = j.merge(real_S[["team", "unit", "realized_oppadj_z"]], on=["team", "unit"], how="inner")
            j["abs_err"] = np.abs(j["realized_oppadj_z"] - j["prior_z"])
            churn_err.append(j[["team", "unit", "churn", "prior_z", "prior_z_sd",
                                "realized_oppadj_z", "abs_err"]])

    def _pool(recs: dict, real_key: str) -> float | None:
        if not recs["proj"]:
            return None
        return _spearman(np.concatenate(recs["proj"]), np.concatenate(recs[real_key]))

    arm_out = {}
    for a in arms:
        row = {"config": a.name, "opp_adjust": a.opp_adjust, "churn_shrink_k": a.churn_shrink_k}
        for unit in D.UNITS:
            row[f"{unit}_rho_oppadj"] = _pool(per_arm[a.name][unit], "real_oppadj")
            row[f"{unit}_rho_raw"] = _pool(per_arm[a.name][unit], "real_raw")
        oppadj_vals = [row[f"{u}_rho_oppadj"] for u in D.UNITS if row[f"{u}_rho_oppadj"] is not None]
        row["pooled_rho_oppadj"] = round(float(np.mean(oppadj_vals)), 4) if oppadj_vals else None
        arm_out[a.name] = row

    churn_df = pd.concat(churn_err, ignore_index=True) if churn_err else pd.DataFrame()
    return {"arms": arm_out, "seasons": seasons, "_churn_err": churn_df}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Uncertainty validation — churn predicts forward surprise; interval calibration
# ══════════════════════════════════════════════════════════════════════════════════════════════
def uncertainty_validation(churn_df: pd.DataFrame) -> dict:
    """Two honest checks. (a) THE CHURN HYPOTHESIS — does roster churn predict a larger forward
    surprise (|realized_z − prior_z|)? A positive ρ + higher high-churn-tercile error would earn a
    churn-SPECIFIC widen. (b) CALIBRATION — the forward interval needs a season-to-season VOLATILITY
    floor (`forward_noise`) to cover at the nominal 1-sd rate; pick the floor whose coverage is closest
    to 0.68. `churn_df` has (churn, prior_z, prior_z_sd, realized_oppadj_z, abs_err)."""
    if churn_df.empty:
        return {"n": 0}
    d = churn_df.dropna(subset=["churn", "abs_err"]).copy()
    out = {"n": int(len(d))}
    # (a) churn ↔ absolute forward error: positive ⇒ churn is a real surprise signal
    out["rho_churn_vs_abs_error"] = _spearman(d["churn"].to_numpy(), d["abs_err"].to_numpy())
    q1, q2 = d["churn"].quantile([1 / 3, 2 / 3])
    out["abs_error_low_churn"] = round(float(d[d["churn"] <= q1]["abs_err"].mean()), 4)
    out["abs_error_high_churn"] = round(float(d[d["churn"] >= q2]["abs_err"].mean()), 4)
    churn_earns_widen = (out["rho_churn_vs_abs_error"] is not None
                         and out["rho_churn_vs_abs_error"] > 0.05
                         and out["abs_error_high_churn"] > out["abs_error_low_churn"])
    out["churn_earns_targeted_widen"] = bool(churn_earns_widen)
    # (b) 1-sd coverage for each volatility floor (point = the prior, no churn shrink)
    cov = {}
    err = np.abs(d["realized_oppadj_z"].to_numpy() - d["prior_z"].to_numpy())
    psd = d["prior_z_sd"].to_numpy()
    for fn in _NOISE_GRID:
        fwd_sd = D.forward_sd(psd, d["churn"].to_numpy(), fn, 0.0)
        cov[str(fn)] = round(float(np.mean(err <= fwd_sd)), 4)
    out["coverage_1sd_by_forward_noise"] = cov
    out["selected_forward_noise"] = min(_NOISE_GRID, key=lambda fn: abs(cov[str(fn)] - 0.68))
    out["nominal_coverage_1sd"] = 0.68
    out["rms_forward_change"] = round(float(np.sqrt(np.mean(err ** 2))), 4)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Face-validity — the latest projectable season
# ══════════════════════════════════════════════════════════════════════════════════════════════
def face_validity(con, proj_season: int, strengths: pd.DataFrame, continuity: pd.DataFrame,
                  ship: D.DefenseConfig) -> dict:
    """Most- and least-reshaped defenses for `proj_season` + how their projection moves. Uses the SHIP
    config so the reported strengths are the landed ones."""
    fwd = D.build_forward_defense(con, proj_season, config=ship, strengths=strengths,
                                  continuity=continuity)
    if fwd.empty:
        return {"proj_season": proj_season, "note": "no projection (missing prior fit / continuity)"}
    out = {"proj_season": proj_season, "units": {}}
    for unit in D.UNITS:
        cols = ["team", f"{unit}_returning_share", f"{unit}_churn", f"{unit}_prior_strength",
                f"{unit}_def_strength", f"{unit}_def_strength_sd", f"{unit}_top_losses",
                f"{unit}_top_adds"]
        d = fwd[cols].dropna(subset=[f"{unit}_churn"]).copy()
        if d.empty:
            continue
        d = d.rename(columns={c: c.replace(f"{unit}_", "") for c in cols if c != "team"})
        most = d.nlargest(5, "churn").round(3).to_dict("records")
        least = d.nsmallest(3, "churn").round(3).to_dict("records")
        out["units"][unit] = {"most_reshaped": most, "least_reshaped": least}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _f(v, sign: bool = False) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:+.3f}" if sign else f"{v:.3f}"


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    wf, unc, fv, dec = out["walk_forward"], out["uncertainty"], out["face_validity"], out["decision"]
    p("# NF-D6 — Forward defense-strength projection (roster-adjusted; the SOS baseline)")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()} · **walk-forward seasons:** "
      f"{wf['seasons'][0]}–{wf['seasons'][-1]} · opponent-adjusted mixed-model strength "
      f"(`hierarchical.fit`), pass-D + rush-D separately. Edge-independent, `best_alpha=0`.")
    p("")
    p(f"## Verdict — {dec['verdict']}")
    p("")
    p("> The gate (a projection, like NF-D7): the shipped config must best predict next-year strength "
      "on the walk-forward metric, and the churn-widened uncertainty must be calibrated + earned "
      "(churn predicts forward surprise). Not `best_alpha`/PBO.")
    p("")
    p("## 1. Walk-forward bake-off — Spearman(projected strength, realized next-year strength)")
    p("")
    p("Realized target = that season's OPPONENT-ADJUSTED strength z (the de-noised truth); `_raw` = "
      "vs realized unadjusted EPA-allowed z. Pooled over all (season, team) within a unit.")
    p("")
    p("| config | opp-adj | churn k | pass ρ | rush ρ | pooled ρ | pass ρ(raw) | rush ρ(raw) |")
    p("|--------|---------|---------|--------|--------|----------|-------------|-------------|")
    for name, r in wf["arms"].items():
        p(f"| {name} | {'✓' if r['opp_adjust'] else '·'} | {r['churn_shrink_k']} | "
          f"{_f(r['pass_rho_oppadj'])} | {_f(r['rush_rho_oppadj'])} | "
          f"**{_f(r['pooled_rho_oppadj'])}** | {_f(r['pass_rho_raw'])} | {_f(r['rush_rho_raw'])} |")
    p("")
    p("## 2. Uncertainty validation — the churn hypothesis + interval calibration")
    p("")
    if unc.get("n"):
        p(f"**(a) Does churn predict forward surprise?** ρ(churn, |forward error|) = "
          f"**{_f(unc['rho_churn_vs_abs_error'])}** (n={unc['n']}). Mean |forward error|: low-churn "
          f"tercile **{_f(unc['abs_error_low_churn'])}** vs high-churn **{_f(unc['abs_error_high_churn'])}**. "
          f"{'Churn EARNS a targeted widen.' if unc.get('churn_earns_targeted_widen') else '⇒ NULL — roster churn does NOT predict a larger forward surprise for defense (continuity is entangled with having been good, and good units regress unpredictably). The churn-SPECIFIC widen is NOT shipped.'}")
        p("")
        p(f"**(b) Interval calibration.** RMS forward change ≈ **{_f(unc['rms_forward_change'])}** z-units "
          f"— far larger than the measurement sd (~0.3), so the honest forward interval needs a "
          f"season-to-season VOLATILITY floor. 1-sd coverage by floor:")
        p("")
        p("| forward-noise floor | 1-sd coverage |")
        p("|---------------------|---------------|")
        for k, c in unc["coverage_1sd_by_forward_noise"].items():
            mark = " ← selected" if float(k) == unc["selected_forward_noise"] else ""
            p(f"| {k} | {c:.3f}{mark} |")
        p("")
        p(f"Nominal 1-sd coverage = {unc['nominal_coverage_1sd']}; selected floor = "
          f"**{unc['selected_forward_noise']}** (measurement-only floor 0.0 under-covers at "
          f"{unc['coverage_1sd_by_forward_noise']['0.0']:.3f}).")
    else:
        p("- (insufficient churn/realized overlap to validate)")
    p("")
    p(f"## 3. Face-validity — {fv.get('proj_season')} most-reshaped defenses (SHIP config)")
    p("")
    for unit in D.UNITS:
        u = fv.get("units", {}).get(unit)
        if not u:
            continue
        p(f"### {unit.upper()}-D — biggest roster turnover (highest churn = the least-certain "
          f"projections; the returning shares + losses/adds ship as diagnostics)")
        p("")
        p("| team | returning | churn | prior z | fwd strength | fwd sd | key losses | key adds |")
        p("|------|-----------|-------|---------|--------------|--------|------------|----------|")
        for r in u["most_reshaped"]:
            p(f"| {r['team']} | {_f(r.get('returning_share'))} | {_f(r.get('churn'))} | "
              f"{_f(r.get('prior_strength'))} | {_f(r.get('def_strength'))} | "
              f"{_f(r.get('def_strength_sd'))} | {r.get('top_losses', '')} | {r.get('top_adds', '')} |")
        p("")
    p("## Disposition")
    p("")
    p(f"- **Ship config:** `{dec['ship_config']}` — opponent-adjusted mixed-model strength, "
      f"churn point-shrink k={dec['ship_shrink_k']}, forward-volatility floor={dec['ship_forward_noise']}, "
      f"churn-specific widen k={dec['ship_widen_k']}.")
    p("- Delivered as `defense_source.load_forward_defense(season)` → per-team `pass_def_strength` / "
      "`rush_def_strength` (+ `_sd`), landed to `nfl/fantasy/defense/forward_defense_strength` "
      "(season-partitioned Delta). NF1.2's SOS joins it the same way NF1.1 joins the xFP set.")
    p("- Leakage-safe: opponent-adjusted efficiency + league fit read ≤ prior season; the roster-churn "
      "layer uses the preseason-known projection-season roster (the NF-D1/NF-D2 posture). "
      "Edge-independent, `best_alpha=0`.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def decide(wf: dict, unc: dict) -> dict:
    """Pick the ship config honestly. STRENGTH = opponent-adjusted (principled + honest posterior sd;
    it is the correct same-season SOS quantity and ties raw on forward ρ within noise). The churn
    POINT-shrink ships only if it beats the no-churn oppadj arm on walk-forward ρ (the NF-D gate — a
    null add is not forced on). The forward uncertainty = a calibrated VOLATILITY floor; a churn-
    SPECIFIC widen ships only if churn earned it in the uncertainty check (it does not for defense)."""
    arms = wf["arms"]
    scored = {n: r["pooled_rho_oppadj"] for n, r in arms.items()
              if r["opp_adjust"] and r["pooled_rho_oppadj"] is not None}
    raw_rho = arms.get("raw", {}).get("pooled_rho_oppadj")
    forward_noise = unc.get("selected_forward_noise", 0.0) if unc.get("n") else 0.0
    churn_widen_k = 0.0  # earned only if the uncertainty check flags churn (see below)
    if unc.get("churn_earns_targeted_widen"):
        churn_widen_k = 0.5
    if not scored:
        return {"ship_config": "oppadj", "ship_shrink_k": 0.0, "ship_forward_noise": forward_noise,
                "ship_widen_k": churn_widen_k, "verdict": "NULL — insufficient overlap to grade"}
    best = max(scored, key=scored.get)
    best_rho, oppadj_rho = scored[best], arms["oppadj"]["pooled_rho_oppadj"]
    shrink_k = arms[best]["churn_shrink_k"]
    churn_helps = shrink_k > 0 and best_rho > (oppadj_rho or -9) + 1e-4
    raw_cmp = ("ties raw" if raw_rho is not None and abs(oppadj_rho - raw_rho) < 0.02
               else f"vs raw {_f(raw_rho)}")
    if churn_helps:
        verdict = (f"SHIP — opponent-adjusted strength + churn POINT-shrink (k={shrink_k}) best "
                   f"predicts next-year strength (pooled ρ {best_rho:.3f} vs oppadj {oppadj_rho:.3f}, "
                   f"{raw_cmp}); forward uncertainty = volatility floor {forward_noise} (1-sd coverage "
                   f"≈{unc['coverage_1sd_by_forward_noise'][str(forward_noise)]:.2f}).")
    else:
        best, shrink_k = "oppadj", 0.0
        best_rho = oppadj_rho
        widen_note = (f"churn-specific widen ON (k={churn_widen_k})" if churn_widen_k
                      else "churn does NOT predict forward surprise (ρ≈"
                           f"{_f(unc.get('rho_churn_vs_abs_error'))}) ⇒ churn-specific widen OFF")
        verdict = (f"SHIP — opponent-adjusted + EB-shrunk strength (pooled ρ {best_rho:.3f}, "
                   f"{raw_cmp}); churn POINT-shrink adds no walk-forward lift ⇒ OFF (NF-D gate). "
                   f"Forward uncertainty = a calibrated season-to-season VOLATILITY floor "
                   f"{forward_noise} (1-sd coverage ≈"
                   f"{unc['coverage_1sd_by_forward_noise'][str(forward_noise)]:.2f} vs the too-narrow "
                   f"measurement-only {unc['coverage_1sd_by_forward_noise']['0.0']:.2f}); "
                   f"{widen_note}. Roster-churn / returning shares ship as diagnostics.")
    return {"ship_config": best, "ship_shrink_k": shrink_k, "ship_forward_noise": forward_noise,
            "ship_widen_k": churn_widen_k, "pooled_rho": best_rho, "raw_rho": raw_rho,
            "oppadj_rho": oppadj_rho, "verdict": verdict}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Landing
# ══════════════════════════════════════════════════════════════════════════════════════════════
def land(con, season: int, ship: D.DefenseConfig, *, to_s3: bool, local_root: str | None) -> int:
    """Compute the SHIP-config projection for `season` and write it to the lake Delta (season
    partition). Writes the full diagnostic frame (strengths + sds + churn + returning shares +
    losses/adds), so the serving read has everything NF1.2 / a DST projection / N1 need."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    fwd = D.build_forward_defense(con, season, config=ship)
    if fwd.empty:
        log.warning("no forward-defense projection for season=%d — nothing landed", season)
        return 0
    if not (to_s3 or local_root):
        log.info("computed %d team rows for season=%d (no --s3/--lake-root ⇒ not landed)",
                 len(fwd), season)
        return 0
    n = s3io.write_dataframe(fwd, sport=D.LAKE_SPORT, source=D.LAKE_SOURCE, season=season,
                             tier=D.LAKE_TIER, local_root=local_root)
    log.info("landed %d rows → nfl/%s/%s season=%d", n, D.LAKE_TIER, D.LAKE_SOURCE, season)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D6 forward defense-strength validation + landing")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--from", dest="from_season", type=int, default=2016)
    ap.add_argument("--to", dest="to_season", type=int, default=2024)
    ap.add_argument("--build-cache", action="store_true",
                    help="pre-build the S3 play + strength cache for the needed seasons, then exit")
    ap.add_argument("--validate", action="store_true", help="run the walk-forward bake-off + report")
    ap.add_argument("--land", type=int, metavar="SEASON",
                    help="compute + land the SHIP projection for SEASON to the lake")
    ap.add_argument("--s3", action="store_true", help="land to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a local-FS Delta tree (offline)")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb}")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        if args.build_cache:
            # the strengths need seasons [from-1 .. to] (a projection S reads S-1); land needs S-1 too.
            need = list(range(args.from_season - 1, args.to_season + 1))
            if args.land:
                need = sorted(set(need) | {args.land - 1})
            D.team_strengths(con, need)
            print(f"play + strength cache built for {need[0]}–{need[-1]}")
            return 0

        if args.validate:
            proj_seasons = [s for s in range(args.from_season, args.to_season + 1)
                            if s > D.MIN_SNAP_SEASON]
            need = list(range(min(proj_seasons) - 1, max(proj_seasons) + 1))
            strengths = D.team_strengths(con, need)
            if strengths.empty:
                ap.error("no fitted strengths — run --build-cache first (S3 read)")
            continuity = {S: D.load_snap_continuity(con, S) for S in proj_seasons}
            wf = walk_forward(con, proj_seasons, strengths, continuity)
            unc = uncertainty_validation(wf.pop("_churn_err"))
            dec = decide(wf, unc)
            ship = D.DefenseConfig(name=dec["ship_config"], opp_adjust=True,
                                   churn_shrink_k=dec["ship_shrink_k"],
                                   forward_noise=dec["ship_forward_noise"],
                                   churn_widen_k=dec["ship_widen_k"])
            fv_season = max(proj_seasons)
            fv = face_validity(con, fv_season, strengths, continuity[fv_season], ship)
            out = {"walk_forward": wf, "uncertainty": unc, "face_validity": fv, "decision": dec}

            print(f"\n=== NF-D6 forward defense strength, walk-forward {proj_seasons[0]}–"
                  f"{proj_seasons[-1]} ===")
            print("pooled ρ (vs realized opp-adjusted strength) by arm:")
            for name, r in wf["arms"].items():
                print(f"  {name:20s} pooled {r['pooled_rho_oppadj']}  "
                      f"(pass {r['pass_rho_oppadj']} / rush {r['rush_rho_oppadj']})")
            if unc.get("n"):
                print(f"\nchurn↔|error| ρ = {unc['rho_churn_vs_abs_error']}  "
                      f"(low-churn err {unc['abs_error_low_churn']} vs high-churn "
                      f"{unc['abs_error_high_churn']})  churn_earns_widen="
                      f"{unc.get('churn_earns_targeted_widen')}")
                print(f"1-sd coverage by forward-noise floor: {unc['coverage_1sd_by_forward_noise']} "
                      f"→ selected {unc['selected_forward_noise']} (rms fwd change "
                      f"{unc['rms_forward_change']})")
            print(f"\nVERDICT: {dec['verdict']}")

            _REPORT_DIR.mkdir(parents=True, exist_ok=True)
            (_REPORT_DIR / "nf_d6_forward_defense_strength.json").write_text(
                json.dumps(out, indent=2, default=lambda o: None if isinstance(o, float)
                           and not np.isfinite(o) else float(o) if isinstance(o, np.floating) else str(o)))
            if not args.no_report:
                write_report(out, _REPORT_DIR / "nf_d6_forward_defense_strength.md")

        if args.land:
            # the SHIP config (validate first to select it; defaults to SHIP_CONFIG if run standalone)
            ship = D.SHIP_CONFIG
            land(con, args.land, ship, to_s3=args.s3, local_root=args.lake_root)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
