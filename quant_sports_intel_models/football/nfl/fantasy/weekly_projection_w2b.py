"""weekly_projection_w2b.py — NF-W2b: re-register the injury family against a marginal-rate foil.

THE ONE REGISTERED HYPOTHESIS (see ablation_results/nf_w2b_preregistration.md, committed before
the run): NF-W2 proved the injury-report availability family real at every position but refused
QB/RB/WR on ONE clause — the permuted arm carries a small significant week×position
marginal-listing-rate channel (3–9% of the lift), and the registration demanded the attribution
be entirely player-level. NF-W2b absorbs that channel INTO the incumbent: pre-registered
`injury_rate` features (week×position GROUP rates, no player linkage) join the base foil
(`base_rate`), so the matched pair (arm − base_rate) isolates PURE player-level injury content
and the calibrated permutation clause is satisfiable by construction if the effect is truly
player-level. Player content was 91–97% of the NF-W2 lift → one registration away, not one
discovery away.

PIT: the rate for a row aggregates ONLY report rows stamped strictly before THAT ROW'S OWN
target gameday 00:00 UTC (a whole-week rate would leak Friday/Saturday stamps into Thursday
games). The aggregation's consumed-stamp bound flows through the per-game PIT gate as one extra
record per row carrying the MAX consumed stamp — a `<`→`≤` or wrong-instant bug propagates into
the record and the gate rejects. 2025 is prospective_shadow for BOTH families: all-NaN +
observed=0 — ⛔ never fillna(0).

Pure module — no lake IO. The runner is `run_nf_w2b_injury_rate_bakeoff.py`.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

# ── Pre-registration constants (the runner reads these and restates nothing) ────────────────────

#: Folds inherited unchanged from NF-W2: 12 GATED blocks (family ACTIVE + PIT-verifiable on
#: every one) + 2 SHADOW blocks (2025 — both families structurally unmeasured; never gated).
TEST_BLOCKS_W2B = W2.TEST_BLOCKS_W2
SHADOW_BLOCKS_W2B = W2.SHADOW_BLOCKS_W2

#: The declared 3-arm family — the SAME mechanism family as NF-W2 (availability incorporation),
#: now over the rate-augmented base. This is the DSR trial field; anchors/degenerates never
#: enter trial_srs, so the cross-trial dispersion V is degenerate-excluded BY CONSTRUCTION
#: (the MH2.5 DSR-CONV-compatible convention).
REAL_ARMS_W2B: tuple[str, ...] = ("inj_both", "inj_zero_leg", "inj_override")
#: The matched foil: NF-W1 champion spec + the injury_rate family, refit per fold.
#: Non-shippable in this field; arm − base_rate IS the pure player-level attribution (NF-D10).
FOIL_W2B = "base_rate"
#: The production incumbent (NF-W2's `base_hurdle` — the NF-W1 champion EXACT spec), kept as a
#: diagnostic anchor: the winner must ALSO beat it (the deployment bar), and
#: base_noRate − base_rate prices the marginal channel directly (reported, never gated).
PROD_INCUMBENT = "base_noRate"
ANCHORS_W2B: tuple[str, ...] = (
    "nihilist_zero", "pos_marginal", "inj_permuted", "base_noRate",
    "oracle_avail__base", "oracle_avail__inj",
)
#: NF-D16 per-FORM peeking floors — the two oracles differ only in the conditional leg.
ORACLE_OF_FORM_W2B: dict[str, str] = {
    "base_rate": "oracle_avail__base",
    "inj_zero_leg": "oracle_avail__base",
    "inj_override": "oracle_avail__base",
    "inj_both": "oracle_avail__inj",
}

#: The NEW family: week×position GROUP rates of the injury_report family — NO player linkage
#: (mechanically: constant within (season, week, position, gameday); guard-tested).
RATE_FEATURES: tuple[str, ...] = (
    "injury_rate__listed",
    "injury_rate__status_out",
    "injury_rate__status_doubtful",
    "injury_rate__status_questionable",
    "injury_rate__practice_dnp",
    "injury_rate__practice_limited",
    "injury_rate__observed",
)
#: rate column → the player-level injury_report column it aggregates.
RATE_OF_PLAYER_COL: dict[str, str] = {
    "injury_rate__listed": "injury_report__listed",
    "injury_rate__status_out": "injury_report__status_out",
    "injury_rate__status_doubtful": "injury_report__status_doubtful",
    "injury_rate__status_questionable": "injury_report__status_questionable",
    "injury_rate__practice_dnp": "injury_report__practice_dnp",
    "injury_rate__practice_limited": "injury_report__practice_limited",
}

#: The foil's bundle: NF-W1 champion features + the rate family — ⛔ NO player-level injury
#: columns (attribution integrity; guard-tested disjoint).
FEATURES_BASE_RATE: tuple[str, ...] = WP.FEATURES + RATE_FEATURES
#: The arms' full bundle: foil bundle + the player-level injury family.
FEATURES_W2B: tuple[str, ...] = WP.FEATURES + RATE_FEATURES + W2.INJURY_FEATURES
USED_FAMILIES_W2B: tuple[str, ...] = W2.USED_FAMILIES_W2 + ("injury_rate",)

_SEED = WP._SEED


# ── Provenance (W2b family list; same clauses as NF-W2, then the certified guard) ───────────────
def assert_feature_provenance_w2b(feature_columns: list[str] | tuple[str, ...]) -> None:
    bad_prefix = [c for c in feature_columns
                  if "__" not in c or c.split("__", 1)[0] not in USED_FAMILIES_W2B]
    if bad_prefix:
        raise WF.LeakageError(
            f"features with unknown provenance reject the build: {sorted(bad_prefix)} — every "
            f"NF-W2b feature must be named '<family>__<detail>' with family in {USED_FAMILIES_W2B}"
        )
    leaky = [c for c in feature_columns
             if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_")
                    for tok in WF.LEAKY_COLUMNS)]
    if leaky:
        raise WF.LeakageError(f"leaky feature columns reject the build: {sorted(leaky)}")
    era = [c for c in feature_columns if any(tok in c for tok in WP.ERA_FORBIDDEN_TOKENS)]
    if era:
        raise WF.LeakageError(f"participation-era features reject this slice: {sorted(era)}")
    families = sorted({c.split("__", 1)[0] for c in feature_columns})
    WF.assert_no_leakage(pd.DataFrame(), feature_columns=families, projection_week=0)


# ── The injury_rate family (group rates as of each row's OWN gameday instant) ───────────────────
def engineer_injury_rate_features(feat: pd.DataFrame) -> pd.DataFrame:
    """Attach the injury_rate family to a W2-engineered matrix.

    For a row with (season, week, position) and target-gameday instant g (00:00 UTC), each rate
    is the share of ALL modeled rows of that (season, week, position) whose CONSUMED report
    (admissible at their own instant → `_inj_dm_utc` non-null) is stamped STRICTLY BEFORE g and
    carries the respective indicator. Group-level by construction (constant within
    season×week×position×gameday) — no player identity enters. Early-week games see fewer
    stamps: fail-closed honesty, and exactly what is computable at serving time.

    `_rate_max_stamp_utc` records the max consumed stamp per row and feeds the PIT gate — a
    `<`→`≤` or wrong-instant bug here lands in the guard record and the gate REJECTS.
    2025+ (unverified era): rates are NaN with `injury_rate__observed = 0` — ⛔ never fillna(0).
    """
    f = feat.copy()
    verified = f["season"].astype(int) <= W2.INJURY_VERIFIED_MAX_SEASON
    rate_cols = [c for c in RATE_FEATURES if c != "injury_rate__observed"]
    for c in rate_cols:
        f[c] = np.nan
    f["_rate_max_stamp_utc"] = pd.Series(pd.NaT, index=f.index, dtype="datetime64[ns, UTC]")

    modeled = (f["label"] != WF.LABEL_BYE) & verified & f["_target_gameday"].notna()
    sub = f.loc[modeled]
    for (_, _, _), grp in sub.groupby(["season", "week", "position"], sort=False):
        n = len(grp)
        stamps = pd.to_datetime(grp["_inj_dm_utc"], utc=True, errors="coerce")
        instants = pd.to_datetime(grp["_target_gameday"], errors="coerce").dt.tz_localize("UTC")
        indicators = {
            rc: (pd.to_numeric(grp[pc], errors="coerce") == 1.0).to_numpy()
            for rc, pc in RATE_OF_PLAYER_COL.items()
        }
        for g in instants.dropna().unique():
            counted = (stamps.notna() & (stamps < g)).to_numpy()
            rows_idx = grp.index[(instants == g).to_numpy()]
            for rc in rate_cols:
                f.loc[rows_idx, rc] = float((counted & indicators[rc]).sum()) / n
            if counted.any():
                f.loc[rows_idx, "_rate_max_stamp_utc"] = stamps.to_numpy()[counted].max()
    f["injury_rate__observed"] = verified.astype(float)
    return f


# ── PIT gate: the rate aggregation's consumed-stamp bound gets its own guard records ────────────
def rate_guard_records(rows: pd.DataFrame) -> list[dict]:
    """One §13 record per row whose rate features consumed ≥1 report stamp — source_timestamp =
    the MAX consumed stamp (the sufficient statistic for the strictly-before bound)."""
    records: list[dict] = []
    sub = rows.loc[rows["_rate_max_stamp_utc"].notna()]
    for season, week, gsis, mx in zip(
        sub["season"].to_numpy(), sub["week"].to_numpy(),
        sub["gsis_id"].to_numpy(), sub["_rate_max_stamp_utc"],
    ):
        payload = f"{season}|{week}|{gsis}|injrate"
        stamp = pd.Timestamp(mx).isoformat()
        records.append({
            "capture_source": "nflverse_injuries_rate",
            "capture_id": payload,
            "subject_key": payload,
            "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "record_tier": "lake_feature",
            "feature_timestamp": stamp,
            "source_timestamp": stamp,
            "capture_timestamp": stamp,
            "vendor_release_timestamp": stamp,
            "ingestion_timestamp": stamp,
            "is_rolling_window": False,
        })
    return records


def run_pit_gate_w2b(feat: pd.DataFrame, *, guard=LG.assert_point_in_time) -> dict:
    """FAIL-CLOSED PIT gate at PER-GAME granularity — NF-W2's gate plus the rate records.

    Three record families per (season, week, gameday) group: the NF-W1 window records, the
    per-consumed-report injury records, and the per-row rate max-stamp records. A group any
    record of which the guard rejects is DROPPED and counted.
    """
    if WP.PIT_STORE_SOURCES_CONSUMED:
        raise NotImplementedError(
            "PIT_STORE_SOURCES_CONSUMED is non-empty — build a real store_index first (NF1.7 (a))."
        )
    modeled = feat[feat["label"] != WF.LABEL_BYE]
    dropped: list[dict] = []
    kept_idx: list[np.ndarray] = []
    groups_checked = records_checked = injury_records_checked = rate_records_checked = 0
    for (season, week, gameday), rows in modeled.groupby(
        ["season", "week", "_target_gameday"], sort=True
    ):
        projection_ts = pd.Timestamp(gameday).strftime("%Y-%m-%dT00:00:00+00:00")
        records = (WP.pit_guard_records(rows) + W2.injury_guard_records(rows)
                   + rate_guard_records(rows))
        groups_checked += 1
        records_checked += len(records)
        injury_records_checked += sum(
            1 for r in records if r["capture_source"] == "nflverse_injuries")
        rate_records_checked += sum(
            1 for r in records if r["capture_source"] == "nflverse_injuries_rate")
        try:
            report = guard(records, projection_ts, store_index={})
            if getattr(report, "checked", len(records)) == 0:
                raise LG.LeakageRejection([LG.LeakageFinding(
                    LG.Rejection.UNEVALUABLE, "guard checked zero records", None)])
            kept_idx.append(rows.index.to_numpy())
        except LG.LeakageRejection as exc:
            dropped.append({
                "season": int(season), "week": int(week), "gameday": str(gameday)[:10],
                "n_rows": int(len(rows)),
                "reasons": sorted({fnd.reason.name for fnd in exc.findings}),
            })
    kept = np.concatenate(kept_idx) if kept_idx else np.array([], dtype=int)
    return {
        "game_groups_checked": groups_checked,
        "records_checked": records_checked,
        "injury_records_checked": injury_records_checked,
        "rate_records_checked": rate_records_checked,
        "groups_dropped": dropped,
        "rows_dropped": int(sum(d["n_rows"] for d in dropped)),
        "kept_index": kept,
    }


def assemble_matrix_w2b(
    frame: pd.DataFrame,
    stats: pd.DataFrame,
    snaps: pd.DataFrame,
    schedule: pd.DataFrame,
    injuries: pd.DataFrame,
    *,
    guard=LG.assert_point_in_time,
) -> tuple[pd.DataFrame, dict]:
    """THE W2b assembly boundary: NF-W1 engineering → injury family → rate family → provenance →
    per-game PIT gate (all three record families). The only sanctioned path to a W2b matrix."""
    feat = WP.engineer_features(frame, stats, snaps, schedule)
    feat = W2.engineer_injury_features(feat, injuries)
    feat = engineer_injury_rate_features(feat)
    assert_feature_provenance_w2b(FEATURES_W2B)
    audit = run_pit_gate_w2b(feat, guard=guard)
    modeled = feat.loc[audit["kept_index"]].reset_index(drop=True)
    audit = {k: v for k, v in audit.items() if k != "kept_index"}
    return modeled, audit


def matrix_key_w2b(seasons: tuple[int, int]) -> str:
    payload = json.dumps({
        "seasons": seasons, "features": list(FEATURES_W2B), "label_version": WP.LABEL_VERSION,
        "scoring": WP.SCORING_SYSTEM_ID, "positions": list(WP.POSITIONS),
        "injury_verified_max_season": W2.INJURY_VERIFIED_MAX_SEASON, "schema": 1,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── The validated ship specs (MH2.1 (b): serve the object that was validated) ───────────────────
#: PRE-flip: the production-incumbent lineage — the NF-W1 champion spec (base features, no
#: injury families). NF-W2's TE `inj_zero_leg` (non-rate bundle) was validated but never
#: staged, so the deployed baseline every position flips FROM is the NF-W1 champion.
PRE_FLIP_SPEC: dict[str, str] = {p: "base_noRate" for p in WP.POSITIONS}
#: POST-flip: the per-position WINNERS this bake-off certified — pinned to the committed
#: artifact by guard test (`test_post_flip_spec_matches_the_validated_artifact`), so the spec
#: constant cannot drift from what the gates actually validated.
POST_FLIP_SPEC: dict[str, str] = {
    "QB": "inj_zero_leg",
    "RB": "inj_both",
    "WR": "inj_both",
    "TE": "inj_zero_leg",
}


# ── Gate composition + the hand null-classifier (the NF-D18/MH2.7 classify_null gap) ────────────
#: Checks that are ANCHOR/REGISTRATION clauses (a refusal here with all statistical gates green
#: is a CONSTRAINT_REFUSED-family null — more data makes it fail HARDER, never better).
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
)
STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "beats_production", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok",
    "coverage_floor_ok",
)


def position_gate_w2b(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "beats_production": bool(sel["beats_production"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < WP.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= WP.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["nihilist_loses"]
                                 and sel["anchors"]["pos_marginal_loses"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        "oracle_floors_respected": bool(sel["anchors"]["no_arm_beats_own_oracle"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}


def hand_classify_refusal(checks: dict) -> dict | None:
    """The hand-check `classify_null` cannot do (NF-D18/MH2.7, hit twice): when every
    STATISTICAL gate passes and the null rests ONLY on anchor/registration clauses, the state
    is the CONSTRAINT_REFUSED family — the remedy is a different registration/mechanism, more
    data makes the clause fail HARDER, and ⛔ no sample-size re-test trigger may be published.
    Returns None when the null has a statistical component (then classify_null speaks)."""
    stat_fail = [c for c in STATISTICAL_CHECKS if not checks.get(c, True)]
    anchor_fail = [c for c in ANCHOR_CHECKS if not checks.get(c, True)]
    if stat_fail or not anchor_fail:
        return None
    return {
        "state": "CONSTRAINT_REFUSED",
        "reason": ("hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical "
                   f"gate passed and the null rests entirely on anchor/registration clauses "
                   f"{anchor_fail}. More data cannot change this verdict — the remedy is a "
                   f"different registration or mechanism, never more seasons."),
        "retest_trigger": None,
        "failing_anchor_checks": anchor_fail,
    }
