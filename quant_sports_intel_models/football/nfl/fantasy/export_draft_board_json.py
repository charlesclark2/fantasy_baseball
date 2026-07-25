"""export_draft_board_json.py — land the NF-C1 league boards as trimmed JSON for the live draft UI.

MVP-3's frontend draft optimizer is ALL-CLIENT-SIDE (instant recompute per pick, no server round-trip),
so it reads the boards as static JSON bundled in `frontend/public/data/nfl-fantasy/<season>/`:

  * `manifest.json`              — season meta + every league config's roster shape (drives roster-need
                                   detection client-side) + the (config, size) combos available.
  * `board_<config>_<size>.json` — the per-(config, n_teams) player board, trimmed to the columns the
                                   optimizer + UI need, names title-cased, FB folded into RB.

Reads the boards from the local artifacts CSVs by default (what `run_league_board.py` writes), or from
the S3 Delta with `--from-lake`. SF-free / off-box. This is the frontend analog of "land to S3 + a
readable output" — the board data the draft tool consumes.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy.league_presets import (  # noqa: E402
    NFL_PROFILE,
    PRESETS,
    get_preset,
)

log = logging.getLogger("nfl.fantasy.export_draft_board")

_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_BOARDS_DIR = _ARTIFACTS / "league_boards"
_FRONTEND_OUT = _PROJECT_ROOT / "frontend/public/data/nfl-fantasy"

# The projectable fantasy positions (MVP-1 = offensive skill only). K/DST carry no projection → the UI
# flags their roster slots as "draft late (no projection)"; they never appear on the board.
PROJECTABLE = ("QB", "RB", "WR", "TE")

# nflverse team abbreviations → the veteran-projection convention (the board's team_id style). Only a
# couple differ; the rest pass through. Kept broad so any nflverse-alt code maps cleanly.
_NFLVERSE_TEAM_FIX = {
    "AZ": "ARI", "LA": "LAR", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
    "SL": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV", "ARZ": "ARI", "WSH": "WAS",
}


def _norm_team(t: str | None) -> str | None:
    if not t:
        return None
    t = str(t).strip().upper()
    return _NFLVERSE_TEAM_FIX.get(t, t) or None


# Human labels for the shipped presets (the manifest's config picker).
CONFIG_LABELS = {
    "standard": "Standard (non-PPR)",
    "half_ppr": "Half-PPR",
    "full_ppr": "Full-PPR",
    "superflex": "Superflex (Full-PPR)",
    "standard_3wr": "Standard · 3-WR",
    "half_ppr_3wr": "Half-PPR · 3-WR",
    "full_ppr_3wr": "Full-PPR · 3-WR",
    "te_premium": "TE-Premium (Full-PPR)",
}


def _titlecase(name: str) -> str:
    """ALLCAPS board name → display case, with the common Mc/Mac fix (MCCAFFREY → McCaffrey)."""
    out = str(name).title()
    for pre in ("Mc", "Mac"):
        i = 0
        while (i := out.find(pre, i)) != -1:
            j = i + len(pre)
            if j < len(out) and out[j].isalpha():
                out = out[:j] + out[j].upper() + out[j + 1 :]
            i = j
    return out


def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def _fnum(v, nd: int = 1):
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return round(f, nd)
    except (TypeError, ValueError):
        return None


# ── read the boards ───────────────────────────────────────────────────────────────────────────────
def load_boards_local(season: int) -> pd.DataFrame:
    frames = []
    for p in sorted(_BOARDS_DIR.glob(f"nfl_league_board_*_{season}.csv")):
        frames.append(pd.read_csv(p))
    if not frames:
        raise FileNotFoundError(
            f"no board CSVs found in {_BOARDS_DIR} for season {season}. Run run_league_board.py first, "
            f"or use --from-lake."
        )
    return pd.concat(frames, ignore_index=True)


def _lake_connection():
    """A DuckDB connection wired for the S3 lakehouse (delta + httpfs + creds). SF-free / off-box."""
    import duckdb

    from quant_sports_intel_models.football.nfl.ingest import s3io

    con = duckdb.connect()
    con.execute("install delta; load delta; install httpfs; load httpfs;")
    opts = s3io.storage_options()
    con.execute(f"set s3_region='{opts.get('AWS_REGION', 'us-east-2')}';")
    if opts.get("AWS_ACCESS_KEY_ID"):
        con.execute(f"set s3_access_key_id='{opts['AWS_ACCESS_KEY_ID']}';")
        con.execute(f"set s3_secret_access_key='{opts['AWS_SECRET_ACCESS_KEY']}';")
        if opts.get("AWS_SESSION_TOKEN"):
            con.execute(f"set s3_session_token='{opts['AWS_SESSION_TOKEN']}';")
    return con


def load_boards_lake(season: int) -> pd.DataFrame:
    """Read all league boards for the season from the S3 Delta (the real-lake path)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri("nfl", "league_boards", tier="fantasy/derived")
    con = _lake_connection()
    try:
        return con.sql(f"select * from delta_scan('{uri}') where season = {season}").df()
    finally:
        con.close()


def rookie_team_map() -> dict[str, str]:
    """`{player_id -> current NFL team}` for the incoming rookie class, from `nflverse_players`.

    MVP-1's rookie leg (NCAAF-P1A) carries no NFL team (`team_id` is NULL), so a drafted rookie would
    otherwise show no team. We recover it from `nflverse_players.latest_team` (their post-draft team),
    joined on the P1A `gsis_id` (== the projection's rookie `player_id`), normalized to the board's team
    convention. Best-effort: on any lake-read failure we return {} and rookies simply stay teamless (the
    UI shows a rookie tag) rather than crashing the export. This is a stop-gap for the app — the durable
    fix is to carry the team through the projection itself once the 2026 draft-picks feed lands (NF-D1)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "nflverse_players")
        con = _lake_connection()
        try:
            df = con.sql(
                f"select gsis_id, any_value(latest_team) latest_team, any_value(draft_team) draft_team "
                f"from delta_scan('{uri}') group by gsis_id"
            ).df()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001 — best-effort enrichment, never fatal
        log.warning("rookie team enrichment skipped (nflverse_players read failed: %s)", e)
        return {}
    out: dict[str, str] = {}
    for _, r in df.iterrows():
        team = _norm_team(r.get("draft_team")) or _norm_team(r.get("latest_team"))
        if r.get("gsis_id") and team:
            out[str(r["gsis_id"])] = team
    log.info("rookie team map: %d players with a resolved team", len(out))
    return out


# ── build the JSON ────────────────────────────────────────────────────────────────────────────────
def board_records(df: pd.DataFrame, rookie_teams: dict[str, str] | None = None) -> list[dict]:
    """One board (already filtered to a config+size) → trimmed, display-ready player records, sorted by
    overall_rank. FB folds into RB; names title-cased; interval carried honestly. A rookie with no
    projection team is backfilled from `rookie_teams` (their drafted/current NFL team)."""
    rookie_teams = rookie_teams or {}
    recs = []
    for _, r in df.sort_values("overall_rank").iterrows():
        pos = NFL_PROFILE.normalize_position(str(r["position"]))
        if pos not in PROJECTABLE:
            continue
        is_rookie = _to_bool(r.get("is_rookie"))
        team = None if pd.isna(r.get("team_id")) else _norm_team(str(r["team_id"]))
        if not team and is_rookie:                     # MVP-1 rookies carry no team → backfill it
            team = rookie_teams.get(str(r["player_id"]))
        recs.append({
            "id": str(r["player_id"]),
            "name": _titlecase(r["player_name"]),
            "pos": pos,
            "team": team,
            "rookie": is_rookie,
            "g": _fnum(r.get("proj_games")),
            "pts": _fnum(r.get("league_points")),
            "repl": _fnum(r.get("replacement_points")),
            "vor": _fnum(r.get("vor")),
            "posRank": int(_fnum(r.get("positional_rank"), 0) or 0),
            "ovrRank": int(_fnum(r.get("overall_rank"), 0) or 0),
            "vorP10": _fnum(r.get("vor_p10")),
            "vorP90": _fnum(r.get("vor_p90")),
        })
    return recs


# kicker status priority — pick each team's primary kicker off the most-recent roster (active first).
_K_STATUS_RANK = {"ACT": 5, "RES": 4, "INA": 3, "PUP": 3, "DEV": 2, "CUT": 1}


def kicker_map(season: int = 2025) -> dict[str, str]:
    """`{normalized_team -> primary kicker name}` from the most-recent roster (K, active-preferred).

    MVP-1 projects offensive skill only, so kickers aren't in the board — but a manager still drafts one,
    and a real name beats a placeholder. Kickers rarely change team year-to-year, so the latest roster is
    a good proxy. Best-effort: on any lake-read failure returns {} → the K entry falls back to '<TEAM> K'."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "rosters")
        con = _lake_connection()
        try:
            df = con.sql(
                f"select team, full_name, status from delta_scan('{uri}') "
                f"where season = {season} and position = 'K' and full_name is not null"
            ).df()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        log.warning("kicker enrichment skipped (rosters read failed: %s)", e)
        return {}
    best: dict[str, tuple[int, str]] = {}
    for _, r in df.iterrows():
        team = _norm_team(r.get("team"))
        if not team:
            continue
        rank = _K_STATUS_RANK.get(str(r.get("status") or "").strip().upper(), 0)
        if team not in best or rank > best[team][0]:
            best[team] = (rank, str(r["full_name"]))
    return {t: name for t, (_, name) in best.items()}


def kdst_records(teams: list[str], kickers: dict[str, str] | None = None) -> list[dict]:
    """Draftable K & DST placeholders — one per real NFL team. MVP-1 projects offensive skill only, so
    these carry NO projection (pts/vor null): they exist purely so a manager can RECORD their K/DST
    picks and fill those roster slots. They never get recommended (the optimizer skips null-VOR) and sort
    to the bottom. DST is the team unit ('<TEAM> D/ST'); K uses the real kicker name where resolved."""
    kickers = kickers or {}
    recs: list[dict] = []
    for t in teams:
        recs.append({
            "id": f"DST-{t}", "name": f"{t} D/ST", "pos": "DST", "team": t, "rookie": False,
            "g": None, "pts": None, "repl": None, "vor": None, "posRank": 0, "ovrRank": 9999,
            "vorP10": None, "vorP90": None,
        })
        k_name = kickers.get(t)  # roster names are already proper-cased — do not re-title-case
        recs.append({
            "id": f"K-{t}", "name": k_name if k_name else f"{t} K", "pos": "K", "team": t,
            "rookie": False, "g": None, "pts": None, "repl": None, "vor": None, "posRank": 0,
            "ovrRank": 9999, "vorP10": None, "vorP90": None,
        })
    return recs


def config_manifest_entry(name: str) -> dict:
    cfg = get_preset(name)  # roster shape is size-independent (n_teams only scales demand)
    return {
        "name": name,
        "label": CONFIG_LABELS.get(name, name),
        "ppr": cfg.ppr,
        "superflex": cfg.superflex,
        "description": cfg.description,
        "roster": [
            {"name": s.name, "count": s.count, "eligible": list(s.eligible), "bench": s.bench}
            for s in cfg.roster
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--from-lake", action="store_true", help="read boards from the S3 Delta instead of local CSVs")
    ap.add_argument("--out", type=Path, default=None, help="override the frontend output dir")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    df = load_boards_lake(args.season) if args.from_lake else load_boards_local(args.season)
    if "config_name" not in df.columns or "n_teams" not in df.columns:
        raise ValueError("board frame missing config_name / n_teams — cannot key by (config, size)")

    out_dir = (args.out or (_FRONTEND_OUT / str(args.season)))
    out_dir.mkdir(parents=True, exist_ok=True)

    # rookie NFL teams (MVP-1 leaves them NULL) — best-effort from nflverse_players, never fatal
    rookie_teams = rookie_team_map()

    # real NFL team abbreviations from the projection (drives the K/DST placeholder set)
    teams = sorted({
        _norm_team(str(t)) for t in df["team_id"].dropna().unique()
        if str(t) not in ("", "None", "nan") and _norm_team(str(t))
    })
    kdst = kdst_records(teams, kicker_map())

    configs_present: list[str] = []
    sizes_present: set[int] = set()
    combos = 0
    total_rows = 0
    for (config_name, n_teams), grp in df.groupby(["config_name", "n_teams"]):
        config_name = str(config_name)
        n_teams = int(n_teams)
        if config_name not in PRESETS:
            log.warning("skipping unknown config %s (not a shipped preset)", config_name)
            continue
        recs = board_records(grp, rookie_teams) + kdst    # skill board + draftable K/DST placeholders
        path = out_dir / f"board_{config_name}_{n_teams}.json"
        path.write_text(json.dumps(recs, separators=(",", ":")))
        combos += 1
        total_rows += len(recs)
        sizes_present.add(n_teams)
        if config_name not in configs_present:
            configs_present.append(config_name)
        log.info("wrote %s (%d players)", path.name, len(recs))

    # manifest — meta + per-config roster shapes + available combos
    manifest = {
        "season": args.season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "lake" if args.from_lake else "local-artifacts",
        "positions": list(PROJECTABLE),
        "sizes": sorted(sizes_present),
        "configs": [config_manifest_entry(c) for c in sorted(configs_present)],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("wrote manifest.json — %d configs, sizes %s, %d combos, %d player-rows total",
             len(configs_present), sorted(sizes_present), combos, total_rows)
    log.info("frontend draft-board JSON landed in %s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
