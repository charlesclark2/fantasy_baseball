"""registry.py — the SHARED model-family registry: composite lineage + the promotion state machine.

⭐ WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
This is the baseball sub-model registry's shape, lifted so a second model family can use it. It is
NOT a new registry design. The promotion state machine below is the SAME OBJECT
`betting_ml/scripts/sub_model_registry.py` validates against — it imports `PROMOTION_STATES` and
`VALID_TRANSITIONS` from here — so the two families cannot drift apart into two governance shapes.
`betting_ml/tests/test_model_governance.py::test_the_baseball_registry_shares_this_exact_state_machine`
holds that identity mechanically.

⚠️ VOCABULARY NOTE (worth reading once): the delivery epic's illustrative YAML writes
`promotion_status: served`. The SHARED machine's terminal live state is `champion`, inherited from
the baseball registry. Adding a `served` state purely for fantasy would be exactly the parallel
vocabulary the brief forbids, so the fantasy family uses `champion` and `SERVED_STATUS` names the
mapping in ONE place — `served_entry()` answers the family-facing question ("what is served?")
without a second state machine to keep in sync.

────────────────────────────────────────────────────────────────────────────────────────────────
COMPOSITE LINEAGE — why the schema is shaped this way
────────────────────────────────────────────────────────────────────────────────────────────────
The NFL-fantasy board is not one model, it is a STACK, and the stack members version
INDEPENDENTLY. NF1.5b's re-land made that concrete: the served board is MVP-1's calibrated point
LEVEL with NF1.5's learned ORDER assigned on top of it, the rookie leg is its own model, and the
80% band is a THIRD family split three ways (rookie NF1.8 / veteran NF1.9 / K-DST NF1.6). A
registry with a single `model_version` field cannot express that, and the failure mode is not
theoretical — a stale ordering version stamped over a fresh level model reads as one coherent
release while being two.

So `LINEAGE_FIELDS` names each member. `served_version` is the FAMILY's version-of-record (the
thing a payload stamps); the members say what it is MADE of.

────────────────────────────────────────────────────────────────────────────────────────────────
🔑 THE REGISTRY IS THE NAMED AUTHORITY
────────────────────────────────────────────────────────────────────────────────────────────────
When the registry and an artifact stamp disagree, that is a GATE FAILURE — never a silent
"trust the artifact". This is the KP-V2.0 lesson stated as code: the MLB K-props model has NO
registry entry, so its version-of-record lives in code + an S3 path and reconciliation is
structurally impossible. A family on this registry always has a third party to reconcile against.
"""
from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "models" / "model_family_registry.yaml"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The promotion state machine — SHARED, and imported by `betting_ml/scripts/sub_model_registry.py`
# ══════════════════════════════════════════════════════════════════════════════════════════════
PROMOTION_STATES: frozenset[str] = frozenset({"pending", "challenger", "champion", "deprecated"})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending":    frozenset({"challenger", "deprecated"}),
    "challenger": frozenset({"champion", "deprecated"}),
    "champion":   frozenset({"deprecated"}),
    "deprecated": frozenset(),
}

# The state that means "this is what production serves". Named once; see the vocabulary note above.
SERVED_STATUS = "champion"

# The staging state a built-but-unpromoted artifact sits in. Build ≠ publish starts here.
STAGED_STATUS = "challenger"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The schema
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: Fields every entry must carry. `served_version` is the family's version-of-record.
REQUIRED_FIELDS: tuple[str, ...] = (
    "model_family",
    "target",
    "served_version",
    "artifact_uri",
    "promotion_status",
)

#: The composite lineage. Each names ONE member of the served stack. `interval_model_version` is a
#: mapping because the 80% band is genuinely three models (rookie / veteran / K-DST) that version
#: apart from one another — flattening it to a scalar would make one of them unrepresentable.
LINEAGE_FIELDS: tuple[str, ...] = (
    "level_model_version",
    "ordering_model_version",
    "rookie_model_version",
    "rookie_selection_status",
    "interval_model_version",
    "scoring_contract_version",
)

#: Fields the promotion flow writes. Listed so a hand-edit that forgets one is visible in review.
FLOW_FIELDS: tuple[str, ...] = (
    "fallback_artifact_uri",
    "generated_at",
    "published_at",
    "validation_report",
    "promoted_at",
)

#: `rookie_selection_status` vocabulary. `PM_JUDGMENT` exists because NF-D21 is a judgment call and
#: the registry must be able to SAY SO — a status field that can only express "selected" would force
#: a judgment publish to be recorded as a statistical selection, which is the E2.1-r laundering
#: NF-D20 forbade, committed into the system of record.
ROOKIE_SELECTION_STATUSES: frozenset[str] = frozenset({
    "incumbent",        # the shipped rookie point, no correction applied
    "PM_JUDGMENT",      # a correction applied by a recorded PM decision, NOT selected in-fold
    "SELECTED",         # a correction chosen by a passing §0.5 in-fold selection
})

_INTERVAL_MEMBERS: tuple[str, ...] = ("rookie", "veteran", "kdst")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")


def entry_key(model_family: str, target: str, served_version: str) -> str:
    """The registry key: one entry per (family, target, VERSION).

    ⚠️ THE VERSION IS PART OF THE KEY, AND IT HAS TO BE. Keyed on (family, target) alone, staging a
    challenger would OVERWRITE the champion — destroying the very `fallback_artifact_uri` that makes
    the promotion reversible, at the exact moment the flow claims to be wiring rollback. A champion
    and its challenger must be able to coexist, which is also why `promote()` has to deprecate the
    OTHER champions for the same (family, target) rather than simply overwrite one row.

    Same shape as the baseball sub-model registry's `<domain>_v<N>` convention (`run_env_v2`)."""
    return f"{model_family}__{target}__{served_version}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Store
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_registry(path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """Load the full registry, keyed by `entry_key`. A missing file is an EMPTY registry, not an
    error — the first `register()` creates it."""
    p = Path(path)
    if not p.is_file():
        return {}
    with open(p) as fh:
        return yaml.safe_load(fh) or {}


def get_entry(model_family: str, target: str, served_version: str,
              path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """One entry by (family, target, version). Raises `KeyError` when absent — an unregistered model
    has no version-of-record, and returning an empty dict would let a caller serve one anyway."""
    reg = load_registry(path)
    key = entry_key(model_family, target, served_version)
    if key not in reg:
        raise KeyError(f"no registry entry '{key}'. Registered: {sorted(reg)}")
    return copy.deepcopy(reg[key])


def register(model_family: str, target: str, fields: dict[str, Any], *,
             served_version: str | None = None,
             overwrite: bool = False, path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """Add or update an entry. Merges into an existing entry unless `overwrite`.

    The entry is VALIDATED before it is written, so a malformed entry can never land in the file —
    an invalid version-of-record is worse than a missing one, because it reads as authoritative."""
    reg = load_registry(path)
    version = served_version or fields.get("served_version")
    if not version:
        raise ValueError("register() needs a served_version (in `fields` or as the keyword) — it is "
                         "part of the registry key")
    key = entry_key(model_family, target, version)
    entry = dict(fields)
    entry.setdefault("model_family", model_family)
    entry.setdefault("target", target)
    entry.setdefault("served_version", version)
    if key in reg and not overwrite:
        merged = dict(reg[key])
        merged.update(entry)
        entry = merged
    validate_entry(key, entry)
    reg[key] = entry
    _write(reg, path)
    return copy.deepcopy(entry)


def promote(model_family: str, target: str, served_version: str, *, new_status: str,
            promoted_at: date | str | None = None,
            path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """Advance an entry's `promotion_status` along the SHARED state machine.

    Promoting to `champion` deprecates any other champion for the same (family, target) — one
    served version per target, enforced here rather than left to the caller's discipline."""
    reg = load_registry(path)
    key = entry_key(model_family, target, served_version)
    if key not in reg:
        raise KeyError(f"no registry entry '{key}' to promote.")
    current = reg[key].get("promotion_status", "pending")
    if new_status not in VALID_TRANSITIONS.get(current, frozenset()):
        raise ValueError(
            f"invalid transition for '{key}': '{current}' → '{new_status}'. "
            f"Allowed from '{current}': {sorted(VALID_TRANSITIONS.get(current, frozenset()))}"
        )
    if new_status == SERVED_STATUS:
        for other, ent in reg.items():
            if (other != key and ent.get("model_family") == model_family
                    and ent.get("target") == target
                    and ent.get("promotion_status") == SERVED_STATUS):
                ent["promotion_status"] = "deprecated"
    reg[key]["promotion_status"] = new_status
    reg[key]["promoted_at"] = str(promoted_at or date.today())
    validate_entry(key, reg[key])
    _write(reg, path)
    return copy.deepcopy(reg[key])


def list_served(path: Path = _REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    """Every entry production currently serves."""
    return {k: v for k, v in load_registry(path).items()
            if v.get("promotion_status") == SERVED_STATUS}


def served_entry(model_family: str, target: str,
                 path: Path = _REGISTRY_PATH) -> dict[str, Any] | None:
    """The SERVED entry for one (family, target), or None when nothing is served.

    This is the one function a consumer should ask "what is production running?" — see the
    named-authority note in the module docstring."""
    for ent in load_registry(path).values():
        if (ent.get("model_family") == model_family and ent.get("target") == target
                and ent.get("promotion_status") == SERVED_STATUS):
            return copy.deepcopy(ent)
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def validate_entry(key: str, entry: dict[str, Any]) -> None:
    """Raise `ValueError` on anything that would make the entry a misleading authority.

    Deliberately strict about the SMALL set of things that can silently mislead, and silent about
    everything else — a registry that rejects unknown keys would make adding a per-family diagnostic
    field a schema migration, and nothing downstream reads unknown keys."""
    missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
    if missing:
        raise ValueError(f"entry '{key}' is missing required field(s): {missing}")

    status = entry.get("promotion_status")
    if status not in PROMOTION_STATES:
        raise ValueError(f"entry '{key}' has invalid promotion_status {status!r}; "
                         f"must be one of {sorted(PROMOTION_STATES)}")

    for f in ("served_version", *(f for f in LINEAGE_FIELDS if f != "interval_model_version")):
        v = entry.get(f)
        if f == "rookie_selection_status":
            if v is not None and v not in ROOKIE_SELECTION_STATUSES:
                raise ValueError(f"entry '{key}' has rookie_selection_status {v!r}; "
                                 f"must be one of {sorted(ROOKIE_SELECTION_STATUSES)}")
            continue
        if v is not None and not (isinstance(v, str) and _VERSION_RE.match(v)):
            raise ValueError(f"entry '{key}' field {f}={v!r} is not a usable version string")

    iv = entry.get("interval_model_version")
    if iv is not None:
        if not isinstance(iv, dict):
            raise ValueError(f"entry '{key}' interval_model_version must be a mapping of "
                             f"{{{'|'.join(_INTERVAL_MEMBERS)} -> version}}, got {type(iv).__name__}")
        unknown = sorted(set(iv) - set(_INTERVAL_MEMBERS))
        if unknown:
            raise ValueError(f"entry '{key}' interval_model_version has unknown member(s) {unknown}; "
                             f"known members are {list(_INTERVAL_MEMBERS)}")

    # A SERVED entry must be reconcilable and rollback-able. Enforced at `champion` only: a staged
    # challenger legitimately has no `published_at` yet, and requiring one would make staging
    # impossible — the exact build/publish conflation this package exists to separate.
    if status == SERVED_STATUS:
        for f in ("fallback_artifact_uri", "validation_report"):
            if not entry.get(f):
                raise ValueError(
                    f"entry '{key}' is {SERVED_STATUS} but has no {f} — a served version must be "
                    f"rollback-able and must name the validation that earned it")


def _write(registry: dict[str, Any], path: Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        yaml.dump(registry, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
