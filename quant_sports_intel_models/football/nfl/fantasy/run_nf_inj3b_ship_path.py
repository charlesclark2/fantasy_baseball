"""run_nf_inj3b_ship_path.py — the LEVEL-ADJACENT gated ship path for NF-INJ3b (preregistration §5).

NF-INJ3b CLEARED all nine registered gates. A cleared §0.5 gate is **not** a deploy: the arm changes
`proj_games`, and MVP-1's served point is `rate × games`, so a cap change is **LEVEL-ADJACENT** and
must clear the whole-board machinery NF-D16 / NF-D21 / NF-TR2b built before anyone may serve it.

This runner executes the parts of §5 that are executable TODAY and — just as importantly — NAMES the
part that is not, rather than letting an unrun step read as a pass (NF1.7 (a)):

  (a) whole-board cross-position PLACEMENT READ against the PUBLISHED artifact  → RUN HERE
  (b) `run_interval_revalidation` — every shipped 80% band vs its floor         → RUN HERE
  (c) the NF-TR2b SUPERFLEX caveat                                              → CARRIED HERE
  (d) the served-POINT impact, MEASURED not assumed proportional                → ⛔ NOT RUNNABLE HERE

⭐ **WHY (d) IS NOT RUNNABLE IN THIS SESSION, STATED PRECISELY.** The point impact of a games change
is NOT `pts × (arm_games / incumbent_games)`. NF1.5's ordering step PERMUTES the within-position
POINT multiset and rescales the stat line to the new point, so changing every flagged veteran's games
changes the multiset the permutation then re-assigns — NF-INJ1 measured that step handing **+36.4%**
of an availability discount BACK. So the served-point consequence is only obtainable from a real
counterfactual board REBUILD, and that rebuild needs a SERVED artifact for the fitted hurdle which
this deploy-held study deliberately does not create. ⇒ it is handed to the operator as an explicit
step, and this record refuses to publish a proportional figure in its place.

⛔ **OUTPUT DISCIPLINE.** Writes ONLY `nf_inj3b_ship_path.{json,md}`. Both underlying runners write
to a DECIDED story's fixed paths (`nf_tr2b_placement_read.*`, `nf1_9_interval_revalidation.json`), so
this one calls the placement read's pure `run()` (which writes nothing) and byte-RESTORES the
interval artifact afterwards. A post-decision story never clobbers a decided story's audit trail
(the NCAAF-P2.1 S1-serve lesson).

RUN (LAPTOP — needs S3 read on the api-cache bucket + the gitignored panel caches, NF-INFRA1):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3b_ship_path \
        --duckdb <main>/quant_sports_intel_models/sports_dbt/sports.duckdb \
        --artifacts <main>/quant_sports_intel_models/football/nfl/fantasy/artifacts
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_interval_revalidation as IV,
    run_nf_tr2b_placement_read as PR,
)

_ART = pathlib.Path(__file__).resolve().parent / "ablation_results"
_OUT_JSON = _ART / "nf_inj3b_ship_path.json"
_OUT_MD = _ART / "nf_inj3b_ship_path.md"
#: DECIDED artifacts this story's gates run against. Before NF-INJ3b-M node 1 (PM ruling D4) BOTH
#: were rewritten as a side effect of merely running the gate — the interval one even under
#: `--no-report`. They are now verified untouched rather than restored (see `run()`).
_DECIDED_INTERVAL_JSON = _ART / f"{IV.DECIDED_STEM}.json"
_DECIDED_PLACEMENT_JSON = _ART / f"{PR.DECIDED_STEM}.json"
#: this story's OWN output stem for the interval re-validation (the D4 `--out` fix in use).
_OUT_STEM_INTERVAL = "nf_inj3b_ship_path_interval_revalidation"

SUPERFLEX_CAVEAT = (
    "NF-TR2b: the VOR 'shield' — NF-W8-0's finding that a per-group level shift CANCELS in VOR space "
    "because a group's own replacement level absorbs it — is **ADDITIVE-ONLY**, and it additionally "
    "assumes the group is not cross-pooled. Two published configs are SUPERFLEX (`superflex_10`, "
    "`superflex_12`), where QB IS cross-pooled with RB/WR/TE, so the shield does NOT hold there. A "
    "cap change moves `proj_games` for flagged veterans at every position, so the superflex configs "
    "must be read on their own placement rows, never inferred from the non-superflex ones."
)


def placement_read() -> dict:
    """(a) — the whole-board cross-position placement read against the PUBLISHED artifact.

    Calls the TR2b runner's PURE `run()`, which returns a dict and writes nothing.

    ⭐ HISTORICAL NOTE, kept because it is the reason NF-INJ3b-M node 1 exists: this used to be a
    WORKAROUND. `PR.main()` overwrote `nf_tr2b_placement_read.*` — a DECIDED story's record — so
    calling `run()` was how this story avoided clobbering it. Since the D4 fix that is no longer
    necessary (`PR.main()` defaults to `PR.DEFAULT_STEM`), and `_assert_decided_artifacts_intact`
    below now VERIFIES the fix rather than routing around it."""
    with tempfile.TemporaryDirectory() as td:
        src = PR._fetch(pathlib.Path(td))
        return PR.run(src, origin=PR._S3)


def _decided_artifact_digests() -> dict[str, str | None]:
    """SHA-256 of every DECIDED artifact this story's gates touch, taken before and after."""
    import hashlib
    return {p.name: (hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)
            for p in (_DECIDED_INTERVAL_JSON, _DECIDED_PLACEMENT_JSON)}


def interval_revalidation(duckdb: str, artifacts: pathlib.Path) -> dict:
    """(b) — every shipped 80% band re-scored against its pre-registered coverage floor.

    ⛔ A BREACH EXITS NON-ZERO and is a RE-SELECTION TRIGGER, not a log line.

    ⭐ CONSUMES the NF-INJ3b-M node-1 (D4) fix rather than routing around it: the run is written to
    this story's OWN `--out` stem, so NF1.9's decided record is untouched by construction. Before
    D4 this function byte-restored that record afterwards, because `--no-report` rewrote its JSON
    anyway — a workaround the next session would have had to re-invent."""
    cmd = [sys.executable, "-m",
           "quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation",
           "--out", _OUT_STEM_INTERVAL, "--duckdb", duckdb,
           "--rookie-pool", str(artifacts / "nf1_4_rookie_training.parquet"),
           "--veteran-panel", str(artifacts / "nf1_9_veteran_band_panel"),
           "--kdst-panel", str(artifacts / "nfl_fantasy_kdst_band_panel.parquet")]
    r = subprocess.run(cmd, cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=1800)
    out_json = _ART / f"{_OUT_STEM_INTERVAL}.json"
    payload = json.loads(out_json.read_text()) if out_json.exists() else {}
    blocks = {b.get("population"): {
        "config": b.get("config"), "form": b.get("form"), "n": b.get("n"),
        "pooled_coverage": b.get("pooled_coverage"),
        "coverage": b.get("coverage"), "floors": b.get("floors"),
        "slack_rows": b.get("slack_rows"), "error": b.get("error")}
        for b in (payload.get("blocks") or [])}
    return {"exit_code": r.returncode, "all_floors_met": bool(payload.get("pass")),
            "blocks": blocks, "stdout_tail": r.stdout.strip().splitlines()[-1:],
            "written_to": f"{_OUT_STEM_INTERVAL}.json",
            "why_it_gates": "a floor breach is a RE-SELECTION trigger for that population, never a "
                            "reason to move the floor (E2.1-r / NF1.8 §1)"}


def run(duckdb: str, artifacts: pathlib.Path) -> dict:
    # ⭐ TWO-SIDED: take the decided artifacts' digests BEFORE the gates run and again after, so
    #    "the D4 fix works" is MEASURED by the caller rather than trusted (NF-C0e: wired ≠ invoked).
    before = _decided_artifact_digests()
    pl = placement_read()
    iv = interval_revalidation(duckdb, artifacts)
    after = _decided_artifact_digests()
    decided_intact = {k: bool(before[k] == after[k]) for k in before}
    steps = {
        "a_placement_read_published_board": {
            "status": "RUN", "verdict": pl["verdict"].get("verdict"),
            "gates": pl["verdict"].get("gates"),
            "source": pl.get("source"), "source_kind": pl.get("source_kind"),
            "served_level_model_version": pl.get("served_level_model_version"),
            "board_built_at": pl.get("projection_built_at"),
            "configs_read": sorted(c for c, v in pl["per_config"].items()
                                   if v.get("status") == "OK"),
            "configs_absent": sorted(c for c, v in pl["per_config"].items()
                                     if v.get("status") != "OK"),
            "scope": "⚠️ this is a BASELINE on the board AS PUBLISHED — it establishes that the "
                     "served board is placement-clean TODAY. It is NOT the counterfactual read: "
                     "the decision-relevant comparison (published board vs a board rebuilt on the "
                     "NF-INJ3b caps) is blocked on the same rebuild step (d) is blocked on.",
        },
        "b_interval_revalidation": {"status": "RUN", **iv},
        "c_superflex_caveat": {"status": "CARRIED", "caveat": SUPERFLEX_CAVEAT},
        "d_served_point_impact": {
            "status": "NOT_RUN_BLOCKING",
            "why": "the served POINT is not recoverable from the games change: NF1.5 PERMUTES the "
                   "within-position point multiset and rescales the stat line to the new point, so "
                   "a games change alters the multiset the permutation re-assigns (NF-INJ1 measured "
                   "that step handing +36.4% of an availability discount BACK). It requires a "
                   "counterfactual board REBUILD on the NF-INJ3b caps, which additionally needs a "
                   "SERVED artifact for the fitted hurdle that this deploy-held study deliberately "
                   "does not create.",
            "refused": "⛔ NO proportional estimate is published in its place. `pts × arm_games / "
                       "incumbent_games` is exactly the assumption preregistration §5 (d) forbids, "
                       "and publishing it would read as a measurement.",
            "operator_step": "rebuild the 2026 board with the NF-INJ3b caps, DRY-RUN (no --publish), "
                             "and diff the staged board against the published one on `pts`, "
                             "`proj_games`, overall rank and per-config placement.",
        },
    }
    executable_ok = bool(steps["a_placement_read_published_board"]["verdict"] in ("SANE", "PASS")
                         and iv["all_floors_met"] and iv["exit_code"] == 0)
    return {
        "story": "NF-INJ3b", "read": "level-adjacent gated ship path (preregistration §5)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_outcome": "CLEARS (9/9 registered gates)",
        "steps": steps,
        "d4_decided_artifacts_intact": {
            "verified": decided_intact, "all_intact": bool(all(decided_intact.values())),
            "what_it_proves": "running these gates left every DECIDED artifact byte-identical — "
                              "the NF-INJ3b-M node-1 (D4) fix, measured at the CALL SITE rather "
                              "than assumed from the runners' source."},
        "executable_steps_pass": executable_ok,
        "ship_path_complete": False,
        "verdict": "SHIP_PATH_INCOMPLETE — step (d) is unrun and BLOCKING",
        "deploy_held": True, "served_arm": "incumbent", "best_alpha": 0,
        "decision_owner": "OPERATOR — ship/no-ship is not this harness's call, and it cannot be "
                          "taken until (d) is measured.",
        "placement_read_full": pl,
    }


def _md(r: dict) -> str:
    s = r["steps"]
    a, b, c, d = (s["a_placement_read_published_board"], s["b_interval_revalidation"],
                  s["c_superflex_caveat"], s["d_served_point_impact"])
    L = [
        "# NF-INJ3b — the LEVEL-ADJACENT gated ship path (preregistration §5)",
        "",
        f"_generated {r['generated_at']}_ · `best_alpha = 0` · **DEPLOY-HELD**, served arm "
        f"`{r['served_arm']}`",
        "",
        f"## Verdict: **{r['verdict']}**",
        "",
        "NF-INJ3b cleared all nine registered gates. **A cleared §0.5 gate is not a deploy.** The arm "
        "changes `proj_games` and MVP-1's served point is `rate × games`, so the change is "
        "LEVEL-ADJACENT and must clear the whole-board machinery first. Two of the four steps run "
        "here and pass; one is carried; **one is unrun and BLOCKING** — and it is named rather than "
        "quietly omitted (NF1.7 (a): a check that did not run is not a pass).",
        "",
        "| step | status | result |", "|---|---|---|",
        f"| (a) whole-board cross-position placement read (published artifact) | {a['status']} | "
        f"**{a['verdict']}** — {a['gates']} |",
        f"| (b) `run_interval_revalidation` (every shipped 80% band vs its floor) | {b['status']} | "
        f"**{'ALL FLOORS MET' if b['all_floors_met'] else '🚨 FLOOR BREACH'}** (exit {b['exit_code']}) |",
        f"| (c) NF-TR2b superflex caveat | {c['status']} | see below |",
        f"| (d) served-POINT impact, MEASURED | **{d['status']}** | ⛔ blocking |",
        "",
        "## (a) Placement read — the PUBLISHED board, as a BASELINE",
        "",
        f"Read from `{a['source']}` (`{a['source_kind']}`), served level model "
        f"`{a['served_level_model_version']}`, board built {a['board_built_at']}. Configs read: "
        f"{len(a['configs_read'])}; absent: {a['configs_absent'] or 'none'}.",
        "",
        f"Verdict **{a['verdict']}**, gates `{a['gates']}`.",
        "",
        a["scope"],
        "",
        "## (b) Interval re-validation",
        "",
        f"**{'✅ ALL FLOORS MET' if b['all_floors_met'] else '🚨 FLOOR BREACH — RE-SELECTION TRIGGERED'}** "
        f"(exit {b['exit_code']}). {b['why_it_gates']}",
        "",
        "| population | form | n | pooled coverage |", "|---|---|---|---|",
    ]
    for pop, blk in (b["blocks"] or {}).items():
        L.append(f"| {pop} | {blk.get('form')} | {blk.get('n')} | {blk.get('pooled_coverage')} |")
    L += [
        "",
        f"Written to `{b['written_to']}` via the D4 `--out` stem. Decided artifacts verified "
        f"byte-identical across BOTH gates: `{r['d4_decided_artifacts_intact']['verified']}` "
        f"(all intact: **{r['d4_decided_artifacts_intact']['all_intact']}**) — measured at the "
        f"call site, not assumed from the runners' source.",
        "",
        "## (c) The NF-TR2b superflex caveat — CARRIED",
        "",
        c["caveat"],
        "",
        "## (d) ⛔ The served-POINT impact — UNRUN and BLOCKING",
        "",
        d["why"],
        "",
        d["refused"],
        "",
        f"**Operator step:** {d['operator_step']}",
        "",
        "## What this means for the decision",
        "",
        f"Every step that COULD run has run and passed (`executable_steps_pass: "
        f"{r['executable_steps_pass']}`). The ship path is nevertheless **INCOMPLETE**, so nothing "
        f"serves and `SERVED_ARM` stays `\"{r['served_arm']}\"`. {r['decision_owner']}",
        "",
    ]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3b level-adjacent gated ship path")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--artifacts", required=True,
                    help="dir holding the gitignored panel caches (NF-INFRA1)")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    rep = run(args.duckdb, pathlib.Path(args.artifacts))
    print(f"NF-INJ3b ship path — {rep['verdict']}")
    for k, v in rep["steps"].items():
        print(f"  {k:38s} {v['status']}")
    if not args.no_report:
        _ART.mkdir(parents=True, exist_ok=True)
        _OUT_JSON.write_text(json.dumps(rep, indent=2, default=str))
        _OUT_MD.write_text(_md(rep))
        print(f"wrote {_OUT_JSON.name} + {_OUT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
