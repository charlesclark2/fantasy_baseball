"""
Sub-model registry helpers.

Thin wrapper around sub_model_registry.yaml that provides typed access for
load / get / register / promote operations. All writes go back to the YAML
file; no database is involved.

Usage:
    from betting_ml.scripts.sub_model_registry import (
        load_registry, get_entry, register, promote
    )

Promotion state machine:
    pending → challenger  (artifact trained, gate not yet evaluated)
    challenger → champion (promotion gate passed; closes prior champion)
    champion → deprecated (superseded by newer version)
    pending → deprecated  (decided not to build)
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any

import yaml

_REGISTRY_PATH = Path(__file__).parent.parent / "sub_model_registry.yaml"

_VALID_STATUSES = {"pending", "challenger", "champion", "deprecated"}

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending":    {"challenger", "deprecated"},
    "challenger": {"champion", "deprecated"},
    "champion":   {"deprecated"},
    "deprecated": set(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_registry(path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """Load and return the full registry dict keyed by entry name."""
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def get_entry(name: str, path: Path = _REGISTRY_PATH) -> dict[str, Any]:
    """Return a single registry entry by name. Raises KeyError if not found."""
    registry = load_registry(path)
    if name not in registry:
        raise KeyError(f"Sub-model '{name}' not found in registry. "
                       f"Available: {sorted(registry)}")
    return copy.deepcopy(registry[name])


def register(
    name: str,
    fields: dict[str, Any],
    *,
    overwrite: bool = False,
    path: Path = _REGISTRY_PATH,
) -> None:
    """
    Add or update a registry entry.

    Parameters
    ----------
    name:      Entry key, e.g. 'run_env_v2'
    fields:    Dict of fields to set. Merged with existing entry when present.
    overwrite: If True, replace the entry entirely. Default merges into existing.
    path:      Registry file path (override for testing).
    """
    registry = load_registry(path)
    if name in registry and not overwrite:
        existing = registry[name]
        existing.update(fields)
        registry[name] = existing
    else:
        registry[name] = fields

    _validate_entry(name, registry[name])
    _write(registry, path)


def promote(
    name: str,
    *,
    new_status: str,
    promoted_at: date | None = None,
    path: Path = _REGISTRY_PATH,
) -> None:
    """
    Advance the promotion_status of an entry.

    When promoting to 'champion', the current champion in the same domain
    (same prefix before the final _vN) is automatically deprecated.

    Parameters
    ----------
    name:        Entry key to promote (e.g. 'run_env_v2')
    new_status:  Target status — one of pending/challenger/champion/deprecated
    promoted_at: Date to stamp on the entry (defaults to today)
    path:        Registry file path (override for testing)
    """
    registry = load_registry(path)
    if name not in registry:
        raise KeyError(f"Sub-model '{name}' not in registry.")

    current_status = registry[name].get("promotion_status", "pending")
    if new_status not in _VALID_TRANSITIONS.get(current_status, set()):
        raise ValueError(
            f"Invalid transition for '{name}': "
            f"'{current_status}' → '{new_status}'. "
            f"Allowed: {_VALID_TRANSITIONS[current_status]}"
        )

    if new_status == "champion":
        domain = _domain(name)
        for key, entry in registry.items():
            if _domain(key) == domain and entry.get("promotion_status") == "champion":
                registry[key]["promotion_status"] = "deprecated"

    registry[name]["promotion_status"] = new_status
    registry[name]["promoted_at"] = str(promoted_at or date.today())

    _write(registry, path)


def list_champions(path: Path = _REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    """Return all entries with promotion_status == 'champion'."""
    return {
        name: entry
        for name, entry in load_registry(path).items()
        if entry.get("promotion_status") == "champion"
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _domain(name: str) -> str:
    """Extract domain prefix: 'run_env_v2' → 'run_env'."""
    parts = name.rsplit("_v", maxsplit=1)
    return parts[0] if len(parts) == 2 else name


def _validate_entry(name: str, entry: dict[str, Any]) -> None:
    status = entry.get("promotion_status")
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"Entry '{name}' has invalid promotion_status '{status}'. "
            f"Must be one of {_VALID_STATUSES}."
        )


def _write(registry: dict[str, Any], path: Path) -> None:
    with open(path, "w") as fh:
        yaml.dump(registry, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
