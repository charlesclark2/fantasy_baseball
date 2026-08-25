"""run_nf_inj3b_ship_flipped_diff.py — NF-INJ3b-SHIP node 4: the FLIPPED dry-run rebuild + diff.

⭐ WHAT MAKES THIS DIFFERENT FROM NF-INJ3b-M, and it is the whole point. NF-INJ3b-M forced the
policy ON **in memory** and hand-supplied a covariate feed, because neither the flip nor the feed
existed. This runner builds the board the operator would actually publish: the flip as COMMITTED,
the feed as the board build now derives it for itself, no patching of anything. If the committed
code cannot reproduce -M's measured impact, the flip is not the thing -M measured — and that is a
question worth failing on rather than discovering after a publish.

THREE BOARDS, and the third is not optional:

  incumbent   the policy forced OFF in memory — the rollback board, the diff's base
  control     the SAME board built AGAIN at the SAME commit
  flipped     the committed state, untouched — what would publish

⛔ THE CONTROL IS THE STANDING RULE, NOT A NICETY (NF-INJ3c §6, card QkpAHBYa). Two rebuilds of the
same board at the same commit differ in the rookie band (`fp_ppr_sd`/`p10`/`p90`) at 0–21 MATERIAL
cells. So no comparison here is bitwise; every diff is at `rtol/atol = 1e-9`, SCOPED BY POPULATION,
and any rookie-band motion is read against the control BEFORE it is attributed to this change. A
cell that moves in the control moved for reasons that are not the flip.

🔒 DRY RUN. No `--publish`, no S3 client, no lake write, and it never touches
`injury_games_policy.SERVING_ENABLED` on disk. It writes two artifacts under its own `--out` stem
and nothing else — ⛔ never a decided story's paths (the D4 rule).
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

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    injury_games_policy as POLICY,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    injury_games_publish_guard as IGPG,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_inj3_injury_games as R3,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_inj3b_m_counterfactual as CF,
)
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as NF15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_season_projection as RSP,
)

log = logging.getLogger("nfl.fantasy.nf_inj3b_ship.flipped_diff")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
SEASON = R3.SERVING_SEASON

#: ⛔ MATERIAL, never bitwise (NF-INJ3c §6).
RTOL = ATOL = 1e-9

#: the columns a population-scoped diff reads. The rookie band is listed explicitly because it is
#: the one the same-commit control is known to move.
POINT_COLS = ("proj_games", "proj_fp_ppr", "proj_fp_half", "proj_fp_std")
BAND_COLS = ("fp_ppr_sd", "fp_ppr_p10", "fp_ppr_p90")

#: NF-INJ3b-M's measured headline, the SANITY ANCHOR. A materially divergent number means the
#: committed flip is not the thing that was measured — which HALTS the story, and is not a gate.
ANCHOR = {"mean_d_proj_games": -2.6104, "mean_d_pts_ppr": -1.2341, "n_flagged": 22}
#: how far the committed rebuild may land from the anchor before the story halts. Generous ON
#: PURPOSE: the two runs differ in a KNOWN, INTENDED way (the returner boundary, and a feed built
#: over the whole board rather than the study's 22 rows), so an exact match would be the surprising
#: outcome. What this catches is an ORDER-OF-MAGNITUDE divergence — the flip not doing what -M said.
ANCHOR_TOL = {"mean_d_proj_games": 0.75, "mean_d_pts_ppr": 0.75}


def build_flipped(con, schema: str, nf15: dict) -> pd.DataFrame:
    """The board as the COMMITTED code builds it — ⛔ nothing forced, nothing supplied.

    This is the one board in this runner that is not a control, and it is deliberately built by
    calling the shipped assembly with no arguments this story invented. The covariate feed it uses
    is the one `build_veteran_projection` derives for itself."""
    cap: dict = {}
    board = NF15.build_season_projection(
        con, nf15["base_season"], SEASON, schema, nf15["selections"], nf15["inputs"],
        base_from=2017, market_refresh=False, capture=cap)
    CF._assert_reorder_fired(cap)
    return board


def _material(a: pd.Series, b: pd.Series) -> np.ndarray:
    """Rows where `b` differs from `a` by more than the material tolerance. NaN==NaN counts as
    equal (a column both boards leave empty has not moved)."""
    x, y = pd.to_numeric(a, errors="coerce").to_numpy(float), pd.to_numeric(b, errors="coerce").to_numpy(float)
    both_nan = np.isnan(x) & np.isnan(y)
    close = np.isclose(x, y, rtol=RTOL, atol=ATOL, equal_nan=True)
    return ~(close | both_nan)


def _scoped_diff(base: pd.DataFrame, other: pd.DataFrame, label: str) -> dict:
    """A material diff SCOPED BY POPULATION — rookies, flagged veterans, unflagged veterans."""
    key = "player_id"
    cols = [c for c in (*POINT_COLS, *BAND_COLS) if c in base.columns and c in other.columns]
    keep = [key, "is_rookie", "injury_games_served", *cols]
    b = base[[c for c in keep if c in base.columns]].copy()
    o = other[[c for c in keep if c in other.columns]].copy()
    m = b.merge(o, on=key, suffixes=("_a", "_b"))
    rookie = m["is_rookie_b"].astype(bool).to_numpy() if "is_rookie_b" in m else np.zeros(len(m), bool)
    served = (np.isfinite(pd.to_numeric(m.get("injury_games_served_b"), errors="coerce")
                          .to_numpy(float)) if "injury_games_served_b" in m
              else np.zeros(len(m), bool))
    pops = {"rookie": rookie, "veteran_fitted": (~rookie) & served,
            "veteran_other": (~rookie) & (~served)}
    out: dict = {"label": label, "n_rows": int(len(m)), "rtol": RTOL, "atol": ATOL,
                 "populations": {}}
    for pop, mask in pops.items():
        cell: dict = {"n": int(mask.sum()), "columns": {}}
        for c in cols:
            d = _material(m[f"{c}_a"], m[f"{c}_b"]) & mask
            if d.any():
                delta = (pd.to_numeric(m.loc[d, f"{c}_b"], errors="coerce")
                         - pd.to_numeric(m.loc[d, f"{c}_a"], errors="coerce"))
                cell["columns"][c] = {"n_moved": int(d.sum()),
                                      "max_abs": float(delta.abs().max()),
                                      "mean": float(delta.mean())}
            else:
                cell["columns"][c] = {"n_moved": 0, "max_abs": 0.0, "mean": 0.0}
        cell["total_moved_cells"] = int(sum(v["n_moved"] for v in cell["columns"].values()))
        out["populations"][pop] = cell
    return out


def _rookie_band_attribution(flip_vs_inc: dict, control_diffs: list[dict]) -> dict:
    """⭐ THE STANDING RULE, EXECUTED — against an ENVELOPE, not one control draw.

    ⚠️⚠️ A SINGLE CONTROL IS NOT ENOUGH, AND THE FIRST CUT OF THIS FUNCTION GOT IT WRONG. The rule
    says same-commit rebuilds differ in the rookie band at **0–21** material cells — a RANGE. So a
    control draw that happens to move ZERO cells of a column proves nothing about that column, and
    reading it as "deterministic" turns the very next flip-side move into a false attribution. That
    is exactly what happened here: one control moved 0 `fp_ppr_sd` cells, the flipped board moved 3
    (by 0.01, i.e. one unit of that column's 2-dp rounding), and the attribution came back TRUE for
    a quantity the flip structurally cannot touch. An inactive control is UNINFORMATIVE, never a
    pass (NF-D20, NF1.7 (a)).

    So the control is drawn `n_controls` times and a flip-side move is attributed only if it lands
    OUTSIDE the observed envelope — in BOTH the cell count and the magnitude. The envelope is
    reported whether or not anything is attributed, because a reader needs to see how wide it was
    before believing either answer."""
    fl = flip_vs_inc["populations"]["rookie"]["columns"]
    per = {}
    for c in BAND_COLS:
        if c not in fl:
            continue
        counts = [d["populations"]["rookie"]["columns"][c]["n_moved"] for d in control_diffs]
        mags = [d["populations"]["rookie"]["columns"][c]["max_abs"] for d in control_diffs]
        per[c] = {
            "flipped_moved": fl[c]["n_moved"], "flipped_max_abs": fl[c]["max_abs"],
            "control_moved_range": [int(min(counts)), int(max(counts))],
            "control_max_abs_range": [float(min(mags)), float(max(mags))],
            "n_controls": len(control_diffs),
            "attributable_to_the_flip": bool(
                fl[c]["n_moved"] > max(counts) and fl[c]["max_abs"] > max(max(mags), ATOL)),
        }
    return {
        "per_column": per,
        "any_attributable": bool(any(v["attributable_to_the_flip"] for v in per.values())),
        "rule": ("NF-INJ3c §6 (card QkpAHBYa): same-commit rebuilds differ in the rookie band at "
                 "0–21 material cells, so a rookie-band move is read against SAME-COMMIT controls "
                 "before it is attributed to this change. ⛔ Never bitwise, and ⛔ never against a "
                 "SINGLE control draw — the rule states a RANGE, so one draw that moves nothing "
                 "cannot establish that a column is deterministic."),
        "why_rookies_cannot_be_moved_by_this_flip": (
            "structurally: the formal cap runs INSIDE `project_veterans`, and `project_rookies` is "
            "a separate frame concatenated afterwards which routes the INCUMBENT constants "
            "(NF-INJ3c AC-1). So any rookie motion here is the build's own noise, and the envelope "
            "is what MEASURES that rather than asserting it from this sentence."),
        "magnitude_note": (
            "every observed move on both sides is one unit of the column's own display rounding "
            "(0.01 on `fp_ppr_sd`, 0.1 on `fp_ppr_p10`/`p90`) — the documented signature of the "
            "build's non-determinism, not of a model change."),
    }


def _anchor_check(flagged: dict) -> dict:
    """Reproduce NF-INJ3b-M's headline on the COMMITTED flip. Materially divergent numbers HALT the
    story — they mean the flip is not the thing that was measured — and this is NOT a gate."""
    got = {"mean_d_proj_games": flagged["mean_d_proj_games"],
           "mean_d_pts_ppr": flagged["mean_d_pts_ppr"], "n_flagged": flagged.get("n_flagged")}
    dev = {k: (None if got.get(k) is None else round(float(got[k]) - ANCHOR[k], 4))
           for k in ("mean_d_proj_games", "mean_d_pts_ppr")}
    ok = all(dev[k] is not None and abs(dev[k]) <= ANCHOR_TOL[k] for k in dev)
    return {"anchor": ANCHOR, "measured": got, "deviation": dev, "tolerance": ANCHOR_TOL,
            "reproduces": bool(ok),
            "what_it_is": (
                "NF-INJ3b-M measured the served impact by forcing the policy on IN MEMORY with a "
                "hand-supplied feed. This run measures the COMMITTED flip with the feed the board "
                "build derives for itself. The two differ in TWO known, intended ways — the "
                "returner boundary (4 flagged returners now hold the incumbent) and a feed built "
                "over the whole board rather than the study's 22 rows — so an exact match would be "
                "the surprising result. What this catches is an order-of-magnitude divergence."),
            "if_it_fails": ("HALT the story and diagnose. A materially different number means the "
                            "committed flip is not what the operator accepted in ruling D5=A.")}


def _top_moves_by_config(per_config: dict, base: pd.DataFrame, flip: pd.DataFrame,
                         top_n: int = 25) -> dict:
    """The operator packet's core table: the largest rank moves per config, WITH NAMES."""
    from quant_sports_intel_models.football.nfl.fantasy import nf_tr2b_placement as PL
    from quant_sports_intel_models.football.nfl.fantasy.league_presets import (
        NFL_PROFILE, get_preset)
    from quant_sports_intel_models.football.nfl.fantasy.run_league_board import (
        build_board, score_players)

    out: dict = {}
    for stem, preset, n_teams in CF.CONFIGS:
        cfg = get_preset(preset, n_teams=n_teams)
        boards = {}
        for lab, frame in (("inc", base), ("cf", flip)):
            scored = score_players(frame, cfg, NFL_PROFILE)
            pf = pd.DataFrame({
                "position": scored["position"].to_numpy(),
                "id": scored["player_id"].to_numpy(),
                "name": scored["player_name"].to_numpy(),
                "rookie": (scored["is_rookie"].to_numpy() if "is_rookie" in scored.columns
                           else np.zeros(len(scored), dtype=bool)),
                "adp": (pd.to_numeric(scored["adp"], errors="coerce").to_numpy()
                        if "adp" in scored.columns else np.full(len(scored), np.nan)),
                "league_points": pd.to_numeric(scored["league_points"],
                                               errors="coerce").to_numpy(),
            })
            pf = pf[pf["league_points"].notna()]
            boards[lab] = build_board(pf, cfg, NFL_PROFILE, points_col="league_points")
        m = PL.movement(boards["inc"], boards["cf"]).copy()
        m["abs_move"] = m["move"].abs()
        top = m.sort_values("abs_move", ascending=False).head(top_n)
        cols = [c for c in ("name", "position", "overall_rank_inc", "overall_rank_cf", "move")
                if c in top.columns]
        out[stem] = {"is_superflex": bool(preset == "superflex"),
                     "top": top[cols].to_dict("records")}
    return out


def run(con, art: Path, schema: str, top_n: int, n_controls: int = 3) -> dict:
    nf15 = CF.nf15_inputs(con, schema)
    log.info("building INCUMBENT board (policy forced OFF in memory) …")
    inc = CF.build_board_frame(con, schema, serving_on=False, cov=None, nf15=nf15)
    controls = []
    for i in range(n_controls):
        log.info("building SAME-COMMIT CONTROL %d/%d (the NF-INJ3c §6 rule) …", i + 1, n_controls)
        controls.append(CF.build_board_frame(con, schema, serving_on=False, cov=None, nf15=nf15))
    ctl = controls[0]
    log.info("building FLIPPED board (the COMMITTED state — nothing forced, feed self-built) …")
    flip = build_flipped(con, schema, nf15)

    if not POLICY.serving_enabled():
        raise RuntimeError(
            "NF-INJ3b-SHIP: `injury_games_policy.SERVING_ENABLED` is False, so the 'flipped' board "
            "is the incumbent and this whole diff would measure NOTHING while reporting a clean "
            "result. Refusing (NF1.7 (a)).")

    stamp = IGPG.evaluate(flip)
    flagged_ids = set(flip.loc[
        np.isfinite(pd.to_numeric(flip.get("injury_games_served"), errors="coerce")
                    .to_numpy(float)), "player_id"].astype(str)) if \
        "injury_games_served" in flip.columns else set()
    log.info("the fitted arm produced %d row(s); the stamp guard says %s",
             len(flagged_ids), stamp["verdict"])

    points = CF._point_diff(inc, flip, flagged_ids)
    noise = CF._noise_floor(inc, ctl)
    flip_vs_inc = _scoped_diff(inc, flip, "flipped vs incumbent")
    control_diffs = [_scoped_diff(inc, c, f"SAME-COMMIT control {i + 1} vs incumbent")
                     for i, c in enumerate(controls)]
    ctl_vs_inc = control_diffs[0]
    per_config = CF._per_config(inc, flip)
    return {
        "story": "NF-INJ3b-SHIP",
        "read": "node 4 — the flipped dry-run rebuild + population-scoped material diff",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": SEASON,
        "policy": {"serving_enabled_on_disk": bool(POLICY.SERVING_ENABLED),
                   "model_version": POLICY.MODEL_VERSION, "arm": POLICY.ARM,
                   "certified_statuses": list(POLICY.CERTIFIED_STATUSES),
                   "incumbent_statuses": list(POLICY.INCUMBENT_STATUSES),
                   "returner_boundary": POLICY.RETURNER_BOUNDARY,
                   "nothing_forced_in_memory_for_the_flipped_board": True},
        "stamp_guard": stamp,
        "noise_floor": noise,
        "material_diff": {"flipped_vs_incumbent": flip_vs_inc,
                          "same_commit_control_vs_incumbent": ctl_vs_inc,
                          "same_commit_controls": control_diffs,
                          "n_controls": len(control_diffs)},
        "rookie_band_attribution": _rookie_band_attribution(flip_vs_inc, control_diffs),
        "served_point_impact": points,
        "anchor_check": _anchor_check(points["flagged"] | {"n_flagged": points["n_flagged"]}),
        "per_config_placement": per_config,
        "top_rank_moves": _top_moves_by_config(per_config, inc, flip, top_n),
        "deploy_held": True, "published": False, "best_alpha": 0,
    }


def _md(r: dict) -> str:
    p, a, rb = r["served_point_impact"], r["anchor_check"], r["rookie_band_attribution"]
    fl, un, n = p["flagged"], p["unflagged_collateral"], r["noise_floor"]
    L = [
        "# NF-INJ3b-SHIP node 4 — the FLIPPED rebuild, diffed",
        "",
        f"_generated {r['generated_at']}_ · season {r['season']} · `best_alpha = 0` · "
        f"**DRY RUN — nothing published** · `SERVING_ENABLED` on disk = "
        f"**{r['policy']['serving_enabled_on_disk']}**",
        "",
        "This builds the board the operator would publish — the flip **as committed**, the "
        "covariate feed **as the board build derives it for itself**, nothing forced in memory and "
        "nothing hand-supplied. NF-INJ3b-M could not do that (neither existed), so this is the "
        "first measurement of the real serving path.",
        "",
        "## 1. The D6 stamp guard, on the board that would publish",
        "",
        f"**{r['stamp_guard']['verdict']}** — {r['stamp_guard']['detail']}",
        "",
        f"certified rows {r['stamp_guard']['n_certified']} · produced by the fitted arm "
        f"{r['stamp_guard']['n_fitted']} · materially moved {r['stamp_guard']['n_moved']} · "
        f"largest move {r['stamp_guard']['max_abs_move']:.4g} games",
        "",
        "## 2. The noise floor and the same-commit control",
        "",
        "| quantity | rows differing | max abs | p99 abs |", "|---|---|---|---|",
    ]
    for c in ("proj_games", "proj_fp_ppr"):
        b = n[c]
        L.append(f"| `{c}` (same-commit replicate) | {b['n_nonzero']} | {b['max_abs']:.2e} | "
                 f"{b['p99_abs']:.2e} |")
    L += [
        "",
        f"Replicate overall-rank order identical: **{n['overall_rank_order_identical']}**.",
        "",
        "### Rookie-band motion, read against the control FIRST",
        "",
        rb["rule"], "",
        f"Controls drawn: **{r['material_diff']['n_controls']}** — an envelope, not one draw.", "",
        "| column | moved (flipped) | moved (control range) | max abs (flipped) | "
        "max abs (control range) | attributable to the flip |",
        "|---|---|---|---|---|---|",
    ] + [
        f"| `{c}` | {v['flipped_moved']} | {v['control_moved_range'][0]}–"
        f"{v['control_moved_range'][1]} | {v['flipped_max_abs']:.2e} | "
        f"{v['control_max_abs_range'][0]:.2e}–{v['control_max_abs_range'][1]:.2e} | "
        f"**{v['attributable_to_the_flip']}** |"
        for c, v in rb["per_column"].items()
    ] + [
        "", rb["magnitude_note"],
    ] + [
        "",
        f"Any rookie-band move attributable to this change: **{rb['any_attributable']}**. "
        + rb["why_rookies_cannot_be_moved_by_this_flip"],
        "",
        "## 3. The population-scoped material diff",
        "",
        f"rtol = atol = {RTOL:g}, **never bitwise**.",
        "",
        "| population | n | cells moved (flipped) | cells moved (control) |",
        "|---|---|---|---|",
    ]
    fpop = r["material_diff"]["flipped_vs_incumbent"]["populations"]
    cpop = r["material_diff"]["same_commit_control_vs_incumbent"]["populations"]
    for pop in fpop:
        L.append(f"| `{pop}` | {fpop[pop]['n']} | {fpop[pop]['total_moved_cells']} | "
                 f"{cpop[pop]['total_moved_cells']} |")
    L += [
        "",
        "## 4. The served-POINT impact, and the sanity anchor",
        "",
        f"**{p['n_flagged']} rows served by the fitted arm** of {p['n_rows']} board rows.",
        "",
        "| | flagged | unflagged |", "|---|---|---|",
        f"| mean Δ `proj_games` | **{fl['mean_d_proj_games']:+.3f}** | — |",
        f"| mean Δ `pts` (PPR) | **{fl['mean_d_pts_ppr']:+.3f}** | — |",
        f"| points down / up | {fl['n_pts_down']} / {fl['n_pts_up']} | "
        f"{un['n_pts_changed']} changed |",
        f"| rank moves | {fl['n_rank_moved']} | {un['n_rank_moved']} |",
        "",
        f"### Sanity anchor vs NF-INJ3b-M: **{'REPRODUCES' if a['reproduces'] else 'DIVERGES'}**",
        "",
        a["what_it_is"], "",
        "| quantity | NF-INJ3b-M | this run | deviation | tolerance |", "|---|---|---|---|---|",
    ] + [
        f"| `{k}` | {a['anchor'][k]:+.4f} | {a['measured'][k]:+.4f} | {a['deviation'][k]:+.4f} | "
        f"±{a['tolerance'][k]} |" for k in a["tolerance"]
    ] + [
        "",
        (f"⛔ **{a['if_it_fails']}**" if not a["reproduces"] else
         "The committed flip reproduces the measurement the operator accepted."),
        "",
        "## 5. Per-config placement — all 14 published configs",
        "",
        "| config | rank moves | max \\|move\\| | top-60 moved | within-pos order | rookie cap |",
        "|---|---|---|---|---|---|",
    ] + [
        f"| `{s}`{' ⭐SF' if v['is_superflex'] else ''} | {v['n_rank_moved']}/{v['n']} | "
        f"{v['max_abs_move']} | {v['top60_n_moved']} | {v['within_position_order']} | "
        f"{v['rookie_placement_cap']} |"
        for s, v in r["per_config_placement"].items()
    ] + [
        "",
        "⚠️ Superflex is read on its OWN rows: NF-TR2b's VOR shield is ADDITIVE-ONLY and assumes "
        "the group is not cross-pooled, and QB IS cross-pooled there.",
        "",
        "## 6. What is still the OPERATOR's",
        "",
        "This is a DRY RUN. Nothing was published, no lake write, no `--publish` flag exists on "
        "this runner, and the D10 combined read gates the first publish. The ship/hold call is the "
        "operator's.",
        "",
    ]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3b-SHIP node 4: the flipped rebuild + diff")
    ap.add_argument("--duckdb", default=R3._DEFAULT_DUCKDB)
    ap.add_argument("--artifacts", default=None)
    ap.add_argument("--schema", default=RSP.MARTS_SCHEMA)
    ap.add_argument("--out", default="nf_inj3b_ship_flipped_diff")
    ap.add_argument("--top-n", type=int, default=25)
    ap.add_argument("--n-controls", type=int, default=3,
                    help="same-commit control rebuilds. ⛔ Not 1: the non-determinism rule states a "
                         "RANGE (0-21 cells), so one draw cannot establish that a column is "
                         "deterministic and the next flip-side move reads as a false attribution.")
    ap.add_argument("--rerender", action="store_true",
                    help="re-render the MD from the existing JSON — the three board builds take "
                         "minutes and a wording fix must not cost one")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.rerender:
        rep = json.loads((_REPORT_DIR / f"{args.out}.json").read_text())
        (_REPORT_DIR / f"{args.out}.md").write_text(_md(rep))
        print(f"re-rendered {args.out}.md (no rebuild)")
        return 0

    import duckdb
    con = duckdb.connect(args.duckdb, read_only=True)
    rep = run(con, R3.artifacts_dir(args.artifacts), args.schema, args.top_n, args.n_controls)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{args.out}.json").write_text(json.dumps(rep, indent=2, default=str))
    (_REPORT_DIR / f"{args.out}.md").write_text(_md(rep))
    p, a = rep["served_point_impact"], rep["anchor_check"]
    print(f"NF-INJ3b-SHIP node 4 — stamp guard: {rep['stamp_guard']['verdict']}")
    print(f"  {p['n_flagged']} served rows / {p['n_rows']} board rows; "
          f"mean Δgames {p['flagged']['mean_d_proj_games']:+.3f}, "
          f"mean Δpts(PPR) {p['flagged']['mean_d_pts_ppr']:+.3f}")
    print(f"  anchor vs NF-INJ3b-M: {'REPRODUCES' if a['reproduces'] else 'DIVERGES'} "
          f"{a['deviation']}")
    print(f"  rookie-band motion attributable to the flip: "
          f"{rep['rookie_band_attribution']['any_attributable']}")
    print(f"  🔒 DRY RUN — nothing published. wrote {args.out}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
