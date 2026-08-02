"""design_block.py — MH2.3: a small, REQUIRED, machine-readable design block for every
`ablation_results` bake-off report.

WHY THIS EXISTS
---------------------------------------------------------------------------------------------------
MH2's mechanical inventory (`betting_ml/scripts/mh2_cv_power.py`) found 46 of 75 markdown reports
state no fold count, PBO or DSR anywhere in their header — a report without its design line cannot
have its null read by anyone, now or later. This module defines the block those reports (and every
new one going forward) should carry, plus the render/parse pair that makes it machine-readable.

WHAT THIS IS DELIBERATELY NOT
---------------------------------------------------------------------------------------------------
Not a re-fit and not a schema forced retroactively onto data that never recorded it. A report whose
design was never captured, or whose generating artifact no longer exists, gets an explicit
`status="unrecoverable"` block with a reason — never a fabricated fold count (readiness lock 2).
A report that was never a bake-off/verdict document at all (a pre-registration, a research spike, an
access probe, a data audit) gets `status="exempt"` — forcing a fold-count field onto a document that
never had a design to record would itself be a fabrication.

FORMAT
---------------------------------------------------------------------------------------------------
A single HTML-comment-delimited JSON object, anchored right after the report's H1 so it never
disturbs the rendered document. JSON (not YAML-ish key:value) because several fields are naturally
nested (`per_metric`) and a single `json.loads` is a more robust parse than a hand-rolled line
scanner — see `mh2_cv_power.py`'s legacy `_MD_ARMS`/`_MD_VERDICT` regexes for what happens when the
parser has to guess at prose.

    <!-- MH2-DESIGN-BLOCK
    {"schema": 1, "status": "recorded", "fold_rule": "...", "n_folds": 11, "n_arms": 7,
     "primary_contrast": "paired-t", "verdict": "ADD", "gates": {"pbo": 0.05, "dsr": 0.97},
     "per_metric": [...], "source_artifact": "...", "reason": null}
    -->
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

log = logging.getLogger("mh2.design_block")

SCHEMA_VERSION = 1

BLOCK_OPEN = "<!-- MH2-DESIGN-BLOCK"
BLOCK_CLOSE = "-->"

# status: what kind of claim this block is making.
#   recorded      — the design was captured live by the harness that produced this report.
#   recovered     — backfilled from a stored artifact after the fact (no re-fit); the artifact
#                    that supports it is named in `source_artifact`.
#   exempt        — this report was never a bake-off/verdict document; there is no design to record.
#   unrecoverable — this WAS (or looks like) a bake-off report, but its stored per-fold/per-arm
#                    data no longer exists in the repo; `reason` names what's missing.
STATUSES = ("recorded", "recovered", "exempt", "unrecoverable")

_BLOCK_RE = re.compile(
    re.escape(BLOCK_OPEN) + r"\s*(.*?)\s*" + re.escape(BLOCK_CLOSE), re.DOTALL)


@dataclass
class DesignBlock:
    status: str
    schema: int = SCHEMA_VERSION
    fold_rule: str | None = None
    n_folds: int | None = None
    n_arms: int | None = None
    primary_contrast: str | None = None
    verdict: str | None = None
    gates: dict | None = None
    per_metric: list | None = None
    source_artifact: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown design-block status {self.status!r}, must be one of {STATUSES}")
        if self.status in ("exempt", "unrecoverable") and not self.reason:
            raise ValueError(f"status={self.status!r} requires a `reason` — "
                             f"naming why is the whole point (LOCK 2: never silently opaque)")


def render_design_block(db: DesignBlock) -> str:
    """A single HTML-comment JSON block. `sort_keys` + fixed indent so a re-render of an unchanged
    block is byte-identical (idempotency depends on this — see `insert_design_block`)."""
    body = json.dumps({k: v for k, v in asdict(db).items()}, indent=1, sort_keys=True, default=str)
    return f"{BLOCK_OPEN}\n{body}\n{BLOCK_CLOSE}"


def parse_design_block(text: str) -> DesignBlock | None:
    """Find the FIRST design block in `text` and parse it. Returns None — never raises — on a
    missing or malformed block; a corpus this heterogeneous will have hand-edited or truncated
    files, and a parser that crashes on those makes the whole inventory brittle."""
    m = _BLOCK_RE.search(text)
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        log.warning("design block present but not valid JSON: %s", e)
        return None
    if not isinstance(d, dict) or "status" not in d:
        log.warning("design block JSON missing required `status` key")
        return None
    try:
        return DesignBlock(**{k: v for k, v in d.items() if k in DesignBlock.__dataclass_fields__})
    except (ValueError, TypeError) as e:
        log.warning("design block failed to construct: %s", e)
        return None


def has_design_block(text: str) -> bool:
    return _BLOCK_RE.search(text) is not None


def design_block_from_ladder_results(
    results: dict, fold_rule: str, primary_contrast: str = "paired-t") -> DesignBlock:
    """Build a `status="recorded"` design block straight from the SAME `{metric: Result}` dict a
    milb_mle `write_report()` already has in hand when it renders its markdown — no re-fit, no
    re-derivation. Duck-typed rather than tied to one dataclass: `LadderResult` (E7.12-S1) and
    `H1Result`/`H2Result`/`H3Result`/`H4Result` (E7.15) are independently declared per script but
    all carry `metric`, `leaderboard`, `mae_by_fold`, `fold_cohorts`, `deflation`, `verdict`, and
    the H-series additionally carries a top-level `dsr` dict — readiness lock 3's "extend the
    resolver, don't force one schema retroactively" applied to EMISSION rather than extraction.
    Lives here (not in `h_harness.py`) so `run_e7_12_slice1.py` — which `h_harness` imports FROM —
    can call it without a circular import.
    """
    per_metric = []
    for metric, res in results.items():
        cohorts = getattr(res, "fold_cohorts", None) or []
        n_folds = len(cohorts) or None
        if n_folds is None:
            mae = getattr(res, "mae_by_fold", None)
            n_folds = (len(mae.index) if mae is not None and len(getattr(mae, "index", ())) else None)
        lb = getattr(res, "leaderboard", None)
        n_arms = (int(lb["selectable"].sum())
                 if lb is not None and "selectable" in getattr(lb, "columns", ()) else None)
        defl = getattr(res, "deflation", None) or {}
        dsr_field = getattr(res, "dsr", None)
        if isinstance(dsr_field, dict):
            elig = dsr_field.get("eligible")
            dsr_val = elig.get("dsr") if isinstance(elig, dict) else dsr_field.get("dsr")
        else:
            dsr_val = None
        per_metric.append({
            "metric": metric, "verdict": getattr(res, "verdict", None), "n_folds": n_folds,
            "n_arms": n_arms, "pbo": defl.get("pbo"), "dsr": dsr_val})
    folds = {e["n_folds"] for e in per_metric if e["n_folds"]}
    return DesignBlock(
        status="recorded", fold_rule=fold_rule,
        n_folds=(next(iter(folds)) if len(folds) == 1 else None),
        n_arms=max((e["n_arms"] or 0) for e in per_metric) or None,
        primary_contrast=primary_contrast,
        verdict=", ".join(f"{e['metric']}={e['verdict']}" for e in per_metric),
        per_metric=per_metric)


def design_block_from_comp_validation_report(
    report: dict, *, fold_rule: str, primary_contrast: str,
    use_fold_census: bool, source_artifact: str | None = None) -> DesignBlock:
    """Build a design block from the prospect-comp `fold_census`/`by_type`/`verdict_by_type` report
    dict shared by `run_e7_13_comp_validation.py` and `run_e7_16_pipeline_comps.py` — called BOTH
    live (the in-memory `report` dict right before it's rendered to markdown, `status="recorded"`)
    and by the backfill script reading the same shape back off a stored JSON artifact
    (`status="recovered"`), so the two paths can never drift apart on how this shape is read.
    """
    by_type = (report.get("fold_census", {}).get("by_type") if use_fold_census
              else report.get("by_type")) or {}
    verdict_by_type = report.get("verdict_by_type") or {}
    per_metric = []
    for ptype, info in by_type.items():
        strict = info.get("strictly_matured_folds") or (
            len(info.get("folds") or []) if info.get("strict_maturity") else None)
        relaxed = len(info.get("folds") or []) if not info.get("strict_maturity") else None
        per_metric.append({
            "metric": ptype, "verdict": verdict_by_type.get(ptype, report.get("verdict")),
            "n_folds": strict if info.get("strict_maturity") else (relaxed or strict),
            "n_arms": None})
    n_folds_set = {e["n_folds"] for e in per_metric if e["n_folds"]}
    return DesignBlock(
        status=("recorded" if source_artifact is None else "recovered"),
        fold_rule=fold_rule,
        n_folds=(next(iter(n_folds_set)) if len(n_folds_set) == 1 else None),
        n_arms=len(by_type) or None,
        primary_contrast=(report.get("constraint") or primary_contrast),
        verdict=str(report.get("verdict")), per_metric=per_metric,
        source_artifact=source_artifact)


def design_block_from_source_accuracy_report(
    report: dict, *, fold_rule: str, primary_contrast: str,
    source_artifact: str | None = None) -> DesignBlock:
    """Build a design block from `run_e7_14_source_accuracy.py`'s `org_scope`/`verdict` report
    dict — same live/backfill sharing rationale as `design_block_from_comp_validation_report`."""
    org = report.get("org_scope") or {}
    folds = org.get("folds") or []
    ranking = org.get("rank_ic") or {}
    ruling = ((report.get("verdict") or {}).get("source_rank_head_to_head") or {}).get("ruling")
    return DesignBlock(
        status=("recorded" if source_artifact is None else "recovered"),
        fold_rule=fold_rule, n_folds=len(folds) or None, n_arms=len(ranking) or None,
        primary_contrast=primary_contrast, verdict=(ruling or "").split(" — ")[0] or "NULL",
        gates={"min_detectable_gap_95":
               ((report.get("verdict") or {}).get("source_rank_head_to_head") or {}).get(
                   "min_detectable_gap_95")},
        source_artifact=source_artifact)


def insert_design_block(md_text: str, db: DesignBlock) -> str:
    """Insert (or, if one already exists, REPLACE — idempotent) the design block right after the
    report's first H1 line. Falls back to the top of the file if there is no H1."""
    block = render_design_block(db)
    if has_design_block(md_text):
        return _BLOCK_RE.sub(lambda _m: block, md_text, count=1)
    lines = md_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            new_lines = lines[: i + 1] + ["", block, ""] + lines[i + 1 :]
            return "\n".join(new_lines) + ("\n" if md_text.endswith("\n") else "")
    return block + "\n\n" + md_text
