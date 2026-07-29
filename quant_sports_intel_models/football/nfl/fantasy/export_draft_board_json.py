"""export_draft_board_json.py — land the NFL fantasy boards + projections as trimmed JSON for the app.

MVP-3's frontend draft optimizer is ALL-CLIENT-SIDE (instant recompute per pick, no server round-trip),
so it reads the boards as static JSON, staged locally then uploaded to S3 where the server-side-gated
`/fantasy/nfl/*` endpoints read them:

  * `manifest.json`              — season meta + every league config's roster shape (drives roster-need
                                   detection client-side) + the (config, size) combos available.
  * `board_<config>_<size>.json` — the per-(config, n_teams) player board, trimmed to the columns the
                                   optimizer + UI need, names title-cased, FB folded into RB.
  * `projections.json`           — NF3: the MVP-1 SEASON PROJECTION (raw stat line + the 80% PPR
                                   interval + uncertainty type / confidence / rookie flag), format-
                                   independent. Feeds the browse "Projections" surface; the league
                                   boards above stay the format-SCORED view.

⚠️ NF3 SERVING-PATH NOTE: these blobs ARE the fantasy serving path. The boards live only as dbt-duckdb
views over S3 Delta with no request-time reader, and a wide lakehouse read from the API Lambda fails
silently (CLAUDE.md landmine) — so the app is served this pre-computed static JSON instead, exactly
like the MLB `write_api_cache` pattern. The data updates rarely (not intraday), so a re-export is an
operator command, not a daily op.

Reads the boards from the local artifacts CSVs by default (what `run_league_board.py` writes), or from
the S3 Delta with `--from-lake`. SF-free / off-box. This is the frontend analog of "land to S3 + a
readable output" — the board data the draft tool consumes.
"""
from __future__ import annotations

import argparse
import functools
import json
import logging
import os
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
# MVP-1's season projection (the format-INDEPENDENT raw line the boards are scored from).
_PROJECTION_PARQUET = "nfl_fantasy_season_projections_{season}.parquet"
# E9.45: the draft board is a PAID surface, so it is no longer shipped as public JSON
# (a public asset URL is bypassable). It is staged locally then uploaded to S3, where
# the server-side-gated /fantasy/nfl/* endpoints read it. Default local staging dir:
_STAGING_OUT = _ARTIFACTS / "draft_board_json"

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


# ── market ADP (a REFERENCE column, not a claim) ──────────────────────────────────────────────────
# Each preset maps to the Fantasy Football Calculator ADP format that actually MATCHES it, and the
# board's own `n_teams`. Format-matching is not cosmetic: superflex ADP ("2qb") drafts ~34 QBs vs
# ~27 in PPR, so pairing a superflex board with PPR ADP would make every QB look like a huge
# "value" that is purely an artefact of the mismatched reference. A preset with no direct FFC
# equivalent falls back to the closest scoring rule (the roster-shape variants share a format).
PRESET_ADP_FORMAT = {
    "standard": "standard",
    "standard_3wr": "standard",
    "half_ppr": "half-ppr",
    "half_ppr_3wr": "half-ppr",
    "full_ppr": "ppr",
    "full_ppr_3wr": "ppr",
    "superflex": "2qb",
    "te_premium": "ppr",
}
# The projections surface is format-INDEPENDENT, so its ADP reference is pinned to the most common
# home-league shape and labelled as such rather than silently varying.
PROJECTION_ADP_FORMAT = "ppr"
PROJECTION_ADP_TEAMS = 12

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


# Generational suffixes `.title()` mangles (JAMES COOK III → "Iii"). Only ever applied to the LAST
# token of a name, so a real name that happens to look like one (Ivory, Vince) is never touched.
_NAME_SUFFIXES = {"Ii": "II", "Iii": "III", "Iv": "IV", "Vi": "VI"}


def _titlecase(name: str) -> str:
    """ALLCAPS board name → display case, with the common Mc/Mac fix (MCCAFFREY → McCaffrey) and
    generational suffixes restored (JAMES COOK III → James Cook III, not "Cook Iii")."""
    out = str(name).title()
    for pre in ("Mc", "Mac"):
        i = 0
        while (i := out.find(pre, i)) != -1:
            j = i + len(pre)
            if j < len(out) and out[j].isalpha():
                out = out[:j] + out[j].upper() + out[j + 1 :]
            i = j
    parts = out.split()
    if parts and parts[-1] in _NAME_SUFFIXES:
        parts[-1] = _NAME_SUFFIXES[parts[-1]]
        out = " ".join(parts)
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


def _inum(v):
    """A nullable integer (draft slot) — NaN/unparseable stays null rather than becoming 0."""
    f = _fnum(v, 0)
    return None if f is None else int(f)


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


def load_projections_local(season: int) -> pd.DataFrame:
    """MVP-1's season projection from the local artifacts parquet (what run_season_projection.py writes)."""
    path = _ARTIFACTS / _PROJECTION_PARQUET.format(season=season)
    if not path.is_file():
        raise FileNotFoundError(
            f"no season projection at {path}. Run run_season_projection.py first, or use --from-lake."
        )
    return pd.read_parquet(path)


def load_projections_lake(season: int) -> pd.DataFrame:
    """MVP-1's season projection from the S3 Delta (`mart_nfl_fantasy_season_projection`'s source)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri("nfl", "season_projections", tier="fantasy/derived")
    con = _lake_connection()
    try:
        return con.sql(
            f"select * from delta_scan('{uri}') where projection_season = {season}"
        ).df()
    finally:
        con.close()


# The projection's RAW STAT LINE → the compact JSON keys the browse table renders. Season totals.
_STAT_KEYS = (
    ("proj_pass_att", "passAtt"), ("proj_pass_cmp", "passCmp"), ("proj_pass_yds", "passYds"),
    ("proj_pass_td", "passTd"), ("proj_pass_int", "passInt"),
    ("proj_rush_att", "rushAtt"), ("proj_rush_yds", "rushYds"), ("proj_rush_td", "rushTd"),
    ("proj_targets", "tgt"), ("proj_rec", "rec"), ("proj_rec_yds", "recYds"), ("proj_rec_td", "recTd"),
    ("proj_fumbles_lost", "fum"), ("proj_two_pt", "twoPt"),
)


def projection_records(
    df: pd.DataFrame,
    rookie_teams: dict[str, str] | None = None,
    byes: dict[str, int] | None = None,
) -> list[dict]:
    """MVP-1's season projection → display-ready records for the NF3 browse "Projections" surface.

    FORMAT-INDEPENDENT by design: the raw season stat line plus the 80% PPR interval, the uncertainty
    TYPE (veteran `empirical` game-to-game variance vs the rookie `calibrated` band) and the model's own
    confidence tier — the honest-uncertainty payload. `proj_fp_*` are carried as a one-format convenience
    for sorting only; the FORMAT-scored number is the league board's `league_points`, never these.
    Sorted by PPR points desc; FB folds into RB; names title-cased; NULL (unknown) stays null."""
    rookie_teams = rookie_teams or {}
    byes = byes or {}
    recs: list[dict] = []
    seen: set[str] = set()
    for _, r in df.sort_values("proj_fp_ppr", ascending=False).iterrows():
        pos = NFL_PROFILE.normalize_position(str(r["position"]))
        if pos not in PROJECTABLE:
            continue
        pid = str(r["player_id"])
        if pid in seen:                                # 1 row per player (MVP-1 can emit a dupe)
            continue
        seen.add(pid)
        is_rookie = _to_bool(r.get("is_rookie"))
        team = None if pd.isna(r.get("team_id")) else _norm_team(str(r["team_id"]))
        if not team and is_rookie:                     # MVP-1 rookies carry no team → backfill it
            team = rookie_teams.get(pid)
        rec = {
            "id": pid,
            "name": _titlecase(r["player_name"]),
            "pos": pos,
            "team": team,
            "bye": byes.get(team) if team else None,
            "rookie": is_rookie,
            "draftPick": _inum(r.get("draft_overall")),
            "conf": None if pd.isna(r.get("confidence")) else str(r["confidence"]),
            "g": _fnum(r.get("proj_games")),
            "fpStd": _fnum(r.get("proj_fp_std")),
            "fpHalf": _fnum(r.get("proj_fp_half")),
            "fpPpr": _fnum(r.get("proj_fp_ppr")),
            "fpSd": _fnum(r.get("fp_ppr_sd")),
            "fpP10": _fnum(r.get("fp_ppr_p10")),
            "fpP90": _fnum(r.get("fp_ppr_p90")),
            "uncType": None if pd.isna(r.get("uncertainty_type")) else str(r["uncertainty_type"]),
            "adp": None,   # filled by _attach_adp; declared so the shape is fetch-independent
        }
        for src, key in _STAT_KEYS:
            rec[key] = _fnum(r.get(src))
        recs.append(rec)
    return recs


def adp_lookup(season: int, fmt: str, teams: int) -> dict[tuple[str, str], float]:
    """`{(normalized_name, position) -> adp}` from Fantasy Football Calculator for one (format, size).

    Keyed on the NAME, not our gsis id, on purpose: the board's rookies carry synthetic ids (their
    projection comes from the NCAAF rookie leg, not an NFL game log), so a gsis crosswalk would drop
    exactly the players a drafter most wants an ADP for. Both sides go through `adp_source`'s vetted
    normalizer, which already folds accents, generational suffixes and the FFC nickname aliases.

    Best-effort by design: FFC is an external free API. A failure logs a warning and yields {} → the
    ADP column renders "—" rather than failing the export, which is the draft-critical output."""
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

    try:
        df = A.fetch_ffc_adp(season, fmt=fmt, teams=teams)
    except Exception as e:  # noqa: BLE001 — a reference column must never break the boards
        log.warning("ADP unavailable for %s %s/%dteam (%s: %s)", season, fmt, teams, type(e).__name__, e)
        return {}
    out: dict[tuple[str, str], float] = {}
    for _, r in df.iterrows():
        pos = NFL_PROFILE.normalize_position(str(r.get("position") or ""))
        adp = _fnum(r.get("adp"))
        if pos in PROJECTABLE and adp is not None:
            out.setdefault((A._normalize_name(r.get("player_name")), pos), adp)
    log.info("ADP %s %s/%dteam: %d players", season, fmt, teams, len(out))
    return out


@functools.lru_cache(maxsize=None)
def adp_cache_for(season: int, fmt: str, teams: int) -> dict[tuple[str, str], float]:
    """Memoized `adp_lookup` — the 14 (config, size) boards share only a handful of distinct ADP
    samples, so this keeps the export to one FFC fetch per (format, size) instead of one per board."""
    return adp_lookup(season, fmt, teams)


def _attach_adp(recs: list[dict], adp: dict[tuple[str, str], float]) -> int:
    """Add `adp` to each record in place (null when the player is undrafted in that ADP sample —
    a real signal, not a gap). Returns how many matched."""
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

    n = 0
    for rec in recs:
        val = adp.get((A._normalize_name(rec["name"]), rec["pos"])) if rec.get("pos") else None
        rec["adp"] = val
        n += val is not None
    return n


def audit_interval_quality(recs: list[dict], p10: str = "fpP10", p90: str = "fpP90",
                           point: str = "fpPpr") -> list[str]:
    """Data-quality check on the served 80% bands. Returns a list of human-readable findings.

    ALERT-tier: this WARNS, it never blocks the export — a coarse band is still data, and the app
    labels it honestly. The point is that a degenerate band should never reach users SILENTLY.

    Two failure modes it catches, both real as of 2026-07-29 (NF3 review):
      * SHARED bands — a band identical across many players is not a per-player interval at all.
        The rookie leg quantises to ~3 buckets per position, so every rookie QB in a bucket carries
        26.5–277.0 while their point projections span 25 to 268.
      * INCOHERENT bands — the point projection sitting outside, or in the extreme tail of, its own
        interval. A direct consequence of the above: one shared band cannot centre on every player
        it is pasted onto.
    """
    findings: list[str] = []
    usable = [r for r in recs if r.get(p10) is not None and r.get(p90) is not None]
    if not usable:
        return findings

    # a band shared by many players is a class-level band masquerading as a player-level one
    shared: dict[tuple, int] = {}
    for r in usable:
        shared[(r[p10], r[p90])] = shared.get((r[p10], r[p90]), 0) + 1
    worst = max(shared.items(), key=lambda kv: kv[1])
    if worst[1] > 1:
        n_shared = sum(c for c in shared.values() if c > 1)
        findings.append(
            f"{n_shared}/{len(usable)} players carry a band shared with at least one other player "
            f"(worst: {worst[0][0]}–{worst[0][1]} shared by {worst[1]}) — a shared band is a "
            f"CLASS-level range, not a player-level one"
        )

    # the point projection must sit inside its own interval, and not pinned to an extreme
    outside = [r for r in usable if r.get(point) is not None
               and not (r[p10] <= r[point] <= r[p90])]
    if outside:
        findings.append(
            f"{len(outside)} players have a point projection OUTSIDE their own 80% band "
            f"(e.g. {outside[0]['name']}: {outside[0][point]} vs {outside[0][p10]}–{outside[0][p90]})"
        )
    tail = [r for r in usable
            if r.get(point) is not None and r[p90] > r[p10]
            and not (0.05 <= (r[point] - r[p10]) / (r[p90] - r[p10]) <= 0.95)]
    if tail:
        findings.append(
            f"{len(tail)} players have a point projection in the extreme 5% tail of their own band "
            f"(e.g. {tail[0]['name']}: {tail[0][point]} in {tail[0][p10]}–{tail[0][p90]})"
        )
    return findings


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
def board_records(
    df: pd.DataFrame,
    rookie_teams: dict[str, str] | None = None,
    byes: dict[str, int] | None = None,
) -> list[dict]:
    """One board (already filtered to a config+size) → trimmed, display-ready player records, sorted by
    overall_rank. FB folds into RB; names title-cased; interval carried honestly. A rookie with no
    projection team is backfilled from `rookie_teams`; `bye` is the team's bye week (null until known)."""
    rookie_teams = rookie_teams or {}
    byes = byes or {}
    recs = []
    seen: set[str] = set()
    for _, r in df.sort_values("overall_rank").iterrows():
        pos = NFL_PROFILE.normalize_position(str(r["position"]))
        if pos not in PROJECTABLE:
            continue
        pid = str(r["player_id"])
        if pid in seen:                                # dedupe by player_id (keep best overall_rank);
            continue                                    # MVP-1 can emit a player twice → 1 row per player
        seen.add(pid)
        is_rookie = _to_bool(r.get("is_rookie"))
        team = None if pd.isna(r.get("team_id")) else _norm_team(str(r["team_id"]))
        if not team and is_rookie:                     # MVP-1 rookies carry no team → backfill it
            team = rookie_teams.get(str(r["player_id"]))
        recs.append({
            "id": str(r["player_id"]),
            "name": _titlecase(r["player_name"]),
            "pos": pos,
            "team": team,
            "bye": byes.get(team) if team else None,
            "rookie": is_rookie,
            "g": _fnum(r.get("proj_games")),
            "pts": _fnum(r.get("league_points")),
            # NF3: the 80% interval on league POINTS (the browse surfaces lead with this rather
            # than a false-precise point). vor_p10/p90 is the same interval shifted by the
            # replacement level, so both are carried.
            "ptsP10": _fnum(r.get("league_points_p10")),
            "ptsP90": _fnum(r.get("league_points_p90")),
            "repl": _fnum(r.get("replacement_points")),
            "vor": _fnum(r.get("vor")),
            "posRank": int(_fnum(r.get("positional_rank"), 0) or 0),
            "ovrRank": int(_fnum(r.get("overall_rank"), 0) or 0),
            "vorP10": _fnum(r.get("vor_p10")),
            "vorP90": _fnum(r.get("vor_p90")),
            # declared here (not only added by _attach_adp) so every record has the same shape
            # whether or not the external ADP fetch succeeded
            "adp": None,
        })
    return recs


# kicker status priority — pick each team's primary kicker off the most-recent roster (active first).
_K_STATUS_RANK = {"ACT": 5, "RES": 4, "INA": 3, "PUP": 3, "DEV": 2, "CUT": 1}


def bye_week_map(season: int) -> dict[str, int]:
    """`{normalized_team -> bye week}` for `season`, derived from the lake `schedules` (the REG week a
    team has no game). READ-ONLY: it reads whatever season is already in the lake and returns {} if the
    season isn't there yet — it never pulls/ingests. So byes are empty until NF-D1 lands the 2026 slate,
    then populate automatically on the next export. Best-effort (never fatal)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "schedules")
        con = _lake_connection()
        try:
            df = con.sql(
                f"select week, home_team, away_team from delta_scan('{uri}') "
                f"where season = {season} and game_type = 'REG'"
            ).df()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        log.warning("bye-week enrichment skipped (schedules read failed: %s)", e)
        return {}
    if df.empty:
        log.info("no %d schedule in the lake yet — byes stay null until NF-D1 lands the season", season)
        return {}
    weeks = sorted(int(w) for w in df["week"].dropna().unique())
    long = pd.concat([
        df[["week", "home_team"]].rename(columns={"home_team": "team"}),
        df[["week", "away_team"]].rename(columns={"away_team": "team"}),
    ])
    out: dict[str, int] = {}
    for team, g in long.groupby("team"):
        t = _norm_team(str(team))
        if not t:
            continue
        played = {int(w) for w in g["week"].dropna()}
        missing = [w for w in weeks if w not in played]
        if missing:
            out[t] = int(missing[0])
    log.info("bye week map: %d teams", len(out))
    return out


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


def kdst_records(
    teams: list[str],
    kickers: dict[str, str] | None = None,
    byes: dict[str, int] | None = None,
) -> list[dict]:
    """Draftable K & DST placeholders — one per real NFL team. MVP-1 projects offensive skill only, so
    these carry NO projection (pts/vor null): they exist purely so a manager can RECORD their K/DST
    picks and fill those roster slots. They never get recommended (the optimizer skips null-VOR) and sort
    to the bottom. DST is the team unit ('<TEAM> D/ST'); K uses the real kicker name where resolved."""
    kickers = kickers or {}
    byes = byes or {}
    recs: list[dict] = []
    for t in teams:
        bye = byes.get(t)
        recs.append({
            "id": f"DST-{t}", "name": f"{t} D/ST", "pos": "DST", "team": t, "bye": bye, "rookie": False,
            "g": None, "pts": None, "repl": None, "vor": None, "posRank": 0, "ovrRank": 9999,
            "vorP10": None, "vorP90": None, "ptsP10": None, "ptsP90": None, "adp": None,
        })
        k_name = kickers.get(t)  # roster names are already proper-cased — do not re-title-case
        recs.append({
            "id": f"K-{t}", "name": k_name if k_name else f"{t} K", "pos": "K", "team": t, "bye": bye,
            "rookie": False, "g": None, "pts": None, "repl": None, "vor": None, "posRank": 0,
            "ovrRank": 9999, "vorP10": None, "vorP90": None, "ptsP10": None, "ptsP90": None, "adp": None,
        })
    return recs


def config_manifest_entry(name: str) -> dict:
    cfg = get_preset(name)  # roster shape is size-independent (n_teams only scales demand)
    return {
        "name": name,
        "label": CONFIG_LABELS.get(name, name),
        "ppr": cfg.ppr,
        "superflex": cfg.superflex,
        # which FFC ADP sample this board's ADP column was drawn from — the UI labels it so an
        # ADP is never shown as though it came from the user's exact format when it didn't
        "adpFormat": PRESET_ADP_FORMAT.get(name),
        "description": cfg.description,
        "roster": [
            {"name": s.name, "count": s.count, "eligible": list(s.eligible), "bench": s.bench}
            for s in cfg.roster
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--from-lake", action="store_true",
                    help="read the boards + season projection from the S3 Delta instead of local artifacts")
    ap.add_argument("--out", type=Path, default=None, help="override the local staging output dir")
    ap.add_argument(
        "--s3-bucket",
        default=os.getenv("CACHE_BUCKET"),
        help="S3 bucket to upload the boards to (default $CACHE_BUCKET). Uploaded under "
        "fantasy/nfl/<season>/ where the gated /fantasy/nfl/* API reads them. If empty, "
        "boards are only staged locally.",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    df = load_boards_lake(args.season) if args.from_lake else load_boards_local(args.season)
    if "config_name" not in df.columns or "n_teams" not in df.columns:
        raise ValueError("board frame missing config_name / n_teams — cannot key by (config, size)")

    out_dir = (args.out or (_STAGING_OUT / str(args.season)))
    out_dir.mkdir(parents=True, exist_ok=True)

    # rookie NFL teams (MVP-1 leaves them NULL) — best-effort from nflverse_players, never fatal
    rookie_teams = rookie_team_map()
    # bye weeks for the projection season — empty until NF-D1 lands the schedule, then auto-populates
    byes = bye_week_map(args.season)

    # real NFL team abbreviations from the projection (drives the K/DST placeholder set)
    teams = sorted({
        _norm_team(str(t)) for t in df["team_id"].dropna().unique()
        if str(t) not in ("", "None", "nan") and _norm_team(str(t))
    })
    kdst = kdst_records(teams, kicker_map(), byes)

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
        skill = board_records(grp, rookie_teams, byes)
        # market ADP, matched to THIS board's scoring format + league size (see PRESET_ADP_FORMAT)
        adp_fmt = PRESET_ADP_FORMAT.get(config_name, "ppr")
        matched = _attach_adp(skill, adp_cache_for(args.season, adp_fmt, n_teams))
        log.info("  %s_%d: ADP (%s/%dteam) matched %d/%d players",
                 config_name, n_teams, adp_fmt, n_teams, matched, len(skill))
        recs = skill + kdst   # skill board + draftable K/DST placeholders
        path = out_dir / f"board_{config_name}_{n_teams}.json"
        path.write_text(json.dumps(recs, separators=(",", ":")))
        combos += 1
        total_rows += len(recs)
        sizes_present.add(n_teams)
        if config_name not in configs_present:
            configs_present.append(config_name)
        log.info("wrote %s (%d players)", path.name, len(recs))

    # NF3 — the format-INDEPENDENT season projection blob (the browse "Projections" surface).
    # Best-effort: a missing projection artifact must not cost the operator the boards, which are
    # the draft-critical output. The endpoint 404s until it lands (the UI shows an honest empty state).
    projections: list[dict] = []
    proj_meta: dict = {}
    try:
        pdf = load_projections_lake(args.season) if args.from_lake else load_projections_local(args.season)
        projections = projection_records(pdf, rookie_teams, byes)
        # The projections surface is format-independent, so its ADP reference is pinned + labelled.
        proj_adp_matched = _attach_adp(
            projections, adp_cache_for(args.season, PROJECTION_ADP_FORMAT, PROJECTION_ADP_TEAMS)
        )
        log.info("  projections: ADP (%s/%dteam) matched %d/%d players",
                 PROJECTION_ADP_FORMAT, PROJECTION_ADP_TEAMS, proj_adp_matched, len(projections))
        for finding in audit_interval_quality(projections):
            log.warning("[ALERT] interval quality: %s", finding)
        proj_meta = {
            "adp_format": PROJECTION_ADP_FORMAT,
            "adp_teams": PROJECTION_ADP_TEAMS,
            "model_version": (
                str(pdf["model_version"].dropna().iloc[0]) if "model_version" in pdf.columns
                and pdf["model_version"].notna().any() else None
            ),
            "base_season": (
                int(pdf["base_season"].dropna().iloc[0]) if "base_season" in pdf.columns
                and pdf["base_season"].notna().any() else None
            ),
        }
        payload = {
            "season": args.season,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "lake" if args.from_lake else "local-artifacts",
            **proj_meta,
            "players": projections,
        }
        (out_dir / "projections.json").write_text(json.dumps(payload, separators=(",", ":")))
        log.info("wrote projections.json (%d players, model %s)", len(projections),
                 proj_meta.get("model_version"))
    except Exception as e:  # noqa: BLE001 — the boards are the critical output; warn loudly and go on
        log.warning("projections.json SKIPPED (%s: %s) — the browse Projections surface will 404 "
                    "until the season projection is exported", type(e).__name__, e)

    # manifest — meta + per-config roster shapes + available combos
    manifest = {
        "season": args.season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "lake" if args.from_lake else "local-artifacts",
        "positions": list(PROJECTABLE),
        "sizes": sorted(sizes_present),
        "configs": [config_manifest_entry(c) for c in sorted(configs_present)],
        # NF3: the browse surfaces read this to know whether the projections blob is available
        # (and to show its provenance) without a speculative fetch.
        "projections": {"players": len(projections), **proj_meta} if projections else None,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("wrote manifest.json — %d configs, sizes %s, %d combos, %d player-rows total",
             len(configs_present), sorted(sizes_present), combos, total_rows)
    log.info("draft-board JSON staged in %s", out_dir)

    # Upload to S3 for the server-side-gated /fantasy/nfl/* endpoints (E9.45). Without a
    # bucket the boards are only staged locally (the API then 404s until they're uploaded).
    if args.s3_bucket:
        _upload_to_s3(out_dir, args.s3_bucket, args.season)
    else:
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — boards staged locally only; the gated API "
            "will 404 until they are uploaded to s3://<bucket>/fantasy/nfl/%d/", args.season,
        )
    return 0


def _upload_to_s3(out_dir: Path, bucket: str, season: int) -> None:
    """Upload every staged board + the manifest to s3://<bucket>/fantasy/nfl/<season>/.

    Plain (key-less) client — instance-role / AWS_PROFILE safe (never pass
    aws_access_key_id=os.environ.get(...); see test_boto3_credential_lint.py). The
    cache bucket lives in us-east-1 (matches app.backend.services.s3_cache) — pin the
    region here so a laptop AWS_DEFAULT_REGION=us-east-2 (the ML-artifacts bucket)
    can't misroute the put."""
    import boto3

    s3 = boto3.client("s3", region_name="us-east-1")
    prefix = f"fantasy/nfl/{season}"
    n = 0
    for path in sorted(out_dir.glob("*.json")):
        s3.put_object(
            Bucket=bucket,
            Key=f"{prefix}/{path.name}",
            Body=path.read_bytes(),
            ContentType="application/json",
        )
        n += 1
    log.info("uploaded %d board files to s3://%s/%s/", n, bucket, prefix)


if __name__ == "__main__":
    raise SystemExit(main())
