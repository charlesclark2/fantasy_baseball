"""run_nf_w6c_stage_registry.py — stage the NF-W6c served per-stat distributions in the NF-G0
registry.

WHAT THIS WRITES (and only this): ONE entry — family `nfl_fantasy`, target
`weekly_stat_distribution`, promotion_status = challenger (STAGED). ⛔ It does NOT promote, does
NOT publish, does NOT touch serving: `served_entry()` returns champion-status entries only, no
serving path reads this registry at all, and `betting_ml/tests/test_nf_w6c_stat_distribution_
serving.py` proves the inertness BOTH ways — the staged entry is invisible to the serving-facing
query, and the SAME query would see it if its status were champion (so the inertness rests on the
status field, not on the entry happening to be absent).

⚠️ WHY A NEW TARGET RATHER THAN `weekly_projection`. The registry key is
(family, target, version), and `weekly_projection` already carries NF-W2b's staged POINTS
challenger. Per-stat distributions version apart from the points model — NF-W6b explicitly left
the points hurdle champion untouched and never tested it — so folding them into one target would
make one of the two unrepresentable, which is the same reason `interval_model_version` is a
mapping rather than a scalar.

⛔ PROMOTE/PUBLISH IS BLOCKED — the blockers are read from `SDS.PROMOTE_BLOCKERS` (one source; the
serving module owns them) and written into the entry, so the gate is a fact in the system of
record rather than a sentence in a PR description.

Idempotent: re-running re-registers the same content (the digest moves only when the staged
manifest does). RUN (LAPTOP, seconds — AFTER the build runner has produced the manifest):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6c_stage_registry
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.governance import publish as P  # noqa: E402
from betting_ml.governance import registry as R  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving as SDS,
)

log = logging.getLogger("nfl.fantasy.nf_w6c_stage")

_FANTASY_DIR = "quant_sports_intel_models/football/nfl/fantasy"
#: The staged artifact of record: the build runner's committed manifest. It carries the served
#: representation contract, the provenance, the serving smoke AND the built parquet's sha256 —
#: so pinning this manifest pins the (gitignored) parquet by digest.
ARTIFACT = f"{_FANTASY_DIR}/ablation_results/nf_w6c_served_stat_distributions.json"
#: The two §0.5 records that CERTIFIED the seven forms — cited as the validation, never re-run
#: here. NF-W6b ships six cells; NF-W6b-C is a SEPARATE fresh-family registration that ships the
#: seventh (RB|rushing_tds) after W6b's own field failed to clear DSR for it.
BAKEOFF_RECORD = f"{_FANTASY_DIR}/ablation_results/nf_w6b_stat_distributions.md"
BAKEOFF_RECORD_W6BC = f"{_FANTASY_DIR}/ablation_results/nf_w6b_c_rb_rush_tds.md"
#: The rollback target. Nothing per-stat-distributional has ever served, so there is no previous
#: served version; what the raw line reverts to is the CHAMPION'S PER-STAT POINT MEAN (the NF-W1
#: component head) — its validated record is the fallback the serving rule falls back to.
FALLBACK_ARTIFACT = f"{_FANTASY_DIR}/ablation_results/nf_w1_weekly_bakeoff.json"


def stage_entry(registry_path: Path = R._REGISTRY_PATH) -> dict:
    artifact_path = _PROJECT_ROOT / ARTIFACT
    staged_digest = P.digest_file(artifact_path)
    if staged_digest is None:
        raise SystemExit(
            f"staged manifest missing: {artifact_path}\n"
            f"Run the build first (LAPTOP):\n"
            f"  uv run python -m {_FANTASY_DIR.replace('/', '.')}"
            f".run_nf_w6c_serve_stat_distributions")
    manifest = json.loads(artifact_path.read_text())
    if manifest.get("smoke"):
        raise SystemExit("refusing to stage a --smoke manifest: a short-train path proof is not "
                         "a servable fit (its own artifact is suffixed _smoke; this one is not)")
    # the staged forms must be the ones the module pins, which the fast gate pins to the record
    staged_cells = manifest.get("representation", {}).get("cells")
    if staged_cells != dict(SDS.SERVED_CELLS):
        raise SystemExit(f"manifest cells {staged_cells} disagree with SDS.SERVED_CELLS "
                         f"{dict(SDS.SERVED_CELLS)} — refusing to stage a drifted artifact")

    prov = manifest["provenance"]
    lineage = {
        "served_version": SDS.SERVED_VERSION,
        "base_model_version": "nfl_fantasy_nf_w1_v1",
        "per_cell_form": dict(SDS.SERVED_CELLS),
        "withheld_null_cells": list(SDS.WITHHELD_NULL_CELLS),
        "closed_cells": list(SDS.CLOSED_CELLS),
        "served_representation": {
            "levels": SDS.N_LEVELS, "grid": "MC.EVAL_LEVELS (0.005…0.995, step 0.005)",
            "index_q10": SDS.IDX_Q10, "index_q50": SDS.IDX_Q50, "index_q90": SDS.IDX_Q90,
            "zero_atom": "P(0) = the share of grid levels at 0",
        },
        "feature_bundle": (f"weekly_projection.FEATURES ({len(SDS.FEATURES)} columns) + position "
                           f"code — the champion set; no new features (NF-W6b prereg)"),
        "matrix_key": manifest["matrix_key"],
        "built_artifact_sha256": manifest["built_artifact"]["sha256"],
        "fallback_artifact_uri": f"repo:{FALLBACK_ARTIFACT}",
        "validation_report": (
            "NF-W6b per-stat distributional bake-off, SHIP x6 of 8 cells (2026-08-15): QB "
            "passing_tds +22.1% / passing_yards +17.0% / rushing_yards +18.9%, RB rushing_yards "
            "+13.5%, TE receiving_yards +14.2%, WR receiving_yards +11.5% of CRPS (crps_q199) vs "
            "the binding champion-faithful incumbent; 8/8 folds each, PBO 0.0, DSR 0.969-1.0, "
            "two-family BH-FDR, coverage floor, degenerate + permutation anchors all green. "
            f"Record: {BAKEOFF_RECORD}. NF-W6b-C per-stat distributional successor (SEPARATE "
            "record, fresh registration, seed 20260816): SHIP RB|rushing_tds — `knn_quantile` "
            "+12.966% CRPS vs the discrete climatology, 8/8 folds, PBO 0.0, DSR 1.0 (sr0 1.33) "
            "where NF-W6b's OWN field could not clear DSR for this cell (sr0 ≈7.32, inflated "
            "by an excluded incoherent arm) — a fresh, coherent, atom-aware family, not a re-score "
            f"of W6b's field (MH2.2). Record: {BAKEOFF_RECORD_W6BC}. NF-W6c re-derives NOTHING: "
            "it fits those certified constructions fresh on full train through the identical "
            "pinned code path (stat_distribution_serving dispatches into stat_distributions.arm_*) "
            "and emits the 199-level representation. Serving-smoke readout (in-family check on "
            f"the served week, NEVER a gate) is in the staged manifest; serve gw {prov['serve_gw']} "
            f"({prov['serve_season']} wk {prov['serve_week']}), {prov['n_train_rows']} train rows "
            "= a superset of NF-W6b's purged fold train "
            f"({prov['train_containment']['n_fold_train']}, "
            f"+{prov['train_containment']['extra_rows_vs_fold_train']}), containment measured."),
        "reviewed_by": ("Charlie (operator/PM) — NF-W6b Decision A (wire ALL SIX ship cells; "
                        "points hurdle champion untouched) + NF-W6b-C Decision C (wire RB "
                        "rushing_tds once the fresh-family successor shipped), 2026-08-15"),
        "notes": (
            "STAGED CHALLENGER (NF-W6c) — inert at serve by construction: served_entry() returns "
            "champion-status entries only and no serving path reads this registry. "
            "PROMOTE/PUBLISH BLOCKED until ALL of: "
            + "; ".join(f"({i}) {b}" for i, b in enumerate(SDS.PROMOTE_BLOCKERS, 1))
            + ". ⛔ `scoring_contract_version` is deliberately ABSENT: nothing scores these "
            "distributions yet (this story is the SUBSTRATE; the arbitrary-league re-scoring "
            "consumer is a follow-on), and stamping a scoring contract no consumer honors would "
            "be a lineage claim with no consumer. ⛔ The remaining recorded-null cell is NOT "
            "staged — RB receiving_yards is PM Decision B (calendar-bound re-test on the same "
            "harness once the 2026 folds exist). RB rushing_tds (PM Decision C) IS now staged: "
            "NF-W6b's own field never cleared DSR for it (an excluded linear-residual arm "
            "inflated the field's cross-trial dispersion), so NF-W6b-C registered a FRESH, "
            "coherent, atom-aware family that cleared DSR cleanly (1.0, sr0 1.33) — that "
            "successor record, not a re-read of NF-W6b's null, is what licenses serving it. ⛔ The "
            "points hurdle champion (total fantasy points) is untouched — NF-W6b never tested it "
            "and never beat it; these per-stat distributions sit BESIDE it on the raw line. "
            "Nothing distributional has ever served per-stat, so fallback_artifact_uri is the "
            "NF-W1 base champion's record = the per-stat POINT mean the raw line reverts to. "
            "Edge-independent projection product (best_alpha = 0): a quantile bank is honest "
            "predictive uncertainty and carries no edge, ROI or win-rate claim."),
    }
    result = P.stage(model_family=SDS.MODEL_FAMILY, target=SDS.REGISTRY_TARGET, lineage=lineage,
                     artifact_uri=f"repo:{ARTIFACT}", staged_digest=staged_digest,
                     registry_path=registry_path)

    # self-checks at write time: staging must not have created anything the serving-facing query
    # can see for this target, and neither neighbouring entry may move.
    assert R.served_entry(SDS.MODEL_FAMILY, SDS.REGISTRY_TARGET, registry_path) is None, (
        "staging produced a SERVED per-stat entry — the build/publish separation is broken")
    season = R.served_entry(SDS.MODEL_FAMILY, "season_projection", registry_path)
    assert season and season.get("served_version") == "nfl_fantasy_nf1_5_v1", (
        "the season-projection champion changed during staging — refuse and investigate")
    assert R.served_entry(SDS.MODEL_FAMILY, "weekly_projection", registry_path) is None, (
        "a weekly_projection champion appeared during staging — refuse and investigate")
    return result.as_dict()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = stage_entry()
    log.info("staged %s (challenger; promote blocked on %d gates)", out["key"],
             len(SDS.PROMOTE_BLOCKERS))
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
