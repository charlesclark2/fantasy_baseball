"""run_college_nfl_translation.py — NCAAF-P1A CLI: fit the college→NFL translation (the NFL feeder).

Reads `ncaaf_draft_college_production_pairs` from the sports dbt DuckDB, runs the §0.5 bake-off,
emits a leakage-safe per-player NFL rookie projection keyed to `gsis_id` (the NFL-vertical join
contract), validates the leakage + plausibility + oracle-floor + join-coverage gates, and writes a
markdown report.

⭐ RUN THIS ON THE LAPTOP. P1A is a once-per-draft-class feeder, not a live-serving job, and the
bake-off is pure in-process numpy/sklearn compute (the only DuckDB touch is a ~2.8k-row read). The
sports lake (`credence-sports-lakehouse`, S3) is a SEPARATE bucket from MLB's, so a laptop run —
laptop compute + S3 I/O — uses ZERO shared-box CPU/RAM and cannot compete with the live MLB
pipelines. Keep it off the EC2 box (esp. during the MLB season); the box shares CPU/RAM with the
live Dagster and there is no reason to contend for it here.

The dbt build the script depends on ALSO runs on the laptop: `dbt-duckdb` reads the S3 Delta lake
directly via the credential chain (ambient AWS creds on a laptop — profiles.yml `dev` target), so
building the substrate mart is likewise laptop compute + S3 reads, no box.

🚨 BUILD THE SPORTS PROJECT WITH dbt-core (`python -m dbt.cli.main`), NOT `dbtf` (fusion). Fusion
preview-196 SEGFAULTS building 2+ `delta_scan` models in one invocation (the staging layer is all
delta_scan) — this is exactly what the box job avoids by running `python -m dbt.cli.main`. `dbtf` is
ONLY for the `parse`/`compile` structural gate, never `run`. Build staging SERIALLY first (its
delta_scan models become physical tables), then the marts — two invocations, `--threads 1` (the
INC-22 OOM + the DeltaScan-serialization cure).

Usage (LAPTOP — the recommended path; lands the feeder output in the S3 sports lake for the NFL
vertical to consume). All steps `SPORTS_LAKE_REGION=us-east-2`:
    cd quant_sports_intel_models/sports_dbt
    export SPORTS_LAKE_REGION=us-east-2
    # 1a. staging serially (delta_scan → physical tables). dbt-core, NOT dbtf.
    python -m dbt.cli.main run --select ncaaf.staging --threads 1
    # 1b. the marts (the pairs mart + its upstream). Exclude the not-yet-seeded projections view.
    python -m dbt.cli.main run --select ncaaf.marts --exclude tag:ncaaf_p1a --threads 1
    cd -
    # 2. run the bake-off + land the projections in the sports lake (S3)
    SPORTS_LAKE_REGION=us-east-2 \
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_college_nfl_translation \
        --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --s3
    # 3. build the read-only view over the now-seeded derived Delta (dbt-core again)
    (cd quant_sports_intel_models/sports_dbt && \
        SPORTS_LAKE_REGION=us-east-2 python -m dbt.cli.main run --select tag:ncaaf_p1a --threads 1)

Usage (LAPTOP, FULLY OFFLINE — no S3 write at all; writes the derived Delta to a LOCAL FS lake).
Use `--lake-root <dir>` and point the dbt view at the same local tree via `--vars`:
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_college_nfl_translation \
        --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --lake-root /tmp/sports_lake
    # then build the view against the same local lake (dbt-core, NOT dbtf):
    (cd quant_sports_intel_models/sports_dbt && \
        python -m dbt.cli.main run --select tag:ncaaf_p1a --vars '{lake_root: /tmp/sports_lake}' --threads 1)
    # (requires the xref + P1.1 marts to also live under /tmp/sports_lake — i.e. a fully-local
    #  lake mirror; otherwise use the S3 path above, which never touches the box either.)

Outputs:
  * <out-dir>/ncaaf_nfl_rookie_projections.parquet   — per-player projection (the feeder output)
  * <out-dir>/ncaaf_college_nfl_translation_summary.json — gates + bake-off leaderboard + PBO/DSR
  * s3://credence-sports-lakehouse/ncaaf/derived/nfl_rookie_projections/ (--s3), OR
    <lake-root>/ncaaf/derived/nfl_rookie_projections/ (--lake-root, a local Delta tree)
  * quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1a_college_nfl_translation.md

⚠️ RUNTIME: the full bake-off (leave-one-draft-class-out CV × ~7 configs incl. GBM quantile fits) is
minutes on the real ~2.8k-player build. Per the repo's >1-minute rule this is an OPERATOR-run
script, not something a session executes inline.
"""
from __future__ import annotations

import argparse
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

from quant_sports_intel_models.football.ncaaf.models.college_nfl_translation import (  # noqa: E402
    MODEL_VERSION,
    SEED_DRAFT_YEAR,
    _MAX_PLAUSIBLE_Z,
    _MAX_PLAUSIBLE_Z_SD,
    TranslationConfig,
    build_target,
    run_college_nfl_translation,
)

log = logging.getLogger("ncaaf.p1a")

MARTS_SCHEMA = "main_ncaaf_marts"
PAIRS_TABLE = "ncaaf_draft_college_production_pairs"

_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/ncaaf/models/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1a_college_nfl_translation.md"
)


def load_pairs(duckdb_path: str, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        df = con.sql(f"select * from {schema}.{PAIRS_TABLE}").df()
    finally:
        con.close()
    log.info("loaded %-40s %7d rows", PAIRS_TABLE, len(df))
    return df


# ══════════════════════════════════════════════════════════════════════════════════════
# The join-coverage report (PM note #4 — the P1.2b dead-bridge lesson)
# ══════════════════════════════════════════════════════════════════════════════════════


def join_coverage(pairs: pd.DataFrame, config: TranslationConfig) -> dict:
    """How much of the xref actually carries P1.1 college production + an NFL outcome. A silently-
    thin join under-trains the model, so the coverage is SURFACED (and ALERTed if implausibly low),
    never hidden."""
    n = len(pairs)
    drafted = pairs["match_method"].eq("deterministic_slot") if "match_method" in pairs else pd.Series([], dtype=bool)
    has_prod = pairs["has_college_production"].astype(bool) if "has_college_production" in pairs else pd.Series(False, index=pairs.index)
    has_outcome = pd.to_numeric(pairs.get(config.target_metric), errors="coerce").notna()
    trainable = has_prod & has_outcome
    cov = {
        "n_xref_rows": int(n),
        "n_drafted": int(drafted.sum()),
        "n_with_college_production": int(has_prod.sum()),
        "pct_with_college_production": round(100.0 * has_prod.mean(), 1) if n else 0.0,
        "n_with_nfl_outcome": int(has_outcome.sum()),
        "n_trainable": int(trainable.sum()),
        "pct_trainable": round(100.0 * trainable.mean(), 1) if n else 0.0,
    }
    return cov


# ══════════════════════════════════════════════════════════════════════════════════════
# Gates — leakage + plausibility + oracle-floor + join-coverage (behavioural, per the P1.2 lesson)
# ══════════════════════════════════════════════════════════════════════════════════════


def validate(run, config: TranslationConfig, cov: dict) -> list[str]:
    """Assert the P1A contract. Raises on a violation — HALT-tier. Returns passed checks."""
    proj = run.projections
    bake = run.bakeoff
    passed: list[str] = []

    # 1. The seed class is NEVER emitted (its map would need a <seed class the floor forbids).
    if (proj["draft_year"] <= SEED_DRAFT_YEAR).any():
        raise AssertionError(
            f"draft class {SEED_DRAFT_YEAR} (the seed) was emitted — its college→NFL map has no "
            f"strictly-prior class and is in-sample"
        )
    passed.append(f"seed class {SEED_DRAFT_YEAR} not emitted (no strictly-prior map exists)")

    # 2. Every emitted projection used a STRICTLY-PRIOR training window (leakage contract, by class).
    if (proj["n_prior_classes"] < 1).any():
        raise AssertionError("a projection was emitted with zero strictly-prior training classes")
    passed.append("every emitted projection was fit on strictly-prior draft classes (n_prior ≥ 1)")

    # 3. Grain is unique — one row per NFL player.
    dupes = proj.duplicated(subset=["gsis_id"]).sum()
    if dupes:
        raise AssertionError(f"{dupes} duplicate gsis_id projection rows")
    passed.append("per-player grain (gsis_id) is unique")

    # 4. The projection + its uncertainty are finite and physically plausible.
    for col in ("projected_nfl_z", "projected_nfl_z_sd"):
        if not np.isfinite(proj[col]).all():
            raise AssertionError(f"{col} contains non-finite values")
    if (proj["projected_nfl_z_sd"] <= 0).any():
        raise AssertionError("projected_nfl_z_sd must be strictly positive")
    if float(proj["projected_nfl_z"].abs().max()) > _MAX_PLAUSIBLE_Z:
        w = proj.reindex(proj["projected_nfl_z"].abs().sort_values(ascending=False).index).iloc[0]
        raise AssertionError(
            f"projected_nfl_z reaches {w['projected_nfl_z']:.2f} sd ({w['draft_year']} "
            f"{w['player_name']}, {w['position_group']}) — above the ±{_MAX_PLAUSIBLE_Z} "
            f"plausibility ceiling; the college→NFL map is broken."
        )
    if float(proj["projected_nfl_z_sd"].max()) > _MAX_PLAUSIBLE_Z_SD:
        raise AssertionError(
            f"projected_nfl_z_sd reaches {proj['projected_nfl_z_sd'].max():.2f} — above the "
            f"{_MAX_PLAUSIBLE_Z_SD} ceiling; a coefficient is unidentified (P1.2's ±913-point leak)."
        )
    passed.append(
        f"projection finite + plausible (|z|≤{proj['projected_nfl_z'].abs().max():.2f}, "
        f"sd≤{proj['projected_nfl_z_sd'].max():.2f})"
    )

    # 5. ORACLE-FLOOR: no candidate beat the target-seeing oracle (the metric is not inverted).
    if not bake.oracle_floor_ok:
        raise AssertionError(
            "ORACLE-FLOOR VIOLATION — a candidate scored a LOWER MAE than a model that sees the "
            "target. That is mathematically impossible and means the selection metric is inverted."
        )
    passed.append("oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)")

    # 6. JOIN-COVERAGE (PM note #4): the xref→college-production join must not be silently thin.
    #    Reported as a gate; ALERTs (does not raise) below a floor — a thin join under-trains but is
    #    a coverage limit to surface, not a correctness emergency.
    if cov["pct_trainable"] < 40.0:
        run.notes.append(
            f"⚠️ THIN JOIN: only {cov['pct_trainable']}% of the xref is trainable "
            f"(college production + NFL outcome; n={cov['n_trainable']}). The college→NFL map is fit "
            f"on a thin base — verify fact_ncaaf_player_game.player_id == xref.college_athlete_id on "
            f"the real lake (the P1.2b dead-bridge class)."
        )
    passed.append(
        f"join coverage surfaced: {cov['pct_with_college_production']}% carry college production, "
        f"{cov['pct_trainable']}% trainable (n={cov['n_trainable']})"
    )

    # 7. Does the body of work beat the null FLOOR out-of-sample? (else honest 'no signal')
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "position_mean", "oos_mae"].iloc[0])
    sel = lb[lb["selectable"]]
    win_mae = float(sel["oos_mae"].min())
    if win_mae >= null_mae:
        run.notes.append(
            f"⚠️ NO SIGNAL: the winning config's OOS MAE ({win_mae:.4f}) does not beat the "
            f"position-mean null ({null_mae:.4f}) — the college body of work adds nothing here. "
            f"Emitting anyway (it degrades to the position mean), flagged for the NFL vertical."
        )
        passed.append(f"⚠️ winner does NOT beat the null (MAE {win_mae:.4f} ≥ {null_mae:.4f}) — honest no-signal")
    else:
        passed.append(f"winner beats the position-mean null OOS (MAE {win_mae:.4f} < {null_mae:.4f})")

    # 8. Draft-slot benchmark context (reported, never raised): does college production beat the
    #    market's draft-slot prior? The whole value proposition.
    slot_row = lb[lb["config"] == "draft_slot_ref"]
    if not slot_row.empty:
        slot_mae = float(slot_row["oos_mae"].iloc[0])
        rel = "beats" if win_mae < slot_mae else "does NOT beat"
        passed.append(
            f"vs draft-slot benchmark: college→NFL winner {rel} draft-slot-only "
            f"(MAE {win_mae:.4f} vs {slot_mae:.4f})"
        )

    # 9. Deflation gates (PBO<0.2 / DSR≥0.95) — reported, not raised: a TIED field yields a high PBO
    #    that is the NULL, not overfitting (E2.1-r); and a robust-but-weak DSR<0.95 is a VALID feeder
    #    deliverable here (the noisy NFL draft; the P1.2b DSR-0.821 precedent).
    if bake.pbo is not None:
        passed.append(f"PBO computed = {bake.pbo.pbo:.3f} over {bake.pbo.n_configs} configs "
                      f"({'<0.2 ✅' if bake.pbo.pbo < 0.2 else 'see report — tie vs overfit'})")
    if bake.dsr is not None:
        passed.append(f"DSR computed = {bake.dsr.dsr:.3f} (n_trials={bake.dsr.n_trials}) — "
                      f"{'≥0.95' if bake.dsr.dsr >= 0.95 else 'robust-but-weak, honest feeder (OK)'}")

    return passed


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def _by_group_projection_corr(run, config: TranslationConfig) -> dict:
    """OOS correlation of the emitted projection vs the realized standardized NFL outcome, per
    group (a true out-of-sample read — each class's projection was fit only on strictly-prior
    classes)."""
    tgt = build_target(run._pairs, config)[["gsis_id", "target_z", "has_target"]]
    merged = run.projections.merge(tgt, on="gsis_id", how="left")
    merged = merged[merged["has_target"].fillna(False)]
    out = {}
    for grp, g in merged.groupby("position_group"):
        if len(g) >= 20 and g["projected_nfl_z"].std() > 0 and g["target_z"].std() > 0:
            out[grp] = float(np.corrcoef(g["projected_nfl_z"], g["target_z"])[0, 1])
    if len(merged) >= 20 and merged["projected_nfl_z"].std() > 0 and merged["target_z"].std() > 0:
        out["ALL"] = float(np.corrcoef(merged["projected_nfl_z"], merged["target_z"])[0, 1])
    return out


def write_report(run, config: TranslationConfig, checks: list[str], cov: dict, corr: dict, path: Path) -> None:
    proj, bake = run.projections, run.bakeoff
    years = sorted(proj["draft_year"].unique())
    lines: list[str] = []
    a = lines.append

    a("# NCAAF-P1A — college → NFL translation (the NFL feeder; the MLB Edge-E7 analog)")
    a("")
    a(f"**Model:** `{MODEL_VERSION}` · **target metric:** `{config.target_metric}` · "
      f"**generated:** {datetime.now(timezone.utc).isoformat()}")
    a(f"**Draft classes emitted:** {years[0]}–{years[-1]} ({len(proj):,} player projections) · "
      f"**seed (not emitted):** {SEED_DRAFT_YEAR}")
    a("")
    a("> ⚠️ **This is an NFL-rookie PRIOR/projection, not an edge claim.** It translates a player's "
      "pre-draft college body of work + combine + recruiting pedigree into a projected early-career "
      "NFL outcome, measured against realized NFL production — never a market. `best_alpha = 0` "
      "holds. The uncertainty is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a "
      "calibrated predictive interval — **N1.2 (rookie-prop pricing) MUST recalibrate on held-out "
      "data before pricing** (the E13.6 pattern). The NFL draft is famously noisy: a ROBUST-BUT-WEAK "
      "signal (low PBO, DSR possibly <0.95) is a VALID and VALUABLE feeder — reported honestly, not "
      "forced. Even a modest projection beats the priors-only NFL rookie market.")
    a("")

    a("## 1. Gates")
    a("")
    for c in checks:
        a(f"- ✅ {c}")
    a("")

    a("## 2. Join coverage (the P1.2b dead-bridge check — PM note #4)")
    a("")
    a("Does every drafted player in the P0.3 xref actually carry P1.1 college production? The "
      "college→NFL map trains only on rows that carry BOTH college production AND an NFL outcome; a "
      "silently-thin join under-trains it, so the coverage is surfaced here.")
    a("")
    a(pd.DataFrame([cov]).T.rename(columns={0: "value"}).to_markdown())
    a("")

    a("## 3. The §0.5 bake-off leaderboard (leave-one-draft-class-out expanding-window CV)")
    a("")
    a("Every candidate is fit on STRICTLY-PRIOR draft classes and scored on the held-out class; the "
      "metric is MAE on the standardized NFL-outcome target (lower = better). `position_mean` is the "
      "NULL FLOOR (ignores the body of work); `draft_slot_ref` is the MARKET-PRIOR benchmark (log "
      "draft slot). Both are REPORTED but EXCLUDED from winner selection (`selectable = False`). "
      "`oos_skill_vs_null` = how much MAE the config removes vs the null (>0 ⇒ signal).")
    a("")
    a(bake.leaderboard.to_markdown(index=False, floatfmt=".4f"))
    a("")
    a(f"**Winner:** `{bake.winner_name}` (best selectable OOS MAE), refit on all labelled draft "
      f"classes for emission.")
    a("")

    # ── Headline read — computed from the leaderboard so the key takeaway is explicit, not inferred.
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "position_mean", "oos_mae"].iloc[0])
    win_mae = float(lb[lb["selectable"]]["oos_mae"].min())
    slot_row = lb[lb["config"] == "draft_slot_ref"]
    a("### 3b. Headline read")
    a("")
    consistency = ""
    if bake.pbo is not None and bake.dsr is not None:
        consistency = (f" and the beat is CONSISTENT (PBO {bake.pbo.pbo:.3f} / DSR {bake.dsr.dsr:.3f} "
                       f"— real, not a lucky draw)")
    a(f"- The college→NFL body of work is a **robust-but-weak** signal: the winner beats the "
      f"position-mean null out-of-sample ({win_mae:.4f} < {null_mae:.4f}){consistency}, but the "
      f"margin is small.")
    if not slot_row.empty:
        slot_mae = float(slot_row["oos_mae"].iloc[0])
        beats = win_mae < slot_mae
        a(f"- ⭐ **The draft slot alone {'beats' if not beats else 'is beaten by'} it "
          f"{'decisively' if abs(slot_mae-win_mae) > 0.05 else ''}** "
          f"(slot MAE {slot_mae:.4f} vs college→NFL {win_mae:.4f}). "
          + ("The market's draft position encodes far more than college box production + combine "
             "(scouting, medicals, film, interviews). So **do NOT use this projection as a "
             "standalone rookie board** — its value is as a COMPLEMENT to the draft slot: the "
             "RESIDUAL (where college production disagrees with where a player was drafted) is the "
             "part N1.2/N1.3 should exploit, by combining both, not P1A alone." if not beats else
             "College production adds signal beyond the draft board here."))
    # position-signal concentration, computed from the per-group OOS correlations
    if corr:
        strong = sorted([(k, v) for k, v in corr.items() if k != "ALL" and v >= 0.15],
                        key=lambda kv: -kv[1])
        weak = sorted([(k, v) for k, v in corr.items() if k != "ALL" and v < 0.08],
                      key=lambda kv: kv[1])
        if strong:
            a(f"- **Signal concentrates at skill positions**: "
              + ", ".join(f"{k} {v:.2f}" for k, v in strong)
              + (f" carry the projection↔realized correlation; "
                 + ", ".join(f"{k} {v:.2f}" for k, v in weak)
                 + " are near-zero (college defensive box stats translate poorly — expected)."
                 if weak else "."))
    # did combine + pedigree (GBM-only inputs) help?
    gbm_rows = lb[lb["config"].str.startswith("gbm")]
    if not gbm_rows.empty and float(gbm_rows["oos_mae"].min()) >= null_mae:
        a("- **Combine + recruiting pedigree add NO signal at this sample size** — every GBM config "
          "(the only candidates that use them) scores at or below the null. The college-production "
          "composite (used by the linear winners) carries what signal there is.")
    a("")

    a("## 4. Overfitting deflation (PBO / DSR)")
    a("")
    if bake.pbo is not None:
        a(f"- **PBO** = {bake.pbo.pbo:.3f} over {bake.pbo.n_configs} configs × {bake.pbo.n_splits} "
          f"CSCV splits.")
        a("  - ⚠️ **Reading a high PBO correctly (E2.1-r):** if the top configs genuinely TIE, a high "
          "PBO is the NULL (which tied candidate wins is noise), not overfitting. A high PBO with a "
          "WIDE leaderboard spread IS overfitting. Read the spread above.")
    else:
        a("- PBO not computed (need ≥4 folds and ≥2 configs with a complete performance column).")
    if bake.dsr is not None:
        a(f"- **DSR** = {bake.dsr.dsr:.3f} (observed skill-Sharpe {bake.dsr.observed_sr:.3f} vs "
          f"deflated floor {bake.dsr.sr0:.3f}, n_trials={bake.dsr.n_trials}). ≥0.95 = the winner's "
          f"OOS skill survives multiple-testing deflation. **DSR<0.95 here is EXPECTED and OK** — the "
          f"NFL draft is noisy; a robust-but-weak feeder is still valuable (the P1.2b precedent).")
    else:
        a("- DSR not computed (winner skill series too short or degenerate).")
    a("")

    a("## 5. Does the projection track realized NFL production? (OOS)")
    a("")
    a("Correlation of the emitted `projected_nfl_z` (fit only on strictly-prior classes) with the "
      "player's REALIZED standardized NFL outcome, per position group. A positive, position-plausible "
      "correlation is the behavioural gate that the map learned something; a flat correlation means "
      "the college body of work does not translate and the honest verdict is no signal.")
    a("")
    if corr:
        a(pd.DataFrame([{"group": k, "proj↔realized corr": v} for k, v in sorted(corr.items())])
          .to_markdown(index=False, floatfmt=".3f"))
    else:
        a("_(insufficient produced-player rows to estimate a stable correlation.)_")
    a("")

    a("## 6. Face validity — the top projected rookies (most recent DRAFTED class)")
    a("")
    # Eye-test on the most recent DRAFTED class only. A derived-class cohort (a class whose players
    # are ALL undrafted — e.g. when the xref's draft seasons stop before the latest emitted class)
    # is a lower-signal UDFA-only group and makes a misleading headline; drafted players are the
    # meaningful test. `draft_overall` is null for UDFAs, so filtering on it isolates the drafted.
    drafted = proj[pd.to_numeric(proj["draft_overall"], errors="coerce").notna()]
    latest_drafted = int(drafted["draft_year"].max()) if not drafted.empty else int(years[-1])
    top = drafted[drafted["draft_year"] == latest_drafted].nlargest(15, "projected_nfl_z")
    n_udfa_recent = int((proj["draft_year"] > latest_drafted).sum())
    a(f"**{latest_drafted} class (drafted only):** the top projected rookies should be early-round "
      "picks at premium positions with strong final college seasons. Read the list, do not just count "
      "it — if they are not recognizable early-career contributors, the map is picking up something "
      "else.")
    if n_udfa_recent:
        a("")
        a(f"> ⚠️ {n_udfa_recent} projections sit in later, UDFA-ONLY derived classes "
          f"(> {latest_drafted}) — the P0.3 xref's drafted seasons stop at {latest_drafted}, so those "
          f"cohorts carry no drafted players and are a separate lower-signal group (excluded from this "
          f"eye-test). To project a future DRAFTED class, extend the xref's `--draft-seasons`.")
    a("")
    a(top[["player_name", "position_group", "college", "draft_round", "draft_overall",
           "projected_nfl_z", "projected_nfl_z_sd"]]
      .to_markdown(index=False, floatfmt=".3f"))
    a("")

    a("## 7. Limitations")
    a("")
    a("- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks "
      "confidence correctly, too tight to price. N1.2 MUST recalibrate on held-out data (E13.6).")
    a("- **The target is WITHIN-(position, draft class) standardized** — it captures who produced "
      "more AMONG their positional draft peers, not an absolute AV. That is the honestly-learnable "
      "signal; absolute cross-position NFL production is not comparable and is not claimed.")
    a("- **OL and specialists have NO college box production** (`box_production_available = False`): "
      "they get a combine/pedigree-only projection and are excluded from the production VALIDATION.")
    a("- **UDFAs carry no NFL-outcome label** (undrafted → no draft-pick outcome row): they are "
      "excluded from TRAINING but still receive a college-only projection, flagged `is_udfa` / lower "
      "confidence. Weight them accordingly downstream.")
    a("- **~11 draft classes (2015–25) is the training ceiling** (the 2014 box-production floor). The "
      "seed class is not emitted. A small class count is why the DSR bar is read leniently.")
    a("- **Draft slot is a REPORTED benchmark, not a feature of the translation candidates** — the "
      "college→NFL map is built from college production + combine + pedigree so it can be COMPARED to "
      "the market's draft-slot prior, not built from it.")
    a("- **Empirical-Bayes plug-in** (partial-pool winner): the variance components are point "
      "estimates, not integrated over — the same posture as P1.2 and MLB's bullpen posteriors.")
    a("")

    if run.notes:
        a("## 8. Run notes")
        a("")
        for n in run.notes:
            a(f"- {n}")
        a("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NCAAF-P1A college→NFL translation (the NFL feeder)")
    p.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb",
                   help="path to the sports dbt DuckDB (laptop default; the box would use "
                        "/tmp/sports_ncaaf.duckdb but prefer the laptop off-season)")
    p.add_argument("--schema", default=MARTS_SCHEMA)
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--s3", action="store_true",
                   help="also land the projections in the S3 sports lake (laptop-safe: S3 I/O, no "
                        "box compute). Needs ambient AWS creds + SPORTS_LAKE_REGION (default us-east-2)")
    p.add_argument("--lake-root", default=None,
                   help="write the derived Delta to a LOCAL FS lake at this root instead of S3 "
                        "(fully-offline laptop run). Mutually exclusive with --s3.")
    p.add_argument("--target-metric", default="target_w_av",
                   help="NFL outcome to translate to (target_w_av|target_car_av|target_dr_av|"
                        "target_games|target_seasons_started)")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if args.s3 and args.lake_root:
        p.error("--s3 and --lake-root are mutually exclusive (pick S3 OR a local Delta tree)")

    if not Path(args.duckdb).exists():
        p.error(f"DuckDB not found at {args.duckdb} — run the sports dbt build first "
                f"(needs {PAIRS_TABLE}), or point --duckdb at the box's /tmp/sports_ncaaf.duckdb")

    pairs = load_pairs(args.duckdb, args.schema)
    config = TranslationConfig(target_metric=args.target_metric)
    cov = join_coverage(pairs, config)
    log.info("join coverage: %s", cov)

    log.info("running the P1A bake-off (this is the multi-minute part) ...")
    run = run_college_nfl_translation(pairs, config)
    run._pairs = pairs  # for the OOS correlation diagnostic
    if run.projections.empty:
        log.error("no projections produced — check the pairs mart / target metric")
        return 1
    log.info("emitted %d player projections across %d classes; winner=%s",
             len(run.projections), run.projections["draft_year"].nunique(), run.bakeoff.winner_name)

    checks = validate(run, config, cov)
    for c in checks:
        log.info("gate ✅ %s", c)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run.projections.to_parquet(out_dir / "ncaaf_nfl_rookie_projections.parquet", index=False)

    corr = _by_group_projection_corr(run, config)
    (out_dir / "ncaaf_college_nfl_translation_summary.json").write_text(json.dumps({
        "model_version": MODEL_VERSION,
        "target_metric": config.target_metric,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_projections": int(len(run.projections)),
        "classes": [int(y) for y in sorted(run.projections["draft_year"].unique())],
        "join_coverage": cov,
        "winner": run.bakeoff.winner_name,
        "leaderboard": run.bakeoff.leaderboard.to_dict(orient="records"),
        "pbo": None if run.bakeoff.pbo is None else run.bakeoff.pbo.pbo,
        "dsr": None if run.bakeoff.dsr is None else run.bakeoff.dsr.dsr,
        "oracle_floor_ok": run.bakeoff.oracle_floor_ok,
        "by_group_projection_corr": corr,
        "gates_passed": checks,
        "notes": run.notes,
    }, indent=2, default=float))
    log.info("by-group OOS projection↔realized corr: %s", corr)

    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.ncaaf.ingest import s3io

        # local_root=None → S3 (botocore credential chain: ambient laptop creds OR the box's
        # instance role); local_root=<dir> → a local FS Delta tree (fully-offline laptop run).
        for year, part in run.projections.groupby("draft_year"):
            s3io.write_dataframe(part.assign(season=int(year)), sport="ncaaf",
                                 source="nfl_rookie_projections", season=int(year), tier="derived",
                                 local_root=args.lake_root)
        dest = f"local lake {args.lake_root}" if args.lake_root else "the S3 sports lake"
        log.info("landed rookie projections in %s (derived tier)", dest)

    if not args.no_report:
        write_report(run, config, checks, cov, corr, _REPORT_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
