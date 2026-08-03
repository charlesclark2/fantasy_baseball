"""run_e8_7_complex_screen.py — E8.7: does a COMPLEX (DSL / CPX) line translate?

THE PRE-REGISTERED GATE, measured. See `ablation_results/e8_7_preregistration.md`, written and
committed BEFORE any statistic in this module was computed.

WHAT THIS IS
------------
A **screen**, not the MLE fit. It answers one question — *is there translatable signal in a
complex-level line at all?* — cheaply enough to decide whether the multi-hour sportId-16 game-log
backfill is justified. It reads the Stats API's SEASON-AGGREGATE endpoint (one call per
(season, sportId) page) instead of one boxscore per game, which is ~3 orders of magnitude cheaper
and returns exactly the season-level counting line the translation statistic consumes.

⚠️ It carries NO park / opponent / age context and therefore cannot itself fit or replace the E7.3
MLE. Per the pre-registration it may move the decision only toward MORE work or NO work.

THE STATISTIC
-------------
The E7.15-H1 primitive: the **within-player translation correlation** between a player's rate at a
source rung in season t and the same rate at the destination rung in a later season. Rates are
computed by `milb_mle.compute_rate_metrics_from_counts` — the SAME function the MLE uses, imported
rather than re-implemented so the screen and the model can never drift apart.

TWO-SIDED ANCHORS (NF1.7 (a)–(d) — an anchor that fails to compute is NOT a pass)
--------------------------------------------------------------------------------
* **CEILING — the analytic attenuation bound.** Both sides of a transition are noisy measurements,
  so the observed correlation is bounded above by `sqrt(rel_src * rel_dst)` where reliability is
  `(Var_observed - E[sampling noise]) / Var_observed`. Sampling noise is exact for a rate over a
  known denominator. ⭐ If the ceiling is ~0, the mechanism CANNOT ACT (NF1.9): a ~200-PA complex
  line is not a stable measurement of anything, and no number of extra seasons changes that. That
  is a SCOPE finding (`INACTIVE`), not a power one, and must never be reported as "needs N seasons".
* **FLOOR — a permutation null.** Destination lines shuffled within (rung, destination season). If
  the null is not centred on zero the pairing machinery is manufacturing correlation and no reading
  in this file is trustworthy. ⚠️ Scored against the null DISTRIBUTION (200 draws; |mean| <= 3 SE),
  **not** against a fixed |r| tolerance — see `evaluate()` for why the fixed tolerance was itself
  the MH2-H8 defect (a gate whose stringency is a side-effect of n).
* **BENCHMARK — the incumbent rungs** (`A -> A+`, `A+ -> AA`) through the identical code path. This
  is the matched comparison that makes a bare correlation interpretable (NF-D10: read the paired
  quantity, not a rank).

Usage (LAPTOP; the fetch is cached to parquet so re-runs are free):
    uv run python betting_ml/scripts/milb_mle/run_e8_7_complex_screen.py --seasons 2006-2025
    uv run python betting_ml/scripts/milb_mle/run_e8_7_complex_screen.py --seasons 2006-2025 --no-fetch
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The MLE's own rate formulas + the ladder's own transition-thickness floor, IMPORTED so the screen
# and the model cannot drift apart (and so the PA floor is inherited, not invented here).
from betting_ml.scripts.milb_mle.level_ladder import MIN_TRANSITION_PA  # noqa: E402
from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    _WOBA_W,
    compute_rate_metrics_from_counts,
)

# The ingest's league->rung map, imported for the same reason (one source of truth for the rung).
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("_ingest_milb", REPO / "scripts" / "ingest_milb_to_s3.py")
_ingest = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ingest)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("e8.7.screen")

STATSAPI = "https://statsapi.mlb.com/api/v1/stats"
# sportId 1 = MLB. Included so the screen can measure the DIRECT complex->MLB translation — which is
# the quantity an `mle_<metric>` board number literally IS — not only the rung-to-rung step.
MLB_SPORT_ID = 1
SPORT_IDS = (1, 11, 12, 13, 14, 16)
PAGE = 1000
DELAY = 0.15
TIMEOUT = 60

ARTIFACTS = REPO / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results" / "e8_7_artifacts"
CACHE = ARTIFACTS / "season_lines.parquet"

# The pre-registered transitions. Source rung -> the destination rungs a player realistically
# climbs to next. Registered in the pre-registration doc BEFORE measurement.
TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("DSL", "CPX"), ("DSL", "Single-A"),
    ("CPX", "Single-A"), ("CPX", "High-A"),
    # incumbent benchmarks — rungs the MLE already trusts, same instrument
    ("Single-A", "High-A"), ("High-A", "Double-A"),
    # ⭐ the DIRECT translation to the majors: an `mle_<metric>` board number literally IS a
    # projected MLB rate, so this is the estimand itself rather than a proxy for it. Read beside
    # the incumbent Single-A->MLB / Triple-A->MLB rows, which the E7.3 MLE is already fit on.
    ("DSL", "MLB"), ("CPX", "MLB"),
    ("Single-A", "MLB"), ("Triple-A", "MLB"),
)
INCUMBENT_BENCHMARK = ("Single-A", "High-A")
INCUMBENT_MLB_BENCHMARK = ("Single-A", "MLB")

METRICS = ("k_pct", "bb_pct", "iso", "woba")
# Clause 4 of the pre-registered PASS bar: >= this fraction of the incumbent A->A+ correlation.
PASS_FRACTION_OF_INCUMBENT = 0.50
# Draws used to characterise the permutation null. The floor is scored against this
# distribution's MEAN (a design constant at every n), never against a fixed |r|.
PERMUTATION_DRAWS = 200
BOOTSTRAP_N = 2000
SCREEN_SEED = 20260803

# API stat key -> the bat_* column name compute_rate_metrics_from_counts expects.
_STAT_COLS: dict[str, str] = {
    "plateAppearances": "bat_plate_appearances", "atBats": "bat_at_bats",
    "hits": "bat_hits", "doubles": "bat_doubles", "triples": "bat_triples",
    "homeRuns": "bat_home_runs", "baseOnBalls": "bat_walks",
    "intentionalWalks": "bat_intentional_walks", "hitByPitch": "bat_hit_by_pitch",
    "strikeOuts": "bat_strike_outs", "sacFlies": "bat_sac_flies",
    "totalBases": "bat_total_bases",
}


# ── fetch ────────────────────────────────────────────────────────────────────────────────────

def _fetch_page(session, sport_id: int, season: int, offset: int) -> tuple[list[dict], int]:
    r = session.get(STATSAPI, params={
        "stats": "season", "group": "hitting", "sportId": sport_id, "season": season,
        "limit": PAGE, "offset": offset, "playerPool": "ALL",
    }, timeout=TIMEOUT)
    r.raise_for_status()
    blocks = r.json().get("stats", [])
    if not blocks:
        return [], 0
    return blocks[0].get("splits", []), int(blocks[0].get("totalSplits") or 0)


def fetch_season_lines(seasons: list[int]) -> pd.DataFrame:
    """(player, season, level) season lines for every level, from the season-aggregate endpoint."""
    session = requests.Session()
    session.headers.update({"User-Agent": "credence-e8.7-screen/1.0 (research)"})
    rows: list[dict] = []
    for season in seasons:
        for sport_id in SPORT_IDS:
            offset, total, got = 0, None, 0
            while True:
                try:
                    splits, total = _fetch_page(session, sport_id, season, offset)
                except Exception as exc:  # noqa: BLE001
                    log.warning("  %d sport %d offset %d failed: %s", season, sport_id, offset, exc)
                    break
                if not splits:
                    break
                for sp in splits:
                    pl, st = sp.get("player") or {}, sp.get("stat") or {}
                    lg = sp.get("league") or {}
                    league_id = lg.get("id")
                    if sport_id == MLB_SPORT_ID:
                        level = "MLB"
                    else:
                        level = _ingest.derive_level_name(
                            sport_id, int(league_id) if league_id is not None else None, lg.get("name"))
                    if level is None:
                        continue  # unrecognised league — never guessed (see the ingest docstring)
                    row = {"player_id": pl.get("id"), "player_name": pl.get("fullName"),
                           "season": season, "sport_id": sport_id, "level_name": level,
                           "league_id": league_id}
                    for api_key, col in _STAT_COLS.items():
                        row[col] = pd.to_numeric(st.get(api_key), errors="coerce")
                    rows.append(row)
                got += len(splits)
                offset += PAGE
                time.sleep(DELAY)
                if total is not None and offset >= total:
                    break
            log.info("  %d sport %-2d -> %5d split(s)", season, sport_id, got)
    df = pd.DataFrame(rows)
    log.info("fetched %d raw split(s) over %d season(s)", len(df), len(seasons))
    return df


# ── build (player, season, level) lines ──────────────────────────────────────────────────────

def build_lines(raw: pd.DataFrame) -> pd.DataFrame:
    """Sum a player's splits within (player, season, level) then attach the MLE's own rates.

    ⭐ Also attaches a `<metric>_c` column: the rate CENTRED ON ITS OWN (rung, season) mean.

    Why this exists, and it was NOT anticipated — the pre-registered permutation FLOOR caught it.
    Shuffling destination lines within destination season preserves that season's MEAN, so a
    league-wide ERA TREND (minor-league K% rose steadily over 2006-2025) survives the shuffle and
    leaks into the null: the floor returned up to +0.161, and it did so on the INCUMBENT rungs too,
    i.e. it was never a complex-level artefact but a confound in the raw statistic itself. Part of
    every raw correlation is "both lines are from the same era", not "this player translates".

    Centring within (rung, season) removes exactly that mean shift — which is also precisely what
    the MLE's level factor does — and is therefore the honest primary reading. The RAW statistic is
    still computed and reported beside it (NF1.8: report both conventions when changing one).
    """
    count_cols = [c for c in _STAT_COLS.values()]
    agg = (raw.dropna(subset=["player_id"])
              .groupby(["player_id", "season", "level_name"], as_index=False)[count_cols]
              .sum(min_count=1))
    out = compute_rate_metrics_from_counts(agg)
    out = out.rename(columns={f"minor_{m}": m for m in METRICS})
    for m in METRICS:
        out[f"{m}_c"] = out[m] - out.groupby(["level_name", "season"])[m].transform("mean")
    return out


# ── anchors ──────────────────────────────────────────────────────────────────────────────────

def _sampling_noise_var(df: pd.DataFrame, metric: str) -> np.ndarray:
    """E[sampling variance] of the metric for each row, computed EXACTLY from its own outcome counts.

    ⚠️ A first cut approximated the weighted metrics with a crude delta-method bound
    (`p*(w_max - p)/n`). It over-stated the noise so badly that reliability came out NEGATIVE for
    `woba` at every rung — including rungs the MLE already trusts — which is not a finding, it is an
    uninformative estimator. It is replaced here by the exact multinomial variance, which the season
    line's own counts fully determine:

        per-trial outcome x takes weight w_k with probability p_k = count_k / denominator
        Var(x)      = SUM_k p_k w_k^2  -  (SUM_k p_k w_k)^2
        Var(metric) = Var(x) / denominator

    k_pct / bb_pct are the binomial special case (weights 0/1). ISO is extra-bases-per-AB with
    weights {1B:0, 2B:1, 3B:2, HR:3}. wOBA uses the same linear weights the metric is defined by,
    imported from the MLE rather than re-typed.
    """
    def c(name: str) -> np.ndarray:
        return pd.to_numeric(df.get(name), errors="coerce").fillna(0.0).to_numpy(float)

    p = pd.to_numeric(df[metric], errors="coerce").to_numpy(float)
    pa, ab, h = c("bat_plate_appearances"), c("bat_at_bats"), c("bat_hits")
    dbl, tpl, hr = c("bat_doubles"), c("bat_triples"), c("bat_home_runs")
    bb, ibb, hbp, sf = c("bat_walks"), c("bat_intentional_walks"), c("bat_hit_by_pitch"), c("bat_sac_flies")

    with np.errstate(divide="ignore", invalid="ignore"):
        if metric in ("k_pct", "bb_pct"):
            return p * (1.0 - p) / pa
        if metric == "iso":
            second = (1.0**2 * dbl + 2.0**2 * tpl + 3.0**2 * hr) / ab
            return np.maximum(second - p**2, 0.0) / ab
        # woba — exact, using the metric's own linear weights (imported, never re-typed)
        den = ab + (bb - ibb) + sf + hbp
        b1, ubb = np.maximum(h - dbl - tpl - hr, 0.0), np.maximum(bb - ibb, 0.0)
        second = (_WOBA_W["ubb"]**2 * ubb + _WOBA_W["hbp"]**2 * hbp + _WOBA_W["b1"]**2 * b1
                  + _WOBA_W["b2"]**2 * dbl + _WOBA_W["b3"]**2 * tpl + _WOBA_W["hr"]**2 * hr) / den
        return np.maximum(second - p**2, 0.0) / den


def reliability(df: pd.DataFrame, metric: str) -> dict:
    """Analytic reliability = (Var_observed - E[noise]) / Var_observed, on this exact population."""
    sub = df.dropna(subset=[metric])
    if len(sub) < 30:
        return {"n": len(sub), "reliability": None, "reason": "n<30"}
    obs_var = float(np.var(sub[metric].to_numpy(float), ddof=1))
    noise = float(np.nanmean(_sampling_noise_var(sub, metric)))
    if obs_var <= 0:
        return {"n": len(sub), "reliability": None, "reason": "zero observed variance"}
    rel = (obs_var - noise) / obs_var
    return {"n": len(sub), "reliability": float(rel), "obs_var": obs_var, "noise_var": noise,
            "mean_pa": float(sub["bat_plate_appearances"].mean())}


# ── transitions ──────────────────────────────────────────────────────────────────────────────

def build_transitions(lines: pd.DataFrame, src: str, dst: str, min_pa: int) -> pd.DataFrame:
    """One row per player: their FIRST qualifying source line and their FIRST LATER dest line."""
    s = lines[(lines.level_name == src) & (lines.bat_plate_appearances >= min_pa)]
    d = lines[(lines.level_name == dst) & (lines.bat_plate_appearances >= min_pa)]
    if s.empty or d.empty:
        return pd.DataFrame()
    s = s.sort_values("season").groupby("player_id", as_index=False).first()
    m = s.merge(d, on="player_id", suffixes=("_src", "_dst"))
    m = m[m.season_dst > m.season_src]
    if m.empty:
        return pd.DataFrame()
    return m.sort_values("season_dst").groupby("player_id", as_index=False).first()


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 10 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def evaluate(pairs: pd.DataFrame, metric: str, rng: np.random.Generator,
             centred: bool = True) -> dict:
    """Translation correlation for one metric. `centred` uses the (rung, season)-centred rate — the
    primary reading, because the raw one carries an era confound the permutation floor exposed."""
    col = f"{metric}_c" if centred else metric
    sub = pairs.dropna(subset=[f"{col}_src", f"{col}_dst"])
    n = len(sub)
    if n < 10:
        return {"n": n, "r": None, "reason": "n<10"}
    a = sub[f"{col}_src"].to_numpy(float)
    b = sub[f"{col}_dst"].to_numpy(float)
    r = _corr(a, b)
    # player-clustered bootstrap. One row per player here, so a row resample IS a player resample.
    boots = np.array([_corr(a[i], b[i]) for i in
                      (rng.integers(0, n, n) for _ in range(BOOTSTRAP_N))])
    boots = boots[np.isfinite(boots)]
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) \
        if len(boots) > 50 else (float("nan"), float("nan"))
    # ── FLOOR: the permutation null (destination shuffled within destination season) ──────────
    # ⚠️ A first cut scored ONE permutation draw against a FIXED |r| < 0.05 tolerance. That is the
    # MH2-H8 defect in a new costume: a single draw's sd is ~1/sqrt(n), so the same constant is
    # ~1.7 sigma at n=3,509 but only ~0.57 sigma at n=130 — i.e. the gate's stringency was a
    # side-effect of n, and at the small ->MLB transitions it would fire on genuinely independent
    # data roughly half the time. It duly "failed" at exactly those rows (DSL->MLB bb_pct +0.183,
    # n=130) while every large rung sat inside +-0.065, and a control on independent data confirmed
    # the shuffler itself is unbiased (mean -0.0022, sd 0.0286 at n=1,200).
    #
    # CURE: score against the permutation DISTRIBUTION, not a constant. Many draws; the floor is
    # honest iff the null MEAN is indistinguishable from zero (|mean| <= 3 SE of the mean, a bound
    # that is a design constant at every n), and the observed r is then read as a z against that
    # null's own spread.
    perm_r = np.empty(PERMUTATION_DRAWS, float)
    base = sub[["season_dst"]].copy()
    for i in range(PERMUTATION_DRAWS):
        base["_b"] = b
        shuffled = base.groupby("season_dst")["_b"].transform(
            lambda s: s.to_numpy()[rng.permutation(len(s))])
        perm_r[i] = _corr(a, shuffled.to_numpy(float))
    perm_r = perm_r[np.isfinite(perm_r)]
    perm_mean = float(np.mean(perm_r)) if len(perm_r) else float("nan")
    perm_sd = float(np.std(perm_r, ddof=1)) if len(perm_r) > 1 else float("nan")
    perm_se = perm_sd / np.sqrt(len(perm_r)) if len(perm_r) > 1 else float("nan")

    # ⚠️ SECOND correction to this floor, in the OPPOSITE direction to the first. Requiring the
    # null MEAN to be statistically zero (|mean| <= 3 SE) is also wrong: with 200 draws the SE is
    # ~0.0013, so a null mean of +0.0116 is "significant" while being utterly negligible against an
    # observed r of 0.658 that sits 24.5 null-sd out. That test fails 26 of 40 cells INCLUDING the
    # incumbent rungs — a floor a known-good rung cannot pass is measuring the wrong thing.
    #
    # The residual location is real and explicable: shuffling within destination season cannot break
    # the pairing inside a SINGLETON season group, and the ->MLB transitions spread 130-193 players
    # over 20 seasons. So the null carries a small positive location by construction.
    #
    # CURE: use the null for what it actually provides — a LOCATION and a SCALE. Subtract the
    # location (`r_adj = r - perm_mean`, applied IDENTICALLY to the incumbent benchmark so the ratio
    # stays a matched comparison) and judge significance against the scale (`z`). This is the
    # MH2.1 (d) discipline: score a statistic against its own permutation null rather than against
    # an invented constant.
    r_adj = r - perm_mean if np.isfinite(perm_mean) else float("nan")
    z_vs_null = float((r - perm_mean) / perm_sd) if perm_sd and np.isfinite(perm_sd) else float("nan")
    # The floor's remaining job: the null must be CHARACTERISED (finite spread) and must not be so
    # large that the corrected statistic is mostly correction.
    floor_ok = bool(np.isfinite(perm_sd) and perm_sd > 0 and np.isfinite(r_adj))
    return {"n": n, "r": r, "r_adj": r_adj, "ci_lo": lo, "ci_hi": hi,
            "perm_mean": perm_mean, "perm_sd": perm_sd, "perm_se": perm_se,
            "floor_ok": floor_ok, "z_vs_permutation_null": z_vs_null,
            "mean_pa_src": float(sub["bat_plate_appearances_src"].mean()),
            "mean_pa_dst": float(sub["bat_plate_appearances_dst"].mean())}


def run(seasons: list[int], min_pa: int, fetch: bool) -> dict:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if fetch or not CACHE.exists():
        raw = fetch_season_lines(seasons)
        raw.to_parquet(CACHE, index=False)
    else:
        log.info("reading cached season lines from %s", CACHE)
        raw = pd.read_parquet(CACHE)
    raw = raw[raw.season.isin(seasons)]
    lines = build_lines(raw)
    log.info("(player, season, level) lines: %d", len(lines))
    log.info("lines per rung:\n%s", lines.level_name.value_counts().to_string())

    rng = np.random.default_rng(SCREEN_SEED)
    out: dict = {"seasons": [min(seasons), max(seasons)], "min_transition_pa": min_pa,
                 "lines_per_level": lines.level_name.value_counts().to_dict(),
                 "reliability": {}, "transitions": {}}

    # CEILING anchor — per (rung, metric), on the qualifying population only.
    for lvl in sorted(lines.level_name.unique()):
        sub = lines[(lines.level_name == lvl) & (lines.bat_plate_appearances >= min_pa)]
        out["reliability"][lvl] = {m: reliability(sub, m) for m in METRICS}

    for (src, dst) in TRANSITIONS:
        pairs = build_transitions(lines, src, dst, min_pa)
        key = f"{src}->{dst}"
        if pairs.empty:
            out["transitions"][key] = {"n_players": 0, "metrics": {}}
            log.info("%-22s  no qualifying transitions", key)
            continue
        res = {m: evaluate(pairs, m, rng, centred=True) for m in METRICS}
        raw = {m: evaluate(pairs, m, rng, centred=False) for m in METRICS}
        out["transitions"][key] = {"n_players": int(len(pairs)), "metrics": res,
                                   "metrics_raw_uncentred": raw}
        log.info("%-22s  n=%4d  " + "  ".join(
            f"{m}={res[m]['r']:+.3f}" if res[m].get("r") is not None and np.isfinite(res[m]["r"])
            else f"{m}=  n/a" for m in METRICS), key, len(pairs))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="E8.7 complex-level translation feasibility screen.")
    ap.add_argument("--seasons", default="2006-2025")
    ap.add_argument("--min-pa", type=int, default=MIN_TRANSITION_PA)
    ap.add_argument("--no-fetch", action="store_true", help="use the cached parquet")
    a = ap.parse_args()
    if "-" in a.seasons:
        lo, hi = a.seasons.split("-"); seasons = list(range(int(lo), int(hi) + 1))
    else:
        seasons = [int(s) for s in a.seasons.split(",")]
    res = run(seasons, a.min_pa, fetch=not a.no_fetch)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "complex_screen.json").write_text(json.dumps(res, indent=2, default=str))
    log.info("wrote %s", ARTIFACTS / "complex_screen.json")


if __name__ == "__main__":
    main()
