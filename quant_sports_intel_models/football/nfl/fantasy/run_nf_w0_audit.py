"""run_nf_w0_audit.py — NF-W0 V0 gate: build + certify the weekly PIT training/serving frame.

Reads the live NFL lake, builds the player-week spine, attaches versioned labels with the zeros
RETAINED, measures coverage by year/position, runs the train/serve parity test, and emits the seven
status fields the delivery epic names.

⛔ NO MODELLING. This is a gate: it decides whether NF-W1 may start, and with WHICH features.

Run (LAPTOP — reads the S3 lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w0_audit \\
        --seasons 2016-2025 --out quant_sports_intel_models/football/nfl/fantasy/ablation_results

The parity test is the load-bearing part and is deliberately NOT a tautology. The TRAINING features
are assembled from the full lake; the SERVING features are assembled by the SAME function from a
lake slice TRUNCATED at the projection week. A correctly-lagged feature is identical either way; a
feature that peeks at the target week differs the moment the truncation removes it. That makes the
test capable of going red, which a same-input-same-output comparison never is.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF

log = logging.getLogger("nfl.fantasy.nf_w0")

# The advanced-stack floor: NGS + pbp_participation both begin 2016 (N0.1 §7).
DEFAULT_SEASONS = (2016, 2025)


def _lake():
    from quant_sports_intel_models.football.nfl.ingest.query_lake import q, delta
    return q, delta


def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


# ── Lake reads ───────────────────────────────────────────────────────────────────────────────────
def load_sources(seasons: list[int], season_type: str = "REG") -> dict[str, pd.DataFrame]:
    """Pull the minimum column set the frame needs. Narrow reads on purpose (E9.26b: a wide read of
    a 145-col table is the fragile thing; we need 8 columns)."""
    q, delta = _lake()
    lo, hi = min(seasons), max(seasons)
    yrs = f"between {lo} and {hi}"

    rosters = q(f"""
        select season, week, team, position, status, gsis_id
        from {delta('weekly_rosters')}
        where season {yrs} and game_type = '{season_type}' and gsis_id is not null
    """)
    # NF-W0b: the identity universe the snap ladder resolves INTO. Read season-UNSCOPED on purpose
    # — a vendor id is a stable property of a player, so a season whose roster row omits `pfr_id`
    # is still resolvable from another season's row. That single widening is what recovers the
    # high-value cohort (see `entity/__init__.py`).
    identity = q(f"""
        select season, week, team, position, gsis_id,
               coalesce(full_name, concat(first_name, ' ', last_name)) as full_name,
               espn_id, sportradar_id, yahoo_id, rotowire_id, pff_id, pfr_id,
               fantasy_data_id, sleeper_id, esb_id, gsis_it_id, smart_id
        from {delta('weekly_rosters')}
        where gsis_id is not null
    """)
    schedule = q(f"""
        select season, week, home_team, away_team, gameday, roof, surface, div_game
        from {delta('schedules')}
        where season {yrs} and game_type = '{season_type}'
    """)
    stats = q(f"""
        select season, week, player_id, position, fantasy_points_ppr,
               carries, targets, attempts, receptions
        from {delta('stats_player_week')}
        where season {yrs} and season_type = '{season_type}'
    """)
    # 🐛 NF-W0b (v3 §12A): this read used to be an INNER join from `snap_counts` to a per-SEASON
    # (pfr_id, gsis_id) bridge — which silently DROPPED 19–46% of snap rows per season, because
    # `weekly_rosters.pfr_id` is 25–53% NULL in any given season. A dropped snap row is invisible:
    # the frame simply has fewer rows and every coverage number still reads healthy. The SQL now
    # reads snaps RAW and hands identity resolution to the entity service, which runs the full
    # §12A ladder rather than the one sparse vendor column (19.2% unresolved → ~1%).
    snaps_raw = q(f"""
        select season, week, team, position, player, pfr_player_id, offense_snaps, offense_pct
        from {delta('snap_counts')}
        where season {yrs} and game_type = '{season_type}'
    """)
    snaps = _resolve_snap_identities(snaps_raw, identity)
    return {"rosters": rosters, "schedule": schedule, "stats": stats, "snaps": snaps}


def _resolve_snap_identities(snaps_raw: pd.DataFrame, identity: pd.DataFrame) -> pd.DataFrame:
    """Attach `gsis_id` to every snap row via the NF-W0b ladder — dropping NOTHING.

    Returns the snap frame with a `gsis_id` column that is NULL where the identity is unresolved.
    Downstream feature assembly groups by `gsis_id`, so an unattributed row contributes to no
    feature (correct — we do not know whose snaps they are) while remaining COUNTED and visible,
    which is the difference between a measured residual and a silent drop.
    """
    from datetime import datetime, timezone

    from quant_sports_intel_models.football.nfl.entity.crosswalk import build_crosswalk
    from quant_sports_intel_models.football.nfl.entity.snap_bridge import resolve_snap_counts

    if snaps_raw.empty:
        return snaps_raw.assign(gsis_id=pd.NA)

    crosswalk = build_crosswalk(
        identity, last_verified_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    targets = identity.rename(
        columns={"gsis_id": "canonical_player_id", "full_name": "player_name"}
    )[["canonical_player_id", "player_name", "team", "position", "season", "week"]]

    resolved, report = resolve_snap_counts(snaps_raw, targets=targets, crosswalk=crosswalk)
    if report.silent_drop_count:  # pragma: no cover — the resolver asserts row preservation
        raise AssertionError(f"snap resolution dropped {report.silent_drop_count} rows")
    if report.unmatched_rate:
        # ALERT-tier: every row is retained, so this degrades coverage rather than the run — but a
        # silent skip here is exactly the class NF-W0b exists to remove, so it is never quiet.
        log.warning(
            "ALERT [nfl/fantasy/nf_w0] %d of %d snap rows (%.2f%%) have no canonical identity — "
            "RETAINED with a NULL gsis_id (never dropped, never zeroed; v3 §12A silent_drop=0); "
            "%d of them are high-value (skill starters). Run "
            "`entity.run_entity_resolution --report` for the ladder + QA queue.",
            report.n_output_rows - report.n_matched, report.n_output_rows,
            100.0 * report.unmatched_rate, report.high_value_unmatched_count,
        )
    return resolved.rename(columns={"canonical_player_id": "gsis_id"})


# ── Feature assembly (the parity subject) ────────────────────────────────────────────────────────
# A SMALL but genuine lagged feature block. NF-W1 will grow this; NF-W0's job is to prove the
# assembly is identical under truncation, which is a property of the CODE PATH, not of its width.
PARITY_FEATURES = ["prior_week_box", "snap_share"]


def assemble_features(
    stats: pd.DataFrame,
    snaps: pd.DataFrame,
    *,
    season: int,
    week: int,
    lookback: int = 4,
) -> pd.DataFrame:
    """Assemble the week-`week` feature row for every player, from weeks STRICTLY BEFORE `week`.

    The `< week` bound is the single PIT rule this function enforces, and every caller — training or
    serving — goes through it. `prior_week_box` and `snap_share` are named to match
    `ALLOWED_FEATURE_CONTRACT`, so `assert_no_leakage` can check provenance by name."""
    lo = max(1, week - lookback)
    s = stats[(stats["season"] == season) & (stats["week"] < week) & (stats["week"] >= lo)]
    n = snaps[(snaps["season"] == season) & (snaps["week"] < week) & (snaps["week"] >= lo)]

    box = (
        s.assign(_opp=s[["carries", "targets"]].fillna(0).sum(axis=1))
        .groupby("player_id", as_index=False)["_opp"].mean()
        .rename(columns={"player_id": "gsis_id", "_opp": "prior_week_box"})
    )
    snp = (
        n.groupby("gsis_id", as_index=False)["offense_pct"].mean()
        .rename(columns={"offense_pct": "snap_share"})
    )
    out = box.merge(snp, on="gsis_id", how="outer")
    out["season"] = season
    out["week"] = week
    return out[["season", "week", "gsis_id", *PARITY_FEATURES]].sort_values("gsis_id").reset_index(drop=True)


def _leaky_assemble(stats: pd.DataFrame, snaps: pd.DataFrame, *, season: int, week: int) -> pd.DataFrame:
    """A DELIBERATELY leaky assembly — the canary. Identical to `assemble_features` except the bound
    is `<= week`, so it reads the target week's own box score."""
    s = stats[(stats["season"] == season) & (stats["week"] <= week)]
    n = snaps[(snaps["season"] == season) & (snaps["week"] <= week)]
    box = (
        s.assign(_opp=s[["carries", "targets"]].fillna(0).sum(axis=1))
        .groupby("player_id", as_index=False)["_opp"].mean()
        .rename(columns={"player_id": "gsis_id", "_opp": "prior_week_box"})
    )
    snp = (
        n.groupby("gsis_id", as_index=False)["offense_pct"].mean()
        .rename(columns={"offense_pct": "snap_share"})
    )
    out = box.merge(snp, on="gsis_id", how="outer")
    out["season"], out["week"] = season, week
    return out[["season", "week", "gsis_id", *PARITY_FEATURES]].sort_values("gsis_id").reset_index(drop=True)


def run_parity(sources: dict[str, pd.DataFrame], season: int, week: int) -> dict:
    """Training assembly (full lake) vs serving assembly (lake truncated at the projection week).

    ⭐ TWO-SIDED. A parity PASS only means something if the same instrument is shown to FAIL on a
    known-leaky assembly against the SAME live data (NF1.7 (a): a check that cannot fail is
    vacuously true). So the run also scores a canary whose only difference is `<= week` instead of
    `< week`; `parity_canary` must read DETECTED. If it reads BLIND, the PASS above is worthless and
    the frame is NOT certified."""
    stats, snaps = sources["stats"], sources["snaps"]
    training = assemble_features(stats, snaps, season=season, week=week)
    # The SERVING view of the world at the Tuesday of `week`: nothing from week >= `week` exists yet.
    truncated_stats, truncated_snaps = stats[stats["week"] < week], snaps[snaps["week"] < week]
    serving = assemble_features(truncated_stats, truncated_snaps, season=season, week=week)
    parity = WF.train_serve_parity(training, serving, compare_columns=PARITY_FEATURES)
    parity["projection_season"] = season
    parity["projection_week"] = week

    canary_train = _leaky_assemble(stats, snaps, season=season, week=week)
    canary_serve = _leaky_assemble(truncated_stats, truncated_snaps, season=season, week=week)
    canary = WF.train_serve_parity(canary_train, canary_serve, compare_columns=PARITY_FEATURES)
    parity["parity_canary"] = "DETECTED" if canary["train_serve_parity"] == "FAIL" else "BLIND"
    parity["parity_canary_detail"] = canary["failures"]
    return parity


# ── Runner ───────────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W0 weekly PIT frame certification (no modelling)")
    ap.add_argument("--seasons", default=f"{DEFAULT_SEASONS[0]}-{DEFAULT_SEASONS[1]}")
    ap.add_argument("--season-type", default="REG")
    ap.add_argument("--parity-season", type=int, default=2024)
    ap.add_argument("--parity-week", type=int, default=10)
    ap.add_argument("--out", default="quant_sports_intel_models/football/nfl/fantasy/ablation_results")
    args = ap.parse_args()

    seasons = _parse_seasons(args.seasons)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    log.info("reading lake for seasons %s…", seasons)
    src = load_sources(seasons, args.season_type)
    for k, v in src.items():
        log.info("  %-9s %8d rows", k, len(v))

    spine = WF.build_spine(src["rosters"], src["schedule"])
    log.info("spine rows: %d", len(spine))

    frame = WF.attach_labels(
        spine, src["stats"],
        label_version="v1.nflverse.stats_player_week",
        label_as_of_timestamp=stamp,
        scoring_system_id="ppr",
        snaps=src["snaps"],
    )
    log.info("labelled frame rows: %d  (zeros retained: %d)", len(frame), int(frame["is_zero"].sum()))

    coverage = WF.coverage_by_year_position(frame)
    parity = run_parity(src, args.parity_season, args.parity_week)
    log.info("train/serve parity: %s %s", parity["train_serve_parity"], parity["failures"] or "")
    log.info("parity canary (must be DETECTED): %s", parity["parity_canary"])

    # Fail-closed provenance check on the feature block we actually assembled.
    leak_status = "PASS"
    try:
        WF.assert_no_leakage(frame, feature_columns=PARITY_FEATURES,
                             projection_week=args.parity_week)
    except WF.LeakageError as exc:  # pragma: no cover - a live regression, not a unit path
        leak_status = f"FAIL: {exc}"
        log.error("leakage guard: %s", leak_status)

    label_mix = frame["label"].value_counts().to_dict()
    known_missingness = {
        "injury_date_modified_dropped_upstream_from": 2025,
        "ngs_weekly_is_qualifying_players_only": True,
        "depth_charts_schema_replaced_at": 2025,
        "weather_forecast_not_ingested": True,
        "market_snapshots_landed_seasons": "2020-2024 (closing only)",
        "label_mix": {str(k): int(v) for k, v in label_mix.items()},
    }
    # ⛔ Certification requires all three: the leakage guard passes, parity passes, AND the canary
    # proves the parity instrument was capable of failing on this data. A BLIND canary means the
    # parity PASS carries no information, so it blocks exactly as a FAIL would.
    certified = (
        leak_status == "PASS"
        and parity["train_serve_parity"] == "PASS"
        and parity["parity_canary"] == "DETECTED"
    )
    status = WF.build_status(
        frame, parity,
        training_status="CERTIFIED" if certified else "BLOCKED",
        serving_status="CERTIFIED_TIER0_LAGGED" if certified else "BLOCKED",
        known_missingness=known_missingness,
    )

    cov_path = out_dir / "nf_w0_coverage_by_year_position.csv"
    coverage.to_csv(cov_path, index=False)
    status_path = out_dir / "nf_w0_frame_status.json"
    payload = {
        "generated_at": stamp,
        "seasons": seasons,
        "season_type": args.season_type,
        "n_frame_rows": int(len(frame)),
        "n_zero_rows": int(frame["is_zero"].sum()),
        "leakage_guard": leak_status,
        "parity": parity,
        **status.to_dict(),
    }
    status_path.write_text(json.dumps(payload, indent=2, default=str))
    contract_path = out_dir / "nf_w0_feature_contract.csv"
    pd.concat([
        WF.contract_as_frame(WF.ALLOWED_FEATURE_CONTRACT).assign(contract="allowed"),
        WF.contract_as_frame(WF.DEFERRED_FEATURE_CONTRACT).assign(contract="deferred"),
    ], ignore_index=True).to_csv(contract_path, index=False)

    log.info("wrote %s", cov_path)
    log.info("wrote %s", status_path)
    log.info("wrote %s", contract_path)
    print(json.dumps({k: payload[k] for k in
                      ("n_frame_rows", "n_zero_rows", "leakage_guard",
                       "weekly_training_frame_status", "weekly_serving_frame_status",
                       "train_serve_parity")}, indent=2))


if __name__ == "__main__":
    main()
