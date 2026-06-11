#!/usr/bin/env python
"""Back-compat shim — the canonical module moved to
`betting_ml.monitoring.model_health_metrics`.

It was relocated out of scripts/ (which is NOT shipped to the Dagster code
location in production) and into the installable `betting_ml` package so the
`model_health_alert_sensor` can import it in prod. This shim keeps the old
import path (`import model_health_metrics`) and the documented CLI command
(`python scripts/ops/model_health_metrics.py …`) working unchanged for the
dev-only ops tools (refit_home_win_calibrator / rescore_audit / align_alpha_audit).

The sys.modules alias below makes `import model_health_metrics as mh` resolve to
the real module object, so every public AND private name (mh.evaluate, mh._corr,
mh._brier, mh.MIN_GAMES, …) is available exactly as before.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is importable when this shim is loaded as a bare script
# (python scripts/ops/model_health_metrics.py) — sys.path[0] is scripts/ops then.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from betting_ml.monitoring import model_health_metrics as _mod  # noqa: E402

# Alias this module to the real one so attribute access (incl. underscore-prefixed
# helpers used by the sibling ops tools) transparently hits the relocated module.
sys.modules[__name__] = _mod

if __name__ == "__main__":
    _mod.main()
