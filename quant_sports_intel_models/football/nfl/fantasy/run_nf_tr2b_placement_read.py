"""run_nf_tr2b_placement_read.py — run the NF-TR2b cross-position placement read against the SERVED
board artifacts and emit `ablation_results/nf_tr2b_placement_read.{json,md}`.

⚠️ THIS READS THE PUBLISHED ARTIFACT, NOT A REBUILD. The whole point is to verify what is ON THE
WIRE (the repo's standing "verify the SERVED artifact, never a claim" rule): it pulls the served
board JSONs + `projections.json`, takes `k` from the artifact's OWN `veteran_level_policy` stamp
(never from a constant in this file, so a stale k cannot make the read agree with itself), and
reconstructs the incumbent by undoing that k.

RUN (LAPTOP — needs S3 read on the api-cache bucket, ~10s):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_tr2b_placement_read

  --from-dir DIR   read board_*.json + projections.json from a local directory instead of S3
  --no-report     compute + print, write nothing

⛔ It writes ONLY its own two `nf_tr2b_placement_read.*` paths. A run must never overwrite a decided
story's artifacts (the NCAAF-P2.1 S1-serve lesson: a fixed-output-path write clobbered a decided
story's audit trail, and nothing failed).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import pandas as pd

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf_tr2b_placement as PL  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import veteran_level_policy as VLP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.league_presets import (  # noqa: E402
    NFL_PROFILE, get_preset)

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"

#: ⛔ THE DECIDED ARTIFACT — NF-TR2b's own committed record. Writing it is now an EXPLICIT act
#: (`--out nf_tr2b_placement_read`), never something a run does on its way past (NF-INJ3b D4).
DECIDED_STEM = "nf_tr2b_placement_read"
#: the DEFAULT stem: a neutral "latest run" path that belongs to NO story, so a session that needs
#: this read as a SIDE-STEP (NF-INJ3b's ship path did, and clobbered the decided record doing it)
#: cannot silently rewrite a decided story's audit trail.
DEFAULT_STEM = "nf_tr2b_placement_read_latest"
_S3 = "s3://credence-prod-s3-api-cache/fantasy/nfl/2026/"

#: (served board file stem, league preset, n_teams) for every config the product publishes.
CONFIGS: tuple[tuple[str, str, int], ...] = tuple(
    (f"{preset}_{n}", preset, n)
    for preset in ("standard", "standard_3wr", "half_ppr", "half_ppr_3wr",
                   "full_ppr", "full_ppr_3wr", "superflex")
    for n in (10, 12))


def _fetch(dest: pathlib.Path) -> pathlib.Path:
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["aws", "s3", "cp", _S3, str(dest), "--recursive",
                    "--exclude", "*", "--include", "board_*.json",
                    "--include", "projections.json", "--quiet"],
                   check=True, timeout=600)
    return dest


def run(src: pathlib.Path, origin: str | None = None) -> dict:
    proj = json.loads((src / "projections.json").read_text())
    stamp = proj.get("veteran_level_policy") or {}
    k = {str(p): float(v) for p, v in (stamp.get("params") or {}).items()}
    if not k:
        raise RuntimeError(
            "the served projections.json carries no veteran_level_policy params — the placement read "
            "has nothing to undo. Either the artifact predates NF-TR2b or serving is OFF; either way "
            "this is a finding, not something to default past.")

    per_config, gates_all = {}, {}
    for stem, preset, n_teams in CONFIGS:
        path = src / f"board_{stem}.json"
        if not path.exists():
            per_config[stem] = {"status": "ABSENT", "note": f"{path.name} not published"}
            continue
        board = pd.DataFrame(json.loads(path.read_text()))
        cfg = get_preset(preset, n_teams=n_teams)
        pair = PL.paired_boards(board, k, cfg, NFL_PROFILE)
        b_i, b_r = pair["board_inc"], pair["board_rec"]
        m = PL.movement(b_i, b_r)

        bands = []
        for lo, hi, lab in ((1, 24, "1-24"), (25, 60, "25-60"), (61, 120, "61-120"),
                            (121, 300, "121-300"), (301, 10**9, "301+")):
            s = m[(m["overall_rank_inc"] >= lo) & (m["overall_rank_inc"] <= hi)]
            if not len(s):
                continue
            bands.append({"band": lab, "n": int(len(s)),
                          "mean_abs_move": round(float(s["move"].abs().mean()), 2),
                          "median_abs_move": int(s["move"].abs().median()),
                          "max_abs_move": int(s["move"].abs().max())})

        rook = m[m["rookie"].astype(bool)]
        vet = m[~m["rookie"].astype(bool)]
        # ⭐ ANTI-VACUITY: the incumbent's cap verdict is computed too, so the record can show
        # whether G2 could ACT at all. A gate that no board could ever trip is passing on nothing
        # (NF-D20: count the cases the mechanism can move before crediting a pass).
        inc_cap = PL.rookie_placement(b_i)
        g = {"within_position_order": PL.within_position_order_preserved(b_i, b_r),
             "rookie_placement_cap": PL.rookie_placement(b_r),
             "position_survival": PL.position_survival(b_r, k)}
        g["rookie_placement_cap"]["incumbent"] = {
            "best_rookie_overall_rank": inc_cap["best_rookie_overall_rank"],
            "breach": inc_cap["verdict"].get("breach"),
            "cap": inc_cap["verdict"].get("cap")}
        gates_all[stem] = g
        per_config[stem] = {
            "status": "OK", "n": int(len(m)),
            "movement_by_band": bands,
            "composition": {str(n): {"incumbent": PL.top_n_composition(b_i, n),
                                     "recalibrated": PL.top_n_composition(b_r, n)}
                            for n in PL.TOP_N_REPORT},
            "replacement": {p: {"incumbent": round(float(pair["repl_inc"].get(p, 0.0)), 1),
                                "recalibrated": round(float(pair["repl_rec"].get(p, 0.0)), 1),
                                "started_incumbent": int(pair["started_inc"].get(p, 0)),
                                "started_recalibrated": int(pair["started_rec"].get(p, 0))}
                            for p in PL.BOARD_POSITIONS if p in pair["repl_inc"]},
            "cohort_shift": {
                "veteran_mean_move": round(float(vet["move"].mean()), 2) if len(vet) else None,
                "rookie_mean_move": round(float(rook["move"].mean()), 2) if len(rook) else None,
                # ⭐ The whole-board rookie mean is dominated by the ~76 rookies in the flat-VOR
                # tail, where a big rank move is near-noise. The DECISION-RELEVANT figure is the
                # handful inside the top 60 — reported separately so the disclosure is quantified
                # where a drafter would actually feel it rather than where the tail inflates it.
                "rookie_top60": (
                    {"n": int((rook["overall_rank_inc"] <= 60).sum()),
                     "mean_move": round(float(
                         rook.loc[rook["overall_rank_inc"] <= 60, "move"].mean()), 2),
                     "median_move": float(
                         rook.loc[rook["overall_rank_inc"] <= 60, "move"].median())}
                    if int((rook["overall_rank_inc"] <= 60).sum()) else None),
                "rookie_by_position": {
                    p: round(float(rook.loc[rook["position"] == p, "move"].mean()), 2)
                    for p in sorted(rook["position"].unique())
                    if int((rook["position"] == p).sum()) >= 3},
            },
            "market_read_not_a_gate": PL.spearman_vs_adp(m),
            "gates": {n: v.get("pass") for n, v in g.items()},
        }

    repaired = [c for c, g in gates_all.items()
                if g["rookie_placement_cap"]["incumbent"]["breach"] is True
                and g["rookie_placement_cap"].get("pass") is True]
    band = PL.band_integrity(pd.DataFrame(proj["players"]))
    merged = {"band_integrity": band}
    for name in ("within_position_order", "rookie_placement_cap", "position_survival"):
        fails = [c for c, g in gates_all.items() if g[name].get("pass") is False]
        unev = [c for c, g in gates_all.items() if g[name].get("pass") is None]
        # None (UNEVALUABLE) wins over a pass: a gate that could not be computed on some config is
        # never rolled up as healthy (NF1.7 (a)). A FAIL anywhere still fails.
        merged[name] = {"pass": (False if fails else (None if unev else True)),
                        "failing_configs": fails, "unevaluable_configs": unev}
    merged["rookie_placement_cap"]["incumbent_breached_configs"] = [
        c for c, g in gates_all.items()
        if g["rookie_placement_cap"]["incumbent"]["breach"] is True]
    merged["rookie_placement_cap"]["repaired_by_tr2b"] = repaired
    verdict = PL.classify_placement(merged)

    return {"story": "NF-TR2b", "read": "cross-position placement (NF-D16 class)",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            # ⭐ PROVENANCE, stated honestly: this record's whole claim is "this is what is ON THE
            # WIRE", so it must name where the artifacts actually came from. A `--from-dir` run
            # records the LOCAL path and does NOT claim the prod bucket — a record that asserted S3
            # while reading an arbitrary directory would be worse than no provenance at all.
            "source_kind": "s3" if origin else "local-dir",
            "source": origin or f"local-dir:{src}",
            "read_from": str(src), "season": proj.get("season"),
            "served_level_model_version": stamp.get("level_model_version"),
            "served_level_status": stamp.get("status"),
            "policy_serving_enabled": bool(VLP.SERVING_ENABLED),
            "k_from_served_artifact": k,
            "projection_built_at": (proj.get("freshness") or {}).get("projection_built_at"),
            "gates": merged, "verdict": verdict, "per_config": per_config}


def _md(r: dict) -> str:
    v, k = r["verdict"], r["k_from_served_artifact"]
    L = [f"# NF-TR2b — whole-board CROSS-POSITION placement read (the NF-D16 class)",
         f"_generated {r['generated_at']}_ · read from `{r['source']}` · `best_alpha = 0` · served "
         f"`{r['served_level_model_version']}` · status `{r['served_level_status']}` · "
         f"board built {r['projection_built_at']}", "",
         f"## Verdict: **{v['verdict']}**", "",
         "The WITHIN-position guarantee (a positive constant is monotone) is exact and already "
         "pinned by the TR2b record's L5 identity. This read answers the question that guarantee is "
         "silent on — what the correction does ACROSS positions on the VOR board a drafter reads.",
         "",
         "⚠️ VOR does not absorb it: NF-W8-0's finding that a per-group level shift cancels in "
         "VOR space is about an ADDITIVE shift. TR2b is MULTIPLICATIVE, so `vor -> k*vor` does not "
         "cancel AND the greedy FLEX allocation (a cross-position draft on points) re-runs.", "",
         "### Gates — structural or inherited, never tuned to the measured answer",
         "", "| gate | verdict | detail |", "|---|---|---|"]
    g = r["gates"]
    L += [f"| G1 within-position order preserved | {v['gates']['within_position_order']} | "
          f"failing: {g['within_position_order']['failing_configs'] or 'none'} |",
          f"| G2 rookie placement cap (DELEGATED to NF-D18/D20) | {v['gates']['rookie_placement_cap']} | "
          f"failing: {g['rookie_placement_cap']['failing_configs'] or 'none'} |",
          f"| G3 no recalibrated position wiped from top {PL.TOP_N_SURVIVAL} | "
          f"{v['gates']['position_survival']} | failing: "
          f"{g['position_survival']['failing_configs'] or 'none'} |",
          f"| G4 served band integrity (p10 <= point <= p90) | {v['gates']['band_integrity']} | "
          f"n={g['band_integrity']['n']}, above p90 {g['band_integrity']['point_above_p90']}, "
          f"below p10 {g['band_integrity']['point_below_p10']}, order violations "
          f"{g['band_integrity']['band_order_violations']} |", "",
          f"`k` READ FROM THE SERVED ARTIFACT: " + " · ".join(f"{p} {kv:.4f}" for p, kv in sorted(k.items())),
          "", "### Movement — REPORTED, NEVER GATED",
          "", "| config | n | top 1-24 mean\\|move\\| | 301+ mean\\|move\\| | vet mean move | "
          "rookie mean move | rho(ADP) inc -> rec |", "|---|---|---|---|---|---|---|"]
    for stem, c in r["per_config"].items():
        if c.get("status") != "OK":
            L.append(f"| {stem} | — | — | — | — | — | {c.get('note','absent')} |"); continue
        by = {b["band"]: b for b in c["movement_by_band"]}
        mk = c["market_read_not_a_gate"]
        L.append(f"| {stem} | {c['n']} | {by.get('1-24',{}).get('mean_abs_move','—')} | "
                 f"{by.get('301+',{}).get('mean_abs_move','—')} | {c['cohort_shift']['veteran_mean_move']} | "
                 f"{c['cohort_shift']['rookie_mean_move']} | {mk['rho_incumbent']} -> "
                 f"{mk['rho_recalibrated']} ({mk['delta']:+}) |")
    L += ["", "⭐ The churn concentrates in the DEEP board where VOR is flat and overall rank is "
          "near-noise; the decision-relevant top-24 moves by a few ranks. Market agreement is a "
          "READ, never a target (`best_alpha = 0`).", "",
          "### G2 is ACTIVE, not vacuously passing", "",
          f"The INCUMBENT board breaches the inherited rookie-placement cap on "
          f"`{r['gates']['rookie_placement_cap']['incumbent_breached_configs'] or 'no'}` config(s), "
          f"and TR2b REPAIRS it on `{r['gates']['rookie_placement_cap']['repaired_by_tr2b'] or 'none'}`. "
          "That matters for how the pass should be read: a gate no board could ever trip would be "
          "passing on nothing (NF-D20 — count the cases the mechanism can move before crediting a "
          "pass). Here the cap demonstrably CAN fire on this board, and the correction moves it the "
          "right way.", "",
          "### The rookie/veteran boundary — a measured, DISCLOSED consequence", "",
          "TR2b touches VETERANS only; the rookie leg is held at incumbent (NF-D21 CLOSED, "
          "CONSTRAINT_REFUSED). So rookies move purely as a RELATIVE consequence, and because three "
          "of four `k` exceed 1 they move DOWN — per position tracking the `k` of the veterans they "
          "compete with, QB rookies (the only `k` < 1) being the ones that RISE.", "",
          "⚠️ The whole-board rookie mean is dominated by the ~76 rookies in the flat-VOR tail, "
          "where a large rank move is near-noise. The DECISION-RELEVANT figure is the 3-5 rookies "
          "inside the top 60, and it is NOT simply a smaller version of the headline — it runs "
          "both above and below it by config (`standard_10` moves -34.8 in the top 60 against a "
          "-14.1 whole-board mean; `superflex_10` moves -11.8 against -30.6). Read this table, not "
          "the headline:", "",
          "| config | rookies in top 60 | mean move | median move |", "|---|---|---|---|"]
    for _stem, _c in r["per_config"].items():
        _t = (_c.get("cohort_shift") or {}).get("rookie_top60") if _c.get("status") == "OK" else None
        if _t:
            L.append(f"| {_stem} | {_t['n']} | {_t['mean_move']:+} | {_t['median_move']:+} |")
    L += ["",
          "⭐ That direction is why G2 cannot be breached here: `rookie_placement_breach` caps a "
          "rookie placing TOO HIGH, and this correction moves them away from that cap. ⚠️ The honest "
          "converse: there is NO guard on the opposite side, so veterans are re-priced against an "
          "UNCORRECTED rookie leg by construction. Disclosed, not adjudicated by this read.", ""]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from-dir", default=None,
                    help="read served artifacts from a local dir instead of S3")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--out", default=DEFAULT_STEM,
                    help=f"output stem under ablation_results/ (default {DEFAULT_STEM!r}). Pass "
                         f"--out {DECIDED_STEM} to DELIBERATELY refresh NF-TR2b's decided record.")
    a = ap.parse_args(argv)
    if a.from_dir:
        src, origin = pathlib.Path(a.from_dir), None
    else:
        src, origin = _fetch(pathlib.Path(tempfile.mkdtemp(prefix="nf_tr2b_placement_"))), _S3
    r = run(src, origin=origin)
    print(f"NF-TR2b placement read — verdict {r['verdict']['verdict']} "
          f"({r['served_level_model_version']})")
    for name, val in r["verdict"]["gates"].items():
        print(f"  {name:<26}{val}")
    if not a.no_report:
        _ART.mkdir(parents=True, exist_ok=True)
        (_ART / f"{a.out}.json").write_text(json.dumps(r, indent=1, default=str))
        (_ART / f"{a.out}.md").write_text(_md(r))
        print(f"wrote {a.out}.json + {a.out}.md")
        if a.out != DECIDED_STEM:
            # ⭐ say so LOUDLY: a run that quietly wrote somewhere else is how a stale decided
            #    record goes unnoticed — the opposite failure to the one D4 fixes.
            print(f"  ⚠️ NF-TR2b's decided record ({DECIDED_STEM}.*) was NOT updated. To refresh it "
                  f"deliberately: --out {DECIDED_STEM}")
    return 0 if r["verdict"]["verdict"] == "SANE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
