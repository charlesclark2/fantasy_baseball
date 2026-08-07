#!/usr/bin/env python3
"""NF-TR1 — rebuild the two-layer CLAIM block inside the captured track-record manifest fixture.

    uv run python frontend/e2e/fixtures/build-track-record-claim.py

WHY THIS EXISTS AT ALL — the E9.63 rule is ⛔ do not hand-write a fixture, because a hand-written
one encodes the assumption under test. NF-TR1 hits the one case that rule does not cover: the
`claim` block does not exist in production yet (it lands at the post-merge `--publish`), so there is
nothing to capture. `subscription-public-pricing.json` had exactly this shape for one day at E9.59.

The resolution is that NOTHING here is authored. Every other byte of the fixture stays the verbatim
prod capture; the `claim` block and the repointed `headline` are produced by calling the SHIPPING
`export_track_record_json.build_claim` over the SAME committed artifacts the real export reads:

    ablation_results/nf_d3_benchmark_scorecard_nf1_5.json      (Δρ, per-position split, context systems)
    ablation_results/nf_d17_track_record_population.json       (player count, bootstrap interval)

So the fixture is generated output of the code under test, not a guess about it — and
`betting_ml/tests/test_nf_tr1_claim_copy.py::test_the_e2e_fixture_claim_is_the_shipping_builders_own_output`
asserts the equality, which is what turns "we regenerated it once" into a red build if the copy
ever changes without the fixture following.

⚠️ RE-CAPTURE AFTER THE PUBLISH. Once the operator has run the exporter with `--publish`, the real
manifest carries `claim` and `npm run e2e:capture` supersedes this script entirely. Delete it then,
the way E9.59's synthetic pricing fixture was deleted the day the route went live.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
sys.path.insert(0, str(_REPO))

from quant_sports_intel_models.football.nfl.fantasy.export_track_record_json import (  # noqa: E402
    build_claim,
)

_REPORTS = _REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_FIXTURE = _HERE.parent / "api" / "fantasy-nfl-track-record-manifest.json"


def rebuilt_manifest() -> dict:
    """The captured manifest with `claim` injected and `headline` repointed at the consumer lead."""
    manifest = json.loads(_FIXTURE.read_text())
    claim = build_claim(
        json.loads((_REPORTS / "nf_d3_benchmark_scorecard_nf1_5.json").read_text()),
        json.loads((_REPORTS / "nf_d17_track_record_population.json").read_text()),
    )
    manifest["headline"] = claim["lead"]
    manifest["claim"] = claim
    return manifest


def main() -> int:
    _FIXTURE.write_text(json.dumps(rebuilt_manifest(), indent=2) + "\n")
    print(f"rewrote {_FIXTURE.relative_to(_REPO)} with the shipping builder's claim block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
