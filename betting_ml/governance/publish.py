"""publish.py — the promotion flow: build ≠ publish, and publish DEFAULTS TO A NO-OP.

    build → validate → stage → PM/operator review → promote → publish → live readback
                                                                   ↘ rollback (one action)

⭐ WHY BUILD AND PUBLISH ARE SEPARATE FUNCTIONS AND NOT ONE FLAG
Because a fused build-and-ship has already cost this repo real incidents. The NF-D12 publish guard
exists because the draft-board exporter used to upload whenever a bucket happened to resolve; the
NF3.4 near-miss was one `--publish` away from shipping another story's unreleased board. `stage()`
writes NOTHING outside the registry and the staging directory; `publish()` will not move a byte
unless it is handed `execute=True` AND the entry is already promoted. Two independent conditions,
because a single one is a single typo.

⚠️ `publish(execute=False)` RETURNS A PLAN — it is a dry run in the strict sense: it computes what
WOULD move, and returns it, having moved nothing. That is the AC ("publish defaults to no-op/
dry-run") implemented as a default ARGUMENT rather than as a documented habit.

🔁 ROLLBACK IS ONE OPERATOR ACTION: `rollback(family, target)` — it restores the previous artifact
from `fallback_artifact_uri` and re-points the registry. It is one call because a rollback executed
under pressure must not require the operator to remember a sequence.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from betting_ml.governance import gates as G
from betting_ml.governance import registry as R


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(payload: bytes) -> str:
    """The digest the `live_payload_matches_staged` gate compares. SHA-256 over raw bytes — the
    comparison must be BYTE-for-byte, so no JSON re-serialisation is allowed to sneak in."""
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str | None:
    p = Path(path)
    return digest_bytes(p.read_bytes()) if p.is_file() else None


def digest_tree(root: Path, pattern: str = "*.json") -> str | None:
    """A stable digest over a DIRECTORY of published files (the api-cache export is many blobs).

    Sorted by relative path so the digest depends on content, never on filesystem order."""
    d = Path(root)
    if not d.is_dir():
        return None
    files = sorted(p for p in d.rglob(pattern) if p.is_file())
    if not files:
        return None
    h = hashlib.sha256()
    for p in files:
        h.update(str(p.relative_to(d)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# stage
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class StageResult:
    key: str
    entry: dict
    staged_digest: str | None

    def as_dict(self) -> dict:
        return {"key": self.key, "staged_digest": self.staged_digest, "entry": self.entry}


def stage(*, model_family: str, target: str, lineage: dict[str, Any],
          artifact_uri: str, staged_digest: str | None = None,
          registry_path: Path = R._REGISTRY_PATH) -> StageResult:
    """Register a BUILT artifact as a challenger. Publishes nothing.

    The prior SERVED entry's `artifact_uri` becomes this entry's `fallback_artifact_uri`
    automatically — rollback is wired at STAGE time, not remembered at publish time, because the
    moment you need it is the moment nobody is thinking clearly."""
    version = lineage.get("served_version")
    if not version:
        raise ValueError("stage() needs `served_version` in the lineage — it is the registry key")
    prior = R.served_entry(model_family, target, registry_path)
    if prior and prior.get("served_version") == version:
        raise ValueError(
            f"refusing to stage {version!r} — it is ALREADY the served version. A challenger that "
            f"reuses the champion's version string would overwrite the champion's entry and destroy "
            f"its rollback record. Bump the version.")
    fields: dict[str, Any] = {
        **lineage,
        "artifact_uri": artifact_uri,
        "promotion_status": R.STAGED_STATUS,
        "generated_at": _now(),
        "staged_digest": staged_digest,
    }
    if prior and prior.get("artifact_uri"):
        fields.setdefault("fallback_artifact_uri", prior["artifact_uri"])
        fields.setdefault("previous_served_version", prior.get("served_version"))
    entry = R.register(model_family, target, fields, path=registry_path)
    return StageResult(R.entry_key(model_family, target, version), entry, staged_digest)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# validate + promote
# ══════════════════════════════════════════════════════════════════════════════════════════════
def validate(*, entry: dict, **gate_inputs) -> dict:
    """Run the ten gates and return the roll-up. Does not mutate the registry.

    The two post-publish gates are permitted to be UNEVALUABLE here and ONLY here — see
    `gates.POST_PUBLISH_GATE_NAMES` for why that exemption is enumerated rather than general."""
    results = G.run_gates(entry=entry, **gate_inputs)
    summary = G.summarize(results)
    summary["ready_to_promote"] = G.all_passed(
        results, allow_unevaluable=G.POST_PUBLISH_GATE_NAMES)
    summary["evaluated_at"] = _now()
    return summary


def promote(*, model_family: str, target: str, served_version: str, validation: dict,
            validation_report: str, reviewed_by: str,
            registry_path: Path = R._REGISTRY_PATH) -> dict:
    """Promote a staged challenger to SERVED, refusing on anything the gates did not clear.

    `reviewed_by` is required and recorded: the flow includes a human review step, and a review
    with no name attached is not a review."""
    if not validation.get("ready_to_promote"):
        failed = [g["gate"] for g in validation.get("gates", []) if g["status"] != G.PASS]
        raise ValueError(
            "refusing to promote — the gates did not clear: " + ", ".join(failed) +
            ". Fix the finding; do NOT loosen the gate.")
    if not reviewed_by:
        raise ValueError("refusing to promote without a named reviewer (the flow has a human "
                         "review step; an unattributed review is not one)")
    R.register(model_family, target,
               {"validation_report": validation_report, "reviewed_by": reviewed_by},
               served_version=served_version, path=registry_path)
    return R.promote(model_family, target, served_version,
                     new_status=R.SERVED_STATUS, path=registry_path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# publish — DEFAULTS TO A NO-OP
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class PublishPlan:
    executed: bool
    reason: str
    source: str
    destination: str
    staged_digest: str | None
    served_version: str | None

    def as_dict(self) -> dict:
        return {"executed": self.executed, "reason": self.reason, "source": self.source,
                "destination": self.destination, "staged_digest": self.staged_digest,
                "served_version": self.served_version}


def publish(*, model_family: str, target: str, served_version: str,
            source: Path | str, destination: str,
            execute: bool = False,
            uploader: Callable[[Path, str], None] | None = None,
            registry_path: Path = R._REGISTRY_PATH) -> PublishPlan:
    """Publish the promoted artifact. **`execute` defaults to False — a plan, not a publish.**

    Two independent conditions must hold before a byte moves:
      1. `execute=True` — the caller deliberately asked for it, and
      2. the entry is already `champion` — i.e. it went through validate + promote.

    A promoted-but-unpublished entry is a normal, safe state; an unpromoted publish is not, so it
    RAISES rather than silently no-opping (a silent skip on an outward-facing action is the
    ALERT-tier violation this repo has been bitten by repeatedly)."""
    entry = R.get_entry(model_family, target, served_version, registry_path)
    staged_digest = entry.get("staged_digest")
    src = Path(source)

    if entry.get("promotion_status") != R.SERVED_STATUS:
        raise ValueError(
            f"refusing to publish '{R.entry_key(model_family, target, served_version)}' — its "
            f"promotion_status is "
            f"{entry.get('promotion_status')!r}, not {R.SERVED_STATUS!r}. Run validate + promote "
            f"first (build ≠ publish).")

    if not execute:
        return PublishPlan(False, "DRY-RUN (the default) — nothing was uploaded; pass execute=True "
                                  "to actually publish", str(src), destination, staged_digest,
                           served_version)

    if uploader is None:
        raise ValueError("execute=True but no uploader was supplied — refusing to claim a publish "
                         "this function cannot perform")
    uploader(src, destination)
    R.register(model_family, target, {"published_at": _now(), "published_to": destination},
               served_version=served_version, path=registry_path)
    return PublishPlan(True, "published", str(src), destination, staged_digest, served_version)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# live readback
# ══════════════════════════════════════════════════════════════════════════════════════════════
def live_readback(*, model_family: str, target: str, served_version: str | None = None,
                  live_payload: dict | None,
                  live_digest: str | None = None,
                  backend_version: str | None = None, frontend_version: str | None = None,
                  registry_path: Path = R._REGISTRY_PATH) -> dict:
    """Verify what is LIVE against what the registry says is served — version AND rookie policy.

    ⭐ THE ROOKIE POLICY IS READ BACK, NOT ONLY THE VERSION. A publish can carry the right version
    string and the wrong rookie treatment (the recalibration silently off, or on at the wrong
    shrink); a version-only readback would call that a success."""
    entry = (R.get_entry(model_family, target, served_version, registry_path) if served_version
             else R.served_entry(model_family, target, registry_path))
    if entry is None:
        raise KeyError(f"nothing is SERVED for ({model_family}, {target}) — cannot read back "
                       f"against an authority that names no version")
    payload = live_payload or {}
    stamp = payload.get("rookiePolicy") or payload.get("rookie_policy") or {}

    checks: list[dict] = []

    def _check(name: str, want: Any, got: Any, *, required: bool = True) -> None:
        if got is None:
            checks.append({"check": name, "status": G.UNEVALUABLE if required else G.PASS,
                           "want": want, "got": None,
                           "detail": "absent from the live payload"})
            return
        ok = str(want) == str(got)
        checks.append({"check": name, "status": G.PASS if ok else G.FAIL,
                       "want": want, "got": got,
                       "detail": "matches the registry" if ok else "DISAGREES with the registry"})

    _check("served_version", entry.get("served_version"),
           payload.get("model_version") or payload.get("served_version"))
    _check("rookie_selection_status", entry.get("rookie_selection_status"),
           stamp.get("selection_status"))
    _check("rookie_shrink_lambda", entry.get("rookie_shrink_lambda"), stamp.get("shrink_lambda"))
    _check("rookie_statistically_selected", entry.get("rookie_statistically_selected"),
           stamp.get("statistically_selected"))

    post = [
        G.live_payload_matches_staged(entry.get("staged_digest"), live_digest),
        G.clients_agree_on_version(entry, backend_version, frontend_version),
    ]
    ok = (all(c["status"] == G.PASS for c in checks)
          and all(r.status == G.PASS for r in post))
    return {"key": R.entry_key(model_family, target, entry["served_version"]),
            "read_at": _now(), "pass": ok,
            "checks": checks, "post_publish_gates": [r.as_dict() for r in post]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# rollback — ONE operator action
# ══════════════════════════════════════════════════════════════════════════════════════════════
def rollback(*, model_family: str, target: str, served_version: str | None = None,
             execute: bool = False,
             restorer: Callable[[str, str], None] | None = None,
             destination: str | None = None,
             registry_path: Path = R._REGISTRY_PATH) -> dict:
    """Restore the previous served artifact. ONE call, and it is a dry run unless `execute=True`.

    Symmetric with `publish` on purpose: the same two-condition shape means an operator who has
    used one already knows the other, which matters when the second one is used in an incident."""
    entry = (R.get_entry(model_family, target, served_version, registry_path) if served_version
             else R.served_entry(model_family, target, registry_path))
    if entry is None:
        raise KeyError(f"nothing is SERVED for ({model_family}, {target}) — nothing to roll back")
    key = R.entry_key(model_family, target, entry["served_version"])
    fallback = entry.get("fallback_artifact_uri")
    if not fallback:
        raise ValueError(
            f"cannot roll back '{key}' — no fallback_artifact_uri. "
            f"The promotion that produced this entry did not preserve its predecessor.")
    dest = destination or entry.get("published_to") or entry.get("artifact_uri")
    plan = {"key": key, "restores": fallback, "destination": dest,
            "restores_version": entry.get("previous_served_version"), "executed": False}
    if not execute:
        plan["reason"] = ("DRY-RUN (the default) — nothing was restored; pass execute=True to "
                          "actually roll back")
        return plan
    if restorer is None:
        raise ValueError("execute=True but no restorer was supplied — refusing to claim a rollback "
                         "this function cannot perform")
    restorer(fallback, dest)
    # ⭐ The rollback RE-PROMOTES the predecessor's own entry rather than rewriting this one's
    #    version in place. Overwriting would leave the registry claiming the old version at the new
    #    key — a record that reads coherent and is false. `promote()` then deprecates the rolled-back
    #    champion automatically, so the history stays readable: what was served, and what replaced it.
    prev_version = entry.get("previous_served_version")
    R.register(model_family, target, {"rolled_back_at": _now(),
                                      "rolled_back_to": prev_version},
               served_version=entry["served_version"], path=registry_path)
    R.promote(model_family, target, entry["served_version"], new_status="deprecated",
              path=registry_path)
    if prev_version:
        prior_key = R.entry_key(model_family, target, prev_version)
        if prior_key in R.load_registry(registry_path):
            R.register(model_family, target, {"promotion_status": R.SERVED_STATUS,
                                              "restored_at": _now()},
                       served_version=prev_version, path=registry_path)
    plan["executed"] = True
    plan["reason"] = "rolled back"
    return plan


# ══════════════════════════════════════════════════════════════════════════════════════════════
# local helpers used by the CLI + the synthetic proof
# ══════════════════════════════════════════════════════════════════════════════════════════════
def copy_tree_uploader(src: Path, destination: str) -> None:
    """A filesystem 'uploader' — used by the dry-run/synthetic proof and by local staging.

    The real S3 upload lives in the exporter (`export_draft_board_json._upload_to_s3`, behind its
    own `--publish` guard); this package never opens a boto3 client, which is what keeps it
    importable in the fast gate."""
    dst = Path(destination)
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(Path(src).rglob("*")):
        if p.is_file():
            out = dst / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)


def copy_tree_restorer(fallback_uri: str, destination: str) -> None:
    copy_tree_uploader(Path(fallback_uri), destination)


def write_record(record: dict, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(record, indent=2, default=str))
