"""Bets endpoints (per-user, DynamoDB-backed).

POST /bets        — log a bet for the authenticated user
GET  /bets        — list the authenticated user's bets (newest first)
POST /users/login — login-sync: upsert the caller into the users registry

user_id is the Cognito sub from the API Gateway JWT (see app.backend.dependencies).
"""

from __future__ import annotations

import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.models.bets import Bet, BetCreate, BetUpdate, BetsResponse, LoginSyncRequest
from app.backend.services.dynamo import delete_bet, list_bets, put_bet, update_bet, upsert_user
from app.backend.services.lakehouse_read import lakehouse_query, lakehouse_query_reason

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bets"])


@router.post("/bets", response_model=Bet, status_code=201)
def create_bet(body: BetCreate, user_id: str = Depends(get_user_id)) -> Bet:
    try:
        stored = put_bet(user_id, body.model_dump())
    except ClientError as exc:
        logger.exception("DynamoDB put_bet failed")
        raise HTTPException(status_code=503, detail="Could not save bet") from exc
    return Bet(**stored)


@router.get("/bets", response_model=BetsResponse)
def get_bets(user_id: str = Depends(get_user_id)) -> BetsResponse:
    try:
        bets = list_bets(user_id)
    except ClientError as exc:
        logger.exception("DynamoDB list_bets failed")
        raise HTTPException(status_code=503, detail="Bets unavailable") from exc

    # Auto-void pending bets whose games were postponed or cancelled
    pending = [b for b in bets if b.get("outcome") is None and b.get("game_pk")]
    if pending:
        game_pks = list({b["game_pk"] for b in pending})
        pks_csv = ",".join(str(pk) for pk in game_pks)
        try:
            # E11.1-W7b: zero-Snowflake request path — read stg_statsapi_games directly
            # from the S3 lakehouse via DuckDB. FRESHNESS: stg_statsapi_games (source
            # monthly_schedule) is re-flattened to the same S3 path by the 30-min intraday
            # re-export, and the helper globs the live dir (**/*.parquet), so this read
            # picks up postponements/cancellations promptly with no special-casing.
            rows = lakehouse_query(f"""
                SELECT game_pk
                FROM baseball_data.betting.stg_statsapi_games
                WHERE game_pk IN ({pks_csv})
                  AND abstract_game_state IN ('Postponed', 'Cancelled', 'Suspended')
            """)
            voided_pks = {r["GAME_PK"] for r in rows}
            for bet in pending:
                if bet["game_pk"] in voided_pks:
                    try:
                        update_bet(user_id, bet["bet_id"], {"outcome": "void", "profit_loss": 0.0})
                        bet["outcome"] = "void"
                        bet["profit_loss"] = 0.0
                    except Exception:
                        logger.warning("Could not auto-void bet %s", bet["bet_id"])
        except Exception:
            logger.warning("Could not check game statuses for auto-void", exc_info=True)

    # Defence in depth (E9.49): one un-representable row must never blank the whole bet log.
    # `Bet` no longer inherits BetCreate's validators, so this should be unreachable — but a
    # list comprehension that raises turns a single bad row into a 500 for EVERY bet the user
    # has, which is the worst possible failure for a page whose whole job is showing them
    # their money. Skip the row, log it loudly (an unshown bet is itself a correctness bug
    # worth alerting on), and serve the rest.
    out: list[Bet] = []
    for b in bets:
        try:
            out.append(Bet(**b))
        except Exception:
            logger.error("Bet %s could not be serialized — OMITTED from the response",
                         b.get("bet_id"), exc_info=True)
    return BetsResponse(bets=out, total=len(out))


@router.delete("/bets/{bet_id}", status_code=204)
def delete_bet_endpoint(bet_id: str, user_id: str = Depends(get_user_id)) -> None:
    try:
        delete_bet(user_id, bet_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Bet not found")
    except ClientError as exc:
        logger.exception("DynamoDB delete_bet failed")
        raise HTTPException(status_code=503, detail="Could not delete bet") from exc


@router.put("/bets/{bet_id}", response_model=Bet)
def update_bet_endpoint(bet_id: str, body: BetUpdate, user_id: str = Depends(get_user_id)) -> Bet:
    try:
        updated = update_bet(user_id, bet_id, body.model_dump())
    except ValueError:
        raise HTTPException(status_code=404, detail="Bet not found")
    except ClientError as exc:
        logger.exception("DynamoDB update_bet failed")
        raise HTTPException(status_code=503, detail="Could not update bet") from exc
    return Bet(**updated)


@router.get("/props/starters")
def prop_starters(date: str, _: str = Depends(get_user_id)) -> dict:
    """Starting pitchers for a given date, for logging a strikeout prop into the Bet Log
    (E9.42 — supports back-logging a past prop within the last ~14 days).

    Returns each game's two starters with the `pitcher_id` + `game_pk` that settlement keys
    on (see settle_user_bets.py), plus name / team / opponent for the picker. Read from the
    S3 lakehouse via DuckDB (stg_statsapi_probable_pitchers, one row per game/side joined to
    stg_statsapi_games for team names) — zero-Snowflake request path. Never raises: an empty
    list on any miss, so the picker just shows "no starters" rather than 500ing — but the
    response now says WHICH it was: `degraded=true` means the lakehouse read FAILED and the
    empty list is meaningless, `degraded=false` means the date genuinely has no starters.
    Without that flag the two are byte-identical (the E9.26b silent-empty class).

    NOTE: the probable-pitcher feed is the right source (NOT mart_player_game_starts, whose
    lineup-derived position_code '1' pitcher slot is empty in the universal-DH era — the
    starter no longer bats). For a past game the probable is the actual starter in the common
    case; a scratched start simply won't settle (no game-log row) until voided.
    """
    sql = """
        WITH ranked AS (
            SELECT game_pk, side, probable_pitcher_id, probable_pitcher_name, game_date,
                   row_number() OVER (PARTITION BY game_pk, side ORDER BY ingestion_ts DESC) AS rn
            FROM baseball_data.betting.stg_statsapi_probable_pitchers
            WHERE CAST(game_date AS DATE) = CAST(%(date)s AS DATE)
              AND probable_pitcher_id IS NOT NULL
        )
        SELECT r.game_pk,
               r.probable_pitcher_id   AS pitcher_id,
               r.probable_pitcher_name AS pitcher_name,
               CASE WHEN r.side = 'home' THEN gm.home_team_name ELSE gm.away_team_name END AS team,
               CASE WHEN r.side = 'home' THEN gm.away_team_name ELSE gm.home_team_name END AS opponent,
               r.game_date AS game_date
        FROM ranked r
        LEFT JOIN baseball_data.betting.stg_statsapi_games gm ON gm.game_pk = r.game_pk
        WHERE r.rn = 1
        ORDER BY pitcher_name
    """
    rows, read_err = lakehouse_query_reason(sql, {"date": date})
    starters = [
        {
            "game_pk": r["GAME_PK"],
            "pitcher_id": r["PITCHER_ID"],
            "pitcher_name": r["PITCHER_NAME"],
            "team": r["TEAM"],
            "opponent": r["OPPONENT"],
            "game_date": str(r["GAME_DATE"])[:10] if r.get("GAME_DATE") is not None else date,
        }
        for r in rows
    ]
    # `source` identifies which build is live (the probable-pitcher feed, post-DH-fix). Extra
    # field; the frontend ignores it. If a deployed /props/starters response lacks this key, the
    # Lambda is still on the pre-fix build regardless of the (identical) empty-array shape.
    return {"date": date, "source": "probable_pitchers", "degraded": read_err is not None,
            "degraded_reason": read_err, "starters": starters}


@router.get("/props/batters")
def prop_batters(date: str, _: str = Depends(get_user_id)) -> dict:
    """Batters in a given date's posted lineups, for logging a TOTAL-BASES prop (E5.10).

    The batter-side analog of /props/starters, and the same contract: each row carries the
    `player_id` + `game_pk` settlement keys on, plus name / team / opponent for the picker.

    Source is stg_statsapi_lineups_wide (one row per game/side, nine slot columns unpivoted)
    — deliberately NOT stg_ref_players, whose S3 export is a one-shot MANUAL job on no
    schedule: it was last written 2026-06-24 and holds ZERO players whose mlb_played_last is
    2026, so every 2026 debutant is missing from it. The lineup feed names exactly the
    players who actually batted, on any date in the back-log window.

    Never raises: an empty list on any miss, so the picker shows "no batters" rather than
    500ing — and `degraded=true` distinguishes a FAILED read from a genuinely empty date
    (see /props/starters above; the E9.26b silent-empty class).
    """
    # ⚠️ ONE scan of the wide lineup table, not nine. The first cut UNION ALL'd a per-slot
    # SELECT (9 scans of a very wide table) — precisely the heavy-read profile E9.26b showed
    # can fail INSIDE the API Lambda while working fine locally, where lakehouse_query then
    # swallows it and returns []. Worse, that lesson notes a failed read on the shared DuckDB
    # singleton can take down a LATER query, so a heavy read here could zero /props/starters
    # too. Parallel `unnest` lists zip positionally in DuckDB, giving the same rows in a
    # single pass (verified: byte-identical 261 rows / 15 games on 2026-08-15).
    slot_ids = ", ".join(f"lw.slot_{i}_player_id" for i in range(1, 10))
    slot_names = ", ".join(f"lw.slot_{i}_full_name" for i in range(1, 10))
    sql = f"""
        WITH slotted AS (
            SELECT lw.game_pk,
                   lw.home_away,
                   unnest([{slot_ids}])   AS player_id,
                   unnest([{slot_names}]) AS player_name
            FROM baseball_data.betting.stg_statsapi_lineups_wide lw
            WHERE lw.game_pk IN (
                SELECT game_pk FROM baseball_data.betting.stg_statsapi_games
                WHERE CAST(official_date AS DATE) = CAST(%(date)s AS DATE)
            )
        )
        SELECT s.game_pk,
               s.player_id,
               any_value(s.player_name) AS player_name,
               CASE WHEN lower(s.home_away) = 'home' THEN any_value(gm.home_team_name)
                    ELSE any_value(gm.away_team_name) END AS team,
               CASE WHEN lower(s.home_away) = 'home' THEN any_value(gm.away_team_name)
                    ELSE any_value(gm.home_team_name) END AS opponent,
               any_value(CAST(gm.official_date AS DATE)) AS game_date
        FROM slotted s
        LEFT JOIN baseball_data.betting.stg_statsapi_games gm ON gm.game_pk = s.game_pk
        WHERE s.player_id IS NOT NULL
        GROUP BY s.game_pk, s.player_id, s.home_away
        ORDER BY player_name
    """
    rows, read_err = lakehouse_query_reason(sql, {"date": date})
    batters = [
        {
            "game_pk": r["GAME_PK"],
            "player_id": r["PLAYER_ID"],
            "player_name": r["PLAYER_NAME"],
            "team": r["TEAM"],
            "opponent": r["OPPONENT"],
            # NB no batting_slot: the single-scan query does not carry it, and the picker
            # does not show it. An always-null field is a declaration with no production
            # behind it — better absent than permanently empty.
            "game_date": str(r["GAME_DATE"])[:10] if r.get("GAME_DATE") is not None else date,
        }
        for r in rows
        if r.get("PLAYER_ID") is not None and r.get("PLAYER_NAME")
    ]
    return {"date": date, "source": "lineups_wide", "degraded": read_err is not None,
            "degraded_reason": read_err, "batters": batters}


@router.post("/users/login")
def login_sync(body: LoginSyncRequest, user_id: str = Depends(get_user_id)) -> dict:
    """Called once by the frontend post-login. sub is trusted (JWT); email is
    metadata supplied by the client (access-token claims don't carry email)."""
    try:
        upsert_user(user_id, body.email)
    except ClientError as exc:
        logger.exception("DynamoDB upsert_user failed")
        raise HTTPException(status_code=503, detail="Could not sync user") from exc
    return {"user_id": user_id, "status": "ok"}
