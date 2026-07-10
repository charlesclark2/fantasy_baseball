"""Parlay decision-support calculator — Edge Program Story E10.1 (honest MVP).

A STATELESS calculator that tells the user the TRUTH about a parlay they build: our model's estimate
of its true combined probability (same-game legs correlation-adjusted, never the naive product) next
to the book's implied probability from the parlay price, the expected value, and a plain-language
verdict. Education / transparency — NOT a bet recommendation (that is E10.3, hard-gated behind a
proven advantage we do not have; `best_alpha = 0` holds).

Endpoints:
  GET  /parlay/legs      — the leg universe for a slate (games × markets × sides that carry a served
                           model probability), enriched with per-BOOK American odds + de-vigged
                           implied % + the model's probability at that book's line, plus the list of
                           books to choose from. Read from the SERVING CACHE.
  POST /parlay/evaluate  — evaluate a user-built parlay: re-resolve each leg's model probability from
                           the serving cache (at the selected book's line for totals), then compute
                           combined true prob + implied + EV + verdict.

🔒 SERVING-CACHE ONLY. Per-leg model probabilities + per-book odds come from the DynamoDB → S3 serving
cache (`picks/today`, `picks/book-odds/{game_pk}`, `pitcher_k_projection/index`) — the same blobs the
picks / odds-comparison / props pages read, deduped to latest per game. No `daily_model_predictions` /
mart / lakehouse query, so the calculator is insulated from the E11.20 Delta migration. No serving-store
write, no dbt, no box.

🔒 HONEST FRAMING. Every response carries `best_alpha = 0`, `is_bet_recommendation = False`, and the
"most parlays are −EV after vig" disclaimer (baked in `parlay_calc`). The per-leg model-% vs book-% is
a transparency comparison, never framed as an edge / +EV / value play. The banned-language guard
(test_parlay_serving.py) fails the build on any +EV/value/edge/bet-rec wording here or on the frontend.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day

from app.backend.dependencies import get_user_id
from app.backend.models.parlay import ParlayEvaluateRequest
from app.backend.services import parlay_calc as pm  # pure-stdlib math (no numpy/scipy — Lambda-safe)
from app.backend.services import serving_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parlay", tags=["parlay"])

_VALID_SIDES = {
    "h2h": {"home", "away"},
    "totals": {"over", "under"},
    "strikeouts": {"over", "under"},
}

# Display order for the book selector — US-bettable books first, the sharp reference (Pinnacle) last.
# Bovada is the documented target book, so it leads (and is the default selection when present).
_BOOK_PREF = ["bovada", "betmgm", "fanduel", "draftkings", "caesars", "fanatics", "pinnacle"]

# Fallback display names for books that appear only in the K-prop feed (its comparison rows carry the
# bookmaker_key but no display name); the h2h/totals blobs supply names for the rest.
_BOOK_DISPLAY = {
    "bovada": "Bovada", "betmgm": "BetMGM", "fanduel": "FanDuel", "draftkings": "DraftKings",
    "caesars": "Caesars", "fanatics": "Fanatics", "pinnacle": "Pinnacle",
}


def _one_minus(x) -> float | None:
    return None if x is None else round(1.0 - float(x), 6)


# ---------------------------------------------------------------------------
# Serving-cache lookups (DynamoDB → S3). Dedup-to-latest per (game_pk, market_type).
# ---------------------------------------------------------------------------

def _picks_blob(date: str) -> list[dict]:
    """Today's served picks for `date` (the `picks/today` blob), deduped to one row per
    (game_pk, market_type). Latest-inserted wins (the blob is already latest-written; dedup guards)."""
    blob = serving_cache.get_cache("picks/today", date) or {}
    picks = blob.get("picks") or []
    seen: dict[tuple, dict] = {}
    for p in picks:
        key = (p.get("game_pk"), p.get("market_type"))
        if key[0] is None or key[1] is None:
            continue
        seen.setdefault(key, p)
    return list(seen.values())


def _book_odds_blob(game_pk: int) -> dict:
    """The per-book odds comparison blob for one game (`picks/book-odds/{game_pk}`) — all books' h2h +
    totals American lines, de-vigged implied %, and the model's P recomputed at each book's line.
    Latest-available wins (mirrors the /odds-comparison endpoint)."""
    return serving_cache.get_cache_latest(f"picks/book-odds/{game_pk}") or {}


def _k_index(date: str) -> list[dict]:
    """The K-projection index rows for `date` (or the latest available)."""
    payload = serving_cache.get_cache("pitcher_k_projection/index", date)
    if not payload:
        payload = serving_cache.get_cache_latest("pitcher_k_projection/index")
    return (payload or {}).get("pitchers") or []


def _k_detail_blob(pitcher_id: int, date: str) -> dict:
    """A pitcher's full K-projection payload for `date` (or latest) — carries `book_comparisons`, the
    per-book posted strikeout line + over/under price + de-vigged implied + model P at that line."""
    payload = serving_cache.get_cache(f"pitcher_k_projection/{pitcher_id}", date)
    if not payload:
        payload = serving_cache.get_cache_latest(f"pitcher_k_projection/{pitcher_id}")
    return payload or {}


def _k_comparison_row(detail: dict, book_key: str, line: float | None) -> dict | None:
    """The book_comparisons row for a book at a given posted line (or that book's first row when
    `line` is None), else None."""
    for c in detail.get("book_comparisons") or []:
        if c.get("book") != book_key or c.get("over_odds") is None and c.get("under_odds") is None:
            continue
        if line is None or (c.get("line") is not None and float(c["line"]) == float(line)):
            return c
    return None


def _k_books(detail: dict, line: float, book_names: dict) -> tuple[dict, dict]:
    """Per-book odds maps for the over / under strikeout sides AT the given (primary) line. Each entry
    is {american, book_devig_prob, model_prob, line}; also records book display names into `book_names`."""
    over: dict[str, dict] = {}
    under: dict[str, dict] = {}
    for c in detail.get("book_comparisons") or []:
        bk = c.get("book")
        if not bk or c.get("line") is None or float(c["line"]) != float(line):
            continue
        book_names.setdefault(bk, {"book_key": bk, "book_name": _BOOK_DISPLAY.get(bk, bk.title()),
                                   "is_sharp_reference": bk == "pinnacle"})
        bimp = c.get("book_implied_p_over")
        if c.get("over_odds") is not None:
            over[bk] = {"american": c.get("over_odds"), "line": float(line),
                        "book_devig_prob": bimp, "model_prob": c.get("model_p_over")}
        if c.get("under_odds") is not None:
            under[bk] = {"american": c.get("under_odds"), "line": float(line),
                         "book_devig_prob": _one_minus(bimp), "model_prob": c.get("model_p_under")}
    return over, under


def _h2h_book_row(blob: dict, book_key: str) -> dict | None:
    for r in blob.get("h2h") or []:
        if r.get("book_key") == book_key and r.get("home_american") is not None:
            return r
    return None


def _totals_book_row(blob: dict, book_key: str) -> dict | None:
    for r in blob.get("totals") or []:
        if r.get("book_key") == book_key and r.get("over_american") is not None:
            return r
    return None


# ---------------------------------------------------------------------------
# GET /parlay/legs — leg universe (per-book odds + model-vs-book)
# ---------------------------------------------------------------------------

def _h2h_books(blob: dict) -> tuple[dict, dict, dict]:
    """Per-book odds maps for the home / away h2h sides + the {book_key: book_name} it saw.

    Each side map is {book_key: {american, book_devig_prob, model_prob, line=None}}. `book_devig_prob`
    is the no-vig implied probability (the honest apples-to-apples number vs the model). `model_prob`
    is the model's P(home win) (book-independent) oriented to the side."""
    home: dict[str, dict] = {}
    away: dict[str, dict] = {}
    names: dict[str, dict] = {}
    for r in blob.get("h2h") or []:
        bk = r.get("book_key")
        if not bk:
            continue
        names[bk] = {"book_key": bk, "book_name": r.get("book_name") or bk,
                     "is_sharp_reference": bool(r.get("is_sharp_reference"))}
        if r.get("home_american") is not None:
            home[bk] = {"american": r.get("home_american"),
                        "book_devig_prob": r.get("market_bet_pct_home"),
                        "model_prob": r.get("model_prob_home"), "line": None}
        if r.get("away_american") is not None:
            away[bk] = {"american": r.get("away_american"),
                        "book_devig_prob": _one_minus(r.get("market_bet_pct_home")),
                        "model_prob": _one_minus(r.get("model_prob_home")), "line": None}
    return home, away, names


def _totals_books(blob: dict) -> tuple[dict, dict, dict]:
    """Per-book odds maps for the over / under totals sides + {book_key: book_name}. Each entry carries
    that book's own `line` and the model's P(over/under) recomputed at THAT line."""
    over: dict[str, dict] = {}
    under: dict[str, dict] = {}
    names: dict[str, dict] = {}
    for r in blob.get("totals") or []:
        bk = r.get("book_key")
        if not bk:
            continue
        names[bk] = {"book_key": bk, "book_name": r.get("book_name") or bk,
                     "is_sharp_reference": bool(r.get("is_sharp_reference"))}
        if r.get("over_american") is not None:
            over[bk] = {"american": r.get("over_american"), "line": r.get("line"),
                        "book_devig_prob": r.get("market_bet_pct_over"),
                        "model_prob": r.get("model_prob_over")}
        if r.get("under_american") is not None:
            under[bk] = {"american": r.get("under_american"), "line": r.get("line"),
                         "book_devig_prob": _one_minus(r.get("market_bet_pct_over")),
                         "model_prob": r.get("model_prob_under")}
    return over, under, names


@router.get("/legs")
def get_parlay_legs(date: str | None = None, _: str = Depends(get_user_id)) -> dict:
    """Return the selectable parlay legs for a slate — games × markets × sides that carry a served
    model probability — enriched with per-BOOK American odds, the book's de-vigged implied %, and the
    model's probability at that book's line, plus the list of books to choose from.

    Read order: DynamoDB serving cache → S3. Markets: moneyline (h2h) + total runs (totals) from
    `picks/today` enriched by `picks/book-odds/{game_pk}`; pitcher strikeouts (E5.5) from the
    K-projection index (model prob only — the user enters those odds). Honest framing: best_alpha=0,
    is_bet_recommendation=False; the per-leg model-vs-book % is a transparency comparison, not an edge.
    """
    slate = date or current_game_date_iso()
    games: dict[int, dict] = {}
    book_names: dict[str, dict] = {}

    def _game(game_pk: int, home: str | None, away: str | None, start_utc=None) -> dict:
        g = games.get(game_pk)
        if g is None:
            g = {"game_pk": game_pk, "home_team": home, "away_team": away,
                 "game_start_utc": start_utc, "markets": []}
            games[game_pk] = g
        return g

    # h2h + totals from picks/today, enriched with per-book odds from the book-odds blob.
    for p in _picks_blob(slate):
        gp = p.get("game_pk")
        mt = p.get("market_type")
        mp = p.get("model_prob")
        if gp is None or mp is None or mt not in ("h2h", "totals"):
            continue
        g = _game(gp, p.get("home_team"), p.get("away_team"), p.get("game_start_utc"))
        blob = _book_odds_blob(gp)
        if mt == "h2h":
            home_books, away_books, names = _h2h_books(blob)
            book_names.update(names)
            g["markets"].append({
                "market_type": "h2h", "label": "Moneyline", "line": None,
                "sides": [
                    {"side": "home", "team": p.get("home_team"),
                     "model_prob": round(float(mp), 4), "books": home_books},
                    {"side": "away", "team": p.get("away_team"),
                     "model_prob": round(1.0 - float(mp), 4), "books": away_books},
                ],
            })
        else:  # totals
            over_books, under_books, names = _totals_books(blob)
            book_names.update(names)
            g["markets"].append({
                "market_type": "totals", "label": "Total Runs",
                "line": p.get("market_total_line"),
                "sides": [
                    {"side": "over", "model_prob": round(float(mp), 4), "books": over_books},
                    {"side": "under", "model_prob": round(1.0 - float(mp), 4), "books": under_books},
                ],
            })

    # strikeouts (E5.5) — enriched with each book's posted K line + over/under price at the pitcher's
    # primary (most-common) line, from the per-pitcher K detail blob.
    for row in _k_index(slate):
        gp = row.get("game_pk")
        line = row.get("primary_line")
        p_over = row.get("model_p_over")
        pid = row.get("pitcher_id")
        if gp is None or line is None or p_over is None or pid is None:
            continue
        over_books, under_books = _k_books(_k_detail_blob(pid, slate), float(line), book_names)
        g = _game(gp, None, None, row.get("game_datetime"))
        g["markets"].append({
            "market_type": "strikeouts",
            "label": f"{row.get('full_name') or 'Pitcher'} Strikeouts",
            "pitcher_id": pid, "pitcher_name": row.get("full_name"),
            "line": float(line),
            "sides": [
                {"side": "over", "model_prob": round(float(p_over), 4), "books": over_books},
                {"side": "under", "model_prob": round(1.0 - float(p_over), 4), "books": under_books},
            ],
        })

    # Book selector — union across games, US books first (Bovada leads), Pinnacle (sharp ref) last.
    def _rank(bk: str) -> int:
        return _BOOK_PREF.index(bk) if bk in _BOOK_PREF else len(_BOOK_PREF)
    books = sorted(book_names.values(), key=lambda b: (_rank(b["book_key"]), b["book_key"]))
    us_books = [b["book_key"] for b in books if not b["is_sharp_reference"]]
    default_book = "bovada" if "bovada" in us_books else (us_books[0] if us_books else None)

    ordered = sorted(games.values(), key=lambda g: (str(g.get("game_start_utc") or "~"), g["game_pk"]))
    return {
        "date": slate,
        "books": books,
        "default_book_key": default_book,
        "games": ordered,
        "caption": pm.CAPTION,
        "disclaimer": pm.DISCLAIMER,
        "best_alpha": 0,
        "is_bet_recommendation": False,
    }


# ---------------------------------------------------------------------------
# POST /parlay/evaluate — evaluate a user-built parlay
# ---------------------------------------------------------------------------

def _resolve_leg(leg, picks_by_key: dict[tuple, dict], k_by_pitcher: dict[int, dict], date: str) -> dict:
    """Resolve one leg from the serving cache → (oriented hit_prob, book_odds, line, display fields).

    * h2h:    model P(home win) from picks/today (book-independent); odds from the selected book.
    * totals: model P(over/under) recomputed at the SELECTED BOOK's line (picks/book-odds); odds too.
              Falls back to the picks/today consensus prob when the book row is unavailable.
    * strikeouts: model P from the K index (primary line); odds are user-entered (per-book K lines vary).
    A leg whose model probability isn't in the cache resolves with hit_prob=None (excluded gracefully).
    """
    mt = leg.market_type
    side = (leg.side or "").lower()
    book_key = leg.book_key
    out: dict = {"hit_prob": None, "book_odds_american": leg.book_odds_american,
                 "line": leg.line, "home_team": None, "away_team": None, "pitcher_name": None}

    if mt == "h2h":
        p = picks_by_key.get((leg.game_pk, "h2h"))
        if not p:
            return out
        out["home_team"], out["away_team"] = p.get("home_team"), p.get("away_team")
        out["hit_prob"] = pm.oriented_hit_prob("h2h", side, p.get("model_prob"))
        if out["book_odds_american"] is None and book_key and leg.game_pk is not None:
            row = _h2h_book_row(_book_odds_blob(leg.game_pk), book_key)
            if row:
                out["book_odds_american"] = row.get("home_american") if side == "home" else row.get("away_american")
        return out

    if mt == "totals":
        row = _totals_book_row(_book_odds_blob(leg.game_pk), book_key) if (book_key and leg.game_pk is not None) else None
        if row is not None:
            out["line"] = row.get("line")
            mp_over = row.get("model_prob_over")
            out["hit_prob"] = mp_over if side == "over" else _one_minus(mp_over) if mp_over is not None else None
            if out["book_odds_american"] is None:
                out["book_odds_american"] = row.get("over_american") if side == "over" else row.get("under_american")
        else:  # fall back to the consensus-line model prob from picks/today
            p = picks_by_key.get((leg.game_pk, "totals"))
            if p:
                out["line"] = out["line"] if out["line"] is not None else p.get("market_total_line")
                out["hit_prob"] = pm.oriented_hit_prob("totals", side, p.get("model_prob"))
        return out

    if mt == "strikeouts":
        row = k_by_pitcher.get(leg.pitcher_id) if leg.pitcher_id is not None else None
        if not row or row.get("model_p_over") is None:
            return out
        primary = row.get("primary_line")
        out["pitcher_name"] = row.get("full_name")
        out["line"] = leg.line if leg.line is not None else primary
        # Auto-fill the odds + use the model P at the SELECTED BOOK's posted line, from the K detail
        # blob's per-book comparison rows (mirrors the totals book-line handling).
        if book_key and leg.pitcher_id is not None:
            comp = _k_comparison_row(_k_detail_blob(leg.pitcher_id, date), book_key, out["line"])
            if comp is not None:
                out["line"] = comp.get("line", out["line"])
                mp_over = comp.get("model_p_over")
                out["hit_prob"] = mp_over if side == "over" else _one_minus(mp_over) if mp_over is not None else None
                if out["book_odds_american"] is None:
                    out["book_odds_american"] = comp.get("over_odds") if side == "over" else comp.get("under_odds")
                if out["hit_prob"] is not None:
                    return out
        # Fallback: the index model prob at the primary line (a non-primary line has no served prob).
        if leg.line is not None and primary is not None and float(leg.line) != float(primary):
            return out  # excluded gracefully
        out["line"] = primary
        out["hit_prob"] = pm.oriented_hit_prob("strikeouts", side, row.get("model_p_over"))
        return out

    return out


@router.post("/evaluate")
def evaluate_parlay(req: ParlayEvaluateRequest, _: str = Depends(get_user_id)) -> dict:
    """Evaluate a user-built parlay. Re-resolves each leg's MODEL probability from the serving cache
    (authoritative — at the selected book's line for totals), then returns the true combined
    probability (same-game legs correlation-adjusted + source-stamped), the book-implied probability +
    expected value from the parlay price, and an honest plain-language verdict.

    Cross-game price is computed from the leg odds; a same-game parlay's price must be entered
    (`parlay_odds_american`) — the book prices it with its own correlation model (E10.2 gap).
    """
    if not req.legs:
        raise HTTPException(status_code=400, detail="At least one leg is required.")
    for leg in req.legs:
        if leg.market_type not in _VALID_SIDES:
            raise HTTPException(status_code=400, detail=f"Unknown market_type: {leg.market_type!r}")
        if (leg.side or "").lower() not in _VALID_SIDES[leg.market_type]:
            raise HTTPException(status_code=400, detail=f"Invalid side {leg.side!r} for market {leg.market_type!r}")

    slate = req.date or current_game_date_iso()
    picks_by_key = {(p.get("game_pk"), p.get("market_type")): p for p in _picks_blob(slate)}
    k_by_pitcher = {r.get("pitcher_id"): r for r in _k_index(slate) if r.get("pitcher_id") is not None}

    math_legs: list[dict] = []
    for leg in req.legs:
        r = _resolve_leg(leg, picks_by_key, k_by_pitcher, slate)
        math_legs.append({
            "game_pk": leg.game_pk,
            "market_type": leg.market_type,
            "side": (leg.side or "").lower(),
            "book_key": leg.book_key,
            "hit_prob": r["hit_prob"],
            "book_odds_american": r["book_odds_american"],
            "line": r["line"],
            "label": leg.label,
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "pitcher_name": r["pitcher_name"],
        })

    return pm.evaluate_parlay(math_legs, user_parlay_american=req.parlay_odds_american)
