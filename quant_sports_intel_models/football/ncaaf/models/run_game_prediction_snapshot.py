"""run_game_prediction_snapshot.py — NCAAF-PS CLI: take + persist a pre-kickoff snapshot.

Runs the SERVED P1.4 game model over the upcoming FBS-vs-FBS slate and appends one immutable row
per (game_id, snapshot_ts) to `ncaaf/derived/game_prediction_snapshots`, optionally fanning out to
a weekly P1.5 futures-board snapshot. See `game_prediction_snapshot.py` for the contract (the
DATE-based leakage gate, the READ-MERGE-WRITE that can never lose a prior week, `best_alpha=0`).

Usage (LAPTOP or BOX — it is a lake-only job: no Snowflake, no DuckDB mart, no local artifact
beyond the two committed served JSONs):

    # what WOULD be snapshotted, computed in full but written nowhere (the safe pre-flight)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_game_prediction_snapshot \
        --dry-run

    # the real weekly snapshot → the lake (this is what the Dagster op runs)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_game_prediction_snapshot \
        --s3 --futures

    # prove the served-contract assembly reproduces the P1.3 matrix, on a season that has both
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_game_prediction_snapshot \
        --verify-against-matrix 2025

The season is CLOCK-DERIVED (`sources.current_season()`) — never pinned, the P0.6 landmine.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps  # noqa: E402

log = logging.getLogger("ncaaf.prediction_snapshot.cli")

_RESULTS_DIR = Path(__file__).resolve().parent.parent / "ablation_results"
_REPORT_PATH = _RESULTS_DIR / "ncaaf_ps_prediction_snapshot.md"


# ══════════════════════════════════════════════════════════════════════════════════════════
# The run
# ══════════════════════════════════════════════════════════════════════════════════════════

def run_snapshot(season: int, *, snapshot_ts: datetime | None = None, horizon_days: float = 7.0,
                 min_lead_minutes: float = 0.0, as_of_week: int | None = None,
                 n_draws: int = 20_000, seed: int = 20260829, to_s3: bool = False,
                 local_root: str | None = None, read_local_root: str | None = None,
                 dry_run: bool = False, futures: bool = False, n_sims: int = 10_000) -> dict:
    """Take one snapshot. Returns a manifest dict (also what the Dagster op logs).

    ⚠️ `local_root` routes only the WRITE (a real-data smoke that lands in a local Delta table
    instead of prod S3); the slate + strengths still come from the lake. `read_local_root` is the
    separate, offline-test knob that also reads locally. Conflating the two would make the natural
    smoke — "run it for real but do not touch prod" — fail with a confusing "no games in the lake."

    A slate with NO upcoming games is a legitimate NO-OP (`status="no_games"`) — an off-week, a
    fire before the season opens. It is reported DISTINCTLY from a failure, because "nothing to do"
    and "we could not read the slate" looking alike is how a frozen feed goes unnoticed for weeks
    (the INC-38 / NF-FRESH1 class). Every other failure raises.
    """
    ts = snapshot_ts or gps.utc_now()
    served = gps.load_served_model()
    log.info("served model: %s (%s/%s, form %s) ← %s | mean %s (%d cols, pace %s)",
             served.version, served.dispersion.learner, served.dispersion.contract,
             served.dispersion.form, served.dispersion_path, served.mean.version,
             len(served.mean.columns), served.mean.pace_columns or "ABSENT")

    games = gps.load_season_games(season, local_root=read_local_root)
    slate = gps.select_upcoming_slate(games, ts, horizon_days=horizon_days,
                                      min_lead_minutes=min_lead_minutes)
    log.info("season %d: %d FBS-vs-FBS games in the lake; %d kick off in the next %.1f day(s) "
             "after %s", season, len(games), len(slate), horizon_days, gps._iso(ts))

    manifest: dict = {
        "story": "NCAAF-PS", "season": int(season), "snapshot_ts": gps._iso(ts),
        "horizon_days": float(horizon_days), "model_version": served.version,
        "model_contract": str(served.dispersion.contract), "framing": gps.FRAMING,
        "best_alpha": 0.0, "dry_run": bool(dry_run),
    }
    if slate.empty:
        log.info("no upcoming FBS-vs-FBS kickoffs inside the window — NO-OP (not a failure). "
                 "The next scheduled fire picks up whatever has entered the window by then.")
        manifest.update({"status": "no_games", "n_games": 0, "rows_written": 0})
        return manifest

    strength, week = gps.load_strength_week(season, as_of_week,
                                           local_root=read_local_root)
    log.info("strength vintage: season %d as_of_week %d (%d teams, %s)", season, week,
             len(strength),
             "pre-season priors" if int(strength["games_in_window"].max() or 0) == 0
             else f"max {int(strength['games_in_window'].max())} games in window")

    frame = gps.build_slate_frame(slate, strength)
    scored = gps.predict_slate(frame, served, n_draws=n_draws, seed=seed)

    hfa = float(strength["home_field_advantage"].mean())
    analytic = gps.analytic_margin_mu(scored, hfa)
    delta = np.abs(np.asarray(scored["mu_margin"], float) - analytic)
    log.info("DIAGNOSTIC — served μ_margin vs P1.5's analytic strength map: mean |Δ| %.2f, max "
             "%.2f pts (they legitimately differ; the served ridge carries NO neutral-site term, "
             "so a neutral game gets the intercept's blended home bump either way)",
             float(delta.mean()), float(delta.max()))

    rows = gps.build_snapshot_rows(scored, served, snapshot_ts=ts, strength_as_of_week=week)
    gps.assert_pre_kickoff(rows)
    gps.assert_no_edge_claim(rows)
    log.info("leakage gate PASSED — %d row(s), min lead %.1f min, max %.1f min",
             len(rows), float(rows["lead_minutes"].min()), float(rows["lead_minutes"].max()))

    manifest.update({
        "status": "ok", "n_games": int(len(rows)), "strength_as_of_week": int(week),
        "min_lead_minutes": float(rows["lead_minutes"].min()),
        "p_home_win_min": float(rows["p_home_win"].min()),
        "p_home_win_max": float(rows["p_home_win"].max()),
        "p_home_win_mean": float(rows["p_home_win"].mean()),
        "median_margin_interval_width": float(rows["margin_interval_width"].median()),
        "median_total_interval_width": float(rows["total_interval_width"].median()),
        "pace_term_active": bool(rows["pace_term_active"].any()),
    })
    _log_slate(rows)

    if dry_run or not (to_s3 or local_root):
        log.info("DRY RUN — %d row(s) computed, NOTHING written.", len(rows))
        manifest["rows_written"] = 0
    else:
        n = gps.write_snapshot(rows, season=season, source=gps.SNAPSHOT_SOURCE,
                               key=gps.GAME_SNAPSHOT_KEY, local_root=local_root)
        manifest["rows_written"] = int(len(rows))
        manifest["season_partition_rows"] = int(n)

    if futures:
        manifest["futures"] = _run_futures(season, games, strength, served, ts, week,
                                           n_sims=n_sims, seed=seed, dry_run=dry_run,
                                           local_root=local_root, to_s3=to_s3)
    return manifest


def run_futures_only(season: int, *, snapshot_ts: datetime | None = None,
                     as_of_week: int | None = None, n_sims: int = 10_000, seed: int = 20260829,
                     to_s3: bool = False, local_root: str | None = None,
                     read_local_root: str | None = None, dry_run: bool = False) -> dict:
    """Snapshot ONLY the P1.5 futures board.

    Deliberately its own entry point rather than `run_snapshot(horizon_days=0)`: the futures board
    is a season-long quantity that does not depend on there being an upcoming slate, and routing it
    through the game path would make it silently no-op on every off-week (the game path returns
    early on an empty slate — which is correct for games and wrong for futures).
    """
    ts = snapshot_ts or gps.utc_now()
    served = gps.load_served_model()
    games = gps.load_season_games(season, local_root=read_local_root)
    strength, week = gps.load_strength_week(season, as_of_week, local_root=read_local_root)
    manifest: dict = {
        "story": "NCAAF-PS", "season": int(season), "snapshot_ts": gps._iso(ts),
        "strength_as_of_week": int(week), "model_version": served.version,
        "framing": gps.FRAMING, "best_alpha": 0.0, "dry_run": bool(dry_run), "status": "ok",
    }
    manifest["futures"] = _run_futures(season, games, strength, served, ts, week, n_sims=n_sims,
                                       seed=seed, dry_run=dry_run, local_root=local_root,
                                       to_s3=to_s3)
    return manifest


def _run_futures(season, games, strength, served, ts, week, *, n_sims, seed, dry_run,
                 local_root, to_s3) -> dict:
    rows = gps.run_futures_snapshot(season, games, strength, served, snapshot_ts=ts,
                                    strength_as_of_week=week, n_sims=n_sims, seed=seed)
    gps.assert_no_edge_claim(rows, context="futures board snapshot")
    top = rows.sort_values("p_natty", ascending=False).head(5) if "p_natty" in rows.columns else rows.head(5)
    log.info("futures snapshot: %d team(s), %d sims. Top by title probability: %s", len(rows),
             n_sims, ", ".join(f"{r.team} {100 * getattr(r, 'p_natty', float('nan')):.1f}%"
                               for r in top.itertuples(index=False)))
    out = {"n_teams": int(len(rows)), "n_sims": int(n_sims)}
    if dry_run or not (to_s3 or local_root):
        out["rows_written"] = 0
        return out
    gps.write_snapshot(rows, season=season, source=gps.FUTURES_SNAPSHOT_SOURCE,
                       key=gps.FUTURES_SNAPSHOT_KEY, local_root=local_root)
    out["rows_written"] = int(len(rows))
    return out


def _log_slate(rows: pd.DataFrame) -> None:
    for r in rows.sort_values("commence_time").itertuples(index=False):
        log.info("  %s  %-26s @ %-26s  P(home) %.3f | margin %+.1f [%+.1f, %+.1f] | total %.1f "
                 "[%.1f, %.1f]", r.commence_time[:16], r.away_team, r.home_team, r.p_home_win,
                 r.mu_margin, r.margin_q10, r.margin_q90, r.mu_total, r.total_q10, r.total_q90)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Acceptance: does the lake-assembled contract reproduce the P1.3 matrix?
# ══════════════════════════════════════════════════════════════════════════════════════════

def verify_against_matrix(season: int, *, tol: float = 1e-9) -> dict:
    """Prove the lake-assembled served-contract columns EQUAL the P1.3 matrix's, on a real season.

    The snapshot assembles the served contract by joining `team_strength_week` onto the schedule —
    a second renderer of `feature_ncaaf_pregame_matrix.sql`'s strength join. This is the check that
    the second renderer agrees with the first (the E9.61 lesson: a grep of one file does not clear
    the other). It needs BOTH artifacts in the lake, so it runs on a completed season, not on the
    upcoming one whose matrix has not been rebuilt yet.
    """
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake

    served = gps.load_served_model()
    matrix = query_lake.query_or_missing(
        f"select * from {query_lake.delta('feature_pregame_matrix', tier='derived')} "
        f"where season = {int(season)}")
    if matrix is None or matrix.empty:
        raise SystemExit(f"[NCAAF-PS] the lake has no `feature_pregame_matrix` rows for {season} — "
                         "nothing to verify against. Pick a season P1.3 has landed.")
    games = gps.load_season_games(season)
    checked: dict[str, dict] = {}
    for week in sorted(int(w) for w in
                       query_lake.q(f"select distinct as_of_week from "
                                    f"{query_lake.delta('team_strength_week', tier='derived')} "
                                    f"where season = {int(season)}")["as_of_week"]):
        strength, _ = gps.load_strength_week(season, week)
        frame = gps.build_slate_frame(games, strength)
        m = matrix[matrix["season_order_week"] == week] if "season_order_week" in matrix else matrix
        joined = frame.merge(m, on="game_id", how="inner", suffixes=("", "_matrix"))
        if joined.empty:
            continue
        for col in served.mean.columns:
            if col in gps.PACE_COMPOSITE_COLS or f"{col}_matrix" not in joined.columns:
                continue
            a = pd.to_numeric(joined[col], errors="coerce").to_numpy(float)
            b = pd.to_numeric(joined[f"{col}_matrix"], errors="coerce").to_numpy(float)
            both = np.isfinite(a) & np.isfinite(b)
            if not both.any():
                continue
            d = float(np.max(np.abs(a[both] - b[both])))
            prev = checked.setdefault(col, {"max_abs_diff": 0.0, "n": 0})
            prev["max_abs_diff"] = max(prev["max_abs_diff"], d)
            prev["n"] += int(both.sum())
    if not checked:
        raise SystemExit("[NCAAF-PS] the verification compared ZERO columns — that is a REFUSAL, "
                         "not a pass (a check that cannot fail is not a check).")
    bad = {c: v for c, v in checked.items() if v["max_abs_diff"] > tol}
    for col, v in sorted(checked.items()):
        log.info("  %-42s max|Δ| %.3g over %d rows%s", col, v["max_abs_diff"], v["n"],
                 "   ❌" if col in bad else "")
    if bad:
        raise SystemExit(f"[NCAAF-PS] ❌ the lake-assembled contract DISAGREES with the P1.3 matrix "
                         f"on {list(bad)} — the snapshot would serve different inputs than the "
                         "model was certified on. Fix `STRENGTH_COLUMN_MAP`.")
    log.info("✅ %d served-contract column(s) reproduce the P1.3 matrix exactly (tol %.0e) on "
             "season %d", len(checked), tol, season)
    return {"season": int(season), "columns_checked": len(checked), "max_abs_diff":
            max(v["max_abs_diff"] for v in checked.values())}


# ══════════════════════════════════════════════════════════════════════════════════════════
# Report + CLI
# ══════════════════════════════════════════════════════════════════════════════════════════

def write_report(manifest: dict) -> None:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    f = manifest.get("futures") or {}
    lines = [
        "# NCAAF-PS — pre-kickoff game-prediction snapshots",
        "",
        f"_Last run: {manifest.get('snapshot_ts')} (UTC)_",
        "",
        "## What this is",
        "",
        "One immutable row per `(game_id, snapshot_ts)` in "
        "`s3://…/ncaaf/derived/game_prediction_snapshots`, written BEFORE kickoff, carrying the "
        "served P1.4 model's win probability and the margin/total predictive distributions. It is "
        "the forward track record: a backtest can always be re-derived, so only a row written in "
        "advance shows what we would actually have said.",
        "",
        "⚠️ **Market-blind projection — `best_alpha = 0`.** Probabilities and intervals only; no "
        "pick, no edge, no win-rate. P1.4's CLV leg came back a clean null (ATS 0.496 = placebo), "
        "so an edge claim would assert something the evidence does not support. "
        "`assert_no_edge_claim` makes that a schema property.",
        "",
        "## Last run",
        "",
        f"| field | value |", "|---|---|",
        f"| season | {manifest.get('season')} |",
        f"| status | `{manifest.get('status')}` |",
        f"| games snapshotted | {manifest.get('n_games')} |",
        f"| rows written | {manifest.get('rows_written')} |",
        f"| strength vintage | `as_of_week = {manifest.get('strength_as_of_week')}` |",
        f"| served model | `{manifest.get('model_version')}` "
        f"({manifest.get('model_contract')}) |",
        f"| min lead to kickoff | {manifest.get('min_lead_minutes', float('nan')):.0f} min |",
        f"| P(home win) range | {manifest.get('p_home_win_min', float('nan')):.3f} – "
        f"{manifest.get('p_home_win_max', float('nan')):.3f} |",
        f"| median 80% margin interval | "
        f"{manifest.get('median_margin_interval_width', float('nan')):.1f} pts |",
        f"| median 80% total interval | "
        f"{manifest.get('median_total_interval_width', float('nan')):.1f} pts |",
        f"| pace term active | {manifest.get('pace_term_active')} |",
        f"| futures teams snapshotted | {f.get('n_teams', '—')} |",
        "",
        "## The gates",
        "",
        "* **Leakage (HALT, DATE-based).** `assert_pre_kickoff` refuses the whole write unless "
        "every row's `snapshot_ts` is strictly before its `commence_time`. It is deliberately "
        "date-based: a week-based assertion re-uses CFBD's postseason week ordering (which "
        "restarts at 1) and passes green on exactly the rows it should catch — the P1.1/P1.2 "
        "lesson.",
        "* **Never lose a prior week.** The writer READ-MERGE-WRITEs the season partition "
        "(`s3io.write_season_partition` overwrites), dropping only the `(game_id, snapshot_ts)` "
        "keys the new batch re-covers. A transient lake read RAISES rather than being mistaken "
        "for an empty partition.",
        "* **Contract coverage.** `assert_contract_covered` refuses to score if any served column "
        "is absent or wholly NULL — a missing column is mean-imputed to exactly 0.0, which would "
        "silently serve a different model than the one certified.",
        "",
        "## Known limits of the served model (stated, not patched)",
        "",
        "* The served `strength_pace` contract carries **no neutral-site term** — the intercept "
        "absorbs one blended home-field bump (P2.1). Neutral-site games are priced with it; "
        "`is_neutral_site` is persisted so the limitation is auditable.",
        "* The certified **pace term is inert pre-season** (week-1 tempo is NULL by construction, "
        "and a NULL column contributes exactly 0.0). `pace_term_active` records it per row.",
        "",
        "## The assembly is verified, not asserted",
        "",
        "The snapshot joins `team_strength_week` onto the schedule to rebuild the served contract — "
        "a SECOND renderer of `feature_ncaaf_pregame_matrix.sql`'s strength join, and a grep of one "
        "file never clears the other (E9.61). `--verify-against-matrix 2025` compares the two on "
        "real data: **all 25 served non-pace columns reproduce the P1.3 matrix to float noise "
        "(max |Δ| 6.75e-14) across 807 games**, at each game's own as-of week.",
        "",
        "## ⏭️ The operator prerequisite (quality, not a blocker)",
        "",
        "**Run the close-to-kickoff P1.2 RE-FIT before the first real snapshot.** Until fall-camp "
        "covariates publish, the strength mart carries the pre-season COLD START — a 2025 "
        "carry-forward, which is why the current 2026 board has Indiana leading. A snapshot is by "
        "design immutable and cannot be retaken after kickoff, so firing before the re-fit would "
        "freeze the cold start into the permanent forward record. The schedule therefore ships "
        "`default_status=STOPPED`; enable it only after the re-fit.",
        "",
    ]
    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    log.info("report → %s", _REPORT_PATH)


def main(argv=None) -> int:
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season

    p = argparse.ArgumentParser(description="NCAAF-PS pre-kickoff prediction snapshot")
    p.add_argument("--season", type=int, default=None,
                   help="default: the clock-derived current_season() — never pin it (P0.6)")
    p.add_argument("--horizon-days", type=float, default=7.0,
                   help="snapshot games kicking off within this many days (default 7 = the "
                        "weekly cadence)")
    p.add_argument("--min-lead-minutes", type=float, default=0.0,
                   help="K−buffer: skip a game kicking off sooner than this")
    p.add_argument("--as-of-week", type=int, default=None,
                   help="strength vintage (default: the latest emitted for the season)")
    p.add_argument("--n-draws", type=int, default=20_000)
    p.add_argument("--n-sims", type=int, default=10_000, help="futures-board simulations")
    p.add_argument("--seed", type=int, default=20260829)
    p.add_argument("--s3", action="store_true", help="write to the sports lake")
    p.add_argument("--local-root", default=None,
                   help="WRITE to a local Delta table instead of prod S3 (the real-data smoke; "
                        "the slate + strengths still come from the lake)")
    p.add_argument("--read-local-root", default=None,
                   help="also READ the slate/strengths from a local Delta table (offline only)")
    p.add_argument("--dry-run", action="store_true", help="compute everything, write nothing")
    p.add_argument("--futures", action="store_true", help="also snapshot the P1.5 futures board")
    p.add_argument("--futures-only", action="store_true",
                   help="snapshot ONLY the futures board (no game slate needed)")
    p.add_argument("--verify-against-matrix", type=int, default=None, metavar="SEASON",
                   help="acceptance: prove the assembled contract equals the P1.3 matrix's")
    p.add_argument("--no-report", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.verify_against_matrix is not None:
        print(json.dumps(verify_against_matrix(args.verify_against_matrix), indent=2))
        return 0

    season = args.season if args.season is not None else current_season()
    if args.futures_only:
        manifest = run_futures_only(
            season, as_of_week=args.as_of_week, n_sims=args.n_sims, seed=args.seed,
            to_s3=args.s3, local_root=args.local_root, read_local_root=args.read_local_root,
            dry_run=args.dry_run)
        print(json.dumps(manifest, indent=2, default=float))
        return 0
    manifest = run_snapshot(
        season, horizon_days=args.horizon_days, min_lead_minutes=args.min_lead_minutes,
        as_of_week=args.as_of_week, n_draws=args.n_draws, seed=args.seed, to_s3=args.s3,
        local_root=args.local_root, read_local_root=args.read_local_root, dry_run=args.dry_run,
        futures=args.futures, n_sims=args.n_sims)
    print(json.dumps(manifest, indent=2, default=float))
    if not args.no_report and manifest.get("status") == "ok":
        write_report(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
