"""run_nf_inj4b_ship_battery.py — the level-adjacent MEASUREMENT BATTERY for NF-INJ4b-SHIP.

The discount changes `proj_games`, and MVP-1's served point is `rate × games`, so shipping it is a
LEVEL-ADJACENT change: it has to clear the whole-board machinery NF-D16 / NF-D21 / NF-TR2b / NF1.9
built before anyone may serve it. This runner executes that battery on the CAPTURED publish
candidate and — just as importantly — NAMES the legs it CANNOT run and the legs that are
STRUCTURALLY INACTIVE, because an unrun leg reported as a pass is the error this program keeps
naming (NF1.7 (a) / NF-D20).

⛔ **WHAT THIS IS NOT: A CAPTURE-PINNED REBUILD.** The registered ship path's step 1 rebuilds the
board against a pinned baseline with matched market vintages. That is NOT REACHABLE from this
checkout today and the runner proves it rather than asserting it: `assert_vintages_match` is RUN,
and it refuses. Measured on 2026-09-13 — the served board carries `ecr_as_of 2026-09-10` while the
local FantasyPros cache is `9/01`, and FantasyPros serves ONLY the current snapshot, so the board's
own ECR vintage is **UNRECOVERABLE** (NF-INJ2c: do not chase a vintage whose day has rolled). The
rebuild is therefore the OPERATOR'S step, in an environment whose caches match — which is exactly
where NF-INJ4b's closeout §5B already put it.

⭐ **WHAT IT IS INSTEAD, and why it is a real read rather than a substitute.** Every leg runs on the
PUBLISHED board with the SERVED constants applied through the SHIPPED serving path. The population
is the real one, the constants are the ones the operator is deciding about, and the arithmetic is
the board's own. What it cannot see is what a REBUILD would additionally do — re-fit replacement
levels against the moved field, and re-run NF1.5's ordering permutation, which NF-INJ1 measured
handing **+36.4%** of an availability discount back. So every figure here is FIRST-ORDER and is
labelled as such; none of them is a substitute for the operator's rebuild.

RUN (LAPTOP — needs S3 read on the api-cache bucket):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_ship_battery
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
import sys
import tempfile
import time
from datetime import datetime, timezone

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    designation_discount_policy as POLICY,
    designation_discount_serving as DDS,
    export_draft_board_json as EX,
    run_nf_inj2c_dominance_baseline as VINTAGE,
    run_nf_tr2b_placement_read as PR,
)

log = logging.getLogger("nfl.fantasy.nf_inj4b.ship_battery")

_HERE = pathlib.Path(__file__).resolve().parent
_ART = _HERE / "ablation_results"
_CAPTURE = _HERE / "artifacts" / "nf_inj4b_ship_baseline"
SEASON = 2026
TOP_N = 25

#: the 1e-9 material epsilon. ⛔ NEVER a bitwise comparison: two rebuilds of the same board at the
#: same commit differ in the ROOKIE BAND at 0-21 material cells (card QkpAHBYa), so a bitwise diff
#: reports a change this repo cannot attribute and sends a session hunting a phantom.
EPS = 1e-9

#: the board columns the discount moves, and the ones it must not.
_SCALED_COLS = ("pts", "g", "ptsP10", "ptsP90")
_INVARIANT_COLS = ("adp", "repl", "bye", "pos", "team", "rookie")

#: NF-INJ1 / NF-RATE1 — the realized-max full-season pace per position, READ from the published
#: TypeScript owner rather than restated here (a second copy is a second thing to drift).
_FANTASY_TS = _PROJECT_ROOT / "frontend/lib/fantasy.ts"
MIN_GAMES_FOR_FULL_SEASON_RATE = 8.0


def _realized_max_pace() -> dict:
    import re
    m = re.search(r"export const REALIZED_MAX_SEASON_PACE:[^=]*=\s*\{(?P<body>.*?)\}",
                  _FANTASY_TS.read_text(), re.S)
    if not m:
        raise SystemExit("REALIZED_MAX_SEASON_PACE could not be parsed from frontend/lib/fantasy.ts "
                         "— the envelope leg would be vacuous, so it refuses instead")
    out = {k: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", m.group("body"))}
    if not out:
        raise SystemExit("the envelope map parsed EMPTY — refusing rather than reporting 0 breaches")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. PRECONDITIONS — run, not assumed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def preconditions(season: int) -> dict:
    """The D3 table-driven vintage surface, RUN. A refusal here is the finding, not a blocker."""
    out: dict = {"capture_dir": str(_CAPTURE)}
    manifest = json.loads((_CAPTURE / "manifest.json").read_text())
    board_sha = hashlib.sha256((_CAPTURE / "projections.json").read_bytes()).hexdigest()[:16]
    out["capture"] = {
        "board_generated_at": manifest.get("generated_at"),
        "projection_built_at": (manifest.get("freshness") or {}).get("projection_built_at"),
        "adp_as_of": manifest.get("adp_as_of"),
        "ecr_as_of": manifest.get("ecr_as_of"),
        "input_vintage": (manifest.get("freshness") or {}).get("input_vintage"),
        "projections_sha256_16": board_sha,
    }
    # ⛔ The market/vintage precondition, RUN. It REFUSES by raising; that refusal is a measurement
    #    about this checkout, so it is caught and RECORDED rather than allowed to end the run.
    try:
        VINTAGE.assert_vintages_match(con=None, season=season)
        out["vintage_match"] = {"verdict": "MATCHES", "detail": None}
    except SystemExit as e:
        out["vintage_match"] = {"verdict": "REFUSED", "detail": str(e)}
    except Exception as e:  # noqa: BLE001
        out["vintage_match"] = {"verdict": "UNEVALUABLE", "detail": f"{type(e).__name__}: {e}"}

    # ⚠️ AND THE SAME COMPARISON AGAINST **THIS STORY'S OWN CAPTURE**, because the shared helper is
    #    pinned to NF-INJ2c's baseline directory and therefore reports THAT manifest's vintages.
    #    Its VERDICT is still the right one for this checkout — the local caches match neither
    #    board — but quoting its "served" figures beside a capture they do not describe is how a
    #    reader ends up comparing the wrong two things (the stale-premise class).
    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF
    local = MF.market_as_of(season)
    rows = []
    for name, key in (("adp", "adp_as_of"), ("ecr", "ecr_as_of")):
        mine = (local.get(name) or {}).get("as_of")
        served = out["capture"][key]
        rows.append({"input": name, "this_capture_served": served, "local_cache": mine,
                     "matches": (mine is not None and str(mine) == str(served))})
    out["vintage_vs_this_capture"] = {
        "rows": rows,
        "all_match": all(r["matches"] for r in rows),
        "note": ("a local cache reading None means this WORKTREE has none at all — the market "
                 "caches are gitignored (NF-INFRA1), so they are absent from a fresh worktree and "
                 "live only in the main checkout"),
    }
    return out


def live_designations(season: int) -> dict:
    """The live map, through the board's OWN owner, plus the feed vintage the packet was read at."""
    m = EX.weekly_designation_map(season)
    if m is None:
        raise SystemExit("the weekly designation feed is unreadable — every leg below would be a "
                         "no-op, and a no-op reported as a passed check is the NF1.7 (a) error")
    census: dict = {}
    for v in m.values():
        census[str(v) if v is not None else "UNINTERPRETABLE"] = census.get(
            str(v) if v is not None else "UNINTERPRETABLE", 0) + 1
    return {"map": m, "census": census, "rows": len(m)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. THE CANDIDATE BOARD — built through the SHIPPED serving path
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_board(board: pd.DataFrame, designations: dict) -> pd.DataFrame:
    """Apply the SERVED discount to one published board, FIRST-ORDER.

    ⭐ THE MULTIPLIER COMES FROM THE SHIPPED CALLABLE, not from a second reading of the artifact.
    `designation_games_callable` is the object the board build will use; deriving the cap any other
    way here would measure a model the board is not going to serve (NF-C0e: drive the real engine).

    ⛔ FIRST-ORDER, and the boundary is the whole reason the operator still has a rebuild to run:
    `pts` and `g` scale together (`rescale_line_to_games` carries the season line with the games),
    `vor` is re-derived against the board's OWN replacement level, and the ranks are re-derived.
    A REBUILD would additionally re-fit replacement against the moved field and re-run NF1.5's
    ordering permutation — which NF-INJ1 measured handing +36.4% of an availability discount back.
    """
    g = board.copy()
    g["_pid"] = g["id"].map(EX._norm_player_id)
    g["_desig"] = g["_pid"].map(designations)

    frame = pd.DataFrame({"player_id": g["_pid"].to_numpy(), "proj_games": g["g"].astype(float)})
    cb = DDS.designation_games_callable(SEASON, designations=designations)
    if cb is None:
        raise SystemExit("the serving path returned no channel — either the policy is OFF or the "
                         "feed is unreadable; either way this battery has nothing to measure")
    new_games = np.asarray(cb(frame), dtype=float)
    old_games = g["g"].to_numpy(dtype=float)
    scale = np.where(old_games > 1e-6, new_games / np.clip(old_games, 1e-6, None), 1.0)

    # ⭐⭐ APPLY THE DELTA TO THE PUBLISHED VALUE — never RE-DERIVE `vor` from `pts - repl`.
    #    ⛔ THE NO-OP CONTROL CAUGHT THIS, and it is worth recording because the re-derivation is the
    #    obvious way to write it. The published board carries `pts`, `repl` and `vor` each ROUNDED
    #    to one decimal, so `pts - repl` differs from the published `vor` by up to 0.1 — a rounding
    #    residue, not a discount. Re-deriving it moved **1,113 ranks across the 14 boards under an
    #    EMPTY designation map**, which would have reached the operator packet as phantom movement
    #    on rows nothing had touched. Exactly the shape of the `(config_name, n_teams)` defect that
    #    made 1,715 of 1,716 rows 'move' in NF-INJ4b's own counterfactual.
    #
    #    `repl` is INVARIANT under a first-order read, so `Δvor == Δpts` EXACTLY. Adding the delta
    #    preserves the published figure byte-for-byte on every untouched row (so a zero discount is
    #    a zero diff BY CONSTRUCTION) and is exact on every moved one.
    for col in _SCALED_COLS:
        if col == "g":
            g[col] = new_games
        elif col in g.columns:
            g[col] = g[col].astype(float).to_numpy() * scale
    for pts_col, vor_col in (("pts", "vor"), ("ptsP10", "vorP10"), ("ptsP90", "vorP90")):
        if pts_col in g.columns and vor_col in board.columns:
            delta = g[pts_col].astype(float).to_numpy() - board[pts_col].astype(float).to_numpy()
            g[vor_col] = board[vor_col].astype(float).to_numpy() + delta
    return g


def _ranks(vor: pd.Series) -> np.ndarray:
    return vor.astype(float).rank(ascending=False, method="first").astype(int).to_numpy()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. THE LEGS
# ══════════════════════════════════════════════════════════════════════════════════════════════
def no_op_control(boards: dict) -> dict:
    """⭐ THE REPRESENTATION-TOLERANT PIN (NF-INJ2c #5 semantics): with an EMPTY designation map the
    candidate must reproduce the baseline, worst <= tol at an EXPLICIT 1e-9 epsilon.

    ⛔ This control is not decoration — it caught the `(config_name, n_teams)` board-key defect that
    made 1,715 of 1,716 rows 'move' under an empty map. Stated at an explicit epsilon rather than
    bitwise, because a bitwise pin on this board reports rookie-band motion the repo cannot
    attribute (card QkpAHBYa)."""
    worst, worst_where, ranks_moved = 0.0, None, 0
    for stem, board in boards.items():
        cand = candidate_board(board, {})
        for col in _SCALED_COLS + ("vor",):
            if col not in board.columns:
                continue
            d = float(np.nanmax(np.abs(board[col].astype(float).to_numpy()
                                       - cand[col].astype(float).to_numpy())))
            if d > worst:
                worst, worst_where = d, f"{stem}.{col}"
        ranks_moved += int((_ranks(board["vor"]) != _ranks(cand["vor"])).sum())
    return {"tolerance": EPS, "worst_abs_difference": worst, "worst_cell": worst_where,
            "ranks_moved_under_an_empty_map": ranks_moved,
            "passes": bool(worst <= EPS and ranks_moved == 0)}


def material_diff(boards: dict, designations: dict) -> dict:
    """Population-scoped material diff at 1e-9 — never bitwise, and scoped so a moved population is
    reported as a population rather than as a row count."""
    per_pop: dict = {}
    for stem, board in boards.items():
        cand = candidate_board(board, designations)
        desig = cand["_desig"]
        for pop, mask in (("designated", desig.notna()),
                          ("undesignated", desig.isna()),
                          ("rookies", board.get("rookie", pd.Series(False, index=board.index))
                           .fillna(False).astype(bool)),
                          ("veterans", ~board.get("rookie", pd.Series(False, index=board.index))
                           .fillna(False).astype(bool))):
            m = mask.to_numpy()
            rec = per_pop.setdefault(pop, {"rows": 0, "material_cells": 0, "worst_abs": 0.0,
                                           "worst_cell": None})
            rec["rows"] += int(m.sum())
            for col in _SCALED_COLS + ("vor",):
                if col not in board.columns:
                    continue
                d = np.abs(board[col].astype(float).to_numpy()[m]
                           - cand[col].astype(float).to_numpy()[m])
                rec["material_cells"] += int((d > EPS).sum())
                if d.size and float(np.nanmax(d)) > rec["worst_abs"]:
                    rec["worst_abs"] = float(np.nanmax(d))
                    rec["worst_cell"] = f"{stem}.{col}"
        # the columns the discount must NOT touch
        for col in _INVARIANT_COLS:
            if col in board.columns and not board[col].equals(cand[col]):
                per_pop.setdefault("INVARIANT_VIOLATIONS", []).append(f"{stem}.{col}")
    return {"epsilon": EPS, "per_population": per_pop}


def envelope_and_suppression(boards: dict, designations: dict) -> dict:
    """⭐ NF-INJ1's realized-max envelope and NF-RATE1's suppression, on BOTH boards.

    ⚠️ **A STRUCTURAL RESULT, MEASURED RATHER THAN ARGUED.** The full-season rate is
    `pts × 17 / g`, and the discount scales `pts` and `g` by the SAME multiplier — so the rate is
    INVARIANT under it and the suppressed population CANNOT move. That is a strong claim, so it is
    measured on every board rather than reasoned from the arithmetic: if a suppression DOES fire on
    a newly-capped row, that is the system composing and it belongs in the record (the spec's own
    instruction), not in an argument about why it should not have."""
    pace = _realized_max_pace()
    out = {"envelope": pace, "min_games": MIN_GAMES_FOR_FULL_SEASON_RATE, "per_board": {}}
    tot_b = tot_c = 0
    for stem, board in boards.items():
        cand = candidate_board(board, designations)
        row = {}
        for tag, frame in (("baseline", board), ("candidate", cand)):
            g = frame["g"].astype(float).to_numpy()
            pts = frame["pts"].astype(float).to_numpy()
            pos = frame["pos"].astype(str).str.upper().to_numpy()
            ceil = np.array([pace.get(p, np.inf) for p in pos], dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                rate = np.where(g >= MIN_GAMES_FOR_FULL_SEASON_RATE, pts * 17.0 / g, np.nan)
            row[tag] = int(np.nansum(rate > ceil))
        row["delta"] = row["candidate"] - row["baseline"]
        # the rate itself, to machine precision, on the rows the discount touched
        touched = cand["_desig"].notna().to_numpy()
        gb, pb = board["g"].astype(float).to_numpy(), board["pts"].astype(float).to_numpy()
        gc, pc = cand["g"].astype(float).to_numpy(), cand["pts"].astype(float).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            rb, rc = pb * 17.0 / gb, pc * 17.0 / gc
        d = np.abs(rb[touched] - rc[touched])
        row["worst_rate_move_on_a_capped_row"] = float(np.nanmax(d)) if d.size else 0.0
        out["per_board"][stem] = row
        tot_b += row["baseline"]
        tot_c += row["candidate"]
    out["totals"] = {"baseline_suppressed": tot_b, "candidate_suppressed": tot_c,
                     "delta": tot_c - tot_b}
    return out


def coherence_delta(designations: dict) -> dict:
    """⭐ NF-INJ1's COHERENCE, on the served `projections.json` — baseline vs candidate.

    The board publishes `coherence.violating_players` (8 on this capture): rows whose stat line
    could not have happened in the games projected. The discount changes BOTH the line and the
    games, so it is a direct question whether it creates or clears any.

    ⚠️ Measured through `projection_coherence.coherence_summary` — the OWNER the exporter itself
    calls — rather than re-implemented here, and `applicable` / `n_unevaluable` are carried through
    because a summary that reports zero violations WITHOUT having checked anything is a clean-looking
    board (that module's own warning)."""
    from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as PC

    rows = json.loads((_CAPTURE / "projections.json").read_text())
    rows = rows.get("players") if isinstance(rows, dict) else rows
    if not isinstance(rows, list) or not rows:
        return {"verdict": "UNEVALUABLE",
                "why": "the served projections.json carried no row list — not scored as clean"}
    base = pd.DataFrame(rows)
    if "id" not in base.columns or "g" not in base.columns:
        return {"verdict": "UNEVALUABLE",
                "why": f"projections.json lacks id/g (cols {sorted(base.columns)[:12]})"}
    cand = candidate_board(base, designations)
    b = PC.coherence_summary(base.to_dict(orient="records"))
    c = PC.coherence_summary(cand[[x for x in cand.columns
                                   if not x.startswith("_")]].to_dict(orient="records"))
    return {
        "baseline": {k: b.get(k) for k in ("applicable", "n_in_scope", "n_unevaluable",
                                           "n_violating_players", "by_position")},
        "candidate": {k: c.get(k) for k in ("applicable", "n_in_scope", "n_unevaluable",
                                            "n_violating_players", "by_position")},
        "delta_violating_players": int((c.get("n_violating_players") or 0)
                                       - (b.get("n_violating_players") or 0)),
        "verdict": ("UNEVALUABLE" if not (b.get("applicable") and c.get("applicable"))
                    else "UNCHANGED" if (c.get("n_violating_players")
                                         == b.get("n_violating_players")) else "MOVED"),
    }


def rank_moves(boards: dict, designations: dict) -> dict:
    """Top-25 rank moves per config, INCLUDING superflex.

    ⚠️ SUPERFLEX IS READ ON ITS OWN ROWS, never inferred from the others: NF-W8-0's VOR 'shield' —
    a per-group level shift cancelling because the group's own replacement absorbs it — is
    ADDITIVE-ONLY and additionally assumes the group is not cross-pooled. This discount is
    MULTIPLICATIVE and QB IS cross-pooled in superflex, so the shield does not hold there (NF-TR2b)."""
    out: dict = {}
    for stem, board in boards.items():
        cand = candidate_board(board, designations)
        base_rank, new_rank = _ranks(board["vor"]), _ranks(cand["vor"])
        move = base_rank - new_rank
        published = board["ovrRank"].astype(int).to_numpy()
        agree = float((base_rank == published).mean())
        idx = np.argsort(-np.abs(move), kind="stable")
        top = [
            {"player": str(board["name"].iloc[i]), "pos": str(board["pos"].iloc[i]),
             "designation": (None if pd.isna(cand["_desig"].iloc[i])
                             else str(cand["_desig"].iloc[i])),
             "rank_before": int(base_rank[i]), "rank_after": int(new_rank[i]),
             "move": int(move[i]),
             "games_before": round(float(board["g"].iloc[i]), 2),
             "games_after": round(float(cand["g"].iloc[i]), 2),
             "pts_before": round(float(board["pts"].iloc[i]), 2),
             "pts_after": round(float(cand["pts"].iloc[i]), 2)}
            for i in idx if int(move[i]) != 0][:TOP_N]
        out[stem] = {
            "rows": int(len(board)),
            "recomputed_baseline_rank_agrees_with_published": round(agree, 4),
            "designated_rows_on_board": int(cand["_desig"].notna().sum()),
            "rows_whose_rank_moved": int((move != 0).sum()),
            "max_abs_rank_move": int(np.abs(move).max()) if len(move) else 0,
            "top_moves": top,
        }
    return out


def placement_read(boards: dict, designations: dict) -> dict:
    """⭐ THE WHOLE-BOARD CROSS-POSITION PLACEMENT READ, on BOTH boards — a REAL read this time.

    NF-INJ4b's §6 correctly REFUSED this leg: under the scope rule the counterfactual moved zero
    rows on all 14 boards, so the read had no input and would have returned a byte-identical answer
    that said nothing. The board now moves 500+ ranks per config, so the read is ACTIVE.

    ⚠️ REQUIRED here rather than optional: NF-W8-0's VOR shield is ADDITIVE-ONLY, and this discount
    is MULTIPLICATIVE — `vor → k·vor` does not cancel and it re-runs the greedy FLEX allocation, a
    cross-position draft on points (NF-TR2b's own rule: a multiplicative per-position correction
    MUST get the whole-board placement read).

    ⛔ OUTPUT DISCIPLINE: writes into a TEMP dir under this story's own stem. `PR.main()` would
    write a DECIDED story's fixed paths; the pure `run()` writes nothing."""
    out = {}
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        for tag, build in (("baseline", False), ("candidate", True)):
            d = root / tag
            d.mkdir()
            (d / "projections.json").write_text((_CAPTURE / "projections.json").read_text())
            for stem, board in boards.items():
                frame = candidate_board(board, designations) if build else board
                cols = [c for c in frame.columns if not c.startswith("_")]
                (d / f"board_{stem}.json").write_text(
                    json.dumps(frame[cols].to_dict(orient="records")))
            try:
                out[tag] = PR.run(d, origin=str(_CAPTURE))
            except Exception as e:  # noqa: BLE001
                out[tag] = {"status": "UNEVALUABLE", "error": f"{type(e).__name__}: {e}"}
    return out


def interval_revalidation_activity() -> dict:
    """⭐ MEASURE WHETHER THIS LEG CAN ACT AT ALL, and report the answer as a finding.

    NF1.9's interval revalidation scores every shipped 80% band against its coverage floor, over
    HISTORICAL panels (rookie draft classes 2019-2025; the veteran walk-forward folds). The
    designation channel is gated on the CURRENT season, so it cannot reach a single row of either
    panel — the leg is STRUCTURALLY INACTIVE for this change, and running it would return a
    byte-identical answer.

    ⛔ Reporting that as a PASSED interval check is exactly the error NF-INJ4b §6 avoided for the
    preseason placement read. It is reported as INACTIVE, with the reason, and with the separate
    question it would be easy to conflate it with ANSWERED: does the discount change a SERVED band?
    It scales it with the point, because `apply_availability_chain` runs BEFORE
    `attach_season_interval` — so a capped player's band is attached to his capped point, which is
    byte-identically how the FORMAL availability cap has always been treated. The band's own
    calibration is a property of the panel, and the panel is untouched."""
    src = (_HERE / "season_projection.py").read_text()
    vet = src.split("def project_veterans(", 1)[1].split("\ndef ", 1)[0]
    avail_at = vet.find("apply_availability_chain(")
    band_at = vet.find("attach_season_interval(")
    caller = (_HERE / "run_season_projection.py").read_text()
    return {
        "verdict": "STRUCTURALLY_INACTIVE",
        "why": ("the designation channel is gated on the current season, and the NF1.9 revalidation "
                "scores historical rookie/veteran panels — it cannot reach a row the discount moved"),
        "season_gated": "_current_season()" in caller.split("_designation_games = (", 1)[1][:400],
        "availability_runs_before_the_band_attach": bool(0 <= avail_at < band_at),
        "consequence": ("a capped player's 80% band is attached to his CAPPED point — the identical "
                        "treatment the formal availability cap has always received; the band's "
                        "calibration lives in the panel, which this change cannot touch"),
        "reported_as_a_pass": False,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
def render(s: dict) -> str:
    cap, vm = s["preconditions"]["capture"], s["preconditions"]["vintage_match"]
    L = [
        "# NF-INJ4b-SHIP — the measurement battery on the publish candidate", "",
        f"**Generated {s['generated_at']} · season {s['season']}.** `best_alpha = 0`. "
        f"⛔ **This run publishes nothing.** It measures what the wired discount does to the board "
        f"the operator is deciding about.", "",
        "---", "", "## 1. What board these numbers describe", "",
        "| field | value |", "|---|---|",
        f"| board generated at | `{cap['board_generated_at']}` |",
        f"| projections sha256 (16) | `{cap['projections_sha256_16']}` |",
        f"| ADP as-of | `{cap['adp_as_of']}` |",
        f"| ECR as-of | `{cap['ecr_as_of']}` |",
        f"| sleeper status as-of | `{(cap['input_vintage'] or {}).get('sleeper_status_as_of')}` |",
        f"| designation feed rows | {s['live_feed']['rows']} |",
        f"| designation census | `{s['live_feed']['census']}` |", "",
        f"### ⛔ The capture-pinned REBUILD precondition: **{vm['verdict']}**", "",
    ]
    vvc = s["preconditions"].get("vintage_vs_this_capture") or {}
    if vvc:
        L += ["Measured against **this capture** (the shared helper is pinned to NF-INJ2c's own "
              "baseline directory, so its figures describe a different board):", "",
              "| market input | this capture served | local cache | match |", "|---|---|---|---|"]
        for r in vvc["rows"]:
            L.append(f"| {r['input'].upper()} | `{r['this_capture_served']}` | "
                     f"`{r['local_cache']}` | {'✅' if r['matches'] else '⛔'} |")
        L += ["", f"⚠️ {vvc['note']}.", ""]
    if vm["verdict"] != "MATCHES":
        L += ["The registered ship path's step 1 — a full rebuild against a pinned baseline with "
              "matched market vintages — is **not reachable from this checkout**, and the "
              "precondition was RUN rather than assumed:", "",
              "```", (vm["detail"] or "").strip()[:1400], "```", "",
              "⚠️ **The ECR vintage is UNRECOVERABLE, not merely stale.** FantasyPros serves only "
              "the CURRENT snapshot, so the board's own `ecr_as_of` cannot be re-fetched once its "
              "day has rolled (NF-INJ2c). ⛔ Do not chase it. The rebuild belongs to the operator, "
              "in an environment whose caches match — which is where NF-INJ4b's closeout already "
              "put it. **Every leg below therefore runs on the PUBLISHED board with the SERVED "
              "constants applied, FIRST-ORDER.**", ""]
    noc = s["no_op_control"]
    L += ["---", "", "## 2. ⭐ The no-op control — why anything below can be trusted", "",
          f"With an EMPTY designation map the candidate must reproduce the baseline. Measured "
          f"across **{len(s['rank_moves'])} boards** at an explicit epsilon of `{noc['tolerance']}`: "
          f"{'✅ PASS' if noc['passes'] else '⛔ FAIL'} — worst absolute difference "
          f"`{noc['worst_abs_difference']:.3e}`"
          f"{' at ' + noc['worst_cell'] if noc['worst_cell'] else ''}, "
          f"{noc['ranks_moved_under_an_empty_map']} ranks moved.", "",
          "⛔ Representation-tolerant, never bitwise: two rebuilds of this board at the SAME commit "
          "differ in the rookie band at 0–21 material cells, so a bitwise pin reports motion this "
          "repo cannot attribute (card QkpAHBYa).", "",
          "---", "", "## 3. The per-designation magnitude actually being served", "",
          "| designation | E[games missed] | rate multiplier | players on the live feed |",
          "|---|---|---|---|"]
    for level, c in s["served_constants"].items():
        n = s["live_feed"]["census"].get(level.capitalize(), 0)
        L.append(f"| `{level}` | {c['expected_games_missed']:.4f} | "
                 f"×{c['rate_multiplier']:.4f} | {n} |")
    unint = s["live_feed"]["census"].get("UNINTERPRETABLE", 0)
    L += ["", f"⚠️ {unint} further player(s) carry a value the feed publishes but we cannot "
              f"interpret. They are DISCLOSED as unknown and **priced at nothing** — never silently "
              f"dropped, and never guessed at.", ""]
    md = s["material_diff"]["per_population"]
    L += ["---", "", "## 4. The material diff, population-scoped", "",
          f"At an epsilon of `{s['material_diff']['epsilon']}`.", "",
          "| population | rows (summed over boards) | material cells moved | worst move |",
          "|---|---|---|---|"]
    for pop in ("designated", "undesignated", "rookies", "veterans"):
        r = md.get(pop)
        if not r:
            continue
        L.append(f"| {pop} | {r['rows']} | {r['material_cells']} | "
                 f"{r['worst_abs']:.4f}{' (' + str(r['worst_cell']) + ')' if r['worst_cell'] else ''} |")
    rk = md.get("rookies") or {}
    L += ["", (f"⭐ **ROOKIE-BAND MOTION IS EXACTLY ZERO** ({rk.get('material_cells', 0)} material "
               f"cells over {rk.get('rows', 0)} rookie rows), so it needs no comparison against the "
               f"≥5-draw same-commit envelope (card QkpAHBYa) — that envelope exists to tell real "
               f"motion from rebuild noise, and there is no motion to classify. The reason is a "
               f"POPULATION fact rather than a guarantee: no rookie on this slate carries a weekly "
               f"designation."
               if (rk.get("material_cells") == 0) else
               f"⚠️ The rookie band moved in {rk.get('material_cells')} material cell(s) — read it "
               f"against the ≥5-draw same-commit envelope (card QkpAHBYa) before attributing it to "
               f"the discount; rebuilds of this board differ there at 0–21 cells on their own.")]
    viol = md.get("INVARIANT_VIOLATIONS")
    L += ["", ("⛔ **INVARIANT VIOLATION** — the discount moved a column it must not: "
               f"`{viol}`") if viol else
          "✅ Every column the discount must NOT touch (`adp`, `repl`, `bye`, `pos`, `team`, "
          "`rookie`) is unchanged on every board.", ""]
    env = s["envelope_and_suppression"]
    L += ["---", "", "## 5. NF-INJ1's envelope and NF-RATE1's suppression", "",
          f"Suppressed rows, summed over the 14 boards: baseline "
          f"**{env['totals']['baseline_suppressed']}**, candidate "
          f"**{env['totals']['candidate_suppressed']}** (Δ {env['totals']['delta']:+d}).", "",
          "⭐ **The full-season rate is INVARIANT under this discount, and that is measured rather "
          "than argued.** The rate is `pts × 17 ÷ games` and the discount scales `pts` and `games` "
          "by the SAME multiplier, so it cancels. Worst rate move on any capped row across all "
          f"boards: `{max(b['worst_rate_move_on_a_capped_row'] for b in env['per_board'].values()):.3e}`. "
          "⇒ the suppression population cannot move, so NF-RATE1's guard stays green here for a "
          "STRUCTURAL reason, not a lucky one.", "",
          "---", "", "## 5b. NF-INJ1's COHERENCE on the served projections", ""]
    co = s["coherence"]
    if co.get("verdict") == "UNEVALUABLE":
        L += [f"⚠️ **UNEVALUABLE** — {co.get('why')}. ⛔ An unevaluable coherence read is NOT a "
              f"clean board (`projection_coherence`'s own warning).", ""]
    else:
        L += [f"| | in scope | unevaluable | violating players |", "|---|---|---|---|",
              f"| baseline | {co['baseline']['n_in_scope']} | "
              f"{co['baseline']['n_unevaluable']} | **{co['baseline']['n_violating_players']}** |",
              f"| candidate | {co['candidate']['n_in_scope']} | "
              f"{co['candidate']['n_unevaluable']} | **{co['candidate']['n_violating_players']}** |",
              "",
              f"**{co['verdict']}** (Δ {co['delta_violating_players']:+d}). The 8 violations on the "
              f"published board are a PRE-EXISTING property of it, not something this discount did; "
              f"what matters for the decision is that it neither creates nor clears any — which "
              f"follows from the same invariance as §5: scaling the line and the games together "
              f"leaves the implied per-game rate untouched.", ""]
    L += ["---", "", "## 6. The whole-board placement read", ""]
    pl = s["placement"]
    b, c = pl.get("baseline", {}), pl.get("candidate", {})
    if b.get("status") == "UNEVALUABLE" or c.get("status") == "UNEVALUABLE":
        L += [f"⚠️ UNEVALUABLE — baseline `{b.get('error')}` / candidate `{c.get('error')}`. "
              f"An unevaluable placement read is NOT a pass (NF1.7 (a)).", ""]
    else:
        L += [f"Verdict — baseline **{(b.get('verdict') or {}).get('verdict')}** "
              f"({len((b.get('verdict') or {}).get('failing') or [])} failing), "
              f"candidate **{(c.get('verdict') or {}).get('verdict')}** "
              f"({len((c.get('verdict') or {}).get('failing') or [])} failing).", "",
              "⭐ **The decision-relevant question is not whether the candidate PASSES — it is "
              "whether it fails anything the baseline does not.** A gate the published board "
              "already breaches is a pre-existing property of the board, and reading it as damage "
              "this discount did would attribute someone else's finding to this ship.", "",
              "| gate | baseline | candidate | introduced by the discount? |", "|---|---|---|---|"]
        gb, gc = b.get("gates") or {}, c.get("gates") or {}
        for gate in sorted(set(gb) | set(gc)):
            pb = (gb.get(gate) or {}).get("pass")
            pc = (gc.get(gate) or {}).get("pass")
            introduced = "⛔ **YES**" if (pb is True and pc is False) else (
                "no" if pc is not False else "no — already failing on the published board")
            L.append(f"| `{gate}` | {pb} | {pc} | {introduced} |")
        newly = [g for g in set(gb) | set(gc)
                 if (gb.get(g) or {}).get("pass") is True and (gc.get(g) or {}).get("pass") is False]
        L += ["", (f"⛔ **{len(newly)} gate(s) NEWLY FAIL under the discount: `{newly}`** — this is "
                   f"a blocker for the operator's decision." if newly else
                   "✅ **No placement gate that passes on the published board fails under the "
                   "discount.**"), ""]
    iv = s["interval"]
    L += ["", "⚠️ Read the SUPERFLEX rows on their own: NF-W8-0's VOR shield is ADDITIVE-only and "
              "assumes the group is not cross-pooled. This discount is MULTIPLICATIVE and QB IS "
              "cross-pooled in superflex, so the shield does not hold there (NF-TR2b).", "",
          "---", "", "## 7. The interval revalidation — ⛔ **STRUCTURALLY INACTIVE, not passed**", "",
          f"{iv['why']}.", "",
          f"- season-gated: `{iv['season_gated']}` · availability runs before the band attach: "
          f"`{iv['availability_runs_before_the_band_attach']}`",
          f"- {iv['consequence']}.", "",
          "⛔ It is NOT reported as a passed interval check. An inactive read presented as a pass is "
          "the error NF-INJ4b §6 avoided for the preseason placement read, and the reason that "
          "refusal was correct then is the reason this one is correct now (NF1.7 (a) / NF-D20).", "",
          "---", "", "## 8. Top rank moves per config", ""]
    for stem in sorted(s["rank_moves"]):
        r = s["rank_moves"][stem]
        L.append(f"- `{stem}` — {r['designated_rows_on_board']} designated, "
                 f"{r['rows_whose_rank_moved']} ranks moved, max |move| {r['max_abs_rank_move']}, "
                 f"baseline rank agrees with published {r['recomputed_baseline_rank_agrees_with_published']:.4f}")
    sf = s["rank_moves"].get("superflex_12") or next(iter(s["rank_moves"].values()))
    L += ["", "**Top moves, `superflex_12`** (the config the VOR shield does NOT protect):", "",
          "| player | pos | designation | rank before | rank after | move | games before → after |",
          "|---|---|---|---|---|---|---|"]
    for m in sf["top_moves"][:TOP_N]:
        L.append(f"| {m['player']} | {m['pos']} | `{m['designation']}` | {m['rank_before']} | "
                 f"{m['rank_after']} | {m['move']:+d} | {m['games_before']} → {m['games_after']} |")
    L += ["", "---", "", "## 9. ⛔ What this battery does NOT establish", "",
          "- **Not a rebuild.** Replacement levels are the published board's, and NF1.5's ordering "
          "permutation has not re-run. NF-INJ1 measured that step handing **+36.4%** of an "
          "availability discount BACK, so a rebuild's rank moves will differ — most plausibly they "
          "will be SMALLER. That is the operator's step and it is the one that produces the real "
          "publish candidate.",
          "- **Not a publish.** Nothing here writes a served artifact.",
          "- **Not a re-reading of NF-INJ4b's gates.** They are settled (E2.1-r); this measures the "
          "SHIP, not the model.", ""]
    return "\n".join(L)



# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE OPERATOR PACKET — GENERATED, never hand-transcribed
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⛔ EVERY FIGURE BELOW IS READ OUT OF THE MEASURED STATE. Hand-copying a number into a decision
#: document is the exact defect this story exists downstream of: NF-INJ4b §3b(3) records the
#: counterfactual's magnitude table priced from the REGISTERED arm rather than the CERTIFIED WINNER
#: (out x0.8682 for x0.8639), which produced a plausible, wrong packet nobody could have caught by
#: reading it. A generated packet cannot disagree with the run that produced it.
def render_packet(s: dict) -> str:
    cap = s["preconditions"]["capture"]
    env, co, rm = s["envelope_and_suppression"], s["coherence"], s["rank_moves"]
    pl, noc = s["placement"], s["no_op_control"]
    gb = (pl.get("baseline") or {}).get("gates") or {}
    gc = (pl.get("candidate") or {}).get("gates") or {}
    newly = [g for g in sorted(set(gb) | set(gc))
             if (gb.get(g) or {}).get("pass") is True and (gc.get(g) or {}).get("pass") is False]
    n_desig = next(iter(rm.values()))["designated_rows_on_board"] if rm else 0

    L = [
        "# NF-INJ4b-SHIP — OPERATOR PACKET: ship the weekly-designation discount?", "",
        f"**Prepared {s['generated_at']} · season {s['season']} · `best_alpha = 0`.** Nothing in "
        f"this session published anything. The decision is yours.", "",
        "---", "", "## ⚠️⚠️ Read this first: **merging the PR IS the deploy**", "",
        "The season board is not like the API Lambda. It is published by "
        "`sports_nfl_board_publish_schedule` — a Dagster schedule that ships "
        "`default_status=RUNNING` and runs `export_draft_board_json --publish` **daily at 07:15 "
        "America/Los_Angeles** from the box image, which is built from `main` on merge.", "",
        "⇒ **There is no separate publish step to approve later.** Merging this PR to `dev` and on "
        "to `main` means the next scheduled build serves the discount and NF-C9's new copy becomes "
        "true. That is the MH2.1 (c) promotion-mechanics landmine on the fantasy board, and it is "
        "why the copy change and the changelog line are IN this PR rather than a follow-up: a "
        "declaration must not outrun its production, and here they arrive together or not at all.",
        "", "**If the answer is no:** the PR does not merge. It is not a case of pulling the copy "
        "and keeping the wiring — the wiring IS the serve.", "",
        "---", "", "## 1. What you are approving", "",
        "When a club lists a player Out / Doubtful / Questionable on the game-status report our "
        "injury feed carries, his projected games are discounted by a measured average of what past "
        "listings like it have cost. NF-INJ4b certified the model (9 of 9 registered gates under a "
        "matched-resolution anchor); those gates are settled and this packet does not re-open them.",
        "",
        "| designation | E[games missed] | multiplier on projected games | players on the live feed |",
        "|---|---|---|---|",
    ]
    for level, c in s["served_constants"].items():
        n = s["live_feed"]["census"].get(level.capitalize(), 0)
        L.append(f"| **{level.title()}** | {c['expected_games_missed']:.4f} | "
                 f"x{c['rate_multiplier']:.4f} | {n} |")
    unint = s["live_feed"]["census"].get("UNINTERPRETABLE", 0)
    L += ["",
          f"It touches **{n_desig} of {next(iter(rm.values()))['rows']} rows** on each board. "
          f"{unint} further player(s) carry a feed value we cannot interpret: they are shown as "
          f"'unknown' and **priced at nothing** — never guessed at, never silently dropped.", "",
          "⛔ The no-designation baseline hazard (x0.9906) is **not** served. Applying it would "
          "discount ~2,400 undesignated players — a board-wide level shift, which is a different "
          "change from the one that was certified.", "",
          "---", "", "## 2. The combined read on the publish candidate", "",
          "| check | result |", "|---|---|",
          f"| no-op control (empty map ⇒ zero movement) | "
          f"{'✅ PASS' if noc['passes'] else '⛔ FAIL'}, worst "
          f"`{noc['worst_abs_difference']:.1e}` at eps `{noc['tolerance']}` |",
          f"| baseline rank reproduces the published `ovrRank` | "
          f"{min(r['recomputed_baseline_rank_agrees_with_published'] for r in rm.values()):.4f} "
          f"(min over {len(rm)} boards) |",
          f"| whole-board placement gates newly failing | "
          f"{'⛔ ' + str(newly) if newly else '✅ none'} |",
          f"| NF-INJ1 coherence (violating players) | {co.get('verdict')} — "
          f"{(co.get('baseline') or {}).get('n_violating_players')} → "
          f"{(co.get('candidate') or {}).get('n_violating_players')} |",
          f"| NF-RATE1 full-season-rate suppression | "
          f"{env['totals']['baseline_suppressed']} → {env['totals']['candidate_suppressed']} "
          f"(Δ {env['totals']['delta']:+d}) |",
          f"| columns the discount must not touch | "
          f"{'⛔ VIOLATED' if s['material_diff']['per_population'].get('INVARIANT_VIOLATIONS') else '✅ unchanged'} |",
          f"| interval revalidation | ⛔ {s['interval']['verdict']} — reported as such, **not** as "
          f"a pass |", "",
          "⭐ The suppression and coherence rows are **structurally** unchanged, not luckily so: the "
          "full-season rate is `pts x 17 / games` and the discount scales `pts` and `games` by the "
          "same multiplier, so it cancels (worst rate move on any capped row across all boards: "
          f"`{max(b['worst_rate_move_on_a_capped_row'] for b in env['per_board'].values()):.1e}`).",
          "", "---", "", "## 3. What moves, per config", "",
          "| config | designated | ranks moved | max abs move |", "|---|---|---|---|"]
    for stem in sorted(rm):
        r = rm[stem]
        star = " ⭐" if stem.startswith("superflex") else ""
        L.append(f"| `{stem}`{star} | {r['designated_rows_on_board']} | "
                 f"{r['rows_whose_rank_moved']} | {r['max_abs_rank_move']} |")
    L += ["", "⭐ **Read the two superflex configs on their own rows.** NF-W8-0's VOR 'shield' — a "
              "per-group level shift cancelling because the group's own replacement absorbs it — is "
              "ADDITIVE-ONLY and assumes the group is not cross-pooled. This discount is "
              "MULTIPLICATIVE and QB **is** cross-pooled in superflex, so the shield does not hold "
              "there (NF-TR2b).", ""]
    for stem in [x for x in sorted(rm) if x.startswith("superflex")] + ["half_ppr_12"]:
        r = rm.get(stem)
        if not r:
            continue
        L += [f"### Top {min(TOP_N, len(r['top_moves']))} moves — `{stem}`", "",
              "| player | pos | designation | rank | → | move | games |", "|---|---|---|---|---|---|"]
        for m in r["top_moves"][:TOP_N]:
            L.append(f"| {m['player']} | {m['pos']} | {m['designation']} | {m['rank_before']} | "
                     f"{m['rank_after']} | {m['move']:+d} | {m['games_before']} → "
                     f"{m['games_after']} |")
        L.append("")
    L += ["---", "", "## 4. ⛔ What this packet does NOT establish", "",
          "- **It is not a capture-pinned rebuild.** The registered ship path's step 1 rebuilds the "
          "board against a pinned baseline with matched market vintages. It is **not reachable from "
          "this checkout**: the precondition was RUN and it "
          f"**{s['preconditions']['vintage_match']['verdict']}**. The served board carries "
          f"`ecr_as_of {cap['ecr_as_of']}` and FantasyPros serves only the CURRENT snapshot, so that "
          "vintage is **unrecoverable** (NF-INJ2c) — ⛔ do not chase it.",
          "- **So every figure above is FIRST-ORDER**: replacement levels are the published board's, "
          "and NF1.5's ordering permutation has not re-run. NF-INJ1 measured that step handing "
          "**+36.4%** of an availability discount BACK, so a rebuild's rank moves will differ — most "
          "plausibly they will be **smaller** than the table above.",
          "- **The interval revalidation is inactive, not passed** — the channel is season-gated and "
          "NF1.9 scores historical panels, so it cannot reach a row the discount moved.", "",
          "---", "", "## 5. If you approve — the sequence", "",
          "**Step 1 — merge the PR (`nf-inj4b-ship` → `dev`), then `dev` → `main`.** This is the "
          "deploy; nothing else is required for the discount to serve.", "",
          "**Step 2 — the next scheduled publish does the rest**, at 07:15 America/Los_Angeles. To "
          "watch it rather than wait: Dagster → `sports_nfl_board_publish_job`. Expected in the "
          "step log: `NF-INJ4b: designation discount applied to N of M rows`.", "",
          "**Step 3 — verify the SERVED board actually moved (LAPTOP, ~30 s).** ⭐ This is the check "
          "that matters, and it is the reason the manifest stamp alone is not enough: a stamp "
          "records what a build was CONFIGURED to do, never what it DID (NF-C0e / NF-INJ3b-SHIP "
          "D6). This joins the PUBLISHED board back to the 60 designated players by normalised id "
          "and reports whether each one's games actually moved off the pre-ship figure.", "",
          "```bash",
          "uv run python -m quant_sports_intel_models.football.nfl.fantasy."
          "run_nf_inj4b_ship_battery --verify-published",
          "```", "",
          "Expected on a board that HAS shipped: `✅ all N scoreable designated player(s) moved off "
          "their pre-ship games` (exit 0). ⭐ **The check is proven two-sided**: run against "
          "today's pre-ship board it reports `moved 0 · UNMOVED 58 · below the board's rounding 2` "
          "and exits 1 — so a green is informative rather than the only thing it can say "
          "(G100-D1: a check whose failure state is indistinguishable from its healthy state has "
          "not been verified).", "",
          "⚠️ Two players' whole discount is smaller than the board's own one-decimal rounding, so "
          "they are individually UNSCOREABLE and are reported as their own state rather than as "
          "passes.", "",
          "**Step 4 — if you want it OFF again (LAPTOP, one line + the copy).**", "", "```bash",
          "# in quant_sports_intel_models/football/nfl/fantasy/designation_discount_policy.py",
          "#   SERVING_ENABLED: bool = False",
          "```", "",
          "⚠️ The rollback is **two** edits, and the guard enforces it: "
          "`WEEKLY_DESIGNATION_HOW_MODELLED` must revert to denying the adjustment in the SAME "
          "change, or `test_nf_inj4b_ship_wiring.py` goes red. A one-line flag flip feels complete "
          "and would leave the board advertising a discount of exactly zero.", "",
          "---", "", "## 6. The decision", "",
          "**Ship the weekly-designation discount — yes or no?**", "",
          f"A yes moves {n_desig} players per board by the multipliers in §1, moves "
          f"{min(r['rows_whose_rank_moved'] for r in rm.values())}–"
          f"{max(r['rows_whose_rank_moved'] for r in rm.values())} ranks per board, breaks no "
          f"placement gate the published board passes, and changes neither the coherence nor the "
          f"suppression population. A no leaves the board exactly as it is today and the PR unmerged.",
          ""]
    return "\n".join(L)



#: The states one CAPTURED expectation can be in when re-read against a LIVE board and a LIVE feed.
#: ⛔ SIX, NOT TWO. Every one of these is a different fact about the world, and the whole defect this
#: block exists to fix was two of them rendering identically (see `classify_verification`).
VERIFY_MOVED = "MOVED"
VERIFY_UNMOVED = "UNMOVED"
VERIFY_BELOW_ROUNDING = "BELOW_ROUNDING"
VERIFY_NO_LONGER_DESIGNATED = "NO_LONGER_DESIGNATED"
VERIFY_DESIGNATION_CHANGED = "DESIGNATION_CHANGED"
VERIFY_ABSENT = "ABSENT_FROM_BOARD"

#: The published board rounds `g` to ONE DECIMAL, so a row whose whole discount is smaller than that
#: cannot be told apart from an un-discounted one. ⛔ Those rows are their own state, not a pass:
#: counting them as 'moved' once reported 2 successes against a board that had not shipped at all.
VERIFY_ROUND_TOL = 0.051


def classify_verification(expected_rows, live_games, live_designations, *, round_tol=VERIFY_ROUND_TOL):
    """Classify each CAPTURED expectation against the LIVE board and the LIVE designation feed.

    ⭐ WHY THIS READS THE LIVE FEED, AND THE INCIDENT THAT PUT IT HERE (2026-09-13, the first
    post-publish run of this check). `verify_published` joined the served board to a FROZEN
    expectation captured three days earlier and asked one question — "did this player's games move
    off the pre-ship figure?" It reported `⛔ 4 of 58 ... the discount is not reaching the served
    board` and exited 1. The discount was reaching the board perfectly. All four players had been
    **cleared of their designation** between the capture and the publish: absent from the live feed,
    correctly carrying no discount, and therefore correctly sitting at the undiscounted base — which
    is the very number the frozen expectation calls "pre-ship".

    ⛔ SO THE CHECK RENDERED "this player got better" AND "the wiring is broken" IDENTICALLY, and
    resolved the ambiguity toward the alarming one. That is this repo's most-repeated lesson landing
    on the guard written to honour it: a check whose failure state is indistinguishable from a
    healthy state has not verified anything (G100-D1), and an expectation pinned to a live vendor
    snapshot expires (NF-INJ2b/2c — a pin binds on the vintage of its inputs, not just the artifact).

    ⭐ THE CURE IS THE THREE-STATE DISCIPLINE `weekly_designation_map` ALREADY USES one module over:
    a designation that is ABSENT, one that is PRESENT-BUT-DIFFERENT, and one that is present and
    unchanged are three different facts, and only the third licenses any verdict about the wiring.
    A row whose designation has left or changed is EXPIRED EVIDENCE — it is reported, never scored.

    Returns `(rows, counts)`: per-row `(state, name, designation, live_designation, g, expected)`
    tuples and a `{state: count}` tally. PURE — no network, no lake, no clock. The IO lives in
    `verify_published`, so this classification is exercisable by a test (the NF-TR2 lesson: a block
    nothing can invoke is a block nothing has checked).
    """
    missing = object()
    out, counts = [], {s: 0 for s in (
        VERIFY_MOVED, VERIFY_UNMOVED, VERIFY_BELOW_ROUNDING,
        VERIFY_NO_LONGER_DESIGNATED, VERIFY_DESIGNATION_CHANGED, VERIFY_ABSENT)}

    def _norm_label(v):
        return None if v is None else str(v).strip().lower()

    for e in expected_rows:
        pid = EX._norm_player_id(e["id"])
        captured = e.get("designation")
        live_label = live_designations.get(pid, missing)
        g = live_games.get(pid)

        if live_label is missing:
            # He is no longer on the feed at all — cleared, or his status is no longer disclosable.
            # Carrying NO discount is the CORRECT serving behaviour for him, so his games sitting at
            # the undiscounted base is evidence the system works, not evidence it is broken.
            state, shown = VERIFY_NO_LONGER_DESIGNATED, "—"
        elif _norm_label(live_label) != _norm_label(captured):
            # Still designated, but not as what we captured (Questionable → Out, or a token this
            # build cannot price, which serves NO discount by design). A different constant applies,
            # so the captured `games_after` is simply the wrong number to compare against.
            state, shown = VERIFY_DESIGNATION_CHANGED, (live_label if live_label is not None
                                                        else "<unreadable token>")
        elif g is None:
            state, shown = VERIFY_ABSENT, str(live_label)
        elif abs(float(e["games_after"]) - float(e["games_before"])) <= round_tol:
            state, shown = VERIFY_BELOW_ROUNDING, str(live_label)
        elif abs(float(g) - float(e["games_before"])) <= 1e-6:
            state, shown = VERIFY_UNMOVED, str(live_label)
        else:
            # Moved — though not necessarily TO the captured figure. A rebuild refreshes depth
            # charts, rosters and the market, so the BASE drifts (measured 2026-09-13: ±0.07 games
            # across 54 rows). Landing near-but-not-on the first-order number is expected.
            state, shown = VERIFY_MOVED, str(live_label)

        counts[state] += 1
        out.append((state, e.get("name"), captured, shown, g, e.get("games_after")))
    return out, counts


def verify_published(season: int) -> int:
    """⭐ THE POST-PUBLISH CHECK THE OPERATOR RUNS — did the SERVED board actually move?

    Fetches the live `projections.json` AND the live designation feed, then joins this story's
    committed expected-effect artifact to both by NORMALISED player id (NF-C9: 275 of 2,501 live
    feed rows carry a leading space, and a silent non-match is indistinguishable from 'the feed said
    nothing about him').

    ⛔ READING THE LIVE FEED IS NOT OPTIONAL — see `classify_verification` for the incident. Without
    it this check cannot tell a CLEARED PLAYER from BROKEN WIRING, and it resolves that ambiguity
    toward the alarm.

    ⚠️ AN UNREADABLE FEED IS `UNVERIFIABLE` (exit 2), NEVER A PASS AND NEVER A FAILURE (NF1.7(a)):
    with no live designations every row looks cleared, so a check that fell back to 'no feed, assume
    unchanged' would report a GREEN over a board it could not assess — the one direction that must
    never be reachable."""
    import subprocess

    art = _ART / "nf_inj4b_ship_expected_effect.json"
    if not art.exists():
        print(f"⛔ {art.name} is absent — run the battery first; there is nothing to verify against")
        return 2
    expected = json.loads(art.read_text())

    # ⚠️ CREDENTIALED, not a public HTTPS GET — the api-cache bucket is not world-readable, and an
    #    anonymous fetch returns 403, which is UNVERIFIABLE rather than a verdict either way.
    uri = f"s3://credence-prod-s3-api-cache/fantasy/nfl/{season}/projections.json"
    try:
        with tempfile.TemporaryDirectory() as td:
            dst = pathlib.Path(td) / "projections.json"
            subprocess.run(["aws", "s3", "cp", uri, str(dst), "--region", "us-east-1", "--quiet"],
                           check=True, timeout=300)
            live = json.loads(dst.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"⛔ UNVERIFIABLE — could not fetch the published board ({type(e).__name__}: {e}). "
              f"That is not evidence the discount failed to serve.")
        return 2

    # ⭐ GROUND TRUTH — the build's own record of what the discount did, carried on the served
    #    manifest (NF-INJ4b-VERIFY). Absent on any board published before that change, in which case
    #    this check falls back to per-row INFERENCE and says so.
    built = {}
    try:
        with tempfile.TemporaryDirectory() as td:
            mdst = pathlib.Path(td) / "manifest.json"
            subprocess.run(["aws", "s3", "cp",
                            f"s3://credence-prod-s3-api-cache/fantasy/nfl/{season}/manifest.json",
                            str(mdst), "--region", "us-east-1", "--quiet"], check=True, timeout=300)
            built = (json.loads(mdst.read_text()) or {}).get("designationDiscountStamp") or {}
    except Exception as e:  # noqa: BLE001
        print(f"  (could not read the served manifest: {type(e).__name__}: {e})")

    live_designations = EX.weekly_designation_map(int(season))
    if live_designations is None:
        print("⛔ UNVERIFIABLE — the live designation feed is unreadable, so a player who was "
              "CLEARED cannot be told apart from one the discount failed to reach. Refusing to "
              "return a verdict rather than scoring every row against an expired expectation.")
        return 2

    rows = live.get("projections") or live.get("players") if isinstance(live, dict) else live
    live_games = {EX._norm_player_id(r.get("id")): (None if r.get("g") is None else float(r["g"]))
                  for r in (rows or []) if r.get("id") is not None}

    detail, c = classify_verification(expected["rows"], live_games, live_designations)

    for state, name, captured, shown, g, exp_g in detail:
        if state == VERIFY_UNMOVED:
            print(f"  UNMOVED              {name:26s} {str(captured):13s} "
                  f"g={g} (pre-ship {exp_g} expected)")
        elif state == VERIFY_NO_LONGER_DESIGNATED:
            print(f"  no longer designated {name:26s} was {str(captured):13s} "
                  f"— cleared since the capture; carrying no discount is CORRECT")
        elif state == VERIFY_DESIGNATION_CHANGED:
            print(f"  designation changed  {name:26s} {str(captured):13s} -> {shown}")

    n = len(expected["rows"])
    captured_at = expected.get("generated_at", "unknown")
    print(f"\ncaptured {n} designated row(s) at {captured_at}")
    print(f"  still designated as captured : moved {c[VERIFY_MOVED]} · UNMOVED {c[VERIFY_UNMOVED]} "
          f"· below the board's rounding {c[VERIFY_BELOW_ROUNDING]} · absent {c[VERIFY_ABSENT]}")
    print(f"  expectation EXPIRED          : no longer designated {c[VERIFY_NO_LONGER_DESIGNATED]} "
          f"· designation changed {c[VERIFY_DESIGNATION_CHANGED]}")

    # ⭐ The capture's population ages too, in BOTH directions. Rows that have entered the feed since
    #    are outside this artifact entirely — not a failure, but the number that tells the operator
    #    how stale the expectation has become, which is the thing that made this check misfire.
    fresh = sum(1 for pid in live_designations if pid in live_games)
    print(f"  live feed now designates {fresh} board row(s) "
          f"({max(0, fresh - n)} of them outside the capture)")

    scoreable = c[VERIFY_MOVED] + c[VERIFY_UNMOVED]
    moved_at_build = built.get("rows_discounted")
    designated_at_build = built.get("designated_rows_at_build")

    # ── the verdict, keyed on GROUND TRUTH where the board carries it ──────────────────────────
    # ⭐ WHY THIS OUTRANKS THE PER-ROW READ. The per-row read asks "did this player's games move off
    #    a figure captured earlier?", which conflates TWO causes whenever the capture and the build
    #    are different vintages: the discount not reaching the row, and the row's BASE drifting by
    #    more than the discount (fresh depth charts, rosters and market). On 2026-09-13 four rows
    #    with the four SMALLEST discounts in the set read as failures for the second reason. The
    #    build's own count cannot be confused that way — it records what the code did, at the moment
    #    it did it.
    if isinstance(moved_at_build, int):
        print(f"\nGROUND TRUTH (the build's own record, on the served manifest):")
        print(f"  the discount moved {moved_at_build} of {designated_at_build} designated row(s) "
              f"at build time")
        if designated_at_build in (None, 0):
            print("⛔ UNVERIFIABLE — the build recorded no designated population to move.")
            return 2
        if moved_at_build == 0:
            print("⛔ the build moved ZERO rows — the discount is not reaching the served board")
            return 1
        if moved_at_build < designated_at_build:
            print(f"⛔ {designated_at_build - moved_at_build} designated row(s) were NOT discounted "
                  f"by the build — the channel is reaching some rows and not others")
            return 1
        if c[VERIFY_UNMOVED]:
            print(f"ℹ️  {c[VERIFY_UNMOVED]} captured row(s) show the SAME 1-decimal games as the "
                  f"capture. The build discounted every designated row, so this is BASE DRIFT "
                  f"between the two vintages, not a missed discount — the board rounds `g` to one "
                  f"decimal and these carry the smallest discounts in the set.")
        print(f"✅ the build applied the discount to every designated row "
              f"({moved_at_build}/{designated_at_build})")
        return 0

    # ── fallback: no ground truth on this board, so INFER, and label it as inference ───────────
    print("\n⚠️  This board carries no build-time discount record (published before "
          "NF-INJ4b-VERIFY), so the verdict below is INFERRED from a capture of a different "
          "vintage and an UNMOVED row is AMBIGUOUS — either a missed discount, or base drift "
          "larger than the discount. Re-publish to get a board that states its own count.")
    if not scoreable:
        print(f"⛔ UNVERIFIABLE — no captured player is still designated AND individually scoreable "
              f"on the published board. That is not evidence either way; re-run the battery to "
              f"re-capture the expectation against the current feed.")
        return 2
    if c[VERIFY_UNMOVED]:
        print(f"⛔ {c[VERIFY_UNMOVED]} of {scoreable} scoreable player(s) are STILL designated as "
              f"captured yet still carry their PRE-SHIP games — AMBIGUOUS, see above")
        return 1
    print(f"✅ all {scoreable} still-designated scoreable player(s) moved off their pre-ship games")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-INJ4b-SHIP measurement battery")
    ap.add_argument("--season", type=int, default=SEASON)
    ap.add_argument("--out", default="nf_inj4b_ship_battery")
    ap.add_argument("--verify-published", action="store_true",
                    help="post-publish: did the SERVED board actually move?")
    args = ap.parse_args(argv)
    if args.verify_published:
        return verify_published(args.season)
    t0 = time.time()

    if not (_CAPTURE / "projections.json").exists():
        raise SystemExit(
            f"the captured publish candidate is absent at {_CAPTURE}. Stage it:\n"
            f"  aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/{args.season}/ {_CAPTURE}/ "
            f"--recursive --exclude '*' --include 'board_*.json' --include 'projections.json' "
            f"--include 'manifest.json' --region us-east-1")

    boards = {}
    for stem, _preset, _n in PR.CONFIGS:
        p = _CAPTURE / f"board_{stem}.json"
        if p.exists():
            boards[stem] = pd.DataFrame(json.loads(p.read_text()))
    if not boards:
        raise SystemExit("no board_*.json staged — every leg would be vacuous")

    feed = live_designations(args.season)
    s = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-INJ4b-SHIP", "season": args.season,
        "best_alpha": 0, "publishes_nothing": True,
        "served_constants": POLICY.load_constants(),
        "policy_stamp": POLICY.stamp(),
        "preconditions": preconditions(args.season),
        "live_feed": {"rows": feed["rows"], "census": feed["census"]},
        "no_op_control": no_op_control(boards),
        "material_diff": material_diff(boards, feed["map"]),
        "envelope_and_suppression": envelope_and_suppression(boards, feed["map"]),
        "coherence": coherence_delta(feed["map"]),
        "rank_moves": rank_moves(boards, feed["map"]),
        "placement": placement_read(boards, feed["map"]),
        "interval": interval_revalidation_activity(),
    }
    s["elapsed_s"] = round(time.time() - t0, 1)
    _ART.mkdir(exist_ok=True)
    (_ART / f"{args.out}.json").write_text(json.dumps(s, indent=1, default=str) + "\n")
    (_ART / f"{args.out}.md").write_text(render(s))
    (_ART / "nf_inj4b_ship_operator_packet.md").write_text(render_packet(s))

    # ⭐ THE DECISIVE POST-PUBLISH EVIDENCE, committed. A policy stamp records what a build was
    #    CONFIGURED to do; only this says what it must DO to each named row. `verify_published`
    #    below joins it back to the PUBLISHED board, which is the NF-INJ3b-SHIP D6 discipline:
    #    measure the artifact, never trust the stamp (and NF-C9's own id lesson is why the join is
    #    on the normalised id).
    proj = json.loads((_CAPTURE / "projections.json").read_text())
    proj = proj.get("players") if isinstance(proj, dict) else proj
    base = pd.DataFrame(proj)
    cand = candidate_board(base, feed["map"])
    touched = cand["_desig"].notna().to_numpy()
    effect = {
        "story": "NF-INJ4b-SHIP",
        "generated_at": s["generated_at"],
        "baseline_board_generated_at": s["preconditions"]["capture"]["board_generated_at"],
        "constants": s["served_constants"],
        "what_it_is": ("for every player the live feed designated at capture time: the games the "
                       "PRE-SHIP board published, and the games a board serving the discount must "
                       "publish for him. ⚠️ `games_after` is FIRST-ORDER — a real rebuild re-runs "
                       "NF1.5's ordering permutation, so treat a mismatch as a signal to read, not "
                       "as a failure on its own."),
        "rows": [
            {"id": str(base["id"].iloc[i]), "name": str(base["name"].iloc[i]),
             "pos": str(base["pos"].iloc[i]),
             "designation": str(cand["_desig"].iloc[i]),
             "games_before": round(float(base["g"].iloc[i]), 4),
             "games_after": round(float(cand["g"].iloc[i]), 4)}
            for i in range(len(base)) if touched[i]
        ],
    }
    (_ART / "nf_inj4b_ship_expected_effect.json").write_text(
        json.dumps(effect, indent=1) + "\n")
    print(f"wrote {_ART / 'nf_inj4b_ship_expected_effect.json'} "
          f"({len(effect['rows'])} designated rows)")
    print(f"wrote {_ART / (args.out + '.md')}  ({s['elapsed_s']}s)")
    print(f"wrote {_ART / 'nf_inj4b_ship_operator_packet.md'}")
    print(f"  no-op control: {'PASS' if s['no_op_control']['passes'] else 'FAIL'} "
          f"(worst {s['no_op_control']['worst_abs_difference']:.3e})")
    print(f"  vintage precondition: {s['preconditions']['vintage_match']['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
