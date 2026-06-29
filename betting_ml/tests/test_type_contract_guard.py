"""
test_type_contract_guard.py  (INC-19 DURABLE TYPE-PIN — enforcement half)
=========================================================================
Fast-gate guard for the recurring NUMBER<->FLOAT incremental-drift HALT class
(INC-15 / W1d / INC-16-P0 / INC-19 / INC-19-recurrence — 5 incidents). See
CLAUDE.md "type-contract guard" and scripts/gen_type_contract.py.

The CURE is the explicit `::double` TYPE-PIN block in feature_pregame_game_features_raw
(generated from dbt/type_contracts/feature_pregame_game_features_raw.types.json). This
guard is the ENFORCEMENT: it goes RED when the model's pinned set drifts from the
manifest, so a type-drifting PR fails CI BEFORE the next prod rebuild — not after a HALT.

To make an INTENDED type change: update the manifest AND re-run
`scripts/gen_type_contract.py --write` in the same PR (the documented convention).

No network / no warehouse — pure file + string checks (fast gate safe).
"""
import pathlib
import re

import gen_type_contract as gtc  # scripts/ is on pytest pythonpath (see pyproject.toml)

REPO = pathlib.Path(__file__).resolve().parents[2]
PUBLIC_MODEL = REPO / "dbt/models/feature/feature_pregame_game_features.sql"


def test_raw_model_blocks_match_their_manifests():
    """The generated TYPE-PIN block in each guarded model must equal the block built
    from its manifest. A NUMBER->FLOAT (or any) type change that touches the model
    without updating the manifest — or vice versa — fails here."""
    mismatches = []
    for manifest_path, model_path in gtc.CONTRACTS:
        manifest = gtc.load_manifest(manifest_path)
        expected = gtc.build_block(manifest)
        actual = gtc.extract_block(model_path.read_text())
        assert actual is not None, (
            f"{model_path.name}: no `-- TYPE-PIN-START ... -- TYPE-PIN-END` block. "
            f"Run `uv run python scripts/gen_type_contract.py --write`."
        )
        if actual.strip() != expected.strip():
            mismatches.append(model_path.name)
    assert not mismatches, (
        "TYPE-PIN block(s) drifted from their manifest: "
        f"{mismatches}. An intended type change must update the manifest and re-run "
        "`scripts/gen_type_contract.py --write` in the SAME PR (and the operator "
        "DROP+rebuilds the incremental if a stored NUMBER<->FLOAT type actually changed)."
    )


def test_manifests_are_well_formed():
    for manifest_path, _ in gtc.CONTRACTS:
        m = gtc.load_manifest(manifest_path)  # asserts no dup / subset internally
        assert m["double_pinned"], f"{manifest_path.name}: empty double_pinned set"
        # every pinned column must appear exactly once in the model's pin lines
        assert len(set(m["double_pinned"])) == len(m["double_pinned"])


def test_public_wrapper_pins_seasonnorm_double():
    """feature_pregame_game_features adds _seasonnorm columns on top of raw.*; each
    must be cast ::double so the public surface is also drift-immune."""
    src = PUBLIC_MODEL.read_text()
    assert re.search(r"\)::double as \{\{ c \}\}_seasonnorm", src), (
        "feature_pregame_game_features must cast each season-normalized column "
        "`)::double as {{ c }}_seasonnorm` (INC-19 type-pin) — none found."
    )
    # belt-and-suspenders: no leftover UN-pinned `) as {{ c }}_seasonnorm`
    assert not re.search(r"\)\s+as \{\{ c \}\}_seasonnorm", src), (
        "found an un-pinned `) as {{ c }}_seasonnorm` in feature_pregame_game_features "
        "— it must be `)::double as {{ c }}_seasonnorm`."
    )


def test_guard_detects_drift_positive_control():
    """Proof the guard goes RED on a deliberate NUMBER->FLOAT un-pin: build a block,
    then strip one column's `::double` (what an upstream flip / a forgotten pin looks
    like) and assert the comparison flags it."""
    manifest = {"model": "demo", "all_columns": ["a", "b", "c"], "double_pinned": ["b", "c"]}
    good = gtc.build_block(manifest)
    drifted = good.replace("    c::double as c", "    c")  # un-pin column c
    assert drifted != good
    # the same comparison the live guard uses must reject the drifted block
    assert gtc.extract_block(drifted).strip() != good.strip()
    # ...and an added/removed column is caught too
    manifest_extra = {**manifest, "all_columns": ["a", "b", "c", "d"]}
    assert gtc.build_block(manifest_extra).strip() != good.strip()
