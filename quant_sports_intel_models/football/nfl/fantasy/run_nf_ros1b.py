"""run_nf_ros1b.py — NF-ROS1b walk-forward: NF-ROS1's harness with the HURDLE interval.

Registered in `ablation_results/nf_ros1b_preregistration.md` (+ amendment 1). This file extends
`run_nf_ros1` rather than rebuilding it: the frame, the fits, the anchors and the ship bar are the
parent's; `ros_interval.HurdleInterval` replaces the residual table for every predictor. It never
publishes.

Modes (LAPTOP; `env -u TOKEN` — a bare TOKEN env var poisons delta-rs, registration §11):

    # the decisive run (hurdle); --smoke = 2 folds on 2019-2021, a code-path proof
    env -u TOKEN uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1b [--smoke]
    # §6 parent_reproduction: the parent's construction through the extended harness, compared to
    # nf_ros1_walkforward{_smoke}.json at 0.0
    env -u TOKEN uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1b \\
        --interval location_shift [--smoke]
    # §6 decisive_reproduction: rerun into a scratch stem and compare to the committed record
    env -u TOKEN uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1b \\
        --stem nf_ros1b_repro_check --compare-to nf_ros1b_walkforward.json
    # §8 the name-join rung on the served 2026 board
    env -u TOKEN uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1b --name-join-2026
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import ros_interval as RI
from quant_sports_intel_models.football.nfl.fantasy import ros_value as V
from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1 as N

log = logging.getLogger("nf_ros1b")

RESULTS = N.RESULTS
REPO = N.HERE.parents[3]
STEM = "nf_ros1b_walkforward"
PARENT_STEM = "nf_ros1_walkforward"
REPRO_STEM = "nf_ros1b_parent_repro"
NAME_JOIN_STEM = "nf_ros1b_name_join_2026"
TITLE = "NF-ROS1b walk-forward (hurdle interval)"
REGISTRATION = ("`nf_ros1b_preregistration.md` + amendment 1, inheriting "
                "`nf_ros1_preregistration.md` + amendments 1–2")
DIAG_SEED = V.SEED + 100          # §7 readings draw from their own stream, never the gate's
GSIS_RE = re.compile(r"00-\d{7}")
SERVED_BOARD_KEY = "fantasy/nfl/2026/projections.json"
COMPARE_EXCLUDE = {"meta"}

TIMINGS: dict[str, float] = {}


@contextlib.contextmanager
def timed(name: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        TIMINGS[name] = TIMINGS.get(name, 0.0) + time.perf_counter() - t0


# ── the run ───────────────────────────────────────────────────────────────────────────────────────
def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """§3.2: miss_streak from the frame's own (n, t), then the parent's permutation (which now
    carries the donor's miss_streak)."""
    f = frame.copy()
    with timed("miss_streak"):
        f["miss_streak"] = RI.miss_streak(f)
    with timed("add_permuted"):
        f = N.add_permuted(f)
    return f


def run(frame: pd.DataFrame, evals, interval_name: str) -> dict:
    interval = RI.HurdleInterval() if interval_name == RI.INTERVAL_NAME else None
    with timed("evaluate"):
        result = N.evaluate(frame, evals, interval=interval)
    if interval is not None:
        with timed("hurdle_extras"):
            result["hurdle"] = hurdle_extras(result, interval)
    return result


def _pooled(folds, key_fn):
    ys, ps, qs, pos, ks, rk = [], [], [], [], [], []
    for f in folds:
        t = f["test"]
        point, q = key_fn(f)
        ys.append(t[f"y_{V.GATE_PRESET}"].to_numpy())
        ps.append(point)
        qs.append(q)
        pos.append(t["pos"].to_numpy())
        ks.append(t["k"].to_numpy())
        rk.append(t["rookie"].to_numpy().astype(bool))
    return (np.concatenate(ys), np.concatenate(ps), np.concatenate(qs), np.concatenate(pos),
            np.concatenate(ks), np.concatenate(rk))


def _calibration(y, q, pos, seed_base: int) -> dict:
    """The parent's pooled C7/C9 arithmetic (same seeds per position), for any predictive."""
    out = {}
    for i, P in enumerate(V.POSITIONS):
        m = pos == P
        if not m.any():
            continue
        u = V.randomized_pit(y[m], q[m], np.random.default_rng(seed_base + i))
        out[P] = {"coverage80": float(V.coverage80(y[m], q[m]).mean()),
                  "pit_max_decile_dev": V.max_decile_dev(u),
                  "pooled_crps": float(V.crps_q(y[m], q[m]).mean())}
    return out


def hurdle_extras(result: dict, interval: RI.HurdleInterval) -> dict:
    folds = result["_folds_obj"]
    w = result["winner"]
    G = V.GATE_PRESET
    y, pt, qh, pos, ks, rk = _pooled(folds, lambda f: f["pred"][G][w])
    _, _, qr, _, _, _ = _pooled(folds, lambda f: f["reference"][w])

    # the reference-only location-shift construction on the winner's point (amendment 1 item 2)
    ref = {"label": RI.REFERENCE_LABEL, "arm": w,
           "per_fold_crps": {P: [float(V.crps_q(f["test"][f"y_{G}"].to_numpy()[m],
                                                 f["reference"][w][1][m]).mean())
                                 for f in folds
                                 for m in [(f["test"]["pos"] == P).to_numpy()] if m.any()]
                             for P in V.POSITIONS},
           "calibration": _calibration(y, qr, pos, V.SEED)}

    pi = np.concatenate([interval.by_fold[(f["season"], G, "")] for f in folds])
    counts = {}
    for P in V.POSITIONS:
        m = pos == P
        z0 = m & (pt <= 0)
        counts[P] = {"rows": int(m.sum()), "y_negative_rows": int((m & (y < 0)).sum()),
                     "point_zero_rows": int(z0.sum()),
                     "point_zero_realized_zero_share": (float((y[z0] <= 0).mean())
                                                        if z0.any() else None),
                     "realized_zero_share": float((y[m] <= 0).mean()),
                     "mean_pi": float(pi[m].mean())}
    strata = {}
    rng_i = 0
    for key, mask in ([(f"k{k}", ks == k) for k in V.EVAL_WEEKS]
                      + [("rookie", rk), ("veteran", ~rk)]):
        if mask.any():
            u = V.randomized_pit(y[mask], qh[mask], np.random.default_rng(DIAG_SEED + 50 + rng_i))
            strata[key] = {"rows": int(mask.sum()), "pit_max_decile_dev": V.max_decile_dev(u),
                           "coverage80": float(V.coverage80(y[mask], qh[mask]).mean())}
        rng_i += 1
    pi_diag = list(interval.diag.values())
    return {
        "reference_only_winner_at_location_shift": ref,
        "mechanism_check": {"hurdle": RI.mechanism_check(y, pt, qh, pos, DIAG_SEED),
                            "location_shift_reference": RI.mechanism_check(y, pt, qr, pos, DIAG_SEED)},
        "pi_reliability": RI.pi_reliability(pi, y, pos),
        "counts": counts,
        "strata_c9": strata,
        "pi_fits": {"n": len(pi_diag),
                    "single_class": int(sum(d["single_class"] for d in pi_diag)),
                    "dropped_features": int(sum(d["dropped_features"] for d in pi_diag))},
    }


# ── report ────────────────────────────────────────────────────────────────────────────────────────
def write_report(result: dict, diag: dict, *, smoke: bool, meta: dict, stem: str) -> tuple[Path, Path]:
    # the interval rides in META (never in `result`, which the parent-reproduction pin compares)
    if meta["interval"] != RI.INTERVAL_NAME:
        return N.write_report(result, diag, smoke=smoke, meta=meta, stem=stem,
                              title="NF-ROS1b parent reproduction (location-shift)",
                              registration=REGISTRATION)
    jp, mp = N.write_report(result, diag, smoke=smoke, meta=meta, stem=stem, title=TITLE,
                            registration=REGISTRATION)
    h = result["hurdle"]
    L = ["", "## NF-ROS1b hurdle readings (§5 reference, §7 diagnostics — never gates)", "",
         f"### `{RI.REFERENCE_KEY}` — **{RI.REFERENCE_LABEL}**", "",
         "| pos | hurdle cov80 | hurdle PIT dev | hurdle CRPS | ref cov80 | ref PIT dev | ref CRPS |",
         "|---|---|---|---|---|---|---|"]
    for P, d in result["positions"].items():
        r = h["reference_only_winner_at_location_shift"]["calibration"].get(P, {})
        L.append(f"| {P} | {d['coverage80']:.3f} | {d['pit_max_decile_dev']:.4f} | "
                 f"{d['winner_pooled_crps']:.3f} | {r.get('coverage80', math.nan):.3f} | "
                 f"{r.get('pit_max_decile_dev', math.nan):.4f} | {r.get('pooled_crps', math.nan):.3f} |")
    L += ["", "### Mechanism check (top tercile: q05 = 0 share vs realized zero share; lowest PIT decile)",
          "", "| pos | construction | q05=0 share | realized zero share | lowest decile |",
          "|---|---|---|---|---|"]
    for cons, tab in h["mechanism_check"].items():
        for P, d in tab.items():
            L.append(f"| {P} | {cons} | {d['top_tercile_q05_zero_share']:.3f} | "
                     f"{d['top_tercile_realized_zero_share']:.3f} | {d['lowest_pit_decile_mass']:.3f} |")
    L += ["", "### π reliability (10 equal-count bins: predicted → realized)", ""]
    for P, bins in h["pi_reliability"].items():
        L.append(f"- {P}: " + " · ".join(f"{b['pred']:.2f}→{b['realized']:.2f}" for b in bins))
    L += ["", "### Counts", "", "```", json.dumps(N._clean(h["counts"]), indent=1),
          json.dumps(N._clean(h["pi_fits"])), "```", "",
          "### Strata C9 (informative only — C9 gates pooled per position)", "",
          " · ".join(f"{k} {v['pit_max_decile_dev']:.3f}" for k, v in h["strata_c9"].items())]
    with mp.open("a") as fh:
        fh.write("\n".join(L) + "\n")
    return jp, mp


# ── reproduction comparison (§6) ──────────────────────────────────────────────────────────────────
def max_abs_diff(a, b, path: str = "") -> tuple[float, list[str]]:
    """Largest numeric difference between two JSON trees, plus every structural mismatch."""
    if isinstance(a, dict) and isinstance(b, dict):
        worst, bad = 0.0, []
        for k in sorted(set(a) | set(b)):
            if not path and k in COMPARE_EXCLUDE:
                continue
            if k not in a or k not in b:
                bad.append(f"{path}/{k}: missing on one side")
                continue
            d, e = max_abs_diff(a[k], b[k], f"{path}/{k}")
            worst, bad = max(worst, d), bad + e
        return worst, bad
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return 0.0, [f"{path}: length {len(a)} != {len(b)}"]
        worst, bad = 0.0, []
        for i, (x, y) in enumerate(zip(a, b)):
            d, e = max_abs_diff(x, y, f"{path}[{i}]")
            worst, bad = max(worst, d), bad + e
        return worst, bad
    num = (int, float)
    if (isinstance(a, num) and not isinstance(a, bool)
            and isinstance(b, num) and not isinstance(b, bool)):
        return abs(float(a) - float(b)), []
    return (0.0, []) if a == b else (0.0, [f"{path}: {a!r} != {b!r}"])


def compare(new: Path, old: Path) -> dict:
    a = json.loads(new.read_text())
    b = json.loads(old.read_text())
    worst, bad = max_abs_diff(a, b)
    return {"new": new.name, "reference": old.name, "max_abs_diff": worst,
            "structural_mismatches": bad[:50], "n_structural_mismatches": len(bad),
            "reproduces": bool(worst <= V.REPRO_TOL and not bad)}


# ── §8 the name-join rung on the served 2026 board ────────────────────────────────────────────────
def _cache_bucket() -> str:
    b = os.environ.get("CACHE_BUCKET")
    if b:
        return b
    from dotenv import dotenv_values
    b = dotenv_values(REPO / ".env").get("CACHE_BUCKET")
    if not b:
        raise V.RosError("CACHE_BUCKET is not set (env or repo .env)")
    return b


def load_served_board() -> dict:
    import boto3
    body = boto3.client("s3", region_name="us-east-1").get_object(
        Bucket=_cache_bucket(), Key=SERVED_BOARD_KEY)["Body"].read()
    return json.loads(body)


def _lake(source: str, seasons, columns=None) -> tuple[pd.DataFrame, int]:
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io
    t = DeltaTable(s3io.table_uri("nfl", source), storage_options=s3io.storage_options())
    df = t.to_pandas(partitions=[("season", "in", [str(s) for s in seasons])], columns=columns)
    return df, int(t.version())


def board_frame(served: dict) -> pd.DataFrame:
    rows = [r for r in served["players"] if r.get("pos") in V.POSITIONS]
    return pd.DataFrame({
        "player_id": [str(r["id"]) for r in rows],
        "player_name": [r["name"] for r in rows],
        "position": [r["pos"] for r in rows],
        "team_id": [r.get("team") for r in rows],
        "draft_pick": [r.get("draftPick") for r in rows],
        "is_rookie": [bool(r.get("rookie")) for r in rows],
        "season": 2026,
    })


def classify_join(rid, auth, realized_ids: set) -> str:
    """§8 outcome for one synthetic-id board row."""
    if auth is None:
        return "UNVERIFIABLE"
    if rid is not None:
        return "CORRECT" if rid == auth else "WRONG"
    return "MISSED" if auth in realized_ids else "CORRECT_ABSENT"


def authority(syn: pd.DataFrame, picks: pd.DataFrame, rosters: pd.DataFrame) -> tuple[dict, dict]:
    """(player_id → (gsis|None, source)), plus the pick-key verification record."""
    from app.backend.services import league_scoring as LS

    picks = picks[picks["season"].astype(int) == 2026]
    drafted = syn[syn["draft_pick"].notna()]
    by_pick = picks.groupby(picks["pick"].astype(int))
    unique_picks = bool(by_pick.size().max() == 1) if len(picks) else False
    checks = []
    for _, r in drafted.iterrows():
        pk = int(r["draft_pick"])
        hit = picks[picks["pick"].astype(int) == pk]
        checks.append({"player_id": r["player_id"], "pick": pk, "found": len(hit) == 1,
                       "position_agrees": bool(len(hit) == 1 and LS.normalize_position(
                           hit["position"].iloc[0]) == LS.normalize_position(r["position"])),
                       "draft_name": hit["pfr_player_name"].iloc[0] if len(hit) == 1 else None})
    verified = bool(drafted.shape[0] and unique_picks
                    and all(c["found"] and c["position_agrees"] for c in checks))
    ver = {"drafted_rows": int(drafted.shape[0]), "picks_unique": unique_picks,
           "all_found": all(c["found"] for c in checks),
           "all_positions_agree": all(c["position_agrees"] for c in checks),
           "pick_key_verified": verified,
           "failures": [c for c in checks if not (c["found"] and c["position_agrees"])]}

    ro = rosters[rosters["season"].astype(int) == 2026].copy()
    if "week" in ro.columns:
        ro = ro.sort_values("week").drop_duplicates("gsis_id", keep="last")
    ro = ro[ro["gsis_id"].notna()]
    ro["nkey"] = [f"{LS.normalize_player_name(n)}|{LS.normalize_position(p)}"
                  for n, p in zip(ro["full_name"], ro["position"])]
    by_name = ro.groupby("nkey")["gsis_id"].agg(lambda x: sorted(set(x)))
    pick_map = {int(p): g for p, g in zip(picks["pick"].astype(int), picks["gsis_id"])}

    out = {}
    for _, r in syn.iterrows():
        g, src = None, None
        if verified and pd.notna(r["draft_pick"]):
            gp = pick_map.get(int(r["draft_pick"]))
            if isinstance(gp, str) and gp:
                g, src = gp, "draft_pick"
        if g is None:
            key = f"{LS.normalize_player_name(r['player_name'])}|{LS.normalize_position(r['position'])}"
            cands = by_name.get(key, [])
            if len(cands) == 1:
                g, src = cands[0], "rosters_name (normalizer-dependent)"
            else:
                src = "rosters_name ambiguous" if len(cands) > 1 else "no authority match"
        out[r["player_id"]] = (g, src)
    return out, ver


def name_join_2026() -> dict:
    served = load_served_board()
    boards = board_frame(served)
    from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW
    with timed("nj_load_realized"):
        real, stats_ver = _lake("stats_player_week", [2026], sorted(set(RW.required_columns())))
    real = real[(real["season_type"] == "REG")
                & real["position"].isin(N.REALIZED_POSITIONS)].reset_index(drop=True)
    joined, jdiag = N.identity_join(boards.copy(), real.copy(), (2026,))
    link = {pid: (rid if isinstance(rid, str) else None, how)
            for pid, rid, how in zip(joined["player_id"], joined["rid"], joined["how"])}
    syn = boards[~boards["player_id"].map(lambda x: bool(GSIS_RE.fullmatch(x)))]
    picks, picks_ver = _lake("nflverse_draft_picks", [2026],
                             ["season", "pick", "gsis_id", "pfr_player_name", "position"])
    rosters, rost_ver = _lake("rosters", [2026], ["season", "week", "full_name", "position", "gsis_id"])
    auth, ver = authority(syn, picks, rosters)
    realized_ids = set(real["player_id"])
    rows = []
    for _, r in syn.iterrows():
        rid, how = link.get(r["player_id"], (None, "dropped"))
        g, src = auth[r["player_id"]]
        rows.append({"player_id": r["player_id"], "name": r["player_name"], "pos": r["position"],
                     "draft_pick": None if pd.isna(r["draft_pick"]) else int(r["draft_pick"]),
                     "rung_rid": rid, "rung_how": how, "authority_gsis": g, "authority_source": src,
                     "authority_has_realized_row": bool(g in realized_ids) if g else None,
                     "outcome": classify_join(rid, g, realized_ids)})
    counts = {o: sum(1 for x in rows if x["outcome"] == o) for o in RI.JOIN_OUTCOMES}
    if counts["WRONG"] > 0:
        verdict = "STOP_AND_REPORT"
    elif counts["MISSED"] > 0:
        verdict = "PROCEED_WITH_join_unresolved"
    else:
        verdict = "RUNG_USABLE"
    return {"board_generated_at": served.get("generated_at"),
            "board_model_version": served.get("model_version"),
            "synthetic_rows": len(rows),
            "stats_player_week_version": stats_ver,
            "reg_weeks_present": sorted(int(w) for w in real["week"].unique()),
            "draft_picks_version": picks_ver, "rosters_version": rost_ver,
            "join_diag": jdiag, "pick_key_verification": ver,
            "counts": counts, "verdict": verdict, "rows": rows,
            "named_missed": [x["name"] for x in rows if x["outcome"] == "MISSED"],
            "named_wrong": [x["name"] for x in rows if x["outcome"] == "WRONG"],
            "named_unverifiable": [x["name"] for x in rows if x["outcome"] == "UNVERIFIABLE"]}


def write_name_join(res: dict, meta: dict) -> tuple[Path, Path]:
    jp = RESULTS / f"{NAME_JOIN_STEM}.json"
    mp = RESULTS / f"{NAME_JOIN_STEM}.md"
    jp.write_text(json.dumps(N._clean({"meta": meta, "result": res}), indent=1, sort_keys=True))
    L = ["# NF-ROS1b §8 — the name-join rung on the served 2026 board", "",
         f"Generated {meta['generated_at']} · commit `{meta['commit']}` · board `generated_at "
         f"{res['board_generated_at']}` · stats_player_week v{res['stats_player_week_version']} "
         f"(REG weeks {res['reg_weeks_present']}) · draft_picks v{res['draft_picks_version']} · "
         f"rosters v{res['rosters_version']}", "",
         f"**Verdict: `{res['verdict']}`** — counts {res['counts']} over "
         f"{res['synthetic_rows']} synthetic-id rows.", "",
         f"Pick-key verification: `{res['pick_key_verification']['pick_key_verified']}` "
         f"({ {k: v for k, v in res['pick_key_verification'].items() if k != 'failures'} })", "",
         f"MISSED: {res['named_missed']} · WRONG: {res['named_wrong']} · "
         f"UNVERIFIABLE: {res['named_unverifiable']}", "",
         "| id | name | pos | pick | rung | how | authority | source | outcome |",
         "|---|---|---|---|---|---|---|---|---|"]
    for x in res["rows"]:
        L.append(f"| {x['player_id']} | {x['name']} | {x['pos']} | {x['draft_pick']} | "
                 f"{x['rung_rid']} | {x['rung_how']} | {x['authority_gsis']} | "
                 f"{x['authority_source']} | {x['outcome']} |")
    mp.write_text("\n".join(L) + "\n")
    return jp, mp


# ── entrypoint ────────────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds (2020, 2021) on the 2019-2021 frame — a code-path proof")
    ap.add_argument("--interval", choices=(RI.INTERVAL_NAME, RI.LOCATION_SHIFT),
                    default=RI.INTERVAL_NAME)
    ap.add_argument("--stem", default=None, help="output stem (default by mode)")
    ap.add_argument("--compare-to", default=None,
                    help="an ablation_results JSON to compare the fresh output against at 0.0")
    ap.add_argument("--name-join-2026", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commit": N._commit(), "story": RI.STORY}

    if args.name_join_2026:
        res = name_join_2026()
        jp, mp = write_name_join(res, meta)
        log.info("name-join verdict %s counts %s → %s", res["verdict"], res["counts"], mp)
        return 0

    t_all = time.perf_counter()
    d = N.artifacts_dir()
    hashes = N.verify_prior_hashes(d)
    seasons = (2019, 2020, 2021) if args.smoke else V.PRIOR_SEASONS
    evals = (2020, 2021) if args.smoke else V.EVAL_SEASONS
    with timed("load_frame"):
        frame, diag = N.load_frame(seasons, d)
    frame = prepare_frame(frame)
    result = run(frame, evals, args.interval)
    meta.update({"smoke": args.smoke, "interval": args.interval, "prior_sha16": hashes,
                 "stats_player_week_version": N.STATS_VERSION,
                 "schedules_version": N.SCHEDULES_VERSION, "rows": int(len(frame))})
    stem = args.stem or (STEM if args.interval == RI.INTERVAL_NAME else REPRO_STEM)
    with timed("write_report"):
        jp, mp = write_report(result, diag, smoke=args.smoke, meta=meta, stem=stem)
    TIMINGS["total"] = time.perf_counter() - t_all
    log.info("timings (s): %s", {k: round(v, 2) for k, v in TIMINGS.items()})

    ref = args.compare_to
    if ref is None and args.interval == RI.LOCATION_SHIFT:
        ref = f"{PARENT_STEM}{'_smoke' if args.smoke else ''}.json"
    if ref:
        chk = compare(jp, RESULTS / ref)
        cp = jp.with_name(jp.stem + "_check.json")
        cp.write_text(json.dumps(chk, indent=1))
        log.info("reproduction vs %s: max_abs_diff=%s structural=%s reproduces=%s",
                 ref, chk["max_abs_diff"], chk["n_structural_mismatches"], chk["reproduces"])
        return 0 if chk["reproduces"] else 1
    log.info("wrote %s and %s", jp, mp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
