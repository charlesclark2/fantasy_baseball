"""MLB Edge-E7.5p — PITCHER MiLB MLE → recalibrated rookie-STARTER prior guards.

Fast-gate only: pure numpy/pandas + an IN-MEMORY DuckDB run of the real `eb_starter_posteriors`
DuckDB branch over synthetic tables. No S3, no Snowflake, no `pipeline` import (CLAUDE.md's fast-gate
rule — the fast gate has no dbt manifest).

Model-quality gates are BEHAVIORAL: CI mocks all IO and cannot see this class of bug. What these pin:

  Python side
  * the pitcher wired-metric set is (gb_pct, k_pct, bb_pct) and hr_rate / xwoba_against are NEVER wired
    (E7.3p graded them tied-field-null / no-signal — the E7.3 wOBA precedent);
  * κ = m(1−m)/σ_resid² − 1 (clipped) and the served κ-blend (m·κ + obs·n)/(κ + n): n=0 ⇒ the MLE mean,
    n→∞ ⇒ the observed line;
  * the evidence count is per-metric (BF for K%/BB%, BIP for GB%) — a GB κ measured against TBF would be
    ~2× wrong;
  * the thin-cameo floors are REQUIRED (has_mlb_label, plus MIN_MLB_BIP for GB%) — without them σ_resid
    inflates and the served prior is needlessly weak;
  * the ablation is purged by debut cohort and only wins when the minor line genuinely translates.

  SERVED-SQL side (the part CI would otherwise never see)
  * the DuckDB branch of dbt/models/eb_posteriors/eb_starter_posteriors.sql actually RUNS;
  * a cold-start rookie with an MLE and 0 BF is served EXACTLY his MLE line (not the band prior);
  * with BF accrued, the SQL κ-blend equals the Python `kappa_blend_posterior_mean` to 1e-9 — SQL↔Python
    parity, so the recalibration and the serving surface can't drift apart;
  * an EXPERIENCED starter is byte-identical to the pre-E7.5p behaviour (the cold-start gate holds);
  * with the fail-safe EMPTY prior view (missing parquet) every starter falls back to the generic prior —
    a missing artifact can never change, let alone HALT, the serving-critical build;
  * eb_gb_pct is populated for veterans too (league anchor + prior-season observed, BIP-weighted).
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle import mle_prior_pitcher as mpp

_MODEL = (Path(__file__).resolve().parents[2]
          / "dbt/models/eb_posteriors/eb_starter_posteriors.sql")


# ══════════════════════════════════════════════════════════════════════════════════════
# wiring policy + prior-strength math
# ══════════════════════════════════════════════════════════════════════════════════════


def test_only_the_translating_pitcher_metrics_are_wired():
    assert mpp.PITCHER_PRIOR_METRICS == ("gb_pct", "k_pct", "bb_pct")
    # the two E7.3p nulls must never sneak into the wired set
    for dead in ("hr_rate", "xwoba_against"):
        assert dead not in mpp.PITCHER_PRIOR_METRICS
        assert dead in mpp.PITCHER_NOT_WIRED and mpp.PITCHER_NOT_WIRED[dead]


def test_evidence_units_are_per_metric():
    # GB% accrues per ball in play; K%/BB% per batter faced. κ is a count of binomial trials, so
    # mixing them would mis-weight the prior by ~1/0.6.
    assert mpp.EVIDENCE_COUNT["gb_pct"] == "bip"
    assert mpp.EVIDENCE_COUNT["k_pct"] == mpp.EVIDENCE_COUNT["bb_pct"] == "bf"


def test_kappa_matches_prior_variance_identity_and_clips():
    m, sd = 0.44, 0.06
    k = mpp.kappa_from_resid_sd(m, sd, floor=1.0, cap=1e6)
    assert abs(np.sqrt(m * (1 - m) / (k + 1)) - sd) < 1e-9
    assert mpp.kappa_from_resid_sd(0.44, 1e-9) == mpp.KAPPA_CAP
    assert mpp.kappa_from_resid_sd(0.44, 10.0) == mpp.KAPPA_FLOOR


def test_kappa_blend_is_the_mle_at_zero_evidence_and_the_observation_in_the_limit():
    mean, kappa = 0.44, 68.0
    assert abs(mpp.kappa_blend_posterior_mean(mean, kappa, 0, 0.30) - mean) < 1e-12
    assert abs(mpp.kappa_blend_posterior_mean(mean, kappa, 0, None) - mean) < 1e-12
    # 100 BIP of observed 0.30 → (0.44·68 + 0.30·100)/(68+100)
    want = (0.44 * 68 + 0.30 * 100) / 168.0
    assert abs(mpp.kappa_blend_posterior_mean(mean, kappa, 100, 0.30) - want) < 1e-12
    assert abs(mpp.kappa_blend_posterior_mean(mean, kappa, 1e7, 0.31) - 0.31) < 1e-4


def test_kappa_blend_cannot_be_overwhelmed_by_a_tiny_sample_extreme():
    """The E7.5 ISO blow-up, pre-empted: a 2-BIP pitcher who happened to induce 2 grounders (obs=1.0)
    must barely move a κ≈68 prior. This is why every wired metric uses a pseudo-count, not Normal-Normal."""
    v = mpp.kappa_blend_posterior_mean(0.44, 68.0, n=2, obs_rate=1.0)
    assert 0.44 < v < 0.46


# ══════════════════════════════════════════════════════════════════════════════════════
# synthetic graduated-pitcher universe
# ══════════════════════════════════════════════════════════════════════════════════════


def _synth(seed=11, cohorts=(2016, 2017, 2018, 2019, 2020), per=40, noise=0.03,
           translate=True, thin_cameos=True, low_bip=True):
    """A projections-like frame: per (pitcher, level) rows with an emitted MLE and a realized MLB line.
    `thin_cameos` adds has_mlb_label=False rows with extreme realized rates (the E7.5 landmine);
    `low_bip` adds LABELLED rows whose realized GB% rests on a handful of balls in play (the GB-specific
    second-order version of the same landmine)."""
    rng = np.random.default_rng(seed)
    levels = ["Triple-A", "Double-A", "High-A"]
    rows = []
    pid = 0
    for coh in cohorts:
        for _ in range(per):
            pid += 1
            for lv in levels[: rng.integers(1, 4)]:
                mle_gb = float(np.clip(rng.normal(0.44, 0.05), 0.25, 0.62))
                mle_k = float(np.clip(rng.normal(0.21, 0.03), 0.09, 0.33))
                mle_bb = float(np.clip(rng.normal(0.09, 0.015), 0.04, 0.19))
                if translate:
                    mlb_gb = 0.6 * mle_gb + 0.17 + float(rng.normal(0, noise))
                    mlb_k = 0.6 * mle_k + 0.08 + float(rng.normal(0, noise))
                    mlb_bb = 0.6 * mle_bb + 0.03 + float(rng.normal(0, noise * 0.5))
                else:
                    mlb_gb = 0.44 + float(rng.normal(0, noise))
                    mlb_k = 0.21 + float(rng.normal(0, noise))
                    mlb_bb = 0.09 + float(rng.normal(0, noise * 0.5))
                rows.append(dict(
                    player_id=str(pid), level=lv, debut_cohort=coh, is_prospect=False,
                    mle_gb_pct=mle_gb, mlb_gb_pct=mlb_gb, mle_gb_pct_sd=0.008,
                    mle_k_pct=mle_k, mlb_k_pct=mlb_k, mle_k_pct_sd=0.006,
                    mle_bb_pct=mle_bb, mlb_bb_pct=mlb_bb, mle_bb_pct_sd=0.004,
                    mlb_pa=int(rng.integers(200, 700)), mlb_bip=int(rng.integers(120, 400)),
                    has_mlb_label=True,
                ))
    df = pd.DataFrame(rows)
    if thin_cameos:
        cameo = df.head(30).copy()
        cameo["player_id"] = ["cameo_%d" % i for i in range(len(cameo))]
        cameo[["mlb_k_pct", "mlb_gb_pct"]] = 1.0        # a 1-TBF strikeout — extreme, must be excluded
        cameo[["mlb_pa", "mlb_bip"]] = 1
        cameo["has_mlb_label"] = False
        df = pd.concat([df, cameo], ignore_index=True)
    if low_bip:
        thin = df.head(30).copy()
        thin["player_id"] = ["lowbip_%d" % i for i in range(len(thin))]
        thin["mlb_gb_pct"] = 1.0                        # 3 grounders on 3 balls in play
        thin["mlb_bip"] = 3
        thin["has_mlb_label"] = True                    # clears the TBF floor — only MIN_MLB_BIP saves us
        df = pd.concat([df, thin], ignore_index=True)
    return df


def test_recalibration_replaces_tight_param_sd_and_excludes_thin_samples():
    calib = mpp.recalibrate_pitcher(_synth())
    for m in mpp.PITCHER_PRIOR_METRICS:
        c = calib[m]
        assert c.resid_sd > c.param_sd_median, f"{m}: σ_resid must be WIDER than the parameter sd"
        assert c.resid_sd < 0.15, f"{m} σ_resid={c.resid_sd} — thin samples leaked past the floors"
        assert 0.5 < c.coverage_68 < 0.9


def test_gb_needs_its_own_bip_floor_not_just_the_tbf_floor():
    """A pitcher can clear mlb_pa ≥ 150 while putting 3 balls in play; his realized GB% is noise. Without
    MIN_MLB_BIP those rows survive `has_mlb_label` and inflate σ_resid — a needlessly weak served prior."""
    df = _synth(thin_cameos=False, low_bip=True)
    tight = mpp.recalibrate_pitcher(df, ("gb_pct",))["gb_pct"]
    loose = mpp.recalibrate_pitcher(df.assign(mlb_bip=10_000), ("gb_pct",))["gb_pct"]
    assert loose.resid_sd > tight.resid_sd * 1.5, (
        f"the BIP floor did not bite: {tight.resid_sd:.4f} vs unfiltered {loose.resid_sd:.4f}")


def test_recalibration_without_the_label_floor_is_inflated_by_cameos():
    df = _synth().drop(columns=["has_mlb_label"])
    assert mpp.recalibrate_pitcher(df, ("k_pct",))["k_pct"].resid_sd > 0.15


def test_calibrated_prior_table_is_one_row_per_pitcher_at_the_highest_level():
    df = _synth()
    calib = mpp.recalibrate_pitcher(df)
    tbl = mpp.build_calibrated_pitcher_prior_table(df, calib)
    assert tbl["pitcher_id"].is_unique
    assert not tbl["pitcher_id"].str.contains(r"\.", regex=True).any()   # never '664983.0' (INC-17)
    for m in mpp.PITCHER_PRIOR_METRICS:
        v = tbl[f"{m}_prior_kappa"].dropna()
        assert (v >= mpp.KAPPA_FLOOR - 1e-6).all() and (v <= mpp.KAPPA_CAP + 1e-6).all()
    # hr_rate / xwoba_against must not appear as served columns
    assert not [c for c in tbl.columns if "hr_rate" in c or "xwoba" in c]


def test_ablation_beats_the_generic_prior_when_the_minor_line_translates():
    abl = mpp.ablate_pitcher(_synth(translate=True))
    for m, r in abl.items():
        assert r.mle_wins, f"{m}: MLE nll {r.mle_nll} vs generic {r.generic_nll}"
        assert r.mle_mae < r.generic_mae


def test_ablation_does_not_win_when_the_minor_line_carries_nothing():
    abl = mpp.ablate_pitcher(_synth(translate=False), ("gb_pct",))
    assert not abl["gb_pct"].mle_wins


# ══════════════════════════════════════════════════════════════════════════════════════
# the SERVED SQL — run the real eb_starter_posteriors DuckDB branch over synthetic tables
# ══════════════════════════════════════════════════════════════════════════════════════

_MLE_PRIOR_COLS = ("pitcher_id VARCHAR, mle_gb_pct DOUBLE, gb_pct_prior_kappa DOUBLE, "
                   "mle_k_pct DOUBLE, k_pct_prior_kappa DOUBLE, mle_bb_pct DOUBLE, "
                   "bb_pct_prior_kappa DOUBLE")


def _duckdb_branch() -> str:
    """The model's DuckDB branch, resolved the same way run_w1_lakehouse.extract_duckdb_sql does.
    Re-implemented locally (a few lines) so the fast gate does not import scripts/."""
    text = _MODEL.read_text()
    text = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", "", text, flags=re.DOTALL)
    m = re.search(r"\{%-?\s*if\s+target\.name\s*==\s*['\"]duckdb['\"]\s*-?%\}(.*?)\{%-?\s*else\s*-?%\}",
                  text, re.DOTALL)
    assert m, "no duckdb branch in eb_starter_posteriors.sql"
    sql = re.sub(r"\{%-?\s*if\s+is_incremental\(\)\s*-?%\}.*?\{%-?\s*endif\s*-?%\}", "",
                 m.group(1), flags=re.DOTALL)
    sql = re.sub(r"\{\{\s*invocation_id\s*\}\}", "test", sql)
    assert not re.search(r"\{[{%]", sql), f"unresolved Jinja: {re.findall(r'.[{%].*?[%}].', sql)[:3]}"
    return sql.strip()


def _serve(mle_rows: list[dict] | None, *, season=2026, gb_prior_year_rows=None) -> pd.DataFrame:
    """Build the minimal precursor universe and run the served SQL.

    Three starters, all on the same game_date:
      rookie   — MLBAM 700001, NO prior MLB seasons (cold start), 0 BF this season
      rookie2  — MLBAM 700002, cold start, 80 BF accrued this season
      vet      — MLBAM 500001, 30 prior-season starts (⇒ n_prior_seasons ≥ 1), 300 BF this season
    `mle_rows=None` exercises the FAIL-SAFE empty prior view (missing parquet)."""
    con = duckdb.connect()
    gd = f"{season}-05-01"
    con.execute(f"""
        create table stg_statsapi_probable_pitchers as
        select * from (values
            ('1', date '{gd}', 'home', 700001, timestamp '{gd} 10:00:00'),
            ('2', date '{gd}', 'home', 700002, timestamp '{gd} 10:00:00'),
            ('3', date '{gd}', 'home', 500001, timestamp '{gd} 10:00:00')
        ) t(game_pk, game_date, side, probable_pitcher_id, ingestion_ts)
    """)
    # game logs: rookie2 has 4 current-season starts (80 BF); vet has 30 prior-season + 10 current.
    logs = []
    for i in range(4):                                   # rookie2, current season, 20 BF each
        logs.append((700002, f"{season}-04-0{i+1}", season, 20, 5, 2, 0.300))
    for i in range(30):                                  # vet, prior season
        logs.append((500001, f"{season-1}-06-{i % 28 + 1:02d}", season - 1, 22, 5, 2, 0.310))
    for i in range(10):                                  # vet, current season (300 BF total)
        logs.append((500001, f"{season}-04-{i+1:02d}", season, 30, 8, 3, 0.290))
    con.execute("create table mart_starting_pitcher_game_log(pitcher_id bigint, game_date date, "
                "game_year integer, batters_faced integer, strikeouts integer, walks integer, "
                "xwoba_against double)")
    con.executemany("insert into mart_starting_pitcher_game_log values (?,?,?,?,?,?,?)", logs)

    # experience-band priors (the incumbent generic prior)
    con.execute(f"""
        create table ref_eb_starter_priors as
        select * from (values
            ({season}, 'xwoba_against', 'u25', 1, 0.330, 0.030),
            ({season}, 'k_pct',         'u25', 1, 0.200, 0.040),
            ({season}, 'bb_pct',        'u25', 1, 0.090, 0.020),
            ({season}, 'xwoba_against', 'a33', 4, 0.310, 0.030),
            ({season}, 'k_pct',         'a33', 4, 0.230, 0.040),
            ({season}, 'bb_pct',        'a33', 4, 0.075, 0.020)
        ) t(season, metric, age_band, band_rank, mu, sigma)
    """)
    con.execute("create table player_sequential_posteriors(player_id bigint, player_type varchar, "
                "metric varchar, season integer, game_date date, posterior_mu double)")

    # batted-ball profile: the vet has a prior-season GB line; the rookies do not (the cold start).
    rows = gb_prior_year_rows if gb_prior_year_rows is not None else [
        (500001, season - 1, 0.480, 300), (500002, season - 1, 0.400, 280),
        (500003, season - 1, 0.520, 260), (500004, season - 1, 0.430, 240),
    ]
    con.execute("create table mart_pitcher_batted_ball_profile(pitcher_id bigint, game_year integer, "
                "gb_pct double, total_batted_balls integer)")
    con.executemany("insert into mart_pitcher_batted_ball_profile values (?,?,?,?)", rows)
    # the league anchor is restricted to pitchers who STARTED → give the extra ids a prior-season start
    con.executemany("insert into mart_starting_pitcher_game_log values (?,?,?,?,?,?,?)",
                    [(p, f"{season-1}-06-01", season - 1, 25, 6, 2, 0.310)
                     for p, *_ in rows if p != 500001])

    con.execute(f"create table milb_mle_pitcher_prior({_MLE_PRIOR_COLS})")
    if mle_rows:
        con.executemany(
            "insert into milb_mle_pitcher_prior values (?,?,?,?,?,?,?)",
            [(r["pitcher_id"], r.get("mle_gb_pct"), r.get("gb_pct_prior_kappa"),
              r.get("mle_k_pct"), r.get("k_pct_prior_kappa"),
              r.get("mle_bb_pct"), r.get("bb_pct_prior_kappa")) for r in mle_rows])

    return con.execute(_duckdb_branch()).df().set_index("pitcher_id")


_PRIOR = [dict(pitcher_id="700001", mle_gb_pct=0.520, gb_pct_prior_kappa=68.0,
               mle_k_pct=0.260, k_pct_prior_kappa=81.0, mle_bb_pct=0.070, bb_pct_prior_kappa=146.0),
          dict(pitcher_id="700002", mle_gb_pct=0.380, gb_pct_prior_kappa=68.0,
               mle_k_pct=0.180, k_pct_prior_kappa=81.0, mle_bb_pct=0.110, bb_pct_prior_kappa=146.0)]


def test_served_sql_runs_and_covers_every_starter():
    out = _serve(_PRIOR)
    assert set(out.index) == {"700001", "700002", "500001"}
    assert "eb_gb_pct" in out.columns


def test_cold_start_rookie_with_zero_bf_is_served_his_mle_line_not_the_band_prior():
    out = _serve(_PRIOR)
    r = out.loc["700001"]
    assert r["age_band"] == "u25"
    assert abs(r["eb_k_pct"] - 0.260) < 1e-9,  "K% must be the MLE mean, not the 0.200 band prior"
    assert abs(r["eb_bb_pct"] - 0.070) < 1e-9, "BB% must be the MLE mean, not the 0.090 band prior"
    assert abs(r["eb_gb_pct"] - 0.520) < 1e-9, "GB% must be the MLE mean (no prior-season BIP at all)"
    # xwOBA-against is NOT wired — it keeps the band prior verbatim
    assert abs(r["eb_xwoba_against"] - 0.330) < 1e-9


def test_served_kappa_blend_matches_the_python_formula_exactly():
    """SQL↔Python parity. rookie2 has 80 BF at an observed K% of 20/80 = 0.25 and BB% 8/80 = 0.10."""
    out = _serve(_PRIOR)
    r = out.loc["700002"]
    want_k = mpp.kappa_blend_posterior_mean(0.180, 81.0, n=80, obs_rate=20 / 80)
    want_bb = mpp.kappa_blend_posterior_mean(0.110, 146.0, n=80, obs_rate=8 / 80)
    assert abs(r["eb_k_pct"] - round(want_k, 4)) < 1e-9
    assert abs(r["eb_bb_pct"] - round(want_bb, 4)) < 1e-9
    # and it sits strictly between the MLE prior and the observed line (the accrual blend)
    assert 0.180 < r["eb_k_pct"] < 0.25


def test_experienced_starter_is_untouched_by_the_cold_start_gate():
    """The vet carries an MLE row too — the gate must ignore it (his 2015 minor line is
    out-of-distribution for the E7.3p map, which is calibrated on a pitcher's first two MLB seasons)."""
    vet_prior = _PRIOR + [dict(pitcher_id="500001", mle_gb_pct=0.99, gb_pct_prior_kappa=400.0,
                               mle_k_pct=0.99, k_pct_prior_kappa=400.0,
                               mle_bb_pct=0.99, bb_pct_prior_kappa=400.0)]
    with_mle = _serve(vet_prior).loc["500001"]
    without = _serve(_PRIOR).loc["500001"]
    assert with_mle["age_band"] != "u25"
    for col in ("eb_k_pct", "eb_bb_pct", "eb_xwoba_against", "eb_gb_pct"):
        assert with_mle[col] == without[col], f"{col} moved for an experienced starter"
    assert with_mle["eb_k_pct"] < 0.5, "an absurd MLE leaked into a veteran's posterior"


def test_failsafe_empty_prior_view_reproduces_the_generic_prior_exactly():
    """The missing-parquet path (run_w1_lakehouse registers an EMPTY typed view). Every starter must be
    byte-identical to the pre-E7.5p behaviour — a missing artifact can never change serving, let alone
    HALT it."""
    empty = _serve(None)
    assert abs(empty.loc["700001", "eb_k_pct"] - 0.200) < 1e-9      # the u25 band prior
    assert abs(empty.loc["700001", "eb_bb_pct"] - 0.090) < 1e-9
    assert abs(empty.loc["700001", "eb_xwoba_against"] - 0.330) < 1e-9
    # the veteran's three incumbent metrics are unchanged with or without the prior view
    served = _serve(_PRIOR)
    for col in ("eb_k_pct", "eb_bb_pct", "eb_xwoba_against"):
        assert empty.loc["500001", col] == served.loc["500001", col]
    # eb_gb_pct still populates off the league anchor (it never depended on the MLE for a veteran)
    assert 0.3 < empty.loc["500001", "eb_gb_pct"] < 0.6


def test_eb_gb_pct_shrinks_a_veteran_toward_his_prior_season_ground_ball_rate():
    out = _serve(_PRIOR)
    vet = out.loc["500001", "eb_gb_pct"]
    league = (0.480 * 300 + 0.400 * 280 + 0.520 * 260 + 0.430 * 240) / 1080
    # observed 0.480 on 300 BIP vs a league anchor ≈0.457 → strictly between, nearer the observation
    assert min(league, 0.480) <= vet <= max(league, 0.480)
    assert abs(vet - 0.480) < abs(vet - league)


def test_rookie_gb_prior_is_the_mle_even_though_the_league_anchor_exists():
    """The whole point: at BF/BIP = 0 the cold-start starter is priced off his translated minor-league
    ground-ball profile (0.520), not off the league mean (~0.457)."""
    out = _serve(_PRIOR)
    assert abs(out.loc["700001", "eb_gb_pct"] - 0.520) < 1e-9
    assert abs(out.loc["700002", "eb_gb_pct"] - 0.380) < 1e-9


def test_type_pin_block_covers_the_new_gb_column():
    """INC-19: a new FLOAT output column MUST be ::double-pinned (and hence in the manifest)."""
    body = _MODEL.read_text()
    pin = body.split("-- TYPE-PIN-START")[1].split("-- TYPE-PIN-END")[0]
    assert "eb_gb_pct::double as eb_gb_pct" in pin


@pytest.mark.parametrize("dead", ["hr_rate", "xwoba_against"])
def test_the_no_signal_metrics_never_reach_the_served_sql(dead):
    body = _MODEL.read_text()
    assert f"mle_{dead}" not in body, f"E7.3p graded {dead} no-signal — it must not be wired"
