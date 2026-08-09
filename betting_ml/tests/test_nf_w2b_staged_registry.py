"""NF-W2b staging guards — a STAGED challenger must be inert at serve, proven two-sided.

The MH2.1 promotion-mechanics landmine is why these exist: a model-registry change ships with
the box image on merge, so "staging is safe" must be PROVEN, not assumed. The proof is
two-sided: the staged entry is invisible to the serving-facing query (`served_entry`), AND the
same query WOULD return it if its status were champion — so the inertness demonstrably rests on
the status field, not on the entry's absence. Fast-gate rules honored: no `pipeline` import,
no network/IO at import, no module-level state mutation.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from betting_ml.governance import publish as P
from betting_ml.governance import registry as R
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w2b_stage_registry as STAGE
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B

_KEY = R.entry_key(STAGE.FAMILY, STAGE.TARGET, STAGE.SERVED_VERSION)


def _entry() -> dict:
    return R.get_entry(STAGE.FAMILY, STAGE.TARGET, STAGE.SERVED_VERSION)


class TestStagedEntry:
    def test_entry_exists_as_a_challenger_never_a_champion(self):
        e = _entry()
        assert e["promotion_status"] == R.STAGED_STATUS
        assert e["promotion_status"] != R.SERVED_STATUS

    def test_spec_is_the_guard_pinned_certified_winners(self):
        """Option A verbatim: the registry serves what the bake-off certified per position —
        `POST_FLIP_SPEC` is itself pinned to the validated artifact, so this transitively ties
        the registry to the artifact bytes."""
        e = _entry()
        assert e["per_position_spec"] == dict(W2B.POST_FLIP_SPEC)
        assert e["per_position_spec"] == {"QB": "inj_zero_leg", "RB": "inj_both",
                                          "WR": "inj_both", "TE": "inj_zero_leg"}

    def test_staged_digest_matches_the_validated_artifact_bytes(self):
        e = _entry()
        artifact = Path(STAGE._PROJECT_ROOT) / STAGE.ARTIFACT
        assert e["staged_digest"] == P.digest_file(artifact)

    def test_rollback_is_prewired_to_the_base_champion_record(self):
        e = _entry()
        assert e["fallback_artifact_uri"] == f"repo:{STAGE.FALLBACK_ARTIFACT}"
        assert "nf_w1_weekly_bakeoff" in e["fallback_artifact_uri"]

    def test_notes_record_every_promote_blocker(self):
        e = _entry()
        for needle in ("NF-C6 Phase 2", "NF-W0a", "RETENTION snapshot"):
            assert needle in e["notes"], f"promote blocker missing from the record: {needle}"


class TestServingInertness:
    """⭐ The load-bearing pair: staging cannot flip serving — proven in BOTH directions."""

    def test_the_serving_facing_query_does_not_see_the_staged_entry(self):
        assert _KEY in R.load_registry(), "the staged entry is missing entirely"
        assert R.served_entry(STAGE.FAMILY, STAGE.TARGET) is None, (
            "served_entry() returned a weekly entry — a STAGED challenger is serving")

    def test_nothing_weekly_is_in_the_served_set(self):
        served = R.list_served()
        assert not any(v.get("target") == STAGE.TARGET for v in served.values())

    def test_the_query_discriminates_on_status_not_absence(self, tmp_path):
        """The two-sided half (prove-it-don't-assume-it): copy the registry, flip ONLY the
        staged entry's status to champion, and the SAME query must then return it — so the
        inertness above rests on the status field, not on the entry being invisible for some
        other reason (which would make the first test vacuous, NF1.7 (a))."""
        reg = R.load_registry()
        mutated = copy.deepcopy(reg)
        assert mutated[_KEY]["promotion_status"] != R.SERVED_STATUS
        mutated[_KEY]["promotion_status"] = R.SERVED_STATUS  # the mutation, asserted to land
        p = tmp_path / "registry.yaml"
        with open(p, "w") as fh:
            yaml.dump(mutated, fh)
        seen = R.served_entry(STAGE.FAMILY, STAGE.TARGET, p)
        assert seen is not None and seen["served_version"] == STAGE.SERVED_VERSION

    def test_the_season_projection_champion_is_untouched(self):
        """Staging the weekly challenger must not have moved the family's live surface."""
        season = R.served_entry(STAGE.FAMILY, "season_projection")
        assert season is not None
        assert season["served_version"] == "nfl_fantasy_nf1_5_v1"
        assert season["promotion_status"] == R.SERVED_STATUS
        assert season["artifact_uri"] == "s3://credence-prod-s3-api-cache/fantasy/nfl/2026/"

    def test_no_serving_code_reads_this_registry(self):
        """The registry's consumers must stay governance/research-side: nothing under
        `app/backend/` or `pipeline/` may read the family registry or `served_entry` — the
        MH2.1 'merging IS the deploy' hazard only materializes through a serving-side reader,
        so this pins that none exists."""
        root = Path(STAGE._PROJECT_ROOT)
        offenders = []
        for base in ("app/backend", "pipeline"):
            d = root / base
            if not d.is_dir():
                continue
            for f in d.rglob("*.py"):
                text = f.read_text(errors="ignore")
                if "model_family_registry" in text or "served_entry" in text:
                    offenders.append(str(f.relative_to(root)))
        assert not offenders, (
            f"serving-side code now reads the family registry: {offenders} — the staged-entry "
            f"inertness argument no longer holds; re-derive it before merging")
