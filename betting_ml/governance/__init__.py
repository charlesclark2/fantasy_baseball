"""betting_ml.governance — the SHARED model/publish governance shape (NF-G0).

ONE governance shape for every model family in this repo. The baseball sub-model registry
(`betting_ml/scripts/sub_model_registry.py`) was the first implementation of it; this package is
that same shape lifted into a place a SECOND family can reuse without copying it.

⛔ THE POINT OF THE PACKAGE IS THAT THERE IS NO SECOND SHAPE. NF-G0's brief was explicit — extend
the established baseball registry + K-props (KP-V2.0) governance pattern to NFL fantasy, and do NOT
invent a parallel fantasy registry. So the promotion state machine lives HERE and
`sub_model_registry` IMPORTS it; a guard test asserts the two are the same object, which makes
"the families share one shape" a mechanical property rather than a claim in a doc.

Read the modules in this order:
  · `registry.py` — the composite-lineage schema + the promotion state machine + the YAML store.
  · `gates.py`    — the ten required promotion gates, as PURE functions over already-loaded data.
  · `publish.py`  — build ≠ publish: stage / promote / publish (DEFAULT NO-OP) / readback / rollback.

⚠️ IMPORT-SAFE BY DESIGN (the E11.23 fast-gate rule): nothing in this package imports `pipeline`,
touches the network, or reads S3 at import. The gates take data as ARGUMENTS; the callers do the IO.
"""
from __future__ import annotations

from betting_ml.governance.registry import (
    LINEAGE_FIELDS,
    PROMOTION_STATES,
    REQUIRED_FIELDS,
    SERVED_STATUS,
    VALID_TRANSITIONS,
    entry_key,
    get_entry,
    list_served,
    load_registry,
    promote,
    register,
    served_entry,
    validate_entry,
)

__all__ = [
    "LINEAGE_FIELDS",
    "PROMOTION_STATES",
    "REQUIRED_FIELDS",
    "SERVED_STATUS",
    "VALID_TRANSITIONS",
    "entry_key",
    "get_entry",
    "list_served",
    "load_registry",
    "promote",
    "register",
    "served_entry",
    "validate_entry",
]
