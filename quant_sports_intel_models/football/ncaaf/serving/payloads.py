"""payloads.py — NCAAF-P3.1: PURE builders from lake snapshot rows to served blobs.

Everything here is a pure function of a DataFrame plus an instant. No boto3, no lake read, no
clock of its own — the IO lives in `scripts/write_ncaaf_serving_store.py`, so every shape decision
in this file is testable without touching AWS (which matters more than usual: CI mocks all IO, so a
builder entangled with its writer is a builder nothing can actually exercise).

WHAT IT SERVES, AND FROM WHERE
------------------------------
  * per-game projections  ← `ncaaf/derived/game_prediction_snapshots` (NCAAF-PS; one immutable row
    per (game_id, snapshot_ts), written pre-kickoff by `sports_ncaaf_prediction_snapshot_job`)
  * the futures board     ← `ncaaf/derived/futures_board_snapshots` (the P1.5 season simulation,
    snapshotted on the same cadence)

⭐ IT RE-DERIVES NOTHING. Every probability, μ, σ and quantile is copied verbatim off the persisted
row. The served model is exactly the registered artifact — no re-scoring, no correction, no
week-conditional branch. In particular the VAL3b cold-start correction is CERTIFIED but
DEPLOY-HELD and is NOT expressible in the served contract; expressing any part of it here would
serve a model nobody deployed (that is NCAAF-VAL3c's contract change, post-opener).

⛔ AND NOTHING GROUPS BY A WEEK. CFBD restarts `week` at 1 for the postseason, and
`game_prediction_snapshot.py`'s `season_order_week` is a verbatim alias of that raw week (the
recorded alias landmine). The serving grain is the America/Los_Angeles KICKOFF DAY, which cannot
collide with itself. `cfbd_week` rides along as a display label and is never a key or an ordering.

🕐 THE LA GAME-DAY IS DERIVED FROM THE KICKOFF INSTANT, NOT FROM A UTC DATE STRING (INC-22). A
Saturday-night kickoff at 03:30 UTC Sunday is a SATURDAY game in every US timezone; slicing the
slate on the UTC date would file it under the wrong day and an app opening "today" would show an
empty board while games were being played. `current_game_date(now=<kickoff>)` does the conversion.

⚖️ ABSENT vs NULL. A game with no snapshot row is simply not in the slate (absent). A field we
have no value for is DECLARED and `null` — and where a null has more than one possible cause, it
carries a `status`/`reason` beside it (`NcaafMarketLine`). See `app/backend/models/ncaaf.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import pandas as pd

from app.backend.models import ncaaf as contract
from betting_ml.utils.game_day import current_game_date

#: The quantile ladder the snapshot persists, as (level, column-suffix) pairs. Mirrors
#: `game_prediction_snapshot.PERSISTED_QUANTILES`; pinned equal by a guard test rather than
#: imported, because importing that module drags numpy/pyarrow into a pure builder.
QUANTILE_LEVELS: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
INTERVAL_LO_LEVEL, INTERVAL_HI_LEVEL = 0.10, 0.90

#: `market.reason` values. Machine-readable so a surface can DISTINGUISH the causes of a null
#: market line instead of rendering all of them as one blank (the NF-C6b lesson).
MARKET_REASON_NO_CAPTURE = "no_line_captured_for_this_kickoff"
MARKET_REASON_READ_FAILED = "market_read_failed"
MARKET_SOURCE_CLOSE = "odds_api_historical_close"


def _q_col(target: str, level: float) -> str:
    return f"{target}_q{int(round(level * 100)):02d}"


def _f(value: Any) -> float | None:
    """A finite float, or None. NaN is NULL — never 0.0 (a fabricated zero is a wrong number that
    looks like a measurement; the honest-NULLs rule this vertical already applies to player lines)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # NaN


def _i(value: Any) -> int | None:
    f = _f(value)
    return None if f is None else int(f)


def _s(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    out = str(value)
    return out or None


def _b(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    return bool(value)


def _iso_now(now: datetime | None = None) -> str:
    ts = now or datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ══════════════════════════════════════════════════════════════════════════════════════════
# Vintage selection — the latest PRE-KICKOFF snapshot per game
# ══════════════════════════════════════════════════════════════════════════════════════════

def latest_snapshot_per_key(rows: pd.DataFrame, key: Sequence[str]) -> pd.DataFrame:
    """Collapse an append-only snapshot table to ONE row per `key` — the newest `snapshot_ts`.

    The snapshot table is append-only BY DESIGN: a game still ahead on the following week's fire is
    snapshotted again under a fresh instant, and both vintages are kept because that is what makes
    a forward track record auditable. Serving wants the most recent honest estimate, so it takes the
    newest — and takes it by comparing the ISO instant, not by relying on row order, because a Delta
    read's row order is not a guarantee.
    """
    if rows is None or rows.empty:
        return pd.DataFrame(columns=list(rows.columns) if rows is not None else [])
    df = rows.copy()
    df["_snap_sort"] = pd.to_datetime(df["snapshot_ts"], utc=True, errors="coerce")
    df = df.sort_values(["_snap_sort"], ascending=True, kind="mergesort")
    out = df.drop_duplicates(subset=list(key), keep="last").drop(columns=["_snap_sort"])
    return out.reset_index(drop=True)


def game_day_for(commence_time: Any) -> str | None:
    """The America/Los_Angeles calendar day a UTC kickoff instant belongs to (INC-22).

    ⚠️ NOT `str(commence_time)[:10]`. A 03:30 UTC kickoff is the PRIOR evening everywhere in the
    US, so the UTC date names the wrong day for every West-coast night game — which on a Saturday
    college slate is a large fraction of the marquee window.
    """
    ts = pd.to_datetime(commence_time, utc=True, errors="coerce")
    if ts is pd.NaT or pd.isna(ts):
        return None
    return current_game_date(now=ts.to_pydatetime()).isoformat()


# ══════════════════════════════════════════════════════════════════════════════════════════
# Builders
# ══════════════════════════════════════════════════════════════════════════════════════════

def _distribution(row: Mapping[str, Any], target: str) -> dict:
    levels, values = [], []
    for level in QUANTILE_LEVELS:
        v = _f(row.get(_q_col(target, level)))
        if v is None:
            continue
        levels.append(float(level))
        values.append(v)
    return {
        "mu": _f(row.get(f"mu_{target}")),
        "sigma": _f(row.get(f"sigma_{target}")),
        "quantile_levels": levels,
        "quantiles": values,
        "interval_lo_level": INTERVAL_LO_LEVEL,
        "interval_hi_level": INTERVAL_HI_LEVEL,
        "interval_lo": _f(row.get(_q_col(target, INTERVAL_LO_LEVEL))),
        "interval_hi": _f(row.get(_q_col(target, INTERVAL_HI_LEVEL))),
        "interval_width": _f(row.get(f"{target}_interval_width")),
    }


def _framing() -> dict:
    return contract.NcaafHonestFraming().model_dump()


def _provenance(row: Mapping[str, Any]) -> dict:
    return {
        "model_version": _s(row.get("model_version")),
        "model_form": _s(row.get("model_form")),
        "model_learner": _s(row.get("model_learner")),
        "model_contract": _s(row.get("model_contract")),
        "mean_artifact_version": _s(row.get("mean_artifact_version")),
        "strength_as_of_week": _i(row.get("strength_as_of_week")),
        "pace_term_active": _b(row.get("pace_term_active")),
        "n_draws": _i(row.get("n_draws")),
        "snapshot_ts": _s(row.get("snapshot_ts")),
        "snapshot_kind": _s(row.get("snapshot_kind")),
    }


def _market(market_row: Mapping[str, Any] | None, *, read_failed: bool) -> dict:
    """The market block — ALWAYS present, `unavailable` with a named reason when we have no line.

    A market line for an UPCOMING kickoff exists only if something captured one; the paid
    `/historical` capture reaches a kickoff once it is past its snapshot instant, so a slate written
    days ahead legitimately has none. That is a stated absence, not a defect, and the `reason`
    is what lets a surface say so instead of rendering a blank cell.
    """
    if market_row is None:
        return {
            "status": "unavailable",
            "reason": MARKET_REASON_READ_FAILED if read_failed else MARKET_REASON_NO_CAPTURE,
            "source": None, "snapshot_ts": None, "home_spread": None, "total": None,
            "home_moneyline_american": None, "home_moneyline_implied_probability": None,
        }
    return {
        "status": "available",
        "reason": None,
        "source": MARKET_SOURCE_CLOSE,
        "snapshot_ts": _s(market_row.get("close_snapshot_ts")),
        "home_spread": _f(market_row.get("close_home_spread")),
        "total": _f(market_row.get("close_total")),
        "home_moneyline_american": _f(market_row.get("close_home_ml_american")),
        "home_moneyline_implied_probability": _f(market_row.get("close_home_ml_prob")),
    }


def build_game_payload(row: Mapping[str, Any], *,
                       market_row: Mapping[str, Any] | None = None,
                       market_read_failed: bool = False) -> dict:
    """One persisted snapshot row → the served per-game blob (a plain dict, model-validated).

    Validating through the Pydantic model here — inside the BUILDER, not only at the router — is
    what makes the E9.41 guarantee two-sided: a field the writer forgets fails the WRITE rather
    than being discovered missing on a surface weeks later.
    """
    p_home = _f(row.get("p_home_win"))
    payload = {
        "game_id": int(row["game_id"]),
        "season": int(row["season"]),
        "game_day": game_day_for(row.get("commence_time")) or "",
        "commence_time": _s(row.get("commence_time")),
        "start_time_tbd": _b(row.get("start_time_tbd")),
        "season_type": _s(row.get("season_type")),
        "cfbd_week": _i(row.get("cfbd_week")),
        "is_neutral_site": _b(row.get("is_neutral_site")),
        "is_conference_game": _b(row.get("is_conference_game")),
        "home": {
            "team_id": _i(row.get("home_team_id")),
            "team": _s(row.get("home_team")),
            "conference": _s(row.get("home_conference")),
            "strength_margin": _f(row.get("home_strength_margin")),
            "strength_margin_sd": _f(row.get("home_strength_margin_sd")),
        },
        "away": {
            "team_id": _i(row.get("away_team_id")),
            "team": _s(row.get("away_team")),
            "conference": _s(row.get("away_conference")),
            "strength_margin": _f(row.get("away_strength_margin")),
            "strength_margin_sd": _f(row.get("away_strength_margin_sd")),
        },
        # Both sides served explicitly — a client never re-derives the away side (E9.61).
        "win_probability": {
            "home": p_home,
            "away": None if p_home is None else round(1.0 - p_home, 6),
        },
        "margin": _distribution(row, "margin"),
        "total": _distribution(row, "total"),
        "market": _market(market_row, read_failed=market_read_failed),
        "provenance": _provenance(row),
        "framing": _framing(),
    }
    return contract.NcaafGamePrediction.model_validate(payload).model_dump()


def build_slate_payloads(rows: pd.DataFrame, *, season: int, now: datetime | None = None,
                         market_by_game: Mapping[int, Mapping[str, Any]] | None = None,
                         market_read_failed: bool = False) -> dict[str, dict]:
    """Latest-vintage snapshot rows → `{game_day: slate blob}`, one entry per LA kickoff day."""
    generated_at = _iso_now(now)
    market_by_game = market_by_game or {}
    by_day: dict[str, list[dict]] = {}
    for record in rows.to_dict("records"):
        payload = build_game_payload(
            record,
            market_row=market_by_game.get(int(record["game_id"])),
            market_read_failed=market_read_failed,
        )
        if not payload["game_day"]:
            # A kickoff we cannot place on a calendar day cannot be served on one. Skipping is the
            # honest option; filing it under "today" would put a phantom game on a real slate.
            continue
        by_day.setdefault(payload["game_day"], []).append(payload)

    slates: dict[str, dict] = {}
    for game_day, games in by_day.items():
        games.sort(key=lambda g: (g.get("commence_time") or "", g["game_id"]))
        slates[game_day] = contract.NcaafSlate.model_validate({
            "sport": "ncaaf", "game_day": game_day, "season": int(season),
            "generated_at": generated_at, "n_games": len(games), "games": games,
            "framing": _framing(),
        }).model_dump()
    return slates


def build_manifest_payload(slates: Mapping[str, Mapping[str, Any]], *, season: int,
                           current_game_day: str, futures_available: bool,
                           provenance: Mapping[str, Any] | None = None,
                           now: datetime | None = None) -> dict:
    """The index a surface reads to know what exists — game DAYS, never weeks."""
    days = [{"game_day": d, "n_games": int(s.get("n_games") or 0)} for d, s in sorted(slates.items())]
    return contract.NcaafManifest.model_validate({
        "sport": "ncaaf", "season": int(season), "generated_at": _iso_now(now),
        "current_game_day": current_game_day, "game_days": days,
        "n_games_total": sum(d["n_games"] for d in days),
        "futures_available": bool(futures_available),
        "provenance": dict(provenance) if provenance else contract.NcaafModelProvenance().model_dump(),
        "framing": _framing(),
    }).model_dump()


def build_futures_payload(rows: pd.DataFrame, *, season: int, now: datetime | None = None) -> dict:
    """Latest-vintage futures-board snapshot rows → the served board blob.

    Ordered by P(national title) descending, which is P1.5's own board order — an ordering, not a
    ranking claim. `conference_title_available=False` is carried so a structural zero (a conference
    that crowns no champion) is distinguishable from a projected zero.
    """
    teams: list[dict] = []
    provenance: dict = contract.NcaafModelProvenance().model_dump()
    n_sims = None
    for record in rows.to_dict("records"):
        teams.append({
            "team_id": int(record["team_id"]),
            "team": _s(record.get("team")),
            "conference": _s(record.get("conference")),
            "strength_margin": _f(record.get("strength_margin")),
            "strength_margin_sd": _f(record.get("strength_margin_sd")),
            "expected_wins": _f(record.get("exp_wins")),
            "expected_losses": _f(record.get("exp_losses")),
            "conference_title_available": _b(record.get("conf_title_available")),
            "p_conference_title": _f(record.get("p_conf_title")),
            "p_playoff": _f(record.get("p_playoff")),
            "p_top_seed": _f(record.get("p_top_seed")),
            "p_reach_final": _f(record.get("p_reach_final")),
            "p_national_title": _f(record.get("p_natty")),
        })
        provenance = _provenance(record)
        n_sims = _i(record.get("n_sims"))
    teams.sort(key=lambda t: (-(t["p_national_title"] or 0.0), -(t["p_playoff"] or 0.0),
                              t["team"] or ""))
    return contract.NcaafFuturesBoard.model_validate({
        "sport": "ncaaf", "season": int(season), "generated_at": _iso_now(now),
        "n_sims": n_sims, "n_teams": len(teams), "teams": teams,
        "provenance": provenance, "framing": _framing(),
    }).model_dump()
