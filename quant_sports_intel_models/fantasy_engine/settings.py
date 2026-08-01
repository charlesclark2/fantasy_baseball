"""settings.py — the SPORT-AGNOSTIC settings CATALOG + honest COVERAGE machinery (NF-C0b).

NF-C0b lets a user hand-enter their league's real settings when a platform import can't reach them.
That immediately creates a problem the preset path never had: **a real league scores things we do not
project.** A Sleeper league pays for a defensive forced fumble and a fumble-recovery TD; our season
projection has no such column. The `scoring` module's `_stat_series` returns an all-zero term for an
absent column, so those settings would be accepted, stored, and then SILENTLY SCORE ZERO — the user
would see a number that looks like it honoured their league and does not.

This module is the fix, and it is deliberately MECHANICAL rather than documentary. A term's coverage is
DERIVED from the projection columns that actually exist, never hand-declared:

  * ``APPLIED``    — the profile maps the stat to a column the projection frame really has, so the
                     weight moves the number exactly.
  * ``DERIVED``    — the league expresses a term at FINER resolution than the projection does (the
                     motivating case: a 6-bucket field-goal table over a projection that resolves FG
                     at 0-39 / 40-49 / 50+). The fine weights are folded onto the projected buckets.
                     ⭐ The fold is EXACT whenever the fine values inside a projected bucket agree —
                     which is the common real-world case, because almost every league pays the same
                     for a 25- and a 35-yarder. It is only an approximation when they genuinely
                     differ, and it says so (`exact=False`) rather than quietly rounding.
  * ``CAPTURED``   — the league scores it and we do not project it. The weight is stored verbatim so
                     the config stays faithful and portable, and it contributes NOTHING to the board.
                     The UI contract is to render these as captured-not-applied.

The honest frame the story asks for is therefore enforced by code: a term cannot become "applied" by
someone writing that it is — only by a projection column existing for it.

Nothing here is NFL-specific. A sport supplies its own catalog + derived-bucket table; the engine only
knows "this stat key has a column" / "it doesn't".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from quant_sports_intel_models.fantasy_engine.league_config import ScoringRules, SportProfile

# Coverage verdicts (also the exact strings the API/UI render — keep them stable).
APPLIED = "applied"
DERIVED = "derived"
CAPTURED = "captured"


@dataclass(frozen=True)
class StatTerm:
    """One configurable scoring term in the editor's catalog.

    `key` is the canonical stat key the `ScoringRules.per_stat` map uses; `group`/`label`/`help` are
    presentation only. `default` is the modal league value, used to seed a fresh custom config.
    """

    key: str
    label: str
    group: str
    default: float = 0.0
    help: str = ""
    # Optional UI grouping: several catalog keys that a real platform presents as ONE control. The
    # motivating case is a points-allowed tier table — our nine buckets are the common refinement of
    # the ESPN and Yahoo schemes, so a league whose table says "14-20" sets two of our buckets to the
    # same value. That is an EXACT restatement (not an approximation), which is why it is a display
    # concern here and not a `DerivedBucket`: the editor writes both keys, the engine sees the nine.
    merge_group: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "group": self.group,
            "default": float(self.default),
            "help": self.help,
            "merge_group": self.merge_group,
        }


@dataclass(frozen=True)
class DerivedBucket:
    """A FINE scoring bucket the league expresses that folds onto a COARSER projected bucket.

    `share` is the nominal fraction of the projected bucket's attempts that fall in this fine bucket.
    ⚠️ It is used ONLY to combine fine weights that DISAGREE — when they agree the fold is exact and
    the share is irrelevant to the result. It is a stated modelling assumption, not a measured
    quantity, which is why the resolver reports `exact=False` the moment it actually matters.
    """

    fine_key: str
    projected_key: str
    share: float


@dataclass(frozen=True)
class TermCoverage:
    key: str
    verdict: str
    weight: float
    # for DERIVED terms: which projected bucket absorbed it, and whether the fold was lossless
    projected_key: str | None = None
    exact: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "verdict": self.verdict,
            "weight": float(self.weight),
            "projected_key": self.projected_key,
            "exact": bool(self.exact),
            "note": self.note,
        }


@dataclass(frozen=True)
class CoverageReport:
    """What the engine will and will not do with a config — the payload the UI renders verbatim."""

    terms: tuple[TermCoverage, ...] = ()
    captured_rules: tuple[str, ...] = ()

    def by_verdict(self, verdict: str) -> tuple[TermCoverage, ...]:
        return tuple(t for t in self.terms if t.verdict == verdict)

    @property
    def has_approximation(self) -> bool:
        return any(t.verdict == DERIVED and not t.exact for t in self.terms)

    def to_dict(self) -> dict:
        return {
            "terms": [t.to_dict() for t in self.terms],
            "captured_rules": list(self.captured_rules),
            "has_approximation": self.has_approximation,
        }


def _nonzero(weight: float) -> bool:
    return abs(float(weight)) > 1e-12


def resolve_scoring(
    scoring: ScoringRules,
    profile: SportProfile,
    *,
    derived_buckets: tuple[DerivedBucket, ...] = (),
    available_columns: frozenset[str] | None = None,
    captured_rules: tuple[str, ...] = (),
) -> tuple[ScoringRules, CoverageReport]:
    """Fold a league's scoring onto what the projection can actually express + report the coverage.

    Returns `(resolved_scoring, report)`. `resolved_scoring` is what the scorer should run: fine
    buckets collapsed onto their projected buckets, everything else passed through unchanged.
    `report` classifies EVERY non-zero term the user set as applied / derived / captured.

    `available_columns` — when supplied, the columns the projection frame REALLY has. This is what
    makes coverage mechanical: a stat mapped in the profile but missing from the frame is `CAPTURED`,
    not `APPLIED`, so a projection that silently loses a column downgrades honestly instead of
    scoring zero behind an "applied" label.
    """

    def _is_projected(stat_key: str) -> bool:
        column = profile.stat_columns.get(stat_key)
        if column is None:
            return False
        return True if available_columns is None else column in available_columns

    fine_map = {b.fine_key: b for b in derived_buckets}
    # group the fine buckets by the projected bucket that absorbs them
    by_projected: dict[str, list[DerivedBucket]] = {}
    for b in derived_buckets:
        by_projected.setdefault(b.projected_key, []).append(b)

    per_stat = dict(scoring.per_stat)
    resolved: dict[str, float] = {}
    terms: list[TermCoverage] = []

    # ── 1. fold the fine buckets the user actually set ────────────────────────────────────────────
    handled_fine: set[str] = set()
    for projected_key, buckets in by_projected.items():
        present = [b for b in buckets if b.fine_key in per_stat]
        if not present:
            continue
        if not _is_projected(projected_key):
            # the coarse bucket itself isn't projected → the whole family is captured-only
            for b in present:
                handled_fine.add(b.fine_key)
                terms.append(
                    TermCoverage(
                        key=b.fine_key,
                        verdict=CAPTURED,
                        weight=float(per_stat[b.fine_key]),
                        note="no projection backs this scoring term",
                    )
                )
            continue

        values = [float(per_stat[b.fine_key]) for b in present]
        exact = max(values) - min(values) <= 1e-9
        if exact:
            folded = values[0]
        else:
            total_share = sum(max(0.0, b.share) for b in present)
            folded = (
                sum(float(per_stat[b.fine_key]) * max(0.0, b.share) for b in present) / total_share
                if total_share > 0
                else sum(values) / len(values)
            )
        resolved[projected_key] = folded
        for b in present:
            handled_fine.add(b.fine_key)
            terms.append(
                TermCoverage(
                    key=b.fine_key,
                    verdict=DERIVED,
                    weight=float(per_stat[b.fine_key]),
                    projected_key=projected_key,
                    exact=exact,
                    note=(
                        ""
                        if exact
                        else "the projection resolves this stat more coarsely, so buckets that "
                        "score differently are combined by their attempt share"
                    ),
                )
            )

    # ── 2. everything else passes through, classified against the real columns ────────────────────
    for key, weight in per_stat.items():
        if key in handled_fine:
            continue
        if key in resolved:
            # a coarse key the user ALSO set explicitly — the fine buckets are the finer, more
            # specific statement of the same rule, so they win. Say so rather than silently dropping.
            terms.append(
                TermCoverage(
                    key=key,
                    verdict=DERIVED,
                    weight=float(weight),
                    projected_key=key,
                    exact=True,
                    note="superseded by the per-bucket values set for this stat",
                )
            )
            continue
        resolved[key] = float(weight)
        if not _nonzero(weight):
            continue  # a zeroed term is a non-statement; don't clutter the report
        terms.append(
            TermCoverage(
                key=key,
                verdict=APPLIED if _is_projected(key) else CAPTURED,
                weight=float(weight),
                note="" if _is_projected(key) else "no projection backs this scoring term",
            )
        )

    # position bonuses ride along untouched (they are per-position deltas on keys already classified)
    out = ScoringRules(per_stat=resolved, position_bonuses=dict(scoring.position_bonuses))
    terms.sort(key=lambda t: (t.verdict, t.key))
    return out, CoverageReport(terms=tuple(terms), captured_rules=tuple(captured_rules))


def catalog_to_dict(catalog: tuple[StatTerm, ...]) -> list[dict]:
    return [t.to_dict() for t in catalog]


__all__ = [
    "APPLIED",
    "CAPTURED",
    "DERIVED",
    "CoverageReport",
    "DerivedBucket",
    "StatTerm",
    "TermCoverage",
    "catalog_to_dict",
    "resolve_scoring",
]
