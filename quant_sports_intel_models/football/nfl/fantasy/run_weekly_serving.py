"""run_weekly_serving.py — NF-C6-PH2: build and (optionally) publish the weekly serving artifacts.

    LAPTOP (dry run — stages locally, publishes nothing):
      uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving

    BOX (the scheduled path; `sports_nfl_weekly_serving_job` runs exactly this):
      docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
        python -m quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving \
        --s3-bucket credence-prod-s3-api-cache --publish

⭐ `--publish` IS THE ONLY THING THAT REACHES PROD, and `--publish` WITHOUT A BUCKET IS A HARD ERROR
(the NF1.7 lesson, which cost a real publish: `$CACHE_BUCKET` was unset in the operator's shell, the
run degraded to local staging behind one WARNING line in forty lines of INFO, and looked successful
while nothing reached users). An outward-facing action asked for explicitly never gets a silent no-op.

⛔ IT REFUSES TO PUBLISH PAST A FAILED INVARIANT. Four fail-closed checks run before a byte is
written: the point-in-time gate (non-vacuous — weeks AND records checked > 0), the target-week
outcome-independence proof, the frozen-form horizon check, and contract validation of every blob. A
weekly payload that cannot prove those is not a degraded payload, it is an unknown one.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.backend.models import nfl_weekly as C  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS  # noqa: E402

log = logging.getLogger("nfl.fantasy.run_weekly_serving")

_STAGING = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts/weekly_serving"

#: Exit code for "the target week's rosters have not published yet" — a routine feed
#: cadence state, mapped by the Dagster op to a clean skip rather than a page.
EXIT_AWAITING_ROSTERS = 3
FIRST_TRAIN_SEASON = 2016


def _load_sources(target_season: int) -> dict[str, pd.DataFrame]:
    """The champion's own lake reads, widened by one season so the target year is present.

    Delegates to `run_nf_w1_weekly_bakeoff.load_sources_w1` rather than re-issuing the SQL: a
    serving read that drifts from the read the model was certified on is the E7.9 train/serve
    mismatch, and the cheapest way not to drift is not to have a second copy.
    """
    from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import (
        load_sources_w1,
    )
    return load_sources_w1((FIRST_TRAIN_SEASON, target_season))


def _names(src: dict[str, pd.DataFrame]) -> dict[str, str]:
    """gsis_id → display name, from the roster feed. Absent ⇒ the id itself, never a fabricated
    name: a wrong name on a projection is worse than an ugly one."""
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    try:
        ident = q(
            f"select gsis_id, any_value(coalesce(full_name, concat(first_name, ' ', last_name))) "
            f"as nm from {delta('weekly_rosters')} where gsis_id is not null group by 1"
        )
    except Exception as exc:  # noqa: BLE001 — a name lookup must never block a projection
        log.warning("⚠️ name lookup failed (%s: %s) — serving ids as names", type(exc).__name__, exc)
        return {}
    return {str(r.gsis_id): str(r.nm) for r in ident.itertuples() if r.nm}


def _vintage(src: dict[str, pd.DataFrame], train: pd.DataFrame, target: WS.TargetWeek) -> dict:
    """Per-INPUT vintages, plus the training boundary as a NUMBER.

    ⭐ `train_through_*` is the no-current-week-outcome invariant expressed as data rather than as a
    promise: a reader (and the freshness monitor) can see that the newest realized week behind the
    projection is strictly before the week being projected. `main` refuses to write if it is not.
    """
    def newest(df: pd.DataFrame, col: str = "gameday") -> str | None:
        if df is None or df.empty or col not in df.columns:
            return None
        v = pd.to_datetime(df[col], errors="coerce").max()
        return None if pd.isna(v) else str(pd.Timestamp(v).date())

    def newest_week(df: pd.DataFrame) -> str | None:
        if df is None or df.empty or {"season", "week"} - set(df.columns):
            return None
        row = df.sort_values(["season", "week"]).iloc[-1]
        return f"{int(row['season'])}-W{int(row['week'])}"

    tt = train.sort_values(["season", "week"]).iloc[-1] if len(train) else None
    return {
        "rosters_as_of": newest_week(src["rosters"]),
        "schedule_as_of": newest(src["schedule"]),
        "stats_as_of": newest_week(src["stats"]),
        "snaps_as_of": newest_week(src["snaps"]),
        "train_through_season": None if tt is None else int(tt["season"]),
        "train_through_week": None if tt is None else int(tt["week"]),
    }


def _absences(frame: pd.DataFrame, src: dict[str, pd.DataFrame], universe: pd.DataFrame,
              served_ids: set[str], target: WS.TargetWeek) -> list[dict]:
    """Counts of who is NOT projected, by machine-readable reason.

    ⭐ COUNTED, NOT SILENT. K and D/ST are the case this exists for: NF-W1's champion was fitted on
    QB/RB/WR/TE and on nothing else, so a kicker has no weekly projection — which is a completely
    different fact from "we could not resolve this player" and from "he has no game". Rendering the
    three identically is what cost the D/ST investigation twice (NF-C6b/NF-K1).
    """
    ros = src["rosters"]
    wk = ros[(ros["season"] == target.season) & (ros["week"] == target.week)]
    non_proj = wk[~wk["position"].isin(C.PROJECTED_POSITIONS)]
    in_universe = set(universe["gsis_id"].astype(str))
    dropped = sorted(in_universe - served_ids)
    return [
        {"reason": "position_not_projected", "n": int(len(non_proj)),
         "detail": ("NF-W1's champion covers QB/RB/WR/TE only — it was never fitted on K or D/ST, "
                    "so no weekly projection exists for them. Excluded by design, not missing.")},
        {"reason": "no_gameday_roster_row", "n": int(len(wk[~wk["status"].isin(WF.GAMEDAY_STATUSES)])),
         "detail": ("on the roster feed but not game-day active/inactive for this week "
                    f"(statuses served: {list(WF.GAMEDAY_STATUSES)})")},
        {"reason": "pit_gate_dropped", "n": int(len(dropped)),
         "detail": ("game-day rostered but carrying no predictive after the point-in-time gate; "
                    "dropped rather than fabricated")},
    ]


def build(target_season: int | None, target_week: int | None, *, now=None) -> dict:
    """Build every weekly artifact for the resolved target week. Pure of IO except the lake reads."""
    t0 = time.time()
    probe_season = target_season or datetime.now(timezone.utc).year
    src = _load_sources(probe_season)
    target = WS.resolve_target_week(src["schedule"], now=now)
    if target_season is not None or target_week is not None:
        target = WS.TargetWeek(
            season=target_season or target.season,
            week=target_week or target.week,
            first_kickoff=target.first_kickoff,
            last_reg_week=target.last_reg_week,
        )
        if target.season != probe_season:
            src = _load_sources(target.season)
    log.info("target: %s wk %s (first kickoff %s, last REG week %s)",
             target.season, target.week, target.first_kickoff, target.last_reg_week)

    # ⭐ CADENCE CHECK BEFORE ANY INVARIANT — see `assert_target_week_rosters_published`.
    n_roster = WS.assert_target_week_rosters_published(src["rosters"], target=target)
    log.info("target week carries %d game-day roster rows", n_roster)

    modeled, pit, frame = WS.build_serving_matrix(src, target=target)
    # ⛔ NON-VACUITY FIRST. A gate that examined nothing has not passed (NF1.7(a)).
    WS.assert_pit_gate_non_vacuous(pit)
    log.info("PIT gate: %d weeks / %d records checked, %d rows dropped",
             pit["weeks_checked"], pit["records_checked"], pit["rows_dropped"])

    indep = WS.assert_no_target_week_outcome(src, target=target, clean=modeled)
    log.info("outcome-independence proof: %d target rows × %d features unchanged under injection",
             indep["n_target_rows"], indep["n_features_compared"])

    tgt_mask = (modeled["season"] == target.season) & (modeled["week"] == target.week)
    target_rows = modeled.loc[tgt_mask].reset_index(drop=True)
    train = modeled.loc[modeled["gw"] < int(target_rows["gw"].iloc[0])].reset_index(drop=True)
    if train.empty:
        raise WS.WeeklyServingError("no training rows strictly before the target week")

    # ⛔ NF-INC-0916 — REFUSE TO TRAIN ON A WEEK WHOSE STAT LINE NEVER LANDED, and do it BEFORE the
    # fit rather than after: the fit is the nine-minute step, and there is nothing to learn from a
    # week of fabricated zeros except a wrong P(zero). The gate keys on COVERAGE ABSENCE, never on
    # zeros — the retained-zero convention stands, because a player who played and scored nothing
    # HAS a stat row and is a true zero.
    vintage = _vintage(src, train, target)
    stat_cov = WS.assert_training_stat_coverage(frame, target=target, vintage=vintage)
    log.info("[METRIC] weekly_train_stat_coverage_min=%.4f", stat_cov["min_coverage"])
    log.info("training stat coverage: %d week(s) checked, worst %s at %.4f (floor %.2f)",
             stat_cov["n_weeks_checked"], stat_cov["min_week"], stat_cov["min_coverage"],
             stat_cov["floor"])

    # The serving universe: everyone game-day rostered this week, byes included.
    fr = frame[(frame["season"] == target.season) & (frame["week"] == target.week)
               & frame["position"].isin(C.PROJECTED_POSITIONS)].copy()
    fr["is_bye"] = fr["label"].eq(WF.LABEL_BYE)
    universe = fr[["gsis_id", "position", "team", "is_bye"]].copy()
    ctx = WS._team_week_context(src["schedule"])
    ctx = ctx[(ctx["season"] == target.season) & (ctx["week"] == target.week)]
    universe = universe.merge(ctx[["team", "opponent", "is_home"]], on="team", how="left")
    universe = universe.drop_duplicates(subset=["gsis_id"]).reset_index(drop=True)

    basis = WS.form_basis(modeled, target=target, universe=universe)
    horizon = WS.frozen_form_horizon(basis, src["schedule"], target=target)
    frozen = WS.assert_frozen_form(basis, horizon)
    log.info("frozen-form horizon: %d rows over weeks %d..%d (%d frozen columns checked=%s)",
             frozen["n_horizon_rows"], target.week + 1, target.last_reg_week,
             frozen["n_frozen_columns"], frozen["checked"])

    score = pd.concat([target_rows, horizon], ignore_index=True) if len(horizon) else target_rows
    log.info("fitting the champion on %d train rows, scoring %d", len(train), len(score))
    t_fit = time.time()
    qmat, comps = WS.fit_and_predict(train, score)
    log.info("fit+predict took %.1fs", time.time() - t_fit)

    n_t = len(target_rows)
    target_q, horizon_q = qmat[:n_t], qmat[n_t:]
    ros = WS.build_ros(target_rows, target_q, horizon, horizon_q)
    qmap = {str(g): target_q[i] for i, g in enumerate(target_rows["gsis_id"].astype(str))}
    hist = (modeled[modeled["gw"] < int(target_rows["gw"].iloc[0])]
            .groupby(modeled["gsis_id"].astype(str)).size().to_dict())

    players = WS.build_players(universe, qmap, comps.iloc[:n_t], ros,
                               names=_names(src), hist_weeks=hist)
    served_ids = {p["id"] for p in players}
    n_bye = sum(1 for p in players if p["status"] == "bye")
    # A ROOKIE is a served player the champion's own prior-season prior marks as having none — the
    # same `prior_season_priors__rookie_flag` the model consumes, so the count cannot drift from the
    # feature it describes.
    rookie_ids = set(
        target_rows.loc[
            target_rows["prior_season_priors__rookie_flag"].astype(float) > 0.5, "gsis_id"
        ].astype(str)
    )
    n_rookies = sum(1 for p in players if p["id"] in rookie_ids)
    by_pos = {p: sum(1 for r in players if r["pos"] == p) for p in C.PROJECTED_POSITIONS}

    # The certified purge-equivalent train, so the containment is a NUMBER (the NF-W6c precedent).
    purged = int((modeled["gw"] <= int(target_rows["gw"].iloc[0]) - 1 - WP.PURGE_WEEKS).sum())
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    manifest = {
        "season": target.season, "week": target.week,
        "generated_at": generated_at,
        "projection_day": str(pd.Timestamp(target.first_kickoff).isoformat()),
        "n_players": len(players), "n_by_position": by_pos, "n_bye": n_bye,
        "n_rookies": n_rookies,
        "absences": _absences(frame, src, universe, served_ids, target),
        "pit_weeks_checked": int(pit["weeks_checked"]),
        "pit_records_checked": int(pit["records_checked"]),
        "pit_rows_dropped": int(pit["rows_dropped"]),
        "input_vintage": vintage,
        "lineage": {
            "served_version": WS.SERVED_VERSION,
            "base_model_version": WS.BASE_MODEL_VERSION,
            "point_model_version": WS.POINT_MODEL_VERSION,
            "interval_model_version": WS.INTERVAL_MODEL_VERSION,
        },
    }
    payload = {"season": target.season, "week": target.week, "generated_at": generated_at,
               "players": players}
    current = {
        "season": target.season, "week": target.week, "generated_at": generated_at,
        "manifest_key": C.weekly_manifest_key(target.season, target.week),
        "players_key": C.weekly_players_key(target.season, target.week),
    }

    # ── fail-closed: the invariants, then the contract ────────────────────────────────────────
    tt_s, tt_w = manifest["input_vintage"]["train_through_season"], manifest["input_vintage"]["train_through_week"]
    if tt_s is None or (int(tt_s), int(tt_w)) >= (target.season, target.week):
        raise WS.WeeklyServingError(
            f"training reaches {tt_s} wk {tt_w}, which is NOT strictly before the projected week "
            f"{target.season} wk {target.week} — a current-week outcome would be in the model."
        )
    # ⛔⛔ NF-INC-0916 — the manifest's own two-field proof. One owner, in `weekly_serving`, so the
    # refusal can be driven with the exact historical pair rather than only through a full build.
    sv = WS.assert_stat_vintage_reaches_training(vintage)
    log.info("stat vintage vs training boundary: %s", sv)

    if not players:
        raise WS.WeeklyServingError("zero players — refusing to publish an empty week")
    empty_pos = [p for p, n in by_pos.items() if n == 0]
    if empty_pos:
        raise WS.WeeklyServingError(
            f"position(s) {empty_pos} have ZERO projected players. The champion covers "
            f"{list(C.PROJECTED_POSITIONS)}; a projectable position missing from the artifact is "
            "the NF-K1 class — refusing to publish the gap."
        )
    # ⭐ COUNTS NON-NULL VALUES, NEVER KEYS (NF-WK-TD1). The pre-TD artifact carried all eleven
    # component KEYS and four of them were null on every row, so a fields-carried check passed on
    # the exact payload this refusal exists to stop.
    comp_line = WS.assert_component_line_complete(players)
    log.info("[METRIC] weekly_component_fields_complete=%d", comp_line["n_component_fields"])
    log.info("component line: %d field(s) non-null on all %d projected rows",
             comp_line["n_component_fields"], comp_line["n_projected"])
    # ⛔⛔ NF-INC-0917B — WHAT IS WRITTEN IS THE VALIDATED OBJECT, NEVER THE INPUT DICT.
    #
    # These three lines used to be `model_validate(x)` with the result DISCARDED, and that is the
    # whole of what took `/fantasy/weekly` down for 758 minutes on 2026-09-15. `framing` is
    # declared REQUIRED WITH A DEFAULT, so validating a dict that omits it PASSES — the default
    # lands on an object nobody keeps, and the raw dict goes to S3 without it. A declared field, a
    # passing validation, and nothing on the wire: validation that does not gate what ships is
    # decoration.
    #
    # ⭐ THE DEFAULTED FIELD IS THE DANGEROUS SHAPE, because validation can NEVER fail on its
    # absence. The published week-2 manifest was missing NINE of them — `season_type`,
    # `scoring_system_id`, the two interval levels, `ros_basis`, the two ros-sigma levels,
    # `positions` and `framing` — plus four inside `lineage`, and `players.json` was missing
    # `scoring_system_id`. Only ONE of those was ever dereferenced, and the reason the other nine
    # were survivable is a property of their TYPE rather than of anyone's care: an absent OBJECT
    # throws on its first property read, an absent SCALAR renders `undefined`. `framing` is the
    # only object-valued defaulted field on this contract.
    #
    # ⭐ REBINDING (rather than validating into a new name) is what makes this total: `stage()` and
    # `publish()` both write `built[...]`, so there is no path from here to S3 that does not pass
    # through these three assignments. Measured on the real published artifacts: 9 + 4 + 1 keys
    # ADDED, zero removed, zero values changed on any of 500 rows — the completeness moves, the
    # payload does not.
    manifest = C.NflWeeklyManifest.model_validate(manifest).model_dump()
    payload = C.NflWeeklyPayload.model_validate(payload).model_dump()
    current = C.NflWeeklyCurrent.model_validate(current).model_dump()
    C.assert_best_alpha_is_zero(manifest)

    cov = WS.train_serve_coverage(target_rows, train, target=target)
    for c, v in sorted(cov["serve"].items()):
        log.info("[METRIC] weekly_feature_coverage_%s=%.4f", c, v)
    log.info("[METRIC] weekly_serve_only_null_count=%d", len(cov["serve_only_null"]))
    if cov["null_in_both"]:
        # BENIGN, and named so it is not mistaken for the other list: null on the served week AND on
        # training's rows for the same week number, i.e. a structural property of this week (a
        # season-to-date feature in week 1), not a serving defect.
        log.info("· %d feature(s) null on the served week AND in training's week-%d rows "
                 "(structural, benign): %s",
                 len(cov["null_in_both"]), target.week, cov["null_in_both"])
    if cov["serve_only_null"]:
        # ⭐ THE ACTIONABLE LIST, and it should be EMPTY. A feature training had at this week number
        # and serving does not is the E7.9 train/serve class — the shape `opponent_grid_stub` was
        # written to close. ALERT-tier rather than fatal: the champion is NaN-tolerant, so refusing
        # to serve would be a worse outcome than serving with the gap NAMED.
        log.warning("⚠️ %d feature(s) are null ONLY at serve (training's week-%d rows have them): "
                    "%s — the E7.9 train/serve class; the model was fitted on a feature it is not "
                    "being given", len(cov["serve_only_null"]), target.week, cov["serve_only_null"])
    log.info("[METRIC] weekly_serving_build_seconds=%.1f", time.time() - t0)
    return {"target": target, "manifest": manifest, "payload": payload, "current": current,
            "diagnostics": {"pit": {k: v for k, v in pit.items() if k != "weeks_dropped"},
                            "pit_weeks_dropped": pit["weeks_dropped"],
                            "independence": indep, "frozen_form": frozen,
                            "n_train": int(len(train)),
                            "n_train_purged_equivalent": purged,
                            "n_score": int(len(score)),
                            "feature_coverage": cov,
                            "build_seconds": round(time.time() - t0, 1)}}


def assert_contract_shaped(built: dict) -> dict[str, int]:
    """REFUSE to write a blob that does not carry every field its contract declares.

    ⛔⛔ THE GATE IS ON THE WRITE, NOT ON THE BUILD, AND THAT IS THE WHOLE POINT (NF-INC-0917B).

    `build()` already serialises the validated model, so in the ordinary path this can never fire.
    It is here because the thing that has to be true is a property of what SHIPS, and a check that
    lives one function upstream of the write is a check a future caller can route around — which is
    precisely what happened: `NflWeeklyManifest.model_validate(manifest)` ran on every build for
    the whole life of this surface, passed every time, and `framing` still reached nobody, because
    validating and writing were two different objects. A guard that does not stand between the data
    and the wire is decoration.

    ⭐ IT ASKS A DIFFERENT QUESTION FROM `model_validate`. Validation asks "could this become a
    valid object" and a DEFAULTED field can never fail it by being absent. This asks "is every
    declared field actually here", which is the only question a published artifact has to answer.

    ⭐ AND IT IS WHY THE BUILDER HALF IS TESTABLE AT ALL. Reaching the real rebind otherwise costs
    a ~9-minute fit; this refusal can be driven in milliseconds with a degenerate `built` that no
    shipping writer would ever produce — which is the fixture the E2E suite could not construct and
    the reason the outage's guards were green throughout (NF-INC-0917's own finding).

    Returns the field COUNT checked per blob, so a caller can log a number rather than a promise —
    a gate that examined nothing has not passed (NF1.7(a)).
    """
    checked: dict[str, int] = {}
    problems: list[str] = []
    for name, model in (("manifest", C.NflWeeklyManifest),
                        ("payload", C.NflWeeklyPayload),
                        ("current", C.NflWeeklyCurrent)):
        blob = built.get(name)
        missing = C.missing_declared_fields(blob, model, where=name)
        checked[name] = len(C.declared_field_names(model))
        if missing:
            # Cap the report: a payload defect repeats on all ~500 rows and an unreadable refusal
            # is one nobody acts on.
            shown = missing[:12]
            tail = f" (+{len(missing) - len(shown)} more)" if len(missing) > len(shown) else ""
            problems.append(f"{name}: {shown}{tail}")
    if not any(checked.values()):
        raise WS.WeeklyServingError(
            "the contract-shape gate examined NO declared field — it cannot have passed"
        )
    if problems:
        raise WS.WeeklyServingError(
            "REFUSING to write: a declared field is absent from the blob about to be published. "
            "This is the NF-INC-0917 shape — validation that does not gate what ships is "
            f"decoration. {'; '.join(problems)}"
        )
    return checked


def stage(built: dict, out_dir: Path) -> list[Path]:
    shape = assert_contract_shaped(built)
    log.info("[METRIC] weekly_contract_fields_checked=%d", sum(shape.values()))
    t = built["target"]
    week_dir = out_dir / str(t.season) / str(t.week)
    week_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, blob in (("manifest.json", built["manifest"]), ("players.json", built["payload"])):
        p = week_dir / name
        p.write_text(json.dumps(blob, indent=2, sort_keys=False))
        written.append(p)
    p = out_dir / str(t.season) / "current.json"
    p.write_text(json.dumps(built["current"], indent=2))
    written.append(p)
    d = week_dir / "diagnostics.json"
    d.write_text(json.dumps(built["diagnostics"], indent=2, default=str))
    written.append(d)
    return written


def publish(built: dict, bucket: str, *, do_publish: bool) -> None:
    """Upload the three SERVED blobs. `diagnostics.json` is staged locally and never published —
    it is the build's own record, not part of the contract."""
    # ⚠️ BEFORE the dry-run early return (the NF-INJ3B reading): a `--dry-run` that skips the
    # refusal is a rehearsal of a different program, and the one run an operator uses to convince
    # themselves the publish is safe is exactly the one that must exercise the gate.
    assert_contract_shaped(built)
    t = built["target"]
    keys = {
        C.weekly_manifest_key(t.season, t.week): built["manifest"],
        C.weekly_players_key(t.season, t.week): built["payload"],
        C.weekly_current_key(t.season): built["current"],
    }
    if not do_publish:
        log.info("[DRY-RUN] would upload %d object(s) to s3://%s/fantasy/nfl/{%s} — pass --publish "
                 "to reach the LIVE prod api-cache", len(keys), bucket, ", ".join(keys))
        return
    import boto3

    # Plain (key-less) client — instance-role / AWS_PROFILE safe; never pass a possibly-None
    # aws_access_key_id (test_boto3_credential_lint.py). us-east-1 pins the api-cache bucket so a
    # laptop AWS_DEFAULT_REGION=us-east-2 (the ML-artifacts bucket) cannot misroute the put.
    s3 = boto3.client("s3", region_name="us-east-1")
    log.warning("🚨 PUBLISHING TO LIVE PROD api-cache — s3://%s/fantasy/nfl/ (%d objects)",
                bucket, len(keys))
    for rel, blob in keys.items():
        s3.put_object(Bucket=bucket, Key=f"fantasy/nfl/{rel}",
                      Body=json.dumps(blob).encode(), ContentType="application/json")
    log.info("published %d weekly object(s) for %s wk %s", len(keys), t.season, t.week)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build/publish the NFL weekly serving artifacts")
    ap.add_argument("--season", type=int, default=None, help="override the resolved target season")
    ap.add_argument("--week", type=int, default=None, help="override the resolved target week")
    ap.add_argument("--out", default=str(_STAGING))
    ap.add_argument("--s3-bucket", default=None,
                    help="api-cache bucket; a bucket alone does NOT upload — pass --publish too")
    ap.add_argument("--publish", action="store_true",
                    help="actually upload to the LIVE prod api-cache")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    import os
    # ⭐ `--publish` REQUIRES AN EXPLICIT `--s3-bucket`, and will NOT inherit `$CACHE_BUCKET`.
    #
    # NF1.7's lesson is that `--publish` with NO bucket resolved must be a hard error rather than a
    # silent no-op. This is the SAME hazard facing the other way, and it is the one that actually
    # bit during this story's build: `$CACHE_BUCKET` is set in a normal working shell, so a
    # `--publish` intended to exercise the REFUSAL path resolved a bucket from the environment and
    # reached the LIVE prod api-cache instead. An outward-facing action must not have its target
    # chosen by an environment variable the caller cannot see in the command they typed — that is
    # the documented-but-never-set class (`W7B_LAKEHOUSE_S3`) pointed at a publish.
    #
    # ⚠️ `$CACHE_BUCKET` IS STILL HONOURED FOR STAGING, which is the safe direction: a run without
    # `--publish` uses it only to print what WOULD upload. Only the destination of a real write has
    # to be spelled out.
    bucket = args.s3_bucket or os.environ.get("CACHE_BUCKET")
    if args.publish and not args.s3_bucket:
        raise SystemExit(
            "--publish requires --s3-bucket to be passed EXPLICITLY; it deliberately does not "
            "inherit $CACHE_BUCKET"
            + (f" (which is currently set to {os.environ['CACHE_BUCKET']!r})"
               if os.environ.get("CACHE_BUCKET") else " (which is unset)")
            + ".\n\nA publish reaches the LIVE prod api-cache, so its target must be named in the "
            "command that performs it rather than inherited from the shell. Re-run with:\n"
            "  --s3-bucket credence-prod-s3-api-cache --publish"
        )

    try:
        built = build(args.season, args.week)
    except WS.WeeklyRostersNotPublished as exc:
        # ⭐ A DISTINCT EXIT CODE, not a log line the caller has to parse. The Dagster op maps this
        # to a clean skip; an exit code cannot be faked by a message and cannot be missed by a regex
        # that drifted. ⛔ And it is NOT exit 0: "published" and "correctly declined to publish" are
        # different outcomes and must stay distinguishable at the process boundary (the
        # ALERT-loud-but-continue tier — a graceful skip that hides work is never silent).
        log.warning("⏸️  %s", exc)
        log.warning("[METRIC] weekly_serving_skipped=awaiting_rosters")
        return EXIT_AWAITING_ROSTERS
    written = stage(built, Path(args.out))
    log.info("staged %d file(s) under %s", len(written), args.out)
    if bucket:
        publish(built, bucket, do_publish=args.publish)
    else:
        log.warning("no --s3-bucket / $CACHE_BUCKET — staged locally only; the weekly API will 404 "
                    "until these are uploaded")
    d = built["diagnostics"]
    log.info("DONE %s wk %s — %d players (%d bye), train %d (purged-equivalent %d), %.1fs",
             built["target"].season, built["target"].week, built["manifest"]["n_players"],
             built["manifest"]["n_bye"], d["n_train"], d["n_train_purged_equivalent"],
             d["build_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
