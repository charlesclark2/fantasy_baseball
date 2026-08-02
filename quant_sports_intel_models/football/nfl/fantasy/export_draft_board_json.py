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

🔒 NF-D12 PUBLISH GUARD: resolving an S3 bucket (--s3-bucket / $CACHE_BUCKET) no longer uploads by
itself — pass `--publish` to actually reach the LIVE prod api-cache. The default is always a DRY-RUN
that stages the JSON locally and prints exactly what would upload. This exists because $CACHE_BUCKET
is set in the operator's normal env, so the pre-guard default silently pushed to prod on every
re-export session (NF-D11 did this unintentionally).
"""
from __future__ import annotations

import argparse
import collections
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

# ── WHICH season projection this export SERVES (NF1.5b) ──────────────────────────────────────────
# ⭐ The default is the NF1.5 REFINED market-aware board, not MVP-1. That is the whole of NF1.5b:
# NF1.5 produced a board that beats ADP on the NF-D3 product scorecard at all four positions, the
# operator ruled (2026-08-01) to serve it, and until then `nf1_5_season_projections` was written and
# read by nothing. `mvp1` stays available as the escape hatch / the market-BLIND baseline.
#
# 🔒 HONEST FRAME — carried in the payload (`marketLean` below), not only in a doc. The refined board
# INCORPORATES market consensus at the market-leaning positions, so "beats ADP overall" is a real,
# measured, public-scrutinizable backtest result but it is ⛔ NEVER "we beat the market we use". It
# is also a RE-ORDERING claim, not a re-pricing one: the point projections and their 80% bands are
# MVP-1's calibrated numbers; NF1.5 changes WHICH player gets which level, nothing else.
PROJECTION_SOURCES = ("nf1_5", "mvp1")
DEFAULT_PROJECTION_SOURCE = "nf1_5"
_PROJECTION_PARQUET = {
    # MVP-1's season projection (the format-INDEPENDENT raw line the boards are scored from).
    "mvp1": "nfl_fantasy_season_projections_{season}.parquet",
    # NF1.5's refined market-aware re-ordering OF that projection (same points, same bands, new order).
    "nf1_5": "nf1_5_season_projections_{season}.parquet",
}
_PROJECTION_LAKE_SOURCE = {"mvp1": "season_projections", "nf1_5": "nf1_5_season_projections"}
_PROJECTION_LABEL = {
    "mvp1": "market-blind (MVP-1)",
    "nf1_5": "market-aware refined (NF1.5)",
}
# The standing caveat the surfaces must be able to render. Shipped WITH the data so a client can
# never present the board's market-aware positions as an independent edge over the market.
MARKET_LEAN_NOTE = (
    "At positions labelled market-led or market-blend, the ranking INCORPORATES market consensus "
    "(ADP/ECR) alongside our own model — so it is not an independent read on the market at those "
    "positions. The ordering beat consensus ADP across every position on our held-out backtest; the "
    "point projections and their ranges are unchanged from the market-blind model, so this is a "
    "re-ORDERING of the same numbers, not a re-pricing."
)
# E9.45: the draft board is a PAID surface, so it is no longer shipped as public JSON
# (a public asset URL is bypassable). It is staged locally then uploaded to S3, where
# the server-side-gated /fantasy/nfl/* endpoints read it. Default local staging dir:
_STAGING_OUT = _ARTIFACTS / "draft_board_json"

# The projectable fantasy positions. ⭐ NF1.6 added K + DST: they used to carry NO projection, so the
# UI flagged those roster slots "draft late (no projection)" and they never appeared on the board. They
# now rank off a deliberately BASE model with wide honest intervals — see `LOW_PREDICTABILITY` below,
# which is the caveat the surface MUST render beside them.
PROJECTABLE = ("QB", "RB", "WR", "TE", "K", "DST")

# ⚠️ THE POSITIONS THE UI MUST NOT PRESENT AS CONFIDENT RANKS. K and DST are the least predictable
# fantasy positions: NF1.6's held-out rank correlation is ~0.32 for DST and ~0.23 among STARTABLE
# kickers. The projection is worth shipping because it makes the slots rankable and separates good
# situations from bad ones — not because it can tell DST3 from DST7. Every K/DST record carries
# `lowPred: true` + `predNote` so the surface can label the tier honestly rather than the client
# having to know which positions are soft.
LOW_PREDICTABILITY = ("K", "DST")
LOW_PREDICTABILITY_NOTE = (
    "Base projection — K and D/ST are the least predictable fantasy positions. Use these as "
    "streaming TIERS (better vs worse situations), not precise ranks; the wide interval is the "
    "honest part."
)

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
    generational suffixes restored (JAMES COOK III → James Cook III, not "Cook Iii").

    ⚠️ NF1.6 exception: a DST unit name is a TEAM CODE plus a unit label ("DEN D/ST"), not a person's
    name — `.title()` would render it "Den D/St". Those names are already display-ready, so they pass
    through untouched."""
    raw = str(name)
    if raw.upper().endswith(("D/ST", "DST", "DEFENSE")):
        return raw
    out = raw.title()
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


def load_projections_local(season: int, source: str = DEFAULT_PROJECTION_SOURCE) -> pd.DataFrame:
    """The served season projection from the local artifacts parquet — NF1.5's refined board by
    default, MVP-1's with `source='mvp1'` (see `PROJECTION_SOURCES`)."""
    path = _ARTIFACTS / _PROJECTION_PARQUET[source].format(season=season)
    if not path.is_file():
        script = ("run_nf1_5.py --mode build" if source == "nf1_5" else "run_season_projection.py")
        raise FileNotFoundError(
            f"no {source} season projection at {path}. Run {script} first, or use --from-lake."
        )
    return pd.read_parquet(path)


def load_projections_lake(season: int, source: str = DEFAULT_PROJECTION_SOURCE) -> pd.DataFrame:
    """The served season projection from the S3 Delta (NF1.5's refined board by default)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri("nfl", _PROJECTION_LAKE_SOURCE[source], tier="fantasy/derived")
    con = _lake_connection()
    try:
        return con.sql(
            f"select * from delta_scan('{uri}') where projection_season = {season}"
        ).df()
    finally:
        con.close()


def market_lean_by_position(df: pd.DataFrame) -> dict[str, str]:
    """`{position -> market lean}` from the projection's own `market_lean` column (NF1.5 stamps it
    per row from the selected learner's blend weight). `{}` for a projection that carries none —
    the market-BLIND MVP-1 board, where there is nothing to caveat.

    ⚠️ A position is reported by ITS LEARNER'S lean, not by a value count, and the distinction is
    substantive. Rows the refined ordering did not touch — rookies, and the veterans the research
    frame cannot score — carry `independent` because nothing re-ordered THEM, not because the
    position is market-blind. Counting values would therefore label every real position "mixed" and
    the caveat would read as hedging rather than as the honest statement it is. The learners stamp
    one lean per position, so a genuinely conflicting pair is a data defect and is surfaced as
    `mixed:` rather than resolved."""
    if "market_lean" not in df.columns:
        return {}
    # normalize FIRST (FB folds into RB) — grouping on the raw column would let FB's `independent`
    # rows claim the RB key before RB's own rows are seen
    seen: dict[str, set[str]] = {}
    for pos_raw, lean in zip(df["position"], df["market_lean"]):
        pos = NFL_PROFILE.normalize_position(str(pos_raw))
        if pos not in PROJECTABLE or pd.isna(lean):
            continue
        seen.setdefault(pos, set()).add(str(lean))
    out: dict[str, str] = {}
    for pos, vals in seen.items():
        leaning = sorted(v for v in vals if not v.startswith("independent"))
        if len(leaning) == 1:
            out[pos] = leaning[0]
        elif leaning:                               # conflicting learners: report it, never pick
            out[pos] = "mixed:" + "|".join(leaning)
        else:
            out[pos] = sorted(vals)[0]
    return dict(sorted(out.items()))


# The projection's RAW STAT LINE → the compact JSON keys the browse table renders. Season totals.
_STAT_KEYS = (
    ("proj_pass_att", "passAtt"), ("proj_pass_cmp", "passCmp"), ("proj_pass_yds", "passYds"),
    ("proj_pass_td", "passTd"), ("proj_pass_int", "passInt"),
    ("proj_rush_att", "rushAtt"), ("proj_rush_yds", "rushYds"), ("proj_rush_td", "rushTd"),
    ("proj_targets", "tgt"), ("proj_rec", "rec"), ("proj_rec_yds", "recYds"), ("proj_rec_td", "recTd"),
    ("proj_fumbles_lost", "fum"), ("proj_two_pt", "twoPt"),
)

# NF1.6 — the K/DST raw components the browse table renders. Kept in the SAME `_STAT_KEYS` idiom so a
# mixed frame needs no per-position branching: an absent column yields null, and a WR simply has no
# `fgMade` while a kicker has no `passYds`. The points-allowed BUCKET columns are not DISPLAY columns
# — the surface shows `paPerG`, the number that actually communicates defensive quality — but they
# ARE exported (see `_DST_PA_BUCKET_KEYS`) because they are the scoring input a custom tier table
# needs; NF-C0b scores a hand-entered league client-side off this payload.
_KDST_STAT_KEYS = (
    ("proj_fg_att", "fgAtt"), ("proj_fg_made", "fgMade"),
    ("proj_fg_made_0_39", "fg039"), ("proj_fg_made_40_49", "fg4049"),
    ("proj_fg_made_50_plus", "fg50"), ("proj_fg_missed", "fgMiss"),
    ("proj_pat_att", "patAtt"), ("proj_pat_made", "patMade"),
    ("proj_def_sacks", "sacks"), ("proj_def_int", "defInt"),
    ("proj_def_fumble_rec", "fumRec"), ("proj_def_td", "defTd"), ("proj_st_td", "stTd"),
    ("proj_def_safety", "safety"), ("proj_def_blocked_kick", "blocked"),
    ("proj_dst_points_allowed", "paTot"), ("proj_dst_pa_per_game", "paPerG"),
)

# ── NF-C0b: the nine POINTS-ALLOWED TIER columns ─────────────────────────────────────────────────
# Each is the EXPECTED NUMBER OF GAMES a defence lands in that points-allowed bucket, so a per-game
# tier table scores a season as `Σ_bucket tier_points × expected_games` — LINEAR in these columns.
# That linearity is the whole reason a hand-entered tier table needs no new modelling: the client
# scorer applies the user's own nine weights to these nine numbers and gets the tier table EXACTLY.
# Not rendered anywhere; they exist purely so a custom D/ST scheme is scorable in the browser.
_DST_PA_BUCKET_KEYS = tuple(
    (f"proj_dst_pa_g_{b}", f"paG{b}")
    for b in ("0", "1_6", "7_13", "14_17", "18_20", "21_27", "28_34", "35_45", "46p")
)


def projection_records(
    df: pd.DataFrame,
    rookie_teams: dict[str, str] | None = None,
    byes: dict[str, int] | None = None,
    bio: dict[str, dict] | None = None,
    contributions: dict[str, dict] | None = None,
) -> list[dict]:
    """MVP-1's season projection → display-ready records for the NF3 browse "Projections" surface.

    FORMAT-INDEPENDENT by design: the raw season stat line plus the 80% PPR interval, the uncertainty
    TYPE (veteran `empirical` game-to-game variance vs the rookie `calibrated` band) and the model's own
    confidence tier — the honest-uncertainty payload. `proj_fp_*` are carried as a one-format convenience
    for sorting only; the FORMAT-scored number is the league board's `league_points`, never these.
    Sorted by PPR points desc; FB folds into RB; names title-cased; NULL (unknown) stays null.

    NF3.1 — `bio` (see `player_bio_map`) adds birth date / height / weight / college / years of
    experience / headshot, best-effort and format-independent (identity, not a projection), so it
    lives here rather than on the per-league board records.

    NF3.4 — `contributions` (the `players` map from `load_player_contributions`) adds `contrib`: our
    NF1 research model's own per-player point breakdown (`nf1_model.player_feature_contributions`).
    Absent for rookies/K/DST (NF1 doesn't cover them) — declared as `None` so the shape is
    fetch-independent, same convention as `adp`."""
    rookie_teams = rookie_teams or {}
    byes = byes or {}
    bio = bio or {}
    contributions = contributions or {}
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
            "lowPred": pos in LOW_PREDICTABILITY,     # NF1.6 — see LOW_PREDICTABILITY
            "predNote": LOW_PREDICTABILITY_NOTE if pos in LOW_PREDICTABILITY else None,
            "contrib": None,   # filled below when NF1 covers this player; None for rookies/K/DST
            # NF1.5b — how market-leaning THIS row's ordering is ("market-led" / "market-blend" /
            # "independent-lean" / "independent"). Null on a board with no market input at all. It
            # rides on the row rather than only in the manifest because the caveat is per-POSITION
            # and a player page renders one player, not the whole board.
            "mktLean": (None if pd.isna(r.get("market_lean")) else str(r["market_lean"])),
        }
        c = contributions.get(pid)
        if c:
            rec["contrib"] = {
                # NF3.4: the model's SHARED constant (biasPts) vs THIS player's OWN starting
                # projection (ownPriorPts) — kept separate so the UI can explain why two players at
                # the same position start from different baselines (see player_feature_contributions).
                "biasPts": c.get("bias_pts"),
                "ownPriorPts": c.get("own_prior_pts"),
                "baselinePts": c.get("baseline_pts"),
                "totalPts": c.get("total_pts"),
                "drivers": [{"feature": d["feature"], "pts": d["pts"]} for d in c.get("drivers", [])],
            }
        b = bio.get(pid)
        if b:
            rec["birthDate"] = b.get("birthDate")
            rec["heightIn"] = b.get("heightIn")
            rec["weightLb"] = b.get("weightLb")
            rec["college"] = b.get("college")
            rec["yearsExp"] = b.get("yearsExp")
            rec["headshot"] = b.get("headshot")
        for src, key in (*_STAT_KEYS, *_KDST_STAT_KEYS, *_DST_PA_BUCKET_KEYS):
            rec[key] = _fnum(r.get(src))
        recs.append(rec)
    return recs


def _adp_key(pos: str, name: str | None, team: str | None) -> tuple[str, str] | None:
    """The join key for one ADP row / board record.

    ⚠️ A DEFENCE JOINS ON ITS TEAM CODE, NOT ITS NAME, and that is not a nicety — a name join is
    guaranteed to match ZERO defences. FFC writes a unit as "Denver Defense"; our board writes it as
    "DEN D/ST". Normalized, that is `denver defense` vs `den dst` — no normalizer bridges those,
    because the two strings share no token. This silently cost every defence its ADP (0 of 32 matched
    while FFC published 19, including a Seattle unit going ~pick 87, the one D/ST ADP a drafter
    genuinely acts on). The team code is the real identity of a fantasy defence, and both sides
    already carry it, so it is also the more robust key. A NAMED player keeps the name join: he has
    no stable id across FFC and our rookie rows carry synthetic gsis ids."""
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

    if pos == "DST":
        t = _norm_team(str(team)) if team else None
        return (t, pos) if t else None
    return (A._normalize_name(name), pos) if name else None


def adp_lookup(season: int, fmt: str, teams: int) -> dict[tuple[str, str], float]:
    """`{(key, position) -> adp}` from Fantasy Football Calculator for one (format, size), where the
    key is the normalized NAME for a named player and the TEAM CODE for a defence (see `_adp_key`).

    Keyed on the name, not our gsis id, on purpose: the board's rookies carry synthetic ids (their
    projection comes from the NCAAF rookie leg, not an NFL game log), so a gsis crosswalk would drop
    exactly the players a drafter most wants an ADP for. Both sides go through `adp_source`'s vetted
    normalizer, which already folds accents, generational suffixes and the FFC nickname aliases.

    Best-effort by design: FFC is an external free API. A failure logs a warning and yields {} → the
    ADP column renders "—" rather than failing the export, which is the draft-critical output."""
    try:
        df = A_fetch(season, fmt, teams)
    except Exception as e:  # noqa: BLE001 — a reference column must never break the boards
        log.warning("ADP unavailable for %s %s/%dteam (%s: %s)", season, fmt, teams, type(e).__name__, e)
        return {}
    out: dict[tuple[str, str], float] = {}
    for _, r in df.iterrows():
        pos = NFL_PROFILE.normalize_position(str(r.get("position") or ""))
        adp = _fnum(r.get("adp"))
        if pos not in PROJECTABLE or adp is None:
            continue
        key = _adp_key(pos, r.get("player_name"), r.get("team"))
        if key is not None:
            out.setdefault(key, adp)
    by_pos = collections.Counter(pos for _, pos in out)
    log.info("ADP %s %s/%dteam: %d players (%s)", season, fmt, teams, len(out),
             ", ".join(f"{p}={by_pos[p]}" for p in PROJECTABLE))
    return out


def A_fetch(season: int, fmt: str, teams: int):
    """Indirection so a test can stub the FFC fetch without reaching the network."""
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

    return A.fetch_ffc_adp(season, fmt=fmt, teams=teams)


@functools.lru_cache(maxsize=None)
def adp_cache_for(season: int, fmt: str, teams: int) -> dict[tuple[str, str], float]:
    """Memoized `adp_lookup` — the 14 (config, size) boards share only a handful of distinct ADP
    samples, so this keeps the export to one FFC fetch per (format, size) instead of one per board."""
    return adp_lookup(season, fmt, teams)


def _attach_adp(recs: list[dict], adp: dict[tuple[str, str], float]) -> int:
    """Add `adp` to each record in place (null when the player is undrafted in that ADP sample —
    a real signal, not a gap). Returns how many matched."""
    n = 0
    for rec in recs:
        key = _adp_key(rec["pos"], rec.get("name"), rec.get("team")) if rec.get("pos") else None
        val = adp.get(key) if key is not None else None
        rec["adp"] = val
        n += val is not None
    return n


# ⭐ NF1.7 — the CLASS-LEVEL-BAND tolerance, and it is MEASURED, not asserted. Two players may share
#    a rounded band for two very different reasons:
#      * COINCIDENCE — near-identical projections whose bounds collide at the served 0.1 resolution
#        (typically two deep-bench veterans whose p10 both floor at 0). Harmless.
#      * QUANTISATION — a CLASS-level band pasted onto players the band was never centred on. This is
#        the NF1.7 defect, and its signature is that the sharers' POINT PROJECTIONS span a large
#        fraction of the band's own width: one interval cannot be centred on all of them.
#    The two populations are cleanly separated on the real board (measured 2026-07-29, pre-NF1.7): the
#    four class-level rookie groups sit at a point-spread/width ratio of **0.68–0.84**, while every one
#    of the 44 veteran rounding coincidences tops out at **0.196**. A threshold of 0.25 therefore sits
#    inside a 3.4× empirical gap — it is where the data separates, not a number someone liked. It is
#    also ~5× the extreme-tail tolerance below, so a coincidence can never trip it.
_SHARED_BAND_POINT_SPREAD_TOL = 0.25
# ⚠️ NF1.9 — THE RATIO ALONE HAS NO TRACTION WHEN THE SCALE IS TINY, and that is a second false-positive
#    mode, not a defect. A scale-FREE ratio is most easily tripped by the NARROWEST bands: on the first
#    NF1.9 board, 4 of the 5 offender groups were deep-bench players whose ENTIRE SEASON projections
#    spanned 1.3–4.7 PPR inside a 3.2–13.8-wide band (e.g. 0.0–3.2 shared by 6 players spanning 1.27 PPR
#    = 40% of the band). 1.3 PPR over a 17-game season is 0.08 PPR/game — no drafter can act on it, and
#    flagging it is the "guard that can never go green" failure the ratio fix was itself introduced to
#    cure, arriving from the other end.
#    So a shared band must ALSO span a MATERIAL number of points to count. The floor is a DECISION-
#    RESOLUTION quantity, fixed from the unit rather than from the result: **1 PPR per game over a
#    17-game season = 17 PPR**, below which two players are indistinguishable to a drafter.
#    The measured separation is wide, which is what makes the floor safe rather than convenient: the
#    NF1.9 offenders top out at **20.3 PPR** of spread while the NF1.7 class-level defect this guard
#    exists to catch spanned **243 PPR** (26.5–277.0 shared across rookie QBs projected 25.1→268.3) —
#    a 12× gap, and the defect would clear a 17-PPR floor by 14×. It is NOT a silencer: the NF1.9 board
#    still trips it on 2 players.
_SHARED_BAND_MIN_POINT_SPREAD = 17.0
_EXTREME_TAIL_TOL = 0.05


def audit_interval_quality(recs: list[dict], p10: str = "fpP10", p90: str = "fpP90",
                           point: str = "fpPpr") -> list[str]:
    """Data-quality check on the served 80% bands. Returns a list of human-readable findings.

    ALERT-tier: this WARNS, it never blocks the export — a coarse band is still data, and the app
    labels it honestly. The point is that a degenerate band should never reach users SILENTLY.

    Two failure modes it catches, both real on the 2026 board as of 2026-07-29 (the NF3 review that
    routed NF1.7):
      * CLASS-LEVEL bands — one interval pasted onto players it was never centred on. Pre-NF1.7 the
        rookie leg quantised to ~3 buckets per position: 81 rookies carried 12 distinct intervals
        (703 veterans carried 647), and every top-bucket rookie QB carried an identical 26.5–277.0
        while their point projections spanned 25.1→268.3.
      * INCOHERENT bands — the point projection sitting outside, or in the extreme tail of, its own
        interval. A direct consequence of the above: one shared band cannot centre on every player
        it is pasted onto.

    ⚠️ THE FIRST CUT OF THIS CHECK FIRED ON *ANY* BAND SHARED BY TWO PLAYERS, which made it
    permanently red for a reason that is not a defect — two deep-bench veterans whose p10 both floor
    at 0 collide at the served 0.1 resolution. A guard that can never go green is a guard nobody
    reads, so the shared-band finding now tests the INVARIANT THAT ACTUALLY MATTERS: a band shared by
    players whose points span more than `_SHARED_BAND_POINT_SPREAD_TOL` of its own width cannot be
    centred on all of them. See that constant for the measurement behind the threshold.
    """
    findings: list[str] = []
    usable = [r for r in recs if r.get(p10) is not None and r.get(p90) is not None]
    if not usable:
        return findings

    # ── a band shared by players it cannot be centred on is a CLASS-level range ──
    groups: dict[tuple, list[dict]] = {}
    for r in usable:
        groups.setdefault((r[p10], r[p90]), []).append(r)
    offenders = []
    for (lo, hi), members in groups.items():
        pts = [m[point] for m in members if m.get(point) is not None]
        width = hi - lo
        if len(pts) < 2 or width <= 0:
            continue
        spread = max(pts) - min(pts)
        ratio = spread / width
        # BOTH conditions: the sharers must be un-centrable (the ratio) AND materially different (the
        # absolute spread). Either alone has a false-positive mode — see the two constants.
        if ratio > _SHARED_BAND_POINT_SPREAD_TOL and spread >= _SHARED_BAND_MIN_POINT_SPREAD:
            offenders.append((ratio, lo, hi, members, spread))
    if offenders:
        offenders.sort(reverse=True, key=lambda o: o[0])
        ratio, lo, hi, members, spread = offenders[0]
        n_aff = sum(len(o[3]) for o in offenders)
        findings.append(
            f"{n_aff}/{len(usable)} players carry a CLASS-LEVEL band — one interval shared by players "
            f"whose point projections span more than {_SHARED_BAND_POINT_SPREAD_TOL:.0%} of its own "
            f"width AND at least {_SHARED_BAND_MIN_POINT_SPREAD:.0f} PPR, so it cannot be centred on "
            f"all of them (worst: {lo}–{hi} shared by "
            f"{len(members)} players spanning {spread:.1f} pts = {ratio:.0%} of the band; e.g. "
            f"{members[0]['name']} {members[0][point]} vs {members[-1]['name']} {members[-1][point]}). "
            f"Overall {len(groups)}/{len(usable)} distinct bands"
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
            and not (_EXTREME_TAIL_TOL
                     <= (r[point] - r[p10]) / (r[p90] - r[p10])
                     <= 1.0 - _EXTREME_TAIL_TOL)]
    if tail:
        findings.append(
            f"{len(tail)} players have a point projection in the extreme "
            f"{_EXTREME_TAIL_TOL:.0%} tail of their own band "
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


def load_player_contributions() -> dict | None:
    """NF3.4 — the NF1 GBM's per-PLAYER feature contributions (`run_nf1_feature_importance.py`'s
    output): for every currently-projected veteran, how many fantasy points each signal is estimated
    to add/subtract for HIM specifically (LightGBM TreeSHAP — see `nf1_model.player_feature_contributions`).

    Best-effort like `rookie_team_map`/`player_bio_map`: a missing/stale artifact costs the transparency
    panel only, never the boards (the draft-critical output) or the projections surface. It is a LOCAL
    artifact (no S3/lake read at export time — the DuckDB read already happened when
    `run_nf1_feature_importance.py` was run) — re-run that script to refresh it.

    🚨 HONEST LABELLING lives with the DATA here, not just the UI: the payload carries `model_version`
    (NF1's, not MVP-1's) and every player's `total_pts` is NF1's OWN prediction — never silently equal
    to the served MVP-1 projection (see the model function's docstring). A caller must never drop the
    model identity while presenting these numbers. Rookies and K/DST are absent by design — NF1 has no
    base-season feature row to attribute for them (see the module docstring)."""
    path = _ARTIFACTS / "nf1_player_contributions.json"
    if not path.is_file():
        log.warning("nf1_player_contributions.json not found at %s — the player-page transparency "
                    "panel will be empty until run_nf1_feature_importance.py is (re-)run", path)
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001 — best-effort enrichment, never fatal
        log.warning("nf1_player_contributions.json failed to parse (%s: %s) — transparency panel "
                    "skipped", type(e).__name__, e)
        return None


def player_bio_map() -> dict[str, dict]:
    """`{player_id -> bio dict}` for the NF3.1 player page — birth date, height, weight, college,
    years of NFL experience and an official headshot URL, all PASSED THROUGH from `nflverse_players`
    (the same all-time identity table `rookie_team_map` already reads, keyed the same way on
    `gsis_id`). Nothing derived or computed here: age is left to the client (from `birthDate`) rather
    than baked in as-of the export date, so it never goes stale between re-exports.

    Verified coverage among active players (2026-08-02): birth_date/height/weight 99.8%+, college_name
    and years_of_experience 100%, headshot 99.2% (a live nfl.com CDN URL). Best-effort like its
    sibling: any lake-read failure logs a warning and returns {}, so a bio-enrichment outage costs
    only the bio panel, never the projection export."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "nflverse_players")
        con = _lake_connection()
        try:
            df = con.sql(
                f"select gsis_id, birth_date, height, weight, college_name, years_of_experience, "
                f"headshot from delta_scan('{uri}')"
            ).df()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001 — best-effort enrichment, never fatal
        log.warning("player bio enrichment skipped (nflverse_players read failed: %s)", e)
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        gid = r.get("gsis_id")
        if not gid:
            continue
        out[str(gid)] = {
            "birthDate": None if pd.isna(r.get("birth_date")) else str(r["birth_date"]),
            "heightIn": _inum(r.get("height")),
            "weightLb": _inum(r.get("weight")),
            "college": None if pd.isna(r.get("college_name")) else str(r["college_name"]),
            "yearsExp": _inum(r.get("years_of_experience")),
            "headshot": None if pd.isna(r.get("headshot")) else str(r["headshot"]),
        }
    log.info("player bio map: %d players enriched", len(out))
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
            # NF1.6: the honest low-predictability marker. Declared on EVERY record (false for the
            # skill positions) so the client never has to know which positions are soft.
            "lowPred": pos in LOW_PREDICTABILITY,
            "predNote": LOW_PREDICTABILITY_NOTE if pos in LOW_PREDICTABILITY else None,
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
    *,
    covered: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """UNPROJECTED K & DST placeholders — since NF1.6 the honest FALLBACK, not the normal path.

    ⭐ K and DST are now genuinely projected and arrive through `board_records` like every other
    position. This function now only fills the GAPS: a `(pos, team)` pair the board did NOT project
    still needs a draftable row so a manager can RECORD the pick and fill the roster slot. Those rows
    carry NO projection (pts/vor null), never get recommended (the optimizer skips null-VOR) and sort
    to the bottom — the pre-NF1.6 behaviour, now scoped to what is genuinely missing instead of
    applied to all 32 teams.

    `covered=None` reproduces the old all-teams behaviour, which is exactly what the caller wants
    when the K/DST projection is absent entirely (a loud, complete degradation rather than a board
    with unfillable slots)."""
    kickers = kickers or {}
    byes = byes or {}
    covered = covered or set()
    recs: list[dict] = []
    for t in teams:
        bye = byes.get(t)
        if ("DST", t) not in covered:
            recs.append({
                "id": f"DST-{t}", "name": f"{t} D/ST", "pos": "DST", "team": t, "bye": bye,
                "rookie": False, "g": None, "pts": None, "repl": None, "vor": None, "posRank": 0,
                "ovrRank": 9999, "vorP10": None, "vorP90": None, "ptsP10": None, "ptsP90": None,
                "adp": None, "lowPred": True, "predNote": LOW_PREDICTABILITY_NOTE,
            })
        if ("K", t) not in covered:
            k_name = kickers.get(t)  # roster names are already proper-cased — do not re-title-case
            recs.append({
                "id": f"K-{t}", "name": k_name if k_name else f"{t} K", "pos": "K", "team": t,
                "bye": bye, "rookie": False, "g": None, "pts": None, "repl": None, "vor": None,
                "posRank": 0, "ovrRank": 9999, "vorP10": None, "vorP90": None, "ptsP10": None,
                "ptsP90": None, "adp": None, "lowPred": True,
                "predNote": LOW_PREDICTABILITY_NOTE,
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


def assert_board_projection_source(df: pd.DataFrame, want: str, season: int) -> None:
    """REFUSE to export when the league boards were scored from a DIFFERENT projection than the one
    the Projections surface will serve.

    ⚠️ THIS IS THE FAILURE MODE NF1.5b HAD TO GUARD, not a hypothetical. The draft board (`board_*.json`
    → Rankings / Draft Optimizer / League Board) is scored by `run_league_board.py`, while
    `projections.json` (→ Projections / the player page) is read here. They are two views of ONE
    ranking, but they come from two SEPARATE reads of two SEPARATE artifacts — so a re-land that
    repoints only one of them ships a board where a player is WR4 on one surface and WR9 on another,
    with no error anywhere. A silent disagreement between two serving surfaces is worse than a failed
    export, so this raises.

    A board with NO `projection_source` column predates NF1.5b, i.e. it was scored from MVP-1 before
    the flip and is exactly the stale artifact this exists to catch — it refuses too, with the re-run
    command."""
    rerun = (f"uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_league_board "
             f"--projection-season {season} --projection-source {want}")
    if "projection_source" not in df.columns:
        raise SystemExit(
            f"the league boards carry no `projection_source` — they were built before NF1.5b, so "
            f"they are scored from MVP-1 while this export would serve '{want}' projections. "
            f"Re-score the boards first:\n  {rerun}")
    got = sorted({str(v) for v in df["projection_source"].dropna().unique()})
    if got != [want]:
        raise SystemExit(
            f"projection-source MISMATCH: the league boards were scored from {got} but this export "
            f"would serve '{want}' projections — the draft board and the Projections surface would "
            f"rank the same player differently. Re-score the boards:\n  {rerun}")
    log.info("projection source: %s (%s) — boards and projections agree", want,
             _PROJECTION_LABEL[want])


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--projection-source", choices=PROJECTION_SOURCES,
                    default=DEFAULT_PROJECTION_SOURCE,
                    help="WHICH season projection the Projections surface serves. Default 'nf1_5' = "
                         "the market-aware refined board (NF1.5b re-land); 'mvp1' = the market-blind "
                         "MVP-1 board. ⚠️ this must MATCH the projection run_league_board.py scored "
                         "the board CSVs from, or the Projections surface and the draft board will "
                         "rank the same player differently — the export refuses on a mismatch.")
    ap.add_argument("--from-lake", action="store_true",
                    help="read the boards + season projection from the S3 Delta instead of local artifacts")
    ap.add_argument("--out", type=Path, default=None, help="override the local staging output dir")
    ap.add_argument(
        "--s3-bucket",
        default=os.getenv("CACHE_BUCKET"),
        help="S3 bucket to upload the boards to (default $CACHE_BUCKET). Uploaded under "
        "fantasy/nfl/<season>/ where the gated /fantasy/nfl/* API reads them. Resolving a "
        "bucket alone does NOT upload — pass --publish too (see below).",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help="NF-D12 PUBLISH GUARD: actually upload to the LIVE prod api-cache bucket. Without "
        "this flag the exporter always DRY-RUNS (default) — it stages the JSON locally and "
        "prints exactly what WOULD upload, even if --s3-bucket / $CACHE_BUCKET resolves to the "
        "prod bucket. This is a deliberate act: a re-export session must not push to users "
        "unintentionally (NF-D11 did).",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    df = load_boards_lake(args.season) if args.from_lake else load_boards_local(args.season)
    if "config_name" not in df.columns or "n_teams" not in df.columns:
        raise ValueError("board frame missing config_name / n_teams — cannot key by (config, size)")
    assert_board_projection_source(df, args.projection_source, args.season)

    out_dir = (args.out or (_STAGING_OUT / str(args.season)))
    out_dir.mkdir(parents=True, exist_ok=True)

    # rookie NFL teams (MVP-1 leaves them NULL) — best-effort from nflverse_players, never fatal
    rookie_teams = rookie_team_map()
    # NF3.1 — bio for the player page (birth date/height/weight/college/experience/headshot),
    # same table + same best-effort contract as rookie_teams above.
    bio = player_bio_map()
    if not bio:
        log.warning("[ALERT] player bio map is EMPTY — every published player will show no age/"
                    "height/weight/college/photo on the player page. See the 'player bio "
                    "enrichment skipped' warning above for the actual read failure.")
    # bye weeks for the projection season — empty until NF-D1 lands the schedule, then auto-populates
    byes = bye_week_map(args.season)

    # real NFL team abbreviations from the projection (drives the K/DST placeholder set)
    teams = sorted({
        _norm_team(str(t)) for t in df["team_id"].dropna().unique()
        if str(t) not in ("", "None", "nan") and _norm_team(str(t))
    })
    # NF1.6: the placeholder set is now GAP-FILL only — see `kdst_records`. Resolved per board below
    # because a board that failed to project K/DST needs different placeholders than one that did.
    kicker_names = kicker_map()

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
        # NF1.6: `skill` now already contains the PROJECTED K/DST rows; the placeholders only fill
        # whatever (pos, team) pairs the projection did not cover, so no slot is ever unfillable.
        covered = {(r["pos"], r["team"]) for r in skill
                   if r["pos"] in LOW_PREDICTABILITY and r.get("team")}
        gaps = kdst_records(teams, kicker_names, byes, covered=covered)
        n_projected = len(covered)
        if n_projected == 0:
            log.warning("[ALERT] %s_%d: NO K/DST rows on the board — those slots fall back to "
                        "UNPROJECTED placeholders. Run run_kdst_projection.py + rebuild the board.",
                        config_name, n_teams)
        else:
            log.info("  %s_%d: %d K/DST row(s) projected across %d (pos, team) pair(s), "
                     "%d placeholder gap row(s)", config_name, n_teams,
                     sum(1 for r in skill if r["pos"] in LOW_PREDICTABILITY), n_projected, len(gaps))
        recs = skill + gaps
        path = out_dir / f"board_{config_name}_{n_teams}.json"
        path.write_text(json.dumps(recs, separators=(",", ":")))
        combos += 1
        total_rows += len(recs)
        sizes_present.add(n_teams)
        if config_name not in configs_present:
            configs_present.append(config_name)
        log.info("wrote %s (%d players)", path.name, len(recs))

    # NF3.4 — the NF1 per-player point contributions (`nf1_player_contributions.json`), folded into
    # each projection record below + the manifest's legend. Best-effort: a missing artifact costs the
    # transparency panel only, never the boards/projections themselves.
    contributions_payload = load_player_contributions()
    contrib_map = (contributions_payload or {}).get("players", {})
    if contributions_payload is None:
        log.warning("[ALERT] projections.json will ship with no player 'contrib' — the player-page "
                    "transparency panel renders nothing until run_nf1_feature_importance.py is run")

    # NF3 — the format-INDEPENDENT season projection blob (the browse "Projections" surface).
    # Best-effort: a missing projection artifact must not cost the operator the boards, which are
    # the draft-critical output. The endpoint 404s until it lands (the UI shows an honest empty state).
    projections: list[dict] = []
    proj_meta: dict = {}
    try:
        pdf = (load_projections_lake(args.season, args.projection_source) if args.from_lake
               else load_projections_local(args.season, args.projection_source))
        # NF1.6: fold the K/DST base projection into the browse surface so those positions are
        # BROWSABLE, not just draftable. Best-effort — a missing K/DST lineage logs loudly and leaves
        # the offensive projections intact (they are the draft-critical output).
        from quant_sports_intel_models.football.nfl.fantasy.run_league_board import (
            load_kdst_lake, load_kdst_local,
        )
        kdf = (load_kdst_lake(args.season) if args.from_lake
               else load_kdst_local(_ARTIFACTS, args.season))
        if len(kdf):
            pdf = pd.concat([pdf, kdf], ignore_index=True, sort=False)
            log.info("  projections: folded in %d NF1.6 K/DST rows", len(kdf))
        projections = projection_records(pdf, rookie_teams, byes, bio, contrib_map)
        n_with_contrib = sum(1 for p in projections if p.get("contrib"))
        log.info("  projections: %d/%d players carry an NF1 per-player contribution breakdown",
                 n_with_contrib, len(projections))
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
            # NF1.5b — which projection lineage this board IS, and (for the market-aware one) how
            # market-leaning each position's ordering is. Shipped so the surfaces can carry the
            # caveat from the data instead of hard-coding a claim that can go stale.
            "projection_source": args.projection_source,
            "projection_label": _PROJECTION_LABEL[args.projection_source],
            "market_lean": market_lean_by_position(pdf) or None,
            "market_lean_note": (MARKET_LEAN_NOTE if "market_lean" in pdf.columns else None),
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
        # NF1.5b — which projection lineage EVERY blob in this export came from. Top-level (not only
        # inside `projections`) because the league boards carry it too, and they are exported even
        # when the projections blob is not.
        "projectionSource": args.projection_source,
        "projectionLabel": _PROJECTION_LABEL[args.projection_source],
        "sizes": sorted(sizes_present),
        "configs": [config_manifest_entry(c) for c in sorted(configs_present)],
        # NF3: the browse surfaces read this to know whether the projections blob is available
        # (and to show its provenance) without a speculative fetch.
        "projections": {"players": len(projections), **proj_meta} if projections else None,
        # NF3.4 — the small per-FEATURE legend (label + plain-language description) each projection
        # record's `contrib.drivers[].feature` keys into; None until run_nf1_feature_importance.py
        # has been run at least once. Kept tiny (~12 entries) and separate from the per-player payload
        # so the (label, description) text isn't duplicated across hundreds of player records.
        "featureLegend": contributions_payload.get("legend") if contributions_payload else None,
        "featureContributionsMeta": (
            {k: contributions_payload.get(k) for k in
             ("model_version", "generated_at", "base_season", "projection_season", "n_players")}
            if contributions_payload else None
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("wrote manifest.json — %d configs, sizes %s, %d combos, %d player-rows total",
             len(configs_present), sorted(sizes_present), combos, total_rows)
    log.info("draft-board JSON staged in %s", out_dir)

    # Upload to S3 for the server-side-gated /fantasy/nfl/* endpoints (E9.45) — gated behind
    # --publish (NF-D12). Without a bucket the boards are only staged locally (the API then
    # 404s until they're uploaded); with a bucket but no --publish, this is a DRY-RUN report.
    _maybe_publish(out_dir, args.s3_bucket, args.season, args.publish)
    return 0


def _maybe_publish(out_dir: Path, bucket: str | None, season: int, publish: bool) -> None:
    """Gate the S3 upload behind an explicit `--publish` (NF-D12 PUBLISH GUARD).

    ⭐ WHY: this exporter used to upload whenever a bucket resolved (--s3-bucket / $CACHE_BUCKET),
    so any re-export session pushed straight to the LIVE prod api-cache with no deliberate act
    (NF-D11 did this unintentionally while re-exporting to verify a coverage fix). Default =
    DRY-RUN: a resolved bucket only prints what WOULD upload; reaching the live bucket requires
    the caller to pass --publish, which prints a loud banner first.

    🚨 `--publish` WITH NO BUCKET IS A HARD ERROR (NF1.7, 2026-07-29 — this cost a real publish).
    NF-D12 wrote that `$CACHE_BUCKET` "is ALWAYS set in the operator's env"; it was NOT set in the
    shell the operator actually published NF1.7 from, so `--publish` degraded to the no-bucket
    local-staging WARNING — one line at the end of ~40 lines of INFO, with no upload banner — and
    the run looked successful while nothing reached users. That is the repo's documented-but-never-set
    landmine (cf. `W7B_LAKEHOUSE_S3`) in a publish path. An operator who explicitly asks for an
    outward-facing action must never get a silent no-op: **without `--publish` a missing bucket stays
    an ALERT-tier warn (staging locally is the intended default), but WITH `--publish` it raises.**"""
    if not bucket:
        if publish:
            raise SystemExit(
                "--publish was passed but NO BUCKET resolved (--s3-bucket / $CACHE_BUCKET is unset "
                "or empty), so nothing would be uploaded and the run would have looked successful. "
                "Re-run with the bucket named explicitly:\n"
                f"  --season {season} --s3-bucket credence-prod-s3-api-cache --publish"
            )
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — boards staged locally only; the gated API "
            "will 404 until they are uploaded to s3://<bucket>/fantasy/nfl/%d/", season,
        )
        return
    files = sorted(out_dir.glob("*.json"))
    prefix = f"fantasy/nfl/{season}"
    if not publish:
        log.info(
            "[DRY-RUN] would upload %d file(s) to s3://%s/%s/ — pass --publish to actually "
            "reach the LIVE prod api-cache: %s",
            len(files), bucket, prefix, ", ".join(p.name for p in files),
        )
        return
    log.warning("🚨 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s/ (%d files)", bucket, prefix, len(files))
    _upload_to_s3(out_dir, bucket, season)


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
