"""realized_player_pbp.py — the PLAY-DERIVED long-touchdown bonuses (NF-WK-ACC1 part 3).

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS SUPPLIES, AND WHY NOTHING ELSE CAN
═══════════════════════════════════════════════════════════════════════════════════════════════════

Three scorer keys — `pass_td_40p`, `rush_td_40p`, `rec_td_40p` — are 40+ YARD TOUCHDOWN counts. They
are the largest remaining term in the recap's disclosed gap after part 1 closed `fum`, and they are
the last player-side term with a mechanical source.

They are a PLAY-LEVEL fact. `stats_player_week` is one row per player-week and carries no column
that means "how many of this player's touchdowns travelled 40+ yards", so the term cannot be
supplied from the realized line at any grain. `pbp` can, and this module is that derivation.

───────────────────────────────────────────────────────────────────────────────────────────────────
🕳️ THE WRONG-KEY THIS REPLACES, AND THE SECOND AUTHORITY THAT CORROBORATES IT
───────────────────────────────────────────────────────────────────────────────────────────────────

`stats_player_week` DOES carry `passing_40` / `rushing_40` / `receiving_40`, and they are the
nearest-looking columns to these three keys. They count 40+ yard PLAYS, not 40+ yard TOUCHDOWNS.
`realized_stat_fields`'s header records the measurement that settled it (on 2025 REG, `passing_40`
EXCEEDS `passing_tds` on 36 player-weeks and `receiving_40` exceeds `receiving_tds` on 108 —
impossible for a subset of the touchdown count).

⭐ A SECOND, INDEPENDENT AUTHORITY AGREES, measured 2026-09-18: Sleeper's own stat vocabulary carries
BOTH spellings as SEPARATE keys — `rec_40p` / `rush_40p` / `pass_cmp_40p` (the play counts) beside
`rec_td_40p` / `rush_td_40p` / `pass_td_40p` (the touchdown counts). The platform whose league we are
reproducing distinguishes exactly the two quantities the wrong-key would have conflated, which is
about as direct a confirmation as the distinction can get.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐⭐ THE RULE, AND THE LATERAL CASE THAT WOULD HAVE SHIPPED WRONG AND BEEN INVISIBLE
───────────────────────────────────────────────────────────────────────────────────────────────────

A play contributes when it is a touchdown of at least `LONG_TD_YARDS` yards:

  * `pass_touchdown = 1` → `pass_td_40p` to the PASSER and `rec_td_40p` to the RECEIVER (one play
    pays two different managers, which is why the two keys exist separately and why their season
    totals are equal at the league level).
  * `rush_touchdown = 1` → `rush_td_40p` to the RUSHER.
  * a touchdown that is NEITHER (an interception / fumble / kick return) contributes to none of the
    three. Measured: 2 such plays in the whole lake, both correctly excluded by the two flags.

⚠️⚠️ THE RECEIVER AND RUSHER ARE THE **LATERAL** PLAYER WHERE ONE EXISTS. On a play that ends with a
lateral, the touchdown belongs to whoever crossed the line, not to the player who caught the pass —
and nflverse records that in `lateral_receiver_player_id` / `lateral_rusher_player_id`, leaving the
primary column pointing at the first player. Crediting the primary is the natural implementation and
it is WRONG.

⭐ IT WAS SETTLED BY MEASUREMENT, NOT BY READING THE COLUMN NAMES, and the measurement was only
possible because Sleeper publishes per-player figures. 2024 week 17, DET: Goff completes 1 yard to
Amon-Ra St. Brown, who laterals to Jameson Williams for 41 more and the touchdown. Sleeper credits
**Jameson Williams** with `rec_td_40p` and does NOT credit St. Brown. The simple rule credits
St. Brown.

⭐ AND IT IS THE CASE THAT PROVES WHY AN AGGREGATE CHECK IS NOT ENOUGH: a lateral moves WHICH player
is credited without changing HOW MANY are, so the weekly total is byte-identical under both rules
(measured: 6/1/6 for 2024 wk17 either way). Worse, that week the simple rule's own error was MASKED
from the subset-identity check too, because St. Brown happened to score a different, shorter
receiving touchdown that week — so his `receiving_tds` was 1 and the bound was satisfied by the wrong
touchdown. Only the external per-player authority could separate them.

⛔ THE THRESHOLD IS `>= 40`, and it is measured rather than assumed: at 41 or at 39 the weekly totals
disagree with Sleeper on 5 of 18 weeks in 2025 (see the controls below). It is not a tunable.

───────────────────────────────────────────────────────────────────────────────────────────────────
📐 WHAT IT REPRODUCES — TWO CHECKS, AND NEITHER CAN SUBSTITUTE FOR THE OTHER
───────────────────────────────────────────────────────────────────────────────────────────────────

Both are run by `run_nf_wk_acc1_long_td_verify.py`, which is COMMITTED so these figures can be
re-derived rather than taken on trust (RC1's lesson: a baseline nobody can re-run is not a baseline).
Everything below is what this prints, verbatim:

    env -u TOKEN AWS_DEFAULT_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_acc1_long_td_verify \
        --season 2025 --identity-from 1999 --controls

  1. WEEKLY TOTAL vs Sleeper's own per-player stat lines (`/v1/stats/nfl/regular/<season>/<wk>`),
     summed so it needs no player-id crosswalk at all:
         2025 REG — all three terms agree on **18 of 18 weeks**.
     ⭐ THE SUMMING IS LOAD-BEARING, not lazy. Sleeper's own `gsis_id` is NULL for most recent
     players (measured 2026-09-18: 3,125 of 9,421 active; Bijan Robinson and Michael Penix both
     null), so a per-player join to Sleeper would silently drop exactly the players a fantasy league
     cares about — the NF-W9-0 rookie-crosswalk trap.
  2. SUBSET IDENTITY vs `stats_player_week` — a player's 40+ yard touchdown count can never exceed
     his touchdown count of that type. Same `gsis_id` vocabulary on both sides, so this needs no
     name join either:
         1999–2025 REG — **5,780 derived player-weeks, 0 unjoined, 0 violations**.
         The SIMPLE (non-lateral) rule produces **3 violations**, and all three are lateral plays:
         the check found the mechanism on its own, before anyone went looking for it.
         (Including 2026 to date: 5,796 player-weeks over 3,474 qualifying plays, still 0.)

⭐ THE TWO-SIDED CONTROLS, which are what make the two figures evidence rather than decoration —
each check is BLIND to the error class the other catches:

    rule variant              weeks disagreeing (of 18)    subset violations
    ─────────────────────     ─────────────────────────    ─────────────────
    the rule below                      0                        0
    threshold 41                        5                        0
    threshold 39                        5                        0
    passer/receiver swapped             0                      138

  ⇒ a wrong THRESHOLD is invisible to the identity check, and a wrong ATTRIBUTION is invisible to the
  aggregate check. Reporting either alone would have been a guard that cannot fail in the direction
  that matters (the NF1.7(a) family).

───────────────────────────────────────────────────────────────────────────────────────────────────
⛔ THE RULES ARE FIXED AS OF 2026-09-18
───────────────────────────────────────────────────────────────────────────────────────────────────

No rule here may be changed to close a specific disagreement on a specific week. The figures above
are what this construction reproduces; a rule tuned until a residual vanishes measures the residual,
not the rule (MH2.2, and the same ⛔ `realized_dst_pbp` carries for the D/ST freeze). A genuine
correction is a MECHANISM stated in general terms, measured over the whole population, and recorded
here with what it moved — which is exactly how the lateral clause arrived.

⚠️ SCOPE, stated so a reader does not over-read it: this module is PLAYER-side and touches no D/ST
term, so it is independent of `realized_dst_pbp`'s freeze and of the 2026 seat-flip trigger (PM
ruling ③). It cannot move the D/ST seat and does not try to.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

#: The yardage a touchdown must travel to pay the bonus. ⛔ MEASURED, NOT TUNABLE — see the header:
#: 41 and 39 each disagree with the platform on 5 of 18 weeks.
LONG_TD_YARDS = 40

#: The scorer keys this module supplies, in the order the verification reports them.
LONG_TD_KEYS: tuple[str, ...] = ("pass_td_40p", "rush_td_40p", "rec_td_40p")

#: The `pbp` columns the derivation reads. Named here so ONE place widens the read — a column the
#: query forgot to select would silently count zero of that term (NF-C0e), so `player_long_td_counts`
#: REFUSES a narrower row rather than treating an absent column as a zero.
PBP_PLAYER_COLUMNS: tuple[str, ...] = (
    "season", "week", "game_id",
    "touchdown", "pass_touchdown", "rush_touchdown", "yards_gained",
    "passer_player_id", "receiver_player_id", "rusher_player_id",
    # ⚠️ LOAD-BEARING, NOT BELT-AND-BRACES. See the header's 2024 wk17 case: without these two the
    # touchdown is credited to the player who did not score it, the weekly total is unchanged, and
    # the subset-identity bound can be satisfied by an unrelated touchdown in the same week.
    "lateral_receiver_player_id", "lateral_rusher_player_id",
)

#: The column each supplied term is served under on a flattened realized row. ⭐ PREFIXED so a reader
#: of a row can always see the term came from PLAYS rather than from the weekly stat line — the two
#: have different freshness and different failure modes, and a bare `pass_td_40p` would also collide
#: if the vendor ever adds a column of that name to `stats_player_week`.
LONG_TD_COLUMN: dict[str, str] = {k: f"pbp_{k}" for k in LONG_TD_KEYS}


def _truthy_flag(value: Any) -> bool:
    """A pbp 0/1 flag, read safely. ⚠️ `NaN` MUST READ AS NOT SET: pbp arrives through pandas, so an
    unpopulated flag is `NaN`, and `bool(float('nan'))` is True — the same trap `realized_dst_pbp`
    records, and it would turn every non-scoring play into a touchdown."""
    if value is None:
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return not math.isnan(f) and f == 1.0


def _yards(value: Any) -> float:
    """`yards_gained`, with an absent or NaN value reading as 0 — i.e. never long enough to pay."""
    if value is None:
        return 0.0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def _pid(value: Any) -> str:
    """A player id as a string, with NaN/None/blank reading as absent."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    s = str(value).strip()
    return "" if s in ("", "nan", "None") else s


def player_long_td_counts(plays: Iterable[dict]) -> dict[str, dict[str, float]]:
    """`{player_id: {scorer key: count}}` for one set of plays — the frozen rule in the header.

    Accepts ANY set of plays and counts those that qualify, so the caller decides the week (or
    season) scope. Only players with at least one qualifying touchdown appear; a caller that needs a
    zero for everyone else supplies it, because "this player scored no long touchdown" and "we did
    not look at plays at all" must stay distinguishable (the fallback-announces-itself rule).

    ⛔ REFUSES A NARROWER ROW. A row missing one of `PBP_PLAYER_COLUMNS` would make that column read
    as absent, which this module's own helpers treat as "not set" — so a forgotten column in the
    caller's SELECT would silently zero a whole term instead of failing. The refusal is what makes
    `PBP_PLAYER_COLUMNS` a contract rather than a comment.
    """
    out: dict[str, dict[str, float]] = {}

    def add(pid: str, key: str) -> None:
        if pid:
            out.setdefault(pid, {k: 0.0 for k in LONG_TD_KEYS})[key] += 1.0

    for play in plays:
        missing = [c for c in PBP_PLAYER_COLUMNS if c not in play]
        if missing:
            raise ValueError(
                f"a play row is missing {missing} — the long-touchdown derivation reads every one "
                f"of {list(PBP_PLAYER_COLUMNS)}, and an absent column reads as 'not set' rather "
                "than raising, so a narrower SELECT would score zero of a term with no error "
                "(the NF-C0e wrong-key class). Select the full set."
            )
        if not _truthy_flag(play.get("touchdown")):
            continue
        if _yards(play.get("yards_gained")) < LONG_TD_YARDS:
            continue
        if _truthy_flag(play.get("pass_touchdown")):
            add(_pid(play.get("passer_player_id")), "pass_td_40p")
            # The lateral player scored it; the primary receiver did not. See the header.
            add(_pid(play.get("lateral_receiver_player_id")) or _pid(play.get("receiver_player_id")),
                "rec_td_40p")
        if _truthy_flag(play.get("rush_touchdown")):
            add(_pid(play.get("lateral_rusher_player_id")) or _pid(play.get("rusher_player_id")),
                "rush_td_40p")
    return out


def subset_identity_violations(counts: dict[str, dict[str, float]],
                               touchdowns: dict[str, dict[str, float]]) -> list[dict]:
    """Every player whose derived long-TD count EXCEEDS his touchdown count of that type.

    ⭐ THE CHECK THAT DISPROVED THE WRONG-KEY, RUN IN THE CONFIRMING DIRECTION — and the one that
    found the lateral mechanism unaided. PURE so the verification runner and the guard suite drive
    the same comparison.

    `touchdowns` maps a player id to `{'pass_td_40p': passing_tds, 'rush_td_40p': rushing_tds,
    'rec_td_40p': receiving_tds}` — i.e. keyed by the SCORER KEY the bound applies to, so the pairing
    lives at the caller and cannot be mismatched here.
    """
    out: list[dict] = []
    for pid, got in counts.items():
        bound = touchdowns.get(pid) or {}
        for key in LONG_TD_KEYS:
            have, cap = float(got.get(key) or 0.0), float(bound.get(key) or 0.0)
            if have > cap + 1e-9:
                out.append({"playerId": pid, "term": key, "derived": have, "touchdowns": cap})
    return out
