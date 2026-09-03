"""nf_inj4_designation_duration.py — NF-INJ4: the weekly-designation → games-missed DURATION model.

⭐ READ `ablation_results/nf_inj4_preregistration.md` FIRST once it exists; until then read
`ablation_results/nf_inj4_data_census.md`, which is the DATA CENSUS this story ran BEFORE writing
its registration (the spec's "data honesty first, and it may bind" clause). ⛔ Editing either after
a result is not a pre-registration (E2.1-r).

────────────────────────────────────────────────────────────────────────────────────────────────
THE GAP
────────────────────────────────────────────────────────────────────────────────────────────────
`sleeper_injuries_source.map_injury_status` deliberately returns `None` for a weekly game-report
tag, and `season_projection.injury_availability_games` caps only on `RES/PUP/NFI/SUS`. So
**Questionable, Doubtful and Out apply an availability discount of EXACTLY ZERO** — the board reacts
to a roster TRANSACTION and to nothing else. `ablation_results/nf_c8_injury_designation_gap.md` is
the traced write-up. This module is capability (a) of that record: an EMPIRICAL designation →
games-missed distribution, because a weekly "Out" carries no duration and Out→a fixed penalty is a
guess wearing a projection's clothing.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE IS
────────────────────────────────────────────────────────────────────────────────────────────────
The PURE kernel: the admissibility rules, the per-(player, week) designation resolution, the
outcome (spell) construction, and — from the registration commit onward — the declared field, the
in-fold arm fits and the exact discrete CRPS reducer. No lake IO and no network, so it unit-tests
without a DuckDB or an S3 credential. The runner is `run_nf_inj4_designation_duration.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEASON = 2025
#: The landed NF-W2c / NF-W2c-CBS capture store this story READS (append-only; never rebuilt here).
WAYBACK_STORE_SOURCE = "wayback_injuries"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# SOURCE ADMISSIBILITY — a PROVENANCE rule, decided on the census's leakage argument
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⛔ **ESPN IS EXCLUDED, AND THE REASON IS ADMISSIBILITY, NOT PERFORMANCE.** The census
#: (`ablation_results/nf_inj4_data_census.md` §3) measured that ESPN's landed rows carry a
#: week attribution that is ONE WEEK LATE: an ESPN `out` row's miss rate is 0.484 on the week it is
#: attributed to and **0.986 on the week before** (n=141), while the same probe on CBS reads
#: 1.000/0.522 and on nfl.com 0.931/0.414 — i.e. both of those are correct as attributed and only
#: ESPN inverts. That leaves ESPN's rows with NO admissible week: read at `w` the designation
#: describes a different game, and re-attributed to `w−1` the capture instant no longer bounds it
#: (the capture happens after `w−1`'s kickoff, so the row would LEAK). A row that cannot be given a
#: point-in-time-valid week is inadmissible in either reading, which is a provenance verdict and is
#: settled BEFORE any arm is scored — ⛔ never "the source that scored worse" (E2.1-r).
#: The 537 ESPN rows cost only 97 distinct (player, week) cells the other two do not already cover.
ADMISSIBLE_SOURCES: tuple[str, ...] = ("nfl", "cbs")
#: Kept NAMED rather than deleted so the exclusion is visible and re-checkable when NF-W2c's ESPN
#: leg is fixed (a finding handed to the PM; this story does not rebuild the append-only store).
EXCLUDED_SOURCES: tuple[str, ...] = ("espn",)

#: The vocabulary the two admissible parsers emit, plus the level for a player who is ON the
#: official report with NO game-status designation. ⛔ `none_listed` is NOT "healthy" and is NOT
#: dropped: it is the report's own fourth state and the census measures it as materially different
#: from absence-from-the-report (NF-W0's "report_status NULL ≠ HEALTHY").
DESIGNATION_NONE = "none_listed"
DESIGNATION_LEVELS: tuple[str, ...] = ("out", "doubtful", "questionable", DESIGNATION_NONE)

#: Practice participation, with an explicit UNKNOWN level. ⚠️ The census measures that `unknown` is
#: SOURCE-DRIVEN (CBS omits the practice line on most `out` rows), so an arm conditioning on it
#: carries a stated attribution caveat — declared forward, never discovered.
PRACTICE_UNKNOWN = "unknown"
PRACTICE_LEVELS: tuple[str, ...] = ("dnp", "limited", "full", PRACTICE_UNKNOWN)

#: The certified weekly labels that count as the player having been AVAILABLE for that game.
#: `dressed_no_stat` is an APPEARANCE (he was active and dressed), never a miss.
APPEARED_LABELS: tuple[str, ...] = ("played", "dressed_no_stat")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Designation resolution — ONE designation per (player, week)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def resolve_designations(store: pd.DataFrame) -> pd.DataFrame:
    """Collapse the capture store to ONE row per (week, player): the latest capture that CARRIES a
    designation wins; a player-week designated in NO admissible capture resolves to `none_listed`.

    ⭐ **WHY A NULL `report_status` IS MISSING AND NOT A LEVEL — MEASURED, NOT ASSUMED.** The
    obvious rule ("the latest capture wins, NULL included") is the live product's read and looks
    least-clever, and it is MECHANICALLY WRONG here. nfl.com publishes practice participation from
    Wednesday and only fills the GAME-STATUS column on the final report, so a mid-week capture
    STRUCTURALLY CANNOT carry a designation. Measured on the admissible sources (census §3b): every
    one of the 50 Thursday nfl.com captures is blank, Friday runs 352 blank to 45 designated, and
    nfl.com's blank rows sit a median **1.52 days** before kickoff against **0.34 days** for its
    designated rows. So a blank is "not YET designated", and letting it win on recency would erase a
    real Thursday CBS "Questionable for Week N" and book it as `none_listed` — absence of evidence
    inside one capture read as evidence of absence, which is exactly NF-W0's "report_status NULL ≠
    HEALTHY" in the direction that costs signal.

    ⇒ NULL is treated as MISSING within a capture, and `none_listed` is reserved for a player-week
    no admissible capture ever designated. That level is honest but bounded: it means "never
    designated in the captures we hold", NOT "never designated by the NFL" — our coverage is
    partial, and the census reports it as such.

    ⚠️ The two admissible sources disagree on 18 of the 81 player-weeks where both carry a
    designation, so the resolution rule is load-bearing. `resolve_designations_strongest` is the
    pre-registered SENSITIVITY (declared forward, reported, never a gate).
    """
    _require(store, {"week", "gsis_id", "report_status", "capture_timestamp", "source"})
    df = store[store["source"].isin(ADMISSIBLE_SOURCES)].copy()
    df["capture_ts"] = pd.to_datetime(df["capture_timestamp"], utc=True, errors="coerce")
    if bool(df["capture_ts"].isna().any()):
        raise ValueError(
            f"{int(df['capture_ts'].isna().sum())} capture rows carry an unparseable "
            f"`capture_timestamp` — the capture instant IS the admissibility bound, so an "
            f"unparseable stamp must reject the build, never resolve to an arbitrary winner")
    # ⚠️ `groupby(...).last()` is COLUMN-WISE last-NON-NULL, not "the last row" — it would take
    # `report_status` from one capture and `practice_status` from another. `drop_duplicates
    # (keep="last")` takes the actual ROW. (The column-wise form was caught by a cross-check that
    # measured ZERO rule disagreements on player-weeks where the sources demonstrably disagree.)
    # Ordering: designated captures sort ABOVE blank ones, then by recency, so the winner is the
    # latest DESIGNATED capture when one exists and the latest capture otherwise.
    df = df.assign(_has_designation=df["report_status"].notna().astype(int))
    out = (df.sort_values(["_has_designation", "capture_ts"])
             .drop_duplicates(subset=["week", "gsis_id"], keep="last")
             .drop(columns=["_has_designation"])
             .reset_index(drop=True))
    return _finalize_designation(out)


def resolve_designations_strongest(store: pd.DataFrame) -> pd.DataFrame:
    """PRE-REGISTERED SENSITIVITY: the most SEVERE designation across sources wins (recency breaks
    ties). Reported beside the primary so the resolution rule's influence is a measured quantity
    rather than an assumption; ⛔ it is never a gate and no arm is selected on it."""
    _require(store, {"week", "gsis_id", "report_status", "capture_timestamp", "source"})
    df = store[store["source"].isin(ADMISSIBLE_SOURCES)].copy()
    df["capture_ts"] = pd.to_datetime(df["capture_timestamp"], utc=True, errors="coerce")
    order = {"out": 3, "doubtful": 2, "questionable": 1}
    # NULL sorts BELOW every designation for the same reason the primary rule gives: a blank
    # mid-week capture is "not yet designated", never a resolved absence.
    df["_severity"] = df["report_status"].map(order).fillna(0.0)
    out = (df.sort_values(["_severity", "capture_ts"])
             .drop_duplicates(subset=["week", "gsis_id"], keep="last")
             .drop(columns=["_severity"])
             .reset_index(drop=True))
    return _finalize_designation(out)


def _finalize_designation(out: pd.DataFrame) -> pd.DataFrame:
    out = out.copy()
    out["designation"] = (out["report_status"].astype("object")
                          .where(out["report_status"].notna(), DESIGNATION_NONE))
    bad = sorted(set(out["designation"]) - set(DESIGNATION_LEVELS))
    if bad:
        raise ValueError(
            f"unrecognised designation level(s) {bad} — an unknown token must REJECT rather than "
            f"flow on as if it were captured (the NF-C0e wrong-key class); the admissible "
            f"vocabulary is {list(DESIGNATION_LEVELS)}")
    out["practice_level"] = (out.get("practice_status", pd.Series(index=out.index, dtype=object))
                             .astype("object"))
    out["practice_level"] = out["practice_level"].where(
        out["practice_level"].isin(PRACTICE_LEVELS[:-1]), PRACTICE_UNKNOWN)
    return out


def _require(df: pd.DataFrame, cols: set[str]) -> None:
    missing = sorted(cols - set(df.columns))
    if missing:
        raise ValueError(
            f"the designation frame is missing {missing} — refusing to build a duration target from "
            f"an unrecognised schema (NF1.7 (a): a source that cannot be read must fail loudly, "
            f"never yield an empty family that scores as a clean null)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The outcome — a CONSECUTIVE-ABSENCE SPELL, in TEAM GAMES
# ══════════════════════════════════════════════════════════════════════════════════════════════
def availability_grid(rosters: pd.DataFrame, schedule: pd.DataFrame,
                      labels: pd.DataFrame, *, max_week: int) -> pd.DataFrame:
    """(gsis_id, week) → `has_game` / `missed`, for every skill player on any 2025 roster.

    ⭐ **ABSENCE FROM THE CERTIFIED SPINE IS A MISS, NOT A GAP, AND THIS IS THE LOAD-BEARING
    CHOICE.** `weekly_frame.build_spine` keeps only `ACT`/`INA` roster rows, so a player who lands
    on IR (`RES`) or is demoted (`DEV`) DISAPPEARS from it entirely. Counting only `label ==
    inactive` would therefore systematically under-count exactly the LONG spells a duration model
    exists to price — the designation that turns into a season-ender would read as a short absence.
    So a team-game with no APPEARED label is a miss, and appearance is read positively from the
    certified label rather than inferred from a row's presence. (Measured: for the modelled
    positions the certified appearance flag is a strict SUPERSET of the weekly stats rows — 0
    stat-bearing player-weeks are outside it — so this cannot manufacture a false miss.)

    A BYE is not a game and is skipped, never counted as a miss. A player's team is carried forward
    from his last roster row so a mid-season IR stint does not silently end his schedule.
    """
    _require(rosters, {"season", "week", "team", "gsis_id"})
    _require(schedule, {"week", "home_team", "away_team"})
    _require(labels, {"week", "gsis_id", "label"})

    team_games = pd.concat([
        schedule[["week", "home_team"]].rename(columns={"home_team": "team"}),
        schedule[["week", "away_team"]].rename(columns={"away_team": "team"}),
    ], ignore_index=True).drop_duplicates()
    team_games["has_game"] = True

    players = sorted(pd.Series(rosters["gsis_id"]).dropna().unique())
    grid = pd.MultiIndex.from_product(
        [players, range(1, int(max_week) + 1)], names=["gsis_id", "week"]).to_frame(index=False)

    ros = (rosters.loc[rosters["week"] <= max_week, ["week", "gsis_id", "team"]]
           .drop_duplicates(["week", "gsis_id"]))
    g = grid.merge(ros, on=["gsis_id", "week"], how="left").sort_values(["gsis_id", "week"])
    g["team"] = g.groupby("gsis_id")["team"].ffill()
    g = g.merge(team_games, on=["week", "team"], how="left")
    g["has_game"] = g["has_game"].astype("boolean").fillna(False).astype(bool)

    app = labels[["week", "gsis_id", "label"]].copy()
    app["appeared"] = app["label"].isin(APPEARED_LABELS)
    g = g.merge(app[["week", "gsis_id", "appeared"]], on=["week", "gsis_id"], how="left")
    g["appeared"] = g["appeared"].astype("boolean").fillna(False).astype(bool)
    g["missed"] = g["has_game"] & ~g["appeared"]
    return g.reset_index(drop=True)


def attach_spells(designations: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """The registered TARGET: `spell` = the number of the player's own team's games, starting with
    the designation week's game, that he misses CONSECUTIVELY before his next appearance.

    ⭐ WHY THE CONSECUTIVE SPELL AND NOT "every game missed to season's end". The board's
    availability input needs a DURATION — "how long is he out" — and the consecutive spell is that
    quantity: it is week-invariant modulo censoring, it is the exact input the shipped reported-
    absence cap already takes (`expected_games_missed`), and it does not conflate this injury with
    an unrelated one in December. `total_missed_rest` is carried beside it as a declared diagnostic.

    RIGHT-CENSORING is real and reported, never silently imputed: a spell still running at the end
    of the regular season is flagged `censored`, and the registered target is the OBSERVED count, so
    every arm predicts the same bounded, decision-relevant quantity. `games_remaining` is the row's
    own support bound — a prediction of five missed games where two remain is impossible, and every
    arm's predictive is truncated to it identically.
    """
    by_player = {k: v.sort_values("week") for k, v in grid.groupby("gsis_id")}
    rows: list[dict] = []
    for r in designations.itertuples():
        sub = by_player.get(r.gsis_id)
        fwd = (sub[(sub["week"] >= r.week) & sub["has_game"]]
               if sub is not None else None)
        if fwd is None or len(fwd) == 0:
            # No remaining team game ⇒ the target is UNDEFINED for this row. Recorded and dropped
            # by the caller with a count, never coerced to a zero (NF1.7 (a)).
            rows.append({"spell": np.nan, "censored": None, "games_remaining": 0,
                         "total_missed_rest": np.nan})
            continue
        missed = fwd["missed"].to_numpy()
        played = np.flatnonzero(~missed)
        spell = int(len(missed)) if played.size == 0 else int(played[0])
        rows.append({"spell": float(spell), "censored": bool(played.size == 0),
                     "games_remaining": int(len(missed)),
                     "total_missed_rest": float(missed.sum())})
    return pd.concat([designations.reset_index(drop=True),
                      pd.DataFrame(rows)], axis=1)
