"""probe.py — the NF-W9-0 go/no-go probe runner.

Pulls a MINIMAL slice (a few weeks of NFL and NCAAF), resolves both entities against our ids,
and writes the feasibility artifact. This is a SPIKE, not an ingest: it lands a small local
parquet and a report, touches no serving path, publishes nothing, and `best_alpha = 0`.

  uv run python -m quant_sports_intel_models.football.pff.probe \
      --league nfl --season 2024 --weeks 1,2 --out ablation_results/nf_w9_0

⛔ IT FAILS LOUD RATHER THAN REPORTING A CHEERFUL ZERO. A probe whose whole job is to answer
"can we join this?" must never answer "yes, 0 rows". `--strict` (the default) exits non-zero
when a leg pulls no games, no facet rows, or resolves nothing — because a 0% join is the exact
failure this story exists to catch, and it is indistinguishable from success in any artifact
that only reports what it found.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from . import facets as fx
from .client import PFFClient, PFFClientError
from .resolve import (
    build_pff_crosswalk, id_space_agreement, match_report,
    resolve_games, resolve_ncaaf_players, resolve_nfl_players,
)
from .schools import school_key
from ..nfl.entity.names import normalize_team

log = logging.getLogger("pff.probe")

# Column-name candidates PFF might use, per concept. We do NOT know PFF's exact field names
# before first contact, so the probe NORMALISES tolerantly and RECORDS which candidate hit —
# a hardcoded guess that silently misses is the wrong-key class, and a probe is precisely where
# the real names get discovered.
# MEASURED against the live API 2026-08-18 — `player_id`, `player`, `position`, `franchise_id`
# are the real keys; the alternates are kept as tolerant fallbacks.
FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "pff_player_id": ("player_id", "playerId", "pff_player_id", "id"),
    "pff_player_name": ("player", "player_name", "playerName", "name"),
    "pff_team": ("team_name", "team", "teamName", "club"),
    "pff_position": ("position", "pos"),
    "pff_franchise_id": ("franchise_id",),
    "routes": ("routes", "routes_run", "route_snaps"),
    "targets": ("targets", "tgt"),
    "attempts": ("attempts", "rush_attempts", "carries"),
    "snaps": ("snap_counts_offense", "snaps", "offense_snaps"),
    "adot": ("avg_depth_of_target", "adot", "average_depth_of_target"),
}


def normalise_rows(rows: list[dict], *, facet_key: str, game_id: Any) -> pd.DataFrame:
    """PFF rows → a frame carrying our canonical probe columns PLUS every original column.

    Originals are KEPT (prefixed `raw_`) so the artifact records what PFF actually sent — the
    probe's second job, after the join, is telling NF-W9-1/2/3 which fields exist.
    """
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame(index=df.index)
    hits: dict[str, str] = {}
    for canon, cands in FIELD_CANDIDATES.items():
        for c in cands:
            if c in df.columns:
                out[canon] = df[c]
                hits[canon] = c
                break
        else:
            out[canon] = pd.NA
    out = out.join(df.add_prefix("raw_"))
    out["pff_facet"] = facet_key
    out["pff_game_id"] = str(game_id)
    out.attrs["field_hits"] = hits
    return out


def _our_nfl_games(seasons: list[int]) -> pd.DataFrame:
    from ..nfl.ingest.query_lake import q, delta
    return q(
        f"select game_id, season, week, home_team, away_team from {delta('schedules')} "
        f"where season in ({','.join(str(s) for s in seasons)})"
    )


def _our_nfl_rosters() -> pd.DataFrame:
    from ..nfl.ingest.query_lake import q, delta
    return q(
        f"select season, week, gsis_id, pff_id, full_name, team, position "
        f"from {delta('weekly_rosters')}"
    )


def _our_ncaaf(table: str, seasons: list[int]) -> pd.DataFrame:
    """CFBD raw_json rows → a flat frame (the NCAAF raw tier lands JSON, not typed columns)."""
    import duckdb
    from ..ncaaf.ingest import s3io as ns3
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL delta; LOAD delta")
    con.execute(
        f"CREATE OR REPLACE SECRET pff_s3 (TYPE S3, PROVIDER credential_chain, "
        f"REGION '{ns3.DEFAULT_REGION}')"
    )
    uri = ns3.table_uri("ncaaf", table)
    seas = ",".join(str(s) for s in seasons)
    raw = con.sql(
        f"select raw_json from delta_scan('{uri}') where season in ({seas})"
    ).df()
    return pd.DataFrame([json.loads(r) for r in raw["raw_json"]])


def run_league(
    client: PFFClient, *, league: str, season: int, weeks: list[int],
    discover: bool = True, strict: bool = True,
) -> dict[str, Any]:
    """Probe one league: games → facets → resolution → report."""
    result: dict[str, Any] = {"league": league, "season": season, "weeks": weeks}

    # 1. Games
    games: list[dict] = []
    for w in weeks:
        games.extend(fx.list_games(client, league=league, season=season, week=w))
    result["games_pulled"] = len(games)
    if not games:
        msg = f"PFF returned NO games for {league} {season} weeks={weeks}"
        if strict:
            raise PFFClientError(msg + " — refusing to report a zero-row pull as a success.")
        log.warning(msg)
        return result
    gdf = pd.DataFrame(games)
    log.info("%s: %d games, columns=%s", league, len(gdf), sorted(gdf.columns)[:20])
    result["game_columns"] = sorted(gdf.columns)

    # 2. Facet catalog (discovered against a real game, not declared)
    first_game_id = _first_present(gdf, ("id", "game_id", "gameId"))
    if discover and first_game_id is not None:
        result["facet_catalog"] = fx.discover_facets(client, first_game_id)

    # 3. Crawl the probe facets
    frames: list[pd.DataFrame] = []
    field_hits: dict[str, str] = {}
    entitlement: dict[str, list[str]] = {}
    for _, g in gdf.iterrows():
        gid = _row_game_id(g)
        if gid is None:
            continue
        for facet in fx.PROBE_FACETS:
            try:
                rows, restricted = fx.fetch_facet_with_entitlement(client, facet, gid)
                if restricted:
                    entitlement.setdefault(facet.key, sorted(set(restricted)))
            except PFFClientError as exc:
                log.warning("facet %s game=%s failed: %s", facet.key, gid, str(exc)[:160])
                continue
            f = normalise_rows(rows, facet_key=facet.key, game_id=gid)
            if not f.empty:
                field_hits.update(f.attrs.get("field_hits", {}))
                frames.append(f)
    pff = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result["facet_rows"] = len(pff)
    result["field_name_hits"] = field_hits
    result["model_output_columns_stripped"] = fx.stripped_columns()
    # ⭐ The entitlement verdict — the fields PFF says this SUBSCRIPTION TIER withholds.
    result["restricted_fields_by_facet"] = entitlement
    result["opportunity_field_availability"] = _opportunity_availability(pff, entitlement)
    if pff.empty:
        msg = f"PFF returned games but ZERO facet rows for {league} {season}"
        if strict:
            raise PFFClientError(msg + " — a games list without facets is not a usable feed.")
        log.warning(msg)
        return result
    pff["season"], pff["league"] = season, league
    pff["week"] = pff["pff_game_id"].map(_week_lookup(gdf))
    # Attach the team from the GAME — the facet rows do not carry one (see build_franchise_map).
    fmap = build_franchise_map(games, league)
    resolved_team = pff["pff_franchise_id"].astype("string").str.replace(
        r"\.0$", "", regex=True).map(fmap)
    pff["pff_team"] = pff["pff_team"].where(pff["pff_team"].notna(), resolved_team)
    result["team_attach_rate"] = round(float(pff["pff_team"].notna().mean()), 4)
    if result["team_attach_rate"] < 1.0:
        log.warning(
            "only %.1f%% of PFF rows got a team from the franchise map — the name rungs are "
            "blind for the rest", 100 * result["team_attach_rate"],
        )

    # 4. Resolution
    if league == "nfl":
        rosters = _our_nfl_rosters()
        xw = build_pff_crosswalk(rosters)
        result["id_space_agreement"] = id_space_agreement(pff, xw)
        targets = rosters.rename(columns={"team": "pff_team"})[
            ["season", "week", "gsis_id", "full_name", "pff_team", "position"]
        ].rename(columns={"pff_team": "team"})
        targets["pff_team"] = targets["team"]
        resolved = resolve_nfl_players(pff, xw, targets=targets)
        id_col = "canonical_player_id"
        our = _our_nfl_games([season])
    else:
        roster = _our_ncaaf("roster", [season])
        resolved = resolve_ncaaf_players(pff, roster)
        id_col = "cfbd_athlete_id"
        og = _our_ncaaf("games", [season])
        our = og.rename(columns={"id": "game_id", "homeTeam": "home_team", "awayTeam": "away_team"})

    result["player_match"] = match_report(
        resolved, id_column=id_col, label=f"{league} players",
        opportunity_column="targets" if "targets" in resolved.columns else None,
        name_column="pff_player_name",
    )
    # The team key is league-specific and must match the one the PLAYER join used — see the
    # `team_key` note in `resolve_games` for the 0%-game-match bug this prevents.
    gres = resolve_games(
        _game_frame(gdf, season, league),
        our[["game_id", "season", "week", "home_team", "away_team"]],
        team_key=normalize_team if league == "nfl" else school_key,
    )
    result["game_match"] = {
        "games": len(gres),
        "matched": int(gres["our_game_id"].notna().sum()),
        "match_rate": round(float(gres["our_game_id"].notna().mean()), 4) if len(gres) else None,
        "unmatched_sample": gres.loc[
            gres["our_game_id"].isna(), ["season", "week", "home_team", "away_team"]
        ].head(25).to_dict("records"),
    }

    if strict and result["player_match"]["matched"] == 0:
        raise PFFClientError(
            f"{league}: pulled {len(resolved)} PFF rows and matched ZERO to our ids. A total "
            "join failure is a wrong key, not an empty feed — see id_space_agreement."
        )
    result["_frame"] = resolved
    return result


# The fields NF-W9-1/2/3 exist to consume. Availability of THESE — not row counts — is the
# go/no-go, so the probe answers it explicitly rather than leaving it to be inferred.
OPPORTUNITY_FIELDS: tuple[str, ...] = (
    "routes", "route_rate", "avg_depth_of_target", "slot_rate", "slot_snaps", "wide_rate",
    "inline_rate", "yprr", "pass_plays", "run_plays", "yards_after_contact", "yco_attempt",
    "gap_attempts", "zone_attempts", "breakaway_attempts", "designed_yards", "elusive_rating",
)


def _opportunity_availability(pff: pd.DataFrame, entitlement: dict[str, list[str]]) -> dict:
    """Which opportunity fields we actually GOT vs which PFF withheld.

    A probe that reported only "N rows pulled" would call a tier-restricted payload a success:
    the rows arrive, they simply carry none of the columns the downstream stories need.
    """
    present = {
        f for f in OPPORTUNITY_FIELDS
        if f in pff.columns and pff[f].notna().any()
    } | {
        f for f in OPPORTUNITY_FIELDS if f"raw_{f}" in pff.columns and pff[f"raw_{f}"].notna().any()
    }
    withheld = sorted({f for fields in entitlement.values() for f in fields
                       if f in OPPORTUNITY_FIELDS})
    return {
        "available": sorted(present),
        "withheld_by_tier": withheld,
        "verdict": (
            # ⚠️ Deliberately says NOT_IN_THIS_RESPONSE, not "withheld by tier". The tier reading
            # was measured WRONG (a CSV export on the same account carries all of them) — see
            # facets.fetch_facet_with_entitlement. Naming the response, not the subscription,
            # keeps the artifact honest about what was actually observed.
            "NO_OPPORTUNITY_FIELDS_IN_THIS_RESPONSE — this endpoint omits every field the "
            "downstream stories need. ⚠️ This is a property of the RESPONSE, not proof of an "
            "account entitlement: the CSV export on the same account carries them. Find the "
            "export path before concluding anything about the subscription."
            if not present and withheld else
            "FULL" if present and not withheld else
            "PARTIAL" if present else "UNKNOWN (no facet rows to judge)"
        ),
    }


def _first_present(df: pd.DataFrame, names: tuple[str, ...]):
    for n in names:
        if n in df.columns and len(df):
            return df[n].iloc[0]
    return None


def _row_game_id(row) -> Any:
    for n in ("id", "game_id", "gameId"):
        if n in row.index and pd.notna(row[n]):
            return row[n]
    return None


def _week_lookup(gdf: pd.DataFrame) -> dict:
    for idc in ("id", "game_id", "gameId"):
        if idc in gdf.columns and "week" in gdf.columns:
            return {str(k): v for k, v in zip(gdf[idc], gdf["week"])}
    return {}


# Which key on PFF's team object names the team the way OUR side does. League-specific by
# necessity, and measured: NFL `abbreviation` ("SF") matches nflverse's team codes, while NCAA
# `city` ("Notre Dame") matches CFBD's school names — NCAA's `abbreviation` is "NOTRED", which
# matches nothing on our side.
TEAM_LABEL_KEYS: dict[str, tuple[str, ...]] = {
    "nfl": ("abbreviation", "display_abbreviation", "slug"),
    "ncaa": ("city", "mid_abbreviation", "nickname", "slug"),
}


def build_franchise_map(games: list[dict], league: str) -> dict:
    """`{franchise_id: team label}` from the game list.

    ⭐ THIS IS LOAD-BEARING, NOT A CONVENIENCE. **PFF's facet rows carry NO team name** — only
    a `franchise_id` (measured live: `team`/`team_name` are absent from every facet row). So the
    team a player played for is only knowable by joining back to the GAME. Without this map the
    NCAAF school block is empty, every name rung is unusable, and the join scores a clean 0%
    — which is exactly what the first live NCAAF run did before this existed.
    """
    keys = TEAM_LABEL_KEYS.get(league, TEAM_LABEL_KEYS["nfl"])
    out: dict = {}
    for g in games:
        for side in ("home_team", "away_team"):
            t = g.get(side)
            if not isinstance(t, dict):
                continue
            fid = t.get("franchise_id") or g.get(f"{side.split('_')[0]}_franchise_id")
            if fid is None:
                continue
            for k in keys:
                if t.get(k):
                    out[str(fid)] = t[k]
                    break
    return out


def _team_label(v, league: str = "nfl") -> Any:
    """PFF nests the team as `{"abbreviation": "NYJ", "nickname": "Jets", …}`.

    Measured live: `home_team`/`away_team` are OBJECTS, not strings. Passing the dict straight
    into the team key would stringify it and match nothing — a clean, total, and utterly
    mysterious 0% game join, which is the exact failure this module keeps guarding against.
    """
    if isinstance(v, dict):
        for k in TEAM_LABEL_KEYS.get(league, TEAM_LABEL_KEYS["nfl"]):
            if v.get(k):
                return v[k]
        return pd.NA
    return v


def _game_frame(gdf: pd.DataFrame, season: int, league: str = "nfl") -> pd.DataFrame:
    out = pd.DataFrame({
        "season": gdf["season"] if "season" in gdf.columns else season,
        "week": gdf.get("week"),
        "home_team": _col(gdf, ("home_team", "homeTeam", "home")).map(
            lambda v: _team_label(v, league)),
        "away_team": _col(gdf, ("away_team", "awayTeam", "away")).map(
            lambda v: _team_label(v, league)),
    })
    return out


def _col(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for n in names:
        if n in df.columns:
            return df[n]
    return pd.Series([pd.NA] * len(df), index=df.index)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-W9-0 PFF feasibility probe (research only)")
    ap.add_argument("--league", default="nfl,ncaa", help="comma list: nfl,ncaa")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--weeks", default="1,2")
    ap.add_argument("--out", default="ablation_results/nf_w9_0")
    ap.add_argument("--no-discover", action="store_true", help="skip the facet-catalog probe")
    ap.add_argument("--no-strict", action="store_true",
                    help="report a zero-row pull instead of failing (diagnostics only)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    weeks = [int(w) for w in a.weeks.split(",") if w.strip()]
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = PFFClient()
    log.info("PFF transport=%s credential=%s", client.transport,
             "present" if client.has_credential else "ABSENT")

    report: dict[str, Any] = {"story": "NF-W9-0", "best_alpha": 0, "research_only": True,
                              "transport": client.transport, "legs": []}
    rc = 0
    for league in [l.strip() for l in a.league.split(",") if l.strip()]:
        try:
            res = run_league(client, league=league, season=a.season, weeks=weeks,
                             discover=not a.no_discover, strict=not a.no_strict)
            frame = res.pop("_frame", None)
            if frame is not None and len(frame):
                p = out_dir / f"pff_probe_{league}_{a.season}.parquet"
                frame.to_parquet(p, index=False)
                res["probe_parquet"] = str(p)
                res["probe_rows"] = len(frame)
            report["legs"].append(res)
        except Exception as exc:  # noqa: BLE001
            log.error("%s leg FAILED: %s", league, exc)
            report["legs"].append({"league": league, "failed": True, "error": str(exc)})
            rc = 1

    rp = out_dir / "nf_w9_0_probe_report.json"
    rp.write_text(json.dumps(report, indent=2, default=str))
    log.info("wrote %s", rp)
    return rc


if __name__ == "__main__":
    sys.exit(main())
