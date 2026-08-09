"""run_nf_w2b_stage_registry.py — stage the NF-W2b weekly champion in the NF-G0 registry.

Decision 1 = OPTION A (operator/PM-confirmed 2026-08-09): stage the PER-POSITION CERTIFIED
winners — QB/TE `inj_zero_leg`, RB/WR `inj_both` (serve-what-was-validated, MH2.1 (b); the
spec is read from `W2B.POST_FLIP_SPEC`, which is guard-pinned to the validated bake-off
artifact, so this script cannot stage a spec the gates didn't certify).

WHAT THIS WRITES (and only this): ONE registry entry — family `nfl_fantasy`, target
`weekly_projection`, promotion_status = challenger (STAGED). ⛔ It does NOT promote, does NOT
publish, does NOT touch serving: `served_entry()` returns only champion-status entries, no
serving path reads this registry at all (its consumers are governance/research scripts), and
`betting_ml/tests/test_nf_w2b_staged_registry.py` PROVES both directions — the staged entry is
invisible to the serving-facing query, and the same query WOULD see it if its status were
champion (so the inertness rests on the status field, not on absence).

⛔ PROMOTE/PUBLISH IS BLOCKED (recorded in the entry's notes as the operator gate) on ALL of:
  1. NF-C6 Phase 2 — the weekly serving path does not exist yet;
  2. NF-W0a — the stamped injury forward-capture must be arming the family LIVE in-season
     (dark feed ⇒ the learned arms score WORSE than base; serve the base champion);
  3. the pre-flip RETENTION snapshot + PROJECTION snapshot, taken before any promote
     (run_nf_serving_board_snapshot.py / run_nf_w2b_projection_snapshot.py).

Idempotent: re-running re-registers the same content. RUN (LAPTOP, seconds):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_stage_registry
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
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w2b_stage")

FAMILY = "nfl_fantasy"
TARGET = "weekly_projection"
SERVED_VERSION = "nfl_fantasy_w2b_v1"

_FANTASY_DIR = "quant_sports_intel_models/football/nfl/fantasy"
#: The validated spec record — the artifact the gates certified (`repo:` = a committed file,
#: reviewed in the PR; a real serving artifact does not exist until NF-C6 Phase 2 builds one).
ARTIFACT = f"{_FANTASY_DIR}/ablation_results/nf_w2b_injury_rate_bakeoff.json"
#: The dark-feed / rollback target: the NF-W1 base champion's validated record. Nothing weekly
#: has ever SERVED, so there is no previous served version — the fallback is the SPEC the
#: serving rule falls back to (dark feed ⇒ base champion), wired at stage time.
FALLBACK_ARTIFACT = f"{_FANTASY_DIR}/ablation_results/nf_w1_weekly_bakeoff.json"

PROMOTE_BLOCKERS = (
    "NF-C6 Phase 2 (the weekly serving path does not exist yet)",
    "NF-W0a stamped injury forward-capture arming the family LIVE in-season "
    "(dark feed => serve the base champion; shadow-2025 measured the dark tax)",
    "pre-flip RETENTION snapshot + PROJECTION snapshot taken before any promote "
    "(run_nf_serving_board_snapshot.py / run_nf_w2b_projection_snapshot.py)",
)


def stage_entry(registry_path: Path = R._REGISTRY_PATH) -> dict:
    artifact_path = _PROJECT_ROOT / ARTIFACT
    staged_digest = P.digest_file(artifact_path)
    if staged_digest is None:
        raise SystemExit(f"validated artifact missing: {artifact_path} — nothing to stage")
    lineage = {
        "served_version": SERVED_VERSION,
        "base_model_version": "nfl_fantasy_nf_w1_v1",
        "per_position_spec": dict(W2B.POST_FLIP_SPEC),
        "feature_bundle": ("weekly_projection.FEATURES + injury_rate + injury_report "
                           "(= weekly_projection_w2b.FEATURES_W2B; per-arm legs per spec)"),
        "scoring_contract_version": "nf_c0e",
        "fallback_artifact_uri": f"repo:{FALLBACK_ARTIFACT}",
        "validation_report": (
            "NF-W2b bake-off SHIP x4 (2026-08-09): pure player-level lift vs the "
            "marginal-rate-carrying foil QB +0.098 (11/12) / RB +0.135 (12/12) / WR +0.126 "
            "(12/12) / TE +0.059 (12/12) CRPS/wk; PBO <=0.14, DSR >=0.993, BH-FDR x4; the "
            "permuted arm's lift over base_rate NEGATIVE at all four positions (the NF-W2 "
            "refusal clause now passes two-sided). Record: "
            f"{_FANTASY_DIR}/ablation_results/nf_w2b_injury_rate_bakeoff.md ('Reading the "
            "result')."),
        "reviewed_by": ("Charlie (operator/PM) — Decision 1 = Option A (per-position "
                        "certified winners), 2026-08-09"),
        "notes": (
            "STAGED CHALLENGER (NF-W2b, 2026-08-09) — inert at serve by construction: "
            "served_entry() returns champion-status entries only and no serving path reads "
            "this registry (guard-tested two-sided in test_nf_w2b_staged_registry.py). "
            "PROMOTE/PUBLISH BLOCKED until ALL of: "
            + "; ".join(f"({i}) {b}" for i, b in enumerate(PROMOTE_BLOCKERS, 1))
            + ". Nothing weekly has ever served, so there is no previous served version; "
            "fallback_artifact_uri is the NF-W1 base champion's validated record — the spec "
            "the dark-feed serving rule falls back to. per_position_spec is read from "
            "W2B.POST_FLIP_SPEC (guard-pinned to the validated artifact); the RB/WR tie is "
            "not a licence to re-select (Option A explicitly rejects uniform inj_zero_leg)."),
    }
    result = P.stage(model_family=FAMILY, target=TARGET, lineage=lineage,
                     artifact_uri=f"repo:{ARTIFACT}", staged_digest=staged_digest,
                     registry_path=registry_path)

    # self-check at write time: staging must not have created ANYTHING the serving-facing
    # query can see for this target, and the season champion must be untouched.
    assert R.served_entry(FAMILY, TARGET, registry_path) is None, (
        "staging produced a SERVED weekly entry — the build/publish separation is broken")
    season = R.served_entry(FAMILY, "season_projection", registry_path)
    assert season and season.get("served_version") == "nfl_fantasy_nf1_5_v1", (
        "the season-projection champion changed during staging — refuse and investigate")
    return result.as_dict()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = stage_entry()
    log.info("staged %s (challenger; promote blocked on %d gates)", out["key"],
             len(PROMOTE_BLOCKERS))
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
