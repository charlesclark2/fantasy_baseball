"""NF-C-LDA-0 — the RED PROOF for the extension red-line guard.

A green guard suite is not evidence that the guard works; it is equally consistent with a guard
that cannot fail (NF1.7(a) / INC-38 / NF-D17). This applies one deliberate break at a time and
asserts the NAMED clause goes red.

Three ways a red proof itself lies, all closed here:
  • the mutation never LANDS (#682)          → we assert the file content actually changed
  • the anchor is NOT UNIQUE (#885)          → we assert the anchor occurs exactly once
  • it lands but doesn't move the ASSERTION  → each break targets ONE clause, named per case,
    (#815)                                      and we require THAT test id to fail

Run:  uv run python extension/tools/red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_c_lda_0_extension_red_line.py"
MANIFEST = REPO / "extension/manifest.json"
PROBE = REPO / "extension/src/main-world-probe.js"

# (label, file, anchor, replacement, the test id that MUST go red)
CASES = [
    ("manifest requests the `cookies` permission",
     MANIFEST, '"permissions": []', '"permissions": ["cookies"]',
     "test_the_manifest_requests_no_credential_bearing_permission"),
    ("manifest host scope widened to every host",
     MANIFEST, '"host_permissions": [\n    "https://fantasy.espn.com/football/draft*"',
     '"host_permissions": [\n    "*://*/*"',
     "test_the_manifest_host_scope_is_narrow"),
    ("probe reads document.cookie",
     PROBE, '  var CHANNEL = "__credence_draft_probe__";',
     '  var CHANNEL = "__credence_draft_probe__";\n  var stolen = document.cookie;',
     "test_no_source_reads_a_credential[document.cookie]"),
    ("probe ORIGINATES a fetch to ESPN",
     PROBE, '  installNetworkObservers();',
     '  fetch("https://lm-api-reads.fantasy.espn.com/apis/v3/x");\n  installNetworkObservers();',
     "test_no_source_originates_a_network_call[fetch(]"),
    ("probe stops wrapping fetch (abstains instead of observing)",
     PROBE, '        window.fetch = function () {', '        var disabled = function () {',
     "test_the_probe_really_does_wrap_rather_than_merely_abstain"),
    ("raw frame stored WITHOUT the redactor",
     PROBE, "entry.rawSample = redact(bodyText);", "entry.rawSample = bodyText;",
     "test_a_raw_frame_is_only_ever_stored_through_the_redactor"),
    ("raw frame capture unbounded (limit never applied)",
     PROBE, "      .slice(0, RAW_FRAME_LIMIT);", "      ;",
     "test_the_raw_frame_capture_is_bounded"),
    ("pool extractor grows a league-private field",
     PROBE, "          eligibleSlots: pl.eligibleSlots",
     "          eligibleSlots: pl.eligibleSlots,\n          ownership: pl.ownership",
     "test_the_pool_extractor_keeps_identity_fields_only[ownership]"),
    ("unreadable frames dropped silently again (predicate removed)",
     PROBE, "      } else if (entry.shape === null && bodyText === null && entry.nonTextFrames === undefined) {",
     "      } else if (false) {",
     "test_an_unreadable_frame_is_COUNTED_rather_than_dropped"),
    ("binary decoder defined but never CALLED (wired-not-invoked)",
     PROBE, "                  recordCall(\"websocket-msg\", url, decodePrefix(d));",
     "                  recordCall(\"websocket-msg\", url, null);",
     "test_binary_frames_are_DECODED_rather_than_dropped"),
]


def run_test(test_id: str) -> bool:
    """True when the named test PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_id}", "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    failures = []
    for label, path, anchor, replacement, test_id in CASES:
        original = path.read_text()

        # (#885) the anchor must be UNIQUE, or the break can land on the wrong symbol and the
        # harness reports a FALSE "the guard is vacuous" — the dangerous direction, because it
        # invites weakening a correct guard.
        occurrences = original.count(anchor)
        if occurrences != 1:
            failures.append(f"{label}: anchor occurs {occurrences}× (must be exactly 1)")
            continue

        if not run_test(test_id):
            failures.append(f"{label}: {test_id} was ALREADY RED before the break")
            continue

        mutated = original.replace(anchor, replacement, 1)
        try:
            path.write_text(mutated)
            # (#682) prove the mutation actually reached disk.
            assert path.read_text() != original, "mutation did not land"
            # (#815) prove the forbidden token is genuinely present now (or genuinely gone).
            went_red = not run_test(test_id)
        finally:
            path.write_text(original)
            assert path.read_text() == original, f"FAILED TO RESTORE {path}"

        status = "RED ✓" if went_red else "STILL GREEN ✗"
        print(f"  {status}  {label}\n           → {test_id}")
        if not went_red:
            failures.append(f"{label}: {test_id} stayed GREEN on a deliberate break (VACUOUS)")

    print()
    if failures:
        print("RED PROOF FAILED:")
        for f in failures:
            print("  ✗", f)
        return 1
    print(f"RED PROOF PASSED — all {len(CASES)} clauses go red on their own deliberate break.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
