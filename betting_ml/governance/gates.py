"""gates.py — the ten REQUIRED promotion gates, as pure functions.

Every gate takes ALREADY-LOADED data and returns a `GateResult`. None of them does IO. That is not
tidiness: CI mocks all IO in this repo, so a gate that fetched its own inputs would be untestable in
the fast gate and would only ever be exercised on the box — which is precisely the class of
"validated nowhere" code the E11.30 audit found.

⚠️ EVERY GATE MUST BE ABLE TO FAIL, AND AN UNEVALUABLE GATE IS **NOT** A PASS.
NF1.7 (a): an anchor that fails to fit makes its check vacuously true. Each gate here returns
`status="UNEVALUABLE"` when its input is absent, and `all_passed()` treats UNEVALUABLE as NOT
passing. A gate that cannot see its subject has examined nothing, and scoring that green is how a
governance layer becomes decoration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

PASS = "PASS"
FAIL = "FAIL"
UNEVALUABLE = "UNEVALUABLE"


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    detail: str
    data: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == PASS

    def as_dict(self) -> dict:
        return {"gate": self.name, "status": self.status, "detail": self.detail, **
                ({"data": self.data} if self.data else {})}


def _ok(name: str, detail: str, **data) -> GateResult:
    return GateResult(name, PASS, detail, data)


def _bad(name: str, detail: str, **data) -> GateResult:
    return GateResult(name, FAIL, detail, data)


def _blind(name: str, detail: str, **data) -> GateResult:
    return GateResult(name, UNEVALUABLE, detail, data)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. model-stamp consistency — the registry is the AUTHORITY, the artifact must agree with it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def model_stamp_consistency(entry: dict, artifact_stamp: dict | None) -> GateResult:
    """The artifact's embedded stamps must reconcile against the registry's composite lineage.

    ⭐ THE DIRECTION MATTERS. On a mismatch this FAILS rather than adopting the artifact's value.
    The registry is the named authority (KP-V2.0's lesson: a model whose version-of-record lives
    only in code + an S3 path has no third party to reconcile against, so nothing can ever catch a
    drift). Taking the artifact's word would restore exactly that hole with a registry-shaped lid."""
    name = "model_stamp_consistency"
    if not artifact_stamp:
        return _blind(name, "no artifact stamp supplied — nothing to reconcile against the registry")
    checked, mismatches = [], []
    for field_name in ("served_version", "level_model_version", "ordering_model_version",
                       "rookie_model_version", "rookie_selection_status",
                       "scoring_contract_version"):
        want, got = entry.get(field_name), artifact_stamp.get(field_name)
        if want is None or got is None:
            continue
        checked.append(field_name)
        if str(want) != str(got):
            mismatches.append(f"{field_name}: registry={want!r} artifact={got!r}")
    if not checked:
        return _blind(name, "the artifact stamp shares NO lineage field with the registry entry — "
                            "an empty intersection is not agreement")
    if mismatches:
        return _bad(name, "artifact stamp disagrees with the registry (the registry is the "
                          "authority): " + "; ".join(mismatches), mismatches=mismatches)
    return _ok(name, f"artifact stamp agrees with the registry on {len(checked)} lineage field(s)",
               checked=checked)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. projection-source consistency
# ══════════════════════════════════════════════════════════════════════════════════════════════
def projection_source_consistency(entry: dict, payload_meta: dict | None) -> GateResult:
    """The published payload must declare the projection lineage the registry says is served.

    NF1.5b shipped `projectionSource`/`projectionLabel` into the payload precisely so a surface can
    carry its caveat from the DATA. A payload whose source label has drifted from the registry is a
    board presenting one lineage's caveats over another lineage's numbers."""
    name = "projection_source_consistency"
    if not payload_meta:
        return _blind(name, "no payload meta supplied")
    want = entry.get("ordering_model_version")
    got = payload_meta.get("model_version")
    src = payload_meta.get("projection_source") or payload_meta.get("projectionSource")
    if got is None and src is None:
        return _blind(name, "payload carries neither model_version nor projection_source")
    if want and got and str(want) != str(got):
        return _bad(name, f"payload model_version={got!r} but the registry serves "
                          f"ordering_model_version={want!r}")
    want_src = entry.get("projection_source")
    if want_src and src and str(want_src) != str(src):
        return _bad(name, f"payload projection_source={src!r} but the registry serves {want_src!r}")
    return _ok(name, f"payload lineage agrees with the registry (model_version={got!r}, "
                     f"projection_source={src!r})")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. universe count
# ══════════════════════════════════════════════════════════════════════════════════════════════
def universe_count(n_staged: int | None, n_previous: int | None, *,
                   tolerance: float = 0.02) -> GateResult:
    """The staged board must hold the same player universe as the one it replaces, within tolerance.

    ⭐ THIS GATE EXISTS BECAUSE THE FAILURE ALREADY HAPPENED. NF1.5b's first implementation carried
    716 players against the shipped 784 — 68 returning veterans would have VANISHED from the draft
    board on the flip, and nothing would have said so. A count comparison is cheap and would have
    caught it outright."""
    name = "universe_count"
    if n_staged is None or n_previous is None:
        return _blind(name, "universe counts unavailable on one or both sides")
    if n_previous <= 0:
        return _blind(name, f"previous universe is {n_previous} — no baseline to compare against")
    drift = abs(n_staged - n_previous) / n_previous
    if drift > tolerance:
        return _bad(name, f"universe moved {n_previous} → {n_staged} ({drift:.1%} > "
                          f"{tolerance:.0%} tolerance)", n_staged=n_staged, n_previous=n_previous,
                    drift=round(drift, 4))
    return _ok(name, f"universe {n_previous} → {n_staged} ({drift:.2%} drift, within "
                     f"{tolerance:.0%})", n_staged=n_staged, n_previous=n_previous)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. rookie coverage
# ══════════════════════════════════════════════════════════════════════════════════════════════
def rookie_coverage(n_rookies: int | None, n_previous_rookies: int | None, *,
                    min_rookies: int = 1) -> GateResult:
    """Rookies must still be on the board, in the same number, after a rookie-leg change.

    NF-D12 is the precedent: a rookie-leg coverage hole (Carson Beck) shipped unseen. A change that
    touches the rookie POINT must not silently change WHICH rookies exist."""
    name = "rookie_coverage"
    if n_rookies is None:
        return _blind(name, "staged rookie count unavailable")
    if n_rookies < min_rookies:
        return _bad(name, f"staged board carries {n_rookies} rookie(s), below the minimum "
                          f"{min_rookies}", n_rookies=n_rookies)
    if n_previous_rookies is not None and n_rookies != n_previous_rookies:
        return _bad(name, f"rookie count moved {n_previous_rookies} → {n_rookies}; a LEVEL change "
                          f"must not add or drop rookies", n_rookies=n_rookies,
                    n_previous=n_previous_rookies)
    return _ok(name, f"{n_rookies} rookie(s), unchanged", n_rookies=n_rookies)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. interval floors
# ══════════════════════════════════════════════════════════════════════════════════════════════
def interval_floors(revalidation: dict | None) -> GateResult:
    """Every per-position 80% coverage floor still holds after the change.

    Consumes `run_interval_revalidation`'s report verbatim. ⛔ A floor breach is a RE-SELECTION
    trigger, never a reason to move the floor (E2.1-r; NF1.8 §1) — so this gate has no tolerance
    knob and cannot be tuned into passing."""
    name = "interval_floors"
    if not revalidation:
        return _blind(name, "no interval re-validation report supplied — a level shift moves the "
                            "band CENTRE, so the floors MUST be re-read, not assumed")
    if "pass" not in revalidation:
        return _blind(name, "re-validation report carries no verdict key")
    misses = []
    for pop in ("rookies", "veterans", "kdst"):
        block = revalidation.get(pop) or {}
        for p in block.get("misses") or []:
            misses.append(f"{pop}:{p}")
    if not revalidation.get("pass") or misses:
        return _bad(name, "coverage floor BREACH — re-run that population's bake-off, do NOT move "
                          f"the floor. Breaches: {misses or 'see report'}", misses=misses)
    return _ok(name, "all per-position 80% coverage floors met after the change")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. scoring parity
# ══════════════════════════════════════════════════════════════════════════════════════════════
def scoring_parity(max_abs_diff: float | None, *, tol: float = 1e-6,
                   n_compared: int | None = None) -> GateResult:
    """A player's displayed points must equal what the scoring engine derives from his stat line.

    NF-D21 moves the rookie point by rescaling the whole stat line, so this is the gate that proves
    the line came with it — a board whose points disagree with its own yards and touchdowns is
    visibly broken to any user who adds it up."""
    name = "scoring_parity"
    if max_abs_diff is None:
        return _blind(name, "no scoring-parity measurement supplied")
    if n_compared is not None and n_compared <= 0:
        return _blind(name, "scoring parity compared ZERO rows — a check with no subject is not a "
                            "pass")
    if max_abs_diff > tol:
        return _bad(name, f"scored line disagrees with the displayed point by up to "
                          f"{max_abs_diff:.6g} (tol {tol:g})", max_abs_diff=max_abs_diff)
    return _ok(name, f"scored line reproduces the displayed point (max |Δ| {max_abs_diff:.3g} over "
                     f"{n_compared if n_compared is not None else '?'} row(s))",
               max_abs_diff=max_abs_diff)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. track-record copy compatibility
# ══════════════════════════════════════════════════════════════════════════════════════════════
def track_record_copy_compatible(claim_texts: Iterable[str] | None,
                                 denylist: Sequence[str] | None = None) -> GateResult:
    """Nothing published alongside this promotion may make a claim the track-record page forbids.

    NF-D17 measured the shipped Δρ's own 90% interval as [−0.006, +0.051] — it INCLUDES ZERO — so
    the page's hedging is load-bearing, not decoration, and its `_CLAIM_DENYLIST` must not be
    loosened by a model release writing stronger copy elsewhere."""
    name = "track_record_copy_compatible"
    if claim_texts is None:
        return _blind(name, "no claim copy supplied for screening")
    terms = [t.lower() for t in (denylist if denylist is not None else _DEFAULT_CLAIM_DENYLIST)]
    hits = []
    for text in claim_texts:
        low = str(text).lower()
        hits += [f"{t!r} in {str(text)[:80]!r}" for t in terms if t in low]
    if hits:
        return _bad(name, "copy makes a claim the track-record discipline forbids: "
                    + "; ".join(hits), hits=hits)
    return _ok(name, "copy carries no forbidden market/edge claim")


#: Mirrors the public track-record page's own denylist spirit: no beat-the-market claim, no
#: universal ("every position") claim, no edge/guarantee language.
_DEFAULT_CLAIM_DENYLIST: tuple[str, ...] = (
    "we beat", "beats the market", "beat the market", "every position", "guaranteed",
    "outperforms the market", "market-beating", "profitable", "edge over the market",
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. rollback artifact exists
# ══════════════════════════════════════════════════════════════════════════════════════════════
def rollback_artifact_exists(entry: dict, exists: bool | None) -> GateResult:
    """A promotion is only reversible if the thing it replaces is still there.

    `exists` is passed in (the caller does the stat/head-object) so the gate stays IO-free. `None`
    means the caller could not determine it — UNEVALUABLE, not a pass."""
    name = "rollback_artifact_exists"
    uri = entry.get("fallback_artifact_uri")
    if not uri:
        return _bad(name, "entry names NO fallback_artifact_uri — this promotion would not be "
                          "reversible")
    if exists is None:
        return _blind(name, f"could not determine whether the rollback artifact exists at {uri}")
    if not exists:
        return _bad(name, f"fallback_artifact_uri {uri} does not exist", uri=uri)
    return _ok(name, f"rollback artifact present at {uri}", uri=uri)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. live payload == staged artifact
# ══════════════════════════════════════════════════════════════════════════════════════════════
def live_payload_matches_staged(staged_digest: str | None, live_digest: str | None) -> GateResult:
    """What is live must be byte-identical to what was reviewed and promoted.

    Digests are supplied by the caller. `None` on either side is UNEVALUABLE: pre-publish there IS
    no live payload yet, and calling that a pass would let the publish step claim a verification it
    could not have performed."""
    name = "live_payload_matches_staged"
    if staged_digest is None or live_digest is None:
        return _blind(name, "one side has no digest (pre-publish, or the live read failed) — "
                            "cannot claim the live payload matches what was reviewed")
    if staged_digest != live_digest:
        return _bad(name, f"live payload digest {live_digest[:12]}… != staged {staged_digest[:12]}…",
                    staged=staged_digest, live=live_digest)
    return _ok(name, f"live payload is byte-identical to the staged artifact ({live_digest[:12]}…)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. frontend + backend consume the same version
# ══════════════════════════════════════════════════════════════════════════════════════════════
def clients_agree_on_version(entry: dict, backend_version: str | None,
                             frontend_version: str | None) -> GateResult:
    """Backend and frontend must both be reading the version the registry serves.

    ⭐ THE DEPLOY-SKEW GATE. `frontend/` auto-deploys on push while the API Lambda ships only via a
    manual `deploy.sh` (NF-C0), so the two halves of a release ALWAYS have a skew window. This gate
    is what turns "we think they match" into a read."""
    name = "clients_agree_on_version"
    want = entry.get("served_version")
    if backend_version is None and frontend_version is None:
        return _blind(name, "neither client version could be read")
    seen = {k: v for k, v in (("backend", backend_version), ("frontend", frontend_version))
            if v is not None}
    bad = {k: v for k, v in seen.items() if str(v) != str(want)}
    if bad:
        return _bad(name, f"client(s) not on the served version {want!r}: {bad}", want=want, **seen)
    if len(seen) < 2:
        return _blind(name, f"only {sorted(seen)} version(s) could be read — a one-sided read "
                            f"cannot prove the two clients AGREE")
    return _ok(name, f"backend and frontend both on {want!r}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Composition
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The ten gates NF-G0 requires, in the order the promotion flow runs them.
REQUIRED_GATE_NAMES: tuple[str, ...] = (
    "model_stamp_consistency",
    "projection_source_consistency",
    "universe_count",
    "rookie_coverage",
    "interval_floors",
    "scoring_parity",
    "track_record_copy_compatible",
    "rollback_artifact_exists",
    "live_payload_matches_staged",
    "clients_agree_on_version",
)

#: Gates that CANNOT be evaluated before the artifact is live. They are expected UNEVALUABLE at
#: stage/promote time and are re-run at readback. Naming them explicitly is what stops "it was
#: UNEVALUABLE" from becoming a general-purpose excuse — every OTHER gate must resolve.
POST_PUBLISH_GATE_NAMES: tuple[str, ...] = (
    "live_payload_matches_staged",
    "clients_agree_on_version",
)


def run_gates(*, entry: dict, artifact_stamp: dict | None = None,
              payload_meta: dict | None = None,
              n_staged: int | None = None, n_previous: int | None = None,
              n_rookies: int | None = None, n_previous_rookies: int | None = None,
              revalidation: dict | None = None,
              scoring_max_abs_diff: float | None = None, scoring_n_compared: int | None = None,
              claim_texts: Iterable[str] | None = None,
              rollback_exists: bool | None = None,
              staged_digest: str | None = None, live_digest: str | None = None,
              backend_version: str | None = None,
              frontend_version: str | None = None) -> list[GateResult]:
    """Run all ten gates over already-loaded inputs, in `REQUIRED_GATE_NAMES` order."""
    return [
        model_stamp_consistency(entry, artifact_stamp),
        projection_source_consistency(entry, payload_meta),
        universe_count(n_staged, n_previous),
        rookie_coverage(n_rookies, n_previous_rookies),
        interval_floors(revalidation),
        scoring_parity(scoring_max_abs_diff, n_compared=scoring_n_compared),
        track_record_copy_compatible(claim_texts),
        rollback_artifact_exists(entry, rollback_exists),
        live_payload_matches_staged(staged_digest, live_digest),
        clients_agree_on_version(entry, backend_version, frontend_version),
    ]


def all_passed(results: Sequence[GateResult], *, allow_unevaluable: Sequence[str] = ()) -> bool:
    """True only when every gate PASSED.

    ⚠️ UNEVALUABLE IS NOT A PASS (NF1.7 (a)). `allow_unevaluable` exists for exactly one legitimate
    case — the post-publish gates, which have no live payload to read at stage/promote time — and
    the caller must NAME them, so a gate can never be waved through by accident."""
    allowed = set(allow_unevaluable)
    for r in results:
        if r.status == PASS:
            continue
        if r.status == UNEVALUABLE and r.name in allowed:
            continue
        return False
    return True


def summarize(results: Sequence[GateResult]) -> dict:
    """A JSON-able roll-up for the promotion record."""
    return {
        "n": len(results),
        "passed": sum(1 for r in results if r.status == PASS),
        "failed": sum(1 for r in results if r.status == FAIL),
        "unevaluable": sum(1 for r in results if r.status == UNEVALUABLE),
        "gates": [r.as_dict() for r in results],
    }
