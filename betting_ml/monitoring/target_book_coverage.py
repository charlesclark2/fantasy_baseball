"""target_book_coverage.py — E9.52 TARGET-BOOK (Bovada) price-coverage classifier.

WHY THIS EXISTS (E9.52, 2026-07-29):
    `daily_model_predictions.layer4_h2h_bovada_ml_home/away` carry the REAL Bovada
    American moneyline the pick would be taken at. They went 100% NULL on every served
    row from 2026-07-25 onward while the raw odds capture, `mart_odds_outcomes` and the
    general `h2h_market_implied_prob` were all perfectly healthy — so nothing in the
    existing guard set noticed:
      * the odds-coverage guard watches the BRIDGE ATTACH (has_odds), not a per-book price;
      * the served-integrity guard watched fallback/coverage/flatness, not a book column;
      * `_load_bovada_ml_odds` catches every failure and returns {} → the columns just
        write NULL, and its own log line ("Loaded Bovada ML odds for 0 game(s)") reads
        like a benign off-day.
    Bovada is the TARGET book: with those columns blank the kill-criterion monitors
    (monitor_conviction_h2h / monitor_magnitude_h2h) skip EVERY settled bet and print
    "cannot evaluate", and the conviction-pick email prices each pick "@ Bovada n/a".
    A silently-blank target book is therefore a decision/trust failure, not a cosmetic one.

    Root cause was the INC-23 VARCHAR-timestamp class: `mart_game_odds_bridge.game_date`
    is a string-wrapped TIMESTAMP (VARCHAR '2026-07-25 00:00:00' in the S3 parquet), so
    the un-cast `where game_date = '2026-07-25'` predicate matched NOTHING on the DuckDB
    `--s3` branch while still working on the Snowflake branch (whose external table
    declares the column TIMESTAMP_NTZ). The morning tier broke at the W7B_LAKEHOUSE_S3
    flip; the intraday tier broke on 2026-07-25/26 when W7B_INTRADAY_S3 flipped — which
    is the 7/24→7/25 boundary.

WHAT THIS MODULE IS:
    The ONE definition of "the target book's price coverage is broken", shared by both
    ends of the path so they can never drift apart (the same discipline
    check_served_prediction_integrity already applies to model_health_metrics):
      * SOURCE side  — scripts/predict_today.py::_load_bovada_ml_odds alerts the moment
        the read comes back blank, before the NULLs are ever written.
      * SERVED side  — scripts/check_served_prediction_integrity.py asserts the written
        slate actually carries the price (check #5), so a future regression anywhere in
        the chain is caught the SAME MORNING.

    Import-safe (pure stdlib, no `pipeline` import) so it runs in the fast CI gate.

TIER (E11.7 pipeline failure-handling contract):
    ALERT-loud-but-continue on both sides. A missing book price must never HALT a slate —
    the pick itself is still valid, it is the ROI accounting and the emailed price that
    degrade. Promotion to HALT is the served-integrity gate's --strict switch.
"""

from __future__ import annotations

# The book every actionable H2H pick is priced against (project decision — see
# project_target_bookmaker memory / mart_odds_line_movement, which is bovada-hardcoded).
TARGET_BOOK = "bovada"

# Below this many games on the slate the fraction is too noisy to read (a doubleheader-only
# day, an off-morning re-score). Matches check_served_prediction_integrity.MIN_GAMES_FOR_CHECK.
MIN_GAMES_FOR_CHECK = 5

# Books do not always post every game, so a small shortfall is normal; this floor catches
# the gross partial. Mirrors check_odds_coverage._MIN_COVERAGE (same "attach rate" question,
# one level deeper — per-book price rather than per-game event attach).
MIN_TARGET_BOOK_COVERAGE = 0.50

# Verdicts.
OK = "OK"
PARTIAL = "PARTIAL"
BLANK = "BLANK"
SKIP = "SKIP"


def classify(n_games: int, n_priced: int, *,
             min_games: int = MIN_GAMES_FOR_CHECK,
             min_coverage: float = MIN_TARGET_BOOK_COVERAGE) -> str:
    """Verdict on one slate's target-book price coverage.

    BLANK is the E9.52 signature and is asserted at ANY slate size ≥ 1: "games exist and
    NOT ONE carries a target-book price" is unambiguous — a real books-haven't-posted
    morning still yields a partial, never a categorical zero across a whole slate, and a
    join/type bug yields exactly zero. PARTIAL (a gross shortfall) needs `min_games` rows
    before it is a verdict rather than noise.

    A slate of zero games is SKIP (off-day — nothing to price)."""
    if n_games <= 0:
        return SKIP
    if n_priced == 0:
        return BLANK
    if n_games >= min_games and (n_priced / n_games) < min_coverage:
        return PARTIAL
    return OK


def problem_message(n_games: int, n_priced: int, verdict: str, *,
                    scope: str = "slate",
                    min_coverage: float = MIN_TARGET_BOOK_COVERAGE) -> str | None:
    """Operator-facing description of a BLANK/PARTIAL verdict (None when healthy).

    `scope` names what was measured — a date for the source-side read, a serving tier for
    the served-side guard — so one message shape serves both call sites."""
    if verdict == BLANK:
        return (
            f"{scope}: the TARGET BOOK ({TARGET_BOOK}) moneyline is MISSING on ALL "
            f"{n_games} game(s) — layer4_h2h_{TARGET_BOOK}_ml_home/away write 100% NULL, so "
            f"the kill-criterion ROI monitors skip every settled bet and the conviction-pick "
            f"email prices each pick '@ {TARGET_BOOK.title()} n/a' (E9.52). Odds capture being "
            f"healthy does NOT clear this — check the bridge date predicate first "
            f"(INC-23: mart_game_odds_bridge.game_date is a string-wrapped TIMESTAMP; it must "
            f"be compared as ::date on the --s3 branch), then the bookmaker_key mapping."
        )
    if verdict == PARTIAL:
        return (
            f"{scope}: the TARGET BOOK ({TARGET_BOOK}) moneyline covers only "
            f"{n_priced}/{n_games} game(s) ({n_priced / n_games:.0%} < {min_coverage:.0%}) — "
            f"picks on the uncovered games have no real-book price for ROI accounting (E9.52)."
        )
    return None
