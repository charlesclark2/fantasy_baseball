"""run_nf_inj_news_1_measure.py — NF-INJ-NEWS-1's PRE-PUBLISH MEASUREMENT.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj_news_1_measure \\
        --candidates quant_sports_intel_models/football/nfl/fantasy/data/reported_absence_overrides.proposed.yaml

⚖️ WHAT THIS ANSWERS, and why it has to be answered before anything is published: the reported-
absence cap is an OPERATOR JUDGMENT, so there is no accuracy gate to clear — the only responsible
gate is "show the operator exactly what this does to the board and let them decide". This produces
that number. It certifies nothing and it is not a model evaluation.

⭐ IT MEASURES THE SERVED PATH, NOT THE CAP ARITHMETIC. Knowing an override caps a player at 9 games
is the easy half and it is not the question. The question is what reaches the BOARD, and between
the cap and the board sits NF1.5's within-position re-ordering, which permutes the projected-POINT
multiset and rescales each row's stat line to its new level — through `nf1_model._RAW_SCALE_COLS`,
which contains the twelve stat columns and NOT `proj_games`. So a capped player promoted within the
multiset gets his line multiplied while his games stay cut, and part of the discount is HANDED BACK.
NF-INJ1 measured that give-back at **+36.4%** for the served arm on the formally-capped cohort.

⛔ THEREFORE: DO NOT ASSUME THE GIVE-BACK IS PROPORTIONAL, and do not reuse 36.4%. It is measured
per cohort, and this cohort is a different one (untagged players, different positions, different
places in their positions' point multisets). `injury_giveback` below computes it for THIS cohort on
THIS build — reusing the old figure would be exactly the kind of inherited constant this program
refuses elsewhere.

WHAT IT RUNS
  1. Resolve each candidate to a board `player_id` — BY NAME against the built board, which is the
     join target itself. See `resolve_by_name` for why that is the only defensible direction.
  2. Build the board TWICE — baseline (no overrides) and with the resolved candidates — through the
     real build+export chain, so the numbers include NF1.5's re-ordering rather than modelling it.
  3. Diff: which rows moved, how far, and where they land across positions.
  4. Compute the give-back for this cohort.

⏭️ TWO EXISTING INSTRUMENTS RUN AFTER THIS, and they are NOT re-implemented here:
   • `run_nf_tr2b_placement_read --from-dir <with-overrides dir>` — the whole-board placement read
     (within-position order, the rookie placement cap, position survival, band integrity).
   • `run_interval_revalidation` — the standing coverage-floor gate.
     ⭐ It is INVARIANT to this change BY CONSTRUCTION, and that is worth stating rather than
     leaving to be inferred: it validates the interval bands on HISTORICAL walk-forward panels, and
     `load_overrides`' season gate means a 2026 judgment can never reach a historical fold. Running
     it is a regression check that the gate held, not a measurement of the overrides.

🖥️ RUN IT IN THE MAIN CHECKOUT. It needs `sports.duckdb` and the artifact caches, which are
gitignored and therefore ABSENT from any worktree (NF-INFRA1). It is also a LONG RUN (two full board
builds), so it is an operator command, not a session one.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A
from quant_sports_intel_models.football.nfl.fantasy import reported_absence_overrides as RAO

log = logging.getLogger("nfl.fantasy.inj_news_1_measure")

_ROOT = Path(__file__).resolve().parents[5]
_ART = Path(__file__).resolve().parent / "artifacts"
_OUT_MD = _ROOT / "ablation_results" / "nf_inj_news_1_board_delta.md"
_OUT_JSON = _ROOT / "ablation_results" / "nf_inj_news_1_board_delta.json"

CANDIDATE_TIERS = ("proposed_tier_a", "proposed_tier_b")


def resolve_by_name(candidates: list[dict], board: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Resolve each candidate to a board `player_id` by NORMALISED NAME + POSITION.

    ⭐ BY NAME, AGAINST THE BOARD, and both halves of that are deliberate.

    BY NAME because the id is the thing under test. NF-C9 published a board whose id-keyed check
    reported "0 join failures" while 275 of 2,501 feed ids carried a leading space — a check keyed
    on the join key cannot see a defect in that key, and the miss classified as "not on the board"
    rather than as a failure. Names are the independent key.

    AGAINST THE BOARD rather than against Sleeper because the board is where the override has to
    land. Resolving through a third source would leave a hop where the two could disagree.

    ⛔ AN AMBIGUOUS OR MISSING MATCH IS RETURNED UNRESOLVED, NEVER GUESSED. A wrong id renders
    identically to a genuine absence on every surface, so a near-match silently accepted is the
    worst outcome available. Returns `(resolved, unresolved)` and the caller reports BOTH.
    """
    key = board.assign(_k=board["player_name"].map(A._normalize_name).astype(str) + "|"
                       + board["position"].astype(str).str.upper())
    resolved, unresolved = [], []
    for c in candidates:
        k = f"{A._normalize_name(str(c['player_name']))}|{str(c.get('position') or '').upper()}"
        hit = key[key["_k"] == k]
        if len(hit) != 1:
            unresolved.append({**c, "_reason": ("no board row matched this name+position"
                                                if hit.empty else
                                                f"{len(hit)} board rows matched — ambiguous")})
            continue
        resolved.append({**c, "player_id": RAO.normalize_player_id(hit.iloc[0]["player_id"])})
    return resolved, unresolved


def write_candidate_file(rows: list[dict], path: Path, season: int) -> Path:
    """Write the resolved candidates as a REAL overrides file, so the measured build goes through
    exactly the loader, validation and expiry the published build would. ⛔ Never hand the projection
    a hand-built row list: that would measure a path nobody serves."""
    path.write_text(yaml.safe_dump({
        "schema_version": 1,
        "season": int(season),
        "overrides": [{k: (v.isoformat() if isinstance(v, date) else v)
                       for k, v in r.items()
                       if k in ("player_id", "player_name", "expected_games_missed", "source_url",
                                "note", "entered_by", "entered_at", "review_by")}
                      for r in rows],
    }, sort_keys=False))
    return path


def build(season: int, out_dir: Path, overrides: "Path | None", duckdb: str) -> None:
    """One full build+export through the REAL chain, with `NF_REPORTED_ABSENCE_OVERRIDES` pointed at
    `overrides` (or at an empty file for the baseline arm).

    ⚠️ The env var is set on the SUBPROCESS ONLY and never exported into this process's environment,
    so it cannot leak into a later publishing build from the same shell (the documented-but-actually-
    set class, facing the dangerous way)."""
    env = {**os.environ}
    env["NF_REPORTED_ABSENCE_OVERRIDES"] = str(overrides) if overrides else ""
    for cmd in (
        [sys.executable, "-m", "quant_sports_intel_models.football.nfl.fantasy.run_nf1_5",
         "--mode", "build", "--duckdb", duckdb, "--projection-season", str(season)],
        [sys.executable, "-m", "quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json",
         "--season", str(season), "--out-dir", str(out_dir)],
    ):
        log.info("$ %s", " ".join(cmd))
        subprocess.run(cmd, cwd=_ROOT, env=env, check=True)


def board_delta(base_dir: Path, over_dir: Path, capped: set) -> dict:
    """Diff two PUBLISHED board directories: which rows moved, how far, and across which positions.

    ⭐ IT READS THE PUBLISHED ARTIFACTS, not the in-memory frames. The artifact is what a reader
    gets, and this repo has twice found a defect that existed only between the frame and the file
    (NF-C0e's two post-merge defects were found by reading the published board, never by CI)."""
    out: dict = {"configs": {}}
    for path in sorted(over_dir.glob("board_*.json")):
        b = {r["id"]: r for r in json.loads((base_dir / path.name).read_text())}
        o = json.loads(path.read_text())
        moves = []
        for r in o:
            prev = b.get(r["id"])
            if prev and prev.get("ovrRank") != r.get("ovrRank"):
                moves.append({"id": r["id"], "name": r.get("name"), "pos": r.get("pos"),
                              "from": prev.get("ovrRank"), "to": r.get("ovrRank"),
                              "delta": (r.get("ovrRank") or 0) - (prev.get("ovrRank") or 0),
                              "capped": r["id"] in capped,
                              "g_from": prev.get("g"), "g_to": r.get("g"),
                              "pts_from": prev.get("pts"), "pts_to": r.get("pts")})
        moves.sort(key=lambda m: -abs(m["delta"]))
        # ⚠️ COLLATERAL IS REPORTED SEPARATELY FROM THE INTENDED MOVES. Capping one player pushes
        # every player he passes the other way, and a single "N rows moved" figure hides which of
        # those two things happened — the operator is approving the intended change, not the churn.
        out["configs"][path.stem] = {
            "rows": len(o),
            "moved": len(moves),
            "moved_capped": sum(1 for m in moves if m["capped"]),
            "moved_collateral": sum(1 for m in moves if not m["capped"]),
            "largest": moves[:15],
            "by_position": pd.Series([m["pos"] for m in moves]).value_counts().to_dict() if moves else {},
        }
    return out


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ-NEWS-1 pre-publish board-delta measurement")
    ap.add_argument("--candidates", required=True, help="the seed PROPOSAL yaml")
    ap.add_argument("--tiers", default=",".join(CANDIDATE_TIERS),
                    help="which proposal tiers to measure (comma-separated)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--board-parquet", default=None,
                    help="an already-built board parquet to resolve names against "
                         "(default: the served nf1_5 artifact)")
    ap.add_argument("--work-dir", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    proposal = yaml.safe_load(Path(a.candidates).read_text()) or {}
    cands: list[dict] = []
    for tier in a.tiers.split(","):
        cands.extend(proposal.get(tier.strip()) or [])
    if not cands:
        log.error("no candidates in tiers %s — nothing to measure", a.tiers)
        return 1

    board_path = Path(a.board_parquet or _ART / f"nf1_5_season_projections_{a.season}.parquet")
    if not board_path.exists():
        log.error("no built board at %s — build one first (this is the NF-INFRA1 gitignored-"
                  "artifact case; run in the MAIN CHECKOUT)", board_path)
        return 1
    board = pd.read_parquet(board_path)
    resolved, unresolved = resolve_by_name(cands, board)
    log.info("resolved %d/%d candidates by name", len(resolved), len(cands))
    for u in unresolved:
        # ⚠️ LOUD. An unresolved candidate is a row the operator believes is applied and is not.
        log.warning("[ALERT] UNRESOLVED %s (%s) — %s", u.get("player_name"), u.get("position"),
                    u.get("_reason"))
    if not resolved:
        log.error("nothing resolved — cannot measure")
        return 1

    work = Path(a.work_dir or tempfile.mkdtemp(prefix="nf_inj_news_1_"))
    base_dir, over_dir = work / "baseline", work / "with_overrides"
    base_dir.mkdir(parents=True, exist_ok=True)
    over_dir.mkdir(parents=True, exist_ok=True)
    empty = write_candidate_file([], work / "empty.yaml", a.season)
    cand_file = write_candidate_file(resolved, work / "candidates.yaml", a.season)

    log.info("── BASELINE build (no overrides) ─────────────────────────────────────────────")
    build(a.season, base_dir, empty, a.duckdb)
    base_mvp1 = pd.read_parquet(_ART / f"nfl_fantasy_season_projections_{a.season}.parquet")
    log.info("── WITH-OVERRIDES build ──────────────────────────────────────────────────────")
    build(a.season, over_dir, cand_file, a.duckdb)
    over_mvp1 = pd.read_parquet(_ART / f"nfl_fantasy_season_projections_{a.season}.parquet")
    over_nf15 = pd.read_parquet(_ART / f"nf1_5_season_projections_{a.season}.parquet")

    capped = {r["player_id"] for r in resolved}
    delta = board_delta(base_dir, over_dir, capped)

    # ⭐ THE GIVE-BACK, MEASURED FOR THIS COHORT — never inherited from NF-INJ1's +36.4%.
    from quant_sports_intel_models.football.nfl.fantasy import (
        run_nf_inj2_rate_permutation as RP,
    )
    giveback = RP.injury_giveback(over_mvp1, base_mvp1, over_nf15, sorted(capped))

    result = {
        "story": "NF-INJ-NEWS-1",
        "read": "pre-publish board delta (an operator-judgment mechanism; certifies nothing)",
        "season": a.season,
        "candidates": len(cands),
        "resolved": len(resolved),
        "unresolved": unresolved,
        "capped_ids": sorted(capped),
        "giveback": giveback,
        "board_delta": delta,
        "next_steps": [
            f"run_nf_tr2b_placement_read --from-dir {over_dir}",
            "run_interval_revalidation (regression only — invariant by the season gate)",
        ],
    }
    _OUT_JSON.write_text(json.dumps(result, indent=1, default=str))
    _OUT_MD.write_text(_md(result))
    print(json.dumps({k: result[k] for k in
                      ("resolved", "unresolved", "giveback")}, indent=1, default=str))
    for cfg, d in delta["configs"].items():
        print(f"{cfg:24s} moved {d['moved']:4d} "
              f"(capped {d['moved_capped']}, collateral {d['moved_collateral']}) of {d['rows']}")
    return 0


def _md(r: dict) -> str:
    lines = [f"# NF-INJ-NEWS-1 — pre-publish board delta ({r['season']})", "",
             "**This certifies nothing.** The reported-absence cap is an operator judgment with a "
             "source attached, never a fitted model; it has not been backtested and no claim of "
             "improvement attaches to it. This report exists so the operator can approve the first "
             "publish with the board delta in hand.", "",
             f"- candidates measured: **{r['resolved']} of {r['candidates']}**"]
    if r["unresolved"]:
        lines.append(f"- ⚠️ **UNRESOLVED: {len(r['unresolved'])}** — "
                     + "; ".join(f"{u.get('player_name')} ({u.get('_reason')})"
                                 for u in r["unresolved"]))
    g = r["giveback"]
    lines += ["", "## NF1.5 give-back on THIS cohort", "",
              "NF1.5 re-orders each position by handing every player a different player's projected-"
              "point level and rescaling his stat line to match — but `_RAW_SCALE_COLS` does not "
              "contain `proj_games`, so a capped player promoted within the multiset gets his line "
              "multiplied while his games stay cut. Part of the cap is handed back.", "",
              f"- measured give-back: **{g.get('giveback_pct')}%** on {g.get('n')} capped rows",
              f"- median point ratio (with-overrides ÷ pre-ordering): {g.get('median_point_ratio')}",
              f"- scaled UP: {g.get('n_scaled_up')} · scaled DOWN: {g.get('n_scaled_down')}", "",
              "⛔ Do not compare this to NF-INJ1's +36.4% as though it were the same quantity: that "
              "figure is the served arm's give-back on the FORMALLY-capped cohort. This is a "
              "different cohort in different places in their positions' multisets.", "",
              "## Board delta, per served config", ""]
    for cfg, d in r["board_delta"]["configs"].items():
        lines.append(f"### {cfg} — {d['moved']} of {d['rows']} rows moved "
                     f"({d['moved_capped']} capped, {d['moved_collateral']} collateral)")
        lines.append(f"by position: {d['by_position']}")
        if d["largest"]:
            lines += ["", "| player | pos | rank | games | points | capped |",
                      "|---|---|---|---|---|---|"]
            for m in d["largest"]:
                lines.append(f"| {m['name']} | {m['pos']} | {m['from']} → {m['to']} "
                             f"| {m['g_from']} → {m['g_to']} | {m['pts_from']} → {m['pts_to']} "
                             f"| {'yes' if m['capped'] else ''} |")
        lines.append("")
    lines += ["## Still to run (existing instruments, not re-implemented here)", ""]
    lines += [f"- `{s}`" for s in r["next_steps"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
