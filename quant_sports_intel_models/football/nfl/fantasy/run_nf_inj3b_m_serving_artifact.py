"""run_nf_inj3b_m_serving_artifact.py — NF-INJ3b-M node 2: PERSIST the certified hurdle.

PM ruling **D2 = A**: serve NF-INJ3b's certified `hurdle_transfer` via a persisted, versioned
artifact — MH2.1, *serve the object that was validated, never a re-derivation*.

WHAT THIS WRITES: `served_artifacts/nfl_fantasy_injury_games_hurdle_v1.json`, a COEFFICIENT TABLE
(not a pickle — the NCAAF-P2.1 S1-serve precedent: version-proof, diffable, PR-reviewable, and
immune to the unpinned-sklearn pickle landmine). It is fitted by calling the bake-off's OWN
`nf_inj3_injury_games.fit_hurdle` on the SAME training frame `run_nf_inj3_injury_games.apply_serving`
uses for the serving counterfactual, so the persisted object and the validated one are the same
object — and `test_nf_inj3b_m_serving_artifact.py` PINS that at **1e-9** rather than asserting it.

⛔ The artifact is COMMITTED. A serving artifact under the gitignored `artifacts/` tree is the
NF-INFRA1 deploy-ephemeral time bomb (absent from the image, wiped by every deploy) — and this one
is a few KB of JSON.

⚠️ Writing the artifact SERVES NOTHING. `injury_games_policy.SERVING_ENABLED` is False and stays
False: NF-INJ3b's §5 ship path is incomplete until node 4's measurement, and the flip is the
operator's.

RUN (LAPTOP — reads the local DuckDB + build artifacts read-only):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3b_m_serving_artifact \
        --duckdb <main>/quant_sports_intel_models/sports_dbt/sports.duckdb \
        --artifacts <main>/quant_sports_intel_models/football/nfl/fantasy/artifacts
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as SERVE  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_inj3_injury_games as R3,
)

log = logging.getLogger("nfl.fantasy.nf_inj3b_m.artifact")


def build(con, art: Path) -> tuple[dict, dict]:
    """Fit the certified hurdle exactly as the serving counterfactual does, and return
    `(artifact, verification)`.

    ⭐ THE TRAINING FRAME IS NOT CHOSEN HERE. It is `apply_serving`'s: the whole era-floored history
    `pop[target_season >= ERA_MIN_SEASON]`, at the serving season's game count. Re-deciding it in
    this file is precisely how a served object drifts from a validated one."""
    hist = tuple(range(IG.ERA_MIN_SEASON, R3.SERVING_SEASON))
    pop, prov = R3.build_population(con, art, hist)
    serving, sprov = R3.build_population(con, art, (R3.SERVING_SEASON,))

    n = IG.season_game_count(R3.SERVING_SEASON)
    train = pop[pop.target_season >= IG.ERA_MIN_SEASON]
    fit = IG.fit_hurdle(train, n)

    artifact = {
        "model_version": POLICY.MODEL_VERSION,
        "contract_version": SERVE.CONTRACT_VERSION,
        "source_model": POLICY.SOURCE_MODEL,
        "arm": POLICY.ARM,
        "form": POLICY.FORM,
        "preregistration": "ablation_results/nf_inj3b_preregistration.md",
        "decisive_record": "ablation_results/nf_inj3b_injury_games.md",
        "certified_statuses": list(POLICY.CERTIFIED_STATUSES),
        "incumbent_statuses": list(POLICY.INCUMBENT_STATUSES),
        "pm_boundary": POLICY.PM_BOUNDARY,
        "columns": list(SERVE.design_columns()),
        "n_games": int(n),
        "b_play": [float(x) for x in fit["b_play"]],
        "b_cond": ([float(x) for x in fit["b_cond"]] if fit["b_cond"] is not None else None),
        "cond_pooled": float(fit["cond_pooled"]),
        "train_seasons": [int(min(hist)), int(max(hist))],
        "n_train_rows": int(len(train)),
        "fit_at": datetime.now(timezone.utc).isoformat(),
        "notes": "Fitted by nf_inj3_injury_games.fit_hurdle — the bake-off's OWN function — on the "
                 "frame run_nf_inj3_injury_games.apply_serving uses. ⛔ Never re-fitted at serve "
                 "time (MH2.1). A coefficient table, not a pickle.",
    }

    # ── the pin, computed HERE as well as in the guard, so a bad write cannot be committed ──────
    validated, _ = IG.arm_mu(POLICY.ARM, train, serving, n)
    served = SERVE.predict_games(artifact, serving)
    worst = float(np.max(np.abs(served - validated))) if len(serving) else None
    verification = {
        "n_serving_rows": int(len(serving)),
        "max_abs_difference_vs_validated_arm": worst,
        "tolerance": 1e-9,
        "reproduces_validated_arm": bool(worst is not None and worst < 1e-9),
        "what_it_proves": "the PERSISTED coefficients reproduce the arm the bake-off scored, on the "
                          "live serving cohort, to machine precision — so the object that ships is "
                          "the object that was validated (MH2.1), not a re-fit that happens to "
                          "look similar.",
        "population": prov, "serving_population": sprov,
    }
    return artifact, verification


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3b-M node 2: persist the certified hurdle")
    ap.add_argument("--duckdb", default=R3._DEFAULT_DUCKDB)
    ap.add_argument("--artifacts", default=None,
                    help="dir holding the single-vintage MVP-1 builds (gitignored — NF-INFRA1)")
    ap.add_argument("--dry-run", action="store_true", help="fit + verify, write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    import duckdb
    con = duckdb.connect(args.duckdb, read_only=True)
    artifact, ver = build(con, R3.artifacts_dir(args.artifacts))

    print(f"NF-INJ3b-M serving artifact — {artifact['model_version']}")
    print(f"  trained {artifact['train_seasons'][0]}–{artifact['train_seasons'][1]} on "
          f"{artifact['n_train_rows']} rows; n_games={artifact['n_games']}")
    print(f"  reproduces the validated arm on {ver['n_serving_rows']} serving rows: "
          f"max |Δ| = {ver['max_abs_difference_vs_validated_arm']:.3e} "
          f"(tol {ver['tolerance']:.0e}) ⇒ {ver['reproduces_validated_arm']}")
    print(f"  🔒 SERVING_ENABLED = {POLICY.SERVING_ENABLED} — writing this artifact serves nothing")

    if not ver["reproduces_validated_arm"]:
        # ⛔ REFUSE to write an artifact that does not reproduce the validated arm. A serving object
        #    that "nearly" matches is exactly the re-derivation MH2.1 forbids.
        raise SystemExit("NF-INJ3b-M: the persisted coefficients do NOT reproduce the validated "
                         "arm at 1e-9 — refusing to write the artifact (MH2.1).")
    if args.dry_run:
        print("  --dry-run: nothing written")
        return 0
    SERVE.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SERVE.ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2))
    (SERVE.ARTIFACT_DIR / "nfl_fantasy_injury_games_hurdle_v1.verification.json").write_text(
        json.dumps(ver, indent=2, default=str))
    print(f"  wrote {SERVE.ARTIFACT_PATH.relative_to(_PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
