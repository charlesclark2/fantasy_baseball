"""red_proof.py — deliberately break the source; assert each NF-W9-0 guard goes RED.

    uv run python quant_sports_intel_models/football/pff/red_proof.py

Committed rather than run once and discarded: E9.64 found six red-proof cases whose verdict had
silently stopped matching their declaration, and the mechanism was that nothing ever ran them.
A guard suite that has never been shown to FAIL carries far less information than it appears to.

Three lessons from the repo's own RED-proof failures are enforced here:
  #682 — assert the mutation actually LANDED on disk (a break that silently no-ops comes back
         green and reads as "the guard is vacuous", which is the dangerous direction).
  #815 — assert the mutated token is GONE, not merely that the file changed (a break that
         writes but does not move the asserted predicate is a false green).
  prediction_log — assert the anchor is UNIQUE in the file (a break can otherwise land on the
         wrong symbol and report a false vacuity).
"""
import pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(".").resolve()
TEST = "betting_ml/tests/test_nfl_pff_probe.py"

BREAKS = [
    ("guard: drop 'grades' from the banned tokens",
     "quant_sports_intel_models/football/pff/guards.py",
     '"grade", "grades", "graded",', '"graded",',
     "TestRawStatsOnlyGuard"),
    ("guard: make the token match a raw SUBSTRING (the 'downgrade' trap)",
     "quant_sports_intel_models/football/pff/guards.py",
     'return any(t in MODEL_OUTPUT_TOKENS for t in tokenize(column))',
     'return any(m in (column or "").lower() for m in MODEL_OUTPUT_TOKENS)',
     "TestRawStatsOnlyGuard"),
    ("client: stop detecting the HTML login page served with HTTP 200",
     "quant_sports_intel_models/football/pff/client.py",
     'if _looks_like_login(text):', 'if False:',
     "TestAuthFailsLoudly"),
    ("crosswalk: arbitrate an ambiguous vendor id instead of dropping it",
     "quant_sports_intel_models/football/pff/resolve.py",
     'df = df.drop_duplicates(subset=["gsis_id", "source_player_id"])',
     'df = df.drop_duplicates(subset=["source_player_id"])',
     "TestCrosswalk"),
    ("resolve_games: drop the swapped-orientation pass",
     "quant_sports_intel_models/football/pff/resolve.py",
     'for h_col, a_col, method in ((pff_home, pff_away, "exact"), (pff_away, pff_home, "swapped")):',
     'for h_col, a_col, method in ((pff_home, pff_away, "exact"),):',
     "TestGameResolution"),
    ("probe: let a zero-row pull report success",
     "quant_sports_intel_models/football/pff/probe.py",
     'raise PFFClientError(msg + " — refusing to report a zero-row pull as a success.")',
     'pass',
     "TestProbeFailsLoud"),
    ("schools: use the NFL team folder instead of the college school key",
     "quant_sports_intel_models/football/pff/resolve.py",
     'r["_team"] = r["team"].map(school_key)', 'r["_team"] = r["team"].map(normalize_team)',
     "TestNcaafResolution"),
    ("schools: drop the accent/punctuation folding",
     "quant_sports_intel_models/football/pff/schools.py",
     's = _PUNCT_RE.sub(" ", s).strip()', 's = s.strip()',
     "TestSchoolKey"),
    ("schools: expand a LEADING 'St' to 'State' too (the Saint homograph)",
     "quant_sports_intel_models/football/pff/schools.py",
     '_TRAILING_ST_RE = re.compile(r"\\bst$")', '_TRAILING_ST_RE = re.compile(r"\\bst\\b")',
     "TestSchoolKey"),
    ("ncaaf: stop distinguishing an unknown SCHOOL from an unknown PLAYER",
     "quant_sports_intel_models/football/pff/resolve.py",
     'out["unknown_school"] = ~s_team.isin(known)', 'out["unknown_school"] = False',
     "TestNcaafResolution"),
    ("probe: hardcode ONE team key for the game join regardless of league",
     "quant_sports_intel_models/football/pff/probe.py",
     'team_key=normalize_team if league == "nfl" else school_key,',
     'team_key=normalize_team,',
     "TestGameJoinUsesTheLeagueCorrectTeamKey"),
    ("client: send the cookie twice (the live HTTP 431)",
     "quant_sports_intel_models/football/pff/client.py",
     's.headers.update(self._headers(include_cookie=False))',
     's.headers.update(self._headers(include_cookie=True))',
     "TestClerkAuthMechanics"),
    ("client: stop naming the Clerk handshake",
     "quant_sports_intel_models/football/pff/client.py",
     'if "__clerk_hs_reason" in text or "/v1/client/handshake" in text[:2000]:',
     'if False:',
     "TestClerkAuthMechanics"),
    ("client: split cookies on EVERY '=' (truncates the JWT)",
     "quant_sports_intel_models/football/pff/client.py",
     'k, v = chunk.split("=", 1)\n            out.append((k.strip(), v.strip()))',
     'parts = chunk.split("=")\n            out.append((parts[0].strip(), parts[1].strip()))',
     "TestClerkAuthMechanics"),
    ("facets: let `restricted` be mistaken for the row list",
     "quant_sports_intel_models/football/pff/facets.py",
     'if isinstance(v, list) and k != RESTRICTED_KEY',
     'if isinstance(v, list)',
     "TestEntitlementIsAFirstClassFinding"),
    ("client: retry a 404 like any other error",
     "quant_sports_intel_models/football/pff/client.py",
     'raise PFFNotFoundError(f"{url} does not exist (HTTP 404)")',
     'pass',
     "TestEntitlementIsAFirstClassFinding"),
    ("probe: use ONE team-label key for both leagues",
     "quant_sports_intel_models/football/pff/probe.py",
     '"ncaa": ("city", "mid_abbreviation", "nickname", "slug"),',
     '"ncaa": ("abbreviation", "mid_abbreviation", "nickname", "slug"),',
     "TestTeamComesFromTheGameNotTheFacetRow"),
    ("schools: fold 'state' away as a generic suffix (merges Ohio / Ohio State)",
     "quant_sports_intel_models/football/pff/schools.py",
     '_SUFFIX_RE = re.compile(r"\\b(university|college|the)\\b")',
     '_SUFFIX_RE = re.compile(r"\\b(university|college|the|state)\\b")',
     "TestSchoolAliasesAreMeasuredNotGuessed"),
    ("probe: restore the retracted 'withheld by the subscription tier' verdict",
     "quant_sports_intel_models/football/pff/probe.py",
     '"NO_OPPORTUNITY_FIELDS_IN_THIS_RESPONSE — this endpoint omits every field the "',
     '"NO_OPPORTUNITY_FIELDS — every field is withheld by the subscription tier; "',
     "TestTheEntitlementMisreadingCannotRecur"),
    ("export: stop sending export=true (silently falls back to the reduced field set)",
     "quant_sports_intel_models/football/pff/client.py",
     'payload = self.get(path, {**(params or {}), "export": "true"}, expect="csv")',
     'payload = self.get(path, {**(params or {})}, expect="csv")',
     "TestTheExportPath"),
    ("export: coerce a blank cell to 0.0 (fabricates data)",
     "quant_sports_intel_models/football/pff/client.py",
     '            if v is None or v == "":\n                row[k] = None\n                continue',
     '            if v is None or v == "":\n                row[k] = 0.0\n                continue',
     "TestTheExportPath"),
    ("export: return the CSV before the auth checks run",
     "quant_sports_intel_models/football/pff/client.py",
     '    if _looks_like_login(text):',
     '    if _looks_like_login(text) and expect != "csv":',
     "TestTheExportPath"),
    ("id-space: score an untested (no-ids) probe as agreement",
     "quant_sports_intel_models/football/pff/resolve.py",
     '"UNTESTED (no PFF ids in probe)" if not ids',
     '"SAME_ID_SPACE" if not ids',
     "TestIdSpaceAssumption"),
]

fails = 0
for label, rel, old, new, node in BREAKS:
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td) / "repo"
        shutil.copytree(ROOT, work, symlinks=True, ignore=shutil.ignore_patterns(
            ".git", ".venv", "node_modules", "frontend", "dbt", "__pycache__", "*.parquet"))
        f = work / rel
        src = f.read_text()
        n = src.count(old)
        if n != 1:
            print(f"✗ ANCHOR NOT UNIQUE ({n} hits) for {label}"); fails += 1; continue
        mutated = src.replace(old, new, 1)
        f.write_text(mutated)
        after = f.read_text()
        if after == src or old in after:            # #682 + #815
            print(f"✗ MUTATION DID NOT LAND for {label}"); fails += 1; continue
        r = subprocess.run(
            [sys.executable, "-m", "pytest", f"{TEST}::{node}", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=work, capture_output=True, text=True)
        red = r.returncode != 0
        print(f"{'✓ RED' if red else '✗ STILL GREEN (VACUOUS)'} — {label}")
        if not red:
            fails += 1
            print(r.stdout[-600:])
print(f"\n{len(BREAKS) - fails}/{len(BREAKS)} guards proven RED")
sys.exit(1 if fails else 0)
