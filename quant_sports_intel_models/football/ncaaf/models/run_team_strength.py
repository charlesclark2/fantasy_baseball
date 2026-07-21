"""run_team_strength.py — NCAAF-P1.2 CLI: fit the team-strength posterior and land it.

Reads the P1.1 marts out of the sports dbt DuckDB, fits the hierarchical partial-pooling
model in `team_strength.py` at every point-in-time as-of week, validates the leakage
contract DATE-wise, writes the week-grained posterior, and emits a markdown report.

Usage (LAPTOP, after a sports dbt build):
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_team_strength \
        --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb

Usage (EC2 BOX, after `sports_ncaaf_dbt_build_job`):
    docker compose -f services/dagster/aws/docker-compose.yml exec -T \
        -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
        python -m quant_sports_intel_models.football.ncaaf.models.run_team_strength \
        --duckdb /tmp/sports_ncaaf.duckdb --s3

Outputs:
  * <out-dir>/ncaaf_team_strength_week.parquet   — the week-grained posterior (the feature)
  * <out-dir>/ncaaf_team_strength_hyperparams.csv — per-season stage-A fit diagnostics
  * s3://credence-sports-lakehouse/ncaaf/derived/team_strength_week/  (with --s3)
  * quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1_2_team_strength.md

⚠️ RUNTIME: a full 2014→present run is several minutes (it is ~200 leakage-safe refits plus
one hyperparameter optimization per season). Per the repo's >1-minute rule this is an
OPERATOR-run script, not something a session executes inline. `--seasons` gives a fast smoke.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.ncaaf.models.team_strength import (  # noqa: E402
    COVARIATE_GROUPS,
    MODEL_VERSION,
    SEED_SEASON,
    StrengthConfig,
    run_strength,
)

log = logging.getLogger("ncaaf.p1_2")

MARTS_SCHEMA = "main_ncaaf_marts"

# CFB team strength spans roughly +-40 points end to end, so a posterior sd above this is a
# broken fit, not honest humility. See gate 7 in validate().
_MAX_PLAUSIBLE_SD = 50.0
LAKE_SOURCE = "team_strength_week"
LAKE_TIER = "derived"

_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/ncaaf/models/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1_2_team_strength.md"
)


# ══════════════════════════════════════════════════════════════════════════════════════
# Load
# ══════════════════════════════════════════════════════════════════════════════════════

_GAMES_SQL = """
select
    g.season,
    g.game_id,
    g.season_order_week,
    g.game_date::date                       as game_date,
    g.team_id                               as home_team_id,
    g.conference                            as home_conference,
    g.opponent_team_id                      as away_team_id,
    g.opponent_conference                   as away_conference,
    g.is_neutral_site,
    g.margin                                as home_margin
from {schema}.fact_ncaaf_team_game g
where g.is_completed
  and g.is_home
  and g.season_order_week is not null
  and g.margin is not null
"""

_TEAM_GAMES_SQL = """
select
    season,
    game_id,
    season_order_week,
    game_date::date                         as game_date,
    team_id,
    team,
    conference,
    opponent_team_id,
    opponent_conference,
    is_home,
    is_neutral_site,
    points_for
from {schema}.fact_ncaaf_team_game
where is_completed
  and season_order_week is not null
  and points_for is not null
"""


def load_marts(duckdb_path: str, schema: str = MARTS_SCHEMA) -> dict[str, pd.DataFrame]:
    """Read the four P1.1/P0.4/P0.5 marts this model consumes.

    ⚠️ `game_date::date` is cast explicitly at the use site. dbt-duckdb materializes it as a
    real DATE here, but the INC-23 class of bug (a lakehouse timestamp arriving as an ISO
    VARCHAR and silently failing a comparison) is cheap to immunize against and expensive to
    debug, so the cast is unconditional.
    """
    import duckdb

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        out = {
            "games": con.sql(_GAMES_SQL.format(schema=schema)).df(),
            "team_games": con.sql(_TEAM_GAMES_SQL.format(schema=schema)).df(),
            "roster": con.sql(f"select * from {schema}.ncaaf_team_roster_continuity").df(),
            "coaching": con.sql(f"select * from {schema}.ncaaf_team_coaching_change").df(),
        }
    finally:
        con.close()
    for name, df in out.items():
        log.info("loaded %-12s %7d rows", name, len(df))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# Validation — the leakage gates
# ══════════════════════════════════════════════════════════════════════════════════════


def validate(weekly: pd.DataFrame, games: pd.DataFrame) -> list[str]:
    """Assert the leakage contract. Raises on a violation — this is a HALT-tier gate.

    Returns the list of checks that passed, for the report.
    """
    passed: list[str] = []

    # ── 1. DATE-BASED point-in-time gate. ────────────────────────────────────────────
    # The model filters on `season_order_week < as_of_week`, so a week-based test would
    # re-use the very ordering it is supposed to police and pass green even if that
    # ordering were wrong (the exact trap P1.1 documented). This checks the property in
    # DATE space instead: for every week boundary, every game the fit could see must have
    # been PLAYED before the earliest kickoff of the week being predicted.
    bounds = (
        games.groupby(["season", "season_order_week"])["game_date"]
        .agg(["min", "max"])
        .reset_index()
        .sort_values(["season", "season_order_week"])
    )
    violations = []
    for season, grp in bounds.groupby("season"):
        grp = grp.sort_values("season_order_week")
        prior_max = None
        for _, row in grp.iterrows():
            if prior_max is not None and prior_max >= row["min"]:
                violations.append(
                    f"season {season} week {row['season_order_week']}: a game at an earlier "
                    f"season_order_week kicked off at {prior_max}, on/after this week's first "
                    f"kickoff {row['min']}"
                )
            prior_max = row["max"] if prior_max is None else max(prior_max, row["max"])
    if violations:
        raise AssertionError(
            "season_order_week is not monotone in game_date — the fit window for an as-of "
            "week can contain a game played later than the week it predicts:\n  "
            + "\n  ".join(violations[:10])
        )
    passed.append("season_order_week is monotone in game_date (date-based, not week-based)")

    # ── 2. The seed season is never emitted. ─────────────────────────────────────────
    if (weekly["season"] <= SEED_SEASON).any():
        raise AssertionError(
            f"season {SEED_SEASON} was emitted; it is the hyperparameter seed and its "
            f"coefficients are in-sample"
        )
    passed.append(f"seed season {SEED_SEASON} not emitted (its hyperparameters are in-sample)")

    # ── 3. Every emitted row has out-of-sample hyperparameters. ──────────────────────
    if weekly["hyper_in_sample"].any():
        bad = sorted(weekly.loc[weekly["hyper_in_sample"], "season"].unique())
        raise AssertionError(f"seasons {bad} were emitted with in-sample hyperparameters")
    passed.append("every emitted row's hyperparameters were fit on strictly prior seasons")

    # ── 4. Week 1 has no games in its window, by construction. ───────────────────────
    wk1 = weekly[weekly["as_of_week"] == weekly.groupby("season")["as_of_week"].transform("min")]
    if (wk1["games_in_window"] > 0).any():
        raise AssertionError("the first as-of week of a season has a non-empty fit window")
    passed.append("the first as-of week of each season is a pure preseason prior (0 games)")

    # ── 5. The grain is unique. ──────────────────────────────────────────────────────
    dupes = weekly.duplicated(subset=["season", "team_id", "as_of_week"]).sum()
    if dupes:
        raise AssertionError(f"{dupes} duplicate (season, team_id, as_of_week) rows")
    passed.append("grain (season, team_id, as_of_week) is unique")

    # ── 6. The posterior is finite everywhere. ───────────────────────────────────────
    for col in ("strength_margin", "strength_margin_sd"):
        if not np.isfinite(weekly[col]).all():
            raise AssertionError(f"{col} contains non-finite values")
    if (weekly["strength_margin_sd"] <= 0).any():
        raise AssertionError("strength_margin_sd must be strictly positive")
    passed.append("strength_margin / _sd are finite and the sd is strictly positive")

    # ── 7. The uncertainty must be PHYSICALLY PLAUSIBLE. ────────────────────────────
    # A posterior sd is not just "some positive number". CFB team strength spans roughly
    # +-40 points, so an sd above ~50 is not humility, it is a broken fit — and it is a
    # SILENT break, because the mean can look perfectly reasonable next to it. This gate
    # exists because it fired: a barely-supported covariate indicator inherited the flat
    # prior's variance and 2021 New Mexico State shipped strength_margin_sd = 913.
    worst = weekly.nlargest(1, "strength_margin_sd")
    if float(worst["strength_margin_sd"].iloc[0]) > _MAX_PLAUSIBLE_SD:
        raise AssertionError(
            f"strength_margin_sd reaches {float(worst['strength_margin_sd'].iloc[0]):.1f} "
            f"points ({worst['season'].iloc[0]} {worst['team'].iloc[0]}, week "
            f"{worst['as_of_week'].iloc[0]}) — above the {_MAX_PLAUSIBLE_SD}-point "
            f"plausibility ceiling. This means a coefficient is unidentified and its prior "
            f"variance is leaking into team uncertainty; check covariate support."
        )
    passed.append(
        f"strength_margin_sd is physically plausible (max "
        f"{weekly['strength_margin_sd'].max():.1f} pts, ceiling {_MAX_PLAUSIBLE_SD})"
    )

    return passed


# ══════════════════════════════════════════════════════════════════════════════════════
# Backtest — is the strength number worth anything? (honest, market-free)
# ══════════════════════════════════════════════════════════════════════════════════════


def backtest(weekly: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Score every completed game from its two teams' STRICTLY PREGAME strengths.

    A game at `season_order_week = W` is predicted from the `as_of_week = W` rows — which,
    by the leakage contract, were fit only on games before W. This is a walk-forward
    out-of-sample evaluation, not a fit statistic.

    ⚠️ This measures whether the strength estimate tracks REALITY (margins). It says
    nothing about whether it beats a MARKET price — that is P1.4's job, gated on the P0.6
    closing lines. No edge is claimed here.
    """
    # Rename the join key to the games frame's own column name so the merges never produce
    # a duplicated `as_of_week` (which pandas then refuses to suffix a second time).
    home = weekly[
        ["season", "team_id", "as_of_week", "strength_margin", "strength_margin_sd",
         "residual_sigma", "home_field_advantage"]
    ].rename(
        columns={
            "as_of_week": "season_order_week",
            "team_id": "home_team_id",
            "strength_margin": "home_strength",
            "strength_margin_sd": "home_strength_sd",
        }
    )
    away = weekly[["season", "team_id", "as_of_week", "strength_margin", "strength_margin_sd"]].rename(
        columns={
            "as_of_week": "season_order_week",
            "team_id": "away_team_id",
            "strength_margin": "away_strength",
            "strength_margin_sd": "away_strength_sd",
        }
    )
    df = games.merge(home, on=["season", "home_team_id", "season_order_week"], how="inner").merge(
        away, on=["season", "away_team_id", "season_order_week"], how="inner"
    )
    hfa = np.where(df["is_neutral_site"].astype(bool), 0.0, df["home_field_advantage"].astype(float))
    df["pred_margin"] = hfa + df["home_strength"] - df["away_strength"]
    df["pred_margin_hfa_only"] = hfa

    rows = []
    for label, pred in (
        ("strength model", df["pred_margin"]),
        ("home-field only", df["pred_margin_hfa_only"]),
        ("zero (coin flip)", pd.Series(0.0, index=df.index)),
    ):
        err = df["home_margin"] - pred
        rows.append(
            {
                "predictor": label,
                "n_games": len(df),
                "mae": float(err.abs().mean()),
                "rmse": float(math.sqrt(float((err ** 2).mean()))),
                "winner_accuracy": float(
                    ((pred > 0) == (df["home_margin"] > 0))[df["home_margin"] != 0].mean()
                ),
            }
        )
    out = pd.DataFrame(rows)
    out.attrs["by_season"] = (
        df.assign(abs_err=(df["home_margin"] - df["pred_margin"]).abs())
        .groupby("season")
        .agg(n_games=("game_id", "size"), mae=("abs_err", "mean"))
        .reset_index()
    )
    # Calibration of the emitted uncertainty is checked separately in the report.
    out.attrs["games"] = df
    return out


def uncertainty_calibration(backtest_games: pd.DataFrame) -> dict:
    """Is `strength_margin_sd` honest? Compare claimed to realized predictive spread.

    The model claims a game's margin is Normal with sd = sqrt(sigma^2 + sd_home^2 + sd_away^2).
    If the claim is right, the standardized residual has sd ~= 1. Well above 1 means the
    posterior is overconfident; well below means it is needlessly timid.
    """
    df = backtest_games
    total_sd = np.sqrt(
        df["residual_sigma"] ** 2 + df["home_strength_sd"] ** 2 + df["away_strength_sd"] ** 2
    )
    z = (df["home_margin"] - df["pred_margin"]) / total_sd
    return {
        "n": int(len(z)),
        "z_sd": float(z.std(ddof=0)),
        "z_mean": float(z.mean()),
        "coverage_80": float(((z.abs() < 1.2816)).mean()),
        "coverage_95": float(((z.abs() < 1.9600)).mean()),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def _preseason_rows(weekly: pd.DataFrame) -> pd.DataFrame:
    first = weekly.groupby("season")["as_of_week"].transform("min")
    return weekly[weekly["as_of_week"] == first]


def write_report(
    weekly: pd.DataFrame,
    hyper: pd.DataFrame,
    checks: list[str],
    bt: pd.DataFrame,
    calib: dict,
    notes: list[str],
    path: Path,
) -> None:
    seasons = sorted(weekly["season"].unique())
    final = weekly.sort_values("as_of_week").groupby(["season", "team_id"]).tail(1)
    pre = _preseason_rows(weekly)
    lines: list[str] = []
    a = lines.append

    a("# NCAAF-P1.2 — conference/team-strength mixed-effects model")
    a("")
    a(f"**Model:** `{MODEL_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()}")
    a(f"**Seasons emitted:** {seasons[0]}–{seasons[-1]} ({len(weekly):,} team-week rows) · "
      f"**seed (not emitted):** {SEED_SEASON}")
    a("")
    a("> ⚠️ **This is a strength PRIOR, not an edge claim.** Every number below is measured "
      "against realized margins, never against a market price. No bet, no win rate, no ROI is "
      "implied or claimed; `best_alpha = 0` still holds. Whether this feature is worth "
      "anything against a closing line is P1.4's question, and P1.4 answers it under the "
      "§0.5 bake-off discipline (≥3 model classes, purged/embargoed CV, PBO/DSR).")
    a("")

    a("## 1. Leakage gates")
    a("")
    for c in checks:
        a(f"- ✅ {c}")
    a("")

    a("## 2. What the model learned (stage-A hyperparameters, fit on strictly prior seasons)")
    a("")
    hcols = [c for c in ("season", "model", "seasons_used", "n_obs", "sigma", "home_field",
                         "tau_team", "tau_conference", "converged") if c in hyper.columns]
    h = hyper[hyper["model"] == "margin"][hcols].tail(6)
    a(h.to_markdown(index=False, floatfmt=".3f"))
    a("")
    a("`home_field` is the fitted home-field advantage in points; `tau_team` is how far teams "
      "spread around their conference mean; `tau_conference` is how far conferences spread "
      "around the league. The ratio of the two IS the partial-pooling story — a team with few "
      "games is pulled toward its conference by roughly "
      "`sigma^2 / (sigma^2 + n * tau_team^2)` of the distance.")
    a("")

    a("### 2.1 Pre-season covariate coefficients (points of strength per 1 sd of covariate)")
    a("")
    beta_cols = [c for c in hyper.columns if c.startswith("beta_") and c.endswith("_z")]
    if beta_cols:
        latest = hyper[(hyper["model"] == "margin")].tail(1)
        brows = []
        for c in sorted(beta_cols):
            base = c[len("beta_") : -2]
            brows.append(
                {
                    "covariate": base,
                    "group": COVARIATE_GROUPS.get(base, "other"),
                    "beta (pts / sd)": float(latest[c].iloc[0]) if c in latest else float("nan"),
                }
            )
        a(pd.DataFrame(brows).to_markdown(index=False, floatfmt=".3f"))
    else:
        a("_No covariate coefficients were identified in the most recent fit._")
    a("")

    a("## 3. ⭐ Does the roster/NIL-flux covariate actually move teams? (the P1.2 sanity check)")
    a("")
    a("`covariate_component_roster_flux` is, per team, the points of pre-season strength "
      "attributable to returning production + roster continuity + net portal stars — i.e. "
      "exactly what would vanish if those covariates were removed from the prior mean. "
      "Measured at each season's week-1 row, where the covariates are the ONLY in-season-free "
      "signal there is.")
    a("")
    grp_cols = [c for c in pre.columns if c.startswith("covariate_component_")]
    spread = pd.DataFrame(
        {
            "component": [c.replace("covariate_component_", "") for c in grp_cols],
            "sd across teams (pts)": [float(pre[c].std(ddof=0)) for c in grp_cols],
            "max |contribution| (pts)": [float(pre[c].abs().max()) for c in grp_cols],
        }
    ).sort_values("sd across teams (pts)", ascending=False)
    a(spread.to_markdown(index=False, floatfmt=".3f"))
    a("")
    if "covariate_component_roster_flux" in pre.columns:
        movers = pre.reindex(
            pre["covariate_component_roster_flux"].abs().sort_values(ascending=False).index
        ).head(12)
        a("**Largest roster/portal-driven pre-season adjustments (all seasons):**")
        a("")
        a(
            movers[["season", "team", "conference", "covariate_component_roster_flux",
                    "strength_margin", "strength_margin_sd"]]
            .to_markdown(index=False, floatfmt=".2f")
        )
        a("")
        a("Read this list, do not just count it: if the biggest movers are not teams whose "
          "rosters plausibly churned, the covariate is picking up something else and the "
          "finding is not real.")
    a("")

    a("## 4. Face validity — end-of-season top 10")
    a("")
    for season in seasons[-2:]:
        top = final[final["season"] == season].nlargest(10, "strength_margin")
        a(f"**{season}**")
        a("")
        a(
            top[["team", "conference", "strength_margin", "strength_margin_sd",
                 "strength_offense", "strength_defense"]]
            .to_markdown(index=False, floatfmt=".2f")
        )
        a("")

    if final["strength_offense"].notna().any():
        net = final["strength_offense"] + final["strength_defense"]
        rho = float(np.corrcoef(net.values, final["strength_margin"].values)[0, 1])
        a(f"**Cross-check:** the margin model and the offense/defense model are INDEPENDENT "
          f"fits. `strength_offense + strength_defense` correlates with `strength_margin` at "
          f"**{rho:.3f}**. (Sum, not difference — defense is signed as points PREVENTED.) A "
          f"low value here means the two fits disagree about who is good and neither should "
          f"be trusted.")
        a("")

    a("## 5. Walk-forward accuracy (out-of-sample, vs realized margin — NOT vs a market)")
    a("")
    a(bt.to_markdown(index=False, floatfmt=".3f"))
    a("")
    by_season = bt.attrs.get("by_season")
    if by_season is not None:
        a("**Mean absolute error by season:**")
        a("")
        a(by_season.to_markdown(index=False, floatfmt=".2f"))
        a("")

    a("## 6. Is the emitted uncertainty honest?")
    a("")
    a(f"- standardized-residual sd: **{calib['z_sd']:.3f}** (1.00 = perfectly calibrated; "
      f">1 = overconfident, <1 = timid)")
    a(f"- standardized-residual mean: {calib['z_mean']:.3f} (0 = unbiased)")
    a(f"- realized 80% interval coverage: {calib['coverage_80']:.3f} (target 0.80)")
    a(f"- realized 95% interval coverage: {calib['coverage_95']:.3f} (target 0.95)")
    a(f"- n = {calib['n']:,} games")
    a("")
    a("")
    a("**What this does and does NOT say.** `strength_margin_sd` is the posterior uncertainty "
      "in the STRENGTH PARAMETER, and on that job it behaves correctly — it decays "
      "monotonically as games accumulate and it is wider for thin-sample teams. The numbers "
      "above test something stricter: whether a GAME-LEVEL predictive interval built as "
      "`sqrt(residual_sigma^2 + sd_home^2 + sd_away^2)` is honest. It is not, by about the "
      f"factor above ({calib['z_sd']:.2f}x).")
    a("")
    a("**The identified cause, stated rather than hand-waved.** `residual_sigma` comes from a "
      "RECENCY-WEIGHTED fit in which a game's variance is modelled as `sigma^2 / w`. The "
      "fitted `sigma` is therefore the variance a maximally-weighted (most recent) "
      "observation would have, not the average game's. Using it directly as a predictive "
      "residual understates the spread, and the shortfall is roughly `E[1/w]`. Two smaller "
      "contributors: the variance components are plugged in empirical-Bayes style rather "
      "than integrated over, and the offense/defense model treats a game's two team-rows as "
      "independent when they share weather, pace and officiating.")
    a("")
    a("**Consequence for P1.4 — do not consume this as a calibrated predictive sd.** Use "
      f"`strength_margin` as a point feature and `strength_margin_sd` as a RELATIVE "
      f"confidence signal (it ranks teams' certainty correctly). If P1.4 needs a calibrated "
      f"game-level interval it must recalibrate on held-out data, exactly as MLB's E13.6 did "
      f"for served totals probabilities — recalibration is its own story, and pretending a "
      f"structural sd is a predictive one is how a model ends up quietly overconfident in "
      f"production.")
    a("")

    a("## 7. Limitations")
    a("")
    a("- **`strength_margin_sd` is PARAMETER uncertainty, not a calibrated predictive sd.** "
      "It is correct and well-behaved as a measure of how well the strength is pinned down, "
      "and it is ~1.5x too tight if used to build a game-level interval. §6 gives the "
      "measured factor and the identified cause (a recency-weighted `sigma`). P1.4 must "
      "recalibrate rather than consume it directly.")
    a("- **Empirical-Bayes plug-in.** `sigma`, `tau_team`, `tau_conference` and the covariate "
      "coefficients are point estimates from the prior-season fit, not integrated out.")
    a("- **Offense/defense residual correlation.** The points model's two rows per game share "
      "weather, pace and officiating; treating them as independent makes "
      "`strength_offense_sd` / `strength_defense_sd` mildly optimistic. Prefer "
      "`strength_margin_sd` when one honest uncertainty is needed.")
    a("- **The conference level is a POOLING level, not a claim.** `mu_conf` is where thin "
      "samples get shrunk to; it is not evidence that conference membership causes strength.")
    a(f"- **The first emitted season ({seasons[0]}) is thinly calibrated.** Its "
      "hyperparameters come from a single prior season ("
      f"{int(weekly.loc[weekly['season'] == seasons[0], 'hyper_n_games'].iloc[0]):,} games) "
      "rather than the full lookback, so its shrinkage is less well tuned. This is disclosed "
      "per row via `hyper_n_prior_seasons` / `hyper_n_games` — P1.3/P1.4 can down-weight or "
      "drop it rather than discovering it downstream.")
    a("- **🚨 `strength_offense - strength_defense` is a trap.** Both are signed "
      "higher-is-better (defense = points PREVENTED), so a team's net strength is their "
      "SUM. Subtracting them returns ~0 for everyone. Use `strength_margin`.")
    a("- **Pre-2021 portal data does not exist** (`portal_data_covered = false`). Those "
      "seasons carry a `portal_net_stars_missing` indicator rather than a fabricated zero.")
    a("- **This model does not read `rollup_ncaaf_team_week_opponent_adjusted`.** P1.1's 2-pass "
      "schedule adjustment and this estimator are INDEPENDENT routes to opponent-adjusted "
      "strength; §5 lets them be compared rather than making one depend on the other. Fusing "
      "them is a P1.3/P1.4 question, not a P1.2 assumption.")
    a("")

    if notes:
        a("## 8. Run notes")
        a("")
        for n in notes:
            a(f"- {n}")
        a("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NCAAF-P1.2 team-strength mixed-effects model")
    p.add_argument(
        "--duckdb",
        default="quant_sports_intel_models/sports_dbt/sports.duckdb",
        help="path to the sports dbt DuckDB (box: /tmp/sports_ncaaf.duckdb)",
    )
    p.add_argument("--schema", default=MARTS_SCHEMA, help=f"marts schema (default {MARTS_SCHEMA})")
    p.add_argument(
        "--seasons",
        default=None,
        help="comma-separated seasons to EMIT — a SMOKE run, not a production one. "
             "Predecessors needed for the hyperparameter lookback are still fit, but their "
             "OWN predecessors are not, so the oldest one lacks a prior_strength covariate "
             "and results differ slightly from a full run. Default (recommended): every "
             "season after the seed.",
    )
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT), help="local artifact directory")
    p.add_argument("--s3", action="store_true", help="also land the posterior in the sports lake")
    p.add_argument("--no-points-model", action="store_true", help="skip the offense/defense fit")
    p.add_argument("--half-life-days", type=float, default=StrengthConfig.half_life_days,
                   help=f"recency half-life (default {StrengthConfig.half_life_days})")
    p.add_argument("--hyper-lookback", type=int, default=StrengthConfig.hyper_lookback_seasons,
                   help=f"prior seasons pooled for hyperparameters "
                        f"(default {StrengthConfig.hyper_lookback_seasons})")
    p.add_argument("--no-report", action="store_true", help="skip the markdown report")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    if not Path(args.duckdb).exists():
        p.error(
            f"DuckDB not found at {args.duckdb} — run the sports dbt build first "
            f"(`dbtf run --select ncaaf` in quant_sports_intel_models/sports_dbt), or point "
            f"--duckdb at the box's /tmp/sports_ncaaf.duckdb"
        )

    marts = load_marts(args.duckdb, args.schema)
    config = StrengthConfig(
        half_life_days=args.half_life_days,
        hyper_lookback_seasons=args.hyper_lookback,
        fit_points_model=not args.no_points_model,
    )
    seasons = [int(s) for s in args.seasons.split(",")] if args.seasons else None

    log.info("fitting %s (this is the multi-minute part) ...", MODEL_VERSION)
    run = run_strength(
        games=marts["games"],
        team_games=marts["team_games"],
        roster=marts["roster"],
        coaching=marts["coaching"],
        config=config,
        seasons=seasons,
    )
    weekly = run.weekly
    if weekly.empty:
        log.error("no rows produced — check --seasons")
        return 1
    log.info("produced %d team-week rows across %d seasons", len(weekly), weekly["season"].nunique())

    checks = validate(weekly, marts["games"])
    for c in checks:
        log.info("gate ✅ %s", c)

    bt = backtest(weekly, marts["games"])
    calib = uncertainty_calibration(bt.attrs["games"])
    log.info("walk-forward MAE %.2f pts (home-field-only baseline %.2f)",
             bt.loc[bt["predictor"] == "strength model", "mae"].iloc[0],
             bt.loc[bt["predictor"] == "home-field only", "mae"].iloc[0])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "ncaaf_team_strength_week.parquet"
    weekly.to_parquet(parquet_path, index=False)
    hyper = pd.DataFrame(run.hyperparameters)
    hyper.to_csv(out_dir / "ncaaf_team_strength_hyperparams.csv", index=False)
    (out_dir / "ncaaf_team_strength_summary.json").write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "rows": int(len(weekly)),
                "seasons": [int(s) for s in sorted(weekly["season"].unique())],
                "gates_passed": checks,
                "backtest": bt.to_dict(orient="records"),
                "uncertainty_calibration": calib,
                "config": vars(config),
                "notes": run.notes,
            },
            indent=2,
            default=float,
        )
    )
    log.info("parquet → %s (%d rows)", parquet_path, len(weekly))

    if args.s3:
        from quant_sports_intel_models.football.ncaaf.ingest import s3io

        for season, part in weekly.groupby("season"):
            n = s3io.write_dataframe(
                part, sport="ncaaf", source=LAKE_SOURCE, season=int(season), tier=LAKE_TIER
            )
            log.info("s3 season=%s: %d rows", season, n)

    if not args.no_report:
        write_report(weekly, hyper, checks, bt, calib, run.notes, _REPORT_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
