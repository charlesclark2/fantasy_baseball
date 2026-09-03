"""run_nf_inj2c_dominance_baseline.py — NF-INJ2c node 3b: the capture-pinned give-back re-measure.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2c_dominance_baseline \
        --capture            # ONCE, at study start — stamps the published board
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2c_dominance_baseline

⛔ THIS SCORES NO ARM AGAINST A REALIZED OUTCOME. It reads the CURRENT SERVED BOARD and measures the
board-level dominance inputs M2/M3/M4 of `nf_inj2c_margin_construction_rule.md` on it. It computes no
CV gate and reaches no verdict.

WHY IT EXISTS (PM re-scope ruling 3, verbatim): "the 82.70% -> 27.85% figures rode a board whose pin
failed at 40.58/797 rows. Capture-pin a fresh board + market snapshot (the D3 convention) and
re-measure the give-back and the coherence table on it BEFORE the prereg quotes any number. If the
re-measured dominance no longer holds on any dimension, that is a NULL, not a margin to adjust."

⭐ THE D3 CONVENTION, OPERATIONALISED — the half NF-INJ2b did not have. A reproduction pin over a
LIVE-SNAPSHOT-fed surface must bind an artifact CAPTURED AT STUDY START, never a re-pull:
`run_season_projection --market-refresh` pulls an ADP/ECR consensus that FEEDS THE ORDERING and moves
intraday, so a board re-pulled later is a different board and the pin fails for a reason that is a
property of the chain rather than of any arm. `--capture` stamps the staged artifact ONCE
(sha256 + captured_at + its own `generated_at`) into `nf_inj2c_capture.json`; every later run
ASSERTS the staged bytes still match that stamp and REFUSES if they moved. So "we pinned against the
capture" is a checkable fact rather than a claim about what somebody did first.

⛔ THE MARGINS ARE NOT SET HERE. `nf_inj2c_margin_construction_rule.md` (node 3a) was committed BEFORE
this runs, precisely so the numbers below cannot shape them. This module READS that rule's TIE BANDS
and applies them; it defines none. A band appearing here that is not in the rule is a defect.

🚦 OPERATOR RUN (>2 min: it rebuilds one full 2026 board per arm). `best_alpha = 0`; nothing serves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB  # noqa: E402,E501

log = logging.getLogger("nfl.fantasy.nf_inj2c_baseline")

_STEM = "nf_inj2c_dominance_baseline"
_REPORT_DIR = RB._REPORT_DIR
_BASELINE_DIR = RB._ART / "nf_inj2b_baseline"
_SERVED_JSON = _BASELINE_DIR / "served_projections_2026.json"
_CAPTURE_STAMP = _BASELINE_DIR / "nf_inj2c_capture.json"

#: the arms this node builds. `incumbent` + `stratified` are the dominance PAIR; `mvp1_null` is the
#: attribution CONTROL M2 requires and is therefore not optional; the rest populate the DISCLOSED
#: residual table PM ruling 2 asks for ("coherence is MEASURED AND REPORTED, both residual
#: populations"). ⛔ This arm list is NOT the declared FIELD — the field is a pre-registration act
#: and is not settled by this module.
BASELINE_ARMS: tuple[str, ...] = (
    "mvp1_null", "incumbent", "stratified", "feasibility_clamp",
    "points_rate_permute", "rate_refit", "points_rate_stratified", "rate_refit_stratified",
)

#: the served board's MANIFEST, staged beside `projections.json`. It carries `adp_as_of` /
#: `ecr_as_of` — the board's OWN statement of which market vintage produced it, at DAY
#: granularity, which is the only granularity it publishes.
_MANIFEST_JSON = _BASELINE_DIR / "manifest.json"

#: ⭐ THE MARKET PRECONDITION (PM ruling 2026-09-01 (a)). One entry per market input the ordering
#: reads, with the command that refreshes THAT input — a refusal that does not name its own remedy
#: is the reason this exists at all.
_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("adp", "adp_as_of",
     "uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_adp_ingest "
     "--from 2026 --to 2026 --refresh"),
    ("ecr", "ecr_as_of",
     "uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_ecr_ingest "
     "--from 2026 --to 2026 --refresh"),
)

#: the STAGING command, quoted in every refusal so an operator never has to go and find it.
_STAGE_CMD = (
    "aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/projections.json "
    f"{_SERVED_JSON} --region us-east-1")
#: the manifest is staged BESIDE the board and carries the vintage the precondition checks against.
_MANIFEST_CMD = (
    "aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/manifest.json "
    f"{_MANIFEST_JSON} --region us-east-1")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-INJ2c D3 — THE FULL VINTAGE SURFACE, TABLE-DRIVEN OVER WHAT THE MANIFEST PUBLISHES
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The day-granularity market check above caught run 1 (ECR six days stale). It could not catch
# run 3 (the DuckDB marts two days stale -> 644 rows of wrong `proj_games`) or run 4 (the NF1.5
# feature pool missing 5 registered columns), because neither input is a market input. Both were
# found only AFTER a full build, which is exactly the expensive VOID the precondition exists to
# convert into a cheap refusal.
#
# ⭐ TABLE-DRIVEN, not enumerated: the input-vintage leg iterates over whatever keys the SERVED
# manifest publishes under `freshness.input_vintage`, and the board stamps that block from
# `run_nf1_5._VINTAGE_READS`. So a future input added to that table is published by the board AND
# checked here with no edit to this file and no new ruling.
#
#: served `freshness.adp` key -> the local FFC cache's own meta key. The ADP WINDOW is a finer
#: fingerprint than `as_of`: a re-pull inside the same day that moved the window or the draft count
#: is a different consensus wearing the same date.
_ADP_WINDOW_FIELDS: tuple[tuple[str, str], ...] = (
    ("window_start", "start_date"), ("window_end", "end_date"), ("drafts", "total_drafts"),
)
#: served `freshness.ecr` key -> the local FantasyPros cache's own key. The EXPERT COUNT moves
#: whenever the consensus is recomputed, so it separates two same-day pulls the date cannot.
_ECR_FINGERPRINT_FIELDS: tuple[tuple[str, str], ...] = (("experts", "total_experts"),)


def _served_freshness() -> dict:
    if not _MANIFEST_JSON.exists():
        raise SystemExit(
            f"the served MANIFEST is not staged at {_MANIFEST_JSON} — it carries the vintages the "
            f"precondition checks against. Stage it:\n  {_MANIFEST_CMD}")
    return dict(json.loads(_MANIFEST_JSON.read_text()).get("freshness") or {})


def _local_market_caches(fresh: dict, season: int) -> dict:
    """The raw local ADP/ECR cache payloads, addressed by the SERVED manifest's own descriptors.

    Deriving the filenames from the manifest (format/teams/scoring) rather than hardcoding them
    means we always read the cache the BOARD's own configuration names."""
    adp, ecr = dict(fresh.get("adp") or {}), dict(fresh.get("ecr") or {})
    out: dict[str, dict | None] = {"adp": None, "ecr": None}
    a = RB._ART / "adp_cache" / f"ffc_{adp.get('format')}_{adp.get('teams')}_{season}.json"
    e = RB._ART / "ecr_cache" / f"fp_ecr_{ecr.get('scoring')}_{season}.json"
    if a.exists():
        try:
            out["adp"] = dict(json.loads(a.read_text()).get("meta") or {})
        except Exception:                                    # noqa: BLE001 - unreadable != current
            out["adp"] = None
    if e.exists():
        try:
            out["ecr"] = json.loads(e.read_text())
        except Exception:                                    # noqa: BLE001
            out["ecr"] = None
    return out


def market_fingerprint(season: int = 2026) -> dict:
    """The finer-than-a-day market surface: the ADP window, the ECR expert count, ECR recency."""
    fresh = _served_freshness()
    local = _local_market_caches(fresh, season)
    served_adp, served_ecr = dict(fresh.get("adp") or {}), dict(fresh.get("ecr") or {})
    out: dict = {"adp": {}, "ecr": {}}
    for served_key, local_key in _ADP_WINDOW_FIELDS:
        out["adp"][served_key] = {
            "served": served_adp.get(served_key),
            "local": (local["adp"] or {}).get(local_key) if local["adp"] is not None else None,
        }
    for served_key, local_key in _ECR_FINGERPRINT_FIELDS:
        out["ecr"][served_key] = {
            "served": served_ecr.get(served_key),
            "local": (local["ecr"] or {}).get(local_key) if local["ecr"] is not None else None,
        }
    out["ecr"]["last_updated_ts"] = {
        "local": (local["ecr"] or {}).get("last_updated_ts") if local["ecr"] is not None else None,
        "board_generated_at": json.loads(_MANIFEST_JSON.read_text()).get("generated_at"),
    }
    return out


def input_vintage(con, season: int = 2026, schema: str = N15.MARTS_SCHEMA) -> dict:
    """The SERVED board's `freshness.input_vintage` block beside the LOCAL marts', key by key.

    ⭐ TABLE-DRIVEN over the manifest's published keys — see the block comment above."""
    served = dict(_served_freshness().get("input_vintage") or {})
    local = N15.read_input_vintage(con, season, schema) if con is not None else {}
    return {k: {"served": served.get(k), "local": local.get(k)} for k in served}


def _input_vintage_remedy() -> str:
    return ("rebuild the marts from the lake INTO THE DATABASE THE BUILD READS — an unset\n"
            "      SPORTS_DUCKDB_PATH silently builds a parallel database and exits 0:\n"
            "        export SPORTS_DUCKDB_PATH=\"$PWD/quant_sports_intel_models/sports_dbt/"
            "sports.duckdb\"\n"
            "        uv run python -m dbt.cli.main run --select nfl.staging --threads 1 \\\n"
            "          --project-dir quant_sports_intel_models/sports_dbt "
            "--profiles-dir quant_sports_intel_models/sports_dbt\n"
            "        uv run python -m dbt.cli.main run --select nfl.marts \\\n"
            "          --project-dir quant_sports_intel_models/sports_dbt "
            "--profiles-dir quant_sports_intel_models/sports_dbt")


def _fingerprint_problems(season: int) -> list[str]:
    fp = market_fingerprint(season)
    probs: list[str] = []
    for name, cmd in ((n, c) for n, _k, c in _MARKET_INPUTS):
        for key, got in fp.get(name, {}).items():
            if key == "last_updated_ts":
                continue
            served, mine = got.get("served"), got.get("local")
            if served is None:
                continue                       # the manifest does not publish it -> nothing to bind
            if mine is None:
                probs.append(f"  · {name.upper()}.{key}: served {served}, LOCAL CACHE UNREADABLE "
                             f"OR ABSENT — an unevaluable check is never a pass.\n      {cmd}")
            elif str(mine) != str(served):
                probs.append(f"  · {name.upper()}.{key}: served {served}, local {mine} — "
                             f"MISMATCHED (same DAY, different consensus).\n      {cmd}")
    # ECR recency is ONE-SIDED by necessity: the manifest publishes no `last_updated_ts`, so there
    # is no served twin to equate. What IS checkable, and sound, is that the local consensus was
    # published BEFORE the board was built — a consensus stamped after it cannot be the one it read.
    rec = fp.get("ecr", {}).get("last_updated_ts", {})
    ts, built = rec.get("local"), rec.get("board_generated_at")
    if ts is not None and built:
        try:
            when = datetime.fromtimestamp(int(ts), timezone.utc)
            board = datetime.fromisoformat(str(built))
            if when > board:
                probs.append(
                    f"  · ECR.last_updated_ts: the local consensus was published {when.isoformat()},"
                    f" AFTER the board was built ({board.isoformat()}) — it cannot be the one the "
                    f"board read.\n      re-stage the board + manifest, then re-capture:"
                    f"\n      {_STAGE_CMD}")
        except Exception:                                    # noqa: BLE001
            probs.append("  · ECR.last_updated_ts: unreadable — an unevaluable check is never a "
                         "pass. Re-stage the manifest:\n      " + _MANIFEST_CMD)
    return probs


def _input_vintage_problems(con, season: int, schema: str) -> list[str]:
    served_block = dict(_served_freshness().get("input_vintage") or {})
    if not served_block:
        return []                              # nothing published -> nothing to bind (not a pass)
    if con is None:
        return ["  · INPUT_VINTAGE: no marts connection was supplied, so the board's "
                f"{len(served_block)} published input vintage(s) COULD NOT BE CHECKED — and an "
                "unevaluable check is never a pass (NF1.7(a)). Pass --duckdb."]
    probs: list[str] = []
    for key, got in input_vintage(con, season, schema).items():
        served, mine = got.get("served"), got.get("local")
        if mine is None:
            probs.append(f"  · {key}: served {served}, LOCAL MART UNREADABLE OR ABSENT.\n      "
                         + _input_vintage_remedy())
        elif str(mine).strip() != str(served).strip():
            probs.append(f"  · {key}: served {served}, local {mine} — MISMATCHED.\n      "
                         + _input_vintage_remedy())
    return probs


# ── the margin rule's TIE BANDS, READ not defined (node 3a owns them) ──────────────────────────
#: M3 — `times_over` is recorded at 2 decimals, so its band is that precision (rule R2).
M3_TIE_BAND = 0.01
#: M4 — `giveback_pct` is recorded at 2 decimals (rule R2).
M4_TIE_BAND = 0.01


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def market_vintage(season: int = 2026) -> dict:
    """The SERVED board's market vintage beside the LOCAL caches', per input, at day granularity.

    ⭐ WHY THIS EXISTS — NF-INJ2c node 3b run 1, and NF-INJ2b before it. `apply_2026` builds every
    arm with `market_refresh=False` (correct: that is how an archived run reproduces byte-for-byte),
    so the ordering reads whatever ADP/ECR caches are ON DISK. `nf1_3_model` builds its ordering
    feature as `market_rank = ecr.where(ecr.notna(), adp)` — ECR-PRIMARY — and `market_rank` is a
    feature at ALL FOUR positions. So a local cache from a different day than the served board
    produces a DIFFERENT WITHIN-POSITION ORDERING, and the pin fails for a reason that is a property
    of the chain rather than of any arm.

    Measured on run 1: ADP matched exactly (same window, same 8,161 drafts) while ECR was SIX DAYS
    stale (8/25 against the board's 8/31); the largest ECR mover in that gap (Josh Jacobs, rank
    43 -> 145 over final cuts) was the largest point mover, at exactly the 84.72 that failed the pin.

    ⚠️ DAY GRANULARITY is not a simplification, it is the bar the manifest actually publishes
    (`adp_as_of` / `ecr_as_of` are dates). ⛔ Do not invent a finer-grained field that does not
    exist."""
    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF

    if not _MANIFEST_JSON.exists():
        raise SystemExit(
            f"the served MANIFEST is not staged at {_MANIFEST_JSON} — it carries the board's own "
            "`adp_as_of`/`ecr_as_of`, which is what the market precondition checks against. "
            f"Stage it:\n  {_MANIFEST_CMD}")
    served = json.loads(_MANIFEST_JSON.read_text())
    local = MF.market_as_of(season)
    out = {}
    for name, manifest_key, _cmd in _MARKET_INPUTS:
        out[name] = {
            "served_as_of": served.get(manifest_key),
            "local_as_of": (local.get(name) or {}).get("as_of"),
            "local_label": (local.get(name) or {}).get("label"),
        }
    return out


def assert_market_vintage_matches(season: int = 2026) -> dict:
    """REFUSE unless every market input's LOCAL cache is the same DAY as the SERVED board's.

    ⛔ Refuses rather than warns, and refuses on an UNREADABLE vintage too — a check that cannot be
    evaluated is never scored as a pass (NF1.7 (a)). The message names the mismatched input, BOTH
    vintages, and the command that fixes it: converting an expensive VOID into a cheap up-front
    refusal is the entire point, and a refusal that does not carry its own remedy has not converted
    anything."""
    v = market_vintage(season)
    problems = []
    for name, _key, cmd in _MARKET_INPUTS:
        got = v[name]
        served, mine = got["served_as_of"], got["local_as_of"]
        if served is None:
            problems.append(
                f"  · {name.upper()}: the served manifest carries no vintage for it, so the "
                f"precondition CANNOT be evaluated — and an unevaluable check is never a pass. "
                f"Re-stage the manifest:\n      {_MANIFEST_CMD}")
        elif mine is None:
            problems.append(
                f"  · {name.upper()}: served {served}, LOCAL CACHE UNREADABLE OR ABSENT. Refresh "
                f"it, then re-capture:\n      {cmd}")
        elif str(mine) != str(served):
            problems.append(
                f"  · {name.upper()}: served {served}, local {mine}"
                f"{' (label ' + str(got['local_label']) + ')' if got.get('local_label') else ''}"
                f" — MISMATCHED. Refresh it, then re-capture:\n      {cmd}")
    if problems:
        raise SystemExit(
            "⛔ MARKET VINTAGE MISMATCH — refusing before the arms are built.\n\n"
            + "\n".join(problems)
            + "\n\nWHY: `apply_2026` builds every arm with `market_refresh=False`, so the ordering "
              "reads the ON-DISK caches. `market_rank` is ECR-primary and is a feature at all four "
              "positions, so a cache from a different day than the served board produces a "
              "different within-position ordering and the pin cannot hold. On NF-INJ2c run 1 that "
              "cost a full VOID run at a worst difference of 84.72.\n"
              "⚠️ A vendor snapshot is NOT recoverable once its day rolls — FantasyPros serves only "
              "the current one and the lake's ecr_benchmark asset is season-partitioned and "
              "overwritten. If the served board's vintage has already passed, ⛔ do NOT chase it: "
              "wait for the next publish, refresh the caches promptly after it, and capture then.")
    return v


def assert_vintages_match(con=None, season: int = 2026,
                          schema: str = N15.MARTS_SCHEMA) -> dict:
    """REFUSE unless EVERY vintage the served manifest publishes matches this checkout's.

    D3 (PM ruling, 2026-09-03). The market DAY check alone caught NF-INJ2c run 1 and was blind to
    runs 3 and 4 — the marts two days stale, and the feature pool missing 5 registered columns.
    Both were found only after a full build. This is the same refusal, widened to the whole
    surface the manifest exposes and driven by that manifest rather than by a list here.

    Every refusal names the mismatched INPUT, BOTH vintages, and the FIX — a refusal that does not
    carry its own remedy has not converted an expensive VOID into a cheap stop."""
    market = assert_market_vintage_matches(season)          # the day check; raises on its own
    problems = _fingerprint_problems(season) + _input_vintage_problems(con, season, schema)
    if problems:
        raise SystemExit(
            "⛔ INPUT VINTAGE MISMATCH — refusing before the arms are built.\n\n"
            + "\n".join(problems)
            + "\n\nWHY: the reproduction pin compares this checkout's rebuild against the board "
              "that was actually SERVED. Any input at a different vintage than the board's makes "
              "the comparison a measurement of the gap between two checkouts rather than of any "
              "arm. NF-INJ2c spent three VOID runs (84.72 -> 18.95 -> 5.64 -> 1.82) discovering "
              "these one at a time, each only after a full build.")
    return {"market": market, "fingerprint": market_fingerprint(season),
            "input_vintage": input_vintage(con, season, schema) if con is not None else {}}


def capture(force: bool = False, con=None, season: int = 2026,
            schema: str = N15.MARTS_SCHEMA) -> dict:
    """Stamp the staged published board ONCE, at study start (the D3 convention)."""
    if not _SERVED_JSON.exists():
        raise SystemExit(f"nothing staged at {_SERVED_JSON} — stage it first:\n  {_STAGE_CMD}")
    if _CAPTURE_STAMP.exists() and not force:
        raise SystemExit(
            f"a capture already exists at {_CAPTURE_STAMP}. ⛔ Re-capturing MID-STUDY is exactly "
            "what the D3 convention forbids — the pin would then bind a board captured AFTER the "
            "arms were measured. Pass --recapture ONLY to start the study over.")
    # ⭐ THE MARKET PRECONDITION, enforced HERE — before anything is stamped and long before the
    # >2-min arm build. A capture taken against caches of the wrong vintage is a capture that
    # cannot be pinned, so refusing at capture time is what converts a VOID run into a cheap no.
    vintage = assert_vintages_match(con, season, schema)
    doc = json.loads(_SERVED_JSON.read_text())
    stamp = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(_SERVED_JSON),
        "served_generated_at": doc.get("generated_at"),
        "n_players": len(doc.get("players") or []),
        "source": str(_SERVED_JSON),
        "market_vintage": vintage,
        "convention": ("D3 — a reproduction pin over a live-snapshot-fed surface binds a CAPTURED "
                       "artifact, never a re-pull; --market-refresh moves the ADP/ECR consensus "
                       "that feeds the ordering, so a later pull is a different board. The MARKET "
                       "VINTAGE is recorded here and re-checked on every run, because the board's "
                       "bytes matching is not sufficient — the ORDERING is built from the on-disk "
                       "ADP/ECR caches, which move independently of it."),
    }
    _CAPTURE_STAMP.write_text(json.dumps(stamp, indent=2))
    log.info("captured the published board: generated_at=%s sha256=%s...",
             stamp["served_generated_at"], stamp["sha256"][:12])
    return stamp


def assert_capture_intact(con=None, season: int = 2026,
                          schema: str = N15.MARTS_SCHEMA) -> dict:
    """The staged bytes must still be the ones the capture stamped. REFUSES, never warns."""
    if not _CAPTURE_STAMP.exists():
        raise SystemExit(
            f"no capture stamp at {_CAPTURE_STAMP} — the D3 convention requires the published board "
            "to be CAPTURED AT STUDY START and pinned against that capture. Stage it and capture:\n"
            f"  {_STAGE_CMD}\n"
            "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
            "run_nf_inj2c_dominance_baseline --capture")
    stamp = json.loads(_CAPTURE_STAMP.read_text())
    if not _SERVED_JSON.exists():
        raise SystemExit(f"the captured board is gone from {_SERVED_JSON}; re-stage:\n  {_STAGE_CMD}")
    now = _sha256(_SERVED_JSON)
    if now != stamp.get("sha256"):
        raise SystemExit(
            f"the staged board has CHANGED since it was captured "
            f"(sha256 {stamp.get('sha256','?')[:12]}... -> {now[:12]}...). A pin against a re-pull "
            "is the exact failure D3 names — NF-INJ2b's freshness bar PASSED at 7.30h while its pin "
            "FAILED at 40.58 over 797 rows, because the ADP/ECR snapshot feeding the ordering moves "
            "intraday. Either restore the captured bytes or start the study over with --recapture.")
    # ⭐ RE-CHECKED AT RUN TIME, not only at capture: the caches are ordinary files that a later
    # refresh can move underneath a valid capture. The board's bytes matching does not constrain
    # them, so an unchanged sha256 is NOT evidence the ordering inputs are unchanged.
    now_vintage = assert_vintages_match(con, season, schema)
    captured_vintage = stamp.get("market_vintage")
    if captured_vintage and captured_vintage != now_vintage:
        raise SystemExit(
            "⛔ THE MARKET CACHES MOVED SINCE THE CAPTURE — the arms would be built from inputs the "
            f"capture did not stamp.\n  at capture: {json.dumps(captured_vintage)}\n  now:        "
            f"{json.dumps(now_vintage)}\nRestore the captured vintage, or start the study over "
            "with --recapture (which re-checks the precondition).")
    return stamp


def _giveback_measure(pct) -> float | None:
    """M4 = `max(give_back_pct, 0)` — declared in the margin rule §3(a) BEFORE this ran.

    The defect NF-INJ1 named is injured players marked back UP, i.e. a POSITIVE give-back. Scoring
    the signed value would let an arm bank credit for OVER-discounting, which is a different defect
    wearing this measure's clothes. The signed figure is reported beside it, always."""
    return None if pct is None else max(float(pct), 0.0)


def _worst_times_over(rec: dict) -> float | None:
    w = [v["implied_per_game"] / v["max_ever_per_game"]
         for v in rec.get("worst_violations") or []
         if v.get("max_ever_per_game") and v.get("implied_per_game") is not None]
    return round(max(w), 4) if w else None


def dominance_table(app: dict) -> dict:
    """M2 / M3 / M4 for every built arm, against the SERVED incumbent, through the node-3a bands."""
    arms = app["arms"]
    inc = arms.get("incumbent")
    if inc is None:
        raise SystemExit("the incumbent was not built — there is no baseline to dominate against")
    base = {
        "M2_violations_attributable": inc["coherence_violating_players_attributable"],
        "M3_worst_times_over": _worst_times_over(inc),
        "M4_giveback_measure": _giveback_measure(inc["injury_giveback"].get("giveback_pct")),
        "M4_giveback_signed": inc["injury_giveback"].get("giveback_pct"),
    }
    out: dict = {
        "served_incumbent_baseline": base,
        "bands": {
            "M2": ("SE of the per-fold PAIRED difference — a FOLD quantity computed by the decisive "
                   "run, ⛔ not on a single board; the board figure here is the BASELINE the "
                   "pre-registration quotes"),
            "M3": M3_TIE_BAND, "M4": M4_TIE_BAND,
            "source": "nf_inj2c_margin_construction_rule.md (node 3a), committed before this ran",
        },
        "arms": {},
    }
    for arm, rec in arms.items():
        gb = rec["injury_giveback"]
        m2 = rec["coherence_violating_players_attributable"]
        m3, m4 = _worst_times_over(rec), _giveback_measure(gb.get("giveback_pct"))
        row = {
            "M2_violations_attributable": m2,
            "M2_delta_vs_incumbent": m2 - base["M2_violations_attributable"],
            "M3_worst_times_over": m3,
            "M4_giveback_measure": m4,
            "M4_giveback_signed": gb.get("giveback_pct"),
            "coherence_violating_players_raw": rec["coherence_violating_players"],
            "coherence_by_position": rec["coherence_by_position"],
            "clamp_hi": rec["clamp_saturation_high"], "clamp_lo": rec["clamp_saturation_low"],
        }
        for key, mine, theirs, band in (("M3", m3, base["M3_worst_times_over"], M3_TIE_BAND),
                                        ("M4", m4, base["M4_giveback_measure"], M4_TIE_BAND)):
            if mine is None or theirs is None:
                row[f"{key}_verdict"] = "UNEVALUABLE"   # ⛔ never scored as a pass (NF1.7 (a))
                continue
            d = theirs - mine                            # both measures: LOWER is better
            row[f"{key}_verdict"] = ("IMPROVES" if d > band else
                                     "REGRESSES" if d < -band else "TIES")
        row["M2_verdict"] = ("IMPROVES" if row["M2_delta_vs_incumbent"] < 0 else
                             "REGRESSES" if row["M2_delta_vs_incumbent"] > 0 else "TIES")
        row["M1_M5_M6"] = "UNEVALUATED HERE — fold measures, owned by the decisive run (node 4)"
        out["arms"][arm] = row
    return out


def write_md(rep: dict, path: Path) -> None:
    app, dom = rep["application_2026"], rep["dominance"]
    cap, pin = rep["capture"], app.get("reproduction_pin") or {}
    fresh = app.get("baseline_freshness") or {}
    L = ["# NF-INJ2c node 3b — the capture-pinned dominance baseline", "",
         "> ⛔ A BOARD MEASUREMENT, not a bake-off: no arm is scored against a realized outcome and "
         "no CV gate is computed here. The fold measures M1/M5/M6 belong to the decisive run.", "",
         f"Generated {rep['generated_at']}. PM re-scope ruling 3.", "",
         "## 1. The capture (D3 — pinned against a CAPTURED artifact, never a re-pull)", "",
         "| field | value |", "|---|---|",
         f"| captured_at | {cap['captured_at']} |",
         f"| served `generated_at` | {cap['served_generated_at']} |",
         f"| sha256 | `{cap['sha256'][:16]}...` |",
         f"| players | {cap['n_players']} |",
         f"| local MVP-1 `generated_at` | {app.get('board_generated_at')} |",
         f"| lag vs served | {fresh.get('lag_hours')}h (bar {fresh.get('max_lag_hours')}h) |", "",
         f"**Reproduction pin:** worst absolute difference **{pin.get('worst_abs_diff')}** over "
         f"{pin.get('n')} rows against a tolerance of {pin.get('tolerance')} ⇒ "
         f"**{pin.get('reproduces')}**.", ""]
    if not pin.get("reproduces", False):
        L += ["> ⛔ **THE PIN DOES NOT HOLD, so this run is VOID — not a null** (margin rule §5 "
              "branch 3). A dominance claim against a board nobody is served is not a measurement.",
              ""]
    L += ["## 2. The board-level dominance measures, against the SERVED incumbent", "",
          "Bands are READ from `nf_inj2c_margin_construction_rule.md` (node 3a, committed BEFORE "
          "this ran); ⛔ none is defined here.", "",
          "| arm | M2 attributable viol. | Δ vs inc | M2 | M3 worst × | M3 | M4 give-back "
          "(measure) | M4 signed | M4 | clamp hi/lo |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for arm, r in dom["arms"].items():
        L.append(f"| `{arm}` | {r['M2_violations_attributable']} | "
                 f"{r['M2_delta_vs_incumbent']:+d} | {r['M2_verdict']} | "
                 f"{r['M3_worst_times_over']} | {r['M3_verdict']} | {r['M4_giveback_measure']} | "
                 f"{r['M4_giveback_signed']} | {r['M4_verdict']} | {r['clamp_hi']}/{r['clamp_lo']} |")
    L += ["", "⭐ **M4 is `max(give_back_pct, 0)`** — declared in the margin rule §3(a) before this "
              "ran, because the defect NF-INJ1 named is injured players marked back UP; the SIGNED "
              "figure is reported beside it always.", "",
          f"⭐ **ATTRIBUTION BY CONTROL:** {app.get('attribution_control')}", "",
          "⚠️ M1 (CRPS), M5 (per-position ordering) and M6 (interval floors) are FOLD measures and "
          "are UNEVALUATED here — named rather than silently omitted, because a dominance table "
          "missing three of its six measures must not read as a complete one (NF1.7 (a)).", ""]
    path.write_text("\n".join(L) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ2c node 3b — capture-pinned dominance baseline")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=N15.MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--capture", action="store_true",
                    help="stamp the staged published board ONCE, at study start (D3)")
    ap.add_argument("--recapture", action="store_true",
                    help="start the study over — overwrites an existing capture stamp")
    ap.add_argument("--arms", default=None, help="comma-separated; default = BASELINE_ARMS")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("nfl").setLevel(logging.INFO)

    # D3: the marts connection is opened BEFORE the capture branch, because the vintage
    # precondition now binds the board's `freshness.input_vintage` block against THIS checkout's
    # marts — and a check that cannot be evaluated is never a pass (NF1.7(a)).
    import duckdb
    if not Path(args.duckdb).is_absolute() and not Path(args.duckdb).exists():
        cand = _PROJECT_ROOT / args.duckdb
        if cand.exists():
            args.duckdb = str(cand)
    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — a fresh worktree does not carry the "
                         "gitignored artifact (NF-INFRA1); pass --duckdb with an absolute path.")
    con = duckdb.connect(args.duckdb, read_only=True)

    if args.capture or args.recapture:
        capture(force=args.recapture, con=con, schema=args.schema)
        return 0
    stamp = assert_capture_intact(con, schema=args.schema)
    selections = N15.load_selection(json.loads(RB._NF1_5_REPORT.read_text()),
                                    board="beats-incumbent")
    arms = (tuple(a.strip() for a in args.arms.split(",")) if args.arms else BASELINE_ARMS)
    if "incumbent" not in arms or "mvp1_null" not in arms:
        raise SystemExit("`incumbent` (the dominance baseline) and `mvp1_null` (M2's attribution "
                         "control) are not optional — refusing a run that could not compute M2")

    app = RB.apply_2026(con, args.schema, selections, arms, base_from=args.base_from,
                        served_json=_SERVED_JSON)
    rep = {
        "story": "NF-INJ2c node 3b — capture-pinned dominance baseline (PM re-scope ruling 3)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0,
        "capture": stamp,
        "arms": list(arms),
        "application_2026": app,
        "dominance": dominance_table(app),
    }
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{_STEM}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_md(rep, _REPORT_DIR / f"{_STEM}.md")
    pin = app.get("reproduction_pin") or {}
    if not pin.get("reproduces", False):
        log.error("[ALERT] THE REPRODUCTION PIN DOES NOT HOLD (worst %s over %s rows vs %s) — this "
                  "run is VOID, not a null (margin rule §5 branch 3)",
                  pin.get("worst_abs_diff"), pin.get("n"), pin.get("tolerance"))
        return 2
    log.info("node 3b complete — pin holds; dominance table written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
