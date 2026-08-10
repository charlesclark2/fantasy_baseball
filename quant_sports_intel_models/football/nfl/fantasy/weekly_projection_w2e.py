"""weekly_projection_w2e.py — NF-W2e: is NF-W2d's 2025 attenuation caused by CAPTURE FRESHNESS?

THE ONE REGISTERED HYPOTHESIS (see ablation_results/nf_w2e_preregistration.md, committed before
any lift was scored): NF-W2d measured the injury family's lift at ~1/3 its legacy size at RB on
the 2025 as-of-capture era, ARM-INVARIANTLY, and eliminated coverage dilution, season scale and
practice-line absence. The surviving candidate is the capture signal character itself. NF-W2e
tests its sharpest form — that the attenuation comes from consuming designations a FRESHER
available capture has already superseded (measured: 36.3% of listed 2025 rows), so restricting
consumption to fresher captures should RECOVER lift. The competing outcome is registered as
equally informative: freshness costs 65–79% of the designations, so `inj_latest` winning would
mean a stale-but-present designation beats no designation and would REFUTE carry-over.

⛔ THIS MODULE CERTIFIES NOTHING, BY DESIGN. The consumption rule can only act on capture-era
rows ⇒ 2 active folds, where `fold_consistency_clause(2).attainable` is False, `pbo_evaluable(2)`
is False, `sign_test_floor(2)` = 0.25 exceeds every BH cutoff and `dsr_ceiling(2)` = 0.9214 sits
below the 0.95 gate. The per-position verdict is fixed to NO_CERTIFICATION_POSSIBLE and the
primary read is a ROW-level clustered comparison, not a fold-level gate.

⭐ THE COVERAGE BOUND AND THE CONSUMPTION BOUND ARE SEPARATE, AND THAT IS LOAD-BEARING.
`COVERAGE_MAX_AGE_DAYS = 7` continues to decide which rows are OBSERVED for every rung; only the
consumption bound moves down the ladder. Collapsing them would shrink the scored population as
the ladder tightens, so the arms would differ in their rows as well as their features and the
comparison would be uninterpretable. `assert_population_identical` enforces it.

Pure module — no lake IO. The runner is `run_nf_w2e_capture_freshness.py`.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────

#: The declared family: a monotone FRESHNESS LADDER over the consumption rule. One coherent
#: mechanism (MH2: run a COHERENT, DECLARED family), three rungs answering one question.
#: `None` = "only the week's FRESHEST admissible capture instant for that row".
FRESHNESS_LADDER: tuple[tuple[str, float | None], ...] = (
    ("inj_latest", W2D.COVERAGE_MAX_AGE_DAYS),   # the NF-W2d incumbent construction
    ("inj_fresh1d", 1.0),                        # the VALIDATED stratifier boundary (see below)
    ("inj_freshest", None),                      # freshest instant only — no carry-over at all
)
LADDER_ARMS: tuple[str, ...] = tuple(name for name, _ in FRESHNESS_LADDER)
INCUMBENT_RUNG = "inj_latest"
FOIL_W2E = W2B.FOIL_W2B          # `base_rate`, unchanged from NF-W2b/NF-W2d
ANCHORS_W2E: tuple[str, ...] = ("nihilist_zero", "pos_marginal", "oracle_avail__inj")

#: ⭐ 1.0 day is NOT a tuned knob — it is the boundary of the stratifier validation measured
#: BEFORE any lift was read (designation-change rate 0.161 at ≤1 d vs 0.363 at >1 d over 341
#: multi-capture player-weeks; rank corr +0.289, p < 1e-4). See the pre-registration §(2).
VALIDATED_STRATUM_BOUNDARY_DAYS = 1.0

#: The arm FORM is held fixed at `inj_both` for every rung, justified by a MEASURED quantity:
#: NF-W2d found the era ratio arm-invariant (max |inj_both − inj_zero_leg| = 0.062 across all
#: four positions), so the freshness question does not depend on the leg structure.
LADDER_FORM = "inj_both"
ARM_INVARIANCE_MAX_SPREAD_AT_REGISTRATION = 0.062

#: Legacy folds on which all three rungs are additionally FITTED, so the mechanical proof that
#: the ladder is inert before 2025 is backed by a MEASURED tie rather than standing alone.
MEASURED_TIE_FOLDS: tuple[str, ...] = ("2024H1", "2024H2")
TIE_TOLERANCE = 1e-9

#: The capture-era blocks — the only folds on which the mechanism can act.
CAPTURE_ERA_BLOCKS: tuple[tuple[int, int], ...] = W2B.SHADOW_BLOCKS_W2B   # ((2025,1),(2025,2))
TEST_BLOCKS_W2E = W2D.TEST_BLOCKS_W2D                                     # all 14, unchanged

#: This study registers no ship unit. The field exists so a reader cannot mistake the absence of
#: a verdict for an oversight.
VERDICT_W2E = "NO_CERTIFICATION_POSSIBLE"


# ── The ladder: consumption bound varies, coverage bound does NOT ───────────────────────────────
def engineer_rung(feat: pd.DataFrame, injuries: pd.DataFrame, *,
                  consumption_max_age_days: float | None) -> pd.DataFrame:
    """Engineer the injury + rate families under ONE rung of the freshness ladder.

    Identical to `W2D.engineer_injury_features_w2d` except that the CONSUMPTION bound is supplied
    separately from the COVERAGE bound:

      · coverage (`_inj_observed`) always uses `W2D.COVERAGE_MAX_AGE_DAYS` ⇒ the scored population
        is the SAME for every rung (guard: `assert_population_identical`);
      · consumption keeps only captures within `consumption_max_age_days` of the row's own gameday
        instant, or — when it is None — only captures at the week's FRESHEST admissible instant
        for that row (the no-carry-over extreme).

    The legacy (nflverse) path is untouched by the rung, which is what makes the ladder provably
    inert before 2025.
    """
    f = W2D.attach_coverage(feat, injuries, max_age_days=W2D.COVERAGE_MAX_AGE_DAYS)
    gameday_utc = pd.to_datetime(f["_target_gameday"], errors="coerce").dt.tz_localize("UTC")

    inj = injuries.copy()
    inj["_dm_utc"] = pd.to_datetime(inj["date_modified"], utc=True, errors="coerce")
    inj["_rs"] = W2._norm(inj["report_status"]).where(inj["report_status"].notna())
    inj["_ps"] = W2._norm(inj["practice_status"]).where(inj["practice_status"].notna())
    inj["_practice_known"] = inj["practice_status"].notna()
    keep = ["season", "week", "gsis_id", "_dm_utc", "_rs", "_ps", "_practice_known", "_stamp_kind"]

    legacy = inj[inj["_stamp_kind"] == W2D.STAMP_NFLVERSE]
    legacy = (legacy.sort_values("_dm_utc", na_position="first")
                    .drop_duplicates(["season", "week", "gsis_id"], keep="last"))
    capture = inj[inj["_stamp_kind"] == W2D.STAMP_WAYBACK]

    f = f.merge(legacy[keep], on=["season", "week", "gsis_id"], how="left").reset_index(drop=True)
    gameday_utc = pd.to_datetime(f["_target_gameday"], errors="coerce").dt.tz_localize("UTC")
    observed = f["_inj_observed"].to_numpy(dtype=bool)

    if len(capture):
        cand = f[["season", "week", "gsis_id"]].copy()
        cand["_row"] = np.arange(len(f))
        cand["_g"] = gameday_utc.to_numpy()
        # the row's own week-freshest admissible capture age — the no-carry-over reference
        cand["_wk_freshest"] = pd.to_numeric(f["_inj_capture_age_days"], errors="coerce").to_numpy()
        cand = cand.merge(capture[keep], on=["season", "week", "gsis_id"], how="inner")
        age = (cand["_g"] - cand["_dm_utc"]).dt.total_seconds() / 86400.0
        admissible = (cand["_dm_utc"] < cand["_g"]) & (age <= W2D.COVERAGE_MAX_AGE_DAYS)
        if consumption_max_age_days is None:
            # only captures AT the week's freshest admissible instant for this row: a player the
            # newest report does not list reads NOT LISTED instead of carrying a stale designation
            fresh = admissible & (age <= cand["_wk_freshest"] + 1e-9)
        else:
            fresh = admissible & (age <= float(consumption_max_age_days))
        cand = cand[fresh].sort_values("_dm_utc").drop_duplicates("_row", keep="last")
        for col in ("_rs", "_ps", "_practice_known", "_stamp_kind"):
            f.loc[cand["_row"].to_numpy(), col] = cand[col].to_numpy()
        f.loc[cand["_row"].to_numpy(), "_dm_utc"] = cand["_dm_utc"].to_numpy()
    f["_dm_utc"] = pd.to_datetime(f["_dm_utc"], utc=True, errors="coerce")

    admissible = (observed & f["_dm_utc"].notna().to_numpy()
                  & (f["_dm_utc"] < gameday_utc).to_numpy())
    f["injury_report__listed"] = np.where(observed, admissible.astype(float), np.nan)
    for col, val in (("injury_report__status_out", "out"),
                     ("injury_report__status_doubtful", "doubtful"),
                     ("injury_report__status_questionable", "questionable")):
        f[col] = np.where(observed, (admissible & (f["_rs"] == val).to_numpy()).astype(float),
                          np.nan)
    practice_known = (~admissible) | (f["_practice_known"].to_numpy() == True)  # noqa: E712
    for col, val in (("injury_report__practice_dnp", W2D.CANONICAL_PRACTICE_DNP),
                     ("injury_report__practice_limited", W2D.CANONICAL_PRACTICE_LIMITED)):
        f[col] = np.where(observed & practice_known,
                          (admissible & (f["_ps"] == val).to_numpy()).astype(float), np.nan)
    f["injury_report__observed"] = observed.astype(float)
    f["_inj_dm_utc"] = f["_dm_utc"].where(pd.Series(admissible, index=f.index))
    f["_inj_stamp_kind"] = f["_stamp_kind"].where(pd.Series(admissible, index=f.index))
    f = f.drop(columns=["_dm_utc", "_rs", "_ps", "_practice_known", "_stamp_kind"])
    return W2D.engineer_injury_rate_features_w2d(f)


FAMILY_COLUMNS: tuple[str, ...] = W2.INJURY_FEATURES + W2B.RATE_FEATURES


# ── Controls ────────────────────────────────────────────────────────────────────────────────────
def assert_ladder_inert_before_2025(rungs: dict[str, pd.DataFrame]) -> dict:
    """⭐ THE MECHANICAL CONTROL: the consumption rule can only touch capture-era rows, so every
    rung's feature matrix must be BYTE-IDENTICAL on every pre-2025 row.

    This is a PROOF, not an estimate — it means the 12 legacy folds cannot differ. Fails closed:
    a rung whose legacy rows moved means the consumption rule leaked into the legacy era, and the
    run is INVALID rather than reporting a freshness effect that is really a leak.
    """
    base = rungs[INCUMBENT_RUNG]
    legacy_mask = base["season"].astype(int) < W2D.WAYBACK_FIRST_SEASON
    n_legacy = int(legacy_mask.sum())
    if n_legacy == 0:
        raise ValueError("no pre-2025 rows to compare — the inertness control would be vacuous "
                         "(NF1.7 (a): a control that cannot run is not a pass)")
    compared, diffs = 0, []
    for name, df in rungs.items():
        if name == INCUMBENT_RUNG:
            continue
        if len(df) != len(base):
            diffs.append({"rung": name, "reason": f"row count {len(df)} != {len(base)}"})
            continue
        for col in FAMILY_COLUMNS:
            a = base.loc[legacy_mask, col].to_numpy(dtype=float)
            b = df.loc[legacy_mask, col].to_numpy(dtype=float)
            compared += 1
            if not np.array_equal(a, b, equal_nan=True):
                diffs.append({"rung": name, "column": col,
                              "n_differing": int((~np.isclose(a, b, equal_nan=True)).sum())})
    if compared == 0:
        raise ValueError("the inertness control compared ZERO (rung, column) cells — vacuous")
    return {"state": "PASS" if not diffs else "FAIL", "passes": not diffs,
            "legacy_rows": n_legacy, "cells_compared": compared, "differences": diffs[:20]}


def assert_population_identical(rungs: dict[str, pd.DataFrame]) -> dict:
    """The coverage bound must NOT move with the consumption bound — every rung must score the
    SAME rows. Otherwise the ladder confounds 'fresher features' with 'a different population'."""
    base = rungs[INCUMBENT_RUNG]
    obs_base = pd.to_numeric(base["injury_report__observed"], errors="coerce").fillna(0.0)
    out, mismatches = {}, []
    for name, df in rungs.items():
        obs = pd.to_numeric(df["injury_report__observed"], errors="coerce").fillna(0.0)
        out[name] = {"rows": int(len(df)), "observed_rows": int((obs == 1.0).sum())}
        if len(df) != len(base) or not np.array_equal(obs.to_numpy(), obs_base.to_numpy()):
            mismatches.append(name)
    return {"state": "PASS" if not mismatches else "FAIL", "passes": not mismatches,
            "per_rung": out, "mismatched_rungs": mismatches}


def ladder_activity(rungs: dict[str, pd.DataFrame]) -> dict:
    """The NF-D20 activity count: how many capture-era designations each rung actually keeps."""
    out = {}
    for name, df in rungs.items():
        cap = df[df["season"].astype(int) >= W2D.WAYBACK_FIRST_SEASON]
        listed = pd.to_numeric(cap["injury_report__listed"], errors="coerce")
        by_pos = {str(p): int((pd.to_numeric(g["injury_report__listed"],
                                             errors="coerce") == 1.0).sum())
                  for p, g in cap.groupby("position", sort=True)}
        out[name] = {"listed_capture_era_rows": int((listed == 1.0).sum()), "by_position": by_pos}
    base = out[INCUMBENT_RUNG]["listed_capture_era_rows"]
    for name in out:
        out[name]["share_of_incumbent"] = (
            round(out[name]["listed_capture_era_rows"] / base, 4) if base else None)
    return out


# ── The primary read: a WEEK-CLUSTERED paired delta (rows in a week are not independent) ────────
def clustered_paired_delta(delta: np.ndarray, clusters: np.ndarray) -> dict:
    """Mean paired delta with BOTH the naive and the cluster-robust SE.

    Rows inside a week share one capture schedule, so they are not independent draws; a naive
    per-row SE overstates precision (the NF1.8 rows-not-decimals lesson, one level over). Both are
    reported so the difference is visible rather than asserted.
    """
    d = np.asarray(delta, dtype=float)
    keep = np.isfinite(d)
    d, c = d[keep], np.asarray(clusters)[keep]
    n = len(d)
    if n < 2:
        return {"state": "UNEVALUABLE", "n": int(n),
                "reason": "fewer than 2 finite paired observations"}
    mean = float(d.mean())
    naive_se = float(d.std(ddof=1) / np.sqrt(n))
    groups = [d[c == g] for g in pd.unique(c)]
    k = len(groups)
    if k < 2:
        return {"state": "UNEVALUABLE", "n": int(n), "n_clusters": k,
                "reason": "fewer than 2 clusters — a cluster-robust SE is undefined, and the "
                          "naive SE is not a substitute (NF1.7 (a))"}
    # cluster-robust SE of the mean, with the usual small-cluster correction
    gsum = np.array([g.sum() - len(g) * mean for g in groups], dtype=float)
    var = (gsum ** 2).sum() / (n ** 2) * (k / (k - 1))
    cl_se = float(np.sqrt(var))
    return {
        "state": "OK", "n": int(n), "n_clusters": int(k), "mean_delta": round(mean, 5),
        "naive_se": round(naive_se, 5), "clustered_se": round(cl_se, 5),
        "se_inflation_x": round(cl_se / naive_se, 2) if naive_se > 0 else None,
        "ci95_clustered": [round(mean - 1.96 * cl_se, 5), round(mean + 1.96 * cl_se, 5)],
        "spans_zero": bool((mean - 1.96 * cl_se) <= 0 <= (mean + 1.96 * cl_se)),
    }


def matrix_key_w2e(seasons: tuple[int, int], consumption: float | None) -> str:
    payload = json.dumps({
        "seasons": seasons, "features": list(W2D.FEATURES_W2D),
        "label_version": WP.LABEL_VERSION, "scoring": WP.SCORING_SYSTEM_ID,
        "coverage_max_age_days": W2D.COVERAGE_MAX_AGE_DAYS,
        "consumption": "freshest" if consumption is None else float(consumption),
        "wayback_store": W2D.WAYBACK_STORE_SOURCE, "schema": 1,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
