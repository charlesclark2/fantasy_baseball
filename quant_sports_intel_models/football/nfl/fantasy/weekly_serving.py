"""weekly_serving.py — NF-C6-PH2: the SERVING side of NF-W1's certified weekly champion.

NF-W1 certified `lgbm_hurdle` (P(zero) × conditional quantile bank) SHIP at all four positions —
8/8 folds against the honest degenerate foil, PBO 0.0, DSR ≥ 0.9888, coverage ≥ 0.817 against a 0.80
FLOOR — on 2026-08-07. It has served nothing since: there was no weekly endpoint for it to land on.
This module is the path from that certified construction to a served player-week payload.

⭐ IT RE-DERIVES NOTHING. Every model decision is `weekly_projection`'s, reached through
`weekly_projection.fit_lgbm_hurdle` / `fit_component_head` / `ros_projection` / `assemble_matrix`
verbatim. What is new here is exclusively the SERVING boundary: choosing the target week, proving
the target week's own outcome cannot reach its own features, projecting the remaining schedule, and
shaping the result into `app.backend.models.nfl_weekly`'s contract.

────────────────────────────────────────────────────────────────────────────────────────────────
1. THE FABRICATED-ZERO HAZARD, AND WHY THE HORIZON IS BUILT BY COPYING RATHER THAN RE-ENGINEERING
────────────────────────────────────────────────────────────────────────────────────────────────
`weekly_frame.attach_labels` LEFT-joins the stat feed and RETAINS every non-match as a zero — which
is exactly right for a played week (a rostered player who did not score really did score 0) and is a
PLACEHOLDER for a week that has not happened. That placeholder is inert for the target week itself,
because every champion feature is `shift(1)`-lagged, so the target week's own row never enters its
own features.

⛔ IT IS NOT INERT ONE WEEK LATER. Re-running `engineer_features` across the remaining schedule would
read the target week's placeholder zero as a realized outcome for week W+1's lags, then W+1's
placeholder for W+2, and so on — every player's rolling form collapsing toward zero over the horizon,
silently, with no error and a perfectly plausible-looking payload. A rest-of-season number built that
way would tend to the nihilist while reading like a projection.

So the horizon is built by COPYING each player's target-week feature row and overriding ONLY the
schedule-derived game context (`GAME_CONTEXT_COLUMNS`). No lag is ever recomputed past the last week
with realized outcomes, which makes the compounding structurally impossible rather than merely
avoided. `assert_frozen_form` pins exactly which columns may move, and `assert_no_target_week_outcome`
proves the target week's own outcome is inert by INJECTING one and measuring that the features do not
move (a measurement, not a claim — a `shift(1)` deleted from the champion turns it red).

⚠️ THE OPPONENT BLOCK IS FROZEN TOO, deliberately. Varying it across the horizon would mean
projecting each remaining week against that week's real opponent — and NF-W1 MEASURED that channel as
worth nothing: `foil_matchup` lost to the champion at all four positions and lost to the FLAT foil as
well. Freezing also keeps horizon rows inside the training distribution (a real value rather than a
novel all-null pattern), which matters more to prediction quality than which opponent it describes.
`ROS_VARIES` / `ROS_HELD` name the split on the wire so no reader has to infer it.

────────────────────────────────────────────────────────────────────────────────────────────────
2. THE TRAINING BOUNDARY — A SUPERSET OF THE CERTIFIED FOLD TRAIN, MEASURED (the NF-W6c precedent)
────────────────────────────────────────────────────────────────────────────────────────────────
NF-W1's folds train on rows at least `PURGE_WEEKS` global weeks before the test block; the purge is
belt-and-braces against week-adjacent autocorrelation inflating a MEASURED score. At serve time there
is no measurement to inflate and the two most recent weeks are the most informative rows there are,
so serving trains on every modeled row strictly before the target week — the same choice NF-W6c made
and measured ("84036 train rows = a superset of NF-W6b's purged fold train (83011, +1025), containment
measured"). `n_train` and `n_train_purged_equivalent` are both stamped so the containment is a
number in the artifact rather than a claim in a docstring.

────────────────────────────────────────────────────────────────────────────────────────────────
3. WHAT IS ADVISORY AND SAYS SO
────────────────────────────────────────────────────────────────────────────────────────────────
The per-stat component means come from `weekly_projection.fit_component_head`, whose own docstring
says they are "advisory raw lines beside the gated points distribution (never themselves gated in
this slice)". They are served PAID and stamped `component_head_status = "advisory_ungated"`, because
a value's certification status is part of what it means. The CERTIFIED per-stat distributions
(NF-W6c/W6d) are a different registry target, remain staged CHALLENGERS with no consumer, and are
NOT served here — their own registry notes block promotion until the deferred re-scoring consumer
exists.

⚖️ `best_alpha = 0` — a fantasy projection product. No edge, CLV or win-rate claim rides on any
number here, and `nfl_weekly.assert_best_alpha_is_zero` walks the built payload to say so.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.backend.models import nfl_weekly as C
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

log = logging.getLogger("nfl.fantasy.weekly_serving")

#: The registry version-of-record this build serves, and the certified construction behind it.
SERVED_VERSION = "nfl_fantasy_weekly_v1"
BASE_MODEL_VERSION = "nfl_fantasy_nf_w1_v1"
POINT_MODEL_VERSION = "nf_w1_lgbm_hurdle"
#: The 80% band is the SAME object as the point — one hurdle mixture emits both, so there is no
#: separate interval model to version apart from it (unlike the season stack's three-way band).
INTERVAL_MODEL_VERSION = "nf_w1_lgbm_hurdle"

#: The only columns a horizon row may differ from its target-week row in.
GAME_CONTEXT_COLUMNS: tuple[str, ...] = (
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
)

ROS_VARIES = "home/away, divisional, week index, rest days, and the real bye schedule"
ROS_HELD = (
    "form (all lagged usage, snap and box features), team environment, opponent profile and "
    "prior-season priors, held at their target-week values"
)


class WeeklyServingError(RuntimeError):
    """A serving-boundary invariant was violated. Fail closed: never publish past one."""


# ── 1. which week are we projecting ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TargetWeek:
    season: int
    week: int
    first_kickoff: pd.Timestamp
    last_reg_week: int


def resolve_target_week(schedule: pd.DataFrame, *, now: datetime | None = None) -> TargetWeek:
    """The next REG week to project: the earliest week whose FIRST kickoff has not happened yet.

    ⭐ FIRST kickoff, not last. Once a slate has started, projecting it is projecting a game that is
    already being played — the model is pre-game by construction (game-day status is a banned
    feature) and the honest move is to advance to the next week. Using the LAST kickoff would keep a
    Thursday-night slate "current" until Monday and serve a projection for six games in progress.

    ⚠️ Deliberately NOT a clock-derived week number. The NFL's week boundaries are a property of the
    published schedule, not of arithmetic on a start date: a flexed game, an international kickoff or
    a rescheduled week moves them. Reading the schedule cannot drift; a formula can.
    """
    now = now or datetime.now(timezone.utc)
    now_ts = pd.Timestamp(now).tz_convert("UTC") if pd.Timestamp(now).tzinfo else pd.Timestamp(now, tz="UTC")
    s = schedule.copy()
    s["gameday"] = pd.to_datetime(s["gameday"])
    if s["gameday"].dt.tz is None:
        s["gameday"] = s["gameday"].dt.tz_localize("UTC")
    firsts = s.groupby(["season", "week"], as_index=False)["gameday"].min()
    upcoming = firsts[firsts["gameday"] > now_ts].sort_values("gameday")
    if upcoming.empty:
        raise WeeklyServingError(
            f"no REG week in the schedule kicks off after {now_ts.isoformat()} — the season is over "
            "or the schedule feed has not landed the next one. Refusing to pick a week rather than "
            "silently projecting a played slate."
        )
    row = upcoming.iloc[0]
    season = int(row["season"])
    last_reg = int(s.loc[s["season"] == season, "week"].max())
    return TargetWeek(season=season, week=int(row["week"]),
                      first_kickoff=row["gameday"], last_reg_week=last_reg)


# ── 2. the serving matrix, and the proof its target week's outcome is inert ──────────────────────

#: The two features whose PRESENCE — not value — used to depend on the target week having been
#: played. See `opponent_grid_stub`.
OPPONENT_BLOCK_COLUMNS: tuple[str, ...] = (
    "opponent_matchup__dvp_ppr_index_l8",
    "opponent_matchup__def_ppr_allowed_l8",
)


def opponent_grid_stub(schedule: pd.DataFrame, stats: pd.DataFrame, *,
                       target: TargetWeek) -> pd.DataFrame:
    """Zero-valued stat rows for the target week, so its OPPONENT BLOCK can be computed at all.

    ⭐ THE DEFECT THIS CLOSES, MEASURED. `engineer_features` derives the opponent block from a
    defence-vs-position table built out of the REALIZED stat feed, then lags it `shift(1)` and rolls
    it over 8 appearances. The lagged VALUE for an unplayed week is entirely knowable — every row in
    its window is a prior, realized week — but the table has no GROUP KEY for a week that produced no
    stat rows, so the merge yields null. Measured on the 2026 week-1 serving frame:

        opponent_matchup__dvp_ppr_index_l8     train 0.9580   target week 0.0000
        opponent_matchup__def_ppr_allowed_l8   train 0.9847   target week 0.0000

    and on the exactly analogous shape — week 1 of each of 2022/2023/2024/2025 — training coverage
    is 1.000. So the champion was fitted on a feature that is always present and would have been
    served one that is always absent: the E7.9 train/serve-consistency class, in a model that had
    never served. LightGBM tolerates the null, which is precisely what makes it dangerous — the
    prediction routes through a default direction learnt from almost no null examples, silently.

    ⭐ THE FIX ADDS NO ARITHMETIC, AND THAT IS THE POINT. Rather than re-deriving the block here —
    a fork of a certified construction, which is how a serving path drifts from the model that was
    certified — it supplies the missing GROUP KEYS as zero-valued stat rows and lets
    `engineer_features` compute its own block unchanged. The stub's own zeros cannot reach the value
    it produces, because `shift(1)` excludes a row from its own window, and there is no later week
    for them to reach. The same zeros land on the component columns, where `engineer_features`
    already applies `fillna(0.0)` — so those are bit-identical either way.

    ⛔ NOT PASSED TO `attach_labels`. The stub exists to create a defence's grid key, not an outcome:
    a zero stat line reaching the labeller would be a fabricated result. `build_serving_matrix`
    keeps the two feeds separate and `assert_no_target_week_outcome` is what proves it stayed that
    way — with the stub in place that proof now passes for the right reason, because a feature's
    presence no longer depends on the week having been played and its value never did.
    """
    s = schedule[(schedule["season"] == target.season) & (schedule["week"] == target.week)]
    if s.empty:
        return stats.iloc[0:0]
    rows = []
    for _, g in s.iterrows():
        for off, dfn in ((g["home_team"], g["away_team"]), (g["away_team"], g["home_team"])):
            for pos in WP.POSITIONS:
                rows.append({"season": target.season, "week": target.week, "player_id": None,
                             "position": pos, "team": off, "opponent_team": dfn,
                             "fantasy_points_ppr": 0.0})
    stub = pd.DataFrame(rows)
    for c in stats.columns:
        if c not in stub.columns:
            stub[c] = 0.0
    return stub.reindex(columns=stats.columns)


def build_serving_matrix(src: dict[str, pd.DataFrame], *, target: TargetWeek,
                         guard=None) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """History + the target week, assembled through `weekly_projection.assemble_matrix`.

    That function is the ONLY sanctioned path to a champion feature matrix: it engineers, checks
    provenance against the NF-W0 contract, and runs `assert_point_in_time` per week fail-closed.
    Serving goes through it unchanged, which is how NF-W0a's guard gets its serving-side caller.

    Returns the FRAME beside the matrix because `assemble_matrix` drops bye rows by design — a bye
    is not a modeled row, but it IS a served one (the deterministic identity zero), so the serving
    universe has to be read off the frame rather than off the matrix.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spine = WF.build_spine(src["rosters"], src["schedule"])
    frame = WF.attach_labels(
        spine, src["stats"],
        label_version=WP.LABEL_VERSION,
        label_as_of_timestamp=stamp,
        scoring_system_id=WP.SCORING_SYSTEM_ID,
        snaps=src["snaps"],
    )
    kwargs = {} if guard is None else {"guard": guard}
    # ⭐ TWO DIFFERENT STAT FEEDS, DELIBERATELY. `attach_labels` gets the REAL feed — a stub row
    # reaching the labeller would be a fabricated outcome. `assemble_matrix` gets the feed plus the
    # opponent-grid stub, which supplies only the group keys the block needs to exist at all.
    feat_stats = pd.concat(
        [src["stats"], opponent_grid_stub(src["schedule"], src["stats"], target=target)],
        ignore_index=True,
    )
    modeled, audit = WP.assemble_matrix(frame, feat_stats, src["snaps"], src["schedule"], **kwargs)
    return modeled, audit, frame


def assert_no_target_week_outcome(src: dict[str, pd.DataFrame], *, target: TargetWeek,
                                  clean: pd.DataFrame | None = None,
                                  features: tuple[str, ...] = WP.FEATURES) -> dict:
    """PROVE the target week's own outcome cannot reach the target week's own features.

    ⭐ A MEASUREMENT, NOT A CLAIM. The frame's placeholder zero for an unplayed week is only inert
    because every champion feature is `shift(1)`-lagged — a property of the code, which a future edit
    could remove without any test noticing. So this INJECTS a synthetic realized outcome for every
    target-week player (a large, unmistakable stat line), rebuilds the matrix, and asserts the target
    week's feature block is bit-identical to the clean build's.

    Deleting a `shift(1)` from `engineer_features` turns this red; nothing else does. Returns the
    comparison's own shape so the caller can prove it was NOT VACUOUS — an injection that touched
    zero rows would pass trivially (NF1.7(a)).
    """
    if clean is None:
        clean, _, _ = build_serving_matrix(src, target=target)
    tgt_mask = (clean["season"] == target.season) & (clean["week"] == target.week)
    n_target = int(tgt_mask.sum())
    if n_target == 0:
        raise WeeklyServingError(
            f"the outcome-independence proof has no target-week rows to compare "
            f"({target.season} wk {target.week}) — it would pass on nothing."
        )

    tgt_players = clean.loc[tgt_mask, "gsis_id"].to_numpy()
    injected = pd.DataFrame({
        "season": target.season, "week": target.week, "player_id": tgt_players,
        "position": clean.loc[tgt_mask, "position"].to_numpy(),
        "team": clean.loc[tgt_mask, "team"].to_numpy(),
        "opponent_team": clean.loc[tgt_mask, "opponent"].to_numpy(),
        "fantasy_points_ppr": 99.0,
        "carries": 40.0, "targets": 40.0, "attempts": 60.0, "receptions": 30.0,
        "passing_yards": 600.0, "passing_tds": 7.0, "passing_interceptions": 5.0,
        "rushing_yards": 300.0, "rushing_tds": 5.0,
        "receiving_yards": 400.0, "receiving_tds": 5.0,
    })
    dirty_src = dict(src)
    stats = src["stats"]
    # Drop any real target-week stat rows first, so the injection REPLACES rather than duplicates
    # (a duplicated key would change the features for a reason that is not the injection).
    keep = ~((stats["season"] == target.season) & (stats["week"] == target.week))
    dirty_src["stats"] = pd.concat(
        [stats.loc[keep], injected.reindex(columns=stats.columns)], ignore_index=True
    )
    dirty, _, _ = build_serving_matrix(dirty_src, target=target)

    cols = ["gsis_id", *features]
    a = clean.loc[tgt_mask, cols].sort_values("gsis_id").reset_index(drop=True)
    d_mask = (dirty["season"] == target.season) & (dirty["week"] == target.week)
    b = dirty.loc[d_mask, cols].sort_values("gsis_id").reset_index(drop=True)
    if len(a) != len(b):
        raise WeeklyServingError(
            f"injecting a target-week outcome changed the target-week ROW COUNT "
            f"({len(a)} → {len(b)}); the serving frame depends on the week's own outcome."
        )
    moved = [
        c for c in features
        if not np.allclose(
            pd.to_numeric(a[c], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(b[c], errors="coerce").to_numpy(dtype=float),
            rtol=0.0, atol=0.0, equal_nan=True,
        )
    ]
    if moved:
        raise WeeklyServingError(
            f"the target week's own outcome REACHES its own features: {sorted(moved)} moved when a "
            f"synthetic {target.season} wk {target.week} stat line was injected. A lag was lost — "
            "every champion feature must be shift(1) of strictly-prior weeks."
        )
    return {"n_target_rows": n_target, "n_features_compared": len(features),
            "n_injected_stat_rows": int(len(injected))}


# ── 3. the frozen-form horizon ───────────────────────────────────────────────────────────────────

def _team_week_context(schedule: pd.DataFrame) -> pd.DataFrame:
    """Per (season, week, team): opponent, home, divisional, kickoff and rest days.

    Built from the SCHEDULE alone, which is exactly what makes it knowable for a future week —
    the same reason `engineer_features` derives its own rest days this way."""
    s = schedule.copy()
    s["gameday"] = pd.to_datetime(s["gameday"])
    home = s.rename(columns={"home_team": "team", "away_team": "opponent"}).assign(is_home=1.0)
    away = s.rename(columns={"away_team": "team", "home_team": "opponent"}).assign(is_home=0.0)
    cols = ["season", "week", "team", "opponent", "is_home", "gameday", "div_game"]
    tw = pd.concat([home[cols], away[cols]], ignore_index=True)
    tw["season"] = tw["season"].astype("int64")
    tw["week"] = tw["week"].astype("int64")
    tw = tw.sort_values(["team", "gameday"])
    tw["days_since_last_game"] = tw.groupby("team")["gameday"].diff().dt.days
    return tw.reset_index(drop=True)


def form_basis(modeled: pd.DataFrame, *, target: TargetWeek,
               universe: pd.DataFrame) -> pd.DataFrame:
    """Each served player's MOST RECENT modeled row at or before the target week.

    ⭐ NOT simply the target week's rows. A player whose team is on bye in the target week has no
    modeled row that week (`assemble_matrix` drops byes) and yet still has a rest-of-season, so his
    frozen form has to come from his latest played-week row. Reading "most recent at or before"
    handles the bye case and the ordinary case with one rule instead of a special case that only
    ever runs from week 5 onward — i.e. one that would ship untested.
    """
    tgt_gw = modeled.loc[
        (modeled["season"] == target.season) & (modeled["week"] == target.week), "gw"
    ]
    if tgt_gw.empty:
        raise WeeklyServingError(
            f"no modeled rows for {target.season} wk {target.week}; cannot build a form basis."
        )
    cutoff = int(tgt_gw.iloc[0])
    hist = modeled[modeled["gw"] <= cutoff]
    wanted = set(universe["gsis_id"].astype(str))
    hist = hist[hist["gsis_id"].astype(str).isin(wanted)]
    return (hist.sort_values("gw").groupby("gsis_id", as_index=False).tail(1)
            .reset_index(drop=True))


def frozen_form_horizon(target_rows: pd.DataFrame, schedule: pd.DataFrame, *,
                        target: TargetWeek) -> pd.DataFrame:
    """One row per (player, remaining week AFTER the target), form frozen at `target_rows`.

    A remaining week in which the player's team has no game is a BYE and is emitted with
    `is_bye = True`; the caller scores it as the deterministic identity zero NF-W1 pre-registered
    rather than asking the model for a number the schedule already fixes.
    """
    ctx = _team_week_context(schedule)
    ctx = ctx[(ctx["season"] == target.season) & (ctx["week"] > target.week)]
    weeks = list(range(target.week + 1, target.last_reg_week + 1))
    if not weeks:
        return target_rows.iloc[0:0].assign(is_bye=pd.Series(dtype=bool))

    out = []
    for wk in weeks:
        wk_ctx = ctx[ctx["week"] == wk][
            ["team", "opponent", "is_home", "div_game", "days_since_last_game", "gameday"]
        ]
        block = target_rows.merge(wk_ctx, on="team", how="left", suffixes=("", "_h"))
        block["is_bye"] = block["opponent_h"].isna()
        block["week"] = wk
        block["opponent"] = block["opponent_h"]
        block["game_context__is_home"] = pd.to_numeric(block["is_home_h"], errors="coerce")
        block["game_context__div_game"] = pd.to_numeric(block["div_game_h"], errors="coerce")
        block["game_context__week_index"] = float(wk)
        block["game_context__days_since_last_game"] = pd.to_numeric(
            block["days_since_last_game_h"], errors="coerce"
        )
        out.append(block.drop(columns=[c for c in block.columns if c.endswith("_h")]))
    return pd.concat(out, ignore_index=True)


def assert_frozen_form(target_rows: pd.DataFrame, horizon: pd.DataFrame,
                       features: tuple[str, ...] = WP.FEATURES) -> dict:
    """Every horizon feature EXCEPT `GAME_CONTEXT_COLUMNS` is bit-identical to the player's
    target-week row.

    ⭐ This is what makes "frozen form" a checked property rather than a description. If a future
    edit re-engineers the horizon instead of copying it, the lag columns move and this goes red —
    which is the fabricated-zero compounding hazard caught at its only entry point.

    Also asserts NON-VACUITY on both sides: a comparison over zero rows, or over zero frozen
    columns, would pass on nothing (NF1.7(a)).
    """
    frozen_cols = [c for c in features if c not in GAME_CONTEXT_COLUMNS]
    if not frozen_cols:
        raise WeeklyServingError("no frozen columns to compare — the check would be vacuous")
    if horizon.empty:
        return {"n_horizon_rows": 0, "n_frozen_columns": len(frozen_cols), "checked": False}

    base = target_rows.set_index("gsis_id")[frozen_cols]
    got = horizon.set_index("gsis_id")[frozen_cols]
    ref = base.reindex(got.index)
    moved = [
        c for c in frozen_cols
        if not np.allclose(
            pd.to_numeric(ref[c], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(got[c], errors="coerce").to_numpy(dtype=float),
            rtol=0.0, atol=0.0, equal_nan=True,
        )
    ]
    if moved:
        raise WeeklyServingError(
            f"horizon rows are NOT frozen form: {sorted(moved)} differ from the target week. Only "
            f"{list(GAME_CONTEXT_COLUMNS)} may vary — anything else means a lag was recomputed over "
            "weeks with no realized outcome, which compounds the frame's placeholder zero forward."
        )
    return {"n_horizon_rows": int(len(horizon)), "n_frozen_columns": len(frozen_cols),
            "checked": True}


# ── 4. fit + predict ─────────────────────────────────────────────────────────────────────────────

def quantile_at(qmat: np.ndarray, level: float) -> np.ndarray:
    """Interpolate the 39-level quantile vector at `level`.

    ⭐ USED FOR THE ROS σ AT EXACTLY 0.16/0.84. `ros_projection` computes σ = (q84 − q16)/2, which is
    σ only at those levels; the nearest grid points (0.15/0.85) would give 1.036σ — a 3.6%
    over-estimate baked into every ROS interval. Interpolating a quantile function is the sanctioned
    operation (`weekly_projection.interp_to_levels` does the same thing knot-to-grid).
    """
    q = np.sort(np.asarray(qmat, dtype=float), axis=1)
    return np.array([np.interp(level, WP.Q_LEVELS, row) for row in q])


def fit_and_predict(train: pd.DataFrame, score: pd.DataFrame,
                    features: tuple[str, ...] = WP.FEATURES) -> tuple[np.ndarray, pd.DataFrame]:
    """The certified champion + its advisory component head, fitted once and applied to `score`.

    Both calls are `weekly_projection`'s own — this module chooses the population, never the form
    (the NF-W6c dispatch-only discipline: a serving module that re-implements a certified arm can
    silently diverge from the thing that was certified).
    """
    feats = list(features)
    qmat = WP.fit_lgbm_hurdle(train, score, feats)
    comps = WP.fit_component_head(train, score, feats)
    return qmat, comps


# ── 5. shaping the payload ───────────────────────────────────────────────────────────────────────

def _bye_vector() -> np.ndarray:
    """A bye's predictive: the identity zero at every level. NF-W1's pre-registration says serving
    emits a bye as the identity 0 exactly — it is a DETERMINISTIC zero knowable at schedule release,
    not a missing projection, which is also why the bake-off excluded byes from scoring."""
    return np.zeros(len(WP.Q_LEVELS), dtype=float)


def feature_coverage(rows: pd.DataFrame, features: tuple[str, ...] = WP.FEATURES) -> dict[str, float]:
    """Per-feature non-null share on the SERVED rows.

    ⭐ PER-COLUMN, NEVER A POOLED MEAN (MH2.1 (c)): "missing" and "never existed on this population"
    are different findings and a mean hides both. This is the instrument that makes a structural
    serving-time absence visible — the opponent block, for instance, is derived from realized stats
    and is therefore ENTIRELY absent in week 1 of a new season, which is honest but is a real
    train/serve distribution difference a reader is owed rather than one they discover later.
    """
    n = len(rows)
    if not n:
        return {c: 0.0 for c in features}
    return {
        c: round(float(pd.to_numeric(rows[c], errors="coerce").notna().mean()), 6)
        for c in features
    }


def build_ros(target_rows: pd.DataFrame, target_q: np.ndarray,
              horizon: pd.DataFrame, horizon_q: np.ndarray) -> pd.DataFrame:
    """Rest-of-season via `weekly_projection.ros_projection`, over the target week + the horizon.

    ⭐ THE BAND IS READ AT EXACTLY 0.16/0.84 (`quantile_at`), because that is the only pair at which
    `ros_projection`'s σ = (q84 − q16)/2 is σ. Handing it the nearest 39-level grid points would
    silently widen every ROS interval by 3.6%.

    ⚠️ A BYE CONTRIBUTES ITS IDENTITY ZERO ROW rather than being dropped — `ros_projection` counts
    `n_weeks` as distinct weeks, so dropping byes would make `rosWeeks` mean "weeks with a game" on
    some players and "weeks remaining" on others. One meaning, stated on the contract: weeks
    remaining, byes included as zeros.
    """
    parts = [pd.DataFrame({
        "gsis_id": target_rows["gsis_id"].astype(str).to_numpy(),
        "position": target_rows["position"].to_numpy(),
        "week": target_rows["week"].to_numpy(),
        "mean": np.sort(target_q, axis=1).mean(axis=1),
        "q16": quantile_at(target_q, C.ROS_SIGMA_LO_LEVEL),
        "q84": quantile_at(target_q, C.ROS_SIGMA_HI_LEVEL),
    })]
    if len(horizon):
        hq = np.sort(np.asarray(horizon_q, dtype=float), axis=1)
        is_bye = horizon["is_bye"].to_numpy(dtype=bool)
        mean = hq.mean(axis=1)
        q16 = quantile_at(hq, C.ROS_SIGMA_LO_LEVEL)
        q84 = quantile_at(hq, C.ROS_SIGMA_HI_LEVEL)
        mean[is_bye] = 0.0
        q16[is_bye] = 0.0
        q84[is_bye] = 0.0
        parts.append(pd.DataFrame({
            "gsis_id": horizon["gsis_id"].astype(str).to_numpy(),
            "position": horizon["position"].to_numpy(),
            "week": horizon["week"].to_numpy(),
            "mean": mean, "q16": q16, "q84": q84,
        }))
    return WP.ros_projection(pd.concat(parts, ignore_index=True)).set_index("gsis_id")


def build_players(universe: pd.DataFrame, qmap: dict[str, np.ndarray],
                  comps: pd.DataFrame, ros: pd.DataFrame, *,
                  names: dict[str, str], hist_weeks: dict[str, int]) -> list[dict]:
    """The `players` array, contract-shaped — one row per game-day-rostered player in the week.

    `universe` is the target week's FRAME rows (byes included); `qmap` carries a predictive only for
    the modeled ones. A player in the universe with no predictive and no bye is a defect, not a row
    to fabricate: he is DROPPED here and counted by the caller under `pit_gate_dropped`, because the
    one thing this payload may never contain is a number we did not produce (NF-C6b/NF-K1).
    """
    lo_i = int(np.argmin(np.abs(WP.Q_LEVELS - C.INTERVAL_LO_LEVEL)))
    hi_i = int(np.argmin(np.abs(WP.Q_LEVELS - C.INTERVAL_HI_LEVEL)))
    comp_idx = comps.set_index(comps["gsis_id"].astype(str)) if len(comps) else comps

    out: list[dict] = []
    for _, r in universe.iterrows():
        gid = str(r["gsis_id"])
        is_bye = bool(r["is_bye"])
        if is_bye:
            vec = _bye_vector()
        elif gid in qmap:
            vec = np.sort(np.asarray(qmap[gid], dtype=float))
        else:
            continue
        row: dict = {
            "id": gid,
            "name": names.get(gid) or gid,
            "pos": str(r["position"]),
            "team": str(r["team"]),
            "opp": None if is_bye or pd.isna(r.get("opponent")) else str(r["opponent"]),
            "home": None if is_bye or pd.isna(r.get("is_home")) else bool(float(r["is_home"])),
            "status": "bye" if is_bye else "projected",
            "fpPpr": round(float(vec.mean()), 4),
            "fpP10": round(float(vec[lo_i]), 4),
            "fpP90": round(float(vec[hi_i]), 4),
            "rosPpr": None, "rosP10": None, "rosP90": None,
            "rosWeeks": 0,
            "histWeeks": int(hist_weeks.get(gid, 0)),
            "q": [round(float(v), 4) for v in vec],
        }
        if gid in ros.index:
            rr = ros.loc[gid]
            row["rosPpr"] = round(float(rr["ros_mean"]), 4)
            row["rosP10"] = round(float(rr["ros_q10"]), 4)
            row["rosP90"] = round(float(rr["ros_q90"]), 4)
            row["rosWeeks"] = int(rr["n_weeks"])
        for comp, field in C.WEEKLY_COMPONENT_FIELD.items():
            col = f"proj_{comp}"
            if is_bye:
                row[field] = 0.0
            elif len(comp_idx) and gid in comp_idx.index and col in comp_idx.columns:
                row[field] = round(float(comp_idx.loc[gid, col]), 4)
            else:
                row[field] = None
        out.append(row)
    return out
