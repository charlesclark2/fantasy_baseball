"""RED proof for the NCAAF-CLV-repair guards.

Each break is applied IN-PROCESS to a real source file, the mutation is ASSERTED TO HAVE LANDED and
to be UNIQUE (E11.24 #682/#815/prediction_log: a break that does not write, does not move the
asserted predicate, or lands on the wrong symbol all report a FALSE verdict), then pytest runs.
Backups are restored at START-UP too, so a kill mid-mutation cannot leave a broken tree.
"""
import subprocess, sys
from pathlib import Path

# run from the repo root: `uv run python quant_sports_intel_models/football/ncaaf/models/ncaaf_clv_repair_red_proof.py`
M = Path("quant_sports_intel_models/football/ncaaf/models")
BAKE, VAL1 = M / "bakeoff_ncaaf_game.py", M / "ncaaf_val1_clv_week_strat.py"
TEST = "betting_ml/tests/test_ncaaf_clv_row_alignment.py"

BREAKS = [
    ("bakeoff: restore the ORIGINAL defect (reset index as the draw index)", BAKE,
     "    idx = np.flatnonzero(mask)\n    m = merged[mask].reset_index(drop=True)\n",
     "    m = merged[mask].reset_index(drop=True)\n    idx = m.index.to_numpy()\n"),
    ("bakeoff: recover the positions AFTER the reset (order defect only)", BAKE,
     "    idx = np.flatnonzero(mask)\n    m = merged[mask].reset_index(drop=True)\n",
     "    m = merged[mask].reset_index(drop=True)\n    idx = np.flatnonzero(m.index >= 0)\n"),
    ("bakeoff: drop the merge row-count HALT", BAKE,
     '    if len(merged) != len(oos):\n        raise SystemExit(f"[{_STORY}] the close join changed the row count ({len(oos):,} → "\n',
     '    if False:\n        raise SystemExit(f"[{_STORY}] the close join changed the row count ({len(oos):,} → "\n'),
    ("val1: restore the ORIGINAL defect", VAL1,
     "    idx = np.flatnonzero(mask)\n    m = merged[mask].reset_index(drop=True)\n",
     "    m = merged[mask].reset_index(drop=True)\n    idx = m.index.to_numpy()\n"),
    ("val1: drop the merge row-count HALT", VAL1,
     '    if len(merged) != len(oos):\n', '    if False and len(merged) != len(oos):\n'),
    ("val1: pin targets stop naming the repaired parent", VAL1,
     '"source": "ncaaf_s1_serve_calibration (repaired _clv_eval)"',
     '"source": "hand-set"'),
]

def restore():
    for f in (BAKE, VAL1):
        b = f.with_suffix(f.suffix + ".redbak")
        if b.exists():
            f.write_text(b.read_text()); b.unlink()

restore()                                             # a prior kill may have left a mutation
red = 0
for i, (label, path, old, new) in enumerate(BREAKS, 1):
    src = path.read_text()
    n = src.count(old)
    if n != 1:
        print(f"{i}. {label}\n   ⛔ ANCHOR NOT UNIQUE ({n} occurrences) — break not applied, verdict void")
        continue
    path.with_suffix(path.suffix + ".redbak").write_text(src)
    mutated = src.replace(old, new, 1)
    path.write_text(mutated)
    assert path.read_text() == mutated and path.read_text() != src, "mutation did not land"
    assert old not in path.read_text() or old in new, "mutation landed but did not remove the target"
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header", "-p", "no:cacheprovider"],
                       capture_output=True, text=True)
    restore()
    ok = r.returncode != 0
    red += ok
    print(f"{i}. {label}\n   {'RED ✅' if ok else 'GREEN ❌ (guard is VACUOUS)'}  "
          f"({[l for l in r.stdout.splitlines() if 'passed' in l or 'failed' in l][-1:]})")

print(f"\n{red}/{len(BREAKS)} breaks caught")
restore()
sys.exit(0 if red == len(BREAKS) else 1)
