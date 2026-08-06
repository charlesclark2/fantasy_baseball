"""run_entity_resolution.py — NF-W0b: the lake driver for the entity-resolution service.

Three modes, all LAPTOP-side, read-only against the S3 lake (Snowflake-free, DuckDB/Delta):

  --report      Build the crosswalk, run the ladder over `snap_counts` (and props when present),
                emit the four §12A monitors per season, and write the QA review queue.
  --calibrate   The BLIND-VENDOR-ID CONTROL that sets the fuzzy threshold (see below).
  --write-crosswalk  Persist the crosswalk artifact.

⭐ WHY `--calibrate` EXISTS, AND WHY IT MEASURES ACCURACY RATHER THAN YIELD.

A fuzzy rung is trivially easy to tune the wrong way: lower the threshold, watch `unmatched_rate`
fall, declare victory. But the rate that falls is a YIELD, and yield says nothing about whether the
new matches are RIGHT — a fuzzy join that confidently merges the wrong players reports a better
unmatched_rate than one that honestly abstains. Optimising the monitor rather than the outcome is
the same inversion the program has hit before with a selection metric (E2.1-r), one layer down.

The control: take the snap rows that tier 1 ALREADY resolves — where the vendor id gives a known,
independent answer — HIDE that vendor id, re-run the ladder so those rows must come through the
name rungs, and compare the answer to the vendor id's. That yields a real confusion count per
candidate threshold:

    agree      the fuzzy rung reproduced the vendor id's answer
    disagree   it produced a DIFFERENT canonical player — a wrong merge
    abstain    it declined to match

The threshold is then chosen as the loosest value whose `disagree` count stays at/near zero, and
`disagree` is reported alongside the yield so a future retune cannot quietly trade accuracy for
coverage. This is the direct analogue of the repo's oracle-floor discipline: an anchor whose
answer is known independently, used to police the instrument.

Run (LAPTOP — reads the S3 lake, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.entity.run_entity_resolution \\
        --seasons 2022-2025 --report \\
        --out quant_sports_intel_models/football/nfl/fantasy/ablation_results

    uv run python -m quant_sports_intel_models.football.nfl.entity.run_entity_resolution \\
        --seasons 2022-2025 --calibrate \\
        --out quant_sports_intel_models/football/nfl/fantasy/ablation_results
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .crosswalk import build_crosswalk, load_reviewed_crosswalk, vendor_id_coverage
from .monitors import DEFAULT_THRESHOLDS, ResolutionThresholds, qa_records
from .resolver import METHOD_FUZZY_CONSTRAINED, ResolutionSpec, resolve
from .snap_bridge import SNAP_SPEC, resolve_snap_counts, skill_starter_mask

log = logging.getLogger("nfl.entity.run")

CANDIDATE_THRESHOLDS = (0.80, 0.84, 0.86, 0.88, 0.90, 0.92, 0.95)


def _lake():
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    return q, delta


def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


def load_frames(seasons: list[int]) -> dict[str, pd.DataFrame]:
    """Narrow reads only — the columns the ladder needs and nothing else (the E9.26b rule: a wide
    read of a many-column table is the fragile part)."""
    q, delta = _lake()
    lo, hi = min(seasons), max(seasons)
    yrs = f"between {lo} and {hi}"

    rosters = q(f"""
        select season, week, team, position, gsis_id,
               coalesce(full_name, concat(first_name, ' ', last_name)) as full_name,
               espn_id, sportradar_id, yahoo_id, rotowire_id, pff_id, pfr_id,
               fantasy_data_id, sleeper_id, esb_id, gsis_it_id, smart_id
        from {delta('weekly_rosters')}
        where season {yrs} and gsis_id is not null
    """)
    snaps = q(f"""
        select season, week, team, position, player, pfr_player_id,
               offense_snaps, offense_pct, st_snaps as special_teams_snaps, st_pct as special_teams_pct
        from {delta('snap_counts')}
        where season {yrs} and pfr_player_id is not null
    """)
    return {"rosters": rosters, "snaps": snaps}


def _targets(rosters: pd.DataFrame) -> pd.DataFrame:
    t = rosters.rename(columns={"gsis_id": "canonical_player_id", "full_name": "player_name"})
    return t[["canonical_player_id", "player_name", "team", "position", "season", "week"]]


def run_report(
    seasons: list[int], out_dir: Path, thresholds: ResolutionThresholds = DEFAULT_THRESHOLDS
) -> dict:
    frames = load_frames(seasons)
    rosters, snaps = frames["rosters"], frames["snaps"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    crosswalk = build_crosswalk(rosters, last_verified_timestamp=now)
    reviewed = load_reviewed_crosswalk()
    targets = _targets(rosters)

    per_season, qa_frames = [], []
    for season in sorted(seasons):
        s = snaps[snaps["season"] == season]
        if s.empty:
            continue
        resolved, report = resolve_snap_counts(
            s, targets=targets[targets["season"] == season],
            crosswalk=crosswalk, reviewed=reviewed, thresholds=thresholds,
        )
        row = report.to_dict()
        row["season"] = season
        per_season.append(row)
        qa_frames.append(
            qa_records(
                resolved, source_name=f"{SNAP_SPEC.source_name}@{season}",
                context_columns=["season", "week", "team", "player", "position", "offense_pct"],
            )
        )
        log.info(
            "[nfl/entity] season=%s unmatched=%.4f low_conf=%s high_value_unmatched=%d "
            "silent_drop=%d fail_closed=%s",
            season, row["unmatched_rate"] or 0.0, row["low_confidence_rate"],
            row["high_value_unmatched_count"], row["silent_drop_count"], row["fail_closed"],
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    monitors = pd.DataFrame(per_season)
    monitors.to_csv(out_dir / "nf_w0b_entity_monitors.csv", index=False)
    if qa_frames:
        qa = pd.concat(qa_frames, ignore_index=True)
        qa.to_csv(out_dir / "nf_w0b_entity_qa_queue.csv", index=False)
    coverage = vendor_id_coverage(rosters)
    coverage.to_csv(out_dir / "nf_w0b_vendor_id_coverage.csv", index=False)

    summary = {
        "generated_at": now,
        "seasons": sorted(seasons),
        "n_crosswalk_rows": int(len(crosswalk)),
        "n_reviewed_rows": int(len(reviewed)),
        "any_fail_closed": bool(monitors["fail_closed"].any()) if not monitors.empty else None,
        "max_silent_drop_count": int(monitors["silent_drop_count"].max()) if not monitors.empty else None,
        "per_season": per_season,
    }
    (out_dir / "nf_w0b_entity_report.json").write_text(json.dumps(summary, indent=2))
    return summary


def run_calibration(seasons: list[int], out_dir: Path) -> pd.DataFrame:
    """The blind-vendor-id control. See the module docstring for why yield alone is not enough."""
    frames = load_frames(seasons)
    rosters, snaps = frames["rosters"], frames["snaps"]
    targets = _targets(rosters)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    crosswalk = build_crosswalk(rosters, last_verified_timestamp=now)

    # The control population: snap rows tier 1 resolves TODAY, so a known independent answer exists.
    truth, _ = resolve_snap_counts(snaps, targets=targets, crosswalk=crosswalk)
    known = truth[truth["match_method"] == "stable_vendor_id"].copy()
    if known.empty:
        raise RuntimeError("no tier-1 rows to calibrate against")
    known = known.rename(columns={"canonical_player_id": "_truth"})

    # Blind the vendor id so those rows MUST come through the name rungs.
    blind = known.drop(columns=[c for c in truth.columns if c in ("canonical_player_id",
                                                                  "match_method", "match_confidence",
                                                                  "match_score", "source_degraded")],
                       errors="ignore").copy()
    blind["pfr_player_id"] = pd.NA

    rows = []
    for thr in CANDIDATE_THRESHOLDS:
        spec = ResolutionSpec(**{**SNAP_SPEC.__dict__, "fuzzy_threshold": thr})
        got = resolve(
            blind.drop(columns=["_truth"]), spec=spec, crosswalk=None, reviewed=None,
            targets=targets, target_name_column="player_name",
            target_team_column="team", target_position_column="position",
        )
        got["_truth"] = blind["_truth"].values
        fuzzy = got[got["match_method"] == METHOD_FUZZY_CONSTRAINED]
        matched = got["canonical_player_id"].notna()
        rows.append({
            "fuzzy_threshold": thr,
            "n_control_rows": int(len(got)),
            "n_matched_any_tier": int(matched.sum()),
            "n_fuzzy": int(len(fuzzy)),
            "fuzzy_agree": int((fuzzy["canonical_player_id"] == fuzzy["_truth"]).sum()),
            "fuzzy_disagree": int((fuzzy["canonical_player_id"] != fuzzy["_truth"]).sum()),
            "overall_disagree": int((matched & (got["canonical_player_id"] != got["_truth"])).sum()),
            "abstain": int((~matched).sum()),
        })
    cal = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    cal.to_csv(out_dir / "nf_w0b_fuzzy_threshold_calibration.csv", index=False)
    return cal


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", default="2022-2025")
    ap.add_argument("--out", default="quant_sports_intel_models/football/nfl/fantasy/ablation_results")
    ap.add_argument("--report", action="store_true", help="run the ladder + the four monitors")
    ap.add_argument("--calibrate", action="store_true", help="blind-vendor-id fuzzy calibration")
    ap.add_argument("--write-crosswalk", action="store_true", help="persist the crosswalk artifact")
    ap.add_argument("--max-unmatched-rate", type=float, default=DEFAULT_THRESHOLDS.max_unmatched_rate)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when any season fails closed (the acceptance gate)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    seasons = _parse_seasons(args.seasons)
    out_dir = Path(args.out)
    thresholds = ResolutionThresholds(max_unmatched_rate=args.max_unmatched_rate)

    if args.calibrate:
        cal = run_calibration(seasons, out_dir)
        print(cal.to_string(index=False))

    if args.write_crosswalk:
        frames = load_frames(seasons)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cw = build_crosswalk(frames["rosters"], last_verified_timestamp=now)
        out_dir.mkdir(parents=True, exist_ok=True)
        cw.to_parquet(out_dir / "nf_w0b_canonical_crosswalk.parquet", index=False)
        print(f"[METRIC] crosswalk_rows={len(cw)}")

    if args.report or not (args.calibrate or args.write_crosswalk):
        summary = run_report(seasons, out_dir, thresholds=thresholds)
        print(json.dumps(summary, indent=2))
        worst = max((s["silent_drop_count"] for s in summary["per_season"]), default=0)
        print(f"[METRIC] silent_drop_count={worst}")
        if args.strict and (summary.get("any_fail_closed") or worst > 0):
            log.warning("ALERT [nfl/entity] entity resolution FAILED CLOSED — see the report")
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
