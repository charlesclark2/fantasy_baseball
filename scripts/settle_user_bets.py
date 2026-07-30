"""settle_user_bets.py
--------------------
Settles pending bets in the DynamoDB user-bets table against final game scores.

Bets are OLTP data and live in DynamoDB (credence-{env}-dynamo-user-bets); game
scores live in the S3 lakehouse (read Snowflake-free via DuckDB). This job bridges them:

  1. Scan the sparse GSI `gsi-pending-by-game` — only PENDING bets carry the
     `pending_game_pk` attribute, so the index contains exactly the unsettled bets.
  2. Look up final scores for those games in the S3 lakehouse (stg_statsapi_games,
     status_code 'F'/'O'), the SAME source the GET /bets auto-void reads.
  3. For each pending bet whose game is final: set `outcome` ('win'/'loss'/'push')
     and `profit_loss`, and REMOVE `pending_game_pk` so the bet drops out of the
     pending index. Unfinished games are left pending.

Game markets (h2h / totals) settle against the final score. Pitcher-strikeout props
(E9.42, market 'strikeouts over'/'strikeouts under') settle against the starter's actual
K total from mart_starting_pitcher_game_log — same S3 lakehouse read path as the scores.

E9.49 — the STATS-API BOXSCORE FALLBACK (why props used to sit open for 1-2 days):
mart_starting_pitcher_game_log is derived from Statcast (stg_batter_pitches) and is
rebuilt only by the heavy daily lakehouse W2 step, so it structurally LAGS a game's
final by >= 1 day — whereas the SCORE source (stg_statsapi_games) is intraday-fresh.
Result: h2h/totals settled same-night on the evening passes while a K prop on the SAME
final game stayed `open` for a day or two (audited 2026-07-29: the mart's newest
game_date was 7/27 while 7/28 was complete and 7/29's games were already Final).
So when a prop bet's game is FINAL but the mart has no row yet, we fall back to the MLB
Stats API boxscore — the authoritative K count, available minutes after the last out.
The fallback is validated, not assumed: over all 17 K-prop bets ever logged the boxscore
K agreed with the mart K on 16/16 rows the mart had, and supplied the 17th the mart was
missing. The mart stays PRIMARY (offline-consistent with every model that reads it); the
API is consulted only for the freshness gap, only for FINAL games, only for a pitcher the
boxscore itself marks as a STARTER, and only after an INDEPENDENT live Final confirmation
from the same authority — so a mis-stated Final in our own table can never settle a bet
off a partial K count. Every settled bet records `settle_source` ('mart' | 'statsapi').

Called by settle_user_bets_op — wired into BOTH daily_ingestion_job (after dbt_daily_build)
AND the evening settle_user_bets_job schedule (E11.20 phase-2a): the daily morning pass
alone left a full slate's evening finals unsettled for 12-24h, so the evening passes settle
same-night. Snowflake-free reads make the extra passes free (no warehouse wake). Idempotent:
only bets still in the pending index are touched, so re-running is a no-op.

profit_loss convention: win → stake × (decimal_odds − 1); loss → −stake; push → 0.
decimal_odds − 1 = american_odds/100 (positive) or 100/abs(american_odds) (negative).

Env vars:
    AWS_REGION       DynamoDB region (default us-east-1)
    USER_BETS_TABLE  (default credence-prod-dynamo-user-bets)
    PROP_STATSAPI_FALLBACK  '0' disables the E9.49 boxscore fallback (default on)
    (Snowflake env is NO LONGER required — scores/K totals come from the S3 lakehouse;
     DuckDB resolves S3 creds via the credential chain = the box instance role.)

CLI:
    --dry-run   audit only: log what WOULD be settled, write nothing to DynamoDB.

Exits 0 on success (including nothing to settle), 1 on error.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from dotenv import load_dotenv

# Local runs read creds from the repo-root .env (pipeline runs set env directly).
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# E11.20 phase-2a: settlement is Snowflake-FREE — game scores + starter-K totals are read
# from the S3 lakehouse via DuckDB (the canonical prediction-path reader), the SAME source
# the GET /bets auto-void already uses. So the evening settle passes (settle_user_bets_job)
# never wake the Snowflake warehouse. AWS creds only (DuckDB credential_chain = the box
# instance role / Lambda role).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from scripts.utils.lakehouse_read import duck_connect, query_upper, register_views

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


# ── Lakehouse scores (S3 + DuckDB, Snowflake-free) ───────────────────────────

# The two settlement sources, read straight from the S3 lakehouse parquet. Both are
# materialized (lakehouse/stg_statsapi_games/, lakehouse/mart_starting_pitcher_game_log/)
# and refreshed daily + intraday — the same tables the GET /bets auto-void already reads.
_SCORE_TABLES = ["stg_statsapi_games", "mart_starting_pitcher_game_log"]


def _connect_lakehouse():
    """A DuckDB connection with the two settlement source views registered over S3.

    Uses the canonical prediction-path reader (scripts/utils/lakehouse_read) so there is
    ONE connection/registration path, not a bespoke one that can drift. Snowflake-free:
    DuckDB resolves S3 creds via the credential chain (box instance role / Lambda role).
    """
    conn = duck_connect()
    register_views(conn, _SCORE_TABLES)
    return conn


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
    rows = query_upper(conn, sql)
    return {int(r["GAME_PK"]): (int(r["HOME_SCORE"]), int(r["AWAY_SCORE"])) for r in rows}


def _starter_strikeouts(conn, game_pks: list[int]) -> dict[tuple[int, int], int]:
    """(game_pk, pitcher_id) -> actual strikeouts for starters in the given games.

    Reads mart_starting_pitcher_game_log (grain = one row per pitcher_id/game_pk,
    starters only), the same S3 lakehouse read path _final_scores uses. A row exists only
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
    rows = query_upper(conn, sql)
    return {
        (int(r["GAME_PK"]), int(r["PITCHER_ID"])): int(r["STRIKEOUTS"])
        for r in rows
    }


# ── Stats API boxscore fallback (E9.49) ──────────────────────────────────────

_STATSAPI = "https://statsapi.mlb.com/api/v1"
# Finite timeouts on every call (INC-32: a network call on a scheduled-job path must never
# be able to wedge the worker). Small budget — this runs on a handful of games at most.
_HTTP_TIMEOUT = 15
# MLB Stats API terminal game states. 'F' = Final, 'O' = Game Over — the same pair the
# lakehouse score read gates on, so the two authorities are asked the same question.
_TERMINAL_CODES = {"F", "O"}


def _fallback_enabled() -> bool:
    return os.environ.get("PROP_STATSAPI_FALLBACK", "1") != "0"


def _statsapi_final_games(game_pks: list[int]) -> set[int]:
    """The subset of game_pks the LIVE Stats API schedule reports as terminal.

    An INDEPENDENT Final confirmation. Our own stg_statsapi_games could be wrong or stale
    (the postponed-DH dedup landmine is exactly this class), and settling a prop off a
    boxscore mid-game would bank a PARTIAL K count as final — the one way this fallback
    could produce a wrong answer. One batched call for every candidate game.

    Returns an empty set on any failure: no confirmation ⇒ no fallback ⇒ the bet simply
    stays pending for the next pass. Never raises.
    """
    if not game_pks:
        return set()
    try:
        import requests

        resp = requests.get(
            f"{_STATSAPI}/schedule",
            params={"sportId": 1, "gamePks": ",".join(str(g) for g in game_pks)},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        log.warning("Stats API schedule confirm failed — skipping the prop fallback this pass",
                    exc_info=True)
        return set()

    final: set[int] = set()
    for day in payload.get("dates", []) or []:
        for game in day.get("games", []) or []:
            status = game.get("status") or {}
            # codedGameState is the terminal flag; detailedState screens out a game that is
            # 'Final' only because it was Postponed/Suspended (no complete K count exists).
            if status.get("codedGameState") in _TERMINAL_CODES and status.get("detailedState") in ("Final", "Game Over", "Completed Early"):
                try:
                    final.add(int(game["gamePk"]))
                except (KeyError, TypeError, ValueError):
                    continue
    return final


def _boxscore_starter_strikeouts(game_pk: int) -> dict[int, int]:
    """pitcher_id -> strikeouts for the STARTERS of one game, from the live boxscore.

    Starters only (gamesStarted == 1), matching mart_starting_pitcher_game_log's grain —
    a reliever's K line must never settle a starter prop. Returns {} on any failure so the
    caller leaves the bet pending rather than mis-settling. Never raises.
    """
    try:
        import requests

        resp = requests.get(f"{_STATSAPI}/game/{int(game_pk)}/boxscore", timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        log.warning("Stats API boxscore fetch failed for game %s", game_pk, exc_info=True)
        return {}

    out: dict[int, int] = {}
    for side in ("home", "away"):
        players = ((payload.get("teams") or {}).get(side) or {}).get("players") or {}
        for entry in players.values():
            pitching = (entry.get("stats") or {}).get("pitching") or {}
            if not pitching or pitching.get("gamesStarted") != 1:
                continue
            ks = pitching.get("strikeOuts")
            pid = ((entry.get("person") or {}).get("id"))
            if ks is None or pid is None:
                continue
            try:
                out[int(pid)] = int(ks)
            except (TypeError, ValueError):
                continue
    return out


def _statsapi_strikeouts(pairs: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """(game_pk, pitcher_id) -> K for the pairs the mart could not answer.

    Only games the LIVE schedule independently confirms terminal are fetched.
    """
    if not pairs or not _fallback_enabled():
        if pairs:
            log.warning("PROP_STATSAPI_FALLBACK is off — %s prop bet(s) on final games "
                        "left pending", len(pairs))
        return {}
    game_pks = sorted({gp for gp, _ in pairs})
    confirmed = _statsapi_final_games(game_pks)
    resolved: dict[tuple[int, int], int] = {}
    for gp in game_pks:
        if gp not in confirmed:
            log.warning("Game %s not confirmed terminal by the live Stats API — leaving its "
                        "prop bet(s) pending", gp)
            continue
        starters = _boxscore_starter_strikeouts(gp)
        for g, pid in pairs:
            if g == gp and pid in starters:
                resolved[(g, pid)] = starters[pid]
    return resolved


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Settle pending user bets against final results.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Audit only: log what WOULD be settled, write nothing to DynamoDB.")
    args = ap.parse_args(argv)
    dry_run = args.dry_run
    if dry_run:
        log.info("DRY RUN — no DynamoDB writes will be made")

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
        conn = _connect_lakehouse()
    except Exception:
        log.exception("Failed to connect to the S3 lakehouse (DuckDB)")
        return 1
    try:
        scores = _final_scores(conn, game_pks)
        # Only pay for the starter-K read when a prop bet is actually pending.
        has_props = any(b.get("market") in _PROP_MARKETS for b in pending)
        strikeouts = _starter_strikeouts(conn, game_pks) if has_props else {}
    except Exception:
        log.exception("Failed to load settlement data from the S3 lakehouse")
        return 1
    finally:
        conn.close()

    # E9.49: for prop bets whose game is FINAL but whose starter has no mart row yet (the
    # Statcast/daily-W2 lag), resolve the K count from the live Stats API boxscore. Computed
    # ONCE up front so the fallback costs at most one schedule call + one boxscore call per
    # affected game, however many bets ride on it.
    missing_pairs = sorted({
        (int(b["pending_game_pk"]), int(b["player_id"]))
        for b in pending
        if b.get("market") in _PROP_MARKETS
        and not b.get("outcome")          # an orphaned index entry is de-indexed, not re-graded
        and b.get("player_id") is not None
        and int(b["pending_game_pk"]) in scores
        and (int(b["pending_game_pk"]), int(b["player_id"])) not in strikeouts
    })
    fallback_ks = _statsapi_strikeouts(missing_pairs)
    if fallback_ks:
        log.info("Stats API boxscore fallback resolved %s of %s prop bet(s) the mart could "
                 "not answer", len(fallback_ks), len(missing_pairs))

    settled_at = datetime.now(timezone.utc).isoformat()
    settled = 0
    # Track bets whose game is FINAL but which we still couldn't settle — the silent-failure
    # class (E11.20 phase-2a). A final game with unsettleable bets is worth a loud ALERT: it
    # means a genuine data gap (missing K row, unknown market) rather than the benign
    # "game not final yet" skip, and settlement is otherwise invisible (WARN-tier op).
    final_unsettled = 0
    orphans = 0
    for bet in pending:
        gp = int(bet["pending_game_pk"])
        # E9.49 self-heal: a bet that ALREADY carries a terminal outcome but still has
        # pending_game_pk is stuck in the sparse GSI forever — re-scanned by every pass, and
        # counted against every coverage read of "what is still open". (Found in the audit: one
        # bet settled 'push' back in June still sat in the index.) These predate the
        # phase-2a update_bet REMOVE fix; drop them out of the index rather than re-grading.
        if bet.get("outcome"):
            if dry_run:
                log.info("[DRY RUN] would de-index already-settled bet %s (outcome=%s)",
                         bet.get("bet_id"), bet.get("outcome"))
                orphans += 1
                continue
            try:
                table.update_item(
                    Key={"user_id": bet["user_id"], "bet_id": bet["bet_id"]},
                    UpdateExpression="REMOVE pending_game_pk",
                )
                orphans += 1
            except Exception:
                log.exception("Failed to de-index already-settled bet %s", bet.get("bet_id"))
            continue
        if gp not in scores:
            continue  # game not final yet — the benign, expected skip
        market = bet["market"]
        source = "mart"
        if market in _PROP_MARKETS:
            pid = bet.get("player_id")
            if pid is None:
                log.warning("Bet %s: prop market=%s missing player_id (skipping)", bet.get("bet_id"), market)
                final_unsettled += 1
                continue
            actual_k = strikeouts.get((gp, int(pid)))
            if actual_k is None:
                # E9.49: the mart lags the game's final by >= 1 day (Statcast → daily W2), so
                # fall back to the live boxscore. Still None ⇒ the API could not confirm the
                # game terminal, or the pitcher did not START (a scratch): leave pending, never
                # mis-settle.
                actual_k = fallback_ks.get((gp, int(pid)))
                source = "statsapi"
            if actual_k is None:
                log.warning("Bet %s: no strikeout row for pitcher %s in game %s yet, and the "
                            "Stats API fallback could not resolve it (leaving pending)",
                            bet.get("bet_id"), pid, gp)
                final_unsettled += 1
                continue
            outcome = _prop_outcome(market, actual_k, bet.get("prop_line"))
        else:
            home, away = scores[gp]
            outcome = _outcome(market, home, away, bet.get("total_line"))
        if outcome is None:
            log.warning("Bet %s: cannot settle market=%s (skipping)", bet.get("bet_id"), market)
            final_unsettled += 1
            continue
        pl = _profit_loss(outcome, Decimal(str(bet["stake"])), Decimal(str(bet["american_odds"])))
        if dry_run:
            log.info("[DRY RUN] would settle bet %s (%s, game %s) → %s, P/L %s [source=%s]",
                     bet.get("bet_id"), market, gp, outcome, pl, source)
            settled += 1
            continue
        try:
            # settled_at makes settlement LATENCY observable (E9.49: a prop sitting open for
            # 1-2 days was invisible precisely because nothing recorded when a bet closed).
            # if_not_exists so a re-settle can never rewrite the canonical close time.
            table.update_item(
                Key={"user_id": bet["user_id"], "bet_id": bet["bet_id"]},
                UpdateExpression=(
                    "SET outcome = :o, profit_loss = :p, settled_at = if_not_exists(settled_at, :t), "
                    "settle_source = :s REMOVE pending_game_pk"
                ),
                ExpressionAttributeValues={":o": outcome, ":p": pl, ":t": settled_at, ":s": source},
            )
            settled += 1
        except Exception:
            log.exception("Failed to settle bet %s", bet.get("bet_id"))
            final_unsettled += 1

    # ALERT-loud-but-continue (CLAUDE.md pipeline-failure contract): if any bet's game is
    # FINAL yet unsettled, surface it to stderr so a real settlement gap is visible rather
    # than silently deferred to the next pass. Not an exit-1 — a partial gap must not fail
    # the op (predictions/serving are unaffected) and the next evening pass retries.
    if final_unsettled:
        print(f"[ALERT] settle_user_bets: {final_unsettled} bet(s) on FINAL games left "
              f"unsettled (missing K row / unknown market / write error) — see warnings above",
              file=sys.stderr)

    if orphans:
        log.info("De-indexed %s already-settled bet(s) stuck in the pending index", orphans)
    log.info("Settled %s of %s pending bet(s) in %s", settled, len(pending), _USER_BETS_TABLE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
