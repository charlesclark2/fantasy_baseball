"""test_mh2_3_design_block_guard.py — MH2.3 guards.

⛔ **No `pipeline` import** — the dbt manifest is absent in the fast gate, so a test importing
`pipeline` crashes at COLLECTION rather than skipping cleanly (CLAUDE.md's `betting_ml/monitoring/*`
pattern, applied here to `betting_ml/utils/design_block.py` + `betting_ml/scripts/mh2_*`, neither of
which import `pipeline`).

Two things are being pinned, and they are different in kind:

  1. **The module itself** — render/parse round-trips, `exempt`/`unrecoverable` require a `reason`
     (LOCK 2: never silently opaque), and re-inserting into an already-blocked report is idempotent.
  2. **The known live writers keep emitting the block.** A source-inspection check over the 8
     scripts this story wired (the milb_mle E7.12/E7.15 family + the prospect-board comp_validation
     family — LOCK 3's "the 3 harness generations") — proven, per the PM's readiness note, to
     actually go RED on a report writer whose emitter call has been stripped, not just asserted to
     pass. Scope is deliberately limited to the writers this story touched: this corpus has ~90
     other scripts that write into `ablation_results/`, most of which are one-off research scripts
     never re-run, and a guard that can only assert PRESENCE on a hand-authored report would false
     -fire on every one of them (the PM's second readiness note). Extending this registry to a new
     writer is a one-line addition, not a redesign.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from betting_ml.utils.design_block import (
    DesignBlock,
    has_design_block,
    insert_design_block,
    parse_design_block,
    render_design_block,
)

REPO = Path(__file__).resolve().parents[2]

# Every writer script this story wired to emit the MH2-DESIGN-BLOCK, and the substring that must
# appear in its source to prove the call site is really there (not just imported and unused).
KNOWN_HARNESS_WRITERS: dict[str, str] = {
    "betting_ml/scripts/milb_mle/run_e7_12_slice1.py": "design_block_from_ladder_results(",
    "betting_ml/scripts/milb_mle/run_e7_15_h1.py": "design_block_from_ladder_results(",
    "betting_ml/scripts/milb_mle/run_e7_15_h2.py": "design_block_from_ladder_results(",
    "betting_ml/scripts/milb_mle/run_e7_15_h3.py": "design_block_from_ladder_results(",
    "betting_ml/scripts/milb_mle/run_e7_15_h4.py": "design_block_from_ladder_results(",
    "betting_ml/scripts/prospect_board/run_e7_13_comp_validation.py":
        "design_block_from_comp_validation_report(",
    "betting_ml/scripts/prospect_board/run_e7_16_pipeline_comps.py":
        "design_block_from_comp_validation_report(",
    "betting_ml/scripts/prospect_board/run_e7_14_source_accuracy.py":
        "design_block_from_source_accuracy_report(",
}


def _writer_is_wired(source: str, build_call_marker: str) -> bool:
    """The check the guard runs: the script must import `insert_design_block`, build a block via
    its registered emitter, and actually pass the built block INTO `insert_design_block(...)` —
    not just call the two independently. A script that builds `db` but never threads it into the
    text it writes would still "mention" both calls, so this also checks `insert_design_block(`
    appears AFTER the build call in source order (the common `db = build(...); ...write_text(
    insert_design_block(text, db))` shape every wired writer in this story follows)."""
    if "insert_design_block" not in source or build_call_marker not in source:
        return False
    build_at = source.index(build_call_marker)
    insert_at = source.find("insert_design_block(", build_at)
    return insert_at != -1


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The module itself
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class TestDesignBlockModule:
    def test_render_parse_roundtrip(self):
        db = DesignBlock(status="recorded", fold_rule="leave-one-cohort-out", n_folds=11, n_arms=7,
                         primary_contrast="paired-t", verdict="ADD", gates={"pbo": 0.05, "dsr": 0.97})
        assert parse_design_block(render_design_block(db)) == db

    def test_recovered_with_per_metric_roundtrips(self):
        db = DesignBlock(status="recovered", per_metric=[{"metric": "woba", "verdict": "ADD"}],
                         source_artifact="e7_15_artifacts/e7_15_h1_summary.json")
        assert parse_design_block(render_design_block(db)) == db

    @pytest.mark.parametrize("status", ["exempt", "unrecoverable"])
    def test_status_requiring_reason_rejects_missing_reason(self, status):
        with pytest.raises(ValueError, match="requires a `reason`"):
            DesignBlock(status=status)

    @pytest.mark.parametrize("status", ["exempt", "unrecoverable"])
    def test_status_requiring_reason_accepts_a_reason(self, status):
        db = DesignBlock(status=status, reason="test reason")
        assert db.reason == "test reason"

    def test_unknown_status_rejected(self):
        with pytest.raises(ValueError, match="unknown design-block status"):
            DesignBlock(status="not_a_real_status")

    def test_parse_returns_none_on_absent_block(self):
        assert parse_design_block("# Just a report\n\nNo block here.\n") is None

    def test_parse_returns_none_on_malformed_json(self):
        text = "# T\n\n<!-- MH2-DESIGN-BLOCK\n{not valid json\n-->\n"
        assert parse_design_block(text) is None

    def test_has_design_block(self):
        db = DesignBlock(status="exempt", reason="x")
        assert not has_design_block("# T\n\nbody\n")
        assert has_design_block(insert_design_block("# T\n\nbody\n", db))

    def test_insert_places_block_after_first_h1(self):
        db = DesignBlock(status="exempt", reason="x")
        out = insert_design_block("# Title\n\nBody line.\n", db)
        lines = out.splitlines()
        assert lines[0] == "# Title"
        assert "<!-- MH2-DESIGN-BLOCK" in out
        assert out.rstrip().endswith("Body line.")

    def test_insert_is_idempotent(self):
        db = DesignBlock(status="exempt", reason="x")
        once = insert_design_block("# Title\n\nBody.\n", db)
        twice = insert_design_block(once, db)
        assert once == twice
        assert once.count("MH2-DESIGN-BLOCK") == 1

    def test_insert_replaces_a_stale_block_rather_than_duplicating(self):
        old = DesignBlock(status="unrecoverable", reason="old reason")
        new = DesignBlock(status="recovered", n_folds=5, source_artifact="x.json")
        text = insert_design_block("# Title\n\nBody.\n", old)
        text = insert_design_block(text, new)
        assert text.count("MH2-DESIGN-BLOCK") == 1
        assert parse_design_block(text) == new


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The known live writers keep emitting the block
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class TestKnownHarnessWritersEmitTheBlock:
    @pytest.mark.parametrize("rel_path,marker", sorted(KNOWN_HARNESS_WRITERS.items()))
    def test_writer_calls_the_design_block_emitter(self, rel_path, marker):
        p = REPO / rel_path
        assert p.exists(), f"registered writer no longer exists at {rel_path} — update the registry"
        assert _writer_is_wired(p.read_text(), marker), (
            f"{rel_path} no longer builds+inserts an MH2-DESIGN-BLOCK before writing its report "
            f"(expected `{marker}` followed later by `insert_design_block(`) — a report this "
            f"harness writes would go back to being unclassifiable (MH2.3).")

    def test_registry_is_nonempty(self):
        """A guard whose registry silently emptied would pass on nothing — the NF1.7 (a) vacuous-
        anchor class. Pin the count so a future edit that drops entries is visible in the diff."""
        assert len(KNOWN_HARNESS_WRITERS) == 8

    def test_guard_goes_red_when_the_emitter_call_is_stripped(self):
        """Proves the check above can actually FAIL — INC-38/INC-39's lesson that a source-
        inspection guard which cannot fail is worse than none. Take one real wired writer's source,
        strip its `insert_design_block(` call (simulating a future edit that silently drops it),
        and assert the SAME detection helper the guard above uses reports it as unwired."""
        rel_path, marker = "betting_ml/scripts/milb_mle/run_e7_12_slice1.py", \
            KNOWN_HARNESS_WRITERS["betting_ml/scripts/milb_mle/run_e7_12_slice1.py"]
        source = (REPO / rel_path).read_text()
        assert _writer_is_wired(source, marker), "precondition: the real file must currently pass"

        stripped = source.replace(
            'path.write_text(insert_design_block("\\n".join(L) + "\\n", db))',
            'path.write_text("\\n".join(L) + "\\n")')
        assert stripped != source, "the replace above didn't match — update it to the current tail"
        assert not _writer_is_wired(stripped, marker), (
            "the guard's detection helper did not go RED on a writer with its emitter call "
            "stripped — it would not have caught a real regression")
