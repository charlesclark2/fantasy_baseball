"""derive_clustered_contract.py — Epic E1.3: reproducible slim-contract derivation.

WHY
---
The pruned-clustered feature contracts (`feature_columns_*_pruned_clustered_deleaked_2026.json`)
were previously hand-derived from the clustered-MDA importance JSONs. That manual step is how
the totals contract ended up carrying `home_starter_stuff_plus` / `away_starter_avg_fastball_velo`
— features selected off a *leaky* (Stuff+ season-to-date) ranking that E1.8 later overturned.
This script codifies the fixed E1.3 rule so the contract is a deterministic function of the
importance run, never a judgement call.

THE RULE (no hand-pruning)
--------------------------
Keep every member column of every cluster whose season-stratified paired-bootstrap 95% CI
EXCLUDES 0 (`is_noise == False` in the MDA JSON — a CI crossing 0 is indistinguishable from
noise and is dropped). Output is the alphabetically-sorted union of those members.

This reproduces the E1.7 contracts byte-for-byte from the `*_bullpen_v3` JSONs (validated by
set-equality on all 21/21/15 features) — i.e. it is the exact rule a prior session applied by
hand, now mechanized.

LEAKAGE GUARD
-------------
Refuses to derive from an importance run that still has a known construction leak active —
bullpen `static` (the `bp_eb_xwoba` within-row peek, E2.1b/E1.7) or Stuff+ `leaky`
(season-to-date arsenal, E1.8). This is the precise trap E1.8 hit: the `stuffplus_deleaked`
A/B was run with `bullpen_version=static`, so deriving a contract from it would re-import the
bullpen leak at #1. Pass `--allow-leaky` only for validation/inspection (e.g. reproducing the
historical E1.7 contract), never to write a production contract.

Usage:
    # 1) operator first runs the FULLY de-leaked MDA (multi-minute; hand off):
    #    uv run python betting_ml/scripts/clustered_feature_importance.py \
    #        --target total_runs --bullpen-version v3 --stuff-plus-version deleaked
    # 2) then derive the contract deterministically:
    uv run python betting_ml/scripts/derive_clustered_contract.py --target total_runs

    # validate the rule reproduces the historical E1.7 contract (no write):
    uv run python betting_ml/scripts/derive_clustered_contract.py --target total_runs \
        --importance-json .../clustered_importance_total_runs_bullpen_v3.json --allow-leaky --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_JSON_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "clustered_importance"

# target → (model file stem, model dir) for the contract output path
_TARGET_CFG = {
    "home_win":   ("xgb_classifier", "home_win"),
    "run_diff":   ("ngboost", "run_differential"),
    "total_runs": ("ngboost", "total_runs"),
}


def _default_importance_json(target: str) -> Path:
    """The canonical FULLY de-leaked MDA output for this target."""
    return _JSON_DIR / f"clustered_importance_{target}_bullpen_v3_stuffplus_deleaked.json"


def _contract_path(target: str) -> Path:
    stem, model_dir = _TARGET_CFG[target]
    return (PROJECT_ROOT / "betting_ml" / "models" / model_dir /
            f"feature_columns_{stem}_pruned_clustered_deleaked_2026.json")


def _signal_members(payload: dict) -> list[str]:
    """The E1.3 rule: alphabetically-sorted union of all non-noise clusters' members."""
    members: set[str] = set()
    for c in payload["clusters"]:
        if not c["is_noise"]:
            members.update(c["members"])
    return sorted(members)


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def derive(target: str, importance_json: Path, *, allow_leaky: bool,
           dry_run: bool, date: str, out_path: Path | None = None) -> dict:
    importance_json = importance_json.resolve()
    if not importance_json.exists():
        raise SystemExit(
            f"❌ importance JSON not found: {importance_json}\n"
            f"   Run the fully de-leaked MDA first (operator, multi-minute):\n"
            f"   uv run python betting_ml/scripts/clustered_feature_importance.py "
            f"--target {target} --bullpen-version v3 --stuff-plus-version deleaked")

    payload = json.loads(importance_json.read_text())
    bullpen = payload.get("bullpen_version")
    stuffp = payload.get("stuff_plus_version")

    # ── leakage guard ────────────────────────────────────────────────────────
    leaks = []
    if bullpen != "v3":
        leaks.append(f"bullpen_version={bullpen!r} (need 'v3' — 'static' re-imports the bp_eb_xwoba within-row leak)")
    if stuffp != "deleaked":
        leaks.append(f"stuff_plus_version={stuffp!r} (need 'deleaked' — 'leaky' is the Stuff+ season-to-date peek)")
    if leaks:
        msg = "❌ LEAKY SOURCE — refusing to derive a contract from:\n   " + "\n   ".join(leaks)
        if not allow_leaky:
            raise SystemExit(msg + "\n   (pass --allow-leaky only for validation/inspection, never a production write)")
        print(msg + "\n   ⚠️  --allow-leaky set: proceeding for VALIDATION only.\n")

    feature_cols = _signal_members(payload)
    n_noise = sum(c["is_noise"] for c in payload["clusters"])
    scorer = payload.get("scorer")
    input_contract = payload.get("input_contract")

    prov = {
        "story": "E1.9" if scorer or input_contract else "E1.8",
        "derived": date,
        "method": (
            "non-noise (season-stratified paired-bootstrap 95% CI excludes 0) cluster "
            "members from the FULLY de-leaked clustered MDA "
            "(--bullpen-version v3 --stuff-plus-version deleaked); E1.3 rule, derived "
            "REPRODUCIBLY by betting_ml/scripts/derive_clustered_contract.py (no hand-pruning)"),
        "source_report": _rel(importance_json),
        "n_features": len(feature_cols),
        "n_noise_clusters_dropped": n_noise,
    }
    if scorer or input_contract:
        prov["scorer"] = scorer
        prov["input_contract"] = input_contract
        prov["FINAL"] = (
            f"E1.9 winner-conditioned re-prune. Clustered-MDA scorer = {scorer or 'incumbent'} "
            f"(the bake-off winner, not the incumbent), audited feature set = "
            f"{input_contract or 'default contract'}, on the both-de-leak matrix. Tests whether the "
            "winning learner wants a different feature set than the incumbent-derived slim.")
    else:
        prov["FINAL"] = (
            "Post-E1.8 full-leakage-sweep re-derivation. Both construction de-leaks applied "
            "to the source matrix: bullpen EB (E1.7, equal-weight + appeared-roster fix) and "
            "FanGraphs Stuff+/arsenal (E1.8, prior-season repoint, feature_pregame_starter_features.sql). "
            "Supersedes the INTERIM E1.7 contract that selected Stuff+ columns off the stale "
            "leaky ranking. Cleared for the E1.9 v6 retrain.")
    contract = {"feature_cols": feature_cols, "_provenance": prov}

    out = out_path.resolve() if out_path else _contract_path(target)
    print(f"target          : {target}")
    print(f"source MDA      : {importance_json.name}  (bullpen={bullpen}, stuff_plus={stuffp})")
    print(f"signal features : {len(feature_cols)}  (dropped {n_noise} noise clusters)")
    print(f"contract path   : {_rel(out)}")
    if dry_run:
        print("\n--dry-run: not written. feature_cols would be:")
        for f in feature_cols:
            print(f"  {f}")
    else:
        out.write_text(json.dumps(contract, indent=2))
        print(f"\n✅ wrote {_rel(out)}")
    return contract


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=list(_TARGET_CFG), required=True)
    ap.add_argument("--importance-json", type=Path, default=None,
                    help="MDA importance JSON (default: the canonical bullpen_v3 + stuffplus_deleaked run).")
    ap.add_argument("--allow-leaky", action="store_true",
                    help="Bypass the leakage guard (validation/inspection only — never a production write).")
    ap.add_argument("--dry-run", action="store_true", help="Print the derived contract; do not write.")
    ap.add_argument("--date", default=_dt.date.today().isoformat(), help="Provenance date (default: today).")
    ap.add_argument("--out-path", type=Path, default=None,
                    help="Write the contract here instead of the canonical path (E1.9 re-prune variants "
                         "— winner-conditioned / morning-pruned — must NOT clobber the FINAL slim contract).")
    args = ap.parse_args()

    importance_json = args.importance_json or _default_importance_json(args.target)
    derive(args.target, importance_json, allow_leaky=args.allow_leaky,
           dry_run=args.dry_run, date=args.date, out_path=args.out_path)


if __name__ == "__main__":
    main()
