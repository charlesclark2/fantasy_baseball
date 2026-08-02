"""benchmark_scorecard.py — NF-D3: the STANDING us-vs-consensus scorecard (the GTM proof asset).

Turns the one-off "FF 2025 file" comparison into a REPRODUCIBLE, season-over-season, multi-system
scorecard: grade OUR shipped projection against every obtainable public/competitor system on the SAME
player universe, the SAME realized-outcome truth, and the SAME ordering metric — apples-to-apples.

⭐ THE HONESTY BAR IS THE WHOLE POINT (a public "we beat X" claim backfires if it is cherry-picked):
  • APPLES-TO-APPLES — every system is scored on the SHARED universe of players it AND our model both
    cover, with ≥6 realized games; and on the strict all-systems intersection for a head-to-head. We
    never compare our full-pool ρ to their top-N ρ. Format is held fixed (PPR) across systems.
  • NO HINDSIGHT / NO LEAKAGE — our projection for season Y is built from ≤Y−1 data only
    (`project_veterans(base=Y−1 → Y)`); ADP/ECR are the FROZEN PRESEASON snapshots. So every season is
    a genuine holdout. The FF file must likewise be a PRESEASON ranking/projection (the operator
    supplies preseason files only).
  • ORDERING METRICS — within-position Spearman ρ (what wins drafts) + rank-MAE (rank-space, so a
    RANKING system like ADP/ECR/FF grades the same way our POINT projection does). Points-MAE is
    reported for point systems only (ours), never demanded of a ranking system.
  • NULL, DON'T FABRICATE — a system with no data for a season is simply absent from that season's row.

SYSTEMS — two kinds, one scorer:
  • API systems (auto-fetched, reproducible): `adp` (Fantasy Football Calculator) and `ecr`
    (FantasyPros). Both are RANKINGS → scored as `-rank`.
  • FILE systems (operator-supplied, e.g. Fantasy Footballers / PFF / ESPN — paid, no public API):
    drop a CSV named `<system>_<season>.csv` into `artifacts/benchmarks_manual/`. The loader
    auto-detects a name, position, and EITHER a rank OR a projected-points column, crosswalks to gsis
    via the shared `adp_source` crosswalk, and scores it identically. See `FILE_BENCHMARK_README`.

Entry point: `build_scorecard(con, seasons, schema)` → the per-(system, season) metrics + aggregates.
The CLI `run_benchmark_scorecard.py` renders the report and (optionally) lands a scorecard asset.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A
from quant_sports_intel_models.football.nfl.fantasy import espn_source as E
from quant_sports_intel_models.football.nfl.fantasy import fantasypros_source as F
from quant_sports_intel_models.football.nfl.fantasy import mfl_adp_source as MFL
from quant_sports_intel_models.football.nfl.fantasy import sleeper_source as S

log = logging.getLogger("nfl.fantasy.scorecard")

_POSITIONS = ("QB", "RB", "WR", "TE")
_MANUAL_DIR = Path(__file__).resolve().parent / "artifacts" / "benchmarks_manual"

# Column-name candidates for the flexible file-benchmark loader (case/space-insensitive match).
_NAME_COLS = ("player_name", "player", "name", "fullname", "full_name")
_POS_COLS = ("position", "pos", "player_position", "fantasy_position")
_RANK_COLS = ("rank", "overall_rank", "overall", "ecr", "consensus_rank", "adp", "ovr_rank")
_POINTS_COLS = ("proj_fp_ppr", "points", "projection", "fpts", "proj_points", "fantasy_points",
                "ppr", "ppr_points", "proj", "projected_fantasy_points")

# ESPN's raw fantasy-export `position` STRING column is shifted relative to its own `position_id`
# (verified 2026-08-01 against known players in a real ESPN export: position_id=1 held Mahomes/Allen
# labeled "TQB", 2 held McCaffrey/Barkley labeled "RB", 3 held Jefferson labeled "RB_WR", 4 held Kelce
# labeled "WR", 5 held Tucker labeled "WR_TE"). `position_id` itself is the standard, UNSHIFTED ESPN
# slot id — derive true position from it whenever a file carries this column, rather than trusting the
# string label.
_ESPN_POSITION_ID_MAP = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

FILE_BENCHMARK_README = """\
FILE-BENCHMARK DROP-IN (Fantasy Footballers / PFF / ESPN / 4for4 / any competitor)
----------------------------------------------------------------------------------
Put a CSV here:  artifacts/benchmarks_manual/<system>_<season>.csv
  <system>  a short slug, e.g. fantasy_footballers, pff, espn, 4for4  (underscores ok)
  <season>  the 4-digit projection season the file is FOR, e.g. 2025

The CSV needs (header names are matched case/space-insensitively; extra columns are ignored):
  • a NAME column     — one of: player_name | player | name
  • a POSITION column — one of: position | pos           (QB/RB/WR/TE; K/DST are dropped)
  • ONE ordering column, EITHER:
      – a RANK column   — one of: rank | overall_rank | ecr | consensus_rank   (lower = better), OR
      – a POINTS column — one of: proj_fp_ppr | points | projection | fpts     (higher = better)
    (if both are present, POINTS is used.)

⚠️ LEAKAGE: the file MUST be that system's PRESEASON ranking/projection for <season> (frozen before
Week 1). A file scored against a season it was published DURING/AFTER is hindsight and is disqualified
— the scorecard cannot verify this, so it is on the supplier to provide preseason files only.
"""


# ══════════════════════════════════════════════════════════════════════════════════════════════
# File-benchmark loader (operator-supplied competitor files: Fantasy Footballers, PFF, ESPN, …)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _find_col(cols, candidates):
    norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in cols}
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]", "", cand.lower())
        if key in norm:
            return norm[key]
    return None


def discover_file_benchmarks(manual_dir: str | Path | None = None) -> list[dict]:
    """Enumerate operator-supplied `<system>_<season>.csv` files under `benchmarks_manual/`.
    Returns [{system, season, path}], sorted. Silent (empty list) when the dir is absent — file
    benchmarks are optional; the API systems always run."""
    d = Path(manual_dir or _MANUAL_DIR)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.csv")):
        m = re.match(r"^(?P<system>.+)_(?P<season>\d{4})$", p.stem)
        if not m:
            log.warning("benchmarks_manual: '%s' does not match <system>_<season>.csv — skipping", p.name)
            continue
        out.append({"system": m.group("system"), "season": int(m.group("season")), "path": p})
    return out


def load_file_benchmark(con, path: str | Path, season: int, schema: str = "main_nfl_marts") -> pd.DataFrame:
    """Read an operator-supplied competitor CSV → a scored benchmark frame with `player_id, position,
    score` (score higher = better). Auto-detects the name/position/rank-or-points columns, crosswalks
    to gsis via the shared `adp_source` crosswalk. Raises a clear error if a required column is absent
    (so a malformed drop-in fails loudly, never silently produces a wrong scorecard)."""
    df = pd.read_csv(path)
    # ESPN's raw export can carry TWO rows per player under one `stat_split_type_id` column — a
    # season-total projection (0) AND a per-game-average projection (2). Left alone, both feed the
    # same `score` column: the merge fans out per player (one "system" row becomes two), and a
    # season-total (~100-180) sits next to a per-game average (~5-9) in the same ranking — corrupting
    # both the ordering metric and the system's own accuracy read. Keep the season-total row only,
    # matching the season-total scale of `real_fp_ppr`/`proj_fp_ppr`.
    split_c = _find_col(df.columns, ("stat_split_type_id",))
    if split_c is not None and df[split_c].nunique() > 1 and (df[split_c] == 0).any():
        before = len(df)
        df = df[df[split_c] == 0].copy()
        log.info("  %s: multiple stat_split_type_id values — kept season-total (0): %d -> %d rows",
                 Path(path).name, before, len(df))
    name_c = _find_col(df.columns, _NAME_COLS)
    pos_c = _find_col(df.columns, _POS_COLS)
    if name_c is None or pos_c is None:
        raise ValueError(f"{Path(path).name}: need a name column {_NAME_COLS} and a position column "
                         f"{_POS_COLS}; found {list(df.columns)}")
    pts_c = _find_col(df.columns, _POINTS_COLS)
    rank_c = _find_col(df.columns, _RANK_COLS)
    if pts_c is None and rank_c is None:
        raise ValueError(f"{Path(path).name}: need a points column {_POINTS_COLS} OR a rank column "
                         f"{_RANK_COLS}; found {list(df.columns)}")

    position = df[pos_c].astype(str).str.upper().str.strip()
    posid_c = _find_col(df.columns, ("position_id",))
    if posid_c is not None:
        posid = pd.to_numeric(df[posid_c], errors="coerce")
        mapped = posid.map(_ESPN_POSITION_ID_MAP)
        n_remapped = int((mapped.notna() & (mapped != position)).sum())
        if n_remapped:
            log.info("  %s: position_id present — remapped %d row(s) off the shifted `position` "
                     "string (e.g. TQB->QB, RB_WR->WR, WR->TE)", Path(path).name, n_remapped)
            position = mapped.fillna(position)

    norm = pd.DataFrame({
        "player_name": df[name_c].astype(str),
        "position": position,
    })
    if pts_c is not None:
        norm["score"] = pd.to_numeric(df[pts_c], errors="coerce")
        kind = f"points[{pts_c}]"
    else:
        norm["score"] = -pd.to_numeric(df[rank_c], errors="coerce")
        kind = f"rank[{rank_c}]"
    norm = norm.dropna(subset=["score"])
    xw = A.attach_gsis(con, norm, season, schema=schema)
    xw = xw[xw["player_id"].notna()][["player_id", "position", "score"]].copy()
    xw["player_id"] = xw["player_id"].astype(str)
    dup_ct = int(xw["player_id"].duplicated().sum())
    if dup_ct:
        # A duplicate player_id here fans out the downstream merge (one system row becomes N) —
        # never let that happen silently. Keep the highest score per player (higher-is-better,
        # already normalized above) and say so loudly.
        log.warning("  %s: %d duplicate player_id row(s) post-crosswalk — keeping the highest score "
                    "per player", Path(path).name, dup_ct)
        xw = xw.sort_values("score", ascending=False).drop_duplicates("player_id", keep="first")
    log.info("  file benchmark %s (%s): %d rows, %d gsis-matched", Path(path).name, kind,
             len(norm), len(xw))
    return xw


# ══════════════════════════════════════════════════════════════════════════════════════════════
# System registry — every benchmark returns (player_id, position, score) where score higher = better
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _adp_system(con, season, schema):
    adp = A.load_adp_for_season(con, season, schema=schema)
    adp = adp[adp["player_id"].notna()].copy()
    if adp.empty:
        return adp.reindex(columns=["player_id", "position", "score"])
    adp["player_id"] = adp["player_id"].astype(str)
    adp["score"] = -pd.to_numeric(adp["adp"], errors="coerce")
    return adp[["player_id", "position", "score"]].dropna(subset=["score"])


def _ecr_system(con, season, schema):
    ecr = F.load_ecr_for_season(con, season, schema=schema)
    ecr = ecr[ecr["player_id"].notna()].copy()
    if ecr.empty:
        return ecr.reindex(columns=["player_id", "position", "score"])
    ecr["player_id"] = ecr["player_id"].astype(str)
    ecr["score"] = -pd.to_numeric(ecr["rank_ecr"], errors="coerce")
    return ecr[["player_id", "position", "score"]].dropna(subset=["score"])


def _sleeper_system(con, season, schema):
    df = S.load_sleeper_for_season(con, season, schema=schema)
    df = df[df["player_id"].notna()].copy()
    if df.empty:
        return df.reindex(columns=["player_id", "position", "score"])
    df["player_id"] = df["player_id"].astype(str)
    df["score"] = pd.to_numeric(df["proj_pts_ppr"], errors="coerce")   # a POINT projection (higher=better)
    return df[["player_id", "position", "score"]].dropna(subset=["score"])


def _espn_system(con, season, schema):
    df = E.load_espn_for_season(con, season, schema=schema)
    df = df[df["player_id"].notna()].copy()
    if df.empty:
        return df.reindex(columns=["player_id", "position", "score"])
    df["player_id"] = df["player_id"].astype(str)
    df["score"] = -pd.to_numeric(df["ppr_draft_rank"], errors="coerce")   # a RANK (lower=better)
    return df[["player_id", "position", "score"]].dropna(subset=["score"])


def _mfl_adp_system(con, season, schema):
    """NF3.2: MyFantasyLeague as a SECOND, INDEPENDENT real-draft ADP source — registered so the
    scorecard's "we beat ADP" claim is cross-validated against a crowd separate from FFC's, not just
    reproduced on the same one. Confirmed genuinely year-scoped (unlike FantasyPros' live-only ADP
    page) and covers all 7 backtest seasons, incl. 2025 where FFC itself has no archive at all."""
    mfl = MFL.load_adp_for_season(con, season, schema=schema)
    mfl = mfl[mfl["player_id"].notna()].copy()
    if mfl.empty:
        return mfl.reindex(columns=["player_id", "position", "score"])
    mfl["player_id"] = mfl["player_id"].astype(str)
    mfl["score"] = -pd.to_numeric(mfl["adp"], errors="coerce")
    return mfl[["player_id", "position", "score"]].dropna(subset=["score"])


# API systems always attempted; file systems discovered at runtime and appended. Each is scored the
# same way — see the per-system leakage basis documented in `benchmark_scorecard.py` header / the
# report: adp (FFC, dated week-before-Week-1), ecr (FantasyPros, dated early-Sept snapshot) and sleeper
# (Rotowire, verified frozen-preseason by the gp=17 test) are leakage-safe; espn (draft rank) is a
# preseason artifact but its as-of date is unstamped → lower-verified.
API_SYSTEMS = {
    "adp": _adp_system, "ecr": _ecr_system, "sleeper": _sleeper_system, "espn": _espn_system,
    "mfl_adp": _mfl_adp_system,
}


def load_systems(con, season, schema, manual_dir=None) -> dict[str, pd.DataFrame]:
    """All benchmark systems that have data for `season`, as {name: frame(player_id, position,
    score)}. API systems (adp/ecr) + any operator file benchmarks for that season."""
    out = {}
    for name, fn in API_SYSTEMS.items():
        try:
            f = fn(con, season, schema)
        except Exception as e:  # noqa: BLE001 — a fetch failure NULLs that system, never the run
            log.warning("  system '%s' season %d failed: %s", name, season, e)
            continue
        if f is not None and not f.empty:
            out[name] = f
    for fb in discover_file_benchmarks(manual_dir):
        if fb["season"] != season:
            continue
        try:
            f = load_file_benchmark(con, fb["path"], season, schema)
        except Exception as e:  # noqa: BLE001
            log.warning("  file benchmark '%s' failed: %s", fb["path"].name, e)
            continue
        if not f.empty:
            out[fb["system"]] = f
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Apples-to-apples metrics
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 10 or a.std() == 0 or b.std() == 0:
        return None
    return float(pd.Series(a.to_numpy()).corr(pd.Series(b.to_numpy()), method="spearman"))


def _within_position_rho(d: pd.DataFrame, score_col: str) -> tuple[dict, float | None]:
    """Per-position Spearman(score, realized) + the position-pooled mean. `d` has position,
    `score_col`, real_fp_ppr."""
    per = {}
    for p in _POSITIONS:
        s = d[d["position"] == p]
        v = _spearman(s[score_col], s["real_fp_ppr"])
        if v is not None:
            per[p] = round(v, 3)
    pooled = round(float(np.mean(list(per.values()))), 3) if per else None
    return per, pooled


def _rank_mae(d: pd.DataFrame, score_col: str) -> float | None:
    """Mean absolute WITHIN-POSITION rank error vs the realized within-position rank. Rank-space, so a
    ranking system and a point projection grade identically. Lower = better."""
    errs = []
    for p in _POSITIONS:
        s = d[d["position"] == p]
        if len(s) < 5:
            continue
        r_sys = s[score_col].rank(ascending=False, method="average")
        r_real = s["real_fp_ppr"].rank(ascending=False, method="average")
        errs.append((r_sys - r_real).abs())
    if not errs:
        return None
    return round(float(pd.concat(errs).mean()), 2)


def _topn_hit(d: pd.DataFrame, score_col: str, n: int = 24) -> str | None:
    if len(d) < n:
        return None
    top_sys = set(d.nlargest(n, score_col)["player_id"])
    top_real = set(d.nlargest(n, "real_fp_ppr")["player_id"])
    return f"{len(top_sys & top_real)}/{n}"


def _score_pair(m: pd.DataFrame, us_col: str, sys_col: str) -> dict:
    """Grade OUR model vs a system on the SAME frame `m` (already the aligned universe). Returns both
    sides' within-pos ρ / rank-MAE / top-24 and the us−system deltas."""
    us_per, us_pool = _within_position_rho(m, us_col)
    sy_per, sy_pool = _within_position_rho(m, sys_col)
    us_mae, sy_mae = _rank_mae(m, us_col), _rank_mae(m, sys_col)
    delta_pos = {p: round(us_per[p] - sy_per[p], 3) for p in us_per if p in sy_per}
    return {
        "n_aligned": int(len(m)),
        "us": {"rho_by_pos": us_per, "rho_pooled": us_pool, "rank_mae": us_mae,
               "top24_hit": _topn_hit(m, us_col)},
        "system": {"rho_by_pos": sy_per, "rho_pooled": sy_pool, "rank_mae": sy_mae,
                   "top24_hit": _topn_hit(m, sys_col)},
        "delta_rho_by_pos": delta_pos,
        "delta_rho_pooled": (round(us_pool - sy_pool, 3)
                             if us_pool is not None and sy_pool is not None else None),
        "delta_rank_mae": (round(us_mae - sy_mae, 2)
                           if us_mae is not None and sy_mae is not None else None),
    }


def _disagreement_frame(m: pd.DataFrame, us_col: str, sys_col: str, q: float = 0.75) -> pd.DataFrame:
    """Row-level basis for `_disagreement()`: z-score `us_col`/`sys_col` WITHIN POSITION (position needs
    >=12 aligned rows to enter at all), then flag the top-quartile |z_us − z_sys| across the POOLED
    (all-position) distribution as `is_fade`. Extracted so a per-player export (NF3.2) can carry the
    IDENTICAL fade flag the aggregate scorecard reports, never a re-derived one — `_disagreement()` below
    is now a thin aggregate over this same frame. Returns all of `m`'s columns plus `z_us`, `z_sys`,
    `_dis`, `is_fade`; empty (with those columns) if no position has >=12 rows."""
    pool = []
    for p in _POSITIONS:
        d = m[m["position"] == p]
        if len(d) < 12:
            continue
        zf, zs = _zscore(d[us_col].to_numpy()), _zscore(d[sys_col].to_numpy())
        pool.append(d.assign(z_us=zf, z_sys=zs, _dis=np.abs(zf - zs)))
    if not pool:
        return m.iloc[0:0].assign(z_us=pd.Series(dtype="float64"), z_sys=pd.Series(dtype="float64"),
                                   _dis=pd.Series(dtype="float64"), is_fade=pd.Series(dtype="bool"))
    allp = pd.concat(pool, ignore_index=True)
    return allp.assign(is_fade=allp["_dis"] >= allp["_dis"].quantile(q))


def _disagreement(m: pd.DataFrame, us_col: str, sys_col: str, q: float = 0.75) -> dict:
    """Where OUR model most disagrees with the system (top-quartile |z_us − z_sys| within position),
    who predicts the realized finish better? The edge of a NON-MARKET product lives in the fades.

    ⭐ NF-D13 AUDIT (2026-08-01) — checked this scorer against E7.11's baseball-side finding that a
    source can't "disagree" with a consensus it alone constitutes (aggregate-vs-member, defect #4;
    1-source rows + mismatched percentile denominators produced a lopsided false flag split there).
    CLEAN here: `build_scorecard` never builds an N-source consensus — every system is graded
    against us independently (one system per `m`, always both sides present via inner join), and
    `zf`/`zs` below are z-scored over the IDENTICAL population `d` for both sides, so a
    mismatched-denominator split cannot occur. If a future change ever folds multiple competitor
    systems into one blended "consensus" entrant, re-apply the E7.11 discipline (n_sources≥2,
    exclude-self, shared residual — see `betting_ml/scripts/prospect_board/consensus.py`) before
    wiring it in here. Pinned by
    `test_scorecard_systems_score_independently_of_each_other` in
    `betting_ml/tests/test_nfl_fantasy_projection.py`."""
    allp = _disagreement_frame(m, us_col, sys_col, q)
    hi = allp[allp["is_fade"]]
    if len(hi) < 10:
        return {}
    return {
        "n_high_disagreement": int(len(hi)),
        "us": round(float(hi[us_col].corr(hi["real_fp_ppr"], method="spearman")), 3),
        "system": round(float(hi[sys_col].corr(hi["real_fp_ppr"], method="spearman")), 3),
    }


def _zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype="float64")
    sd = np.nanstd(x)
    if not np.isfinite(sd) or sd == 0:
        return np.zeros_like(x)
    return (x - np.nanmean(x)) / sd


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The scorecard
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_scorecard(con, seasons, schema, *, project_fn, load_realized_fn, manual_dir=None) -> dict:
    """Grade our shipped projection vs every available benchmark system, per season, apples-to-apples.

    `project_fn(con, season, schema) -> DataFrame[player_id, position, proj_fp_ppr]` builds the SHIPPED
    model for a season (base = season−1); `load_realized_fn(con, season, schema) -> [player_id, g,
    real_fp_ppr]` is the realized truth. (Injected so this module stays free of the heavy projection
    imports and is unit-testable.)

    Returns {"per_season": [...], "aggregate": {system: {...}}, "seasons_scored": [...]}.
    """
    per_season = []
    for y in seasons:
        systems = load_systems(con, y, schema, manual_dir=manual_dir)
        if not systems:
            log.info("  %d: no benchmark systems with data — skip", y)
            continue
        proj = project_fn(con, y, schema)
        proj = proj[proj["position"].isin(_POSITIONS)].copy()
        proj["player_id"] = proj["player_id"].astype(str)
        real = load_realized_fn(con, y, schema)
        real["player_id"] = real["player_id"].astype(str)
        base = proj.merge(real, on="player_id", how="inner", suffixes=("", "_r"))
        base = base[base["g"] >= 6].copy()  # players who actually played the target season
        # our position is authoritative; keep just what the scorer needs
        base = base[["player_id", "position", "proj_fp_ppr", "real_fp_ppr"]]
        if len(base) < 30:
            log.info("  %d: thin overlap (%d) — skip", y, len(base))
            continue

        row = {"season": y, "n_scored_universe": int(len(base)), "systems": {}}
        for name, sysf in systems.items():
            s = sysf.rename(columns={"score": "sys_score"})[["player_id", "sys_score"]]
            m = base.merge(s, on="player_id", how="inner")
            if len(m) < 20:
                row["systems"][name] = {"n_aligned": int(len(m)), "note": "thin aligned overlap"}
                continue
            scored = _score_pair(m, "proj_fp_ppr", "sys_score")
            scored["disagreement"] = _disagreement(m, "proj_fp_ppr", "sys_score")
            scored["coverage_pct"] = round(100.0 * len(m) / len(base), 1)
            row["systems"][name] = scored
        per_season.append(row)

    aggregate = _aggregate(per_season)
    return {"per_season": per_season, "aggregate": aggregate,
            "seasons_scored": [r["season"] for r in per_season]}


_TRACK_RECORD_COLS = ("season", "player_id", "player_name", "position", "our_points", "our_rank",
                      "adp", "adp_rank", "actual_points", "actual_rank", "is_fade", "adp_source")


def player_track_record_frame(con, season, schema, *, project_fn, load_realized_fn) -> pd.DataFrame:
    """NF3.2 — the per-PLAYER materialization behind `build_scorecard`'s aggregate "adp" numbers for one
    season: our projection vs that season's preseason ADP vs the realized outcome, one row per player.

    Reuses the IDENTICAL proj/realized join + g>=6 filter `build_scorecard` uses (see `base` there) and
    the identical `_disagreement_frame` fade flag (vs ADP specifically — the aggregate's ADP-vs-us
    comparison is the one NF1.5b's headline claim is about; ECR/ESPN/Sleeper still out-order us). A
    per-player row can therefore never disagree with the season's own aggregate scorecard number — this
    is deliberately NOT a parallel re-derivation of `_adp_system`'s merge.

    Returns columns: season, player_id, player_name, position, our_points, our_rank, adp, adp_rank,
    actual_points, actual_rank, is_fade, adp_source — one row per player with BOTH a shipped projection
    AND that season's ADP AND >=6 realized games (the same "aligned universe" `build_scorecard` scores).

    ⚠️ FFC has NO archive for some seasons (2025 confirmed live: `{"status":"Error"}` across every
    teams/format combination — a genuine, permanent gap, not a cache problem; see
    `adp_source.fetch_ffc_adp`'s docstring). When that happens this FALLS BACK to MyFantasyLeague
    (`mfl_adp_source.py`) — a second, independently-verified real-draft ADP source that DOES cover
    2025 — rather than blanking the season's ADP columns. `adp_source` on every row names which one
    actually backed it ("ffc" or "mfl"), so a consumer can label the season honestly instead of
    silently blending two different real-world draft populations under one undifferentiated "ADP".
    Only if BOTH sources are empty does this fall through to real our-vs-actual rows with `adp`/
    `adp_rank` null, `adp_source=None`, and `is_fade=False` (fade is an ADP-disagreement signal and
    cannot be computed without ANY ADP) — a season with a shipped board and a completed realized
    outcome always has SOMETHING honest to show, even when no external ADP benchmark is available."""
    proj = project_fn(con, season, schema)
    proj = proj[proj["position"].isin(_POSITIONS)].copy()
    proj["player_id"] = proj["player_id"].astype(str)
    real = load_realized_fn(con, season, schema)
    real["player_id"] = real["player_id"].astype(str)
    base = proj.merge(real, on="player_id", how="inner", suffixes=("", "_r"))
    base = base[base["g"] >= 6].copy()
    base = base[["player_id", "player_name", "position", "proj_fp_ppr", "real_fp_ppr"]]

    # Mirrors `_adp_system`'s exact filter/transform (notna -> str id -> score=-adp -> dropna score) so
    # this frame's ADP side is byte-identical to the aggregate's, while also keeping the raw `adp`
    # value for display (which `_adp_system` discards).
    adp = A.load_adp_for_season(con, season, schema=schema)
    adp = adp[adp["player_id"].notna()].copy()
    if not adp.empty:
        adp["player_id"] = adp["player_id"].astype(str)
        adp["sys_score"] = -pd.to_numeric(adp["adp"], errors="coerce")
        adp = adp.dropna(subset=["sys_score"])
    adp_source_used = "ffc"

    if adp.empty:
        mfl = MFL.load_adp_for_season(con, season, schema=schema)
        mfl = mfl[mfl["player_id"].notna()].copy()
        if not mfl.empty:
            mfl["player_id"] = mfl["player_id"].astype(str)
            mfl["sys_score"] = -pd.to_numeric(mfl["adp"], errors="coerce")
            mfl = mfl.dropna(subset=["sys_score"])
        adp = mfl
        adp_source_used = "mfl"

    if adp.empty:
        out = base.rename(columns={"proj_fp_ppr": "our_points", "real_fp_ppr": "actual_points"}).copy()
        if out.empty:
            return pd.DataFrame(columns=_TRACK_RECORD_COLS)
        out["our_rank"] = out.groupby("position")["our_points"].rank(ascending=False, method="min").astype(int)
        out["actual_rank"] = out.groupby("position")["actual_points"].rank(ascending=False, method="min").astype(int)
        out["adp"] = pd.NA
        out["adp_rank"] = pd.NA
        out["is_fade"] = False
        out["adp_source"] = None
        out["season"] = season
        return out[list(_TRACK_RECORD_COLS)].sort_values(["position", "our_rank"]).reset_index(drop=True)

    m = base.merge(adp[["player_id", "adp", "sys_score"]], on="player_id", how="inner")
    if m.empty:
        return pd.DataFrame(columns=_TRACK_RECORD_COLS)

    disagreement = _disagreement_frame(m, "proj_fp_ppr", "sys_score")
    fade_ids = set(disagreement.loc[disagreement["is_fade"], "player_id"]) if len(disagreement) else set()

    m = m.rename(columns={"proj_fp_ppr": "our_points", "real_fp_ppr": "actual_points"})
    m["our_rank"] = m.groupby("position")["our_points"].rank(ascending=False, method="min").astype(int)
    m["adp_rank"] = m.groupby("position")["adp"].rank(ascending=True, method="min").astype(int)
    m["actual_rank"] = m.groupby("position")["actual_points"].rank(ascending=False, method="min").astype(int)
    m["is_fade"] = m["player_id"].isin(fade_ids)
    m["adp_source"] = adp_source_used
    m["season"] = season
    return m[list(_TRACK_RECORD_COLS)].sort_values(["position", "our_rank"]).reset_index(drop=True)


def forward_comparison(con, season, schema, *, project_fn, manual_dir=None) -> dict:
    """FORWARD (no-realized) comparison for an INCOMPLETE season (e.g. the current draft year): how
    aligned is OUR board with each system, and where do we most DISAGREE? ⚠️ This is an AGREEMENT view,
    NOT an accuracy claim — there is no realized truth yet, so NO "we beat X" statement can be made
    here (that waits for `build_scorecard` once the season completes). It exists so an operator-supplied
    forward file (Fantasy Footballers 2026) is USABLE now — as draft content (our contrarian takes),
    not as a proof point.

    Returns {"season", "systems": {name: {agreement ρ by pos + overall, top disagreements}}}.
    """
    systems = load_systems(con, season, schema, manual_dir=manual_dir)
    proj = project_fn(con, season, schema)
    proj = proj[proj["position"].isin(_POSITIONS)].copy()
    proj["player_id"] = proj["player_id"].astype(str)
    # a display name if the projection carries one (for readable disagreement rows)
    name_col = "player_name" if "player_name" in proj.columns else None
    keep = ["player_id", "position", "proj_fp_ppr"] + ([name_col] if name_col else [])
    base = proj[keep].copy()
    out = {"season": season, "systems": {}}
    for name, sysf in systems.items():
        s = sysf.rename(columns={"score": "sys_score"})[["player_id", "sys_score"]]
        m = base.merge(s, on="player_id", how="inner")
        if len(m) < 20:
            continue
        per = {}
        for p in _POSITIONS:
            d = m[m["position"] == p]
            v = _spearman(d["proj_fp_ppr"], d["sys_score"])
            if v is not None:
                per[p] = round(v, 3)
        # biggest within-position disagreements = our most contrarian picks vs this system
        rows = []
        for p in _POSITIONS:
            d = m[m["position"] == p].copy()
            if len(d) < 8:
                continue
            d["z_us"] = _zscore(d["proj_fp_ppr"].to_numpy())
            d["z_sys"] = _zscore(d["sys_score"].to_numpy())
            d["gap"] = d["z_us"] - d["z_sys"]   # +gap = WE are higher on them than the system
            rows.append(d)
        disagreements = []
        if rows:
            allp = pd.concat(rows, ignore_index=True)
            for _, r in allp.reindex(allp["gap"].abs().sort_values(ascending=False).index).head(15).iterrows():
                disagreements.append({
                    "player": (r[name_col] if name_col else r["player_id"]),
                    "position": r["position"],
                    "direction": "we_higher" if r["gap"] > 0 else "we_lower",
                    "gap_z": round(float(r["gap"]), 2),
                })
        out["systems"][name] = {
            "n_aligned": int(len(m)),
            "agreement_rho_by_pos": per,
            "agreement_rho_pooled": round(float(np.mean(list(per.values()))), 3) if per else None,
            "top_disagreements": disagreements,
        }
    return out


def _aggregate(per_season: list[dict]) -> dict:
    """Average each system's us-vs-system deltas across the seasons it appears in (a durable claim
    holds across seasons, not one)."""
    agg: dict[str, dict] = {}
    names = {n for r in per_season for n in r["systems"]}
    for name in sorted(names):
        rows = [r["systems"][name] for r in per_season
                if name in r["systems"] and "delta_rho_pooled" in r["systems"][name]]
        if not rows:
            continue
        def _m(key):
            xs = [x[key] for x in rows if x.get(key) is not None]
            return round(float(np.mean(xs)), 3) if xs else None
        dis_us = [x["disagreement"]["us"] for x in rows if x.get("disagreement")]
        dis_sy = [x["disagreement"]["system"] for x in rows if x.get("disagreement")]
        agg[name] = {
            "n_seasons": len(rows),
            "us_rho_pooled": _m_over(rows, "us", "rho_pooled"),
            "system_rho_pooled": _m_over(rows, "system", "rho_pooled"),
            "delta_rho_pooled": _m("delta_rho_pooled"),
            "delta_rank_mae": _m("delta_rank_mae"),
            "disagreement_us": round(float(np.mean(dis_us)), 3) if dis_us else None,
            "disagreement_system": round(float(np.mean(dis_sy)), 3) if dis_sy else None,
            "delta_rho_by_pos": _agg_by_pos(rows),
        }
    return agg


def _m_over(rows, side, key):
    xs = [r[side][key] for r in rows if r.get(side, {}).get(key) is not None]
    return round(float(np.mean(xs)), 3) if xs else None


def _agg_by_pos(rows) -> dict:
    out = {}
    for p in _POSITIONS:
        xs = [r["delta_rho_by_pos"][p] for r in rows if p in r.get("delta_rho_by_pos", {})]
        if xs:
            out[p] = round(float(np.mean(xs)), 3)
    return out
