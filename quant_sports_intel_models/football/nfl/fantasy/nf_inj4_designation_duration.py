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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE PRE-REGISTERED FIELD — declared FORWARD, committed before any arm was scored.
# The narrative registration is `ablation_results/nf_inj4_preregistration.md`; everything
# decidable in advance is a CONSTANT here and the runner RESTATES NOTHING (the NF-D16 discipline).
# ══════════════════════════════════════════════════════════════════════════════════════════════
PRIMARY_ARM = "desig_empirical"
#: the SERVED model's implicit predictive: a weekly designation applies a discount of EXACTLY zero.
INCUMBENT_ARM = "always_zero"
#: the matched foil (NF-D10 / NF-D15): the identical machinery with the DESIGNATION content
#: stripped and nothing else changed. The paired delta IS the designation attribution — "my arm
#: won" is not "it won for the reason I said".
MATCHED_FOIL = "status_blind_foil"

#: DEGENERATES — pre-registered to LOSE, at BOTH ends of the support (NF1.8: a constraint a
#: degenerate satisfies is fine because the metric eliminates it; a CRITERION a degenerate wins is
#: fatal, so both the maximally-optimistic and the maximally-pessimistic point mass are scored).
#: ⭐ `always_zero` is ALSO the incumbent reference for the lift series, so its trial Sharpe is
#: identically 0 and MH2.1 (a) is satisfied BY CONSTRUCTION rather than by a second rule.
DEGENERATE_ARMS: tuple[str, ...] = ("always_zero", "always_max")

ARMS: tuple[str, ...] = (
    "desig_empirical",     # PRIMARY — in-fold empirical spell pmf per designation level
    "desig_x_posgroup",    # + position, with the declared min-cell backoff
    "desig_x_practice",    # + practice participation, with the declared min-cell backoff
    "fixed_penalty",       # the naive constant the gap record refuses — scored, NOT shippable
    "status_blind_foil",   # the MATCHED FOIL — designation content stripped
    "always_zero",         # DEGENERATE + the incumbent
    "always_max",          # DEGENERATE
)
DECLARED_FIELD_SIZE = len(ARMS)

#: ⛔ NOT SHIPPABLE BY REGISTRATION, declared before scoring (the NF-D20 discipline). `fixed_penalty`
#: is the "Out → some fixed games penalty" guess `nf_c8_injury_designation_gap.md` names as the
#: thing this story exists to replace, and `sleeper_injuries_source.WEEKLY_DESIGNATIONS` carries a
#: standing prohibition against exactly it. It is SCORED so the empirical forms have to beat it.
#: ⭐ If it beats every real arm, that is a REFUTED-MAGNITUDE finding to be reported plainly as a
#: null resting on a REGISTRATION CHOICE rather than on a gate level — ⛔ never re-labelled shippable
#: after the fact (E2.1-r in its most literal form). The foil and the degenerates are likewise
#: unshippable: a foil is a measuring instrument and a degenerate is an anchor.
SHIPPABLE_ARMS: tuple[str, ...] = ("desig_empirical", "desig_x_posgroup", "desig_x_practice")
NON_SHIPPABLE_BY_REGISTRATION: tuple[str, ...] = (
    ("fixed_penalty", MATCHED_FOIL) + DEGENERATE_ARMS)

#: ANCHORS — scored, never shippable. A missing or unfittable anchor RAISES; it is NEVER a pass
#: (NF1.7 (a): an anchor that fails to fit makes its check vacuously true).
ANCHORS: tuple[str, ...] = ("own_form_oracle", "matched_n_control", "permutation")

# ── Design ─────────────────────────────────────────────────────────────────────────────────────
#: PRIMARY design: GROUPED K-fold by player. A player contributes up to 14 designation rows whose
#: spells overlap, so grouping keeps them together; and at ONE season it is the only design giving
#: both an admissible fold count and usable training depth. 10 is the smallest count clearing the
#: MLB-TV2-2 margin rule (`sign_floor <= 0.5 x bh_cutoff`) under BOTH declared BH readings — the
#: census computes it with `validate_sign_certifiability` BEFORE this file declared it.
N_FOLDS = 10
FOLD_UNIT = "gsis_id"
FOLD_SEED = 20260903
#: ⚠️ THE LIMITATION, STATED FORWARD: grouped-by-player folds share WEEKS between train and test,
#: so week-level shocks are not held out; and at `n_seasons = 1` season-transfer is structurally
#: unmeasurable. Neither is fixable at this depth — they are what makes 2026 the named re-test.

#: SECONDARY design, declared FORWARD and REPORTED, never a gate: forward-chained week blocks with
#: purging (a training row is admissible only if its own outcome window closes before the test
#: block opens). It carries a SIGN-CONSISTENCY reading only, because at 6 folds its sign floor
#: (0.0156) REFUSES the conservative BH cutoff — measured by `validate_sign_certifiability`, which
#: is why it is not the primary.
SECONDARY_TEST_BLOCKS: tuple[tuple[int, int], ...] = (
    (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18))

#: The support the pmfs are carried on before per-row truncation. 17 = the most team games any row
#: can have remaining in an 18-week season with one bye.
SUPPORT_MAX = 17

#: A conditioning cell with fewer than this many in-fold training rows BACKS OFF to its parent
#: (designation-only) cell. A conventional floor for an empirical distribution over a count
#: support, fixed a-priori; ⛔ no variant is scored and nothing selects on it.
MIN_CELL_N = 30

#: The position axis is the program's OWN modelled set — not a grouping invented for this story.
POSITION_GROUPS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

#: The naive constant `fixed_penalty` embodies: "Out means out for ONE game". Read off the domain,
#: a-priori, never fitted.
FIXED_PENALTY_GAMES: dict[str, float] = {
    "out": 1.0, "doubtful": 1.0, "questionable": 0.0, DESIGNATION_NONE: 0.0}

# ── Gates ──────────────────────────────────────────────────────────────────────────────────────
MAX_PBO, MIN_DSR = 0.20, 0.95

#: ⭐ THE BH FAMILY, NAMED BEFORE SCORING (the NF-INJ3b PM ruling; CLAUDE.md's "say which reading
#: binds, and why"). This study tests ONE mechanism on ONE population with NO position axis in the
#: hypothesis: does the weekly-designation channel improve the games-missed predictive over its
#: matched status-blind foil? That is a SINGLE hypothesis, so `BH_CUTOFF_BINDING` binds. Correcting
#: across ARMS would deflate a second time for the search `dsr` already deflates.
BH_FAMILY_SIZE = 1
BH_CUTOFF_BINDING = 0.05
#: REPORTED beside it so the choice is auditable rather than assumed. Both are sign-certifiable at
#: `N_FOLDS` with margin (headroom 0.020 and 0.137 against the 0.5 rule) — measured in the census.
BH_CUTOFF_CONSERVATIVE = 0.05 / DECLARED_FIELD_SIZE

#: ⭐ THE EXPLICIT GATE PARTITION (PLAT-CVP2 defect 2). `gate_classes` is the ONLY input that can
#: affirm "there is no deflation gate here", and it must classify EVERY gate the study scores — a
#: partially declared partition reintroduces the ambiguity it exists to remove. ⛔ This registration
#: DECLARES the partition; it does not fall back on the instrument's name heuristic.
#: The PM convention (CLAUDE.md): deflation-class = {pbo, cscv, dsr, deflated_sharpe};
#: `bh_ok` and `fold_consistency` are MULTIPLICITY / STABILITY gates, not deflation-class.
GATE_CLASSES: dict[str, str] = {
    "beats_incumbent": "metric",
    "beats_foil": "metric",
    "fold_consistency": "metric",
    "bh_ok": "metric",
    "oracle_respected": "metric",
    "beats_permutation": "metric",
    "dsr_ok": "deflation",
    "degenerates_lose": "invariant",
}
#: ⭐ DECLARED FORWARD as gates the injection structurally CANNOT move (PLAT-CVP2 defect 1).
#: Planting a stronger designation → duration relationship cannot make a point mass at 0 or a point
#: mass at `games_remaining` win, so an arm stopped by this clause ALONE cleared every movable gate
#: and is `CONSTRAINT_BLOCKED`, not `BLIND`. Declaring it here, before the control runs, is what
#: keeps it from laundering: a gate cannot be reclassified as injection-invariant after seeing that
#: it blocked (E2.1-r).
INVARIANT_GATES: tuple[str, ...] = ("degenerates_lose",)
DEFLATION_GATES: tuple[str, ...] = tuple(
    g for g, c in GATE_CLASSES.items() if c == "deflation")

#: ⛔ `pbo` is a FIELD-LEVEL statistic and is NOT in the per-arm gate table. Carrying it per-arm
#: converts "the search was unstable" into "this arm failed", which is not a statement PBO makes
#: (the PM convention; `cv_power.classify_null(pbo_application=...)` refuses that reading).
PBO_APPLICATION = "field"

#: The positive control's planted effect: ONE extra missed game on the rows the mechanism claims to
#: price. The smallest unit the target can express and the magnitude the product cares about.
INJECTION_EFFECT_GAMES = 1.0
INJECTED_DESIGNATIONS: tuple[str, ...] = ("out", "doubtful")

#: DSR-CONV: degenerates count toward `n_trials` for multiplicity and are EXCLUDED from `V`. This
#: registration OPTS IN explicitly and forward (the convention is forward-only and inert otherwise).
DEGENERATES_EXCLUDED_FROM_V = True

# ── Application (registered forward; see the pre-registration §7) ──────────────────────────────
#: The full regular season, the denominator of the remaining-season RATE the shipped news cap
#: already uses. Imported meaning, not a new constant: `season_projection.reported_absence_games`.
SEASON_GAMES = 17.0
#: ⛔ SCOPE: the discount applies ONLY to REGULAR-SEASON weekly designations. The fitted population
#: is 2025 REG weeks 1–18; a PRESEASON tag is a different animal (the live 2026 snapshot of
#: 2026-08-21 carried 116 `Questionable` and ZERO `Out`/`Doubtful`, because the game-status report
#: only publishes those once the season starts). Applying an in-season fit to a preseason tag would
#: be an out-of-population read, so it is refused rather than quietly extended.
APPLY_FROM_REGULAR_SEASON_ONLY = True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The metric — EXACT discrete CRPS on the count support
# ══════════════════════════════════════════════════════════════════════════════════════════════
def crps_discrete(pmf: np.ndarray, y: np.ndarray) -> np.ndarray:
    """`Σ_k (F(k) − 1{y ≤ k})²` on the integer support {0..SUPPORT_MAX}.

    ⛔ Not a quantile grid: a coarse grid silently TIES arms whose predictives differ by less than
    its step, on exactly the zero-heavy discrete target this study has (NF-W4). ⛔ And never a point
    MAE: 65.6% of this target is zero and its conditional median is 0, so MAE is minimised by the
    all-zero nihilist — the NF-D11 inversion, measurably present here. MAE is DISCLOSED as a
    diagnostic precisely so the inversion is on the record.
    """
    f = np.cumsum(np.asarray(pmf, dtype=float), axis=1)
    k = np.arange(pmf.shape[1])[None, :]
    return ((f - (np.asarray(y, dtype=float)[:, None] <= k).astype(float)) ** 2).sum(axis=1)


def truncate_to_support(pmf: np.ndarray, games_remaining: np.ndarray) -> np.ndarray:
    """Truncate each row's pmf to {0..games_remaining} and renormalise.

    A prediction of five missed games where two remain is impossible, so the support bound is a
    property of the ROW. Applied IDENTICALLY to every arm and every anchor — a transformation one
    arm gets and another does not is not a comparison. A pmf left with zero admissible mass falls
    back to a point mass at 0 rather than producing NaN (unreachable for the declared field, whose
    arms all carry mass at 0 or inside the bound; kept so a future arm cannot fail silently).
    """
    p = np.array(pmf, dtype=float, copy=True)
    k = np.arange(p.shape[1])[None, :]
    p[k > np.asarray(games_remaining, dtype=float)[:, None]] = 0.0
    tot = p.sum(axis=1, keepdims=True)
    dead = (tot[:, 0] <= 0.0)
    if bool(dead.any()):
        p[dead] = 0.0
        p[dead, 0] = 1.0
        tot = p.sum(axis=1, keepdims=True)
    return p / tot


def empirical_pmf(spells: np.ndarray) -> np.ndarray:
    """The raw empirical pmf of a set of observed spells over {0..SUPPORT_MAX}.

    ⛔ NO SMOOTHING, and that is a decision rather than an omission: CRPS is finite for any
    predictive (unlike a log score), so a smoothing constant would buy nothing and cost a free
    parameter. Thin cells are handled by the declared `MIN_CELL_N` backoff instead.
    """
    counts = np.bincount(np.clip(np.asarray(spells, dtype=int), 0, SUPPORT_MAX),
                         minlength=SUPPORT_MAX + 1).astype(float)
    tot = counts.sum()
    if tot <= 0:
        raise ValueError("empirical_pmf received ZERO observations — an empty cell must raise, "
                         "never yield a silently uniform or degenerate predictive (NF1.7 (a))")
    return counts / tot


def point_mass(k: np.ndarray | float) -> np.ndarray:
    k = np.atleast_1d(np.asarray(k, dtype=float))
    out = np.zeros((len(k), SUPPORT_MAX + 1), dtype=float)
    out[np.arange(len(k)), np.clip(np.rint(k), 0, SUPPORT_MAX).astype(int)] = 1.0
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The arms — every one fitted IN-FOLD on `train` and applied to `test`
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cell_pmfs(train: pd.DataFrame, keys: list[str]) -> tuple[dict, np.ndarray]:
    """(cell → pmf) for every cell with ≥ `MIN_CELL_N` training rows, plus the pooled parent pmf."""
    parent = empirical_pmf(train["spell"].to_numpy())
    cells: dict[tuple, np.ndarray] = {}
    for key, grp in train.groupby(keys):
        if len(grp) >= MIN_CELL_N:
            cells[key if isinstance(key, tuple) else (key,)] = empirical_pmf(
                grp["spell"].to_numpy())
    return cells, parent


def _apply_cells(test: pd.DataFrame, keys: list[str], cells: dict,
                 parent_by_designation: dict, pooled: np.ndarray) -> np.ndarray:
    """Look each test row up in its own cell; BACK OFF to the designation-only cell, then to the
    pooled distribution. The backoff order is declared and identical for every conditioned arm."""
    out = np.empty((len(test), SUPPORT_MAX + 1), dtype=float)
    tuples = list(zip(*[test[k].to_numpy() for k in keys]))
    desigs = test["designation"].to_numpy()
    for i, (cell, des) in enumerate(zip(tuples, desigs)):
        out[i] = cells.get(cell, parent_by_designation.get(des, pooled))
    return out


def fit_predict(arm: str, train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """One arm's per-row predictive on `test`, fitted only on `train`. Returns the UNTRUNCATED pmf;
    the caller truncates every arm identically via `truncate_to_support`."""
    if arm not in ARMS:
        raise ValueError(f"{arm!r} is not a declared arm — the field is {list(ARMS)} and it was "
                         f"registered before scoring (E2.1-r)")
    pooled = empirical_pmf(train["spell"].to_numpy())

    if arm == "status_blind_foil":
        return np.repeat(pooled[None, :], len(test), axis=0)
    if arm == "always_zero":
        return point_mass(np.zeros(len(test)))
    if arm == "always_max":
        return point_mass(test["games_remaining"].to_numpy())
    if arm == "fixed_penalty":
        return point_mass(test["designation"].map(FIXED_PENALTY_GAMES).to_numpy(dtype=float))

    by_desig, _ = _cell_pmfs(train, ["designation"])
    by_desig = {k[0]: v for k, v in by_desig.items()}
    if arm == "desig_empirical":
        return np.stack([by_desig.get(d, pooled) for d in test["designation"].to_numpy()])
    if arm == "desig_x_posgroup":
        cells, _ = _cell_pmfs(train, ["designation", "position"])
        return _apply_cells(test, ["designation", "position"], cells, by_desig, pooled)
    if arm == "desig_x_practice":
        cells, _ = _cell_pmfs(train, ["designation", "practice_level"])
        return _apply_cells(test, ["designation", "practice_level"], cells, by_desig, pooled)
    raise AssertionError(f"unreachable: {arm}")   # pragma: no cover


def expected_games_missed(pmf: np.ndarray) -> np.ndarray:
    """`E[spell]` under a (already truncated) predictive — the quantity the board consumes."""
    return (np.asarray(pmf, dtype=float) * np.arange(pmf.shape[1])[None, :]).sum(axis=1)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Folds
# ══════════════════════════════════════════════════════════════════════════════════════════════
def grouped_player_folds(frame: pd.DataFrame, *, n_folds: int = N_FOLDS,
                         seed: int = FOLD_SEED) -> list[np.ndarray]:
    """PRIMARY design: `n_folds` disjoint TEST index sets, grouped so a player is wholly in one."""
    players = np.array(sorted(frame[FOLD_UNIT].unique()))
    rng = np.random.default_rng(seed)
    assign = dict(zip(players, rng.permutation(len(players)) % n_folds))
    fold_of = frame[FOLD_UNIT].map(assign).to_numpy()
    folds = [np.flatnonzero(fold_of == k) for k in range(n_folds)]
    empty = [k for k, f in enumerate(folds) if len(f) == 0]
    if empty:
        raise ValueError(f"fold(s) {empty} are EMPTY — a fold with no test rows scores every arm "
                         f"on nothing and would enter the fold-consistency count as a free pass "
                         f"(NF1.7 (a))")
    return folds


def purged_week_folds(frame: pd.DataFrame,
                      blocks: tuple[tuple[int, int], ...] = SECONDARY_TEST_BLOCKS
                      ) -> list[tuple[np.ndarray, np.ndarray]]:
    """SECONDARY design, reported never gated: forward-chained (train_idx, test_idx) week blocks.

    PURGING is on the training row's OWN outcome window: a row designated in week `w` whose spell
    runs to `w + spell` is admissible for a test block opening at `t` only if `w + spell < t`. That
    is standard purged CV — using a TRAINING row's own label to decide its admissibility is allowed;
    using a TEST row's would not be.
    """
    week = frame["week"].to_numpy()
    end = week + frame["spell"].to_numpy()
    out = []
    for lo, hi in blocks:
        test = np.flatnonzero((week >= lo) & (week <= hi))
        train = np.flatnonzero((week < lo) & (end < lo))
        if len(test) == 0 or len(train) == 0:
            raise ValueError(f"week block {(lo, hi)} yields {len(train)} train / {len(test)} test "
                             f"rows — an empty side is a vacuous fold, never a free pass")
        out.append((train, test))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# APPLICATION SEMANTICS — pure, tested, and DELIBERATELY NOT WIRED INTO THE SERVING PATH
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⛔ **WHY THIS LIVES HERE AND NOT IN `season_projection`.** The bake-off returned
#: `CONSTRAINT_REFUSED` and the model is deploy-held, so wiring a branch into the shipped
#: availability owner would put an uncertified, never-invoked code path on the serving module —
#: the "wired ≠ invoked" / dead-config hazard, for a model that is not authorised to serve. The
#: semantics are nevertheless implemented and ASSERTED here, because the spec registers them
#: forward and because the disjointness invariant is the thing most likely to be got wrong by a
#: future session wiring this up in a hurry. `compose_availability_caps` is the exact shape the
#: ship path would call; wiring it is a one-line change made ONLY under the gated ship path.

#: The channels that can cap `proj_games`, in the order a reader should think about them. Each is a
#: MIN-CAP on one quantity, which is what makes "the strongest wins" well defined.
CHANNEL_FORMAL = "formal_status"        # season_projection.injury_availability_games (RES/PUP/NFI/SUS)
CHANNEL_DESIGNATION = "weekly_designation"   # THIS story
CHANNEL_NEWS = "reported_absence"       # season_projection.reported_absence_games (NF-INJ-NEWS-1)
CHANNEL_NONE = "none"


def remaining_season_rate_cap(current_games: float, expected_missed: float,
                              *, season_games: float = SEASON_GAMES) -> float:
    """The shipped remaining-season RATE, reused verbatim rather than re-derived:

        `new_games = min(current, current × (season_games − missed) / season_games)`

    ⭐ A RATE, NOT A CEILING, and the reason is measured rather than argued: the PM ruled this form
    on 2026-08-23 after `min(current, season_games − missed)` moved 5 of 6 proposed rows by ZERO on
    the real board — the model already projects starters at 11–16 games, so a ceiling of "17 minus a
    short absence" sits ABOVE the current projection. The `min()` is redundant arithmetic for any
    `missed ≥ 0` and is KEPT: monotonicity is the property, and it should be visible in the
    expression rather than inferred from the sign of a coefficient.
    """
    if not np.isfinite(current_games):
        return float("nan")
    target = (float(season_games) - float(expected_missed)) / float(season_games)
    return float(min(float(current_games), float(current_games) * target))


def compose_availability_caps(current_games: float, *, formal_games: float | None = None,
                              designation_games: float | None = None,
                              news_games: float | None = None) -> tuple[float, str]:
    """Return `(applied_games, owning_channel)` — the SINGLE STRONGEST applicable discount.

    ⭐ **DISJOINTNESS, ENFORCED RATHER THAN TRUSTED.** Every channel is a min-cap on the same
    `proj_games`, so "strongest" is unambiguously the smallest resulting figure, and exactly ONE
    channel is recorded as the owner. A player carrying a news cap AND a live designation takes one
    of them, never their composition.

    ⚠️ **THE FAILURE MODE THIS EXISTS TO STOP.** `season_projection.reported_absence_games` skips a
    row when a formal discount **WAS APPLIED**, reading a per-row `_formal_discount_applied` flag.
    If the designation channel does not SET that flag, a player with both would take the news cap
    ON TOP of the designation cap — the exact stacking the NEWS-1 rule exists to prevent, arriving
    silently through a third channel the rule predates. So the ship path sets the same flag whenever
    this function returns `CHANNEL_DESIGNATION`, and the invariant is asserted on a CONSTRUCTED
    both-channels row rather than trusted to a reading of the code.

    Ties go to the EARLIER channel in (formal, designation, news) — a deterministic order, so two
    channels arriving at the same number can never make the owner depend on dict iteration.
    """
    candidates = [(CHANNEL_FORMAL, formal_games), (CHANNEL_DESIGNATION, designation_games),
                  (CHANNEL_NEWS, news_games)]
    best_val, best_owner = float(current_games), CHANNEL_NONE
    for name, val in candidates:
        if val is None or not np.isfinite(val):
            continue
        if float(val) < best_val - 1e-12:
            best_val, best_owner = float(val), name
    return best_val, best_owner
