"""run_league_board.py — NF-C1-lite CLI: MVP-1 raw projections → per-league scored + ranked boards.

Reads the MVP-1 season projection (the raw stat line — `mart_nfl_fantasy_season_projection` / the S3
Delta `nfl/fantasy/derived/season_projections`, or a local artifact parquet), RESCORES it per league
config with the sport-agnostic `fantasy_engine`, computes VOR / positional scarcity (flex + superflex
allocation), and lands a cross-position ranked board per preset to the lake + readable CSVs + a
face-validity report. The board is MVP-3's (draft optimizer) input contract.

⚠️ RESCORES THE RAW STAT LINE — never the MVP-1 `proj_fp_*` convenience columns (those are one format).

⭐ RUN ON THE LAPTOP (like the MVP-1 projection). SF-free; laptop compute + S3 I/O, zero shared-box CPU.
`SPORTS_LAKE_REGION=us-east-2` for the S3 read/write.

Read the projection from the local MVP-1 artifact (default) or straight from the lake Delta:
    # from the local MVP-1 artifact parquet (offline, no creds):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_league_board \
        --projection-season 2026

    # from the S3 lake Delta (the real lake):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
        quant_sports_intel_models.football.nfl.fantasy.run_league_board \
        --projection-season 2026 --from-lake --s3

Outputs (per projection season):
  * <out-dir>/league_boards/nfl_league_board_<preset>_<year>.csv   — a readable ranked board per preset
  * <out-dir>/league_configs/<preset>.json                          — the config object (shared contract)
  * s3://credence-sports-lakehouse/nfl/fantasy/derived/league_boards/season=<year>/  (--s3; all presets)
  * ablation_results/nf_c1_lite_league_board.md                     — the face-validity report
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

from quant_sports_intel_models.fantasy_engine import score_players  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import captured_terms  # noqa: E402
from quant_sports_intel_models.fantasy_engine.vor import (  # noqa: E402
    build_board,
    compute_replacement_levels,
    replacement_summary,
)
from quant_sports_intel_models.football.nfl.fantasy.league_presets import (  # noqa: E402
    NFL_PROFILE,
    PRESETS,
    get_preset,
)

log = logging.getLogger("nfl.fantasy.league_board")

_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_c1_lite_league_board.md"
)

ENGINE_VERSION = "nfl_fantasy_league_board_v1"

# ── WHICH season projection the boards are SCORED from (NF1.5b) ─────────────────────────────────
# ⭐ Default = the NF1.5 REFINED market-aware board (the NF1.5b re-land), not MVP-1. The board and
# the Projections surface MUST come from the same projection: they are two views of one ranking, and
# a drafter who sees a player at WR4 on one and WR9 on the other has been handed a bug, not a nuance.
# `export_draft_board_json.py` refuses to publish when its `--projection-source` disagrees with the
# `projection_source` these boards carry, which is why the column is emitted rather than implied.
PROJECTION_SOURCES = ("nf1_5", "mvp1")
DEFAULT_PROJECTION_SOURCE = "nf1_5"
_PROJECTION_PARQUET = {
    "mvp1": "nfl_fantasy_season_projections_{season}.parquet",
    "nf1_5": "nf1_5_season_projections_{season}.parquet",
}
_PROJECTION_LAKE_SOURCE = {"mvp1": "season_projections", "nf1_5": "nf1_5_season_projections"}

# The emitted per-league board schema (MVP-3's input contract). Ordered for readability.
BOARD_COLS = [
    "config_name", "sport", "season", "player_id", "player_name", "position", "team_id",
    "is_rookie", "proj_games",
    "league_points", "replacement_points", "vor", "positional_rank", "overall_rank",
    "league_points_p10", "league_points_p90", "vor_p10", "vor_p90",
    "uncertainty_type", "n_teams", "ppr", "superflex", "engine_version", "generated_at",
    # NF1.5b — the projection lineage this board was scored from ("nf1_5" | "mvp1"). Emitted so the
    # export can PROVE the draft board and the Projections surface agree, rather than assuming it.
    "projection_source",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Read the MVP-1 raw projection
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_projection_local(artifacts_dir: Path, season: int,
                          source: str = DEFAULT_PROJECTION_SOURCE) -> pd.DataFrame:
    p = artifacts_dir / _PROJECTION_PARQUET[source].format(season=season)
    if not p.exists():
        script = ("run_nf1_5.py --mode build" if source == "nf1_5" else "run_season_projection.py")
        raise FileNotFoundError(
            f"{source} projection artifact not found: {p}. Run {script} first, "
            f"or use --from-lake to read the S3 Delta, or pass --projections-parquet."
        )
    # NF-C0e: the graduated captured terms are derived columns applied on the READ path, and EVERY
    # projection loader must route through the one function (`captured_terms.CONSUMER_CALLERS`) —
    # `two_pt` carries weight 2.0 in every preset, so a loader that skips it scores this board a
    # few points below the exporter's for the same player.
    return captured_terms.apply_to_projection(pd.read_parquet(p), artifacts_dir, season)


def load_kdst_local(artifacts_dir: Path, season: int) -> pd.DataFrame:
    """NF1.6 — the K/DST BASE projection, from its own artifact lineage. LOCAL ONLY.

    Best-effort by design: a missing K/DST artifact must not cost the operator the offensive board,
    which is the draft-critical output. It logs loudly and the K/DST slots fall back to the
    pre-NF1.6 "declared but unprojected" behaviour rather than failing the run.

    ⚠️ CALLERS WANT `load_kdst`, NOT THIS. On its own this function is the NF-K1 defect: it is the
    ONE artifact the box's publish chain READS but never WRITES, and it is gitignored, so on the box
    "best-effort" meant "silently drop two positions from the published board". See `load_kdst`."""
    p = artifacts_dir / f"nfl_fantasy_kdst_projections_{season}.parquet"
    if not p.exists():
        log.warning("[ALERT] NF1.6 K/DST projection artifact NOT FOUND at %s — the board's K and DST "
                    "slots will render UNPROJECTED. Run run_kdst_projection.py to fill them.", p)
        return pd.DataFrame()
    return pd.read_parquet(p)


def load_kdst_lake(season: int) -> pd.DataFrame:
    """NF1.6 — the K/DST BASE projection from the S3 lake Delta (best-effort; see `load_kdst_local`)."""
    import duckdb

    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "kdst_projections", tier="fantasy/derived")
        con = _kdst_lake_connection()
        try:
            return con.sql(
                f"select * from delta_scan('{uri}') where projection_season = {season}").df()
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — advisory: never lose the offensive board over K/DST
        log.warning("[ALERT] NF1.6 K/DST lake read FAILED (%s) — the board's K and DST slots will "
                    "render UNPROJECTED", exc)
        return pd.DataFrame()


def load_kdst(artifacts_dir: Path, season: int, *, from_lake: bool = False) -> pd.DataFrame:
    """THE K/DST entry point every caller must use: LOCAL FIRST, then the LAKE.

    🔴 NF-K1 — THIS IS THE CURE FOR A LIVE REGRESSION, and the mechanism is worth stating exactly,
    because it is the THIRD instance of one class in this vertical (NF-INFRA1's two were
    `sports.duckdb` and `ncaaf_nfl_rookie_projections.parquet`).

    `nfl_fantasy_kdst_projections_<season>.parquet` is the ONLY artifact the box's board-publish
    chain READS but never WRITES:

        run_nf1_5 --mode build        → writes nf1_5_season_projections_<season>.parquet   ✅
        run_league_board              → writes the board CSVs                              ✅
        export_draft_board_json       → reads BOTH of the above, plus ↓
        nfl_fantasy_kdst_projections_<season>.parquet   ← written by NOTHING in the chain  ❌

    and `artifacts/.gitignore` ignores `*.parquet`, so it is ABSENT from the `COPY . .` image. On
    the laptop it is on disk and everything works; on the box `load_kdst_local` warned once and
    returned an empty frame, K and DST fell out of BOTH the boards and `projections.json`, and every
    step still exited 0. Measured: the operator's 2026-08-15 laptop publish shipped 868 players with
    42 K + 32 DST; the first automated `sports_nfl_board_publish_job` run (2026-08-16 07:15 PT,
    `generated_at` 14:22:15Z) shipped 795 players with ZERO of either.

    🔴 INC-45 — AND THE FALLBACK ITSELF THEN FAILED ON THE BOX, for a reason no reading of this
    function could show: it resolved credentials correctly and handed them to DuckDB through the
    deprecated `s3_*` settings, which `delta_scan` IGNORES (it authenticates through the Secret
    Manager). The read therefore ran on delta-kernel-rs's own ambient chain — which finds `~/.aws`
    on a laptop and did not work on the box — so this returned 0 rows every morning and the publish
    guard below refused to ship, freezing the board. Fixed by routing every lake read through
    `s3io.duckdb_lake_connection`; see `docs/inc45_box_kdst_lake_read.md`. ⚠️ The lake PARTITION was
    never the problem: it has held 74 rows since 2026-08-03.

    ⭐ THE FALLBACK IS TO THE LAKE, NOT TO A REBUILD. `run_kdst_projection --s3` already lands this
    projection at `nfl/fantasy/derived/kdst_projections/season=<season>/`, so the data the box needs
    is already there — it was only ever the local READ that was missing. Adding the model build to
    the daily publish chain would instead put a heavy preseason fit (and a new failure mode) on a
    cadence that has no need to refresh it: K/DST is a BASE preseason projection, not a daily one.

    LOCAL-FIRST is deliberate: a laptop build stays byte-identical to what it produced before this
    change, so this can only ever ADD a path that used to be an empty frame.

    ⛔ AN EMPTY RETURN IS STILL POSSIBLE and is still non-fatal here (a lake outage must not cost the
    operator the draft-critical offensive board). What makes that safe now is that it can no longer
    reach users silently: `export_draft_board_json.assert_published_position_coverage` REFUSES to
    publish a board missing a projectable position."""
    if from_lake:
        return load_kdst_lake(season)
    p = artifacts_dir / f"nfl_fantasy_kdst_projections_{season}.parquet"
    if p.is_file():
        return pd.read_parquet(p)
    log.warning("[ALERT] NF1.6 K/DST projection artifact NOT FOUND at %s (expected on the BOX — it "
                "is gitignored, so it is absent from the deployed image) — falling back to the S3 "
                "lake Delta. This is the NF-K1 path.", p)
    kdf = load_kdst_lake(season)
    if len(kdf):
        log.info("NF-K1: K/DST recovered from the lake — %d row(s)", len(kdf))
    else:
        log.warning("[ALERT] NF-K1: the K/DST lake fallback ALSO returned nothing for season %s. "
                    "K and DST will be UNPROJECTED, and the publish guard will refuse to ship "
                    "that board. Run run_kdst_projection.py --projection-season %s --s3.",
                    season, season)
    return kdf


def combine_projections(offense: pd.DataFrame, kdst: pd.DataFrame) -> pd.DataFrame:
    """Concat the offensive (MVP-1) and K/DST (NF1.6) projection lineages into ONE frame the engine
    scores with a single `SportProfile`.

    This works without any engine change because both lineages publish the SAME four contract
    columns (`proj_fp_ppr` + `fp_ppr_sd/_p10/_p90`) and the scorer reads every stat through
    `SportProfile.stat_columns`, treating an absent/NULL raw column as a zero term for THAT term
    only. So a kicker's missing passing line never zeroes his FG points, and a WR's missing
    points-allowed buckets never zero his receiving line."""
    frames = [f for f in (offense, kdst) if f is not None and len(f)]
    if not frames:
        raise ValueError("combine_projections: both projection lineages are empty")
    out = pd.concat(frames, ignore_index=True, sort=False)
    before = len(out)
    out = out.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    if len(out) < before:
        log.warning("combine_projections dropped %d duplicate player_id row(s) across the two "
                    "projection lineages — investigate the id spaces", before - len(out))
    return out


def _kdst_lake_connection():
    """🔴 INC-45 — one owner for "how a lake read authenticates". This used to set the deprecated
    `s3_*` settings, which `delta_scan` IGNORES: the read then depended on delta-kernel-rs's own
    ambient chain, which is why it worked on the laptop and returned nothing on the box. See
    `s3io.configure_duckdb_lake_auth`."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    return s3io.duckdb_lake_connection()


def load_projection_lake(season: int, source: str = DEFAULT_PROJECTION_SOURCE) -> pd.DataFrame:
    """Read the served season projection straight from the S3 lake Delta (the real-lake path)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri("nfl", _PROJECTION_LAKE_SOURCE[source], tier="fantasy/derived")
    con = _kdst_lake_connection()  # INC-45 — the secret channel `delta_scan` actually reads
    try:
        df = con.sql(
            f"select * from delta_scan('{uri}') where projection_season = {season}"
        ).df()
    finally:
        con.close()
    # NF-C0e — see `load_projection_local`. The rates artifact is local even on the lake path:
    # it is a handful of measured league constants, not projection data.
    return captured_terms.apply_to_projection(df, _DEFAULT_OUT, season)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Board assembly per config
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_for_config(proj: pd.DataFrame, config, season: int,
                     projection_source: str = DEFAULT_PROJECTION_SOURCE
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score + VOR the raw projection under one config. Returns (board, replacement_summary)."""
    scored = score_players(proj, config, NFL_PROFILE)
    board = build_board(scored, config, NFL_PROFILE)
    repl, started = compute_replacement_levels(scored, config, NFL_PROFILE)
    repl_tbl = replacement_summary(config, NFL_PROFILE, repl, started)

    board["config_name"] = config.name
    board["season"] = int(season)
    board["n_teams"] = config.n_teams
    board["ppr"] = config.ppr
    board["superflex"] = config.superflex
    board["engine_version"] = ENGINE_VERSION
    board["projection_source"] = projection_source
    board["generated_at"] = datetime.now(timezone.utc).isoformat()
    # rename the carried point-interval columns to the emitted names
    board = board.rename(columns={
        "league_points_p10": "league_points_p10", "league_points_p90": "league_points_p90",
    })
    for c in BOARD_COLS:
        if c not in board.columns:
            board[c] = np.nan
    board = board[BOARD_COLS].sort_values("overall_rank").reset_index(drop=True)
    return board, repl_tbl


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report — the edge-independent gate (scoring correctness + face-valid preset deltas)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".1f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def _qb_rank_of_best(board: pd.DataFrame) -> tuple[str, int]:
    qb = board[board["position"] == "QB"].nsmallest(1, "overall_rank")
    if qb.empty:
        return ("—", -1)
    return (str(qb["player_name"].iloc[0]), int(qb["overall_rank"].iloc[0]))


def _size_effect_table(boards_all: dict, fmt: str, sizes: list[int]) -> pd.DataFrame:
    """For ONE format across league sizes: how positional replacement + QB scarcity + the count of
    positive-VOR (draftable-with-value) players move with league size. The auditable proof that size
    is a real dimension of value, not a label — fewer teams ⇒ shallower demand ⇒ higher replacement bar."""
    rows = []
    for size in sizes:
        b = boards_all.get((fmt, size))
        if b is None:
            continue
        repl = b.groupby("position")["replacement_points"].max()
        _, qb_rank = _qb_rank_of_best(b)
        rows.append({
            "format": fmt, "n_teams": size,
            "QB_repl": round(float(repl.get("QB", 0.0)), 1),
            "RB_repl": round(float(repl.get("RB", 0.0)), 1),
            "WR_repl": round(float(repl.get("WR", 0.0)), 1),
            "TE_repl": round(float(repl.get("TE", 0.0)), 1),
            "best_QB_rank": qb_rank,
            "players_positive_VOR": int((b["vor"] > 0).sum()),
        })
    return pd.DataFrame(rows)


def write_report(boards: dict, repl_tables: dict, season: int, path: Path, *,
                 reference_n_teams: int = 12, size_effect: pd.DataFrame | None = None,
                 size_fmt: str = "full_ppr") -> None:
    a = []
    p = a.append
    p(f"# NF-C1-lite — {season} NFL league-config scoring + VOR boards (MVP-2)")
    p("")
    p(f"**Engine:** `{ENGINE_VERSION}` (sport-agnostic `fantasy_engine`) · **projection season:** {season} "
      f"· **generated:** {datetime.now(timezone.utc).isoformat()}")
    p("")
    p(f"> 🧮 **Sections 1–3 below are shown at the {reference_n_teams}-team reference size** (the modal "
      f"redraft size); the boards are landed for every scored size — see §4 for the league-size effect. "
      f"The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not "
      f"part of the format name.")
    p("")
    p("> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is "
      "(1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT "
      "replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset "
      "deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat "
      "line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the "
      "rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie "
      "intervals remain PARAMETER uncertainty and must be recalibrated before pricing.")
    p("")

    # ── face-validity: how the best QB's overall rank moves across presets (the superflex proof) ──
    p("## 1. Face validity — the preset deltas that prove the scarcity math")
    p("")
    rows = []
    for name in ("standard", "half_ppr", "full_ppr", "superflex"):
        if name not in boards:
            continue
        b = boards[name]
        qb_name, qb_rank = _qb_rank_of_best(b)
        # count pass-catchers (WR/TE) in the top 10
        top10 = b.head(10)
        pass_catchers_top10 = int(top10["position"].isin(("WR", "TE")).sum())
        rbs_top10 = int((top10["position"] == "RB").sum())
        rows.append({
            "preset": name,
            "best_QB": qb_name,
            "best_QB_overall_rank": qb_rank,
            "WR+TE_in_top10": pass_catchers_top10,
            "RB_in_top10": rbs_top10,
        })
    p(_md(pd.DataFrame(rows)))
    p("")
    p("- ✅ **Superflex lifts QBs:** the best QB's overall rank should jump sharply from full-PPR to "
      "superflex (a QB-eligible SUPERFLEX slot roughly doubles QB starter demand → QB replacement drops "
      "→ QB VOR rises). This is the direct check the flex-allocation math is right.")
    p("- ✅ **PPR lifts pass-catchers:** WR/TE representation in the top 10 should rise from standard → "
      "half → full PPR as receptions gain value.")
    p("")

    # ── the transparent replacement-level definition per preset ──
    p("## 2. Positional scarcity — the replacement-level definition (auditable)")
    p("")
    p("Replacement level per position = the points of the FIRST non-startable player (the best player "
      "available for free). DEMAND = dedicated starter spots + the position's allocated share of the "
      "FLEX/SUPERFLEX pool (allocated greedily, most-restrictive slot first). VOR = league points − this "
      "replacement level.")
    p("")
    for name in ("standard", "full_ppr", "superflex"):
        if name not in repl_tables:
            continue
        p(f"### {name}")
        p("")
        p(_md(repl_tables[name]))
        p("")

    # ── the boards themselves ──
    p("## 3. Ranked boards — top 20 by VOR")
    p("")
    show = ["overall_rank", "player_name", "position", "positional_rank", "proj_games",
            "league_points", "replacement_points", "vor", "vor_p10", "vor_p90"]
    for name in ("standard", "full_ppr", "superflex"):
        if name not in boards:
            continue
        p(f"### {name}")
        p("")
        p(_md(boards[name].head(20)[show]))
        p("")

    if size_effect is not None and not size_effect.empty and len(size_effect) > 1:
        p("## 4. League-size effect — size is a real dimension of value, not a label")
        p("")
        p(f"For **{size_fmt}** across the scored league sizes: replacement level per position + the best "
          f"QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower "
          f"starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the "
          f"board grain includes `n_teams` — each size is a genuinely different value board off the same "
          f"MVP-1 projections.")
        p("")
        p(_md(size_effect))
        p("")

    p("## 5. Limitations")
    p("")
    p("- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it "
      "rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 "
      "closes it upstream.")
    p("- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK "
      "instead of rendering \"not projected\", scored off raw components (distance-bucketed FG; DST "
      "takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). "
      "⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 "
      "for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not "
      "fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE "
      "(FB folded into RB) + K/DST.")
    p("- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). "
      "Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.")
    p("- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the "
      "config schema is the shared contract.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-C1-lite — per-league scored + VOR boards from MVP-1")
    ap.add_argument("--projection-season", type=int, default=2026)
    ap.add_argument(
        "--presets", nargs="*",
        default=["standard", "half_ppr", "full_ppr", "superflex",
                 "standard_3wr", "half_ppr_3wr", "full_ppr_3wr"],
        help=f"presets to score. Available: {sorted(PRESETS)}. ⚠️ the S3 write is a replaceWhere by "
             f"season — a run OVERWRITES the whole season partition, so pass the FULL set you want "
             f"persisted (the default = the 4 gate presets + the 3-WR roster variants).")
    ap.add_argument("--n-teams", type=int, nargs="+", default=[12, 10],
                    help="league size(s) to score. Size is a normalized dimension of the board grain "
                         "(config_name, n_teams, player_id) — VOR replacement scales with it, so each "
                         "size is a genuinely different value board. Default: 12 and 10.")
    ap.add_argument("--projection-source", choices=PROJECTION_SOURCES,
                    default=DEFAULT_PROJECTION_SOURCE,
                    help="WHICH season projection to score. Default 'nf1_5' = the market-aware "
                         "refined board (the NF1.5b re-land); 'mvp1' = the market-blind MVP-1 board. "
                         "Stamped onto every board row as `projection_source` so the JSON export can "
                         "prove the draft board and the Projections surface came from the same one.")
    ap.add_argument("--from-lake", action="store_true",
                    help="read the season projection from the S3 lake Delta instead of a local artifact")
    ap.add_argument("--projections-parquet", default=None,
                    help="explicit path to a projection parquet (overrides the default artifact). "
                         "⚠️ still stamped with --projection-source — name them consistently.")
    ap.add_argument("--no-kdst", action="store_true",
                    help="NF1.6 escape hatch: build the board WITHOUT the K/DST base projection (the "
                         "pre-NF1.6 behaviour, where those slots render unprojected). Diagnostic only.")
    ap.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    ap.add_argument("--s3", action="store_true", help="also land the boards to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")

    season = args.projection_season
    out_dir = Path(args.out_dir)
    (out_dir / "league_boards").mkdir(parents=True, exist_ok=True)
    (out_dir / "league_configs").mkdir(parents=True, exist_ok=True)

    if args.projections_parquet:
        proj = pd.read_parquet(args.projections_parquet)
        proj = proj[pd.to_numeric(proj.get("projection_season"), errors="coerce") == season] \
            if "projection_season" in proj.columns else proj
    elif args.from_lake:
        proj = load_projection_lake(season, args.projection_source)
    else:
        proj = load_projection_local(out_dir, season, args.projection_source)

    # ⭐ NF1.6 — fold in the K/DST BASE projection so those roster slots RANK instead of rendering
    #    "not projected". Best-effort: a missing K/DST lineage logs loudly and leaves the offensive
    #    board (the draft-critical output) untouched.
    if not args.no_kdst:
        # NF-K1 — `load_kdst`, never `load_kdst_local`: on the box the local artifact is absent
        # (gitignored, and nothing in the publish chain writes it), and the local-only read silently
        # dropped both positions from every published board. See `load_kdst`.
        kdst = load_kdst(out_dir, season, from_lake=args.from_lake)
        if len(kdst):
            proj = combine_projections(proj, kdst)
            log.info("NF1.6: folded in %d K/DST rows (%s)", len(kdst),
                     ", ".join(f"{k}={v}" for k, v in
                               sorted(kdst.groupby("position").size().items())))
    if proj.empty:
        ap.error(f"no {args.projection_source} projection rows for season {season}")
    log.info("loaded %d %s projection rows for season %d (model_version %s)", len(proj),
             args.projection_source, season,
             (proj["model_version"].dropna().iloc[0] if "model_version" in proj.columns
              and proj["model_version"].notna().any() else "—"))

    sizes = sorted(set(args.n_teams), reverse=True)
    ref_size = 12 if 12 in sizes else sizes[0]  # the size the report's main tables use

    boards_all: dict[tuple[str, int], pd.DataFrame] = {}   # (preset, size) -> board (for the write)
    ref_boards: dict[str, pd.DataFrame] = {}               # preset -> board at ref_size (report)
    ref_repl: dict[str, pd.DataFrame] = {}
    for size in sizes:
        for name in args.presets:
            cfg = get_preset(name, size)
            board, repl_tbl = board_for_config(proj, cfg, season, args.projection_source)
            boards_all[(name, size)] = board
            # persist the config object (the shared contract NF-C0 populates) + a readable CSV, per size
            (out_dir / "league_configs" / f"{name}_{size}team.json").write_text(
                json.dumps(cfg.to_dict(), indent=2))
            board.to_csv(
                out_dir / "league_boards" / f"nfl_league_board_{name}_{size}team_{season}.csv", index=False)
            if size == ref_size:
                ref_boards[name] = board
                ref_repl[name] = repl_tbl
            log.info("  %s (%d-team): %d players ranked (best QB overall rank %d)",
                     name, size, len(board), _qb_rank_of_best(board)[1])

    # league-size effect: for a representative format, how replacement + QB scarcity move with size
    size_fmt = next((f for f in ("full_ppr", "half_ppr", "standard") if f in args.presets), args.presets[0])
    size_effect = _size_effect_table(boards_all, size_fmt, sizes)

    # land EVERY (preset × size) board for the season as one Delta partition (replaceWhere by season —
    # a single combined write, so re-running never drops a preset/size already landed).
    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io
        combined = pd.concat(boards_all.values(), ignore_index=True)
        n = s3io.write_dataframe(
            combined, sport="nfl", source="league_boards", season=int(season),
            tier="fantasy/derived", local_root=args.lake_root)
        log.info("landed %d board rows (%d presets × %d sizes) → nfl/fantasy/derived/league_boards season=%d",
                 n, len(args.presets), len(sizes), season)

    if not args.no_report:
        write_report(ref_boards, ref_repl, season, _REPORT_PATH,
                     reference_n_teams=ref_size, size_effect=size_effect, size_fmt=size_fmt)

    log.info("done. presets: %s | sizes: %s", ", ".join(args.presets), sizes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
