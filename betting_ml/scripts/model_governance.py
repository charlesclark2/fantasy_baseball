"""model_governance.py — the operator CLI for the shared model/publish governance flow (NF-G0).

    build → validate → stage → PM/operator review → promote → publish → live readback
                                                                    ↘ rollback (ONE action)

Every verb is a separate subcommand because build and publish are separate OPERATIONS, not one
operation with a flag. `publish` and `rollback` both default to a DRY RUN and require `--execute`.

WHERE TO RUN THESE: the LAPTOP. Nothing here touches Snowflake, the box, or a Dagster op; the S3
upload itself stays inside the board exporter behind its own `--publish` guard (NF-D12), which is
why this CLI never opens a boto3 client.

    # what does the registry say is served?
    uv run python -m betting_ml.scripts.model_governance show --family nfl_fantasy \\
        --target season_projection

    # prove the whole pipeline end-to-end against a throwaway registry (touches nothing real)
    uv run python -m betting_ml.scripts.model_governance selftest

    # stage a built artifact as a challenger (publishes NOTHING)
    uv run python -m betting_ml.scripts.model_governance stage --family nfl_fantasy \\
        --target season_projection --lineage path/to/lineage.json \\
        --artifact-uri s3://credence-prod-s3-api-cache/fantasy/nfl/2026/

    # dry-run the publish (the DEFAULT — prints the plan, moves nothing)
    uv run python -m betting_ml.scripts.model_governance publish --family nfl_fantasy \\
        --target season_projection --source <staging dir> \\
        --destination s3://credence-prod-s3-api-cache/fantasy/nfl/2026/

    # roll back (also a dry run without --execute)
    uv run python -m betting_ml.scripts.model_governance rollback --family nfl_fantasy \\
        --target season_projection
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.governance import gates as G  # noqa: E402
from betting_ml.governance import publish as P  # noqa: E402
from betting_ml.governance import registry as R  # noqa: E402

log = logging.getLogger("model_governance")


def _dump(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# selftest — the SYNTHETIC PROMOTION that proves the pipeline before a real artifact touches it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def synthetic_promotion(tmp: Path) -> dict:
    """Drive the ENTIRE flow against a throwaway registry and a throwaway artifact.

    ⭐ WHY A SYNTHETIC PROMOTION IS A REQUIRED STEP AND NOT A NICE-TO-HAVE (NF-G0's Phase-A gate):
    a governance pipeline that has never had anything run through it is a set of untested claims.
    This exercises stage → validate → promote → publish(dry) → publish(execute) → readback →
    rollback, and — the part that matters — it also proves the pipeline REFUSES the things it is
    supposed to refuse: publishing before promotion, promoting on failed gates, and rolling back
    to something that was never preserved.

    Returns a record; raises on any step that does not behave as the AC requires."""
    reg = tmp / "registry.yaml"
    staged_dir, live_dir = tmp / "staged", tmp / "live"
    staged_dir.mkdir(parents=True, exist_ok=True)

    lineage = {
        "served_version": "synthetic_family_v2",
        "level_model_version": "synthetic_level_v1",
        "ordering_model_version": "synthetic_family_v2",
        "rookie_model_version": "synthetic_rookie_v1",
        "rookie_selection_status": "PM_JUDGMENT",
        "rookie_shrink_lambda": 0.5,
        "rookie_statistically_selected": False,
        "interval_model_version": {"rookie": "nf1_8", "veteran": "nf1_9", "kdst": "nf1_6"},
        "scoring_contract_version": "nf_c0e",
    }
    steps: list[dict] = []

    # ── genesis: something must already be served, or there is nothing to roll back TO ──────────
    (staged_dir / "board.json").write_text(json.dumps({"v": "synthetic_family_v1"}))
    prev_dir = tmp / "previous"
    P.copy_tree_uploader(staged_dir, str(prev_dir))
    R.register("synthetic", "board", {
        **lineage, "served_version": "synthetic_family_v1",
        "ordering_model_version": "synthetic_family_v1",
        "rookie_selection_status": "incumbent",
        "artifact_uri": str(prev_dir), "fallback_artifact_uri": str(prev_dir),
        "validation_report": "genesis (pre-governance incumbent)",
        "promotion_status": "champion"}, path=reg)
    steps.append({"step": "genesis", "served": R.served_entry("synthetic", "board", reg)
                  ["served_version"]})
    v2 = lineage["served_version"]

    # ── build (outside this CLI) → stage ────────────────────────────────────────────────────────
    (staged_dir / "board.json").write_text(json.dumps({"v": "synthetic_family_v2"}))
    digest = P.digest_tree(staged_dir)
    st = P.stage(model_family="synthetic", target="board", lineage=lineage,
                 artifact_uri=str(staged_dir), staged_digest=digest, registry_path=reg)
    if st.entry["promotion_status"] != R.STAGED_STATUS:
        raise AssertionError("stage() did not leave the entry in the staged state")
    if st.entry.get("fallback_artifact_uri") != str(prev_dir):
        raise AssertionError("stage() did not wire the rollback target from the prior champion")
    steps.append({"step": "stage", "status": st.entry["promotion_status"],
                  "fallback_wired": True, "staged_digest": digest[:12]})

    # ── build ≠ publish: publishing an UNPROMOTED entry must RAISE, never silently no-op ────────
    try:
        P.publish(model_family="synthetic", target="board", served_version=v2, source=staged_dir,
                  destination=str(live_dir), execute=True,
                  uploader=P.copy_tree_uploader, registry_path=reg)
    except ValueError:
        steps.append({"step": "publish_before_promote", "refused": True})
    else:
        raise AssertionError("publish() accepted an UNPROMOTED entry — build ≠ publish is broken")

    # ── validate: a FAILING gate must block the promotion ───────────────────────────────────────
    bad = P.validate(entry=st.entry, artifact_stamp={"served_version": "WRONG"},
                     n_staged=100, n_previous=100, n_rookies=5, n_previous_rookies=5,
                     revalidation={"pass": True}, scoring_max_abs_diff=0.0, scoring_n_compared=100,
                     claim_texts=[], rollback_exists=True)
    if bad["ready_to_promote"]:
        raise AssertionError("a mismatched model stamp did not block the promotion")
    try:
        P.promote(model_family="synthetic", target="board", served_version=v2, validation=bad,
                  validation_report="x", reviewed_by="selftest", registry_path=reg)
    except ValueError:
        steps.append({"step": "promote_on_failed_gates", "refused": True})
    else:
        raise AssertionError("promote() accepted a failing validation")

    # ── validate: the clean pass ────────────────────────────────────────────────────────────────
    good = P.validate(
        entry=st.entry,
        artifact_stamp={k: lineage[k] for k in ("served_version", "level_model_version",
                                                "ordering_model_version", "rookie_model_version",
                                                "rookie_selection_status",
                                                "scoring_contract_version")},
        payload_meta={"model_version": lineage["ordering_model_version"]},
        n_staged=100, n_previous=100, n_rookies=5, n_previous_rookies=5,
        revalidation={"pass": True}, scoring_max_abs_diff=0.0, scoring_n_compared=100,
        claim_texts=["a board-blind conservative recalibration chosen by judgment"],
        rollback_exists=Path(prev_dir).is_dir())
    if not good["ready_to_promote"]:
        raise AssertionError(f"the clean validation did not clear: {good['gates']}")
    # …and the two post-publish gates must be UNEVALUABLE here, never quietly PASS
    post = {g["gate"]: g["status"] for g in good["gates"]
            if g["gate"] in G.POST_PUBLISH_GATE_NAMES}
    if set(post.values()) != {G.UNEVALUABLE}:
        raise AssertionError(f"post-publish gates should be UNEVALUABLE pre-publish, got {post}")
    steps.append({"step": "validate", "passed": good["passed"], "unevaluable": good["unevaluable"],
                  "post_publish_gates": post})

    # ── promote ────────────────────────────────────────────────────────────────────────────────
    entry = P.promote(model_family="synthetic", target="board", served_version=v2, validation=good,
                      validation_report="synthetic", reviewed_by="selftest", registry_path=reg)
    steps.append({"step": "promote", "status": entry["promotion_status"]})

    # ── publish: the DEFAULT is a no-op ─────────────────────────────────────────────────────────
    plan = P.publish(model_family="synthetic", target="board", served_version=v2, source=staged_dir,
                     destination=str(live_dir), registry_path=reg)
    if plan.executed or live_dir.exists():
        raise AssertionError("the DEFAULT publish moved bytes — it must be a dry run")
    steps.append({"step": "publish_dry_run", "executed": False, "moved_nothing": True})

    # ── publish for real ───────────────────────────────────────────────────────────────────────
    done = P.publish(model_family="synthetic", target="board", served_version=v2, source=staged_dir,
                     destination=str(live_dir), execute=True, uploader=P.copy_tree_uploader,
                     registry_path=reg)
    steps.append({"step": "publish", "executed": done.executed})

    # ── live readback ──────────────────────────────────────────────────────────────────────────
    rb = P.live_readback(
        model_family="synthetic", target="board",
        live_payload={"model_version": lineage["ordering_model_version"],
                      "rookie_policy": {"selection_status": "PM_JUDGMENT", "shrink_lambda": 0.5,
                                        "statistically_selected": False}},
        live_digest=P.digest_tree(live_dir),
        backend_version=lineage["served_version"], frontend_version=lineage["served_version"],
        registry_path=reg)
    if not rb["pass"]:
        raise AssertionError(f"live readback failed: {rb}")
    steps.append({"step": "live_readback", "pass": True,
                  "checked": [c["check"] for c in rb["checks"]]})

    # ── rollback: dry run, then for real, then BYTE-FOR-BYTE ────────────────────────────────────
    dry = P.rollback(model_family="synthetic", target="board", registry_path=reg)
    if dry["executed"]:
        raise AssertionError("the DEFAULT rollback executed — it must be a dry run")
    before = P.digest_tree(live_dir)
    P.rollback(model_family="synthetic", target="board", execute=True,
               restorer=P.copy_tree_restorer, destination=str(live_dir), registry_path=reg)
    after, expected = P.digest_tree(live_dir), P.digest_tree(prev_dir)
    if after != expected:
        raise AssertionError("rollback did not restore the previous artifact byte-for-byte")
    steps.append({"step": "rollback", "dry_run_first": True, "byte_identical": True,
                  "live_before": before[:12], "live_after": after[:12],
                  "previous": expected[:12]})
    steps.append({"step": "registry_after_rollback",
                  "served_version": (R.served_entry("synthetic", "board", reg) or {})
                  .get("served_version")})
    return {"pass": True, "steps": steps}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _fam(p):
        p.add_argument("--family", required=True)
        p.add_argument("--target", required=True)
        p.add_argument("--registry", type=Path, default=R._REGISTRY_PATH)
        p.add_argument("--version", default=None,
                       help="served_version — part of the registry key. Omit to act on whatever "
                            "is currently SERVED.")
        return p

    _fam(sub.add_parser("show", help="print the registry entry + what is SERVED"))
    sub.add_parser("list", help="print every SERVED entry").add_argument(
        "--registry", type=Path, default=R._REGISTRY_PATH)
    sub.add_parser("selftest", help="run the synthetic promotion against a throwaway registry")

    p = _fam(sub.add_parser("stage", help="register a BUILT artifact as a challenger (no publish)"))
    p.add_argument("--lineage", type=Path, required=True, help="JSON file of the lineage fields")
    p.add_argument("--artifact-uri", required=True)
    p.add_argument("--staging-dir", type=Path, default=None,
                   help="local staging dir to digest (recorded for the live-payload gate)")

    p = _fam(sub.add_parser("publish", help="publish the PROMOTED artifact (DRY RUN by default)"))
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--destination", required=True)
    p.add_argument("--execute", action="store_true",
                   help="actually move bytes. Without this it is a dry run.")

    p = _fam(sub.add_parser("rollback", help="restore the previous artifact (DRY RUN by default)"))
    p.add_argument("--destination", default=None)
    p.add_argument("--execute", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "selftest":
        with tempfile.TemporaryDirectory() as td:
            rec = synthetic_promotion(Path(td))
        _dump(rec)
        print("\n✅ SYNTHETIC PROMOTION PASSED — stage → validate → promote → publish(dry) → "
              "publish → readback → rollback, and every refusal fired.")
        return 0

    if args.cmd == "list":
        _dump(R.list_served(args.registry))
        return 0

    if args.cmd == "show":
        served = R.served_entry(args.family, args.target, args.registry)
        entry = (R.get_entry(args.family, args.target, args.version, args.registry)
                 if args.version else served)
        _dump({"entry": entry,
               "served_version": (served or {}).get("served_version"),
               "authority": "this registry is the NAMED AUTHORITY for what is served"})
        return 0

    if args.cmd == "stage":
        lineage = json.loads(Path(args.lineage).read_text())
        digest = P.digest_tree(args.staging_dir) if args.staging_dir else None
        st = P.stage(model_family=args.family, target=args.target, lineage=lineage,
                     artifact_uri=args.artifact_uri, staged_digest=digest,
                     registry_path=args.registry)
        _dump(st.as_dict())
        print("\nSTAGED — nothing was published. Run the gates, then `promote`, then `publish`.")
        return 0

    if args.cmd == "publish":
        plan = P.publish(model_family=args.family, target=args.target,
                         served_version=args.version, source=args.source,
                         destination=args.destination, execute=args.execute,
                         uploader=P.copy_tree_uploader if args.execute else None,
                         registry_path=args.registry)
        _dump(plan.as_dict())
        return 0

    if args.cmd == "rollback":
        rec = P.rollback(model_family=args.family, target=args.target,
                         served_version=args.version, execute=args.execute,
                         restorer=P.copy_tree_restorer if args.execute else None,
                         destination=args.destination, registry_path=args.registry)
        _dump(rec)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
