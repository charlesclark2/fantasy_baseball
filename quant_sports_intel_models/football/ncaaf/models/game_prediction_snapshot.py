"""game_prediction_snapshot.py — NCAAF-PS: PERSIST a pre-kickoff per-game predictive.

WHAT THIS IS (and deliberately is not)
--------------------------------------
The P1.4 game model and the P1.5 futures board are both LIVE, but nothing has ever *written down*
what the model said about a specific upcoming game BEFORE it kicked off. Without that row there is
no forward track record — only a backtest, which can always be re-derived and therefore proves
nothing about what we would have said in advance. This module closes exactly that gap and nothing
else: it runs the ALREADY-SERVED model over the upcoming FBS-vs-FBS slate and appends one immutable
row per (game_id, snapshot_ts) to the lake.

⛔ NOT P3.1. There is no serving store, no API, no app surface here. This is the precursor that
makes those honest later — the snapshots accrue from 8/29 forward, so whenever the app ships it can
show a real pre-kickoff record instead of a backtest.

⭐ IT DOES NOT RE-IMPLEMENT THE MODEL. μ comes from the served MEAN artifact
(`ncaaf_game_mean_v2.json`, `NcaafGameMeanParams.predict`), the predictive width + the joint draw
come from the served DISPERSION artifact via `ncaaf_game_predictor.sample_matchup`, and the three
markets are read off that ONE joint sample by `derive_markets` / `market_probabilities` — exactly
as P1.4 defines them (H2H = P(margin>0)). What this module owns is the *slate assembly* (which
games, which strengths, which instant) and the *persistence*.

🔒 THE LEAKAGE CONTRACT — DATE-BASED, NEVER WEEK-BASED
-----------------------------------------------------
Every persisted row must satisfy `snapshot_ts < commence_time`. Two independent mechanisms:

  1. SELECTION — the slate is chosen by KICKOFF INSTANT inside a forward window, never by CFBD
     `week`. CFBD restarts `week` at 1 for the postseason (the P1.1 leak; the P0.6b landmine), so
     any week-grained selection or assertion re-uses a broken ordering and passes green while
     being wrong. A kickoff timestamp cannot lie about which games have started.
  2. THE GATE — `assert_pre_kickoff` re-checks the FINAL rows at the write boundary and REFUSES the
     whole write if any row's kickoff is at or before the snapshot instant. It is deliberately a
     second, independent assertion rather than a restatement of the filter: a filter bug, a stale
     `commence_time`, or a hand-assembled row must not be able to reach the lake.

The strength inputs inherit P1.2's own DATE-based point-in-time gate
(`assert_team_strength_is_point_in_time`) — a strength row at `as_of_week = W` is fitted strictly
on games before W. This module does not re-derive that; it records which `as_of_week` it read so a
reader can audit the vintage.

♻️ APPEND-ONLY / READ-MERGE-WRITE
---------------------------------
`s3io.write_season_partition` OVERWRITES a season partition — a weekly re-run that wrote only the
new week would DELETE every prior week of the season (the exact P0.6b landmine). So the writer
READS the season's existing snapshot rows, drops only those whose (game_id, snapshot_ts) the new
batch re-covers (an idempotent re-run is a value-identical rewrite), and writes the union. The read
goes through `query_lake.query_or_missing`, which RAISES on a transient read failure rather than
returning "nothing there" — because "I could not read it" must never be mistaken for a licence to
overwrite.

📣 HONEST FRAMING (`best_alpha = 0`)
------------------------------------
The payload carries PROBABILITIES and DISTRIBUTIONAL INTERVALS and nothing else. There is no pick,
no edge, no recommended side, no win-rate — P1.4's CLV leg came back a clean null (ATS 0.496 =
placebo), so a pick column would be a claim the evidence does not support. `assert_no_edge_claim`
makes that a mechanical property of the schema, not a promise in a docstring.

⚠️ TWO LIMITS OF THE SERVED MODEL, STATED RATHER THAN PATCHED
-------------------------------------------------------------
* NO NEUTRAL-SITE TERM. The served `strength_pace` contract carries no neutral-site column, so the
  intercept absorbs one blended home-field bump (P2.1 measured this; 7.93% of games are neutral).
  A neutral-site game is therefore priced with that same bump. We persist `is_neutral_site` so the
  limitation is visible and auditable — inventing a correction here would serve a model nobody
  certified.
* PACE IS INERT PRE-SEASON. The certified S1/S1b pace composites are NULL at week 1 (the team-week
  rollup's honest empty row), and a NULL column contributes EXACTLY 0.0 to a mean-imputed ridge.
  That is why an opening-week snapshot is byte-identical to a pace-free one — and why every row
  carries `pace_term_active`, so "no pace" is recorded, never silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.ncaaf.ingest import query_lake, s3io
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    NcaafGameDistributionParams,
)
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_mean import NcaafGameMeanParams
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_predictor import (
    market_probabilities,
    matchup_sigma,
    sample_matchup,
)
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import PACE_COMPOSITE_COLS

log = logging.getLogger("ncaaf.prediction_snapshot")

# ── lake location ───────────────────────────────────────────────────────────────────────────
SPORT = "ncaaf"
LAKE_TIER = "derived"
#: one row per (game_id, snapshot_ts) — the pre-kickoff per-game predictive.
SNAPSHOT_SOURCE = "game_prediction_snapshots"
#: one row per (team_id, snapshot_ts) — the weekly P1.5 futures board, snapshotted (NOT the
#: `season_simulation_board` table, which is a season-partition OVERWRITE and keeps no history).
FUTURES_SNAPSHOT_SOURCE = "futures_board_snapshots"

GAME_SNAPSHOT_KEY: tuple[str, ...] = ("game_id", "snapshot_ts")
FUTURES_SNAPSHOT_KEY: tuple[str, ...] = ("team_id", "snapshot_ts")

#: the snapshot's kind — one value today; a column so a later T-1 / intraday cadence is additive
#: rather than a schema change (the P0.6c `_snapshot_kind` shape).
SNAPSHOT_KIND_PRE_KICKOFF = "pre_kickoff"

#: what the payload IS. Read by any consumer that renders it; asserted by `assert_no_edge_claim`.
FRAMING = "market_blind_projection"

#: the quantiles persisted per target — enough to draw the distributional curve the NCAAF brand
#: directive leads with, without persisting a 10k-draw sample per game.
PERSISTED_QUANTILES: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)

#: the central interval quoted as "the interval" in any summary (80%, matching P1.4's calib_80).
INTERVAL_LO, INTERVAL_HI = 0.10, 0.90

# ── the served-contract strength columns ────────────────────────────────────────────────────
#
# A 1:1 rename of `ncaaf_team_strength_week` → the P1.3 matrix's `home_*`/`away_*` names. This
# MIRRORS `feature_ncaaf_pregame_matrix.sql` L183-194 / L278-289 exactly; it is a join, not a
# model. ⚠️ It is a SECOND renderer of that mapping, which is only safe because
# `assert_contract_covered` refuses to score unless every served non-pace column is present —
# a column that silently went missing would be mean-imputed to EXACTLY 0.0 and we would serve a
# quietly different model with no error (the NF-C0e wrong-key class).
STRENGTH_COLUMN_MAP: tuple[tuple[str, str], ...] = (
    ("strength_margin", "strength_margin"),
    ("strength_margin_sd", "strength_margin_sd"),
    ("strength_offense", "strength_offense"),
    ("strength_defense", "strength_defense"),
    ("strength_conference_component", "strength_conf_component"),
    ("strength_covariate_component", "strength_cov_component"),
    ("strength_team_component", "strength_team_component"),
    ("covariate_component_roster_flux", "strength_cov_roster_flux"),
    ("covariate_component_coaching", "strength_cov_coaching"),
    ("covariate_component_talent", "strength_cov_talent"),
    ("hyper_n_prior_seasons", "strength_hyper_prior_seasons"),
    ("has_sufficient_sample", "strength_has_sufficient_sample"),
)

#: the derived cross-side column the served contract carries beyond the per-side renames.
STRENGTH_DIFF_COL = "strength_margin_diff"

#: tokens a market-blind projection payload may never carry (the honest-framing guard).
FORBIDDEN_PAYLOAD_TOKENS: tuple[str, ...] = (
    "edge", "pick", "bet", "wager", "win_rate", "roi", "clv", "recommend", "kelly", "alpha",
    "value_side", "best_side",
)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Slate + strengths (lake reads)
# ══════════════════════════════════════════════════════════════════════════════════════════

def _iso(ts: datetime) -> str:
    """A UTC ISO-8601 instant with a `Z` suffix — the same string form the odds lake stores, so a
    snapshot_ts and a commence_time compare identically as text or as timestamps."""
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_ts(ts: datetime) -> pd.Timestamp:
    """`datetime` → a UTC `pd.Timestamp`, accepting either an aware or a naive input.

    A naive instant is READ as UTC rather than as local time: every timestamp in this vertical is
    UTC (CFBD kickoffs, the odds lake, the snapshot instant), and silently applying a machine's
    local zone would shift the leakage comparison by hours on a laptop (the E11.20 phase-2b
    LTZ/NTZ class, one layer down).
    """
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


_SLATE_SQL = """
select
    json_extract_string(raw_json,'$.id')::bigint            as game_id,
    season,
    json_extract_string(raw_json,'$.week')::int             as week,
    json_extract_string(raw_json,'$.seasonType')            as season_type,
    json_extract_string(raw_json,'$.startDate')             as commence_time,
    coalesce(json_extract_string(raw_json,'$.startTimeTBD') = 'true', false) as start_time_tbd,
    coalesce(json_extract_string(raw_json,'$.completed')    = 'true', false) as is_completed,
    coalesce(json_extract_string(raw_json,'$.neutralSite')  = 'true', false) as is_neutral_site,
    coalesce(json_extract_string(raw_json,'$.conferenceGame') = 'true', false) as is_conference_game,
    json_extract_string(raw_json,'$.homeId')::bigint        as home_team_id,
    json_extract_string(raw_json,'$.homeTeam')              as home_team,
    json_extract_string(raw_json,'$.homeConference')        as home_conference,
    json_extract_string(raw_json,'$.awayId')::bigint        as away_team_id,
    json_extract_string(raw_json,'$.awayTeam')              as away_team,
    json_extract_string(raw_json,'$.awayConference')        as away_conference,
    try_cast(json_extract_string(raw_json,'$.homePoints') as double) as home_points,
    try_cast(json_extract_string(raw_json,'$.awayPoints') as double) as away_points
from {games}
where season = {season}
  and json_extract_string(raw_json,'$.homeClassification') = 'fbs'
  and json_extract_string(raw_json,'$.awayClassification') = 'fbs'
"""


def load_season_games(season: int, *, local_root: str | None = None) -> pd.DataFrame:
    """Every FBS-vs-FBS game of `season` from the raw lake, with its KICKOFF INSTANT.

    Reads the raw `games` Delta directly rather than the `dim_ncaaf_game` mart, deliberately: the
    mart lives in `sports.duckdb`, which is gitignored and therefore ABSENT from the box image
    unless the named volume happens to be populated (NF-INFRA1) — a snapshot op that silently
    depends on a deploy-ephemeral file is the class of bug that produced 19 green runs over a
    frozen table. The lake is the durable source, and everything this module needs is on it.
    """
    expr = query_lake.local("games", local_root) if local_root else query_lake.delta("games")
    df = query_lake.query_or_missing(_SLATE_SQL.format(games=expr, season=int(season)))
    if df is None:
        raise RuntimeError(
            f"the `games` Delta has no partition to read for season {season}. This is NOT a "
            "no-op: run the P0.7 roll-forward (`sports_ncaaf_roll_forward_job`) so the upcoming "
            "season's schedule is in the lake.")
    return df


def load_strength_week(season: int, as_of_week: int | None = None, *,
                       local_root: str | None = None) -> tuple[pd.DataFrame, int]:
    """The P1.2 team-strength posteriors for `season` at ONE `as_of_week` (default: the LATEST
    emitted for that season) → (frame, resolved_as_of_week).

    "Latest emitted" is the right default and is leakage-safe by construction: P1.2 emits a row at
    `as_of_week = W` fitted STRICTLY on games with `season_order_week < W`, under its own
    DATE-based point-in-time gate. Picking the newest available vintage therefore gives the most
    current honest estimate; the chosen week is persisted on every row so the vintage is auditable
    rather than assumed.
    """
    expr = (query_lake.local("team_strength_week", local_root, tier=LAKE_TIER) if local_root
            else query_lake.delta("team_strength_week", tier=LAKE_TIER))
    df = query_lake.query_or_missing(f"select * from {expr} where season = {int(season)}")
    if df is None or df.empty:
        raise RuntimeError(
            f"no P1.2 strength rows in the lake for season {season}. A snapshot cannot be taken "
            "without them — re-fit P1.2 for the season (`run_team_strength.py --s3`) first. "
            "(Refusing rather than degrading: a snapshot built off another season's strengths "
            "would be silently wrong, and a snapshot is not retakeable after kickoff.)")
    weeks = sorted(int(w) for w in df["as_of_week"].dropna().unique())
    week = weeks[-1] if as_of_week is None else int(as_of_week)
    rows = df[df["as_of_week"] == week].reset_index(drop=True)
    if rows.empty:
        raise RuntimeError(
            f"season {season} has no strength rows at as_of_week={week}; emitted weeks: {weeks}")
    return rows, week


def select_upcoming_slate(games: pd.DataFrame, snapshot_ts: datetime, *,
                          horizon_days: float = 7.0,
                          min_lead_minutes: float = 0.0) -> pd.DataFrame:
    """The games whose KICKOFF falls in `(snapshot_ts + min_lead, snapshot_ts + horizon]`.

    ⭐ DATE-BASED, NOT WEEK-BASED. CFBD numbers postseason games "week 1, 2, 3…", colliding with
    the regular season (the P1.1 leak / the P0.6b kickoff-grain fix), so a week-grained selection
    is wrong in exactly the window — December/January — where a mistake is least visible. A kickoff
    instant carries no such ambiguity.

    `min_lead_minutes` is the K−buffer: a game kicking off in the next few minutes is skipped
    rather than raced. A game already under way is excluded here AND would be refused by
    `assert_pre_kickoff` at the write boundary.
    """
    if games.empty:
        return games.copy()
    out = games.copy()
    out["commence_dt"] = pd.to_datetime(out["commence_time"], utc=True, errors="coerce")
    lo = _utc_ts(snapshot_ts) + pd.Timedelta(minutes=float(min_lead_minutes))
    hi = _utc_ts(snapshot_ts) + pd.Timedelta(days=float(horizon_days))
    sel = out[(out["commence_dt"].notna()) & (out["commence_dt"] > lo) & (out["commence_dt"] <= hi)]
    return sel.sort_values(["commence_dt", "game_id"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Frame assembly (PURE — no IO, fully unit-tested)
# ══════════════════════════════════════════════════════════════════════════════════════════

def build_slate_frame(slate: pd.DataFrame, strength: pd.DataFrame, *,
                      pace_by_team: Mapping[int, float] | None = None) -> pd.DataFrame:
    """Attach each side's P1.2 strength posterior to the slate under the SERVED contract's column
    names, plus the pace composites. PURE — `slate`/`strength` are already-read frames.

    Rows whose home or away team has no strength row are DROPPED (a team the strength model never
    emitted cannot be priced) and counted by the caller — never silently imputed, which would
    manufacture a confident prediction out of nothing.
    """
    if slate.empty:
        return slate.copy()
    keep = ["team_id"] + [src for src, _ in STRENGTH_COLUMN_MAP] + ["games_in_window"]
    missing_src = [c for c in keep if c not in strength.columns]
    if missing_src:
        raise KeyError(
            f"the strength frame is missing {missing_src} — the served contract cannot be "
            "assembled. A missing column would be mean-imputed to exactly 0.0 and we would serve "
            "a quietly different model with no error (NF-C0e).")
    s = strength[keep].copy()
    s["team_id"] = s["team_id"].astype("int64")

    out = slate.copy()
    for side in ("home", "away"):
        ren = {src: f"{side}_{dst}" for src, dst in STRENGTH_COLUMN_MAP}
        ren["games_in_window"] = f"{side}_strength_games_in_window"
        part = s.rename(columns=ren).rename(columns={"team_id": f"{side}_team_id"})
        out = out.merge(part, on=f"{side}_team_id", how="left", validate="many_to_one")

    unpriceable = out["home_strength_margin"].isna() | out["away_strength_margin"].isna()
    if unpriceable.any():
        log.warning(
            "[ALERT] %d of %d slate game(s) have no P1.2 strength row on one or both sides and are "
            "DROPPED (not imputed): %s", int(unpriceable.sum()), len(out),
            ", ".join(f"{r.away_team}@{r.home_team}"
                      for r in out[unpriceable].itertuples(index=False)))
        out = out[~unpriceable].reset_index(drop=True)

    out[STRENGTH_DIFF_COL] = out["home_strength_margin"] - out["away_strength_margin"]
    out = _attach_pace(out, pace_by_team)
    return out


def _attach_pace(frame: pd.DataFrame, pace_by_team: Mapping[int, float] | None) -> pd.DataFrame:
    """Add `pace_sum` / `pace_diff` via the ONE certified derivation.

    ⭐ Reuses `p2_1_blocks.derive_pace_composites`, the same function the S1 certification and the
    P1.4 serving assemble call — a second implementation of the served representation would be two
    rule sets (E9.61). NULL propagates: an unknown tempo on either side ⇒ both composites NULL ⇒
    the served pace term contributes EXACTLY 0.0 (mean-imputation), which is the honest pre-season
    answer and is recorded via `pace_term_active`, never silent.
    """
    from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import (
        PACE_SIDE_COL,
        derive_pace_composites,
    )

    out = frame.copy()
    pace = dict(pace_by_team or {})
    for side in ("home", "away"):
        out[f"{side}_{PACE_SIDE_COL}"] = [
            float(pace[int(t)]) if int(t) in pace else np.nan for t in out[f"{side}_team_id"]
        ]
    return derive_pace_composites(out)


def assert_contract_covered(frame: pd.DataFrame, mean: NcaafGameMeanParams) -> None:
    """REFUSE to score unless every served column is on the frame.

    An absent column is mean-imputed and contributes exactly 0.0 — silently, with no error. So a
    typo, a renamed strength field, or an upstream schema change would not fail; it would serve a
    DIFFERENT model that looks fine. This turns that into a hard stop. Pace columns are exempt from
    the *presence* requirement only in the sense that they may be all-NULL (inert by design) — the
    columns themselves must still exist.
    """
    missing = [c for c in mean.columns if c not in frame.columns]
    if missing:
        raise KeyError(
            f"the slate frame is missing served-contract column(s) {missing}. Scoring anyway "
            "would mean-impute them to exactly 0.0 and serve a quietly different model than the "
            f"one certified as {mean.learner}/{mean.contract} (NF-C0e). Fix the assembly.")
    non_pace = [c for c in mean.columns if c not in PACE_COMPOSITE_COLS]
    all_null = [c for c in non_pace if frame[c].isna().all()]
    if all_null:
        raise ValueError(
            f"served-contract column(s) {all_null} are entirely NULL on this slate — they would "
            "contribute exactly 0.0 for every game, which is a silently different model, not a "
            "prediction. (Pace columns are allowed to be NULL; these are not.)")


# ══════════════════════════════════════════════════════════════════════════════════════════
# Scoring — the SERVED model, called not re-implemented
# ══════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ServedModel:
    """The served (dispersion, mean) pair plus where the dispersion was resolved from."""

    dispersion: NcaafGameDistributionParams
    mean: NcaafGameMeanParams
    dispersion_path: str

    @property
    def version(self) -> str:
        return str(self.dispersion.version)


def load_served_model(artifact_dir: Any = None) -> ServedModel:
    """The served pair, REFUSING a mean-less or mismatched pair.

    `load_served_pair` already raises when the dispersion and mean were fitted on different
    (learner, contract) — the E7.9 train/serve mismatch. A missing MEAN artifact returns `None`
    there (the pre-S1-serve state); this module refuses it outright, because μ is not optional for
    a per-game prediction and the analytic fallback the season sim uses is a DIFFERENT model.
    """
    from quant_sports_intel_models.football.ncaaf.models import ncaaf_game_predictor as gp

    disp, mean, path = (gp.load_served_pair(artifact_dir) if artifact_dir is not None
                        else gp.load_served_pair())
    if mean is None:
        raise FileNotFoundError(
            "no served MEAN artifact — a per-game snapshot needs μ, and the season sim's analytic "
            "strength map is a different model, not a fallback. Run "
            "`bakeoff_ncaaf_game --stage finalize` to write one.")
    return ServedModel(dispersion=disp, mean=mean, dispersion_path=str(path))


def predict_slate(frame: pd.DataFrame, served: ServedModel, *, n_draws: int = 20_000,
                  seed: int = 20260829) -> pd.DataFrame:
    """Score the assembled slate with the SERVED model → per-game probabilities + quantiles.

    The whole predictive comes from the served artifacts: μ from `NcaafGameMeanParams.predict`, the
    per-game width + the joint (margin,total) draw from `ncaaf_game_predictor.sample_matchup`, and
    the markets from `market_probabilities` — P1.4's own derivation (H2H = P(margin>0)).

    `fixed_strength=False` — the FULL posterior-predictive for a standalone game. That is the
    serving mode: the per-game σ propagates the P1.2 strength-posterior uncertainty
    (σ² = σ₀² + k²·[home_sd² + away_sd²]). `fixed_strength=True` is the season-sim mode and would
    UNDER-state a single game's width by stripping a term the sim supplies elsewhere.
    """
    assert_contract_covered(frame, served.mean)
    if frame.empty:
        return frame.copy()

    values = {c: pd.to_numeric(frame[c], errors="coerce").to_numpy(float) for c in served.mean.columns}
    mu_margin = served.mean.predict(values, "margin")
    mu_total = served.mean.predict(values, "total")

    sd_h = pd.to_numeric(frame["home_strength_margin_sd"], errors="coerce").to_numpy(float)
    sd_a = pd.to_numeric(frame["away_strength_margin_sd"], errors="coerce").to_numpy(float)
    strength_var = np.nan_to_num(sd_h, nan=0.0) ** 2 + np.nan_to_num(sd_a, nan=0.0) ** 2

    sigma_margin, sigma_total = matchup_sigma(served.dispersion, strength_var, fixed_strength=False)

    rng = np.random.default_rng(seed)
    markets = sample_matchup(served.dispersion, mu_margin, mu_total, strength_var, rng,
                             n_draws=int(n_draws), fixed_strength=False)
    probs = market_probabilities(markets)

    out = frame.copy()
    out["mu_margin"] = np.asarray(mu_margin, float)
    out["mu_total"] = np.asarray(mu_total, float)
    out["sigma_margin"] = np.asarray(sigma_margin, float)
    out["sigma_total"] = np.asarray(sigma_total, float)
    out["p_home_win"] = np.atleast_1d(np.asarray(probs["p_home_win"], float))
    for target, sample in (("margin", markets["margin"]), ("total", markets["total"])):
        arr = np.atleast_2d(np.asarray(sample, float))
        qs = np.quantile(arr, PERSISTED_QUANTILES, axis=1)
        for level, row in zip(PERSISTED_QUANTILES, qs):
            out[f"{target}_q{int(round(level * 100)):02d}"] = row
    lo, hi = int(round(INTERVAL_LO * 100)), int(round(INTERVAL_HI * 100))
    for target in ("margin", "total"):
        out[f"{target}_interval_width"] = out[f"{target}_q{hi:02d}"] - out[f"{target}_q{lo:02d}"]
    out["n_draws"] = int(n_draws)
    return out


def analytic_margin_mu(frame: pd.DataFrame, hfa: float) -> np.ndarray:
    """P1.5's analytic strength map for μ_margin — a DIAGNOSTIC, never the served number.

    `μ = HFA·(not neutral) + (strength_margin_home − strength_margin_away)`. Comparing it to the
    served ridge's μ is a cheap sanity read on the slate assembly (a mis-joined strength side shows
    up immediately as a large disagreement). It is NOT a fallback and is never persisted as μ: the
    served ridge carries no neutral-site term, so the two legitimately differ on neutral games.
    """
    neutral = frame["is_neutral_site"].astype(bool).to_numpy()
    diff = pd.to_numeric(frame[STRENGTH_DIFF_COL], errors="coerce").to_numpy(float)
    return diff + np.where(neutral, 0.0, float(hfa))


# ══════════════════════════════════════════════════════════════════════════════════════════
# The persisted rows + the leakage gate
# ══════════════════════════════════════════════════════════════════════════════════════════

_ROW_COLUMNS: tuple[str, ...] = (
    "season", "game_id", "snapshot_ts", "snapshot_kind", "commence_time", "lead_minutes",
    "start_time_tbd", "cfbd_week", "season_type",
    "home_team_id", "home_team", "home_conference",
    "away_team_id", "away_team", "away_conference",
    "is_neutral_site", "is_conference_game",
    "p_home_win",
    "mu_margin", "sigma_margin", "margin_q05", "margin_q10", "margin_q25", "margin_q50",
    "margin_q75", "margin_q90", "margin_q95", "margin_interval_width",
    "mu_total", "sigma_total", "total_q05", "total_q10", "total_q25", "total_q50",
    "total_q75", "total_q90", "total_q95", "total_interval_width",
    "strength_as_of_week", "home_strength_margin", "home_strength_margin_sd",
    "away_strength_margin", "away_strength_margin_sd",
    "home_strength_games_in_window", "away_strength_games_in_window",
    "pace_term_active", "n_draws",
    "model_version", "model_form", "model_learner", "model_contract", "mean_artifact_version",
    "framing", "best_alpha",
)


def build_snapshot_rows(scored: pd.DataFrame, served: ServedModel, *, snapshot_ts: datetime,
                        strength_as_of_week: int) -> pd.DataFrame:
    """The exact frame that gets persisted — typed, flat, and free of any edge/pick column."""
    if scored.empty:
        return pd.DataFrame(columns=list(_ROW_COLUMNS))
    commence = pd.to_datetime(scored["commence_time"], utc=True, errors="coerce")
    snap = _utc_ts(snapshot_ts)
    pace_active = bool(scored["pace_sum"].notna().any())

    out = pd.DataFrame({
        "season": scored["season"].astype("int64"),
        "game_id": scored["game_id"].astype("int64"),
        "snapshot_ts": _iso(snapshot_ts),
        "snapshot_kind": SNAPSHOT_KIND_PRE_KICKOFF,
        "commence_time": commence.dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "lead_minutes": ((commence - snap).dt.total_seconds() / 60.0).astype(float),
        "start_time_tbd": scored["start_time_tbd"].astype(bool),
        "cfbd_week": scored["week"].astype("int64"),
        "season_type": scored["season_type"].astype(str),
        "home_team_id": scored["home_team_id"].astype("int64"),
        "home_team": scored["home_team"].astype(str),
        "home_conference": scored["home_conference"].astype(str),
        "away_team_id": scored["away_team_id"].astype("int64"),
        "away_team": scored["away_team"].astype(str),
        "away_conference": scored["away_conference"].astype(str),
        "is_neutral_site": scored["is_neutral_site"].astype(bool),
        "is_conference_game": scored["is_conference_game"].astype(bool),
        "p_home_win": scored["p_home_win"].astype(float),
        "strength_as_of_week": int(strength_as_of_week),
        "pace_term_active": pace_active,
        "n_draws": scored["n_draws"].astype("int64"),
        "model_version": served.version,
        "model_form": str(served.dispersion.form),
        "model_learner": str(served.dispersion.learner),
        "model_contract": str(served.dispersion.contract),
        "mean_artifact_version": str(served.mean.version),
        "framing": FRAMING,
        # ⛔ NOT a knob and NOT a result — the recorded fact that no stake rides on this number.
        # P1.4's CLV leg came back a clean null (ATS 0.496 = placebo), so the honest bet size is 0.
        "best_alpha": 0.0,
    })
    for col in ("mu_margin", "sigma_margin", "mu_total", "sigma_total",
                "margin_interval_width", "total_interval_width",
                "home_strength_margin", "home_strength_margin_sd",
                "away_strength_margin", "away_strength_margin_sd"):
        out[col] = scored[col].astype(float)
    for target in ("margin", "total"):
        for level in PERSISTED_QUANTILES:
            c = f"{target}_q{int(round(level * 100)):02d}"
            out[c] = scored[c].astype(float)
    for side in ("home", "away"):
        c = f"{side}_strength_games_in_window"
        out[c] = pd.to_numeric(scored[c], errors="coerce").astype(float)
    return out[list(_ROW_COLUMNS)].reset_index(drop=True)


def assert_pre_kickoff(rows: pd.DataFrame, *, context: str = "game prediction snapshot") -> None:
    """🔒 THE LEAKAGE GATE (HALT) — every row's `snapshot_ts` must be STRICTLY before its kickoff.

    DATE-BASED on purpose. A week-based assertion re-uses CFBD's postseason week ordering, which
    restarts at 1, so it passes green on exactly the rows it should catch (the P1.1/P1.2 lesson).
    Comparing two instants cannot be fooled that way.

    Deliberately an INDEPENDENT check at the write boundary rather than a restatement of
    `select_upcoming_slate`'s filter: the filter is how rows are chosen, this is what may be
    written. A filter bug, a re-used stale frame, a hand-assembled row, or a clock that moved
    during a long scoring run must all be refused here rather than persisted as a "prediction" of
    a game that had already started.
    """
    if rows.empty:
        return
    for col in ("snapshot_ts", "commence_time"):
        if col not in rows.columns:
            raise KeyError(f"{context}: cannot verify the leakage gate — no `{col}` column. An "
                           "unverifiable gate is not a passed gate (NF1.7 a).")
    snap = pd.to_datetime(rows["snapshot_ts"], utc=True, errors="coerce")
    kick = pd.to_datetime(rows["commence_time"], utc=True, errors="coerce")
    unusable = snap.isna() | kick.isna()
    if unusable.any():
        raise ValueError(
            f"{context}: {int(unusable.sum())} row(s) carry an unparseable snapshot_ts or "
            "commence_time — the leakage gate cannot be evaluated on them, which is a REFUSAL, "
            "not a pass (NF1.7 a).")
    late = kick <= snap
    if late.any():
        offenders = rows.loc[late, ["game_id", "snapshot_ts", "commence_time"]].head(10)
        raise ValueError(
            f"🚨 {context}: LEAKAGE GATE FAILED — {int(late.sum())} of {len(rows)} row(s) have a "
            f"snapshot_ts at or after kickoff. A post-kickoff 'prediction' is not a prediction. "
            f"Refusing the whole write. First offenders:\n{offenders.to_string(index=False)}")


def assert_no_edge_claim(rows: pd.DataFrame, *, context: str = "game prediction snapshot") -> None:
    """The honest-framing gate: the payload carries probabilities and intervals, never a claim.

    `best_alpha = 0` is the program's standing position on NCAAF game lines (P1.4's CLV leg was a
    clean null), so a column named for an edge, a pick, a stake or a win-rate would assert
    something the evidence does not support. Making it a schema property means a later story
    cannot add one by accident — it has to delete this guard, which is a reviewable act.
    """
    offending = [c for c in rows.columns
                 if any(tok in c.lower() for tok in FORBIDDEN_PAYLOAD_TOKENS)
                 and c not in ("best_alpha",)]
    if offending:
        raise ValueError(
            f"{context}: the payload carries {offending}, which reads as an edge/pick claim. This "
            "surface is a market-blind projection (best_alpha=0; P1.4's CLV leg was a clean null) "
            "— probabilities and intervals only.")
    if "best_alpha" in rows.columns and not (rows["best_alpha"].astype(float) == 0.0).all():
        raise ValueError(f"{context}: best_alpha must be 0.0 on every row — no stake rides on this.")


# ══════════════════════════════════════════════════════════════════════════════════════════
# READ-MERGE-WRITE persistence (append-only across snapshots)
# ══════════════════════════════════════════════════════════════════════════════════════════

def merge_snapshot_rows(existing: pd.DataFrame | None, new: pd.DataFrame,
                        key: Sequence[str]) -> pd.DataFrame:
    """Union `existing` and `new`, dropping only the EXISTING rows whose key the new batch
    re-covers. PURE.

    This is the whole never-lose-prior-weeks contract: `write_season_partition` overwrites a season
    partition, so writing only `new` would delete every earlier snapshot of the season. Re-running
    with an identical `snapshot_ts` is a value-identical rewrite (idempotent); a fresh
    `snapshot_ts` APPENDS, which is what builds the forward track record.

    ⚠️ `existing is None` means "the partition genuinely does not exist yet" — the caller must have
    obtained it from `query_or_missing`, which RAISES on a transient read failure. Never pass
    `None` because a read failed.
    """
    if new.empty:
        raise ValueError("refusing to merge an EMPTY new batch — an empty write would rewrite the "
                         "season partition to whatever `existing` holds and is never intended; "
                         "the caller should skip the write instead.")
    if existing is None or existing.empty:
        return new.reset_index(drop=True)
    keys = set(map(tuple, new[list(key)].astype(str).to_numpy()))
    keep = ~existing[list(key)].astype(str).apply(tuple, axis=1).isin(keys)
    kept = existing[keep]
    combined = pd.concat([kept, new], ignore_index=True, sort=False)
    return combined.reset_index(drop=True)


def read_existing_snapshots(season: int, source: str, *,
                            local_root: str | None = None) -> pd.DataFrame | None:
    """The season's already-written snapshot rows, or `None` iff the table genuinely does not exist
    yet. A transient read failure RAISES (see `query_or_missing`) so it can never be mistaken for
    "nothing to preserve."""
    expr = (query_lake.local(source, local_root, tier=LAKE_TIER) if local_root
            else query_lake.delta(source, tier=LAKE_TIER))
    return query_lake.query_or_missing(f"select * from {expr} where season = {int(season)}")


def write_snapshot(rows: pd.DataFrame, *, season: int, source: str, key: Sequence[str],
                   local_root: str | None = None,
                   bucket: str = s3io.DEFAULT_BUCKET) -> int:
    """READ-MERGE-WRITE `rows` into the season partition of `source`. Returns rows written."""
    existing = read_existing_snapshots(season, source, local_root=local_root)
    combined = merge_snapshot_rows(existing, rows, key)
    uri = (s3io.local_table_uri(local_root, SPORT, source, tier=LAKE_TIER) if local_root
           else s3io.table_uri(SPORT, source, bucket=bucket, tier=LAKE_TIER))
    import pyarrow as pa

    table = pa.Table.from_pandas(combined, preserve_index=False)
    n = s3io.write_season_partition(table, uri, int(season))
    log.info("  [%s/%s] season=%s: %d new row(s) merged into %d total → %s",
             SPORT, source, season, len(rows), n, uri)
    return n


# ══════════════════════════════════════════════════════════════════════════════════════════
# The FUTURES-board snapshot (the cheap fan-out — starts the futures track record too)
# ══════════════════════════════════════════════════════════════════════════════════════════
#
# WHY A SECOND TABLE. P1.5 already renders a board to `ncaaf/derived/season_simulation_board`, but
# that write is a season-partition OVERWRITE: every publish REPLACES the season's board, so the
# table holds only the newest one and no history accrues. A track record needs the vintage kept, so
# the weekly snapshot lands in its own append-only table keyed (team_id, snapshot_ts). The P1.5
# publish is untouched — it remains "the current board", this is "what we said, when".
#
# WHY IT READS THE LAKE, NOT `run_season_simulation.run_board`. That driver reads the strength
# PARQUET (gitignored ⇒ absent from the box image) and `sports.duckdb` (gitignored ⇒ in a named
# volume at best) — a box-run op must not depend on deploy-ephemeral files (NF-INFRA1). Everything
# the simulation needs is in the lake, and the game-snapshot op has already read it.

def futures_schedule_from_lake(games: pd.DataFrame, *, as_of: datetime):
    """Lake games frame → the P1.5 sim's schedule, via the SHARED `schedule_from_frame`.

    A game counts as PLAYED iff it is completed AND its kickoff is already past `as_of` — the
    DATE-based rule, so the CCG/postseason exclusions never lean on CFBD's restarting `week`.
    """
    from quant_sports_intel_models.football.ncaaf.models.run_season_simulation import (
        schedule_from_frame,
    )

    df = games.copy()
    kick = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    df["is_postseason"] = df["season_type"].astype(str).str.lower() != "regular"
    df["home_margin"] = df["home_points"] - df["away_points"]
    # `season_order_week` is unused when an explicit `played` mask is supplied; it is present only
    # so the shared converter's frame contract is satisfied.
    df["season_order_week"] = df["week"].astype("int64")
    played = df["is_completed"].astype(bool) & (kick <= _utc_ts(as_of))
    return schedule_from_frame(df, as_of_week=0, played=played)


def futures_posteriors_from_lake(strength: pd.DataFrame):
    """The P1.2 strength frame → the sim's `TeamPosterior` list + (hfa, league_base)."""
    from quant_sports_intel_models.football.ncaaf.models.season_simulation import TeamPosterior

    posteriors = [
        TeamPosterior(
            team_id=int(r.team_id), team=str(r.team), conference=str(r.conference),
            strength_margin=float(r.strength_margin),
            strength_margin_sd=float(r.strength_margin_sd),
            strength_offense=float(r.strength_offense),
            strength_offense_sd=float(r.strength_offense_sd),
            strength_defense=float(r.strength_defense),
            strength_defense_sd=float(r.strength_defense_sd),
        )
        for r in strength.itertuples(index=False)
    ]
    return posteriors, float(strength["home_field_advantage"].mean()), \
        float(strength["league_base_points"].mean())


def build_futures_snapshot_rows(board, served: ServedModel, *, snapshot_ts: datetime,
                                season: int, strength_as_of_week: int) -> pd.DataFrame:
    """The P1.5 board → the persisted futures-snapshot rows (probabilities only)."""
    rows = pd.DataFrame(board.teams)
    if rows.empty:
        return rows
    rows.insert(0, "season", int(season))
    rows.insert(1, "snapshot_ts", _iso(snapshot_ts))
    rows["snapshot_kind"] = SNAPSHOT_KIND_PRE_KICKOFF
    rows["strength_as_of_week"] = int(strength_as_of_week)
    rows["n_sims"] = int(board.n_sims)
    rows["model_version"] = served.version
    rows["model_contract"] = str(served.dispersion.contract)
    rows["framing"] = FRAMING
    rows["best_alpha"] = 0.0
    if "team_id" in rows.columns:
        rows["team_id"] = rows["team_id"].astype("int64")
    return rows.reset_index(drop=True)


def run_futures_snapshot(season: int, games: pd.DataFrame, strength: pd.DataFrame,
                         served: ServedModel, *, snapshot_ts: datetime, strength_as_of_week: int,
                         n_sims: int = 10_000, seed: int = 20260829,
                         pace_by_team: Mapping[int, float] | None = None) -> pd.DataFrame:
    """Run the P1.5 season simulation off the LAKE inputs → the futures-snapshot rows.

    Calls `simulate_season` (the pure, unit-tested P1.5 engine) directly — the futures numbers are
    P1.5's, not a re-derivation. `fixed_strength` discipline, the CFP bookkeeping and the
    once-per-season strength draw all live inside that engine and are untouched here.
    """
    from quant_sports_intel_models.football.ncaaf.models.run_season_simulation import build_format
    from quant_sports_intel_models.football.ncaaf.models.season_simulation import (
        PaceAdjustment,
        SeasonSimConfig,
        simulate_season,
    )

    posteriors, hfa, league_base = futures_posteriors_from_lake(strength)
    schedule, _realized_ccg, _realized_hw = futures_schedule_from_lake(games, as_of=snapshot_ts)
    pace = None
    if pace_by_team and served.mean.pace_columns:
        vec = np.array([float(pace_by_team.get(int(p.team_id), np.nan)) for p in posteriors])
        if np.isfinite(vec).any():
            pace = PaceAdjustment.from_mean_params(served.mean, vec)
    if pace is None:
        log.info("futures snapshot: pace term INERT (no as-of tempo for any team) — the board is "
                 "byte-identical to a pace-free run, by construction, not by omission.")
    cfg = SeasonSimConfig(n_sims=int(n_sims), seed=int(seed))
    board = simulate_season(posteriors, schedule, served.dispersion, hfa, league_base,
                            build_format(int(season)), cfg, season=int(season), pace=pace)
    board.meta["as_of_week"] = int(strength_as_of_week)
    return build_futures_snapshot_rows(board, served, snapshot_ts=snapshot_ts, season=int(season),
                                       strength_as_of_week=int(strength_as_of_week))
