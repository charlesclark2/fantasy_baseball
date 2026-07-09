"""settle_user_bets.py
--------------------
Settles pending bets in the DynamoDB user-bets table against final game scores.

Bets are OLTP data and live in DynamoDB (credence-{env}-dynamo-user-bets); game
scores are OLAP data and live in Snowflake. This job bridges them:

  1. Scan the sparse GSI `gsi-pending-by-game` — only PENDING bets carry the
     `pending_game_pk` attribute, so the index contains exactly the unsettled bets.
  2. Look up final scores for those games in Snowflake (stg_statsapi_games, status
     'F').
  3. For each pending bet whose game is final: set `outcome` ('win'/'loss'/'push')
     and `profit_loss`, and REMOVE `pending_game_pk` so the bet drops out of the
     pending index. Unfinished games are left pending.

Game markets (h2h / totals) settle against the final score. Pitcher-strikeout props
(E9.42, market 'strikeouts over'/'strikeouts under') settle against the starter's actual
K total from mart_starting_pitcher_game_log — same Snowflake read path as the scores.

Called by settle_user_bets_op in pipeline/ops/daily_ingestion_ops.py, wired into
daily_ingestion_job after dbt_daily_build (scores are fresh there). Idempotent:
only bets still in the pending index are touched, so re-running is a no-op.

profit_loss convention: win → stake × (decimal_odds − 1); loss → −stake; push → 0.
decimal_odds − 1 = american_odds/100 (positive) or 100/abs(american_odds) (negative).

Env vars:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PRIVATE_KEY (PEM/base64)
    AWS_REGION                  (default us-east-1)
    USER_BETS_TABLE             (default credence-prod-dynamo-user-bets)

Exits 0 on success (including nothing to settle), 1 on error.
"""

from __future__ import annotations

import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

import boto3
import snowflake.connector
from dotenv import load_dotenv

# Local runs read creds from the repo-root .env (pipeline runs set env directly).
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
_USER_BETS_TABLE = os.environ.get("USER_BETS_TABLE", "credence-prod-dynamo-user-bets")
_PENDING_INDEX = "gsi-pending-by-game"

# E9.42: pitcher-strikeout props settle against the starter's actual K total, not the
# final score. Kept in sync with _PROP_MARKETS in app/backend/models/bets.py (defined
# locally so this box script needs no app.backend / FastAPI import).
_PROP_MARKETS = {"strikeouts over", "strikeouts under"}


def _aws_session() -> boto3.Session:
    """Prefer an explicit AWS_PROFILE over any AWS_* keys pulled in from .env.

    botocore ranks env-var credentials above named profiles, so when AWS_PROFILE
    is set we drop the .env-injected static keys to let the profile's creds win.
    """
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            os.environ.pop(k, None)
        return boto3.Session(profile_name=profile)
    return boto3.Session()


# ── Snowflake ────────────────────────────────────────────────────────────────

def _connect_snowflake() -> snowflake.connector.SnowflakeConnection:
    # INC-22 straggler cure (2026-07-05): this script previously rolled its OWN inline-key
    # PEM parser, which mishandled the box's `\n`-escaped SNOWFLAKE_PRIVATE_KEY
    # (`ValueError: Unable to load PEM file … InvalidByte(0, 92)` — a literal backslash at
    # byte 0). Delegate to the shared PATH-if-exists→inline→password resolver, which handles
    # the raw/base64/escaped inline key correctly. All queries here are fully-qualified
    # (baseball_data.betting.*), so the default schema is immaterial. See CLAUDE.md INC-22.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


def _final_scores(conn, game_pks: list[int]) -> dict[int, tuple[int, int]]:
    """game_pk -> (home_score, away_score) for games that are final.

    MLB Stats API uses 'F' (Final) and 'O' (Final/Official) — both are terminal
    scored states. Filtering on only 'F' misses games whose status advanced to 'O'
    before the settle job ran, leaving those bets permanently pending.
    """
    if not game_pks:
        return {}
    placeholders = ",".join(str(int(g)) for g in game_pks)
    sql = (
        "SELECT game_pk, home_score, away_score "
        "FROM baseball_data.betting.stg_statsapi_games "
        f"WHERE status_code IN ('F', 'O') AND game_pk IN ({placeholders}) "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL"
    )
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql)
    return {int(r["GAME_PK"]): (int(r["HOME_SCORE"]), int(r["AWAY_SCORE"])) for r in cur.fetchall()}


def _starter_strikeouts(conn, game_pks: list[int]) -> dict[tuple[int, int], int]:
    """(game_pk, pitcher_id) -> actual strikeouts for starters in the given games.

    Reads mart_starting_pitcher_game_log (grain = one row per pitcher_id/game_pk,
    starters only), the same Snowflake read path _final_scores uses. A row exists only
    once the game is played, so a pending prop whose starter has no row yet (mart lag,
    or a scratched start) simply stays pending — it is never mis-settled.
    """
    if not game_pks:
        return {}
    placeholders = ",".join(str(int(g)) for g in game_pks)
    sql = (
        "SELECT game_pk, pitcher_id, strikeouts "
        "FROM baseball_data.betting.mart_starting_pitcher_game_log "
        f"WHERE game_pk IN ({placeholders}) AND strikeouts IS NOT NULL"
    )
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql)
    return {
        (int(r["GAME_PK"]), int(r["PITCHER_ID"])): int(r["STRIKEOUTS"])
        for r in cur.fetchall()
    }


# ── Settlement math ──────────────────────────────────────────────────────────

def _prop_outcome(market: str, actual_k: int, prop_line) -> str | None:
    """Settle a pitcher-strikeout prop vs the starter's actual K total (over/under/push)."""
    if prop_line is None:
        return None
    line = float(prop_line)
    if actual_k == line:
        return "push"  # only possible on an integer line
    higher = actual_k > line
    if market == "strikeouts over":
        return "win" if higher else "loss"
    if market == "strikeouts under":
        return "loss" if higher else "win"
    return None


def _outcome(market: str, home: int, away: int, total_line) -> str | None:
    if market == "h2h home":
        return "win" if home > away else "loss"
    if market == "h2h away":
        return "win" if away > home else "loss"
    if market in ("over", "under"):
        if total_line is None:
            return None
        total = home + away
        line = float(total_line)
        if total == line:
            return "push"
        higher = total > line
        if market == "over":
            return "win" if higher else "loss"
        return "loss" if higher else "win"  # under
    return None


def _profit_loss(outcome: str, stake: Decimal, american_odds: Decimal) -> Decimal:
    if outcome == "push":
        return Decimal("0")
    if outcome == "loss":
        return (-stake).quantize(Decimal("0.01"))
    profit_mult = (american_odds / 100) if american_odds > 0 else (Decimal(100) / abs(american_odds))
    return (stake * profit_mult).quantize(Decimal("0.01"))


# ── DynamoDB ─────────────────────────────────────────────────────────────────

def _scan_pending(table) -> list[dict]:
    """All pending bets, via the sparse gsi-pending-by-game index."""
    items: list[dict] = []
    kwargs = {"IndexName": _PENDING_INDEX}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items


def main() -> int:
    table = _aws_session().resource("dynamodb", region_name=_AWS_REGION).Table(_USER_BETS_TABLE)

    try:
        pending = _scan_pending(table)
    except Exception:
        log.exception("Failed to scan pending bets")
        return 1

    if not pending:
        log.info("No pending bets to settle.")
        return 0

    game_pks = sorted({int(b["pending_game_pk"]) for b in pending})
    log.info("%s pending bet(s) across %s game(s)", len(pending), len(game_pks))

    try:
        conn = _connect_snowflake()
    except Exception:
        log.exception("Failed to connect to Snowflake")
        return 1
    try:
        scores = _final_scores(conn, game_pks)
        # Only pay for the starter-K read when a prop bet is actually pending.
        has_props = any(b.get("market") in _PROP_MARKETS for b in pending)
        strikeouts = _starter_strikeouts(conn, game_pks) if has_props else {}
    except Exception:
        log.exception("Failed to load settlement data from Snowflake")
        return 1
    finally:
        conn.close()

    settled = 0
    for bet in pending:
        gp = int(bet["pending_game_pk"])
        if gp not in scores:
            continue  # game not final yet
        market = bet["market"]
        if market in _PROP_MARKETS:
            pid = bet.get("player_id")
            if pid is None:
                log.warning("Bet %s: prop market=%s missing player_id (skipping)", bet.get("bet_id"), market)
                continue
            actual_k = strikeouts.get((gp, int(pid)))
            if actual_k is None:
                # Game is final but the starter has no game-log row yet (mart lag) or
                # did not start (scratch). Leave pending — never mis-settle.
                log.warning("Bet %s: no strikeout row for pitcher %s in game %s yet (leaving pending)",
                            bet.get("bet_id"), pid, gp)
                continue
            outcome = _prop_outcome(market, actual_k, bet.get("prop_line"))
        else:
            home, away = scores[gp]
            outcome = _outcome(market, home, away, bet.get("total_line"))
        if outcome is None:
            log.warning("Bet %s: cannot settle market=%s (skipping)", bet.get("bet_id"), market)
            continue
        pl = _profit_loss(outcome, Decimal(str(bet["stake"])), Decimal(str(bet["american_odds"])))
        try:
            table.update_item(
                Key={"user_id": bet["user_id"], "bet_id": bet["bet_id"]},
                UpdateExpression="SET outcome = :o, profit_loss = :p REMOVE pending_game_pk",
                ExpressionAttributeValues={":o": outcome, ":p": pl},
            )
            settled += 1
        except Exception:
            log.exception("Failed to settle bet %s", bet.get("bet_id"))

    log.info("Settled %s of %s pending bet(s) in %s", settled, len(pending), _USER_BETS_TABLE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
