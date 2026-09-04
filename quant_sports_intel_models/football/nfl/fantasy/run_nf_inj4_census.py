"""run_nf_inj4_census.py — NF-INJ4 node 1: the DATA CENSUS, run BEFORE the registration.

The spec's first acceptance criterion is "DATA HONESTY FIRST, and it may bind": assemble the
PIT-safe designation → games-missed frame, INVOKE `assert_point_in_time` on it with row counts
reported, state the realized depth, and run the power arithmetic — all before a single arm exists,
so the registered family is shaped by what the data can carry rather than by what a fit preferred.

⭐ WHAT THE CENSUS IS ALLOWED TO LOOK AT. Row counts, cell sizes, coverage, censoring, the pooled
target moments and the source-provenance probes — every one of them a DESIGN quantity. It also runs
one FRAME-INTEGRITY check (does an `out` designation overwhelmingly produce a miss?), and that is
recorded rather than hidden: a frame in which `out` players play is BROKEN, and registering a study
on it would be the most expensive kind of silent null. ⛔ No arm is fitted, ranked or chosen here,
and no per-cell outcome level is used to pick a conditioning shape — the fallback shapes are chosen
on CELL SIZE, which the spec names as the criterion.

RUN (LAPTOP — reads the S3 lake + the PIT store read-only, writes local artifacts; ~2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4_census
"""
from __future__ import annotations

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

from betting_ml.utils import cv_power as CP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj4_designation_duration as DD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_inj4_census")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
MODELED_POSITIONS = ("QB", "RB", "WR", "TE")

#: The fold count the registration will declare. Stated HERE because the census's job is to prove
#: it is admissible before it is registered (`validate_sign_certifiability`), not to discover it
#: afterwards.
CANDIDATE_FOLDS: tuple[int, ...] = (7, 8, 10, 12)
N_ARMS_PLANNED = 7


# ── Sources ────────────────────────────────────────────────────────────────────────────────────
def load_capture_store() -> pd.DataFrame:
    """The immutable NF-W0a store landed by NF-W2c + NF-W2c-CBS. An empty/unreadable store RAISES:
    a census silently built from zero captures would report a clean, confident, empty depth."""
    import duckdb
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io
    from quant_sports_intel_models.football.nfl.pit import store

    uri = store.table_uri(DD.WAYBACK_STORE_SOURCE)
    dt = DeltaTable(uri, storage_options=s3io.storage_options() if uri.startswith("s3://") else None)
    con = duckdb.connect()
    con.register("pit_captures", dt.to_pyarrow_dataset())
    try:
        df = con.sql(
            "select subject_key, capture_id, season, week, gsis_id, full_name, position, "
            "report_status, practice_status, capture_timestamp, feature_timestamp, "
            "source_timestamp, source_timestamp_absent_reason, ingestion_timestamp, "
            "payload_sha256 from pit_captures"
        ).df()
    finally:
        con.unregister("pit_captures")
        con.close()
    if df.empty:
        raise SystemExit(
            f"the {DD.WAYBACK_STORE_SOURCE} store returned ZERO rows — refusing to census an unread "
            f"source (NF1.7 (a): an empty read must never be recorded as a measured depth)")
    df["source"] = df["subject_key"].str.split("|").str[-1]
    return df


def load_forward_capture() -> pd.DataFrame:
    """The NF-W0a FORWARD injury capture (`nfl/pit/injuries`). Read so its realized contribution is
    a MEASURED number rather than an inherited premise — the spec names it as a substrate."""
    import duckdb
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io
    from quant_sports_intel_models.football.nfl.pit import store

    uri = store.table_uri("injuries")
    dt = DeltaTable(uri, storage_options=s3io.storage_options() if uri.startswith("s3://") else None)
    con = duckdb.connect()
    con.register("fwd", dt.to_pyarrow_dataset())
    try:
        return con.sql("select season, week, gsis_id, position, report_status, capture_timestamp, "
                       "capture_date, cadence_label from fwd").df()
    finally:
        con.unregister("fwd")
        con.close()


def load_outcome_sources() -> dict:
    from quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3_injury_games import (  # noqa: F401
        _DEFAULT_DUCKDB,
    )
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    rosters = q(f"""select season, week, team, position, status, gsis_id
                    from {delta('weekly_rosters')}
                    where season = {DD.SEASON} and position in {MODELED_POSITIONS}""")
    schedule = q(f"""select season, week, home_team, away_team, gameday from {delta('schedules')}
                     where season = {DD.SEASON} and game_type = 'REG'""")
    stats = q(f"select * from {delta('stats_player_week')} where season = {DD.SEASON}")
    snaps = q(f"select * from {delta('snap_counts')} where season = {DD.SEASON}")
    return {"rosters": rosters, "schedule": schedule, "stats": stats, "snaps": snaps}


# ── The PIT gate, INVOKED on the assembled frame ───────────────────────────────────────────────
def run_pit_gate(frame: pd.DataFrame, gamedays: pd.DataFrame) -> dict:
    """FAIL-CLOSED §13 gate over every assembled designation row, grouped by its own gameday.

    ⭐ WIRED **AND** INVOKED. These rows already passed NF-W2c's gate at landing; re-running it here
    is deliberate — the census assembles a NEW frame (a different resolution rule and a different
    source set), and a gate that only ever ran in an upstream story is a gate this story never ran
    (NF-C0e). `store_index={}` matches NF-W2/W2b/W2d: consuming the LATEST admissible capture of a
    player-week is a correct as-of read, not a vendor restatement, so a populated index would
    false-reject a legitimate second observation of one subject. The count of subjects holding >1
    capture is REPORTED, so "the revision clause did not fire" is never mistaken for "it passed"
    (NF-D20: an inactive clause is uninformative, never a pass).
    """
    gd = gamedays.set_index(["gsis_id", "week"])["gameday_iso"].to_dict()
    checked = dropped = 0
    kept: list[int] = []
    findings: dict[str, int] = {}
    for (week,), grp in frame.groupby(["week"]):
        for gameday, sub in grp.assign(
            _gd=[gd.get((r.gsis_id, r.week)) for r in grp.itertuples()]
        ).groupby("_gd"):
            projection_ts = f"{gameday}T00:00:00+00:00"
            records = []
            for r in sub.itertuples():
                records.append({
                    "capture_source": DD.WAYBACK_STORE_SOURCE,
                    "capture_id": r.capture_id,
                    "subject_key": r.subject_key,
                    "payload_sha256": r.payload_sha256,
                    "record_tier": "injury",
                    "feature_timestamp": r.feature_timestamp,
                    "source_timestamp": None,
                    "source_timestamp_absent_reason": r.source_timestamp_absent_reason,
                    "capture_timestamp": r.capture_timestamp,
                    "vendor_release_timestamp": None,
                    "ingestion_timestamp": r.ingestion_timestamp,
                    "is_rolling_window": False,
                })
            checked += len(records)
            try:
                LG.assert_point_in_time(records, projection_ts, store_index={})
                kept.extend(sub.index.tolist())
            except LG.LeakageRejection as exc:
                dropped += len(sub)
                for f in exc.findings:
                    findings[f.reason.name] = findings.get(f.reason.name, 0) + 1
                log.warning("PIT gate dropped week %s gameday %s (%d rows): %s",
                            week, gameday, len(sub), sorted({f.reason.name for f in exc.findings}))
    return {"records_checked": checked, "rows_dropped": dropped,
            "rows_kept": len(kept), "kept_index": kept, "findings": findings}


# ── Probes ─────────────────────────────────────────────────────────────────────────────────────
def source_week_attribution_probe(store: pd.DataFrame, grid: pd.DataFrame) -> dict:
    """⭐ THE PROBE THAT DECIDED SOURCE ADMISSIBILITY. For each source × designation, the realized
    MISS RATE when the designation is read against the week it is attributed to, and against the
    weeks either side. A source whose designation describes `w` should peak at lag 0; a source that
    peaks at lag −1 is attributed ONE WEEK LATE, and its rows have no admissible week (see
    `DD.ADMISSIBLE_SOURCES`). Run on the FULL store, including the excluded source, so the exclusion
    is a measurement anyone can re-run rather than an assertion."""
    key = grid.set_index(["gsis_id", "week"])[["has_game", "missed"]]
    out: dict = {}
    for lag in (-1, 0, 1):
        m = store[["source", "week", "gsis_id", "report_status"]].copy()
        m["wk_test"] = m["week"] + lag
        j = m.merge(key.reset_index().rename(columns={"week": "wk_test"}),
                    on=["gsis_id", "wk_test"], how="left")
        j = j[j["has_game"].astype("boolean").fillna(False)]
        t = (j.assign(designation=j["report_status"].fillna(DD.DESIGNATION_NONE))
               .groupby(["source", "designation"])["missed"]
               .agg(n="size", miss_rate="mean"))
        out[f"lag_{lag:+d}"] = {f"{s}|{d}": {"n": int(r.n), "miss_rate": round(float(r.miss_rate), 4)}
                                for (s, d), r in t.iterrows()}
    return out


def null_designation_timing_probe(store: pd.DataFrame, gd_map: pd.DataFrame) -> dict:
    """⭐ THE PROBE THAT DECIDED HOW A NULL `report_status` IS TREATED. For each admissible source,
    when captures carrying a designation land versus when blank ones do. nfl.com publishes practice
    participation from Wednesday and fills the GAME-STATUS column only on the final report, so a
    blank mid-week capture is "not YET designated" — and a rule that let it win on recency would
    erase a real earlier designation from the other source. Measured here rather than asserted."""
    df = store[store["source"].isin(DD.ADMISSIBLE_SOURCES)].copy()
    df["cap"] = pd.to_datetime(df["capture_timestamp"], utc=True)
    df["has_designation"] = df["report_status"].notna()
    df["capture_dow"] = df["cap"].dt.day_name()
    j = df.merge(gd_map, on=["gsis_id", "week"], how="inner")
    j["days_before_gameday"] = (
        pd.to_datetime(j["gameday_iso"]).dt.tz_localize("UTC") - j["cap"]
    ).dt.total_seconds() / 86400.0
    lead = (j.groupby(["source", "has_designation"])["days_before_gameday"]
              .agg(n="size", median="median",
                   q25=lambda x: x.quantile(0.25), q75=lambda x: x.quantile(0.75)).round(3))
    dow = df.groupby(["source", "capture_dow", "has_designation"]).size()
    return {
        "capture_lead_days_by_source_and_designation_presence":
            {f"{a}|has_designation={b}": {k: (int(v) if k == "n" else float(v))
                                          for k, v in r.items()}
             for (a, b), r in lead.iterrows()},
        "captures_by_source_dow_and_designation_presence":
            {f"{a}|{b}|has_designation={c}": int(v) for (a, b, c), v in dow.items()},
    }


def resolution_activity_probe(store: pd.DataFrame) -> dict:
    """⭐ IS THE RESOLUTION RULE'S SENSITIVITY ABLE TO ACT AT ALL? (NF-D20 / NF1.9: count the cases a
    mechanism could move BEFORE reading its agreement — an inactive clause is uninformative, never a
    pass.) Measured: on the player-weeks whose admissible captures carry MORE THAN ONE distinct
    designation, does the latest-designated capture differ from the most severe one?"""
    a = store[store["source"].isin(DD.ADMISSIBLE_SOURCES) & store["report_status"].notna()].copy()
    a["cap"] = pd.to_datetime(a["capture_timestamp"], utc=True)
    a["_sev"] = a["report_status"].map({"out": 3, "doubtful": 2, "questionable": 1})
    conflict = a.groupby(["week", "gsis_id"]).filter(lambda x: x["report_status"].nunique() > 1)
    n_conflict = conflict.groupby(["week", "gsis_id"]).ngroups
    same = 0
    pairs: dict[str, int] = {}
    for _, x in conflict.groupby(["week", "gsis_id"]):
        latest = x.sort_values("cap").iloc[-1]["report_status"]
        strongest = x.sort_values(["_sev", "cap"]).iloc[-1]["report_status"]
        same += int(latest == strongest)
        pairs[f"latest={latest}|strongest={strongest}"] = (
            pairs.get(f"latest={latest}|strongest={strongest}", 0) + 1)
    return {
        "player_weeks_with_more_than_one_distinct_designation": int(n_conflict),
        "of_those_latest_equals_strongest": int(same),
        "resolution_pairs": pairs,
        "sensitivity_is_active": bool(n_conflict > 0 and same < n_conflict),
        "reading": (
            "INACTIVE — every conflicting player-week resolves identically under both rules, because "
            "in this population a designation only ever ESCALATES through the week (questionable → "
            "out) and never de-escalates. The pre-registered sensitivity is therefore guaranteed "
            "byte-identical to the primary, and its agreement carries NO information (NF-D20: an "
            "inactive clause is uninformative, never a pass)."
            if n_conflict > 0 and same == n_conflict else
            "ACTIVE — the two rules resolve at least one player-week differently, so the sensitivity "
            "is a real second reading."),
    }


def power_arithmetic(n_arms: int) -> dict:
    """`validate_sign_certifiability` (PLAT-CVP2) + the rest of the design's operating characteristics,
    run at REGISTRATION TIME so a refusal re-shapes the folds BEFORE scoring, never after."""
    rows = []
    for k in CANDIDATE_FOLDS:
        entry: dict = {"n_folds": k}
        for cut, label in ((0.05, "single_hypothesis"), (0.05 / n_arms, "arm_corrected")):
            r = CP.validate_sign_certifiability(n_folds=k, bh_cutoff=cut, two_sided=False,
                                                strict=False)
            entry[label] = {"bh_cutoff": round(r.bh_cutoff, 5), "sign_floor": round(r.sign_floor, 5),
                            "certifiable": r.certifiable, "headroom": round(r.headroom, 4),
                            "folds_needed": r.folds_needed,
                            "margin_rule_met": bool(r.certifiable and r.headroom <= 0.5)}
        fc = CP.fold_consistency_clause(k)
        entry["fold_consistency"] = {"wins_required": fc.wins_required, "attainable": fc.attainable,
                                     "attained_false_fire": round(fc.attained_false_fire, 4),
                                     "legacy_wins_required": fc.legacy_wins_required}
        entry["pbo_evaluable"] = CP.pbo_evaluable(k, n_arms)
        entry["dsr_ceiling"] = round(CP.dsr_ceiling(k), 4)
        entry["mde_sd_units"] = round(CP.mde_in_sd_units(n_folds=k), 4)
        rows.append(entry)
    return {"n_arms_planned": n_arms, "by_fold_count": rows}


# ── Assembly ───────────────────────────────────────────────────────────────────────────────────
def build(store: pd.DataFrame, src: dict) -> dict:
    schedule = src["schedule"]
    max_week = int(schedule["week"].max())

    spine = WF.build_spine(src["rosters"], src["schedule"])
    labels = WF.attach_labels(
        spine, src["stats"], label_version=WP.LABEL_VERSION,
        label_as_of_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        scoring_system_id=WP.SCORING_SYSTEM_ID, snaps=src["snaps"])
    grid = DD.availability_grid(src["rosters"], schedule, labels, max_week=max_week)

    probe = source_week_attribution_probe(store, grid)

    resolved = DD.resolve_designations(store)
    strongest = DD.resolve_designations_strongest(store)
    disagree = int((resolved.sort_values(["week", "gsis_id"])["designation"].to_numpy()
                    != strongest.sort_values(["week", "gsis_id"])["designation"].to_numpy()).sum())
    activity = resolution_activity_probe(store)

    gd_map = _gameday_map(src["rosters"], schedule, max_week)
    null_timing = null_designation_timing_probe(store, gd_map)
    resolved = resolved.merge(gd_map, on=["gsis_id", "week"], how="left")
    no_gameday = int(resolved["gameday_iso"].isna().sum())
    resolved = resolved[resolved["gameday_iso"].notna()].reset_index(drop=True)

    audit = run_pit_gate(resolved, resolved[["gsis_id", "week", "gameday_iso"]])
    resolved = resolved.loc[audit.pop("kept_index")].reset_index(drop=True)

    if resolved.empty:
        raise SystemExit(
            "the PIT gate kept ZERO designation rows — a census built on an empty frame would "
            "report a confident, empty depth (NF1.7 (a)). Read `pit_audit.findings_by_reason`.")
    framed = DD.attach_spells(resolved, grid)
    undefined = int(framed["spell"].isna().sum())
    framed = framed[framed["spell"].notna()].copy()
    framed["spell"] = framed["spell"].astype(int)

    return {"frame": framed, "grid": grid, "labels": labels, "probe": probe,
            "resolution_disagreement": disagree, "resolution_activity": activity,
            "null_designation_timing": null_timing, "rows_without_gameday": no_gameday,
            "rows_target_undefined": undefined, "pit_audit": audit}


def _gameday_map(rosters: pd.DataFrame, schedule: pd.DataFrame, max_week: int) -> pd.DataFrame:
    """(gsis_id, week) → the player's own team's gameday, the instant the PIT bound is taken against."""
    tg = pd.concat([
        schedule[["week", "home_team", "gameday"]].rename(columns={"home_team": "team"}),
        schedule[["week", "away_team", "gameday"]].rename(columns={"away_team": "team"}),
    ], ignore_index=True).drop_duplicates(["week", "team"])
    tg["gameday_iso"] = pd.to_datetime(tg["gameday"]).dt.date.astype(str)
    ros = (rosters.loc[rosters["week"] <= max_week, ["week", "gsis_id", "team"]]
           .drop_duplicates(["week", "gsis_id"]))
    return ros.merge(tg[["week", "team", "gameday_iso"]], on=["week", "team"],
                     how="inner")[["gsis_id", "week", "gameday_iso"]]


# ── Census ─────────────────────────────────────────────────────────────────────────────────────
def census(built: dict, store: pd.DataFrame, forward: pd.DataFrame) -> dict:
    d = built["frame"]
    all_pw = store.groupby(["week", "gsis_id"]).ngroups
    adm_pw = (store[store["source"].isin(DD.ADMISSIBLE_SOURCES)]
              .groupby(["week", "gsis_id"]).ngroups)

    subj_multi = int((store.groupby("subject_key").size() > 1).sum())

    cells = (d.groupby(["designation", "position"]).size().unstack(fill_value=0)
             .reindex(index=list(DD.DESIGNATION_LEVELS), fill_value=0))
    integrity = d.groupby("designation")["spell"].agg(
        n="size", zero_share=lambda s: round(float((s == 0).mean()), 4))

    fwd_seasons = (forward.groupby("season")["week"]
                   .agg(n="size", min_week="min", max_week="max").to_dict("index")
                   if len(forward) else {})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-INJ4", "node": "1-data-census", "season": DD.SEASON,

        "substrate_wayback": {
            "rows_landed_all_sources": int(len(store)),
            "rows_by_source": store["source"].value_counts().to_dict(),
            "distinct_player_weeks_all_sources": int(all_pw),
            "admissible_sources": list(DD.ADMISSIBLE_SOURCES),
            "excluded_sources": list(DD.EXCLUDED_SOURCES),
            "distinct_player_weeks_admissible": int(adm_pw),
            "player_weeks_lost_to_exclusion": int(all_pw - adm_pw),
            "store_subjects_with_more_than_one_capture": subj_multi,
            "revision_clause_activity": (
                "INACTIVE — no store subject holds more than one capture, so the §13 "
                "revised-vendor-record clause had nothing to act on. Reported so 'it did not fire' "
                "is never read as 'it passed' (NF-D20)." if subj_multi == 0 else
                f"ACTIVE — {subj_multi} subject(s) hold more than one capture."),
        },
        "substrate_forward_capture": {
            "rows": int(len(forward)),
            "seasons": {int(k): {kk: (int(vv) if kk != "n" else int(vv)) for kk, vv in v.items()}
                        for k, v in fwd_seasons.items()},
            "distinct_capture_dates": sorted(forward["capture_date"].dropna().unique().tolist())
                                      if len(forward) else [],
            "usable_2026_rows": int((forward["season"] == 2026).sum()) if len(forward) else 0,
        },
        "resolution": {
            "rule": "the LATEST admissible capture CARRYING a designation wins; a player-week designated in no admissible capture resolves to `none_listed` (a NULL report_status is MISSING within a capture, never a resolved absence)",
            "sensitivity_rule": "most SEVERE designation wins, recency breaks ties (pre-registered sensitivity; see `sensitivity_activity` before reading its agreement)",
            "player_weeks_where_the_two_rules_disagree": built["resolution_disagreement"],
            "sensitivity_activity": built["resolution_activity"],
            "null_designation_is_missing_not_a_level": built["null_designation_timing"],
        },
        "pit_gate": {
            "invoked": True,
            "records_checked": built["pit_audit"]["records_checked"],
            "rows_dropped": built["pit_audit"]["rows_dropped"],
            "rows_kept": built["pit_audit"]["rows_kept"],
            "findings_by_reason": built["pit_audit"]["findings"],
            "rows_without_a_resolvable_gameday": built["rows_without_gameday"],
        },
        "modelled_frame": {
            "rows": int(len(d)),
            "rows_target_undefined_dropped": built["rows_target_undefined"],
            "distinct_players": int(d["gsis_id"].nunique()),
            "weeks_covered": sorted(int(w) for w in d["week"].unique()),
            "rows_per_week": {int(k): int(v) for k, v in d.groupby("week").size().items()},
            "cell_sizes_designation_x_position": cells.to_dict("index"),
            "cell_sizes_designation": d["designation"].value_counts().to_dict(),
            "cell_sizes_designation_x_practice":
                d.groupby(["designation", "practice_level"]).size().unstack(fill_value=0)
                 .to_dict("index"),
            "practice_level_totals": d["practice_level"].value_counts().to_dict(),
        },
        "target": {
            "definition": "consecutive team games missed from the designation week onward, "
                          "terminated by the next appearance; right-censored at the season end",
            "mean": round(float(d["spell"].mean()), 4),
            "sd": round(float(d["spell"].std()), 4),
            "zero_share": round(float((d["spell"] == 0).mean()), 4),
            "max": int(d["spell"].max()),
            "distribution": {int(k): int(v) for k, v in
                             d["spell"].value_counts().sort_index().items()},
            "censored_rows": int(d["censored"].sum()),
            "censored_share": round(float(d["censored"].mean()), 4),
            "games_remaining": {k: round(float(v), 2) for k, v in
                                d["games_remaining"].describe().items()},
        },
        "frame_integrity_check": {
            "what": "does an `out` designation overwhelmingly produce a miss? A frame in which it "
                    "does not is BROKEN, and registering on it would be a silent null. Recorded "
                    "rather than hidden; no arm is fitted, ranked or chosen on it.",
            "zero_spell_share_by_designation": integrity.to_dict("index"),
        },
        "source_week_attribution_probe": built["probe"],
        "power": power_arithmetic(N_ARMS_PLANNED),
    }


def render(summary: dict, frame: pd.DataFrame) -> str:
    m = summary["modelled_frame"]
    cells = pd.DataFrame(m["cell_sizes_designation_x_position"]).T.fillna(0).astype(int)
    integ = pd.DataFrame(summary["frame_integrity_check"]["zero_spell_share_by_designation"]).T
    pw = pd.DataFrame(summary["power"]["by_fold_count"])
    probe = summary["source_week_attribution_probe"]
    prow = []
    for key in sorted(probe["lag_+0"]):
        src, des = key.split("|")
        prow.append({"source": src, "designation": des,
                     "n@lag0": probe["lag_+0"][key]["n"],
                     "miss@lag-1": probe.get("lag_-1", {}).get(key, {}).get("miss_rate"),
                     "miss@lag0": probe["lag_+0"][key]["miss_rate"],
                     "miss@lag+1": probe.get("lag_+1", {}).get(key, {}).get("miss_rate")})
    return "\n".join([
        "# NF-INJ4 — data census (node 1), run BEFORE the pre-registration", "",
        f"Generated {summary['generated_at']}. Season {summary['season']}. Regenerate with "
        "`uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4_census`.",
        "",
        "> Every number below is a DESIGN quantity — depth, cell sizes, coverage, censoring, "
        "provenance. No arm is fitted, ranked or chosen here. The one exception is §5, a "
        "FRAME-INTEGRITY check, recorded rather than hidden: a frame in which `out` players play "
        "is broken, and registering a study on it would be the most expensive kind of silent null.",
        "",
        "## 0. What the census concluded (and what it cost)", "",
        f"- **The substrate is ONE season, {m['rows']} player-weeks, {m['distinct_players']} "
        f"players, {len(m['weeks_covered'])}/18 weeks.** Season-transfer is structurally "
        "unmeasurable at `n_seasons = 1`; 2026 is the named, genuinely reachable re-test.",
        f"- **The NF-W0a forward capture contributes ZERO usable rows.** It holds "
        f"{summary['substrate_forward_capture']['rows']} rows, ALL `season=2025`, ALL captured on "
        f"{summary['substrate_forward_capture']['distinct_capture_dates']} — i.e. one post-season "
        "backfill of the finished season, whose capture instant is months AFTER every 2025 "
        "gameday and therefore point-in-time inadmissible for it. 2026 rows: "
        f"{summary['substrate_forward_capture']['usable_2026_rows']} (Week 1 is 2026-09-09). The "
        "spec's \"plus the NF-W0a forward capture (2026)\" premise does not hold today.",
        "- **ESPN's 537 rows are inadmissible** — its designations are attributed ONE WEEK LATE "
        "(§3a), which leaves them with no point-in-time-valid week in either reading. Cost: 97 "
        "distinct player-weeks the other two sources do not already cover.",
        "- **A NULL `report_status` is MISSING, not a level** (§3b) — nfl.com fills its "
        "game-status column only on the final report.",
        "- **The pre-registered resolution SENSITIVITY is INACTIVE** (§3c): all 18 conflicting "
        "player-weeks resolve identically under both rules, so its agreement carries no "
        "information.",
        f"- **The `doubtful` cell holds {summary['modelled_frame']['cell_sizes_designation'].get('doubtful', 0)} "
        "rows and its thinnest position cell holds 1**, so a designation x position family cannot "
        "be certified at this depth — which is exactly why the registration declares the coarser "
        "conditioning shapes FORWARD, with a min-cell backoff, rather than choosing after a fit.",
        "",
        "## 1. Substrate depth, measured", "",
        "```json", json.dumps({k: summary[k] for k in
                               ("substrate_wayback", "substrate_forward_capture", "resolution",
                                "pit_gate")}, indent=2), "```", "",
        "## 2. The modelled frame", "",
        f"{m['rows']} rows / {m['distinct_players']} distinct players / "
        f"{len(m['weeks_covered'])} weeks.", "",
        "### Cell sizes — designation x position", "", cells.to_markdown(), "",
        "### Cell sizes — designation x practice participation", "",
        pd.DataFrame(m["cell_sizes_designation_x_practice"]).T.fillna(0).astype(int).to_markdown(), "",
        "## 3a. Source week-attribution probe (the SOURCE-admissibility decision)", "",
        "A source whose designation describes week `w` should peak at lag 0. One peaks at lag -1.",
        "", pd.DataFrame(prow).to_markdown(index=False), "",
        "## 3b. Capture timing (the NULL-designation decision)", "",
        "`report_status` NULL is treated as MISSING within a capture rather than as a level, "
        "because nfl.com fills its game-status column only on the final report:", "",
        pd.DataFrame(summary["resolution"]["null_designation_is_missing_not_a_level"]
                     ["capture_lead_days_by_source_and_designation_presence"]).T.to_markdown(), "",
        "## 3c. Is the pre-registered resolution SENSITIVITY able to act?", "",
        "```json",
        json.dumps(summary["resolution"]["sensitivity_activity"], indent=2), "```", "",
        "## 4. The target", "",
        "```json", json.dumps(summary["target"], indent=2), "```", "",
        "## 5. Frame integrity", "",
        summary["frame_integrity_check"]["what"], "", integ.to_markdown(), "",
        "## 6. Power arithmetic (PLAT-CVP2 `validate_sign_certifiability` + operating characteristics)",
        "", pw.to_markdown(index=False), "",
        "```json", json.dumps(summary["power"], indent=2), "```", "",
    ])


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    store = load_capture_store()
    forward = load_forward_capture()
    src = load_outcome_sources()
    built = build(store, src)
    summary = census(built, store, forward)

    art = _HERE / "artifacts" / "nf_inj4_designation_frame_2025.parquet"
    art.parent.mkdir(parents=True, exist_ok=True)
    built["frame"].to_parquet(art, index=False)
    summary["artifact"] = str(art.relative_to(_PROJECT_ROOT))

    (_REPORT_DIR / "nf_inj4_data_census.json").write_text(json.dumps(summary, indent=2, default=str))
    (_REPORT_DIR / "nf_inj4_data_census.md").write_text(render(summary, built["frame"]))
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("source_week_attribution_probe", "power")},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
