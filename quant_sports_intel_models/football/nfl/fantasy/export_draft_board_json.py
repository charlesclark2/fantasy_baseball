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

from quant_sports_intel_models.fantasy_engine.auction import (  # noqa: E402
    DEFAULT_AUCTION_BUDGET,
    auction_pool,
    auction_values,
)
from quant_sports_intel_models.football.nfl.fantasy import captured_terms  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import player_naming as PN  # noqa: E402
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
# INCORPORATES market consensus at the market-leaning positions, so whatever it beats, it is ⛔ NEVER
# "we beat the market we use". It is also a RE-ORDERING claim, not a re-pricing one: the point
# projections and their 80% bands are MVP-1's calibrated numbers; NF1.5 changes WHICH player gets
# which level, nothing else.
#
# ⚠️ THE PAYLOAD NOTE DELIBERATELY MAKES NO "BEATS ADP" CLAIM. NF1.5b's re-grade DID reproduce it
# (+0.022 pooled Δρ-vs-ADP over 2019–2024, against the served MVP-1 board's −0.059), but a bare
# superiority claim on a browse surface would sit with no evidence beside it AND would contradict the
# copy already on those surfaces ("ADP is a reference point, not a scoreboard"). The claim belongs to
# the receipts surface that can show its working (NF3.2); this note's job is the CAVEAT, which is the
# part a user cannot look up. See `ablation_results/nf1_5b_serving_reland.md` for the measured result
# — including that it is NOT positive at every position (RB is a wash) and that ECR/ESPN/Sleeper
# still order better than we do.
from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as _PC

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
    "positions, and a gap between our order and the market's is a smaller, less independent signal "
    "there than it would be from a model that ignored the market. The point projections and their "
    "ranges are unchanged from the market-blind model, so this is a re-ORDERING of the same numbers, "
    "not a re-pricing."
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


def _titlecase(name: str, authority: str | None = None,
               draft_board: str | None = None) -> str:
    """A board name rendered for display — delegated to `player_naming.display_name`, the ONE casing
    authority shared with the track-record export (E9.61 item 4).

    ⚠️ THIS FUNCTION USED TO PRODUCE "MacK Hollins" ON THE LIVE BOARD. It ran `.title()` over EVERY
    name (damaging the rookie pipeline's already-correct `KC Concepcion` -> "Kc Concepcion") and
    then upper-cased the letter after any "Mac", which turns MACK into MacK. Both are fixed in
    `player_naming`; the measurement and the reasoning live in that module's docstring — read it
    before changing casing behaviour here.

    `authority` is that player's nflverse roster name (`player_naming.roster_casing_authority`),
    used for CASE ONLY: 703 of 784 source rows arrive ALL-CAPS and casing is not recoverable from an
    upper-case string by rule ("DEVONTA FREEMAN" -> Devonta, "DEVONTA SMITH" -> DeVonta). Omitted, the
    rule pass still runs — it just cannot fix the 30 names only the authority knows."""
    return PN.display_name(name, authority, draft_board)


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
    """A DuckDB connection wired for the S3 lakehouse (delta + httpfs + creds). SF-free / off-box.

    INC-45 — the credentials must go in through the SECRET MANAGER; `delta_scan` ignores the
    deprecated `s3_*` settings this used to set. See `s3io.configure_duckdb_lake_auth`."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    return s3io.duckdb_lake_connection()


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
    # NF-C0e: the graduated captured terms are derived columns applied on the READ path. EVERY
    # projection loader routes through this one function (`captured_terms.CONSUMER_CALLERS`) —
    # `two_pt` carries weight 2.0 in every preset, so a loader that skipped it would export a
    # payload scored a few points apart from the board CSVs for the same player.
    return captured_terms.apply_to_projection(pd.read_parquet(path), _ARTIFACTS, season)


def load_projections_lake(season: int, source: str = DEFAULT_PROJECTION_SOURCE) -> pd.DataFrame:
    """The served season projection from the S3 Delta (NF1.5's refined board by default)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri("nfl", _PROJECTION_LAKE_SOURCE[source], tier="fantasy/derived")
    con = _lake_connection()
    try:
        df = con.sql(
            f"select * from delta_scan('{uri}') where projection_season = {season}"
        ).df()
    finally:
        con.close()
    # NF-C0e — see `load_projections_local`. The rates artifact is local even on the lake path: it
    # is a handful of measured league constants, not projection data.
    return captured_terms.apply_to_projection(df, _ARTIFACTS, season)


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
    # NF-C0e — the graduated long-touchdown bonus terms. `twoPt` above was ALWAYS listed here but
    # carried NaN for every player (MVP-1 declared the column and never filled it), so the field
    # was dropped on export and `two_pt` reported CAPTURED. It now carries a measured value.
    ("proj_pass_td_40p", "passTd40p"), ("proj_rush_td_40p", "rushTd40p"),
    ("proj_rec_td_40p", "recTd40p"),
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
    # NF-C0e — forced fumbles + the yards-allowed season total / per-game rate.
    ("proj_def_forced_fumble", "ff"),
    ("proj_dst_yards_allowed", "yaTot"), ("proj_dst_ya_per_game", "yaPerG"),
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

# ── NF-C0e: the nine YARDS-ALLOWED TIER columns ──────────────────────────────────────────────────
# Same contract, same reason as the points block above: each is the EXPECTED NUMBER OF GAMES in that
# yards-allowed bucket, so the client scorer multiplies the user's own nine weights by these nine
# numbers and reproduces the league's tier table EXACTLY. Not rendered anywhere — they exist purely
# so a league that scores yards allowed (Sleeper +6..-6, ESPN +5..-7) is scorable in the browser
# instead of being told, correctly but uselessly, that we saved the rule and ignored it.
_DST_YA_BUCKET_KEYS = tuple(
    (f"proj_dst_ya_g_{b}", f"yaG{b}")
    for b in ("0_99", "100_199", "200_299", "300_349", "350_399",
              "400_449", "450_499", "500_549", "550p")
)


def projection_records(
    df: pd.DataFrame,
    rookie_teams: dict[str, str] | None = None,
    byes: dict[str, int] | None = None,
    bio: dict[str, dict] | None = None,
    contributions: dict[str, dict] | None = None,
    casing: dict[str, str] | None = None,
    board_names: dict[tuple[str, str], str] | None = None,
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
    casing = casing or {}
    board_names = board_names or {}
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
            "name": _titlecase(r["player_name"], casing.get(pid),
                               board_names.get(_adp_key(pos, r["player_name"], team) or ("", ""))),
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
        for src, key in (*_STAT_KEYS, *_KDST_STAT_KEYS, *_DST_PA_BUCKET_KEYS,
                         *_DST_YA_BUCKET_KEYS):
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


@functools.lru_cache(maxsize=8)
def draft_board_names(season: int, fmt: str = "ppr", teams: int = 12) -> dict[tuple[str, str], str]:
    """`{(normalized name, position) -> the name a DRAFT BOARD shows}` from Fantasy Football
    Calculator — see `player_naming.drafted_as` for why a draft board is the right authority for a
    drafter-facing name, and for the one change it is not allowed to make.

    ⭐ THE KEY IS `_adp_key`, THE SAME CROSSWALK THE ADP COLUMN ALREADY JOINS ON. That matters twice
    over: it is a vetted normalizer (it folds accents, generational suffixes and FFC's own nickname
    aliases, so "Kenny Gainwell" and "Kenneth Gainwell" land on one key), and it introduces no new
    matching surface — if this join could put the wrong name on a row, the ADP column would already
    be wrong for that row.

    ⚠️ A DEFENCE IS DELIBERATELY EXCLUDED. `_adp_key` keys a DST on its TEAM CODE, so every defence
    in the sample would collide onto a handful of keys, and their names are unit labels ("DEN D/ST")
    rather than anything a person spells. Named players only.

    Best-effort, exactly like `adp_lookup`, and off the same cached fetch — the export already pulls
    this sample for the ADP column, so this adds no network call."""
    try:
        df = A_fetch(season, fmt, teams)
    except Exception as e:  # noqa: BLE001 — a display name must never break the boards
        log.warning("draft-board names unavailable for %s %s/%dteam (%s: %s)",
                    season, fmt, teams, type(e).__name__, e)
        return {}
    out: dict[tuple[str, str], str] = {}
    for _, r in df.iterrows():
        pos = NFL_PROFILE.normalize_position(str(r.get("position") or ""))
        name = r.get("player_name")
        if pos not in PROJECTABLE or pos == "DST" or not name:
            continue
        key = _adp_key(pos, name, r.get("team"))
        if key is not None:
            out.setdefault(key, str(name))
    return out


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


# NF-FRESH2 P1 — set once by `main()` from `--market-refresh`. Module state (rather than an extra
# parameter) because `adp_cache_for` is an `lru_cache` keyed on (season, fmt, teams) and threading a
# 4th argument through it would give the two refresh modes SEPARATE cache entries, i.e. one export
# could fetch the same sample twice. The refresh decision is a per-RUN property, not a per-sample
# one, so it belongs beside the run, not in the memo key.
_MARKET_REFRESH = False


def set_market_refresh(enabled: bool) -> None:
    """Set the per-run market-refresh mode and drop the memoized ADP samples.

    Clearing `adp_cache_for` matters: without it a lookup memoized under the previous mode would be
    replayed under the new one, and the export would ship a snapshot it did not actually fetch."""
    global _MARKET_REFRESH
    _MARKET_REFRESH = bool(enabled)
    adp_cache_for.cache_clear()


def A_fetch(season: int, fmt: str, teams: int):
    """Indirection so a test can stub the FFC fetch without reaching the network.

    ⭐ NF-FRESH2 P1 — the `refresh` argument is reduced through `should_refresh_market`, so the
    exporter can only ever re-fetch the CURRENT season. A historical export (a re-publish of a past
    season's board) still reads that season's pinned snapshot no matter what the CLI said — the
    E5.9 backfill boundary, enforced here as well as in the projection build."""
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A
    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF

    refresh = MF.should_refresh_market(season, _MARKET_REFRESH)
    if _MARKET_REFRESH and not refresh:
        log.info("market refresh REFUSED for season %s (not the current season) — reading the "
                 "pinned ADP snapshot", season)
    return A.fetch_ffc_adp(season, fmt=fmt, teams=teams, refresh=refresh)


# Every (fmt, teams) ADP sample this export actually pulled. Recorded through the ONE funnel every
# ADP fetch goes through, so the freshness block reports the samples the boards were REALLY built
# from rather than a hard-coded list that could drift from the shipped configs.
_ADP_SAMPLES_USED: set[tuple[str, int]] = set()


@functools.lru_cache(maxsize=None)
def adp_cache_for(season: int, fmt: str, teams: int) -> dict[tuple[str, str], float]:
    """Memoized `adp_lookup` — the 14 (config, size) boards share only a handful of distinct ADP
    samples, so this keeps the export to one FFC fetch per (format, size) instead of one per board."""
    _ADP_SAMPLES_USED.add((fmt, int(teams)))
    return adp_lookup(season, fmt, teams)


def _freshness_meta(season: int) -> dict:
    """The NF-FRESH2 per-input vintage block, for both `projections.json` and `manifest.json`.

    Flat `adp_as_of` / `ecr_as_of` are the two dates a surface renders beside the ADP column; the
    nested `freshness` object carries the full provenance (the ADP draft WINDOW and draft count,
    every sample the export pulled, and the lake-input vintages the projection build recorded).

    ⛔ Every read here is a CACHE read — this function cannot fetch, so it can neither change what
    the export shipped nor disagree with it. It reports the vintage; `A_fetch` chose it."""
    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF

    adp = MF.adp_as_of(season, fmt=PROJECTION_ADP_FORMAT, teams=PROJECTION_ADP_TEAMS)
    ecr = MF.ecr_as_of(season)
    by_sample = {}
    for fmt, teams in sorted(_ADP_SAMPLES_USED):
        by_sample[f"{fmt}/{teams}"] = MF.adp_as_of(season, fmt=fmt, teams=teams)

    # The projection build's own record of which lake inputs it consumed (NF-FRESH2 P2). Read from
    # the summary the build wrote, NOT re-derived from the lake here: re-deriving would report what
    # the lake holds NOW, which is a different and flattering question (NF-FRESH1 §1.1 measured the
    # exact gap — a board generated 7h42m BEFORE that day's ingest landed).
    input_vintage, built_at = None, None
    summary = _ARTIFACTS / f"nf1_5_projection_summary_{season}.json"
    try:
        if summary.exists():
            blob = json.loads(summary.read_text())
            input_vintage = blob.get("input_vintage")
            built_at = blob.get("generated_at")
    except Exception as e:  # noqa: BLE001 — a provenance stamp must never fail the export
        log.warning("freshness: could not read %s (%s: %s)", summary.name, type(e).__name__, e)

    if adp is None:
        log.warning("[ALERT] freshness: no ADP as-of stamp for %s %s/%dteam — the surfaces will "
                    "render the ADP vintage as unknown", season, PROJECTION_ADP_FORMAT,
                    PROJECTION_ADP_TEAMS)
    return {
        "adp_as_of": (adp or {}).get("as_of"),
        "ecr_as_of": (ecr or {}).get("as_of"),
        "freshness": {
            "adp": adp,
            "ecr": ecr,
            "adp_by_sample": by_sample or None,
            "input_vintage": input_vintage,
            "projection_built_at": built_at,
            "market_refresh": bool(_MARKET_REFRESH),
        },
    }


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


#: The board columns `run_season_projection` stamps the rookie policy into → the payload keys the
#: governance readback reconciles. Kept as an explicit MAP so a renamed column fails a guard test
#: rather than silently publishing a policy block with a missing field.
_ROOKIE_POLICY_COLUMNS: dict[str, str] = {
    "rookie_selection_status": "selection_status",
    "rookie_shrink_lambda": "shrink_lambda",
    "rookie_statistically_selected": "statistically_selected",
    "rookie_source_model": "source_model",
    "rookie_decision_story": "decision_story",
}


def rookie_policy_stamp(pdf: pd.DataFrame) -> dict | None:
    """The rookie-policy block for the published payload, READ OFF THE BOARD's own stamp columns.

    Returns None for a board built before NF-D21 (no stamp columns) — an honest absence, so a
    consumer can tell "this board predates the policy" apart from "this board asserts a policy".
    ⛔ It must never fall back to the policy module's values: a stamp that describes the CODE rather
    than the ARTIFACT would keep reading correct while the served board drifted, which is the
    NF-C0e "declaration outruns its production" class.

    ⚠️ A board carrying MORE THAN ONE distinct policy is a hard error, not a majority vote: it means
    two builds were concatenated, and picking one of them would publish a stamp true of half a
    board."""
    present = [c for c in _ROOKIE_POLICY_COLUMNS if c in pdf.columns]
    if not present:
        return None
    stamp: dict = {}
    for col in present:
        vals = pdf[col].dropna().unique()
        if len(vals) > 1:
            raise ValueError(
                f"board carries {len(vals)} distinct values for {col} ({list(vals)[:4]}) — two "
                f"builds appear to have been concatenated; refusing to stamp one of them")
        v = vals[0] if len(vals) else None
        if hasattr(v, "item"):          # numpy scalar → JSON-able python scalar
            v = v.item()
        stamp[_ROOKIE_POLICY_COLUMNS[col]] = v
    return stamp or None


#: NF-TR2b — the VETERAN-LEVEL policy stamp columns → payload keys (the rookie map's sibling).
_VETERAN_LEVEL_COLUMNS: dict[str, str] = {
    "veteran_level_status": "status",
    "veteran_level_form": "form",
    "veteran_level_params": "params",
    "veteran_level_window": "window_seasons",
    "veteran_level_source_model": "source_model",
    "veteran_level_decision_story": "decision_story",
    "veteran_level_statistically_selected": "statistically_selected",
    "level_model_version": "level_model_version",
}


def veteran_level_stamp(pdf: pd.DataFrame) -> dict | None:
    """The veteran-LEVEL policy block for the published payload, READ OFF THE BOARD's own stamp
    columns — `rookie_policy_stamp`'s sibling, same rules: None for a pre-NF-TR2 board (an honest
    absence), ⛔ never the policy module's values, and a board carrying two distinct policies is a
    hard error. `params` is the board's OWN fitted per-position constant (a JSON string), decoded
    here so the payload carries `{"QB": k, ...}` rather than a string-in-a-string."""
    present = [c for c in _VETERAN_LEVEL_COLUMNS if c in pdf.columns]
    if not present:
        return None
    stamp: dict = {}
    for col in present:
        vals = pdf[col].dropna().unique()
        if len(vals) > 1:
            raise ValueError(
                f"board carries {len(vals)} distinct values for {col} ({list(vals)[:4]}) — two "
                f"builds appear to have been concatenated; refusing to stamp one of them")
        v = vals[0] if len(vals) else None
        if hasattr(v, "item"):
            v = v.item()
        if col == "veteran_level_params" and isinstance(v, str):
            try:
                v = json.loads(v) if v else None
            except ValueError:
                pass
        stamp[_VETERAN_LEVEL_COLUMNS[col]] = v
    return stamp or None


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


# ══ NF-C9 — THE WEEKLY GAME-STATUS DESIGNATION, SERVED FOR DISCLOSURE ══════════════════════════
#
# NF-C8's finding, in one line: the availability discount fires on a ROSTER TRANSACTION (IR / PUP /
# NFI / suspension) and on nothing else, so a player carrying a weekly game-status designation —
# Questionable, Doubtful, Out — is projected with a discount of exactly ZERO. That is leakage-safe
# and working as designed. It is also not what a reader assumes when they meet an "Out" player at a
# normal-looking projection. We already HOLD the designation; we simply never served it.
#
# ⭐ THIS SERVES IT AND MODELS NOTHING. The projection is byte-identical before and after this
# change: `injury_availability_games` does not read this field, no ordering reads it, no VOR reads
# it. It is one string per player on the payload and a sentence in the UI saying plainly that our
# games figure does not price it in. `ablation_results/nf_c8_injury_designation_gap.md` §3 is the
# decision this implements ("a cheap, honest interim that ships nothing predictive"), including its
# ⛔: it must NOT be dressed up as a projection adjustment, because it is not one.
#
# ⚠️ NO PER-PLAYER AS-OF, AND THAT IS THE HONEST CHOICE RATHER THAN A GAP. Sleeper's feed carries no
# per-designation timestamp — the only date we can defend is when we READ THE SNAPSHOT, which is
# already served for every surface as `freshness.input_vintage.sleeper_status_as_of` (NF-FRESH2) and
# already rendered under the NF-C8 flag. Stamping a per-row date here would invent a precision the
# source does not have, and 870 copies of one board-level fact is not provenance, it is bytes.


def _norm_player_id(value) -> str:
    """⭐ THE ONE OWNER OF PLAYER-ID NORMALISATION ON THE DISCLOSURE PATH, and it exists because the
    Sleeper feed does not deliver clean ids.

    ⚠️ MEASURED ON THE LIVE SNAPSHOT (2026-08-22): **275 of 2,501 rows carry a LEADING SPACE** in
    `player_id` (`' 00-0035700'`). The gsis id is otherwise identical to the board's, so an exact
    string match — which is what this module did until now — silently matches NOTHING for those
    players, and a silent non-match on this field is indistinguishable from "the feed says nothing
    about him": the row simply renders no chip.

    It shipped that way for a few hours and the cost was concrete: **Josh Jacobs and DK Metcalf were
    both listed Questionable and both silently undisclosed** on a published board, i.e. exactly the
    high-value rows the disclosure exists for. Found by joining the published artifact back to the
    feed BY NAME, not by any test — the NF-C0e wrong-key / NF-C6P3 join-miss family, and the reason
    an id join must normalise rather than trust its source.
    """
    return str(value).strip()


def weekly_designation_map(season: int) -> "dict[str, str | None] | None":
    """`{player_id -> weekly designation label or None}`, or **None** when the feed is unreadable.

    ⭐ THE RETURN TYPE CARRIES THE THREE STATES the payload needs, and conflating any two of them is
    the whole failure mode this function is shaped to avoid:

      `None` (the whole map)   The designation feed could not be read — no ingest yet, a lake
                               failure, a season with no snapshot. NO record gets the key, so the UI
                               renders nothing per row. ⛔ Deliberately NOT "a null on every row":
                               that would put "unknown" under every player on the board during a
                               routine ingest gap, which is precisely the scary-word-everywhere
                               failure `AVAILABILITY_DATA_AS_OF_PREFIX`'s doc warns about. The
                               board-level statement already exists and is the right place for it —
                               `sleeper_status_as_of` renders "unknown" when the vintage is missing.

      key ABSENT (one player)  The feed was read and has nothing to disclose about him: no
                               designation, or a LONG-ABSENCE tag the projection already prices.
                               Both render nothing, and for the same reason — in neither case does
                               this channel have a true sentence to say (see
                               `sleeper_injuries_source.disclosable_designation`).

      value `None` (one player) The feed lists something we cannot interpret. Renders "unknown", is
                               never silently dropped (NF1.7 (a)).

    Best-effort by construction: any read failure logs and returns None. A provenance/disclosure
    enrichment must never be able to fail a board build — the boards are the draft-critical output.
    """
    from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI
    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "sleeper_injuries", tier="raw")
        con = _lake_connection()
        try:
            df = con.sql(
                f"select player_id, injury_status from delta_scan('{uri}') "
                f"where season = {int(season)} and player_id is not null"
            ).df()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001 — a disclosure stamp must never fail the export
        log.warning("[ALERT] NF-C9: weekly game-status designations unreadable (%s: %s) — the "
                    "boards will carry NO designation field, and every surface will correctly "
                    "render nothing rather than an invented status", type(e).__name__, e)
        return None

    out: dict[str, str | None] = {}
    unrecognised: dict[str, int] = {}
    for pid, status in zip(df["player_id"], df["injury_status"]):
        if pid is None or (isinstance(pid, float) and pd.isna(pid)):
            continue
        status = None if (status is None or (isinstance(status, float) and pd.isna(status))) else status
        disclose, label = SI.disclosable_designation(status)
        if not disclose:
            continue
        out[_norm_player_id(pid)] = label
        if label is None:
            unrecognised[str(status).strip().upper()] = unrecognised.get(
                str(status).strip().upper(), 0) + 1

    log.info("NF-C9 weekly designations: %d player(s) to disclose out of %d fed rows",
             len(out), len(df))
    if unrecognised:
        # ⭐ SURFACED TO THE OPERATOR, not to the reader. The UI says "unknown" (honest, and never a
        # fabricated status); this line is the only place anyone learns WHICH token we failed to
        # read, and it is what turns "add DNR to WEEKLY_DESIGNATIONS" into a visible task rather
        # than a silent shrug on somebody's board row.
        log.warning("[ALERT] NF-C9: %d player(s) carry a game-status value this build does not "
                    "recognise %s — they will render as 'unknown'. Add the token to "
                    "sleeper_injuries_source.WEEKLY_DESIGNATIONS if it is a real designation.",
                    sum(unrecognised.values()), unrecognised)
    return out


def _attach_designations(recs: list[dict], designations: "dict[str, str | None] | None") -> int:
    """Add `gameStatus` to the records the feed has something to disclose about. Returns how many.

    ⚠️ IT SETS THE KEY ONLY WHERE THERE IS SOMETHING TO SAY — no `gameStatus: null` sprayed across
    the board. See `weekly_designation_map` for why absent and null are different facts here, and
    `shared.tsx::WeeklyDesignation` for the rendering that depends on it.

    ⚠️ K/DST rows never carry one and that is a SOURCE fact, not an omission: Sleeper's feed is
    scoped to QB/RB/WR/TE (`sleeper_injuries_source._SKILL`), so it has no opinion about a kicker or
    a team defence, and an absent key is the correct rendering of "we were told nothing".
    """
    if not designations:
        return 0
    # ⚠️ NORMALISE THE MAP'S KEYS HERE TOO, not only at the one call site that builds it. The first
    # cut of this fix normalised the ROW id and trusted the map — which is safe only while every
    # caller happens to route through `weekly_designation_map`, i.e. it makes correctness a property
    # of the CALLER rather than of this function. Its own regression test caught that immediately.
    lookup = {_norm_player_id(k): v for k, v in designations.items()}
    n = 0
    for rec in recs:
        pid = _norm_player_id(rec.get("id"))
        if pid in lookup:
            rec["gameStatus"] = lookup[pid]
            n += 1
    return n


# ── build the JSON ────────────────────────────────────────────────────────────────────────────────
def board_records(
    df: pd.DataFrame,
    rookie_teams: dict[str, str] | None = None,
    byes: dict[str, int] | None = None,
    casing: dict[str, str] | None = None,
    board_names: dict[tuple[str, str], str] | None = None,
) -> list[dict]:
    """One board (already filtered to a config+size) → trimmed, display-ready player records, sorted by
    overall_rank. FB folds into RB; names title-cased; interval carried honestly. A rookie with no
    projection team is backfilled from `rookie_teams`; `bye` is the team's bye week (null until known)."""
    rookie_teams = rookie_teams or {}
    byes = byes or {}
    casing = casing or {}
    board_names = board_names or {}
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
            "name": _titlecase(r["player_name"], casing.get(pid),
                               board_names.get(_adp_key(pos, r["player_name"], team) or ("", ""))),
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


def attach_auction_values(recs: list[dict], config_name: str, n_teams: int,
                          budget: int = DEFAULT_AUCTION_BUDGET) -> int:
    """NF-C5 — stamp `aucVal` on every record of ONE board, in place.

    ⭐ ADDITIVE ONLY. A NEW key; nothing existing is removed, renamed or repurposed. The API
    Lambda has no CD (NF-C0), so the deployed client is always some previous build — a dropped or
    renamed key blanks it with a 200 and no error anywhere.

    🩹 `aucLo`/`aucHi` WERE published by the first cut and are now GONE — see `AuctionValue` for the
    measurement (the low edge was $1 for all 870 rows; the high edges summed to 412% of the room's
    money, so they were never prices). Dropping a published key is exactly what the NF-C0 rule above
    forbids, so this is deliberate and checked: NOTHING reads them. The app recomputes every dollar
    figure client-side from `vor` through the shared TS port (a board is quoted at one budget and
    converted to the user's), and a repo-wide grep finds no other consumer. Retiring two keys that
    carry a wrong number beats keeping them alive to be believed.

    ⭐ WHY THE WHOLE BOARD AND NOT JUST THE SKILL ROWS. This runs AFTER the K/DST gap-fill rows are
    folded in, so every published row carries a value. A row the model could not project has
    `vor = None` and prices at the minimum bid, which is both correct (he is free) and the only
    answer that keeps him visible on an auction board instead of blank.

    ⚠️ THE VALUES ARE QUOTED AT ONE BUDGET (`manifest.auctionBudget`), NOT AT THE USER'S. The
    client re-prices for a league on a different budget through the same shared function — the
    board is quoted in one currency and converted, rather than exported once per budget.
    """
    cfg = get_preset(config_name)
    pool = auction_pool(n_teams, cfg.roster_spots(), budget)
    for rec, val in zip(recs, auction_values(recs, pool)):
        rec["aucVal"] = val.value
    return pool.total


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
        # NF-C5 — every shipped preset is a SNAKE league; auction is a per-user choice made on the
        # auction surface, not a property of the preset. Stated rather than implied so the client
        # never has to infer a draft type from the absence of a key.
        "draftType": cfg.draft_type,
        "auctionBudget": int(cfg.auction_budget),
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


def _staged_position_coverage(blob: object) -> dict[str, int]:
    """`{position -> count of rows carrying a real projection}` for one staged board/projections blob.

    ⭐ "CARRYING A REAL PROJECTION" IS THE LOAD-BEARING HALF, and a presence-only count would make
    this guard VACUOUS on exactly the artifact it exists to catch. `kdst_records` gap-fills a
    DRAFTABLE-BUT-UNPROJECTED placeholder row for every (pos, team) the projection did not cover, so
    a board that lost the whole K/DST projection still ships 32 K + 32 DST rows — with `pts: null`.
    Counting rows would pass the broken board; counting PROJECTED rows fails it.

    `projections.json` carries no placeholders (they exist only on the league boards), so its rows
    are projected by construction and both readings agree there — which is why the same function
    serves both files."""
    rows = blob.get("players") if isinstance(blob, dict) else blob
    out: dict[str, int] = collections.Counter()
    if not isinstance(rows, list):
        return dict(out)
    for r in rows:
        if not isinstance(r, dict):
            continue
        pos = str(r.get("pos") or "")
        # A board row prices its projection in `pts`; a projections.json row in `fpPpr`. A row that
        # carries NEITHER is a placeholder (or a malformed row) and must not count as coverage.
        projected = r.get("pts") if "pts" in r else r.get("fpPpr")
        if pos and projected is not None:
            out[pos] += 1
    return dict(out)


def assert_published_position_coverage(out_dir: Path, season: int) -> None:
    """🔒 NF-K1 PUBLISH GUARD — REFUSE to ship a board that lost a whole PROJECTABLE position.

    ⭐ IT READS THE STAGED FILES OFF DISK, not the in-memory records, and that is the entire point.
    `betting_ml/tests/test_nf1_6_kdst_projection.py` has guarded the K/DST code PATH since NF1.6 and
    was green throughout this regression; the E2E fixtures still carry 42 K + 32 DST, so no test in
    the repo could see that production had neither. A guard on the code, on a fixture, or on a
    record list in memory answers a different question from "what is about to be uploaded". This one
    opens the bytes.

    THE DEFECT IT CATCHES (measured, not hypothetical — NF-K1, 2026-08-16): the first automated
    `sports_nfl_board_publish_job` run published `projections.json` with 795 players and ZERO K, ZERO
    DST, because the gitignored K/DST artifact is absent from the box image and `load_kdst_local`
    treated that as a warn-and-continue. Every step exited 0; `_verify_published` passed (it checks
    `generated_at` + `adp_as_of`, neither of which a missing position disturbs); the failure reached
    users as "not matched" beside every rostered kicker and defence.

    ⛔ IT RAISES ON A DRY RUN TOO, not only on `--publish`. A board missing a projectable position is
    defective whether or not it is uploaded, staging is where the operator can still act, and a guard
    that only fires on the publish flag cannot be exercised by the operator who wants to check first.

    ⛔ NO ESCAPE HATCH — no flag, and deliberately no env var (INC-39: an env backdoor left set turns
    the guard off silently and permanently). If a future board legitimately should not carry a
    position, that position leaves `PROJECTABLE`, which is a reviewable one-line diff rather than an
    invisible runtime state.

    The bar is ZERO, not a count threshold: any minimum would be an arbitrary number to argue about
    and to tune, while "this position vanished" is exactly the failure that occurred.

    ⚠️ SCOPE, stated because it is easy to over-read: this checks the files that WERE staged. A run
    whose `projections.json` was skipped entirely (the exporter tolerates that by design — the boards
    are the draft-critical output and the browse endpoint 404s until the blob lands) is judged on its
    board files alone. That is deliberate: a missing FILE is a loud, visible 404, whereas a file
    present with a position silently missing is the failure that reached users."""
    staged = sorted(out_dir.glob("*.json"))
    checked = [p for p in staged if p.name == "projections.json" or p.name.startswith("board_")]
    if not checked:
        # NF1.7 (a): a check that found nothing to check has not passed — it did not run.
        raise SystemExit(
            f"NF-K1 position-coverage guard found NO board/projections JSON in {out_dir} — there is "
            "nothing to publish, and an empty export must never be reported as a clean one.")

    problems: list[str] = []
    for path in checked:
        try:
            blob = json.loads(path.read_text())
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path.name}: UNREADABLE ({type(exc).__name__}: {exc}) — an "
                            "unverifiable artifact is a failure, never a pass")
            continue
        cov = _staged_position_coverage(blob)
        missing = [p for p in PROJECTABLE if cov.get(p, 0) == 0]
        if missing:
            problems.append(
                f"{path.name}: NO projected rows at {', '.join(missing)} "
                f"(have {', '.join(f'{p}={cov.get(p, 0)}' for p in PROJECTABLE)})")

    if problems:
        raise SystemExit(
            "🔴 NF-K1 PUBLISH REFUSED — the staged board is missing a whole PROJECTABLE position.\n\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nNOTHING WAS PUBLISHED. The board currently serving from S3 is untouched, which is "
            "the right outcome: a stale-but-complete board beats a fresh one that renders every "
            "rostered kicker and defence as 'not matched'.\n\n"
            "MOST LIKELY CAUSE (NF-K1): the K/DST projection did not load. It lives in its OWN "
            "artifact lineage, which nothing in the publish chain rebuilds, and it is gitignored — "
            f"so on the box it comes from the lake. Check the run log for '[ALERT] NF1.6 K/DST' and "
            f"'NF-K1', then rebuild it if the lake partition is genuinely absent:\n"
            f"  uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_kdst_projection "
            f"--projection-season {season} --s3\n"
            f"then re-run this export.")
    log.info("NF-K1 position coverage OK — every PROJECTABLE position (%s) carries a projected row "
             "in all %d staged board/projections file(s)", ", ".join(PROJECTABLE), len(checked))


def report_publish_coherence(out_dir: Path, season: int, freshness: dict | None,
                             now_iso: str, strict: bool = False) -> dict:
    """🔶 NF-INJ1 PUBLISH CHECK — does the staged board serve a physically possible (games, line) pair,
    and was it built on a current injury snapshot? ALERT-tier: it MEASURES and PAGES LOUDLY, and only
    REFUSES under `--strict-coherence`.

    ⭐ WHY ALERT AND NOT HALT, stated because the sibling guard one function up DOES halt. NF-K1
    refuses because a board missing a whole position is unusable and the remedy is a rebuild the
    operator can run in minutes. Here the defect is nine backup QBs carrying an impossible stat line
    on an otherwise sound 868-player board, and the remedy is a §0.5 model change (the ordering step
    rescales the stat line but not `proj_games` — see `projection_coherence`). Halting would freeze
    every publish until that lands, in the middle of draft season, which is a worse outcome than
    shipping a board whose defect is measured, named and visible. ⛔ THE DEFAULT IS A PM DECISION,
    not a modelling one: `--strict-coherence` exists so the operator can flip it without a code
    change, and the count rides on the manifest so the choice is never invisible.

    ⛔ It reads the STAGED BYTES (NF-K1's lesson) and it reports NOT-APPLICABLE rather than "clean"
    for the league-board blobs, which carry no counting line and on which the envelope structurally
    cannot fire."""
    summaries: dict[str, dict] = {}
    for path in sorted(out_dir.glob("*.json")):
        if path.name != "projections.json" and not path.name.startswith("board_"):
            continue
        try:
            blob = json.loads(path.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("[ALERT] NF-INJ1 coherence: %s UNREADABLE (%s) — an unverifiable artifact "
                        "is a failure, never a pass", path.name, type(exc).__name__)
            summaries[path.name] = {"applicable": False, "unreadable": True}
            continue
        rows = blob.get("players") if isinstance(blob, dict) else blob
        summaries[path.name] = _PC.coherence_summary(rows if isinstance(rows, list) else [])

    scored = {n: s for n, s in summaries.items() if s.get("applicable")}
    if not scored:
        log.warning("[ALERT] NF-INJ1 coherence: NO staged file carried a counting stat line — the "
                    "check did not run. That is not a pass (NF1.7 (a)).")
    total = 0
    for name, s in scored.items():
        log.info("%s", _PC.format_summary(s, name))
        total += int(s.get("n_violating_players", 0))

    fresh = _PC.assess_injury_input_freshness((freshness or {}).get("input_vintage"), now_iso)
    log.info("[METRIC] nf_inj1_coherence_violating_players=%d", total)
    log.info("[METRIC] nf_inj1_injury_input_freshness=%s lag_hours=%s",
             fresh["verdict"], fresh["lag_hours"])
    if total:
        log.warning("[ALERT] NF-INJ1 — %d player(s) are about to be published with a stat line that "
                    "is impossible at their own expected games. The paid /projections-full surface "
                    "serves this line verbatim. Cause: the NF1.5 ordering step rescales the stat "
                    "line to the assigned point level but leaves `proj_games` untouched "
                    "(`nf1_model._RAW_SCALE_COLS`). Fix is pre-registered as a §0.5 model change; "
                    "see ablation_results/nf_inj1_diagnosis.md.", total)
    if fresh["verdict"] != "OK":
        log.warning("[ALERT] NF-INJ1 injury input %s — %s", fresh["verdict"], fresh["detail"])

    if strict and (total or fresh["verdict"] != "OK" or not scored):
        raise SystemExit(
            "🔴 NF-INJ1 PUBLISH REFUSED (--strict-coherence).\n"
            f"  - {total} player(s) exceed the all-time realized per-game envelope\n"
            f"  - injury input: {fresh['verdict']} ({fresh['detail']})\n"
            f"  - files carrying a scorable stat line: {len(scored)}\n"
            "NOTHING WAS PUBLISHED; the board serving from S3 is untouched.")
    return {"violating_players": total, "by_file": {n: s.get("n_violating_players")
                                                   for n, s in scored.items()},
            "injury_input": fresh}


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
    # ── NF-FRESH2 P1 — the ADP column's refresh, DEFAULT ON, bounded to the current season ─────
    # Mirrors `run_nf1_5.py`'s pair. Before this, `A_fetch` omitted `refresh` entirely, so a
    # republish re-read whatever JSON was already on disk — which is how the 2026-08-10 publish
    # shipped a 2026-07-25 ADP window (NF-FRESH1 §2.2).
    ap.add_argument("--market-refresh", dest="market_refresh", action="store_true", default=True,
                    help="re-fetch the ADP samples for the CURRENT season (default; a historical "
                         "season always reads its pinned snapshot)")
    ap.add_argument("--no-market-refresh", dest="market_refresh", action="store_false",
                    help="read the on-disk ADP caches only — for reproducing an archived export")
    ap.add_argument(
        "--s3-bucket",
        default=os.getenv("CACHE_BUCKET"),
        help="S3 bucket to upload the boards to (default $CACHE_BUCKET). Uploaded under "
        "fantasy/nfl/<season>/ where the gated /fantasy/nfl/* API reads them. Resolving a "
        "bucket alone does NOT upload — pass --publish too (see below).",
    )
    ap.add_argument(
        "--strict-coherence", action="store_true",
        help="NF-INJ1: REFUSE to publish when the staged board carries a physically impossible "
             "(expected-games, stat-line) pair or was built on a stale injury snapshot. Default is "
             "ALERT-loud-but-continue — see report_publish_coherence for why that default is a PM "
             "decision rather than a modelling one.")
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

    # NF-FRESH2 P1 — arm the refresh BEFORE any ADP sample is fetched or memoized.
    set_market_refresh(args.market_refresh)

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
    # NF-C9 — the UN-MODELLED weekly game-status designation, for DISCLOSURE. Read once and shared
    # by the boards and the projections blob so the two surfaces can never disagree about what the
    # feed said (the E9.61 "two renderers of one field are two rule sets" lesson). None on any read
    # failure → no record carries the field → every surface renders nothing, never an invented
    # status. See `weekly_designation_map`.
    designations = weekly_designation_map(args.season)

    # real NFL team abbreviations from the projection (drives the K/DST placeholder set)
    teams = sorted({
        _norm_team(str(t)) for t in df["team_id"].dropna().unique()
        if str(t) not in ("", "None", "nan") and _norm_team(str(t))
    })
    # NF1.6: the placeholder set is now GAP-FILL only — see `kdst_records`. Resolved per board below
    # because a board that failed to project K/DST needs different placeholders than one that did.
    kicker_names = kicker_map()

    # E9.61: the nflverse roster's own casing, for CASE ONLY (`player_naming`). The source frame is
    # 90% ALL-CAPS and casing is not rule-recoverable from it, so without this the board publishes
    # "Ceedee Lamb" / "Dj Moore" / "Sam Laporta". Reported rather than assumed — a silent empty read
    # would just restore the old wrong names, so the repair COUNT is logged per board below.
    casing = PN.roster_casing_authority()
    log.info("name-casing authority: %d roster names", len(casing))
    # E9.61 (2nd pass): the name a DRAFT BOARD shows, for the players a drafter is actually looking
    # for. Off the SAME cached FFC sample the ADP column already pulls, keyed on the SAME crosswalk,
    # so it adds no fetch and no new matching surface. See `player_naming.drafted_as`.
    board_names = draft_board_names(args.season, PROJECTION_ADP_FORMAT, PROJECTION_ADP_TEAMS)
    log.info("draft-board names: %d", len(board_names))

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
        skill = board_records(grp, rookie_teams, byes, casing, board_names)
        # market ADP, matched to THIS board's scoring format + league size (see PRESET_ADP_FORMAT)
        adp_fmt = PRESET_ADP_FORMAT.get(config_name, "ppr")
        matched = _attach_adp(skill, adp_cache_for(args.season, adp_fmt, n_teams))
        log.info("  %s_%d: ADP (%s/%dteam) matched %d/%d players",
                 config_name, n_teams, adp_fmt, n_teams, matched, len(skill))
        # NF-C9 — disclose the weekly designation on the row whose games figure it is NOT in.
        flagged = _attach_designations(skill, designations)
        log.info("  %s_%d: %d player(s) carry a weekly game-status designation to disclose",
                 config_name, n_teams, flagged)
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
        # NF-C5 — auction dollar values, on the WHOLE board (gap-fill rows included) so an auction
        # drafter never meets a blank price. Quoted at `DEFAULT_AUCTION_BUDGET`; the client
        # re-prices any other budget through the same formula.
        room = attach_auction_values(recs, config_name, n_teams)
        log.info("  %s_%d: auction values at $%d/team (a $%d room), top $%d",
                 config_name, n_teams, DEFAULT_AUCTION_BUDGET, room,
                 max((r.get("aucVal") or 0) for r in recs) if recs else 0)
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
        # NF-K1 — `load_kdst` is LOCAL-FIRST-THEN-LAKE. The previous local-only read is exactly how
        # the 2026-08-16 automated publish shipped a board with ZERO K and ZERO DST: the artifact is
        # gitignored, so it is absent from the box image, and nothing in the publish chain writes it.
        from quant_sports_intel_models.football.nfl.fantasy.run_league_board import load_kdst
        kdf = load_kdst(_ARTIFACTS, args.season, from_lake=args.from_lake)
        if len(kdf):
            pdf = pd.concat([pdf, kdf], ignore_index=True, sort=False)
            log.info("  projections: folded in %d NF1.6 K/DST rows", len(kdf))
        projections = projection_records(pdf, rookie_teams, byes, bio, contrib_map, casing,
                                         board_names)
        # NF-C9 — the same map the boards used, so the Projections table and the player page
        # disclose exactly what Rankings does.
        log.info("  projections: %d player(s) carry a weekly game-status designation to disclose",
                 _attach_designations(projections, designations))
        # E9.61 — what the casing authority DID, so a silent S3 failure reads as a zero rather than
        # as a clean run. `repaired` counts names the rule pass ALONE would have got wrong (measured
        # against the source frame, not against the output); `kept` counts roster disagreements the
        # casefold gate deliberately refused (suffix / nickname — see `player_naming`).
        src_names = dict(zip(pdf["player_id"].astype(str), pdf["player_name"].astype(str)))
        repaired = sum(
            1 for pid, src in src_names.items()
            if PN.display_name(src, casing.get(pid)) != PN.display_name(src)
        )
        # Counted separately: a draft-board name is a DIFFERENT claim from a casing repair (it may
        # change characters), so folding the two into one number would hide which authority acted.
        renamed = sum(
            1 for p in projections
            if (b := board_names.get(_adp_key(p["pos"], p["name"], p.get("team")) or ("", "")))
            and b == p["name"]
            and b != PN.display_name(src_names.get(p["id"], p["name"]), casing.get(p["id"]))
        )
        log.info("  projections: %d name(s) taken from the draft board", renamed)
        kept = sum(
            1 for p in projections
            if (a := casing.get(p["id"])) and a.casefold() != p["name"].casefold()
        )
        log.info("  projections: casing authority repaired %d name(s); refused %d roster "
                 "disagreement(s) that were more than case (suffix/nickname — by design)",
                 repaired, kept)
        if casing and not repaired:
            log.warning("[ALERT] the name-casing authority repaired NOTHING across %d players — "
                        "expected ~30 on a 2026-shaped board. Check the roster join.", len(projections))
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
            # ── NF-FRESH2 — PER-INPUT VINTAGE ────────────────────────────────────────────────
            # ⭐ THE HONESTY FIX, not a nice-to-have. Every surface renders ONE `built <date>` from
            # `generated_at`, and on 2026-08-10 that read "built 8/10" over an ADP column whose
            # window ended 7/25 and a depth-chart view from 8/03 — one date stated over three
            # vintages, which a reader reasonably takes as covering the whole row (NF-FRESH1 §1.2).
            # These say which vintage each input actually is. A null means "we could not tell", and
            # the UI renders that as unknown — never as fresh (NF1.7(a)).
            **_freshness_meta(args.season),
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
            # ── NF-G0/NF-D21 — the ROOKIE-POLICY STAMP, READ OFF THE BUILT BOARD ──────────────────
            # ⛔ NOT read from `rookie_publish_policy` here, and the difference is the whole point:
            # importing the policy would publish what the policy SAYS, which is exactly how a payload
            # comes to describe a board it was not built from. Reading the artifact's own columns
            # means the payload can only ever claim the policy the board was ACTUALLY built at — and
            # the governance `model_stamp_consistency` gate then reconciles that against the registry.
            "rookie_policy": rookie_policy_stamp(pdf),
            # ── NF-TR2b — the VETERAN-LEVEL policy stamp, READ OFF THE BUILT BOARD (same rule).
            "veteran_level_policy": veteran_level_stamp(pdf),
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
        # NF-FRESH2 — the per-input vintage, on the MANIFEST as well as on `projections.json`,
        # because the boards ship even on a run where the projections blob is skipped, and the
        # Rankings / League Board surfaces read their provenance line from the manifest alone.
        **_freshness_meta(args.season),
        "positions": list(PROJECTABLE),
        # NF1.5b — which projection lineage EVERY blob in this export came from. Top-level (not only
        # inside `projections`) because the league boards carry it too, and they are exported even
        # when the projections blob is not.
        "projectionSource": args.projection_source,
        "projectionLabel": _PROJECTION_LABEL[args.projection_source],
        "sizes": sorted(sizes_present),
        # NF-C5 — the budget the boards' `aucVal`/`aucLo`/`aucHi` are QUOTED AT. Load-bearing: the
        # client re-prices a league on a different budget from these, and a re-price that assumed
        # the wrong base currency would be silently wrong rather than obviously so.
        "auctionBudget": DEFAULT_AUCTION_BUDGET,
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

    # 🔒 NF-K1 — the LAST thing before the upload decision, and it reads what was just written to
    # disk rather than anything held in memory. A whole projectable position going missing must
    # fail the export, not reach users as "not matched" beside every kicker and defence.
    assert_published_position_coverage(out_dir, args.season)

    # 🔶 NF-INJ1 — beside NF-K1 and for the same reason: it opens the staged bytes. ALERT-tier by
    # default (see `report_publish_coherence` for why this one measures where NF-K1 refuses); the
    # result is written back onto the manifest so the count is visible on the served payload rather
    # than living only in a run log nobody reads (the E11.30 lesson).
    _coh = report_publish_coherence(out_dir, args.season, manifest.get("freshness"),
                                    datetime.now(timezone.utc).isoformat(),
                                    strict=args.strict_coherence)
    manifest["coherence"] = _coh
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

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
