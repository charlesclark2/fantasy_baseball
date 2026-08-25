"""run_nf_inj3b_ship_combined_read.py — NF-INJ3b-SHIP node 5: THE D10 COMBINED READ.

⭐ WHY IT IS COMBINED, and it is the whole ruling. Two things gate the first publish of a
level-adjacent change: a whole-board cross-position PLACEMENT read and an INTERVAL revalidation.
Run per-story, each answers about a board that moved for ONE reason. But the board that actually
publishes carries EVERYTHING that is live at publish time — this flip, plus whatever
NF-INJ-NEWS-1 overrides have been adopted, plus the post-cutdown rookie rows — and a per-story read
CANNOT ATTRIBUTE a board that moved for two reasons. So there is ONE read, on the ONE board.

⭐⭐ IT BINDS TO A BOARD, NOT TO A DATE. This is the operational consequence and it is easy to lose:
if the adoption state of the overrides changes, or the roster cutdown lands and the rookie rows
move, the board that would publish is NO LONGER the board this read covers, and the read must be
RE-RUN before that board ships. The report therefore records the exact publish-state it saw —
override count, rookie-row count, injury stamp — so a later reader can tell at a glance whether it
still applies rather than having to reconstruct it.

⛔ OUTPUT DISCIPLINE (the D4 rule). Writes ONLY under this story's `--out` stem, and the interval
leg runs under its own stem too. Both underlying runners have DECIDED artifacts
(`nf_tr2b_placement_read.*`, `nf1_9_interval_revalidation.*`); their digests are taken before and
after and the report states whether they are intact — MEASURED at the call site, never assumed from
the runners' source (NF-C0e).

🔒 It reads a STAGED export directory and publishes nothing. No `--publish`, no S3 write.

RUN (LAPTOP — needs the gitignored panel caches + build artifacts, NF-INFRA1):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3b_ship_combined_read \
        --staged /tmp/nf_inj3b_ship_stage/2026 \
        --artifacts quant_sports_intel_models/football/nfl/fantasy/artifacts
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import pandas as pd

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    injury_games_publish_guard as IGPG,
    run_interval_revalidation as IV,
    run_nf_tr2b_placement_read as PR,
)

log = logging.getLogger("nfl.fantasy.nf_inj3b_ship.combined_read")

_ART = pathlib.Path(__file__).resolve().parent / "ablation_results"
_DECIDED = (_ART / f"{PR.DECIDED_STEM}.json", _ART / f"{IV.DECIDED_STEM}.json")
_INTERVAL_STEM = "nf_inj3b_ship_combined_read_interval_revalidation"


def _digests() -> dict[str, str | None]:
    return {p.name: (hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)
            for p in _DECIDED}


def publish_state(staged: pathlib.Path) -> dict:
    """WHAT THIS BOARD IS — the state the read is valid FOR, read off the staged bytes.

    ⭐ Recorded rather than described, because the read binds to a board: a later reader must be
    able to tell whether the board in front of them is still this one WITHOUT reconstructing the
    session that produced it."""
    proj = json.loads((staged / "projections.json").read_text())
    manifest_p = staged / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    players = proj.get("players") or []
    rookies = sum(1 for r in players if r.get("rookie"))
    return {
        "season": proj.get("season"),
        "generated_at": proj.get("generated_at"),
        "projection_source": proj.get("projection_source"),
        "n_players": len(players),
        "n_rookie_rows": int(rookies),
        # ── the three components the D10 ruling names ────────────────────────────────────────
        "injury_games_policy": proj.get("injury_games_policy"),
        "reported_absence_count": manifest.get("reportedAbsenceCount"),
        "injury_games_stamp_verdict": (manifest.get("injuryGamesStamp") or {}).get("verdict"),
        "rookie_policy": proj.get("rookie_policy"),
        "veteran_level_policy": proj.get("veteran_level_policy"),
        "freshness": proj.get("freshness"),
        "binds_to": (
            "THE BOARD, NOT THE DATE. If `reported_absence_count` changes (NF-INJ-NEWS-1 overrides "
            "adopted or withdrawn), or `n_rookie_rows` changes (the roster cutdown), or "
            "`injury_games_policy` changes, the board that would publish is no longer the board "
            "this read covers and the combined read must be RE-RUN before it ships."),
    }


def placement(staged: pathlib.Path) -> dict:
    """The whole-board cross-position placement read, on the PUBLISH-CANDIDATE staged board.

    ⚠️ NOT the S3 read the NF-INJ3b ship path ran. That one is a BASELINE on the board as currently
    PUBLISHED, and it structurally cannot see a change that has not shipped. The decision-relevant
    board is the one that WOULD ship, which is what `--staged` points at."""
    return PR.run(staged, origin=None)


def interval(duckdb: str, artifacts: pathlib.Path) -> dict:
    """Every shipped 80% band re-scored against its pre-registered coverage floor.

    ⛔ A breach is a RE-SELECTION trigger for that population, never a reason to move the floor
    (E2.1-r / NF1.8 §1). Runs under THIS story's `--out` stem so NF1.9's decided record is untouched
    by construction (the D4 fix, consumed rather than routed around)."""
    cmd = [sys.executable, "-m",
           "quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation",
           "--out", _INTERVAL_STEM, "--duckdb", duckdb,
           "--rookie-pool", str(artifacts / "nf1_4_rookie_training.parquet"),
           "--veteran-panel", str(artifacts / "nf1_9_veteran_band_panel"),
           "--kdst-panel", str(artifacts / "nfl_fantasy_kdst_band_panel.parquet")]
    r = subprocess.run(cmd, cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=1800)
    out_json = _ART / f"{_INTERVAL_STEM}.json"
    payload = json.loads(out_json.read_text()) if out_json.exists() else {}
    blocks = {b.get("population"): {"config": b.get("config"), "form": b.get("form"),
                                    "n": b.get("n"), "pooled_coverage": b.get("pooled_coverage"),
                                    "floors": b.get("floors"), "error": b.get("error")}
              for b in (payload.get("blocks") or [])}
    return {"exit_code": r.returncode, "all_floors_met": bool(payload.get("pass")),
            "blocks": blocks, "written_to": f"{_INTERVAL_STEM}.json",
            "stderr_tail": r.stderr.strip().splitlines()[-3:],
            "why_it_gates": "a floor breach is a RE-SELECTION trigger for that population, never a "
                            "reason to move the floor (E2.1-r / NF1.8 §1)"}


def run(staged: pathlib.Path, duckdb: str, artifacts: pathlib.Path) -> dict:
    if not (staged / "projections.json").exists():
        raise SystemExit(
            f"NF-INJ3b-SHIP: no staged board at {staged}. The combined read runs on the board that "
            f"WOULD PUBLISH, so it needs a staged export — build it with `export_draft_board_json "
            f"--season 2026 --out {staged}` (⛔ no --publish). An unrun read is not a pass "
            f"(NF1.7 (a)).")
    state = publish_state(staged)
    before = _digests()
    pl = placement(staged)
    iv = interval(duckdb, artifacts)
    after = _digests()
    intact = {k: bool(before[k] == after[k]) for k in before}

    # the D6 guard, re-read on the very artifact the combined read covers
    stamp = state.get("injury_games_policy") or {}
    combined_pass = bool(pl["verdict"].get("verdict") in ("SANE", "PASS")
                         and iv["all_floors_met"] and iv["exit_code"] == 0)
    return {
        "story": "NF-INJ3b-SHIP",
        "read": "node 5 — the D10 COMBINED READ (placement + interval) on the publish candidate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "publish_state": state,
        "placement": {"verdict": pl["verdict"].get("verdict"), "gates": pl["verdict"].get("gates"),
                      "source": pl.get("source"), "source_kind": pl.get("source_kind"),
                      "served_level_model_version": pl.get("served_level_model_version"),
                      "configs_read": sorted(c for c, v in pl["per_config"].items()
                                             if v.get("status") == "OK"),
                      "configs_absent": sorted(c for c, v in pl["per_config"].items()
                                               if v.get("status") != "OK"),
                      "per_config": pl["per_config"]},
        "interval": iv,
        "injury_games_stamp_on_the_read_board": stamp,
        "decided_artifacts_intact": intact,
        "combined_verdict": ("PASS" if combined_pass else "FAIL"),
        "why_combined": (
            "a per-story read cannot attribute a board that moved for two reasons. The board that "
            "publishes carries this flip PLUS whatever else is live, so there is ONE read on the "
            "ONE board — and it binds to that board, not to a date."),
        "deploy_held": True, "published": False, "best_alpha": 0,
    }


def _md(r: dict) -> str:
    s, pl, iv = r["publish_state"], r["placement"], r["interval"]
    ig = s.get("injury_games_policy") or {}
    L = [
        "# NF-INJ3b-SHIP node 5 — the D10 COMBINED READ",
        "",
        f"_generated {r['generated_at']}_ · `best_alpha = 0` · **DEPLOY-HELD, nothing published**",
        "",
        f"## Verdict: **{r['combined_verdict']}**",
        "",
        r["why_combined"],
        "",
        "## 1. The board this read is valid FOR",
        "",
        "⭐ " + s["binds_to"],
        "",
        "| component | value |", "|---|---|",
        f"| season | {s['season']} |",
        f"| projection lineage | `{s['projection_source']}` |",
        f"| board rows | {s['n_players']} ({s['n_rookie_rows']} rookie) |",
        f"| injury-games cap | `{ig.get('status')}` / `{ig.get('injury_games_model_version')}` |",
        f"| adopted reported-absence overrides | **{s['reported_absence_count']}** |",
        f"| rookie policy | `{(s.get('rookie_policy') or {}).get('rookie_selection_status')}` |",
        f"| veteran level | `{(s.get('veteran_level_policy') or {}).get('status')}` |",
        "",
        "## 2. Placement — whole-board, cross-position, on the PUBLISH CANDIDATE",
        "",
        f"**{pl['verdict']}** · gates `{pl['gates']}`",
        "",
        f"Read from `{pl['source']}` ({pl['source_kind']}); configs read: "
        f"{len(pl['configs_read'])}, absent: {pl['configs_absent'] or 'none'}.",
        "",
        "⚠️ This is NOT the S3 baseline the NF-INJ3b ship path ran. That one reads the board as "
        "currently PUBLISHED and structurally cannot see a change that has not shipped; this one "
        "reads the board that WOULD ship.",
        "",
        "## 3. Interval re-validation",
        "",
        f"**{'✅ ALL FLOORS MET' if iv['all_floors_met'] else '🔴 FLOOR BREACH'}** "
        f"(exit {iv['exit_code']}). {iv['why_it_gates']}",
        "",
        "| population | form | n | pooled coverage |", "|---|---|---|---|",
    ] + [
        f"| {p} | {b.get('form')} | {b.get('n')} | {b.get('pooled_coverage')} |"
        for p, b in iv["blocks"].items()
    ] + [
        "",
        f"Written to `{iv['written_to']}` via this story's own `--out` stem. Decided artifacts "
        f"verified byte-identical across BOTH legs: `{r['decided_artifacts_intact']}`.",
        "",
        "## 4. What is still the OPERATOR's",
        "",
        "The ship/hold call. This read gates the first publish; it does not take it. Nothing here "
        "wrote to S3 and this runner has no `--publish` flag.",
        "",
    ]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3b-SHIP node 5: the D10 combined read")
    ap.add_argument("--staged", required=True,
                    help="the STAGED export directory (export_draft_board_json --out ...), i.e. the "
                         "board that would publish. ⛔ Not an S3 read: that is the board already "
                         "published, which cannot show a change that has not shipped.")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--artifacts",
                    default="quant_sports_intel_models/football/nfl/fantasy/artifacts")
    ap.add_argument("--out", default="nf_inj3b_ship_combined_read")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    rep = run(pathlib.Path(args.staged), args.duckdb, pathlib.Path(args.artifacts))
    _ART.mkdir(parents=True, exist_ok=True)
    (_ART / f"{args.out}.json").write_text(json.dumps(rep, indent=2, default=str))
    (_ART / f"{args.out}.md").write_text(_md(rep))
    print(f"NF-INJ3b-SHIP combined read — {rep['combined_verdict']}")
    print(f"  placement: {rep['placement']['verdict']} {rep['placement']['gates']}")
    print(f"  interval : all floors met = {rep['interval']['all_floors_met']}")
    print(f"  board    : {rep['publish_state']['n_players']} rows, "
          f"{rep['publish_state']['reported_absence_count']} adopted overrides, "
          f"injury cap {(rep['publish_state'].get('injury_games_policy') or {}).get('status')}")
    print(f"  decided artifacts intact: {rep['decided_artifacts_intact']}")
    print(f"  wrote {args.out}.json")
    return 0 if rep["combined_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
