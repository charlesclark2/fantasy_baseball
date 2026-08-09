"""weekly_projection_w2.py — NF-W2: the availability channel (current-week injury-report state).

THE ONE REGISTERED HYPOTHESIS (see ablation_results/nf_w2_preregistration.md, committed before
the run): the final pre-gameday injury designation + latest practice participation improve the
weekly per-game distribution, primarily through the zero/availability leg of the hurdle mixture.
The NF-W1 champion (`lgbm_hurdle`) is simultaneously the INCUMBENT and the MATCHED FOIL
(NF-D10): every arm here is the identical bundle plus the `injury_report` family, so the paired
per-fold delta IS the attribution.

PIT: the family is verified 2016–2024 via `injuries.date_modified` (the single real as-of stamp
in the free stack). A report row is admissible for a player-week iff its stamp lands STRICTLY
BEFORE the target gameday 00:00 UTC — hours before any kickoff, so game-day inactives cannot
smuggle in. 2025 deleted the stamp upstream (`prospective_shadow`): the whole family is NaN with
`injury_report__observed = 0` — ⛔ never fillna(0); NULL = unmeasured, not healthy (the NF-W0b
snap discipline applied to this family). The 2025 half-season blocks are SHADOW (reported,
never gated): the registered expectation there is a near-tie with the incumbent — a mechanism
that cannot act is a finding, not an omission (NF1.9).

Pure module — no lake IO. The runner is `run_nf_w2_injury_bakeoff.py`.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

# ── Pre-registration constants (the runner reads these and restates nothing) ────────────────────

#: 12 GATED expanding-window half-season blocks — the injury family is ACTIVE + PIT-verifiable on
#: every one (date_modified present 2016–2024). Burn-in history 2016–2018.
TEST_BLOCKS_W2: tuple[tuple[int, int], ...] = (
    (2019, 1), (2019, 2), (2020, 1), (2020, 2), (2021, 1), (2021, 2),
    (2022, 1), (2022, 2), (2023, 1), (2023, 2), (2024, 1), (2024, 2),
)
#: SHADOW blocks — the family is structurally UNMEASURED (upstream deleted date_modified in
#: 2025). Scored + reported, NEVER gated; registered expectation = near-tie with the incumbent.
SHADOW_BLOCKS_W2: tuple[tuple[int, int], ...] = ((2025, 1), (2025, 2))

#: The declared 3-arm family (ONE coherent mechanism family — availability incorporation).
REAL_ARMS_W2: tuple[str, ...] = ("inj_both", "inj_zero_leg", "inj_override")
#: The incumbent NF-W1 champion refit per fold — the matched foil; non-shippable in this field.
FOIL_W2 = "base_hurdle"
ANCHORS_W2: tuple[str, ...] = (
    "nihilist_zero", "pos_marginal", "inj_permuted", "oracle_avail__base", "oracle_avail__inj",
)
#: Which peeking availability oracle floors which arm (NF-D16 — per-FORM ceilings; the two
#: oracles differ only in the conditional leg, so each is same-family/same-sample for its arms).
ORACLE_OF_FORM: dict[str, str] = {
    "base_hurdle": "oracle_avail__base",
    "inj_zero_leg": "oracle_avail__base",
    "inj_override": "oracle_avail__base",
    "inj_both": "oracle_avail__inj",
}

#: The verified era: date_modified is 100% present through 2024, 0% in 2025 (measured).
INJURY_VERIFIED_MAX_SEASON = 2024
#: Statuses whose empirical zero-rate the override arm may substitute (Out∪Doubtful — measured
#: 99.9% zero in scoping). Questionable/no-designation rows are NEVER overridden.
OVERRIDE_STATUSES: tuple[str, ...] = ("out", "doubtful")
#: An override cell thinner than this RAISES — a device that fails to fit must fail loudly,
#: never silently no-op (NF1.7 (a)).
OVERRIDE_MIN_N = 200

INJURY_FEATURES: tuple[str, ...] = (
    "injury_report__listed",
    "injury_report__status_out",
    "injury_report__status_doubtful",
    "injury_report__status_questionable",
    "injury_report__practice_dnp",
    "injury_report__practice_limited",
    "injury_report__observed",
)
FEATURES_W2: tuple[str, ...] = WP.FEATURES + INJURY_FEATURES
USED_FAMILIES_W2: tuple[str, ...] = WP.USED_FAMILIES + ("injury_report",)
#: Still allowed-but-deferred after this slice (recorded, not silent).
UNUSED_ALLOWED_FAMILIES_W2: tuple[str, ...] = (
    "participation_proxies", "pfr_advanced", "ngs_qualifying",
)

_SEED = WP._SEED


# ── Provenance (W2 family list; same three clauses as NF-W1, then the certified guard) ──────────
def assert_feature_provenance_w2(feature_columns: list[str] | tuple[str, ...]) -> None:
    bad_prefix = [c for c in feature_columns
                  if "__" not in c or c.split("__", 1)[0] not in USED_FAMILIES_W2]
    if bad_prefix:
        raise WF.LeakageError(
            f"features with unknown provenance reject the build: {sorted(bad_prefix)} — every "
            f"NF-W2 feature must be named '<family>__<detail>' with family in {USED_FAMILIES_W2}"
        )
    leaky = [c for c in feature_columns
             if any(tok == c or c.endswith(f"_{tok}") or c.startswith(f"{tok}_")
                    for tok in WF.LEAKY_COLUMNS)]
    if leaky:
        raise WF.LeakageError(f"leaky feature columns reject the build: {sorted(leaky)}")
    era = [c for c in feature_columns if any(tok in c for tok in WP.ERA_FORBIDDEN_TOKENS)]
    if era:
        raise WF.LeakageError(
            f"participation-era features reject this slice: {sorted(era)}"
        )
    families = sorted({c.split("__", 1)[0] for c in feature_columns})
    WF.assert_no_leakage(pd.DataFrame(), feature_columns=families, projection_week=0)


# ── Injury feature engineering (latest ADMISSIBLE row per player-week; fail-closed) ─────────────
def _norm(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower()


def engineer_injury_features(feat: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """Attach the injury_report family to the engineered matrix.

    Admissibility (fail-closed): a report row is consumable iff `date_modified` (UTC) lands
    STRICTLY BEFORE the row's target gameday 00:00 UTC. A row failing the bound is excluded and
    the player-week reads as unlisted — PIT-honesty over completeness (measured cost:
    45 / 47,640 player-weeks). 2025+ (no date_modified upstream): the family is NaN with
    `observed = 0` — ⛔ NULL means unmeasured, never healthy.
    """
    inj = injuries.loc[injuries["gsis_id"].notna()].copy()
    for c in ("season", "week"):
        inj[c] = inj[c].astype("int64")
    inj["_dm_utc"] = pd.to_datetime(inj["date_modified"], utc=True, errors="coerce")
    # one row per player-week: latest stamp wins (4 dupes measured in 47,653)
    inj = (inj.sort_values("_dm_utc", na_position="first")
              .drop_duplicates(["season", "week", "gsis_id"], keep="last"))
    inj["_rs"] = _norm(inj["report_status"])
    inj["_ps"] = _norm(inj["practice_status"])
    keep = ["season", "week", "gsis_id", "_dm_utc", "_rs", "_ps"]

    f = feat.merge(inj[keep], on=["season", "week", "gsis_id"], how="left")

    gameday_utc = pd.to_datetime(f["_target_gameday"], errors="coerce").dt.tz_localize("UTC")
    verified = f["season"].astype(int) <= INJURY_VERIFIED_MAX_SEASON
    admissible = verified & f["_dm_utc"].notna() & (f["_dm_utc"] < gameday_utc)

    listed = admissible.astype(float)
    f["injury_report__listed"] = np.where(verified, listed, np.nan)
    for col, val in (
        ("injury_report__status_out", "out"),
        ("injury_report__status_doubtful", "doubtful"),
        ("injury_report__status_questionable", "questionable"),
    ):
        hit = (admissible & (f["_rs"] == val)).astype(float)
        f[col] = np.where(verified, hit, np.nan)
    for col, val in (
        ("injury_report__practice_dnp", "did not participate in practice"),
        ("injury_report__practice_limited", "limited participation in practice"),
    ):
        hit = (admissible & (f["_ps"] == val)).astype(float)
        f[col] = np.where(verified, hit, np.nan)
    f["injury_report__observed"] = verified.astype(float)

    # the consumed stamp — feeds the PIT guard records; NaT where nothing was consumed
    f["_inj_dm_utc"] = f["_dm_utc"].where(admissible)
    return f.drop(columns=["_dm_utc", "_rs", "_ps"])


# ── The PIT gate (per-GAME as-of instants; injury source records carry date_modified) ───────────
def injury_guard_records(rows: pd.DataFrame) -> list[dict]:
    """One extra §13 record per CONSUMED injury-report row — source_timestamp = date_modified."""
    records: list[dict] = []
    sub = rows.loc[rows["_inj_dm_utc"].notna()]
    for season, week, gsis, dm in zip(
        sub["season"].to_numpy(), sub["week"].to_numpy(),
        sub["gsis_id"].to_numpy(), sub["_inj_dm_utc"],
    ):
        payload = f"{season}|{week}|{gsis}|inj"
        stamp = pd.Timestamp(dm).isoformat()
        records.append({
            "capture_source": "nflverse_injuries",
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


def run_pit_gate_w2(feat: pd.DataFrame, *, guard=LG.assert_point_in_time) -> dict:
    """FAIL-CLOSED PIT gate at PER-GAME granularity.

    NF-W1 grouped by (season, week) with the week-min gameday as the projection instant. NF-W2
    refines to (season, week, gameday): the projection instant for a row is ITS OWN game's
    gameday 00:00 UTC — serving reality is a re-projection before each game's kickoff, and the
    injury family's admissibility bound is exactly this instant. Prior-week records only gain
    slack; a game-group whose records the guard rejects is DROPPED and counted.
    """
    if WP.PIT_STORE_SOURCES_CONSUMED:
        raise NotImplementedError(
            "PIT_STORE_SOURCES_CONSUMED is non-empty — build a real store_index first (NF1.7 (a))."
        )
    modeled = feat[feat["label"] != WF.LABEL_BYE]
    dropped: list[dict] = []
    kept_idx: list[np.ndarray] = []
    groups_checked = records_checked = injury_records_checked = 0
    for (season, week, gameday), rows in modeled.groupby(
        ["season", "week", "_target_gameday"], sort=True
    ):
        projection_ts = pd.Timestamp(gameday).strftime("%Y-%m-%dT00:00:00+00:00")
        records = WP.pit_guard_records(rows) + injury_guard_records(rows)
        n_inj = sum(1 for r in records if r["capture_source"] == "nflverse_injuries")
        groups_checked += 1
        records_checked += len(records)
        injury_records_checked += n_inj
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
        "groups_dropped": dropped,
        "rows_dropped": int(sum(d["n_rows"] for d in dropped)),
        "kept_index": kept,
    }


def assemble_matrix_w2(
    frame: pd.DataFrame,
    stats: pd.DataFrame,
    snaps: pd.DataFrame,
    schedule: pd.DataFrame,
    injuries: pd.DataFrame,
    *,
    guard=LG.assert_point_in_time,
) -> tuple[pd.DataFrame, dict]:
    """THE W2 assembly boundary: NF-W1 engineering → injury family → provenance → per-game PIT
    gate. The only sanctioned path to a W2 fit/score matrix."""
    feat = WP.engineer_features(frame, stats, snaps, schedule)
    feat = engineer_injury_features(feat, injuries)
    assert_feature_provenance_w2(FEATURES_W2)
    audit = run_pit_gate_w2(feat, guard=guard)
    modeled = feat.loc[audit["kept_index"]].reset_index(drop=True)
    audit = {k: v for k, v in audit.items() if k != "kept_index"}
    return modeled, audit


# ── Folds (parameterized blocks; same purge/expanding-window semantics as NF-W1) ────────────────
def build_folds_w2(feat: pd.DataFrame,
                   blocks: tuple[tuple[int, int], ...] = TEST_BLOCKS_W2) -> list[WP.Fold]:
    folds: list[WP.Fold] = []
    for season, half in blocks:
        in_half = (feat["season"] == season) & (
            feat["week"].isin(WP.H1_WEEKS) if half == 1 else ~feat["week"].isin(WP.H1_WEEKS)
        )
        test_idx = feat.index[in_half].to_numpy()
        if not len(test_idx):
            continue
        start_gw = int(feat.loc[test_idx, "gw"].min())
        train_idx = feat.index[feat["gw"] <= start_gw - 1 - WP.PURGE_WEEKS].to_numpy()
        folds.append(WP.Fold(f"{season}H{half}", train_idx, test_idx, season, half))
    return folds


# ── The hurdle in parts (so legs can be shared/overridden without refitting) ────────────────────
def hurdle_parts(train: pd.DataFrame, test: pd.DataFrame,
                 clf_features: list[str], cond_features: list[str],
                 *, y_train_override: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """P(zero) + conditional 39-level bank, mechanically identical to NF-W1's
    `fit_lgbm_hurdle` when both feature lists equal WP.FEATURES (guard-tested equal)."""
    import lightgbm as lgb

    def _X(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
        X = df[list(cols)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        return np.column_stack([X, WP._pos_codes(df)])

    y = (train["fantasy_points"].to_numpy(dtype=float)
         if y_train_override is None else np.asarray(y_train_override, dtype=float))
    Xtr_c, Xte_c = _X(train, clf_features), _X(test, clf_features)
    is_zero = (y == 0.0).astype(int)
    clf = lgb.LGBMClassifier(
        n_estimators=250, learning_rate=0.06, num_leaves=63, min_child_samples=40,
        subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
        random_state=_SEED, verbose=-1, n_jobs=-1,
    )
    clf.fit(Xtr_c, is_zero)
    p0 = clf.predict_proba(Xte_c)[:, 1]

    Xtr_q, Xte_q = _X(train, cond_features), _X(test, cond_features)
    nz = y != 0.0
    knots = np.empty((len(test), len(WP.FIT_LEVELS)))
    for j, alpha in enumerate(WP.FIT_LEVELS):
        m = WP._lgbm({"objective": "quantile", "alpha": alpha})
        m.fit(Xtr_q[nz], y[nz])
        knots[:, j] = m.predict(Xte_q)
    cond = WP.interp_to_levels(np.array(WP.FIT_LEVELS), knots)
    return p0, cond


def mix_parts(p0: np.ndarray, cond: np.ndarray) -> np.ndarray:
    out = np.empty((len(p0), len(WP.Q_LEVELS)))
    for i in range(len(p0)):
        out[i] = WP._mixture_quantiles(float(p0[i]), np.sort(cond[i]))
    return out


# ── The override arm's device ───────────────────────────────────────────────────────────────────
def override_p0(p0: np.ndarray, train: pd.DataFrame, test: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Replace p0 on test rows carrying an admissible Out∪Doubtful designation with the
    train-fold pooled empirical P(zero | Out∪Doubtful) over observed listed rows. RAISES on a
    thin cell — a device that fails to fit must fail loudly (NF1.7 (a))."""
    tr_sel = (
        (pd.to_numeric(train["injury_report__observed"], errors="coerce") == 1.0)
        & ((pd.to_numeric(train["injury_report__status_out"], errors="coerce") == 1.0)
           | (pd.to_numeric(train["injury_report__status_doubtful"], errors="coerce") == 1.0))
    )
    n = int(tr_sel.sum())
    if n < OVERRIDE_MIN_N:
        raise ValueError(
            f"override cell too thin: {n} < {OVERRIDE_MIN_N} train rows with Out∪Doubtful — "
            f"refusing to fit silently (NF1.7 (a))"
        )
    p_emp = float((train.loc[tr_sel, "fantasy_points"].to_numpy(dtype=float) == 0.0).mean())
    te_sel = (
        (pd.to_numeric(test["injury_report__status_out"], errors="coerce") == 1.0)
        | (pd.to_numeric(test["injury_report__status_doubtful"], errors="coerce") == 1.0)
    ).to_numpy()
    out = np.asarray(p0, dtype=float).copy()
    out[te_sel] = p_emp
    return out, {"p_emp": round(p_emp, 4), "n_train_cell": n, "n_test_overridden": int(te_sel.sum())}


# ── The content-not-capacity permutation anchor ─────────────────────────────────────────────────
def permute_injury_within_pos_week(df: pd.DataFrame, seed: int = _SEED) -> pd.DataFrame:
    """The injury family's VALUES permuted jointly (rows keep a coherent family vector) within
    (position × global week), in whichever frame is passed (applied to train AND test). Destroys
    the player-level linkage while preserving every week×position marginal rate."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    cols = [c for c in INJURY_FEATURES]
    vals = out[cols].to_numpy(dtype=float, copy=True)
    keys = out["position"].astype(str) + "|" + out["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(out)), index=keys).groupby(level=0):
        pos = idx.to_numpy()
        if len(pos) > 1:
            vals[pos] = vals[rng.permutation(pos)]
    out[cols] = vals
    return out


# ── Per-fold activity (the NF-D20 discipline: report where the mechanism CAN act) ───────────────
def fold_activity(test: pd.DataFrame) -> dict:
    listed = pd.to_numeric(test["injury_report__listed"], errors="coerce")
    outdbt = (
        (pd.to_numeric(test["injury_report__status_out"], errors="coerce") == 1.0)
        | (pd.to_numeric(test["injury_report__status_doubtful"], errors="coerce") == 1.0)
    )
    return {
        "n_test": int(len(test)),
        "listed_share": round(float(np.nanmean(listed.to_numpy(dtype=float))), 4)
        if listed.notna().any() else None,
        "out_doubtful_share": round(float(outdbt.mean()), 4),
        "observed_share": round(float(
            pd.to_numeric(test["injury_report__observed"], errors="coerce").fillna(0.0).mean()), 4),
    }


def matrix_key_w2(seasons: tuple[int, int]) -> str:
    payload = json.dumps({
        "seasons": seasons, "features": list(FEATURES_W2), "label_version": WP.LABEL_VERSION,
        "scoring": WP.SCORING_SYSTEM_ID, "positions": list(WP.POSITIONS),
        "injury_verified_max_season": INJURY_VERIFIED_MAX_SEASON, "schema": 1,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
