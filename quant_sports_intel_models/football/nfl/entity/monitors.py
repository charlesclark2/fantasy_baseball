"""monitors.py — NF-W0b: the four §12A monitors, the QA record, and the fail-closed gate.

    unmatched_rate               share of source rows with no canonical id
    low_confidence_rate          share of MATCHED rows at or below the low-confidence bar
    high_value_unmatched_count   unmatched rows whose feature would materially move a projection
    silent_drop_count            source rows that vanished between input and output — MUST be 0

⭐ `silent_drop_count` IS NOT THRESHOLD-GOVERNED. The other three are rates a build may knowingly
tolerate; a silent drop is a category error — a row that entered the pipeline and left no trace,
so nothing downstream can even know to ask about it. Any value > 0 fails closed unconditionally,
and `ResolutionThresholds` deliberately has no knob for it (a configurable "0" is a 0 someone
eventually configures to 1).

⚠️ AN UNEVALUABLE MONITOR IS NOT A PASS (NF1.7 (a)). `evaluate` refuses to report a rate over an
empty population as 0.0 — that is the vacuous-anchor bug, where "no rows" reads identically to
"every row matched". An empty source yields `unmatched_rate=None` and `evaluated=False`, and a
build configured to require evaluation fails closed on it rather than scoring it healthy.

⭐ WHY THE HIGH-VALUE COUNT IS SEPARATE FROM THE RATE. Measured on the live 2024 lake, the
unresolved snap rows are ~0.26% of skill-position rows — a rate any threshold would wave through.
One of them is Michael Woods II at a **100% week-15 snap share**. A rate averages a starter and a
special-teamer into the same number; the high-value count is what makes "an expected starter is
affected" a condition a build can fail closed on, which is exactly what §12A asks for.

THE FALL-BACK-AND-FLAG POLICY (§12A) is `degraded_frame()`: an unmatched high-value feature falls
back to the lower tier, is flagged `source_degraded`, and lands in `qa_records()`. It is never
silently set to zero or silently dropped — `assert_no_silent_zero()` is the mechanical guard that
a consumer has not re-introduced the `coalesce(..., 0.0)` this story exists to remove.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .resolver import LOW_CONFIDENCE_AT_OR_BELOW, METHOD_UNRESOLVED

log = logging.getLogger("nfl.entity.monitors")

__all__ = [
    "DEFAULT_THRESHOLDS",
    "EntityResolutionFailClosed",
    "MonitorReport",
    "ResolutionThresholds",
    "assert_no_silent_zero",
    "degraded_frame",
    "evaluate",
    "qa_records",
]


class EntityResolutionFailClosed(RuntimeError):
    """Raised when a build must not proceed on the identities it managed to resolve."""


@dataclass(frozen=True)
class ResolutionThresholds:
    """Pre-registered fail-closed bars. PRE-REGISTERED is the operative word: these are set from
    the measured baseline BEFORE a build runs, so a build cannot be rescued by relaxing the bar
    that caught it (the E2.1-r post-hoc-reclassification inversion, one domain over).

    Defaults are calibrated on the 2022–2025 lake (see `nf_w0b_entity_resolution.md`):
    skill-position unresolved runs 0.10–0.31% of snap rows once the ladder is applied, so a 2%
    bar is ~6× the worst observed season — loose enough not to fire on normal roster churn,
    tight enough that a bridge REGRESSION (the pre-fix 34% miss) trips it immediately.

    ⚠️ `max_high_value_unmatched` defaults to None = "report, do not gate". A hard 0 would fail
    closed every week that a practice-squad elevation out-runs the roster feed, which is a real
    and recurring condition, not a defect. Set it to an integer for a build that genuinely cannot
    ship a degraded starter; leaving it None still FLAGS every such row and records it in QA.
    """

    max_unmatched_rate: float = 0.02
    max_low_confidence_rate: float = 0.05
    max_high_value_unmatched: int | None = None
    require_evaluated: bool = True


DEFAULT_THRESHOLDS = ResolutionThresholds()


@dataclass
class MonitorReport:
    """The four §12A monitors plus the verdict. `fail_closed` is the decision; `reasons` names
    every clause that fired, so a report says WHICH bar broke rather than only that one did."""

    source_name: str
    n_input_rows: int
    n_output_rows: int
    n_matched: int
    unmatched_rate: float | None
    low_confidence_rate: float | None
    high_value_unmatched_count: int
    silent_drop_count: int
    evaluated: bool
    fail_closed: bool
    reasons: list[str] = field(default_factory=list)
    by_method: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "n_input_rows": self.n_input_rows,
            "n_output_rows": self.n_output_rows,
            "n_matched": self.n_matched,
            "unmatched_rate": self.unmatched_rate,
            "low_confidence_rate": self.low_confidence_rate,
            "high_value_unmatched_count": self.high_value_unmatched_count,
            "silent_drop_count": self.silent_drop_count,
            "evaluated": self.evaluated,
            "fail_closed": self.fail_closed,
            "reasons": list(self.reasons),
            "by_method": dict(self.by_method),
        }


def evaluate(
    resolved: pd.DataFrame,
    *,
    source_name: str,
    n_input_rows: int,
    thresholds: ResolutionThresholds = DEFAULT_THRESHOLDS,
    high_value_mask: pd.Series | None = None,
    low_confidence_at_or_below: float = LOW_CONFIDENCE_AT_OR_BELOW,
) -> MonitorReport:
    """Compute the four monitors over a `resolve()` output and decide the fail-closed verdict.

    `n_input_rows` is passed in rather than inferred, because `silent_drop_count` is precisely the
    gap between what the caller HANDED the resolver and what came back — a number the output frame
    alone cannot know.
    """
    n_out = int(len(resolved))
    silent_drop = max(0, int(n_input_rows) - n_out)

    matched = (
        resolved["canonical_player_id"].notna()
        if "canonical_player_id" in resolved.columns
        else pd.Series(False, index=resolved.index)
    )
    n_matched = int(matched.sum())
    evaluated = n_out > 0

    if evaluated:
        unmatched_rate = float((n_out - n_matched) / n_out)
        if n_matched > 0:
            conf = pd.to_numeric(resolved.loc[matched, "match_confidence"], errors="coerce")
            low_conf_rate = float((conf <= low_confidence_at_or_below).sum() / n_matched)
        else:
            # Every row unmatched: there is no matched population to rate, and reporting 0.0
            # would read as "no low-confidence matches" — the vacuous-anchor shape again.
            low_conf_rate = None
    else:
        unmatched_rate = None
        low_conf_rate = None

    if high_value_mask is not None and n_out:
        hv = high_value_mask.reindex(resolved.index).astype("boolean").fillna(False).astype(bool)
        high_value_unmatched = int((hv & ~matched).sum())
    else:
        high_value_unmatched = 0

    by_method: dict[str, int] = {}
    if "match_method" in resolved.columns and n_out:
        by_method = {str(k): int(v) for k, v in resolved["match_method"].value_counts().items()}

    reasons: list[str] = []
    # (1) silent drops — unconditional, never threshold-governed.
    if silent_drop > 0:
        reasons.append(
            f"silent_drop_count={silent_drop} (must be 0 — {n_input_rows} rows in, {n_out} out)"
        )
    # (2) an unevaluable run is not a passing run.
    if thresholds.require_evaluated and not evaluated:
        reasons.append("unevaluable: the source frame is empty, so no monitor was computed")
    # (3)-(5) the pre-registered rate/count bars.
    if unmatched_rate is not None and unmatched_rate > thresholds.max_unmatched_rate:
        reasons.append(
            f"unmatched_rate={unmatched_rate:.4f} exceeds {thresholds.max_unmatched_rate:.4f}"
        )
    if low_conf_rate is not None and low_conf_rate > thresholds.max_low_confidence_rate:
        reasons.append(
            f"low_confidence_rate={low_conf_rate:.4f} exceeds {thresholds.max_low_confidence_rate:.4f}"
        )
    if (
        thresholds.max_high_value_unmatched is not None
        and high_value_unmatched > thresholds.max_high_value_unmatched
    ):
        reasons.append(
            f"high_value_unmatched_count={high_value_unmatched} exceeds "
            f"{thresholds.max_high_value_unmatched}"
        )

    report = MonitorReport(
        source_name=source_name,
        n_input_rows=int(n_input_rows),
        n_output_rows=n_out,
        n_matched=n_matched,
        unmatched_rate=None if unmatched_rate is None else round(unmatched_rate, 6),
        low_confidence_rate=None if low_conf_rate is None else round(low_conf_rate, 6),
        high_value_unmatched_count=high_value_unmatched,
        silent_drop_count=silent_drop,
        evaluated=evaluated,
        fail_closed=bool(reasons),
        reasons=reasons,
        by_method=by_method,
    )
    if report.fail_closed:
        log.warning(
            "ALERT [nfl/entity] source=%s FAIL-CLOSED: %s", source_name, "; ".join(reasons)
        )
    return report


def assert_fail_closed(report: MonitorReport) -> None:
    """Raise when the report says the build must not proceed. Callers that want to continue on a
    degraded (but not failing) resolution simply do not call this."""
    if report.fail_closed:
        raise EntityResolutionFailClosed(
            f"[{report.source_name}] entity resolution failed closed: " + "; ".join(report.reasons)
        )


def qa_records(resolved: pd.DataFrame, *, source_name: str, context_columns: list[str] | None = None,
                low_confidence_at_or_below: float = LOW_CONFIDENCE_AT_OR_BELOW) -> pd.DataFrame:
    """The §12A QA record: every unmatched row and every low-confidence match, with enough context
    to be actionable by a human (that is what makes it a review queue and not a counter).

    Ordered worst-first — unmatched before low-confidence, then by score — so the top of the file
    is the work.
    """
    if resolved is None or resolved.empty:
        return pd.DataFrame(
            columns=["source_name", "qa_reason", "match_method", "match_confidence", "match_score"]
        )
    matched = resolved["canonical_player_id"].notna()
    conf = pd.to_numeric(resolved["match_confidence"], errors="coerce").fillna(0.0)
    low = matched & (conf <= low_confidence_at_or_below)
    keep = ~matched | low
    if not keep.any():
        return pd.DataFrame(
            columns=["source_name", "qa_reason", "match_method", "match_confidence", "match_score"]
        )

    cols = [c for c in (context_columns or []) if c in resolved.columns]
    out = resolved.loc[keep, cols + ["canonical_player_id", "match_method", "match_confidence", "match_score"]].copy()
    out.insert(0, "qa_reason", ["unmatched" if not m else "low_confidence" for m in matched[keep]])
    out.insert(0, "source_name", source_name)
    # Worst-first, by SEVERITY — not alphabetically. Sorting on `qa_reason` as a string puts
    # "low_confidence" above "unmatched", which buries the rows that carry no answer at all under
    # the rows that at least have a weak one. A review queue whose top is not the worst work is a
    # queue nobody works from the top of.
    out["_severity"] = (out["qa_reason"] == "low_confidence").astype(int)
    return (
        out.sort_values(["_severity", "match_score"], ascending=[True, True], na_position="first")
        .drop(columns=["_severity"])
        .reset_index(drop=True)
    )


def degraded_frame(resolved: pd.DataFrame) -> pd.DataFrame:
    """The rows a consumer must serve at the LOWER data tier — flagged, never zeroed."""
    if resolved is None or resolved.empty or "source_degraded" not in resolved.columns:
        return resolved.iloc[0:0] if resolved is not None else pd.DataFrame()
    return resolved[resolved["source_degraded"].astype("boolean").fillna(False).astype(bool)]


def assert_no_silent_zero(
    frame: pd.DataFrame, *, value_columns: list[str], degraded_column: str = "source_degraded"
) -> None:
    """Fail if a source-DEGRADED row carries a real numeric value in a resolution-dependent column.

    This is the mechanical guard against the exact defect NF-W0c found: `coalesce(offense_pct, 0.0)`
    turns an unresolved identity into a 0.0 snap share that is indistinguishable from an observed
    "dressed, played no snaps". A degraded row must carry NULL, so the absence is VISIBLE.
    """
    if frame is None or frame.empty or degraded_column not in frame.columns:
        return
    degraded = frame[degraded_column].astype("boolean").fillna(False).astype(bool)
    if not degraded.any():
        return
    offenders: list[str] = []
    for col in value_columns:
        if col not in frame.columns:
            continue
        bad = int(frame.loc[degraded, col].notna().sum())
        if bad:
            offenders.append(f"{col}={bad} rows")
    if offenders:
        raise EntityResolutionFailClosed(
            "source-degraded rows carry non-NULL resolution-dependent values ("
            + ", ".join(offenders)
            + "); an unresolved identity must fall back and be FLAGGED, never silently zeroed "
            "(v3 §12A)"
        )
