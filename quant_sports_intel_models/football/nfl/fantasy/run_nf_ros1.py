"""run_nf_ros1.py — NF-ROS1 walk-forward: does 2026-style realized production improve on the prior?

Registered in `ablation_results/nf_ros1_preregistration.md` (+ amendment 1). This file ASSEMBLES
the frame from the pinned inputs, runs the registered walk-forward, applies the registered ship bar
verbatim, and writes `ablation_results/nf_ros1_walkforward{_smoke}.{json,md}`. It never publishes.

Usage (LAPTOP; reads the MAIN checkout's gitignored priors — a worktree lacks them):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1 --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1

`NF_ROS1_ARTIFACTS` overrides the prior directory; the run REFUSES on any hash mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.backend.services import league_scoring as LS
from app.backend.services import realized_stat_fields as R
from app.backend.services.projection_fields import STAT_FIELD
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP
from quant_sports_intel_models.football.nfl.entity.names import normalize_team
from quant_sports_intel_models.football.nfl.fantasy import ros_value as V

log = logging.getLogger("nf_ros1")

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "ablation_results"
MAIN_ARTIFACTS = Path(
    "/Users/charlesclark/Documents/machine_learning/baseball_betting/"
    "baseball_betting_and_fantasy/quant_sports_intel_models/football/nfl/fantasy/artifacts"
)
FRAME_CACHE_DIR = HERE / "artifacts" / "nf_ros1_frame_cache"

#: §2 pins.
STATS_VERSION = 28
SCHEDULES_VERSION = 36
PRIOR_SHA16: dict[str, str] = {
    "nf1_5_season_projections_2019.parquet": "e7640a1026b5ac9d",
    "nf1_5_season_projections_2020.parquet": "c0a7aa5d3d8277ce",
    "nf1_5_season_projections_2021.parquet": "a6645484fd204937",
    "nf1_5_season_projections_2022.parquet": "b76490e08c123f5a",
    "nf1_5_season_projections_2023.parquet": "abebdff5be7e9bbc",
    "nf1_5_season_projections_2024.parquet": "3aa7150e245a54af",
    "nf1_5_season_projections_2025.parquet": "3580273de0469b1d",
    "nfl_fantasy_kdst_projections_2019.parquet": "8c5955a8eb134254",
    "nfl_fantasy_kdst_projections_2020.parquet": "ab4513d2cafc5692",
    "nfl_fantasy_kdst_projections_2021.parquet": "83a11dc70dfa2527",
    "nfl_fantasy_kdst_projections_2022.parquet": "317bc59367da943f",
    "nfl_fantasy_kdst_projections_2023.parquet": "f0593e8c851e70dc",
    "nfl_fantasy_kdst_projections_2024.parquet": "5efac9750e2901a9",
    "nfl_fantasy_kdst_projections_2025.parquet": "509633c49b466bce",
}
REALIZED_POSITIONS = {"QB", "RB", "FB", "HB", "WR", "TE", "K"}
UNRESOLVED_TEAM_MAX_SHARE = 0.01


# ── scoring through the existing machinery (amendment 1 item 2) ───────────────────────────────────
def preset_config(name: str) -> dict:
    return {"standard": LP.standard, "half_ppr": LP.half_ppr, "full_ppr": LP.full_ppr}[name]().to_dict()


def prior_payload_rows(board: pd.DataFrame) -> list[dict]:
    """Board raw line → payload-field rows the scorer reads (STAT_FIELD names)."""
    cols = LP.NFL_PROFILE.stat_columns
    keys = [k for k in STAT_FIELD if cols.get(k) in board.columns]
    out = []
    recs = board[[cols[k] for k in keys]].to_dict("records")
    for rec in recs:
        out.append({STAT_FIELD[k]: rec[cols[k]] for k in keys
                    if rec[cols[k]] is not None and not (isinstance(rec[cols[k]], float)
                                                        and math.isnan(rec[cols[k]]))})
    return out


def resolve_presets(prior_rows: list[dict], realized_flat: list[dict]) -> tuple[dict, dict, dict]:
    """(resolved_for_prior, resolved_for_realized, report) per preset, on the INTERSECTION of the
    terms both sides can express — so the two sides score the same quantity."""
    f_prior = LS.available_fields(prior_rows)
    f_real = LS.available_fields(realized_flat)
    keys_prior = {k for k, f in STAT_FIELD.items() if f in f_prior}
    keys_real = {k for k, f in R.REALIZED_STAT_FIELD.items() if f in f_real}
    both = keys_prior & keys_real
    rp, rr, rep = {}, {}, {}
    for p in V.PRESETS:
        cfg = preset_config(p)
        prior_fields = {STAT_FIELD[k] for k in both}
        real_fields = {R.REALIZED_STAT_FIELD[k] for k in both}
        rp[p], rep_p = LS.resolve_scoring(cfg["scoring"], stat_field=STAT_FIELD, fields=prior_fields)
        rr[p], rep_r = LS.resolve_scoring(cfg["scoring"], stat_field=R.REALIZED_STAT_FIELD,
                                          fields=real_fields)
        applied_p = sorted(t["key"] for t in rep_p["terms"] if t["verdict"] != "captured")
        applied_r = sorted(t["key"] for t in rep_r["terms"] if t["verdict"] != "captured")
        if applied_p != applied_r:
            raise V.RosError(f"{p}: prior and realized resolve different term sets "
                             f"{applied_p} vs {applied_r}")
        rep[p] = {"applied": applied_p,
                  "captured": sorted(t["key"] for t in rep_p["terms"] if t["verdict"] == "captured")}
    return rp, rr, rep


def score_rows(rows: list[dict], positions, resolved: dict, stat_field: dict) -> np.ndarray:
    return np.array([LS.score_row(r, str(p), resolved, stat_field)["pts"]
                     for r, p in zip(rows, positions)], dtype=float)


# ── inputs ────────────────────────────────────────────────────────────────────────────────────────
def artifacts_dir() -> Path:
    return Path(os.environ.get("NF_ROS1_ARTIFACTS") or MAIN_ARTIFACTS)


def verify_prior_hashes(d: Path) -> dict[str, str]:
    seen = {}
    for name, want in PRIOR_SHA16.items():
        p = d / name
        if not p.exists():
            raise V.RosError(f"pinned prior missing: {p} (a worktree lacks the gitignored boards — "
                             "point NF_ROS1_ARTIFACTS at the MAIN checkout's artifacts dir)")
        got = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        if got != want:
            raise V.RosError(f"prior vintage changed: {name} sha256 {got} != pinned {want}")
        seen[name] = got
    return seen


def load_board(d: Path, season: int) -> pd.DataFrame:
    a = pd.read_parquet(d / f"nf1_5_season_projections_{season}.parquet")
    a = a[a["position"].isin(["QB", "RB", "WR", "TE"])]
    k = pd.read_parquet(d / f"nfl_fantasy_kdst_projections_{season}.parquet")
    k = k[k["position"] == "K"]
    b = pd.concat([a, k], ignore_index=True, sort=False)
    b = b.drop_duplicates("player_id", keep="first").reset_index(drop=True)
    b["season"] = season
    b["is_rookie"] = b["is_rookie"].fillna(False).astype(bool)
    b["team_id"] = [normalize_team(t) or None for t in b["team_id"]]
    return b


def _delta_frame(source: str, version: int | None, seasons, columns=None) -> pd.DataFrame:
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io
    t = DeltaTable(s3io.table_uri("nfl", source), version=version,
                   storage_options=s3io.storage_options())
    return t.to_pandas(partitions=[("season", "in", [str(s) for s in seasons])], columns=columns)


def load_realized(seasons, version: int | None) -> pd.DataFrame:
    from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW
    cols = sorted(set(RW.required_columns()))
    df = _delta_frame("stats_player_week", version, seasons, cols)
    df = df[(df["season_type"] == "REG") & df["position"].isin(REALIZED_POSITIONS)].copy()
    df["team"] = [normalize_team(t) for t in df["team"]]
    return df.reset_index(drop=True)


def load_schedule(seasons, version: int | None) -> pd.DataFrame:
    df = _delta_frame("schedules", version, seasons,
                      ["season", "week", "game_type", "home_team", "away_team"])
    df = df[df["game_type"] == "REG"].copy()
    for c in ("home_team", "away_team"):
        df[c] = [normalize_team(t) for t in df[c]]
    return df.reset_index(drop=True)


def team_week_games(sched: pd.DataFrame) -> pd.DataFrame:
    """(season, team, week) → cumulative REG games through week, and the season total."""
    long = pd.concat([sched[["season", "week", "home_team"]].rename(columns={"home_team": "team"}),
                      sched[["season", "week", "away_team"]].rename(columns={"away_team": "team"})])
    long["week"] = long["week"].astype(int)
    long["season"] = long["season"].astype(int)
    rows = []
    for (s, tm), g in long.groupby(["season", "team"]):
        weeks = np.sort(g["week"].to_numpy())
        total = len(weeks)
        for k in V.EVAL_WEEKS:
            t = int((weeks <= k).sum())
            rows.append((s, tm, k, t, total - t, total))
    return pd.DataFrame(rows, columns=["season", "team", "k", "t", "g_rem", "g_season"])


# ── frame assembly ────────────────────────────────────────────────────────────────────────────────
def assemble(seasons, *, stats_version, schedules_version, d: Path) -> tuple[pd.DataFrame, dict]:
    boards = pd.concat([load_board(d, s) for s in seasons], ignore_index=True)
    real = load_realized(seasons, stats_version)
    sched = load_schedule(seasons, schedules_version)
    tw = team_week_games(sched)

    prior_rows = prior_payload_rows(boards)
    real_flat = [R.flatten_realized_row(r) for r in real.to_dict("records")]
    rp, rr, term_report = resolve_presets(prior_rows, real_flat)

    for p in V.PRESETS:
        boards[f"board_{p}"] = score_rows(prior_rows, boards["position"], rp[p], STAT_FIELD)
        real[f"pts_{p}"] = score_rows(real_flat, real["position"], rr[p], R.REALIZED_STAT_FIELD)

    # ── identity join (§2.1, amendment 1 item 1) ──
    real["nkey"] = [f"{LS.normalize_player_name(n)}|{LS.normalize_position(p)}"
                    for n, p in zip(real["player_display_name"], real["position"])]
    boards["nkey"] = [f"{LS.normalize_player_name(n)}|{LS.normalize_position(p)}"
                      for n, p in zip(boards["player_name"], boards["position"])]
    diag = {"seasons": {}}
    link = []
    for s in seasons:
        rs = real[real["season"] == s]
        bs = boards[boards["season"] == s]
        ids = set(rs["player_id"])
        by_key = rs.groupby("nkey")["player_id"].agg(lambda x: sorted(set(x)))
        n_id = n_name = n_amb = n_none = 0
        claimed: dict[str, int] = {}
        board_ids_s = set(bs["player_id"])
        for idx, row in bs.iterrows():
            pid = row["player_id"]
            if pid in ids:
                rid, how = pid, "id"
                n_id += 1
            else:
                cands = by_key.get(row["nkey"], [])
                cands = [c for c in cands if c not in board_ids_s]
                if len(cands) == 1:
                    rid, how = cands[0], "name"
                    n_name += 1
                elif len(cands) > 1:
                    rid, how = None, "ambiguous"
                    n_amb += 1
                else:
                    rid, how = None, "none"
                    n_none += 1
            if rid is not None:
                claimed[rid] = claimed.get(rid, 0) + 1
            link.append((idx, rid, how))
        dup = {r for r, c in claimed.items() if c > 1}
        diag["seasons"][int(s)] = {"board_rows": int(len(bs)), "by_id": n_id, "by_name": n_name,
                                   "ambiguous_dropped": n_amb, "no_realized_row": n_none,
                                   "doubly_claimed_dropped": len(dup)}
    ln = pd.DataFrame(link, columns=["bidx", "rid", "how"]).set_index("bidx")
    boards = boards.join(ln)
    dup_ids = boards.groupby(["season", "rid"]).size()
    dup_ids = {k for k, v in dup_ids.items() if v > 1}
    boards = boards[boards["how"] != "ambiguous"]
    boards = boards[[(s, r) not in dup_ids for s, r in zip(boards["season"], boards["rid"])]]

    # ── per-player weekly realized, keyed (season, rid) ──
    real["week"] = real["week"].astype(int)
    realg = real.groupby(["season", "player_id", "week"], as_index=False).agg(
        team=("team", "last"), **{f"pts_{p}": (f"pts_{p}", "sum") for p in V.PRESETS})
    by_player = {k: g.sort_values("week") for k, g in realg.groupby(["season", "player_id"])}
    teams_by_season = {s: set(tw.loc[tw["season"] == s, "team"]) for s in seasons}
    tw_idx = tw.set_index(["season", "team", "k"])
    league_med = tw.groupby(["season", "k"])[["t", "g_rem", "g_season"]].median()
    league_basis_rows = 0

    rows = []
    unresolved = 0
    off_board_share = {}
    for s in seasons:
        board_ids = set(boards.loc[boards["season"] == s, "rid"].dropna())
        rs = realg[realg["season"] == s]
        tot = rs["pts_full_ppr"].sum()
        off_board_share[int(s)] = float(rs.loc[~rs["player_id"].isin(board_ids), "pts_full_ppr"].sum()
                                        / tot) if tot else math.nan
    for _, b in boards.iterrows():
        s = int(b["season"])
        g = by_player.get((s, b["rid"])) if isinstance(b["rid"], str) else None
        weeks = g["week"].to_numpy() if g is not None else np.array([], dtype=int)
        pts = {p: (g[f"pts_{p}"].to_numpy() if g is not None else np.array([])) for p in V.PRESETS}
        g_board = max(float(b["proj_games"]), 0.0) if pd.notna(b["proj_games"]) else 0.0
        r0 = {p: float(b[f"board_{p}"]) / max(g_board, 1.0) for p in V.PRESETS}
        capped = False
        cap = V.REALIZED_MAX_SEASON_PACE.get(b["position"])
        if cap is not None and r0["full_ppr"] > cap / V.PACE_GAMES:
            scale = (cap / V.PACE_GAMES) / r0["full_ppr"]
            r0 = {p: v * scale for p, v in r0.items()}
            capped = True
        for k in V.EVAL_WEEKS:
            upto = weeks <= k
            team = None
            if upto.any():
                team = str(g["team"].to_numpy()[upto][-1])
            if team not in teams_by_season[s]:
                team = b["team_id"] if b["team_id"] in teams_by_season[s] else team
            basis = "team"
            if team in teams_by_season[s]:
                tr = tw_idx.loc[(s, team, k)]
            elif not upto.any() and not b["team_id"]:
                # amendment 2 item 2 — unsigned, not yet played: league-typical schedule
                tr = league_med.loc[(s, k)]
                basis = "league_median"
                league_basis_rows += 1
            else:
                unresolved += 1
                continue
            n = int(upto.sum())
            last3 = np.where(upto)[0][-3:]
            row = {"season": s, "player_id": b["player_id"], "rid": b["rid"], "k": k,
                   "name": b["player_name"], "pos": b["position"], "team": team,
                   "rookie": bool(b["is_rookie"]), "how": b["how"], "pace_capped": capped,
                   "team_basis": basis,
                   "proj_games": g_board, "t": float(tr["t"]), "g_rem": float(tr["g_rem"]),
                   "g_season": float(tr["g_season"]), "n": n, "last3_n": len(last3)}
            row["a0"] = min(1.0, g_board / row["g_season"]) if row["g_season"] else 0.0
            for p in V.PRESETS:
                row[f"r0_{p}"] = r0[p]
                row[f"board_{p}"] = float(b[f"board_{p}"])
                row[f"xsum_{p}"] = float(pts[p][upto].sum())
                row[f"last3_sum_{p}"] = float(pts[p][last3].sum())
                row[f"y_{p}"] = float(pts[p][weeks > k].sum())
            rows.append(row)
    frame = pd.DataFrame(rows)
    n_ps = frame[["season", "player_id"]].drop_duplicates().shape[0] if len(frame) else 0
    share = unresolved / max(1, unresolved + len(frame))
    if share > UNRESOLVED_TEAM_MAX_SHARE:
        raise V.RosError(f"{share:.3%} of player-weeks have no schedule team (> 1%) — refusing")
    diag.update({"unresolved_team_rows": unresolved, "player_seasons": n_ps,
                 "league_median_basis_rows": league_basis_rows,
                 "pace_capped_player_seasons": int(frame.loc[frame["pace_capped"],
                                                             ["season", "player_id"]]
                                                   .drop_duplicates().shape[0]) if len(frame) else 0,
                 "off_board_realized_share_full_ppr": off_board_share,
                 "scoring_terms": term_report})
    return frame, diag


def add_permuted(frame: pd.DataFrame) -> pd.DataFrame:
    """Amendment 1 item 7: one permutation per (season, position), applied to every k."""
    rng = np.random.default_rng(V.SEED)
    f = frame.copy()
    f["perm_n"] = f["n"]
    for p in V.PRESETS:
        f[f"perm_xsum_{p}"] = f[f"xsum_{p}"]
    for (s, P), g in f.groupby(["season", "pos"], sort=True):
        players = np.array(sorted(g["player_id"].unique()))
        shuffled = players[rng.permutation(len(players))]
        src = dict(zip(players, shuffled))
        look = g.set_index(["player_id", "k"])
        idx = g.index
        donor = [src[pid] for pid in g["player_id"]]
        f.loc[idx, "perm_n"] = look.loc[list(zip(donor, g["k"])), "n"].to_numpy()
        for p in V.PRESETS:
            f.loc[idx, f"perm_xsum_{p}"] = look.loc[list(zip(donor, g["k"])), f"xsum_{p}"].to_numpy()
    return f


# ── walk-forward ──────────────────────────────────────────────────────────────────────────────────
def _loso_residual_table(train: pd.DataFrame, arm: str, preset: str, prefix: str = "") -> dict:
    seasons = sorted(train["season"].unique())
    preds, ys, pos, ks = [], [], [], []
    for s in seasons:
        rest = train[train["season"] != s] if len(seasons) > 1 else train
        p, _ = fit_for(rest, arm, prefix)
        sub = train[train["season"] == s]
        preds.append(ros_for(sub, arm, preset, p, prefix))
        ys.append(sub[f"y_{preset}"].to_numpy())
        pos.append(sub["pos"].to_numpy())
        ks.append(sub["k"].to_numpy())
    return V.fit_residual_table(np.concatenate(pos), np.concatenate(ks),
                                np.concatenate(preds), np.concatenate(ys))


_FIT_CACHE: dict = {}


def fit_for(df: pd.DataFrame, arm: str, prefix: str = "") -> tuple[dict, dict]:
    """Per-position params for an arm. Params are fitted on full-PPR only (§4.3), so a fit is a
    pure function of (the season set, the arm, the realized columns) and is memoized — the
    per-preset loops would otherwise refit identical parameters three times."""
    key = (tuple(sorted(int(x) for x in df["season"].unique())), arm, prefix, len(df))
    if key in _FIT_CACHE:
        return _FIT_CACHE[key]
    _FIT_CACHE[key] = _fit_for(df, arm, prefix)
    return _FIT_CACHE[key]


def _fit_for(df: pd.DataFrame, arm: str, prefix: str = "") -> tuple[dict, dict]:
    params, diag = {}, {}
    for P in V.POSITIONS:
        sub = df[df["pos"] == P]
        if arm == V.INCUMBENT:
            params[P] = V.FormParams(math.inf, math.inf)
            diag[P] = {}
            continue
        fit_arm = V.PRIMARY_ARM if arm == V.MATCHED_FOIL else arm
        p, d = V.fit_params(sub, fit_arm, prefix=prefix)
        params[P], diag[P] = p, d
    return params, diag


def ros_for(df: pd.DataFrame, arm: str, preset: str, params: dict, prefix: str = "") -> np.ndarray:
    out = np.zeros(len(df))
    posv = df["pos"].to_numpy()
    for P, p in params.items():
        m = posv == P
        if m.any():
            out[m] = V.ros_point(df[m], preset, p, prefix=prefix)
    return out


def _fixed_table(train: pd.DataFrame, preset: str, point_fn) -> dict:
    return V.fit_residual_table(train["pos"].to_numpy(), train["k"].to_numpy(),
                                point_fn(train), train[f"y_{preset}"].to_numpy())


def score_fold(frame: pd.DataFrame, Y: int, presets=V.PRESETS) -> dict:
    train = frame[frame["season"] < Y]
    test = frame[frame["season"] == Y].reset_index(drop=True)
    recent = frame[frame["season"] == Y - 1]
    out: dict = {"season": Y, "n_test": len(test), "params": {}, "fallbacks": {}, "pred": {}}
    for preset in presets:
        preds = {}

        def add(name, point, table):
            q, fb = V.apply_residual_table(table, test["pos"], test["k"], point)
            preds[name] = (point, q)
            out["fallbacks"][f"{preset}:{name}"] = fb

        # incumbent + real arms (LOSO residuals)
        for arm in (V.INCUMBENT,) + V.ARMS:
            params, d = fit_for(train, arm)
            if preset == V.GATE_PRESET:
                out["params"][arm] = {P: {"m_r": _j(p.m_r), "m_a": _j(p.m_a), **{
                    kk: (_j(vv) if isinstance(vv, float) else vv) for kk, vv in d[P].items()
                    if kk not in ("m_r", "m_a")}} for P, p in params.items()}
            table = _loso_residual_table(train, arm, preset)
            add(arm, ros_for(test, arm, preset, params), table)
        # matched foil — permuted history on BOTH train and test
        pparams, pd_ = fit_for(train, V.MATCHED_FOIL, prefix="perm_")
        if preset == V.GATE_PRESET:
            out["params"][V.MATCHED_FOIL] = {P: {"m_r": _j(p.m_r), "m_a": _j(p.m_a)}
                                            for P, p in pparams.items()}
        ptable = _loso_residual_table(train, V.MATCHED_FOIL, preset, prefix="perm_")
        add(V.MATCHED_FOIL, ros_for(test, V.MATCHED_FOIL, preset, pparams, prefix="perm_"), ptable)
        # point degenerates
        for dname in ("frozen_full", "naive_pace", "last3_pace", "nihilist_zero"):
            fn = (lambda df, dn=dname: V.degenerate_point(df, preset, dn))
            add(dname, fn(test), _fixed_table(train, preset, fn))
        # per-form oracle + matched-n (fixed params; amendment 1 item 3)
        for arm in V.ARMS:
            op, _ = fit_for(test, arm)
            mp, _ = fit_for(recent, arm)
            if preset == V.GATE_PRESET:
                out["params"][f"oracle_{arm}"] = {P: {"m_r": _j(p.m_r), "m_a": _j(p.m_a)}
                                                 for P, p in op.items()}
                out["params"][f"matched_n_{arm}"] = {P: {"m_r": _j(p.m_r), "m_a": _j(p.m_a)}
                                                    for P, p in mp.items()}
            for nm, pr in ((f"oracle_{arm}", op), (f"matched_n_{arm}", mp)):
                fn = (lambda df, a=arm, pp=pr: ros_for(df, a, preset, pp))
                add(nm, fn(test), _fixed_table(train, preset, fn))
        out["pred"][preset] = preds
    out["test"] = test
    return out


def _j(v):
    return "inf" if isinstance(v, float) and math.isinf(v) else v


def add_width_degenerates(fold: dict, winner: str, frame: pd.DataFrame, preset: str) -> None:
    preds = fold["pred"][preset]
    point, _ = preds[winner]
    test = fold["test"]
    train = frame[frame["season"] < fold["season"]]
    preds["zero_width"] = (point, np.repeat(point[:, None], len(V.LEVELS), axis=1))
    hi = np.array([train.loc[train["pos"] == P, f"y_{preset}"].max() for P in test["pos"]])
    # registered as the interval [0, max]: every level below the median at 0, the rest at the max
    q = np.zeros((len(point), len(V.LEVELS)))
    q[:, V.LEVELS >= 0.5] = hi[:, None]
    preds["max_width"] = (point, q)


# ── statistics ────────────────────────────────────────────────────────────────────────────────────
def one_sided_p(d) -> float | None:
    from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M1
    return M1.onesided_paired_pvalue(np.asarray(d, dtype=float))


def dsr(d, trial_srs) -> float | None:
    from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M1
    return M1.deflated_sharpe(np.asarray(d, dtype=float), np.asarray(trial_srs, dtype=float))


def sharpe(d) -> float:
    d = np.asarray(d, dtype=float)
    sd = d.std(ddof=1) if len(d) > 1 else 0.0
    return float(d.mean() / sd) if sd > 1e-12 else math.nan


def pbo(scores: np.ndarray) -> float | None:
    """scores: (n_configs, n_folds) — HIGHER is better for cscv_pbo, so pass negated CRPS."""
    from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M1
    return M1.cscv_pbo(scores)


def bh(pvals: dict) -> dict:
    from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M1
    return M1.bh_fdr(pvals, q=V.BH_Q)


def block_bootstrap_ci(crps_a: np.ndarray, crps_b: np.ndarray, groups: np.ndarray) -> list[float]:
    rng = np.random.default_rng(V.SEED)
    d = crps_b - crps_a
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=d)
    cnts = np.bincount(inv)
    stats = []
    for _ in range(2000):
        pick = rng.integers(0, len(uniq), len(uniq))
        stats.append(sums[pick].sum() / cnts[pick].sum())
    return [float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))]


def evaluate(frame: pd.DataFrame, seasons=V.EVAL_SEASONS) -> dict:
    from betting_ml.utils import cv_power as CP
    from betting_ml.utils.coverage_power_floor import power_floor

    folds = [score_fold(frame, Y) for Y in seasons]
    nF = len(folds)
    G = V.GATE_PRESET

    # ── per fold × position × predictor CRPS (gate preset) ──
    def crps_rows(fold, name, preset=G):
        point, q = fold["pred"][preset][name]
        return V.crps_q(fold["test"][f"y_{preset}"], q)

    names = list(folds[0]["pred"][G].keys())
    pooled = {nm: [float(crps_rows(f, nm).mean()) for f in folds] for nm in names}

    # winner = real arm with lowest pooled CRPS (mean over folds of pooled fold means)
    winner = min(V.ARMS, key=lambda a: float(np.mean(pooled[a])))
    for f in folds:
        for preset in V.PRESETS:
            add_width_degenerates(f, winner, frame, preset)
    names = list(folds[0]["pred"][G].keys())

    per_pos = {}
    for P in V.POSITIONS:
        tab = {}
        for nm in names:
            vals = []
            for f in folds:
                m = (f["test"]["pos"] == P).to_numpy()
                vals.append(float(crps_rows(f, nm)[m].mean()) if m.any() else math.nan)
            tab[nm] = vals
        per_pos[P] = tab

    # ── field-level PBO precondition ──
    field = [V.INCUMBENT] + list(V.ARMS)
    # cscv_pbo: (n_configs, n_seasons), HIGHER is better ⇒ negated CRPS.
    field_scores = -np.array([pooled[a] for a in field])
    field_pbo = pbo(field_scores)
    pbo_ok = field_pbo is not None and field_pbo < V.PBO_MAX

    # ── NF1.8 triad for the form search ──
    flips = {}
    for i in range(nF):
        best = min(V.ARMS, key=lambda a: pooled[a][i])
        flips[best] = flips.get(best, 0) + 1
    arm_means = {a: float(np.mean(pooled[a])) for a in V.ARMS}

    positions = {}
    pvals = {}
    for P in V.POSITIONS:
        tab = per_pos[P]
        lifts = np.array(tab[V.INCUMBENT]) - np.array(tab[winner])
        pvals[P] = one_sided_p(lifts)
        trial_srs = [sharpe(np.array(tab[V.INCUMBENT]) - np.array(tab[a])) for a in V.ARMS]
        pos_d = {
            "per_fold_crps": {nm: tab[nm] for nm in names},
            "lift_per_fold": lifts.tolist(),
            "mean_lift": float(lifts.mean()),
            "folds_won": int((lifts > 0).sum()),
            "p_one_sided": pvals[P],
            "trial_sharpes": trial_srs,
            "dsr": dsr(lifts, trial_srs),
        }
        # rows for pooled stats
        ys, qs, grp, crps_w, crps_i = [], [], [], [], []
        pit_rng = np.random.default_rng(V.SEED + V.POSITIONS.index(P))
        for f in folds:
            m = (f["test"]["pos"] == P).to_numpy()
            if not m.any():
                continue
            y = f["test"][f"y_{G}"].to_numpy()[m]
            q = f["pred"][G][winner][1][m]
            ys.append(y)
            qs.append(q)
            grp.append((f["test"]["season"].astype(str) + "|" + f["test"]["player_id"]).to_numpy()[m])
            crps_w.append(V.crps_q(y, q))
            crps_i.append(V.crps_q(y, f["pred"][G][V.INCUMBENT][1][m]))
        y = np.concatenate(ys)
        q = np.concatenate(qs)
        g = np.concatenate(grp)
        cov = V.coverage80(y, q)
        n_ps = len(np.unique(g))
        floor = power_floor(n_ps, nominal=V.COVERAGE_NOMINAL, target=V.COVERAGE_TARGET)
        pit = V.randomized_pit(y, q, pit_rng)
        pos_d["coverage80"] = float(cov.mean())
        pos_d["coverage_floor"] = float(floor)
        pos_d["coverage_n_player_seasons"] = int(n_ps)
        pos_d["pit_max_decile_dev"] = V.max_decile_dev(pit)
        pos_d["bootstrap_ci_lift"] = block_bootstrap_ci(np.concatenate(crps_w),
                                                        np.concatenate(crps_i), g)
        # anchors
        foil_l = np.array(tab[V.MATCHED_FOIL]) - np.array(tab[winner])
        orc = np.array(tab[f"oracle_{winner}"])
        mn = np.array(tab[f"matched_n_{winner}"])
        beat_oracle = orc - np.array(tab[winner])
        p_orc = one_sided_p(beat_oracle)
        pooled_win = float(np.mean(tab[winner]))
        degen = {dn: float(np.mean(tab[dn])) for dn in V.DEGENERATES}
        mn_gap = float(np.mean(mn) - np.mean(orc))
        pair_inactive = abs(mn_gap) <= V.INACTIVE_PAIR_TOL
        # max_width coverage (must SATISFY the floor and still lose — NF1.8)
        mw_cov = float(np.concatenate([V.coverage80(
            f["test"][f"y_{G}"].to_numpy()[(f["test"]["pos"] == P).to_numpy()],
            f["pred"][G]["max_width"][1][(f["test"]["pos"] == P).to_numpy()]) for f in folds]).mean())
        pos_d.update({
            "foil_lift_per_fold": foil_l.tolist(),
            "winner_beats_oracle_per_fold": beat_oracle.tolist(),
            "p_winner_beats_oracle": p_orc,
            "oracle_minus_matched_n": -mn_gap,
            "matched_n_pair_inactive": bool(pair_inactive),
            "degenerate_pooled_crps": degen,
            "winner_pooled_crps": pooled_win,
            "max_width_coverage80": mw_cov,
            "collapsed_to_incumbent": [folds[i]["params"][winner][P].get("collapsed_to_incumbent")
                                       for i in range(nF)],
        })
        positions[P] = pos_d

    bh_pass = bh(pvals)
    for P, d in positions.items():
        collapsed = any(bool(c) for c in d["collapsed_to_incumbent"])
        c = {
            "C1_beats_incumbent": d["mean_lift"] > 0 and not collapsed,
            "C2_fold_consistency": d["folds_won"] >= V.FOLD_WINS_REQUIRED,
            "C3_significant_bh": bool(bh_pass.get(P)),
            "C4_dsr_ok": d["dsr"] is not None and d["dsr"] >= V.DSR_MIN,
            "C5_beats_matched_foil": (float(np.mean(d["foil_lift_per_fold"])) > 0
                                      and int((np.array(d["foil_lift_per_fold"]) > 0).sum())
                                      >= V.FOLD_WINS_REQUIRED),
            "C6_degenerates_lose": all(v > d["winner_pooled_crps"]
                                       for v in d["degenerate_pooled_crps"].values()),
            "C7_coverage_floor": d["coverage80"] >= d["coverage_floor"],
            "C8a_oracle_floor": not (
                float(np.mean(d["winner_beats_oracle_per_fold"])) < 0
                and -float(np.mean(d["winner_beats_oracle_per_fold"]))
                > V.ORACLE_MATERIAL_SHARE * max(d["mean_lift"], 0.0)
                and d["p_winner_beats_oracle"] is not None
                and (1.0 - d["p_winner_beats_oracle"]) < V.ORACLE_P),
            "C8b_matched_n": (True if d["matched_n_pair_inactive"]
                              else d["oracle_minus_matched_n"] <= V.MATCHED_N_TOL),
            "C9_pit_flat": d["pit_max_decile_dev"] <= V.PIT_MAX_DECILE_DEV,
        }
        d["clauses"] = c
        d["ships"] = bool(pbo_ok and all(c.values()))
        if not d["ships"]:
            failed = [k for k, v in c.items() if not v]
            anchor_bound = any(k.split("_")[0] in ("C5", "C6", "C7", "C8a", "C8b", "C9")
                               for k in failed)
            nv = CP.classify_null(
                metric="crps_q19_full_ppr", n_folds=nF, n_arms=V.DECLARED_FIELD_SIZE,
                beats_foil=d["mean_lift"] > 0, observed_sr=sharpe(d["lift_per_fold"]),
                var_trials_sr=float(np.nanvar(d["trial_sharpes"], ddof=1)),
                fold_wins=d["folds_won"], p_one_sided=d["p_one_sided"],
                pbo=field_pbo, pbo_application="field",
                degenerates_excluded_from_v=True,
                declared_field_size=V.DECLARED_FIELD_SIZE)
            d["null"] = {"classify_null_state": nv.state, "classify_null_reason": nv.reason,
                         "failed_clauses": failed,
                         "reported_state": ("CONSTRAINT_REFUSED" if anchor_bound else nv.state),
                         "binding_half": "anchor" if anchor_bound else "statistical"}
        # the channel interaction (reported, never recombined)
        tab = per_pos[P]
        base = np.array(tab[V.INCUMBENT])
        lr = float(np.mean(base - np.array(tab["eb_rate"])))
        la = float(np.mean(base - np.array(tab["eb_avail"])))
        lb = float(np.mean(base - np.array(tab["eb_rate_avail"])))
        d["channel_2x2"] = {"lift_rate": lr, "lift_avail": la, "lift_both": lb,
                            "interaction": lb - lr - la}

    # per-k and rookie strata (reported)
    strata = {}
    for f in folds:
        t = f["test"]
        cw = V.crps_q(t[f"y_{G}"], f["pred"][G][winner][1])
        ci = V.crps_q(t[f"y_{G}"], f["pred"][G][V.INCUMBENT][1])
        for key, mask in [(f"k{k}", t["k"] == k) for k in V.EVAL_WEEKS] + [
                ("rookie", t["rookie"]), ("veteran", ~t["rookie"])]:
            m = mask.to_numpy()
            s = strata.setdefault(key, [0.0, 0])
            s[0] += float((ci[m] - cw[m]).sum())
            s[1] += int(m.sum())
    strata = {k: {"mean_lift": v[0] / v[1] if v[1] else None, "rows": v[1]} for k, v in strata.items()}

    other_presets = {}
    for preset in V.PRESETS:
        if preset == G:
            continue
        other_presets[preset] = {nm: [float(crps_rows(f, nm, preset).mean()) for f in folds]
                                 for nm in (V.INCUMBENT, winner)}

    waiver = evaluate_waiver(folds, winner, frame,
                             [P for P, d in positions.items() if d["ships"]])

    return {
        "winner": winner,
        "arm_pooled_mean_crps": arm_means,
        "pooled_per_fold_crps": pooled,
        "field_pbo": field_pbo,
        "field_pbo_ok": pbo_ok,
        "flip_distribution": flips,
        "positions": positions,
        "strata": strata,
        "other_presets": other_presets,
        "params": {f["season"]: f["params"] for f in folds},
        "residual_fallbacks": {f["season"]: f["fallbacks"] for f in folds},
        "waiver": waiver,
        "folds": [f["season"] for f in folds],
        "_folds_obj": folds,
    }


def evaluate_waiver(folds, winner: str, frame: pd.DataFrame, shipped: list[str]) -> dict:
    """§7. INACTIVE unless ≥2 positions ship."""
    if len(shipped) < 2:
        return {"state": "INACTIVE", "reason": f"only {len(shipped)} position(s) ship the value",
                "shipped_positions": shipped}
    G = V.GATE_PRESET
    per_order = {o: [] for o in V.WAIVER_ORDERINGS + ("oracle_order", "random_order")}
    k_counts = {o: {"top10": 0, "top25": 0, "slates": 0} for o in V.WAIVER_ORDERINGS}
    rng = np.random.default_rng(V.SEED)
    for f in folds:
        t = f["test"]
        Y = f["season"]
        s_frame = frame[frame["season"] == Y]
        # rostered proxy: K top-12 by board points; skill top-156 by preseason draft VOR
        pre = s_frame[s_frame["k"] == 1].drop_duplicates("player_id")
        rostered = set(pre[pre["pos"] == "K"].nlargest(V.WAIVER_K_ROSTERED, f"board_{G}")["player_id"])
        skill = pre[pre["pos"].isin(["QB", "RB", "WR", "TE"])]
        cfg = preset_config(G)
        repl, _ = LS.replacement_levels(
            [{"pos": p, "pts": v} for p, v in zip(skill["pos"], skill[f"board_{G}"])], cfg)
        vor = skill[f"board_{G}"] - skill["pos"].map(repl).fillna(0.0)
        rostered |= set(skill.assign(vor=vor).nlargest(V.WAIVER_SKILL_ROSTERED, "vor")["player_id"])
        vals = {o: [] for o in per_order}
        for k in V.EVAL_WEEKS:
            m = ((t["k"] == k) & t["pos"].isin(shipped)).to_numpy()
            sub = t[m]
            pos = sub["pos"].to_numpy()
            ros, q = f["pred"][G][winner][0][m], f["pred"][G][winner][1][m]
            fa = ~sub["player_id"].isin(rostered).to_numpy()
            util = V.realized_utility(sub[f"y_{G}"].to_numpy(), pos)
            if fa.sum() < V.WAIVER_TOP_N:
                continue
            fa_idx = np.where(fa)[0]
            for o in V.WAIVER_ORDERINGS:
                sc = V.waiver_scores(o, ros, q, pos, fa)
                order = fa_idx[np.argsort(-sc[fa_idx], kind="stable")]
                vals[o].append(float(util[order[:V.WAIVER_TOP_N]].mean()))
                k_counts[o]["top10"] += int((pos[order[:10]] == "K").sum())
                k_counts[o]["top25"] += int((pos[order[:25]] == "K").sum())
                k_counts[o]["slates"] += 1
            vals["oracle_order"].append(float(np.sort(util[fa_idx])[::-1][:V.WAIVER_TOP_N].mean()))
            vals["random_order"].append(float(util[rng.choice(fa_idx, V.WAIVER_TOP_N,
                                                              replace=False)].mean()))
        for o in per_order:
            per_order[o].append(float(np.mean(vals[o])) if vals[o] else math.nan)
    res = {"state": "EVALUATED", "shipped_positions": shipped, "per_fold_utility": per_order,
           "kicker_counts": k_counts}
    prim = np.array(per_order[V.WAIVER_PRIMARY])
    pv, comps = {}, {}
    for foil in V.WAIVER_FOILS:
        d = prim - np.array(per_order[foil])
        pv[foil] = one_sided_p(d)
        comps[foil] = {"lift_per_fold": d.tolist(), "mean_lift": float(np.mean(d)),
                       "folds_won": int((d > 0).sum())}
    bhp = bh(pv)
    for foil in V.WAIVER_FOILS:
        comps[foil]["p_one_sided"] = pv[foil]
        comps[foil]["bh_pass"] = bool(bhp.get(foil))
    random_loses = float(np.mean(per_order["random_order"])) < float(np.mean(prim))
    ships = random_loses and all(c["mean_lift"] > 0 and c["folds_won"] >= V.FOLD_WINS_REQUIRED
                                 and c["bh_pass"] for c in comps.values())
    res.update({"comparisons": comps, "random_order_loses": random_loses, "ships": bool(ships)})
    return res


# ── report ────────────────────────────────────────────────────────────────────────────────────────
def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None if math.isnan(o) else ("inf" if o > 0 else "-inf")
    return o


def write_report(result: dict, diag: dict, *, smoke: bool, meta: dict) -> tuple[Path, Path]:
    tag = "_smoke" if smoke else ""
    jp = RESULTS / f"nf_ros1_walkforward{tag}.json"
    mp = RESULTS / f"nf_ros1_walkforward{tag}.md"
    payload = _clean({"meta": meta, "diagnostics": diag, "result": result})
    jp.write_text(json.dumps(payload, indent=1, sort_keys=True))
    L = [f"# NF-ROS1 walk-forward{' — SMOKE (code-path proof, never a gate)' if smoke else ''}",
         "", f"Generated {meta['generated_at']} · commit `{meta['commit']}` · folds "
         f"{result['folds']} · registration `nf_ros1_preregistration.md` + amendments 1–2.", "",
         f"**Winner (pooled full-PPR CRPS):** `{result['winner']}` · field PBO "
         f"{result['field_pbo']} (precondition < {V.PBO_MAX}: "
         f"{'PASS' if result['field_pbo_ok'] else 'FAIL'}) · flips {result['flip_distribution']}", "",
         "| arm | pooled mean CRPS |", "|---|---|"]
    for a, v in result["arm_pooled_mean_crps"].items():
        L.append(f"| `{a}` | {v:.4f} |")
    L += ["", "## Per position (gate: full-PPR 12-team)", "",
          "| pos | mean lift | folds won | p | DSR | foil lift | cov80 / floor | PIT dev | ships |",
          "|---|---|---|---|---|---|---|---|---|"]
    for P, d in result["positions"].items():
        L.append(f"| {P} | {d['mean_lift']:+.4f} | {d['folds_won']}/{len(result['folds'])} | "
                 f"{d['p_one_sided']} | {d['dsr']} | {np.mean(d['foil_lift_per_fold']):+.4f} | "
                 f"{d['coverage80']:.3f} / {d['coverage_floor']:.3f} | "
                 f"{d['pit_max_decile_dev']:.4f} | {'**YES**' if d['ships'] else 'no'} |")
    L += ["", "### Clauses", ""]
    for P, d in result["positions"].items():
        failed = [k for k, v in d["clauses"].items() if not v]
        L.append(f"- **{P}**: {'all pass' if not failed else 'FAILED ' + ', '.join(failed)}"
                 + (f" → `{d['null']['reported_state']}` (classify_null: "
                    f"`{d['null']['classify_null_state']}`)" if 'null' in d else ""))
    L += ["", "### Channel 2×2 (reported, never recombined)", "",
          "| pos | rate | avail | both | interaction |", "|---|---|---|---|---|"]
    for P, d in result["positions"].items():
        c = d["channel_2x2"]
        L.append(f"| {P} | {c['lift_rate']:+.4f} | {c['lift_avail']:+.4f} | {c['lift_both']:+.4f} "
                 f"| {c['interaction']:+.4f} |")
    L += ["", "### Degenerates (pooled CRPS; must exceed the winner)", ""]
    for P, d in result["positions"].items():
        L.append(f"- {P}: winner {d['winner_pooled_crps']:.3f} · " + " · ".join(
            f"{k} {v:.3f}" for k, v in d["degenerate_pooled_crps"].items())
                 + f" · max_width cov80 {d['max_width_coverage80']:.3f}")
    L += ["", "### Strata (mean CRPS lift over incumbent, per row)", ""]
    L.append(" · ".join(f"{k} {v['mean_lift']:+.3f}" for k, v in result["strata"].items()
                        if v["mean_lift"] is not None))
    w = result["waiver"]
    L += ["", "## Waiver replacement (§7)", "", f"State: **{w['state']}**"
          + (f" — {w.get('reason')}" if w.get("reason") else "")]
    if w["state"] == "EVALUATED":
        L.append("")
        for o, v in w["per_fold_utility"].items():
            L.append(f"- `{o}`: mean utility {np.nanmean(v):.3f} · per fold "
                     + ", ".join(f"{x:.2f}" for x in v))
        for foil, c in w["comparisons"].items():
            L.append(f"- expected_excess vs `{foil}`: lift {c['mean_lift']:+.3f}, "
                     f"{c['folds_won']}/{len(result['folds'])}, p {c['p_one_sided']}, "
                     f"BH {c['bh_pass']}")
        L.append(f"- kicker counts (top10/top25 over slates): {w['kicker_counts']}")
        L.append(f"- random loses: {w['random_order_loses']} · **ships: {w['ships']}**")
    L += ["", "## Diagnostics", "", "```", json.dumps(_clean(diag), indent=1)[:4000], "```"]
    mp.write_text("\n".join(L) + "\n")
    return jp, mp


def _commit() -> str:
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, cwd=HERE, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001 - provenance only
        return "unknown"


def frame_cache_key(seasons) -> str:
    h = hashlib.sha256()
    for f in (Path(__file__), HERE / "ros_value.py"):
        h.update(f.read_bytes())
    h.update(json.dumps([list(seasons), STATS_VERSION, SCHEDULES_VERSION, PRIOR_SHA16]).encode())
    return h.hexdigest()[:16]


def load_frame(seasons, d: Path) -> tuple[pd.DataFrame, dict]:
    FRAME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = frame_cache_key(seasons)
    fp = FRAME_CACHE_DIR / f"frame_{key}.parquet"
    dp = FRAME_CACHE_DIR / f"diag_{key}.json"
    if fp.exists() and dp.exists():
        return pd.read_parquet(fp), json.loads(dp.read_text())
    frame, diag = assemble(seasons, stats_version=STATS_VERSION,
                           schedules_version=SCHEDULES_VERSION, d=d)
    frame.to_parquet(fp)
    dp.write_text(json.dumps(_clean(diag)))
    return frame, diag


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds (2020, 2021) on the 2019-2021 frame — a code-path proof")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    d = artifacts_dir()
    hashes = verify_prior_hashes(d)
    seasons = (2019, 2020, 2021) if args.smoke else V.PRIOR_SEASONS
    evals = (2020, 2021) if args.smoke else V.EVAL_SEASONS
    frame, diag = load_frame(seasons, d)
    frame = add_permuted(frame)
    result = evaluate(frame, evals)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commit": _commit(), "smoke": args.smoke, "prior_sha16": hashes,
            "stats_player_week_version": STATS_VERSION, "schedules_version": SCHEDULES_VERSION,
            "rows": int(len(frame))}
    jp, mp = write_report(result, diag, smoke=args.smoke, meta=meta)
    log.info("wrote %s and %s", jp, mp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
