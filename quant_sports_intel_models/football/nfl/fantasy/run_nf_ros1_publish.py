"""run_nf_ros1_publish.py — NF-ROS1b node 4: build + publish the certified REST-OF-SEASON value.

Registered in `ablation_results/nf_ros1b_preregistration.md` §9 (+ amendment 1). Contract:
`app/backend/models/nfl_ros.py`.

TWO STEPS, AND THE SPLIT IS THE NF-INFRA1 LANDMINE AVOIDED RATHER THAN A TIDINESS CHOICE.

  1. `--fit-params` (LAPTOP, once): fit the certified form on the 2019–2025 history — `m` per
     position, the hurdle's logistic per (preset, position), and the ratio table per preset — and
     write `serving_params/nf_ros1b_params_<season>.json`, which is COMMITTED. The history it reads
     (the gitignored preseason boards) does not exist in the box image, so a box build that tried
     to fit would die at its first read. The history does not change, so fitting once is exact:
     this IS "serve-time fitting on 2019–2025", frozen and diffable (the NCAAF-S1-serve coefficient
     table pattern — no pickle, nothing a library bump can break).
  2. the BUILD (box-capable): the committed params + the PUBLISHED 2026 board + the live lake
     (`stats_player_week`, `schedules`, and the draft/roster authority for the identity audit) →
     three validated blobs → the write-gate → (with `--publish`) the api-cache → a served-bytes
     read-back.

Usage:

    # laptop, once (reads the MAIN checkout's pinned boards; `env -u TOKEN`, registration §11)
    env -u TOKEN uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1_publish --fit-params
    # dry-run build (stages locally, runs every gate, uploads nothing)
    env -u TOKEN uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_ros1_publish
    # the real publish (POST-MERGE operator step)
    ... run_nf_ros1_publish --publish --s3-bucket credence-prod-s3-api-cache

Exit codes: 0 built (and published when asked); 3 no FINAL REG week yet (nothing to update — a
clean skip, never a zero-row artifact).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.backend.models import nfl_ros as C
from app.backend.services import league_scoring as LS
from app.backend.services import realized_stat_fields as R
from app.backend.services.projection_fields import STAT_FIELD
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP
from quant_sports_intel_models.football.nfl.fantasy import ros_interval as RI
from quant_sports_intel_models.football.nfl.fantasy import ros_value as V
from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1 as N

log = logging.getLogger("nf_ros1_publish")

HERE = Path(__file__).resolve().parent
PARAMS_DIR = HERE / "serving_params"
STAGING = HERE / "artifacts" / "ros_serving"
DECISIVE_RECORD = N.RESULTS / "nf_ros1b_walkforward.json"
SERVING_SEASON = 2026
EXIT_NO_FINAL_WEEK = 3
COHERENCE_TOL = 1e-9
SERVED_BOARD_KEY = "fantasy/nfl/{season}/projections.json"


class RosPublishError(RuntimeError):
    """A registered precondition failed — the build refuses rather than ship a different artifact."""


def params_path(season: int) -> Path:
    return PARAMS_DIR / f"nf_ros1b_params_{season}.json"


# ── step 1: fit the serving params (laptop) ───────────────────────────────────────────────────────
def _inf(v):
    return None if isinstance(v, float) and math.isinf(v) else v


def _table_to_json(t: dict) -> dict:
    return {"edges": {P: list(map(float, e)) for P, e in t["edges"].items()},
            "cell": {f"{P}|{b}|{tt}": list(map(float, q)) for (P, b, tt), q in t["cell"].items()},
            "kb": {f"{P}|{b}": list(map(float, q)) for (P, b), q in t["kb"].items()},
            "pos": {P: list(map(float, q)) for P, q in t["pos"].items()}}


def table_from_json(j: dict) -> dict:
    def split(k):
        parts = k.split("|")
        return (parts[0], *map(int, parts[1:]))
    return {"edges": {P: np.array(e) for P, e in j["edges"].items()},
            "cell": {split(k): np.array(q) for k, q in j["cell"].items()},
            "kb": {split(k): np.array(q) for k, q in j["kb"].items()},
            "pos": {P: np.array(q) for P, q in j["pos"].items()}}


def _pi_to_json(m: dict) -> dict:
    out = {"single_class": bool(m["single_class"]), "base": float(m["base"]),
           "dropped": int(m["dropped"]), "mu": m["mu"].tolist(), "sd": m["sd"].tolist(),
           "keep": [bool(x) for x in m["keep"]]}
    if not m["single_class"]:
        out.update({"coef": m["coef"].tolist(), "intercept": float(m["intercept"])})
    return out


def pi_from_json(j: dict) -> dict:
    m = {"single_class": j["single_class"], "base": j["base"], "dropped": j["dropped"],
         "mu": np.array(j["mu"]), "sd": np.array(j["sd"]), "keep": np.array(j["keep"], dtype=bool)}
    if not j["single_class"]:
        m.update({"coef": np.array(j["coef"]), "intercept": j["intercept"]})
    return m


def certification_table(record: dict) -> tuple[list[dict], list[str]]:
    """The decisive run's per-position verdicts, verbatim — and the certified set DERIVED from them
    (never typed: a hand list is how a refused position gets served)."""
    rows, certified = [], []
    for P, d in record["result"]["positions"].items():
        failed = [k for k, v in d["clauses"].items() if not v]
        rows.append({"pos": P, "certified": bool(d["ships"]), "failed_clauses": failed,
                     "mean_lift": d["mean_lift"], "folds_won": d["folds_won"],
                     "pit_max_decile_dev": d["pit_max_decile_dev"],
                     "coverage80": d["coverage80"], "coverage_floor": d["coverage_floor"],
                     "reported_state": (d.get("null") or {}).get("reported_state")})
        if d["ships"]:
            certified.append(P)
    return rows, certified


def fit_serving_params(frame: pd.DataFrame, diag: dict, record: dict) -> dict:
    """The certified form fitted on every history season — what the 2026 'fold' would train on."""
    if record["result"]["winner"] != V.PRIMARY_ARM:
        raise RosPublishError(f"the decisive winner is {record['result']['winner']}, not "
                              f"{V.PRIMARY_ARM} — the serving form must be the certified one")
    params, _ = N.fit_for(frame, V.PRIMARY_ARM)
    iv = RI.HurdleInterval()
    tables = {p: _table_to_json(N._loso_residual_table(frame, V.PRIMARY_ARM, p, interval=iv))
              for p in V.PRESETS}
    X = RI.pi_features(frame)
    pos = frame["pos"].to_numpy()
    pis = {p: {P: _pi_to_json(RI.fit_pi(X[pos == P], (frame.loc[pos == P, f"y_{p}"] <= 0)
                                        .astype(int).to_numpy()))
               for P in V.POSITIONS} for p in V.PRESETS}
    cert, certified = certification_table(record)
    terms = diag["scoring_terms"]
    return {
        "story": C.STORY, "serving_season": SERVING_SEASON,
        "history_seasons": sorted(int(s) for s in frame["season"].unique()),
        "form": V.PRIMARY_ARM,
        "m": {P: {"m_r": _inf(p.m_r), "m_a": _inf(p.m_a)} for P, p in params.items()},
        "pi": pis, "ratio_tables": tables,
        "certification": cert, "certified_positions": certified,
        "certified_weeks": [min(V.EVAL_WEEKS), max(V.EVAL_WEEKS)],
        "scoring_terms": {p: terms[p]["applied"] for p in V.PRESETS},
        "stat_keys": terms["_stat_keys"],
        "decisive_commit": record["meta"]["commit"],
        "prior_sha16": record["meta"]["prior_sha16"],
        "stats_player_week_version": N.STATS_VERSION,
        "schedules_version": N.SCHEDULES_VERSION,
        "frame_rows": int(len(frame)),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": N._commit(),
    }


def load_params(season: int) -> tuple[dict, str]:
    p = params_path(season)
    if not p.exists():
        raise RosPublishError(f"no committed serving params at {p} — run --fit-params on the laptop")
    raw = p.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


# ── step 2: the build ─────────────────────────────────────────────────────────────────────────────
def served_board_frame(served: dict, season: int) -> pd.DataFrame:
    """The PUBLISHED board, in `run_nf_ros1.load_board`'s column shape (evaluated positions only)."""
    cols = LP.NFL_PROFILE.stat_columns
    rows = []
    for r in served["players"]:
        if r.get("pos") not in V.POSITIONS:
            continue
        row = {"player_id": str(r["id"]), "player_name": r["name"], "position": r["pos"],
               "team_id": r.get("team"), "proj_games": r.get("g"),
               "is_rookie": bool(r.get("rookie")), "season": season}
        for k, field in STAT_FIELD.items():
            if k in cols and r.get(field) is not None:
                row[cols[k]] = r.get(field)
        rows.append(row)
    return pd.DataFrame(rows)


def final_through_week(real: pd.DataFrame, sched: pd.DataFrame) -> int:
    """The largest week w such that every REG week 1..w is FINAL (`realized_week`'s one owner of
    what FINAL means). A partial week never counts — a Thursday game is not a played week."""
    from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW

    reg = sched[sched["game_type"] == "REG"]
    scheduled = reg.groupby(reg["week"].astype(int)).size().to_dict()
    rr = real[real["season_type"] == "REG"]
    realized = rr.groupby(rr["week"].astype(int))["game_id"].nunique().to_dict()
    states = RW.week_completeness_map(realized, scheduled)
    w = 0
    for wk in sorted(states):
        if states[wk] != "final":
            break
        w = wk
    return w


def stat_line(prior_row: dict, real_rows: list[dict], stat_keys, m_r: float | None, n: int,
              scale: float, avail: float, g_rem: float) -> dict[str, float]:
    """The ROS stat line: the SAME credibility weight on every stat (registration §4.1), so it
    scores to the ROS points under any linear preset. `m_r=None` is ∞ (the prior)."""
    out = {}
    for k in stat_keys:
        pf, rf = STAT_FIELD[k], R.REALIZED_STAT_FIELD[k]
        prior = scale * float(prior_row.get(pf) or 0.0)
        real_sum = float(sum(float(r.get(rf) or 0.0) for r in real_rows))
        rate = prior if m_r is None else (m_r * prior + real_sum) / (m_r + n)
        out[pf] = rate * avail * g_rem
    return out


def _m(v):
    return math.inf if v is None else float(v)


def build(params: dict, params_sha: str, served: dict, real: pd.DataFrame, sched: pd.DataFrame,
          *, season: int, stats_version: int, schedules_version: int,
          authority=None, now: datetime | None = None) -> dict | None:
    """Everything up to (not including) the write. Returns None when no REG week is FINAL yet."""
    now = now or datetime.now(timezone.utc)
    k = final_through_week(real, sched)
    if k == 0:
        return None
    certified_positions = list(params["certified_positions"])
    lo, hi = params["certified_weeks"]
    certified_week = lo <= k <= hi

    boards = served_board_frame(served, season)
    frame, diag = N.assemble((season,), stats_version=None, schedules_version=None, d=Path("."),
                             boards_override=boards, real_override=real, sched_override=sched,
                             allowed_keys=params["stat_keys"])
    applied = {p: diag["scoring_terms"][p]["applied"] for p in V.PRESETS}
    if applied != params["scoring_terms"]:
        raise RosPublishError(f"the served inputs resolve a different term set {applied} from the "
                              f"certified one {params['scoring_terms']} (registration §4)")
    rp = diag["_resolved_prior"]
    frame = frame[frame["k"] <= k].copy()
    frame["miss_streak"] = RI.miss_streak(frame)
    row = frame[frame["k"] == k].reset_index(drop=True)

    # ── identity audit at the certified positions (§8 / amendment 1) ──
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    linked = dict(zip(row["player_id"], row["rid"]))
    unresolved = set(boards["player_id"]) - set(row["player_id"])     # dropped by the join rules
    syn = boards[boards["position"].isin(certified_positions)
                 & ~boards["player_id"].map(lambda x: bool(B.GSIS_RE.fullmatch(x)))]
    realized_ids = set(real["player_id"])
    if len(syn):
        picks, rosters = authority() if authority else (None, None)
        if picks is None:
            raise RosPublishError("the identity audit needs the draft/roster authority")
        auth, _ = B.authority(syn.assign(
            draft_pick=[_pick(served, pid) for pid in syn["player_id"]]), picks, rosters)
        for pid in syn["player_id"]:
            rid = linked.get(pid)
            outcome = B.classify_join(rid if isinstance(rid, str) else None, auth[pid][0],
                                      realized_ids)
            if outcome == "WRONG":
                raise RosPublishError(f"identity join WRONG for {pid}: the rung found {rid}, the "
                                      f"authority says {auth[pid][0]} — STOP (PM amendment 1)")
            if outcome == "MISSED":
                unresolved.add(pid)

    # ── the certified numbers (computed only where they are served) ──
    m = {P: (params["m"][P]["m_r"], params["m"][P]["m_a"]) for P in V.POSITIONS}
    point, q = {}, {}
    X = RI.pi_features(row)
    posv = row["pos"].to_numpy()
    for p in V.PRESETS:
        pt = np.zeros(len(row))
        pi = np.zeros(len(row))
        for P in certified_positions:
            sel = posv == P
            if sel.any():
                pt[sel] = V.ros_point(row[sel], p, V.FormParams(_m(m[P][0]), _m(m[P][1])))
                pi[sel] = RI.predict_pi(pi_from_json(params["pi"][p][P]), X[sel])
        qq, _ = RI.apply_hurdle(table_from_json(params["ratio_tables"][p]), posv,
                                row["k"].to_numpy(), pt, pi)
        point[p], q[p] = pt, qq

    real_rows = real[(real["season_type"] == "REG") & (real["week"].astype(int) <= k)]
    real_flat = {}
    for rec in real_rows.to_dict("records"):
        real_flat.setdefault(rec["player_id"], []).append(R.flatten_realized_row(rec))
    served_by_id = {str(r["id"]): r for r in served["players"]}
    by_id = {pid: i for i, pid in enumerate(row["player_id"])}

    players = []
    for r in served["players"]:
        pid = str(r["id"])
        base = {"id": pid, "name": r["name"], "pos": r["pos"], "team": r.get("team"),
                "certified": False, "absence": None,
                "waiverValue": None, "waiverAbsence": C.WAIVER_ABSENCE}
        if r["pos"] not in V.POSITIONS:
            base["absence"] = "position_not_evaluated"
        elif r["pos"] not in certified_positions or not certified_week:
            base["absence"] = "not_certified"
        elif pid in unresolved or pid not in by_id:
            base["absence"] = "join_unresolved"
        else:
            i = by_id[pid]
            x = row.iloc[i]
            m_r, m_a = m[r["pos"]]
            avail = float(V.credibility_avail([x["a0"]], [x["n"]], [x["t"]], _m(m_a))[0])
            uncapped = float(x["board_full_ppr"]) / max(float(x["proj_games"]), 1.0)
            scale = float(x["r0_full_ppr"]) / uncapped if uncapped > 0 else 1.0
            prior_row = {f: (float(served_by_id[pid][f]) / max(float(x["proj_games"]), 1.0)
                             if served_by_id[pid].get(f) is not None else 0.0)
                         for f in (STAT_FIELD[k2] for k2 in params["stat_keys"])}
            rid = x["rid"] if isinstance(x["rid"], str) else None
            line = stat_line(prior_row, real_flat.get(rid, []), params["stat_keys"], m_r,
                             int(x["n"]), scale, avail, float(x["g_rem"]))
            base.update({
                "certified": True,
                "gamesPlayed": int(x["n"]), "teamGamesPlayed": int(x["t"]),
                "teamGamesRemaining": int(x["g_rem"]),
                "expGamesRemaining": avail * float(x["g_rem"]),
                "priorRate": float(x["r0_full_ppr"]),
                "realizedRate": (float(x["xsum_full_ppr"]) / int(x["n"])) if x["n"] > 0 else None,
                "rateWeight": float(V.rate_weight([x["n"]], _m(m_r))[0]),
                "availWeight": (0.0 if m_a is None else float(x["t"]) / (float(m_a) + float(x["t"]))),
                **line,
            })
            for p, suf in C.PRESET_SUFFIX.items():
                base[f"rosPts{suf}"] = float(point[p][i])
                base[f"rosP10{suf}"] = float(q[p][i, V.Q10_IDX])
                base[f"rosP90{suf}"] = float(q[p][i, V.Q90_IDX])
                got = LS.score_row(line, r["pos"], rp[p], STAT_FIELD)["pts"]
                if abs(got - point[p][i]) > COHERENCE_TOL * max(1.0, abs(point[p][i])):
                    raise RosPublishError(f"stat-line coherence failed for {pid} ({p}): the line "
                                          f"scores {got}, the value is {point[p][i]}")
        players.append(base)

    # in-season additions: realized players on no board row, scored by OUR scorer (assemble's)
    scored = diag["_real"]
    ev = scored[(scored["season_type"] == "REG") & (scored["week"].astype(int) <= k)]
    linked_rids = {v for v in row["rid"] if isinstance(v, str)}
    off = ev[~ev["player_id"].isin(linked_rids)]
    tot = float(ev["pts_full_ppr"].sum())

    payload = C.NflRosPayload.model_validate(
        {"season": season, "throughWeek": k, "generated_at": now.isoformat(timespec="seconds"),
         "players": players}).model_dump()
    players_bytes = json.dumps(payload).encode()
    counts = {a: sum(1 for x in players if x["absence"] == a) for a in C.ROS_ABSENCES}
    counts["no_preseason_prior"] = int(off["player_id"].nunique())
    manifest = C.NflRosManifest.model_validate({
        "season": season, "throughWeek": k, "generated_at": now.isoformat(timespec="seconds"),
        "certified_positions": certified_positions,
        "certified_weeks": [lo, hi], "certified_for_this_week": certified_week,
        "params": [{"pos": P, "m_rate": m[P][0], "m_avail": m[P][1]} for P in V.POSITIONS],
        "certification": params["certification"],
        "decisive_commit": params["decisive_commit"], "params_sha256": params_sha,
        "prior_generated_at": served.get("generated_at"),
        "prior_model_version": served.get("model_version"),
        "stats_player_week_version": stats_version, "schedules_version": schedules_version,
        "scoring_terms": params["scoring_terms"],
        "n_players": len(players),
        "absence_counts": [{"reason": a, "n": n} for a, n in counts.items()],
        "no_preseason_prior_players": counts["no_preseason_prior"],
        "no_preseason_prior_realized_share": (float(off["pts_full_ppr"].sum()) / tot
                                              if tot > 0 else None),
        "join_unresolved_names": sorted(x["name"] for x in players
                                        if x["absence"] == "join_unresolved"),
        "rookie_stratum_note": None,
        "players_sha256": hashlib.sha256(players_bytes).hexdigest(),
    }).model_dump()
    current = C.NflRosCurrent.model_validate({
        "season": season, "throughWeek": k, "generated_at": manifest["generated_at"],
        "manifest_key": C.ros_manifest_key(season, k),
        "players_key": C.ros_players_key(season, k)}).model_dump()
    return {"season": season, "week": k, "manifest": manifest, "payload": payload,
            "current": current, "players_bytes": players_bytes}


def _pick(served: dict, pid: str):
    for r in served["players"]:
        if str(r["id"]) == pid:
            return r.get("draftPick")
    return None


# ── the write-gate, staging and publish (the NF-INC-0917B pattern) ────────────────────────────────
def assert_contract_shaped(built: dict) -> None:
    """REFUSE to write a blob short of its contract — on every path, dry-run included."""
    problems = []
    for name, model in (("manifest", C.NflRosManifest), ("payload", C.NflRosPayload),
                        ("current", C.NflRosCurrent)):
        missing = C.missing_declared_fields(built.get(name), model, where=name)
        if missing:
            problems.append(f"{name}: {missing[:12]}")
    if json.dumps(built["payload"]).encode() != built["players_bytes"]:
        problems.append("players bytes differ from the validated payload")
    if hashlib.sha256(built["players_bytes"]).hexdigest() != built["manifest"]["players_sha256"]:
        problems.append("manifest.players_sha256 does not match the players bytes")
    if problems:
        raise RosPublishError("REFUSING to write: " + "; ".join(problems))


def blobs(built: dict) -> dict[str, bytes]:
    s, w = built["season"], built["week"]
    return {C.ros_manifest_key(s, w): json.dumps(built["manifest"]).encode(),
            C.ros_players_key(s, w): built["players_bytes"],
            C.ros_current_key(s): json.dumps(built["current"]).encode()}


def stage(built: dict, out_dir: Path) -> list[Path]:
    assert_contract_shaped(built)
    written = []
    for rel, body in blobs(built).items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        written.append(p)
    return written


def publish(built: dict, bucket: str | None, *, do_publish: bool, s3=None) -> dict[str, str]:
    """Upload, then READ BACK and compare sha256 (the served-bytes assertion)."""
    assert_contract_shaped(built)            # before the dry-run return (NF-INJ3B reading)
    payloads = blobs(built)
    if not do_publish:
        log.info("[DRY-RUN] would upload %d object(s) under fantasy/nfl/ros/ — pass --publish",
                 len(payloads))
        return {}
    if not bucket:
        raise RosPublishError("--publish needs a bucket (a publish that uploads nothing must fail)")
    if s3 is None:
        import boto3
        s3 = boto3.client("s3", region_name="us-east-1")    # key-less: instance-role safe
    served = {}
    for rel, body in payloads.items():
        key = f"fantasy/nfl/{rel}"
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
        back = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        want, got = hashlib.sha256(body).hexdigest(), hashlib.sha256(back).hexdigest()
        if want != got:
            raise RosPublishError(f"served bytes differ for {key}: wrote {want}, read {got}")
        served[key] = got
    log.info("published %d ROS object(s) for %s through week %s", len(served), built["season"],
             built["week"])
    return served


# ── IO for the build ──────────────────────────────────────────────────────────────────────────────
def load_served_board(season: int, bucket: str) -> dict:
    import boto3
    return json.loads(boto3.client("s3", region_name="us-east-1").get_object(
        Bucket=bucket, Key=SERVED_BOARD_KEY.format(season=season))["Body"].read())


def lake_reads(season: int):
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW
    from quant_sports_intel_models.football.nfl.ingest import s3io

    def table(src):
        return DeltaTable(s3io.table_uri("nfl", src), storage_options=s3io.storage_options())

    st, sc = table("stats_player_week"), table("schedules")
    parts = [("season", "in", [str(season)])]
    cols = sorted(set(RW.required_columns()) | {"game_id"})
    real = st.to_pandas(partitions=parts, columns=cols)
    real = real[real["season_type"] == "REG"].reset_index(drop=True)
    sched = sc.to_pandas(partitions=parts,
                         columns=["season", "week", "game_type", "home_team", "away_team"])
    sched = sched[sched["game_type"] == "REG"].reset_index(drop=True)
    return real, sched, int(st.version()), int(sc.version())


def authority_reads(season: int):
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io
    parts = [("season", "in", [str(season)])]

    def read(src, cols):
        return DeltaTable(s3io.table_uri("nfl", src), storage_options=s3io.storage_options()
                          ).to_pandas(partitions=parts, columns=cols)
    return (read("nflverse_draft_picks", ["season", "pick", "gsis_id", "pfr_player_name", "position"]),
            read("rosters", ["season", "week", "full_name", "position", "gsis_id"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit-params", action="store_true")
    ap.add_argument("--season", type=int, default=SERVING_SEASON)
    ap.add_argument("--s3-bucket", default=None)
    ap.add_argument("--board-bucket", default="credence-prod-s3-api-cache",
                    help="where the PUBLISHED season board is read from")
    ap.add_argument("--publish", action="store_true", help="upload to the LIVE prod api-cache")
    ap.add_argument("--out", default=str(STAGING))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.fit_params:
        d = N.artifacts_dir()
        N.verify_prior_hashes(d)
        # assembled directly (not from the frame cache): the stat-key set is a private diagnostic
        # the cache strips. Same code and pins, so the frame must be the decisive run's frame.
        frame, diag = N.assemble(V.PRIOR_SEASONS, stats_version=N.STATS_VERSION,
                                 schedules_version=N.SCHEDULES_VERSION, d=d)
        record = json.loads(DECISIVE_RECORD.read_text())
        if len(frame) != record["meta"]["rows"]:
            raise RosPublishError(f"the assembled frame has {len(frame)} rows, the decisive run "
                                  f"had {record['meta']['rows']} — not the certified frame")
        frame = frame.copy()
        frame["miss_streak"] = RI.miss_streak(frame)
        out = fit_serving_params(frame, diag, record)
        PARAMS_DIR.mkdir(parents=True, exist_ok=True)
        params_path(args.season).write_text(json.dumps(out, sort_keys=True))
        log.info("wrote %s (certified: %s)", params_path(args.season), out["certified_positions"])
        return 0

    params, sha = load_params(args.season)
    served = load_served_board(args.season, args.board_bucket)
    real, sched, sv, scv = lake_reads(args.season)
    built = build(params, sha, served, real, sched, season=args.season, stats_version=sv,
                  schedules_version=scv, authority=lambda: authority_reads(args.season))
    if built is None:
        log.warning("[METRIC] nfl_ros_publish=no_final_week — no REG week of %s is FINAL yet; "
                    "nothing to update, nothing written", args.season)
        return EXIT_NO_FINAL_WEEK
    paths = stage(built, Path(args.out))
    log.info("[METRIC] nfl_ros_through_week=%s players=%s certified_rows=%s", built["week"],
             built["manifest"]["n_players"],
             sum(1 for p in built["payload"]["players"] if p["certified"]))
    log.info("staged %s", [str(p) for p in paths])
    publish(built, args.s3_bucket, do_publish=args.publish)
    return 0


if __name__ == "__main__":
    sys.exit(main())
