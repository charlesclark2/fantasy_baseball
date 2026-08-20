"""RED proof for the NF-C7b guards — `uv run python betting_ml/tests/nf_c7b_red_proof.py`.

Same harness contract as `nf_c7_red_proof.py` (mutation must LAND, asserted token must be GONE,
anchor must be UNIQUE, pytest in a SUBPROCESS, only exit code 1 counts as RED, restore in a
`finally`) — see that file's header for why each clause is there.

⭐ THE FIRST BREAK IS THE POINT OF THE WHOLE STORY. NF-C7 shipped `recommend(depth_targets=...)`
wired on the web path and NOT on the extension path: the parameter existed, all 15 guards passed,
and the feature was simply absent for extension users. That is the NF-C0e "wired ≠ invoked" class,
and it survived because every NF-C7 guard exercised the surface that worked. `unwire the extension`
below re-introduces exactly that defect and requires a test to notice.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_c7b_depth_target_settings.py"
_ASSIST = "app/backend/services/draft_assistant.py"
_RESOLVE = "app/backend/services/depth_targets.py"
_MODELS = "app/backend/models/fantasy.py"
_DYNAMO = "app/backend/services/dynamo.py"
_ROUTER = "app/backend/routers/fantasy.py"
_TS = "frontend/lib/depth-targets.ts"
_REGEN_TS = ["node", "--experimental-strip-types",
             "frontend/scripts/gen-depth-target-precedence-fixture.mjs"]

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
#: Optionally an 7th element: a command to run AFTER mutating and BEFORE pytest. Used for the one
#: break that lives in TypeScript — the committed TS answers must be REGENERATED from the mutated
#: resolver, or the mutation lands on code the guard never reads and reports a false GREEN.
BREAKS = [
    # ── THE GAP NF-C7 SHIPPED ────────────────────────────────────────────────────────────────────
    ("unwire the extension: accept `depth_targets` and never pass it on (the NF-C7 gap)", _ASSIST,
     "        depth_targets=depth_targets or None,\n",
     "",
     "changes_what_the_extension_recommends", "depth_targets=depth_targets or None"),
    ("extension: stop echoing WHICH screen the targets came from", _ASSIST,
     '            "source": depth_targets_source,',
     '            "source": "none",',
     "names_where_the_targets_came_from", '"source": depth_targets_source'),
    ("extension: omit the block entirely when nothing applies", _ASSIST,
     '        "depth_targets": {\n'
     '            "applied": dict(depth_targets or {}),\n'
     '            "source": depth_targets_source,\n'
     '        },\n',
     "",
     "reported_as_none_rather_than_omitted", '"applied": dict(depth_targets or {})'),

    # ── THE ROUTER: the layer the NF-C7 gap actually lived in ────────────────────────────────────
    ("router: resolve the targets and then never pass them (the NF-C7 gap, one level up)", _ROUTER,
     "        depth_targets=applied_targets,\n        depth_targets_source=targets_source,\n",
     "",
     "account_default_reaches_the_extension", "depth_targets=applied_targets"),
    ("router: ignore the ACCOUNT default (read only the league record)", _ROUTER,
     "        record, dynamo.get_fantasy_prefs(user_id).get(\"depth_targets\")",
     "        record, None",
     # ⚠️ the token must be unique to THIS call site — a bare `dynamo.get_fantasy_prefs(user_id)`
     # also appears in the `/fantasy/preferences` GET handler and survives legitimately.
     "account_default_reaches_the_extension", "record, dynamo.get_fantasy_prefs(user_id)"),

    # ── THE STORE: the shipped Decimal bug ───────────────────────────────────────────────────────
    ("store: go back to the SHALLOW converter, so nested counts come back as Decimal", _DYNAMO,
     "            return _deep_from_dynamo(prefs)",
     "            return _from_dynamo(prefs)",
     "TestTheValuesSurviveARealDynamoRoundTrip", "return _deep_from_dynamo(prefs)"),

    # ── PRECEDENCE: the distinction the resolver exists for ──────────────────────────────────────
    ("precedence: write it the obvious way (`league or account`), so clearing re-inherits", _RESOLVE,
     "    if league is not None:",
     "    if league:",
     "shared_fixture_says or does_not_re_inherit", "    if league is not None:"),
    ("precedence: treat a legacy record with NO key as CLEARED rather than inheriting", _RESOLVE,
     '    raw = (record or {}).get("depth_targets")',
     '    raw = (record or {}).get("depth_targets") or {}',
     "inherits_rather_than_opting_out", '.get("depth_targets")\n'),
    ("precedence: let the ACCOUNT default win over the league", _RESOLVE,
     "    if league is not None:\n        league_targets = sanitize_depth_targets(league)",
     "    if False:\n        league_targets = sanitize_depth_targets(league)",
     "shared_fixture_says", None),
    ("precedence: MERGE the account default under the league instead of replacing", _RESOLVE,
     "        league_targets = sanitize_depth_targets(league)",
     "        league_targets = {**sanitize_depth_targets(account), **sanitize_depth_targets(league)}",
     "shared_fixture_says", "        league_targets = sanitize_depth_targets(league)\n"),

    # ── NORMALISATION: must agree with the TypeScript sanitizer ──────────────────────────────────
    ("sanitize: CLAMP an over-large count instead of dropping it (the TS/Python divergence)", _MODELS,
     "        if count <= 0 or count > MAX_DEPTH_TARGET:\n            continue\n        out[pos] = count",
     "        if count <= 0:\n            continue\n        out[pos] = min(count, MAX_DEPTH_TARGET)",
     "above_the_ceiling_is_dropped", "count > MAX_DEPTH_TARGET"),
    ("sanitize: accept ANY key, so an unknown position reaches storage", _MODELS,
     "    for pos in DEPTH_TARGET_POSITIONS:\n        value = raw.get(pos)",
     "    for pos in raw:\n        value = raw.get(pos)",
     "unknown_position_can_never_be_stored", "for pos in DEPTH_TARGET_POSITIONS:"),
    ("sanitize: store a zero, so `{}` and `{QB: 0}` stop being the same thing", _MODELS,
     "        if count <= 0 or count > MAX_DEPTH_TARGET:",
     "        if count < 0 or count > MAX_DEPTH_TARGET:",
     "shared_fixture_says", "        if count <= 0 or count > MAX_DEPTH_TARGET:"),

    # ── E9.49: a write rule must never gate a read ───────────────────────────────────────────────
    # ── the ANTI-DRIFT guarantee: TypeScript must answer the same as Python ──────────────────────
    ("typescript: make the browser resolver disagree (clearing a league re-inherits there)", _TS,
     "  if (args.league != null) {",
     "  if (args.league != null && Object.keys(args.league).length) {",
     "typescript_resolver_answers_identically", "  if (args.league != null) {\n"),

    ("validator: move it onto the SHARED base, so a READ rewrites what is stored", _MODELS,
     "    depth_targets: dict[str, int] | None = None\n",
     '    depth_targets: dict[str, int] | None = None\n\n'
     '    @field_validator("depth_targets")\n'
     "    @classmethod\n"
     "    def _dt_on_the_base(cls, v):\n"
     "        return None if v is None else sanitize_depth_targets(v)\n",
     "never_rewrites_what_is_stored", None),
]


def main() -> int:
    failures = []
    generated = REPO / "betting_ml/tests/fixtures/nf_c7b_depth_target_precedence_ts.json"
    generated_original = generated.read_text()
    for break_spec in BREAKS:
        name, rel, old, new, selector, gone = break_spec[:6]
        path = REPO / rel
        original = path.read_text()
        occurrences = original.count(old)
        if occurrences == 0:
            print(f"{'BROKEN ❌ (anchor not found)':34} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        if occurrences > 1:
            print(f"{'BROKEN ❌ (anchor not unique)':34} {name} -> {occurrences}x in {rel}")
            failures.append(f"{name}: anchor appears {occurrences}x in {rel}")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name
        if gone is not None and gone in mutated:
            print(f"{'BROKEN ❌ (token survives)':34} {name} -> {gone!r} still present")
            failures.append(f"{name}: asserted token survived the mutation")
            continue
        path.write_text(mutated)
        try:
            if rel == _TS:
                # ⚠️ REGENERATE, or the mutation sits in a file the Python guard never opens and the
                # break reports a false GREEN — the "mutation landed but does not bite" class
                # (E11.24 #815), here because the guard reads a COMMITTED artifact rather than the
                # source. A failed regen must abort the break, never fall through to pytest.
                regen = subprocess.run(_REGEN_TS, cwd=REPO, capture_output=True, text=True)
                if regen.returncode != 0:
                    print(f"{'BROKEN ❌ (regen failed)':34} {name}")
                    failures.append(f"{name}: TS fixture regeneration failed")
                    continue
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:34} {name}\n{'':34} -> {tail}")
        finally:
            path.write_text(original)
            generated.write_text(generated_original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} deliberate breaks were caught ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
