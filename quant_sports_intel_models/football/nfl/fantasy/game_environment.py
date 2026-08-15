"""game_environment.py — NF-W3: the game-environment component (team play-volume + pass/rush
allocation), pure. The runner reads these constants; nothing here may be chosen after a score.

THE STORY IN ONE PARAGRAPH. NF-W3 is the first V1 COMPONENT of the v3 weekly system (doc §2): the
game environment sits at the top of the causal chain `environment → volume → allocation →
availability → opportunity → efficiency` that NF-W5/W6 extend and NF-W8 assembles. It emits, per
team-game, a DISTRIBUTION for two targets — `off_plays` (a count) and `pass_share` (a rate on a
known denominator) — under the NF-W0 allowed feature contract, the NF-W0a PIT guard, and the
NF-W0c era constraint. ⭐ AND IT IS GATED TWICE: Layer A asks whether either target beats its own
honest team-level baseline; Layer B asks the only question that decides whether any of it is worth
serving — does the environment layer improve the ASSEMBLED PLAYER PROJECTION against the NF-W1
`lgbm_hurdle` champion as the permanent direct foil (doc §10.3)? A component that wins Layer A and
loses Layer B is a RECORDED NULL, not a served model.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS PRE-REGISTERED (narrative copy: `ablation_results/nf_w3_preregistration.md`)
────────────────────────────────────────────────────────────────────────────────────────────────
  · TARGETS. `off_plays` = count of `play_type ∈ {pass, run}` with `posteam = team`;
    `pass_share` = `count(play_type='pass') / off_plays`. The `play_type` split is chosen because
    it COMPOSES downstream: `play_type='run'` IS team carries (designed runs + QB scrambles) and
    `play_type='pass' − sacks` IS team pass attempts — exactly the pair NF-W5 needs.
  · ⚠️ T2 IS UNCONDITIONAL ON THE REALIZED DENOMINATOR. The realized play count encodes game
    script, so it may not enter a T2 arm's features or its TEST-time trial count. It is used only
    as the binomial WEIGHT in training (train labels are known — no leak); at test the binomial /
    beta-binomial arms use the lagged `team_environment__off_plays_l4` as the trial count.
  · FOLDS. The NF-W1 blocks verbatim (8 expanding half-season blocks 2022H1…2025H2, purge 2 global
    weeks). Identical fold axis is what makes Layer B a MATCHED comparison rather than an anecdote.
  · METRIC. CRPS (`crps_q39`) over the shared 39-level quantile grid, one reducer for every arm and
    both layers. ⛔ MAE never selects and never gates.
  · FIELD. 4 real arms per target + 2 foils; anchors are DIAGNOSTIC, never trials (MH2.1 (a)) —
    they are excluded from the PBO matrix and the DSR trial field.
  · ANCHORS, two-sided: `nihilist_zero` + `marginal_train` + `zero_width` + `max_width` must all
    LOSE (a constraint a degenerate satisfies is fine; a criterion one WINS is fatal — NF1.8);
    `permuted_within_week` must lose AND its lift over the foil must not be significant, FAILING
    CLOSED on a None p-value (NF1.7 (a)); `oracle_<arm>` is ONE PEEKING ORACLE PER ARM OF THAT
    ARM'S OWN FORM (NF-D16 (g‴) — a single shared ceiling would veto a legitimately-better nested
    form as a false metric inversion); `matched_n_<arm>` reports the capacity axis (NF1.9 (f)).
  · GATES. beats_foil ∧ fold_consistency(cv_power clause at 8 ⇒ 6/8) ∧ PBO < 0.20 ∧ DSR ≥ 0.95 ∧
    BH-FDR q = 0.10 — where TWO families are declared and the STRICTER binds (see FDR_FAMILIES) ∧
    degenerates lose ∧ permutation behaves ∧ own-form oracle floors respected ∧ coverage floor.
  · POWER IS CHECKED IN ADVANCE: at 8 folds the fold clause is attainable (6/8), PBO is evaluable,
    the sign floor 0.0039 < the 0.10 BH cutoff, and `dsr_ceiling(8) = 0.9999` against a 0.95 gate.
    No gate is structurally unattainable ⇒ a null here is a FINDING, not a design artifact.

NF-W0 CONSTRAINTS, honored mechanically rather than by comment:
  (1) three certified families only — `game_context`, `team_environment`, `opponent_matchup`;
      unknown provenance is a REJECTION (`assert_feature_provenance_w3`);
  (2) ⛔ NO pbp_participation leg at all — the 2023 provider replacement forbids pooling
      pressure/coverage/route rates; enforced by ERA_FORBIDDEN_TOKENS, not prose;
  (3) `assert_point_in_time` is INVOKED per target week at the assembly boundary, fail-closed;
  (4) ⛔ no `fillna(0)` — a missing lagged window is NaN (0 plays is a legal value); learners that
      cannot pass NaN use TRAIN-fitted MEDIAN imputation as a device inside the arm, with presence
      carried by `team_environment__games_prior_season`;
  (5) ⛔ no markets / weather / depth-chart rank / game-day inactive status — the realized-weather
      trap (`schedules.temp`/`wind`) is excluded by never reading those columns
      (`BANNED_SOURCE_TOKENS` makes that checkable).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: this module promotes nothing and serves
nothing; serving is NF-W8 / NF-C6 Ph2.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W3"
SELECTION_METRIC = WP.SELECTION_METRIC          # crps_q39 — inherited so Layer A/B are commensurable
Q_LEVELS = WP.Q_LEVELS
FIT_LEVELS = WP.FIT_LEVELS
TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE

#: The two component targets.
TARGETS: tuple[str, ...] = ("off_plays", "pass_share")

#: Real arms per target — 4 structurally different classes each (§0.5).
REAL_ARMS: dict[str, tuple[str, ...]] = {
    "off_plays": ("pois_glm", "negbin_glm", "lgbm_quantile", "knn_quantile"),
    "pass_share": ("binom_glm", "betabinom", "lgbm_quantile", "knn_quantile"),
}
#: Honest baselines the winner must beat. Never shippable.
FOILS: tuple[str, ...] = ("foil_team_eb", "foil_team_eb_matchup")
#: Diagnostic anchors — EXCLUDED from the PBO matrix and the DSR trial field (MH2.1 (a)).
BASE_ANCHORS: tuple[str, ...] = (
    "nihilist_zero", "marginal_train", "zero_width", "max_width", "permuted_within_week",
)


def oracle_of(arm: str) -> str:
    """The peeking ceiling of an arm's OWN form (NF-D16 (g‴))."""
    return f"oracle__{arm}"


def matched_n_of(arm: str) -> str:
    """The arm trained on one block-sized recent window — the capacity axis (NF1.9 (f))."""
    return f"matched_n__{arm}"


def anchors_for(target: str) -> tuple[str, ...]:
    arms = REAL_ARMS[target]
    return (*BASE_ANCHORS,
            *(oracle_of(a) for a in arms), *(oracle_of(f) for f in FOILS),
            *(matched_n_of(a) for a in arms))


def all_labels(target: str) -> tuple[str, ...]:
    return (*REAL_ARMS[target], *FOILS, *anchors_for(target))


def eligible_labels(target: str) -> list[str]:
    """The set the selection actually searched — real arms + foils. PBO is computed over THIS,
    never over every scored label (NF1.8: a deflation statistic over a field containing its own
    anchors measures the anchors)."""
    return [*REAL_ARMS[target], *FOILS]


#: ⭐ TWO pre-registered multiplicity families, and the STRICTER binds (MH2 (a): you may
#: pre-register a family, you may not discover one). The pooled 6-hypothesis correction is also
#: computed, and a SHIP must survive BOTH — so no verdict can turn on the family choice.
FDR_FAMILIES: dict[str, tuple[str, ...]] = {
    "component": ("off_plays", "pass_share"),
    "downstream": tuple(WP.POSITIONS),
}

#: EB shrinkage toward the league level, in team-GAMES; the matchup multiplier's clip.
EB_KAPPA_TEAM = 4.0
#: Plays and pass share move far less than fantasy points — a ±25% clip (NF-W1's) would be inert
#: here, so the foil's matchup arm gets a clip matched to the target's own scale.
MATCHUP_CLIP = (0.90, 1.10)

#: NF-W0c constraint honored by EXCLUSION (identical token list to NF-W1).
ERA_FORBIDDEN_TOKENS = WP.ERA_FORBIDDEN_TOKENS
#: Deferred-contract source columns that may never be READ by this build (constraint (5)). Checked
#: against the aggregation SQL itself, so the ban is mechanical rather than a promise.
BANNED_SOURCE_TOKENS: tuple[str, ...] = (
    "spread_line", "total_line", "vegas_wp", "vegas_home_wp", "vegas_wpa", "vegas_home_wpa",
    "temp", "wind", "moneyline", "depth_team", "depth_chart",
)

USED_FAMILIES: tuple[str, ...] = ("game_context", "team_environment", "opponent_matchup")

FEATURES: tuple[str, ...] = (
    # ── game context (immutable at schedule release) ──
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
    # ── own offense, lagged ──
    "team_environment__off_plays_l4",
    "team_environment__off_plays_l8",
    "team_environment__off_plays_ewm",
    "team_environment__off_plays_s2d",
    "team_environment__off_plays_prior_season",
    "team_environment__pass_share_l4",
    "team_environment__pass_share_l8",
    "team_environment__pass_share_ewm",
    "team_environment__pass_share_s2d",
    "team_environment__pass_share_prior_season",
    "team_environment__neutral_pass_rate_l4",
    "team_environment__proe_l4",
    "team_environment__no_huddle_l4",
    "team_environment__sec_per_play_l4",
    "team_environment__drives_l4",
    "team_environment__plays_per_drive_l4",
    "team_environment__epa_per_play_l4",
    "team_environment__success_rate_l4",
    "team_environment__points_l4",
    "team_environment__sack_rate_l4",
    "team_environment__games_prior_season",
    # ── opponent, lagged: what its defense has faced AND what its own offense does ──
    "opponent_matchup__def_plays_faced_l4",
    "opponent_matchup__def_pass_share_faced_l4",
    "opponent_matchup__def_epa_allowed_l4",
    "opponent_matchup__def_success_allowed_l4",
    "opponent_matchup__def_sec_per_play_faced_l4",
    "opponent_matchup__def_points_allowed_l4",
    "opponent_matchup__def_drives_faced_l4",
    "opponent_matchup__opp_off_plays_l4",
    "opponent_matchup__opp_off_pass_share_l4",
    "opponent_matchup__opp_off_epa_l4",
    "opponent_matchup__opp_off_sec_per_play_l4",
)

#: ── Layer B: the env block injected into the NF-W1 champion's feature matrix ────────────────────
ENV_FEATURES: tuple[str, ...] = (
    "team_environment__proj_off_plays",
    "team_environment__proj_pass_plays",
    "team_environment__proj_rush_plays",
    "team_environment__proj_pass_share",
    "team_environment__proj_off_plays_sd",
    "opponent_matchup__proj_opp_off_plays",
    "opponent_matchup__proj_opp_pass_plays",
)
#: The columns the ORACLE substitutes with REALIZED week-w values (the peeking upper bound on
#: everything the environment chain can buy at the player level). `_sd` is deliberately NOT
#: substituted — a realized value has no spread, and zeroing it would change the column's meaning
#: rather than its accuracy.
ORACLE_SUBSTITUTED: tuple[str, ...] = (
    "team_environment__proj_off_plays", "team_environment__proj_pass_plays",
    "team_environment__proj_rush_plays", "team_environment__proj_pass_share",
    "opponent_matchup__proj_opp_off_plays", "opponent_matchup__proj_opp_pass_plays",
)

LAYER_B_REAL_ARMS: tuple[str, ...] = ("champion_env",)
LAYER_B_FOIL = "champion"
LAYER_B_ANCHORS: tuple[str, ...] = ("champion_env_shuffled", "champion_env_oracle")
#: The Layer-B eligible field, declared HERE and never trimmed or grown after a score (MH2 (a)).
LAYER_B_ELIGIBLE: tuple[str, ...] = (LAYER_B_FOIL, *LAYER_B_REAL_ARMS)

_SEED = 20260809


# ── Provenance (fail-closed; delegates to the NF-W0 certified guard) ────────────────────────────
def assert_feature_provenance_w3(feature_columns) -> None:
    """Reject any feature whose provenance is not checkable against the NF-W0 contract.

    Four independently RED-provable clauses:
      1. every column is `<family>__<detail>` with family ∈ USED_FAMILIES;
      2. no LEAKY token (WF.LEAKY_COLUMNS, token-boundary rule);
      3. no participation-ERA token (the 2023 provider switch — NF-W0c constraint);
      4. no DEFERRED-contract source token (market / weather / depth chart — constraint (5)).
    Then the certified NF-W0 clause runs on the family names themselves.
    """
    cols = list(feature_columns)
    bad = [c for c in cols if "__" not in c or c.split("__", 1)[0] not in USED_FAMILIES]
    if bad:
        raise WF.LeakageError(
            f"features with unknown provenance reject the build: {sorted(bad)} — every NF-W3 "
            f"feature must be named '<family>__<detail>' with family in {USED_FAMILIES}"
        )
    leaky = [c for c in cols
             if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_")
                    for tok in WF.LEAKY_COLUMNS)]
    if leaky:
        raise WF.LeakageError(f"leaky feature columns reject the build: {sorted(leaky)}")
    era = [c for c in cols if any(tok in c for tok in ERA_FORBIDDEN_TOKENS)]
    if era:
        raise WF.LeakageError(
            f"participation-era features reject this build: {sorted(era)} — the 2023 provider "
            f"switch (NF-W0c) forbids pooling pressure/coverage/route legs without an era split"
        )
    banned = [c for c in cols if any(tok in c for tok in BANNED_SOURCE_TOKENS)]
    if banned:
        raise WF.LeakageError(
            f"deferred-contract features reject this build: {sorted(banned)} — markets, weather, "
            f"depth-chart rank and game-day inactive status are NF-W0 DEFERRED, not allowed"
        )
    WF.assert_no_leakage(pd.DataFrame(), feature_columns=sorted({c.split("__", 1)[0] for c in cols}),
                         projection_week=0)


def assert_source_query_is_clean(sql: str) -> None:
    """The aggregation SQL may not READ a deferred-contract column. Constraint (5) is about what
    the build TOUCHES, not only about what it names as a feature — a realized `temp` read into an
    intermediate and averaged into a 'pace' column would pass the feature check and still be a
    hard leak. Comment lines are stripped first, so a PROSE mention cannot satisfy or trip it
    (the INC-38 lesson: a source check that matches prose tests nothing)."""
    body = "\n".join(ln.split("--", 1)[0] for ln in sql.splitlines()).lower()
    hits = sorted({tok for tok in BANNED_SOURCE_TOKENS if tok in body})
    if hits:
        raise WF.LeakageError(
            f"the NF-W3 aggregation reads deferred-contract columns {hits} — markets and realized "
            f"weather are banned at the SOURCE, not merely as named features"
        )


# ── Franchise-code canonicalisation (a MEASURED nflverse defect, not a precaution) ──────────────
#: ⚠️ `pbp.posteam` is normalised to the CURRENT franchise code while `schedules` (and
#: `weekly_rosters`, which is why NF-W1 never saw this) keeps the ERA code. Measured on this span:
#: pbp says `LAC`/`LV` in 2016 where schedules says `SD`/`OAK`, and `LV` through 2019. A team-grain
#: join between the two therefore NaNs exactly the relocated franchises — and because pandas
#: merges NaN against NaN, those NaN-keyed rows then CROSS-JOIN with each other on the next merge
#: and SILENTLY DUPLICATE (34 rows in a 32-team week, measured). The NF-W0a PIT guard refused all
#: 65 affected weeks fail-closed, which is how this was found rather than shipped.
TEAM_CODE_CANON: dict[str, str] = {"SD": "LAC", "OAK": "LV", "STL": "LA"}


def canonicalize_team_codes(df: pd.DataFrame, columns) -> pd.DataFrame:
    out = df.copy()
    for c in columns:
        if c in out.columns:
            out[c] = out[c].replace(TEAM_CODE_CANON)
    return out


def assert_team_codes_align(team_box: pd.DataFrame, schedule: pd.DataFrame) -> None:
    """The two sources must agree on the franchise code set in EVERY season, post-canonicalisation.

    A silent one-sided code is a NaN join, and a NaN join here is a duplicated row rather than a
    missing one — so this is asserted, never assumed. `assert_point_in_time` would also refuse the
    week, but a guard that only says 'unevaluable' does not name the cause."""
    bad: list[str] = []
    for season, box in team_box.groupby("season"):
        sch = schedule[schedule["season"] == season]
        a = set(box["team"].dropna().unique())
        b = set(sch["home_team"].dropna().unique()) | set(sch["away_team"].dropna().unique())
        if a - b or b - a:
            bad.append(f"{int(season)}: pbp-only {sorted(a - b)}, schedule-only {sorted(b - a)}")
    if bad:
        raise WF.LeakageError(
            "pbp and schedules disagree on franchise codes after canonicalisation — a team-grain "
            f"join would NaN (and then silently CROSS-JOIN) those rows: {bad}"
        )


# ── Team-game frame: targets + lagged features (all strictly-prior) ─────────────────────────────
def _team_sched(schedule: pd.DataFrame) -> pd.DataFrame:
    home = schedule.rename(columns={"home_team": "team", "away_team": "opponent"}).assign(is_home=1)
    away = schedule.rename(columns={"away_team": "team", "home_team": "opponent"}).assign(is_home=0)
    cols = ["season", "week", "team", "opponent", "is_home", "gameday", "div_game"]
    tw = pd.concat([home[cols], away[cols]], ignore_index=True)
    tw["season"] = tw["season"].astype("int64")
    tw["week"] = tw["week"].astype("int64")
    tw["gameday"] = pd.to_datetime(tw["gameday"])
    return tw


def _lagged(g: pd.DataFrame, key: str, col: str, window: int, minp: int = 1) -> pd.Series:
    """shift(1) BEFORE any rolling — a window may never contain its own target row."""
    return (g.groupby(key, sort=False)[col].shift(1)
            .groupby(g[key], sort=False).rolling(window, min_periods=minp).mean()
            .reset_index(level=0, drop=True))


def build_team_game_frame(team_box: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """One row per (season, week, team) carrying both targets and the full lagged feature block.

    `team_box` is the per-team-game pbp aggregate (see the runner's TEAM_BOX_SQL). Every feature is
    computed from STRICTLY PRIOR games — rolling windows run over the team's own game sequence and
    cross seasons deliberately (a team's "last four games" is what the phrase means), while the
    within-season and prior-season columns stay separate so a week-1 row is honestly NaN rather
    than silently borrowing. ⛔ No `fillna(0)` anywhere: 0 plays is a legal value.
    """
    schedule = canonicalize_team_codes(schedule, ("home_team", "away_team"))
    team_box = canonicalize_team_codes(team_box, ("team",))
    assert_team_codes_align(team_box, schedule)

    tw = _team_sched(schedule)
    gw = WP._global_week_index(schedule)

    df = team_box.copy()
    for c in ("season", "week"):
        df[c] = df[c].astype("int64")
    df = df.merge(gw, on=["season", "week"], how="left")
    df = df.merge(tw, on=["season", "week", "team"], how="left")
    unmatched = df["gameday"].isna() | df["opponent"].isna()
    if unmatched.any():
        sample = df.loc[unmatched, ["season", "week", "team"]].head(5).to_dict("records")
        raise WF.LeakageError(
            f"{int(unmatched.sum())} team-game rows did not match the schedule (e.g. {sample}) — "
            f"⛔ a NaN join key may not proceed: pandas matches NaN against NaN, so these rows "
            f"would CROSS-JOIN on the next merge and silently duplicate"
        )

    df["off_plays"] = pd.to_numeric(df["off_plays"], errors="coerce").astype(float)
    df["pass_plays"] = pd.to_numeric(df["pass_plays"], errors="coerce").astype(float)
    df["pass_share"] = df["pass_plays"] / df["off_plays"].replace(0, np.nan)
    df["rush_plays"] = df["off_plays"] - df["pass_plays"]
    df["plays_per_drive"] = df["off_plays"] / pd.to_numeric(df["drives"], errors="coerce").replace(0, np.nan)
    df["sack_rate"] = pd.to_numeric(df["sacks"], errors="coerce") / df["off_plays"].replace(0, np.nan)

    tws = tw.sort_values(["team", "gameday"]).copy()
    tws["days_since_last_game"] = tws.groupby("team")["gameday"].diff().dt.days
    df = df.merge(tws[["season", "week", "team", "days_since_last_game"]],
                  on=["season", "week", "team"], how="left")

    df = df.sort_values(["team", "gw"]).reset_index(drop=True)

    own = [
        ("off_plays", "off_plays_l4", 4), ("off_plays", "off_plays_l8", 8),
        ("pass_share", "pass_share_l4", 4), ("pass_share", "pass_share_l8", 8),
        ("neutral_pass_rate", "neutral_pass_rate_l4", 4), ("proe", "proe_l4", 4),
        ("no_huddle", "no_huddle_l4", 4), ("sec_per_play", "sec_per_play_l4", 4),
        ("drives", "drives_l4", 4), ("plays_per_drive", "plays_per_drive_l4", 4),
        ("epa_per_play", "epa_per_play_l4", 4), ("success_rate", "success_rate_l4", 4),
        ("points", "points_l4", 4), ("sack_rate", "sack_rate_l4", 4),
    ]
    for src, name, win in own:
        df[f"team_environment__{name}"] = _lagged(df, "team", src, win)
    for src, name in (("off_plays", "off_plays_ewm"), ("pass_share", "pass_share_ewm")):
        df[f"team_environment__{name}"] = (
            df.groupby("team", sort=False)[src].shift(1)
            .groupby(df["team"], sort=False)
            .transform(lambda s: s.ewm(halflife=3, min_periods=1).mean())
        )

    # within-season season-to-date means (strictly prior weeks of the SAME season)
    gs = df.groupby(["team", "season"], sort=False)
    for src, name in (("off_plays", "off_plays_s2d"), ("pass_share", "pass_share_s2d")):
        csum = gs[src].cumsum() - df[src]
        cnt = gs[src].cumcount()
        df[f"team_environment__{name}"] = csum / cnt.replace(0, np.nan)

    # prior-season team level (NaN for a franchise's first season in the span — never 0-filled)
    season_tot = df.groupby(["team", "season"], as_index=False).agg(
        _plays=("off_plays", "mean"), _share=("pass_share", "mean"), _g=("off_plays", "size"))
    season_tot["season"] = season_tot["season"] + 1
    df = df.merge(season_tot.rename(columns={
        "_plays": "team_environment__off_plays_prior_season",
        "_share": "team_environment__pass_share_prior_season",
        "_g": "team_environment__games_prior_season"}),
        on=["team", "season"], how="left")

    # ── opponent block: the opponent's DEFENSE (what it has faced) and its OWN offense ──
    faced = df[["season", "week", "gw", "opponent", "off_plays", "pass_share", "epa_per_play",
                "success_rate", "sec_per_play", "points", "drives"]].rename(
        columns={"opponent": "def_team"})
    faced = faced.sort_values(["def_team", "gw"])
    for src, name in (("off_plays", "def_plays_faced_l4"), ("pass_share", "def_pass_share_faced_l4"),
                      ("epa_per_play", "def_epa_allowed_l4"), ("success_rate", "def_success_allowed_l4"),
                      ("sec_per_play", "def_sec_per_play_faced_l4"), ("points", "def_points_allowed_l4"),
                      ("drives", "def_drives_faced_l4")):
        faced[f"opponent_matchup__{name}"] = _lagged(faced, "def_team", src, 4)
    df = df.merge(
        faced[["season", "week", "def_team"]
              + [c for c in faced.columns if c.startswith("opponent_matchup__")]]
        .rename(columns={"def_team": "opponent"}),
        on=["season", "week", "opponent"], how="left")

    opp_off = df[["season", "week", "team",
                  "team_environment__off_plays_l4", "team_environment__pass_share_l4",
                  "team_environment__epa_per_play_l4", "team_environment__sec_per_play_l4"]].rename(
        columns={"team": "opponent",
                 "team_environment__off_plays_l4": "opponent_matchup__opp_off_plays_l4",
                 "team_environment__pass_share_l4": "opponent_matchup__opp_off_pass_share_l4",
                 "team_environment__epa_per_play_l4": "opponent_matchup__opp_off_epa_l4",
                 "team_environment__sec_per_play_l4": "opponent_matchup__opp_off_sec_per_play_l4"})
    df = df.merge(opp_off, on=["season", "week", "opponent"], how="left")

    df["game_context__is_home"] = pd.to_numeric(df["is_home"], errors="coerce")
    df["game_context__div_game"] = pd.to_numeric(df["div_game"], errors="coerce")
    df["game_context__week_index"] = df["week"].astype(float)
    df["game_context__days_since_last_game"] = pd.to_numeric(df["days_since_last_game"],
                                                             errors="coerce")

    sched = schedule.copy()
    sched["gameday"] = pd.to_datetime(sched["gameday"])
    sched = sched.merge(gw, on=["season", "week"], how="left").sort_values("gw")
    week_max = sched.groupby("gw")["gameday"].max().sort_index()
    week_min = sched.groupby("gw")["gameday"].min().sort_index()
    meta = pd.DataFrame({"gw": week_max.index,
                         "_window_end_day": week_max.cummax().shift(1).values,
                         "_projection_day": week_min.values})
    df = df.merge(meta, on="gw", how="left")
    df["_window_end_day"] = df["_window_end_day"].fillna(df["_projection_day"] - pd.Timedelta(days=7))
    df["_target_gameday"] = df["gameday"]
    return df.reset_index(drop=True)


# ── The PIT gate (NF-W0a — invoked, not merely imported) ────────────────────────────────────────
def pit_guard_records(rows: pd.DataFrame) -> list[dict]:
    """One §13 guard record per assembled team-game row. Stamps are the window-end as-of instant
    (the day AFTER the last strictly-prior game's gameday); `source_timestamp` is declared absent
    because the nflverse pbp release carries no per-row as-of stamp (the `date_modified` class)."""
    window_end_s = ((pd.to_datetime(rows["_window_end_day"]) + timedelta(days=1))
                    .dt.strftime("%Y-%m-%dT00:00:00+00:00").to_numpy())
    target_s = (pd.to_datetime(rows["_target_gameday"])
                .dt.strftime("%Y-%m-%dT00:00:00+00:00").to_numpy())
    out: list[dict] = []
    for season, week, team, window_end, target in zip(
        rows["season"].to_numpy(), rows["week"].to_numpy(), rows["team"].to_numpy(),
        window_end_s, target_s,
    ):
        payload = f"{season}|{week}|{team}"
        out.append({
            "capture_source": "nflverse_lake_pbp_team_game",
            "capture_id": payload,
            "subject_key": payload,
            "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "record_tier": "lake_feature",
            "feature_timestamp": window_end,
            "source_timestamp": None,
            "source_timestamp_absent_reason": (
                "nflverse pbp release carries no per-row as-of stamp; stamps are the window-end "
                "as-of instant (the day after the last strictly-prior game)"
            ),
            "capture_timestamp": window_end,
            "vendor_release_timestamp": window_end,
            "ingestion_timestamp": window_end,
            "is_rolling_window": True,
            "window_end_timestamp": window_end,
            "target_game_timestamp": target,
        })
    return out


def run_pit_gate(df: pd.DataFrame, *, guard=LG.assert_point_in_time) -> dict:
    """FAIL-CLOSED per-week PIT gate over the team-game rows. A week the guard rejects is DROPPED
    and counted; a week the guard CHECKED ZERO records for is a rejection too, never a pass
    (NF1.7 (a) — an anchor that cannot fire is not a passed anchor)."""
    dropped: list[dict] = []
    kept: list[np.ndarray] = []
    weeks = records = 0
    for (season, week), rows in df.groupby(["season", "week"], sort=True):
        proj = rows["_projection_day"].iloc[0].strftime("%Y-%m-%dT00:00:00+00:00")
        recs = pit_guard_records(rows)
        weeks += 1
        records += len(recs)
        try:
            report = guard(recs, proj, store_index={})
            if getattr(report, "checked", len(recs)) == 0:
                raise LG.LeakageRejection([LG.LeakageFinding(
                    LG.Rejection.UNEVALUABLE, "guard checked zero records", None)])
            kept.append(rows.index.to_numpy())
        except LG.LeakageRejection as exc:
            dropped.append({"season": int(season), "week": int(week), "n_rows": int(len(rows)),
                            "reasons": sorted({f.reason.name for f in exc.findings})})
    return {
        "weeks_checked": weeks, "records_checked": records, "weeks_dropped": dropped,
        "rows_dropped": int(sum(d["n_rows"] for d in dropped)),
        "kept_index": np.concatenate(kept) if kept else np.array([], dtype=int),
    }


def assemble_team_matrix(team_box: pd.DataFrame, schedule: pd.DataFrame, *,
                         guard=LG.assert_point_in_time) -> tuple[pd.DataFrame, dict]:
    """THE NF-W3 assembly boundary: engineer → provenance → PIT gate. The only sanctioned path."""
    df = build_team_game_frame(team_box, schedule)
    assert_feature_provenance_w3(FEATURES)
    audit = run_pit_gate(df, guard=guard)
    modeled = df.loc[audit["kept_index"]].reset_index(drop=True)
    modeled = modeled[modeled["off_plays"].notna() & (modeled["off_plays"] > 0)].reset_index(drop=True)
    return modeled, {k: v for k, v in audit.items() if k != "kept_index"}


def matrix_key(seasons: tuple[int, int]) -> str:
    """Cache key over everything that changes the matrix CONTENT (NF-C0e: a cache keyed on params
    but not the query serves a stale column set)."""
    return hashlib.sha256(json.dumps({
        "story": STORY, "seasons": seasons, "features": list(FEATURES),
        "targets": list(TARGETS), "schema": 1,
    }, sort_keys=True).encode()).hexdigest()[:16]


# ── Shared predictive helpers ───────────────────────────────────────────────────────────────────
def crps(qmat: np.ndarray, y: np.ndarray) -> np.ndarray:
    return WP.crps_from_quantiles(qmat, y)


def _X(df: pd.DataFrame, features, medians: dict[str, float] | None = None) -> np.ndarray:
    """Feature matrix. `medians` (fit on TRAIN) is a device inside an arm — ⛔ never a 0-fill."""
    cols = []
    for c in features:
        v = pd.to_numeric(df[c], errors="coerce")
        if medians is not None:
            v = v.fillna(medians[c])
        cols.append(v.to_numpy(dtype=float))
    return np.column_stack(cols)


def train_medians(train: pd.DataFrame, features) -> dict[str, float]:
    out = {}
    for c in features:
        m = pd.to_numeric(train[c], errors="coerce").median()
        out[c] = float(m) if np.isfinite(m) else 0.0
    return out


def residual_bank(y: np.ndarray, point: np.ndarray) -> np.ndarray:
    r = np.asarray(y, float) - np.asarray(point, float)
    r = r[np.isfinite(r)]
    return np.quantile(r, Q_LEVELS)


def apply_bank(point: np.ndarray, bank: np.ndarray) -> np.ndarray:
    return np.asarray(point, float)[:, None] + bank[None, :]


def _clip_share(q: np.ndarray) -> np.ndarray:
    return np.clip(q, 0.0, 1.0)


# ── Foils ───────────────────────────────────────────────────────────────────────────────────────
def foil_point(df: pd.DataFrame, target: str, league_mean: float, *, matchup: bool) -> np.ndarray:
    """EB-shrunk team level (prior season + season-to-date, shrunk to the league mean by
    EB_KAPPA_TEAM team-games), optionally spread by a clipped opponent multiplier."""
    prior = pd.to_numeric(df[f"team_environment__{target}_prior_season"], errors="coerce")
    prior_g = pd.to_numeric(df["team_environment__games_prior_season"], errors="coerce").fillna(0.0)
    s2d = pd.to_numeric(df[f"team_environment__{target}_s2d"], errors="coerce")
    s2d_g = pd.to_numeric(df["game_context__week_index"], errors="coerce").sub(1).clip(lower=0.0)
    s2d_g = s2d_g.where(s2d.notna(), 0.0)
    num = prior.fillna(0.0) * prior_g + s2d.fillna(0.0) * s2d_g + EB_KAPPA_TEAM * league_mean
    point = num / (prior_g + s2d_g + EB_KAPPA_TEAM)
    if matchup:
        faced = "def_plays_faced_l4" if target == "off_plays" else "def_pass_share_faced_l4"
        m = pd.to_numeric(df[f"opponent_matchup__{faced}"], errors="coerce")
        mult = (m / league_mean).fillna(1.0).clip(*MATCHUP_CLIP)
        point = point * mult
    return point.to_numpy(dtype=float)


# ── Arms ────────────────────────────────────────────────────────────────────────────────────────
def fit_pois_glm(train, test, features, target: str, *, y_train=None) -> np.ndarray:
    """Poisson GLM (log link, L2) → the exact Poisson predictive at the fitted mean."""
    from scipy.stats import poisson
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    m = PoissonRegressor(alpha=1e-3, max_iter=2000).fit(sc.transform(_X(train, features, med)), y)
    mu = np.clip(m.predict(sc.transform(_X(test, features, med))), 1e-6, None)
    return poisson.ppf(Q_LEVELS[None, :], mu[:, None])


def _mom_dispersion(y: np.ndarray, mu: np.ndarray) -> float:
    """NB2 dispersion by method of moments: Var = μ + α μ². α ≤ 0 ⇒ under-dispersed ⇒ the NegBin
    arm degenerates toward Poisson, which is a legitimate outcome of TESTING the hypothesis."""
    d = np.asarray(y, float) - np.asarray(mu, float)
    num = float(np.mean(d ** 2 - mu))
    den = float(np.mean(np.asarray(mu, float) ** 2))
    return max(num / den, 1e-6) if den > 0 else 1e-6


def fit_negbin_glm(train, test, features, target: str, *, y_train=None) -> np.ndarray:
    """NB2 GLM: a Poisson pass estimates the dispersion by MoM, then the mean is REFIT under the
    NegBin family (different weights ⇒ genuinely different mean, not just a re-spread Poisson)."""
    import statsmodels.api as sm
    from scipy.stats import nbinom
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    Xtr = sm.add_constant(sc.transform(_X(train, features, med)), has_constant="add")
    Xte = sm.add_constant(sc.transform(_X(test, features, med)), has_constant="add")
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    warm = PoissonRegressor(alpha=1e-3, max_iter=2000).fit(sc.transform(_X(train, features, med)), y)
    alpha = _mom_dispersion(y, np.clip(warm.predict(sc.transform(_X(train, features, med))), 1e-6, None))
    res = sm.GLM(y, Xtr, family=sm.families.NegativeBinomial(alpha=alpha)).fit(maxiter=200)
    mu = np.clip(res.predict(Xte), 1e-6, None)
    r = 1.0 / alpha
    p = r / (r + mu)
    return nbinom.ppf(Q_LEVELS[None, :], r, p[:, None])


def fit_binom_glm(train, test, features, target: str = "pass_share", *, y_train=None) -> np.ndarray:
    """Binomial logistic GLM on (pass_plays successes of off_plays trials). ⚠️ The realized
    denominator is the TRAINING weight only; the TEST predictive uses the LAGGED
    `off_plays_l4` trial count, so no realized play count reaches a scored prediction."""
    import statsmodels.api as sm
    from scipy.stats import binom
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    Xtr = sm.add_constant(sc.transform(_X(train, features, med)), has_constant="add")
    Xte = sm.add_constant(sc.transform(_X(test, features, med)), has_constant="add")
    share = (train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float))
    n_tr = np.clip(train["off_plays"].to_numpy(float), 1.0, None)
    succ = np.clip(share, 0.0, 1.0) * n_tr
    endog = np.column_stack([succ, n_tr - succ])
    res = sm.GLM(endog, Xtr, family=sm.families.Binomial()).fit(maxiter=200)
    p = np.clip(res.predict(Xte), 1e-6, 1 - 1e-6)
    n_te = _test_trials(test)
    return _clip_share(binom.ppf(Q_LEVELS[None, :], n_te[:, None], p[:, None]) / n_te[:, None])


def _test_trials(test: pd.DataFrame) -> np.ndarray:
    """The TEST-time binomial trial count: the LAGGED play count, never the realized one.

    ⚠️ ROUNDED TO AN INTEGER, and that is load-bearing rather than cosmetic: `scipy.stats.binom`
    and `betabinom` return **NaN** for a non-integer `n`, and a 4-game rolling mean is non-integer
    almost always. Unrounded, both T2 GLM arms emit NaN on most rows — which `np.nanmean` then
    silently averages away, scoring those arms on a different (smaller) population than the field.
    The reducer additionally REFUSES a non-finite predictive so this class cannot recur silently."""
    n = pd.to_numeric(test["team_environment__off_plays_l4"], errors="coerce")
    fill = n.median() if np.isfinite(n.median()) else 62.0
    return np.rint(np.clip(n.fillna(fill).to_numpy(float), 5.0, None))


def assert_finite_predictive(qmat: np.ndarray, label: str) -> None:
    """A predictive with NaN cells is a SILENT PARTIAL FAILURE: `np.nanmean` averages the
    survivors, so the arm is scored on a different population than the rest of the field and the
    leaderboard is not a comparison. Refuse it (NF1.7 (a): a check that cannot fire is not a
    passed check — and here the metric would report a number rather than an error)."""
    bad = int((~np.isfinite(np.asarray(qmat, dtype=float))).sum())
    if bad:
        raise ValueError(
            f"arm `{label}` emitted {bad} non-finite quantile cells of {np.size(qmat)} — a NaN "
            f"predictive is scored on a silently different population by any nan-aware mean"
        )


def fit_betabinom(train, test, features, target: str = "pass_share", *, y_train=None) -> np.ndarray:
    """Beta-binomial: the binomial GLM mean plus a MoM concentration φ estimated from the excess
    variance of the train residual shares — the overdispersion hypothesis, tested not assumed."""
    import statsmodels.api as sm
    from scipy.stats import betabinom
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    sc = StandardScaler().fit(_X(train, features, med))
    Xtr = sm.add_constant(sc.transform(_X(train, features, med)), has_constant="add")
    Xte = sm.add_constant(sc.transform(_X(test, features, med)), has_constant="add")
    share = (train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float))
    n_tr = np.clip(train["off_plays"].to_numpy(float), 1.0, None)
    succ = np.clip(share, 0.0, 1.0) * n_tr
    res = sm.GLM(np.column_stack([succ, n_tr - succ]), Xtr,
                 family=sm.families.Binomial()).fit(maxiter=200)
    p_tr = np.clip(res.predict(Xtr), 1e-6, 1 - 1e-6)
    resid_var = float(np.nanmean((np.clip(share, 0, 1) - p_tr) ** 2))
    binom_var = float(np.nanmean(p_tr * (1 - p_tr) / n_tr))
    # Var(share) = p(1-p)/n · (1 + (n-1)/(φ+1)) ⇒ solve for φ; no excess ⇒ φ → ∞ ⇒ binomial.
    nbar = float(np.nanmean(n_tr))
    ratio = resid_var / binom_var if binom_var > 0 else 1.0
    phi = ((nbar - 1.0) / (ratio - 1.0) - 1.0) if ratio > 1.0 + 1e-9 else 1e6
    phi = float(np.clip(phi, 1.0, 1e6))
    p = np.clip(res.predict(Xte), 1e-6, 1 - 1e-6)
    n_te = _test_trials(test)
    a, b = phi * p, phi * (1.0 - p)
    return _clip_share(betabinom.ppf(Q_LEVELS[None, :], n_te[:, None], a[:, None], b[:, None])
                       / n_te[:, None])


def fit_lgbm_quantile(train, test, features, target: str, *, y_train=None) -> np.ndarray:
    """Distributional boosting: a 9-knot quantile bank interpolated onto the 39 levels."""
    Xtr = _X(train, features)
    Xte = _X(test, features)
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    ok = np.isfinite(y)
    knots = np.empty((len(test), len(FIT_LEVELS)))
    for j, a in enumerate(FIT_LEVELS):
        m = WP._lgbm({"objective": "quantile", "alpha": a, "n_estimators": 200,
                      "num_leaves": 31, "min_child_samples": 30})
        m.fit(Xtr[ok], y[ok])
        knots[:, j] = m.predict(Xte)
    q = WP.interp_to_levels(np.array(FIT_LEVELS), knots)
    return _clip_share(q) if target == "pass_share" else np.clip(q, 0.0, None)


def fit_knn_quantile(train, test, features, target: str, *, y_train=None, k: int = 200) -> np.ndarray:
    """Nonparametric neighbourhood: empirical quantiles of the k nearest train games."""
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    med = train_medians(train, features)
    Xtr, Xte = _X(train, features, med), _X(test, features, med)
    y = train[target].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    ok = np.isfinite(y)
    sc = StandardScaler().fit(Xtr[ok])
    kk = int(min(k, max(2, ok.sum() - 1)))
    nn = NearestNeighbors(n_neighbors=kk).fit(sc.transform(Xtr[ok]))
    _, idx = nn.kneighbors(sc.transform(Xte))
    return np.quantile(y[ok][idx], Q_LEVELS, axis=1).T


ARM_FITTERS = {
    "pois_glm": fit_pois_glm, "negbin_glm": fit_negbin_glm,
    "binom_glm": fit_binom_glm, "betabinom": fit_betabinom,
    "lgbm_quantile": fit_lgbm_quantile, "knn_quantile": fit_knn_quantile,
}


# ── Anchors ─────────────────────────────────────────────────────────────────────────────────────
def anchor_nihilist(test: pd.DataFrame) -> np.ndarray:
    """The literal all-zero degenerate — MEASURED every run, never reasoned about (NF-D14)."""
    return np.zeros((len(test), len(Q_LEVELS)))


def anchor_marginal(train: pd.DataFrame, test: pd.DataFrame, target: str) -> np.ndarray:
    y = train[target].to_numpy(float)
    y = y[np.isfinite(y)]
    return np.tile(np.quantile(y, Q_LEVELS), (len(test), 1))


def anchor_zero_width(point: np.ndarray) -> np.ndarray:
    return np.repeat(np.asarray(point, float)[:, None], len(Q_LEVELS), axis=1)


def anchor_max_width(point: np.ndarray, bank: np.ndarray, scale: float = 3.0) -> np.ndarray:
    return apply_bank(point, bank * scale)


def permute_within_week(train: pd.DataFrame, target: str, seed: int = _SEED) -> np.ndarray:
    """Target shuffled WITHIN global week — destroys TEAM identity while preserving every
    week-level marginal (schedule, era drift, league pace). The permuted arm must LOSE."""
    rng = np.random.default_rng(seed)
    y = train[target].to_numpy(float).copy()
    for _, idx in pd.Series(np.arange(len(train)), index=train["gw"].to_numpy()).groupby(level=0):
        pos = idx.to_numpy()
        if len(pos) > 1:
            y[pos] = rng.permutation(y[pos])
    return y


def matched_n_train(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """The most recent slice of TRAIN with about as many rows as the test block — the NF1.9 (f)
    capacity control, so 'the arm beat its own oracle' can be read as capacity rather than
    assumed to be leakage."""
    n = max(len(test), 50)
    return train.sort_values("gw").tail(n)


# ── Verdict vocabulary (three-way, DERIVED — never a stored two-way word; NF-W2e) ───────────────
def direction_word(mean_delta: float | None, lo: float | None, hi: float | None) -> str:
    """BEATS / TIES / LOSES TO, from the interval — FAILING CLOSED TO `TIES` when the interval is
    absent or unevaluable. A two-way `BEATS if d>0 else LOSES TO` narrates a genuine tie as a loss
    and can invert a conclusion off identical arithmetic (the NF-W2e reporting defect)."""
    if mean_delta is None or lo is None or hi is None or not all(
            np.isfinite([mean_delta, lo, hi])):
        return "TIES"
    if lo > 0:
        return "BEATS"
    if hi < 0:
        return "LOSES TO"
    return "TIES"


def verdict_sentence(label: str, foil: str, mean_delta: float | None,
                     lo: float | None, hi: float | None) -> str:
    """The WORD and its PARENTHETICAL are computed together so they cannot contradict each other
    (the other half of the NF-W2e fix: a `TIES … (excludes zero)` sentence is self-contradicting
    and a reader trusts the parenthetical)."""
    word = direction_word(mean_delta, lo, hi)
    if word == "TIES":
        detail = ("interval unevaluable" if mean_delta is None or lo is None or hi is None
                  else f"CI95 [{lo:+.4f}, {hi:+.4f}] spans zero")
    else:
        detail = f"CI95 [{lo:+.4f}, {hi:+.4f}] excludes zero"
    md = "n/a" if mean_delta is None else f"{mean_delta:+.4f}"
    return f"`{label}` {word} `{foil}` by {md} CRPS ({detail})"


def paired_ci95(deltas: np.ndarray) -> tuple[float | None, float | None, float | None]:
    d = np.asarray(deltas, float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return (float(np.mean(d)) if len(d) else None, None, None)
    from scipy.stats import t as student_t
    sd = float(d.std(ddof=1))
    se = sd / np.sqrt(len(d))
    if se <= 0:
        return float(d.mean()), float(d.mean()), float(d.mean())
    h = float(student_t.ppf(0.975, len(d) - 1)) * se
    return float(d.mean()), float(d.mean() - h), float(d.mean() + h)


# ── Gate composition ────────────────────────────────────────────────────────────────────────────
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
)
STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)


def compose_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["nihilist_loses"]
                                 and sel["anchors"]["marginal_loses"]
                                 and sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        # ⭐ the floor is enforced AT MATCHED n (NF1.9 (f)), not strictly: an arm may legitimately
        # beat a peeking oracle of its own form when the oracle is capacity-starved on the test
        # block. The STRICT reading is reported beside it so nothing hides behind the admission.
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}


# ── Layer B's own check sets + classifier ───────────────────────────────────────────────────────
LAYER_B_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_champion", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)
LAYER_B_ANCHOR_CHECKS: tuple[str, ...] = ("permutation_behaves", "oracle_floor_respected")

#: CSCV/PBO resamples a FIELD of configurations; with fewer than two it has nothing to resample.
PBO_MIN_CONFIGS = 2


def pbo_is_evaluable(n_real_arms: int) -> bool:
    """PBO answers 'did SELECTING this config out of a field cost anything out of sample'. A single
    PRE-REGISTERED contrast is not a selection — there was no search to overfit — so CSCV is
    structurally inapplicable and its value is **UNDEFINED, not failed** (MH2's fold-count rule,
    one axis over: field size instead of fold count)."""
    return n_real_arms >= PBO_MIN_CONFIGS


def classify_layer_b(sel: dict, *, n_folds: int, instrument_verdict: dict | None = None) -> dict:
    """Layer B's null state, hand-classified — and WHY that is necessary rather than lazy.

    `cv_power.classify_null` takes `n_arms` as BOTH the DSR trial count and the CSCV config count.
    Layer B fields exactly ONE real arm by pre-registration, so the honest `n_arms=1` drives
    `pbo_evaluable` false and the instrument returns `UNDEFINED`. This is the third time in this
    vertical that `classify_null` has needed a hand correction (NF-W2 → CONSTRAINT_REFUSED, NF-D18 →
    the 8th state, now the field-size axis), so the instrument's verdict is RECORDED alongside
    rather than discarded.

    ✅ **UPDATED BY MH2.7 (2026-08-14) — HALF OF THIS IS NO LONGER TRUE, AND SAYING SO MATTERS more
    in a docstring than in a doc (the next reader takes the premise from here).** This function used
    to note that the instrument *rendered the cause as a FOLD shortage ("8 fold(s) < 4") and
    published a NEGATIVE trigger ("-4 more fold(s)")*. MH2.7 fixed exactly that in `cv_power`: a
    single pre-registered contrast now reports PBO as INAPPLICABLE-not-unmet and publishes **no
    trigger at all**. ⚠️ The hand correction is STILL REQUIRED — `UNDEFINED`-with-no-trigger is a
    correct non-verdict, not Layer B's state, and only the caller knows the remaining gates are
    reachable ⇒ POWER_LIMITED. What is gone is the misleading record it used to overwrite.

    The states, from the same numbers:
      · the arm loses ON AVERAGE ⇒ **GENUINE ABSENCE** — no `n` and no field size rescues a
        negative point estimate, and ⛔ no re-test trigger may be published (MH2);
      · otherwise ⇒ **POWER_LIMITED**, with the shortfall stated in the unit that grows (folds).
    """
    out: dict = {"instrument_verdict": instrument_verdict,
                 "hand_corrected": instrument_verdict is not None
                 and instrument_verdict.get("state") == "UNDEFINED",
                 "pbo_state": (
                     "UNDEFINED — CSCV resamples a FIELD; Layer B fields ONE pre-registered "
                     "contrast, so there was no search to overfit. Reported as undefined, NOT as "
                     "a failed deflation gate."),
                 }
    if not sel["beats_foil"]:
        out.update({
            "state": "GENUINE_ABSENCE",
            "reason": (f"the arm LOSES to the champion on average "
                       f"({sel['mean_delta']:+.4f} CRPS over {n_folds} folds, "
                       f"{sel['fold_wins']}/{n_folds} fold wins) — a negative point estimate is "
                       f"not rescued by more folds or a smaller field."),
            "retest_trigger": None,
        })
        return out
    sr = sel.get("observed_sr")
    folds_needed = None
    if sr and sr > 0:
        # sr0 = 0 for a single trial (nothing to deflate), so DSR ≥ 0.95 needs sr·√(n−1) > z(0.95)
        folds_needed = int(np.ceil((1.6448536269514722 / sr) ** 2)) + 1
    # ⭐ NF-W2e's word-vs-parenthetical rule applies to the classifier's reason too: the CI
    # relationship is DERIVED, never asserted ("spans zero" hardcoded here once described an
    # interval that excluded zero — caught at the NF-W7 record).
    lo, hi = (sel["ci95"] or (None, None))[:2]
    ci_word = ("spans zero" if lo is not None and hi is not None and lo <= 0.0 <= hi
               else "excludes zero" if lo is not None and hi is not None
               else "is unevaluable")
    out.update({
        "state": "POWER_LIMITED",
        "reason": (f"the point estimate is positive ({sel['mean_delta']:+.4f} CRPS) and the "
                   f"interval {ci_word} (CI95 {sel['ci95']}), fold wins are "
                   f"{sel['fold_wins']}/{n_folds} against a required "
                   f"{sel['fold_clause']['required']}, and p={sel['p_one_sided']}. Every "
                   f"EVALUABLE statistical gate is REACHABLE at this design (see `pbo_state` for "
                   f"whether PBO is one of them) — the effect is simply smaller than this design "
                   f"can resolve."),
        "retest_trigger": (
            f"~{folds_needed} half-season folds (≈{folds_needed // 2} seasons) for the DSR gate at "
            f"the observed per-fold Sharpe {sr} — i.e. CALENDAR-bound and far beyond any plausible "
            f"window; ⛔ this is NOT a near-term re-test."
            if folds_needed else "unevaluable — no positive per-fold Sharpe to extrapolate from"),
    })
    return out


def flag_unsafe_field_shrink(verdict: dict, n_declared_arms: int) -> dict:
    """⚠️ MH2.2: `classify_null`'s "the remedy is a SMALLER field" text is UNSAFE when the field is
    already the DECLARED minimum — shrinking below a pre-registered family re-commits the exact
    selection bias DSR exists to deflate, inside a badge that READS LIKE A FIX. The instrument sees
    only a trial COUNT and cannot tell a DECLARED narrow family from a DISCOVERED one, so the
    caller must flag it. Reported, never acted on."""
    import re
    text = f"{verdict.get('reason', '')} {verdict.get('retest_trigger', '')}"
    m = re.search(r"field of ≤\s*(\d+)\s*arms", text)
    suggests_shrink = bool(m) or "SMALLER" in text
    if not suggests_shrink:
        return dict(verdict)
    proposed = int(m.group(1)) if m else None
    unsafe = proposed is None or proposed < n_declared_arms
    out = dict(verdict)
    out["field_shrink_flag"] = {
        "proposed_field_size": proposed,
        "declared_family_size": n_declared_arms,
        "status": "SUSPECT — NOT ADVICE" if unsafe else "admissible",
        "note": (
            f"the instrument suggests a smaller field, but this story's family of "
            f"{n_declared_arms} arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a "
            f"direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the "
            f"selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as "
            f"advice: you may PRE-REGISTER a family, you may not DISCOVER one."
            if unsafe else
            f"the proposed field ({proposed}) is not below the declared family ({n_declared_arms})"),
    }
    return out


def gate_sensitivity(checks: dict, waived: tuple[str, ...]) -> dict:
    """⭐ NF-D15 (g″): prove the null does NOT rest on YOUR gate choice. Waive the named checks and
    report what still refuses. Purely REPORTED — it changes no verdict, and a check waived here is
    still a failed check in `checks`."""
    remaining = [k for k, v in checks.items() if not v and k not in waived]
    return {"waived": list(waived), "still_refusing": remaining,
            "ships_without_waived_checks": not remaining}


def hand_classify_refusal(checks: dict) -> dict | None:
    """The hand-check `cv_power.classify_null` cannot do (the NF-D18 / MH2.7 instrument gap, which
    has already mis-fired twice in this vertical): when every STATISTICAL gate passes and the null
    rests only on anchor/registration clauses, the state is CONSTRAINT_REFUSED — more data makes
    the clause fail HARDER and ⛔ no sample-size re-test trigger may be published."""
    stat_fail = [c for c in STATISTICAL_CHECKS if not checks.get(c, True)]
    anchor_fail = [c for c in ANCHOR_CHECKS if not checks.get(c, True)]
    if stat_fail or not anchor_fail:
        return None
    return {
        "state": "CONSTRAINT_REFUSED",
        "reason": ("hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical gate "
                   f"passed and the null rests entirely on anchor/registration clauses "
                   f"{anchor_fail}. More data cannot change this verdict."),
        "retest_trigger": None,
        "failing_anchor_checks": anchor_fail,
    }
