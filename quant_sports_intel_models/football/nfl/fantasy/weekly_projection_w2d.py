"""weekly_projection_w2d.py — NF-W2d: re-gate the injury family with 2025 in the fold set.

THE ONE REGISTERED HYPOTHESIS (see ablation_results/nf_w2d_preregistration.md, committed before
the run): the certified NF-W2b injury-availability family still beats its matched foil
`base_rate` when the fold set is extended to include 2025 — an era whose injury signal is
composed of as-of-that-instant third-party CAPTURE observations (NF-W2c + NF-W2c-CBS's landed
`nfl/pit/wayback_injuries` store) rather than the vendor's own `date_modified` stamp, i.e. an era
with the same signal character the family will face at serve time.

⛔ ONLY THE FOLD SET CHANGES. Arms, foil, anchors, per-form oracles, features, metric, thresholds,
purge, label, scoring and seed are inherited BY IMPORT from `weekly_projection_w2b` /
`weekly_projection_w2` / `weekly_projection` — a re-typed constant is a constant that can drift.
The 12 legacy folds must reproduce NF-W2b's recorded per-fold CRPS to 1e-9 (`REPRO_TOLERANCE`);
a run that fails that control is INVALID, not a finding.

THE 2025 SOURCE. Every 2025 row is a Wayback capture with a third-party-attested instant.
  · the as-of instant is the CAPTURE instant; `source_timestamp` stays a DECLARED ABSENCE (these
    pages publish no per-row vendor as-of) — ⛔ never laundered into the vendor slot;
  · admissibility is re-derived here fail-closed (capture strictly before the row's OWN target
    gameday 00:00 UTC), never trusted from the landed row;
  · a capture establishes coverage only within COVERAGE_MAX_AGE_DAYS = 7 (one NFL game week —
    registered on sport structure, NOT tuned: CBS mixes a next-week preview into the current
    week's table, so an unbounded rule lets a September capture "cover" a December game);
  · `observed` is PER-ROW, not an era constant. observed=0 ⇒ the whole family is NaN.
    ⛔ NO fillna(0) — an uncovered player-week is unmeasured, never healthy;
  · a COVERED row absent from every admissible capture reads NOT LISTED (each capture is a
    league-wide report snapshot, so absence from a readable report is an observation);
  · a LISTED row whose consumed capture carries NO practice line gets NaN practice columns, never
    0 — "no practice information" is not "practiced fully" (MH2.1 (c) per-column absence; ESPN
    carries no practice line at all).

Pure module — no lake IO. The runner is `run_nf_w2d_2025_regate.py`.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────

#: THE ONE CHANGE: 2025H1/2025H2 leave SHADOW and join the gated set. 14 gated blocks.
TEST_BLOCKS_W2D: tuple[tuple[int, int], ...] = W2B.TEST_BLOCKS_W2B + W2B.SHADOW_BLOCKS_W2B
#: Nothing is shadow any more — the era the shadow blocks existed to flag is now measurable.
SHADOW_BLOCKS_W2D: tuple[tuple[int, int], ...] = ()
#: The 12 NF-W2b blocks, kept for the REPRODUCTION CONTROL (they train only on ≤2024 data, so
#: nothing they touch can depend on the 2025 source).
LEGACY_BLOCKS_W2D: tuple[tuple[int, int], ...] = W2B.TEST_BLOCKS_W2B
#: The seasons the legacy control covers — a fold outside this set is a NEW fold.
LEGACY_SEASONS: frozenset[int] = frozenset(s for s, _ in LEGACY_BLOCKS_W2D)
#: A legacy fold whose CRPS moves by more than this against the NF-W2b artifact INVALIDATES the
#: run (the harness was perturbed by the 2025 plumbing) — it is never reported as an era effect.
REPRO_TOLERANCE = 1e-9

#: Field inherited VERBATIM from NF-W2b (imported, never re-typed).
REAL_ARMS_W2D = W2B.REAL_ARMS_W2B
FOIL_W2D = W2B.FOIL_W2B
PROD_INCUMBENT_W2D = W2B.PROD_INCUMBENT
ANCHORS_W2D = W2B.ANCHORS_W2B
ORACLE_OF_FORM_W2D = W2B.ORACLE_OF_FORM_W2B
FEATURES_W2D = W2B.FEATURES_W2B
FEATURES_BASE_RATE_W2D = W2B.FEATURES_BASE_RATE
RATE_FEATURES_W2D = W2B.RATE_FEATURES
USED_FAMILIES_W2D = W2B.USED_FAMILIES_W2B

#: The immutable NF-W0a store holding the 2025 captures (NF-W2c + NF-W2c-CBS).
WAYBACK_STORE_SOURCE = "wayback_injuries"
#: The first season served by the capture store rather than by nflverse `date_modified`.
WAYBACK_FIRST_SEASON = W2.INJURY_VERIFIED_MAX_SEASON + 1
#: A capture covers a row only within ONE NFL GAME WEEK of that row's own gameday instant.
#: Registered on sport structure (the report is a weekly practice-cycle document; CBS mixes a
#: next-week preview into the current week's table) — ⛔ NOT tuned, and nothing selects on the
#: diagnostic variants below.
COVERAGE_MAX_AGE_DAYS = 7.0
#: Reported beside the primary bound as pure DIAGNOSTICS — the gate never reads them.
DIAGNOSTIC_COVERAGE_BOUNDS: tuple[float, ...] = (3.0, float("inf"))

#: Stamp kinds. The provenance SHAPE of a guard record depends on which one produced the row.
STAMP_NFLVERSE = "nflverse"
STAMP_WAYBACK = "wayback"
#: The declared reason a wayback record carries no `source_timestamp`. `check_provenance_present`
#: REJECTS a null source_timestamp without one, so this is load-bearing, not documentation.
WAYBACK_SOURCE_TS_ABSENT_REASON = (
    "wayback page publishes no per-row vendor as-of; the archive capture instant is the as-of "
    "bound"
)

#: The CANONICAL nflverse practice vocabulary. The wayback parsers emit their own short forms;
#: mapping them onto THESE strings is what makes the 2025 rows readable by the inherited
#: `engineer_injury_features` logic. ⭐ NF-C0e: the guard asserts these canonical keys, never the
#: adapter's own output — a test that reads a value back under the key the code wrote can never
#: catch a wrong key.
CANONICAL_PRACTICE_DNP = "did not participate in practice"
CANONICAL_PRACTICE_LIMITED = "limited participation in practice"
CANONICAL_PRACTICE_FULL = "full participation in practice"
WAYBACK_PRACTICE_MAP: dict[str, str] = {
    "dnp": CANONICAL_PRACTICE_DNP,
    "limited": CANONICAL_PRACTICE_LIMITED,
    "full": CANONICAL_PRACTICE_FULL,
}
#: The canonical designation vocabulary is shared by both sources verbatim (measured: the store
#: emits exactly {out, doubtful, questionable, NULL}).
CANONICAL_REPORT_STATUSES: tuple[str, ...] = ("out", "doubtful", "questionable")


# ── The wayback source, mapped onto the nflverse injury contract ────────────────────────────────
def normalize_wayback_practice(values: pd.Series) -> pd.Series:
    """Map the wayback practice vocabulary onto the CANONICAL nflverse strings.

    An unrecognised token becomes NaN — ⛔ never silently passed through as if it were canonical
    (the NF-C0e wrong-key class: an unrecognised key that flows on reads as "captured" and
    produces an all-zero feature with no error).
    """
    s = values.astype("string").str.strip().str.lower()
    return s.map(WAYBACK_PRACTICE_MAP).astype("object").where(lambda x: x.notna(), other=np.nan)


def wayback_injury_rows(store: pd.DataFrame) -> pd.DataFrame:
    """Project the landed capture store onto the nflverse `injuries` contract.

    The capture instant becomes `date_modified` (the as-of bound the family consumes); the
    stamp KIND rides along so the PIT guard can emit the right provenance shape — a wayback
    record must declare its absent `source_timestamp`, never borrow the capture instant.
    """
    required = {"season", "week", "gsis_id", "report_status", "practice_status",
                "capture_timestamp"}
    missing = required - set(store.columns)
    if missing:
        raise ValueError(
            f"the wayback capture store is missing {sorted(missing)} — refusing to build a 2025 "
            f"injury family from an unrecognised schema (NF1.7 (a): a source that cannot be read "
            f"must fail loudly, never yield an empty family that scores as a clean null)"
        )
    out = pd.DataFrame({
        "season": store["season"].astype("int64"),
        "week": store["week"].astype("int64"),
        "gsis_id": store["gsis_id"].astype(str),
        "report_status": store["report_status"].astype("string").str.strip().str.lower(),
        "practice_status": normalize_wayback_practice(store["practice_status"]),
        "date_modified": pd.to_datetime(store["capture_timestamp"], utc=True, errors="coerce"),
    })
    out["_stamp_kind"] = STAMP_WAYBACK
    bad = out["date_modified"].isna()
    if bool(bad.any()):
        raise ValueError(
            f"{int(bad.sum())} capture rows carry an unparseable capture_timestamp — the as-of "
            f"instant IS the admissibility bound, so an unparseable stamp must reject the build"
        )
    return out


def combine_injury_sources(nflverse: pd.DataFrame, wayback: pd.DataFrame) -> pd.DataFrame:
    """nflverse rows for the `date_modified` era, capture rows for the era that deleted it.

    ⭐ The two filters are DELIBERATELY asymmetric, and the asymmetry is what keeps the overlap
    check reachable (a check both sides silently filter into satisfaction is a vacuous guard —
    NF1.7 (a)/INC-38, and the first cut of this function had exactly that defect):

      · nflverse rows from ≥2025 are EXCLUDED, not refused — they genuinely exist (measured
        5,783 in 2025) and are genuinely inadmissible, because upstream deleted `date_modified`
        and a row with no as-of stamp cannot be bounded. That exclusion is intentional and
        counted, never silent;
      · a capture row from ≤2024 is REFUSED. There is no legitimate reason for one, and letting
        it through would put two different as-of semantics on a single player-week.
    """
    nf = nflverse.loc[nflverse["gsis_id"].notna()].copy()
    for c in ("season", "week"):
        nf[c] = nf[c].astype("int64")
    nf["date_modified"] = pd.to_datetime(nf["date_modified"], utc=True, errors="coerce")
    stampless = nf["season"] > W2.INJURY_VERIFIED_MAX_SEASON
    nf = nf[~stampless]
    nf["_stamp_kind"] = STAMP_NFLVERSE

    early = wayback.loc[wayback["season"] < WAYBACK_FIRST_SEASON, "season"]
    if len(early):
        raise ValueError(
            f"the capture source carries season(s) {sorted(set(early.astype(int)))} < "
            f"{WAYBACK_FIRST_SEASON}, which the nflverse `date_modified` source already covers — "
            f"two as-of semantics for one player-week is refused, never reconciled"
        )
    overlap = set(nf["season"].unique()) & set(wayback["season"].unique())
    if overlap:
        raise ValueError(f"injury sources overlap on seasons {sorted(overlap)} — two as-of "
                         f"semantics for one player-week is refused, never reconciled")
    cols = ["season", "week", "gsis_id", "report_status", "practice_status", "date_modified",
            "_stamp_kind"]
    if not len(nf):
        return wayback[cols].copy()
    if not len(wayback):
        return nf[cols].copy()
    return pd.concat([nf[cols], wayback[cols]], ignore_index=True)


# ── Per-row coverage: `observed` is an instant-level property, not an era constant ──────────────
def attach_coverage(feat: pd.DataFrame, injuries: pd.DataFrame,
                    *, max_age_days: float = COVERAGE_MAX_AGE_DAYS) -> pd.DataFrame:
    """Attach `_inj_observed` + `_inj_capture_age_days` per row.

    A row is OBSERVED iff ≥1 capture for its own `(season, week)` lands strictly before its own
    target gameday 00:00 UTC **and** within `max_age_days` of it. Licensed by the source shape:
    each capture is a league-wide report snapshot, so a readable in-bound report the row is
    absent from is a genuine observation of "no designation", not an imputation.

    ⛔ Rows in the nflverse era are observed by their era (`date_modified` is 100% present
    2016–2024, measured) — the bound applies only where coverage is a capture property.
    """
    f = feat.copy()
    gameday = pd.to_datetime(f["_target_gameday"], errors="coerce").dt.tz_localize("UTC")
    legacy_era = (f["season"].astype(int) <= W2.INJURY_VERIFIED_MAX_SEASON).to_numpy()

    caps_src = injuries[injuries["_stamp_kind"] == STAMP_WAYBACK]
    inst: dict[tuple[int, int], np.ndarray] = {}
    for (season, week), grp in caps_src.groupby(["season", "week"], sort=False):
        stamps = pd.to_datetime(grp["date_modified"], utc=True, errors="coerce").dropna()
        if len(stamps):
            inst[(int(season), int(week))] = np.sort(stamps.to_numpy())

    # ages are a CAPTURE-era property only — an nflverse `date_modified` is a vendor edit stamp,
    # not an archive capture, so an "age" over it would be a category error.
    ages = np.full(len(f), np.nan)
    g_np = gameday.to_numpy()
    seasons = f["season"].astype(int).to_numpy()
    weeks = f["week"].astype(int).to_numpy()
    for (season, week), caps in inst.items():
        sel = np.flatnonzero((seasons == season) & (weeks == week) & ~legacy_era)
        for i in sel:
            g = g_np[i]
            if pd.isna(g):
                continue
            prior = caps[caps < g]
            if len(prior):
                ages[i] = (g - prior.max()) / np.timedelta64(1, "D")
    f["_inj_capture_age_days"] = ages
    capture_covered = np.isfinite(ages) & (ages <= max_age_days)
    f["_inj_observed"] = np.where(legacy_era, True, capture_covered)
    return f


# ── The injury_report family, generalised to a PER-ROW observed flag ────────────────────────────
def engineer_injury_features_w2d(feat: pd.DataFrame, injuries: pd.DataFrame,
                                 *, max_age_days: float = COVERAGE_MAX_AGE_DAYS) -> pd.DataFrame:
    """Attach the `injury_report` family across BOTH as-of eras.

    Byte-identical to `W2.engineer_injury_features` on the nflverse era (the reproduction control
    proves it at the CRPS level; `test_nf_w2d_2025_regate` proves it at the column level). The
    generalisations, all of which are inert before 2025:

      · `observed` is the per-row coverage flag rather than `season <= 2024`;
      · capture rows are deduplicated AFTER the admissibility test, not before — a capture store
        holds several genuine as-of observations of one player-week, so taking the globally
        latest and THEN testing admissibility would silently discard an admissible earlier
        capture in favour of an inadmissible later one. nflverse rows keep the legacy
        dedup-then-test order exactly, so the legacy era cannot move;
      · a listed row whose consumed capture carries no practice line gets NaN practice columns.
    """
    f = attach_coverage(feat, injuries, max_age_days=max_age_days)
    inj = injuries.copy()
    inj["_dm_utc"] = pd.to_datetime(inj["date_modified"], utc=True, errors="coerce")
    inj["_rs"] = W2._norm(inj["report_status"]).where(inj["report_status"].notna())
    inj["_ps"] = W2._norm(inj["practice_status"]).where(inj["practice_status"].notna())
    inj["_practice_known"] = inj["practice_status"].notna()
    keep = ["season", "week", "gsis_id", "_dm_utc", "_rs", "_ps", "_practice_known", "_stamp_kind"]

    legacy = inj[inj["_stamp_kind"] == STAMP_NFLVERSE]
    # legacy order preserved EXACTLY (W2: latest stamp wins, before any admissibility test)
    legacy = (legacy.sort_values("_dm_utc", na_position="first")
                    .drop_duplicates(["season", "week", "gsis_id"], keep="last"))
    capture = inj[inj["_stamp_kind"] == STAMP_WAYBACK]

    f = f.merge(legacy[keep], on=["season", "week", "gsis_id"], how="left").reset_index(drop=True)
    # recomputed AFTER the merge so the mask can never fall out of alignment with the frame
    gameday_utc = pd.to_datetime(f["_target_gameday"], errors="coerce").dt.tz_localize("UTC")
    observed = f["_inj_observed"].to_numpy(dtype=bool)

    if len(capture):
        # admissibility FIRST (strictly before this row's own instant, in-bound), then latest wins
        cand = f[["season", "week", "gsis_id"]].copy()
        cand["_row"] = np.arange(len(f))
        cand["_g"] = gameday_utc.to_numpy()
        cand = cand.merge(capture[keep], on=["season", "week", "gsis_id"], how="inner")
        age = (cand["_g"] - cand["_dm_utc"]).dt.total_seconds() / 86400.0
        cand = cand[(cand["_dm_utc"] < cand["_g"]) & (age <= max_age_days)]
        cand = cand.sort_values("_dm_utc").drop_duplicates("_row", keep="last")
        for col in ("_rs", "_ps", "_practice_known", "_stamp_kind"):
            f.loc[cand["_row"].to_numpy(), col] = cand[col].to_numpy()
        # assigned last + re-coerced: if `legacy` was empty the merge created `_dm_utc` as
        # float64 NaN, and writing timestamps into it would silently produce an object column
        f.loc[cand["_row"].to_numpy(), "_dm_utc"] = cand["_dm_utc"].to_numpy()
    f["_dm_utc"] = pd.to_datetime(f["_dm_utc"], utc=True, errors="coerce")

    admissible = (observed & f["_dm_utc"].notna().to_numpy()
                  & (f["_dm_utc"] < gameday_utc).to_numpy())

    f["injury_report__listed"] = np.where(observed, admissible.astype(float), np.nan)
    for col, val in (
        ("injury_report__status_out", "out"),
        ("injury_report__status_doubtful", "doubtful"),
        ("injury_report__status_questionable", "questionable"),
    ):
        hit = admissible & (f["_rs"] == val).to_numpy()
        f[col] = np.where(observed, hit.astype(float), np.nan)
    # a consumed capture with NO practice line leaves practice UNKNOWN (NaN), never 0 — but a
    # covered row with NO consumed capture is genuinely un-designated, so 0 is the observation.
    practice_known = (~admissible) | (
        f["_practice_known"].to_numpy() == True)  # noqa: E712 — object column, `is True` fails
    for col, val in (
        ("injury_report__practice_dnp", CANONICAL_PRACTICE_DNP),
        ("injury_report__practice_limited", CANONICAL_PRACTICE_LIMITED),
    ):
        hit = admissible & (f["_ps"] == val).to_numpy()
        f[col] = np.where(observed & practice_known, hit.astype(float), np.nan)
    f["injury_report__observed"] = observed.astype(float)

    f["_inj_dm_utc"] = f["_dm_utc"].where(pd.Series(admissible, index=f.index))
    f["_inj_stamp_kind"] = f["_stamp_kind"].where(pd.Series(admissible, index=f.index))
    return f.drop(columns=["_dm_utc", "_rs", "_ps", "_practice_known", "_stamp_kind"])


# ── The injury_rate family, driven by the same per-row observed flag ────────────────────────────
def engineer_injury_rate_features_w2d(feat: pd.DataFrame) -> pd.DataFrame:
    """`W2B.engineer_injury_rate_features` with the era constant replaced by `_inj_observed`.

    Identical construction otherwise: for a row with target-gameday instant g, each rate is the
    share of the OBSERVED modeled rows of its (season, week, position) whose consumed report is
    stamped strictly before g and carries the indicator. Group-level by construction — constant
    within (season, week, position, gameday) — so no player identity can enter.
    """
    f = feat.copy()
    observed = f["_inj_observed"].to_numpy(dtype=bool)
    rate_cols = [c for c in RATE_FEATURES_W2D if c != "injury_rate__observed"]
    for c in rate_cols:
        f[c] = np.nan
    f["_rate_max_stamp_utc"] = pd.Series(pd.NaT, index=f.index, dtype="datetime64[ns, UTC]")
    f["_rate_stamp_kind"] = pd.Series(pd.NA, index=f.index, dtype="object")

    modeled = (f["label"] != WF.LABEL_BYE) & observed & f["_target_gameday"].notna()
    sub = f.loc[modeled]
    for (_, _, _), grp in sub.groupby(["season", "week", "position"], sort=False):
        n = len(grp)
        stamps = pd.to_datetime(grp["_inj_dm_utc"], utc=True, errors="coerce")
        kinds = grp["_inj_stamp_kind"]
        instants = pd.to_datetime(grp["_target_gameday"], errors="coerce").dt.tz_localize("UTC")
        indicators = {
            rc: (pd.to_numeric(grp[pc], errors="coerce") == 1.0).to_numpy()
            for rc, pc in W2B.RATE_OF_PLAYER_COL.items()
        }
        for g in instants.dropna().unique():
            counted = (stamps.notna() & (stamps < g)).to_numpy()
            rows_idx = grp.index[(instants == g).to_numpy()]
            for rc in rate_cols:
                f.loc[rows_idx, rc] = float((counted & indicators[rc]).sum()) / n
            if counted.any():
                f.loc[rows_idx, "_rate_max_stamp_utc"] = stamps.to_numpy()[counted].max()
                # a rate that consumed ANY capture stamp declares the capture provenance — the
                # conservative direction (declare the absence rather than assert a vendor as-of
                # we do not have).
                consumed_kinds = set(kinds.to_numpy()[counted].tolist())
                f.loc[rows_idx, "_rate_stamp_kind"] = (
                    STAMP_WAYBACK if STAMP_WAYBACK in consumed_kinds else STAMP_NFLVERSE)
    f["injury_rate__observed"] = observed.astype(float)
    return f


# ── PIT gate: provenance SHAPE follows the stamp kind ───────────────────────────────────────────
def _record(*, source: str, payload: str, stamp: str, tier: str, kind: str) -> dict:
    """One §13 record. A WAYBACK stamp declares its absent `source_timestamp`; an NFLVERSE stamp
    carries `date_modified` in that slot. ⛔ The capture instant is never laundered into the
    vendor slot — `check_provenance_present` rejects a null source_timestamp with no declared
    reason, so the declaration is load-bearing, not documentation."""
    rec = {
        "capture_source": source,
        "capture_id": payload,
        "subject_key": payload,
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "record_tier": tier,
        "feature_timestamp": stamp,
        "capture_timestamp": stamp,
        "vendor_release_timestamp": None if kind == STAMP_WAYBACK else stamp,
        "ingestion_timestamp": stamp,
        "is_rolling_window": False,
    }
    if kind == STAMP_WAYBACK:
        rec["source_timestamp"] = None
        rec["source_timestamp_absent_reason"] = WAYBACK_SOURCE_TS_ABSENT_REASON
    else:
        rec["source_timestamp"] = stamp
    return rec


def injury_guard_records_w2d(rows: pd.DataFrame) -> list[dict]:
    """One record per CONSUMED injury row, in the provenance shape its source earns."""
    records: list[dict] = []
    sub = rows.loc[rows["_inj_dm_utc"].notna()]
    for season, week, gsis, dm, kind in zip(
        sub["season"].to_numpy(), sub["week"].to_numpy(), sub["gsis_id"].to_numpy(),
        sub["_inj_dm_utc"], sub["_inj_stamp_kind"].to_numpy(),
    ):
        kind = STAMP_WAYBACK if kind == STAMP_WAYBACK else STAMP_NFLVERSE
        source = (WAYBACK_STORE_SOURCE if kind == STAMP_WAYBACK else "nflverse_injuries")
        records.append(_record(source=source, payload=f"{season}|{week}|{gsis}|inj|{kind}",
                               stamp=pd.Timestamp(dm).isoformat(), tier="injury", kind=kind))
    return records


def rate_guard_records_w2d(rows: pd.DataFrame) -> list[dict]:
    """One record per row whose rate features consumed ≥1 stamp — the MAX consumed stamp is the
    sufficient statistic for the strictly-before bound, so a `<`→`≤` or wrong-instant bug lands
    in the record and the gate REJECTS."""
    records: list[dict] = []
    sub = rows.loc[rows["_rate_max_stamp_utc"].notna()]
    for season, week, gsis, mx, kind in zip(
        sub["season"].to_numpy(), sub["week"].to_numpy(), sub["gsis_id"].to_numpy(),
        sub["_rate_max_stamp_utc"], sub["_rate_stamp_kind"].to_numpy(),
    ):
        kind = STAMP_WAYBACK if kind == STAMP_WAYBACK else STAMP_NFLVERSE
        source = (f"{WAYBACK_STORE_SOURCE}_rate" if kind == STAMP_WAYBACK
                  else "nflverse_injuries_rate")
        records.append(_record(source=source, payload=f"{season}|{week}|{gsis}|injrate|{kind}",
                               stamp=pd.Timestamp(mx).isoformat(), tier="lake_feature", kind=kind))
    return records


def run_pit_gate_w2d(feat: pd.DataFrame, *, guard=LG.assert_point_in_time) -> dict:
    """FAIL-CLOSED PIT gate at PER-GAME granularity — NF-W2b's gate with source-aware provenance.

    `store_index={}` matches NF-W2/NF-W2b, and the reason is stated rather than left silent:
    consuming the LATEST admissible capture of a player-week is a correct as-of read, not a
    vendor restatement, so a populated index would false-reject a legitimate second observation
    of a subject. The runner MEASURES how many store subjects hold >1 capture and reports it, so
    "the revision clause did not fire" is never mistaken for "the revision clause passed"
    (NF-D20: an inactive clause is uninformative, never a pass).
    """
    if WP.PIT_STORE_SOURCES_CONSUMED:
        raise NotImplementedError(
            "PIT_STORE_SOURCES_CONSUMED is non-empty — build a real store_index first (NF1.7 (a))."
        )
    modeled = feat[feat["label"] != WF.LABEL_BYE]
    dropped: list[dict] = []
    kept_idx: list[np.ndarray] = []
    counts = {"game_groups_checked": 0, "records_checked": 0, "injury_records_checked": 0,
              "rate_records_checked": 0, "wayback_records_checked": 0}
    for (season, week, gameday), rows in modeled.groupby(
        ["season", "week", "_target_gameday"], sort=True
    ):
        projection_ts = pd.Timestamp(gameday).strftime("%Y-%m-%dT00:00:00+00:00")
        inj_recs = injury_guard_records_w2d(rows)
        rate_recs = rate_guard_records_w2d(rows)
        records = WP.pit_guard_records(rows) + inj_recs + rate_recs
        counts["game_groups_checked"] += 1
        counts["records_checked"] += len(records)
        counts["injury_records_checked"] += len(inj_recs)
        counts["rate_records_checked"] += len(rate_recs)
        counts["wayback_records_checked"] += sum(
            1 for r in inj_recs + rate_recs if r["source_timestamp"] is None)
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
    return {**counts, "groups_dropped": dropped,
            "rows_dropped": int(sum(d["n_rows"] for d in dropped)), "kept_index": kept}


def assemble_matrix_w2d(
    frame: pd.DataFrame,
    stats: pd.DataFrame,
    snaps: pd.DataFrame,
    schedule: pd.DataFrame,
    injuries: pd.DataFrame,
    *,
    guard=LG.assert_point_in_time,
) -> tuple[pd.DataFrame, dict]:
    """THE W2d assembly boundary: NF-W1 engineering → the two-era injury family → the rate family
    → provenance → per-game PIT gate. The only sanctioned path to a W2d matrix."""
    feat = WP.engineer_features(frame, stats, snaps, schedule)
    feat = engineer_injury_features_w2d(feat, injuries)
    feat = engineer_injury_rate_features_w2d(feat)
    W2B.assert_feature_provenance_w2b(FEATURES_W2D)
    audit = run_pit_gate_w2d(feat, guard=guard)
    modeled = feat.loc[audit["kept_index"]].reset_index(drop=True)
    audit = {k: v for k, v in audit.items() if k != "kept_index"}
    return modeled, audit


def matrix_key_w2d(seasons: tuple[int, int]) -> str:
    payload = json.dumps({
        "seasons": seasons, "features": list(FEATURES_W2D), "label_version": WP.LABEL_VERSION,
        "scoring": WP.SCORING_SYSTEM_ID, "positions": list(WP.POSITIONS),
        "injury_verified_max_season": W2.INJURY_VERIFIED_MAX_SEASON,
        "wayback_store": WAYBACK_STORE_SOURCE, "coverage_max_age_days": COVERAGE_MAX_AGE_DAYS,
        "schema": 1,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Coverage reporting (the registered design quantities, recomputed at run time) ───────────────
def revision_clause_activity(store_raw: pd.DataFrame) -> dict:
    """How many records the guard's clause-7 REVISION check could act on (NF-D20).

    ⭐ Two DIFFERENT multiplicities, and conflating them would misstate the clause:
      · `store_subject_max_captures` — captures per the STORE'S OWN `subject_key`
        (`season|week|gsis_id|source`). >1 here is what clause 7 exists to catch.
      · `player_weeks_with_multiple_source_captures` — player-weeks captured by >1 SOURCE. These
        are DISTINCT subjects, not revisions; the count is reported because it is the number of
        rows on which this build's latest-admissible-wins rule actually chose between captures.
    An inactive clause is uninformative, never a pass.
    """
    if "subject_key" not in store_raw.columns:
        raise ValueError("store_raw carries no subject_key — refusing to report the revision "
                         "clause's activity from a frame that cannot express it (NF1.7 (a))")
    per_subject = store_raw.groupby("subject_key").size()
    per_pw = store_raw.groupby(["season", "week", "gsis_id"]).size()
    return {
        "store_rows": int(len(store_raw)),
        "store_subjects": int(len(per_subject)),
        "store_subject_max_captures": int(per_subject.max()) if len(per_subject) else 0,
        "store_subjects_with_multiple_captures": int((per_subject > 1).sum()),
        "player_weeks_with_multiple_source_captures": int((per_pw > 1).sum()),
        "clause_state": ("INACTIVE — no store subject holds more than one capture, so clause 7 "
                         "has nothing it could fire on; this is not a pass"
                         if len(per_subject) and int(per_subject.max()) <= 1
                         else "ACTIVE — at least one subject holds multiple captures"),
    }


def coverage_report(feat: pd.DataFrame, injuries: pd.DataFrame) -> dict:
    """Recompute the pre-registered coverage quantities from the built matrix — ⛔ never
    hardcoded from the pre-registration, so a drift between the doc and the data is visible."""
    capture_era = feat["season"].astype(int) >= WAYBACK_FIRST_SEASON
    sub = feat.loc[capture_era]
    out: dict = {"capture_era_rows": int(len(sub))}
    if not len(sub):
        return out
    ages = pd.to_numeric(sub["_inj_capture_age_days"], errors="coerce")
    out["coverage_primary_bound_days"] = COVERAGE_MAX_AGE_DAYS
    out["coverage_primary"] = round(float((ages <= COVERAGE_MAX_AGE_DAYS).mean()), 4)
    out["coverage_diagnostic_only"] = {
        ("unbounded" if not np.isfinite(b) else f"{b:g}d"):
            round(float((ages <= b).mean()), 4) for b in DIAGNOSTIC_COVERAGE_BOUNDS
    }
    covered = sub["_inj_observed"].to_numpy(dtype=bool)
    out["by_week"] = [
        {"week": int(w), "n": int(len(g)),
         "coverage": round(float(g["_inj_observed"].mean()), 4),
         "median_capture_age_days": (None if not np.isfinite(
             pd.to_numeric(g["_inj_capture_age_days"], errors="coerce").median())
             else round(float(pd.to_numeric(g["_inj_capture_age_days"],
                                            errors="coerce").median()), 3))}
        for w, g in sub.groupby("week", sort=True)
    ]
    out["by_position"] = {
        str(p): round(float(g["_inj_observed"].mean()), 4)
        for p, g in sub.groupby("position", sort=True)
    }
    out["uncovered_weeks"] = [r["week"] for r in out["by_week"] if r["coverage"] == 0.0]
    age_cov = ages[covered]
    out["capture_age_days"] = {
        k: (None if not len(age_cov) else round(float(v), 3)) for k, v in
        {"median": age_cov.median() if len(age_cov) else np.nan,
         "p75": age_cov.quantile(0.75) if len(age_cov) else np.nan,
         "p90": age_cov.quantile(0.90) if len(age_cov) else np.nan}.items()
    }
    # per-COLUMN absence, never a pooled mean (MH2.1 (c))
    listed = pd.to_numeric(sub["injury_report__listed"], errors="coerce") == 1.0
    out["listed_share_over_covered"] = (
        round(float(listed.sum() / max(int(covered.sum()), 1)), 4))
    out["per_column_absence_over_listed"] = {
        c: round(float(pd.to_numeric(sub.loc[listed, c], errors="coerce").isna().mean()), 4)
        for c in ("injury_report__practice_dnp", "injury_report__practice_limited",
                  "injury_report__status_out")
    } if int(listed.sum()) else {}
    out["capture_rows_supplied"] = int((injuries["_stamp_kind"] == STAMP_WAYBACK).sum())
    return out
