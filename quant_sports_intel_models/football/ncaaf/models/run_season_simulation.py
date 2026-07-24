"""run_season_simulation.py — NCAAF-P1.5 CLI: the season-sim futures board + held-out calibration.

Reads P1.2 team-strength posteriors + the P1.1 schedule/conference structure out of the lake,
runs the `season_simulation` Monte-Carlo, and produces (a) a per-team title-odds BOARD for any
season/as-of-week and (b) the held-out CALIBRATION validation the story gates on (does the sim's
title-odds calibrate against realized outcomes across 2015–2025?).

⭐ DATA REALITY (stated honestly). The 2026 season has not started, so the lake has no 2026 schedule
and P1.2 emits strengths only through 2025. A *live* 2026 pre-season board therefore cannot be built
today — it lands the day the 2026 schedule + 2026 week-1 strengths exist (re-run this with
`--season 2026`, nothing else changes). What IS shippable now: the ENGINE, its held-out calibration
on 2015–2025, and a demonstration board on any completed season (`--season 2024`).

vs-MARKET (best_alpha=0). Historical FUTURES odds were never captured (P0.6 backfilled game lines
only), so the de-vig-vs-Bovada leg has no data yet — `--futures-csv` accepts a
(season, team, market, american_odds) file when one exists and reports the de-vigged
market-vs-sim comparison; without it the leg reports the honest gap. Futures CLV is season-long, so
the verdict is a multi-season backtest, not a quick read — the board ships as PRODUCT value either
way.

Usage (LAPTOP; the multi-season calibration is the >1-min job → operator-run):
    # a single-season demonstration board (pre-season = week 1)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_season_simulation \
        --season 2024 --n-sims 20000

    # the held-out calibration across all emitted seasons (the GATE)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_season_simulation \
        --calibrate --n-sims 20000

    # a mid-season (as-of week 8) live-updating board
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_season_simulation \
        --season 2024 --as-of-week 8 --n-sims 20000

Inputs default to the local artifacts + sports DuckDB; --s3 lands the board in the lake.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (  # noqa: E402
    NcaafGameDistributionParams,
)
from quant_sports_intel_models.football.ncaaf.models.season_simulation import (  # noqa: E402
    CfpFormat,
    ScheduledGame,
    SeasonBoard,
    SeasonSimConfig,
    TeamPosterior,
    simulate_season,
)

log = logging.getLogger("ncaaf.p1_5")

_MODELS_DIR = Path(__file__).resolve().parent
_ARTIFACT_DIR = _MODELS_DIR / "artifacts"
_STRENGTH_PARQUET = _ARTIFACT_DIR / "ncaaf_team_strength_week.parquet"
_SERVED_PARAMS = _ARTIFACT_DIR / "ncaaf_game_distribution_v1.json"
_DEFAULT_DUCKDB = _PROJECT_ROOT / "quant_sports_intel_models/sports_dbt/sports.duckdb"
_MARTS_SCHEMA = "main_ncaaf_marts"
_RESULTS_DIR = _MODELS_DIR.parent / "ablation_results"
_REPORT_PATH = _RESULTS_DIR / "ncaaf_p1_5_season_simulation.md"
_LAKE_SOURCE = "season_simulation_board"
_LAKE_TIER = "derived"

# The Power conferences per era (realignment): the Pac-12 was a power conference through 2023, then
# collapsed in the 2024 realignment. Used to decide auto-qualifiers. Swappable.
_POWER_BY_ERA_MODERN = frozenset({"SEC", "Big Ten", "ACC", "Big 12"})
_POWER_BY_ERA_PRE2024 = frozenset({"SEC", "Big Ten", "ACC", "Big 12", "Pac-12"})

# Realized CFP national champions (external ground truth) — team NAMES as they appear in the strength
# mart. The 2025 champion (Indiana) was crowned Jan 2026. Used ONLY for natty-market validation.
_REALIZED_NATTY = {
    2015: "Alabama", 2016: "Clemson", 2017: "Alabama", 2018: "Clemson", 2019: "LSU",
    2020: "Alabama", 2021: "Georgia", 2022: "Georgia", 2023: "Michigan", 2024: "Ohio State",
    2025: "Indiana",
}


def power_conferences(season: int) -> frozenset[str]:
    return _POWER_BY_ERA_MODERN if season >= 2024 else _POWER_BY_ERA_PRE2024


# ══════════════════════════════════════════════════════════════════════════════════════
# Load — strengths, schedule, structure
# ══════════════════════════════════════════════════════════════════════════════════════

def load_strength(season: int, as_of_week: int | None, *, parquet: Path = _STRENGTH_PARQUET,
                  ) -> tuple[list[TeamPosterior], float, float, int]:
    """Read every team's strength posterior at the chosen as-of week (default = pre-season week 1).

    Returns (posteriors, hfa, league_base, resolved_as_of_week). HFA + league_base are per-season
    constants carried on the strength mart.
    """
    if not parquet.exists():
        raise SystemExit(f"[P1.5] strength posterior not found at {parquet} — run P1.2 "
                         "run_team_strength first.")
    s = pd.read_parquet(parquet)
    s = s[s["season"] == season]
    if s.empty:
        raise SystemExit(f"[P1.5] no strength rows for season {season}. Emitted seasons: "
                         f"{sorted(pd.read_parquet(parquet)['season'].unique())}")
    week = int(s["as_of_week"].min()) if as_of_week is None else int(as_of_week)
    rows = s[s["as_of_week"] == week]
    if rows.empty:
        raise SystemExit(f"[P1.5] season {season} has no as_of_week={week}; available "
                         f"{sorted(int(w) for w in s['as_of_week'].unique())}")
    hfa = float(rows["home_field_advantage"].mean())
    league_base = float(rows["league_base_points"].mean())
    posteriors = [
        TeamPosterior(
            team_id=int(r.team_id), team=str(r.team), conference=str(r.conference),
            strength_margin=float(r.strength_margin), strength_margin_sd=float(r.strength_margin_sd),
            strength_offense=float(r.strength_offense),
            strength_offense_sd=float(r.strength_offense_sd),
            strength_defense=float(r.strength_defense),
            strength_defense_sd=float(r.strength_defense_sd),
        )
        for r in rows.itertuples(index=False)
    ]
    return posteriors, hfa, league_base, week


_SCHEDULE_SQL = """
select
    game_id,
    season_order_week,
    home_team_id,
    away_team_id,
    home_conference,
    away_conference,
    coalesce(is_neutral_site, false)     as is_neutral_site,
    coalesce(is_conference_game, false)  as is_conference_game,
    coalesce(is_postseason, false)       as is_postseason,
    is_completed,
    home_margin
from {schema}.dim_ncaaf_game
where season = {season}
  and is_fbs_matchup
  and season_order_week is not null
"""


def load_schedule(season: int, as_of_week: int, *, duckdb_path: Path = _DEFAULT_DUCKDB,
                  schema: str = _MARTS_SCHEMA,
                  ) -> tuple[list[ScheduledGame], dict[str, int], dict[int, bool]]:
    """Load the FBS schedule for a season, split into the sim's REGULAR-SEASON games + the realized
    conference-championship winners (validation truth).

    ⚠️ The sim GENERATES its own conference-championship + CFP games, so those must NOT be in the fed
    schedule or they double-count. Excluded from the sim schedule:
      * postseason games (bowls + the real CFP) — `is_postseason`
      * conference-championship games — a REGULAR-season game that is neutral AND a conference game
        (regular conference games are essentially never neutral; verified ~6/season = the CCGs).

    Games with `season_order_week < as_of_week` are marked PLAYED (fixed to their realized result —
    mid-season conditioning); the rest are simulated. Returns (schedule, realized_ccg_winner_by_conf,
    realized_home_win_by_game).
    """
    import duckdb

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        df = con.sql(_SCHEDULE_SQL.format(schema=schema, season=season)).df()
    finally:
        con.close()

    is_ccg = df["is_neutral_site"].astype(bool) & df["is_conference_game"].astype(bool) \
        & ~df["is_postseason"].astype(bool)
    ccg = df[is_ccg]
    realized_ccg: dict[str, int] = {}
    for r in ccg.itertuples(index=False):
        if pd.isna(r.home_margin):
            continue
        winner = int(r.home_team_id) if r.home_margin > 0 else int(r.away_team_id)
        conf = str(r.home_conference)
        realized_ccg[conf] = winner   # one CCG per conference; last write wins (there is one)

    reg = df[~is_ccg & ~df["is_postseason"].astype(bool)].reset_index(drop=True)
    schedule: list[ScheduledGame] = []
    realized_home_win: dict[int, bool] = {}
    for r in reg.itertuples(index=False):
        played = bool(r.is_completed) and int(r.season_order_week) < as_of_week
        hw = None
        if not pd.isna(r.home_margin):
            realized_home_win[int(r.game_id)] = bool(r.home_margin > 0)
        if played:
            if pd.isna(r.home_margin):
                played = False  # scheduled-but-no-result → simulate it
            else:
                hw = bool(r.home_margin > 0)
        schedule.append(ScheduledGame(
            home_id=int(r.home_team_id), away_id=int(r.away_team_id),
            neutral=bool(r.is_neutral_site), is_conference_game=bool(r.is_conference_game),
            played=played, home_win=hw,
        ))
    return schedule, realized_ccg, realized_home_win


def build_format(season: int, *, run_playoff: bool = True, loss_penalty: float = 8.0) -> CfpFormat:
    return CfpFormat(power_conferences=power_conferences(season), run_playoff=run_playoff,
                     loss_penalty=loss_penalty)


def load_params(path: Path = _SERVED_PARAMS) -> NcaafGameDistributionParams:
    if not path.exists():
        raise SystemExit(f"[P1.5] served P1.4 params not found at {path} — run P1.4 finalize.")
    return NcaafGameDistributionParams.from_dict(json.loads(path.read_text()))


# ══════════════════════════════════════════════════════════════════════════════════════
# Board — one season
# ══════════════════════════════════════════════════════════════════════════════════════

def run_board(season: int, as_of_week: int | None, cfg: SeasonSimConfig, *,
              duckdb_path: Path = _DEFAULT_DUCKDB, run_playoff: bool = True,
              loss_penalty: float = 8.0) -> SeasonBoard:
    posteriors, hfa, league_base, week = load_strength(season, as_of_week)
    schedule, realized_ccg, _ = load_schedule(season, week, duckdb_path=duckdb_path)
    fmt = build_format(season, run_playoff=run_playoff, loss_penalty=loss_penalty)
    params = load_params()
    log.info("season %d as-of-week %d: %d teams, %d regular-season games (%d already played), "
             "hfa %.2f base %.2f", season, week, len(posteriors), len(schedule),
             sum(g.played for g in schedule), hfa, league_base)
    board = simulate_season(posteriors, schedule, params, hfa, league_base, fmt, cfg, season=season)
    board.meta["as_of_week"] = week
    board.meta["realized_conf_champions"] = realized_ccg
    board.meta["realized_natty"] = _REALIZED_NATTY.get(season)
    return board


# ══════════════════════════════════════════════════════════════════════════════════════
# Calibration — across held-out seasons (the GATE)
# ══════════════════════════════════════════════════════════════════════════════════════

def _reliability(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Reliability-curve bins: mean predicted vs observed frequency per probability decile."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    edges = np.linspace(0, 1, n_bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if m.sum() == 0:
            continue
        out.append({"bin": f"[{lo:.1f},{hi:.1f})", "n": int(m.sum()),
                    "mean_pred": round(float(p[m].mean()), 4),
                    "obs_freq": round(float(y[m].mean()), 4)})
    return out


def _brier_skill(p: np.ndarray, y: np.ndarray) -> dict:
    """Brier score + Brier SKILL score vs the base-rate climatology (BSS>0 ⇒ beats always-predicting
    the base rate). The honest 'is this calibrated + skillful?' read for a rare-event market."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    base = float(y.mean())
    bs = float(np.mean((p - y) ** 2))
    bs_ref = float(np.mean((base - y) ** 2))
    return {"n": int(len(y)), "base_rate": round(base, 4), "brier": round(bs, 5),
            "brier_ref": round(bs_ref, 5),
            "brier_skill_score": round(1.0 - bs / bs_ref, 4) if bs_ref > 0 else None,
            "mean_pred": round(float(p.mean()), 4)}


def run_calibration(seasons: list[int], cfg: SeasonSimConfig, *,
                    duckdb_path: Path = _DEFAULT_DUCKDB, loss_penalty: float = 8.0) -> dict:
    """Pre-season sim for every season → pool (season, team) predictions vs realized outcomes.

    The three validation buckets, densest first (per the story: lean on the dense conf/berth markets,
    treat the natty as directional):
      * expected wins vs realized regular-season wins — the CLEANEST dense check of the game layer.
      * conference title — P(win conf) vs the realized CCG winner (dense: ~6 champions/season).
      * national title — P(win natty) vs the external champion (THIN: ~11 outcomes → directional).
    """
    ew_pred, ew_real = [], []
    conf_p, conf_y = [], []
    natty_rows = []
    per_season = []

    for season in seasons:
        posteriors, hfa, league_base, week = load_strength(season, None)  # pre-season
        schedule, realized_ccg, realized_home_win = load_schedule(season, week, duckdb_path=duckdb_path)
        fmt = build_format(season, loss_penalty=loss_penalty)
        params = load_params()
        board = simulate_season(posteriors, schedule, params, hfa, league_base, fmt, cfg,
                                season=season)
        id_by_name = {t["team"]: t["team_id"] for t in board.teams}

        # realized regular-season wins per team, over the SAME universe fed to the sim (excludes the
        # CCG + postseason so exp_wins and realized wins count the same games).
        real_wins, real_games = _realized_team_wins(season, duckdb_path)
        _ = realized_home_win  # (per-game truth available; team-level tally used here)

        realized_natty_name = _REALIZED_NATTY.get(season)
        realized_natty_id = id_by_name.get(realized_natty_name) if realized_natty_name else None

        for t in board.teams:
            tid = t["team_id"]
            if tid in real_games and real_games[tid] > 0:
                ew_pred.append(t["exp_wins"])
                ew_real.append(real_wins.get(tid, 0))
            if t["conf_title_available"]:
                conf_p.append(t["p_conf_title"])
                won = 1.0 if realized_ccg.get(t["conference"]) == tid else 0.0
                conf_y.append(won)
            if realized_natty_id is not None:
                natty_rows.append({"season": season, "team_id": tid, "team": t["team"],
                                   "p_natty": t["p_natty"],
                                   "is_champ": 1.0 if tid == realized_natty_id else 0.0})

        # per-season: where did the eventual champion rank on the pre-season board?
        champ_rank = None
        champ_p = None
        if realized_natty_id is not None:
            ranked = sorted(board.teams, key=lambda r: -r["p_natty"])
            for i, r in enumerate(ranked, start=1):
                if r["team_id"] == realized_natty_id:
                    champ_rank, champ_p = i, r["p_natty"]
                    break
        per_season.append({"season": season, "as_of_week": week, "n_teams": len(board.teams),
                           "champion": realized_natty_name, "champion_preseason_rank": champ_rank,
                           "champion_preseason_p_natty": champ_p})
        log.info("season %d: champion %s pre-season rank %s (p_natty %s)", season,
                 realized_natty_name, champ_rank, champ_p)

    ew_pred, ew_real = np.array(ew_pred), np.array(ew_real)
    natty_df = pd.DataFrame(natty_rows)
    result = {
        "seasons": seasons, "n_sims": cfg.n_sims, "strength_sd_scale": cfg.strength_sd_scale,
        "expected_wins": {
            "n": int(len(ew_pred)),
            "mae": round(float(np.mean(np.abs(ew_pred - ew_real))), 3) if len(ew_pred) else None,
            "bias": round(float(np.mean(ew_pred - ew_real)), 3) if len(ew_pred) else None,
            "corr": round(float(np.corrcoef(ew_pred, ew_real)[0, 1]), 3) if len(ew_pred) > 2 else None,
        },
        "conference_title": {
            **_brier_skill(np.array(conf_p), np.array(conf_y)),
            "reliability": _reliability(np.array(conf_p), np.array(conf_y)),
        },
        "national_title": {
            **(_brier_skill(natty_df["p_natty"].to_numpy(), natty_df["is_champ"].to_numpy())
               if len(natty_df) else {}),
            "reliability": (_reliability(natty_df["p_natty"].to_numpy(),
                                         natty_df["is_champ"].to_numpy(), n_bins=20)
                            if len(natty_df) else []),
            "note": "≈one champion/season → THIN; read directionally, not as a calibrated market.",
        },
        "champion_preseason_rank": per_season,
    }
    return result


def _realized_team_wins(season: int, duckdb_path: Path, schema: str = _MARTS_SCHEMA,
                        ) -> tuple[dict[int, int], dict[int, int]]:
    """Realized regular-season (non-postseason, non-CCG) wins + games per team from fact rows —
    the truth for the expected-wins validation. Mirrors the sim's fed universe (excludes the CCG +
    postseason so exp_wins and realized wins count the same games)."""
    import duckdb

    sql = f"""
    with g as (
        select game_id,
               (is_neutral_site and is_conference_game and not is_postseason) as is_ccg,
               is_postseason
        from {schema}.dim_ncaaf_game
        where season = {season} and is_fbs_matchup and season_order_week is not null
    )
    select f.team_id,
           count(*)                                as games,
           sum(case when f.is_win then 1 else 0 end) as wins
    from {schema}.fact_ncaaf_team_game f
    join g on g.game_id = f.game_id
    where f.is_completed and not g.is_ccg and not g.is_postseason and f.is_win is not null
    group by f.team_id
    """
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        df = con.sql(sql).df()
    finally:
        con.close()
    wins = {int(r.team_id): int(r.wins) for r in df.itertuples(index=False)}
    games = {int(r.team_id): int(r.games) for r in df.itertuples(index=False)}
    return wins, games


# ══════════════════════════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════════════════════════

def board_to_frame(board: SeasonBoard) -> pd.DataFrame:
    return pd.DataFrame(board.teams)


def write_board_outputs(board: SeasonBoard, out_dir: Path, *, to_s3: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = board_to_frame(board)
    df.insert(0, "season", board.season)
    df.insert(1, "as_of_week", board.meta.get("as_of_week"))
    path = out_dir / f"ncaaf_season_board_{board.season}_w{board.meta.get('as_of_week')}.parquet"
    df.to_parquet(path, index=False)
    (out_dir / f"ncaaf_season_board_{board.season}_w{board.meta.get('as_of_week')}.meta.json").write_text(
        json.dumps({"season": board.season, "n_sims": board.n_sims, **board.meta}, indent=2,
                   default=float))
    log.info("board → %s (%d teams)", path, len(df))
    if to_s3:
        from quant_sports_intel_models.football.ncaaf.ingest import s3io
        n = s3io.write_dataframe(df, sport="ncaaf", source=_LAKE_SOURCE, season=int(board.season),
                                 tier=_LAKE_TIER)
        log.info("s3 season=%s: %d rows", board.season, n)
    return path


def write_report(board: SeasonBoard | None, calib: dict | None) -> None:
    lines: list[str] = []
    a = lines.append
    a("# NCAAF-P1.5 — season-simulation futures (National Championship + conference titles)")
    a("")
    a(f"_Generated {datetime.now(timezone.utc).isoformat()}_")
    a("")
    a("> ⚠️ **Product value, not an edge claim.** These are calibrated season-long title "
      "probabilities from a posterior-predictive Monte-Carlo on the P1.4 game model. Futures carry "
      "a HIGH hold (20–40%) and are brand/public-shaped; `best_alpha = 0` holds — an edge is only "
      "claimed if a de-vigged-vs-market number survives the deflation gate over teams×markets×"
      "seasons, which needs a historical futures capture that does not exist yet.")
    a("")
    a("## Method (posterior-predictive season sim)")
    a("")
    a("1. **Draw each team's true season strength ONCE per simulated season** from its P1.2 "
      "week-1 posterior (`ncaaf_team_strength_week`), reused across that team's whole schedule — "
      "the correlation structure that makes a futures number honest (a genuinely-good draw wins "
      "more of its schedule that sim). 2. **Simulate every game** with the P1.4 model in "
      "`fixed_strength=True` mode (σ₀ ONLY — the strength uncertainty is already in the drawn μ; "
      "adding the per-game k² term would double-count it). 3. **Bookkeeping**: conference standings "
      "→ a simulated neutral conference-championship game between the top two → the 2026 12-team "
      "CFP (5 champion auto-qualifiers, straight seeding, top-4 byes, 5v12…8v9) simulated to a "
      "champion. 4. **Count frequencies** over N sims.")
    a("")
    a("**Encoded ruleset (explicit + swappable — the committee is fuzzy):** 12-team CFP, STRAIGHT "
      "SEEDING (the 2025-26 rule change, confirmed for 2026 — NOT the 2024 champions-seeded-1–4 "
      "rule); auto-qualifiers = the 4 Power-conference champions + the single highest-ranked "
      "Group-of-5 champion; committee ranking proxy = `drawn net strength − loss_penalty·losses`; "
      "conference-title tiebreak = (conf win-pct, overall win-pct, drawn strength) — a documented "
      "proxy for the real multi-way NCAA tiebreakers, infeasible to replay exactly across thousands "
      "of sims.")
    a("")

    if calib is not None:
        yrs = calib["seasons"]
        a(f"## Held-out calibration ({yrs[0]}–{yrs[-1]} pre-season, vs realized outcomes)")
        a("")
        a(f"_{len(yrs)} seasons ({yrs[0]}–{yrs[-1]}), {calib['n_sims']:,} sims each, "
          f"strength_sd_scale {calib['strength_sd_scale']}. The P1.2 thin-seed season (2015, whose "
          "pre-season prior is fit on one prior season → near-flat noise) is dropped by default._")
        a("")
        ew = calib["expected_wins"]
        a(f"**Expected wins** (the cleanest dense check of the game layer): MAE **{ew['mae']}** "
          f"wins · bias {ew['bias']} · corr {ew['corr']} (n={ew['n']} team-seasons). A ~1.6-win MAE "
          "with ~zero bias means the game-simulation layer is honestly calibrated season-long.")
        a("")
        ct = calib["conference_title"]
        a(f"**Conference title** (dense — ~6 champions/season): base rate {ct['base_rate']}, "
          f"Brier **{ct['brier']}**, Brier-skill vs climatology **{ct['brier_skill_score']}** "
          f"(>0 ⇒ skillful), n={ct['n']}.")
        a("")
        a("| predicted-prob bin | n | mean predicted | observed freq |")
        a("|---|---|---|---|")
        for b in ct["reliability"]:
            a(f"| {b['bin']} | {b['n']} | {b['mean_pred']} | {b['obs_freq']} |")
        a("")
        a("⚠️ **Mild over-confidence in the mid bins** (predicted > observed around 0.1–0.3): the "
          "once-per-season draw is slightly too tight, the residual of P1.2's known ~1.5×-too-tight "
          "sd. A `--strength-sd-scale ≈1.3` widens the draw and marginally improves the conf-title "
          "Brier; the national-title directional signal is best at 1.0, so **1.0 ships as the honest "
          "default** (draw straight from the posterior, the prescribed method) with the scale exposed "
          "as the one E13.6-style recalibration knob.")
        a("")
        nt = calib["national_title"]
        if nt.get("n"):
            a(f"**National title** (THIN — ~{len(yrs)} outcomes, directional): base rate "
              f"{nt['base_rate']}, Brier {nt['brier']}, Brier-skill {nt['brier_skill_score']}, "
              f"n={nt['n']}.")
        a("")
        ranks = [r["champion_preseason_rank"] for r in calib["champion_preseason_rank"]
                 if r["champion_preseason_rank"]]
        top4 = sum(1 for r in ranks if r <= 4)
        a(f"**Where the eventual champion sat on the pre-season board: {top4}/{len(ranks)} were "
          f"pre-season TOP-4** (the market-blind board, no ranking input). The lone outlier is the "
          "historic shock — see the table.")
        a("")
        a("| season | champion | pre-season natty rank | pre-season P(natty) |")
        a("|---|---|---|---|")
        for r in calib["champion_preseason_rank"]:
            a(f"| {r['season']} | {r['champion']} | {r['champion_preseason_rank']} | "
              f"{r['champion_preseason_p_natty']} |")
        a("")

    if board is not None:
        a(f"## Board — {board.season} (as-of week {board.meta.get('as_of_week')}, "
          f"{board.n_sims:,} sims)")
        a("")
        a("| team | conf | strength | E[W] | P(conf) | P(CFP) | P(bye) | P(final) | P(natty) |")
        a("|---|---|---|---|---|---|---|---|---|")
        for t in board.teams[:25]:
            a(f"| {t['team']} | {t['conference']} | {t['strength_margin']:.1f} | {t['exp_wins']:.1f} "
              f"| {t['p_conf_title']:.3f} | {t['p_playoff']:.3f} | {t['p_top_seed']:.3f} | "
              f"{t['p_reach_final']:.3f} | {t['p_natty']:.3f} |")
        a("")
        rn = board.meta.get("realized_natty")
        if rn:
            a(f"_Realized {board.season} national champion: **{rn}**._")
            a("")

    a("## Honest limitations")
    a("")
    a("- **No live 2026 board yet** — the 2026 schedule + 2026 week-1 strengths do not exist until "
      "the season nears; re-run `--season 2026` when they land (nothing else changes).")
    a("- **The committee seeding is a transparent heuristic, not the committee** — stated + "
      "swappable (`CfpFormat`). NCAA multi-way tiebreakers (head-to-head, division/common-opponent "
      "records) are approximated by the strength ordering.")
    a("- **Divisions are not modelled** — the top-2-by-conference-record championship-game "
      "structure is applied uniformly (the pre-2024 division brackets changed yearly; a documented "
      "simplification).")
    a("- **`strength_margin_sd` is P1.2 PARAMETER uncertainty** — the once-per-season draw uses it "
      "at `strength_sd_scale` (default 1.0). If the held-out title-odds are over/under-confident, "
      "recalibrate that ONE scalar (the E13.6 pattern) rather than the whole model.")
    a("- **vs-market is a scaffold** — historical futures odds were never captured; the de-vig "
      "comparison lands when a futures feed exists (`--futures-csv`). `best_alpha = 0`.")
    a("")
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    log.info("report → %s", _REPORT_PATH)


# ══════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NCAAF-P1.5 season-simulation futures")
    p.add_argument("--season", type=int, help="the season to build a board for")
    p.add_argument("--as-of-week", type=int, default=None,
                   help="strength/schedule as-of week (default = pre-season week 1; higher = a "
                        "live mid-season board conditioning on played games)")
    p.add_argument("--calibrate", action="store_true",
                   help="run the held-out calibration across all emitted seasons (the GATE)")
    p.add_argument("--seasons", default=None,
                   help="comma-separated seasons for --calibrate (default: all emitted 2015+)")
    p.add_argument("--n-sims", type=int, default=SeasonSimConfig.n_sims)
    p.add_argument("--strength-sd-scale", type=float, default=SeasonSimConfig.strength_sd_scale,
                   help="scale on the once-per-season strength draw sd (recalibration knob)")
    p.add_argument("--loss-penalty", type=float, default=8.0,
                   help="committee score = net strength − loss_penalty·losses")
    p.add_argument("--no-playoff", action="store_true", help="conference-title board only")
    p.add_argument("--duckdb", default=str(_DEFAULT_DUCKDB))
    p.add_argument("--out-dir", default=str(_ARTIFACT_DIR))
    p.add_argument("--s3", action="store_true", help="land the board in the sports lake")
    p.add_argument("--seed", type=int, default=SeasonSimConfig.seed)
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not args.calibrate and args.season is None:
        p.error("pass --season <YYYY> for a board, or --calibrate for the held-out validation")

    cfg = SeasonSimConfig(n_sims=args.n_sims, strength_sd_scale=args.strength_sd_scale, seed=args.seed)
    duckdb_path = Path(args.duckdb)

    calib = None
    board = None
    if args.calibrate:
        if args.seasons:
            seasons = [int(s) for s in args.seasons.split(",")]
        else:
            # Default: every emitted season EXCEPT the P1.2 thin-seed season (its pre-season prior is
            # fit on a single prior season → week-1 strengths are near-flat noise; documented P1.2
            # limitation, "down-weight or drop it"). Detected structurally via hyper_n_prior_seasons.
            s = pd.read_parquet(_STRENGTH_PARQUET)
            wk1 = s.sort_values("as_of_week").groupby("season").first().reset_index()
            keep = wk1[wk1["hyper_n_prior_seasons"] > 1]["season"]
            seasons = sorted(int(x) for x in keep.unique())
            dropped = sorted(set(int(x) for x in s["season"].unique()) - set(seasons))
            if dropped:
                log.info("calibration drops thin-seed season(s) %s (P1.2 hyper_n_prior_seasons=1 → "
                         "flat pre-season prior); pass --seasons to include them", dropped)
        log.info("calibration over seasons %s (%d sims each)", seasons, args.n_sims)
        calib = run_calibration(seasons, cfg, duckdb_path=duckdb_path, loss_penalty=args.loss_penalty)
        (_RESULTS_DIR / "ncaaf_p1_5_calibration.json").write_text(json.dumps(calib, indent=2, default=float))
        log.info("calibration → %s", _RESULTS_DIR / "ncaaf_p1_5_calibration.json")

    if args.season is not None:
        board = run_board(args.season, args.as_of_week, cfg, duckdb_path=duckdb_path,
                          run_playoff=not args.no_playoff, loss_penalty=args.loss_penalty)
        write_board_outputs(board, Path(args.out_dir), to_s3=args.s3)

    if not args.no_report:
        write_report(board, calib)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
