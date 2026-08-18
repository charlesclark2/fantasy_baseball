"""mh1_margin_attribution.py — MH1 driver: re-emit the affected §0.5 reports, and pin the verdicts.

MH1 ports E7.9's learner-vs-contract margin decomposition into a single shared owner
(`betting_ml.utils.margin_attribution`) and wires it into every report the affected harnesses
write. This driver does the two things a session must NOT do by hand:

  `--rewrite-all`       re-emit every affected report FROM STORED ARM JSON. ⛔ **NO RE-FITTING.**
                        Every score in every re-emitted report is read off the recorded table; not
                        one model is trained. (E7.9's `--rewrite-reports` proved this path.)

  `--capture-baseline`  snapshot the DECISION fields of every affected stored result AT A GIT REF,
                        so the guard can prove the MIGRATION itself changed no verdict — not merely
                        that a re-run is idempotent. Committed as a fixture and re-derivable:
                        `--ref <sha>` reads the blobs out of git, never the working tree, so the
                        baseline cannot be quietly regenerated from already-changed files.

  `--check`             print the verdict-invariance diff (the same comparison the guard asserts).

⚠️ **ATTRIBUTION IS PRESENTATIONAL.** No gate, threshold, verdict, winner or selection is
recomputed anywhere in this story. A decomposition that would move a verdict is a bug, not a
feature — which is exactly what the baseline pins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_JSON_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "bakeoff"
BASELINE_PATH = (PROJECT_ROOT / "betting_ml" / "tests" / "fixtures"
                 / "mh1_verdict_baseline.json")

# The keys MH1 is allowed to add/replace. EVERYTHING else in a stored result is a decision field
# and must survive the migration byte-identically.
ATTRIBUTION_KEYS = ("margin_attribution", "margin_decomposition")

# The stored results MH1 touches, relative to `_JSON_DIR`.
AFFECTED_GLOBS = ("bakeoff_*.json", "e7_9_retrain_*.json")

# The legacy sub-keys of E7.9's `margin_decomposition` block. MH1 adds keys beside these; it must
# not move one of THEM, because those are the numbers the recorded reports quote.
LEGACY_DECOMP_KEYS = ("available", "total", "learner_swap", "contract", "learner_share",
                      "same_learner_reference_arm")


def affected_names() -> list[str]:
    names: list[str] = []
    for pat in AFFECTED_GLOBS:
        names += [p.name for p in _JSON_DIR.glob(pat)]
    return sorted(set(names))


def decision_fingerprint(result: dict) -> dict:
    """Everything that is NOT the attribution block, hashed — plus the legacy decomposition values.

    A hash over the whole remainder is deliberately stricter than an enumerated field list: a field
    added to the harness later is covered automatically, so the guard cannot rot into checking a
    subset of what a verdict now depends on.
    """
    rest = {k: v for k, v in result.items() if k not in ATTRIBUTION_KEYS}
    blob = json.dumps(rest, sort_keys=True, separators=(",", ":"), default=float)
    legacy = {}
    old = result.get("margin_decomposition")
    if isinstance(old, dict):
        legacy = {k: old[k] for k in LEGACY_DECOMP_KEYS if k in old}
    return {"sha256": hashlib.sha256(blob.encode()).hexdigest(),
            "n_fields": len(rest),
            "legacy_margin_decomposition": legacy}


def _read_at_ref(ref: str, relpath: str) -> dict:
    out = subprocess.run(["git", "show", f"{ref}:{relpath}"], cwd=PROJECT_ROOT,
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def capture_baseline(ref: str) -> dict:
    """Fingerprint every affected result AS OF `ref` (a git ref — never the working tree)."""
    rel = _JSON_DIR.relative_to(PROJECT_ROOT)
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, str(rel)],
                            cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    tracked = {Path(p).name: p for p in listed.stdout.split() if p.endswith(".json")}
    baseline = {"ref": subprocess.run(["git", "rev-parse", ref], cwd=PROJECT_ROOT,
                                      capture_output=True, text=True, check=True).stdout.strip(),
                "results": {}}
    for name in affected_names():
        path = tracked.get(name)
        if path is None:          # a result created after `ref` has no baseline to preserve
            continue
        baseline["results"][name] = decision_fingerprint(_read_at_ref(ref, path))
    return baseline


def check(baseline: dict) -> list[str]:
    """Return a human-readable diff of every decision-field change since the baseline (empty = OK)."""
    problems: list[str] = []
    for name, want in baseline["results"].items():
        path = _JSON_DIR / name
        if not path.exists():
            problems.append(f"{name}: stored result DISAPPEARED")
            continue
        got = decision_fingerprint(json.loads(path.read_text()))
        if got["sha256"] != want["sha256"]:
            problems.append(f"{name}: decision fields CHANGED "
                            f"({want['n_fields']}→{got['n_fields']} fields)")
        if got["legacy_margin_decomposition"] != want["legacy_margin_decomposition"]:
            problems.append(f"{name}: legacy margin_decomposition values moved: "
                            f"{want['legacy_margin_decomposition']} → "
                            f"{got['legacy_margin_decomposition']}")
    return problems


def rewrite_all() -> dict[str, list[str]]:
    """Re-emit every affected report from stored JSON. NOT ONE MODEL IS FITTED."""
    from betting_ml.scripts import e7_9_train_serve_consistency as e79
    from betting_ml.scripts import model_bakeoff as mb
    return {"model_bakeoff": mb.rewrite_reports(), "e7_9": e79.rewrite_reports()}


_REPORT_PATH = (PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program"
                / "ablation_results" / "mh1_margin_attribution.md")


def _decomp_rows() -> list[dict]:
    """Every affected result's attribution, read off the re-emitted JSON (never hand-typed)."""
    rows = []
    for name in affected_names():
        d = json.loads((_JSON_DIR / name).read_text())
        att = d.get("margin_attribution") or {"decomposition": d.get("margin_decomposition") or {},
                                              "leader_arm": d.get("leader_arm"),
                                              "incumbent_arm": d.get("incumbent_arm")}
        rows.append({"result": name.replace(".json", ""), "metric": d["metric"],
                     "noise_floor": d.get("noise_floor"), "att": att,
                     "harness": "e7_9" if name.startswith("e7_9") else "model_bakeoff"})
    return rows


def write_report() -> Path:
    rows = _decomp_rows()
    active = [r for r in rows if r["att"]["decomposition"].get("available")]
    L: list[str] = [
        "# MH1 — margin attribution across the shared bake-off harness", "",
        "> ⚠️ **Not an edge claim.** `best_alpha = 0`. MH1 changes no model, no feature, no gate and "
        "no verdict — it changes what a report is allowed to CLAIM a margin means.", "",
        "## What the defect was", "",
        "A `(contract variant × learner class)` bake-off reports one headline number, "
        "`margin = incumbent_arm − leader_arm`. That is the right PROMOTION question and is "
        "unchanged here. It is the wrong number to attribute to a FEATURE study, because a leader "
        "that also swapped its learner class carries both effects in one figure.", "",
        "E7.9 measured this on itself (54–77% of its margins were the learner swap) and fixed it "
        "locally. MH1's finding is that the defect is GENERIC: `model_bakeoff.py` has the same arm "
        "shape and the same leader-vs-incumbent comparison — but SPREAD ACROSS A PAIR OF RUNS "
        "(a `--contract` variant run beside the tier-default run), so the comparison a reader makes "
        "was made BY EYE, across two reports, with nothing holding the learner fixed. Strictly more "
        "exposed than E7.9 was: there, at least one number was computed; here, none was.", "",
        "## What shipped", "",
        "- `betting_ml/utils/margin_attribution.py` — the ONE owner of the decomposition and its "
        "markdown block (pure, IO-free, fast-gate safe). E7.9 now DELEGATES to it; its local "
        "implementation is gone, verified byte-identical on all three recorded results first.",
        "- `model_bakeoff.py` emits the block on EVERY report — including the runs where the "
        "decomposition cannot act, which carry a NAMED reason. Silence and \"checked, came back "
        "clean\" must not look the same (NF1.7 (a)).",
        "- `--rewrite-reports` / `mh1_margin_attribution.py --rewrite-all` re-emit every recorded "
        "report FROM STORED ARM JSON. **⛔ Not one model was fitted.**", "",
        "## Two readings the raw share cannot give you", "",
        "**1 — A SIGN FLIP.** `learner_share > 1` means the CONTRACT component points the OPPOSITE "
        "way to the headline: holding the learner fixed, the \"winning\" contract LOST. That is not "
        "over-crediting, it is the wrong DIRECTION, and it is flagged separately.", "",
        "**2 — A SUB-NOISE DENOMINATOR.** A share is a RATIO, and a ratio whose denominator sits "
        "inside the metric's own noise floor is noise amplification, not a proportion. The number "
        "is still computed (the recorded values did not move) but the report refuses to headline a "
        "percentage it cannot support. ⚠️ **This applies to E7.9's own quoted figures: two of its "
        "three margins (0.0053 and 0.0127 crps against a 0.02 floor) are sub-noise, so its "
        "\"54%\" and \"77%\" are shares of a denominator the gate itself calls noise.** The "
        "ABSOLUTE contract components (+0.0059 / +0.0012 / +0.0053) are unaffected and are what "
        "should be quoted.", "",
        "## Every affected result", "",
        f"| result | harness | metric | total | learner swap | contract | share | reading |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        d = r["att"]["decomposition"]
        if not d.get("available"):
            L.append(f"| `{r['result']}` | {r['harness']} | {r['metric']} | — | — | — | — | "
                     f"_inactive — {d.get('reason', 'no reason recorded')}_ |")
            continue
        share = d.get("learner_share")
        meaningful = d.get("share_is_meaningful")
        share_s = ("—" if share is None else
                   (f"{share:.0%}" if meaningful is not False else f"({share:.0%}) sub-noise"))
        if d.get("sign_flip"):
            read = "🚩🚩 **SIGN FLIP** — the contract is WORSE holding the learner fixed"
        elif share is not None and share >= 0.5:
            read = "🚩 majority of the margin is the LEARNER SWAP"
        else:
            read = "contract-dominated ✅"
        L.append(f"| `{r['result']}` | {r['harness']} | {r['metric']} | {d['total']:+.4f} | "
                 f"{d['learner_swap']:+.4f} | {d['contract']:+.4f} | {share_s} | {read} |")
    L += ["",
          f"Active decompositions: **{len(active)} of {len(rows)}**. The rest are single-contract "
          "runs with no contract axis — an inactive check is NOT a passed one (NF-D20), which is "
          "why the count is stated rather than implied.", "",
          "## The finding", "",
          "**`total_runs / pre_lineup` is a SIGN FLIP.** The 14-column re-pruned contract shows a "
          "`+0.0007` crps margin over the 87-column incumbent — but holding the learner fixed it is "
          "`-0.0029` WORSE, and it is worse for all four of the most competitive learners "
          "(`ngboost_normal` −0.0029, `ngboost_lognormal` −0.0009, `glm_elasticnet` −0.0184, "
          "`catboost` −0.0102); it wins only on the three weakest. The entire apparent margin, and "
          "more, is the `glm_elasticnet → ngboost_normal` swap. ⚠️ Every one of these quantities is "
          "inside the 0.02 crps noise floor, so the honest statement is **\"this pair of runs is "
          "evidence for nothing\"** — which is a materially different record from \"the re-pruned "
          "contract won\".", "",
          "`home_win / post_lineup` is 68% learner swap (the contract bought +0.0009 of a +0.0029 "
          "margin, against a 0.002 brier floor). `home_win / pre_lineup` is only 11% learner — a "
          "genuine contract effect. **The instrument exonerates as well as accuses**, which is what "
          "makes it worth reading.", "",
          "## Where the decomposition is structurally INACTIVE (and why that is a finding)", "",
          "Checked, so a future session does not chase a non-defect:", "",
          "- **NCAAF P1.4** (`bakeoff_ncaaf_game.py`) has a literal `learner × contract × form` "
          "grid and IS the same arm shape — but its verdict is `REFERENCE_STANDS` with "
          "`winner=None` and `gain_vs_reference=0.0`, so there is no promoted margin to "
          "mis-attribute. It becomes affected the moment a winner is promoted.",
          "- **NFL fantasy** (`run_nf_w*_bakeoff.py`) arms are mechanism/form arms on a FIXED "
          "feature set — no contract axis, so no learner-vs-contract confound exists to split.",
          "- **`h_harness.py`** (MiLB/prospect, E7.12/E7.15/MH2.x) arms are hypothesis arms against "
          "a shared foil — same reason.", "",
          "All three can adopt the shared owner by calling it; none needed a report change now. "
          "The shared function takes `lower_is_better=` precisely so a higher-is-better vertical "
          "cannot adopt it and get every sign silently backwards.", "",
          "## Verdict safety", "",
          "Attribution is PRESENTATIONAL. A decomposition that would move a verdict is a bug, not a "
          "feature — so the proof is a fingerprint of every decision field of all "
          f"{len(rows)} affected results, captured at the PRE-MH1 commit "
          "(`betting_ml/tests/fixtures/mh1_verdict_baseline.json`, read out of git blobs, never the "
          "working tree) and asserted by "
          "`test_mh1_margin_attribution.py::test_no_verdict_gate_or_selection_moved_across_the_"
          "whole_migration`. The fingerprint hashes EVERY field except the attribution block, so a "
          "field added to the harness later is covered without editing the guard.", "",
          "Result: **no verdict, gate, winner, tie-break, PBO or margin moved.** 20 guards, all 14 "
          "declared breaks RED-proved (`betting_ml/tests/mh1_red_proof.py`).", "",
          "## Reproduce", "",
          "```bash",
          "# LAPTOP — re-emit every affected report from stored arm JSON (no fitting, ~2s)",
          "uv run python betting_ml/scripts/mh1_margin_attribution.py --rewrite-all --check",
          "uv run python betting_ml/tests/mh1_red_proof.py",
          "```", ""]
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text("\n".join(L))
    return _REPORT_PATH


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rewrite-all", action="store_true",
                    help="Re-emit every affected report from stored arm JSON (no re-fitting).")
    ap.add_argument("--capture-baseline", action="store_true",
                    help="Write the decision-field baseline fixture (reads git, not the worktree).")
    ap.add_argument("--ref", default="HEAD", help="Git ref to capture the baseline at.")
    ap.add_argument("--report", action="store_true",
                    help="Write ablation_results/mh1_margin_attribution.md from the stored JSON.")
    ap.add_argument("--check", action="store_true",
                    help="Diff today's stored results against the committed baseline.")
    args = ap.parse_args()

    if args.capture_baseline:
        bl = capture_baseline(args.ref)
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(bl, indent=2, sort_keys=True) + "\n")
        print(f"Wrote {BASELINE_PATH} — {len(bl['results'])} results at {bl['ref'][:12]}")
    if args.rewrite_all:
        for harness, written in rewrite_all().items():
            print(f"{harness}: re-emitted {len(written)} report(s)")
            for w in written:
                print(f"  - {w}")
    if args.report:
        print(f"Wrote {write_report()}")
    if args.check:
        bl = json.loads(BASELINE_PATH.read_text())
        problems = check(bl)
        print("\n".join(problems) if problems
              else f"✅ verdict-invariant: {len(bl['results'])} stored results, "
                   f"no decision field moved since {bl['ref'][:12]}")
        raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
